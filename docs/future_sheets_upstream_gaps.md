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

**Updated after the `schedule[]`/`team_roster[]`/`opponent_rosters[]`
exports and the real, sourced 23-Rule check shipped** (see
`docs/close_match_performance.md`, `docs/lineup_legality.md`) — several
gaps below that were open when this was first written are now closed.
Each section says which.

## Schedule_History — UNBLOCKED

The original gap (no `schedule[]`-shaped export existed) is closed.
`ui/export_json.py`'s `_schedule()` now produces exactly this shape: week,
date, opponent team, your player, opponent player, both real skill
levels, result, and real match margin — joined from `Match` +
`PlayerHeadToHead`, attributed match-by-match via real `PlayerMatch.team_id`
evidence (not a stale roster label). `notes`/`clutch_flag`/`break_run_flag`
remain correctly omitted — still not real fields anywhere in this
project's captured data.

**Nothing new needed upstream.** A real Schedule_History sheet (Excel
and/or a JSON-consuming view) could be built directly from the existing
`schedule[]` export.

## Next_Match — UNBLOCKED

The original gap (no "your roster" vs "opponent roster" split) is closed:
`team_roster`/`opponent_rosters` now exist, built from real match-level
`PlayerMatch.team_id` evidence, keyed off the same `apa_config.yaml`
`team.team_id` this project already treats as "yours" elsewhere.

Identifying "the next match" itself is a real, derivable fact, not a new
upstream field: the earliest-by-week entry in `matches[]` where the
configured team is `home_team_id`/`away_team_id` and `is_scored` is still
false. The matchup grid and colour zones are not a blocker either —
Matchups' existing Risk Band and Win Rate colouring are directly reusable
once the roster split exists, exactly as originally noted.

**Nothing new needed upstream.** Buildable now.

### The 23-rule legality check specifically — DONE

No longer a blocker anywhere in this document. `analytics/lineup_legality.py`
implements the real, sourced Team Skill Level Limit
(`rules.poolplayers.com/general-rules/team-skill-level-limit/`), including
duplicate-player rejection, and it's exported as `lineup_legality_rule`
(the rule itself) and `lineup_legality` (real, retroactive checks against
actual fielded lineups from already-played matches).

## Player Cards / Opponent Cards — UNBLOCKED

Player Cards were never blocked: "Best Matchup" / "Worst Matchup" per
player is real and already computable (max/min `matchup_score` or win
rate from `PlayerMatchup`, grouped by player). Opponent Cards' blocker —
the your-team/opponent-team split — is now closed the same way Next_Match's
was, via `team_roster`/`opponent_rosters`.

**Nothing new needed upstream.** Both are buildable now; the remaining
work is layout ("visual cards": borders, shading, bold headers), not data.

## Lineup Simulator — MOSTLY UNBLOCKED (updated)

All three of its original blockers are now real and shipped:

- The legality rule exists (`analytics.lineup_legality`, with
  duplicate-player rejection).
- The per-team roster split exists (`team_roster`/`opponent_rosters`).
- The "aggregation formula" gap this section originally called out --
  "how five individual pairwise matchups combine into one team-level
  expected outcome" -- is now real and shipped, checked against this
  project's own real data first: `analytics.win_probability` computes a
  real, transparent per-PAIRING win probability (SLDelta/WR_SL/WR_H2H/
  Volatility), and `analytics.lineup_risk` already aggregates exactly
  five such pairings into one team-level summary (Upset Risk Index,
  Anchor Stability Score, Lineup Volatility Load, Danger Matchup Count,
  Lineup Risk Score). See `docs/win_probability.md` and
  `docs/lineup_risk.md`.

**What's still genuinely open**: both of those real functions currently
take the OPTIMIZER'S OWN solved assignment as input
(`scripts.build_lineups._lineup_for_group` calls them right after
`solve_lineup_assignment` returns) -- neither has been wired to accept an
arbitrary, HYPOTHETICAL 5-player-vs-5-player combination a captain picks
by hand instead of the solver's own pick. The math already generalizes
(neither `compute_win_probability` nor `compute_lineup_risk` requires its
input to have come from the solver specifically), but the
combination-selection interface itself -- letting a captain choose
"Your lineup" / "Opponent lineup" from dropdowns and get a real,
non-solver-picked projection back -- has not been built. A real, scoped
remaining piece of work, not a re-discovery.

## Captain Summary — a related but DIFFERENT real sheet now exists

`Captains_Edge_Summary` (see `docs/captains_edge_summary.md`) now ships a
real rollup of Top Strongest Pairings, Top Danger Matchups, Best Anchor
Candidates, and Highest-Risk Lineups -- covering some of the same real
ground this section originally described (`Recommended ... Anchor`,
`Avoid_List`-style danger flags) using data already available TODAY
(every solved lineup across the whole league), not the one specific
upcoming match Next_Match would provide.

This is NOT the same feature this section originally scoped: a genuine
`Next_Match`-scoped Captain Summary (one upcoming opponent,
`Recommended Starter/Mid/Anchor` and `Avoid_List`/`Target_List` for THAT
match specifically, `Optimal Lineup` from the Lineup Simulator once its
own remaining gap above is closed) is still real, still useful, and
still not built. `Captains_Edge_Summary` closes the "is there a rollup of
real danger/anchor/risk data" gap; it doesn't replace the
one-upcoming-match-scoped version this section first asked for.

## What's NOT blocked (cumulative, updated)

Everything previously shipped (Team_Stats, Matchups' Risk Band,
Head-to-Head's two-signal highlighting, Trend Score, Close-Match Win Rate)
plus the real, match-scoped `schedule[]`/`team_roster[]`/`opponent_rosters[]`
exports, the real, sourced 23-Rule check (`lineup_legality_rule` /
`lineup_legality`), the real per-pairing win-probability model
(`analytics.win_probability`), and the real team-level lineup-risk
aggregation (`analytics.lineup_risk`) are all shipped, real, and usable
as building blocks today.

Of the six originally deferred features: Schedule_History, Next_Match,
Player Cards, and Opponent Cards need no new upstream data at all -- only
a scoping decision on which to build first. The 5-player-combination
aggregation formula Lineup Simulator and Captain Summary were both
waiting on is now real and shipped (see "Lineup Simulator" above) --
their remaining gap is a combination-selection interface for a
HYPOTHETICAL lineup, not a missing formula. A real, differently-scoped
`Captains_Edge_Summary` sheet already ships some of Captain Summary's
original intent using data available today, across the whole league
rather than one upcoming match -- see `docs/captains_edge_summary.md`.
