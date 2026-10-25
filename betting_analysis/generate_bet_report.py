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
    "BETONLINE": "#F97316",
    "BUCKEYE": "#DC2626",
}

LEAGUE_LOGO_MAP = {
    "NHL": "nhl.png",
    "NCAAB": "ncaab.png",
    "NBA": "nba.png",
    "NFL": "nfl.png",
    "MLB": "mlb.png",
    "NCAAF": "ncaaf.webp",
}

BOOK_LOGO_MAP = {
    "FANDUEL": "fanduel.jpeg",
    "DRAFTKINGS": "draftkings.png",
    "CAESARS": "caesars.jpg",
    "BETMGM": "betmgm.png",
    "MGM": "betmgm.png",
    "BALLYS": "bally.png",
    "RIVERS": "rivers.png",
    "NOVIG": "novig.jpeg",
    "PROPHETX": "prophetx.png",
    "FANATICS": "fanatics.png",
    "KALSHI": "kalshi.png",
    "BOOKMAKER": "bookmaker.png",
    "BOOKIE": "bookmaker.png",
    "BM": "bookmaker.png",
    "BOL": "betonline.png",
    "BETONLINE": "betonline.png",
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


def _join_href(base: str, filename: str) -> str:
    b = (base or "").strip().rstrip("/")
    f = (filename or "").strip().lstrip("/")
    if not b:
        return f
    return f"{b}/{f}"


def _logo_href(
    label: str,
    logo_map: Dict[str, str],
    logo_base_href: str,
    available_logo_files: Optional[set[str]],
) -> Optional[str]:
    filename = logo_map.get(_normalize_key(label))
    if not filename:
        return None
    if available_logo_files is not None and filename.lower() not in available_logo_files:
        return None
    return _join_href(logo_base_href, filename)


def _badge_html(label: str, color: str, logo_href: Optional[str] = None) -> str:
    safe = html.escape((label or "").strip() or "(blank)")
    if logo_href:
        safe_logo_href = html.escape(logo_href, quote=True)
        return (
            '<span class="badge badge-logo" title="'
            f'{safe}">'
            f'<img class="badge-logo-img" src="{safe_logo_href}" alt="{safe}" loading="lazy" decoding="async" />'
            "</span>"
        )
    fg = _text_color_for_bg(color)
    return (
        f'<span class="badge badge-sticker" style="background:{color}; border-color:{color}; color:{fg};">{safe}</span>'
    )


def _league_badge(
    league: str, logo_base_href: str = "logos", available_logo_files: Optional[set[str]] = None
) -> str:
    key = _normalize_key(league)
    color = LEAGUE_COLOR_MAP.get(key, _fallback_color(league))
    logo_href = _logo_href(league, LEAGUE_LOGO_MAP, logo_base_href, available_logo_files)
    return _badge_html(league, color, logo_href=logo_href)


def _book_badge(
    book: str, logo_base_href: str = "logos", available_logo_files: Optional[set[str]] = None
) -> str:
    key = _normalize_key(book)
    color = BOOK_COLOR_MAP.get(key, _fallback_color(book))
    logo_href = _logo_href(book, BOOK_LOGO_MAP, logo_base_href, available_logo_files)
    return _badge_html(book, color, logo_href=logo_href)


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


def _risk_to_win_to_american_odds(risk: Optional[float], to_win: Optional[float]) -> Optional[float]:
    if risk is None or to_win is None:
        return None
    if math.isnan(risk) or math.isnan(to_win) or risk <= 0 or to_win <= 0:
        return None
    if to_win >= risk:
        return 100.0 * (to_win / risk)
    return -100.0 * (risk / to_win)


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
            date_cell = (row.get("D", "") or "").strip()
            if not date_cell:
                continue
            month_day = _parse_month_day(date_cell)
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


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and math.isnan(value)


def _finite_float(value: Any) -> Optional[float]:
    if value is None or _is_nan(value):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number):
        return None
    return number


def _sum_finite(values: Any) -> float:
    total = 0.0
    for value in values:
        number = _finite_float(value)
        if number is not None:
            total += number
    return total


def _counts_in_pl(bet: Bet) -> bool:
    # Open bets have no result and a blank net. They stay out of profit, ROI, and streaks.
    return bool(bet.result) and _finite_float(bet.net) is not None


RESULT_LABELS = {
    "W": "W",
    "L": "L",
    "P": "P",
    "CO": "Cash Out",
}


def _result_label(result: str) -> str:
    code = (result or "").strip().upper()
    if not code:
        return ""
    return RESULT_LABELS.get(code, code)


def _net_class(value: Any) -> str:
    number = _finite_float(value)
    if number is None or number == 0:
        return ""
    return "positive" if number > 0 else "negative"


def _edge_class(edge: Optional[float]) -> str:
    if edge is None or _is_nan(edge):
        return ""
    if edge > 0:
        return "positive"
    if edge < 0:
        return "negative"
    return ""


def _fmt_edge(edge: Optional[float]) -> str:
    if edge is None or _is_nan(edge):
        return "n/a"
    return f"{edge * 100.0:+.2f} pts"


def _record_note(counts: Dict[str, Any]) -> str:
    return (
        f"Resolved: {counts['resolved']} | Open: {counts['open']} | "
        f"Push: {counts['pushes']} | Cash out: {counts['cash_outs']}"
    )


def _edge_note(avgs: Dict[str, Any]) -> str:
    win_rate = _fmt_pct(avgs.get("win_rate")) or "n/a"
    implied = _fmt_pct(avgs.get("avg_implied_prob")) or "n/a"
    return f"Win {win_rate} vs implied {implied} (edge {_fmt_edge(avgs.get('edge'))})"


def _money_net_cell(value: Any) -> Any:
    number = _finite_float(value)
    if number is None:
        return ""
    text = _fmt_money(number)
    css = _net_class(number)
    if css:
        return (text, css)
    return text


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
    other = sum(1 for b in window if b.result and b.result not in {"W", "L", "P", "CO"})
    pl = [b for b in window if _counts_in_pl(b)]
    risk = sum(_nan_to_zero(b.risk) for b in pl)
    net = sum(b.net for b in pl)
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
    cash_outs = [b for b in bets if b.result == "CO"]
    open_bets = [b for b in bets if not b.result]
    other = [b for b in bets if b.result and b.result not in {"W", "L", "P", "CO"}]
    pl_bets = [b for b in bets if _counts_in_pl(b)]

    total_risk = sum(_nan_to_zero(b.risk) for b in pl_bets)
    total_net = sum(b.net for b in pl_bets)
    roi = _safe_div(total_net, total_risk)

    wins = [b for b in resolved if b.result == "W"]
    losses = [b for b in resolved if b.result == "L"]

    win_rate = _safe_div(len(wins), len(resolved))

    avg_risk = _safe_div(sum(_nan_to_zero(b.risk) for b in bets), len(bets))
    avg_odds = _safe_div(
        sum(b.odds_american for b in bets if b.odds_american is not None),
        sum(1 for b in bets if b.odds_american is not None),
    )

    decided_implied = [
        p
        for b in resolved
        if (p := _american_to_implied_prob(b.odds_american)) is not None
    ]
    avg_implied = _safe_div(sum(decided_implied), float(len(decided_implied))) if decided_implied else None
    edge = None if win_rate is None or avg_implied is None else win_rate - avg_implied

    by_league = group_metrics(bets, key_fn=lambda b: b.league)
    by_book = group_metrics(bets, key_fn=lambda b: b.book)
    by_type = group_metrics(bets, key_fn=lambda b: b.bet_type)

    # cumulative net by date
    net_by_date: Dict[dt.date, float] = defaultdict(float)
    risk_by_date: Dict[dt.date, float] = defaultdict(float)
    stake_by_date: Dict[dt.date, float] = defaultdict(float)
    count_by_date: Dict[dt.date, int] = defaultdict(int)
    for b in bets:
        count_by_date[b.date] += 1
        stake_by_date[b.date] += _nan_to_zero(b.risk)
        if not _counts_in_pl(b):
            continue
        net_by_date[b.date] += b.net
        risk_by_date[b.date] += _nan_to_zero(b.risk)

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
                "risk": stake_by_date.get(d, 0.0),
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
    all_bets_sorted = sorted(bets, key=lambda b: b.date, reverse=True)
    open_exposure = sum(_nan_to_zero(b.risk) for b in open_bets)

    today = dt.date.today()
    today_open = [b for b in open_bets if b.date == today]
    today_settled = [b for b in settled_bets if b.date == today]
    future_open = [b for b in open_bets if b.date > today]

    return {
        "as_of": as_of.isoformat(),
        "counts": {
            "total": len(bets),
            "resolved": len(resolved),
            "wins": len(wins),
            "losses": len(losses),
            "pushes": len(pushes),
            "cash_outs": len(cash_outs),
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
            "edge": edge,
        },
        "recent_periods": recent_periods,
        "recent_daily_series": recent_daily_series,
        "recent_7_day_calendar": recent_7_day_calendar,
        "open_exposure": open_exposure,
        "streaks": {
            "daily": daily_streaks,
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
        "all_bets": [bet_to_row(b) for b in all_bets_sorted],
        "today_open": [bet_to_row(b) for b in sorted(today_open, key=lambda b: b.date, reverse=True)],
        "today_settled": [bet_to_row(b) for b in sorted(today_settled, key=lambda b: b.date, reverse=True)],
        "future_open": [bet_to_row(b) for b in sorted(future_open, key=lambda b: b.date)],
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
        pl = [b for b in bs if _counts_in_pl(b)]
        risk = sum(_nan_to_zero(b.risk) for b in pl)
        net = sum(b.net for b in pl)
        resolved = [b for b in bs if b.result in {"W", "L"}]
        wins = sum(1 for b in resolved if b.result == "W")
        win_rate = (wins / len(resolved)) if resolved else None
        roi = (net / risk) if risk else None
        implied_vals = [
            p
            for b in resolved
            if (p := _american_to_implied_prob(b.odds_american)) is not None
        ]
        avg_implied = (sum(implied_vals) / len(implied_vals)) if implied_vals else None
        edge = (win_rate - avg_implied) if win_rate is not None and avg_implied is not None else None
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
                "avg_implied_prob": avg_implied,
                "edge": edge,
            }
        )

    rows.sort(key=lambda r: (r["net"], r["count"]), reverse=True)
    return rows


