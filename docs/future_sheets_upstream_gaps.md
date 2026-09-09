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

## Lineup Simulator — PARTIALLY UNBLOCKED

Both of its original blockers are closed: the legality rule exists (see
above) and the per-team roster split exists (`team_roster`/`opponent_rosters`),
so "Your lineup" / "Opponent lineup" dropdowns have real data to populate
from.

**What's still genuinely open**: `Expected Win Probability` /
`Expected Rack Differential` for a CHOSEN 5-player-vs-5-player combination
needs its own aggregation formula over the real, already-computed
per-pair `PlayerMatchup` data (win rate, `matchup_score`, `confidence_score`)
— e.g., how five individual pairwise matchups combine into one team-level
expected outcome is a real design question, not a re-export of an
existing field. This is the same kind of step Trend Score and Close-Match
Win Rate each needed — a formula checked against real data and finalized
— before implementation, not assumed from a plausible-sounding name. Not
started; should not be guessed at.

Choosing a HYPOTHETICAL combination of real, real rostered players to
simulate is not itself a fabrication concern — that's what a simulator is
for — as long as every number the simulation displays traces back to real,
already-computed pairwise data, the same discipline this project already
applies everywhere else.

## Captain Summary — PARTIALLY UNBLOCKED

Downstream of the above: `Recommended Starter/Mid/Anchor` and
`Avoid_List`/`Target_List` need Next_Match's matchup grid (buildable now,
see above); `Legal Lineups` needs the confirmed 23-rule (done); `Optimal
Lineup` needs the Lineup Simulator's combination search, which is blocked
on the same win-probability aggregation formula described above. Nothing
new to add here beyond what's already listed — this sheet is purely a
rollup of the others, and inherits their status.

## What's NOT blocked (cumulative)

Everything previously shipped (Team_Stats, Matchups' Risk Band,
Head-to-Head's two-signal highlighting, Trend Score, Close-Match Win Rate)
plus the real, match-scoped `schedule[]`/`team_roster[]`/`opponent_rosters[]`
exports and the real, sourced 23-Rule check (`lineup_legality_rule` /
`lineup_legality`) are all shipped, real, and usable as building blocks
today. Of the six deferred features, four (Schedule_History, Next_Match,
Player Cards, Opponent Cards) now need no new upstream data at all — only
a scoping decision on which to build first. Lineup Simulator and Captain
Summary need one more real step first: designing and verifying a
5-player-combination win-probability formula, the same rigor every other
formula in this project has gotten.
