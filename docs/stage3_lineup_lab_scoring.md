# Stage 3 amendment: the Lineup Lab pairing score and assignment rule

Dated 2026-09-14. A dated amendment to `docs/captain_first_edge_experience.md`
per its own §10 rule: no lineup objective ships without its formula written
down and checked against this project's real data *before* the code that
uses it. This document is that write-up for Stage 3 (§9, §16), posted to
[Issue #14](https://github.com/ssands5-cloud/APA-Tracker/issues/14) before
any assignment code is added, per the same issue's established audit
protocol.

## 1. The problem this document solves

Stage 1's evidence matrix carries two different per-pairing numbers that a
lineup assignment needs to compare on one scale:

- a DIRECT pairing's `observed_win_rate` (raw wins ÷ distinct authoritative
  matches), and
- an INDIRECT pairing's `modeled_win_probability` (the validated
  skill-gap-only estimate).

Picking a lineup means ranking pairings against each other regardless of
which evidence class they fall in. Comparing a raw `observed_win_rate`
against a smoothed `modeled_win_probability` directly would be miscalibrated
on its face: a single observed win reads as a raw 100%, which would always
outrank a INDIRECT pairing's smoothed, clamped estimate (bounded to
[0.02, 0.98]) regardless of the players' real relative strength. That bias
toward small, noisy DIRECT samples is exactly the kind of thing Issue #14
has failed closed before (see the `analytics.opponent_scouting` audit:
"unweighted per-pair averaging" letting a 1-match record and a 10-match
record contribute equally).

## 2. The score: reuse, not a new formula

**`analytics.pairing_evidence.PairingEvidence` already carries the single
number Stage 3 needs: `modeled_win_probability`.** No new formula is
introduced. The Stage 3 pairing score is:

```
score(pairing) =
    pairing.modeled_win_probability   if pairing.evidence_label in {DIRECT, INDIRECT}
    None (no edge; not scoreable)     if pairing.evidence_label is UNKNOWN
```

That field is already computed by Stage 1 (commit `8852904`) directly from
`analytics.head_to_head`, a pre-existing, non-excluded module (see §13):

- **INDIRECT** uses `skill_only_win_probability(own_skill_level,
  opponent_skill_level)`:

  ```
  logit(p) = SL_LOG_ODDS_PER_LEVEL * (own_skill_level - opponent_skill_level)
  p = clamp(sigmoid(logit(p)), 0.02, 0.98)
  ```

  where `SL_LOG_ODDS_PER_LEVEL = 0.40` is the same real, already-shipped
  constant `analytics.head_to_head.win_probability` uses (see that module's
  own docstring for the log-odds-per-skill-level rationale), and the
  0.02/0.98 clamp is the same real, already-shipped asymptote guard.

- **DIRECT** uses `win_probability(direct_rows)`:

  ```
  logit(p) = SL_LOG_ODDS_PER_LEVEL * (own_skill_level - opponent_skill_level)
           + reliability_weight(n) * logit(smoothed_win_rate)

  smoothed_win_rate = (wins + 1.0) / (n + 2.0)      # Laplace smoothing
  reliability_weight(n) = n / (n + 3)               # analytics.matchups' own shrinkage curve
  p = clamp(sigmoid(logit(p)), 0.02, 0.98)
  ```

  This is the *same* skill term as the INDIRECT case, plus a
  reliability-weighted, Laplace-smoothed real-history term. Both are
  already-shipped functions in `analytics/head_to_head.py`; Stage 1 did not
  invent either, it only extracted `skill_only_win_probability` as a named
  function so the INDIRECT path and
  `analytics.prediction_validation`'s already-graded skill term cannot
  drift apart (commit `8852904`).

**Why this, and not a new blend:** `win_probability` already IS "DIRECT
observed evidence combined with the skill term" — building a *second*,
Stage-3-specific formula on top of an already-combined number would
double-count the skill term and the observed record against each other,
exactly the "unquantified double-counting" finding Issue #14 raised against
`analytics.win_probability`'s WR_H2H/WR_SL overlap. Reusing the one existing,
already-validated number is what avoids repeating that mistake.

## 3. Why this satisfies the three required properties

**Monotonic in both components.** `sigmoid` and `logit` are both strictly
increasing; `reliability_weight(n) >= 0`. Score increases (weakly) with:
higher own skill level, lower opponent skill level, and a stronger observed
record at any fixed sample size. It never decreases when a real "good"
signal strengthens.

