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
        self.assertEqual(report._result_mark_html("W"), '<span class="result-mark result-win">W</span>')
        self.assertEqual(report._result_mark_html("L"), '<span class="result-mark result-loss">L</span>')
        self.assertEqual(report._result_mark_html("CO"), '<span class="result-mark result-cash">Cash Out</span>')
        self.assertEqual(report._result_mark_html(""), "")

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
        self.assertIn('<details class="today-group" data-today-group="closed" aria-labelledby="today-closed-title" open>', today_html)
        self.assertIn('<summary id="today-closed-title"', today_html)
        self.assertIn("| Last synced ", html_doc)
        self.assertNotIn("Showing data from", html_doc)
        self.assertIn("Cash Out", html_doc)
        self.assertIn('class="result-mark result-win">W</span>', html_doc)
        self.assertIn('class="result-mark result-loss">L</span>', html_doc)
        self.assertIn('class="result-mark result-cash">Cash Out</span>', html_doc)
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
        self.assertIn('&lt;Win &quot;total&quot;&gt;', today_html)
        self.assertIn('<dt>Risk</dt><dd><span class="today-risk-amount" title="0.60u · 1u = $100">$60</span></dd>', today_html)
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
        self.assertIn('title="1u · 1u = $100">$100</span>', upcoming)
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
        self.assertIn('class="team-abbr">MTL</span>', nhl)
        self.assertIn('class="team-abbr">TOR</span>', nhl)
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
        self.assertEqual(report._today_pick_html("NL/AL o7.5", "MLB", "logos", files), "NL AL o7.5")
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
        self.assertTrue(ncaab_shu.startswith("SHU "))
        self.assertNotIn(espn("sacredHeart"), ncaab_shu)
        self.assertIn(espn("ncState"), ncaab_shu)
        self.assertIn('data-name="Sacred Heart"', report._today_pick_html("LIU/SHU u43.5", "NCAAF", "logos", set()))
        gonz = report._today_pick_html("SJU/GONZ o150", "NCAAB", "logos", set())
        self.assertIn(espn("stJohns"), gonz)
        self.assertIn("St. John", gonz)
        self.assertIn(espn("gonzaga"), gonz)
        self.assertIn('data-name="Marshall"', report._today_pick_html("BU, MAR & UNCG ML", "NCAAB", "logos", set()))
        self.assertTrue(report._today_pick_html("TSU/UTSA u65", "NCAAF", "logos", set()).startswith("TSU "))
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
            "MTL TOR o6.5",
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
        self.assertIn('title="Montreal Canadiens Toronto Maple Leafs o6.5 · -110"', today_html)
        self.assertIn('data-name="Montreal Canadiens"', today_html)
        self.assertIn('title="Duke NC State o52 · -110"', today_html)
        table = doc.split("id='all-bets-table'", 1)[1].split("</table>", 1)[0]
        self.assertIn("MTL/TOR o6.5", table)
        self.assertNotIn("team-logo", table)

    def test_today_card_shows_fetched_start_time(self) -> None:
        today = report.dt.date.today()
        bets = [
            _bet(date=today, pick="MTL/TOR o6.5", league="NHL", result="", net=float("nan"), bet_type="Total"),
        ]
        times = {
            (today.isoformat(), "NHL", "MTL/TOR o6.5"): {
                "display": "7:00 PM",
                "iso": "2026-11-08T00:00:00+00:00",
                "title": "Montreal Canadiens at Toronto Maple Leafs · Scotiabank Arena, Toronto · ESPN+",
                "done": "",
            }
        }
        doc = report.build_html_report(
            report.summarize(bets),
            "Test",
            {},
            "NHL",
            logo_base_href="logos",
            available_logo_files={"teams/nhl/mtl.png", "teams/nhl/tor.png"},
            game_times=times,
        )
        today_html = doc.split('<section id="today-panel"', 1)[1].split("</section>", 1)[0]
        self.assertIn('class="today-start"', today_html)
        self.assertIn("7:00 PM", today_html)
        money = today_html.split('class="today-bet-money"', 1)[1].split("</dl>", 1)[0]
        meta = today_html.split('class="today-meta"', 1)[1].split("</div>", 1)[0]
        self.assertIn("7:00 PM", money)
        self.assertIn('class="today-when"', money)
        self.assertNotIn("7:00 PM", meta)
        self.assertIn("Scotiabank Arena, Toronto", today_html)
        self.assertIn('datetime="2026-11-08T00:00:00+00:00"', today_html)

    def test_finished_game_moves_to_closed(self) -> None:
        today = report.dt.date.today()
        tomorrow = today + report.dt.timedelta(days=1)
        bets = [
            _bet(date=today, pick="BOS/NYR o6.5", league="NHL", result="", net=float("nan"), bet_type="Total"),
            _bet(date=today, pick="MTL/TOR o6.5", league="NHL", result="", net=float("nan"), bet_type="Total"),
            _bet(date=today, pick="TBL/MIN o6.5", league="NHL", result="", net=float("nan"), bet_type="Total"),
            _bet(date=today, pick="DAL & COL ML", league="NHL", result="", net=float("nan"), bet_type="Parlay"),
            _bet(date=tomorrow, pick="MTL/TOR o6.5", league="NHL", result="", net=float("nan"), bet_type="Total"),
        ]
        def clock(display, iso, done=""):
            return {"display": display, "iso": iso, "title": display, "done": done}

        day = today.isoformat()
        times = {
            (day, "NHL", "BOS/NYR o6.5"): clock("7 PM", "2026-11-08T00:00:00+00:00"),
            (day, "NHL", "MTL/TOR o6.5"): {**clock("Live", "2026-11-07T23:00:00+00:00"), "broadcast": "ESPN"},
            (day, "NHL", "TBL/MIN o6.5"): clock("Final", "2026-11-07T17:00:00+00:00", "1"),
            (day, "NHL", "DAL & COL ML"): clock("Live", "2026-11-07T23:30:00+00:00"),
            (tomorrow.isoformat(), "NHL", "MTL/TOR o6.5"): clock("Live", "2026-11-08T23:00:00+00:00"),
        }
        doc = report.build_html_report(
            report.summarize(bets),
            "Test",
            {},
            "NHL",
            logo_base_href="logos",
            available_logo_files={"teams/nhl/mtl.png", "teams/nhl/tor.png", "teams/nhl/tbl.png", "teams/nhl/min.png"},
            game_times=times,
        )
        today_html = doc.split('<section id="today-panel"', 1)[1].split("</section>", 1)[0]
        upcoming_html = doc.split('<section id="upcoming-panel"', 1)[1].split("</section>", 1)[0]

        def group(html: str, name: str) -> str:
            marker = f'data-today-group="{name}"'
            start = html.index(marker)
            rest = html[start:]
            nxt = rest.find('data-today-group="', len(marker))
            return rest if nxt < 0 else rest[:nxt]

        live_html = group(today_html, "live")
        open_html = group(today_html, "open")
        closed_html = group(today_html, "closed")
        self.assertLess(today_html.index('data-today-group="live"'), today_html.index('data-today-group="open"'))
        self.assertLess(today_html.index('data-today-group="open"'), today_html.index('data-today-group="closed"'))
        self.assertIn('<div class="today-group" data-today-group="live" role="group" aria-labelledby="today-live-title">', today_html)
        self.assertIn('<h3 id="today-live-title" class="today-group-title">Live <span class="today-group-count">2</span></h3>', today_html)
        self.assertIn('data-bet-section="straight"', live_html)
        self.assertIn(">Straight</h4>", live_html)
        self.assertIn("MTL/TOR o6.5", live_html)
        self.assertNotIn('class="today-start is-live"', live_html)
        self.assertNotIn(">Live<", live_html)
        self.assertIn('class="today-broadcast" title="ESPN"', live_html)
        self.assertNotIn("today-broadcast-separator", live_html)
        self.assertIn('data-bet-section="parlay"', live_html)
        self.assertIn(">Parlays</h4>", live_html)
        self.assertIn("DAL &amp; COL ML", live_html)
        self.assertIn("BOS/NYR o6.5", open_html)
        self.assertIn(">7 PM<", open_html)
        self.assertNotIn("MTL/TOR o6.5", open_html)
        self.assertNotIn(">Final<", open_html)
        self.assertIn("TBL/MIN o6.5", closed_html)
        self.assertIn(">Final<", closed_html)
        self.assertIn('class="today-start is-final"', closed_html)
        self.assertNotIn(">Live<", closed_html)
        self.assertNotIn('data-today-group="live"', upcoming_html)
        self.assertIn("MTL/TOR o6.5", upcoming_html)


