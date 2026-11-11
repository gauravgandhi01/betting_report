import contextlib
import datetime as dt
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from betting_analysis import generate_bet_report as report
from betting_analysis import live_scores as cli


DAY = dt.date(2026, 11, 9)


def bet(pick="TBL/MIN o6.5", league="NHL", **overrides):
    values = dict(date=DAY, pick=pick, odds_american=-110, risk=110, to_win=100,
                  result="", net=float("nan"), book="Test Book", league=league, bet_type="Total")
    values.update(overrides)
    return report.Bet(**values)


def event(event_id="123", *, state="in", name="STATUS_IN_PROGRESS", detail="8:12 - 2nd Period",
          away_id="14", home_id="30", away_abbr="TB", home_abbr="MIN"):
    return {
        "id": event_id, "date": "2026-11-10T01:00Z",
        "status": {"period": 2, "displayClock": "8:12", "type": {
            "state": state, "name": name, "detail": detail, "completed": state == "post"}},
        "competitions": [{"competitors": [
            {"homeAway": "home", "score": "3", "linescores": [
                {"value": 1.0, "period": 1}, {"displayValue": "2", "period": 2}], "team": {
                "id": home_id, "abbreviation": home_abbr, "displayName": "Home Team"}},
            {"homeAway": "away", "score": "2", "linescores": [
                {"displayValue": "2", "period": 1}, {"value": 0.0, "period": 2}], "team": {
                "id": away_id, "abbreviation": away_abbr, "displayName": "Away Team"}},
        ]}],
    }


def game(**kwargs):
    return report._game_from_espn_event(event(**kwargs))


