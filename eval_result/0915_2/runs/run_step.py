import json, pathlib, subprocess, sys, datetime
ROOT = pathlib.Path('C:/Users/CGOMI/.codex/plugins/cache/medlit-local/medlit-cli/0.2.0+codex.20260915113715')
BASE = pathlib.Path(__file__).resolve().parent.parent
RESULT = BASE / 'runs/results.json'
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def read(p): return json.loads(pathlib.Path(p).read_text(encoding='utf-8-sig'))
def write(p, x):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def command(tid, folder, name, args):
    folder.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ROOT/'scripts/medlit_cli.py'), '--state', str(BASE/f'runs/states/{tid}.json')] + args
    start = now()
    r = subprocess.run(cmd, capture_output=True, cwd=BASE)
    (folder/f'{name}.stdout.log').write_bytes(r.stdout)
    (folder/f'{name}.stderr.log').write_bytes(r.stderr)
    write(folder/f'{name}.command.json', dict(argv=cmd, started_at=start, finished_at=now(), exit_code=r.returncode))
    if name == 'search' and r.returncode == 0:
        a = read(BASE/f'runs/states/{tid}.json')['query_attempts'][-1]
        print(json.dumps({k:v for k,v in a.items() if k!='feedback_records'},ensure_ascii=True))
        for i, f in enumerate(a['feedback_records'], 1):
            print(json.dumps(dict(rank=i,pmid=f['pmid'],title=f['title'],abstract=f['abstract']),ensure_ascii=True))
    else:
        print(r.stdout.decode('utf-8', errors='replace'))
    print(r.stderr.decode('utf-8', errors='replace'), file=sys.stderr)
    return r.returncode
if __name__ == '__main__':
    action, tid = sys.argv[1:3]
    data = read(RESULT)
    row = next(r for r in data['results'] if r['test_id']==tid)
    if not data['metadata']['started_at']:
        data['metadata'].update(started_at=now(), model='Codex (GPT-6 family per runtime instructions; exact model ID / 6 Astra selection not independently verifiable)', environment_notes='Only designated workspace and installed plugin files accessed. Exact model ID unavailable. Initial workspace Set-Content write denied; recovery recorded in command logs.', plugin_execution_root=str(ROOT))
        data['run_status']='running'
        write(RESULT, data)
    if action == 'search':
        aid = sys.argv[3]
        folder = BASE/f'runs/{tid}/{aid}'
        if not (folder/'query.json').exists():
            proposal=read(BASE/'runs/proposals.json')[tid][aid]
            write(folder/'query.json', dict(attempt_id=aid, **proposal))
        if not (BASE/row['state_file']).exists():
            command(tid, folder, 'status', ['status'])
            if command(tid, folder, 'init', ['init', '--question', row['question']]): sys.exit(1)
        sys.exit(command(tid, folder, 'search', ['search-pubmed', '--query-file', str(folder/'query.json'), '--retmax', '100', '--feedback-records', '10']))
    elif action == 'accept':
        aid=sys.argv[3]
        sys.exit(command(tid, BASE/f'runs/{tid}/{aid}', 'accept', ['accept-query', '--attempt-id', aid]))
