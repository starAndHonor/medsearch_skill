---
name: medlit-cli
description: "Use when the user explicitly invokes $medlit-cli to run the bundled stateful biomedical literature workflow: accept a PICO JSON, build and run PubMed searches, fetch records, attempt open-access localization, parse supported sources, extract deterministic evidence, diagnose progress, and write and integrity-check a report. Does not extract PDF text or validate medical correctness."
---

# MedLit CLI

Run the bundled MedLit implementation for an explicitly requested
biomedical literature task. Codex operates the workflow and inspects its state;
do not ask the user to imitate CLI execution.

## Execution path

Resolve the execution root by walking upward from this `SKILL.md` until the
same directory contains both of these implemented paths:

- `scripts/medlit_cli.py`
- `medlit/cli.py`

Stop with a missing-installation blocker if no such ancestor exists. Do not
guess the root from the current working directory or a fixed number of parent
directories. Convert the resolved entrypoint to an absolute path before use.

The implemented call chain is:

`scripts/medlit_cli.py` -> `medlit.cli.main()` -> the selected command handler

Honor a Python interpreter explicitly supplied by the user or environment;
otherwise use the active interpreter. Confirm the entrypoint with `--help`
before its first use. Invoke every stage in this form, with the global
`--state` option before the command:

```text
python "<resolved execution root>/scripts/medlit_cli.py" --state "<workspace state.json>" <command> [arguments]
```

Store `state.json`, downloaded sources, parsed text, and `report.md` in a
dedicated directory inside the user's workspace. The JSON state is the source
of truth for completed stages, records, evidence, blockers, and provenance.

## Step-by-step instructions

1. Inspect the request and choose a workspace-local state path. Run `status`
   first when that path may contain an earlier run. Resume from the recommended
   next action instead of reinitializing an existing state.
2. If no state exists, run `init --question <question>`. This creates a
   `medlit-state/v0.1` JSON state with workflow budgets and counters.
3. Create a UTF-8 PICO JSON file from the user's question or user-supplied
   concepts, then run `decompose --pico-file <file>`. The code does not perform
   local PICO decomposition. Use these implemented keys:
   `population`, `intervention_or_exposure`, `comparator`, and `outcome`.
4. Run `plan-terms`. It derives candidate MeSH and Title/Abstract terms from
   the PICO fields and applies the implemented human and English filters.
5. Run `validate-mesh`. Inspect each validation result. A failed NCBI MeSH
   lookup becomes a per-term `fallback`; the command can still exit successfully.
6. Run `build-query`. Inspect `query_ladder`; an empty ladder cannot be
   searched. The builder may create broad, focused, comparator, review, and
   trial variants according to the available concepts.
7. Run `search-pubmed`, optionally with `--query-id` or `--retmax`. With no
   query ID, the code selects the first unexecuted query, then falls back to the
   first query. Inspect the returned PMIDs and the saved retrieval audit.
8. Run `fetch-records`. It uses `last_pmids`, or all PMIDs from prior retrieval
   runs when `last_pmids` is empty, and stores parsed PubMed metadata.
9. Run `localize-fulltext`. For at most `budgets.max_records`, the code writes
   per-paper metadata and tries open-access sources: Europe PMC XML, Europe PMC
   PDF, then an Unpaywall PDF when an email is configured. Otherwise it records
   abstract-only or unavailable status.
10. Run `parse-fulltext`. The parser uses existing XML first, then existing
    HTML, then a PDF placeholder, then the PubMed abstract. Inspect
    `parse_method` for every parsed source.
11. Run `extract-evidence`. This is deterministic first-pass extraction from
    `parsed_text`, not expert interpretation. Inspect every item and its local
    source before relying on it.
12. Run `diagnose` and follow `recommended_next_actions`. A blocked diagnosis
    exits with code 8. A termination-ready diagnosis sets the state to
    `ready_to_stop` until a report exists.
13. When the available evidence is sufficient for the requested deliverable,
    run `report`, then `verify`. The report is written beside the state as
    `report.md`. After reporting, run `diagnose` again if the final state status
    must be updated to `done`.

