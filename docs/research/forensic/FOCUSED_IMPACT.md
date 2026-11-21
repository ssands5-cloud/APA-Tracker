# Focused forensic impact: ties, Unknown evidence, 8-Ball vs 9-Ball

Evidence only. No fixes, no tuning, no new models, no production change, no deployment. Script `focused_impact.py`; outputs `focused_impact_EIGHT_clean.json`, `focused_impact_NINE_clean.json` (aggregates only). Snapshot sha256 `4f4c861b…` (matches the manifest); clean record policy.

Labels: **PROVEN** (direct computation on recorded data or code), **SUPPORTED** (consistent evidence, model-dependent or with caveats), **INCONCLUSIVE**, **CONTRADICTED**. Severity: cosmetic, statistically meaningful, or potentially consequential to captain decisions.

## Populations, exclusions and evaluator assumptions

- **Test nights:** every 2025-09-01+ match with exactly five players a side and five decided games, all ten skill levels recorded: 3,476 8-Ball and 3,132 9-Ball nights. Excluded: forfeits and partial capture (fewer than ten decided rows), byes, unscored matches, missing skill levels. All paired comparisons use these identical nights, the identical ten players and identical pairing evidence; only the factor under study changes.
- **Actual recorded outcomes:** 2023+ games, one row per game: 66,361 8-Ball and 57,785 9-Ball games (sections 2 and 3 tables); and the 17,380 / 15,660 games actually played on the test nights (evaluator check).
- **Simulated counterfactuals:** M3 (production search and points) plays all five games against a fixed opponent policy (adversarial best reply, or "top first": highest-level legal player, greedy answer), both first-leader orders. Unplayed games are scored by two evaluators fitted only on 2013-2021 with the penalty chosen on 2022: skill+evidence and skill-only. Games are treated as independent. **"Three of five games" is a simulated summary, not an actual APA team win.**
- **Evaluator check on actual test games:** skill+evidence log loss 0.6695 vs base rate 0.6931 (8-Ball), calibration slope 1.04; 0.6843 vs 0.6931, slope 1.07 (9-Ball). Skill-only 0.6819 (slope 1.00) and 0.6920 (slope 0.81, overconfident) respectively.
- **Replay proxy:** the replay builds each player's record from archive-captured games; the live product uses APA league career totals for the overall record. Current rosters show the two agree on who is new (section 2.4).

## 1. Roster order and tie-breaks

M3's search values are independent of roster order; the order only decides which of several equally scored players is chosen. So changing the whole order and randomizing only the final tie-break act through the same mechanism: a fixed order applies one consistent preference to every tie (production: highest skill level first; reversed: lowest first), while random tie-breaking draws independently at each tie.

**Results (skill+evidence evaluator; ranges cover both opponent policies and both first-leader orders; per-setup figures are in the JSON):**

| Variant vs production order | 8-Ball first decision changed | 8-Ball five-game board changed | 8-Ball expected games, mean [95% CI] | 9-Ball first changed | 9-Ball board changed | 9-Ball expected games |
|---|---|---|---|---|---|---|
| Reversed order | 38-65% | 66-77% | -0.0009 to -0.0018 | 37-62% | 66-76% | +0.0005 to +0.0008 |
| Player-id order | 13-25% | 35-40% | -0.0005 | 14-25% | 35-39% | +0.0003 |
| Random order (3 seeds) | 22-40% | 48-60% | -0.0004 to -0.0037 | 21-38% | 47-56% | +0.0003 to -0.0036 |
| Random tie-break only (3 seeds) | 22-40% | 49-60% | -0.0004 to -0.0022 | 20-39% | 48-57% | +0.0003 to -0.0025 |

- Projected outcome changed on about the same share of nights as the board. Mean absolute change 0.01-0.04 expected games per night; worst single night -0.17 to -0.47 games; best single night +0.13 to +0.34.
- Direction depends on the assumed opponent: against the adversarial opponent the production order is equal or slightly better; against "top first" in 8-Ball, reversed and random tie-breaks are slightly better (+0.003 to +0.004, CI above zero).
- Cap compliance: 100% for every variant and the production order.
- Preservation: the tie-break largely decides when our strongest player plays. Reversing the order moves that player 1.3-1.65 games later on average; random orders about 0.7-0.8 games later.
- **Are tied candidates interchangeable?** Under the skill+evidence evaluator, when M3 answers their put-up, 46% of ties are exactly equal in evaluator value, 25% (8-Ball) / 14% (9-Ball) differ by more than 0.02 games, 7% / 2% by more than 0.05. When M3 leads, almost no ties are equal (1-2%), and 50-54% (8-Ball) / 29-37% (9-Ball) differ by more than 0.02 games.

