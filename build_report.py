"""Build the README report from the saved course-runner outputs. Author: eula."""
from pathlib import Path
import csv
import hashlib
import json
import re
from html import escape

ROOT = Path(__file__).resolve().parent
ORDER = ['B0','V1','V2a','V2','V3','V4','V5','V6']
CHANGES = {
    'B0':'Required naive baseline',
    'V1':'Add table row, column and unit text',
    'V2a':'Add section and table aware chunk boundaries',
    'V2':'Add contextual headers to the same chunks',
    'V3':'Add question parsing and metadata filtering',
    'V4':'Add the financial lexical normalizer',
    'V5':'Add balanced retrieval for comparisons',
    'V6':'Add the evidence support check',
}


def load(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def pct(value):
    return f'{100*value:.1f}%'


def pipeline_svg():
    boxes=[(25,35,'HTML reports','Supplied document text'),(325,35,'Parse tables','Preserve rows, columns and units'),
           (625,35,'Create chunks','Sections, tables and metadata'),(925,35,'Build lexical index','BM25 in memory'),
           (25,190,'Parse the question','Company, year and document type'),(325,190,'Filter candidates','Exact company and year coverage'),
           (625,190,'Rank and balance','Financial terms and each company'),(925,190,'Check support','Required topic words in evidence'),
           (625,345,'Up to five chunks','Original chunk objects'),(925,345,'Fixed course generator','Answer or NOT_FOUND')]
    lines=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="490" viewBox="0 0 1200 490">',
           '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>eula</dc:creator></metadata>',
           '<title>Homework 4 retrieval pipeline</title>',
           '<rect width="1200" height="490" fill="#f5f7f8"/>',
           '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#087f83"/></marker></defs>']
    for x1,y1,x2,y2 in [(275,80,325,80),(575,80,625,80),(875,80,925,80),(275,235,325,235),
                          (575,235,625,235),(875,235,925,235),(1050,125,1050,157),
                          (1050,157,450,157),(450,157,450,190),
                          (1050,280,1050,310),(1050,310,750,310),(750,310,750,345),(875,390,925,390)]:
        lines.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="#087f83" stroke-width="2" marker-end="url(#arrow)"/>')
    for x,y,title,description in boxes:
        lines.append(f'<rect x="{x}" y="{y}" width="250" height="90" rx="12" fill="white" stroke="#b9d3d4"/>')
        lines.append(f'<text x="{x+15}" y="{y+32}" font-family="Arial,sans-serif" font-size="19" font-weight="bold" fill="#142536">{escape(title)}</text>')
        lines.append(f'<text x="{x+15}" y="{y+61}" font-family="Arial,sans-serif" font-size="13" fill="#526875">{escape(description)}</text>')
    lines.extend(['<text x="25" y="385" font-family="Arial,sans-serif" font-size="17" fill="#142536">Missing company, year or topic support:</text>',
                  '<text x="25" y="416" font-family="Arial,sans-serif" font-size="17" fill="#087f83">Return [] and the runner produces NOT_FOUND.</text>',
                  '<text x="25" y="467" font-family="Arial,sans-serif" font-size="12" fill="#526875">Author: eula. Retrieval uses the supplied HTML and question; the fixed generator is provided by the course.</text>','</svg>'])
    return '\n'.join(lines)+'\n'


