import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import create_app
from app.service import DataService, build_snapshot_from_payloads
from test_service import POLYALPHA, POLYALPHA_INDEX, SPORTTERY, TEST_NOW


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.service = DataService()
        self.service._snapshot = build_snapshot_from_payloads(POLYALPHA, POLYALPHA_INDEX, SPORTTERY, now=TEST_NOW)
        self.client = TestClient(create_app(self.service, enable_scheduler=False))

    def test_status_endpoint_returns_counts(self):
        response = self.client.get("/api/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["valid_had_matches"], 1)
        self.assertEqual(payload["skipped_matches"], 1)
        self.assertFalse(payload["stale"])

    def test_single_ev_endpoint_returns_readable_pick(self):
        response = self.client.get("/api/ev/singles?limit=10")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["match_num"], "周四001")
        self.assertEqual(payload[0]["pick_label"], "胜")
        self.assertEqual(payload[0]["team_or_draw"], "墨西哥")

    def test_parlay_endpoint_returns_leg_buckets_with_limit(self):
        response = self.client.get("/api/ev/parlays?min_legs=2&max_legs=8&limit=10")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(set(payload.keys()), {"2", "3", "4", "5", "6", "7", "8"})
        self.assertTrue(all(len(rows) <= 10 for rows in payload.values()))

    def test_nearest_sale_endpoint_returns_current_nearest_buyable_day(self):
        response = self.client.get("/api/ev/nearest-sale")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["match_date"], "2026-06-12")
        self.assertEqual(payload["match_count"], 1)
        self.assertEqual(payload["singles"][0]["match_num"], "周四001")
        self.assertEqual(payload["parlays_by_legs"], {})

    def test_accuracy_strategy_endpoint_returns_fixed_accuracy_strategy(self):
        response = self.client.get("/api/ev/accuracy-strategy")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["accuracy"], 0.5)
        self.assertEqual(payload["single_top"][0]["match_num"], "周四001")
        self.assertAlmostEqual(payload["single_top"][0]["probability"], 0.5)
        self.assertIn("nearest_sale", payload)

    def test_backtest_endpoint_returns_day_buckets(self):
        with patch("app.main.load_odds_history", return_value={}):
            response = self.client.get("/api/backtest")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("days", payload)
        self.assertIn("priced_match_count", payload)
        self.assertIn("unpriced_match_count", payload)


if __name__ == "__main__":
    unittest.main()
