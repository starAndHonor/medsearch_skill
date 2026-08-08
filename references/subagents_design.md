# Subagents Design

Codex remains the main agent. Subagents are optional workers for bounded tasks.

Recommended worker roles:

- Search Planner: propose query variants.
- Fulltext Localizer: try open-access full-text routes.
- Paper Reader: read one localized paper and extract evidence.
- Evidence Synthesizer: compare extracted evidence.
- Verifier: check PMID/DOI/local-source traceability.

Use files for communication:

```text
workspace/runs/<run_id>/tasks/task_001.json
workspace/runs/<run_id>/outputs/task_001_output.json
```

Main Codex should only trust schema-valid outputs.

