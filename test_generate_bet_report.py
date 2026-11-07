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
        markup = report._book_badge("Bet365", logo_base_href="logos", available_logo_files={"fanduel.png"})

        self.assertIn("badge-sticker", markup)
        self.assertIn(">Bet365<", markup)
        self.assertNotIn("<img", markup)

    def test_betonline_abbreviation_uses_logo(self) -> None:
        markup = report._book_badge("BOL", logo_base_href="logos", available_logo_files={"betonline.png"})

        self.assertIn('src="logos/betonline.png"', markup)
        self.assertIn('alt="BOL"', markup)
        self.assertNotIn("badge-sticker", markup)


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

        today_html = html_doc.split('<section id="today-panel"', 1)[1].split('</section>', 1)[0]
        self.assertIn('<dt>Settled net</dt><dd class="positive">$114</dd>', today_html)
        self.assertIn('<dt>Total risk</dt><dd>$250</dd>', today_html)
        self.assertIn('<dt>Open risk</dt><dd class="today-risk-value">$100</dd>', today_html)
        self.assertIn('today-bet--open', today_html)
        self.assertIn('today-bet--won', today_html)
        self.assertIn('today-bet--lost', today_html)
        self.assertIn('today-bet--cash-out', today_html)
        self.assertIn('<dd class="positive">+$100</dd>', today_html)
        self.assertIn('<dd class="negative">−$10</dd>', today_html)
        self.assertEqual(today_html.count('<li class="today-bet '), 6)
        self.assertIn('<details class="today-group" data-today-group="closed" aria-labelledby="today-closed-title">', today_html)
        self.assertIn('<summary id="today-closed-title"', today_html)
        self.assertIn("| Last synced ", html_doc)
        self.assertNotIn("Showing data from", html_doc)
        self.assertIn("Cash Out", html_doc)
        self.assertIn("Cash out: 1", html_doc)
        self.assertIn("Settled ROI:", html_doc)
        self.assertIn("Edge vs implied:", html_doc)
        self.assertNotIn("Avg odds:", html_doc)
        self.assertNotIn('class="negative"></td>', html_doc)
        self.assertNotIn('class="negative"></span>', html_doc)
        self.assertNotIn('class="below50"', html_doc)
        self.assertIn('class="positive">33.33%</td>', html_doc)

    def test_today_combines_wagers_and_escapes_titles(self) -> None:
        today = report.dt.date.today()
        bets = [
            _bet(date=today, pick='<Win & "total">', result='', risk=20.0, to_win=30.0, net=float('nan')),
            _bet(date=today, pick='<Win & "total">', result='', risk=40.0, to_win=60.0, net=float('nan'), book='DraftKings'),
            _bet(date=today, pick='Pushed wager', result='P', risk=10.0, net=0.0),
        ]
        summary = report.summarize(bets)
        doc = report.build_html_report(summary, 'Test', {}, 'NFL', available_logo_files=set())
        today_html = doc.split('<section id="today-panel"', 1)[1].split('</section>', 1)[0]
        self.assertEqual(today_html.count('<li class="today-bet '), 2)
        self.assertNotIn('wagers combined', today_html)
        self.assertIn('&lt;Win &amp; &quot;total&quot;&gt;', today_html)
        self.assertIn('<dt>Risk</dt><dd>$60<span class="today-units" title="1u = $100">0.60u</span></dd>', today_html)
        self.assertIn('<dt>wins</dt><dd class="">$90</dd>', today_html)
        self.assertIn('today-bet--push', today_html)
        self.assertIn('<dt class="today-net-label">Net result</dt><dd class="">$0</dd>', today_html)

    def test_today_empty_state(self) -> None:
        doc = report.build_html_report(report.summarize([]), 'Test', {}, 'NFL')
        today_html = doc.split('<section id="today-panel"', 1)[1].split('</section>', 1)[0]
        self.assertIn('No bets today.', today_html)
        self.assertNotIn('<li class="today-bet ', today_html)
        self.assertIn('<dt>Total risk</dt><dd>$0</dd>', today_html)
        self.assertIn('No upcoming open bets.', doc)

    def test_upcoming_cards_preserve_dates_and_stay_separate_from_today(self) -> None:
        today = report.dt.date.today()
        tomorrow = today + report.dt.timedelta(days=1)
        later = today + report.dt.timedelta(days=2)
        bets = [
            _bet(date=today, pick='Today only', result='W', net=100.0),
            _bet(date=later, pick='Later pick', result='', net=float('nan'), risk=25.5, to_win=50.0),
            _bet(date=tomorrow, pick='Next pick', result='', net=float('nan'), risk=60.0, to_win=90.0),
            _bet(date=tomorrow, pick='Next pick', result='', net=float('nan'), risk=40.0, to_win=60.0, book='DraftKings'),
        ]
        doc = report.build_html_report(report.summarize(bets), 'Test', {}, 'MLB', available_logo_files=set())
        upcoming = doc.split('<section id="upcoming-panel"', 1)[1].split('</section>', 1)[0]
        today_html = doc.split('<section id="today-panel"', 1)[1].split('</section>', 1)[0]
        self.assertNotIn('Today only', upcoming)
        self.assertNotIn('Next pick', today_html)
        self.assertEqual(upcoming.count('<li class="today-bet '), 2)
        self.assertLess(upcoming.index('Next pick'), upcoming.index('Later pick'))
        self.assertIn(f'<time datetime="{tomorrow.isoformat()}">', upcoming)
        self.assertNotIn('wagers combined', upcoming)
        self.assertIn('<dt>Open risk</dt><dd class="today-risk-value">$125.50</dd>', upcoming)
        self.assertIn('<dt>wins</dt><dd>$200</dd>', upcoming)
        self.assertIn('title="1u = $100">1u</span>', upcoming)
        self.assertIn('aria-controls="upcoming-bets"', upcoming)
        self.assertNotIn('aria-controls="today-bets"', upcoming)
        self.assertNotIn('data-today-status=', upcoming)


