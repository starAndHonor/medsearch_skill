from __future__ import annotations

import unittest

from medlit.retrieval.fusion import reciprocal_rank_fusion


class FusionTests(unittest.TestCase):
    def test_second_lane_can_change_top_rank(self):
        runs = [
            {"query_id": "a", "pmids": ["1", "2", "3"]},
            {"query_id": "b", "pmids": ["3", "4", "2"]},
        ]
        self.assertEqual(reciprocal_rank_fusion(runs)[0], "3")

    def test_duplicate_within_lane_contributes_once(self):
        duplicated = [{"pmids": ["1", "1", "2"]}, {"pmids": ["2"]}]
        clean = [{"pmids": ["1", "2"]}, {"pmids": ["2"]}]
        self.assertEqual(reciprocal_rank_fusion(duplicated), reciprocal_rank_fusion(clean))

    def test_depth_truncates_each_lane(self):
        runs = [{"pmids": ["1", "2"]}, {"pmids": ["2", "3"]}]
        self.assertEqual(reciprocal_rank_fusion(runs, depth=1), ["1", "2"])


if __name__ == "__main__":
    unittest.main()
