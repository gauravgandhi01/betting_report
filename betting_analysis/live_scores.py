#!/usr/bin/env python3
"""Read local open bets and display their current ESPN scores in the terminal."""

import argparse
import csv
import datetime as dt
import json
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

if __package__:
    from . import generate_bet_report as report
else:
    import generate_bet_report as report


Fetch = Callable[[str, dt.date], Tuple[List[Dict[str, Any]], Optional[str]]]
DEFAULT_INPUT = Path(__file__).resolve().with_name("bets.csv")
SPORT_EMOJI = {"NHL": "🏒", "NBA": "🏀", "NCAAB": "🏀",
               "NFL": "🏈", "NCAAF": "🏈", "MLB": "⚾"}
REGULATION = {"NCAAB": (2, 20), "NBA": (4, 12), "NFL": (4, 15),
              "NCAAF": (4, 15), "NHL": (3, 20)}


def _bet_data(bet: report.Bet) -> Dict[str, Any]:
    row = report.bet_to_row(bet)
    # Open bets contain NaN in the CSV reader; emit strict, portable JSON.
    return {key: None if isinstance(value, float) and not math.isfinite(value) else value
            for key, value in row.items()}


def collect_scores(
    bets: List[report.Bet], day: dt.date, *, leagues: Sequence[str] = (),
    open_only: bool = True, live_only: bool = False, fetch: Optional[Fetch] = None,
    now: Optional[dt.datetime] = None,
) -> Dict[str, Any]:
    """Fetch each required league once; associate open bets only with unique matches.

    A bet with any recorded result is graded and is left out when ``open_only``
    is set. That is the default, and the CLI always sets it.
    """
    selected = [bet for bet in bets if bet.date == day
                and (not leagues or bet.league.upper() in leagues)
                and (not open_only or not bet.result)]
    skipped = []
    candidates = []
    for bet in selected:
        league = bet.league.upper()
        if bet.bet_type.casefold() == "parlay":
            reason = "parlay requires individual leg mappings"
            teams = []
        elif league not in report._ESPN_SCOREBOARDS:
            reason = f"no ESPN scoreboard for {league or 'unknown league'}"
            teams = []
        else:
            teams, reason = report._matchup_from_pick(bet.pick, league)
        if reason or not teams:
            skipped.append({"bet": _bet_data(bet), "reason": reason or "no recognized teams"})
        else:
            candidates.append((bet, teams))

    fetch = fetch or report._espn_slate
    slates = {}
    errors = []
    needed = sorted({bet.league.upper() for bet, _ in candidates})
    if needed:
        with ThreadPoolExecutor(max_workers=len(needed)) as pool:
            pending = {league: pool.submit(fetch, league, day) for league in needed}
            for league, future in pending.items():
                try:
                    games, error = future.result()
                except Exception as exc:
                    games, error = [], f"ESPN request failed for {league}: {exc}"
                slates[league] = (games, error)
                if error:
                    errors.append(error)

    now = now or dt.datetime.now(report._EASTERN)
    if now.tzinfo is None:
        now = now.replace(tzinfo=report._EASTERN)
    grouped = {}
    matched_bets = 0
    for bet, teams in candidates:
        league = bet.league.upper()
        games, error = slates[league]
        hits = report._matching_games(games, teams)
        if len(hits) != 1:
            reason = ("more than one game matches; cannot identify the event uniquely"
                      if len(hits) > 1 else error or "no matching game on the ESPN slate")
            skipped.append({"bet": _bet_data(bet), "reason": reason})
            continue
        matched_bets += 1
        game = hits[0]
        live = game["state"] == "in" and not game["done"]
        upcoming = (not live_only and not game["done"] and bool(game["event_id"])
                    and game["state"] == "pre" and game["status_name"] == "STATUS_SCHEDULED"
                    and dt.datetime.fromisoformat(game["iso"]) > now)
        if not live and not upcoming:
            continue
        key = (league, game["event_id"] or (game["iso"], tuple(sorted(game["ids"]))))
        if key not in grouped:
            grouped[key] = {
                "league": league,
                "event_id": game["event_id"],
                "start": game["iso"],
                "state": game["state"],
                "status_name": game["status_name"],
                "status": game["status_detail"],
                "completed": game["done"],
                "period": game["period"],
                "clock": game["clock"],
                "away": game["away"],
                "home": game["home"],
                "neutral_site": game["neutral_site"],
                "broadcast": game.get("broadcast") or "",
                "bets": [],
            }
        grouped[key]["bets"].append(_bet_data(bet))
    matched = sorted(grouped.values(), key=_finish_order)
    games = [game for game in matched if game["state"] == "in"]
    upcoming = [game for game in matched if game["state"] == "pre"]
    return {
        "date": day.isoformat(),
        "fetched_at": now.isoformat(timespec="seconds"),
        "selected_bets": len(selected),
        "matched_bets": matched_bets,
        "displayed_bets": sum(len(game["bets"]) for game in matched),
        "games": games,
        "upcoming": upcoming,
        "skipped": skipped,
        "errors": errors,
    }


