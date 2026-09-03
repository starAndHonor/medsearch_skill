from __future__ import annotations

import unittest

from medlit.pubmed.query import lint_pubmed_query, validate_query_submission


class QueryValidationTests(unittest.TestCase):
    def test_accepts_agent_authored_pubmed_query_without_rewriting(self):
        query = (
            '("UCHL1"[Title/Abstract] OR "ubiquitin C-terminal '
            'hydrolase L1"[Title/Abstract]) AND heterozygous[Title/Abstract]'
        )
        result = validate_query_submission({
            "attempt_id": "q1",
            "exact_query": query,
            "reasoning": "Use the explicit gene and inheritance state.",
            "added_terms": [{
                "term": "ubiquitin C-terminal hydrolase L1",
                "source_term": "UCHL1",
                "reason": "Expanded gene name.",
            }],
        })
        self.assertEqual(result["exact_query"], query)
        self.assertTrue(result["lint"]["valid"])

    def test_rejects_definitely_malformed_structure(self):
        for query in (
            "(UCHL1[Title/Abstract] AND heterozygous[Title/Abstract]",
            "UCHL1[Title/Abstract] AND",
            '"UCHL1[Title/Abstract]',
            "UCHL1[[Title/Abstract]]",
        ):
            with self.subTest(query=query):
                self.assertFalse(lint_pubmed_query(query)["valid"])

    def test_unknown_well_formed_field_is_only_a_warning(self):
        result = lint_pubmed_query("UCHL1[Future PubMed Field]")
        self.assertTrue(result["valid"])
        self.assertTrue(result["warnings"])

    def test_added_terms_require_audit_metadata(self):
        with self.assertRaisesRegex(ValueError, "source_term"):
            validate_query_submission({
                "exact_query": "UCHL1[Title/Abstract]",
                "added_terms": [{"term": "UCH-L1", "reason": "variant"}],
            })

    def test_lowercase_boolean_is_not_rewritten(self):
        query = "UCHL1[Title/Abstract] and heterozygous[Title/Abstract]"
        result = lint_pubmed_query(query)
        self.assertTrue(result["valid"])
        self.assertIn("lowercase boolean-like words", result["warnings"][0])


if __name__ == "__main__":
    unittest.main()