Do not use `evolve`, `spawn-tasks`, or `merge-task-output` as part of the
default research workflow. They are separate helpers and are not required to
produce or verify a report.

## Evidence and reporting rules

- Treat PMID, DOI, and local file paths in state as provenance. Do not invent
  records, retrieved text, or citations.
- Distinguish XML/HTML full text from abstract fallback in the response.
- Never use `parse_method: pdf_placeholder` as article evidence. The current
  PDF branch writes only a message containing the PDF path; it does not extract
  the PDF's text, even though the current state labels its granularity as
  `fulltext`.
- The extractor reads at most the first 20,000 characters of each parsed source
  and uses heuristics for study design, methods, results, numbers, and
  limitations. Present its output as a draft extraction requiring inspection.
- `report` serializes the current state into sections; it does not independently
  synthesize or medically validate an answer.
- `verify` checks reference integrity and the presence of local paths for
  full-text-labelled evidence. It does not verify factual accuracy, study
  quality, clinical applicability, or medical correctness.
- Use only open-access material or user-provided local files. Do not bypass
  paywalls or access controls.
- Do not turn literature findings into diagnosis or patient-specific medical
  advice.

## Examples of inputs and outputs

### New run

User input:

```text
$medlit-cli Find studies comparing intervention X with standard care for
outcome Y in adults with condition Z.
```

Codex-created PICO input:

```json
{
  "population": "adults with condition Z",
  "intervention_or_exposure": "intervention X",
  "comparator": "standard care",
  "outcome": "outcome Y"
}
```

Expected artifact flow:

```text
state.json
  -> query_ladder and retrieval_runs
  -> PubMed records
  -> papers/<identifier>/metadata.json and any open-access files
  -> parsed_sources and evidence
  -> report.md and verification in state.json
```

The final response must report what was actually retrieved, whether each relied
on full text or abstract, where the report was written, and any blocker or
degradation. It must not claim a successful medical review solely because
`verify` returned `ok: true`.

### Resume

User input:

```text
$medlit-cli Continue the literature run in research/condition-z/state.json.
```

Run `status` against that exact state, inspect its JSON, and continue with the
diagnosed next stage. Do not overwrite it with `init`.

## Common edge cases

- **Missing state:** `status` reports `no_state`; initialize only if the user is
  starting a new run.
- **Missing PICO file:** `decompose` records `codex_required` and exits 8.
  Create or obtain explicit PICO JSON rather than claiming local decomposition.
- **Incomplete PICO:** `diagnose` blocks when population, intervention/exposure,
  or outcome is absent. Ask for or infer only information justified by the
  request, then update the PICO file explicitly.
- **MeSH service failure:** validation entries may fall back to
  Title/Abstract terms. Report the degradation; do not describe fallback terms
  as validated MeSH headings.
- **No query or PMIDs:** search/fetch commands exit 5 and add a blocker. Return
  to the preceding stage instead of fabricating results.
- **Network or API failure:** network failures exit 7; PubMed API failures exit
  6 and are recorded as recoverable errors. Retry only when the network or
  configuration has changed, and respect the stored budgets.
- **No open-access full text:** localization can still exit 0 with
  `abstract_only` or `unavailable` items. Continue only with the provenance that
  actually exists and disclose abstract-only evidence.
- **Unpaywall email absent:** DOI-based Unpaywall retrieval is skipped unless
  `UNPAYWALL_EMAIL` or `MEDLIT_EMAIL` is configured.
- **Localized PDF:** the parser creates `pdf_placeholder`, not extracted text.
  Exclude the placeholder from evidence and use an actual abstract or supported
  XML/HTML source instead.
- **Zero parsed or extracted items:** parse and extraction commands can exit 0
  even when no usable items were produced. Inspect counts and state, then use
  `diagnose`; never equate exit code 0 with research success.
- **Verification issues:** exit code 9 means referential-integrity problems.
  Fix state provenance before presenting the report as verified.
- **Budget exhaustion or repeated blockers:** stop when `diagnose` reports a
  blocked state. Return the partial supported result and the exact unresolved
  blocker instead of looping.
