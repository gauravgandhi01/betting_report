#!/usr/bin/env python3

import argparse
import csv
import datetime as dt
import html
import json
import math
import os
import ssl
import tempfile
import urllib.request
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Bet:
    date: dt.date
    pick: str
    odds_american: Optional[float]
    risk: float
    to_win: float
    result: str
    net: float
    book: str
    league: str
    bet_type: str


LEAGUE_COLOR_MAP = {
    "NHL": "#1D4ED8",
    "NCAAB": "#D97706",
    "NBA": "#C8102E",
    "NFL": "#013369",
    "MLB": "#0477BF",
    "NCAAF": "#7C2D12",
    "PGA": "#15803D",
    "OTHER": "#6B7280",
    "CROSSSPORT": "#8B5CF6",
}


BOOK_COLOR_MAP = {
    "FANDUEL": "#0077FF",
    "DRAFTKINGS": "#53B949",
    "CAESARS": "#C7A257",
    "BETMGM": "#C0A362",
    "MGM": "#C0A362",
    "FANATICS": "#E31837",
    "BET365": "#1E9B4F",
    "BALLYS": "#CC0033",
    "RIVERS": "#1D4ED8",
    "NOVIG": "#4F46E5",
    "PROPHETX": "#06B6D4",
    "SPORTTRADE": "#0EA5E9",
    "BOOKIE": "#7C3AED",
    "BM": "#64748B",
    "BOL": "#F97316",
    "BUCKEYE": "#DC2626",
}


BADGE_FALLBACK_PALETTE = [
    "#38BDF8",
    "#22C55E",
    "#F59E0B",
    "#EF4444",
    "#A78BFA",
    "#14B8A6",
    "#F97316",
    "#84CC16",
    "#06B6D4",
    "#E879F9",
]


def _normalize_key(label: str) -> str:
    return "".join(ch for ch in (label or "").upper() if ch.isalnum())


def _fallback_color(label: str) -> str:
    key = _normalize_key(label)
    if not key:
        return "#64748B"
    return BADGE_FALLBACK_PALETTE[sum(ord(ch) for ch in key) % len(BADGE_FALLBACK_PALETTE)]


def _text_color_for_bg(hex_color: str) -> str:
    s = (hex_color or "").lstrip("#")
    if len(s) != 6:
        return "#F8FAFC"
    r = int(s[0:2], 16)
    g = int(s[2:4], 16)
    b = int(s[4:6], 16)
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
    return "#0B1220" if luminance > 0.62 else "#F8FAFC"


def _badge_html(label: str, color: str) -> str:
    safe = html.escape((label or "").strip() or "(blank)")
    fg = _text_color_for_bg(color)
    return f'<span class="badge" style="background:{color}; border-color:{color}; color:{fg};">{safe}</span>'


def _league_badge(league: str) -> str:
    key = _normalize_key(league)
    color = LEAGUE_COLOR_MAP.get(key, _fallback_color(league))
    return _badge_html(league, color)


def _book_badge(book: str) -> str:
    key = _normalize_key(book)
    color = BOOK_COLOR_MAP.get(key, _fallback_color(book))
    return _badge_html(book, color)


def _parse_money(value: str) -> float:
    # Handles values like "$1,381.91", "-$105.05", "$105.05" or "105.05"
    s = (value or "").strip()
    if not s:
        return float("nan")
    s = s.replace("$", "").replace(",", "")
    return float(s)


def _parse_odds(value: str) -> Optional[float]:
    s = (value or "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date_mmdd(value: str, year: int) -> dt.date:
    s = (value or "").strip()
    if not s:
        raise ValueError("Missing date")
    # CSV has format M/D
    month_s, day_s = s.split("/")
    return dt.date(year, int(month_s), int(day_s))


def _parse_month_day(value: str) -> Tuple[int, int]:
    s = (value or "").strip()
    if not s:
        raise ValueError("Missing date")
    month_s, day_s = s.split("/")
    return int(month_s), int(day_s)


def _american_to_implied_prob(odds: Optional[float]) -> Optional[float]:
    if odds is None:
        return None
    if odds == 0:
        return None
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return (-odds) / ((-odds) + 100.0)


def read_bets(csv_path: str, start_year: int = 2026) -> List[Bet]:
    bets: List[Bet] = []
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"D", "Pick", "Odds", "Risk", "Wins", "R", "Net", "Book", "League", "Type"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"bets.csv missing columns: {sorted(missing)}")

        current_year = start_year
        last_month_day: Optional[Tuple[int, int]] = None

        for row in reader:
            month_day = _parse_month_day(row.get("D", ""))
            if last_month_day is not None and month_day < last_month_day:
                current_year += 1
            last_month_day = month_day

            bet = Bet(
                date=dt.date(current_year, month_day[0], month_day[1]),
                pick=(row.get("Pick", "") or "").strip(),
                odds_american=_parse_odds(row.get("Odds", "")),
                risk=_parse_money(row.get("Risk", "")),
                to_win=_parse_money(row.get("Wins", "")),
                result=(row.get("R", "") or "").strip().upper(),
                net=_parse_money(row.get("Net", "")),
                book=(row.get("Book", "") or "").strip(),
                league=(row.get("League", "") or "").strip(),
                bet_type=(row.get("Type", "") or "").strip(),
            )
            bets.append(bet)
    return bets


def _nan_to_zero(x: float) -> float:
    return 0.0 if (isinstance(x, float) and math.isnan(x)) else x


def _download_bytes(url: str, timeout_seconds: int = 30) -> bytes:
    return _download_bytes_with_ssl(url, timeout_seconds=timeout_seconds, insecure=False)


def _download_bytes_with_ssl(url: str, timeout_seconds: int = 30, insecure: bool = False) -> bytes:
    context: Optional[ssl.SSLContext] = None
    if insecure:
        context = ssl._create_unverified_context()
    else:
        try:
            import certifi  # type: ignore

            context = ssl.create_default_context(cafile=certifi.where())
        except Exception:
            context = ssl.create_default_context()

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "betting-analysis-sync/1.0",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=timeout_seconds, context=context) as resp:
        return resp.read()


