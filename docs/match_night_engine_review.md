# Match Night Engine (M3): review, Captain Decision Review and risk register status

## GPT read-only review of implemented M3 — 2026-10-18, source 5101bc9

**M312 — known opponent budget is absent from the response model; decision-changing limitation.**
The implementation and existing tests below are acknowledged. A new source-executed case shows a
remaining gap in the claim that the engine protects against the opposing captain's most damaging reply.
The response set is unconstrained by their remaining skill budget. No engine fix is made in this review.

Synthetic scenario: two matches remain. Our A/B/C are SL4 with a supplied remaining budget of eight.
Their X/Y/Z are SL7/SL7/SL2 with a known remaining budget of nine. This is an explicit arithmetic
constraint, not a claim that a particular league/tournament rule profile is completely verified.
X and Y cannot both play; either can play alongside Z.

| Existing confidence utility | X (7) | Y (7) | Z (2) |
| --- | --- | --- | --- |
| A (4) | Caution (-3) | Caution (-3) | Thin (1) |
| B (4) | Thin (1) | Solid (3) | Strong (6) |
| C (4) | Solid (3) | Strong (6) | Unknown (0) |

An explicit two-round enumeration follows our lead / their response / their lead / our best remaining
response. Without their budget, lead values are A=0, B=2, C=1 and actual `match_plan` selects B.
Restricting opposing continuations to the known budget gives A=3, B=2, C=1: A is preferred under
the implementation's *unchanged* utility. These are utility totals, not match points, expected wins or
probabilities. The difference arises from treating their X+Y continuation as possible despite its
SL total of 14 exceeding nine. This can spend a better counter unnecessarily against an impossible reply.

**Source cause:** `analytics/match_night_engine.py::_Night.solve` filters our moves through `legal`;
the opposing candidates are all remaining roster bits. `match_plan` accepts our `cap` and `used` only.
There is no place to pass the known opposing remaining budget. Python/phone agreement and optimality
against a reference search with the same relaxed opposing action set do not test this missing constraint.

**Smallest improvement to evaluate:** accept/filter an explicitly known opposing remaining budget and
needed completion when building their response set; when that scope is unknown, identify the plan as
conservative under an unconstrained-opponent assumption. Do not guess their cap or report a legal-game
optimum from our budget alone. This is a proposed correction, not permission to implement one.

**Validation:** `test_m312_implemented_plan_can_choose_differently_when_opponent_budget_is_known` in
`tests/test_match_night_design_review.py` checks the actual implemented lead and both exhaustive
two-round evaluations. All twelve design-review cases passed in 0.29s. Initial exploration of a two-by-two
case found no distinct lead reversal; the three-player/two-round case above establishes the actual
decision difference. No unchanged 764-case suite was rerun. Earlier reported verification remains scoped
to its tested rules; this finding prevents a blanket recommendation-quality acceptance claim.

---

Claude, 2026-10-18. M3 is built on branch `claude/confidence-levels`. No probabilities, odds or machine learning
anywhere. Every recommendation names its evidence.

## What a captain gets

M3 is the primary decision tool. On the phone and in the HTML it re-plans after every ✓ Sent, availability
change and cap edit. The Captain Packet prints the start-of-night plan, which is retired as soon as anything
changes.

| Captain question | M3 output |
|---|---|
| Who do I lead with? | **Lead pick**, with why: which strong answers it keeps, and their most damaging reply. Equally good leads are disclosed. |
| Who do I answer with? | **Response table**: "If they put up Xavier → Paul (Strong)". |
| What does this choice cost later? | Each response notes when the stronger answer tonight is held back: "Dana is the stronger answer tonight, but sending her now costs more later; keep Dana". |
| Who do I hold? | **Hold-backs**: "our only Strong answer to Zed — 9-1 in 10 meetings". |
| Who can I sacrifice? | **Lowest-cost concessions**: planned pairings worth least, using the players we lose least without. |
| Tonight's game plan? | The **game plan** both ways (we lead / they lead), the **best-case board** and the **safest board**. |
| How much do I trust it? | **Match confidence** (Strong/Solid/Thin/Unknown/Conflicted/Caution counts), **fragility** (one player, thin pairings) and **cap safety** under the entered cap. |

## How it decides

1. **Pair value.** Each pairing gets a captain confidence level from recorded evidence:
   - the direct record and its depth;
   - a skill-level change since the pair last met;
   - both players' league-scoped lifetime records in the format;
   - shared opponents.

   The levels are Strong, Solid, Thin, Unknown, Conflicted and Caution. The full rule is in
   `analytics/ultimate_coach_confidence.py`.
2. **Planning weights.** Strong 6, Solid 3, Thin 1, Unknown/Conflicted 0, Caution −3.
   - These come from how much more often each level won its next game in the 15-year replay, scaled so
     Thin = 1.
   - 8-Ball: +18 / +8 / +3 / 0 / −8 points from even. 9-Ball: +11 / +4 / +1 / 0 / −4.
   - They are never shown to captains.
3. **Objective.** The night's total. An APA team match is decided by points across its games. The safest
   board (best worst pairing first) is shown alongside for a "steady" night.
4. **Opponent model.** Put-ups alternate. The other captain is assumed to make the choice that hurts us most
   (minimax), so the plan holds up against their best reply.
