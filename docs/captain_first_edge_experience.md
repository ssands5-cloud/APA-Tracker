# Captain-First Edge Experience

Governing spec for the captain-first hybrid view: what a captain sees when
they open the app before tonight's match, and the evidence rules every
number on that screen must obey. This document is the contract; the three
implementation stages below build against it one push at a time, each
audited against Issue #14 before the next stage starts.

**Filename note for the audit trail:** GPT's coordination comment on
Issue #14 named this file `docs/captain_first_experience.md`; the task that
produced this document specified `docs/captain_first_edge_experience.md`.
Same scope, same claim, different filename — flagged here so a future
audit doesn't read the mismatch as two competing documents.

## 0. Why this exists, and what it is not

Issue #14 is a long, still-open chain of fail-closed audits against this
project's analytics: an uncalibrated *new* modeled win-probability stack,
invented danger/rationale thresholds, a roster export that mislabels
historical participants as a current roster, a historical-lineup filter
that doesn't require a played match, and a Trend Score gate that ignores
its own persisted flag, among others (full list in §13). Stage 1 does not
reuse any of those failed paths.

What this document defines instead is a **second, independent lens** on
approved inputs: exact-opponent results from authoritative matches and the
older skill-gap-only model already graded against real recorded outcomes in
`docs/prediction_validation.md`. It answers "what kind of evidence is
available for this pairing?" without importing the failed WR_SL/logistic
stack or inventing a neutral fallback.

## 1. Tonight's Match — the opening view

The app opens on **Tonight's Match**, not a sheet index or a generic
dashboard. It answers one question first: *who are we playing, and what do
we actually know?* Everything else (Lineup Lab, Data Coverage) is reached
from here, never in place of it.

Tonight's Match renders nothing about a matchup until a real team, opponent,
format, and session are selected (§2) — no default guess, no "most recent"
auto-pick presented as if the captain chose it.

## 2. Controls

Five real, independently changeable controls gate everything Tonight's
Match shows:

| Control | Source | Notes |
| --- | --- | --- |
| Team | `apa_config.yaml` team id / `Team.external_id` | The team this app is "ours." |
| Opponent | `Match.home_team_id`/`away_team_id` for a real scheduled match | Never free text; always a real opponent from the schedule. |
| Format | `Match.format` (`EIGHT`/`NINE`) | A player's 8-ball record and 9-ball record are different evidence — never merged. |
| Session | `Match.session_name` | A stale prior session's record is not current form — never merged with the active session by default. |
| Player availability | Captain input, per player, for tonight only | Not persisted as a roster change — an availability *toggle* for this match, separate from §12's roster-membership question. |

Changing any control recomputes the matrix (§3) and evidence counts (§8)
from scratch. There is no cached "last computed" view that can silently go
stale relative to the selected controls.

## 3. The matchup matrix

One row per feasible pairing: every available one-of-ours player against
every identified opponent player, for the selected format/session. A
**feasible pairing** is:

```
(our player, opponent player)
  our player  ∈ team roster for the selected team, marked available
  opponent    ∈ canonical current roster for the selected opponent and
                session (§12)
  scoped to the selected format + session
```

Total feasible pairings = `|available our players| × |identified opponent
players|`. The matrix always renders exactly that many rows — see §7 and
§8.

Each row carries, at minimum: both canonical player ids and names, both
real current-roster skill levels (when known), the evidence label (§4), a
DIRECT observed win rate/count when one exists, and a separately named
modeled probability when the approved model has usable inputs (§5).

## 4. Evidence labels: DIRECT, INDIRECT, UNKNOWN

Every row in the matrix gets exactly one label, computed by
`analytics/pairing_evidence.py`:

- **DIRECT** — one or more *distinct matches* supplies a recognized `W`/`L`
  for this exact player/opponent pair. Both the denormalized H2H row and its
  parent `Match` must match the selected format/session; the parent match
  must contain the selected team ids and be scored, finalized, and non-bye.
  Exact duplicate rows for one match count once; conflicting facts for one
  match stop the build rather than being averaged.
- **INDIRECT** — no DIRECT match exists, but both canonical current-roster
  rows carry a real skill level. The separately displayed probability comes
  from `analytics.head_to_head.skill_only_win_probability`, the production
  implementation of the skill-only term validated against 106 recorded
  outcomes in `docs/prediction_validation.md`. No other opponent's history
  is pooled into this label.