def _risk_amount(bet: Dict[str, Any]) -> str:
    """Compact stake, or blank when the sheet left risk empty."""
    return report._fmt_money_compact(bet.get("risk"))


def _upcoming_pick(bet: Dict[str, Any]) -> str:
    pick = _text(bet["pick"])
    amount = _risk_amount(bet)
    return f"{pick} {amount}" if amount else pick


def _text(value: Any) -> str:
    """Keep CSV and remote strings on one line and strip terminal controls."""
    return " ".join("".join(char for char in str(value) if char.isprintable() or char.isspace()).split())


def _clock_seconds(value: Any) -> Optional[float]:
    try:
        clock = str(value or "").split(":")
        if len(clock) == 2:
            minutes, seconds = int(clock[0]), float(clock[1])
            if minutes < 0 or not 0 <= seconds < 60:
                return None
            remaining = minutes * 60 + seconds
        elif len(clock) == 1:
            remaining = float(clock[0])
        else:
            return None
    except (TypeError, ValueError):
        return None
    return remaining if math.isfinite(remaining) and remaining >= 0 else None


def _game_timing(game: Dict[str, Any]) -> Optional[Tuple[float, float]]:
    """Elapsed and total regulation seconds, excluding time spent on breaks."""
    spec = REGULATION.get(game["league"])
    if spec is None or game["state"] != "in" or game["completed"]:
        return None
    periods, minutes = spec
    period = game.get("period")
    if not isinstance(period, int) or not 1 <= period <= periods:
        return None
    if game["status_name"] == "STATUS_HALFTIME":
        elapsed = periods * minutes * 60 / 2
    elif game["status_name"] in {"STATUS_END_PERIOD", "STATUS_INTERMISSION"}:
        elapsed = period * minutes * 60
    else:
        remaining = _clock_seconds(game.get("clock"))
        if remaining is None or remaining > minutes * 60:
            return None
        elapsed = period * minutes * 60 - remaining
    return elapsed, periods * minutes * 60


def _seconds_until_finish(game: Dict[str, Any]) -> Optional[float]:
    """Regulation or overtime seconds still to play, when the clock supports it."""
    timing = _game_timing(game)
    if timing is not None:
        return timing[1] - timing[0]
    if game.get("state") != "in" or game.get("completed"):
        return None
    spec = REGULATION.get(game.get("league"))
    period = game.get("period")
    if spec and isinstance(period, int) and period > spec[0]:
        clock = _clock_seconds(game.get("clock"))
        return 0.0 if clock is None else clock
    return None


def _finish_order(game: Dict[str, Any]) -> Tuple[Any, ...]:
    """Closest to the end first. Upcoming games follow, soonest start first."""
    start = game.get("start") or ""
    league = game.get("league") or ""
    event_id = str(game.get("event_id") or "")
    remaining = _seconds_until_finish(game)
    if remaining is not None:
        return (0, remaining, start, league, event_id)
    if game.get("state") == "in" and not game.get("completed"):
        period = game.get("period") if isinstance(game.get("period"), int) else 0
        return (1, -period, start, league, event_id)
    return (2, start, league, event_id)


