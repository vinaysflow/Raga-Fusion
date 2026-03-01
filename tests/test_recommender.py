#!/usr/bin/env python3
import unittest

from recommender import Recommender


class RecommenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rec = Recommender()

    def test_deterministic_sequence(self):
        a = self.rec.recommend_phrases("yaman", "lofi", duration=30, source="library")
        b = self.rec.recommend_phrases("yaman", "lofi", duration=30, source="library")
        self.assertEqual([p["phrase_id"] for p in a], [p["phrase_id"] for p in b])

    def test_scores_in_range(self):
        phrases = self.rec._get_candidates("yaman", source="library")
        self.assertTrue(len(phrases) > 0)
        for p in phrases[:5]:
            self.assertGreaterEqual(p.get("authenticity_score", 0), 0.0)
            self.assertLessEqual(p.get("authenticity_score", 0), 1.0)
            self.assertEqual(len(p.get("pitch_histogram", [])), 12)


if __name__ == "__main__":
    unittest.main()
