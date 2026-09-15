# Player vs Player Excel structure

The canonical workbook is `exports/player_vs_player.xlsx`. Its summary sheet is
named `Player_vs_Player` with table name `PlayerVsPlayer_Table`; when at least
one real game exists, a second `PvP_Game_History` sheet preserves the
`GameRecord` timeline. It contains materialized values only: no formulas,
macros, external links, or hidden helper sheets.

## Summary column order

| Column | Header | Type / display |
| ---: | --- | --- |
| A | Our Team ID | text |
| B | Our Team | text |
| C | Player ID | text |
| D | Player | text |
| E | Player Current SL | integer or `No data` |
| F | Opponent Team ID | text |
| G | Opponent Team | text |
| H | Opponent ID | text |
| I | Opponent | text |
| J | Opponent Current SL | integer or `No data` |
| K | Format | text |
| L | Session | text |
| M | Evidence | DIRECT / INDIRECT / UNKNOWN |
| N | Direct Matches | Stage 1 distinct authoritative match count |
| O | Observed Win Rate | percentage or `No data` |
| P | Recognized Games | `PlayerVsPlayerSummary.total_games` |
| Q | Game Wins | integer |
| R | Game Losses | integer |
| S | Avg SL Delta | fixed decimal or `No data` |
| T | History Reliability (Games) | `summary.reliability`, percentage |
| U | Last Recorded Skill Probability | percentage or `No data` |
| V | Modeled Win Probability | percentage or `No data` |
| W | Model Validation Status | text |
| X | Avg Innings | `No data — unavailable upstream` |
| Y | Avg Defense | `No data — unavailable per opponent` |
| Z | Break/Run Rate | `No data — not attributable per opponent` |
| AA | Pair Trend | up / down / stable / no data |
| AB | Recent Pair Trend | up / down / stable / no data |
| AC | Volatility | `No data — not produced by this analytics contract` |
| AD | Forward Pair Projection | percentage or `No data` |
| AE | Projection Source | same source/status as modeled probability |
| AF | Data Notes | semicolon-separated deterministic warnings |

`Direct Matches` and `Recognized Games` are deliberately separate. Stage 1
counts distinct authoritative team matches for evidence classification;
`PlayerVsPlayerSummary` counts recognized exact-pair game rows, and one team
match can contain more than one legitimate game.

## Game-history sheet

`PvP_Game_History` contains Pair Key, Player ID, Opponent ID, Match ID, Match
Date, Result, Own Posted SL, Opponent Posted SL, Points Earned, 9-Ball Balls,
Format, and Session. Rows follow the parent summary order and then the
analytics-provided chronological `games` order. Missing dates remain `No data`;
they are never generated from insertion time.

The detail sheet is omitted when no real game exists. A header-only history
sheet would imply a delivered dataset where there is none.

## Row and sheet rules

Summary rows follow the canonical structural ordering in
`player_vs_player_exports.md`; score/probability values never reorder them.
Every feasible pair has exactly one summary row, including UNKNOWN. External
IDs are stored as text so Excel cannot convert them to scientific notation or
dates.

Freeze panes at `A2`, enable the table filter over real data rows, and use fixed
documented widths. Header style, row banding, and evidence-label fills are
constant. UNKNOWN uses a neutral gray fill, but the text label remains the
authority. No formula or conditional-format rule may substitute for a value
from the export document.

Probabilities use `0.0%` and skill delta uses `0.000`. Dates retain delivered
text unless a separately audited normalizer exists. Workbook core properties
use the run timestamp, not the build machine's local clock, to preserve
deterministic output.

If the export document has zero feasible pairs, the builder does not create a
header-only `Player_vs_Player` sheet. It returns an explicit no-data result to
`demo.py`, which records the reason in the manifest.

## Parity checks

Before release, load the workbook with openpyxl and compare each materialized
summary and game row with the JSON/HTML source document by stable pair key.
Values are compared before display rounding. The workbook must open without a
repair prompt and contain no formulas, VBA, external links, hidden sheets, or
duplicate pair keys.

