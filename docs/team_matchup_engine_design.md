# Team matchup engine: "Best Scenario Match Night" (design proposal)

**Current GPT review status, 2026-10-18: NOT implementation-ready.** The original proposal below is
preserved for discussion. The executed review at the end identifies unresolved objective/utility rules,
unenforceable static boards, missing declaration-order evidence, and a board-count correction. Its phrase
"validated confidence levels" is not accepted as validation of a captain-selection objective. No M3 solver,
level scorer, recommendation change or probability model has been implemented.

Claude, 2026-10-18. Design only; nothing is implemented. No win probability, odds or machine learning. Paul decides
what is built.

## What a strong APA captain actually wants

A strong captain does not want a fixed board. In APA singles play the two captains **alternate putting players
up**, so the opponent chooses half the matchups. A board like "Paul → Xavier, Rashael → Yara" survives only
until the other captain sends someone else. Before and during a match, a strong captain is answering five
questions:

1. **Who do I lead with** when we put up first, blind?
2. **Who answers each of their likely put-ups**, and what does that answer cost me later?
3. **Who must I hold back**, because they are my only good answer to someone dangerous, or because I need
   their skill points later?
4. **Does every plan fit under the skill cap** (23 in standard 8-Ball/9-Ball, or as configured) with the
   players I have tonight?
5. **Where am I conceding a game on purpose**, and is that the right place to concede it?

So the output is not one board. It is **a best-case board plus a response plan** that recalculates after
every put-up.

## Building blocks (all from recorded evidence)

**Pair value: how good is our player `i` against their player `j`?** It uses the validated confidence levels
in `docs/captain_confidence_framework.md`: direct record and depth, overall record, shared opponents, skill-level
change and recency, with the reasons shown. Recency barely mattered in the replay, so it stays a light
adjustment.

**Skill budget.** Each player's current captured SL counts against the configured cap. A missing SL means the
plan is "incomplete — check by hand". It never counts as 0.

**Availability.** It comes from the existing Lineup Lab marks. Unknown availability stays eligible and is
labelled.

## 1. Formula options for the pair value

| Option | Pair value | Pros | Cons |
|---|---|---|---|
| **A. Level points** (recommended first) | Strong +2, Solid +1, Thin +0.5, Unknown 0, Conflicted 0, Caution −1 | Readable; checked against 15 years of games; no fitted weights | Coarse: two Strongs tie |
| **B. Evidence score** | Sample-weighted direct record `(w+1)/(g+2) − .5`, plus overall-form gap, plus shared-opponent edge when there is no direct record | Separates within a level; uses the strongest signals | Needs one stated blend; must pass a held-out season before use |
| **C. Legacy weighted formula** (`docs/lineup_optimizer.md`) | `0.50·matchup + 0.30·win_probability + 0.15·confidence + 0.05·risk` | Already built | Relies on a win-probability term the project chose not to trust; tuned weights; ignores put-up order and the cap |

**Recommendation.** Start with **A**, and use **B** only to break ties inside a level. Retire **C** from captain
decisions. Every option shows the reasons, never a percentage.

## 2. Ranking methods: choosing a whole night

### M1. Best-case board

The single best one-to-one assignment of our available players to their roster, under the cap.
- Maximize the total pair value. Tie-breaks: fewer Caution pairs, then more Strong pairs.
- A roster of up to 8 against 8 is about 6,720 legal 5-player boards, so exact search is instant.
- This is the "Paul → Xavier, Rashael → Yara" board the brief asked for. It is the plan if the other captain
  cooperates, and the shape the captain is steering toward.

### M2. Safest board (maximin)

Maximize the **worst** pairing first, then the total.
- This is what a captain wants when one bad loss sinks the night, for example in a must-win tournament round.
- It avoids boards that win four big and concede one disaster.

### M3. Put-up game plan (recommended core)

