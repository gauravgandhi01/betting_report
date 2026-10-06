import math
import os
import sys
import unittest


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "betting_analysis"))

import generate_bet_report as report


class BadgeTests(unittest.TestCase):
    def test_logo_badge_shows_only_the_logo(self) -> None:
        markup = report._league_badge("NHL", logo_base_href="logos", available_logo_files={"nhl.png"})

        self.assertIn('src="logos/nhl.png"', markup)
        self.assertIn('alt="NHL"', markup)
        self.assertIn('title="NHL"', markup)
        self.assertNotIn(">NHL<", markup)
        self.assertNotIn("badge-sticker", markup)

    def test_missing_logo_uses_text_sticker(self) -> None:
        markup = report._book_badge("Bet365", logo_base_href="logos", available_logo_files={"fanduel.jpeg"})

        self.assertIn("badge-sticker", markup)
        self.assertIn(">Bet365<", markup)
        self.assertNotIn("<img", markup)


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


class SummaryStreakTests(unittest.TestCase):
    def test_summary_only_tracks_daily_streaks(self) -> None:
        bets = [
            report.Bet(
                date=report.dt.date(2026, 6, 24),
                pick="A",
                odds_american=-110.0,
                risk=55.0,
                to_win=50.0,
                result="W",
                net=50.0,
                book="Book",
                league="MLB",
                bet_type="ML",
            ),
            report.Bet(
                date=report.dt.date(2026, 6, 24),
                pick="B",
                odds_american=-110.0,
                risk=55.0,
                to_win=50.0,
                result="L",
                net=-55.0,
                book="Book",
                league="MLB",
                bet_type="ML",
            ),
            report.Bet(
                date=report.dt.date(2026, 6, 25),
                pick="C",
                odds_american=-110.0,
                risk=55.0,
                to_win=50.0,
                result="L",
                net=-55.0,
                book="Book",
                league="MLB",
                bet_type="ML",
            ),
        ]

        summary = report.summarize(bets)

        self.assertEqual(set(summary["streaks"].keys()), {"daily"})
        self.assertEqual(summary["streaks"]["daily"]["current"]["type"], "loss")
        self.assertEqual(summary["streaks"]["daily"]["current"]["length"], 2)


def _bet(**overrides: object) -> report.Bet:
    values = {
        "date": report.dt.date(2026, 6, 24),
        "pick": "A",
        "odds_american": -110.0,
        "risk": 110.0,
        "to_win": 100.0,
        "result": "W",
        "net": 100.0,
        "book": "FanDuel",
        "league": "MLB",
        "bet_type": "ML",
    }
    values.update(overrides)
    return report.Bet(**values)