class CardSortingTests(unittest.TestCase):
    def test_parlay_leg_count_preserves_matchups_and_combined_stats(self) -> None:
        cases = {
            "Robinson o2.5, Concepcion o3.5 & Lamb o5.5 Rec": 3,
            "NYK/PHI u228.5, BOS -14.5 & TOR -5.5": 3,
            "Young o11.5, McDavid o1.5 Ast, Peralta o5.5 K, & Pickens Long Rec o29.5": 4,
            "Texas A&M ML & Duke ML": 2,
            "Fears o9.5 Reb & Ast": None,
            "Fears o9.5 Reb & Ast, Smith o10.5 Pts": 2,
            "A o1,000 Yds and B o1/2": 2,
            "4-leg parlay": 4,
            "Combined pick": None,
        }
        for pick, count in cases.items():
            with self.subTest(pick=pick):
                self.assertEqual(report._parlay_leg_count(pick), count)

    def test_straight_and_parlay_sections_replace_card_badges(self) -> None:
        today = report.dt.date.today()
        for panel, result, days in [("today", "", 0), ("today", "W", 0), ("upcoming", "", 1)]:
            with self.subTest(panel=panel, result=result):
                day = today + report.dt.timedelta(days=days)
                bets = [
                    _bet(date=day, pick="Combined pick", bet_type="Parlay", risk=200, result=result),
                    _bet(date=day, pick="Single pick", bet_type="ML", risk=100, result=result),
                ]
                doc = report.build_html_report(report.summarize(bets), "Test", {}, "MLB")
                panel_html = doc.split(f'<section id="{panel}-panel"', 1)[1].split("</section>", 1)[0]
                straight, parlay = panel_html.split('data-bet-section="parlay"', 1)
                self.assertIn('data-bet-section="straight"', straight)
                self.assertIn('>Straight</h4>', straight)
                self.assertIn('>Single pick</h4>', straight)
                self.assertNotIn('>Combined pick</h4>', straight)
                self.assertIn('>Parlays</h4>', parlay)
                self.assertIn('>Combined pick</h4>', parlay)
                self.assertNotIn('today-parlay', panel_html)

    def test_cards_sort_by_start_then_combined_risk_with_unknown_starts_last(self) -> None:
        today = report.dt.date.today()
        for panel, result, days in [("today", "", 0), ("today", "W", 0), ("upcoming", "", 1)]:
            with self.subTest(panel=panel, result=result):
                day = today + report.dt.timedelta(days=days)
                later_day = day + report.dt.timedelta(days=1) if days else day
                specs = [
                    ("Unknown small", 20, day),
                    ("Late large", 900, later_day),
                    ("Early small", 100, day),
                    ("Unknown large", 1000, day),
                    ("Early combined", 60, day),
                    ("Early combined", 60, day),
                ]
                bets = [_bet(date=date, pick=pick, risk=risk, league="NHL", result=result)
                        for pick, risk, date in specs]
                times = {}
                for pick, date, clock, offset, display in [
                    ("Late large", later_day, "22:00:00", "+00:00", "5 PM"),
                    ("Early small", day, "17:00:00", "+00:00", "Live"),
                    ("Early combined", day, "12:00:00", "-05:00", "Live"),
                ]:
                    times[(date.isoformat(), "NHL", pick)] = {
                        "iso": f"{date.isoformat()}T{clock}{offset}",
                        "display": "Final" if result else display,
                        "title": pick,
                        "done": "1" if result else "",
                    }
                doc = report.build_html_report(report.summarize(bets), "Test", {}, "NHL",
                                               available_logo_files=set(), game_times=times)
                panel_html = doc.split(f'<section id="{panel}-panel"', 1)[1].split("</section>", 1)[0]
                picks = [card.split('<h4 class="today-pick">', 1)[1].split('</h4>', 1)[0]
                         for card in panel_html.split('<li class="today-bet ')[1:]]
                self.assertEqual(picks, ["Early combined", "Early small", "Late large",
                                         "Unknown large", "Unknown small"])

    def test_list_view_exposes_sortable_columns(self) -> None:
        today = report.dt.date.today()
        tomorrow = today + report.dt.timedelta(days=1)
        bets = [
            _bet(date=today, pick="Alpha", odds_american=-110, risk=25, result="", net=float("nan"), to_win=20),
            _bet(date=today, pick="Zulu", odds_american=150, risk=80, result="W", net=40, to_win=40),
            _bet(date=tomorrow, pick="Next", odds_american=-105, risk=15, result="", net=float("nan"), to_win=10),
        ]
        doc = report.build_html_report(report.summarize(bets), "Test", {}, "MLB", available_logo_files=set())
        today_html = doc.split('<section id="today-panel"', 1)[1].split("</section>", 1)[0]
        upcoming = doc.split('<section id="upcoming-panel"', 1)[1].split("</section>", 1)[0]
        for key in ("result", "pick", "odds", "time", "risk", "return"):
            self.assertIn(f'data-list-sort="{key}"', today_html)
        self.assertNotIn('data-list-sort="date"', today_html)
        self.assertIn('data-list-sort="date"', upcoming)
        self.assertNotIn('data-list-sort="result"', upcoming)
        self.assertIn('data-pick="Alpha"', today_html)
        self.assertIn('data-odds="-110.00000000"', today_html)
        self.assertIn('data-pick="Zulu"', today_html)
        self.assertIn('data-odds="150.00000000"', today_html)
        self.assertIn('data-result="W"', today_html)
        self.assertIn('compareTodayBet', doc)
        self.assertIn("bettingReportTodayListSort", doc)
        self.assertIn("bettingReportUpcomingListSort", doc)
        self.assertIn('.today-bet--open .today-league { display: none; }', doc)
        self.assertIn('.today-panel[data-view="list"] .today-bet--open .today-league { display: flex; }', doc)


