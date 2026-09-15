---
name: medlit-cli
description: "Use when the user explicitly invokes $medlit-cli to run the bundled stateful biomedical literature workflow: author and iteratively assess PubMed queries, select retrieved records, attempt open-access localization, extract evidence, and write an integrity-checked report. Does not validate medical correctness."
---

# MedLit CLI

Use the bundled CLI as a toolbox. Codex decides which PubMed query to try,
reads the returned search evidence, and decides whether to revise or accept it.
The Python package executes atomic commands; it is not a query-planning
orchestrator.

## Execution

Resolve the execution root by walking upward from this file until one directory
contains both scripts/medlit_cli.py and medlit/cli.py. Stop with a
missing-installation blocker if no such directory exists. Use the active Python
interpreter unless the user supplied another one, and confirm the entrypoint
with --help before its first use.

Invoke commands with the global state argument before the subcommand:

~~~text
python "<execution root>/scripts/medlit_cli.py" --state "<workspace/state.json>" <command> [arguments]
~~~

Keep the state and generated artifacts in a dedicated workspace directory. The
state records query attempts, the accepted attempt, records, evidence, blockers,
and provenance.

## Workflow

1. Run status. If there is no state, run init --question <question>.
   Do not overwrite an existing run merely to change its search query.
   For a retrieval-only request, initialize with --mode retrieval. Legacy
   states without task_mode retain the full research workflow.
2. Read
   [references/pubmed_query_rules.md](references/pubmed_query_rules.md), then
   author a UTF-8 JSON query file containing the complete PubMed query:

   ~~~json
   {
     "attempt_id": "q1",
     "exact_query": "(UCHL1[Title/Abstract]) AND (heterozygous[Title/Abstract])",
     "reasoning": "Search the explicit gene and inheritance state together.",
     "added_terms": []
   }
   ~~~

   For every term not visibly present in the question, add an audit item:

   ~~~json
   {
     "term": "expanded term",
     "source_term": "term from the question",
     "reason": "Why this is a direct synonym or spelling variant."
   }
   ~~~

3. Run:

   ~~~text
   search-pubmed --query-file "<query.json>" --retmax 100 --feedback-records 10
   ~~~

   Add --max-date YYYY/MM/DD only when the user or task requires a cutoff.
   The command performs one real ESearch and returns count, ranked PMIDs,
   Query Translation, warnings, errors, and top title/abstract records.
4. Judge the attempt yourself. Check whether PubMed preserved the intended
   entities and fields, and whether the top records address the question's
   actual relationship. Count alone does not establish quality.
   Check feedback_coverage: missing_pmids means records were not returned,
   whereas no_abstract_pmids means the record exists without an abstract.
   Use recover-feedback --attempt-id <id> to refetch only missing records when
   needed. Recovery never changes the search ranking. Failed searches remain
   separate attempts; do not treat api_failed/network_failed as zero hits.
5. If the result is unsuitable, author a materially changed complete query and
   run search-pubmed again. Use a new attempt ID. Typical corrections include
   removing weak prose, splitting a false phrase, changing a field, relaxing an
   unsupported condition, or adding a directly justified synonym.
6. Do not create fixed broad/narrow lanes, merge attempts, or run RRF. Earlier
   attempts are comparison context only. There is no prescribed number of
   attempts; stop retrying when an attempt is suitable, infrastructure blocks
   progress, or another query cannot be justified from observed evidence.
7. Run accept-query --attempt-id <id> for the chosen attempt. Only its PMID
   order becomes available to downstream commands.
8. Run fetch-records, then localize-fulltext, parse-fulltext, and
   extract-evidence.
   In retrieval mode, instead run export-retrieval --output-dir <fresh directory>
   after acceptance, then stop. It exports the unmodified ranking, audit state,
   integrity check and SHA-256 manifest. Do not download full text merely to
   complete a retrieval-only task. Read
   [references/retrieval_audit.md](references/retrieval_audit.md) for recovery
   and export details.
9. Run diagnose and follow its current recommendation. When the available
   evidence is sufficient, run report, verify, and optionally diagnose again
   to update the terminal status.

Do not use evolve, spawn-tasks, or merge-task-output in the default workflow.
They are separate helpers.

## Query Decisions

- Begin with distinctive entities and noun phrases from the question. Do not
  submit the untouched natural-language question to PubMed ATM.
- Write the complete PubMed syntax yourself, including Boolean relationships,
  parentheses, phrases, and field tags.
- Preserve rare genes, drugs, diseases, variants, named methods, and other
  discriminative entities. Remove question scaffolding such as describe,
  what is, and which.
- Add a synonym only when it is a direct, defensible form of a visible source
  term. Do not add a guessed answer, mechanism, phenotype, broader disease, or
  drug class merely because it is medically related.
- Add human, language, year, publication-type, or study-design restrictions
  only when explicitly requested.
- Prefer [Title/Abstract] for explicit entity co-occurrence, but use other
  valid PubMed syntax when the question and observed Query Translation justify
  it.
- Treat zero results, unexpected author/journal mappings, ignored phrases, and
  irrelevant top records as reasons to revise. A large result count is only a
  warning; inspect the ranking before narrowing.

## Supporting References

- Read [references/pubmed_query_rules.md](references/pubmed_query_rules.md)
  before authoring or revising a query.
- Read
  [references/fulltext_download_policy.md](references/fulltext_download_policy.md)
  before localization, parsing, or evidence extraction.
- Read [references/termination_policy.md](references/termination_policy.md)
  when diagnose reports a blocker or readiness to report.
- Read [references/subagents_design.md](references/subagents_design.md) only
  when the user explicitly requests file-based task helpers.

## Evidence Rules

- Treat PMID, DOI, PubMed responses, and local paths in state as provenance. Do
  not invent records, retrieved text, or citations.
- Distinguish XML/HTML full text from abstract fallback. Never treat
  pdf_placeholder as article evidence.
- Evidence extraction and report are deterministic first passes, not expert
  medical synthesis. verify checks reference integrity, not factual or
  clinical correctness.
- Use only open-access or user-provided material. Do not bypass paywalls,
  authentication, CAPTCHAs, or access controls.
- Do not turn literature findings into diagnosis or patient-specific advice.

## Recovery

- **Invalid query file:** fix the JSON or definite syntax error and submit a new
  attempt.
- **Zero or irrelevant results:** inspect Query Translation and feedback
  records, then make one explainable change at a time.
- **No accepted query:** inspect attempts and either submit another query or
  explicitly accept the best suitable attempt.
- **Network failure:** preserve state and report the blocker; do not fabricate
  a successful search.
- **Resume:** run status on the exact state and continue from its live
  recommendation.
