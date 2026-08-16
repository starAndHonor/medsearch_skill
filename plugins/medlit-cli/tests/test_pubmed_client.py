from __future__ import annotations

import unittest

from medlit.pubmed.client import PubMedClient


class FakeHttp:
    def __init__(self):
        self.url = ""

    def get_json(self, url):
        self.url = url
        return {
            "esearchresult": {
                "count": "2",
                "idlist": ["22", "11"],
                "querytranslation": "translated query",
                "translationset": [{"from": "x", "to": "y"}],
            }
        }


class PubMedSearchTests(unittest.TestCase):
    def test_search_preserves_translation_and_cutoff(self):
        http = FakeHttp()
        result = PubMedClient(http).search("RankMHC", retmax=50, maxdate="2025/12/31")
        self.assertEqual(result["pmids"], ["22", "11"])
        self.assertEqual(result["query_translation"], "translated query")
        self.assertEqual(result["retmax"], 50)
        self.assertIn("2025%2F12%2F31", http.url)


if __name__ == "__main__":
    unittest.main()
