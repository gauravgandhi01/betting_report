#!/bin/zsh

set -euo pipefail

ROOT_DIR="/Users/ggandhi001/nhl_tools/betting_report"
ANALYSIS_DIR="$ROOT_DIR/betting_analysis"
LOG_FILE="$ANALYSIS_DIR/cron_log.txt"
LOCK_DIR="/tmp/betting_report_cron.lock"

PYTHON_BIN="/usr/local/bin/python3"
GIT_BIN="/usr/bin/git"
DATE_BIN="/bin/date"

SYNC_URL="https://docs.google.com/spreadsheets/d/e/2PACX-1vRWq2b3UQWrMAyMVpvt2ZIfzbIcvF42SOAvx1Q7FtkT3i105w46_K_VoSy_OyBJ1bqs-Ow7n71xlIsa/pub?gid=383914663&single=true&output=csv"

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "python3 not found" >> "$LOG_FILE"
  exit 1
fi

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "=== $($DATE_BIN -Iseconds) SKIP betting (already running) ===" >> "$LOG_FILE"
  exit 0
fi

cleanup() {
  rmdir "$LOCK_DIR" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

run_job() {
  "$PYTHON_BIN" "$ANALYSIS_DIR/generate_bet_report.py" \
    --input "$ANALYSIS_DIR/bets.csv" \
    --output "$ROOT_DIR/index.html" \
    --start-year 2025 \
    --sync-url "$SYNC_URL"

  cd "$ROOT_DIR"
  "$GIT_BIN" add -A

  if "$GIT_BIN" diff --cached --quiet; then
    echo "No changes to commit"
  else
    "$GIT_BIN" commit -m "Auto-update: betting report $($DATE_BIN -Iminutes)"
    "$GIT_BIN" push
  fi
}

{
  echo "=== $($DATE_BIN -Iseconds) START betting ==="
  if run_job; then
    rc=0
  else
    rc=$?
  fi
  echo "=== $($DATE_BIN -Iseconds) END betting rc=$rc ==="
  exit "$rc"
} >> "$LOG_FILE" 2>&1
