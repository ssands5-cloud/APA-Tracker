# Upstream gaps blocking Schedule_History, Next_Match, Player/Opponent Cards, Lineup Simulator, Captain Summary

Phase 3 infrastructure work, scoped deliberately to documentation: no
placeholder sheets, no export stubs, no stub code paths added to the real
workbook. A sheet with headers and no real data source behind it, sitting
in the production export next to Team_Stats and Close_Match_Stats, would
look like a real feature to a captain opening the file — that's a
different kind of fabrication risk than an invented number, but a real one,
so it isn't done here. This document IS the requested infrastructure: the
exact gap each feature needs closed, so building it later is a scoping
decision, not a discovery process.

## Schedule_History

Needs a `schedule[]`-shaped export the pipeline doesn't produce.
`apa_data.json` has `matches[]` (team-level: id, week, home/away
team+score, status) and `match_scores[]` (per-player scoresheet rows) —
neither carries `your_player` vs `opponent_player` as a labeled pair, or
`notes`/`clutch_flag`/`break_run_flag` (the last two don't exist as real
fields at all — see `docs/close_match_performance.md` on why "which game
was the decider" isn't captured). A real Schedule_History would need to be
assembled from `matches[]` + `PlayerHeadToHead`, joined by `match_id` and
by whichever roster the viewing team belongs to (see Next_Match's gap
below) — buildable, but as a new query/dataframe, not a re-export of an
existing shape.

## Next_Match

Needs a "your roster" vs "opponent roster" split this workbook does not
have. Every existing sheet (Player Stats, Matchups, Team_Stats,
Close_Match_Stats) is whole-league: every real team's players in one
table, distinguished by a `Team` column, not by "mine" vs "theirs". Making
Next_Match real requires either (a) a config value naming which
`Team.external_id` is "yours" for this export run, or (b) a viewer-scoped
concept threaded through from a real signed-in account context. Neither
exists today. The matchup grid and colour zones themselves are not the
blocker — Matchups' existing Risk Band and Win Rate colouring are directly
reusable once the roster split exists.

### The 23-rule legality check specifically

Not started, and shouldn't be guessed at. This needs APA's actual,
current roster-eligibility rule (a real skill-level cap and/or composition
constraint for a 5-player team lineup) confirmed from the league's own
published rules or a captured API field — not assumed from the name. The
charter's own draft formula (`SL_Total <= 23`, "no more than two SL6+",
"at least one SL3 or below") is exactly the kind of plausible-sounding,
unverified rule this project's whole approach exists to catch before it
ships as if authoritative. Confirm the real rule first.

## Player Cards / Opponent Cards

Both need "Best Matchup" / "Worst Matchup" per player, which is real and
already computable (max/min `matchup_score` or `Win Rate` from the
Matchups sheet's own data, grouped by player) — the layout ("visual
cards": borders, shading, bold headers) is a formatting task with no data
gap. The blocker is the "Opponent" half of Opponent Cards, which needs the
same your-team/opponent-team split Next_Match does; Player Cards alone
(every real player, whole-league) could be built today without waiting.

## Lineup Simulator

Needs a legality rule (see Next_Match above) and a per-team roster split
to populate "Your lineup" vs "Opponent lineup" dropdowns. `Expected Win
Probability` / `Expected Rack Differential` for a 5-player combination is
a real, derivable aggregate of already-real Matchups/Head-to-Head data
once individual pairings are chosen — not a new upstream field — but the
combination-selection UI itself has no home until the roster split exists.

## Captain Summary

Downstream of everything above: `Recommended Starter/Mid/Anchor`,
`Avoid_List`/`Target_List` need Next_Match's matchup grid; `Legal Lineups`
needs the confirmed 23-rule; `Optimal Lineup` needs the Lineup Simulator's
combination search. Nothing new to add here beyond what's already listed —
this sheet is purely a rollup of the others.

## What's NOT blocked

Everything already shipped tonight (Team_Stats, Matchups' Risk Band,
Head-to-Head's two-signal highlighting, Trend Score, Close-Match Win Rate)
needed none of the above — that's why they were buildable immediately and
these six are not.
