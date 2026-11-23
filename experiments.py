"""Run cumulative variants through the original course runner. Author: eula."""
from __future__ import annotations

import argparse
import contextlib
import csv
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent
VARIANTS = ('B0', 'V1', 'V2a', 'V2', 'V3', 'V4', 'V5', 'V6')


class Tee:
    def __init__(self, file, console):
        self.file, self.console, self.lock = file, console, threading.Lock()
        self.secret = os.environ.get('DEEPSEEK_API_KEY', '')

    def write(self, value):
        safe = value.replace(self.secret, '[redacted]') if self.secret else value
        with self.lock:
            self.file.write(safe)
            self.console.write(safe)
            self.file.flush()
            self.console.flush()
        return len(value)

    def flush(self):
        self.file.flush()
        self.console.flush()


def run_variant(args):
    started = time.perf_counter()
    os.environ['HW4_VARIANT'] = args.variant
    import hw4 as hw
    output = Path(args.out) if args.out else ROOT/'experiments'/args.variant
    output = output.resolve()
    if (output/'summary.json').exists():
        raise FileExistsError('Preserving existing run: '+str(output))
    output.mkdir(parents=True, exist_ok=True)
    folder = Path(args.data_folder).resolve()
    corpus = hw.load_corpus(folder/'corpus')
    questions = hw.load_json(folder/'questions.json')
    gold = hw.load_json(folder/'ground_truth.json')
    table_tests = hw.load_json(folder/'tables.json')
    document_tests = hw.load_json(folder/'docs.json')
    by_question = {question: qid for qid, question in questions.items()}
    saved_chunks, saved_retrieval, generator_records = {}, {}, {}
    original_chunk, original_retrieve, original_generate = hw.chunk_document, hw.retrieve, hw.generate
    progress_lock = threading.Lock()

    def capture_chunks(file_name, html):
        result = original_chunk(file_name, html)
        saved_chunks[file_name] = result
        return result

    def capture_retrieval(index, question):
        result = original_retrieve(index, question)
        saved_retrieval[by_question[question]] = list(result)
        return result

    def capture_generation(question, chunks):
        call_start = time.perf_counter()
        record = {'status': 'complete'}
        try:
            answer = original_generate(question, chunks)
            record['answer'] = answer
            return answer
        except Exception as error:
            record.update(status='failed', error_type=type(error).__name__, error=str(error))
            raise
        finally:
            record['seconds'] = time.perf_counter()-call_start
            with progress_lock:
                generator_records[by_question[question]] = record
                if len(generator_records) % 10 == 0:
                    print(f'{args.variant}: completed {len(generator_records)}/{len(questions)} answer attempts', flush=True)

    hw.chunk_document, hw.retrieve, hw.generate = capture_chunks, capture_retrieval, capture_generation
    sys.argv = ['hw4.py', '--data-folder', str(folder), '--output', str(output/'results.csv')]
    with (output/'run.log').open('w', encoding='utf-8') as log:
        tee = Tee(log, sys.stdout)
        with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
            hw.main()
    rows = list(csv.DictReader((output/'results.csv').open(encoding='utf-8', newline='')))
    assert len(rows) == len(questions)
    truthy = lambda value: str(value).casefold() == 'true'
    answerable = [row for row in rows if gold[row['id']]['evidence']]
    unanswerable = [row for row in rows if not gold[row['id']]['evidence']]
    recall = sum(truthy(row['retrieval_hit']) for row in answerable)/len(answerable)
    kept = sum(bool(saved_retrieval[row['id']]) for row in answerable)/len(answerable)
    rejected = sum(not saved_retrieval[row['id']] for row in unanswerable)/len(unanswerable)
    valid = sum(truthy(row['valid']) and bool(saved_retrieval[row['id']]) for row in answerable)/len(answerable)
    parse_mean = sum(float(row['parse_score']) for row in rows)/len(rows)
    accuracy = sum(truthy(row['correct']) for row in rows)/len(rows)
    table_mean = sum(hw.table_score(hw.table_to_text(t['html']), t) for t in table_tests)/len(table_tests)
    document_problems = {name: problem for name, meta in document_tests.items()
                         if (problem := hw.document_problems(saved_chunks[name], None, meta, name))}
    document_pass = 1-len(document_problems)/len(document_tests)
    points = {'1.1': 8*table_mean, '1.2': 7*document_pass, '2.1': 5*valid,
              '2.2': 10*parse_mean, '2.3': 15*hw.clip((recall-.5)/.4),
              '3': 10*hw.clip(kept+rejected-1), '4': 20*accuracy}
    errors = [qid for qid, record in generator_records.items() if record['status'] == 'failed']
    corpus_digest = hashlib.sha256()
    for name, html in sorted(corpus.items()):
        corpus_digest.update(name.encode()+b'\0'+html.encode()+b'\0')
    source = (ROOT/'hw4.py').read_text(encoding='utf-8')
    marker = '# Provided code below. Do not change it.'
    by_category = {}
    for category in sorted({row['category'] for row in rows}):
        selected = [row for row in rows if row['category'] == category]
        relevant = [row for row in selected if row['retrieval_hit'] != '']
        by_category[category] = {'n': len(selected), 'correct': sum(truthy(row['correct']) for row in selected),
                                 'accuracy': sum(truthy(row['correct']) for row in selected)/len(selected),
                                 'recall_at_5': sum(truthy(row['retrieval_hit']) for row in relevant)/len(relevant) if relevant else None}
    summary = {'author': 'eula', 'variant': args.variant, 'status': 'failed' if errors else 'complete',
               'finished_at_utc': datetime.now(timezone.utc).isoformat(), 'question_count': len(rows),
               'correct': sum(truthy(row['correct']) for row in rows), 'accuracy': accuracy,
               'recall_at_5': recall, 'parse_mean': parse_mean, 'answerable_kept': kept,
               'unanswerable_rejected': rejected, 'valid_nonempty': valid,
               'table_mean': table_mean, 'document_pass_rate': document_pass,
               'chunks': sum(map(len, saved_chunks.values())), 'points': points, 'total_automatic_points': sum(points.values()),
               'wall_seconds': time.perf_counter()-started, 'usage': hw.USAGE.summary(),
               'generator_usage': hw.GENERATOR_USAGE.summary(), 'generator_errors': errors,
               'by_category': by_category, 'document_problems': document_problems,
               'model': hw.LLM_MODEL, 'temperature': 0, 'thinking': False, 'generator_max_tokens': 64,
               'source_sha256_lf': hashlib.sha256(source.encode()).hexdigest(),
               'provided_code_sha256_lf': hashlib.sha256(source[source.index(marker):].encode()).hexdigest(),
               'corpus_sha256_lf': corpus_digest.hexdigest(), 'python': platform.python_version(),
               'packages': {package: importlib.metadata.version(package) for package in
                            ['langchain-core', 'langchain-deepseek', 'beautifulsoup4', 'rank-bm25', 'langchain-text-splitters']},
               'cost_note': 'Estimated USD using the input/output prices in the course runner; actual billing may differ.'}
    with (output/'retrieval_trace.jsonl').open('w', encoding='utf-8') as file:
        for qid, question in questions.items():
            trace = {'author': 'eula', 'id': qid, 'question': question,
                     'chunks': [{'page_content': c.page_content, 'metadata': c.metadata} for c in saved_retrieval[qid]],
                     'generation': generator_records.get(qid)}
            file.write(json.dumps(trace, ensure_ascii=False)+'\n')
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({key: summary[key] for key in ['variant', 'status', 'accuracy', 'recall_at_5', 'total_automatic_points', 'wall_seconds']}, indent=2))
    if errors:
        raise RuntimeError('Provider errors retained in '+str(output))
    if summary['wall_seconds'] >= 1800:
        raise RuntimeError('Run exceeded the course time limit')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--variant', choices=VARIANTS, default='V6')
    parser.add_argument('--data-folder', default='public_test')
    parser.add_argument('--out')
    parser.add_argument('--output-root', default='experiments')
    args = parser.parse_args()
    if args.all:
        if args.out:
            raise ValueError('Use --out with one variant')
        for variant in VARIANTS:
            subprocess.run([sys.executable, '-X', 'utf8', str(Path(__file__).resolve()),
                            '--variant', variant, '--data-folder', args.data_folder,
                            '--out', str(Path(args.output_root)/variant)], cwd=ROOT,
                           env={**os.environ, 'PYTHONUTF8': '1'}, check=True, timeout=1800)
        shutil.copyfile(ROOT/args.output_root/'V6/results.csv', ROOT/'results.csv')
    else:
        run_variant(args)


if __name__ == '__main__':
    main()
