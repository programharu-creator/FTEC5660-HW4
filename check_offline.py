"""Inspect parsing and retrieval with the course scorers and zero API calls. Author: eula."""
from pathlib import Path
import argparse
import json
import os
import time


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--variant', default='V6')
    parser.add_argument('--data-folder', default='public_test')
    parser.add_argument('--output', default='.cache/offline.json')
    args = parser.parse_args()
    os.environ['HW4_VARIANT'] = args.variant
    import hw4 as hw
    start = time.perf_counter()
    folder = Path(args.data_folder)
    corpus = hw.load_corpus(folder/'corpus')
    questions = hw.load_json(folder/'questions.json')
    truth = hw.load_json(folder/'ground_truth.json')
    docs = hw.load_json(folder/'docs.json')
    tables = hw.load_json(folder/'tables.json')
    table_scores = [hw.table_score(hw.table_to_text(t['html']), t) for t in tables]
    by_file = {name: hw.chunk_document(name, html) for name, html in corpus.items()}
    document_errors = {name: problems for name, meta in docs.items()
                       if (problems := hw.document_problems(by_file[name], None, meta, name))}
    chunks = [chunk for values in by_file.values() for chunk in values]
    parsed = {qid: hw.parse_query(question) for qid, question in questions.items()}
    index = hw.build_index(chunks)
    parse_errors, misses, rejected, kept = [], [], [], []
    hits = 0
    answerable = sum(bool(gold['evidence']) for gold in truth.values())
    unanswerable = len(truth)-answerable
    for qid, question in questions.items():
        gold = truth[qid]
        if hw.parse_score(parsed[qid], gold) < 1:
            parse_errors.append({'id': qid, 'question': question, 'parsed': parsed[qid], 'expected': gold['query']})
        found = hw.retrieve(index, question)
        assert len(found) <= hw.MAX_RETRIEVED
        assert all(id(chunk) in {id(c) for c in chunks} for chunk in found)
        if gold['evidence']:
            if found:kept.append(qid)
            if hw.retrieval_hit(found, gold):hits += 1
            else:misses.append({'id': qid, 'question': question, 'empty': not found,
                                'sources': [c.metadata['source'] for c in found],
                                'content': [c.page_content[:400] for c in found]})
        elif not found:
            rejected.append(qid)
    assert hw.USAGE.llm_calls == hw.GENERATOR_USAGE.llm_calls == 0
    summary={'author':'eula','variant':args.variant,'table_mean':sum(table_scores)/len(table_scores),
             'document_pass_rate':1-len(document_errors)/len(docs),'chunks':len(chunks),
             'longest_chunk':max(map(lambda c:len(c.page_content),chunks)),
             'parse_mean':sum(hw.parse_score(parsed[qid],gold) for qid,gold in truth.items())/len(truth),
             'recall_at_5':hits/answerable,'answerable_kept':len(kept)/answerable,
             'unanswerable_rejected':len(rejected)/unanswerable,'elapsed_seconds':time.perf_counter()-start,
             'model_calls':0,'table_scores':table_scores,'document_errors':document_errors,
             'parse_errors':parse_errors,'retrieval_misses':misses,'rejected_ids':rejected}
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(summary,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ['retrieval_misses','rejected_ids']},indent=2,ensure_ascii=False))
    print('Retrieval misses:',[(row['id'],row['empty']) for row in misses])


if __name__=='__main__':main()