| Conclusion | Label | Severity |
|---|---|---|
| Roster order changes M3's recommendation on a fifth to two thirds of nights and the full plan on a third to most nights | PROVEN | potentially consequential (per night) |
| On average the choice of tie-break has no meaningful effect on projected outcomes (means within ±0.004 games, sign depends on opponent model) | SUPPORTED | cosmetic on average |
| Individual nights can differ by up to about 0.2-0.5 projected games depending only on the tie-break | SUPPORTED (model-dependent) | potentially consequential for that night |
| Equally scored candidates are often not strategically equal under an independent evaluator, especially for our own leads | SUPPORTED (model-dependent) | statistically meaningful |
| Answer ties are not disclosed to the captain (lead ties are) | PROVEN (code) | potentially consequential to trust and explanation |
| The tie-break never affects cap compliance | PROVEN | none |

## 2. Unknown and no-evidence handling

### 2.1 GPT's counterexample is correct

For the reproduced case, the smoothed records are (5+5)/(7+10) = 58.82% and (691+5)/(1,084+10) = 63.62%: a 4.796-point difference, below the 5-point Caution threshold. **Even without the 20-game gate the pairing is Unknown.** My earlier statement that this player was Unknown "because of the 20-game minimum" is **CONTRADICTED**. The real reason: no direct history, and records within 5 points of each other after shrinkage (a 5-2 start is pulled toward .500). Teammates were Caution because their records are more than 5 points worse.

### 2.2 Associated vs caused (counterfactual with the gate removed)

Each Unknown pairing was re-scored by the production rule with `FORM_MIN_GAMES` set to 0, all else equal. 2023+ games:

| Unknown cause | 8-Ball | 9-Ball |
|---|---|---|
| Caused by the 20-game gate (counterfactual level is not Unknown) | 6,376 (41.9%) | 5,097 (38.3%) |
| Associated with the gate but not caused (a player has fewer than 20 games, records still within 5 points) | 4,451 (29.3%) | 4,029 (30.3%) |
| No direct history, both players 20+ games, records within 5 points, no decisive shared opponents | 4,387 (28.8%) | 4,167 (31.3%) |

The previously quoted 71% is the **associated** share (41.9% + 29.3%). The **causal** share is 42% (8-Ball) and 38% (9-Ball). With the gate removed, gate-caused Unknowns would become Caution 50%, Solid 39%, Strong 12% (8-Ball) and Caution 50%, Solid 40%, Strong 10% (9-Ball): the gate hides both negative and positive edges, not only negative ones.

### 2.3 Actual outcomes by cause and skill gap (lower = our player's skill level minus theirs)

| 8-Ball gap | Gate-caused Unknown | Associated, not caused | Records too close | Caution |
|---|---|---|---|---|
| -3 or less | 26.2% (229) | 31.6% (98) | n < 30 | 28.0% (867) |
| -2 | 37.4% (476) | 45.7% (311) | 46.1% (180) | 33.5% (2,637) |
| -1 | 44.4% (1,328) | 51.3% (981) | 50.1% (950) | 39.7% (7,029) |
| 0 | 48.3% (2,263) | 51.3% (1,633) | 51.6% (2,084) | 45.4% (8,702) |
| +1 | 54.9% (1,341) | 52.8% (1,005) | 51.2% (945) | 48.2% (2,873) |
| +2 | 65.4% (511) | 57.5% (320) | 57.6% (184) | 50.2% (460) |

In 9-Ball every Unknown cause sits at 46-55% at every gap (no skill-gap trend).

### 2.4 Genuine inexperience vs incomplete capture vs missing direct history vs contradiction

- **Current Sunday rosters** (live product uses APA career totals): 296 of 1,297 8-Ball players have fewer than 20 archive games; 275 of them (93%) also have fewer than 20 APA career matches (genuinely new) and 21 have 20+ (incomplete capture). 9-Ball: 204 players, 177 new, 27 capture gaps. Separately, 245 (8-Ball) and 185 (9-Ball) players have less than half of their career matches in the archive, which thins their direct and shared-opponent evidence.
- **Missing direct history with similar records** (both 20+): 29% / 31% of Unknowns (table 2.2).
- **Contradictory evidence** (Conflicted level): 4.4% (8-Ball) and 4.7% (9-Ball) of all games; actual 50.1% and 51.1%.
- **Influence on recommendations** (production plan, adversarial, they lead first): chosen pairings were gate-caused Unknown 14.0% / 12.5%, associated-not-caused 8.0% / 8.0%, records-too-close 5.7% / 8.3%.
- **Counterfactual decision effect of the gate:** removing it changes the first decision on 28-35% of nights and the five-game board on 45-53%, and projected outcomes get slightly **worse**: -0.003 to -0.005 games (8-Ball), -0.001 to -0.002 (9-Ball), all intervals below zero.

