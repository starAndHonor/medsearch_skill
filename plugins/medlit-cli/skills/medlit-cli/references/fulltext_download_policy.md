# Open-access localization and parsing policy

Read this reference before `localize-fulltext`, `parse-fulltext`, or
`extract-evidence`.

## Localization order

For each fetched PubMed record, the CLI records metadata and tries:

1. Existing PMCID, or PMID/DOI lookup through the PMC ID Converter.
2. Europe PMC full-text XML when a PMCID is available.
3. Europe PMC PDF when XML is unavailable.
4. Unpaywall `best_oa_location.url_for_pdf` when a DOI and
   `UNPAYWALL_EMAIL` or `MEDLIT_EMAIL` are available.
5. PubMed abstract status when no open full text is located.

The localizer stops at the first successfully downloaded XML or PDF. Every
attempt and failure is recorded in `fulltexts[].sources_tried`. A successful
command may still produce `abstract_only` or `unavailable`; command success is
not proof of full-text access.

Do not bypass paywalls, use unauthorized repositories, hide failures, or imply
that every PubMed record has accessible full text.

## What the parser actually supports

`parse-fulltext` prefers an existing XML file, then HTML, then a PDF, and then
the PubMed abstract. XML and HTML are converted to text. The current PDF branch
does **not** extract PDF text: it writes a `pdf_placeholder` containing only the
local PDF path.

Important current limitation: because PDF precedes the abstract in parser
selection, a downloaded PDF produces the placeholder rather than automatic
abstract fallback. The state currently labels that placeholder as `fulltext`.
Treat both behaviors as implementation limitations, not evidence that PDF text
was parsed.

Never use `parse_method: pdf_placeholder` or evidence heuristically derived
from that placeholder as article evidence. The downloaded PDF may be reported
as a localized file, while evidence must come from real XML/HTML text or the
fetched PubMed abstract and must retain that provenance.

The public CLI currently has no command for importing an arbitrary local
HTML/XML/PDF file. Do not claim user-provided file ingestion as an implemented
workflow merely because the internal parser accepts paths stored in a
manifest.