class ScoreTests(unittest.TestCase):
    def test_groups_bets_and_fetches_once_using_pro_aliases(self):
        fetch = Mock(return_value=([game()], None))
        snapshot = cli.collect_scores([bet(), bet("TB +1.5", bet_type="Side")], DAY, fetch=fetch)
        fetch.assert_called_once_with("NHL", DAY)
        self.assertEqual(snapshot["matched_bets"], 2)
        self.assertEqual(len(snapshot["games"]), 1)
        matched = snapshot["games"][0]
        self.assertEqual(matched["away"]["score"], "2")
        self.assertEqual(matched["home"]["score"], "3")
        self.assertEqual(matched["event_id"], "123")
        self.assertEqual(matched["period"], 2)
        self.assertEqual(matched["clock"], "8:12")
        text = cli.format_scores(snapshot)
        self.assertIn("🏒 LIVE | 8:12 - 2nd Period", text)
        self.assertRegex(text, r"│ Away Team\s+│\s+2 │")
        self.assertRegex(text, r"│ Home Team\s+│\s+3 │")
        self.assertIn("│  Margin: MIN +1", text)
        self.assertIn("│  Total: 5", text)
        self.assertIn("Total pace: 9.4", text)
        self.assertIn("TBL/MIN o6.5", text)
        self.assertIn("TB +1.5", text)
        self.assertNotIn("(-110)", text)
        colored = cli.format_scores(snapshot, color=True)
        self.assertIn("\033[92m8:12 - 2nd Period\033[0m", colored)
        self.assertIn("\033[96m  TBL/MIN o6.5\033[0m", colored)
        self.assertNotIn("\033[", cli.format_scores(snapshot, color=False))
        for hidden in ("ESPN", "NHL", "123", "risk", "$", "Test Book", "OPEN", "Unmatched", "skipped"):
            self.assertNotIn(hidden, text)
        self.assertIsNone(json.loads(json.dumps(snapshot, allow_nan=False))["games"][0]["bets"][0]["net"])
        for bet_type in ("Side", "ML", "Player Prop", ""):
            side_only = cli.collect_scores([bet("TB +1.5", bet_type=bet_type)], DAY,
                                           fetch=lambda *_: ([game()], None))
            self.assertNotIn("Total pace:", cli.format_scores(side_only))

    def test_orders_by_time_left_and_shows_broadcast_when_present(self):
        def live(**overrides):
            base = {"league": "NHL", "state": "in", "completed": False, "period": 1, "clock": "20:00",
                    "status_name": "STATUS_IN_PROGRESS", "start": "2026-11-10T00:00:00+00:00", "event_id": "a"}
            base.update(overrides)
            return base

        late = live(period=3, clock="1:00", event_id="late")
        overtime = live(period=4, clock="2:00", event_id="ot")
        second = live(period=2, clock="8:12", event_id="second")
        half = live(period=2, clock="20:00", status_name="STATUS_HALFTIME", event_id="half")
        mlb_ninth = live(league="MLB", period=8, event_id="mlb8")
        mlb_second = live(league="MLB", period=2, event_id="mlb2")
        soon = {"state": "pre", "completed": False, "league": "NHL", "period": 1, "clock": "",
                "status_name": "STATUS_SCHEDULED", "start": "2026-11-10T01:00:00+00:00", "event_id": "soon"}
        later = {**soon, "start": "2026-11-10T04:00:00+00:00", "event_id": "later"}
        ordered = sorted([second, later, half, soon, overtime, mlb_second, late, mlb_ninth], key=cli._finish_order)
        self.assertEqual([game["event_id"] for game in ordered],
                         ["late", "ot", "second", "half", "mlb8", "mlb2", "soon", "later"])

        closing = game(event_id="999", away_id="1", home_id="2", away_abbr="BOS", home_abbr="NYR",
                       detail="1:00 - 3rd Period")
        closing["period"] = 3
        closing["clock"] = "1:00"
        closing["status_detail"] = "1:00 - 3rd Period"
        closing["broadcast"] = "TNT"
        early = game()
        soon_game = game(event_id="201", state="pre", name="STATUS_SCHEDULED", detail="Scheduled",
                         away_id="3", home_id="4", away_abbr="DET", home_abbr="CHI")
        soon_game["broadcast"] = "ESPN+"
        later_game = game(event_id="202", state="pre", name="STATUS_SCHEDULED", detail="Scheduled",
                          away_id="5", home_id="6", away_abbr="EDM", home_abbr="VAN")
        later_game["iso"] = "2026-11-10T04:00:00+00:00"
        now = dt.datetime(2026, 11, 9, 19, 30, tzinfo=report._EASTERN)
        snapshot = cli.collect_scores([
            bet(), bet("BOS/NYR o6.5"), bet("DET/CHI o6.5"), bet("EDM/VAN o6.5"),
        ], DAY, now=now, fetch=lambda *_: ([closing, early, later_game, soon_game], None))
        self.assertEqual([row["event_id"] for row in snapshot["games"]], ["999", "123"])
        self.assertEqual([row["event_id"] for row in snapshot["upcoming"]], ["201", "202"])
        text = cli.format_scores(snapshot, color=False)
        self.assertLess(text.index("1:00 - 3rd Period | TNT"), text.index("8:12 - 2nd Period"))
        self.assertIn("🏒 LIVE | 8:12 - 2nd Period\n", text)
        self.assertIn("Away Team @ Home Team | starts in 30m | ESPN+", text)
        self.assertLess(text.index("ESPN+"), text.index("starts in 3h 30m"))
        self.assertNotIn("ESPN+", text[text.index("starts in 3h 30m"):])

    def test_college_uses_ids_even_when_abbreviations_differ(self):
        college = game(away_id=report.NCAA_ESPN_IDS["duke"],
                       home_id=report.NCAA_ESPN_IDS["ncState"],
                       away_abbr="DUKE", home_abbr="NCSU")
        snapshot = cli.collect_scores([bet("DUKE/NCST o152", "NCAAB")], DAY,
                                      fetch=lambda *_: ([college], None))
        self.assertEqual(snapshot["matched_bets"], 1)
        text = cli.format_scores(snapshot)
        self.assertIn("🏀", text)
        self.assertIn("Score", text)
        self.assertNotIn("1H", text)
        self.assertNotIn("2H", text)

    def test_unlisted_college_codes_resolve_from_the_slate(self):
        now = dt.datetime(2026, 11, 9, 19, 30, tzinfo=report._EASTERN)
        loyola = game(event_id="501", state="pre", name="STATUS_SCHEDULED", detail="Scheduled",
                      away_id=report.NCAA_ESPN_IDS["loyolaChicago"], home_id=report.NCAA_ESPN_IDS["airForce"],
                      away_abbr="LUC", home_abbr="AF")
        colgate = game(event_id="502", state="pre", name="STATUS_SCHEDULED", detail="Scheduled",
                       away_id="2142", home_id=report.NCAA_ESPN_IDS["stJohns"],
                       away_abbr="COLG", home_abbr="SJU")
        fetch = Mock(return_value=([loyola, colgate], None))
        snapshot = cli.collect_scores([
            bet("LUC -9.5", "NCAAB", bet_type="Side"),
            bet("COLG/SJU u159.5", "NCAAB"),
            bet("LUC/AFA o159.5", "NCAAB"),
            bet("SHU/NCST u144.5", "NCAAB"),
        ], DAY, now=now, fetch=fetch)
        fetch.assert_called_once_with("NCAAB", DAY)
        self.assertEqual(snapshot["matched_bets"], 3)
        self.assertEqual(snapshot["displayed_bets"], 3)
        picks = {row["event_id"]: [item["pick"] for item in row["bets"]] for row in snapshot["upcoming"]}
        self.assertEqual(picks["501"], ["LUC -9.5", "LUC/AFA o159.5"])
        self.assertEqual(picks["502"], ["COLG/SJU u159.5"])
        self.assertIn("unrecognized team (SHU)", snapshot["skipped"][0]["reason"])

        blocked = Mock()
        skipped = cli.collect_scores([bet("SHU -3", "NCAAB", bet_type="Side")], DAY, fetch=blocked)
        blocked.assert_not_called()
        self.assertIn("no recognized team", skipped["skipped"][0]["reason"])

        parlay = Mock()
        cli.collect_scores([bet("LUC/AFA ML", "NCAAB", bet_type="Parlay")], DAY, fetch=parlay)
        parlay.assert_not_called()

        failed = Mock(return_value=([], "ESPN scoreboard request failed for NCAAB"))
        offline = cli.collect_scores([bet("LUC -9.5", "NCAAB", bet_type="Side")], DAY, fetch=failed)
        self.assertEqual(offline["matched_bets"], 0)
        self.assertIn("scoreboard request failed", offline["skipped"][0]["reason"])
        self.assertEqual(offline["errors"], ["ESPN scoreboard request failed for NCAAB"])

    def test_unsupported_props_and_parlays_do_not_trigger_requests(self):
        fetch = Mock()
        bets = [bet("McDavid o1.5 Ast"), bet("TB ML", bet_type="Parlay"),
                bet("Unknown", league="PGA"), bet("TB/XYZ o6.5")]
        snapshot = cli.collect_scores(bets, DAY, fetch=fetch)
        fetch.assert_not_called()
        self.assertEqual(len(snapshot["skipped"]), 4)
        reasons = " ".join(item["reason"] for item in snapshot["skipped"])
        self.assertIn("no recognized team", reasons)
        self.assertIn("parlay", reasons)
        self.assertIn("unrecognized team (XYZ)", reasons)

    def test_filters_before_fetching_and_uses_actual_live_state(self):
        fetch = Mock(return_value=([game(state="pre", name="STATUS_DELAYED", detail="Delayed")], None))
        snapshot = cli.collect_scores([
            bet(), bet(result="W"), bet(league="NBA"), bet(date=DAY - dt.timedelta(days=1)),
        ], DAY, leagues=["NHL"], open_only=True, live_only=True, fetch=fetch)
        self.assertEqual(snapshot["selected_bets"], 1)
        self.assertEqual(snapshot["matched_bets"], 1)
        self.assertEqual(snapshot["games"], [])
        self.assertEqual(snapshot["skipped"], [])
        fetch.assert_called_once_with("NHL", DAY)

    def test_never_guesses_when_two_events_match(self):
        snapshot = cli.collect_scores([bet()], DAY,
                                      fetch=lambda *_: ([game(), game(event_id="456")], None))
        self.assertEqual(snapshot["matched_bets"], 0)
        self.assertIn("more than one game", snapshot["skipped"][0]["reason"])

    def test_upcoming_is_one_line_per_confirmed_event_with_colored_bets(self):
        now = dt.datetime(2026, 11, 9, 19, 30, tzinfo=report._EASTERN)
        scheduled = game(state="pre", name="STATUS_SCHEDULED", detail="Scheduled")
        snapshot = cli.collect_scores([bet(), bet("TB +1.5")], DAY, now=now,
                                      fetch=lambda *_: ([scheduled], None))
        self.assertEqual(snapshot["games"], [])
        self.assertEqual(len(snapshot["upcoming"]), 1)
        self.assertEqual(snapshot["displayed_bets"], 2)
        text = cli.format_scores(snapshot, color=True)
        upcoming_lines = [line for line in text.splitlines() if "starts in" in line]
        self.assertEqual(len(upcoming_lines), 1)
        self.assertIn("🏒 Away Team @ Home Team | \033[92mstarts in 30m\033[0m", upcoming_lines[0])
        self.assertIn("\033[96mTBL/MIN o6.5 $110; TB +1.5 $110\033[0m", upcoming_lines[0])
        self.assertNotIn("(-110)", text)
        for hidden in ("┌", "Margin:", "Total:", "ESPN", "123", "Test Book", "Unmatched"):
            self.assertNotIn(hidden, text)
        later = cli.collect_scores([bet()], DAY, now=now + dt.timedelta(minutes=10),
                                   fetch=lambda *_: ([scheduled], None))
        self.assertIn("starts in 20m", cli.format_scores(later))
        live_only = cli.collect_scores([bet()], DAY, live_only=True, now=now,
                                       fetch=lambda *_: ([scheduled], None))
        self.assertEqual(live_only["upcoming"], [])

    def test_graded_bets_are_removed_and_upcoming_risk_keeps_cents(self):
        now = dt.datetime(2026, 11, 9, 19, 30, tzinfo=report._EASTERN)
        fetch = Mock(return_value=([game()], None))
        snapshot = cli.collect_scores([bet(), bet("TB +1.5", result="W")], DAY, fetch=fetch)
        self.assertEqual(snapshot["selected_bets"], 1)
        self.assertEqual([row["pick"] for row in snapshot["games"][0]["bets"]], ["TBL/MIN o6.5"])
        self.assertNotIn("TB +1.5", cli.format_scores(snapshot))

        unused = Mock()
        graded = cli.collect_scores([bet(result="L"), bet(result="CO")], DAY, fetch=unused)
        unused.assert_not_called()
        self.assertEqual(graded["games"], [])
        self.assertIn("No bets found", cli.format_scores(graded))

        scheduled = game(state="pre", name="STATUS_SCHEDULED", detail="Scheduled")
        upcoming = cli.collect_scores([
            bet(risk=89.66), bet("TB +1.5", risk=float("nan")), bet("TB ML", result="P", risk=50),
        ], DAY, now=now, fetch=lambda *_: ([scheduled], None))
        text = cli.format_scores(upcoming, color=False)
        self.assertIn("TBL/MIN o6.5 $89.66; TB +1.5", text)
        self.assertNotIn("TB ML", text)
        self.assertNotIn("$50", text)
        self.assertNotRegex(text, r"TB \+1\.5 \$")

    def test_upcoming_requires_future_start_and_scheduled_status_and_event_id(self):
        now = dt.datetime(2026, 11, 9, 19, 30, tzinfo=report._EASTERN)
        scheduled = game(state="pre", name="STATUS_SCHEDULED", detail="Scheduled")
        for override in ({"iso": now.isoformat()},
                         {"iso": (now - dt.timedelta(minutes=1)).isoformat()},
                         {"status_name": "STATUS_POSTPONED"},
                         {"status_name": "STATUS_DELAYED"},
                         {"status_name": "STATUS_CANCELED"},
                         {"event_id": ""}):
            with self.subTest(override=override):
                snapshot = cli.collect_scores([bet()], DAY, now=now,
                                              fetch=lambda *_: ([{**scheduled, **override}], None))
                self.assertEqual(snapshot["upcoming"], [])
                self.assertNotIn("starts in", cli.format_scores(snapshot))

    def test_upcoming_countdown_hours_days_and_under_a_minute(self):
        now = dt.datetime(2026, 11, 9, 19, 30, tzinfo=report._EASTERN)
        scheduled = game(state="pre", name="STATUS_SCHEDULED", detail="Scheduled")
        for seconds, label, code in ((20, "1m", 91), (300, "5m", 91), (600, "10m", 93),
                                     (900, "15m", 93), (3660, "1h 1m", 92), (90000, "1d 1h", 92)):
            with self.subTest(seconds=seconds):
                scheduled["iso"] = (now + dt.timedelta(seconds=seconds)).astimezone(dt.timezone.utc).isoformat()
                snapshot = cli.collect_scores([bet()], DAY, now=now,
                                              fetch=lambda *_: ([scheduled], None))
                self.assertIn(f"starts in {label}", cli.format_scores(snapshot))
                self.assertIn(f"\033[{code}mstarts in {label}\033[0m", cli.format_scores(snapshot, color=True))

    def test_partial_failure_keeps_successful_games_and_reports_errors(self):
        def fetch(league, day):
            if league == "NBA":
                raise TimeoutError("timed out")
            return [game()], "FCS-style partial failure"
        snapshot = cli.collect_scores([bet(), bet("NYK ML", "NBA")], DAY, fetch=fetch)
        self.assertEqual(len(snapshot["games"]), 1)
        self.assertEqual(len(snapshot["errors"]), 2)
        self.assertIn("timed out", snapshot["skipped"][0]["reason"])

    def test_only_live_statuses_and_missing_scores(self):
        cases = [
            ("pre", "STATUS_SCHEDULED", "Scheduled", False),
            ("pre", "STATUS_POSTPONED", "Postponed", False),
            ("in", "STATUS_HALFTIME", "Halftime", True),
            ("in", "STATUS_END_PERIOD", "End of 2nd Period", True),
            ("post", "STATUS_FINAL", "Final/OT", False),
        ]
        for state, name, detail, live in cases:
            with self.subTest(name=name):
                snapshot = cli.collect_scores([bet()], DAY, fetch=lambda *_: (
                    [game(state=state, name=name, detail=detail)], None),
                    now=dt.datetime(2026, 11, 9, 21, tzinfo=report._EASTERN))
                text = cli.format_scores(snapshot)
                self.assertEqual(len(snapshot["games"]), int(live))
                if live:
                    self.assertIn(f"LIVE | {detail}", text)
                    self.assertIn("Away Team", text)
                else:
                    self.assertIn("No live games for your bets.", text)
                    self.assertNotIn("Away Team", text)
        raw = event()
        del raw["competitions"][0]["competitors"][0]["score"]
        for competitor in raw["competitions"][0]["competitors"]:
            del competitor["linescores"]
        snapshot = cli.collect_scores([bet()], DAY, fetch=lambda *_: ([report._game_from_espn_event(raw)], None))
        self.assertRegex(cli.format_scores(snapshot), r"│ Home Team\s+│\s+- │")
        self.assertIn("Margin: -", cli.format_scores(snapshot))
        self.assertIn("Total: -", cli.format_scores(snapshot))

    def test_empty_date_does_not_fetch(self):
        fetch = Mock()
        snapshot = cli.collect_scores([], DAY, fetch=fetch)
        fetch.assert_not_called()
        self.assertIn("No bets found", cli.format_scores(snapshot))


