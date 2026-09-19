"""Format inputs and invoke unchanged BioASQ Java source; no metric formulas."""
import hashlib
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / 'evals/official-bioasq'
PROJECT = UPSTREAM / 'flat/BioASQEvaluation'
OUT = ROOT / 'evals/results_0915_official'
# Audited capitalization, punctuation and wording variants in the blind sample.
QUESTION_IDS = {
    'list_01':'67d34e2518b1e36f2e000006',
    'list_02':'67e6ba8e18b1e36f2e0000bf',
    'list_03':'67cc973e81b1027333000011',
    'list_04':'67cddce881b102733300001c',
    'summary_01':'67d74cde18b1e36f2e00003c',
    'yesno_02':'67c7708481b1027333000002',
    'yesno_03':'66301d1d187cba990d000026',
    'yesno_04':'662fc277187cba990d000013',
}

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--include-medlit-astra', action='store_true')
    parser.add_argument('--include-v3', action='store_true')
    options = parser.parse_args()
    if options.include_v3:
        options.include_medlit_astra = True
    if options.include_medlit_astra:
        OUT = ROOT / 'evals/results_0915_2_official'
    if options.include_v3:
        OUT = ROOT / 'evals/results_0915_v3_official'
    OUT.mkdir(exist_ok=True)
    java_root = Path(os.environ.get('JAVA_HOME', 'D:/JDK'))
    classes = OUT / 'classes'
    classes.mkdir(exist_ok=True)
    libraries = str(PROJECT / 'dist/lib/*')
    compile_command = [str(java_root/'bin/javac.exe'), '-encoding', 'UTF-8',
                       '-cp', libraries, '-sourcepath', str(PROJECT/'src'), '-d', str(classes),
                       str(PROJECT/'src/evaluation/EvaluatorTask1b.java')]
    built = subprocess.run(compile_command, capture_output=True, text=True, errors='replace')
    (OUT/'compile.log').write_text(built.stdout+built.stderr, encoding='utf-8')
    if built.returncode:
        raise RuntimeError('Official source compilation failed; see compile.log')
    commit = subprocess.check_output(['git','-C',str(UPSTREAM),'rev-parse','HEAD'],text=True).strip()
    assert not subprocess.check_output(['git','-C',str(UPSTREAM),'diff','--name-only'],text=True).strip()
    questions = read(ROOT/'eval_result/0915/questions.json')['questions']
    run = read(ROOT/'eval_result/0915/runs/results.json')
    assert run['run_status'] == 'completed' and len(run['results']) == len(questions) == 16
    for entry in read(ROOT/'eval_result/0915/runs/manifest.sha256.json')['files']:
        path=(ROOT/'eval_result/0915'/entry['path']).resolve()
        assert path.is_relative_to((ROOT/'eval_result/0915').resolve())
        assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
    benchmark=read(ROOT/'evals/bioasq_13b_test_benchmark.json')['questions']
    gold=[]
    systems={'medlit_0904':[], 'science_pubmed_0915':[]}
    astra_run = None
    if options.include_medlit_astra:
        astra_root = ROOT / 'eval_result/0915_2'
        astra_run = read(astra_root/'runs/results.json')
        assert astra_run['run_status'] == 'completed' and len(astra_run['results']) == 16
        assert len({r['test_id'] for r in astra_run['results']}) == 16
        assert read(astra_root/'questions.json')['questions'] == questions
        for entry in read(astra_root/'runs/manifest.sha256.json')['files']:
            path = (astra_root/entry['path']).resolve()
            assert path.is_relative_to(astra_root.resolve())
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], entry['path']
        systems['medlit_astra_0915_2'] = []
    v3_run = None
    if options.include_v3:
        v3_root = ROOT / 'eval_result/0915_v3'
        v3_run = read(v3_root/'runs/results.json')
        assert v3_run['run_status'] in ('completed', 'completed_with_warnings')
        assert len(v3_run['results']) == len({r['test_id'] for r in v3_run['results']}) == 16
        assert read(v3_root/'questions.json')['questions'] == questions
        for entry in read(v3_root/'runs/manifest.sha256.json')['files']:
            path = (v3_root/entry['path']).resolve()
            assert path.is_relative_to(v3_root.resolve())
            assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256'], entry['path']
        systems['medlit_astra_0915_v3'] = []
    def payload(q, pmids, source_id):
        return {'id':source_id, 'type':q['type'], 'body':q['question'],
                'documents':['http://www.ncbi.nlm.nih.gov/pubmed/'+str(p) for p in pmids],
                'concepts':[], 'snippets':[], 'triples':[]}
    for q,r in zip(questions,run['results']):
        assert all(q[k]==r[k] for k in ('test_id','type','question')) and r['status']=='completed'
        matches=[b for b in benchmark if b['id']==QUESTION_IDS[q['test_id']]] if q['test_id'] in QUESTION_IDS else [b for b in benchmark if b['question']==q['question']]
        assert len(matches)==1
        b=matches[0]
        gold.append(payload(q,list(dict.fromkeys(b['gold_pmids'])),b['id']))
        accepted=next(a for a in r['attempts'] if a['attempt_id']==r['accepted_attempt_id'])
        pred=r['original_pubmed_ranked_pmids']
        assert pred==accepted['ranked_pmids']==read(ROOT/'eval_result/0915'/accepted['search_file'])
        assert len(pred)<=100 and len(set(pred))==len(pred)
        systems['science_pubmed_0915'].append(payload(q,pred[:10],b['id']))
        old=read(ROOT/f"eval_result/0904/runs/states/{q['test_id']}.json")
        old_pred=old['final_ranked_pmids']
        assert len(set(old_pred))==len(old_pred)
        systems['medlit_0904'].append(payload(q,old_pred[:10],b['id']))
        if astra_run:
            ar = next(row for row in astra_run['results'] if row['test_id'] == q['test_id'])
            assert all(ar[k] == q[k] for k in ('test_id','type','question')) and ar['status'] == 'completed'
            state_path = (astra_root/ar['state_file']).resolve()
            assert state_path.is_relative_to(astra_root.resolve())
            state = read(state_path)
            attempt = next(a for a in state['query_attempts'] if a['attempt_id'] == state['accepted_query_attempt_id'])
            assert state['question'] == q['question']
            assert ar['accepted_attempt_id'] == state['accepted_query_attempt_id']
            assert ar['final_query'] == attempt['exact_query']
            apred = ar['original_pubmed_ranked_pmids']
            assert apred == state['final_ranked_pmids'] == attempt['pmids']
            assert len(apred) <= 100 and len(set(apred)) == len(apred)
            assert not ar['abstract_screened_ranked_pmids'] and not ar['selected_pmids_for_fulltext']
            assert attempt['retmax'] == 100 and attempt['sort'] == 'relevance' and not attempt['max_date']
            systems['medlit_astra_0915_2'].append(payload(q,apred[:10],b['id']))
        if v3_run:
            vr = next(row for row in v3_run['results'] if row['test_id'] == q['test_id'])
            assert all(vr[k] == q[k] for k in ('test_id','type','question'))
            assert vr['status'] in ('completed', 'completed_with_warnings')
            state_path = (v3_root/vr['state_file']).resolve()
            export_path = (v3_root/vr['export_dir']).resolve()
            assert state_path.is_relative_to(v3_root.resolve()) and export_path.is_relative_to(v3_root.resolve())
            state = read(state_path)
            exported = read(export_path/'result.json')
            snapshot = read(export_path/'state_snapshot.json')
            for entry in read(export_path/'manifest.sha256.json')['files']:
                path = (export_path/entry['path']).resolve()
                assert path.is_relative_to(export_path)
                assert hashlib.sha256(path.read_bytes()).hexdigest() == entry['sha256']
            attempt = next(a for a in state['query_attempts'] if a['attempt_id'] == state['accepted_query_attempt_id'])
            assert state['question'] == q['question'] == exported['question']
            assert state['task_mode'] == 'retrieval'
            assert vr['accepted_attempt_id'] == state['accepted_query_attempt_id'] == exported['accepted_attempt_id']
            assert vr['final_query'] == attempt['exact_query'] == exported['final_query']
            pred3 = vr['original_pubmed_ranked_pmids']
            assert pred3 == state['final_ranked_pmids'] == attempt['pmids'] == exported['original_pubmed_ranked_pmids'] == snapshot['final_ranked_pmids']
            assert len(pred3) <= 100 and len(set(pred3)) == len(pred3)
            assert not vr['abstract_screened_ranked_pmids'] and not vr['selected_pmids_for_fulltext']
            assert attempt['status'] == 'success'
            assert attempt['retmax'] == 100 and attempt['sort'] == 'relevance' and not attempt['max_date']
            systems['medlit_astra_0915_v3'].append(payload(q,pred3[:10],b['id']))
    command=[str(java_root/'bin/java.exe'),'-cp',str(classes)+os.pathsep+libraries,
             'evaluation.EvaluatorTask1b','-phaseA','-e','9']
    def evaluate(gs,ss,folder):
        gp,sp=folder/'gold.json',folder/'system.json'
        gp.write_text(json.dumps({'questions':gs}),encoding='utf-8')
        sp.write_text(json.dumps({'questions':ss}),encoding='utf-8')
        response=subprocess.run(command+[str(gp),str(sp)],capture_output=True,text=True,errors='replace')
        if response.returncode:
            raise RuntimeError('Official evaluator failed; reference data withheld from logs')
        values=response.stdout.split()
        assert len(values)==20, 'Unexpected official output layout'
        return dict(zip(['mean_precision','mean_recall','mean_f1','MAP','GMAP'],map(float,values[5:10]))),response.stdout
    summary={}
    per_question=[]
    with tempfile.TemporaryDirectory(prefix='bioasq_official_') as tmp:
        folder=Path(tmp)
        for name,submission in systems.items():
            summary[name],raw=evaluate(gold,submission,folder)
            (OUT/(name+'_raw.txt')).write_text(raw,encoding='utf-8')
            (OUT/(name+'_submission.json')).write_text(json.dumps({'questions':submission},indent=2)+'\n',encoding='utf-8')
        for i,q in enumerate(questions):
            per_question.append({'test_id':q['test_id'], 'type':q['type'],
                                 **{name:evaluate([gold[i]],[s[i]],folder)[0] for name,s in systems.items()}})
    result={'upstream':'https://github.com/BioASQ/Evaluation-Measures','commit':commit,
            'evaluator':'evaluation.EvaluatorTask1b','edition_mode':9,'submission_depth':10,
            'question_count':16,'compiled_from_unmodified_source':True,
            'summary':summary,'questions':per_question,
            'medlit_astra_metadata':astra_run['metadata'] if astra_run else None,
            'medlit_v3_metadata':v3_run['metadata'] if v3_run else None,
            'note':'Official source evaluated locally on a project-selected sample, not an official leaderboard result. Non-document fields are empty; their raw NaN outputs are not reported as scores.'}
    (OUT/'scores.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    lines=['# BioASQ 官方源码：同16题文献检索评分','',
           f'源码：[BioASQ/Evaluation-Measures](https://github.com/BioASQ/Evaluation-Measures/tree/{commit})；commit `{commit}`。',
           '', '直接编译未修改的 Java 源码，调用 `evaluation.EvaluatorTask1b -phaseA -e 9`。9是源码支持的规则版本，不是用第9届数据；文献MAP采用BioASQ8以来的分母规则。输入保留全部gold，每个系统仅提交原排名前10篇。',
           '', '| 官方文献指标 | MedLit 0904 | Science PubMed 0915 | 差值 |','|---|---:|---:|---:|']
    for key in summary['medlit_0904']:
        a,b=summary['medlit_0904'][key],summary['science_pubmed_0915'][key]
        lines.append(f'| {key} | {a:.6f} | {b:.6f} | {b-a:+.6f} |')
    lines+=['', '| test_id | MedLit AP | Science AP | 差值 |','|---|---:|---:|---:|']
    for row in per_question:
        a,b=row['medlit_0904']['MAP'],row['science_pubmed_0915']['MAP']
        lines.append(f"| {row['test_id']} | {a:.6f} | {b:.6f} | {b-a:+.6f} |")
    lines+=['','## 与旧评分的区别','',
            '旧自写AP@10除以全部gold数；官方源码在规则8/9下除以min(10,gold数)。因此gold超过10篇的问题旧AP被额外压低。本报告替代旧MAP结论；原始检索结果不变。',
            '', '官方程序输出mean precision、mean recall、mean F1、MAP、GMAP。Recall@20/100及Hit是项目诊断指标，不属于这份前10篇官方提交评分，不混入本表。',
            '', '仅评价文献，不评价片段、概念、三元组或问答。临时gold文件已随临时目录清理；输出没有gold PMID。',
            '', '仍是自选16题的本地官方源码评分，不是官方榜单成绩。0904模型为5.6 Luna，0915为6 Astra（用户提供）；检索日期不同且无截止，不能分离模型、技能和数据库时点的影响。',
            '', '复现：`python evals/run_official_bioasq.py`；要求已下载官方源码及Java JDK，可用JAVA_HOME指定JDK。']
    (OUT/'benchmark.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if astra_run:
        lines = ['# BioASQ官方源码：MedLit + Astra 实验对照','',
                 f'未修改的官方源码 commit `{commit}`；直接编译运行 `evaluation.EvaluatorTask1b -phaseA -e 9`，每题提交原排名前10篇。',
                 '', '| 文献指标 | ' + ' | '.join(systems) + ' |', '|---|' + '---:|' * len(systems)]
        for key in summary['medlit_0904']:
            lines.append('| '+key+' | '+' | '.join(f'{summary[name][key]:.6f}' for name in systems)+' |')
        lines += ['', '| test_id | ' + ' | '.join(systems) + ' |', '|---|' + '---:|' * len(systems)]
        for row in per_question:
            lines.append('| '+row['test_id']+' | '+' | '.join(f'{row[name]["MAP"]:.6f}' for name in systems)+' |')
        lines += ['', '## 完整性与限制','',
                  '两轮新实验的封存哈希均验证通过，0915_2全部16题完成。题目、所接受查询、state排名与结果排名逐题核对一致；未筛选或重排。原始结果及封存文件未改动。',
                  '', '本轮记录20次搜索请求：19次成功、1次HTTP500失败后恢复；16题均接受查询。模型按用户选择标为Astra，精确运行ID未独立确认。',
                  '', '这是自选16题的本地官方源码评分，不是官方榜单成绩。两轮Astra实验为同日独立运行，但模型精确标识、生成随机性及在线数据库变化仍未完全控制。不能由一轮成绩证明skill因果优势。',
                  '', '评分仅涉及文献。MAP分母由官方源码决定，为min(10,gold数)。不把项目Hit、Recall@20/100或空片段等字段当作官方文献提交指标。gold输入仅在临时目录存在，结束后已清理，输出不包含gold PMID。',
                  '', '复现：`python evals/run_official_bioasq.py --include-medlit-astra`。输出保留官方原始stdout、指标JSON及逐题官方评分。']
        (OUT/'benchmark.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
        if v3_run:
            with (OUT/'benchmark.md').open('a', encoding='utf-8') as report:
                report.write('\n## 0915_v3 验证\n\n16题排名均与live state、接受的attempt及原始导出一致；批次和逐题导出哈希验证通过。运行包含警告而非全部无异常：23次查询、3次反馈恢复，详情见原实验观察记录。复现：`python evals/run_official_bioasq.py --include-v3`。本次仅评分原始排名，不把反馈缺失计作相关性标签。\n')
                previous = summary['medlit_astra_0915_2']
                current = summary['medlit_astra_0915_v3']
                differences = [row['medlit_astra_0915_v3']['MAP'] - row['medlit_astra_0915_2']['MAP'] for row in per_question]
                wins = sum(d > 1e-12 for d in differences)
                losses = sum(d < -1e-12 for d in differences)
                report.write(f'\n相对0915_2：MAP差值 {current["MAP"]-previous["MAP"]:+.6f}；Recall差值 {current["mean_recall"]-previous["mean_recall"]:+.6f}；逐题AP {wins}升、{losses}降、{16-wins-losses}不变。未观察到总体MAP提升，不能据此宣称检索性能优化成功；运行可靠性改动与检索质量需分别判断。\n')
    print(json.dumps({'commit':commit,'summary':summary},indent=2))

if __name__=='__main__':
    main()
