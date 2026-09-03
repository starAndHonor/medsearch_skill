# PubMed query rules

Read this reference before authoring or revising a query.

## Author the query

Write one complete PubMed query for the current attempt. The CLI sends
exact_query unchanged to ESearch after checking only definite structural
errors.

Start from discriminative biomedical entities explicitly present in the
question:

- genes, proteins, variants, drugs, diseases, phenotypes, named methods, and
  biological processes;
- direct aliases, acronyms, spelling variants, or hyphen variants when they
  are genuinely useful;
- contextual nouns only when they distinguish the requested relationship.

Use OR for equivalent forms of one concept and AND when separate concepts must
co-occur. Prefer [Title/Abstract] when explicit lexical co-occurrence is the
intended behavior. Quotes, field tags, wildcards, proximity expressions, MeSH,
and other PubMed syntax remain available when justified.

Do not submit the untouched natural-language question. Remove instructions and
question scaffolding such as describe, list, what is, which, and how. Do not
turn every remaining word into a required condition.

## Control expansion

For every query term not visibly present in the user's question, record term,
source_term, and reason in added_terms.

Acceptable additions are direct aliases and lexical variants. Do not add:

- a possible answer or a term learned from a known answer;
- a guessed mechanism, phenotype, target, disease, or drug class;
- a generic term merely because it is medically related;
- human, language, date, publication-type, or study-design filters that the
  user did not request.

The audit record does not mechanically prove semantic correctness. It forces
the Agent to make each expansion explicit and reviewable.

## Read PubMed feedback

After each search, inspect:

- count and the ranked PMID list;
- query_translation and translationset;
- warninglist and errorlist;
- the returned top titles and abstracts.

Revise when PubMed mapped a term to an unintended author or journal, ignored a
critical phrase, returned no records, required too many weak terms together, or
ranked mostly unrelated records.

Do not narrow solely because count is large. A rare entity may still place the
right papers first. Do not broaden solely because count is small. A unique
result may be exactly the intended paper.

## Revise or accept

Each new attempt is a complete replacement proposal, not a lane. Make a
materially justified change and use a new attempt ID. Earlier attempts may
inform judgment but are never merged.

When one result ranking is suitable, run accept-query for that attempt. Only
the accepted PMID order is consumed by fetch-records and later stages.