def _projected_total(game: Dict[str, Any]) -> Optional[float]:
    """Extrapolate scoring over regulation using elapsed time on the game clock."""
    timing = _game_timing(game)
    if timing is None or timing[0] <= 0:
        return None
    try:
        total = sum(int((game.get(side) or {})["score"]) for side in ("away", "home"))
    except (KeyError, TypeError, ValueError):
        return None
    return total / timing[0] * timing[1]


def _time_text(text: str, remaining: Optional[float], color: bool) -> str:
    if not color or remaining is None:
        return text
    code = 91 if remaining <= 5 * 60 else 93 if remaining <= 15 * 60 else 92
    return f"\033[{code}m{text}\033[0m"


def _box_score(game: Dict[str, Any]) -> List[str]:
    teams = [game[side] or {} for side in ("away", "home")]
    headers = ["Team", "Score"]
    rows = [[_text(team.get("name") or "?"),
             _text(team["score"]) if team.get("score") is not None else "-"]
            for team in teams]
    widths = [max(len(row[column]) for row in [headers, *rows]) for column in range(len(headers))]

    def border(left: str, middle: str, right: str) -> str:
        return left + middle.join("─" * (width + 2) for width in widths) + right

    def row(values: List[str]) -> str:
        cells = [f" {value:<{width}} " if index == 0 else f" {value:>{width}} "
                 for index, (value, width) in enumerate(zip(values, widths))]
        return "│" + "│".join(cells) + "│"

    box = [border("┌", "┬", "┐"), row(headers), border("├", "┼", "┤"),
           *(row(values) for values in rows), border("└", "┴", "┘")]
    margin, total = "-", "-"
    try:
        away_score, home_score = (int(team["score"]) for team in teams)
    except (KeyError, TypeError, ValueError):
        pass
    else:
        difference = away_score - home_score
        leader = teams[0] if difference > 0 else teams[1]
        margin = (f"{_text(leader.get('abbr') or leader.get('name') or '?')} +{abs(difference)}"
                  if difference else "Tied")
        total = str(away_score + home_score)
    box[3] += f"  Margin: {margin}"
    box[4] += f"  Total: {total}"
    if any(str(bet.get("type") or "").strip().casefold() == "total" for bet in game["bets"]):
        pace = _projected_total(game)
        box[5] += f"  Total pace: {pace:.1f}" if pace is not None else "  Total pace: -"
    return box


