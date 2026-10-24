# Captain confidence framework (design proposal)

Claude, 2026-10-18. Design only, not implemented. No prediction, no win probability and no machine learning.
Paul decides adoption.

## Purpose

A recommendation tells a captain **who**. This framework tells them **how much to trust it**, in one word and
the reason behind it, from plain rules a captain can check by eye. It answers "should I go with this, or use
my own read?". It does not answer "what are the odds?".

## The five levels

| Level | Meaning for the captain |
|---|---|
| **Strong** | The record is deep and consistent. Go with it unless you know something the data does not. |
| **Solid** | Real support, but not overwhelming. A good default. |
| **Thin** | Some support from little evidence. Your own read should weigh about as much as the record. |
| **Conflicted** | The signals disagree. Use your judgment; the reasons say which way each one points. |
| **Unknown** | Nothing recorded either way. This is not weak; it means the coach has no edge to offer. |
| **Caution** | The recorded evidence points against this send. |

Every level is shown with its reasons. For example: "Strong — 8-2 in 10 meetings, same skill levels" or
"Conflicted — 1-0 in 1 meeting, but a weaker overall record (.44 vs .61)".

## The rules

The inputs are the six you named, all recorded results.
- The overall record is in the same format against everyone, pulled toward .500 by five wins and five
  losses so a new player is not extreme.
- An overall record counts once a player has 20 or more games.
- A form gap is our overall rate minus theirs.

### With a direct record

1. **Conflicted.** A favorable direct record but our overall record is 5+ points weaker; or a losing direct
   record but ours is 5+ points stronger.
2. **Caution.** More direct losses than wins, and form does not disagree.
3. **Strong.**
   - 5+ meetings at 70%+; or
   - 3+ meetings favorable, with form also 5+ points in our favor.
4. **Solid.** 3–9 meetings favorable, or a thinner favorable record backed by better form.
5. **Thin.** 1–2 meetings favorable, or an even record.
6. **Skill-level change.** If either player's SL has changed since they last met, drop one level: Strong to
   Solid, Solid to Thin.
7. **Recency.** If the last meeting was more than 3 years ago, Strong drops to Solid. Recency is a weak
   adjustment; see the evidence below.

### Without a direct record

1. **Strong.** Our overall record is 15+ points better.
2. **Solid.**
   - Our overall record is 5–15 points better; or
   - shared-opponent results favor us by 10+ points across 3 or more common opponents.
3. **Thin.** Shared-opponent results favor us through only 1–2 common opponents.
4. **Caution.** Their overall record is 5+ points better, or shared opponents favor them.
5. **Unknown.** Everything else.

## Does it work? Checked against 15 years of history

A read-only chronological replay (`scripts/replay_confidence_levels.py`) assigned a level to every singles game
in the staging archive using only earlier results. It then recorded how often that player won.

| Level | 8-Ball games | Won | 9-Ball games | Won |
|---|---|---|---|---|
| Strong | 17,232 | **68.1%** | 10,182 | **61.1%** |
| Solid | 83,802 | 57.7% | 61,156 | 54.3% |
| Thin | 79,427 | 53.3% | 61,782 | 51.4% |
| Unknown | 124,874 | 50.0% | 92,052 | 50.0% |
| Caution | 159,963 | 42.3% | 116,520 | 46.0% |
| Conflicted | 20,682 | see below | 15,908 | see below |

- **The levels mean what they say, in the same order, in both formats.** Each level beats the one below it,
  and Unknown is a true coin flip.
- These percentages are for internal validation of the level boundaries only. Captains see the word and
  the reasons, never a percentage.
- **Conflicted** reads 50.0% in aggregate by construction. When one player is Conflicted against another,
  the other is Conflicted the opposite way.
  - Which side tends to win shows up in the earlier replay (`docs/recommendation_review/`): when a single
    favorable meeting meets weaker form, form wins. A 1-0 with weaker form won 42.9% in 8-Ball, and a 0-1
    with stronger form won 57.1%.
  - That is why the reasons should name both signals rather than pretend one settles it.

### Evidence behind each input

| Input | Finding (8-Ball; 9-Ball is the same direction, smaller) | How the framework uses it |
|---|---|---|
| Meeting count | 1-0 won 53.7%; 10+ meetings at 70%+ won 64.7% | Depth is what moves a record from Thin to Strong |
| Overall record | Order accuracy 0.598 vs 0.522 for direct-record order | Raises or lowers a level; decides when there is no direct history |
| Shared opponents | With 3+ common opponents favoring us, 59.1%; with 1–2, 56.0% | Solid when there are 3+ opponents, Thin when 1–2 |
| Skill-level change | Favorable same-SL records 55.6% vs 52.4% after an SL change | Drops one level |
| Recency | Favorable under 1 year 54.4%; 3+ years 53.5% | Only a light Strong-to-Solid adjustment |

## What it changes for the four philosophy questions

- **1-0 vs 8-2.** The 1-0 is Thin; the 8-2 is Strong. The captain sees the difference at once, even while
  the existing order is unchanged.
- **1-0 vs 50-15.** The 1-0 is Thin. If the 1-0 player's form is weaker, it is Conflicted. The 50-15 player
  with no direct history is Strong or Solid, not "unknown".
- **One-game vs six-game threats.** Apply the same levels from the opponent's side. One win over us is Thin;
  a deep winning record or strong overall form is Strong.
- **Save-for-later.** A save warning carries the level of the option being saved. "Consider saving (Strong:
  9-1)" is a real reason to hold. "Consider saving (Thin: 1-0)" is minor and can be overridden.

## Boundaries kept

- No probability, odds, percentage or prediction is shown to captains.
- No weights are fitted. Thresholds are round numbers chosen for readability, and checked only for ordering.
- Unknown is never shown as weak.
- Recorded evidence only. Reasons are always visible.
- Identity-verified evidence only. Re-run the replay on the verified snapshot before adoption, because this
  check used the broader staging archive.

## Open decisions for Paul

1. **Display or order.** Should the levels only be displayed, with today's order kept, or should they also
   order Next Send, for example Strong before Solid before Thin?
2. **Shared-opponent ordering.** Should shared-opponent candidates stay "not ordered"? This replay shows a 3+
   common-opponent edge is about as reliable as a Solid direct record.
3. **Thresholds.** Accept the round-number thresholds (5 meetings at 70%, 5- and 15-point form gaps, 20 games),
   or adjust them after a held-out season check.
