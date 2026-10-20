# Match Night Engine (M3): review, Captain Decision Review and risk register status

## GPT verification of Claude F1/F2/F3 — 2026-10-20

Source checkpoint 9fbabc4. Review only; no production correction or ranking/utility change.

**F1:** Claude's RQ13 executes successfully and demonstrates overlap between designated hold players
and response players. This proves the data overlap, not that every captain interprets the label as a
prohibition. The proposed conditional-matchup wording is a presentation candidate, not an engine policy.

**F2: rendered conflict verified.** A new sanitized browser fixture uses our Ann/Bea and opposing Cam/Eve,
all SL4. Ann is 5-0 vs Cam and 2-0 vs Eve; Bea is 0-3 vs both. No broader career form is supplied.
At both 390 and 1280 pixels, after explicitly selecting the teams and Cam's put-up chip, Next Send's
visible plan answer is Ann (Strong), while that same player's evidence row says **consider saving**
as our only favorable direct option vs Eve (2-0 in 2 meetings). No page errors/global overflow.
This verifies the conflicting instructions in the actual rendered DOM, not a physical-device test or
visual screenshot review. The initial browser setup left both team selectors empty and timed out before
any recommendation; corrected explicit selection reaches the intended case. No setup timeout is a pass.
The fixture differs from Claude's prose example but proves the same decision-context failure with
complete recorded inputs. Suppression versus contextual integration remains a proposed presentation
choice; do not silently remove raw evidence or assert an unmeasured win benefit.

**F3: finding valid, original fixture and smallest-fix proposal need correction.** Executing RQ14's
confidence inputs gives Alice **Strong (6)** vs Xavier (5-2 in seven meetings), Bob **Solid (3)**
(4-2 in six), not equal Solid answers as its comment claims. The current test passes without checking
that premise. A new exact tie uses 4-2 in six meetings for both vs Xavier: both Solid (3), Alice 0-3
vs Yvonne (Caution -3), Bob 6-1 vs Yvonne (Strong 6). The plan answers Alice to Xavier and emits no
cost-later explanation. Sending Alice then Bob totals 9 existing utility; reversing them totals 0.
Those totals are not match points, expected wins or probabilities.

In this true-tie roster order, `naive` is already Alice, equal to the chosen plan answer. Therefore
changing only `>` to `>=` still fails the separate `naive != i` guard. A correction candidate must
inspect equal-or-better *alternative* answers and their continuation cost, rather than only the single
roster-first naive answer. This can improve explanations without changing which answer is selected;
no implementation or policy authorization is inferred from the audit suggestion.

Validation: Claude's RQ13/RQ14 characterization cases passed (2 in0.16s); the new F2 browser and corrected
F3 characterization cases passed together (2 in3.72s,14 unchanged design cases deselected). These pass
counts establish reproduced behavior, not acceptance or improved match outcomes. Existing suites were
not rerun. M313 remains open separately; M312 remains closed.

## M313 — hold-back explanation can protect an opponent excluded by the known cap

GPT source-executed review, 2026-10-20, checkpoint a33d951. **Open recommendation-context finding.**
This is distinct from closed M312: the response search enforces the opponent budget correctly,
but the hold explanation still examines all opposing roster entries.

Two games remain. Our A/B/C are each SL4; our cap is 8. Their X/Y/Z are SL7/SL2/SL2;
their supplied remaining budget is 8. X plus either remaining teammate costs 9, so X cannot leave a complete two-player lineup. These are synthetic arithmetic
inputs, not an assertion about a particular format's valid SL range or tournament rules.

| Existing evidence utility | X | Y | Z |
| --- | --- | --- | --- |
| A | Caution (-3) | Solid (3) | Unknown (0) |
| B | Unknown (0) | Strong (6) | Solid (3) |
| C | Solid (3) | Strong (6) | Thin (1) |

Actual output: lead B (C equally good); responses only to Y and Z. Neither game plan nor board
contains X. However, the hold section says **C — our only Solid answer to X** and its covers list
is exactly X. Paper `plan_text` repeats this reason; the browser engine returns the identical plan
at 390 and 1280 pixels. This is browser-engine execution, not a visual review of a rendered card.