def format_scores(snapshot: Dict[str, Any], *, color: Optional[bool] = None) -> str:
    if color is None:
        color = sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"
    now = dt.datetime.fromisoformat(snapshot["fetched_at"])
    stamp = now.astimezone(report._EASTERN).strftime("%I:%M:%S %p %Z")
    upcoming = snapshot.get("upcoming", [])
    summary = f"{len(snapshot['games'])} live games"
    if upcoming:
        summary += f" | {len(upcoming)} upcoming"
    lines = [f"Bet scores | {snapshot['date']} | Fetched {stamp}",
             f"{summary} | {snapshot['displayed_bets']} bets"]
    if not snapshot["selected_bets"]:
        lines.append("No bets found for this date and filters.")
    elif not snapshot["games"] and not upcoming:
        lines.append("No live games for your bets.")
    for game in sorted(snapshot["games"], key=_finish_order):
        emoji = SPORT_EMOJI.get(game["league"], "🏟️")
        timing = _game_timing(game)
        remaining = timing[1] - timing[0] if timing is not None else None
        spec = REGULATION.get(game["league"])
        if timing is None and spec and isinstance(game.get("period"), int) and game["period"] > spec[0]:
            remaining = _clock_seconds(game.get("clock"))
        status = _time_text(_text(game["status"]), remaining, color)
        label = f"{emoji} LIVE | {status}"
        broadcast = _text(game.get("broadcast") or "")
        if broadcast:
            label = f"{label} | {broadcast}"
        lines.extend(["", label, *_box_score(game)])
        for bet in game["bets"]:
            text = f"  {_text(bet['pick'])}"
            lines.append(f"\033[96m{text}\033[0m" if color else text)
    if upcoming:
        lines.extend(["", "Upcoming"])
        for game in sorted(upcoming, key=_finish_order):
            remaining = (dt.datetime.fromisoformat(game["start"]) - now).total_seconds()
            minutes = max(1, math.ceil(remaining / 60))
            days, minutes = divmod(minutes, 24 * 60)
            hours, minutes = divmod(minutes, 60)
            countdown = " ".join(f"{value}{unit}" for value, unit in ((days, "d"), (hours, "h"), (minutes, "m")) if value)
            countdown = _time_text(f"starts in {countdown}", remaining, color)
            away = _text((game["away"] or {}).get("name") or "?")
            home = _text((game["home"] or {}).get("name") or "?")
            bets_text = "; ".join(_upcoming_pick(bet) for bet in game["bets"])
            if color:
                bets_text = f"\033[96m{bets_text}\033[0m"
            versus = " vs " if game["neutral_site"] else " @ "
            broadcast = _text(game.get("broadcast") or "")
            network = f" | {broadcast}" if broadcast else ""
            lines.append(f"{SPORT_EMOJI.get(game['league'], '🏟️')} {away}{versus}{home} | {countdown}{network} | {bets_text}")
    if snapshot["errors"]:
        lines.extend(["", "Score updates failed (scores may be incomplete):"])
        lines.extend(f"  {_text(error).replace('ESPN ', '')}" for error in snapshot["errors"])
    return "\n".join(lines)


def _positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT, help="Bets CSV (default: alongside this script)")
    parser.add_argument("--start-year", type=int, default=2025, help="First CSV year, before M/D rollovers (default: 2025)")
    parser.add_argument("--date", type=dt.date.fromisoformat, help="Slate date YYYY-MM-DD (default: today in New York)")
    parser.add_argument("--league", action="append", type=str.upper, choices=sorted(report._ESPN_SCOREBOARDS), default=[], help="Filter league; repeat for multiple leagues")
    parser.add_argument("--open-only", action="store_true", help="Omit bets that already have a result (also the default)")
    parser.add_argument("--live-only", action="store_true", help="Hide upcoming countdowns; only show games in progress")
    parser.add_argument("--watch", nargs="?", type=_positive_int, const=30, metavar="SECONDS", help="Refresh repeatedly (default: 30 seconds; minimum: 5)")
    parser.add_argument("--timeout", type=_positive_int, default=10, help="HTTP timeout in seconds per scoreboard request (default: 10)")
    parser.add_argument("--json", action="store_true", help="Emit JSON; watch mode emits one JSON object per line")
    args = parser.parse_args(argv)
    if args.watch is not None and args.watch < 5:
        parser.error("--watch must be at least 5 seconds")
    if not 1 <= args.start_year <= 9999:
        parser.error("--start-year must be between 1 and 9999")

    def fetch(league: str, day: dt.date) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        return report._espn_slate(league, day, timeout_seconds=args.timeout)

    try:
        while True:
            day = args.date or dt.datetime.now(report._EASTERN).date()
            try:
                bets = report.read_bets(str(args.input), start_year=args.start_year)
            except (OSError, ValueError, csv.Error) as exc:
                print(f"Cannot read bets: {_text(exc)}", file=sys.stderr)
                return 1
            # Graded bets are always omitted. --open-only stays valid for existing commands.
            snapshot = collect_scores(bets, day, leagues=args.league, open_only=True,
                                      live_only=args.live_only, fetch=fetch)
            if args.watch and not args.json and sys.stdout.isatty():
                print("\033[2J\033[H", end="")
            print(json.dumps(snapshot, allow_nan=False) if args.json else format_scores(snapshot), flush=True)
            if not args.watch:
                return 1 if snapshot["errors"] else 0
            time.sleep(args.watch)
    except KeyboardInterrupt:
        if not args.json:
            print("\nStopped.", file=sys.stderr)
        return 0
    except BrokenPipeError:
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