Model the night as it is played. The put-ups alternate, and each side picks from who is left, under the cap.
- For every state, the plan is the response that keeps the best board still reachable after the other
  captain's most damaging reasonable choice. The state is who is left on each side, the points used and
  whose turn it is.
- That is a minimax search over at most 8 × 8 players and 5 rounds. It is small enough to solve exactly in
  the browser and workbook build.
- It produces three things captains ask for directly:
  - **Lead pick.** Who to put up blind, chosen by what it leaves us against every reply, not just by records.
    This replaces today's "fewest concerning records" rule.
  - **Response table.** "If they put up Xavier, send Paul. If Yara, send Rashael…"
  - **Hold-back list.** "Keep Dana: she is our only Strong answer to Zed, and sending her now drops Zed to
    Caution."
- It explains its sacrifices: "concede Quinn vs Xavier (Caution) to keep Paul for Yara (Strong)".

M3 can lean toward M1 (total) or M2 (worst case). The captain chooses with a "steady" or "go for it" switch.

## 3. Confidence methods for a whole night

The night's confidence is built from the pair levels, never a probability.

| Method | What the captain sees | Use |
|---|---|---|
| **Level count** | "Board: 2 Strong, 2 Solid, 1 Thin" | At-a-glance trust in the plan |
| **Weakest link** | "Weakest: Quinn vs Xavier — Caution (0-3)" | Where the night can go wrong |
| **Fragility** | "If Yara is unavailable, the plan changes 3 sends" or "One Thin pairing decides the lead pick" | Whether the plan depends on thin evidence or one assumption |
| **Budget slack** | "Board uses 22 of 23; one SL-change makes it illegal" | Cap risk, with incomplete SL data flagged |
| **Evidence coverage** | "12 of 25 pairings have no evidence" | How much of the night is the captain's own read |

The plan confidence is the **weakest link plus the level count**. A board of four Strong and one Caution is not
a Strong plan. It is a Strong plan with a known hole.

## 4. Captain workflow

**Before match night, at home or on the phone:**
1. Mark availability. Unknown stays eligible and labelled.
2. Review the **best-case board** (M1) and the **safest board** (M2) side by side.
3. Read the **hold-back list** and the **weakest link**. Add coach observations where your own read differs.
4. Print the Packet. It carries the lead pick, the response table and the hold-back list.