def _fmt_money(x: Optional[float]) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"${x:,.2f}"


def _fmt_money_compact(x: Optional[float]) -> str:
    return _fmt_money(x).rstrip("0").rstrip(".")


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
                "to_win_values": [],
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

        to_win = r.get("to_win")
        if to_win is not None and not (isinstance(to_win, float) and math.isnan(to_win)):
            g["to_win_values"].append(float(to_win))

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
        to_win_values = g["to_win_values"]
        net_values = g["net_values"]
        total_risk = sum(risk_values) if risk_values else float("nan")
        total_to_win = sum(to_win_values) if to_win_values else float("nan")
        display_odds: Optional[float]
        if g["count"] == 1:
            display_odds = odds_values[0] if odds_values else None
        else:
            has_complete_payout_data = len(risk_values) == g["count"] and len(to_win_values) == g["count"]
            display_odds = _risk_to_win_to_american_odds(total_risk, total_to_win) if has_complete_payout_data else None
            if display_odds is None and odds_values:
                display_odds = sum(odds_values) / len(odds_values)
        if display_odds is not None:
            display_odds = float(_round_half_away_from_zero(display_odds))

        collapsed.append(
            {
                "date": g["date"],
                "pick": g["pick"],
                "odds": display_odds,
                "risk": total_risk,
                "to_win": total_to_win,
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


def build_html_report(
    summary: Dict[str, Any],
    title: str,
    league_summaries: Dict[str, Dict[str, Any]],
    default_sport: str,
    logo_base_href: str = "logos",
    available_logo_files: Optional[set[str]] = None,
) -> str:
    as_of = summary["as_of"]
    synced_at = dt.datetime.now().astimezone()
    last_synced = synced_at.strftime("%I:%M %p %Z").lstrip("0")
    counts = summary["counts"]
    totals = summary["totals"]
    avgs = summary["averages"]
    today_label = f"{dt.date.today():%b} {dt.date.today().day}, {dt.date.today().year}"
    today_rows = summary["today_open"] + summary["today_settled"]
    today_net_total = _sum_finite(r.get("net") for r in summary["today_settled"])
    today_risk_total = _sum_finite(r.get("risk") for r in today_rows)
    today_open_risk = _sum_finite(r.get("risk") for r in summary["today_open"])
    if default_sport not in league_summaries and league_summaries:
        default_sport = next(iter(league_summaries.keys()))
    default_sport_summary = league_summaries.get(default_sport, summarize([]))

    series_json = json.dumps(summary["series"])
    recent_series_json = json.dumps(summary["recent_daily_series"])

    def league_badge(league: str) -> str:
        return _league_badge(
            league,
            logo_base_href=logo_base_href,
            available_logo_files=available_logo_files,
        )

    def book_badge(book: str) -> str:
        return _book_badge(
            book,
            logo_base_href=logo_base_href,
            available_logo_files=available_logo_files,
        )

    def today_bets() -> str:
        if not today_rows:
            return '<p class="today-empty">No bets today. Today’s wagers will appear here after the next sync.</p>'

        def league_style(league: str) -> str:
            color = LEAGUE_COLOR_MAP.get(league, LEAGUE_COLOR_MAP["OTHER"])
            rgb = ",".join(str(int(color[i:i + 2], 16)) for i in (1, 3, 5))
            return f"--league-color:{color};--league-rgb:{rgb}"

        rows = _collapse_bet_rows(today_rows)
        league_names = sorted({str(r.get("league") or "").strip().upper() or "OTHER" for r in rows})
        filters = ['<button type="button" data-today-league="" aria-pressed="true" aria-controls="today-bets">All</button>']
        for league in league_names:
            filters.append(f'<button type="button" data-today-league="{html.escape(league, quote=True)}" style="{league_style(league)}" aria-pressed="false" aria-controls="today-bets"><span class="today-league-dot" aria-hidden="true"></span>{html.escape(league)}</button>')
        items = {"open": [], "closed": []}
        statuses = {
            "": ("open", "Open", "◷"),
            "W": ("won", "Won", "✓"),
            "L": ("lost", "Lost", "×"),
            "P": ("push", "Push", "—"),
            "CO": ("cash-out", "Cash Out", "↗"),
        }
        for r in rows:
            result = str(r.get("result") or "").strip().upper()
            state, label, icon = statuses.get(result, ("other", _result_label(result), "—"))
            leagues = "".join(league_badge(x) for x in r["leagues"])
            books = "".join(book_badge(x) for x in r["books"])
            combined = f'<span class="today-combined">{r["row_count"]} wagers combined</span>' if r["row_count"] > 1 else ""
            amount = r.get("net") if result else r.get("to_win")
            amount_value = _finite_float(amount)
            amount_text = _fmt_money_compact(amount_value) or "—"
            if result and amount_value is not None:
                amount_text = ("+" if amount_value > 0 else "−" if amount_value < 0 else "") + _fmt_money_compact(abs(amount_value))
            amount_class = _net_class(amount_value) if result and amount_value is not None else ""
            risk_value = _finite_float(r.get("risk"))
            units = ""
            if risk_value is not None:
                unit_text = f"{risk_value / 100:.2f}".rstrip("0").rstrip(".")
                units = f'<span class="today-units" title="1u = $100">{unit_text}u</span>'
            league = str(r.get("league") or "").strip().upper() or "OTHER"
            items["closed" if result else "open"].append(f'''<li class="today-bet today-bet--{state}" data-league="{html.escape(league, quote=True)}" style="{league_style(league)}" data-risk="{_sum_finite([r.get('risk')])}" data-net="{_sum_finite([r.get('net')]) if result else 0}" data-count="{r['row_count']}" data-open="{str(not result).lower()}">
              <div class="today-bet-top">
                <div class="today-league"><span class="chip-row">{leagues}{books}</span><span>{html.escape(r["type"] or "Bet")}</span></div>
                <span class="today-result"><span aria-hidden="true">{icon}</span> {html.escape(label)}</span>
              </div>
              <div class="today-bet-body">
                <h4 class="today-pick">{html.escape(r["pick"])}</h4>
                <div class="today-meta"><span class="today-odds" title="Odds"><strong>{html.escape(_fmt_odds(r.get("odds"))) or "—"}</strong></span>{combined}</div>
              </div>
              <dl class="today-bet-money">
                <div class="today-stake"><dt>Risk</dt><dd>{_fmt_money_compact(r.get("risk")) or "—"}{units}</dd></div>
                <div class="today-return"><dt{(' class="today-net-label"' if result else '')}>{"Net result" if result else "To win"}</dt><dd class="{amount_class}">{amount_text}</dd></div>
              </dl>
            </li>''')
        groups = "".join(
            f'<div class="today-group" data-today-group="{status}" role="group" aria-labelledby="today-{status}-title"{(" hidden" if not bets else "")}>'
            f'<h3 id="today-{status}-title" class="today-group-title">{status.title()} <span class="today-group-count">{len(bets)}</span></h3>'
            f'<ul class="today-bets" aria-label="{status.title()} bets">{"".join(bets)}</ul></div>'
            for status, bets in items.items()
        )
        return (
            '<div class="today-filter-bar" hidden><div class="today-filter-controls">'
            '<div class="today-filters today-status-filters" role="group" aria-label="Filter today’s bets by status">'
            '<button type="button" data-today-status="" aria-pressed="true" aria-controls="today-bets">All</button>'
            '<button type="button" data-today-status="open" aria-pressed="false" aria-controls="today-bets">Open</button>'
            '<button type="button" data-today-status="closed" aria-pressed="false" aria-controls="today-bets">Closed</button>'
            '</div><div class="today-filters" role="group" aria-label="Filter today’s bets by league">'
            + "".join(filters)
            + f'</div></div><span id="today-filter-count" class="note" role="status">{len(rows)} bets</span></div>'
            + '<div id="today-bets">' + groups
            + '<p id="today-filter-empty" class="today-empty" hidden>No bets match these filters.</p></div>'
        )

    def group_table(group_rows: List[Dict[str, Any]], limit: int = 25, badge_kind: str = "") -> str:
        headers = ["Group", "Bets", "W", "L", "Risk", "Net", "ROI", "Win%"]
        rows = []
        for r in group_rows[:limit]:
            net_fmt = _fmt_money(r["net"])
            net_cls = "positive" if r["net"] >= 0 else "negative"
            roi_fmt = _fmt_pct(r["roi"])
            roi_cls = _net_class(r["roi"]) if r["roi"] is not None else ""
            win_fmt = _fmt_pct(r["win_rate"])
            win_cls = _edge_class(r.get("edge"))
            key_label = str(r["key"])
            if badge_kind == "league":
                group_cell = league_badge(key_label)
            elif badge_kind == "book":
                group_cell = book_badge(key_label)
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
                    (roi_fmt, roi_cls) if roi_cls else roi_fmt,
                    (win_fmt, win_cls) if win_cls else win_fmt,
                ]
            )
        return _render_table(headers, rows)

    def bets_table(
        bet_rows: List[Dict[str, Any]],
        include_result: bool = True,
        include_net: bool = True,
        collapse_duplicates: bool = True,
        show_totals: bool = False,
    ) -> str:
        rows_in = _collapse_bet_rows(bet_rows) if collapse_duplicates else bet_rows
        headers = ["Date", "League", "Book", "Type", "Pick", "Odds", "Risk"]
        if include_result:
            headers.append("Result")
        if include_net:
            headers.append("Net")
        rows = []
        total_risk = 0.0
        total_net = 0.0
        for r in rows_in:
            leagues = r.get("leagues") or [r.get("league", "")]
            books = r.get("books") or [r.get("book", "")]
            if len(leagues) == 1:
                league_cell = league_badge(leagues[0])
            else:
                league_cell = f'<div class="chip-row">{"".join(league_badge(x) for x in leagues)}</div>'
            if len(books) == 1:
                book_cell = book_badge(books[0])
            else:
                book_cell = f'<div class="chip-row">{"".join(book_badge(x) for x in books)}</div>'

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
                row.append(html.escape(_result_label(str(r.get("result") or ""))))
            if include_net:
                row.append(_money_net_cell(r.get("net")))
            rows.append(row)
            finite_risk = _finite_float(r.get("risk"))
            if finite_risk is not None:
                total_risk += finite_risk
            if include_net:
                finite_net = _finite_float(r.get("net"))
                if finite_net is not None:
                    total_net += finite_net

        if not show_totals:
            return _render_table(headers, rows)

        ths = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
        tbody_rows = []
        for r in rows:
            tds = []
            for c in r:
                if isinstance(c, tuple):
                    formatted, cls = c
                    tds.append(f'<td class="{cls}">{formatted}</td>')
                else:
                    tds.append(f"<td>{c}</td>")
            tbody_rows.append(f"<tr>{''.join(tds)}</tr>")

        tfoot_cells = [""] * len(headers)
        tfoot_cells[0] = '<span class="muted">Subtotal</span>'
        risk_idx = headers.index("Risk")
        tfoot_cells[risk_idx] = _fmt_money(total_risk)
        if include_net and "Net" in headers:
            net_idx = headers.index("Net")
            net_cls = _net_class(total_net)
            net_text = _fmt_money(total_net)
            if net_cls:
                tfoot_cells[net_idx] = f'<span class="{net_cls}">{net_text}</span>'
            else:
                tfoot_cells[net_idx] = net_text
        tfoot_html = "".join(f"<td>{c}</td>" for c in tfoot_cells)

        return (
            f"<table><thead><tr>{ths}</tr></thead>"
            f"<tbody>{''.join(tbody_rows)}</tbody>"
            f"<tfoot><tr>{tfoot_html}</tr></tfoot></table>"
        )

    def all_bets_table(bet_rows: List[Dict[str, Any]]) -> str:
        if not bet_rows:
            return "<div class='note'>No bets available.</div>"

        header_cols = [
            ("date", "Date", "text"),
            ("league", "League", "text"),
            ("book", "Book", "text"),
            ("type", "Type", "text"),
            ("pick", "Pick", "text"),
            ("odds", "Odds", "number"),
            ("risk", "Risk", "number"),
            ("result", "Result", "text"),
            ("net", "Net", "number"),
        ]
        thead = "".join(
            f"<th><button type='button' class='sort-btn' data-key='{key}' data-type='{kind}'>{html.escape(label)}</button></th>"
            for key, label, kind in header_cols
        )

        trs = []
        for r in bet_rows:
            league = str(r.get("league", "") or "").strip()
            book = str(r.get("book", "") or "").strip()
            bet_type = str(r.get("type", "") or "").strip()
            pick = str(r.get("pick", "") or "").strip()
            result = str(r.get("result", "") or "").strip().upper()
            date = str(r.get("date", "") or "").strip()
            odds = r.get("odds")
            risk = r.get("risk")
            net = r.get("net")

            odds_val = "" if odds is None or (isinstance(odds, float) and math.isnan(odds)) else f"{float(odds):.8f}"
            risk_val = "" if risk is None or (isinstance(risk, float) and math.isnan(risk)) else f"{float(risk):.8f}"
            net_val = "" if net is None or (isinstance(net, float) and math.isnan(net)) else f"{float(net):.8f}"

            finite_net = _finite_float(net)
            net_cls = _net_class(finite_net)

            row_attrs = (
                f"data-date='{html.escape(date, quote=True)}' "
                f"data-league='{html.escape(league, quote=True)}' "
                f"data-book='{html.escape(book, quote=True)}' "
                f"data-type='{html.escape(bet_type, quote=True)}' "
                f"data-pick='{html.escape(pick, quote=True)}' "
                f"data-odds='{html.escape(odds_val, quote=True)}' "
                f"data-risk='{html.escape(risk_val, quote=True)}' "
                f"data-result='{html.escape(result, quote=True)}' "
                f"data-net='{html.escape(net_val, quote=True)}'"
            )

            cells = [
                html.escape(_fmt_date_short(date)),
                league_badge(league),
                book_badge(book),
                html.escape(bet_type),
                html.escape(pick),
                html.escape(_fmt_odds(odds)),
                _fmt_money(risk),
                html.escape(_result_label(result)),
                (_fmt_money(finite_net), net_cls) if net_cls else (_fmt_money(finite_net) if finite_net is not None else ""),
            ]
            tds = []
            for c in cells:
                if isinstance(c, tuple):
                    formatted, cls = c
                    tds.append(f'<td class="{cls}">{formatted}</td>')
                else:
                    tds.append(f"<td>{c}</td>")
            trs.append(f"<tr class='all-bets-row' {row_attrs}>{''.join(tds)}</tr>")

        return (
            "<div class='scroll'>"
            "<table id='all-bets-table'>"
            f"<thead><tr>{thead}</tr></thead>"
            f"<tbody>{''.join(trs)}</tbody>"
            "</table>"
            "</div>"
        )

    def period_table(period_rows: List[Dict[str, Any]]) -> str:
        headers = ["Window", "Bets", "W-L", "Win%", "Risk", "Net", "ROI", "Open"]
        rows = []
        for r in period_rows:
            net_cls = _net_class(r["net"])
            roi_cls = _net_class(r["roi"]) if r["roi"] is not None else ""
            net_text = _fmt_money(r["net"])
            roi_text = _fmt_pct(r["roi"])
            rows.append(
                [
                    html.escape(r["label"]),
                    str(r["bets"]),
                    f"{r['wins']}-{r['losses']}",
                    _fmt_pct(r["win_rate"]),
                    _fmt_money(r["risk"]),
                    (net_text, net_cls) if net_cls else net_text,
                    (roi_text, roi_cls) if roi_cls else roi_text,
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

    def current_streak_text(streak_group: Dict[str, Any]) -> str:
        current = streak_group["current"]
        if current["length"] > 0:
            return (
                f"{current['length']} {current['type']} "
                f"day(s) ({current['start']} to {current['end']})"
            )
        return "No active daily win/loss streak"

    def sport_summary_payload(league_label: str, league_summary: Dict[str, Any]) -> Dict[str, Any]:
        league_counts = league_summary["counts"]
        league_totals = league_summary["totals"]
        league_avgs = league_summary["averages"]
        league_streaks = league_summary["streaks"]
        league_best_day = league_summary["best_day"]
        league_worst_day = league_summary["worst_day"]

        best_day_text = "n/a"
        if league_best_day:
            best_day_text = f"{league_best_day['date']} ({_fmt_money(league_best_day['net'])})"

        worst_day_text = "n/a"
        if league_worst_day:
            worst_day_text = f"{league_worst_day['date']} ({_fmt_money(league_worst_day['net'])})"

        return {
            "label": league_label,
            "as_of": league_summary["as_of"],
            "counts": league_counts,
            "totals": league_totals,
            "averages": league_avgs,
            "open_exposure": league_summary["open_exposure"],
            "series": league_summary["series"],
            "recent_daily_series": league_summary["recent_daily_series"],
            "recent_periods_html": period_table(league_summary["recent_periods"]),
            "recent_calendar_html": daily_net_risk_calendar(league_summary["recent_7_day_calendar"]),
            "recently_settled_html": bets_table(league_summary["recently_settled"][:25]),
            "open_bets_html": bets_table(league_summary["open_bets"]),
            "by_book_html": group_table(league_summary["by_book"], badge_kind="book"),
            "by_type_html": group_table(league_summary["by_type"]),
            "top_wins_html": bets_table(league_summary["top_wins"], include_result=False),
            "top_losses_html": bets_table(league_summary["top_losses"], include_result=False),
            "longest_shots_html": bets_table(league_summary["longest_shots"], include_result=False),
            "daily_current_text": current_streak_text(league_streaks["daily"]),
            "streak_lines_html": "".join(
                [
                    streak_line("Longest daily win streak", league_streaks["daily"]["best_win"]),
                    streak_line("Longest daily loss streak", league_streaks["daily"]["best_loss"]),
                ]
            ),
            "best_day_text": best_day_text,
            "worst_day_text": worst_day_text,
        }

    daily_streaks = summary["streaks"]["daily"]

    daily_current_text = current_streak_text({"current": daily_streaks["current"]})

    best_day = summary["best_day"]
    worst_day = summary["worst_day"]
    sport_options = list(league_summaries.keys())
    sport_options_html = "".join(
        f"<option value=\"{html.escape(league)}\"{' selected' if league == default_sport else ''}>{html.escape(league)}</option>"
        for league in sport_options
    )
    sport_summaries_json = json.dumps(
        {league: sport_summary_payload(league, league_summary) for league, league_summary in league_summaries.items()}
    )
    default_sport_payload = sport_summary_payload(default_sport, default_sport_summary)

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
    .history-split {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }}
    .history-col {{ display: flex; flex-direction: column; gap: 12px; min-width: 0; }}
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
    .row-controls {{ display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 10px; }}
    .search-input {{
      flex: 1 1 260px;
      min-width: 220px;
      background: rgba(255,255,255,0.03);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
      font-size: 13px;
      box-sizing: border-box;
    }}
    .control-input {{
      box-sizing: border-box;
      width: 100%;
      min-width: 0;
      background: rgba(255,255,255,0.03);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 7px 10px;
      font-size: 12px;
      line-height: 1.25;
      min-height: 40px;
      flex: 0 0 auto;
    }}
    select.control-input {{
      appearance: none;
      background-image:
        linear-gradient(45deg, transparent 50%, var(--muted) 50%),
        linear-gradient(135deg, var(--muted) 50%, transparent 50%);
      background-position:
        calc(100% - 18px) calc(50% - 2px),
        calc(100% - 12px) calc(50% - 2px);
      background-size: 6px 6px, 6px 6px;
      background-repeat: no-repeat;
      padding-right: 28px;
    }}
    .filter-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-bottom: 14px;
      align-items: end;
    }}
    .filter-field {{
      display: flex;
      flex-direction: column;
      gap: 5px;
      min-width: 0;
    }}
    .filter-label {{
      color: var(--muted);
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .filter-range {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
    .filter-actions {{
      display: flex;
      align-items: end;
      gap: 8px;
      min-width: 0;
    }}
    .filter-btn {{
      box-sizing: border-box;
      background: rgba(157, 176, 208, 0.15);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 9px;
      padding: 0 14px;
      min-height: 40px;
      font-size: 12px;
      cursor: pointer;
      white-space: nowrap;
    }}
    .filter-btn:hover {{ border-color: rgba(96, 165, 250, 0.5); }}
    .all-bets-kpis {{
      display: grid;
      grid-template-columns: repeat(5, minmax(120px, 1fr));
      gap: 10px;
      margin-bottom: 10px;
    }}
    .sub-kpi {{
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 8px 10px;
      background: rgba(255,255,255,0.02);
    }}
    .sub-kpi .label {{ color: var(--muted); font-size: 11px; }}
    .sub-kpi .value {{ margin-top: 4px; font-size: 15px; font-variant-numeric: tabular-nums; }}
    .sort-btn {{
      appearance: none;
      border: 0;
      background: transparent;
      color: inherit;
      padding: 0;
      font: inherit;
      cursor: pointer;
      text-align: left;
    }}
    .sort-btn.active {{ color: var(--accent); }}
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
    .badge-logo {{
      width: 26px;
      height: 26px;
      padding: 2px;
      border-radius: 7px;
      justify-content: center;
      background: rgba(255,255,255,0.96);
      border-color: rgba(15,23,42,0.16);
      overflow: hidden;
      vertical-align: middle;
    }}
    .badge-logo-img {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      object-position: center;
    }}
    .badge-sticker {{
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.18);
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

    .today-panel {{ min-width: 0; padding: 10px 12px; }}
    .today-header {{ display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 16px; margin-bottom: 7px; }}
    .today-heading {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 10px; }}
    .today-heading h2 {{ margin: 0; font-size: 16px; }}
    .today-date {{ font-size: 12px; color: var(--muted); }}
    .today-header .note {{ margin-top: 3px; font-size: 11px; }}
    .today-view {{ display: flex; gap: 3px; padding: 3px; border: 1px solid var(--border); border-radius: 9px; background: var(--bg); }}
    .today-view[hidden] {{ display: none; }}
    .today-filter-bar {{ display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 4px 10px; margin-bottom: 6px; padding-top: 6px; border-top: 1px solid var(--border); }}
    .today-filter-controls {{ display: flex; flex-wrap: wrap; align-items: center; gap: 4px 8px; }}
    .today-status-filters {{ padding-right: 8px; border-right: 1px solid var(--border); }}
    .today-filter-bar[hidden], .today-panel[data-view] .today-bet[hidden], .today-group[hidden], #today-filter-empty[hidden] {{ display: none; }}
    .today-group + .today-group {{ margin-top: 9px; }}
    .today-group[hidden] + .today-group {{ margin-top: 0; }}
    .today-group-title {{ display: flex; align-items: center; gap: 6px; margin: 0 0 5px; font-size: 11px; font-weight: 600; color: var(--muted); }}
    .today-group-title::after {{ content: ''; height: 1px; flex: 1; background: var(--border); }}
    [data-today-group="open"] .today-group-title {{ color: var(--accent); }}
    .today-group-count {{ font-weight: 400; color: var(--muted); font-variant-numeric: tabular-nums; }}
    .today-filters {{ display: flex; flex-wrap: wrap; gap: 4px; }}
    .today-filters button {{ display: inline-flex; align-items: center; gap: 5px; min-height: 26px; padding: 2px 7px; border: 1px solid transparent; border-radius: 5px; background: transparent; color: var(--muted); font: inherit; font-size: 11px; cursor: pointer; }}
    .today-filters button:hover {{ background: rgba(255,255,255,0.04); color: var(--text); }}
    .today-filters button[aria-pressed="true"] {{ border-color: var(--border); background: rgba(255,255,255,0.06); color: var(--text); }}
    .today-filters button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .today-league-dot {{ width: 6px; height: 6px; border-radius: 50%; background: var(--league-color); box-shadow: 0 0 0 1px rgba(255,255,255,0.18); }}
    #today-filter-count {{ font-size: 11px; }}
    .today-view button {{ display: inline-flex; align-items: center; gap: 6px; border: 1px solid transparent; border-radius: 6px; background: transparent; color: var(--muted); padding: 5px 8px; font: inherit; font-size: 11px; cursor: pointer; }}
    .today-view button[aria-pressed="true"] {{ color: var(--text); background: rgba(96,165,250,0.18); border-color: rgba(96,165,250,0.35); }}
    .today-view button:hover {{ color: var(--text); }}
    .today-view button:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
    .today-view svg {{ width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 1.5; }}
    .today-summary {{ display: flex; flex-wrap: wrap; gap: 5px 12px; margin: 0 0 0 auto; }}
    .today-summary > div {{ display: flex; align-items: baseline; gap: 6px; }}
    .today-panel dt {{ color: var(--muted); font-size: 11px; line-height: 1.4; }}
    .today-panel dd {{ margin: 3px 0 0; font-size: 18px; font-weight: 700; font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }}
    .today-summary dd {{ margin: 0; font-size: 14px; }}
    .today-summary .today-risk-value {{ color: #fbbf24; }}
    .today-bets {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; list-style: none; padding: 0; margin: 0; }}
    .today-bet {{ --result-color: var(--muted); --result-bg: rgba(157,176,208,0.1); display: flex; flex-direction: column; min-width: 0; padding: 8px 10px; border: 1px solid rgba(var(--league-rgb),0.25); border-left: 2px solid rgba(var(--league-rgb),0.65); border-radius: 8px; background: linear-gradient(135deg, rgba(var(--league-rgb),0.10), rgba(var(--league-rgb),0.025)); }}
    .today-bet--open {{ --result-color: var(--accent); --result-bg: rgba(96,165,250,0.12); }}
    .today-bet--won {{ --result-color: var(--good); --result-bg: rgba(52,211,153,0.12); }}
    .today-bet--lost {{ --result-color: var(--bad); --result-bg: rgba(251,113,133,0.12); }}
    .today-bet-top {{ display: flex; justify-content: space-between; align-items: center; gap: 8px; }}
    .today-league {{ display: flex; align-items: center; flex-wrap: wrap; gap: 7px; color: var(--muted); font-size: 11px; min-width: 0; overflow-wrap: anywhere; }}
    .today-result {{ display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0; border: 1px solid var(--result-color); background: var(--result-bg); color: var(--result-color); border-radius: 5px; padding: 2px 5px; font-size: 10px; font-weight: 700; }}
    .today-result > span {{ font-size: 12px; line-height: 1; }}
    .today-bet-body {{ flex: 1; min-width: 0; padding: 5px 0; }}
    .today-pick {{ margin: 0 0 4px; font-size: 16px; font-weight: 700; line-height: 1.3; overflow-wrap: anywhere; }}
    .today-meta {{ display: flex; align-items: center; flex-wrap: wrap; gap: 5px 8px; color: var(--muted); font-size: 11px; }}
    .today-odds {{ white-space: nowrap; }}
    .today-odds strong {{ color: var(--text); font-size: 13px; font-variant-numeric: tabular-nums; }}
    .today-bet .badge-logo {{ width: 18px; height: 18px; border-radius: 5px; }}
    .today-combined {{ font-size: 10px; }}
    .today-bet-money {{ display: grid; grid-template-columns: 1fr 1fr; align-items: center; gap: 8px; margin: 0; padding-top: 7px; border-top: 1px solid var(--border); }}
    .today-stake {{ background: rgba(251,191,36,0.07); border: 1px solid rgba(251,191,36,0.18); border-radius: 5px; padding: 5px 7px; }}
    .today-stake dt {{ color: #fbbf24; font-weight: 600; }}
    .today-stake dd {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 3px 6px; }}
    .today-units {{ color: var(--muted); font-size: 10px; font-weight: 400; letter-spacing: 0; white-space: nowrap; }}
    .today-return {{ padding: 5px 0; text-align: right; }}
    .today-return dd {{ font-size: 16px; }}
    .today-net-label {{ position: absolute; width: 1px; height: 1px; padding: 0; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }}
    .today-panel[data-view="cards"] .today-bet-body {{ display: flex; align-items: center; align-content: flex-start; flex-wrap: wrap; gap: 4px 8px; }}
    .today-panel[data-view="cards"] .today-pick {{ margin: 0; min-width: 0; }}
    .today-panel[data-view="cards"] .today-meta {{ gap: 4px 6px; }}
    .today-panel[data-view="cards"] .today-bet-money {{ display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 8px; padding-top: 5px; }}
    .today-panel[data-view="cards"] .today-stake, .today-panel[data-view="cards"] .today-return {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 6px; padding: 3px 6px; }}
    .today-panel[data-view="cards"] .today-return {{ margin-left: auto; padding-right: 0; }}
    .today-panel[data-view="cards"] .today-bet-money dd {{ margin: 0; font-size: 16px; }}
    .today-empty {{ margin: 0; padding: 12px; text-align: center; color: var(--muted); font-size: 12px; }}
    .today-panel[data-view="list"] .today-bets {{ grid-template-columns: 1fr; gap: 4px; }}
    .today-panel[data-view="list"] .today-bet {{ display: grid; grid-template-columns: 180px minmax(0, 1fr) 250px; align-items: center; gap: 10px; padding: 5px 8px; border-radius: 6px; }}
    .today-panel[data-view="list"] .today-bet-top {{ justify-content: flex-start; align-items: center; flex-wrap: wrap; gap: 4px 6px; }}
    .today-panel[data-view="list"] .today-league {{ gap: 5px; }}
    .today-panel[data-view="list"] .today-result {{ gap: 3px; padding: 1px 4px; }}
    .today-panel[data-view="list"] .today-bet-body {{ display: flex; align-items: center; flex-wrap: wrap; gap: 3px 10px; padding: 0; }}
    .today-panel[data-view="list"] .today-pick {{ flex: 1 1 160px; font-size: 14px; margin: 0; }}
    .today-panel[data-view="list"] .today-meta {{ gap: 3px 6px; }}
    .today-panel[data-view="list"] .badge-logo {{ width: 16px; height: 16px; padding: 1px; border-radius: 4px; }}
    .today-panel[data-view="list"] .today-bet-money {{ display: flex; align-items: baseline; flex-wrap: wrap; justify-content: space-between; gap: 3px 8px; border: 0; padding: 0; }}
    .today-panel[data-view="list"] .today-stake, .today-panel[data-view="list"] .today-return {{ display: flex; align-items: baseline; flex-wrap: wrap; gap: 3px 5px; padding: 2px 5px; }}
    .today-panel[data-view="list"] .today-return {{ margin-left: auto; padding-right: 0; }}
    .today-panel[data-view="list"] .today-bet-money dd {{ margin: 0; font-size: 14px; }}
    @media (max-width: 1100px) {{
      .today-bets {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .today-panel[data-view="list"] .today-bet {{ grid-template-columns: 160px minmax(0, 1fr) 230px; gap: 8px; }}
    }}
    @media (max-width: 640px) {{
      .today-bets {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 720px) {{
      .today-summary {{ order: 1; flex-basis: 100%; margin-left: 0; }}
      .today-panel[data-view="list"] .today-bet {{ grid-template-columns: minmax(0, 1fr); gap: 4px; }}
    }}

    @media (max-width: 1000px) {{
      .kpi {{ grid-column: span 6; }}
      .half {{ grid-column: span 12; }}
      .third {{ grid-column: span 12; }}
      .history-split {{ grid-template-columns: 1fr; }}
      .filter-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .all-bets-kpis {{ grid-template-columns: repeat(2, minmax(120px, 1fr)); }}
    }}
    @media (max-width: 640px) {{
      .filter-grid {{ grid-template-columns: 1fr; }}
      .filter-range {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class=\"container\">
    <h1>{html.escape(title)}</h1>
    <div class=\"subtitle\">As of {html.escape(as_of)} | Last synced {html.escape(last_synced)}</div>
    <div class="tabs">
      <button class="tab-btn active" data-tab="home">Home</button>
      <button class="tab-btn" data-tab="history">History</button>
      <button class="tab-btn" data-tab="all-bets">All Bets</button>
      <button class="tab-btn" data-tab="sports">Sports</button>
    </div>

    <section id="tab-home" class="tab-panel active">
      <div class=\"grid\">
        <div class="card kpi">
          <div class="label">Total Bets</div>
          <div class="value">{counts['total']}</div>
          <div class="note">{_record_note(counts)}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Net Profit</div>
          <div class=\"value {'good' if totals['net'] >= 0 else 'bad'}\">{_fmt_money(totals['net'])}</div>
          <div class=\"note\">Settled ROI: {_fmt_pct(totals['roi'])}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Win Rate (W/L only)</div>
          <div class=\"value\">{_fmt_pct(avgs['win_rate'])}</div>
          <div class=\"note\">W: {counts['wins']} | L: {counts['losses']} | Edge vs implied: {_fmt_edge(avgs['edge'])}</div>
        </div>
        <div class=\"card kpi\">
          <div class=\"label\">Open Risk</div>
          <div class=\"value\">{_fmt_money(summary['open_exposure'])}</div>
        </div>

        <section id="today-panel" class="card full today-panel" data-view="cards" aria-labelledby="today-title">
          <div class="today-header">
            <div>
              <div class="today-heading"><h2 id="today-title">Today</h2><span class="today-date">{today_label}</span></div>
              <div id="today-wager-count" class="note">{len(today_rows)} wagers · {len(summary['today_open'])} open · {len(summary['today_settled'])} settled</div>
            </div>
          <dl class="today-summary">
            <div data-today-total="risk"><dt>Total risk</dt><dd>{_fmt_money_compact(today_risk_total)}</dd></div>
            <div data-today-total="open"><dt>Open risk</dt><dd class="today-risk-value">{_fmt_money_compact(today_open_risk)}</dd></div>
            <div data-today-total="net"><dt>Settled net</dt><dd class="{_net_class(today_net_total)}">{_fmt_money_compact(today_net_total)}</dd></div>
          </dl>
            <div class="today-view" role="group" aria-label="Today’s bet layout" hidden>
              <button type="button" data-today-view="cards" aria-pressed="true" aria-controls="today-bets"><svg viewBox="0 0 16 16" aria-hidden="true"><rect x="1" y="1" width="5" height="5" rx="1"/><rect x="10" y="1" width="5" height="5" rx="1"/><rect x="1" y="10" width="5" height="5" rx="1"/><rect x="10" y="10" width="5" height="5" rx="1"/></svg>Cards</button>
              <button type="button" data-today-view="list" aria-pressed="false" aria-controls="today-bets"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="M5 3h10M5 8h10M5 13h10M1 3h1M1 8h1M1 13h1"/></svg>List</button>
            </div>
          </div>
          {today_bets()}
        </section>

        <div class="card full">
          <div class="section-title">Upcoming Open Bets</div>
          <div class="note">Open bets scheduled after {today_label}.</div>
          <div class="scroll">{bets_table(summary['future_open'], include_result=False, include_net=False)}</div>
        </div>

        <div class="card full">
          <div class="section-title">Daily Net / Risk (Last 7 Days)</div>
          {daily_net_risk_calendar(summary['recent_7_day_calendar'])}
        </div>

        <div class="card full">
          <div class="section-title">Recent Performance</div>
          <div class="note">Net and ROI use settled bets only. Open stakes stay in Open Risk.</div>
          <div class="scroll">{period_table(summary['recent_periods'])}</div>
        </div>

        <div class="card full">
          <div class="section-title">Recently Settled Bets</div>
          <div class="scroll">{bets_table(summary['recently_settled'][:25])}</div>
        </div>

        <div class="card half">
          <div class="section-title">Notable Streaks</div>
          <div class="note">{html.escape(daily_current_text)}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            {streak_line("Longest daily win streak", daily_streaks["best_win"])}
            {streak_line("Longest daily loss streak", daily_streaks["best_loss"])}
          </div>
        </div>

        <div class="card half">
          <div class="section-title">Recent Highlights</div>
          <div class="note">Avg Risk / Bet: {_fmt_money(avgs['avg_risk'])}</div>
          <div class="note">{_edge_note(avgs)}</div>
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
          <div class="note">Cumulative ROI = settled net / settled risk. Open bets are excluded.</div>
        </div>
      </div>

      <div class="history-split">
        <div class="history-col">
          <div class="card">
            <div class=\"section-title\">By League (top 25 by Net)</div>
            <div class=\"scroll\">{group_table(summary['by_league'], badge_kind='league')}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">By Type (top 25 by Net)</div>
            <div class=\"scroll\">{group_table(summary['by_type'])}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">Biggest Wins (top 10)</div>
            <div class=\"scroll\">{bets_table(summary['top_wins'], include_result=False)}</div>
          </div>
        </div>
        <div class="history-col">
          <div class="card">
            <div class=\"section-title\">By Book (top 25 by Net)</div>
            <div class=\"scroll\">{group_table(summary['by_book'], badge_kind='book')}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">Biggest Losses (top 10)</div>
            <div class=\"scroll\">{bets_table(summary['top_losses'], include_result=False)}</div>
          </div>
          <div class="card">
            <div class=\"section-title\">Longest Shots (top 10 winning odds)</div>
            <div class=\"note\">Winning wagers with the longest pre-game odds (lowest implied win probability).</div>
            <div class=\"scroll\">{bets_table(summary['longest_shots'], include_result=False)}</div>
          </div>
        </div>
      </div>
    </section>

    <section id="tab-all-bets" class="tab-panel">
      <div class="card">
        <div class="section-title">All Bets (2026+)</div>
        <div class="note">Every table column now has a dedicated filter. Use date ranges or numeric min/max for greater-than / less-than filtering.</div>

        <div class="filter-grid">
          <label class="filter-field">
            <span class="filter-label">Pick Contains</span>
            <input id="all-bets-pick-filter" class="control-input" type="text" placeholder="Exact pick text or fragment" />
          </label>
          <label class="filter-field">
            <span class="filter-label">Date Range</span>
            <div class="filter-range">
              <input id="all-bets-date-from" class="control-input" type="date" />
              <input id="all-bets-date-to" class="control-input" type="date" />
            </div>
          </label>
          <label class="filter-field">
            <span class="filter-label">League</span>
            <select id="all-bets-league-filter" class="control-input">
              <option value="">All leagues</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Book</span>
            <select id="all-bets-book-filter" class="control-input">
              <option value="">All books</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Type</span>
            <select id="all-bets-type-filter" class="control-input">
              <option value="">All types</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Result</span>
            <select id="all-bets-result-filter" class="control-input">
              <option value="">All results</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="filter-label">Odds Range</span>
            <div class="filter-range">
              <input id="all-bets-odds-min" class="control-input" type="number" step="0.01" placeholder="Min" />
              <input id="all-bets-odds-max" class="control-input" type="number" step="0.01" placeholder="Max" />
            </div>
          </label>
          <label class="filter-field">
            <span class="filter-label">Risk Range</span>
            <div class="filter-range">
              <input id="all-bets-risk-min" class="control-input" type="number" step="0.01" placeholder="Min" />
              <input id="all-bets-risk-max" class="control-input" type="number" step="0.01" placeholder="Max" />
            </div>
          </label>
          <label class="filter-field">
            <span class="filter-label">Net Range</span>
            <div class="filter-range">
              <input id="all-bets-net-min" class="control-input" type="number" step="0.01" placeholder="Min" />
              <input id="all-bets-net-max" class="control-input" type="number" step="0.01" placeholder="Max" />
            </div>
          </label>
          <div class="filter-actions">
            <button id="all-bets-clear" class="filter-btn" type="button">Clear Filters</button>
          </div>
        </div>

        <div class="all-bets-kpis">
          <div class="sub-kpi">
            <div class="label">Visible Bets</div>
            <div id="all-bets-count" class="value">0</div>
          </div>
          <div class="sub-kpi">
            <div class="label">Visible Risk</div>
            <div id="all-bets-risk" class="value">$0.00</div>
          </div>
          <div class="sub-kpi">
            <div class="label">Visible Net</div>
            <div id="all-bets-net" class="value">$0.00</div>
          </div>
          <div class="sub-kpi">
            <div class="label">Settled ROI</div>
            <div id="all-bets-roi" class="value">0.00%</div>
          </div>
          <div class="sub-kpi">
            <div class="label">W-L-Open</div>
            <div id="all-bets-wlo" class="value">0-0-0</div>
          </div>
        </div>

        {all_bets_table(summary['all_bets'])}
      </div>
    </section>

    <section id="tab-sports" class="tab-panel">
      <div class="row-controls">
        <select id="sport-select" class="control-input">
          {sport_options_html}
        </select>
        <div class="note">Switch this tab to any league tag in your sheet. It starts on {html.escape(default_sport)} to preserve the current workflow.</div>
      </div>
      <div class="grid">
        <div class="card kpi">
          <div id="sport-kpi-total-label" class="label">{html.escape(default_sport_payload['label'])} Total Bets</div>
          <div id="sport-kpi-total-value" class="value">{default_sport_payload['counts']['total']}</div>
          <div id="sport-kpi-total-note" class="note">{_record_note(default_sport_payload['counts'])}</div>
        </div>
        <div class="card kpi">
          <div id="sport-kpi-net-label" class="label">{html.escape(default_sport_payload['label'])} Net Profit</div>
          <div id="sport-kpi-net-value" class="value {'good' if default_sport_payload['totals']['net'] >= 0 else 'bad'}">{_fmt_money(default_sport_payload['totals']['net'])}</div>
          <div id="sport-kpi-net-note" class="note">Settled ROI: {_fmt_pct(default_sport_payload['totals']['roi'])}</div>
        </div>
        <div class="card kpi">
          <div id="sport-kpi-win-label" class="label">{html.escape(default_sport_payload['label'])} Win Rate (W/L)</div>
          <div id="sport-kpi-win-value" class="value">{_fmt_pct(default_sport_payload['averages']['win_rate'])}</div>
          <div id="sport-kpi-win-note" class="note">W: {default_sport_payload['counts']['wins']} | L: {default_sport_payload['counts']['losses']} | Edge vs implied: {_fmt_edge(default_sport_payload['averages']['edge'])}</div>
        </div>
        <div class="card kpi">
          <div id="sport-kpi-open-label" class="label">{html.escape(default_sport_payload['label'])} Open Exposure</div>
          <div id="sport-kpi-open-value" class="value">{_fmt_money(default_sport_payload['open_exposure'])}</div>
          <div id="sport-kpi-open-note" class="note">As of {html.escape(default_sport_payload['as_of'])} | League tag = <code>{html.escape(default_sport_payload['label'])}</code></div>
        </div>

        <div class="card full">
          <div id="sport-periods-title" class="section-title">{html.escape(default_sport_payload['label'])} Recent Performance</div>
          <div id="sport-periods-note" class="note">Calendar-day windows ending on {html.escape(default_sport_payload['as_of'])}. Net and ROI use settled bets only.</div>
          <div id="sport-periods-table" class="scroll">{default_sport_payload['recent_periods_html']}</div>
        </div>

        <div class="card full">
          <div id="sport-calendar-title" class="section-title">{html.escape(default_sport_payload['label'])} Daily Net / Risk (Last 7 Days)</div>
          <div id="sport-calendar-content">{default_sport_payload['recent_calendar_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-streaks-title" class="section-title">{html.escape(default_sport_payload['label'])} Notable Streaks</div>
          <div id="sport-daily-streak-note" class="note">{html.escape(default_sport_payload['daily_current_text'])}</div>
          <div id="sport-streak-lines" style="margin-top: 8px; line-height: 1.6;">{default_sport_payload['streak_lines_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-highlights-title" class="section-title">{html.escape(default_sport_payload['label'])} Highlights</div>
          <div id="sport-highlights-risk" class="note">Avg Risk / Bet: {_fmt_money(default_sport_payload['averages']['avg_risk'])}</div>
          <div id="sport-highlights-odds" class="note">{_edge_note(default_sport_payload['averages'])}</div>
          <div style="margin-top: 8px; line-height: 1.6;">
            <div><strong>Best settled day:</strong> <span id="sport-best-day">{html.escape(default_sport_payload['best_day_text'])}</span></div>
            <div><strong>Worst settled day:</strong> <span id="sport-worst-day">{html.escape(default_sport_payload['worst_day_text'])}</span></div>
          </div>
        </div>

        <div class="card full">
          <div id="sport-cum-title" class="section-title">{html.escape(default_sport_payload['label'])} Cumulative Profit</div>
          <div id="chart-cum-sport" style="height: 320px;"></div>
        </div>

        <div class="card full">
          <div id="sport-recent-title" class="section-title">{html.escape(default_sport_payload['label'])} Last 30 Days Net (daily)</div>
          <div id="chart-recent-sport" style="height: 320px;"></div>
        </div>

        <div class="card full">
          <div id="sport-settled-title" class="section-title">{html.escape(default_sport_payload['label'])} Recently Settled Bets</div>
          <div class="note">Most recent settled bets, latest 25.</div>
          <div id="sport-settled-table" class="scroll">{default_sport_payload['recently_settled_html']}</div>
        </div>

        <div class="card full">
          <div id="sport-open-title" class="section-title">{html.escape(default_sport_payload['label'])} Open Bets</div>
          <div id="sport-open-note" class="note">Open bets tagged with League <code>{html.escape(default_sport_payload['label'])}</code>.</div>
          <div id="sport-open-table" class="scroll">{default_sport_payload['open_bets_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-by-book-title" class="section-title">{html.escape(default_sport_payload['label'])} By Book</div>
          <div id="sport-by-book-table" class="scroll">{default_sport_payload['by_book_html']}</div>
        </div>
        <div class="card half">
          <div id="sport-by-type-title" class="section-title">{html.escape(default_sport_payload['label'])} By Type</div>
          <div id="sport-by-type-table" class="scroll">{default_sport_payload['by_type_html']}</div>
        </div>

        <div class="card half">
          <div id="sport-wins-title" class="section-title">{html.escape(default_sport_payload['label'])} Biggest Wins (top 10)</div>
          <div id="sport-wins-table" class="scroll">{default_sport_payload['top_wins_html']}</div>
        </div>
        <div class="card half">
          <div id="sport-losses-title" class="section-title">{html.escape(default_sport_payload['label'])} Biggest Losses (top 10)</div>
          <div id="sport-losses-table" class="scroll">{default_sport_payload['top_losses_html']}</div>
        </div>

        <div class="card full">
          <div id="sport-longest-title" class="section-title">{html.escape(default_sport_payload['label'])} Longest Shots (top 10 winning odds)</div>
          <div id="sport-longest-table" class="scroll">{default_sport_payload['longest_shots_html']}</div>
        </div>
      </div>
    </section>
  </div>

<script>
  // Keep the layout control independent of chart loading and browser storage access.
  (() => {{
    const panel = document.getElementById('today-panel');
    const controls = panel.querySelector('.today-view');
    const buttons = panel.querySelectorAll('[data-today-view]');
    const setView = view => {{
      const selected = view === 'list' ? 'list' : 'cards';
      panel.dataset.view = selected;
      buttons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.todayView === selected)));
    }};
    try {{ setView(localStorage.getItem('bettingReportTodayView')); }} catch {{ setView('cards'); }}
    if (document.getElementById('today-bets')) controls.hidden = false;
    buttons.forEach(button => button.addEventListener('click', () => {{
      setView(button.dataset.todayView);
      try {{ localStorage.setItem('bettingReportTodayView', panel.dataset.view); }} catch {{ /* Layout still works without storage. */ }}
    }}));
    const filterBar = panel.querySelector('.today-filter-bar');
    if (!filterBar) return;
    const leagueButtons = panel.querySelectorAll('[data-today-league]');
    const statusButtons = panel.querySelectorAll('[data-today-status]');
    const groups = panel.querySelectorAll('[data-today-group]');
    const bets = Array.from(panel.querySelectorAll('.today-bet'));
    let league = '', status = '';
    const money = value => '$' + value.toLocaleString('en-US', {{minimumFractionDigits: 0, maximumFractionDigits: 2}});
    const applyFilters = () => {{
      let risk = 0, openRisk = 0, net = 0, wagers = 0, open = 0, visible = 0;
      bets.forEach(bet => {{
        const betStatus = bet.dataset.open === 'true' ? 'open' : 'closed';
        bet.hidden = Boolean((league && bet.dataset.league !== league) || (status && status !== betStatus));
        if (bet.hidden) return;
        visible++;
        const stake = Number(bet.dataset.risk);
        const count = Number(bet.dataset.count);
        risk += stake;
        net += Number(bet.dataset.net);
        wagers += count;
        if (bet.dataset.open === 'true') {{ openRisk += stake; open += count; }}
      }});
      leagueButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.todayLeague === league)));
      statusButtons.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.todayStatus === status)));
      groups.forEach(group => {{
        const count = Array.from(group.querySelectorAll('.today-bet')).filter(bet => !bet.hidden).length;
        group.hidden = count === 0;
        group.querySelector('.today-group-count').textContent = count;
      }});
      panel.querySelector('#today-filter-empty').hidden = visible > 0;
      panel.querySelector('[data-today-total="risk"] dd').textContent = money(risk);
      panel.querySelector('[data-today-total="open"] dd').textContent = money(openRisk);
      const netValue = panel.querySelector('[data-today-total="net"] dd');
      netValue.textContent = money(net);
      netValue.className = net > 0 ? 'positive' : net < 0 ? 'negative' : '';
      panel.querySelector('#today-wager-count').textContent = `${{wagers}} wagers · ${{open}} open · ${{wagers - open}} settled`;
      panel.querySelector('#today-filter-count').textContent = `${{league || 'All leagues'}} · ${{status || 'all statuses'}} · ${{visible}} of ${{bets.length}} bets`;
    }};
    leagueButtons.forEach(button => button.addEventListener('click', () => {{ league = button.dataset.todayLeague; applyFilters(); }}));
    statusButtons.forEach(button => button.addEventListener('click', () => {{ status = button.dataset.todayStatus; applyFilters(); }}));
    applyFilters();
    filterBar.hidden = false;
  }})();

  const series = {series_json};
  const recentSeries = {recent_series_json};
  const sportSummaries = {sport_summaries_json};
  const defaultSport = {json.dumps(default_sport)};

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

  function fmtMoney(value) {{
    const n = Number.isFinite(value) ? value : 0;
    return '$' + n.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
  }}
  function fmtPct(value) {{
    if (!Number.isFinite(value)) return '';
    return (value * 100).toFixed(2) + '%';
  }}
  function fmtEdge(value) {{
    if (!Number.isFinite(value)) return 'n/a';
    const pts = value * 100;
    return (pts > 0 ? '+' : '') + pts.toFixed(2) + ' pts';
  }}
  function resultFilterLabel(value) {{
    if (value === '__OPEN__') return 'Open';
    if (value === 'CO') return 'Cash Out';
    return value;
  }}
  function fmtNum(value) {{
    if (!Number.isFinite(value)) return '';
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }}
  function escapeHtml(value) {{
    return String(value || '')
      .replaceAll('&', '&amp;')
      .replaceAll('<', '&lt;')
      .replaceAll('>', '&gt;')
      .replaceAll('"', '&quot;')
      .replaceAll("'", '&#39;');
  }}
  function normalizeText(value) {{
    return String(value || '').trim().toLowerCase();
  }}
  function parseNum(row, key) {{
    const v = Number.parseFloat((row.dataset[key] || '').trim());
    return Number.isFinite(v) ? v : NaN;
  }}
  function parseOptionalNumberInput(input) {{
    const raw = (input?.value || '').trim();
    if (!raw) return null;
    const parsed = Number.parseFloat(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }}
  function matchesRange(value, minValue, maxValue) {{
    if (minValue == null && maxValue == null) return true;
    if (!Number.isFinite(value)) return false;
    if (minValue != null && value < minValue) return false;
    if (maxValue != null && value > maxValue) return false;
    return true;
  }}
  function setSignedClass(el, value) {{
    if (!el) return;
    el.classList.remove('positive', 'negative', 'good', 'bad');
    if (value > 0) el.classList.add('positive');
    else if (value < 0) el.classList.add('negative');
  }}
  function setText(id, value) {{
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  }}
  function setHtml(id, value) {{
    const el = document.getElementById(id);
    if (el) el.innerHTML = value;
  }}
  function buildSportCumulativeTraces(seriesData, label) {{
    const sportX = seriesData.map(d => d.date);
    const sportYCum = seriesData.map(d => d.cum_net);
    const sportYDaily = seriesData.map(d => d.net);
    const sportYCumRoi = seriesData.map(d => d.cum_roi == null ? null : d.cum_roi * 100.0);
    return [
      {{
        x: sportX,
        y: sportYDaily,
        type: 'bar',
        name: `${{label}} Daily Net`,
        marker: {{ color: sportYDaily.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
        opacity: 0.55,
        hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
      }},
      {{
        x: sportX,
        y: sportYCum,
        type: 'scatter',
        mode: 'lines+markers',
        name: `${{label}} Cumulative Net`,
        line: {{ color: '#60a5fa', width: 3 }},
        hovertemplate: '%{{x}}<br>Cumulative Net: %{{y:$,.2f}}<extra></extra>'
      }},
      {{
        x: sportX,
        y: sportYCumRoi,
        type: 'scatter',
        mode: 'lines',
        name: `${{label}} Cumulative ROI %`,
        yaxis: 'y2',
        line: {{ color: 'rgba(157,176,208,0.9)', width: 2, dash: 'dot' }},
        hovertemplate: '%{{x}}<br>Cumulative ROI: %{{y:.2f}}%<extra></extra>'
      }},
    ];
  }}
  function buildSportRecentTrace(seriesData) {{
    const sportRecentX = seriesData.map(d => d.date);
    const sportRecentY = seriesData.map(d => d.net);
    return {{
      x: sportRecentX,
      y: sportRecentY,
      type: 'bar',
      marker: {{ color: sportRecentY.map(v => v >= 0 ? '#34d399' : '#fb7185') }},
      hovertemplate: '%{{x}}<br>Net: %{{y:$,.2f}}<extra></extra>'
    }};
  }}
  function renderSportTab(sportKey) {{
    const sport = sportSummaries[sportKey] || sportSummaries[defaultSport];
    if (!sport) return;

    setText('sport-kpi-total-label', `${{sport.label}} Total Bets`);
    setText('sport-kpi-total-value', String(sport.counts.total));
    setText('sport-kpi-total-note', `Resolved: ${{sport.counts.resolved}} | Open: ${{sport.counts.open}} | Push: ${{sport.counts.pushes}} | Cash out: ${{sport.counts.cash_outs}}`);

    setText('sport-kpi-net-label', `${{sport.label}} Net Profit`);
    setText('sport-kpi-net-value', fmtMoney(sport.totals.net));
    setText('sport-kpi-net-note', `Settled ROI: ${{fmtPct(sport.totals.roi)}}`);
    setSignedClass(document.getElementById('sport-kpi-net-value'), sport.totals.net);

    setText('sport-kpi-win-label', `${{sport.label}} Win Rate (W/L)`);
    setText('sport-kpi-win-value', fmtPct(sport.averages.win_rate));
    setText('sport-kpi-win-note', `W: ${{sport.counts.wins}} | L: ${{sport.counts.losses}} | Edge vs implied: ${{fmtEdge(sport.averages.edge)}}`);

    setText('sport-kpi-open-label', `${{sport.label}} Open Exposure`);
    setText('sport-kpi-open-value', fmtMoney(sport.open_exposure));
    setHtml('sport-kpi-open-note', `As of ${{escapeHtml(sport.as_of)}} | League tag = <code>${{escapeHtml(sport.label)}}</code>`);

    setText('sport-periods-title', `${{sport.label}} Recent Performance`);
    setText('sport-periods-note', `Calendar-day windows ending on ${{sport.as_of}}. Net and ROI use settled bets only.`);
    setHtml('sport-periods-table', sport.recent_periods_html);

    setText('sport-calendar-title', `${{sport.label}} Daily Net / Risk (Last 7 Days)`);
    setHtml('sport-calendar-content', sport.recent_calendar_html);

    setText('sport-streaks-title', `${{sport.label}} Notable Streaks`);
    setText('sport-daily-streak-note', sport.daily_current_text);
    setHtml('sport-streak-lines', sport.streak_lines_html);

    setText('sport-highlights-title', `${{sport.label}} Highlights`);
    setText('sport-highlights-risk', `Avg Risk / Bet: ${{fmtMoney(sport.averages.avg_risk)}}`);
    setText('sport-highlights-odds', `Win ${{fmtPct(sport.averages.win_rate) || 'n/a'}} vs implied ${{fmtPct(sport.averages.avg_implied_prob) || 'n/a'}} (edge ${{fmtEdge(sport.averages.edge)}})`);
    setText('sport-best-day', sport.best_day_text);
    setText('sport-worst-day', sport.worst_day_text);

    setText('sport-cum-title', `${{sport.label}} Cumulative Profit`);
    setText('sport-recent-title', `${{sport.label}} Last 30 Days Net (daily)`);
    setText('sport-settled-title', `${{sport.label}} Recently Settled Bets`);
    setHtml('sport-settled-table', sport.recently_settled_html);

    setText('sport-open-title', `${{sport.label}} Open Bets`);
    setHtml('sport-open-note', `Open bets tagged with League <code>${{escapeHtml(sport.label)}}</code>.`);
    setHtml('sport-open-table', sport.open_bets_html);

    setText('sport-by-book-title', `${{sport.label}} By Book`);
    setHtml('sport-by-book-table', sport.by_book_html);
    setText('sport-by-type-title', `${{sport.label}} By Type`);
    setHtml('sport-by-type-table', sport.by_type_html);

    setText('sport-wins-title', `${{sport.label}} Biggest Wins (top 10)`);
    setHtml('sport-wins-table', sport.top_wins_html);
    setText('sport-losses-title', `${{sport.label}} Biggest Losses (top 10)`);
    setHtml('sport-losses-table', sport.top_losses_html);
    setText('sport-longest-title', `${{sport.label}} Longest Shots (top 10 winning odds)`);
    setHtml('sport-longest-table', sport.longest_shots_html);

    const sportCumChart = document.getElementById('chart-cum-sport');
    const sportRecentChart = document.getElementById('chart-recent-sport');
    if (sportCumChart) {{
      Plotly.react(sportCumChart, buildSportCumulativeTraces(sport.series, sport.label), layout, {{displayModeBar: false, responsive: true}});
    }}
    if (sportRecentChart) {{
      Plotly.react(sportRecentChart, [buildSportRecentTrace(sport.recent_daily_series)], recentLayout, {{displayModeBar: false, responsive: true}});
    }}

    const sportSelect = document.getElementById('sport-select');
    if (sportSelect && sportSelect.value !== sportKey) {{
      sportSelect.value = sportKey;
    }}
    localStorage.setItem('bettingReportSelectedSport', sportKey);
  }}

  const allBetsTable = document.getElementById('all-bets-table');
  const allBetsTbody = allBetsTable ? allBetsTable.querySelector('tbody') : null;
  const allBetsSortButtons = allBetsTable ? Array.from(allBetsTable.querySelectorAll('.sort-btn')) : [];
  const allBetsRows = allBetsTbody ? Array.from(allBetsTbody.querySelectorAll('tr.all-bets-row')) : [];
  const allBetsFilterInputs = {{
    pick: document.getElementById('all-bets-pick-filter'),
    dateFrom: document.getElementById('all-bets-date-from'),
    dateTo: document.getElementById('all-bets-date-to'),
    league: document.getElementById('all-bets-league-filter'),
    book: document.getElementById('all-bets-book-filter'),
    type: document.getElementById('all-bets-type-filter'),
    result: document.getElementById('all-bets-result-filter'),
    oddsMin: document.getElementById('all-bets-odds-min'),
    oddsMax: document.getElementById('all-bets-odds-max'),
    riskMin: document.getElementById('all-bets-risk-min'),
    riskMax: document.getElementById('all-bets-risk-max'),
    netMin: document.getElementById('all-bets-net-min'),
    netMax: document.getElementById('all-bets-net-max'),
  }};
  const allBetsClear = document.getElementById('all-bets-clear');
  const allBetsState = {{ key: 'date', dir: 'desc', type: 'text' }};

  function uniqueValuesFor(key) {{
    const values = new Set();
    allBetsRows.forEach((row) => {{
      const value = (row.dataset[key] || '').trim();
      if (key === 'result' && !value) {{
        values.add('__OPEN__');
      }} else if (value) {{
        values.add(value);
      }}
    }});
    const sorted = Array.from(values);
    sorted.sort((a, b) => {{
      if (a === '__OPEN__') return 1;
      if (b === '__OPEN__') return -1;
      return a.localeCompare(b, undefined, {{ numeric: true, sensitivity: 'base' }});
    }});
    return sorted;
  }}
  function populateSelectOptions(selectEl, values, placeholder) {{
    if (!selectEl) return;
    const currentValue = selectEl.value;
    const options = [`<option value="">${{escapeHtml(placeholder)}}</option>`];
    values.forEach((value) => {{
      const label = resultFilterLabel(value);
      const selected = value === currentValue ? ' selected' : '';
      options.push(`<option value="${{escapeHtml(value)}}"${{selected}}>${{escapeHtml(label)}}</option>`);
    }});
    selectEl.innerHTML = options.join('');
  }}
  function initAllBetsFilters() {{
    populateSelectOptions(allBetsFilterInputs.league, uniqueValuesFor('league'), 'All leagues');
    populateSelectOptions(allBetsFilterInputs.book, uniqueValuesFor('book'), 'All books');
    populateSelectOptions(allBetsFilterInputs.type, uniqueValuesFor('type'), 'All types');
    populateSelectOptions(allBetsFilterInputs.result, uniqueValuesFor('result'), 'All results');
  }}

  function updateAllBetsSortButtons() {{
    allBetsSortButtons.forEach((btn) => {{
      const active = btn.dataset.key === allBetsState.key;
      btn.classList.toggle('active', active);
      let label = btn.textContent.replace(' ↑', '').replace(' ↓', '');
      if (active) {{
        label += allBetsState.dir === 'asc' ? ' ↑' : ' ↓';
      }}
      btn.textContent = label;
    }});
  }}

  function compareAllBetsRows(a, b) {{
    const key = allBetsState.key;
    const dirMul = allBetsState.dir === 'asc' ? 1 : -1;
    if (allBetsState.type === 'number') {{
      const av = parseNum(a, key);
      const bv = parseNum(b, key);
      const an = Number.isFinite(av) ? av : Number.NEGATIVE_INFINITY;
      const bn = Number.isFinite(bv) ? bv : Number.NEGATIVE_INFINITY;
      if (an < bn) return -1 * dirMul;
      if (an > bn) return 1 * dirMul;
      return 0;
    }}
    const at = (a.dataset[key] || '').toLowerCase();
    const bt = (b.dataset[key] || '').toLowerCase();
    return at.localeCompare(bt, undefined, {{ numeric: true, sensitivity: 'base' }}) * dirMul;
  }}

  function updateAllBetsTotals(visibleRows) {{
    const countEl = document.getElementById('all-bets-count');
    const riskEl = document.getElementById('all-bets-risk');
    const netEl = document.getElementById('all-bets-net');
    const roiEl = document.getElementById('all-bets-roi');
    const wloEl = document.getElementById('all-bets-wlo');
    if (!countEl || !riskEl || !netEl || !roiEl || !wloEl) return;

    let risk = 0;
    let settledRisk = 0;
    let net = 0;
    let wins = 0;
    let losses = 0;
    let open = 0;
    visibleRows.forEach((row) => {{
      const result = (row.dataset.result || '').toUpperCase();
      const r = parseNum(row, 'risk');
      const n = parseNum(row, 'net');
      if (Number.isFinite(r)) risk += r;
      if (Number.isFinite(n)) {{
        net += n;
        if (Number.isFinite(r)) settledRisk += r;
      }}
      if (result === 'W') wins += 1;
      else if (result === 'L') losses += 1;
      else if (!result) open += 1;
    }});
    const roi = settledRisk ? (net / settledRisk) : NaN;
    countEl.textContent = String(visibleRows.length);
    riskEl.textContent = fmtMoney(risk);
    netEl.textContent = fmtMoney(net);
    roiEl.textContent = Number.isFinite(roi) ? fmtPct(roi) : 'n/a';
    wloEl.textContent = `${{wins}}-${{losses}}-${{open}}`;
    setSignedClass(netEl, net);
    setSignedClass(roiEl, roi);
  }}

  function rowMatchesAllBetsFilters(row) {{
    const pickQuery = normalizeText(allBetsFilterInputs.pick?.value);
    const dateFrom = (allBetsFilterInputs.dateFrom?.value || '').trim();
    const dateTo = (allBetsFilterInputs.dateTo?.value || '').trim();
    const leagueFilter = normalizeText(allBetsFilterInputs.league?.value);
    const bookFilter = normalizeText(allBetsFilterInputs.book?.value);
    const typeFilter = normalizeText(allBetsFilterInputs.type?.value);
    const resultFilter = (allBetsFilterInputs.result?.value || '').trim();
    const oddsMin = parseOptionalNumberInput(allBetsFilterInputs.oddsMin);
    const oddsMax = parseOptionalNumberInput(allBetsFilterInputs.oddsMax);
    const riskMin = parseOptionalNumberInput(allBetsFilterInputs.riskMin);
    const riskMax = parseOptionalNumberInput(allBetsFilterInputs.riskMax);
    const netMin = parseOptionalNumberInput(allBetsFilterInputs.netMin);
    const netMax = parseOptionalNumberInput(allBetsFilterInputs.netMax);

    if (pickQuery && !normalizeText(row.dataset.pick).includes(pickQuery)) return false;

    const rowDate = (row.dataset.date || '').trim();
    if (dateFrom && (!rowDate || rowDate < dateFrom)) return false;
    if (dateTo && (!rowDate || rowDate > dateTo)) return false;

    if (leagueFilter && normalizeText(row.dataset.league) !== leagueFilter) return false;
    if (bookFilter && normalizeText(row.dataset.book) !== bookFilter) return false;
    if (typeFilter && normalizeText(row.dataset.type) !== typeFilter) return false;

    const rowResult = (row.dataset.result || '').trim();
    if (resultFilter) {{
      if (resultFilter === '__OPEN__') {{
        if (rowResult) return false;
      }} else if (rowResult !== resultFilter) {{
        return false;
      }}
    }}

    if (!matchesRange(parseNum(row, 'odds'), oddsMin, oddsMax)) return false;
    if (!matchesRange(parseNum(row, 'risk'), riskMin, riskMax)) return false;
    if (!matchesRange(parseNum(row, 'net'), netMin, netMax)) return false;
    return true;
  }}

  function applyAllBetsView() {{
    if (!allBetsTbody) return;
    const visibleRows = [];
    const hiddenRows = [];
    allBetsRows.forEach((row) => {{
      const matches = rowMatchesAllBetsFilters(row);
      row.style.display = matches ? '' : 'none';
      if (matches) visibleRows.push(row);
      else hiddenRows.push(row);
    }});

    visibleRows.sort(compareAllBetsRows);
    [...visibleRows, ...hiddenRows].forEach((row) => allBetsTbody.appendChild(row));
    updateAllBetsSortButtons();
    updateAllBetsTotals(visibleRows);
  }}

  Object.values(allBetsFilterInputs).forEach((input) => {{
    if (!input) return;
    const eventName = input.tagName === 'SELECT' ? 'change' : 'input';
    input.addEventListener(eventName, applyAllBetsView);
  }});
  if (allBetsClear) {{
    allBetsClear.addEventListener('click', () => {{
      Object.values(allBetsFilterInputs).forEach((input) => {{
        if (input) input.value = '';
      }});
      applyAllBetsView();
    }});
  }}
  allBetsSortButtons.forEach((btn) => {{
    btn.addEventListener('click', () => {{
      const key = btn.dataset.key || 'date';
      const type = btn.dataset.type || 'text';
      if (allBetsState.key === key) {{
        allBetsState.dir = allBetsState.dir === 'asc' ? 'desc' : 'asc';
      }} else {{
        allBetsState.key = key;
        allBetsState.type = type;
        allBetsState.dir = key === 'date' ? 'desc' : 'asc';
      }}
      applyAllBetsView();
    }});
  }});
  initAllBetsFilters();
  applyAllBetsView();

  const sportSelect = document.getElementById('sport-select');
  if (sportSelect) {{
    sportSelect.addEventListener('change', () => renderSportTab(sportSelect.value || defaultSport));
  }}
  const savedSport = localStorage.getItem('bettingReportSelectedSport');
  renderSportTab(savedSport && sportSummaries[savedSport] ? savedSport : defaultSport);

  const tabButtons = Array.from(document.querySelectorAll('.tab-btn'));
  const tabPanels = Array.from(document.querySelectorAll('.tab-panel'));
  function resizeCharts() {{
    const recentChart = document.getElementById('chart-recent');
    const cumulativeChart = document.getElementById('chart-cum');
    const sportRecentChart = document.getElementById('chart-recent-sport');
    const sportCumulativeChart = document.getElementById('chart-cum-sport');
    if (recentChart) Plotly.Plots.resize(recentChart);
    if (cumulativeChart) Plotly.Plots.resize(cumulativeChart);
    if (sportRecentChart) Plotly.Plots.resize(sportRecentChart);
    if (sportCumulativeChart) Plotly.Plots.resize(sportCumulativeChart);
  }}
  function activateTab(tabName) {{
    tabButtons.forEach((btn) => btn.classList.toggle('active', btn.dataset.tab === tabName));
    tabPanels.forEach((panel) => panel.classList.toggle('active', panel.id === `tab-${{tabName}}`));
    localStorage.setItem('bettingReportActiveTab', tabName);
    requestAnimationFrame(resizeCharts);
  }}
  tabButtons.forEach((btn) => btn.addEventListener('click', () => activateTab(btn.dataset.tab)));
  const savedTab = localStorage.getItem('bettingReportActiveTab');
  if (savedTab === 'history' || savedTab === 'home' || savedTab === 'sports' || savedTab === 'all-bets') {{
    activateTab(savedTab);
  }} else if (savedTab === 'ncaab') {{
    activateTab('sports');
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
    league_groups: Dict[str, List[BetRow]] = {}
    for bet in bets:
        league_key = bet.league.strip().upper()
        if not league_key:
            continue
        league_groups.setdefault(league_key, []).append(bet)
    league_summaries = {league: summarize(rows) for league, rows in sorted(league_groups.items())}
    default_sport = "NCAAB" if "NCAAB" in league_summaries else (next(iter(league_summaries.keys()), "NCAAB"))

    title = "G's Betting Report"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    report_root = os.path.dirname(script_dir)
    logos_dir = os.path.join(report_root, "logos")
    available_logo_files: Optional[set[str]] = None
    if os.path.isdir(logos_dir):
        available_logo_files = {
            name.lower() for name in os.listdir(logos_dir) if os.path.isfile(os.path.join(logos_dir, name))
        }

    out_dir = os.path.dirname(os.path.abspath(args.output))
    logo_base_href = "logos"
    if os.path.isdir(logos_dir):
        logo_base_href = os.path.relpath(logos_dir, out_dir).replace(os.sep, "/")

    html_report = build_html_report(
        summary,
        title=title,
        league_summaries=league_summaries,
        default_sport=default_sport,
        logo_base_href=logo_base_href,
        available_logo_files=available_logo_files,
    )

    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html_report)

    print(f"Wrote: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
