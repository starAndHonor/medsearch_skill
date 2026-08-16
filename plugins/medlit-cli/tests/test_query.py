from __future__ import annotations

import unittest

from medlit.pubmed.query import QueryBuilder, TermPlanner, clean_natural_query


def plan(question: str, **extra):
    pico = {
        "question": question,
        "population": question,
        "intervention_or_exposure": "",
        "comparator": "",
        "outcome": "",
        **extra,
    }
    return TermPlanner().plan(pico)


class QueryConstructionTests(unittest.TestCase):
    def test_entity_is_not_glued_to_following_verb(self):
        term_plan = plan("Does Plozasiran reduce triglyceride levels?")
        terms = term_plan["concepts"][0]["title_abstract_terms"]
        self.assertIn("Plozasiran", terms)
        self.assertNotIn("Plozasiran reduce", terms)
        self.assertNotIn("reduce", terms)

    def test_generic_words_do_not_become_structured_or_terms(self):
        for question, generic in (
            ("What is the mechanism of action of Nipocalimab?", "action"),
            ("What associations were identified by MR-PheWAS?", "identified"),
        ):
            term_plan = plan(question)
            structured = next(
                lane["exact_query"]
                for lane in QueryBuilder().build(term_plan, [])
                if lane["query_id"] == "Q1_structured_recall"
            )
            self.assertNotIn(f'"{generic}"', structured.casefold())

    def test_natural_lane_is_cleaned_and_untagged(self):
        self.assertEqual(clean_natural_query("Describe RankMHC"), "RankMHC")
        self.assertEqual(
            clean_natural_query("What is the mechanism of action of Nipocalimab?"),
            "mechanism of action of Nipocalimab",
        )
        lane = QueryBuilder().build(plan("Describe RankMHC"), [])[0]
        self.assertEqual(lane["query_id"], "Q0_cleaned_natural")
        self.assertNotIn("[", lane["exact_query"])

    def test_entity_anchor_requires_cooccurrence(self):
        lanes = QueryBuilder().build(
            plan("Should Zotiraciclib be used for glioblastoma?"), []
        )
        anchor = next(lane for lane in lanes if lane["query_id"] == "Q1b_entity_anchor")
        self.assertIn('"Zotiraciclib"[Title/Abstract]', anchor["exact_query"])
        self.assertIn('"glioblastoma"[Title/Abstract]', anchor["exact_query"])
        self.assertIn(" AND ", anchor["exact_query"])

    def test_filters_are_opt_in(self):
        self.assertEqual(plan("Describe RankMHC")["filters"], {})
        filtered = plan("Describe RankMHC", filters={"humans": True, "language": "english"})
        focused = next(
            lane for lane in QueryBuilder().build(filtered, [])
            if lane["query_id"] == "Q2_explicit_filters"
        )
        self.assertIn("humans[MeSH Terms]", focused["exact_query"])
        self.assertIn("english[Language]", focused["exact_query"])


if __name__ == "__main__":
    unittest.main()