class GameTimeTests(unittest.TestCase):
    def test_pro_abbreviations_follow_espn_spelling(self) -> None:
        self.assertEqual(report._team_ref("TB", "NHL")["espn_abbr"], "TB")
        self.assertEqual(report._team_ref("TBL", "NHL")["espn_abbr"], "TB")
        self.assertEqual(report._team_ref("LA", "NHL")["espn_abbr"], "LA")
        self.assertEqual(report._team_ref("UTAH", "NHL")["espn_abbr"], "UTA")
        self.assertEqual(report._team_ref("UTA", "NBA")["espn_abbr"], "UTAH")
        self.assertEqual(report._team_ref("WAS", "NBA")["espn_abbr"], "WSH")
        self.assertEqual(report._team_ref("NYK", "NBA")["espn_abbr"], "NY")
        self.assertEqual(report._team_ref("CHW", "MLB")["espn_abbr"], "CHW")
        self.assertEqual(report._team_ref("CWS", "MLB")["espn_abbr"], "CHW")
        self.assertEqual(report._team_ref("DUKE", "NCAAB")["espn_id"], report.NCAA_ESPN_IDS["duke"])

    def test_resolve_uses_espn_abbreviation_and_college_id(self) -> None:
        day = "2026-11-07"
        duke = report.NCAA_ESPN_IDS["duke"]
        ncst = report.NCAA_ESPN_IDS["ncState"]

        def fetch(league: str, date: report.dt.date):
            self.assertEqual(date.isoformat(), day)
            if league == "NHL":
                return [
                    {
                        "abbrs": frozenset({"TB", "MIN"}),
                        "ids": frozenset({"20", "30"}),
                        "display": "8:00 PM",
                        "iso": "2026-11-08T01:00:00+00:00",
                        "title": "Tampa Bay Lightning at Minnesota Wild",
                        "done": False,
                    }
                ], None
            if league == "NCAAF":
                texas = report.NCAA_ESPN_IDS["texas"]
                missouri = report.NCAA_ESPN_IDS["missouri"]
                return [
                    {
                        "abbrs": frozenset({"DUKE", "NCSU"}),
                        "ids": frozenset({duke, ncst}),
                        "display": "12:30 PM",
                        "iso": "2026-11-07T17:30:00+00:00",
                        "title": "Duke at NC State",
                        "done": False,
                    },
                    {
                        "abbrs": frozenset({"TEX", "MIZ"}),
                        "ids": frozenset({texas, missouri}),
                        "display": "12:00 PM",
                        "iso": "2026-11-07T17:00:00+00:00",
                        "title": "Texas at Missouri",
                        "done": False,
                    },
                ], None
            if league == "NFL":
                return [
                    {
                        "abbrs": frozenset({"TB", "ARI"}),
                        "ids": frozenset(),
                        "display": "1:00 PM",
                        "iso": "2026-11-08T18:00:00+00:00",
                        "title": "Tampa Bay Buccaneers at Arizona Cardinals",
                        "done": False,
                    }
                ], None
            return [], "ESPN scoreboard request failed"

        rows = [
            {"date": day, "league": "NHL", "pick": "TBL/MIN 1P o1.5"},
            {"date": day, "league": "NCAAF", "pick": "DUKE/NCST o52"},
            {"date": day, "league": "NFL", "pick": "TB +6"},
            {"date": day, "league": "NCAAF", "pick": "TEX -6.5"},
            {"date": day, "league": "NHL", "pick": "McDavid o1.5 Ast"},
            {"date": day, "league": "NCAAF", "pick": "MSU & GT ML"},
            {"date": day, "league": "NBA", "pick": "NYK/BOS o220"},
        ]
        before_tip = report.dt.datetime(2026, 11, 7, 15, 0, tzinfo=report.dt.timezone.utc)
        times, notes, _logos = report.resolve_game_times(rows, fetch=fetch, now=before_tip)
        self.assertEqual(times[(day, "NHL", "TBL/MIN 1P o1.5")]["display"], "8 PM")
        self.assertEqual(times[(day, "NCAAF", "DUKE/NCST o52")]["display"], "12:30 PM")
        self.assertEqual(times[(day, "NFL", "TB +6")]["display"], "1 PM")
        self.assertEqual(times[(day, "NCAAF", "TEX -6.5")]["display"], "12 PM")
        self.assertNotIn((day, "NCAAF", "MSU & GT ML"), times)
        joined = "\n".join(notes)
        self.assertIn("1 cards have no recognized team abbreviation", joined)
        self.assertNotIn("Michigan State", joined)
        self.assertNotIn("not written as one matchup", joined)
        self.assertIn("ESPN scoreboard request failed", joined)

    def test_live_after_tip_and_final_when_espn_is_done(self) -> None:
        day = "2026-11-07"
        after_tip = report.dt.datetime(2026, 11, 8, 2, 0, tzinfo=report.dt.timezone.utc)
        rows = [{"date": day, "league": "NHL", "pick": "TBL/MIN o6.5"}]

        def fetch(done: bool):
            def _fetch(league: str, date: report.dt.date):
                return [
                    {
                        "abbrs": frozenset({"TB", "MIN"}),
                        "ids": frozenset(),
                        "display": "8:00 PM",
                        "iso": "2026-11-08T01:00:00+00:00",
                        "title": "Tampa Bay Lightning at Minnesota Wild",
                        "done": done,
                    }
                ], None
            return _fetch

        live, _, _ = report.resolve_game_times(rows, fetch=fetch(False), now=after_tip)
        self.assertEqual(live[(day, "NHL", "TBL/MIN o6.5")]["display"], "Live")
        self.assertEqual(live[(day, "NHL", "TBL/MIN o6.5")]["done"], "")
        final, _, _ = report.resolve_game_times(rows, fetch=fetch(True), now=after_tip)
        self.assertEqual(final[(day, "NHL", "TBL/MIN o6.5")]["display"], "Final")
        self.assertEqual(final[(day, "NHL", "TBL/MIN o6.5")]["done"], "1")

    def test_format_game_start_uses_eastern_time(self) -> None:
        display, iso = report._format_game_start("2026-11-08T00:00Z")
        self.assertEqual(display, "7 PM")
        self.assertTrue(iso.startswith("2026-11-08T00:00:00"))
        self.assertEqual(report._format_game_start("2026-11-07T17:30:00+00:00")[0], "12:30 PM")

    def test_sast_is_sacramento_state(self) -> None:
        sast = report._team_ref("SAST", "NCAAB")
        self.assertIsNotNone(sast)
        self.assertEqual(sast["name"], "Sacramento State")
        self.assertEqual(sast["espn_id"], report.NCAA_ESPN_IDS["sacramentoState"])
        sam = report._team_ref("SAM", "NCAAB")
        self.assertEqual(sam["name"], "Samford")

    def test_hand_map_beats_slate_and_text_only_stays_text(self) -> None:
        mercyhurst = {"MERC": {"abbr": "MERC", "name": "Mercyhurst", "espn_id": "2385"}}
        mercer = report._team_ref("MERC", "NCAAB", mercyhurst)
        self.assertEqual(mercer["name"], "Mercer")
        self.assertEqual(mercer["espn_id"], report.NCAA_ESPN_IDS["mercer"])
        sacred = {"SHU": {"abbr": "SHU", "name": "Sacred Heart", "espn_id": "2529"}}
        self.assertIsNone(report._team_ref("SHU", "NCAAB", sacred))
        self.assertEqual(report._team_ref("SHU", "NCAAF", sacred)["name"], "Sacred Heart")
        famu = {"FAMU": {"abbr": "FAMU", "name": "Florida A&M", "espn_id": "50"}}
        self.assertEqual(report._team_ref("FAMU", "NCAAB", famu)["espn_id"], "50")
        self.assertIsNone(report._team_ref("FAMU", "NCAAB"))

    def test_slate_logo_fills_unlisted_school_and_keeps_blocked_codes_text(self) -> None:
        day = "2026-11-11"
        kansas_city = report.NCAA_ESPN_IDS["kansasCity"]
        ncst = report.NCAA_ESPN_IDS["ncState"]

        def fetch(league: str, date: report.dt.date):
            self.assertEqual((league, date.isoformat()), ("NCAAB", day))
            return [
                {
                    "abbrs": frozenset({"FAMU", "KC"}),
                    "ids": frozenset({"50", kansas_city}),
                    "teams": [
                        {"abbr": "FAMU", "id": "50", "name": "Florida A&M"},
                        {"abbr": "KC", "id": kansas_city, "name": "Kansas City"},
                    ],
                    "display": "6:00 PM",
                    "iso": "2026-11-11T23:00:00+00:00",
                    "title": "Kansas City Roos at Florida A&M Rattlers",
                    "done": False,
                },
                {
                    "abbrs": frozenset({"SHU", "NCSU"}),
                    "ids": frozenset({"2529", ncst}),
                    "teams": [
                        {"abbr": "SHU", "id": "2529", "name": "Sacred Heart"},
                        {"abbr": "NCSU", "id": ncst, "name": "NC State"},
                    ],
                    "display": "7:00 PM",
                    "iso": "2026-11-12T00:00:00+00:00",
                    "title": "Sacred Heart at NC State",
                    "done": False,
                },
                {
                    "abbrs": frozenset({"LUC", "AF"}),
                    "ids": frozenset({"2350", "2005"}),
                    "teams": [
                        {"abbr": "LUC", "id": "2350", "name": "Loyola Chicago"},
                        {"abbr": "AF", "id": "2005", "name": "Air Force"},
                    ],
                    "display": "8:00 PM",
                    "iso": "2026-11-12T01:00:00+00:00",
                    "title": "Loyola Chicago Ramblers at Air Force Falcons",
                    "done": False,
                },
            ], None

        rows = [
            {"date": day, "league": "NCAAB", "pick": "UMKC/FAMU u148.5"},
            {"date": day, "league": "NCAAB", "pick": "SHU/NCST u144.5"},
            {"date": day, "league": "NCAAB", "pick": "LUC -9.5"},
        ]
        before_tip = report.dt.datetime(2026, 11, 11, 16, 0, tzinfo=report.dt.timezone.utc)
        times, notes, logos = report.resolve_game_times(rows, fetch=fetch, now=before_tip)
        self.assertEqual(times[(day, "NCAAB", "UMKC/FAMU u148.5")]["display"], "6 PM")
        self.assertEqual(times[(day, "NCAAB", "LUC -9.5")]["display"], "8 PM")
        self.assertNotIn((day, "NCAAB", "SHU/NCST u144.5"), times)
        joined = "\n".join(notes)
        self.assertIn("unrecognized team (SHU)", joined)
        self.assertNotIn("Sacred Heart", joined)
        famu_logo = report.ESPN_NCAA_LOGO.format(team_id="50")
        luc_logo = report.ESPN_NCAA_LOGO.format(team_id="2350")
        self.assertEqual(logos[(day, "NCAAB")]["FAMU"], (famu_logo, "Florida A&M"))
        self.assertEqual(logos[(day, "NCAAB")]["LUC"], (luc_logo, "Loyola Chicago"))
        self.assertNotIn("SHU", logos[(day, "NCAAB")])
        self.assertNotIn("UMKC", logos[(day, "NCAAB")])
        pick = report._today_pick_html("UMKC/FAMU u148.5", "NCAAB", "logos", set(), logos[(day, "NCAAB")])
        self.assertIn(f'src="{famu_logo}"', pick)
        self.assertIn('data-name="Florida A&amp;M"', pick)
        self.assertIn(report.ESPN_NCAA_LOGO.format(team_id=kansas_city), pick)
        self.assertTrue(report._today_pick_html("SHU/NCST u144.5", "NCAAB", "logos", set(), logos[(day, "NCAAB")]).startswith("SHU "))

    def test_espn_event_keeps_short_team_name_for_logos(self) -> None:
        event = {
            "date": "2026-11-11T23:00:00Z",
            "competitions": [{
                "date": "2026-11-11T23:00:00Z",
                "competitors": [
                    {"homeAway": "away", "team": {
                        "abbreviation": "KC", "id": "140",
                        "displayName": "Kansas City Roos", "shortDisplayName": "Kansas City",
                    }},
                    {"homeAway": "home", "team": {
                        "abbreviation": "FAMU", "id": "50",
                        "displayName": "Florida A&M Rattlers", "shortDisplayName": "Florida A&M",
                    }},
                ],
                "status": {"type": {"state": "pre", "completed": False}},
            }],
        }
        game = report._game_from_espn_event(event)
        self.assertEqual(game["teams"], [
            {"abbr": "KC", "id": "140", "name": "Kansas City"},
            {"abbr": "FAMU", "id": "50", "name": "Florida A&M"},
        ])


