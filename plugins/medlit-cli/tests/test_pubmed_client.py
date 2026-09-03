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
                "warninglist": {"outputmessages": ["warning"]},
                "errorlist": {"fieldsnotfound": ["bad"]},
            }
        }


class PubMedSearchTests(unittest.TestCase):
    def test_search_preserves_translation_and_cutoff(self):
        http = FakeHttp()
        result = PubMedClient(http).search("RankMHC", retmax=50, maxdate="2025/12/31")
        self.assertEqual(result["pmids"], ["22", "11"])
        self.assertEqual(result["query_translation"], "translated query")
        self.assertEqual(result["warninglist"]["outputmessages"], ["warning"])
        self.assertEqual(result["errorlist"]["fieldsnotfound"], ["bad"])
        self.assertEqual(result["retmax"], 50)
        self.assertEqual(result["sort"], "relevance")
        self.assertIn("2025%2F12%2F31", http.url)

    def test_fetch_records_restores_requested_pmid_order(self):
        class XmlHttp:
            def get_text(self, _url):
                return """
                <PubmedArticleSet>
                  <PubmedArticle>
                    <MedlineCitation><PMID>11</PMID>
                      <Article><ArticleTitle>Second</ArticleTitle></Article>
                    </MedlineCitation>
                  </PubmedArticle>
                  <PubmedArticle>
                    <MedlineCitation><PMID>22</PMID>
                      <Article><ArticleTitle>First</ArticleTitle></Article>
                    </MedlineCitation>
                  </PubmedArticle>
                </PubmedArticleSet>
                """

        records = PubMedClient(XmlHttp()).fetch_records(["22", "11"])
        self.assertEqual([record["pmid"] for record in records], ["22", "11"])


if __name__ == "__main__":
    unittest.main()
