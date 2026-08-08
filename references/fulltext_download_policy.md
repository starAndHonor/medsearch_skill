# Full-Text Download Policy

This skill only localizes open-access full text or user-provided local files.

Preferred order:

1. PMID/DOI -> PMC ID Converter for PMCID.
2. PMCID -> Europe PMC `fullTextXML`.
3. PMCID -> Europe PMC PDF renderer.
4. DOI -> Unpaywall `best_oa_location.url_for_pdf`.
5. Fallback to PubMed abstract.

Every attempt must be recorded in `fulltexts[].sources_tried`.

Do not:

- bypass paywalls,
- use Sci-Hub,
- suppress download failures,
- copy long copyrighted text into final reports,
- assume every PubMed record has full text.

