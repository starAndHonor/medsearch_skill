# Workflow status and stopping rules

Read this reference when `status` or `diagnose` reports a blocker, degradation,
budget exhaustion, or readiness to report.

`diagnose` derives the next action from the saved state. Follow the reported
status instead of repeating a completed stage.

## Required progression

- Missing query attempts -> author a query file and run `search-pubmed`.
- Attempts without an accepted query -> inspect the returned translation and
  title/abstract feedback, then submit another attempt or run `accept-query`.
- Accepted query without records -> `fetch-records`.
- Records without localization manifests -> `localize-fulltext`.
- Localized sources without parsed output -> `parse-fulltext`.
- Parsed sources without successful draft extraction -> `extract-evidence`.
- Evidence without a report -> `report` and `verify`.

## Block and stop

Stop and report the concrete blocker when diagnosis returns `blocked`. Current
hard-blocker handling includes missing required configuration or dependency,
repeated blockers reaching `budgets.max_same_blocker`, network unavailability
before any records are available, and an accepted attempt ID that no longer
exists. Retry only after the relevant environment, configuration, or query
condition changes.

## Continue with disclosed degradation

- A zero-result query is feedback, not evidence. Revise it only when another
  materially justified query can be written.
- Missing open full text may leave an `abstract_only` or `unavailable` record.
- A PDF placeholder is not parsed article text and must not be used as evidence.
- One failed source must retain its failure status; it does not justify
  fabricating or generalizing evidence.

When records and usable evidence exist despite an infrastructure blocker,
diagnosis may return `degraded_ready`. Report only what the available sources
support and disclose the degradation.

`ready_to_report`, `degraded_ready`, and `complete` set
`termination_ready: true`. Do not restart expensive search or download stages
after that point unless the user explicitly asks for broader coverage or the
saved evidence is insufficient for the requested output.