class PaceTests(unittest.TestCase):
    def setUp(self):
        self.game = {"league": "NCAAB", "state": "in", "completed": False,
                     "period": 2, "clock": "10:00", "status_name": "STATUS_IN_PROGRESS",
                     "away": {"score": "40"}, "home": {"score": "50"}}

    def test_regulation_projection_uses_each_leagues_period_length(self):
        # 90 points in 30/40 college minutes => 120; in 24/48 NBA minutes => 180.
        cases = [("NCAAB", 2, "10:00", 120), ("NBA", 3, "12:00", 180),
                 ("NFL", 3, "15:00", 180), ("NCAAF", 2, "0:00", 180),
                 ("NHL", 2, "10:00", 180)]
        for league, period, clock, expected in cases:
            with self.subTest(league=league):
                self.assertAlmostEqual(cli._projected_total({**self.game, "league": league,
                                                            "period": period, "clock": clock}), expected)

    def test_breaks_and_fractional_seconds_use_game_time(self):
        for overrides, expected in [({"status_name": "STATUS_HALFTIME", "clock": "20:00"}, 180),
                                    ({"status_name": "STATUS_END_PERIOD", "period": 1, "clock": ""}, 180),
                                    ({"league": "NHL", "status_name": "STATUS_INTERMISSION",
                                      "period": 1, "clock": "20:00"}, 270)]:
            with self.subTest(overrides=overrides):
                self.assertAlmostEqual(cli._projected_total({**self.game, **overrides}), expected)
        nba = {**self.game, "league": "NBA", "period": 4}
        expected = 90 / (48 - 30.5 / 60) * 48
        for clock in ("30.5", "0:30.5"):
            self.assertAlmostEqual(cli._projected_total({**nba, "clock": clock}), expected)

    def test_unavailable_or_zero_elapsed_is_not_projected(self):
        for overrides in ({"period": 1, "clock": "20:00"}, {"clock": ""}, {"clock": "NaN"},
                          {"clock": "10:60"}, {"clock": "-1:00"}, {"clock": "21:00"},
                          {"away": {"score": None}}, {"home": None}, {"period": 3},
                          {"league": "MLB"}, {"state": "pre"}, {"completed": True}):
            with self.subTest(overrides=overrides):
                self.assertIsNone(cli._projected_total({**self.game, **overrides}))
        self.assertEqual(cli._projected_total({**self.game, "away": {"score": "0"},
                                              "home": {"score": "0"}}), 0)


