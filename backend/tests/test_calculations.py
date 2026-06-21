import time
import unittest

from app.calculations import combo_ev, max_probability_pick_for_match, single_ev, top_parlays_by_legs
from app.models import BestBet


class CalculationTests(unittest.TestCase):
    def test_single_ev_uses_decimal_odds_net_profit(self):
        self.assertAlmostEqual(single_ev(0.5, 2.1), 0.05)

    def test_combo_ev_multiplies_probability_and_decimal_odds(self):
        self.assertAlmostEqual(combo_ev([0.5, 0.4], [2.1, 3.0]), 0.26)

    def test_max_probability_strategy_uses_fixed_accuracy_for_ev(self):
        bet = max_probability_pick_for_match(
            match_num="M01",
            match_id="1",
            match_label="A vs B",
            home_cn="A",
            away_cn="B",
            probabilities={"home": 0.62, "draw": 0.22, "away": 0.16},
            had_odds={"home": 1.8, "draw": 3.3, "away": 5.2},
            accuracy=0.5,
        )

        self.assertEqual(bet.pick, "home")
        self.assertAlmostEqual(bet.model_probability, 0.62)
        self.assertAlmostEqual(bet.probability, 0.5)
        self.assertAlmostEqual(bet.ev, -0.1)

    def test_top_parlays_returns_limit_per_leg_without_full_result_table(self):
        bets = [
            BestBet(
                match_num=f"M{i:02d}",
                match_id=str(i),
                match_label=f"A{i} vs B{i}",
                pick="away",
                pick_label="客胜",
                team_or_draw=f"B{i}",
                probability=0.34 + i * 0.001,
                odds=3.1 + i * 0.02,
                ev=0.0,
                factor=(0.34 + i * 0.001) * (3.1 + i * 0.02),
            )
            for i in range(72)
        ]

        started = time.perf_counter()
        result = top_parlays_by_legs(bets, min_legs=2, max_legs=8, limit=10)
        elapsed = time.perf_counter() - started

        self.assertLess(elapsed, 2.0)
        self.assertEqual(set(result.keys()), {2, 3, 4, 5, 6, 7, 8})
        self.assertTrue(all(len(rows) == 10 for rows in result.values()))
        self.assertTrue(all(row.ev > 0 for rows in result.values() for row in rows))


if __name__ == "__main__":
    unittest.main()
