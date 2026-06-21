import copy
import unittest
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app.service import (
    DataService,
    build_backtest_report,
    build_snapshot_from_payloads,
    dashboard_data_from_snapshot,
    fetch_sporttery_json,
    odds_history_records_from_snapshot,
    snapshot_from_dict,
    snapshot_to_dict,
)


POLYALPHA = {
    "generated_at": "2026-06-11T09:00",
    "predictions": [
        {
            "date": "2026-06-11",
            "home": "Mexico",
            "away": "South Africa",
            "p_home": 0.7926,
            "p_draw": 0.1549,
            "p_away": 0.0525,
        },
        {
            "date": "2026-06-11",
            "home": "Qatar",
            "away": "Switzerland",
            "p_home": 0.0091,
            "p_draw": 0.0365,
            "p_away": 0.9544,
        },
    ],
    "simulation": {"title_probability": {"Mexico": 0.01}},
    "schedule": [],
}

POLYALPHA_INDEX = """
<script>
const TEAM = {
  "Mexico":["mx","墨西哥"],
  "South Africa":["za","南非"],
  "Qatar":["qa","卡塔尔"],
  "Switzerland":["ch","瑞士"]
};
</script>
"""

SPORTTERY = {
    "errorCode": "0",
    "success": True,
    "value": {
        "lastUpdateTime": "2026-06-11 21:40:54",
        "totalCount": 2,
        "matchInfoList": [
            {
                "businessDate": "2026-06-11",
                "subMatchList": [
                    {
                        "matchNumStr": "周四001",
                        "matchId": 2040162,
                        "matchDate": "2026-06-12",
                        "matchTime": "03:00:00",
                        "matchStatus": "Selling",
                        "homeTeamAllName": "墨西哥",
                        "awayTeamAllName": "南非",
                        "had": {
                            "h": "1.26",
                            "d": "4.45",
                            "a": "9.00",
                            "updateDate": "2026-06-11",
                            "updateTime": "12:25:40",
                        },
                        "hhad": {"h": "2.00", "d": "3.25", "a": "3.11", "goalLine": "-1"},
                        "poolList": [
                            {"poolCode": "HHAD", "poolStatus": "Selling"},
                            {"poolCode": "HAD", "poolStatus": "Selling"},
                        ],
                    },
                    {
                        "matchNumStr": "周六005",
                        "matchId": 2040166,
                        "matchDate": "2026-06-14",
                        "matchTime": "03:00:00",
                        "matchStatus": "Selling",
                        "homeTeamAllName": "卡塔尔",
                        "awayTeamAllName": "瑞士",
                        "had": {},
                        "hhad": {"h": "2.02", "d": "3.82", "a": "2.69", "goalLine": "+2"},
                        "poolList": [{"poolCode": "HHAD", "poolStatus": "Selling"}],
                    },
                ],
            }
        ],
    },
}

TEST_NOW = datetime(2026, 6, 11, 12, 0, tzinfo=ZoneInfo("Asia/Shanghai"))


