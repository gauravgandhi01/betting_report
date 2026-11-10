# Betting report tools

## Live scores CLI

Requires Python 3.9+ and internet access. No additional packages or API key are required.

Run from the repository root:

```sh
# Live scores and confirmed upcoming countdowns for today's bets.
python3 betting_analysis/live_scores.py

# Refresh every 30 seconds. Stop with Ctrl+C.
python3 betting_analysis/live_scores.py --watch

# Refresh every 15 seconds, showing only open bets on live games.
python3 betting_analysis/live_scores.py --watch 15 --open-only

# Choose a date and one or more leagues.
python3 betting_analysis/live_scores.py --date 2026-11-09 --league NCAAB --league NHL

# Machine-readable snapshot (watch mode emits newline-delimited JSON).
python3 betting_analysis/live_scores.py --json
```

The default input is `betting_analysis/bets.csv`, resolved relative to the script,
so the command also works from other directories. Watch mode rereads it each
refresh and picks up changes made by the existing sheet sync. It does not sync the
sheet itself. `--input PATH` selects another CSV. The CSV must have the same
columns as the report input: `D,Pick,Odds,Risk,Wins,R,Net,Book,League,Type`.
Month/day dates begin in 2025, matching the report's cron configuration; each
month/day rollover advances the year. Use `--start-year YEAR` for another dataset.
The default date and displayed start times use America/New_York.

The CLI reuses the report's college ESPN team IDs and pro-team abbreviation
aliases for NHL, NBA, NFL, MLB, NCAAB, and NCAAF. It fetches each needed league's
scoreboard per refresh and groups your bets by game. The terminal shows a sport
emoji, the live game clock/status, and a table with each team's total score.
The leading team's margin and combined points appear beside the scoreboard.
`Total pace` appears only for games with a bet marked `Total` in the CSV.
It projects the final regulation total as combined points divided by
minutes played, multiplied by regulation game length. It uses the game clock,
including halftime/intermission, and shows `-` before any time has elapsed,
when clock/scores are missing, during overtime, or for baseball.
Each bet shows only its pick in bright cyan in the terminal. Piped output
is plain text; setting `NO_COLOR` also disables color. Game clocks and upcoming
countdowns are green above 15 minutes remaining, yellow from 5 to 15 minutes,
and red at 5 minutes or less. Live colors use total game time remaining across
periods; overtime uses the current overtime clock. Unknown clocks stay plain.
Full scoreboards appear for
games currently in progress; halftime and intermission count as live. Confirmed
upcoming games on the selected slate appear as one line per game with the matchup,
time until start, and your picks. Countdowns refresh in watch mode. A countdown
requires a unique game match, an event ID, a scheduled status, and a future start
time; postponed, delayed, canceled, and past-due scheduled games are omitted.
The CLI does not grade
bets or track individual player statistics. `--open-only` additionally filters
out bets with recorded results. `--live-only` hides upcoming countdowns.

Picks with an explicit `A/B` matchup match both teams. A single-team pick must
match exactly one game on the selected slate. Player-only picks without a team,
parlays, missing team mappings, and ambiguous games are omitted from the terminal.
The CLI does not guess their game. JSON snapshots retain mapping diagnostics and
game metadata. Duplicate bets remain visible under the same game. ESPN determines
whether a game is live, postponed, or final.

`--watch` accepts intervals of at least 5 seconds. `--timeout SECONDS` controls
the timeout for each HTTP request (default: 10). Network errors appear in the
output alongside any successful scores; a one-shot run exits with status 1 if a
scoreboard request fails, or if the CSV cannot be read. Unmatched bets and empty
filters alone are successful runs. No scores are cached between refreshes.
The tool only reads your bets and fetches ESPN data; it does not modify the CSV,
HTML report, or cron configuration.

```sh
python3 betting_analysis/live_scores.py --help
python3 -m unittest -q
```