def _atomic_write_bytes(path: str, data: bytes) -> None:
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(prefix=".tmp_bets_", suffix=".csv", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    finally:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def _safe_div(n: float, d: float) -> Optional[float]:
    if d == 0 or math.isnan(d):
        return None
    return n / d


def _period_metrics(bets: List[Bet], start_date: dt.date, end_date: dt.date, days: int) -> Dict[str, Any]:
    window = [b for b in bets if start_date <= b.date <= end_date]
    resolved = [b for b in window if b.result in {"W", "L"}]
    wins = sum(1 for b in resolved if b.result == "W")
    losses = sum(1 for b in resolved if b.result == "L")
    pushes = sum(1 for b in window if b.result == "P")
    open_count = sum(1 for b in window if not b.result)
    other = sum(1 for b in window if b.result not in {"", "W", "L", "P"})
    risk = sum(_nan_to_zero(b.risk) for b in window)
    net = sum(_nan_to_zero(b.net) for b in window)
    return {
        "label": f"Last {days} days",
        "days": days,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "bets": len(window),
        "resolved": len(resolved),
        "wins": wins,
        "losses": losses,
        "pushes": pushes,
        "open": open_count,
        "other": other,
        "risk": risk,
        "net": net,
        "roi": _safe_div(net, risk),
        "win_rate": _safe_div(wins, len(resolved)),
    }


def _longest_sign_streak(entries: List[Tuple[str, int]]) -> Dict[str, Any]:
    best_win_len = 0
    best_loss_len = 0
    best_win_start: Optional[str] = None
    best_win_end: Optional[str] = None
    best_loss_start: Optional[str] = None
    best_loss_end: Optional[str] = None

    current_sign = 0
    current_len = 0
    current_start: Optional[str] = None

    for label, sign in entries:
        if sign == 0:
            current_sign = 0
            current_len = 0
            current_start = None
            continue
        if sign == current_sign:
            current_len += 1
        else:
            current_sign = sign
            current_len = 1
            current_start = label

        if sign > 0 and current_len > best_win_len:
            best_win_len = current_len
            best_win_start = current_start
            best_win_end = label
        elif sign < 0 and current_len > best_loss_len:
            best_loss_len = current_len
            best_loss_start = current_start
            best_loss_end = label

    # Current active streak from the end of the sequence.
    current_type = ""
    current_start_out: Optional[str] = None
    current_end_out: Optional[str] = None
    current_len_out = 0

    i = len(entries) - 1
    while i >= 0 and entries[i][1] == 0:
        i -= 1
    if i >= 0:
        current_sign = entries[i][1]
        current_end_out = entries[i][0]
        j = i
        while j >= 0 and entries[j][1] == current_sign:
            j -= 1
        current_len_out = i - j
        current_start_out = entries[j + 1][0]
        current_type = "win" if current_sign > 0 else "loss"

    return {
        "current": {
            "type": current_type,
            "length": current_len_out,
            "start": current_start_out,
            "end": current_end_out,
        },
        "best_win": {
            "length": best_win_len,
            "start": best_win_start,
            "end": best_win_end,
        },
        "best_loss": {
            "length": best_loss_len,
            "start": best_loss_start,
            "end": best_loss_end,
        },
    }


def summarize(bets: List[Bet]) -> Dict[str, Any]:
    resolved = [b for b in bets if b.result in {"W", "L"}]
    pushes = [b for b in bets if b.result == "P"]
    open_bets = [b for b in bets if not b.result]
    other = [b for b in bets if b.result not in {"W", "L", "P"}]

    total_risk = sum(_nan_to_zero(b.risk) for b in bets)
    total_net = sum(_nan_to_zero(b.net) for b in bets)
    roi = _safe_div(total_net, total_risk)

    wins = [b for b in resolved if b.result == "W"]
    losses = [b for b in resolved if b.result == "L"]

    win_rate = _safe_div(len(wins), len(resolved))

    avg_risk = _safe_div(sum(_nan_to_zero(b.risk) for b in bets), len(bets))
    avg_odds = _safe_div(
        sum(b.odds_american for b in bets if b.odds_american is not None),
        sum(1 for b in bets if b.odds_american is not None),
    )

    avg_implied = _safe_div(
        sum(p for p in (_american_to_implied_prob(b.odds_american) for b in bets) if p is not None),
        sum(1 for b in bets if _american_to_implied_prob(b.odds_american) is not None),
    )

    by_league = group_metrics(bets, key_fn=lambda b: b.league)
    by_book = group_metrics(bets, key_fn=lambda b: b.book)
    by_type = group_metrics(bets, key_fn=lambda b: b.bet_type)

    # cumulative net by date
    net_by_date: Dict[dt.date, float] = defaultdict(float)
    risk_by_date: Dict[dt.date, float] = defaultdict(float)
    count_by_date: Dict[dt.date, int] = defaultdict(int)
    for b in bets:
        net_by_date[b.date] += _nan_to_zero(b.net)
        risk_by_date[b.date] += _nan_to_zero(b.risk)
        count_by_date[b.date] += 1

    dates_sorted = sorted(net_by_date.keys())
    cum_net = 0.0
    cum_risk = 0.0
    series = []
    for d in dates_sorted:
        cum_net += net_by_date[d]
        cum_risk += risk_by_date[d]
        series.append(
            {
                "date": d.isoformat(),
                "net": net_by_date[d],
                "risk": risk_by_date[d],
                "cum_net": cum_net,
                "cum_risk": cum_risk,
                "cum_roi": (cum_net / cum_risk) if cum_risk else None,
            }
        )

    settled_bets = [b for b in bets if b.result]
    settled_dates = sorted({b.date for b in settled_bets})
    settled_net_by_date: Dict[dt.date, float] = defaultdict(float)
    for b in settled_bets:
        settled_net_by_date[b.date] += _nan_to_zero(b.net)

    daily_entries: List[Tuple[str, int]] = []
    for d in settled_dates:
        net = settled_net_by_date[d]
        sign = 1 if net > 0 else (-1 if net < 0 else 0)
        daily_entries.append((d.isoformat(), sign))
    daily_streaks = _longest_sign_streak(daily_entries)

    resolved_sorted = sorted(
        ((idx, b) for idx, b in enumerate(bets) if b.result in {"W", "L"}),
        key=lambda pair: (pair[1].date, pair[0]),
    )
    bet_entries = [(f"{b.date.isoformat()} #{idx + 1}", 1 if b.result == "W" else -1) for idx, b in resolved_sorted]
    bet_streaks = _longest_sign_streak(bet_entries)

    all_dates = [b.date for b in bets]
    today = dt.date.today()
    non_future_dates = [d for d in all_dates if d <= today]
    as_of = max(non_future_dates) if non_future_dates else (max(all_dates) if all_dates else today)

    recent_periods = []
    for days in (7, 14, 30):
        start = as_of - dt.timedelta(days=days - 1)
        recent_periods.append(_period_metrics(bets, start, as_of, days))

    recent_daily_series: List[Dict[str, Any]] = []
    for i in range(29, -1, -1):
        d = as_of - dt.timedelta(days=i)
        recent_daily_series.append(
            {
                "date": d.isoformat(),
                "net": net_by_date.get(d, 0.0),
                "risk": risk_by_date.get(d, 0.0),
            }
        )

    recent_7_day_calendar: List[Dict[str, Any]] = []
    for i in range(6, -1, -1):
        d = as_of - dt.timedelta(days=i)
        recent_7_day_calendar.append(
            {
                "date": d.isoformat(),
                "net": net_by_date.get(d, 0.0),
                "risk": risk_by_date.get(d, 0.0),
                "bets": count_by_date.get(d, 0),
            }
        )

    best_day = None
    worst_day = None
    if settled_dates:
        best_date = max(settled_dates, key=lambda d: settled_net_by_date[d])
        worst_date = min(settled_dates, key=lambda d: settled_net_by_date[d])
        best_day = {"date": best_date.isoformat(), "net": settled_net_by_date[best_date]}
        worst_day = {"date": worst_date.isoformat(), "net": settled_net_by_date[worst_date]}

    top_wins = sorted(
        [b for b in bets if not math.isnan(b.net) and b.net > 0],
        key=lambda b: b.net,
        reverse=True,
    )[:10]
    top_losses = sorted(
        [b for b in bets if not math.isnan(b.net) and b.net < 0],
        key=lambda b: b.net,
    )[:10]
    longest_shots = sorted(
        [b for b in bets if b.result == "W" and b.odds_american is not None],
        key=lambda b: (_american_to_implied_prob(b.odds_american) if _american_to_implied_prob(b.odds_american) is not None else 1.0),
    )[:10]

    settled_bets_sorted = sorted(settled_bets, key=lambda b: b.date, reverse=True)[:50]
    open_bets_sorted = sorted(open_bets, key=lambda b: b.date, reverse=True)
    open_exposure = sum(_nan_to_zero(b.risk) for b in open_bets)

    return {
        "as_of": as_of.isoformat(),
        "counts": {
            "total": len(bets),
            "resolved": len(resolved),
            "wins": len(wins),
            "losses": len(losses),
            "pushes": len(pushes),
            "open": len(open_bets),
            "other": len(other),
        },
        "totals": {
            "risk": total_risk,
            "net": total_net,
            "roi": roi,
        },
        "averages": {
            "avg_risk": avg_risk,
            "avg_odds": avg_odds,
            "avg_implied_prob": avg_implied,
            "win_rate": win_rate,
        },
        "recent_periods": recent_periods,
        "recent_daily_series": recent_daily_series,
        "recent_7_day_calendar": recent_7_day_calendar,
        "open_exposure": open_exposure,
        "streaks": {
            "daily": daily_streaks,
            "bets": bet_streaks,
        },
        "best_day": best_day,
        "worst_day": worst_day,
        "by_league": by_league,
        "by_book": by_book,
        "by_type": by_type,
        "series": series,
        "top_wins": [bet_to_row(b) for b in top_wins],
        "top_losses": [bet_to_row(b) for b in top_losses],
        "longest_shots": [bet_to_row(b) for b in longest_shots],
        "recently_settled": [bet_to_row(b) for b in settled_bets_sorted],
        "open_bets": [bet_to_row(b) for b in open_bets_sorted],
    }


def bet_to_row(b: Bet) -> Dict[str, Any]:
    return {
        "date": b.date.isoformat(),
        "pick": b.pick,
        "odds": b.odds_american,
        "risk": b.risk,
        "to_win": b.to_win,
        "result": b.result,
        "net": b.net,
        "book": b.book,
        "league": b.league,
        "type": b.bet_type,
    }


def group_metrics(bets: List[Bet], key_fn) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Bet]] = defaultdict(list)
    for b in bets:
        k = (key_fn(b) or "").strip() or "(blank)"
        groups[k].append(b)

    rows: List[Dict[str, Any]] = []
    for k, bs in groups.items():
        risk = sum(_nan_to_zero(b.risk) for b in bs)
        net = sum(_nan_to_zero(b.net) for b in bs)
        resolved = [b for b in bs if b.result in {"W", "L"}]
        wins = sum(1 for b in resolved if b.result == "W")
        win_rate = (wins / len(resolved)) if resolved else None
        roi = (net / risk) if risk else None
        rows.append(
            {
                "key": k,
                "count": len(bs),
                "resolved": len(resolved),
                "wins": wins,
                "losses": sum(1 for b in resolved if b.result == "L"),
                "risk": risk,
                "net": net,
                "roi": roi,
                "win_rate": win_rate,
            }
        )

    rows.sort(key=lambda r: (r["net"], r["count"]), reverse=True)
    return rows