class FinalMarginTests(unittest.TestCase):
    def setUp(self) -> None:
        self.game = {
            "away": {
                "abbr": "TB", "id": "20", "name": "Tampa Bay Lightning", "score": "3",
                "linescores": [
                    {"period": 1, "value": 1}, {"period": 2, "value": 0},
                    {"period": 3, "value": 1}, {"period": 4, "value": 1},
                ],
            },
            "home": {
                "abbr": "MIN", "id": "30", "name": "Minnesota Wild", "score": "4",
                "linescores": [
                    {"period": 1, "value": 2}, {"period": 2, "value": 1},
                    {"period": 3, "value": 1}, {"period": 4, "value": 0},
                ],
            },
        }
        self.teams = [report._team_ref("TB", "NHL"), report._team_ref("MIN", "NHL")]

    def margin(self, pick: str, bet_type: str, league: str = "NHL", game=None, teams=None):
        return report._final_margin(pick, bet_type, league, game if game is not None else self.game, teams if teams is not None else self.teams)

    def test_spread_and_moneyline_use_margin_of_victory(self) -> None:
        side = self.margin("TB -1.5", "Side")
        self.assertEqual(side["margin"], "−1")
        self.assertIn("Tampa Bay Lightning lost by 1", side["margin_title"])
        self.assertIn("3–4", side["margin_title"])
        moneyline = self.margin("MIN ML", "ML")
        self.assertEqual(moneyline["margin"], "+1")
        self.assertIn("Minnesota Wild won by 1", moneyline["margin_title"])
        self.assertEqual(self.margin("TB ML (REG)", "ML")["margin"], "−2")
        tied = dict(self.game)
        tied["home"] = dict(self.game["home"], score="3")
        self.assertEqual(self.margin("TB ML", "ML", game=tied)["margin"], "0")
        self.assertIn("tied", self.margin("TB ML", "ML", game=tied)["margin_title"])

    def test_totals_use_points_won_or_lost_by(self) -> None:
        under = self.margin("TBL/MIN u6.5", "Total")
        self.assertEqual(under["margin"], "−0.5")
        self.assertIn("Lost by 0.5", under["margin_title"])
        self.assertIn("Total 7 vs 6.5", under["margin_title"])
        self.assertEqual(self.margin("TBL/MIN o6.5", "Total")["margin"], "+0.5")
        self.assertEqual(self.margin("TBL/MIN u7", "Total")["margin"], "0")
        self.assertIn("Push", self.margin("TBL/MIN u7", "Total")["margin_title"])
        team = self.margin("MIN u3.5", "Team Total")
        self.assertEqual(team["margin"], "−0.5")
        self.assertIn("Minnesota Wild 4 vs 3.5", team["margin_title"])
        self.assertEqual(self.margin("MIN o3.5", "Team Total")["margin"], "+0.5")

    def test_period_and_regulation_use_linescores(self) -> None:
        self.assertEqual(self.margin("TBL/MIN 1P o1.5", "Total")["margin"], "+1.5")
        self.assertEqual(self.margin("MIN 1P u1.5", "Team Total")["margin"], "−0.5")
        self.assertEqual(self.margin("TBL/MIN u6.5 (REG)", "Total")["margin"], "+0.5")
        halves = {
            "away": {"abbr": "DUKE", "id": "150", "score": "70", "linescores": [
                {"period": 1, "value": 40}, {"period": 2, "value": 30}]},
            "home": {"abbr": "UNC", "id": "153", "score": "60", "linescores": [
                {"period": 1, "value": 20}, {"period": 2, "value": 40}]},
        }
        duke = {"abbr": "DUKE", "name": "Duke", "espn_abbr": "DUKE", "espn_id": "150"}
        half = report._final_margin("DUKE 1H -4.5", "Side", "NCAAB", halves, [duke])
        self.assertEqual(half["margin"], "+20")
        quarters = {
            "away": {"abbr": "KC", "id": "12", "score": "24", "linescores": [
                {"period": 1, "value": 7}, {"period": 2, "value": 3},
                {"period": 3, "value": 7}, {"period": 4, "value": 7}]},
            "home": {"abbr": "BUF", "id": "2", "score": "17", "linescores": [
                {"period": 1, "value": 0}, {"period": 2, "value": 7},
                {"period": 3, "value": 3}, {"period": 4, "value": 7}]},
        }
        kc = {"abbr": "KC", "name": "Kansas City Chiefs", "espn_abbr": "KC", "espn_id": "12"}
        first_half = report._final_margin("KC 1H -3", "Side", "NFL", quarters, [kc])
        self.assertEqual(first_half["margin"], "+3")

    def test_skips_parlays_props_and_unknown_scores(self) -> None:
        self.assertEqual(self.margin("TB -1.5 & MIN ML", "Parlay"), {})
        self.assertEqual(self.margin("McDavid o1.5 Ast", "Player Prop"), {})
        self.assertEqual(self.margin("TB 1P ML", "ML", league="NBA"), {})
        blank = {"away": {"abbr": "TB", "score": None}, "home": {"abbr": "MIN", "score": None}}
        self.assertEqual(self.margin("TB ML", "ML", game=blank), {})

    def test_final_straight_card_shows_margin_and_parlay_does_not(self) -> None:
        today = report.dt.date.today()
        raw = {
            "id": "9", "date": "2026-11-11T23:00:00Z",
            "competitions": [{
                "date": "2026-11-11T23:00:00Z",
                "status": {"type": {"state": "post", "completed": True}},
                "competitors": [
                    {"homeAway": "away", "score": "2", "team": {
                        "abbreviation": "TB", "id": "20", "displayName": "Tampa Bay Lightning"}},
                    {"homeAway": "home", "score": "4", "team": {
                        "abbreviation": "MIN", "id": "30", "displayName": "Minnesota Wild"}},
                ],
            }],
        }
        game = report._game_from_espn_event(raw)
        bets = [
            _bet(date=today, pick="TB -1.5", league="NHL", bet_type="Side", result="L", net=-110),
            _bet(date=today, pick="TB -1.5", league="NHL", bet_type="Parlay", result="L", net=-110),
            _bet(date=today, pick="MIN o3.5", league="NHL", bet_type="Team Total", result="W", net=100),
        ]
        times, notes, _logos = report.resolve_game_times(
            [report.bet_to_row(bet) for bet in bets],
            fetch=lambda league, date: ([game], None),
            now=report.dt.datetime(2026, 11, 12, 4, tzinfo=report.dt.timezone.utc),
        )
        self.assertEqual(notes, [])
        self.assertEqual(times[(today.isoformat(), "NHL", "TB -1.5")]["margin"], "−2")
        self.assertEqual(times[(today.isoformat(), "NHL", "MIN o3.5")]["margin"], "+0.5")
        doc = report.build_html_report(
            report.summarize(bets), "Test", {}, "NHL", game_times=times, available_logo_files=set(),
        )
        today_html = doc.split('<section id="today-panel"', 1)[1].split("</section>", 1)[0]
        straight, parlay = today_html.split('data-bet-section="parlay"', 1)
        self.assertIn('class="today-margin" title="Tampa Bay Lightning lost by 2 (2–4)"', straight)
        self.assertIn(">−2</span>", straight)
        self.assertIn(">Final<", straight)
        self.assertNotIn("today-margin", parlay)
        self.assertIn('class="today-margin"', today_html.split("MIN o3.5", 1)[1].split("</li>", 1)[0])


