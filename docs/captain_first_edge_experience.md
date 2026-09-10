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
project's analytics: an uncalibrated modeled win probability, invented
danger/rationale thresholds, a roster export that mislabels historical
match participants as a current roster, a historical-lineup filter that
doesn't require a played match, and a Trend Score gate that ignores its own
persisted flag, among others (full list in §13). None of that is corrected
here. This document does not re-litigate or re-approve any of it.

What this document defines instead is a **second, independent lens** on
data this project already has real evidence for: not "how good is this
matchup" (that question is exactly where the fail-closed modeling lives),
but "how much do we actually know about this matchup, and from what." A
captain-first view built on that lens can ship real, honest value —
who we have real history against, who we don't, where the gaps are — without
waiting on the modeled-probability chain to be corrected, and without
repeating its mistakes.

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
  opponent    ∈ every real, identified player associated with the
                selected opponent (§12 governs how "associated" is proven
                and how that's labeled — this does not require proof of
                CURRENT opponent roster membership to be feasible, only
                real identity)
  scoped to the selected format + session
```

Total feasible pairings = `|available our players| × |identified opponent
players|`. The matrix always renders exactly that many rows — see §7 and
§8.

Each row carries, at minimum: both player names, both real skill levels
(when known — see §11 for when they aren't), the evidence label (§4), the
observed win rate when one exists (§5), and the evidence count it's based
on.

## 4. Evidence labels: DIRECT, INDIRECT, UNKNOWN

Every row in the matrix gets exactly one label, computed by
`analytics/pairing_evidence.py`:

- **DIRECT** — at least one recognized-result (`W`/`L`) real
  `PlayerHeadToHead` row exists for this *exact* player-vs-opponent pair, in
  the selected format/session. This is the same recognized-result gate
  `analytics.matchups.recognized_results` already uses — a row with a
  missing or unreadable result doesn't count as evidence either way.
- **INDIRECT** — no DIRECT row exists, but the player has at least one
  recognized-result row against a *different* real opponent who shares the
  target opponent's skill level, same format/session. This reuses the same
  real aggregation `docs/win_probability.md` calls WR_SL
  (`scripts.build_lineups.fetch_win_rates_by_skill_level`'s grouping, not
  its output) — a real, transparent, unweighted rate, never blended into a
  model.
- **UNKNOWN** — neither of the above. No history against this opponent,
  and no history against anyone at this opponent's skill level either.

A DIRECT pairing may also have INDIRECT evidence available (games against
other same-skill-level opponents). It still renders as DIRECT — exact
opponent evidence outranks same-skill-level evidence for the label — but
the INDIRECT rate is still carried alongside it as separate descriptive
context, never averaged into the DIRECT rate.

No row is ever unlabeled, and no label is ever invented for a fourth case.

## 5. Observed win rate vs. modeled win probability — kept separate

Two different kinds of number exist in this codebase under confusingly
similar names, and the captain-first views must never blur them:

- **Observed win rate** — a plain count: wins ÷ recognized games, for
  either a DIRECT pair or (separately, labeled INDIRECT) a same-skill-level
  group. A fact about what already happened. This is what Tonight's Match
  and the matrix show.
- **Modeled win probability** — `analytics.win_probability
  .compute_win_probability`'s `modeled_win_probability`: a hand-fit
  logistic estimate, explicitly **FAIL-CLOSED** under Issue #14 (uncalibrated
  coefficients, unquantified double-counting between inputs, a zero-default
  bias on missing win-rate features, a placeholder `race_difficulty()` that
  always returns 0.0). This number does not appear anywhere in the
  captain-first experience — not shown, not ranked on, not blended into an
  observed rate — until it is corrected and separately re-audited under
  Issue #14 (§13).

Where both exist for other, already-shipped features (e.g.
`PlayerH2HAdvantage.win_probability` — itself an OBSERVED rate despite its
field name, per `docs/win_probability.md`'s own note), the captain-first
views read the real observed data directly out of `PlayerHeadToHead`
(§4) rather than through a field whose name overloads "probability" for an
observed rate.

## 6. Neutral fallbacks: displayed as "No data," never as an observed number

Existing internal engines substitute a neutral placeholder when there's no
history — `analytics.matchups.matchup_score` returns `50`,
`analytics.matchups.head_to_head_win_rate` returns `0.0` — documented,
intentional choices *for those specific, already-shipped outputs*
(`docs/matchups.md`). The captain-first evidence layer does not reuse
either fallback as if it were a real observed value:

- An UNKNOWN pairing's `observed_win_rate` is `None`, not `0.0`.
- An UNKNOWN pairing's `indirect_win_rate` is `None`, not `0.0`.
- No pairing's evidence rate is ever `50%`/`0.5` as a stand-in for "haven't
  played."

Every UI surface renders a `None` rate as the literal text **"No data"** —
never a blank cell (which reads as an oversight) and never a number that
could be mistaken for a real 0% or 50% record.

## 7. Every unknown pairing stays visible

An UNKNOWN-labeled row is never dropped, filtered out by default, or
collapsed into a summary count. A captain scanning the matrix for "who have
we literally never seen data on, direct or indirect" must be able to find
every one of those pairings by looking at the matrix itself, not by
inferring them from what's missing. Filters (§2, Stage 2) may let a captain
narrow the view, but the unfiltered matrix is always the complete feasible
set, UNKNOWN rows included.

## 8. Evidence-count reconciliation

For any computed matrix:

```
count(DIRECT) + count(INDIRECT) + count(UNKNOWN) = total feasible pairings
```

This is a hard invariant, not a sanity check that's allowed to drift.
`analytics.pairing_evidence.build_pairing_matrix` raises rather than
returning a mismatched count — a silently dropped or silently duplicated
pairing is exactly the class of bug this document exists to make
impossible to ship unnoticed. Stage 1's tests assert this invariant against
constructed fixtures directly (see §14).

## 9. Lineup Lab

A separate view (Stage 3) from the matrix: given the matrix's evidence for
tonight's available players, Lineup Lab shows three real, always-present
lists — never just the first one:

1. **Approved best lineup** — a full player-vs-opponent-position assignment
   built *only* from §13's approved analytics (DIRECT/INDIRECT observed
   evidence, real skill levels, the already-shipped, unflagged Matchup
   Advantage Engine score for pairs that have real head-to-head history).
   No modeled win probability, no lineup-risk aggregate, no rationale text,
   no danger flag — none of Issue #14's fail-closed chain — contributes to
   this selection.
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
   is not statable here because the only "win probability" this project has
   is the fail-closed modeled one (§5);
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
- **Sample sizes** — recognized-result game counts backing each DIRECT and
  INDIRECT rate in the matrix (already carried on every `PairingEvidence`
  row — this view is a coverage-focused re-read of the same counts, not a
  second computation).
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
`(player, team_name, session_name)` has `is_current == True` — the actual
per-alias field TeamStat itself reports
(`database.ingest.ingest_player_team_history`), refreshed every time that
player's TeamStat history is re-ingested. This is never inferred from
`PlayerMatch`/`PlayerHeadToHead` participation.

When no such `PlayerTeamHistory` row exists for a player who does appear in
the matrix (via real match-participation evidence, or as a name on the
opposing side of a real head-to-head row), that player is labeled
**"seen in matches"**, not "current roster," and their roster status is
listed as an unavailable field in Data Coverage (§11) rather than defaulted
either way.

This rule governs "our" side identically to the opponent's side — a
player on our own team is not presented as "current roster" from match
participation alone either, though in practice `Team.players`
(`Player.team_id`, refreshed on every real roster ingest via
`database.ingest.upsert_roster`) is expected to cover our own team far more
completely than any opponent's.

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

Scope: `analytics/pairing_evidence.py` (evidence labeling, §4–§8) and one
new additive query, `database.queries.canonical_current_roster` (§12). No
HTML, no Excel, no changes to any existing analytics module, no changes to
the frozen scraper contract (`README-scraper.md`). Tests:
`tests/test_pairing_evidence.py`, operating on constructed
`PlayerHeadToHead`/`PlayerTeamHistory` fixtures the same way
`tests/test_matchups.py` and `tests/test_team_stats.py` already do — no
network, no live scrape.

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