**Calibrated / no bias toward one source.** DIRECT does not report the raw
observed rate; it reports the same rate *shrunk toward the skill-only
estimate* by `reliability_weight(n)`, which is 0 at n=0 and only approaches
1 as history accumulates (`1/4` at n=1, `10/13` at n=10 — see §4's worked
examples). A single-game DIRECT record therefore cannot leapfrog a
well-supported INDIRECT estimate the way a raw `observed_win_rate` of 100%
or 0% would. This is the real, structural fix for the miscalibration
described in §1 — not an added correction term, but the reason the
already-existing function was reused instead of the raw rate.

**Explainable in plain language.** "How likely is our player to win this
specific game?", using the same one model whether or not we have direct
history: a skill-level edge is worth something on its own, and real
head-to-head history refines that estimate more as it accumulates, rather
than replacing it outright after a single game.

## 4. Worked examples (verified against the real, shipped code — not hand
arithmetic)

All computed by calling `analytics.head_to_head.skill_only_win_probability`
and `win_probability` directly; own skill level 5, opponent skill level 4
throughout (a real +1 SL edge):

| Evidence | Real record | Score | Reading |
| --- | --- | --- | --- |
| INDIRECT | none | **59.9%** | skill edge alone |
| DIRECT | 1–0 | **64.0%** | one win nudges the skill-only estimate up modestly |
| DIRECT | 0–1 | **55.6%** | one loss nudges it down modestly, not to a low number |
| DIRECT | 8–2 | **77.6%** | a real 10-game sample pulls the estimate substantially toward the observed 80% rate |
| INDIRECT | none, +3 SL edge (6 vs 3) | **76.9%** | for comparison: a big skill edge alone scores close to what a real, well-supported record would |

Note what does **not** happen: a 1–0 DIRECT record does not score 100%,
and a 0–1 record does not score 0%. Both single-game DIRECT records land
close to the INDIRECT (skill-only) baseline of 59.9%, exactly the
calibration property §3 requires.

## 5. Edge cases

- **UNKNOWN.** `modeled_win_probability` is `None`. UNKNOWN pairings get no
  edge in the assignment graph at all -- never a neutral 0.5, never
  excluded from the *matrix* (§7 still applies there), only excluded from
  being a *candidate* for a lineup slot. A player whose only options are
  UNKNOWN pairings is left unassigned rather than matched by a guess (see
  §6.3).
- **Sparse data (n=1 or n=2).** Handled by `reliability_weight(n)`, not a
  special case -- see the 1–0/0–1 examples in §4. No separate sparse-data
  branch is needed because the shrinkage is already built into the reused
  function.