class BroadcastTests(unittest.TestCase):
    def test_first_network_uses_local_asset_and_custom_base(self):
        markup = report._broadcast_html("ESPN+, Spectrum News 1", "../logos",
                                        {"networks/espn-png-file.png"})
        self.assertIn('src="../logos/networks/ESPN-PNG-File.png"', markup)
        self.assertIn('alt="ESPN+"', markup)
        self.assertNotIn("Spectrum", markup)

    def test_missing_or_unknown_logo_falls_back_to_escaped_text(self):
        for name in ("ESPN+", "Unknown & Network"):
            markup = report._broadcast_html(name, available_logo_files=set())
            self.assertNotIn("<img", markup)
            self.assertIn(name.replace("&", "&amp;"), markup)
        self.assertEqual(report._broadcast_html(""), "")


class GameInfoTests(unittest.TestCase):
    def test_game_details_keep_location_but_hide_lines_after_tip(self):
        start = {"venue": "Arena & City", "broadcast": "ESPN+", "spread": "DAY -13.5", "total": "159.5"}
        for display in ("7 PM", "Live", "Final"):
            markup = report._game_info_html(dict(start, display=display))
            self.assertIn("Arena &amp; City", markup)
            self.assertNotIn("ESPN+", markup)
            self.assertEqual("DAY -13.5" in markup, display == "7 PM")
            self.assertEqual("159.5" in markup, display == "7 PM")
        self.assertEqual(report._game_info_html(None), "")
        self.assertEqual(report._game_info_html({}), "")


if __name__ == "__main__":
    unittest.main()
