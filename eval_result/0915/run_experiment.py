import json, os, subprocess, sys, datetime
import hashlib
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent
SCRIPT = 'C:/Users/CGOMI/.codex/skills/pubmed_database/scripts/pubmed_api.py'
RESULT = ROOT / 'runs/results.json'
def now(): return datetime.datetime.now().astimezone().isoformat()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p, x): Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def save(r): write(RESULT,r)
def invoke(path, fn, *args):
    env=os.environ.copy()
    env['PYTHONPATH']=str(ROOT/'.runtime/python-deps')
    env['PYTHONIOENCODING']='utf-8'
    env.pop('NCBI_API_KEY',None); env.pop('USER_EMAIL',None)
    env['PYTHON_DOTENV_DISABLED']='1'
    p=subprocess.run([sys.executable,SCRIPT,str(path),fn,*args],env=env,capture_output=True,text=True,encoding='utf-8',timeout=180)
    if p.returncode: raise RuntimeError(f'{fn} exit={p.returncode}: {p.stderr[-1500:]} {p.stdout[-1000:]}')
    data=read(path)
    if not isinstance(data,list): raise RuntimeError(f'{fn} returned non-array: {data}')
    return data

mode=sys.argv[1]
r=read(RESULT)
if mode=='repair_display':
    row=r['results'][0]; a=row['attempts'][0]
    assert read(ROOT/a['search_file'])==a['ranked_pmids']
    assert len(read(ROOT/a['feedback_file']))==min(10,a['returned_count'])
    a['display_error']=a.pop('error'); a['status']='completed'
    row['status']='in_progress'; row['error']=None; r['run_status']='in_progress'
    save(r)
    with (ROOT/'runs/observations.md').open('a',encoding='utf-8') as f: f.write('\n首题搜索与摘要原始响应均成功落盘；辅助显示程序出现 GBK Unicode 编码错误，已切换 UTF-8 并重新读取完整摘要，未重复检索。\n')
elif mode=='init':
    r['run_status']='in_progress'
    r['metadata']['retrieval_started_at']=now()
    r['metadata']['finished_at']=''
    r['metadata']['environment_notes']='User authorized system Python and continuation without optional NCBI_API_KEY/USER_EMAIL, overriding credential stop prerequisite. Python 3.12.1; polite-http 0.1.3 installed in workspace .runtime/python-deps; python-dotenv available. All PubMed requests use the unmodified installed wrapper; no uv. Optional credentials removed from subprocess environment; dotenv disabled. No date cutoff. Earlier preflight blocking is documented in observations.md.'
    for row in r['results']: row['status']='pending'; row['error']=None
    save(r)
elif mode=='search':
    tid,aid,query,reason=sys.argv[2:6]
    row=next(x for x in r['results'] if x['test_id']==tid)
    earlier=r['results'][:r['results'].index(row)]
    assert all(x['status']=='completed' for x in earlier), 'Previous question not completed'
    folder=ROOT/'runs'/tid/aid; folder.mkdir(parents=True,exist_ok=True)
    sf=folder/'search.json'; ff=folder/'feedback.json'
    attempt=dict(attempt_id=aid,query=query,reason=reason,status='in_progress',returned_count=None,ranked_pmids=[],search_file=sf.relative_to(ROOT).as_posix(),feedback_file=ff.relative_to(ROOT).as_posix(),observation='',started_at=now())
    row['attempts'].append(attempt); row['status']='in_progress'; save(r)
    try:
        ids=invoke(sf,'search_pubmed',query,'--max_results','100','--sort_by','relevance')
        assert all(isinstance(x,str) and x.isdigit() for x in ids) and len(ids)<=100
        attempt['returned_count']=len(ids); attempt['ranked_pmids']=ids
        save(r)
        if ids: feedback=invoke(ff,'fetch_article_abstracts',','.join(ids[:10]))
        else:
            feedback=[]; attempt['feedback_file']=None
            attempt['observation']='Search returned a valid empty array; abstract retrieval not called.'
        attempt['status']='completed'; attempt['finished_at']=now(); save(r)
        print(json.dumps({'test_id':tid,'attempt_id':aid,'returned_count':len(ids),'feedback':[{'pmid':x.get('pmid'),'title':x.get('title'),'abstract':x.get('abstract')} for x in feedback]},ensure_ascii=False))
    except Exception as e:
        attempt['status']='blocked'; attempt['error']=str(e); row['status']='blocked'; row['error']=str(e); r['run_status']='blocked'; save(r); print(str(e)); sys.exit(1)
elif mode=='observe':
    tid,aid,obs=sys.argv[2:5]
    row=next(x for x in r['results'] if x['test_id']==tid)
    a=next(x for x in row['attempts'] if x['attempt_id']==aid)
    a['observation']=obs; save(r)
    with (ROOT/'runs/observations.md').open('a',encoding='utf-8') as f: f.write(f"\n## {tid} / {aid}（未接受）\n检索式：`{a['query']}`\n\n{obs}\n")
elif mode=='accept':
    tid,aid,obs=sys.argv[2:5]
    row=next(x for x in r['results'] if x['test_id']==tid)
    a=next(x for x in row['attempts'] if x['attempt_id']==aid)
    assert a['status']=='completed'
    a['observation']=obs
    row.update(status='completed',accepted_attempt_id=aid,final_query=a['query'],original_pubmed_ranked_pmids=a['ranked_pmids'],error=None)
    save(r)
    with (ROOT/'runs/observations.md').open('a',encoding='utf-8') as f:
        f.write(f"\n## {tid} / {aid}\n检索式：`{a['query']}`\n\n返回 {a['returned_count']} 篇（非总命中数）。{obs}\n接受本次检索；保留所有 PMID 原始顺序。\n")
    print(f'Accepted {tid}/{aid}: {a["returned_count"]}')
