# Recommendation philosophy review: evidence ranking or captain decisions?

## Current product assessment — GPT, 2026-10-18

**Recommendation:** Ultimate Coach should serve captain decision-making, with its verified evidence engine
as the foundation. Keep the current ranking unchanged unless Paul separately approves a decision policy
and its validation. This is a recommendation about product purpose, not permission to implement a model,
reorder players, or promise that a different send will win.

The practical choice has three forms:

| Philosophy | What it promises | Main benefit | Main limitation |
| --- | --- | --- | --- |
| Evidence ranking | Which recorded matchup evidence comes first under a disclosed rule | Transparent, reproducible facts and ordering | First in evidence order need not be the best practical send |
| Prescriptive captain-decision system | Which available send best advances a defined match-night objective | Directly answers the captain's action question | Requires a defensible objective, tradeoff rules and effectiveness validation we do not yet have |
| Captain decision support with an evidence foundation | What the evidence supports, where it conflicts, and which tradeoff the captain must make | Connects facts to the action without pretending the missing information is known | The captain still makes a judgment; the system cannot honestly claim an optimal send |

The third is the appropriate product direction now. It does not mean adding more warnings indefinitely.
Thin-versus-deep, current-versus-historical and now-versus-later conflicts are substantive selection-policy
questions; cosmetic parity and complete disclosure cannot settle them.

### 1. Evidence ranking: pros, cons and risks

**Pros.** Direct meetings address the exact opponent. Results can be inspected, the comparator can be
explained, and identical inputs reproduce the same order. Shared-only candidates are not assigned a
made-up numerical strength; missing evidence stays unknown. This avoids arbitrary blending and makes
identity, counts and source provenance auditable. It remains useful even without a trustworthy predictive
rule: a captain can discover an otherwise overlooked matchup or loss caution.

**Cons.** The current hierarchy treats evidence type as a priority before broader practical considerations.
Within favorable/even direct records, observed win fraction precedes meeting count. Dates and SL changes
annotate rather than alter that order. Captured broader records do not enter it. Consequently an honest,
well-disclosed first row can still be an unpersuasive action recommendation. Blind Send and save warnings
also embody preferences; they are not merely neutral lists of facts.

**Risks.** Captains may follow the first player as the best send, or repeatedly override it and stop trusting
the tool. A thin record can dominate a deeper one. Repeated historical meetings may describe an older race
or a concentrated opponent/player relationship. The hierarchy's simplicity does not make its practical
tradeoffs objectively correct. These risks persist even after all four surfaces agree.

### 2. Captain-decision systems: pros, cons and risks

**Pros.** They focus on the actual action: whom to send now, whether to preserve a counter, and which danger
matters for players still available. They can distinguish the exact pairing from general player history,
and expose conflicts instead of treating evidence type as a complete answer. An explicit decision policy
can be judged against the captain's objective rather than against implementation consistency alone.

**Cons.** The objective must be defined: winning the present individual matchup, maximizing team match
points, or preserving later options are different tasks. Availability, changing skill levels, opposition
selection and uncaptured player context complicate them. A broader record is not automatically a measure
of ability: format, time period, opposition, handicap context and data coverage can differ. Captain
preferences can conflict even when everyone reads the same facts.

**Risks.** A decisive-looking answer can hide more assumptions than the current evidence list. Historical
association can be mistaken for proof that choosing a different teammate improves outcomes. An unverified
identity or incomplete archive can affect broad-record comparisons. Optimization can sacrifice a strong
present opportunity for a later matchup that never happens. Suppressing published probabilities does not
remove the predictive claim implicit in calling a player the best send.

Decision support does not inherently require a new predictive model. Existing evidence can inform a
captain's judgment. Claiming an automatically superior or optimal send, however, requires support beyond
the current recorded-results comparator or a plausible captain story.

### 3. Five requested examples