def _fmt_money(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"${x:,.2f}"


def _fmt_pct(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"{x * 100.0:.2f}%"


def _fmt_num(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    if float(x).is_integer():
        return str(int(x))
    return f"{x:.2f}"


def _fmt_odds(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    if float(x).is_integer():
        return f"{int(x):+d}"
    return f"{x:+.2f}"


def _round_half_away_from_zero(value: float) -> int:
    if value >= 0:
        return int(math.floor(value + 0.5))
    return int(math.ceil(value - 0.5))


def _fmt_date_short(value: str) -> str:
    s = (value or "").strip()
    if not s:
        return ""
    try:
        d = dt.date.fromisoformat(s)
        return f"{d:%b} {d.day}"
    except ValueError:
        return s


def _render_table(headers: List[str], rows: List[List]) -> str:
    ths = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    trs = []
    for r in rows:
        tds = []
        for c in r:
            if isinstance(c, tuple):
                formatted, cls = c
                tds.append(f'<td class="{cls}">{formatted}</td>')
            else:
                tds.append(f"<td>{c}</td>")
        trs.append(f"<tr>{''.join(tds)}</tr>")
    return f"<table><thead><tr>{ths}</tr></thead><tbody>{''.join(trs)}</tbody></table>"


def _normalize_pick(value: str) -> str:
    return " ".join((value or "").strip().split()).upper()


def _unique_nonblank(values: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for v in values:
        label = (v or "").strip() or "(blank)"
        key = label.upper()
        if key in seen:
            continue
        seen.add(key)
        out.append(label)
    return out


def _collapse_bet_rows(bet_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    grouped: Dict[Tuple[str, str, str, str, str], Dict[str, Any]] = {}
    order: List[Tuple[str, str, str, str, str]] = []

    for r in bet_rows:
        date = str(r.get("date", "")).strip()
        pick = str(r.get("pick", "")).strip()
        league = str(r.get("league", "")).strip()
        bet_type = str(r.get("type", "")).strip()
        result = str(r.get("result", "")).strip().upper()

        key = (date, _normalize_pick(pick), league.upper(), bet_type.upper(), result)
        if key not in grouped:
            grouped[key] = {
                "date": date,
                "pick": pick,
                "type": bet_type,
                "result": result,
                "books": [],
                "leagues": [],
                "odds_values": [],
                "risk_values": [],
                "net_values": [],
                "count": 0,
            }
            order.append(key)

        g = grouped[key]
        g["count"] += 1
        g["books"].append(str(r.get("book", "")).strip())
        g["leagues"].append(league)

        odds = r.get("odds")
        if odds is not None and not (isinstance(odds, float) and math.isnan(odds)):
            g["odds_values"].append(float(odds))

        risk = r.get("risk")
        if risk is not None and not (isinstance(risk, float) and math.isnan(risk)):
            g["risk_values"].append(float(risk))

        net = r.get("net")
        if net is not None and not (isinstance(net, float) and math.isnan(net)):
            g["net_values"].append(float(net))

    collapsed: List[Dict[str, Any]] = []
    for key in order:
        g = grouped[key]
        books = _unique_nonblank(g["books"])
        leagues = _unique_nonblank(g["leagues"])
        odds_values = g["odds_values"]
        risk_values = g["risk_values"]
        net_values = g["net_values"]
        avg_odds = (sum(odds_values) / len(odds_values)) if odds_values else None
        if avg_odds is not None:
            avg_odds = float(_round_half_away_from_zero(avg_odds))

        collapsed.append(
            {
                "date": g["date"],
                "pick": g["pick"],
                "odds": avg_odds,
                "risk": (sum(risk_values) if risk_values else float("nan")),
                "to_win": float("nan"),
                "result": g["result"],
                "net": (sum(net_values) if net_values else float("nan")),
                "book": books[0] if len(books) == 1 else f"{len(books)} books",
                "books": books,
                "league": leagues[0] if len(leagues) == 1 else "Mixed",
                "leagues": leagues,
                "type": g["type"],
                "row_count": g["count"],
            }
        )
    return collapsed


def build_html_report(summary: Dict[str, Any], title: str, ncaab_summary: Dict[str, Any]) -> str:
    as_of = summary["as_of"]
    counts = summary["counts"]
    totals = summary["totals"]
    avgs = summary["averages"]
    ncaab_as_of = ncaab_summary["as_of"]
    ncaab_counts = ncaab_summary["counts"]
    ncaab_totals = ncaab_summary["totals"]
    ncaab_avgs = ncaab_summary["averages"]

    series_json = json.dumps(summary["series"])
    recent_series_json = json.dumps(summary["recent_daily_series"])
    ncaab_series_json = json.dumps(ncaab_summary["series"])
    ncaab_recent_series_json = json.dumps(ncaab_summary["recent_daily_series"])

    def group_table(group_rows: List[Dict[str, Any]], limit: int = 25, badge_kind: str = "") -> str:
        headers = ["Group", "Bets", "W", "L", "Risk", "Net", "ROI", "Win%"]
        rows = []
        for r in group_rows[:limit]:
            net_fmt = _fmt_money(r["net"])
            net_cls = "positive" if r["net"] >= 0 else "negative"
            roi_fmt = _fmt_pct(r["roi"])
            roi_cls = "positive" if (r["roi"] is not None and r["roi"] >= 0) else "negative"
            win_fmt = _fmt_pct(r["win_rate"])
            win_cls = "above50" if (r["win_rate"] is not None and r["win_rate"] > 0.5) else "below50"
            key_label = str(r["key"])
            if badge_kind == "league":
                group_cell = _league_badge(key_label)
            elif badge_kind == "book":
                group_cell = _book_badge(key_label)
            else:
                group_cell = html.escape(key_label)
            rows.append(
                [
                    group_cell,
                    str(r["count"]),
                    str(r["wins"]),
                    str(r["losses"]),
                    _fmt_money(r["risk"]),
                    (net_fmt, net_cls),
                    (roi_fmt, roi_cls),
                    (win_fmt, win_cls),
                ]
            )
        return _render_table(headers, rows)

    def bets_table(
        bet_rows: List[Dict[str, Any]],
        include_result: bool = True,
        collapse_duplicates: bool = True,
    ) -> str:
        rows_in = _collapse_bet_rows(bet_rows) if collapse_duplicates else bet_rows
        headers = ["Date", "League", "Book", "Type", "Pick", "Odds", "Risk"]
        if include_result:
            headers.append("Result")
        headers.append("Net")
        rows = []
        for r in rows_in:
            net_fmt = _fmt_money(r["net"])
            net_cls = "positive" if r["net"] >= 0 else "negative"
            leagues = r.get("leagues") or [r.get("league", "")]
            books = r.get("books") or [r.get("book", "")]
            if len(leagues) == 1:
                league_cell = _league_badge(leagues[0])
            else:
                league_cell = f'<div class="chip-row">{"".join(_league_badge(x) for x in leagues)}</div>'
            if len(books) == 1:
                book_cell = _book_badge(books[0])
            else:
                book_cell = f'<div class="chip-row">{"".join(_book_badge(x) for x in books)}</div>'

            pick_cell = html.escape(r["pick"])
            row_count = int(r.get("row_count", 1) or 1)
            if row_count > 1:
                pick_cell += f'<div class="note-inline">{row_count} wagers combined</div>'

            odds_text = _fmt_odds(r.get("odds"))
            row = [
                html.escape(_fmt_date_short(r["date"])),
                league_cell,
                book_cell,
                html.escape(r["type"]),
                pick_cell,
                html.escape(odds_text),
                _fmt_money(r["risk"]),
            ]
            if include_result:
                row.append(html.escape(r["result"]))
            row.append((net_fmt, net_cls))
            rows.append(row)
        return _render_table(headers, rows)

    def period_table(period_rows: List[Dict[str, Any]]) -> str:
        headers = ["Window", "Bets", "W-L", "Win%", "Risk", "Net", "ROI", "Open"]
        rows = []
        for r in period_rows:
            net_cls = "positive" if r["net"] >= 0 else "negative"
            roi_cls = "positive" if (r["roi"] is not None and r["roi"] >= 0) else "negative"
            rows.append(
                [
                    html.escape(r["label"]),
                    str(r["bets"]),
                    f"{r['wins']}-{r['losses']}",
                    _fmt_pct(r["win_rate"]),
                    _fmt_money(r["risk"]),
                    (_fmt_money(r["net"]), net_cls),
                    (_fmt_pct(r["roi"]), roi_cls),
                    str(r["open"]),
                ]
            )
        return _render_table(headers, rows)

    def daily_net_risk_calendar(day_rows: List[Dict[str, Any]]) -> str:
        if not day_rows:
            return '<div class="note">No recent daily data.</div>'

        cards = []
        for r in day_rows:
            date_s = str(r.get("date", "")).strip()
            try:
                d = dt.date.fromisoformat(date_s)
                day_name = f"{d:%a}"
                day_label = f"{d:%b} {d.day}"
            except ValueError:
                day_name = ""
                day_label = date_s

            net = float(r.get("net", 0.0) or 0.0)
            risk = float(r.get("risk", 0.0) or 0.0)
            bets = int(r.get("bets", 0) or 0)
            card_cls = "day-card pos" if net > 0 else ("day-card neg" if net < 0 else "day-card flat")
            net_cls = "positive" if net > 0 else ("negative" if net < 0 else "")
            bet_word = "bet" if bets == 1 else "bets"

            cards.append(
                f"""
                <div class="{card_cls}">
                  <div class="day-top">
                    <div class="day-name">{html.escape(day_name)}</div>
                    <div class="day-date">{html.escape(day_label)}</div>
                  </div>
                  <div class="day-row"><span>Net</span><strong class="{net_cls}">{_fmt_money(net)}</strong></div>
                  <div class="day-row"><span>Risk</span><strong>{_fmt_money(risk)}</strong></div>
                  <div class="day-count">{bets} {bet_word}</div>
                </div>
                """
            )
        return f'<div class="calendar-scroll"><div class="calendar-strip">{"".join(cards)}</div></div>'

    def streak_line(title_text: str, streak: Dict[str, Any]) -> str:
        if streak["length"] <= 0:
            return f"<div><strong>{html.escape(title_text)}:</strong> none</div>"
        if streak["start"] == streak["end"]:
            span = streak["start"]
        else:
            span = f"{streak['start']} to {streak['end']}"
        return f"<div><strong>{html.escape(title_text)}:</strong> {streak['length']} ({html.escape(span)})</div>"

    daily_streaks = summary["streaks"]["daily"]
    bet_streaks = summary["streaks"]["bets"]

    if daily_streaks["current"]["length"] > 0:
        daily_current_text = (
            f"{daily_streaks['current']['length']} {daily_streaks['current']['type']} "
            f"day(s) ({daily_streaks['current']['start']} to {daily_streaks['current']['end']})"
        )
    else:
        daily_current_text = "No active daily win/loss streak"

    if bet_streaks["current"]["length"] > 0:
        bet_current_text = (
            f"{bet_streaks['current']['length']} {bet_streaks['current']['type']} "
            f"bet(s) ({bet_streaks['current']['start']} to {bet_streaks['current']['end']})"
        )
    else:
        bet_current_text = "No active bet-level win/loss streak"

    best_day = summary["best_day"]
    worst_day = summary["worst_day"]
    ncaab_best_day = ncaab_summary["best_day"]
    ncaab_worst_day = ncaab_summary["worst_day"]

    html_doc = f"""<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>{html.escape(title)}</title>
  <script src=\"https://cdn.plot.ly/plotly-2.30.0.min.js\"></script>
  <style>
    :root {{
      --bg: #0b1220;
      --panel: #0f1a2e;
      --panel2: #0c1628;
      --text: #e6eefc;
      --muted: #9db0d0;
      --border: rgba(255,255,255,0.08);
      --good: #34d399;
      --bad: #fb7185;
      --accent: #60a5fa;
    }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, Segoe UI, Roboto, Helvetica, Arial, sans-serif; background: var(--bg); color: var(--text); }}
    .container {{ max-width: 1200px; margin: 0 auto; padding: 24px; }}
    h1 {{ margin: 0 0 8px 0; font-size: 26px; }}
    .subtitle {{ color: var(--muted); margin-bottom: 18px; }}
    .tabs {{ display: flex; gap: 8px; margin-bottom: 14px; }}
    .tab-btn {{
      background: rgba(157, 176, 208, 0.15);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 12px;
      font-size: 13px;
      cursor: pointer;
    }}
    .tab-btn.active {{ background: rgba(96, 165, 250, 0.28); border-color: rgba(96, 165, 250, 0.6); }}
    .tab-panel {{ display: none; }}
    .tab-panel.active {{ display: block; }}
    .grid {{ display: grid; grid-template-columns: repeat(12, 1fr); gap: 12px; }}
    .card {{ background: linear-gradient(180deg, var(--panel), var(--panel2)); border: 1px solid var(--border); border-radius: 14px; padding: 14px 14px; }}
    .kpi {{ grid-column: span 3; }}
    .kpi .label {{ color: var(--muted); font-size: 12px; }}
    .kpi .value {{ font-size: 20px; margin-top: 6px; font-variant-numeric: tabular-nums; }}
    .kpi .value.good {{ color: var(--good); }}
    .kpi .value.bad {{ color: var(--bad); }}
    .full {{ grid-column: span 12; }}
    .half {{ grid-column: span 6; }}
    .third {{ grid-column: span 4; }}

    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 10px 10px; text-align: left; vertical-align: top; }}
    th {{ font-size: 12px; color: var(--muted); font-weight: 600; }}
    td {{ font-size: 13px; }}
    .scroll {{ overflow-x: auto; }}
    .section-title {{ margin: 6px 0 10px; font-size: 16px; }}
    .note {{ color: var(--muted); font-size: 12px; line-height: 1.4; }}
    .badge {{
      display: inline-flex;
      align-items: center;
      padding: 2px 8px;
      border-radius: 999px;
      border: 1px solid transparent;
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 0.01em;
      line-height: 1.4;
      white-space: nowrap;
    }}
    .chip-row {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .note-inline {{ color: var(--muted); font-size: 11px; margin-top: 4px; }}
    .calendar-scroll {{ overflow-x: auto; padding-bottom: 4px; }}
    .calendar-strip {{
      display: grid;
      grid-template-columns: repeat(7, minmax(128px, 1fr));
      gap: 10px;
      min-width: 920px;
    }}
    .day-card {{
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 10px;
      background: rgba(255,255,255,0.02);
    }}
    .day-card.pos {{ border-color: rgba(52,211,153,0.45); }}
    .day-card.neg {{ border-color: rgba(251,113,133,0.45); }}
    .day-card.flat {{ border-color: rgba(157,176,208,0.35); }}
    .day-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 8px;
      gap: 6px;
    }}
    .day-name {{ font-size: 12px; color: var(--muted); font-weight: 600; }}
    .day-date {{ font-size: 13px; font-weight: 700; }}
    .day-row {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      margin-top: 4px;
      font-size: 12px;
      color: var(--muted);
    }}
    .day-row strong {{ font-size: 13px; color: var(--text); }}
    .day-count {{ margin-top: 8px; font-size: 11px; color: var(--muted); }}

    .positive {{ color: var(--good); }}
    .negative {{ color: var(--bad); }}
    .above50 {{ color: var(--good); }}
    .below50 {{ color: var(--bad); }}

    @media (max-width: 1000px) {{
      .kpi {{ grid-column: span 6; }}
      .half {{ grid-column: span 12; }}
      .third {{ grid-column: span 12; }}
    }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>{html.escape(title)}</h1>
    <div class=\"subtitle\">As of {html.escape(as_of)} | Showing data from 2026-01-01 onward</div>
    <div class="tabs">
      <button class="tab-btn active" data-tab="home">Home</button>
      <button class="tab-btn" data-tab="history">History</button>
      <button class="tab-btn" data-tab="ncaab">NCAAB</button>
    </div>

    <section id="tab-home" class="tab-panel active">
      <div class=\"grid\">
        <div class="card kpi">
          <div class="label">Total Bets</div>
          <div class="value">{counts['total']}</div>
          <div class="note">Resolved: {counts['resolved']} | Open: {counts['open']} | Push/Void: {counts['pushes']}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Net Profit</div>
          <div class=\"value {'good' if totals['net'] >= 0 else 'bad'}\">{_fmt_money(totals['net'])}</div>
          <div class=\"note\">ROI: {_fmt_pct(totals['roi'])}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Win Rate (W/L only)</div>
          <div class=\"value\">{_fmt_pct(avgs['win_rate'])}</div>
          <div class=\"note\">W: {counts['wins']} | L: {counts['losses']}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Open Risk</div>
          <div class=\"value\">{_fmt_money(summary['open_exposure'])}</div>
        </div>

        <div class="card full">
          <div class="section-title">Open Bets</div>
          <div class="scroll">{bets_table(summary['open_bets'])}</div>
        </div>

        <div class="card full">
          <div class="section-title">Daily Net / Risk (Last 7 Days)</div>
          {daily_net_risk_calendar(summary['recent_7_day_calendar'])}
        </div>

        <div class="card full">
          <div class="section-title">Recent Performance</div>
          <div class="scroll">{period_table(summary['recent_periods'])}</div>
        </div>

        <div class="card full">
          <div class="section-title">Recently Settled Bets</div>
          <div class="scroll">{bets_table(summary['recently_settled'][:25])}</div>
        </div>

        <div class="card half">
          <div class="section-title">Notable Streaks</div>
          <div class="note">{html.escape(daily_current_text)}</div>
          <div class="note">{html.escape(bet_current_text)}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            {streak_line("Longest daily win streak", daily_streaks["best_win"])}
            {streak_line("Longest daily loss streak", daily_streaks["best_loss"])}
            {streak_line("Longest bet win streak", bet_streaks["best_win"])}
            {streak_line("Longest bet loss streak", bet_streaks["best_loss"])}
          </div>
        </div>

        <div class="card half">
          <div class="section-title">Recent Highlights</div>
          <div class="note">Avg Risk / Bet: {_fmt_money(avgs['avg_risk'])}</div>
          <div class="note">Avg odds: {_fmt_num(avgs['avg_odds'])} | Avg implied: {_fmt_pct(avgs['avg_implied_prob'])}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            <div><strong>Best settled day:</strong> {html.escape(best_day['date']) if best_day else 'n/a'} ({_fmt_money(best_day['net']) if best_day else 'n/a'})</div>
            <div><strong>Worst settled day:</strong> {html.escape(worst_day['date']) if worst_day else 'n/a'} ({_fmt_money(worst_day['net']) if worst_day else 'n/a'})</div>
          </div>
        </div>

        <div class="card full">
          <div class="section-title">Last 30 Days Net (daily)</div>
          <div id="chart-recent" style="height: 320px;"></div>
          <div class="note">Includes zero values on days with no bets.</div>
        </div>
      </div>
    </section>

    <section id="tab-history" class="tab-panel">
      <div class=\"grid\">
        <div class="card full">
          <div class="section-title">Cumulative Profit</div>
          <div id="chart-cum" style="height: 360px;"></div>
          <div class="note">Uses the CSV's <code>Net</code> field for each bet; cumulative ROI = cumulative net / cumulative risk.</div>
        </div>

        <div class=\"card half\">
          <div class=\"section-title\">By League (top 25 by Net)</div>
          <div class=\"scroll\">{group_table(summary['by_league'], badge_kind='league')}</div>
        </div>
        <div class=\"card half\">
          <div class=\"section-title\">By Book (top 25 by Net)</div>
          <div class=\"scroll\">{group_table(summary['by_book'], badge_kind='book')}</div>
        </div>

        <div class=\"card half\">
          <div class=\"section-title\">By Type (top 25 by Net)</div>
          <div class=\"scroll\">{group_table(summary['by_type'])}</div>
        </div>
        <div class=\"card half\">
          <div class=\"section-title\">Biggest Wins (top 10)</div>
          <div class=\"scroll\">{bets_table(summary['top_wins'], include_result=False)}</div>
        </div>

        <div class=\"card half\">
          <div class=\"section-title\">Biggest Losses (top 10)</div>
          <div class=\"scroll\">{bets_table(summary['top_losses'], include_result=False)}</div>
        </div>

        <div class=\"card full\">
          <div class=\"section-title\">Longest Shots (top 10 winning odds)</div>
          <div class=\"note\">Winning wagers with the longest pre-game odds (lowest implied win probability).</div>
          <div class=\"scroll\">{bets_table(summary['longest_shots'], include_result=False)}</div>
        </div>
      </div>
    </section>

    <section id="tab-ncaab" class="tab-panel">
      <div class="grid">
        <div class="card kpi">
          <div class="label">NCAAB Total Bets</div>
          <div class="value">{ncaab_counts['total']}</div>
          <div class="note">Resolved: {ncaab_counts['resolved']} | Open: {ncaab_counts['open']} | Push/Void: {ncaab_counts['pushes']}</div>
        </div>
        <div class="card kpi">
          <div class="label">NCAAB Net Profit</div>
          <div class="value {'good' if ncaab_totals['net'] >= 0 else 'bad'}">{_fmt_money(ncaab_totals['net'])}</div>
          <div class="note">ROI: {_fmt_pct(ncaab_totals['roi'])}</div>
        </div>
        <div class="card kpi">
          <div class="label">NCAAB Win Rate (W/L)</div>
          <div class="value">{_fmt_pct(ncaab_avgs['win_rate'])}</div>
          <div class="note">W: {ncaab_counts['wins']} | L: {ncaab_counts['losses']}</div>
        </div>
        <div class="card kpi">
          <div class="label">NCAAB Open Exposure</div>
          <div class="value">{_fmt_money(ncaab_summary['open_exposure'])}</div>
          <div class="note">As of {html.escape(ncaab_as_of)} | League tag = <code>NCAAB</code></div>
        </div>

        <div class="card full">
          <div class="section-title">NCAAB Recent Performance</div>
          <div class="note">Calendar-day windows ending on {html.escape(ncaab_as_of)}.</div>
          <div class="scroll">{period_table(ncaab_summary['recent_periods'])}</div>
        </div>

        <div class="card full">
          <div class="section-title">NCAAB Cumulative Profit</div>
          <div id="chart-cum-ncaab" style="height: 320px;"></div>
        </div>

        <div class="card full">
          <div class="section-title">NCAAB Last 30 Days Net (daily)</div>
          <div id="chart-recent-ncaab" style="height: 320px;"></div>
        </div>

        <div class="card full">
          <div class="section-title">NCAAB Recently Settled Bets</div>
          <div class="note">Most recent settled bets, latest 25.</div>
          <div class="scroll">{bets_table(ncaab_summary['recently_settled'][:25])}</div>
        </div>

        <div class="card full">
          <div class="section-title">NCAAB Open Bets</div>
          <div class="note">Open bets tagged with League <code>NCAAB</code>.</div>
          <div class="scroll">{bets_table(ncaab_summary['open_bets'])}</div>
        </div>

        <div class="card half">
          <div class="section-title">NCAAB By Book</div>
          <div class="scroll">{group_table(ncaab_summary['by_book'], badge_kind='book')}</div>
        </div>
        <div class="card half">
          <div class="section-title">NCAAB By Type</div>
          <div class="scroll">{group_table(ncaab_summary['by_type'])}</div>
        </div>

        <div class="card half">
          <div class="section-title">NCAAB Biggest Wins (top 10)</div>
          <div class="scroll">{bets_table(ncaab_summary['top_wins'], include_result=False)}</div>
        </div>
        <div class="card half">
          <div class="section-title">NCAAB Biggest Losses (top 10)</div>
          <div class="scroll">{bets_table(ncaab_summary['top_losses'], include_result=False)}</div>
        </div>

        <div class="card full">
          <div class="section-title">NCAAB Highlights</div>
          <div class="note">Avg Risk / Bet: {_fmt_money(ncaab_avgs['avg_risk'])}</div>
          <div class="note">Avg odds: {_fmt_num(ncaab_avgs['avg_odds'])} | Avg implied: {_fmt_pct(ncaab_avgs['avg_implied_prob'])}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            <div><strong>Best settled day:</strong> {html.escape(ncaab_best_day['date']) if ncaab_best_day else 'n/a'} ({_fmt_money(ncaab_best_day['net']) if ncaab_best_day else 'n/a'})</div>
            <div><strong>Worst settled day:</strong> {html.escape(ncaab_worst_day['date']) if ncaab_worst_day else 'n/a'} ({_fmt_money(ncaab_worst_day['net']) if ncaab_worst_day else 'n/a'})</div>
          </div>
        </div>
      </div>
    </section>
  </div>

<script>
  const series = {series_json};
  const recentSeries = {recent_series_json};
  const ncaabSeries = {ncaab_series_json};
  const ncaabRecentSeries = {ncaab_recent_series_json};

  const x = series.map(d => d.date);
  const yCum = series.map(d => d.cum_net);
  const yDaily = series.map(d => d.net);
  const yCumRoi = series.map(d => d.cum_roi == null ? null : d.cum_roi * 100.0);

  const traceCum = {{
    x, y: yCum, type: 'scatter', mode: 'lines+markers', name: 'Cumulative Net',
    line: {{ color: '#60a5fa', width: 3 }},
    hovertemplate: '%{{x}}<br>Cumulative Net: %{{y:$,.2f}}<extra></extra>'
  }};

  const traceDaily = {{
    x, y: yDaily, type: 'bar', name: 'Daily Net',
    marker: {{ color: yDaily.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
    opacity: 0.55,
    hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
  }};

  const traceCumRoi = {{
    x, y: yCumRoi, type: 'scatter', mode: 'lines', name: 'Cumulative ROI %',
    yaxis: 'y2',
    line: {{ color: 'rgba(157,176,208,0.9)', width: 2, dash: 'dot' }},
    hovertemplate: '%{{x}}<br>Cumulative ROI: %{{y:.2f}}%<extra></extra>'
  }};

  const layout = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {{ color: '#e6eefc' }},
    margin: {{ l: 55, r: 55, t: 10, b: 45 }},
    legend: {{ orientation: 'h', y: 1.15, x: 0 }},
    xaxis: {{ gridcolor: 'rgba(255,255,255,0.06)' }},
    yaxis: {{ title: 'Net ($)', gridcolor: 'rgba(255,255,255,0.06)' }},
    yaxis2: {{ title: 'ROI (%)', overlaying: 'y', side: 'right', showgrid: false }},
    barmode: 'overlay'
  }};

  Plotly.newPlot('chart-cum', [traceDaily, traceCum, traceCumRoi], layout, {{displayModeBar: false, responsive: true}});

  const recentX = recentSeries.map(d => d.date);
  const recentY = recentSeries.map(d => d.net);
  const recentTrace = {{
    x: recentX,
    y: recentY,
    type: 'bar',
    marker: {{ color: recentY.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
    hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
  }};
  const recentLayout = {{
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(0,0,0,0)',
    font: {{ color: '#e6eefc' }},
    margin: {{ l: 55, r: 25, t: 10, b: 45 }},
    xaxis: {{ gridcolor: 'rgba(255,255,255,0.06)' }},
    yaxis: {{ title: 'Net ($)', gridcolor: 'rgba(255,255,255,0.06)' }},
  }};
  Plotly.newPlot('chart-recent', [recentTrace], recentLayout, {{displayModeBar: false, responsive: true}});

  const ncaabX = ncaabSeries.map(d => d.date);
  const ncaabYCum = ncaabSeries.map(d => d.cum_net);
  const ncaabYDaily = ncaabSeries.map(d => d.net);
  const ncaabYCumRoi = ncaabSeries.map(d => d.cum_roi == null ? null : d.cum_roi * 100.0);
  const ncaabTraceCum = {{
    x: ncaabX, y: ncaabYCum, type: 'scatter', mode: 'lines+markers', name: 'NCAAB Cumulative Net',
    line: {{ color: '#60a5fa', width: 3 }},
    hovertemplate: '%{{x}}<br>Cumulative Net: %{{y:$,.2f}}<extra></extra>'
  }};
  const ncaabTraceDaily = {{
    x: ncaabX, y: ncaabYDaily, type: 'bar', name: 'NCAAB Daily Net',
    marker: {{ color: ncaabYDaily.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
    opacity: 0.55,
    hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
  }};
  const ncaabTraceRoi = {{
    x: ncaabX, y: ncaabYCumRoi, type: 'scatter', mode: 'lines', name: 'NCAAB Cumulative ROI %',
    yaxis: 'y2',
    line: {{ color: 'rgba(157,176,208,0.9)', width: 2, dash: 'dot' }},
    hovertemplate: '%{{x}}<br>Cumulative ROI: %{{y:.2f}}%<extra></extra>'
  }};
  Plotly.newPlot('chart-cum-ncaab', [ncaabTraceDaily, ncaabTraceCum, ncaabTraceRoi], layout, {{displayModeBar: false, responsive: true}});

  const ncaabRecentX = ncaabRecentSeries.map(d => d.date);
  const ncaabRecentY = ncaabRecentSeries.map(d => d.net);
  const ncaabRecentTrace = {{
    x: ncaabRecentX,
    y: ncaabRecentY,
    type: 'bar',
    marker: {{ color: ncaabRecentY.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
    hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
  }};
  Plotly.newPlot('chart-recent-ncaab', [ncaabRecentTrace], recentLayout, {{displayModeBar: false, responsive: true}});

  const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
  const tabPanels = Array.from(document.querySelectorAll('.tab-panel'));
  function resizeCharts() {{
    const recentChart = document.getElementById('chart-recent');
    const cumulativeChart = document.getElementById('chart-cum');
    const ncaabRecentChart = document.getElementById('chart-recent-ncaab');
    const ncaabCumulativeChart = document.getElementById('chart-cum-ncaab');
    if (recentChart) Plotly.Plots.resize(recentChart);
    if (cumulativeChart) Plotly.Plots.resize(cumulativeChart);
    if (ncaabRecentChart) Plotly.Plots.resize(ncaabRecentChart);
    if (ncaabCumulativeChart) Plotly.Plots.resize(ncaabCumulativeChart);
  }}
  function activateTab(tabName) {{
    tabButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tabName));
    tabPanels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${{tabName}}`));
    localStorage.setItem('bettingReportActiveTab', tabName);
    requestAnimationFrame(resizeCharts);
  }}
  tabButtons.forEach((btn) => btn.addEventListener('click', () => activateTab(btn.dataset.tab)));
  const savedTab = localStorage.getItem('bettingReportActiveTab');
  if (savedTab === 'history' || savedTab === 'home' || savedTab === 'ncaab') {{
    activateTab(savedTab);
  }}
  window.addEventListener('resize', resizeCharts);
</script>

</body>
</html>"""

    return html_doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an HTML analysis report from bets.csv")
    parser.add_argument("--input", default="bets.csv", help="Path to bets.csv")
    parser.add_argument("--output", default="../index.html", help="Output HTML file")
    parser.add_argument(
        "--sync-url",
        default="",
        help="Optional: published Google Sheet CSV URL to download into --input before generating the report",
    )
    parser.add_argument("--sync-timeout", type=int, default=30, help="HTTP timeout seconds for --sync-url")
    parser.add_argument(
        "--sync-insecure",
        action="store_true",
        help="Disable SSL certificate verification for --sync-url (not recommended)",
    )
    parser.add_argument(
        "--start-year",
        type=int,
        default=2025,
        help="Starting year to assume for the first row; year increments when M/D rolls over (e.g. 12/31 -> 1/1)",
    )
    args = parser.parse_args()

    if args.sync_url:
        try:
            data = _download_bytes_with_ssl(
                args.sync_url,
                timeout_seconds=args.sync_timeout,
                insecure=bool(args.sync_insecure),
            )
        except Exception as e:
            raise RuntimeError(
                "Failed to download --sync-url. If this is an SSL certificate issue on macOS, consider installing/updating certifi or rerun with --sync-insecure."
            ) from e
        if not data or b"," not in data:
            raise RuntimeError("Downloaded content does not look like a CSV")
        _atomic_write_bytes(args.input, data)

    bets = read_bets(args.input, start_year=args.start_year)
    # Temporary reporting scope: only include bets from 2026 onward.
    bets = [b for b in bets if b.date >= dt.date(2026, 1, 1)]
    summary = summarize(bets)
    ncaab_bets = [b for b in bets if b.league.strip().upper() == "NCAAB"]
    ncaab_summary = summarize(ncaab_bets)

    title = "G's Betting Report"
    html_report = build_html_report(summary, title=title, ncaab_summary=ncaab_summary)

    out_dir = os.path.dirname(os.path.abspath(args.output))
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_report)

    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
