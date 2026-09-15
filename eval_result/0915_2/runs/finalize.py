from run_step import BASE, ROOT, RESULT, read, write, now
import hashlib, re, json

assert not (BASE/'runs/manifest.sha256.json').exists(), 'Already sealed; do not mutate'
data=read(RESULT)
questions=read(BASE/'questions.json')['questions']
decisions=read(BASE/'runs/decisions.json')
assert len(questions)==16 and [q['test_id'] for q in questions]==[r['test_id'] for r in data['results']]
redactions=[]
# The CLI embedded an HTTP error response containing request contact/network fields.
# Preserve diagnostic content, but remove these values as required by README.
for p in (BASE/'runs/states').glob('*.json'):
    state=read(p)
    changed=False
    for err in state.get('errors',[]):
        raw=err.get('message','')
        safe=re.sub(r'([?&]email=)[^&\s"\\]+',r'\1[REDACTED]',raw,flags=re.I)
        safe=re.sub(r'("api[-_]key"\s*:\s*")[^"]*(")',r'\1[REDACTED]\2',safe,flags=re.I)
        if safe!=raw:
            err['message']=safe
            changed=True
            redactions.append(dict(file=p.relative_to(BASE).as_posix(),field='errors[].message',reason='Remove request email and api-key-labelled network identifier; no search results altered.'))
    if changed: write(p,state)

checks=[]; warnings=[]; total=0; successful=0
lines=['# MedLit 检索实验观察','', '仅检索实验；未生成问题答案、筛选、重排、下载全文或评分。', '', '全部题目首次检索按 questions.json 原顺序执行。list_03 的 HTTP 500 在其余题目按序完成后恢复重试一次；保留独立失败尝试。', '', '模型精确标识无法从本次运行上下文独立核实；插件版本已核实为 0.2.0+codex.20260915113715。', '', '工作区初始普通写入失败，显式限定本目录的提升执行成功。list_04 的前10个PMID中1条未返回反馈记录；其余全部可用摘要均已阅读。', '']
for row,q in zip(data['results'],questions):
    tid=row['test_id']; state=read(BASE/row['state_file'])
    assert row['question']==q['question']==state['question']
    stored={a['attempt_id']:a for a in state['query_attempts']}
    row['attempts']=[]
    lines+=['## '+tid,'',q['question'],'']
    for qp in sorted((BASE/f'runs/{tid}').glob('q*/query.json')):
        proposal=read(qp); aid=proposal['attempt_id']; folder=qp.parent; rel=folder.relative_to(BASE).as_posix()
        log=read(folder/'search.command.json'); total+=1
        a=stored.get(aid)
        obs=decisions[tid][aid]
        rec=dict(attempt_id=aid,query=proposal['exact_query'],reason=proposal['reasoning'],added_terms=proposal['added_terms'],status='success' if a is not None else 'blocked',returned_count=len(a['pmids']) if a else 0,ranked_pmids=a['pmids'] if a else [],total_count=a['count'] if a else None,state_file=row['state_file'],query_file=qp.relative_to(BASE).as_posix(),stdout_log=rel+'/search.stdout.log',stderr_log=rel+'/search.stderr.log',command_log=rel+'/search.command.json',observation=obs,started_at=log['started_at'],finished_at=log['finished_at'],exit_code=log['exit_code'])
        if a:
            successful+=1
            assert log['exit_code']==0 and a['exact_query']==proposal['exact_query'] and a['sort']=='relevance' and a['retmax']==100 and not a['max_date']
            for k in ['query_translation','translationset','warninglist','errorlist','lint_warnings','effective_query','feedback_error','executed_at']: rec[k]=a[k]
            rec['feedback_record_count']=len(a['feedback_records'])
            rec['feedback_reviewed_pmids']=[f['pmid'] for f in a['feedback_records']]
            rec['feedback_expected_pmids']=a['pmids'][:10]
            rec['feedback_missing_pmids']=[p for p in a['pmids'][:10] if p not in rec['feedback_reviewed_pmids']]
            rec['feedback_without_abstract_pmids']=[f['pmid'] for f in a['feedback_records'] if not f['abstract']]
            rec['error']=None
            if rec['feedback_missing_pmids']: warnings.append(dict(test_id=tid,attempt_id=aid,kind='missing_feedback_record',pmids=rec['feedback_missing_pmids']))
        else:
            assert log['exit_code']!=0
            rec.update(query_translation=None,translationset=[],warninglist={},errorlist={},error=state.get('errors',[]),response_available=False,feedback_record_count=0)
        row['attempts'].append(rec)
        seconds=(__import__('datetime').datetime.fromisoformat(log['finished_at'])-__import__('datetime').datetime.fromisoformat(log['started_at'])).total_seconds()
        lines += ['### '+aid,'','```text',proposal['exact_query'],'```','',obs,'',f"总命中：{rec['total_count']}；实际返回：{rec['returned_count']}；耗时：{seconds:.2f} 秒。",'']
    aid=state.get('accepted_query_attempt_id')
    if aid:
        final=stored[aid]
        assert state['final_ranked_pmids']==final['pmids'] and len(final['pmids'])<=100
        assert read(BASE/f'runs/{tid}/{aid}/accept.command.json')['exit_code']==0
        row.update(status='completed',accepted_attempt_id=aid,final_query=final['exact_query'],original_pubmed_ranked_pmids=state['final_ranked_pmids'],error=None)
    else:
        row.update(status='blocked',error=state.get('errors',[]) or state.get('blockers',[]))
    row['recovered_errors']=state.get('errors',[]) if aid else []
    assert row['abstract_screened_ranked_pmids']==[] and row['selected_pmids_for_fulltext']==[] and row['abstract_screening_method']=='pubmed'
    checks.append(dict(test_id=tid,status=row['status'],question_matches=True,accepted_attempt_matches=aid==row['accepted_attempt_id'],final_query_matches=not aid or row['final_query']==stored[aid]['exact_query'],original_ranking_matches=row['original_pubmed_ranked_pmids']==state.get('final_ranked_pmids',[]),no_screening_or_fulltext_selection=True,attempts=len(row['attempts'])))
    lines += [f"最终状态：{row['status']}；接受：{aid}。",'']

