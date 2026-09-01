# Optional file-based task helpers

Read this reference only when the user explicitly asks to use `spawn-tasks`,
`merge-task-output`, workers, or parallel task handling.

These commands are experimental helpers, not the default research workflow
and not an autonomous worker scheduler.

`spawn-tasks` inspects the current state and writes task descriptions under:

```text
<state directory>/tasks/task_001.json
```

Depending on state, it may describe work for `search_planner`,
`fulltext_localizer`, `paper_reader`, or `verifier`. It does not launch agents,
run tasks in parallel, monitor them, retry them, or merge their results.

`merge-task-output --file <path>` reads JSON and appends it to
`state.task_outputs`. The current implementation does not validate a task
output schema, reconcile it into records/evidence, or establish that the work
was performed correctly. Inspect provenance and content before trusting a
merged output.

Do not use either command in the normal
`init -> ... -> report -> verify` path. Use the deterministic CLI stages
directly unless the user explicitly requests an experiment with these helpers.