| Example | Current behavior, reproduced from source | Evidence-ranking argument | Captain-decision argument and limit |
| --- | --- | --- | --- |
| 1-0 vs 8-2 against the same opponent | 1-0 is first: 100% observed wins precede 80%, with meeting count later | Both records are exact-pair facts; the rule is consistent | A captain can reasonably prefer ten meetings of favorable results to one. That does not prove 8-2 always wins or establish a new threshold/weight. |
| 1-0 direct / 3-4 broader vs no direct / 50-15 broader; opponent 8-0 broader | The 1-0 candidate is ranked; the other is unknown/unranked without shared evidence. Broader totals do not change the comparator | The exact matchup has a result; broader records may involve different opponents and contexts | A captain can reasonably choose the 50-15 player after checking record scope. Neither 50-15 nor the opponent's 8-0 justifies an automatic override by itself. Captured team/session records must not be called universal lifetime strength. |
| Save-for-later | A sole favorable direct option against another unplayed opponent triggers consider-saving for both 1-0 and 5-0; disclosed sample differs | The unique positive recorded pairing is a real option worth preserving | Protecting 5-0 may be more persuasive than protecting 1-0, but the value now and later matters. A 5-0 current opportunity can outweigh preserving a 1-0 future option; the future opponent may never be put up. The flag does not establish the optimal trade. |
| Blind Send | Fewest concerning pairings, then most favorable, then most even, then roster order; category ties can have very different meeting totals | Avoiding a recorded counter is a defensible conservative preference when the opponent can choose a response | One loss can outweigh several deep favorable pairings, while an unknown pairing does not count as a recorded loss. A captain may prefer broader coverage. Without knowing the actual opposing choices and the objective, neither worst-case caution nor broader form is universally best. |
| Threats | Winning aggregate against remaining players creates a live threat; one win can qualify. Availability recalculates it | It identifies recorded danger and correctly excludes evidence against unavailable players from the live calculation | A single win does not establish roster-wide superiority. An opponent 10-0 vs A but 0-2 vs B is a roster threat while B is a favorable counter. General opponent concern and danger for the actual send are different questions. Absence from this list is not proof of safety. |

The strongest disagreements concern sample support, absolute evidence priority and strategic opportunity
cost. None requires assuming that a higher-SL player automatically beats a lower-SL player. None proves
that all experienced captains agree or that a synthetic alternative produces more wins.

### 4. What the existing evidence does and does not establish

The current behavior is verified by eleven synthetic fixture cases in
`tests/test_recommendation_quality_risks.py` (11 passed in 0.21s). They execute actual product functions,
not a substitute ranking: `rank_vs_opponent` through `war_room_pair`, then `next_send`, `blind_send` and
`live_threats`. Availability recalculation, unknown-not-safer abstention and removal of a save warning when
the protected opponent Played all work. These are not defects to reopen. Engine source was not changed.

**Important limitation of the earlier exploratory review below:** its numerical replay claims have not
been independently re-run or validated in this assessment. Source inspection of
`scripts/replay_ordering_rules.py` shows that `auc` compares scores for historical winner and loser rows
across a dataset. It does not measure the success rate of selecting A rather than B from the same available
roster against a fixed put-up opponent. An AUC of 0.598 is not a demonstrated 59.8% send-win rate or an
eight-point improvement over following Ultimate Coach. Actual outcomes for unplayed alternatives are
unobserved, and different cohorts cannot establish which player would have won the same matchup.

Strictly earlier-date history is a useful protection against future-result leakage. It is insufficient
for a captain-selection effectiveness claim. The replay uses simplified proxy comparators rather than
calling the product's complete decision path; its blind proxy omits the even-count key and accumulates
historical team participants rather than reconstructing tonight's remaining roster and unplayed opponents.
The archive is also broader than the identity-verified recommendation scope. Mirrored player rows are
not independent matches. These limitations require caution, not dismissal of every historical signal.

Consequently the older statements that captains will usually do better at about 60%/55%, that history
proves the 50-15 send correct, or that a captain-decision system has a measured 58-60% practical accuracy
must be treated as exploratory hypotheses, not accepted product conclusions or release evidence.
No probabilities, fitted weights, new replay, model or ranking change was created for this report.

### 5. Product recommendation and unresolved decisions