class SettledPerformanceTests(unittest.TestCase):
    def test_open_net_does_not_poison_sums_or_color(self) -> None:
        self.assertEqual(report._sum_finite([float("nan"), None, 10.0, 5.5]), 15.5)
        self.assertEqual(report._net_class(float("nan")), "")
        self.assertEqual(report._net_class(0.0), "")
        self.assertEqual(report._net_class(5.0), "positive")
        self.assertEqual(report._net_class(-5.0), "negative")
        self.assertEqual(report._result_label("CO"), "Cash Out")
        self.assertEqual(report._result_label(""), "")

    def test_roi_excludes_open_risk_and_counts_cash_outs(self) -> None:
        bets = [
            _bet(pick="Win", result="W", risk=50.0, net=50.0),
            _bet(pick="Open", result="", risk=1000.0, net=float("nan")),
            _bet(pick="Hedge", result="CO", risk=10.0, net=4.0, book="DraftKings"),
        ]

        summary = report.summarize(bets)

        self.assertAlmostEqual(summary["totals"]["net"], 54.0)
        self.assertAlmostEqual(summary["totals"]["risk"], 60.0)
        self.assertAlmostEqual(summary["totals"]["roi"], 54.0 / 60.0)
        self.assertEqual(summary["counts"]["open"], 1)
        self.assertEqual(summary["counts"]["cash_outs"], 1)
        self.assertEqual(summary["counts"]["other"], 0)
        self.assertAlmostEqual(summary["open_exposure"], 1000.0)
        self.assertEqual(summary["counts"]["wins"], 1)
        self.assertEqual(summary["averages"]["win_rate"], 1.0)

    def test_edge_uses_decided_bets_and_ignores_open_prices(self) -> None:
        bets = [
            _bet(pick="Dog1", odds_american=300.0, risk=10.0, to_win=30.0, result="W", net=30.0, book="Novig"),
            _bet(pick="Dog2", odds_american=300.0, risk=10.0, to_win=30.0, result="L", net=-10.0, book="Novig"),
            _bet(pick="Dog3", odds_american=300.0, risk=10.0, to_win=30.0, result="L", net=-10.0, book="Novig"),
            _bet(pick="Open longshot", odds_american=1000.0, risk=10.0, result="", net=float("nan"), book="Novig"),
        ]

        summary = report.summarize(bets)
        novig = next(row for row in summary["by_book"] if row["key"] == "Novig")

        implied = 100.0 / 400.0
        self.assertAlmostEqual(summary["averages"]["win_rate"], 1.0 / 3.0)
        self.assertAlmostEqual(summary["averages"]["avg_implied_prob"], implied)
        self.assertAlmostEqual(summary["averages"]["edge"], (1.0 / 3.0) - implied)
        self.assertGreater(summary["averages"]["edge"], 0)
        self.assertAlmostEqual(novig["roi"], 10.0 / 30.0)
        self.assertGreater(novig["edge"], 0)
        self.assertEqual(report._edge_class(novig["edge"]), "positive")

    def test_period_roi_excludes_open_stakes(self) -> None:
        today = report.dt.date(2026, 6, 24)
        bets = [
            _bet(date=today, result="W", risk=50.0, net=50.0),
            _bet(date=today, pick="Open", result="", risk=500.0, net=float("nan")),
        ]

        metrics = report._period_metrics(bets, today, today, 1)

        self.assertAlmostEqual(metrics["net"], 50.0)
        self.assertAlmostEqual(metrics["risk"], 50.0)
        self.assertAlmostEqual(metrics["roi"], 1.0)
        self.assertEqual(metrics["open"], 1)

    def test_report_labels_cash_outs_and_skips_blank_nets(self) -> None:
        today = report.dt.date.today()
        bets = [
            _bet(date=today, pick="Open Pick", result="", risk=100.0, net=float("nan"), league="NFL"),
            _bet(date=today, pick="Settled Win", result="W", risk=110.0, net=100.0, league="NFL"),
            _bet(
                date=today,
                pick="Hedge",
                result="CO",
                risk=10.0,
                net=4.0,
                book="DraftKings",
                league="NFL",
            ),
            _bet(date=today, pick="Dog1", odds_american=300.0, risk=10.0, to_win=30.0, result="W", net=30.0, book="Novig", league="MLB"),
            _bet(date=today, pick="Dog2", odds_american=300.0, risk=10.0, to_win=30.0, result="L", net=-10.0, book="Novig", league="MLB"),
            _bet(date=today, pick="Dog3", odds_american=300.0, risk=10.0, to_win=30.0, result="L", net=-10.0, book="Novig", league="MLB"),
        ]
        summary = report.summarize(bets)
        html_doc = report.build_html_report(
            summary,
            title="Test",
            league_summaries={"MLB": report.summarize([b for b in bets if b.league == "MLB"])},
            default_sport="MLB",
            available_logo_files=set(),
        )

        self.assertIn("Settled net: $114.00", html_doc)
        self.assertIn("Cash Out", html_doc)
        self.assertIn("Cash out: 1", html_doc)
        self.assertIn("Settled ROI:", html_doc)
        self.assertIn("Edge vs implied:", html_doc)
        self.assertNotIn("Avg odds:", html_doc)
        self.assertNotIn('class="negative"></td>', html_doc)
        self.assertNotIn('class="negative"></span>', html_doc)
        self.assertNotIn('class="below50"', html_doc)
        self.assertIn('class="positive">33.33%</td>', html_doc)


if __name__ == "__main__":
    unittest.main()
