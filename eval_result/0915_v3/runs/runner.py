import json, subprocess, sys, pathlib, datetime
ROOT=pathlib.Path(__file__).resolve().parent.parent
PLUGIN=pathlib.Path('C:/Users/CGOMI/.codex/plugins/cache/medlit-local/medlit-cli/0.2.0+codex.20260915142801')
CLI=PLUGIN/'scripts/medlit_cli.py'
def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def run(test,label,args):
    d=ROOT/'runs/logs'/test; d.mkdir(parents=True,exist_ok=True)
    cmd=[sys.executable,str(CLI),*args]
    started=datetime.datetime.now(datetime.timezone.utc).isoformat()
    p=subprocess.run(cmd,capture_output=True,encoding='utf-8',errors='replace')
    (d/(label+'.stdout.txt')).write_text(p.stdout,encoding='utf-8')
    (d/(label+'.stderr.txt')).write_text(p.stderr,encoding='utf-8')
    save(d/(label+'.command.json'),dict(command=cmd,started_at=started,finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),returncode=p.returncode))
    print(test,label,p.returncode,flush=True)
    return p
if __name__=='__main__':
    action=sys.argv[1]
    if action=='preflight':
        save(ROOT/'runs/plugin_manifest.json',json.loads((PLUGIN/'.codex-plugin/plugin.json').read_text(encoding='utf-8-sig')))
        for c in ['', 'status','init','search-pubmed','recover-feedback','accept-query','export-retrieval']:
            p=run('_preflight',c or 'main',([c] if c else [])+['--help']); print(p.stdout)
    elif action=='search':
        for plan in json.loads((ROOT/'runs/query_plan.json').read_text(encoding='utf-8')):
            dest=ROOT/'runs/queries'/plan['test_id']/(plan['attempt_id']+'.json')
            if not dest.exists(): save(dest,{k:v for k,v in plan.items() if k!='test_id'})
        qs=json.loads((ROOT/'questions.json').read_text(encoding='utf-8-sig'))['questions']
        for tid in sys.argv[2:]:
            q=next(q for q in qs if q['test_id']==tid)
            state=ROOT/'runs/states'/f'{tid}.json'
            run(tid,'status',['--state',str(state),'status'])
            if not state.exists():
                p=run(tid,'init',['--state',str(state),'init','--question',q['question'],'--mode','retrieval'])
                if p.returncode: continue
            files=sorted((ROOT/'runs/queries'/tid).glob('*.json'))
            f=files[-1]
            run(tid,f.stem+'_search',['--state',str(state),'search-pubmed','--query-file',str(f),'--retmax','100','--feedback-records','10'])
    elif action=='recover2':
        for tid in sys.argv[2:]:
            run(tid,'q2_recover',['--state',str(ROOT/'runs/states'/f'{tid}.json'),'recover-feedback','--attempt-id','q2'])
    elif action=='recover':
        for tid in sys.argv[2:]:
            run(tid,'q1_recover',['--state',str(ROOT/'runs/states'/f'{tid}.json'),'recover-feedback','--attempt-id','q1'])
    elif action=='accept':
        for d in json.loads((ROOT/'runs/decision_plan.json').read_text(encoding='utf-8')):
            save(ROOT/'runs/decisions'/(d['test_id']+'.json'),d)
        for tid in sys.argv[2:]:
            state=ROOT/'runs/states'/f'{tid}.json'
            decision=json.loads((ROOT/'runs/decisions'/f'{tid}.json').read_text(encoding='utf-8'))
            aid=decision['accepted_attempt_id']
            p=run(tid,'accept_'+aid,['--state',str(state),'accept-query','--attempt-id',aid])
            if p.returncode==0:
                run(tid,'export',['--state',str(state),'export-retrieval','--output-dir',str(ROOT/'runs/exports'/tid)])
