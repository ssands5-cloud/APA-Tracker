# Captain's Edge Summary

A real rollup over data this project has already computed. No new
database query, no new per-pairing or per-lineup computation: every
number here already exists somewhere in the real lineup document
`scripts.build_lineups` writes. This module only selects and ranks.

```
analytics/captains_edge_summary.py   the four real selection/ranking functions
ui/export_excel.py                   new Captains_Edge_Summary sheet
```

## The four blocks

| Block | Real source | Ranked by |
| --- | --- | --- |
| Top Strongest Pairings | `pairings[].matchup_score` (`analytics.lineup_optimizer`'s own real H2H input) | highest real `matchup_score` first |
| Top Danger Matchups | `opponent_scouting[]` where `is_danger_matchup` is true (`analytics.opponent_scouting`) | lowest real `avg_win_probability` first (most dangerous), ties broken by highest opponent volatility |
| Best Anchor Candidates | `lineups[].lineup_risk.anchor_player_name`/`.anchor_stability_score` (`analytics.lineup_risk`) | highest real `anchor_stability_score` first |
| Highest-Risk Lineups | `lineups[].lineup_risk.lineup_risk_score` (`analytics.lineup_risk`) | highest real `lineup_risk_score` first |

Every list excludes an entry with no real signal to rank on (a pairing
missing `matchup_score`, a lineup with no real anchor or risk block) --
never ranked as if it scored a fabricated 0.

Reuses each source module's own real ranking concept rather than
re-deriving a competing one: "best anchor" here is exactly
`analytics.lineup_risk`'s own anchor selection, not a second,
independently-invented notion of "best."

## Excel sheet

`Captains_Edge_Summary`, appended the same post-process way the Lineup
Optimizer and Opponent_Scouting sheets already are
(`ui.export_excel.append_captains_edge_summary_sheet`), reading the same
real `lineups.json`. All four blocks share one sheet, each its own titled
table separated by a blank spacer row -- not four separate sheets, since
these are four views of the SAME small set of numbers a captain wants
side by side. Idempotent: a rerun replaces the prior sheet. `n` (how many
rows per block, default 5) is a real, explicit parameter, not a config
section -- there's nothing to verify against real data for a "how many
rows to show" choice.

Verified against the real database: all four blocks render correctly
ranked real data (e.g. the real top danger matchup, Michael Otero, at a
real 27% average win probability against our real roster).