data['run_status']='completed' if all(r['status']=='completed' for r in data['results']) else 'blocked'
data['metadata'].update(finished_at=now(),search_attempt_count=total,successful_search_count=successful,failed_search_count=total-successful,accepted_query_count=sum(r['status']=='completed' for r in data['results']),semantic_revision_count=3,infrastructure_retry_count=1,search_date='2026-09-15',timezone='Asia/Shanghai',model_exact_id_verified=False,plugin_version_verified=True,environment_notes='Initial workspace Set-Content and directory creation denied; workspace-scoped elevated execution succeeded. list_03 q1 HTTP 500 recovered using q2 after subsequent successful requests. list_04 q1 returned 9 of 10 requested feedback records (PMID 29262007 missing); all available abstracts read. Exact runtime model ID / 6 Astra selection cannot be independently verified. Online retrieval is date-dependent; no historical outputs accessed.',redactions=redactions)
write(RESULT,data)
(BASE/'runs/observations.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
write(BASE/'runs/redactions.json',redactions)
allowed={'init','status','search-pubmed','accept-query'}
commands=[]
for p in (BASE/'runs').glob('**/*.command.json'):
    c=read(p); verb=c['argv'][4]
    assert verb in allowed and c['argv'][1]==str(ROOT/'scripts/medlit_cli.py')
    commands.append(verb)
assert commands.count('search-pubmed')==total
integrity=dict(checked_at=now(),integrity_status='passed_with_disclosed_limitations' if warnings else 'passed',run_status=data['run_status'],question_count=16,question_order_matches=True,all_questions_attempted=True,checks=checks,warnings=warnings,redactions=redactions,search_attempt_count=total,successful_search_count=successful,failed_search_count=total-successful,only_authorized_commands=True,exact_model_verified=False,all_available_feedback_abstracts_reviewed=True,all_requested_feedback_records_returned=not bool(warnings),no_scoring_performed=True,scope='Structural consistency and provenance only; no medical validation or relevance scoring.')
write(BASE/'runs/integrity_check.json',integrity)
files=sorted(p for p in (BASE/'runs').rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.sha256.json')
files += [BASE/'README.md',BASE/'questions.json']
manifest=dict(algorithm='SHA-256',sealed_at=now(),files=[dict(path=p.relative_to(BASE).as_posix(),size=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
write(BASE/'runs/manifest.sha256.json',manifest)
assert all(hashlib.sha256((BASE/e['path']).read_bytes()).hexdigest()==e['sha256'] for e in manifest['files'])
print(json.dumps(dict(run_status=data['run_status'],completed=sum(r['status']=='completed' for r in data['results']),search_attempts=total,successful=successful,failed=total-successful,sealed_files=len(files),warnings=warnings),ensure_ascii=True))