**At the table:**
1. **Coin toss.**
   - If we lead: send the **lead pick**. Its reason and level are shown with it.
   - If they lead: tap who they put up, and the **response** appears with its level, its cost ("uses our
     last Strong answer to Zed") and the alternatives.
2. After each game, tap **Sent** for both players. The plan recalculates for who is left and the points used.
3. Override at any time. The engine re-plans from the captain's choice; it never argues.

**After the match:** results flow back through the normal refresh. The record and the levels update, and nothing
is retuned by hand.

## What the engine must never do

- Show win probability, odds or a "projected score".
- Treat unknown as weak, or a missing skill level as 0.
- Present a board as legal when an SL is missing or the format rules are not configured.
- Hide its reasons. Every recommendation names the evidence and its level.

## Validation before building

1. **Pair values.** Already checked: the confidence levels order real outcomes in both formats
   (`docs/captain_confidence_framework.md`). Re-run on the identity-verified snapshot.
2. **Board methods.** Replay past team matches.
   - For each historical match, build M1, M2 and M3 from earlier results only.
   - Compare the outcome of the pairings that actually occurred with each method's level for those pairings,
     and how often the method's lead pick matched a winning lead.
   - Put-up order is not stored in the current data, so only the board, not the full game plan, can be
     replayed directly.
3. **Captain test.** Have a strong captain run one live league night with the response table in hand. Record
   every override and why. The overrides show what the engine is missing.

## Open decisions for Paul

1. **Default.** Should the default be **M3** with the "steady / go for it" switch, or a fixed board first?
2. **Pair value.** Level points (A) only, or level points with evidence-score tie-breaks (B)?
3. **Legacy optimizer.** Should the legacy optimizer (C) and its win-probability term be retired from
   captain-facing use?
4. **Format rules.** Which local format rules beyond the skill cap must be configured, such as team size, so
   that "legal" is never claimed without them?

## GPT Match Night Engine Review — executed counterexamples, 2026-10-18

### What was tested

`tests/test_match_night_design_review.py` contains eleven small, exhaustive/arithmetical design cases,
including calls into actual Next Send and reference-budget functions. Its toy enumeration is confined to
tests: it is not an application engine. Numbers used to challenge the proposed +2/+1/+0.5/0/-1 system are
hypothetical utility assignments from the proposal, never predicted points, wins or probabilities.
Together with thirteen recommendation-quality fixtures, the final run passed **24 cases in 0.41s**.
The first 23-case run reached 22 passes and a historical-opponent fixture KeyError; missing historical SL
was corrected to unknown in the test helper, without product changes. No full parity suite was rerun.

An independent read-only inventory verified all 575 saved response checksums and examined 168 actual
MatchPage fixtures / 1,680 score rows. These contain pair results/positions but no explicit put-up actor
and declaration sequence. No live request, original database write, model fit or new outcome estimate ran.

### Decision-changing findings

| Finding | Reproduced result and captain impact | Smallest design correction |
| --- | --- | --- |
| M301: Static safety is not counter-response safety | In a two-player table with favorable diagonal assignments and concerning crosses, M1 and M2 choose the favorable diagonal. Either lead can be countered into both crosses. A captain cannot enforce the static board. | Define M2 as weakest *planned* pairing, conditional on getting those pairings. Only a correctly specified sequential policy can claim robustness to opposing choices. |
| M302: Local order can consume the only answer | A is first vs X (3-0 vs B 2-1). A is also 5-0 vs Y while B is 0-3. A-X/B-Y gives favorable/concerning; B-X/A-Y gives two favorable records. Existing save warning notices the tradeoff but does not resolve it. | Compare the reachable remaining evidence profiles after each proposed answer, rather than equating the first local row with the best team plan. No win improvement is inferred. |
| M303: Confidence labels are not additive utility | One Strong plus one Unknown ties two Solids under 2/1/0. Changing Strong to 1.5 or 3 preserves all label ordering but reverses the board choice. | Separate evidence support from desirability. Do not sum ordinal confidence labels until an explicit cardinal utility policy is approved; explainability alone does not validate the tradeoffs. |
| M304: Zero unknown can mean falsely safer | Maximize-the-minimum prefers two unknown zeros over a Strong +2/Caution -1 board; maximizing total chooses the latter. Missing evidence is driving a safety conclusion. | Treat unknown coverage as uncertainty and show nondominated tradeoffs; do not silently give it neutral strategic value or claim a safe plan. |
| M305: Concession needs an objective | A concentrated 2/2/-1 plan beats 1/1/0.5 by total; the latter wins by weakest pairing. Neither toy objective establishes who wins a team match. | Define the actual objective and current score/required result before selecting concessions. Do not infer deliberate loss from a Caution label. |
| M306: Board count was understated | `P(8,5)=6,720` enumerates assignments to a fixed chosen set of five opponents. Choosing five from both eight-player rosters gives `C(8,5)^2 * 5! = 376,320` unordered-pair boards before constraints. | Correct the search estimate; benchmark the chosen state/objective separately. Static board count does not prove sequential browser/workbook performance. |
| M307: Sending a high-SL player can remove completion | In a synthetic two-slot budget of eight, SL6+SL2 fits, but sending SL7 leaves no completion with the supplied players. | Filter/annotate the *remaining feasible completion*, not just the immediate player's cost. This is supplied arithmetic, not APA legality. |
| M308: A feasible field alone cannot clear a plan | Existing reference helper can return feasible=True with unknown-SL players and complete=False; its text correctly says no lineup cleared. | Require known SLs for the chosen assignment/completion and verified rule constraints. A known subset can fit despite an unselected player's missing SL, but a globally best-board claim remains incomplete. Never promote one reference boolean to legal-board acceptance. No current-helper bug is asserted. |
| M309: Final matches do not reconstruct decisions | Two different lead/response sequences produce the same A-X/B-Y recorded board. | Replay may validate facts and conditional decisions; it cannot validate actual lead selection without declaration-order evidence. Do not infer the actor from home/away or match position. |
| M310: Unplayed outcomes are unavailable | Observed A-X and B-Y results do not supply B-X and A-Y outcomes. | Distinguish observed results from conditional evidence utility. A replay of alternate assignments cannot honestly count unplayed pairings as wins. |
| M311: Hold promises can collide | A is the sole favorable recorded answer to both Y and Z, but can only play once. Exhaustive two-slot enumeration shows only one of those favorable pairings is attainable. | Represent scarce counters as competing allocations, not two independently satisfiable hold-back instructions. Explain which opportunity remains uncovered. |

### Refined M3 decision contract

1. **State:** remaining/available players on both sides, locked/played players, pending declared player,
   phase (lead selection or response), next side to lead, remaining rounds, captured SL usage/unknowns,
   applicable rule profile, and the chosen objective. A points/match-result objective also requires the
   actual current score and format scoring rules. Masks and points-used alone omit critical information.
2. **Actions:** only the side currently choosing may select a player. A pending put-up must be answered;
   a board optimizer cannot freely rematch it. Both teams' constraint knowledge limits the response set.
3. **Continuation:** after a forced pairing, remove both players, update supplied budget arithmetic and
   verify a feasible completion. Include unavailable, unknown and missing-rule states explicitly. Do not
   infer a match result from a confidence label to advance team score.
4. **Evaluation:** pending the owner's decision, return evidence profiles/tradeoffs rather than a unique
   utility winner. If minimax is later chosen, specify its utility, terminal evaluation, objective,
   unknown handling, legal-action rules and any tie handling before claiming an optimum.
5. **Hold/concession:** compare feasible continuations with and without spending the player now. Show the
   actual counter/opportunity lost, including two opponents competing for the same counter. A concession
   is an accepted tradeoff under an objective, never a predicted loss or an intrinsic weak-player label.
6. **Robustness:** expose changed choices when a thin result or an uncertain availability assumption is
   removed. This checks dependence on assumptions, not a probability of the plan succeeding.

### Captain Decision Review and product-direction gate

| Captain action | What the design must establish |
| --- | --- |
| Lead | Which responses remain possible, which counters we preserve, and what worst-case assumption is being made |
| Answer | Immediate pairing evidence plus the evidence profile and supplied-budget feasibility left afterward |
| Protect/hold | What uniquely useful opportunity disappears, whether another counter exists, and whether two holds compete |
| Concede | The objective and opportunity retained elsewhere; no invented expected result or loss percentage |
| Finish under cap | Complete selected-lineup/completion SL data plus an applicable rule profile; unknown alternatives limit optimization claims, and a reference cap sum alone is insufficient |

**Genuine owner decision required:** should M3 return several nondominated evidence-based plans for the
captain to choose, or automatically name one best plan? The latter requires an explicitly approved
objective and utility/unknown policy. "Strong captain" does not uniquely determine those preferences,
and the test cases demonstrate that reasonable choices reverse under different objectives. Recommended
first direction is multiple conditional plans, preserving captain choice without arbitrary confidence
points. This is a proposal only; it is not permission to implement or change existing rankings.

The mechanical review is complete within these cases; implementation readiness is blocked by that
product-direction decision, not by a test that Paul must manually run. Historical and synthetic checks
cannot choose the product's objective or manufacture unobserved counterfactual outcomes. No current
recommendation-quality PASS or superior winning effectiveness is claimed.