| Conclusion | Label | Severity |
|---|---|---|
| The reproduced case's Unknown is not caused by the 20-game gate | PROVEN | corrects an earlier claim |
| 42% (8-Ball) / 38% (9-Ball) of Unknowns are caused by the gate; 71% was association only | PROVEN | statistically meaningful |
| Removing the gate would improve projected decisions | CONTRADICTED (slightly worse, model-dependent) | n/a |
| Unknown behaves like an even game regardless of cause in 9-Ball | PROVEN (actual outcomes) | cosmetic in 9-Ball |
| Unknown is not an even game at skill gaps in 8-Ball, whatever its cause (26-37% at gaps of -2 or worse; 55-65% at +1/+2) | PROVEN (actual outcomes) | potentially consequential in 8-Ball |
| Most low-history players on current rosters are genuinely new, not capture gaps | PROVEN | context |
| Incomplete capture materially thins direct and shared evidence for about a fifth of rostered players | SUPPORTED | statistically meaningful; effect per recommendation not isolated: INCONCLUSIVE |

## 3. 8-Ball vs 9-Ball

- **Skill-pair outcomes (actual):** lower player vs SL7, 8-Ball SL3 22.2% (n 990) to SL6 37.5% (n 6,775); 9-Ball 49.7% to 50.1%. PROVEN.
- **Category reliability (actual 2023+):** 8-Ball Strong 67.4% / Solid 58.0% / Thin 53.7% / Unknown 50.5% / Conflicted 50.1% / Caution 42.0%; 9-Ball 61.3% / 54.5% / 52.3% / 49.5% / 51.1% / 45.7%. Ordered in both; in 9-Ball Conflicted sits above Unknown and Thin is only 2 points above even. In 8-Ball a category's meaning shifts strongly with the skill gap (Caution 28% at -3 or less, 50% at +2; Solid 49% at -2, 65% at +2); in 9-Ball categories are roughly stable across gaps (Caution 43-49%, Solid 50-59%). PROVEN.
- **Shared point scale:** scoring 9-Ball with 9-Ball-derived ratios (8/3/1/0/0/-3) changes the first decision on 4-9% of 9-Ball nights and the board on 7-13%, with no meaningful projected change (-0.0001 to -0.0006 games). CONTRADICTED as a consequential issue; cosmetic.
- **Recommendation sensitivity to ties and to the gate** is similar in both formats (section 1 and 2 tables).
- **Projected decision quality:** in the earlier night replay the skill+evidence planner gained more over M3 in 8-Ball (+0.013 to +0.032 games) than in 9-Ball (+0.007 to +0.013). SUPPORTED, model-dependent.
- **Caution:** different historical win rates do not by themselves show that the best captain strategy differs by format; this study does not test strategy directly.

| Conclusion | Label | Severity |
|---|---|---|
| Skill gap carries large signal in 8-Ball and almost none in 9-Ball | PROVEN | potentially consequential in 8-Ball |
| M3's categories are reliable in order in both formats but gap-dependent in 8-Ball | PROVEN | statistically meaningful |
| The single shared point scale materially changes 9-Ball recommendations | CONTRADICTED | cosmetic |
| Better-informed planning gains more in 8-Ball | SUPPORTED (model-dependent) | potentially consequential |
| Optimal captain strategy differs by format | INCONCLUSIVE | n/a |

## Outstanding red-team findings (preserved)

- **Leakage:** 0 mismatches in the 400-game-per-format probe; features from strictly earlier dates. Still holds.
- **Duplicates:** 228 identical and 160 conflicting keys; this study uses the clean policy; headline metrics did not depend on it.
- **Holdout reuse:** the 2025-09+ period has now been used by the issue #119 experiment, the night replay and this study. No model or parameter was chosen on it here, but repeated looks increase the risk of over-reading small differences; differences under about 0.005 games should be treated as noise.
- **Calibration:** M3 points are not probabilities and are never used as such. The evaluators are reasonably calibrated on actual test games (slopes 1.00-1.07) except the 9-Ball skill-only evaluator (0.81).

No fixes, tuning or recommendations are made.
