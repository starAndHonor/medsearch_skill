# PubMed retrieval rules

Read this reference before running `plan-terms`, `validate-mesh`, `build-query`,
or `search-pubmed`.

## Current retrieval contract

The PICO JSON is an explicit input prepared by Codex or supplied by the user.
`plan-terms` does not perform PICO decomposition and does not call a model or a
network service. It deterministically cleans the PICO fields, protects
distinctive entities from adjacent generic words, and produces a term plan.

The default path is recall-oriented:

1. Run `plan-terms`.
2. Skip `validate-mesh` unless MeSH is explicitly requested as an experiment.
3. Run `build-query`, or `build-query --use-mesh` only after MeSH validation.
4. Execute every applicable query lane.
5. Use the stored reciprocal rank fusion result in `final_ranked_pmids`.

## Query lanes

`build-query` may create these complementary lanes:

- `Q0_cleaned_natural`: a lightly cleaned, untagged question. Keep this lane so
  PubMed Automatic Term Mapping can interpret the full context.
- `Q1_structured_recall`: conservative Title/Abstract terms grouped with `OR`
  inside each PICO concept and joined with `AND` across available population,
  intervention/exposure, and outcome concepts. Validated MeSH headings are
  added only in explicit MeSH mode.
- `Q1b_entity_anchor`: distinctive entity phrases from separate concepts are
  required to co-occur. This lane protects rare drugs, genes, abbreviations,
  and named methods from generic question wording.
- `Q2_explicit_filters`: created only when the input explicitly requests human
  or language filters.
- `Q3_with_comparator`: created only when a comparator exists and adds a query
  distinct from the main structured lane.

Do not replace these lanes with a single mechanically ANDed PICO query. Do not
remove the untagged lane merely because structured terms exist.

## MeSH and filters

- Treat generated MeSH strings as candidates, not validated headings.
- Use `[MeSH Terms]` only for `valid` or `entry_term` validation results.
- Failed validation falls back to Title/Abstract terms and must not block the
  default workflow.
- Human and language filters are opt-in. Never add them solely because the task
  is biomedical or written in English.

## Retrieval and fusion

Each lane is sent independently to PubMed. The balanced default retrieves up
to 100 PMIDs per lane; `--retmax` may be changed when the task or evaluation
requires another depth. PubMed supplies each lane's relevance order. MedLit
then combines the lane ranks with reciprocal rank fusion (RRF). Re-running a
lane replaces its previous result rather than giving that lane duplicate
weight.

Inspect `query_ladder`, PubMed query translations, every retrieval run, and
`final_ranked_pmids`. Do not report a query as executed merely because it was
generated.
