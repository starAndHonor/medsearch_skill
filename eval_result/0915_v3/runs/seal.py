import pathlib,json,hashlib,datetime,sys
sys.stdout.reconfigure(encoding='utf-8')
ROOT=pathlib.Path(__file__).resolve().parent.parent
def read(p): return json.loads((ROOT/p).read_text(encoding='utf-8-sig'))
def write(p,x): (ROOT/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
questions=read('questions.json')['questions']
results=read('runs/results.json')
decisions={d['test_id']:d for d in read('runs/decision_plan.json')}
checks=[]; issues=[]; warnings=[]; starts=[]; searches=0; recoveries=0
obs=['# 0915_v3 运行观察','',
     '## 批次条件','',
     '使用已安装 MedLit CLI 0.2.0+codex.20260915142801；入口、版本清单及所用各命令帮助保存在 runs/logs/_preflight 和 runs/plugin_manifest.json。Python 3.12.1。',
     '用户选择模型为 6 Astra；当前会话说明为 Codex / GPT-6，但未暴露可独立核实的精确运行时模型 ID，因此不将用户选择视作已验证的 gpt-6-astra 身份。',
     '每题独立 retrieval state；retmax=100，relevance，feedback-records=10，无日期截止。只接受一个查询，完整保留其原始 PubMed 排名；未执行筛选、重排、全文下载、答案生成或 MAP 评分。',
     '查询 JSON、命令参数、stdout、stderr、完整 state、原始插件导出均在 runs 下。全量 attempts 从插件 live state 复制进 results.json；恢复历史在 feedback_recoveries 中。',
     '初始本地写入遇到 PermissionError，之后在自动审核允许的提升执行环境中完成；未修改插件实现。控制台首次读取中文使用了错误默认编码，之后改为 UTF-8；反馈展示脚本也修正了控制台编码。查询及插件原始日志保留 UTF-8。',
     'runner 的 status 日志使用固定名称，重复查询前的 status 会覆盖该题先前 status 展示；每次 search/init/recovery/accept/export 日志独立完整保存，所有搜索与恢复历史仍完整存在 state 中。',
     '本批次基础设施检索均成功；反馈恢复命令返回成功不等于找回记录，实际恢复均未返回缺失 PMID。按规则停止进一步恢复。',
     '','## 逐题记录','']
for row,q in zip(results['results'],questions):
    tid=q['test_id']; assert row['test_id']==tid
    state=read(row['state_file']); ex=read(row['export_dir']+'/result.json'); snap=read(row['export_dir']+'/state_snapshot.json')
    d=decisions[tid]; aa=next(a for a in state['query_attempts'] if a['attempt_id']==d['accepted_attempt_id'])
    row.update(status='completed_with_warnings' if aa['feedback_coverage']['missing_pmids'] else 'completed',
        attempts=state['query_attempts'],accepted_attempt_id=ex['accepted_attempt_id'],final_query=ex['final_query'],
        original_pubmed_ranked_pmids=ex['original_pubmed_ranked_pmids'],abstract_screened_ranked_pmids=[],selected_pmids_for_fulltext=[],
        error=aa['feedback_error'] or None,decision_file='runs/decisions/'+tid+'.json',feedback_coverage=aa['feedback_coverage'])
    c={'test_id':tid,'checks':{},'export_hashes':[]}
    def check(name,value):
        c['checks'][name]=bool(value)
        if not value: issues.append(tid+': '+name)
    check('question_matches',state['question']==snap['question']==ex['question']==q['question'])
    check('retrieval_mode',state['task_mode']==snap['task_mode']==ex['task_mode']=='retrieval')
    check('accepted_attempt_matches',d['accepted_attempt_id']==state['accepted_query_attempt_id']==snap['accepted_query_attempt_id']==ex['accepted_attempt_id'])
    check('final_query_matches',aa['exact_query']==ex['final_query'])
    check('original_ranking_matches',aa['pmids']==ex['original_pubmed_ranked_pmids']==state['final_ranked_pmids']==snap['final_ranked_pmids'])
    check('all_attempts_preserved',state['query_attempts']==snap['query_attempts']==ex['attempts'])
    check('no_fulltext_or_evidence',not state['fulltexts'] and not state['parsed_sources'] and not state['evidence'] and state['counters']['fulltext_attempts']==0)
    check('empty_compatibility_fields',row['abstract_screened_ranked_pmids']==row['selected_pmids_for_fulltext']==[])
    check('search_counter_matches',state['counters']['pubmed_queries']==len(state['query_attempts']))
    obs+=['### '+tid,'','- 模型：同批次，精确运行时 ID 未核实。','- 接受：'+d['accepted_attempt_id']+'；返回排名条数：'+str(len(aa['pmids']))+'。','- 接受理由：'+d['reason'],'']
    for a in state['query_attempts']:
        aid=a['attempt_id']; searches+=1; starts.append(a['started_at']); recovery=a.get('feedback_recoveries',[]); recoveries+=len(recovery)
        query=read('runs/queries/'+tid+'/'+aid+'.json'); orig=read('runs/logs/'+tid+'/'+aid+'_search.stdout.txt')
        check(aid+'_query_matches_file',query['exact_query']==a['exact_query'])
        check(aid+'_parameters',a['retmax']==100 and a['sort']=='relevance' and a['max_date']=='')
        check(aid+'_original_esearch_order',a['pmids']==a['raw_esearch']['esearchresult']['idlist']==orig['pmids'])
        check(aid+'_top10_requested',a['feedback_coverage']['requested_pmids']==a['pmids'][:10])
        check(aid+'_at_most_one_recovery',len(recovery)<=1)
        for suffix in ['stdout.txt','stderr.txt','command.json']:
            check(aid+'_log_'+suffix,(ROOT/'runs/logs'/tid/(aid+'_search.'+suffix)).is_file())
        cov=a['feedback_coverage']
        if cov['missing_pmids']: warnings.append(dict(test_id=tid,attempt_id=aid,kind='missing_feedback',pmids=cov['missing_pmids'],recovery_count=len(recovery),accepted=aid==aa['attempt_id']))
        if cov['no_abstract_pmids']: warnings.append(dict(test_id=tid,attempt_id=aid,kind='returned_without_abstract',pmids=cov['no_abstract_pmids'],accepted=aid==aa['attempt_id']))
        obs+=['- **'+aid+'**：'+a['status']+'；总命中 '+str(a['count'])+'；耗时 '+str(a['elapsed_seconds'])+' 秒。',
              '  - 查询：`'+a['exact_query']+'`',
              '  - 查询理由：'+a['reasoning'],
              '  - PubMed 翻译：`'+a['query_translation']+'`；warnings='+json.dumps(a['warninglist'])+'；errors='+json.dumps(a['errorlist'])+'。',
              '  - 反馈：请求 '+str(len(cov['requested_pmids']))+' 条，返回 '+str(len(cov['returned_pmids']))+' 条；缺失 '+json.dumps(cov['missing_pmids'])+'；已返回无摘要 '+json.dumps(cov['no_abstract_pmids'])+'。',
              '  - 恢复次数 '+str(len(recovery))+'；恢复详情 '+json.dumps(recovery,ensure_ascii=False)+'；最终反馈错误：'+(a['feedback_error'] or '无')+'。']
    obs+=['']
    manifest=read(row['export_dir']+'/manifest.sha256.json')
    for item in manifest['files']:
        p=ROOT/row['export_dir']/item['path']
        ok=p.is_file() and digest(p)==item['sha256'] and p.stat().st_size==item['size']
        check('hash_'+item['path'],ok); c['export_hashes'].append(dict(path=p.relative_to(ROOT).as_posix(),passed=ok))
    check('plugin_integrity_passed',read(row['export_dir']+'/integrity_check.json')['status']=='passed')
    c['status']='passed' if all(c['checks'].values()) else 'failed'; checks.append(c)
results['metadata'].update(model='User-selected: 6 Astra; session describes Codex / GPT-6; exact runtime model ID not independently exposed or verified',started_at=min(starts),finished_at=now,
    environment_notes='Installed pinned plugin and Python 3.12.1 verified. Full access limitations and logging notes in observations.md. Missing feedback retained after one recovery per affected attempt.',query_attempt_count=searches,feedback_recovery_count=recoveries)
results['run_status']='completed_with_warnings' if not issues else 'failed_integrity'
results['unfinished_test_ids']=[]
results['warnings']=warnings
write('runs/results.json',results)
obs+=['## 封存结果','',f'16/16 题已接受并导出；{searches} 次查询，{recoveries} 次反馈恢复。',
      '最终接受的 list_03/q2 仍缺 PMID 20641200；其余最终查询反馈记录齐全。无摘要记录单独标记。',
      '导出与排名完整性：'+('通过' if not issues else '失败：'+str(issues))+'。未完成题：无。',
      '批次状态为 completed_with_warnings；这是检索与审计封存状态，不表示反馈全部可用或检索效果优于旧实验。未计算 MAP。','']
(ROOT/'runs/observations.md').write_text('\n'.join(obs),encoding='utf-8')
integrity=dict(status='passed' if not issues else 'failed',checked_at=now,expected_tests=16,actual_tests=len(checks),all_test_ids_match=[r['test_id'] for r in results['results']]==[q['test_id'] for q in questions],
    unfinished_test_ids=[],query_attempt_count=searches,feedback_recovery_count=recoveries,issues=issues,warnings=warnings,tests=checks,
    note='Integrity pass verifies artifacts and ranking preservation, not clinical relevance or complete feedback availability. Live state export markers may differ from snapshot.')
write('runs/integrity_check.json',integrity)
files=[]
for p in sorted(ROOT.rglob('*')):
    if not p.is_file() or p==ROOT/'runs/manifest.sha256.json' or any(x in p.parts for x in ['.git','__pycache__']): continue
    files.append(dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p),size=p.stat().st_size))
write('runs/manifest.sha256.json',dict(algorithm='SHA-256',created_at=now,files=files))
assert all(digest(ROOT/f['path'])==f['sha256'] for f in files)
print(json.dumps(dict(status=integrity['status'],tests=len(checks),queries=searches,recoveries=recoveries,sealed_files=len(files),issues=issues,warnings=warnings),ensure_ascii=False,indent=2))
sys.exit(bool(issues))
