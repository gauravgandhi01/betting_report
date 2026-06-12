#!/bin/zsh

set -euo pipefail

ROOT_DIR="/Users/ggandhi001/nhl_tools/betting_report"
ANALYSIS_DIR="$ROOT_DIR/betting_analysis"
LOG_FILE="$ANALYSIS_DIR/cron_log.txt"
LOCK_DIR="/tmp/betting_report_cron.lock"
HOME_DIR="/Users/ggandhi001"

PYTHON_BIN="/usr/local/bin/python3"
GIT_BIN="/usr/bin/git"
DATE_BIN="/bin/date"
SSH_BIN="/usr/bin/ssh"

SYNC_URL="https://docs.google.com/spreadsheets/d/e/2PACX-1vRWq2b3UQWrMAyMVpvt2ZIfzbIcvF42SOAvx1Q7FtkT3i105w46_K_VoSy_OyBJ1bqs-Ow7n71xlIsa/pub?gid=383914663&single=true&output=csv"
MAIN_BRANCH="main"
SSH_KEY_FILE="$HOME_DIR/.ssh/id_ed25519_github"
SSH_REMOTE_URL="git@github.com:gauravgandhi01/betting_report.git"

export HOME="$HOME_DIR"
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="$SSH_BIN -i $SSH_KEY_FILE -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new"

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

ensure_git_ready() {
  cd "$ROOT_DIR" || return $?

  if [[ ! -r "$SSH_KEY_FILE" ]]; then
    echo "SSH key not found: $SSH_KEY_FILE"
    return 1
  fi

  local current_branch remote_url
  current_branch="$("$GIT_BIN" branch --show-current)"
  if [[ "$current_branch" != "$MAIN_BRANCH" ]]; then
    echo "Refusing to sync from branch '${current_branch:-detached HEAD}'"
    return 1
  fi

  if ! "$GIT_BIN" diff --quiet || ! "$GIT_BIN" diff --cached --quiet; then
    echo "Working tree is dirty before cron run; skipping git sync"
    return 1
  fi

  remote_url="$("$GIT_BIN" remote get-url origin)"
  if [[ "$remote_url" != "$SSH_REMOTE_URL" ]]; then
    echo "Updating origin remote to SSH"
    "$GIT_BIN" remote set-url origin "$SSH_REMOTE_URL" || return $?
  fi

  "$GIT_BIN" fetch origin "$MAIN_BRANCH" || return $?
  "$GIT_BIN" pull --rebase origin "$MAIN_BRANCH" || return $?
}

push_if_needed() {
  local ahead_count
  ahead_count="$("$GIT_BIN" rev-list --count "origin/$MAIN_BRANCH..HEAD")"
  if [[ "$ahead_count" == "0" ]]; then
    echo "Nothing to push"
    return 0
  fi

  if "$GIT_BIN" push origin "$MAIN_BRANCH"; then
    return 0
  fi

  echo "Push failed; retrying after rebase"
  "$GIT_BIN" pull --rebase origin "$MAIN_BRANCH" || return $?
  "$GIT_BIN" push origin "$MAIN_BRANCH"
}

run_job() {
  ensure_git_ready || return $?

  "$PYTHON_BIN" "$ANALYSIS_DIR/generate_bet_report.py" \
    --input "$ANALYSIS_DIR/bets.csv" \
    --output "$ROOT_DIR/index.html" \
    --start-year 2025 \
    --sync-url "$SYNC_URL" || return $?

  cd "$ROOT_DIR" || return $?
  "$GIT_BIN" add -A || return $?

  if "$GIT_BIN" diff --cached --quiet; then
    echo "No changes to commit"
  else
    "$GIT_BIN" commit -m "Auto-update: betting report $($DATE_BIN -Iminutes)" || return $?
  fi

  push_if_needed || return $?
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
