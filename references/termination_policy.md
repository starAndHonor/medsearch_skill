# Termination and Degradation Policy

The CLI must help Codex avoid useless loops.

## Stop Immediately

Stop and report `blocked` when:

- network is unavailable for repeated retrieval attempts,
- a required configuration is missing and no fallback exists,
- PubMed query budget is exhausted without records,
- the same blocker appears at least `budgets.max_same_blocker` times,
- local dependency is missing for a non-critical enhancement and fallback already exists.

## Continue With Degradation

Continue when a weaker path exists:

- MeSH lookup fails -> use Title/Abstract fallback.
- Focused query returns zero -> use broader query or evolve query.
- Full text is unavailable -> use abstract-only.
- PDF text parsing is unavailable -> keep PDF path and use abstract/XML if available.
- One paper fails extraction -> mark that paper failed and continue others.

## Ready To Stop

`diagnose` returns `termination_ready: true` when:

- report is complete, or
- evidence exists and the run is ready to report, or
- degraded evidence exists and further retries are unlikely to improve the run.

Codex should not run expensive search/download steps after `termination_ready`
unless the user explicitly asks for more.