class ScoreboardTests(unittest.TestCase):
    def test_preserves_distinct_events_with_the_same_teams(self):
        payload = json.dumps({"events": [event("123"), event("456")]}).encode()
        with patch.object(report, "_download_bytes_with_ssl", return_value=payload) as download:
            games, error = report._espn_slate("NHL", DAY, timeout_seconds=3)
        self.assertIsNone(error)
        self.assertEqual(len(games), 2)
        self.assertEqual(download.call_args.kwargs["timeout_seconds"], 3)

    def test_partial_group_failure_and_bad_response(self):
        payload = json.dumps({"events": [event()]}).encode()
        with patch.object(report, "_download_bytes_with_ssl", side_effect=[payload, TimeoutError()]):
            games, error = report._espn_slate("NCAAF", DAY)
        self.assertEqual(len(games), 1)
        self.assertIn("incomplete", error)
        for invalid in (b'{}', b'[]', b'<html>error</html>'):
            with self.subTest(invalid=invalid), patch.object(report, "_download_bytes_with_ssl", return_value=invalid):
                games, error = report._espn_slate("NHL", DAY)
                self.assertEqual(games, [])
                self.assertIsNotNone(error)


class CommandTests(unittest.TestCase):
    def test_csv_year_rollover_and_json_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bets.csv"
            path.write_text("D,Pick,Odds,Risk,Wins,R,Net,Book,League,Type\n"
                            "12/31,TB ML,-110,110,100,W,100,Book,NHL,ML\n"
                            "1/1,TB ML,-110,110,100,,,Book,NHL,ML\n")
            output = io.StringIO()
            with patch.object(report, "_espn_slate", return_value=([game()], None)), contextlib.redirect_stdout(output):
                code = cli.main(["--input", str(path), "--start-year", "2025", "--date", "2026-01-01", "--json"])
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output.getvalue())["selected_bets"], 1)

    def test_watch_reloads_bets_and_emits_json_lines_until_interrupt(self):
        output = io.StringIO()
        with patch.object(report, "read_bets", side_effect=[[bet()], []]) as read, \
                patch.object(report, "_espn_slate", return_value=([game()], None)), \
                patch.object(cli.time, "sleep", side_effect=[None, KeyboardInterrupt]), \
                contextlib.redirect_stdout(output):
            code = cli.main(["--date", str(DAY), "--watch", "5", "--json"])
        self.assertEqual(code, 0)
        self.assertEqual(read.call_count, 2)
        snapshots = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual([s["selected_bets"] for s in snapshots], [1, 0])

    def test_bad_input_and_network_failure_have_nonzero_exit_codes(self):
        with contextlib.redirect_stderr(io.StringIO()), patch.object(report, "read_bets", side_effect=ValueError("missing columns")):
            self.assertEqual(cli.main([]), 1)
        with patch.object(report, "read_bets", return_value=[bet()]), \
                patch.object(report, "_espn_slate", return_value=([], "offline")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["--date", str(DAY)]), 1)

    def test_rejects_invalid_arguments(self):
        for args in (["--watch", "0"], ["--watch", "4"], ["--timeout", "0"],
                     ["--date", "bad"], ["--league", "UNKNOWN"], ["--start-year", "0"]):
            with self.subTest(args=args), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                cli.main(args)
            self.assertEqual(exc.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
