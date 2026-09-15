# Retrieval audit and recovery

Use init --question <text> --mode retrieval for retrieval-only work. The default
research mode and old states retain their existing downstream workflow.

search-pubmed registers an attempt before networking. Successful empty searches,
running/interrupted searches, api_failed and network_failed are distinguishable.
pubmed_queries counts search command attempts, including failures; it does not
count transport-level retries. Timings cover search and feedback acquisition.

feedback_coverage records the original requested IDs, returned IDs, missing IDs
and returned records without abstracts. recover-feedback --attempt-id <id>
fetches only missing IDs and retains the original order. It does not rerun
ESearch or replace missing records with lower-ranked candidates. Legacy states
without coverage cannot infer which IDs were requested.

export-retrieval --output-dir <new directory> validates the accepted ranking,
writes result.json, state_snapshot.json, integrity_check.json and
manifest.sha256.json. Existing destinations are refused. The immutable snapshot
is taken before recording the export marker in live state. Changed accepted
queries invalidate that marker. The manifest seals this export, not arbitrary
external experiment logs; aggregate test IDs and model metadata remain the
experiment runner's responsibility. No gold data is used by these commands.