- **Conflicting signals** (e.g., a real losing record against a player we
  are favored to beat on skill alone). Resolved by addition in log-odds
  space, the same way `win_probability` already documents: the skill term
  and the history term are both real, additive contributions: a
  losing-but-thin record only partially offsets a real skill edge (see the
  8-2-vs-skill interplay in `win_probability`'s own docstring); it is never
  a hand-picked override of one signal by the other.
- **Missing skill level on either side, no history either.** `score` is
  `None` (UNKNOWN) -- never defaulted to an average skill level.

## 6. The assignment rule ("Approved best lineup")

### 6.1 Why the existing `analytics.lineup_optimizer` is *not* reused

`analytics.lineup_optimizer.pairing_score`'s `unit_or_neutral` helper
defaults **every** missing input -- including a missing
`modeled_win_probability` -- to a neutral `0.5` before summing the weighted
objective (its own docstring: "a pairing is NEVER excluded for lacking
data"). That is the correct, already-audited behavior for *that* module's
own purpose, but it is the opposite of what
`docs/captain_first_edge_experience.md` §9 requires here: an UNKNOWN
pairing must never compete for a lineup slot on a fabricated `0.5`. Feeding
Stage 1's `modeled_win_probability` into that optimizer's
`PairingCandidate.modeled_win_probability` field would also be visually
indistinguishable, in that module's own vocabulary, from the field's
documented, *excluded* real source, `analytics.win_probability`'s failed
estimate -- a real risk of exactly this kind of audit confusion. Stage 3
therefore uses its own small, dedicated assignment function
(`analytics.lineup_lab`) rather than reusing or repurposing
`analytics.lineup_optimizer`.

### 6.2 The real APA legality constraint

`analytics.lineup_legality.check_lineup_legality` (already shipped, already
sourced from APA's published Team Skill Level Limit rule, not excluded by
§13) is the only legality check used: a standard lineup is exactly 5 slots,
combined skill level ≤ 23, no duplicate player. The 4-player/19 fallback is
explicitly out of scope here, same as it is everywhere else in this project
(`analytics/lineup_legality.py`'s own docstring: "left for a follow-up with
its own tests once actually needed").

### 6.3 The algorithm

Given the classified matrix for one (team, opponent, format, session)
scope, restricted to the captain's tonight-available players on our side and
every identified opponent on the other:

1. Build the scoreable graph: an edge (our player, opponent) exists only
   when that pairing's `score` (§2) is not `None`. UNKNOWN pairings are
   never edges.
2. Compute `k = min(5, maximum matching size using only scoreable edges)`.
   If `k == 0`, there is no scoreable pairing at all -- BLOCKED.
3. Among all matchings of size exactly `k`, find the one maximizing total
   score (exact search -- see §6.4 for the bound).
4. If `k < 5`: this is the whole result. It is reported as a **partial**
   lineup -- "N of 5 positions filled from approved evidence" -- with no
   legality verdict (legality is only defined for exactly 5 real slots).
   This is not a failure state to hide; a captain seeing 3 of 5 positions
   confidently filled and 2 genuinely unknown is exactly the honest picture
   this project exists to show.
5. If `k == 5`: check legality.
   - Legal: this is the **approved best lineup**.
   - Illegal (skill total > 23): re-run step 3 restricted to
     legal 5-matchings only. If one exists, it becomes the approved best
     lineup. If none exists, report BLOCKED("no legal 5-player lineup
     exists using only approved evidence") and still show the highest-
     scoring *illegal* one for transparency, clearly marked `is_legal:
     False`.
6. **Unassigned players** = every available our-player not in the chosen
   matching. **Unassigned opponents** = every identified opponent not in
   it. Every player who appears anywhere in the matrix appears in exactly
   one of {assigned, unassigned} -- the same reconciliation §9 already
   requires.

### 6.4 Exact search, bounded like the existing optimizer

The search in steps 3/5 is exact exhaustive combinatorics (choose a
`k`-subset of our available players, choose a `k`-subset of identified
opponents, evaluate all `k!` matchings between them), the same "exact,
never approximate, bounded rather than silently slow" posture
`analytics.lineup_optimizer.MAX_ASSIGNMENT_PERMUTATIONS` already
established for this exact class of problem. The real cost is
`C(m, k) * C(n, k) * k!` for roster sizes `m`/`n`; Stage 3 reuses the same
literal cap value (`500_000`) for the same reason
`analytics.lineup_optimizer` gives: "a roster that large would be a data
anomaly worth surfacing, not something to solve approximately without
saying so." A real, current example this matters for: one real team in
this project's own database has 13 rostered players (`Team 13082957`,
"Mark It Up"). `C(13,5)^2 * 120 ~= 2.0e8`, far over the cap -- if a captain
marks that many players available at once, Stage 3 reports BLOCKED("too
many available players/opponents to search exactly -- narrow tonight's
availability first") rather than hanging or approximating. This is exactly
what the availability checkboxes (§2, Stage 2) are for.

## 7. Testing plan

- **Unit tests for the score** (`tests/test_lineup_lab.py` or added to
  `tests/test_pairing_evidence.py`'s own suite): monotonicity in skill
  level and in record strength; UNKNOWN always scores `None`; a DIRECT
  single-game record stays close to the INDIRECT baseline (regression test
  pinned to the §4 worked examples, so a future change to
  `analytics.head_to_head`'s constants cannot silently break Stage 3's
  calibration assumption without a visible test failure).
- **Scenario tests for the assignment**: a full 5-vs-5+ scoreable roster
  producing a legal approved lineup; an illegal maximum-score assignment
  correctly falling back to the best *legal* one; a roster with some
  UNKNOWN-only players correctly leaving them unassigned rather than
  matched; a roster with fewer than 5 scoreable pairings producing a
  correctly labeled partial result; the reconciliation invariant (assigned
  + unassigned = available) on every scenario.
- **Regression test against heuristic drift**: a fixed, hand-checked
  fixture (mirroring the §4 table) asserting the exact expected assignment
  and total score, so an unnoticed change to the scoring or search logic
  is caught even if no single unit test targets that exact change.
- **Bound test**: a roster sized to exceed `500_000` attempts raises a
  clear, real error rather than hanging or truncating silently.

## 8. Limitations, stated plainly

- No lineup alternative beyond the single approved best lineup is
  introduced here -- §10's rule requires each additional objective to be
  separately written down and validated; this amendment covers only the
  one objective docs/captain_first_edge_experience.md §9 already names
  ("approved best lineup").
- The 4-player/19-skill fallback lineup is out of scope, matching
  `analytics/lineup_legality.py`'s own stated scope.
- The `500_000`-attempt bound means a captain with an unusually large
  current roster must narrow availability before Stage 3 can compute a
  result -- a real, disclosed limitation, not a silent one.