class SnapshotServiceTests(unittest.TestCase):
    def test_had_missing_match_is_skipped_from_ev_but_kept_in_odds(self):
        snapshot = build_snapshot_from_payloads(POLYALPHA, POLYALPHA_INDEX, SPORTTERY, now=TEST_NOW)

        self.assertEqual(snapshot.status.valid_had_matches, 1)
        self.assertEqual(snapshot.status.skipped_matches, 1)
        self.assertEqual(len(snapshot.single_top), 1)
        self.assertEqual(snapshot.single_top[0].match_num, "周四001")
        self.assertEqual(snapshot.single_top[0].pick_label, "胜")
        skipped = [row for row in snapshot.odds.matches if not row.participates_ev]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].skip_reason, "HAD_not_selling_or_missing")

    def test_team_name_mapping_uses_polyalpha_index_chinese_names(self):
        snapshot = build_snapshot_from_payloads(POLYALPHA, POLYALPHA_INDEX, SPORTTERY, now=TEST_NOW)

        row = snapshot.odds.matches[0]
        self.assertEqual(row.home_en, "Mexico")
        self.assertEqual(row.away_en, "South Africa")
        self.assertAlmostEqual(row.probabilities["home"], 0.7926)

    def test_refresh_failure_keeps_previous_snapshot_and_marks_stale(self):
        service = DataService()
        service._snapshot = build_snapshot_from_payloads(POLYALPHA, POLYALPHA_INDEX, SPORTTERY, now=TEST_NOW)

        with patch("app.service.fetch_json", side_effect=RuntimeError("network down")):
            snapshot = service.refresh()

        self.assertTrue(snapshot.status.stale)
        self.assertEqual(snapshot.status.valid_had_matches, 1)
        self.assertIn("network down", snapshot.status.errors[-1])

    def test_sporttery_fetch_tries_both_official_gateway_paths(self):
        with patch("app.service.fetch_json", side_effect=[RuntimeError("blocked"), SPORTTERY]) as fetch:
            payload = fetch_sporttery_json()

        self.assertIs(payload, SPORTTERY)
        self.assertEqual(fetch.call_count, 2)
        self.assertIn("/gateway/jc/football/", fetch.call_args_list[0].args[0])
        self.assertIn("/gateway/uniform/football/", fetch.call_args_list[1].args[0])

    def test_old_cache_without_nearest_sale_rebuilds_nearest_sale_from_odds_rows(self):
        snapshot = build_snapshot_from_payloads(POLYALPHA, POLYALPHA_INDEX, SPORTTERY, now=TEST_NOW)
        cached = snapshot_to_dict(snapshot)
        cached.pop("nearest_sale")

        loaded = snapshot_from_dict(cached, now=TEST_NOW)

        self.assertEqual(loaded.nearest_sale.match_date, "2026-06-12")
        self.assertEqual(loaded.nearest_sale.match_count, 1)
        self.assertEqual(loaded.nearest_sale.singles[0].match_num, "周四001")

    def test_nearest_sale_day_uses_earliest_selling_had_date_and_lists_all_combos(self):
        polyalpha = copy.deepcopy(POLYALPHA)
        polyalpha["predictions"] = [
            {
                "date": "2026-06-12",
                "home": "Qatar",
                "away": "Switzerland",
                "p_home": 0.01,
                "p_draw": 0.04,
                "p_away": 0.95,
            },
            {
                "date": "2026-06-13",
                "home": "Mexico",
                "away": "South Africa",
                "p_home": 0.50,
                "p_draw": 0.25,
                "p_away": 0.25,
            },
            {
                "date": "2026-06-13",
                "home": "Canada",
                "away": "Bosnia and Herzegovina",
                "p_home": 0.35,
                "p_draw": 0.25,
                "p_away": 0.40,
            },
            {
                "date": "2026-06-13",
                "home": "United States",
                "away": "Paraguay",
                "p_home": 0.36,
                "p_draw": 0.30,
                "p_away": 0.34,
            },
            {
                "date": "2026-06-14",
                "home": "Brazil",
                "away": "Morocco",
                "p_home": 0.80,
                "p_draw": 0.10,
                "p_away": 0.10,
            },
        ]
        polyalpha_index = """
<script>
const TEAM = {
  "Qatar":["qa","卡塔尔"],
  "Switzerland":["ch","瑞士"],
  "Mexico":["mx","墨西哥"],
  "South Africa":["za","南非"],
  "Canada":["ca","加拿大"],
  "Bosnia and Herzegovina":["ba","波黑"],
  "United States":["us","美国"],
  "Paraguay":["py","巴拉圭"],
  "Brazil":["br","巴西"],
  "Morocco":["ma","摩洛哥"]
};
</script>
"""
        sporttery = {
            "value": {
                "lastUpdateTime": "2026-06-12 10:00:00",
                "totalCount": 5,
                "matchInfoList": [
                    {
                        "businessDate": "2026-06-12",
                        "subMatchList": [
                            _match("周五001", 1, "2026-06-12", "卡塔尔", "瑞士", None),
                            _match("周六001", 2, "2026-06-13", "墨西哥", "南非", ("2.40", "3.00", "3.10")),
                            _match("周六002", 3, "2026-06-13", "加拿大", "波黑", ("2.20", "3.00", "3.20")),
                            _match("周六003", 4, "2026-06-13", "美国", "巴拉圭", ("2.00", "4.00", "2.80")),
                            _match("周日001", 5, "2026-06-14", "巴西", "摩洛哥", ("3.00", "3.20", "2.20")),
                        ],
                    }
                ],
            }
        }

        snapshot = build_snapshot_from_payloads(polyalpha, polyalpha_index, sporttery, now=TEST_NOW)

        self.assertEqual(snapshot.nearest_sale.match_date, "2026-06-13")
        self.assertEqual(snapshot.nearest_sale.match_count, 3)
        self.assertEqual([row.match_num for row in snapshot.nearest_sale.singles], ["周六002", "周六001", "周六003"])
        self.assertEqual(set(snapshot.nearest_sale.parlays_by_legs.keys()), {2, 3})
        self.assertEqual(len(snapshot.nearest_sale.parlays_by_legs[2]), 3)
        self.assertEqual(len(snapshot.nearest_sale.parlays_by_legs[3]), 1)
        self.assertNotIn("周日001", [row.match_num for row in snapshot.nearest_sale.singles])
        self.assertGreaterEqual(
            snapshot.nearest_sale.parlays_by_legs[2][0].ev,
            snapshot.nearest_sale.parlays_by_legs[2][-1].ev,
        )

    def test_backtest_report_settles_completed_singles_and_parlays_by_day(self):
        polyalpha = {
            "live_accuracy": {
                "results": [
                    {
                        "date": "2026-06-11",
                        "home": "Mexico",
                        "away": "South Africa",
                        "score": "2-0",
                        "actual": "Mexico win",
                    },
                    {
                        "date": "2026-06-11",
                        "home": "South Korea",
                        "away": "Czech Republic",
                        "score": "2-1",
                        "actual": "South Korea win",
                    },
                ],
                "by_match": {
                    "2026-06-11|Mexico|South Africa": {"score": "2-0", "actual_idx": 0},
                    "2026-06-11|South Korea|Czech Republic": {"score": "2-1", "actual_idx": 0},
                },
            }
        }
        history = {
            "2026-06-11|Mexico|South Africa": {
                "result_date": "2026-06-11",
                "sporttery_date": "2026-06-12",
                "sporttery_time": "03:00",
                "match_num": "周四001",
                "match_id": "1",
                "home_cn": "墨西哥",
                "away_cn": "南非",
                "home_en": "Mexico",
                "away_en": "South Africa",
                "probabilities": {"home": 0.6, "draw": 0.2, "away": 0.2},
                "had_odds": {"home": 2.0, "draw": 3.0, "away": 4.0},
            },
            "2026-06-11|South Korea|Czech Republic": {
                "result_date": "2026-06-11",
                "sporttery_date": "2026-06-12",
                "sporttery_time": "06:00",
                "match_num": "周四002",
                "match_id": "2",
                "home_cn": "韩国",
                "away_cn": "捷克",
                "home_en": "South Korea",
                "away_en": "Czech Republic",
                "probabilities": {"home": 0.2, "draw": 0.2, "away": 0.6},
                "had_odds": {"home": 5.0, "draw": 4.0, "away": 2.0},
            },
        }

        report = build_backtest_report(polyalpha, history)

        self.assertEqual(report["priced_match_count"], 2)
        self.assertEqual(report["unpriced_match_count"], 0)
        day = report["days"][0]
        self.assertEqual(day["date"], "2026-06-11")
        self.assertEqual(day["summary"]["single_stake"], 2)
        self.assertAlmostEqual(day["summary"]["single_profit"], 0.0)
        self.assertEqual([row["selected_pick"] for row in day["singles"]], ["home", "away"])
        self.assertEqual([row["hit"] for row in day["singles"]], [True, False])
        self.assertAlmostEqual(day["parlays_by_legs"]["2"][0]["decimal_odds"], 4.0)
        self.assertAlmostEqual(day["parlays_by_legs"]["2"][0]["ev"], 0.44)
        self.assertFalse(day["parlays_by_legs"]["2"][0]["hit"])
        self.assertAlmostEqual(day["parlays_by_legs"]["2"][0]["profit"], -1.0)

    def test_backtest_report_lists_completed_matches_without_historical_odds(self):
        polyalpha = {
            "live_accuracy": {
                "results": [
                    {
                        "date": "2026-06-11",
                        "home": "Mexico",
                        "away": "South Africa",
                        "score": "2-0",
                        "actual": "Mexico win",
                    }
                ],
                "by_match": {"2026-06-11|Mexico|South Africa": {"score": "2-0", "actual_idx": 0}},
            }
        }

        report = build_backtest_report(polyalpha, {})

        self.assertEqual(report["priced_match_count"], 0)
        self.assertEqual(report["unpriced_match_count"], 1)
        self.assertEqual(report["days"][0]["unpriced_matches"][0]["match_label"], "Mexico vs South Africa")
        self.assertEqual(report["days"][0]["summary"]["single_stake"], 0)

    def test_odds_history_records_from_snapshot_use_polyalpha_result_date(self):
        snapshot = build_snapshot_from_payloads(POLYALPHA, POLYALPHA_INDEX, SPORTTERY, now=TEST_NOW)

        records = odds_history_records_from_snapshot(snapshot)

        self.assertIn("2026-06-11|Mexico|South Africa", records)
        record = records["2026-06-11|Mexico|South Africa"]
        self.assertEqual(record["result_date"], "2026-06-11")
        self.assertEqual(record["sporttery_date"], "2026-06-12")
        self.assertEqual(record["match_num"], "周四001")

    def test_dashboard_data_from_snapshot_matches_frontend_contract(self):
        snapshot = build_snapshot_from_payloads(POLYALPHA, POLYALPHA_INDEX, SPORTTERY, now=TEST_NOW)

        payload = dashboard_data_from_snapshot(snapshot, history={})

        self.assertEqual(payload["status"]["valid_had_matches"], 1)
        self.assertIn("polyalpha", payload)
        self.assertIn("odds", payload)
        self.assertIn("singles", payload)
        self.assertIn("parlays", payload)
        self.assertIn("nearestSale", payload)
        self.assertIn("accuracyStrategy", payload)
        self.assertIn("backtest", payload)
        self.assertFalse(payload["staticMode"])
        self.assertEqual(set(payload["parlays"].keys()), {"2", "3", "4", "5", "6", "7", "8"})


def _match(match_num, match_id, match_date, home, away, had_odds):
    had = {}
    pool_list = [{"poolCode": "HHAD", "poolStatus": "Selling"}]
    if had_odds is not None:
        h, d, a = had_odds
        had = {"h": h, "d": d, "a": a, "updateDate": "2026-06-12", "updateTime": "10:00:00"}
        pool_list.append({"poolCode": "HAD", "poolStatus": "Selling"})
    return {
        "matchNumStr": match_num,
        "matchId": match_id,
        "matchDate": match_date,
        "matchTime": "03:00:00",
        "matchStatus": "Selling",
        "homeTeamAllName": home,
        "awayTeamAllName": away,
        "had": had,
        "hhad": {"h": "2.00", "d": "3.25", "a": "3.11", "goalLine": "-1"},
        "poolList": pool_list,
    }


if __name__ == "__main__":
    unittest.main()