**Choose captain decision support as the purpose; retain verified evidence as the foundation.** Do not
promise an autonomous best send from the current ranking. Do not replace direct priority with overall
win percentage on the strength of these examples or the exploratory AUC table. Decide separately whether
any selection policy should change, how missing evidence should affect it, and which match-night objective
it serves. Preserve the distinction between an evidence fact, a strategic caution and an action choice.

Before any change, Paul would need to choose whether thin direct records may override deeper favorable
records, how broadly scoped records may influence a direct matchup decision, and whether Blind Send is
primarily counter-avoidance or a different explicitly stated objective. Save-for-later needs an agreed
present-versus-future interpretation. Threats need to remain conditional on available counters. This report
does not choose numerical weights, probabilities, thresholds or an implementation design.

**Review verdict:** current evidence ranking is reproducible and useful but insufficient to establish
winning recommendations. Captain decision support is the better product purpose. Superior automated
selection remains unproven. Strong reasonable-disagreement cases remain, so recommendation-quality
acceptance is not established. No engine, ranking, UI, database, refresh or publication behavior changed.

---

## Prior exploratory Claude review — preserved reference, not accepted effectiveness proof

Read the methodological qualifications above before using the numerical claims or recommendations below.

Claude, 2026-10-18. Review only: no ranking, code or display was changed. Ranking policy remains Paul's decision.

## The question

Today Ultimate Coach is an **evidence-ranking system**. It orders direct records first, then shared-opponent
evidence, then unknown, and leaves the decision to the captain. The alternative is a **captain-decision
system**: it recommends the send most likely to help win, using every recorded signal that has been shown
to carry weight.

This review tests the current rules against history instead of arguing from principle.

## How the evidence was produced

- **Data.** `APA-Tracker-Ultimate-Coach-Live/data/ultimate_coach_staging.db`, opened read-only (SHA-256 prefix
  `fb2b098d6b0537b5`).
  - Singles only: 8-Ball Open (485,980 player-game rows) and 9-Ball Open (357,600).
  - 2011-05 to 2026-09, 46 sessions. Each game appears once from each player's side.
- **Method.** A chronological replay (`scripts/replay_evidence_rules.py`, `scripts/replay_ordering_rules.py`).
  - Every game is judged only from games on **strictly earlier dates**, exactly what the coach could have
    known that night.
  - Same-date games never see each other.
  - "Overall form" is the player's earlier record in that format against everyone, pulled toward .500 by
    five wins and five losses so a new player is not extreme.
- **Measures.**
  - *Next-game win rate*: how often players in a situation won their next game.
  - *Order accuracy*: how often a rule ranks the actual winner above the loser. 0.50 is a coin flip.
  - Aggregate results are in `docs/recommendation_review/`; they contain no player names.
- **Limits.**
  - This is descriptive history, not a calibrated probability. Nothing here should be shown to captains
    as odds.
  - The staging archive is broader than the identity-verified evidence the coach uses tonight, so absolute
    numbers may shift on verified data. The direction of every finding below is the same in 8-Ball and
    9-Ball.
  - APA handicaps already aim to make every game about 50-50. That is why all signals are modest, and why
    a few points matter.

## Headline result

| Rule (8-Ball) | Order accuracy, all games | Games with a direct record | Games after one meeting |
|---|---|---|---|
| Coach category (favorable > even/unknown > concerning) | 0.522 | 0.543 | 0.537 |
| Coach order (win %, then meetings) | 0.522 | 0.546 | 0.537 |
| Direct record pulled toward .500 by one win and one loss | 0.522 | 0.547 | 0.537 |
| **Overall form gap (ours minus theirs)** | **0.598** | **0.600** | **0.598** |

9-Ball: coach order 0.513 overall and 0.526 with a direct record; overall form gap 0.555 and 0.554.