class TodayTeamLogoTests(unittest.TestCase):
    def test_nhl_and_nfl_abbreviations_become_logos(self) -> None:
        # WAS is an alias of WSH; the file on disk is wsh.png.
        files = {
            "teams/nhl/mtl.png",
            "teams/nhl/tor.png",
            "teams/nhl/tbl.png",
            "teams/nfl/wsh.png",
            "teams/nfl/sea.png",
            "teams/nfl/kc.png",
            "teams/nfl/no.png",
        }
        nhl = report._today_pick_html("MTL/TOR 1P o1.5", "NHL", "logos", files)
        self.assertIn('src="logos/teams/nhl/mtl.png"', nhl)
        self.assertIn('alt="Montreal Canadiens"', nhl)
        self.assertIn('data-name="Montreal Canadiens"', nhl)
        self.assertIn('src="logos/teams/nhl/tor.png"', nhl)
        self.assertIn("1P o1.5", nhl)
        self.assertNotIn(">MTL<", nhl)
        self.assertIn('src="logos/teams/nhl/tbl.png"', report._today_pick_html("TBI/NYI o5.5", "NHL", "logos", files | {"teams/nhl/nyi.png"}))

        nfl = report._today_pick_html("WAS/SEA u48", "NFL", "logos", files)
        self.assertIn('src="logos/teams/nfl/wsh.png"', nfl)
        self.assertIn('data-name="Washington Commanders"', nfl)
        self.assertIn('src="logos/teams/nfl/sea.png"', nfl)
        self.assertIn('data-name="Kansas City Chiefs"', report._today_pick_html("Johnson 1st KC TD", "NFL", "logos", files))

    def test_mlb_and_nba_abbreviations_become_logos(self) -> None:
        files = {
            "teams/mlb/lad.png",
            "teams/mlb/wsh.png",
            "teams/mlb/chc.png",
            "teams/mlb/cws.png",
            "teams/mlb/ari.png",
            "teams/mlb/ath.png",
            "teams/nba/wsh.png",
            "teams/nba/cle.png",
            "teams/nba/okc.png",
        }
        mlb = report._today_pick_html("LAD/WSH o8.5", "MLB", "logos", files)
        self.assertIn('src="logos/teams/mlb/lad.png"', mlb)
        self.assertIn('data-name="Washington Nationals"', mlb)
        self.assertIn("o8.5", mlb)
        cubs = report._today_pick_html("CHI/CWS o11.5", "MLB", "logos", files)
        self.assertIn('src="logos/teams/mlb/chc.png"', cubs)
        self.assertIn('data-name="Chicago White Sox"', cubs)
        self.assertIn('src="logos/teams/mlb/ari.png"', report._today_pick_html("COL/AZ o11", "MLB", "logos", files | {"teams/mlb/col.png"}))
        self.assertIn('data-name="Athletics"', report._today_pick_html("MIN/OAK o11.5", "MLB", "logos", files | {"teams/mlb/min.png"}))
        self.assertEqual(report._today_pick_html("NL/AL o7.5", "MLB", "logos", files), "NL/AL o7.5")
        self.assertEqual(report._today_pick_html("NL Cy Young - Misiorowski", "MLB", "logos", files), "NL Cy Young - Misiorowski")

        nba = report._today_pick_html("WAS/CLE o244.5", "NBA", "logos", files)
        self.assertIn('src="logos/teams/nba/wsh.png"', nba)
        self.assertIn('data-name="Washington Wizards"', nba)
        self.assertIn('src="logos/teams/nba/cle.png"', nba)
        self.assertEqual(report._today_pick_html("SGA o49.5 Pts", "NBA", "logos", files), "SGA o49.5 Pts")
        self.assertIn('data-name="Oklahoma City Thunder"', report._today_pick_html("OKC to win NBA Finals", "NBA", "logos", files))

    def test_ncaa_abbreviations_use_clear_logos_only(self) -> None:
        def espn(slug: str) -> str:
            return report.ESPN_NCAA_LOGO.format(team_id=report.NCAA_ESPN_IDS[slug])

        basketball = report._today_pick_html("DUKE/NCST o52", "NCAAB", "logos", set())
        self.assertIn(f'src="{espn("duke")}"', basketball)
        self.assertIn('data-name="NC State"', basketball)
        self.assertIn(f'src="{espn("miami")}"', report._today_pick_html("MI-FL -3", "NCAAF", "logos", set()))
        self.assertIn('data-name="Miami (OH)"', report._today_pick_html("MIOH +4.5", "NCAAB", "logos", set()))
        self.assertIn(f'src="{espn("michiganState")}"', report._today_pick_html("MSU/USC o148.5", "NCAAB", "logos", set()))
        self.assertNotIn(espn("mississippiState"), report._today_pick_html("MSU/USC o148.5", "NCAAB", "logos", set()))
        cb = report._today_pick_html("CB/UTAH o144.5", "NCAAB", "logos", set())
        self.assertIn(f'src="{espn("californiaBaptist")}"', cb)
        self.assertIn('data-name="California Baptist"', cb)
        self.assertIn('data-name="Utah"', cb)
        self.assertIn(f'src="{espn("californiaBaptist")}"', report._today_pick_html("UTA/CBU o131.5", "NCAAB", "logos", set()))
        ncaab_shu = report._today_pick_html("SHU/NCST u144.5", "NCAAB", "logos", set())
        self.assertTrue(ncaab_shu.startswith("SHU/"))
        self.assertNotIn(espn("sacredHeart"), ncaab_shu)
        self.assertIn(espn("ncState"), ncaab_shu)
        self.assertIn('data-name="Sacred Heart"', report._today_pick_html("LIU/SHU u43.5", "NCAAF", "logos", set()))
        gonz = report._today_pick_html("SJU/GONZ o150", "NCAAB", "logos", set())
        self.assertIn(espn("stJohns"), gonz)
        self.assertIn("St. John", gonz)
        self.assertIn(espn("gonzaga"), gonz)
        self.assertIn('data-name="Marshall"', report._today_pick_html("BU, MAR & UNCG ML", "NCAAB", "logos", set()))
        self.assertTrue(report._today_pick_html("TSU/UTSA u65", "NCAAF", "logos", set()).startswith("TSU/"))
        liu = report._today_pick_html("LIU/SHU u43.5", "NCAAF", "logos", set())
        self.assertIn(espn("longIsland"), liu)
        self.assertIn(espn("sacredHeart"), liu)

    def test_non_team_tokens_and_other_leagues_stay_text(self) -> None:
        files = {"teams/nfl/no.png", "teams/nhl/car.png", "teams/ncaab/duke.png"}
        self.assertEqual(
            report._today_pick_html("Opening Kickoff - No Touchback", "NFL", "logos", files),
            "Opening Kickoff - No Touchback",
        )
        self.assertEqual(
            report._today_pick_html("Allen o0.5 Pass OR Rush TD 1Q", "NFL", "logos", files),
            "Allen o0.5 Pass OR Rush TD 1Q",
        )
        self.assertEqual(
            report._today_pick_html("McDavid o1.5 Ast", "NHL", "logos", files),
            "McDavid o1.5 Ast",
        )
        duke = report._today_pick_html("DUKE/NCST o52", "NCAAB", "logos", files)
        self.assertIn(report.ESPN_NCAA_LOGO.format(team_id=report.NCAA_ESPN_IDS["duke"]), duke)
        self.assertNotIn("logos/teams/ncaa/duke.png", duke)
        self.assertEqual(
            report._today_pick_html("MTL/TOR o6.5", "NHL", "logos", set()),
            "MTL/TOR o6.5",
        )
        self.assertIn("&lt;script&gt;", report._today_pick_html("MTL <script>", "NHL", "logos", set()))

    def test_today_cards_use_logos_and_tables_keep_abbreviations(self) -> None:
        today = report.dt.date.today()
        bets = [
            _bet(date=today, pick="MTL/TOR o6.5", league="NHL", result="", net=float("nan"), bet_type="Total"),
            _bet(date=today, pick="DUKE/NCST o52", league="NCAAB", result="", net=float("nan"), bet_type="Total"),
        ]
        doc = report.build_html_report(
            report.summarize(bets),
            "Test",
            {},
            "NHL",
            logo_base_href="logos",
            available_logo_files={"teams/nhl/mtl.png", "teams/nhl/tor.png"},
        )
        today_html = doc.split('<section id="today-panel"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="team-logo" src="logos/teams/nhl/mtl.png"', today_html)
        self.assertIn('class="team-logo" src="logos/teams/nhl/tor.png"', today_html)
        self.assertIn(report.ESPN_NCAA_LOGO.format(team_id=report.NCAA_ESPN_IDS["duke"]), today_html)
        self.assertIn(report.ESPN_NCAA_LOGO.format(team_id=report.NCAA_ESPN_IDS["ncState"]), today_html)
        self.assertEqual(today_html.count('class="team-logo"'), 4)
        self.assertIn('title="Montreal Canadiens/Toronto Maple Leafs o6.5 · -110"', today_html)
        self.assertIn('data-name="Montreal Canadiens"', today_html)
        self.assertIn('title="Duke/NC State o52 · -110"', today_html)
        table = doc.split("id='all-bets-table'", 1)[1].split("</table>", 1)[0]
        self.assertIn("MTL/TOR o6.5", table)
        self.assertNotIn("team-logo", table)


if __name__ == "__main__":
    unittest.main()
