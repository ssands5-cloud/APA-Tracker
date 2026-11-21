# Captain vs M3 head-to-head: pre-registration (written before any code ran)

## What the archive can and cannot support (verified earlier, see M3_HISTORY_AND_VALIDATION_AUDIT.md)
Not recorded: put-up order or who declared, the bench (who was available), the captain's options at each put-up, outcomes of pairings never played. So the "decision state" cannot be reconstructed, and the outcome of the road not taken is never observed.

Consequences, fixed now:
- **Identifiable:** (a) how often the realized board was M3-best among alternative boards built from the same ten players; (b) how far it fell short; (c) whether boards closer to M3's optimum had better results after controlling for skill (dose-response, observational).
- **Not identifiable from outcomes:** "when they disagreed, who was more often correct" and "season-long gain if M3 had been followed". Both need the result of a board nobody played. The honest verdict for those is **NOT IDENTIFIABLE (reported as INCONCLUSIVE)**. I will give an assumption-bound sensitivity number for gain, labelled as such, never as a finding.
- **Not answerable at all:** playoff qualification and tri-cup impact (40 standings snapshots, no playoff flag).

## Decision space (counterfactual boards)
For each match (since 2023-01-01, scored, 5 v 5, five decided games, as in the signal study), the realized ten players are held fixed. Alternatives = all 120 one-to-one matchings of the home five against the away five. Skill cap is unaffected (same players). This is NOT the real choice set: real put-ups alternate, so a captain controls only half of each matching. This is stated as the central limitation.

## M3 score of a board
Production `pair_confidence` evaluated for all 25 cross pairings, both directions, with history strictly before that local date (same replay as before). A team's score for a matching = sum of level points from that team's own perspective. Each team's M3-optimal matching maximises its own sum.

## Categories (per team per match)
regret = (best - realized) / (best - worst) over the 120 matchings (0 when best = worst; those matches are "no alternatives" and excluded from categories).
- M3 optimal: regret = 0
- Near optimal: 0 < regret <= 0.05
- Suboptimal: 0.05 < regret <= 0.40
- Strongly suboptimal: regret > 0.40
(The brief's "within 5% of best score" is ill-defined for scores that can be negative or zero, so it is normalised by range.)

## Quantities
1. Share of team-boards in each category, test period, versus the **null** of a random matching (expected share by enumeration); bootstrap CI on observed minus null.
2. Disagreement rate = 1 - share optimal.
3. Dose-response: night win (ties excluded) and points difference regressed on skill controls (dSL sum, train-fit SL-pair expected wins) plus rdiff = regret_away - regret_home (positive favours home). Train fit 2023-01..2025-08, evaluated 2025-09 onward; coefficient per 1 SD, incremental dAUC/dR2 versus skill-only, bootstrap by match, B=1000. Also win rate by regret tercile of the team.
4. Sensitivity (not a finding): if the fitted dose-response were causal, the expected change in night-win probability and in wins per season from moving every team's regret to zero. Season length = observed mean matches per team-season in the archive.

## Verdict rules
- Dose-response SUPPORTED: rdiff coefficient CI excludes 0 in the expected direction and dAUC >= 0.005 and dR2 >= 0.005 (CI lower bound > 0 for both).
- PARTIALLY SUPPORTED: coefficient CI excludes 0 but incremental metrics below threshold or CI includes 0 for one.
- NOT SUPPORTED: CI includes 0 and coefficient upper bound implies < 0.005 gain, or wrong sign.
- INCONCLUSIVE: otherwise; also used for the non-identifiable items.
- "Do captains using M3 win more": **not testable here**; no verdict of SUPPORTED can be issued for it.

## Limits
Observational; captains had information absent here; the opponent also chooses; regret is computed over counterfactual matchings that may be unreachable; levels reflect partial-capture history. Confounding: strong captains may both pick good boards and win for other reasons.
