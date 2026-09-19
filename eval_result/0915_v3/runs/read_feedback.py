import json,pathlib,sys
sys.stdout.reconfigure(encoding='utf-8')
for tid in sys.argv[1:]:
    files=sorted((pathlib.Path('runs/logs')/tid).glob('*_search.stdout.txt'))
    for f in files[-1:]:
        a=json.loads(f.read_text(encoding='utf-8'))
        print(tid,f.name,json.dumps({k:a.get(k) for k in ['count','status','query_translation','translationset','warninglist','errorlist','feedback_error','feedback_coverage']},ensure_ascii=True))
        for i,r in enumerate(a.get('feedback_records',[]),1):
            print(i,r['pmid'],r['title'])
            print(r['abstract'])
