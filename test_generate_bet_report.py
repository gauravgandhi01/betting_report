import math
import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "betting_analysis"))

import generate_bet_report as report


class CollapseBetRowsTests(unittest.TestCase):
    def test_collapse_uses_effective_odds_when_books_cross_plus_minus_boundary(self) -> None:
        rows = [
            {
                "date": "2026-06-26",
                "pick": "Misiorowski o8.5 K",
                "league": "MLB",
                "type": "Player Prop",
                "result": "",
                "book": "BM",
                "odds": -108.0,
                "risk": 108.27,
                "to_win": 100.25,
                "net": float("nan"),
            },
            {
                "date": "2026-06-26",
                "pick": "Misiorowski o8.5 K",
                "league": "MLB",
                "type": "Player Prop",
                "result": "",
                "book": "Novig",
                "odds": 105.0,
                "risk": 47.06,
                "to_win": 49.75,
                "net": float("nan"),
            },
        ]

        collapsed = report._collapse_bet_rows(rows)

        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["odds"], -104.0)
        self.assertAlmostEqual(collapsed[0]["risk"], 155.33, places=2)
        self.assertAlmostEqual(collapsed[0]["to_win"], 150.00, places=2)

    def test_collapse_uses_stake_weighted_effective_odds_for_same_side_prices(self) -> None:
        rows = [
            {
                "date": "2026-06-26",
                "pick": "Skenes o7.5 K",
                "league": "MLB",
                "type": "Player Prop",
                "result": "",
                "book": "FanDuel",
                "odds": -132.0,
                "risk": 198.00,
                "to_win": 150.00,
                "net": float("nan"),
            },
            {
                "date": "2026-06-26",
                "pick": "Skenes o7.5 K",
                "league": "MLB",
                "type": "Player Prop",
                "result": "",
                "book": "Novig",
                "odds": -135.0,
                "risk": 34.71,
                "to_win": 25.65,
                "net": float("nan"),
            },
        ]

        collapsed = report._collapse_bet_rows(rows)

        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["odds"], -132.0)
        self.assertTrue(math.isnan(collapsed[0]["net"]))

    def test_single_row_keeps_original_listed_odds(self) -> None:
        rows = [
            {
                "date": "2026-06-24",
                "pick": "Gibson o4.5 K",
                "league": "MLB",
                "type": "Player Prop",
                "result": "W",
                "book": "Novig",
                "odds": 100.0,
                "risk": 100.0,
                "to_win": 100.93,
                "net": 100.93,
            }
        ]

        collapsed = report._collapse_bet_rows(rows)

        self.assertEqual(len(collapsed), 1)
        self.assertEqual(collapsed[0]["odds"], 100.0)


if __name__ == "__main__":
    unittest.main()