- **UNKNOWN** — neither of the above. At least one real model input is
  missing, so no probability is emitted.

DIRECT outranks INDIRECT when exact history exists. A DIRECT row may also
carry `analytics.head_to_head.win_probability` as a separately named model
output, but its observed rate is never blended with that model.

No row is ever unlabeled, and no label is ever invented for a fourth case.

## 5. Observed win rate vs. modeled win probability — kept separate

Two different kinds of number exist in this codebase under confusingly
similar names, and the captain-first views must never blur them:

- **Observed win rate** — a DIRECT fact: wins ÷ distinct authoritative
  matches for this exact pair and scope.
- **Approved modeled win probability** — the older
  `analytics.head_to_head` model. INDIRECT uses only its validated
  skill-gap term and only when both current-roster skill levels exist.
  DIRECT may use the same module's full direct-history-plus-skill path.
- **Excluded modeled win probability** — `analytics.win_probability
  .compute_win_probability`, the newer WR_SL/logistic estimate explicitly
  failed closed under Issue #14. It is not imported, shown, ranked, or
  blended anywhere in this experience (§13).

The payload and UI name observed rates and modeled probabilities in
different fields and columns. An INDIRECT probability is never described
as a historical win rate.

## 6. Neutral fallbacks: displayed as "No data," never as an observed number

Existing internal engines substitute a neutral placeholder when there's no
history — `analytics.matchups.matchup_score` returns `50`,
`analytics.matchups.head_to_head_win_rate` returns `0.0` — documented,
intentional choices *for those specific, already-shipped outputs*
(`docs/matchups.md`). The captain-first evidence layer does not reuse
either fallback as if it were a real observed value:

- An UNKNOWN pairing's `observed_win_rate` is `None`, not `0.0`.
- An UNKNOWN pairing's `modeled_win_probability` is `None`, not `0.5`.
- No pairing's evidence rate is ever `50%`/`0.5` as a stand-in for "haven't
  played."

Every UI surface renders a `None` rate as the literal text **"No data"** —
never a blank cell (which reads as an oversight) and never a number that
could be mistaken for a real 0% or 50% record.

## 7. Every unknown pairing stays visible

An UNKNOWN-labeled row is never dropped, filtered out by default, or
collapsed into a summary count. A captain scanning the matrix for "which
pairings lack both direct evidence and usable model inputs" must be able to
find every one of those pairings by looking at the matrix itself, not by
inferring them from what's missing. Filters (§2, Stage 2) may let a captain
narrow the view, but the unfiltered matrix is always the complete feasible
set, UNKNOWN rows included.

## 8. Evidence-count reconciliation

For any computed matrix:

```
count(DIRECT) + count(INDIRECT) + count(UNKNOWN) = total feasible pairings
```

This is a hard invariant over pair *identity*, not only arithmetic.
`analytics.pairing_evidence.build_pairing_matrix` compares classified keys
against an independently derived feasible-pair set and rejects duplicate
expected keys, duplicate classified keys, omissions, and unexpected keys.
One duplicate plus one omission therefore fails even when the totals happen
to balance.

## 9. Lineup Lab

A separate view (Stage 3) from the matrix: given the matrix's evidence for
tonight's available players, Lineup Lab shows three real, always-present
lists — never just the first one:

1. **Approved best lineup** — a full player-vs-opponent-position assignment
   built *only* from §13's approved analytics (DIRECT observed evidence,
   INDIRECT skill-only probability with real inputs, and the older
   validated `analytics.head_to_head` path). No output from the failed
   `analytics.win_probability` stack, no lineup-risk aggregate, no rationale
   text, and no danger flag contributes to this selection.
2. **Unassigned players** — any available one-of-ours player the approved
   lineup didn't place (a roster larger than the number of positions, or a
   position left open because no defensible assignment exists from approved
   evidence alone). Never silently dropped.
3. **Unassigned opponents** — the mirror image: any identified opponent
   player the approved lineup didn't pair against one of ours.

Every player who appears anywhere in the matrix appears in exactly one of
these three lists. Reconciliation here mirrors §8: assigned + unassigned
ours = available ours; assigned + unassigned opponents = identified
opponents.

## 10. Lineup alternatives — opt-in only, and only when validated

Lineup Lab shows exactly one approved lineup by default. A second
("alternative") lineup is only ever added when:

1. its optimization objective is written down in this document (or a dated
   amendment to it) in plain language — e.g. "minimize UNKNOWN pairings
   fielded" is a legitimate, statable objective; "maximize win probability"
   may use only the explicitly approved `analytics.head_to_head` probability
   (§5), never the failed `analytics.win_probability` stack;
2. that objective has been checked against this project's own real data the
   same way `docs/win_probability.md`'s weight table or
   `analytics.close_match_performance.CLOSE_MATCH_MARGIN`'s 14-match sample
   were — not asserted, not borrowed from an unrelated domain; and
3. it has been through the same commit-and-audit cycle as everything else
   in this document (§15).

No alternative lineup ships from a threshold, weight, or heuristic invented
in the implementation and not already described, sourced, and validated
here first — that is exactly the pattern Issue #14 has fail-closed
repeatedly (danger-matchup thresholds, rationale anchor thresholds, the
log5 season-projection transfer).

## 11. Data Coverage view

A dedicated view, separate from the matrix, answering "how much of this can
I actually trust right now" at a glance:

- **Missing skill levels** — every player in the current matrix (either
  side) with a `None` `skill_level` and/or `PlayerHeadToHead
  .own_skill_level`/`opponent_skill_level`, named individually, not just
  counted.
- **Sample sizes** — distinct authoritative-match counts backing each DIRECT
  observed rate. INDIRECT rows expose their two real skill inputs and model
  source, not a fabricated "games" count.
- **Evidence coverage** — `count(DIRECT)`, `count(INDIRECT)`,
  `count(UNKNOWN)` as both raw counts and percentages of the total feasible
  pairings (§8), so a captain can see "this is a 20%-DIRECT-evidence match"
  as a real, load-bearing caveat rather than something they'd only notice
  by counting rows themselves.
- **Refresh dates** — the most recent real capture timestamp this data has:
  `StandingsSnapshot.captured_at` (max, per team) and
  `PlayerCareerStats.updated_at` (per player, where present) are the only
  real timestamps this project currently persists at that grain. No
  synthetic "last updated: today" label is shown where no real timestamp
  exists.
