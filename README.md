# Betting report tools

Generate the static betting dashboard in `index.html`, sync the local CSV from a
published Google Sheet, and follow matched games with the terminal live-score tool.
Requires Python 3.9+ and internet access for ESPN and sheet downloads. No additional
Python packages or API key are required. The dashboard loads Plotly from a CDN.

## Generate the report

Run from the repository root with explicit paths:

```sh
python3 betting_analysis/generate_bet_report.py \
  --input betting_analysis/bets.csv \
  --output index.html \
  --start-year 2025
```

Open `index.html` in a browser to review the result. Edit the generator rather
than the generated HTML so changes survive the next refresh. The generator's
historical defaults (`bets.csv` and `../index.html`) are relative to the working
directory; the command above avoids that ambiguity.

To download the sheet before generating, add `--sync-url 'PUBLISHED_CSV_URL'`.
This replaces the local input CSV. To sync only:

```sh
python3 betting_analysis/sync_bets_from_sheet.py \
  --url 'PUBLISHED_CSV_URL' --output betting_analysis/bets.csv
```

The CSV columns are `D,Pick,Odds,Risk,Wins,R,Net,Book,League,Type`. Dates use
month/day, starting in `--start-year`; each year rollover advances the year.
Blank results are open bets. The HTML report currently includes only bets dated
January 1, 2026 onward. `bets.csv` and the cron log are intentionally ignored by Git.

## Game cards and ESPN data

Today and Upcoming cards share the same renderer. Sport logos appear as faint
watermarks; team and sportsbook logos remain in the foreground. Parlays and round
robins share a section but retain distinct compact labels and full pick details.

A uniquely matched ESPN game supplies its start time, arena and broadcast. The
footer shows only the first broadcast, using a logo when available. Scheduled time
badges are colored by Eastern start hour; live and final badges have separate
status colors. Hover or focus the small info icon for venue and pregame spread /
total with juice when supplied. Betting lines are omitted for live/final games.

The HTML is a snapshot made during generation. Refreshing the browser does not
fetch a new ESPN slate; regenerate the report to update game data. Missing or
ambiguous team mappings, missing ESPN IDs, unavailable games and request failures
are reported in the generator's output. Player-only and multi-game picks may not
have a single game to attach.

## Logo and team maintenance

Mappings live in `betting_analysis/generate_bet_report.py`:

- Add college abbreviations, school slug and display name to `NCAA_LOGO_TEAMS` or
  `NCAA_GAP_LOGO_TEAMS`, and its ESPN ID to `NCAA_ESPN_IDS` for game matching.
- College logos normally use ESPN artwork. For custom artwork, put the file in
  `logos/teams/ncaa/` and register its slug/path in `NCAA_LOCAL_LOGOS`. Keep the
  local filename stem aligned with the school slug so the local-logo ID lookup
  works. Dayton and Utah Tech are examples.
- Put network artwork in `logos/networks/` and register the broadcast name and
  exact filename in `NETWORK_LOGO_FILES`. Names match without case sensitivity;
  file paths preserve case for hosting. Missing files fall back to network text.
- `START_HOUR_COLORS` controls scheduled badge colors. Network CSS uses fixed
  footer dimensions; ESPN+ has extra scaling for image padding and a color filter
  that makes its dark E white while retaining the yellow plus.

`team-logos/` and `logos/sdv-assets/` are ignored source asset directories, not
runtime dependencies. Keep assets used by the site under `logos/`.

## Automation and checks

`betting_analysis/run_betting_cron.sh` is the existing machine-specific sync,
generate, commit and push job. Its paths, Git remote and SSH configuration are
local to the configured machine. It uses a lock directory to prevent overlapping
runs and skips tracked working-tree changes before syncing. For local preview,
use the generation command above; the cron script also changes Git state.

```sh
python3 -m unittest -q
python3 betting_analysis/generate_bet_report.py --help
python3 betting_analysis/live_scores.py --help
```

Tests use fixtures and injected fetch functions; they do not require live ESPN
requests. `test_generate_bet_report.py` covers rendering and game matching;
`test_live_scores.py` covers terminal scores and countdowns.

## Live scores CLI

Run from the repository root:

```sh
# Live scores and confirmed upcoming countdowns for today's bets.
python3 betting_analysis/live_scores.py

# Refresh every 30 seconds. Stop with Ctrl+C.
python3 betting_analysis/live_scores.py --watch

# Refresh every 15 seconds. Bets with a recorded result are omitted.
python3 betting_analysis/live_scores.py --watch 15

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
Live games are ordered by time remaining, closest to the end first. Upcoming
games follow, soonest start first. The broadcast is shown on that line when
ESPN provides one.
`Total pace` appears only for games with a bet marked `Total` in the CSV.
It projects the final regulation total as combined points divided by
minutes played, multiplied by regulation game length. It uses the game clock,
including halftime/intermission, and shows `-` before any time has elapsed,
when clock/scores are missing, during overtime, or for baseball.
Each live bet shows only its pick in bright cyan. Upcoming picks also show
the risk amount. Piped output
is plain text; setting `NO_COLOR` also disables color. Game clocks and upcoming
countdowns are green above 15 minutes remaining, yellow from 5 to 15 minutes,
and red at 5 minutes or less. Live colors use total game time remaining across
periods; overtime uses the current overtime clock. Unknown clocks stay plain.
Full scoreboards appear for
games currently in progress; halftime and intermission count as live. Confirmed
upcoming games on the selected slate appear as one line per game with the matchup,
time until start, and each open pick with its risk. Countdowns refresh in watch mode. A countdown
requires a unique game match, an event ID, a scheduled status, and a future start
time; postponed, delayed, canceled, and past-due scheduled games are omitted.
The CLI does not grade
bets or track individual player statistics. Bets with a recorded result are
omitted, including on the next `--watch` refresh after the sheet grades them.
`--open-only` selects that same set and is the default. `--live-only` hides
upcoming countdowns.

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
