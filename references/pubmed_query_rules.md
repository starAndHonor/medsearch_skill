# PubMed Query Rules

Build query blocks as:

```text
("Preferred MeSH"[MeSH Terms] OR "free text"[Title/Abstract])
```

Within one concept, join synonyms with `OR`.

Between PICO concepts, join blocks with `AND`.

Validate MeSH terms before using `[MeSH Terms]`. If validation fails, use
Title/Abstract fallback terms.

Avoid relying on bare untagged terms because PubMed Automatic Term Mapping can
expand them unpredictably.

Use query ladders:

- `Q1_broad_conceptual`: recall-first query.
- `Q2_focused_primary`: core filters such as humans/language.
- `Q3_reviews`: systematic review/meta-analysis focus.
- `Q4_trials`: clinical trial focus.

