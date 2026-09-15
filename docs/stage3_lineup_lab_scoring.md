# Stage 3 correction: Lineup Lab scoring and assignment

Dated 2026-09-15. This amendment supersedes the scoring claim introduced by
commit `27342e5`. It responds to the fail-closed pre-implementation audit on
Issue #14 before Lineup Lab is exposed in the captain-facing HTML.

This is an analytics contract, not a claim that the view is ready. The static
HTML does not render Lineup Lab yet. A later wiring commit must pass its own
audit, including browser/Python parity for availability changes.

## 1. Why the first score was rejected

Commit `27342e5` ranked DIRECT pairings by
`PairingEvidence.modeled_win_probability`. For DIRECT rows that value comes
from `analytics.head_to_head.win_probability`, which blends the skill gap with
the pairing's historical record.

That arithmetic is transparent and unit-tested, but the historical-record
term is not validated against future rematches. The repository's own
`docs/prediction_validation.md` says Analysis B has zero held-out predictions:
all 106 captured pairings have met exactly once. Worked examples showing that
a formula returns 64.0% or 55.6% prove its arithmetic, not its calibration.
The combined DIRECT probability therefore cannot yet select an "approved best
lineup."

DIRECT history is still real evidence. Lineup Lab carries its observed win
rate, distinct-match count, modeled probability, and model source through to
the result for transparent display. It simply does not use the unvalidated
history term to rank assignments.

## 2. The approved selection score

The selection score is the already-shared skill-only function, applied to the
two canonical current-roster skill levels in the matrix:

```
lineup_score(pairing) =
    skill_only_win_probability(
        pairing.player_skill_level,
        pairing.opponent_skill_level,
    )
        when the label is DIRECT or INDIRECT and both inputs exist
    None
        when the label is UNKNOWN or either current skill input is missing
```

`analytics.head_to_head.skill_only_win_probability` is the exact production
function graded in `docs/prediction_validation.md`. Its only input is the real
current skill gap:

```
logit(p) = 0.40 * (our current skill level - opponent current skill level)
p = clamp(sigmoid(logit(p)), 0.02, 0.98)
```

On the current 106-game sample it has Brier score 0.2416 versus 0.25 for a
50/50 baseline, log loss 0.6755 versus 0.6931, and 56.6% accuracy. This is
modest evidence, not permission to overstate precision; the Data Coverage
view must carry the documented small-sample caveat.

DIRECT and INDIRECT use the same selection score when their current skill
inputs match. A historical 10-0 DIRECT record cannot change the score until
the record term has real walk-forward validation. UNKNOWN never receives a
neutral 0.5 substitute.

## 3. Assignment objective

For the currently available players on both sides:

1. Build a bipartite graph containing only pairings with a non-`None`
   `lineup_score`.
2. Find the maximum scoreable matching size `k`, capped at the standard five
   lineup positions.
3. Among all matchings of exactly `k`, maximize the sum of `lineup_score`.
4. If `k` is less than five, return a clearly blocked partial result. Do not
   pad it with UNKNOWN pairings and do not call it approved.
5. If `k` is five, apply the real 23-rule legality check. Prefer the
   highest-total-score legal matching. If no legal five-player matching
   exists, return a blocked result and show the highest-scoring illegal
   matching only for transparency.

The total is a sum of per-pair probabilities, so it is the expected number of
pairing wins under the model by linearity of expectation; independence is not
required for that expectation. There are no new weights, danger thresholds,
or alternative objectives.

## 4. Legality is fail-closed

`analytics.lineup_legality.check_lineup_legality` is the sole legality rule:
exactly five distinct one-of-ours players with a combined current skill level
of at most 23.

Only our players' current skill levels enter that verdict. An opponent's skill
level is required to compute the selection score, but it is not an input to
our 23-rule total. A complete assignment whose legality cannot be evaluated is
blocked with `is_legal=None`; it is never returned as approved.

The four-player/19 fallback remains out of scope, matching the existing
legality module's documented boundary.

## 5. Availability must recompute, not merely hide

`analytics.lineup_lab.solve` accepts two separate inputs:

- `unavailable_our_player_ids`
- `unavailable_opponent_player_ids`

It validates each id against the corresponding side, removes those vertices,
and recomputes maximum matching, exact score optimization, legality, and both
unassigned lists from scratch. An unavailable id from the wrong side fails
closed instead of colliding in a shared id set.

The current Stage 2 HTML stores availability only in browser state. Therefore
the Python solver is not yet wired into that page. A static-page integration
must either precompute the selected availability states or implement the same
bounded exact algorithm in the browser and prove parity against Python with
shared fixtures. Merely rendering the build-time full-roster result and hiding
rows afterward is forbidden.

## 6. Matrix and result invariants

Before solving, Lineup Lab independently rechecks Stage 1's matrix:

- expected and classified pair keys reconcile exactly;
- stored label counts equal recomputed counts; and
- every pairing matches the matrix format and session.

For the availability-filtered result:

- assigned and unassigned one-of-ours players are disjoint and together equal
  all available one-of-ours players represented in the matrix;
- assigned and unassigned opponents satisfy the mirror invariant; and
- each selected `(player_id, opponent_id)` pair has exactly one real matrix
  row and one non-missing validated selection score.

## 7. Exact-search bound

Maximum matching size is computed first with a deterministic bipartite
augmenting-path search. Only then is the exact-search cost calculated:

```
C(our_available, k) * P(opponents_available, k)
```

The existing `500_000` exact-assignment cap is reused. Above it, the solver
raises `LineupLabError` and asks the captain to narrow tonight's availability;
it never hangs, truncates, or silently approximates. A large but sparse graph
with maximum matching size one is assessed at `k=1`, not incorrectly blocked
as though a five-pair matching existed.

## 8. Pinned examples

The tests call the shared production skill-only function directly:

| Current skill gap | Selection score |
| --- | ---: |
| 5 vs 4 | 59.9% |
| 6 vs 3 | 76.9% |
| 4 vs 4 | 50.0% |

For equal current skills, a DIRECT row with a high history-derived modeled
probability and one with a low history-derived modeled probability receive the
same 50.0% lineup score. Their different real histories remain visible as
evidence, but cannot steer the assignment before validation.

## 9. Test obligations

`tests/test_lineup_lab.py` covers:

- identical current-skill scoring for DIRECT and INDIRECT;
- proof that the unvalidated DIRECT history term cannot change selection;
- UNKNOWN and missing-current-skill rows never receiving a neutral default;
- legal, illegal-with-legal-fallback, partial, and fully blocked scenarios;
- side-specific availability recomputation and unknown-id rejection;
- matrix key/count/scope validation;
- assigned/unassigned reconciliation on both sides; and
- exact-search rejection for a dense oversized graph while allowing a large
  sparse graph whose real maximum matching is small.

No alternative lineup is introduced. No Lineup Lab advice may be rendered in
the HTML until this corrected analytics contract and its wiring pass the
Issue #14 audit cycle.