- **Unavailable fields** — an explicit, named list of what this view does
  *not* have, reusing this project's own already-documented gaps rather
  than re-discovering or re-wording them: innings and per-opponent
  defensive-shot average (`docs/matchups.md`, "Two things this deliberately
  doesn't include"), a canonical current-opponent-roster signal for any
  opponent player never captured by a real roster/TeamStat ingest (§12),
  and per-player sync timestamps finer than the two listed above. A field
  with no real source is named as missing, never silently absent or
  guessed at.

## 12. Roster membership: historical participation is not current roster

`ui/export_json.py`'s `team_roster`/`opponent_rosters` derive a roster from
players who have a `PlayerMatch` row for that team — real evidence that a
player *was seen playing for* a team, not evidence of current membership.
Issue #14 has this open as a P0 finding as of this writing: that derivation
excludes real current members who haven't yet appeared in a captured match
and retains former or occasional players who have. This document does not
fix that export; it forbids the captain-first views from repeating the same
mistake.

**Rule:** a player is presented as "current roster" for a team+session in
any captain-first view *only* when a real `PlayerTeamHistory` row for
`(player_id, team_external_id, division_id, session_name)` has
`is_current == True`. `team_external_id` is APA's captured immutable team
id; `team_name` is refreshed display metadata and never an identity key.
The session is mandatory. If more than one current row remains for the same
player/team/session, the query fails closed instead of choosing a mutable
name or skill level by row order.

This rule governs both sides identically. Historical `PlayerMatch` or
`PlayerHeadToHead` participation never expands either feasible roster. If a
canonical current roster is unavailable, Data Coverage says so and the
matrix remains empty for that side rather than guessing membership.

## 13. Analytics excluded until corrected and re-audited

Per Issue #14, as of this writing, none of the following may be presented
as validated captain advice anywhere in the captain-first experience — not
shown, not summarized, not silently relied on as an input to something
else that IS shown:

| Module / field | Why it's excluded (Issue #14 finding) |
| --- | --- |
| `analytics.win_probability` (`modeled_win_probability`) | Uncalibrated logistic model; unquantified double-counting between `WR_H2H`/`WR_SL`; zero-default bias on missing rate inputs; `race_difficulty()` is a placeholder always returning `0.0` (commit `96fc8a7`). |
| `analytics.lineup_risk` | Built on the above modeled probability chain. |
| `analytics.opponent_scouting` | "Times Faced" mislabels a pairing-record count as a match count; danger-matchup thresholds (win prob < 0.40 OR volatility ≥ 0.50) are invented and unfitted; unweighted per-pair averaging (commit `28afa40`). |
| `analytics.rationale` | Invented, explicitly-unfitted categorical thresholds for volatility/anchor language; presents disputed model outputs as categorical advice (commit `bf53a76`). |
| `analytics.season_projection` | Unvalidated baseball-log5 domain transfer to APA matches; `upset_likelihood` peaks at the wrong point (0.5); `team_volatility_curve` computes no real dispersion measure (commits `2737c94`/`9f8f643`). |
| `analytics.captains_edge_summary` | Rolls up the modules above; its Excel test requires a header-only sheet for an empty document, which is a placeholder-sheet violation on its own (commit `9f8f643`). |
| `ui.export_json._team_roster` / `_opponent_rosters` | Historical-participation-derived, mislabeled "roster" (§12). |
| `analytics.lineup_legality` (the "actual fielded historical lineup" claim) | Doesn't require `Match.is_scored`/`is_finalized`/non-`is_bye`; the *rule itself* (`lineup_legality_rule`, the real 23-rule Team Skill Level Limit check) is not excluded — only the claim that grouped `PlayerMatch` rows represent an actually-played lineup. |
| `analytics.team_stats` Opponent Strength Index specifically | Still scoped through `team.players`/`Player.team_id` rather than the match-linked team, an identity defect distinct from the rest of `team_stats` (commit `15413e7`'s re-audit). |
| `analytics.player_trends.trend_score` / `hot_cold_flag` as a categorical badge | The gate `trend_score()` recomputes eligibility instead of using the persisted `hot_cold_flag`, so it can disagree with stored state. Raw numeric slope/volatility (as already used, uncategorized, inside `analytics.matchups` via `analytics.skill_level_trends` — an unflagged, separate module) are not affected by this exclusion. |

This table is expected to shrink as findings are corrected and
independently re-audited on Issue #14 — it is not a permanent ban, only a
current one. A row is removed from this table in the same commit that
fixes the underlying finding, referencing the re-audit that cleared it, not
before.

## 14. Stage 1 — evidence-label classification and reconciliation

Scope: `analytics/pairing_evidence.py` (database-owned classification and
exact reconciliation, §4–§8), immutable team identity persisted from the
existing TeamStat `team_id` field, mandatory session-scoped
`database.queries.canonical_current_roster` (§12), and one production helper
extracted from the already validated `analytics.head_to_head` skill term.
No frozen scraper-contract field or query changes; no HTML or Excel in this
stage. `tests/test_pairing_evidence.py` exercises the real ORM schema and
production query path in memory, including invalid match states, distinct
match ids, cross-scope noise, duplicate/omitted matrix keys, side-specific
availability, renamed teams, and ambiguous memberships.

## 15. Stage 2 — captain-first HTML layout

Scope: Tonight's Match (§1), the five controls (§2), the full matchup
matrix (§3) rendering every feasible pairing including UNKNOWN rows (§6,
§7). Reuses Stage 1's classifier as its only source of evidence labels and
rates. No Lineup Lab, no Data Coverage view yet. No Excel changes.

## 16. Stage 3 — Lineup Lab and Data Coverage

Scope: §9–§11, built only on §13's approved analytics. No new objective,
threshold, or heuristic that isn't already written down and validated
somewhere in this document or a dated amendment to it (§10).

## 17. Hard boundaries (all stages)

- The scraper contract (`README-scraper.md`, `scraper/full_auto_scrape.py`,
  `scraper/sanitized_fixtures/`) is not modified.
- No fabricated data or invented APA statistic — every displayed number
  traces to a real captured field or a documented, real aggregation of one.
- No VBA, COM, pywin32, or macros.
- No placeholder sheets — a sheet or view with headers and no real data
  behind it is not shipped ahead of the data existing.
- `docs/reproducible_builds.md`, `scripts/reproducible_build.py`,
  `tests/test_reproducible_build.py` are not touched — owned by a separate,
  concurrently staged process.
- CI fixtures and `dist/BUILD_INFO.json` are not touched during this
  feature's development.
- Nothing in §13's table is built on, wired in, or presented as validated
  captain advice until it is corrected and independently re-audited.
- Every push is one stage (§14/§15/§16), followed by a GitHub Issue #14
  comment naming the commit SHA and the real test evidence for it, and
  implementation waits for that stage's audit before the next one starts.