elif mode=='finalize':
    qs=read(ROOT/'questions.json')['questions']
    assert len(r['results'])==len(qs)==16
    raw_paths=[]; urls=['# 查看过的摘要记录链接','', '仅列出各次尝试实际获取并查看的前10篇（不足10篇则全部）。不是相关性标签或筛选名单。','']
    count=0; feedback_count=0; null_abstracts=[]; blank_titles=[]
    for row,q in zip(r['results'],qs):
        assert all(row[k]==q[k] for k in ('test_id','type','question'))
        assert row['status']=='completed' and row['error'] is None
        assert row['abstract_screening_method']=='pubmed'
        assert row['abstract_screened_ranked_pmids']==row['selected_pmids_for_fulltext']==[]
        chosen=next(a for a in row['attempts'] if a['attempt_id']==row['accepted_attempt_id'])
        assert row['final_query']==chosen['query']
        assert row['original_pubmed_ranked_pmids']==read(ROOT/chosen['search_file'])
        for a in row['attempts']:
            count+=1
            assert a['status']=='completed' and a['observation'] and a['reason']
            ids=read(ROOT/a['search_file']); raw_paths.append(ROOT/a['search_file'])
            assert a['ranked_pmids']==ids and a['returned_count']==len(ids)<=100
            assert all(isinstance(x,str) and x.isdigit() for x in ids)
            f=read(ROOT/a['feedback_file']); raw_paths.append(ROOT/a['feedback_file'])
            assert [x['pmid'] for x in f]==ids[:10], 'Feedback IDs/order mismatch'
            feedback_count+=len(f)
            urls.extend([f"## {row['test_id']} / {a['attempt_id']}",''])
            for x in f:
                urls.append(f"- [PMID {x['pmid']}](https://pubmed.ncbi.nlm.nih.gov/{x['pmid']}/)")
                if not x.get('abstract'): null_abstracts.append(dict(test_id=row['test_id'],attempt_id=a['attempt_id'],pmid=x['pmid']))
                if not x.get('title'): blank_titles.append(dict(test_id=row['test_id'],attempt_id=a['attempt_id'],pmid=x['pmid']))
            urls.append('')
    (ROOT/'runs/viewed_paper_urls.md').write_text('\n'.join(urls),encoding='utf-8')
    r['run_status']='completed'; r['metadata']['finished_at']=now()
    r['metadata']['search_attempts']=count
    r['metadata']['abstract_records_fetched']=feedback_count
    r['metadata']['environment_notes']+=' First attempt had a GBK console display failure after both API responses were saved successfully; display switched to UTF-8 and original feedback reread without API rerun. Some wrapper-returned titles are blank or truncated and some abstracts are null; original responses retained unchanged. No surfaced network/rate-limit failures.'
    save(r)
    checks={'checked_at':now(),'status':'passed','question_count':16,'completed_questions':16,'search_attempts':count,'raw_response_files':len(raw_paths),'abstract_records_fetched':feedback_count,'accepted_ranked_entries':sum(len(x['original_pubmed_ranked_pmids']) for x in r['results']),'question_text_and_order_preserved':True,'all_rankings_equal_raw_responses':True,'feedback_matches_first_10_in_original_order':True,'screening_and_fulltext_arrays_empty':True,'null_or_empty_abstract_records':null_abstracts,'blank_title_records':blank_titles,'no_relevance_scores_computed':True}
    write(ROOT/'runs/integrity_check.json',checks)
    notes=ROOT/'runs/observations.md'
    old=notes.read_text(encoding='utf-8-sig')
    summary=f'''# 最终状态：completed

完成时间：{r['metadata']['finished_at']}。
使用已安装 pubmed-database 技能和系统 Python 3.12.1；经用户明确授权不使用可选凭据。16题全部完成，共{count}次搜索及{count}次摘要调用，保存{len(raw_paths)}个原始响应文件；共查看{feedback_count}条摘要记录（含重复及空摘要）。

所有搜索 max_results=100、sort_by=relevance、不设日期截止。4题依据前10篇反馈修改一次：list_03、yesno_01、yesno_02、yesno_03。每题仅接受一个尝试，原始排名完整保留；没有筛选、重排、合并、全文下载或医学答案生成。没有访问历史结果或参考答案，没有计算MAP或其他相关性评分。

结果一致性检查见 integrity_check.json；实际查看记录的论文URL见 viewed_paper_urls.md。原始标题缺失/截断及摘要空值保留，不修补。无向调用端报告的网络或限流失败。首题辅助显示的GBK错误不影响已保存的原始响应，已修复并重读。

在线数据库时点和模型变化限制跨运行比较；未进行有无API key的对照试验，因此不据此量化两者准确率差异。精确运行时模型标识不可得，元数据按会话身份记录。

SHA-256文件清单用于核验输出内容，不代表操作系统级只读封存。后续评分应由原窗口执行。本窗口不读取评分参考。

以下是历史过程记录，其中早期blocked状态已由用户授权及环境恢复解除。

---

'''
    notes.write_text(summary+old,encoding='utf-8')
    files=raw_paths+[RESULT,notes,ROOT/'runs/viewed_paper_urls.md',ROOT/'runs/integrity_check.json',ROOT/'questions.json',ROOT/'run_experiment.py']
    manifest={'sealed_at':now(),'algorithm':'SHA-256','files':[{'path':p.relative_to(ROOT).as_posix(),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in files]}
    write(ROOT/'runs/manifest.sha256.json',manifest)
    assert all(hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest()==x['sha256'] for x in manifest['files'])
    print(json.dumps(checks,ensure_ascii=False))