The signal the coach ranks by is weak. The signal it explicitly sets aside ("Broader records — not used in
this ordering") carries roughly four times as much separation above a coin flip: 0.098 against 0.022
in 8-Ball. That stays true even when a direct record exists. In Next Send the opponent is fixed, so
ordering our remaining players by their own overall form is the same as ordering by the form gap.

## The five challenges

### 1. A 1-0 record against an 8-2 record

- **Coach today:** the 1-0 is first. Order is win %, then meetings, and the product says so.
- **History, 8-Ball next-game win rate:**

  | Prior record vs this opponent | Next-game win rate |
  |---|---|
  | 1-0 | 53.7% |
  | 2-0 | 55.7% |
  | Favorable, 5–9 meetings, ≥70% | 57.5% |
  | Favorable, 10+ meetings, ≥70% (an 8-2) | **64.7%** |

  9-Ball: 52.1% after a 1-0, 55.5% after a 10+ meeting ≥70% record.
- **Captain's view:** an experienced captain sends the 8-2, and history agrees by about 11 points in 8-Ball.
- **Why the overall score barely moves:** pulling the direct record toward .500 only changes order accuracy
  from 0.546 to 0.547, because 1-0 versus 8-2 collisions are rare. They are exactly the moments a captain
  notices, and on those the coach currently points the wrong way.

### 2. A 1-0 record against a 50-15 player with no direct history

- **Coach today:** the 1-0 is ranked. The 50-15 player is "unknown, not weak". Their record appears under
  "not used in this ordering".
- **History, 8-Ball:**

  | Situation | Next-game win rate |
  |---|---|
  | No direct history, own overall ≥ .67 | **66.4%** |
  | No direct history, overall gap ≥ +.15 over opponent | **67.4%** |
  | 1-0, all cases | 53.7% |
  | 1-0 but weaker overall form than the opponent | **42.9%** (worse than a coin flip) |
  | 0-1 but stronger overall form than the opponent | 57.1% |

  9-Ball, same order: 58.2%, 60.4%, 52.1%, 47.6%, 52.4%.
- **Captain's view:** most captains send the 50-15 player. History says they are right. One meeting does not
  outweigh a season.
- **Note:** form uses the whole history in the format. On form, "unknown" is not neutral: it is usually
  well known.

### 3. Save-for-later

- **Coach today:** "consider saving" fires when a player is our only favorable direct option against
  another unplayed opponent. That includes a single 1-0.
- **History:** what a save protects is that player's direct edge against the later opponent. After one
  meeting that edge is +3.7 points (8-Ball) or +2.1 (9-Ball), and it is negative when the player's form is
  weaker than that opponent's. Sending the player now can capture a form edge of +7 to +17 points.
- The later opponent may also never be put up against the saved player, because the other captain chooses.
- **Captain's view:** "don't burn your best answer early" is real strategy, but only when the saved answer
  is strong. Saving a strong-form player because of one earlier win is usually the wrong trade.
- **Weakness:** the save warning has the same weight for a 1-0 as for a 10-0, and it ignores form entirely.

### 4. Blind send (we put up first)

- **Coach today:** fewest concerning records against the opponents still to play, then most favorable, then
  most even.
- **Order accuracy:** coach rule 0.521 in 8-Ball and 0.513 in 9-Ball. The player's own overall form scores
  0.559 and 0.536. A simple blend, form plus (favorable − concerning)/10, scores 0.550 and 0.530, slightly
  below form alone.
- **Captain's view:** when leading blind, captains put up a reliable, in-form player. The current rule mostly
  avoids one-game losses, which history shows carry little information.

### 5. Threat ranking

- **Coach today:** an opponent is a threat when their winning record against our remaining roster holds.
  Order is net wins.
- **History, our player's win rate in 8-Ball:**

  | Opponent | Our win rate |
  |---|---|
  | Threat by record vs our roster, 10+ meetings | 45.7% |
  | Threat by record vs our roster, fewer than 3 meetings | 47.7% |
  | Not a threat by that record | 51.5–51.7% |
  | Overall form ≥ .67 | **34.4%** |
  | Overall form .60–.67 | 43.3% |
  | Overall form below .40 | 59.2% |

  9-Ball, same order: 47.2%, 47.9%, 50.7–51.8%, 42.0%, 45.5%, 56.8%.
- **Captain's view:** captains judge danger mainly by who wins a lot. History agrees strongly. An opponent's
  record against our particular players adds a few points. Their overall form adds about three times as
  much.
- **Weakness:** the most dangerous opponents are often missing from the threat list when they have not
  happened to beat our roster.

### Smaller findings

- **A skill-level change weakens a direct record.** Favorable at the same SL pairing: 55.6% next-game win
  rate. Favorable after either SL changed: 52.4% (8-Ball). 9-Ball: 53.6% and 50.7%. The SL caveat the coach
  already shows matters.
- **Age barely matters.** Favorable records under a year old: 54.4%. Three or more years old: 53.5%. Recency
  is not a strong reason to discount.
- **Avoid on one loss is weak.** 0-1 next-game win rate is 46.3%. A 0-1 player with better form wins 57.1%.

## Philosophy options

| | A. Evidence ranking, as now | B. Evidence ranking with sample strength and form shown | C. Captain-decision system |
|---|---|---|---|
| Order | Win %, then meetings | Unchanged order; conflicts flagged, e.g. "deeper record" and "stronger form" | Ranked by recorded form and direct evidence together, sample-aware |
| What 1-0 vs 8-2 does | 1-0 first | 1-0 first, 8-2 flagged | 8-2 first |
| What 1-0 vs 50-15 does | 1-0 ranked, 50-15 not ordered | 1-0 first, form flagged | 50-15 usually first |
| Measured order accuracy (8-Ball) | 0.52 | 0.52, plus flags the captain can act on | about 0.58–0.60 |
| Probability shown | No | No | No (an order is not a probability) |

### Pros of moving toward C

- It points the same way experienced captains and 15 years of results do, on all five challenges.
- It roughly quadruples the separation above a coin flip in 8-Ball.
- It removes the main trust problem: recommendations a captain overrules on sight.

### Cons of C

- It is a model. It needs a stated, tested rule and governance the project has so far avoided on purpose
  (`probability_publication` FORBIDDEN; "no weights").
- It is less transparent than "most wins against this player". It must still show its reasons.
- Form inherits identity and coverage gaps. A player with thin history in our data looks average.

### Risks

- **Overfitting.** Tuning weights to this archive could look better than it plays. Mitigation: the simple
  untuned rules here already show the gain. Validate any chosen rule chronologically on later seasons only.
- **Perceived prediction.** Captains may read an ordering as odds. Mitigation: keep "no probability" and
  show the evidence beside each pick.
- **Handicap drift.** Strong form partly means a player is under-rated for their SL, and APA may re-rate
  them. Mitigation: shrink form, and use the current season more where possible.
- **Data mismatch.** These results use the broad staging archive, not tonight's verified evidence. Re-run on
  the verified snapshot before adopting any rule.

## Recommendation

**Adopt B now and decide on C deliberately.**

1. **Keep evidence ranking as the spine, but stop hiding the strongest signal.** Show overall form beside
   every candidate in Next Send, Blind Send and Threats. Flag conflicts at the pick: a thin direct leader
   when a deeper record or clearly stronger form is available. This changes no order, adds no probability,
   and turns the captain's likely override into an informed one.
2. **Make warnings sample-aware.**
   - Scale "consider saving" so a single 1-0 no longer carries the same weight as a 10-0.
   - Add opponents with strong overall form to the threat view, labeled as form, not record.
3. **Decide C with a held-out test, as Paul's call.** If adopted, the rule should be simple and stated:
   - direct record pulled toward .500 by its sample size;
   - plus overall form;
   - ties shown.

   Accept it only if it beats the current order on a later season it was not tuned on. The replay scripts
   here are the starting harness.

## Bottom line

As a pure evidence ranking, Ultimate Coach is honest but weakly helpful: about 52% order accuracy in 8-Ball,
51% in 9-Ball. An experienced captain who ignores it and goes by who wins a lot will usually do better,
around 60% and 55%. The evidence supports keeping the honesty and adding the captain's strongest signal to
the decision.