5. **Skill cap.**
   - Only lineups that fit the entered cap are considered.
   - A player with no captured SL is never counted as 0. Their own cost is unverifiable, so the cap check is
     reported incomplete, but the rest of the night must still fit.
   - With no cap entered, none is assumed (the same as the existing budget rule).
6. **Deterministic.** Candidates are tried in roster order, and only a strictly better value replaces a
   choice, so Python and the phone produce identical plans.

## Evidence that it does what it says

| Check | Result |
|---|---|
| Plan values vs an independent game-tree search, 200 random nights | Exact match (`tests/test_match_night_engine.py`) |
| Best-case and safest boards vs brute force, 120 random nights | Optimal |
| Phone (JS) vs Python plans, 61 random nights plus fixture states | Identical |
| Confidence levels vs 15 years of singles games (843k rows) | Ordered Strong 68.1% > Solid 57.7% > Thin 53.3% > Unknown 50.0% > Caution 42.3% next-game wins (8-Ball); 9-Ball the same order |
| Cap legality | Every plan and board fits the cap. An impossible night yields "No legal send fits the entered skill cap", never an over-cap lead. |
| Speed | 8-vs-8 full plan in under 0.75 s in Python; faster on the phone |
| Register scenarios RQ01–RQ12 | 12 executable cases (`tests/test_captain_decision_review.py`) |

### Scale sensitivity: 300 synthetic nights, 5–8 a side, cap 23, replay level mix

Agreement with the default (`docs/recommendation_review/match_night_scale_sensitivity.json`):

| Scale | Same lead pick | Same full response table |
|---|---|---|
| 4/2/1/0/−2 | 93% | 77% |
| 3/2/1/0/−1 | 67% | 39% |
| 6/3/1/0/−6 | 78% | 49% |

The scale is a real policy dial. The default is anchored to history rather than chosen by feel.

## Captain Decision Review: risk register status

| RQ | Scenario | Before M3 | With M3 | Status |
|---|---|---|---|---|
| 01 | A 1-0, B 8-2 vs X | A first (win % first) | A Thin, B Strong; the answer to X is B | **Resolved** |
| 02 | A 1-0; B no direct but 50-15 overall | B "unknown, not weak" | B Strong when X also has a real record; when X's record is thin there is no basis, and A's 1-0 stands | **Resolved, conservatively** |
| 03 | 6-3 with recent losses vs 3-2 with recent wins | A first | Both Solid; dates shown; captain decides | **Evidence-settled.** The replay found recency barely matters (54.4% vs 53.5%). |
| 04 | A 4-0 at an old SL vs B 3-1 at tonight's SL | A first, SL caveat shown | A drops to Thin; B Solid; answer B | **Resolved** |
| 05 | Blind: A 1-0 vs X; B 0-1 vs X but 8-2 vs Y and Z | A named for the fewest losses | B held as the only Strong answer to Y and Z; the lead is not B | **Resolved** |
| 06 | Blind count tie: A 1-0 ×2 vs B 8-2 ×2 | Roster-order tie | Lead A, keep B for a Strong pairing | **Resolved** |
| 07 | Save warning on a 1-0 vs a 5-0 future edge | Same warning | A thin edge is spent now; a deep edge is kept, with the cost stated | **Resolved** |
| 08 | A 5-0 vs X now; thin 1-0 vs future Y | A, plus a save warning | Send A to X; no cost-later warning | **Resolved** |
| 09 | One loss: X beat A once | Live threat | A vs X is Caution and the plan prefers an unknown alternative | **Evidence-settled.** Losing records over 1–2 meetings won 44.0% next, vs 41.7% for deeper ones, so a single loss is a real caution (`replay_thin_caution_split.json`). |
| 10 | X 10-0 vs A, 0-2 vs B | Roster threat | The pair levels decide: answer B | **Resolved** |
| 11 | Strong overall record but one direct loss | Excluded with deep losers | Conflicted (0), chosen over a deep Caution | **Resolved** |
| 12 | Two-sided shared-opponent edge, no direct record | Unordered | Thin (1–2 shared) or Solid (3+), used in the plan | **Resolved** |

No substantial captain-disagreement scenario in the register remains unaddressed. Two are evidence-settled
rather than changed (RQ03 recency, RQ09 single loss).

## Limits, stated plainly

- **Put-up order is not in the captured data.** The full plan cannot be replayed against past nights; only
  its building blocks (levels, boards) are validated against history.
- **The other captain is modelled as worst-case.** A real captain may be kinder; the best-case board shows
  that side.
- **Their skill cap is not modelled.** Their cap is unknown in our data; their choices are treated as
  unconstrained.
- **The replay used the broad staging archive.** Re-run `scripts/replay_confidence_levels.py` on the
  identity-verified snapshot before release.
- **Next Send's evidence list keeps its existing order.** The plan's response table is the recommendation;
  the list stays as the evidence view.

## Decisions for Paul (defaults are in place; none blocks use)

1. **Planning weights.** Keep the history-anchored 6/3/1/0/−3, or choose another scale. The sensitivity
   table shows it matters.
2. **Objective.** Total (default) vs safest board as the headline. Both are shown today.
3. **Default cap.** Assume the standard 23 when none is entered, or keep "no cap assumed" (current).
4. **Next Send list order.** Keep win-percentage-first as the evidence view, or order it by confidence level
   to match the plan.