def main():
    report=ROOT/'report';report.mkdir(exist_ok=True)
    summaries={mode:load(f'experiments/{mode}/summary.json') for mode in ORDER}
    final=summaries['V6'];fresh=load('experiments/final_fresh_clone/summary.json')
    assert final['status']==fresh['status']=='complete' and final['correct']==fresh['correct']==60
    assert {s['corpus_sha256_lf'] for s in summaries.values()}=={final['corpus_sha256_lf']}
    assert len({s['provided_code_sha256_lf'] for s in summaries.values()})==1
    (report/'pipeline.svg').write_text(pipeline_svg(),encoding='utf-8')
    rows={mode:{row['id']:row for row in csv.DictReader((ROOT/f'experiments/{mode}/results.csv').open(encoding='utf-8',newline=''))} for mode in ORDER}
    with (report/'ablation.csv').open('w',encoding='utf-8',newline='') as file:
        writer=csv.DictWriter(file,fieldnames=['variant','change','correct','questions','accuracy','recall_at_5','parse_mean','answerable_kept','unanswerable_rejected','chunks','generator_calls','input_tokens','output_tokens','estimated_usd','wall_seconds'])
        writer.writeheader()
        for mode,s in summaries.items():
            usage=s['generator_usage']
            writer.writerow(dict(variant=mode,change=CHANGES[mode],correct=s['correct'],questions=s['question_count'],accuracy=s['accuracy'],recall_at_5=s['recall_at_5'],parse_mean=s['parse_mean'],answerable_kept=s['answerable_kept'],unanswerable_rejected=s['unanswerable_rejected'],chunks=s['chunks'],generator_calls=usage['llm_calls'],input_tokens=usage['llm_input_tokens'],output_tokens=usage['llm_output_tokens'],estimated_usd=usage['cost_usd'],wall_seconds=s['wall_seconds']))
    with (report/'error_analysis.csv').open('w',encoding='utf-8',newline='') as file:
        fields=['previous','current','id','category','question','previous_answer','current_answer','previous_correct','current_correct','previous_retrieval_hit','current_retrieval_hit','previous_sources','current_sources']
        writer=csv.DictWriter(file,fieldnames=fields);writer.writeheader()
        for previous,current in zip(ORDER,ORDER[1:]):
            for qid,before in rows[previous].items():
                after=rows[current][qid]
                if before['correct']==after['correct'] and before['retrieval_hit']==after['retrieval_hit'] and bool(before['retrieved'])==bool(after['retrieved']):continue
                writer.writerow(dict(previous=previous,current=current,id=qid,category=before['category'],question=before['question'],previous_answer=before['answer'],current_answer=after['answer'],previous_correct=before['correct'],current_correct=after['correct'],previous_retrieval_hit=before['retrieval_hit'],current_retrieval_hit=after['retrieval_hit'],previous_sources=before['retrieved'],current_sources=after['retrieved']))
    all_runs=[load(str(path.relative_to(ROOT)).replace('\\','/')) for path in sorted((ROOT/'experiments').glob('*/summary.json'))]
    smoke=load('.cache/api_smoke.json' if (ROOT/'.cache/api_smoke.json').exists() else 'report/api_smoke.json')
    calls=sum(s['usage']['llm_calls']+s['generator_usage']['llm_calls'] for s in all_runs)+smoke['usage']['llm_calls']
    inputs=sum(s['usage']['llm_input_tokens']+s['generator_usage']['llm_input_tokens'] for s in all_runs)+smoke['usage']['llm_input_tokens']
    outputs=sum(s['usage']['llm_output_tokens']+s['generator_usage']['llm_output_tokens'] for s in all_runs)+smoke['usage']['llm_output_tokens']
    usage={'author':'eula','primary_variant_calls':sum(s['generator_usage']['llm_calls'] for s in summaries.values()),'fresh_clone_runs':2,'smoke_calls':smoke['usage']['llm_calls'],'all_paid_calls':calls,'all_input_tokens':inputs,'all_output_tokens':outputs,'estimated_usd_course_prices':(inputs*.15+outputs*.60)/1e6,'note':'Includes the eight primary rows, two fresh-clone checks and the API smoke. Prices are the provided course estimates.'}
    (report/'usage_accounting.json').write_text(json.dumps(usage,indent=2)+'\n',encoding='utf-8')
    (report/'api_smoke.json').write_text(json.dumps(smoke,indent=2)+'\n',encoding='utf-8')
    table=['| Version | One change from the previous row | Correct / 60 | Accuracy | Recall@5 | Query fields | Kept | Rejected |',
           '|---|---|---:|---:|---:|---:|---:|---:|']
    costs=['| Version | Chunks | Generator calls | Input tokens | Output tokens | Estimated USD | Wall seconds |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for mode,s in summaries.items():
        table.append(f"| {mode} | {CHANGES[mode]} | {s['correct']}/60 | {pct(s['accuracy'])} | {pct(s['recall_at_5'])} | {pct(s['parse_mean'])} | {pct(s['answerable_kept'])} | {pct(s['unanswerable_rejected'])} |")
        u=s['generator_usage'];costs.append(f"| {mode} | {s['chunks']} | {u['llm_calls']} | {u['llm_input_tokens']:,} | {u['llm_output_tokens']:,} | {u['cost_usd']:.4f} | {s['wall_seconds']:.2f} |")
    category=['| Question category | Correct / questions | Accuracy |','|---|---:|---:|']
    for name,values in final['by_category'].items():category.append(f"| {name} | {values['correct']}/{values['n']} | {pct(values['accuracy'])} |")
    saving=100*(1-final['generator_usage']['llm_input_tokens']/summaries['B0']['generator_usage']['llm_input_tokens'])
    text='''# FTEC5660 Homework 4

Author: eula

Student: SANG Yuchen

Student ID: 1155262204

The implementation supplies the five required functions in hw4.py. The final V6 configuration answered all 60 public questions correctly and received 75/75 estimated automatic points from the provided runner, with a second check on the final source from a fresh local clone. The private set and the 25 points assessed by the TAs remain outside these measured results.

## Install and run

Use Python 3.10 or newer; the recorded environment is Python 3.12.12. From this repository's root, create an environment with `python -m venv .venv`, then activate it with `.\\.venv\\Scripts\\Activate.ps1` on Windows or `source .venv/bin/activate` on macOS/Linux.

```text
python -m pip install -r requirements.txt
```

Copy .env.example to .env and set your own DEEPSEEK_API_KEY locally. The course runner uses deepseek-v4-flash through the original client. The Python 3.12 package versions used in the experiments are recorded separately in requirements-lock.txt.

```text
python hw4.py --data-folder public_test
```

This command builds the index from the supplied HTML, uses V6 by default, and writes results.csv. The index exists in memory during a run. The .env file, environment directory and local caches are ignored by Git. The submitted results.csv is the byte-for-byte copy of the measured V6 output in experiments/V6/results.csv.

```text
python -m unittest test_hw4 -v
python check_offline.py --variant V6 --output .cache/offline.json
```

Both checks above use zero model calls. To reproduce every ablation in new folders while preserving the supplied measurements:

```text
python experiments.py --all --output-root .cache/reproduction
```

To measure one configuration, use `python experiments.py --variant V3 --out .cache/my_V3_run`. Existing completed run folders are preserved. Each measured run uses the original course runner, generator and scorers, with observation wrappers saving the selected context and progress. Every generator call uses the provided course client.

## Homework 4 solution

### Pipeline and design

![Retrieval pipeline](report/pipeline.svg)

The parser reads the document heading to identify its company, report year and document type, and it converts tables into lines that retain their caption, row label, column label and printed values. Section and table boundaries guide chunks of at most 1,500 characters, while short headers preserve the company, document year and section within the searchable text. Company and broker catalogues come from the supplied HTML. The question parser identifies requested companies, including unfamiliar names, the requested year and document type. Candidate filtering uses the year coverage of each document, so a previous-year annual figure or a future estimate can come from a report with a different fiscal year. BM25 then ranks canonical financial words after query scaffolding and already-filtered entity/date terms are removed. Comparison retrieval allocates results across each requested company, and a lexical support check returns an empty list when required topic words lack support in the eligible documents. The final result contains up to five original chunk objects for the fixed generator.

### Controlled cumulative comparison

The eight rows use the same 40 documents and 60 public questions, the same fixed generator, temperature 0, thinking disabled, a 64-token output limit, and the original eight-worker runner. Each row adds one component. B0 uses BeautifulSoup get_text, RecursiveCharacterTextSplitter with chunk_size 1200 and chunk_overlap 160, the required metadata, whitespace-token BM25 top five over the whole corpus, an empty question parser and a policy that always retrieves chunks. All retrieval components use zero model calls. The financial normalizer is one text preprocessing component, covering word forms, financial synonyms and removal of query scaffolding after metadata filtering.

'''+ '\n'.join(table)+'''

Recall@5 uses the 46 answerable questions and requires every needed fact, including both companies in a comparison. Query fields measure the three fields checked by the course scorer. Kept is the share of answerable questions receiving chunks; rejected is the share of the 14 unanswerable questions receiving an empty list. The reported answer accuracy uses all 60 questions.

The first seven rows were measured before adding the isolating V2a branch. During review, section boundaries and contextual headers were separated so that each row changes one component. V2a uses the same boundaries as V2 while omitting its contextual metadata header. The new source was checked against all 420 earlier question contexts and parsed outputs, which matched exactly; the fixed generator section also remains unchanged. The additional V2a run and both original and final fresh-clone checks are retained. Details are in experiment_plan.json and report/context_equivalence.json.

### Resource measurements

'''+ '\n'.join(costs)+f'''

All runs finished well within the 30-minute limit. Wall time includes module initialization and the wrapped course run, while the individual run logs also retain the runner's stage timings. Input use fell by {saving:.1f}% between B0 and V6. The USD values use the course price constants and represent estimates; the provider's actual billing can differ. Each configuration was measured once at temperature zero, so these times are descriptive and hosted-model variability remains a limitation. The eight primary rows used {usage['primary_variant_calls']} generator calls, and the complete work including two fresh-clone checks and the API smoke used {calls} paid calls with an estimated course-price cost of USD {usage['estimated_usd_course_prices']:.4f}.

### Analysis of each change

1. Table conversion in V1 reduced accuracy from 53.3% to 38.3% and recall from 37.0% to 19.6%. Expanding rows with labels and years changed the fixed splitter's boundaries and BM25 token statistics while the baseline still used unfiltered whitespace queries. Preserving table structure alone therefore provided limited benefit within that naive ranking configuration.
2. Section and table boundaries in V2a raised accuracy to 43.3% and recall to 28.3%, while many table chunks still lacked searchable company identity. Adding the short contextual header in V2 raised these to 85.0% and 80.4% with exactly the same chunk boundaries, showing the importance of retaining identity and section information in lexical search.
3. V3 reached 93.3% accuracy and 91.3% recall after filtering companies, document types and covered years. The same component rejected the five unsupported company questions and five unsupported year questions, giving 71.4% rejection of unanswerable questions.
4. V4 recovered the remaining four answerable evidence misses through the financial lexical normalizer, reaching 100% recall and accuracy. Focusing the query on the financial subject reduced interference from repeated company names, dates and question wording.
5. V5 retained 100% accuracy and recall. Balanced comparison allocation produced no marginal score gain on this public sample, where V4 already retrieved every required comparison fact. It remains a structural coverage safeguard, supported by the separate comparison test.
6. V6 retained 100% answer accuracy and increased retrieval rejection to 100%. V5's fixed generator already answered NOT_FOUND on the remaining undisclosed figures even though retrieval returned chunks; V6 made that decision earlier, removed four unnecessary generator calls and raised Task 3 from 7.14/10 to 10/10.

### Error analysis

- In q003, the B0 employee comparison was correct, while V1 returned only Payments-related sources and produced NOT_FOUND. Its missing Robotics evidence illustrates why a comparison needs coverage of both companies. Later versions recover the necessary facts, and the final balanced allocation explicitly reserves space for each company.
- In q016, V3 retrieved the correct company document but answered 1724.5 for FY2024 gross profit. V4 answered the correct 1805.4 after retrieving the needed fact with the financial query. Correct file selection alone therefore leaves a risk of missing or confusing a row or year within that file.
- In q054, V3 returned chunks from the correct company report while missing the printed inventory fact. Its answer was NOT_FOUND. V4 retrieved that fact and answered 297.4, demonstrating the benefit of topic-focused lexical matching within the filtered company documents.
- The four undisclosed topics still received chunks in V5, and the fixed generator correctly refused their answers. V6 rejected them at retrieval time. This separates answer accuracy from the abstention score and explains why both measures appear in the table.

The complete changes in correctness, evidence hits and refusal decisions are in report/error_analysis.csv, with per-question chunk text and metadata in every retrieval_trace.jsonl. The final V6 output has no public question errors.

### Final checks and limits

'''+ '\n'.join(category)+'''

All 12 public table tests preserve their labelled cells and captions, and all 40 public documents pass metadata and content coverage checks. The longest final chunk is 1,499 characters. Ten synthetic tests use other company names and years to check multi-level table headers, possessives, similar names, document-year coverage, comparison allocation, unknown subjects, chunk identity and the isolated header comparison. The final source also completed the original end-to-end runner from a fresh clone with an externally supplied key, obtaining 60/60 correct and 75/75 estimated automatic points.

The inference functions derive their inputs from the document HTML and question. Public answer files are used by the provided scorer and evaluation tools. The provided generator, loaders and scoring code remain unchanged below the required boundary, and evidence hashes are supplied in report/evidence_sha256.json. Index data is rebuilt for each supplied corpus and remains in memory.

The public labels informed development, and this sample provides development results with a ceiling at V4. The hidden companies and private scores remain unobserved. Proper-name patterns, word-form aliases and exact topic-word support can miss unfamiliar phrasing or casing, and incidental mentions can satisfy lexical support without establishing that a financial figure is disclosed. A future extension could evaluate paraphrase cases separately and use the permitted model for targeted evidence checks, while keeping the original source chunks and measuring any extra cost. One run per variant also limits conclusions about model variability and timing.

### Evidence files

- report/ablation.csv contains the tabulated measurements.
- experiments/B0 through experiments/V6, including V2a, contain original results.csv, run.log, summary.json and retrieval_trace.jsonl.
- experiments/fresh_clone and experiments/final_fresh_clone retain two end-to-end checks.
- report/context_equivalence.json records the 420-context verification after introducing V2a.
- report/usage_accounting.json includes all paid calls, including the smoke and clone checks.
- requirements-lock.txt records the Python 3.12 environment, and experiment_plan.json records the cumulative design and its revision.

## Reflection

The Task 6 reflection is in [REFLECTION.md](REFLECTION.md). Four connected paragraphs relate finance and FinTech study, securities automation work, consulting and procurement experience, international activities, research and creative interests to the seven reflection questions. AI assistance is disclosed as allowed by the handout, and selected experiences inform the reflection while the original CV stays outside this repository.

## Submission

The handout requires a public fork named FTEC5660-HW4 and its URL on Blackboard by 1 December at 23:59 HKT. Keep the repository public during grading and supply the code, requirements, experiment scripts, this report and the reflection. Local credentials and binary index files are excluded from Git, and the grader supplies its own key.

The source assignment is [hz0567/FTEC5660-HW4](https://github.com/hz0567/FTEC5660-HW4), originally downloaded at commit 89141195ffc63004dec6e8cac1d6ad19e7c862a4. The implementation and measured analysis are by eula for SANG Yuchen, 1155262204.
'''
    assert not re.search('[\u2013\u2014\u201c\u201d]',text)
    (ROOT/'README.md').write_text(text,encoding='utf-8')
    evidence={}
    for path in sorted((ROOT/'experiments').glob('*/*')):
        if path.is_file():evidence[str(path.relative_to(ROOT)).replace('\\','/')]=hashlib.sha256(path.read_bytes()).hexdigest()
    evidence['results.csv']=hashlib.sha256((ROOT/'results.csv').read_bytes()).hexdigest()
    (report/'evidence_sha256.json').write_text(json.dumps({'author':'eula','sha256':evidence},indent=2)+'\n',encoding='utf-8')
    status={'author':'eula','stage':'local_assignment_complete','student':'SANG Yuchen','student_id':'1155262204',
            'primary_variants':ORDER,'final_public_correct':60,'public_questions':60,'estimated_automatic_points':75,
            'automatic_points_available':75,'ta_assessed_points':25,'fresh_clone_verified':True,'model_calls_in_retrieval':0,
            'pending':['Publish the required public fork after browser login.','Submit the public GitHub link on Blackboard.']}
    status_path=ROOT/'submission_status.json'
    if status_path.exists():
        previous=json.loads(status_path.read_text(encoding='utf-8'))
        if previous.get('github_published'):
            status.update(stage='published_ready_for_course_submission',github_published=True,
                          github_url=previous['github_url'],github_visibility='public',github_fork=True,
                          pending=['Review the reflection and submit the public GitHub link on Blackboard.'])
    (ROOT/'submission_status.json').write_text(json.dumps(status,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'primary_rows':len(summaries),'final_accuracy':final['accuracy'],'estimated_automatic_points':final['total_automatic_points'],'all_paid_calls':calls,'estimated_usd':usage['estimated_usd_course_prices'],'evidence_files':len(evidence)},indent=2))


if __name__=='__main__':main()
