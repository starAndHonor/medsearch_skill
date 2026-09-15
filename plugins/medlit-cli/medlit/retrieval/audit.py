"""Retrieval integrity helpers; no relevance scoring or ranking changes."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def feedback_coverage(requested: list[str], records: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(r.get('pmid')): r for r in records}
    returned = [p for p in requested if p in by_id]
    return {'requested_pmids': requested, 'returned_pmids': returned,
            'missing_pmids': [p for p in requested if p not in by_id],
            'no_abstract_pmids': [p for p in returned if not str(by_id[p].get('abstract') or '').strip()],
            'complete': len(returned) == len(requested)}


def export_retrieval(state: dict[str, Any], output: Path) -> dict[str, Any]:
    accepted = next((a for a in state.get('query_attempts', [])
                     if a['attempt_id'] == state.get('accepted_query_attempt_id')), None)
    if not accepted or accepted.get('status', 'success') != 'success':
        raise ValueError('No successful accepted query')
    ranking = state.get('final_ranked_pmids', [])
    if ranking != accepted['pmids'] or len(set(ranking)) != len(ranking):
        raise ValueError('Accepted ranking integrity mismatch')
    if output.exists():
        raise ValueError('Export directory already exists; use a fresh destination')
    output.mkdir(parents=True)
    result = {'question': state['question'], 'accepted_attempt_id': accepted['attempt_id'],
              'final_query': accepted['exact_query'], 'original_pubmed_ranked_pmids': ranking,
              'attempts': state['query_attempts'], 'task_mode': state.get('task_mode', 'research')}
    contents = {'result.json': result, 'state_snapshot.json': state,
                'integrity_check.json': {'status': 'passed', 'ranking_matches_accepted': True,
                                         'ranking_count': len(ranking)}}
    manifest = []
    for name, data in contents.items():
        raw = (json.dumps(data, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
        (output/name).write_bytes(raw)
        manifest.append({'path': name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)})
    seal = {'algorithm': 'SHA-256', 'files': manifest}
    (output/'manifest.sha256.json').write_text(json.dumps(seal, indent=2)+'\n', encoding='utf-8')
    return {'output_dir': str(output), 'ranking_count': len(ranking), 'integrity': 'passed'}