Why a captain may disagree: holding C to answer X cannot serve tonight's supplied budget. C may
still be useful against Y or Z; the demonstrated error is the stated reason, not proof that C must
be sent or that B is the wrong lead. The UI turns this into actionable hold-back guidance, so it
is more than a vocabulary difference. `covers()` and its fallback margin explanation iterate all
opponents instead of the feasible opposing put-ups used by the search. The same loop exists in
Python and JavaScript. Printed hold text consumes the Python output directly.

Smallest correction candidate for Claude: derive hold coverage and fallback reasons from feasible
opponent continuations, preserve the solver/utility/rankings, and use a neutral plan-dependency
reason if no feasible named coverage supports the hold. Verify the reason remains truthful when
cap/availability changes, with feasible coverage retained. No production correction is made here.

Validation: two new characterization cases passed in 3.88s (`-k m313`); 12 unchanged design cases
were deselected. Passing means the open defect was reproduced, **not** recommendation acceptance.
An initial SL10 stress case also reproduced the issue; the final case uses SL7/2/2. A sandboxed final-case browser run stalled after its Python case and was interrupted; authorized browser execution then completed both cases. No stalled run is counted as a pass.
No existing suite, native export, real fixture, or winning-effectiveness validation is claimed.

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

## M312 (GPT review): opponent budget, resolved

The review found that the response model ignored the opponent's remaining skill budget. So a lineup they
could not legally field could still shape our lead: B instead of A in the review's case.

The entered cap now binds both teams, as APA's cap does. Their remaining budget is the cap minus the skill
levels of their players already played. Their replies, lead responses, game plans and both boards are limited
to lineups they can field, with the same unknown-SL rule as ours. If their captured skill levels cannot fit at
all, the plan falls back to the conservative unconstrained opponent rather than planning nothing. With no cap
entered, the plan says it assumes any of their players can still be put up.

`test_m312_known_opponent_budget_changes_the_lead` reproduces the review's case (B unconstrained, A
budgeted). The independent game-tree search now includes random opponent budgets on all 200 nights, and the
phone-vs-Python parity covers them too.

## Limits, stated plainly

- **Put-up order is not in the captured data.** The full plan cannot be replayed against past nights; only
  its building blocks (levels, boards) are validated against history.
- **The other captain is modelled as worst-case.** A real captain may be kinder; the best-case board shows
  that side.
- **Their budget follows the entered cap.** A league whose local rules give the two teams different caps
  needs that entered separately (not supported yet).
- **The replay used the broad staging archive.** Re-run `scripts/replay_confidence_levels.py` on the
  identity-verified snapshot before release.
- **Next Send's evidence list keeps its existing order.** The plan's response table is the recommendation;
  the list stays as the evidence view.

## Oct-20 audit: three new recommendation-quality findings

Audited by Claude, 2026-10-20. No probabilities, no policy changes. Executable test cases in
`tests/test_captain_decision_review.py` (RQ13, RQ14). F2 requires a browser test; documented below.

---

### F1 — "Hold back" label contradicts the response table for the same player (HIGH)

**Scenario.** Three games remain; the plan leads Carol (neutral) to keep Alice and Bob for their
designated matchups. Plan output:

- **Lead**: Carol
- **Hold back**: Alice — our only Strong answer to Xavier and Yvonne
- **Hold back**: Bob — our only Strong answer to Zed
- **Response table**: If Xavier → Alice (Strong) · If Yvonne → Alice (Strong) · If Zed → Bob (Strong)

**Actual recommendation.** "Hold back Alice" appears directly alongside "If Xavier → Alice." Both come
from the same plan and are correct: holds designates Alice for Xavier/Yvonne; the response table is the
execution instruction. But the two sections look contradictory.

**Evidence.** `test_rq13_hold_back_and_response_table_name_the_same_player()` reproduces it.

**Captain disagreement.** A captain reads "Hold back Alice" as "don't use Alice tonight," then sees the
response table say "send Alice when Xavier shows up." They may suppress Alice from the Xavier response to
honour the hold instruction, giving up a Strong pairing for an Unknown one.

**Frequency.** Every night the plan leads a neutral player and reserves strong players for responses —
the standard APA "hold your best for whoever they put up" strategy.

**Smallest correction (presentation only, no engine change).** Relabel the "Hold back" section to
"Designated answers — keep for these matchups" and change each item from "Alice — our only Strong answer
to Xavier" to "Alice → Xavier / Yvonne (Strong)". The response table then reads as the execution of the
designation, not a contradiction of it. The `plan_text()` output for paper/workbook uses the same data;
update its holds line in the same change.

