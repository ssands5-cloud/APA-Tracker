# Team matchup engine: "Best Scenario Match Night" (design proposal)

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
