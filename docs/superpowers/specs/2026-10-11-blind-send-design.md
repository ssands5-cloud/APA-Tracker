# Blind send — "we put up first, who goes?"

Status: **PENDING PAUL REVIEW**. Written under Paul's 2026-10-11 instruction to implement and
document assumptions rather than stop for approval while he is away. The `brainstorming` skill's
approval gate cannot be satisfied in his absence; this substitution is deliberate and recorded.

## The gap

Every recommendation Ultimate Coach makes today is conditioned on knowing who the opponent put
up. Next Send asks "They put up:" and needs a chip before it answers. Best sends now is one line
per unplayed opponent. Captain Packet is organised per opponent.

In APA the lead alternates, so a captain must regularly choose **before** seeing their player.
For that decision — a decision he makes most match nights — the product currently has no answer.
Verified 2026-10-11: no `put up first` / blind / lead-off concept exists in `ui/` or `analytics/`.

This is the decision-first rule applied to the one question the product exists to answer.

## What it must not become

No odds, no model, no prediction of who they will put up. The product's own limitations section
promises recorded results only, and a blind-send recommendation that guesses their lineup would
break that promise. Unknown stays unknown, never "weak".

## Approaches considered

**A. Safest lead (maximin).** Rank remaining players by their *worst* recorded matchup across the
opponents still unplayed; recommend the player whose worst case is least bad. Uses recorded
results only. Answers "who can I put up without handing them a gift?"

**B. Best coverage.** Rank by how many unplayed opponents the player holds a favorable direct
record against. Maximises good matchups, but can lead our strongest player into their one
dominant player.

**C. Hold the ace.** Recommend leading with a mid-strength player and reserving the best for a
known threat. Strategically appealing and what many captains actually do — but it depends on
predicting their lineup, which the product refuses to do.

## Recommendation: A, with B as the stated tiebreak

A is the only one defensible purely from recorded results. B is a reasonable secondary sort when
worst cases tie, which they often will in sparse data. C is rejected: it requires modelling their
behaviour.

Ranking rule, in order:
1. Fewest *concerning* direct records among unplayed opponents (worst case first).
2. Most *favorable* direct records among unplayed opponents (coverage).
3. More total recorded meetings against those opponents (better evidenced).
4. Stable by roster order, so the answer never jitters.

Players marked Unavailable are excluded. Unknown availability stays eligible and is said at the
point of decision, consistent with the rest of the product.

## What it says

```
If we put up first:  <player>
Why:                 no concerning record vs any of the 5 they have left · 2 favorable
Evidence:            (the existing per-opponent detail, unchanged, below)
```

When evidence is thin it must say so rather than manufacture confidence, e.g.
"little recorded evidence either way — this is a weak recommendation".

## Assumptions, for Paul to overturn

1. Captains want the *safe* lead rather than the aggressive one. If he prefers "hold the ace",
   that is approach C and needs his judgement, not mine.
2. Unavailable excluded, Unknown eligible — matching Next Send.
3. It belongs at the top of Tonight, above the "They put up:" chips, because when we lead there
   is no chip to pick yet.

## Scope

HTML first (the match-night interface). Python analytics function is the oracle with tests; the
JS mirrors it, as Next Send already does. Excel and the Captain Packet follow only if Paul keeps
the feature.