---

### F2 — Save warning fires on the plan-recommended player, contradicting the plan answer (MEDIUM)

**Scenario.** Carol has led; Xavier is on the board. Captain opens Next Send, selects Xavier:

- **Plan answer box** (top of Next Send): "Alice (Strong) — Match Night Plan answer"
- **Evidence list** immediately below: "🥇 Alice — 3-0 direct · **consider saving Alice for Yvonne**
  (2-0 in 2 meetings)"

**Actual recommendation.** The plan says send Alice now. The save warning on the same player says hold
her. Both come from the product; neither is wrong in isolation. The plan has already priced in that Alice
won't be available for Yvonne.

**Evidence.** Reproducible fixture: three games remaining, Alice is Strong vs both Xavier (3-0) and
Yvonne (2-0); she is the only category-G (favorable direct) option vs Yvonne; Carol leads; plan response
table shows Alice for Xavier. The Next Send `onlyGreen` check fires because exactly one of our remaining
players has category-G vs Yvonne and that player is Alice.

**Captain disagreement.** Captain sees plan say Alice, save warning say hold Alice. May override plan and
send Bob (Thin/Solid) instead of Alice (Strong) to avoid "wasting" Alice on Xavier. Gets a weaker pairing
for Xavier and still loses Alice to Yvonne in the next round with no improvement.

**Frequency.** Any night a strong player has a good record vs two future opponents and the plan designates
them for the first one. Common for players with multiple strong matchups.

**Smallest correction (UI-only, no engine change).** In `wrPlanAnswer`, when the plan answer for the
current opponent is player P, suppress the save warning for P in the evidence list rendered below it (the
`wrNextSendEvidence` / `wrSaveWarning` call). Add a single line to the plan answer box: "Save warnings
below do not apply to the plan recommendation — the cost has already been weighed." Alternatively, move
the save warning into the plan answer itself: "Alice (Strong) — spending Alice here forgoes the save
opportunity vs Yvonne; the plan judges this worthwhile."

---

### F3 — cost_later is silent when tonight-values are equal but futures differ (LOW-MEDIUM)

**Scenario.** Alice and Bob are both Solid (3 points) vs Xavier. Bob is Strong (6) vs Yvonne; Alice is
Caution (−3). Plan leads Alice (keeping Bob for Yvonne). If they put up Xavier first, the plan sends Alice
— but `cost_later` is blank.

**Actual recommendation.** Response table: "If Xavier → Alice (Solid)" — no cost_later text.

**Evidence.** `test_rq14_cost_later_is_silent_when_tonight_values_are_equal_but_futures_differ()`.
The condition that fires cost_later is `naive != i and pair(naive, j) > pair(i, j)`. When Alice and Bob
have identical pair-values vs Xavier (both Solid = 3), the `>` comparison is False and the text never
generates, even though sending Bob tonight costs 9 planning points (6 + 3) for the rest of the night.

**Captain disagreement.** Captain sees Alice and Bob are equal vs Xavier, sees no explanation, and may
send Bob (roster familiarity, hunch) — giving up the Strong pairing vs Yvonne.

**Smallest correction (engine change, needs Paul's approval).** Change the `cost_later` condition from
`night.pair(naive, j) > night.pair(i, j)` to `night.pair(naive, j) >= night.pair(i, j)`. Also update
the generated text from "B is the stronger answer tonight" to "B is an equally good answer tonight"
when the values are equal. This lets the explanation fire: "Bob is an equally good answer tonight, but
sending them now costs more later; keep Bob." A new assertion in `test_rq14` can verify the corrected
behaviour once the fix is approved.

---

## Decisions for Paul (defaults are in place; none blocks use)

1. **Planning weights.** Keep the history-anchored 6/3/1/0/−3, or choose another scale. The sensitivity
   table shows it matters.
2. **Objective.** Total (default) vs safest board as the headline. Both are shown today.
3. **Default cap.** Assume the standard 23 when none is entered, or keep "no cap assumed" (current).
4. **Next Send list order.** Keep win-percentage-first as the evidence view, or order it by confidence level
   to match the plan.
5. **F1 fix** (presentation): relabel "Hold back" → "Designated answers — keep for these matchups."
6. **F2 fix** (UI): suppress save warning for the plan-recommended player in the Next Send evidence list.
7. **F3 fix** (engine): extend cost_later to equal-tonight/different-future cases.
