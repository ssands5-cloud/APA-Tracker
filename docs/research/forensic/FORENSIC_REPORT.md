# Ultimate Coach forensic investigation: findings

Research only. No production code, M3, recommendations, UI, Excel, database, Sunday file or deployment was changed, and nothing here is an implementation proposal. Evidence first; ranking at the end (P1 proven, P2 likely, P3 theoretical). Aggregates only; no player records.

Inputs: code at `claude/uc-broadcast-ui` `6d74dc8` (contains `main` and `feat/phase1-war-room`); archive snapshot sha256 `4f4c861b…` (matches `docs/research/m3-validation/snapshot_manifest.json`); the original archive for the production replay; the Sunday captain file (counts only). Scripts and outputs are in this folder and in `docs/research/issue119/`.

## 1. Algorithm inventory

**Live surfaces** (the Sunday Broadcast HTML and Excel workbook): `ui/ultimate_coach.py`, `ui/ultimate_coach_war_room.js`, `ui/ultimate_coach_broadcast.py`, `ui/export_excel_ultimate_coach.py`, `ui/excel_war_room.py`. **Legacy surfaces** (Streamlit tabs, coach dashboard, `scripts/build_lineups.py` exports) still exist but are not in the Sunday package.

| Engine | Status | Inputs | Output and rule | Thresholds / constants | Tie-break | Missing data |
|---|---|---|---|---|---|---|
| Confidence levels `analytics/ultimate_coach_confidence.py` (JS mirror) | live | direct (W, meetings); both overall records; shared-opponent record; skill-changed flag | Strong/Solid/Thin/Unknown/Conflicted/Caution; points 6/3/1/0/0/-3 | form = (w+5)/(g+10), compared only if both have 20+ games; edges .05 (any) .15 (strong) .10 (shared); Strong at 5+ meetings and 70%+ or 3+ meetings with stronger form; Solid shared needs 3 common opponents | n/a | no history or under 20 games: Unknown (0); favorable direct with weaker form: Conflicted (0) |
| M3 Match Night `analytics/match_night_engine.py` (JS mirror) | live | level points per pair, availability, cap both teams, games left, used SL | answer = argmax(points now + minimax rest of night); lead = maximin; holds, sacrifices, fragility | cap 23 default (both teams); opponent assumed adversarial | first in roster order (skill level high to low, then name) | skill-unknown players' own cost unverified; plan still runs |
| Evidence ranking (Next Send) `analytics/ultimate_coach_matchup_evidence.py` (JS mirror) | live | direct records, shared opponents | tiers: direct, then shared (unranked group), then none; direct ordered by win rate, then more meetings; losing records by net losses | none | identical evidence shown as "2=" | no evidence: listed last, unranked |
| War Room categories `analytics/ultimate_coach_war_room.py` | live | direct record sign | G (more wins) / R (more losses) / E (even) / I (shared only) / X (none) | none (1-0 is G) | n/a | X |
| Blind send `analytics/ultimate_coach_war_room.py::blind_send` | live | categories vs unplayed opponents | fewest R, then most G, then most E | stated preference | roster order | X counts as nothing |
| Live threats `live_threats` | live | opponent record vs our remaining players | live threat / unknown | none | n/a | unknown kept, not called safe |
| Cap checks `wrCapFor`, `lineup_budget`, `analytics/lineup_legality.py` | live (budget) / classic (legality) | skill levels, cap | reference arithmetic; 5/23 and 4/19 paths | 23 | n/a | unknown SL keeps check incomplete |
| Skill-only win probability `analytics/head_to_head.py::skill_only_win_probability` | legacy (Lineup Lab, opponent risk profile, baselines) | SL difference | logistic, 0.40 log-odds per level | 0.40, clamp .02-.98 | n/a | missing SL: None |
| H2H win probability `head_to_head.win_probability` | legacy | SL difference + smoothed record x reliability | logistic | 0.40, Laplace 1/2 | n/a | |
| Lineup Optimizer `analytics/lineup_optimizer.py` | legacy (`build_lineups`) | matchup score, win prob, confidence, risk | Fij = .50 matchup + .30 win prob + .15 confidence + .05 (1-risk); assignment | weights; modeled-win weight 0 | solver order | neutral .5 for unknown |
| Win probability `analytics/win_probability.py` | legacy | SL delta, WR by SL, WR h2h, volatility | logistic | weights .15/.20/.30/.05, race term returns 0 | n/a | missing = 0 |
| Captain's Edge `analytics/captains_edge.py` | legacy | win prob, expected points, expected balls | .6/.3/.1 composite, normalized | confidence bases | rank order | null components skipped |
| Lineup risk `analytics/lineup_risk.py` | legacy | per-pair signals | .30/.30/.20/.20; danger threshold .40 | | | |
| Team matchup / opponent risk / team strength / season projection | legacy | various | reliability-weighted skill probability; equal-weight team index; log5 projection | | | |
| Player trends `analytics/player_trends.py` | legacy (Excel/Streamlit) | skill-level history | HOT/COLD from SL slope | slope ±0.05, volatility 0.40, min 5 | | |
| Research `matchup_candidate_model`, `baseline_evaluation` | research | | | | | |

## 2. Assumptions that differ (or should differ) between 8-Ball and 9-Ball

| Assumption | Code treats the formats | Evidence |
|---|---|---|
| Skill-level effect | Legacy skill-only probability: same 0.40 per level for both | Archive, lower player vs SL7: 8-Ball SL3 22.2% (n 990), 9-Ball SL3 49.7% (n 788); gap +1 overall 8-Ball 56%, 9-Ball 49% (test period). The 0.40 rule gives SL3 vs SL7 16.8% in both. |
| Level point scale | One scale (6/3/1/0/-3) for both, derived from 8-Ball replay ratios | 9-Ball replay ratios scaled to Thin = 1 would give about 8/3/1/0/-3; within a night only ratios matter, so the effect is small |
| 20-game form threshold | Same in both | Unknown-by-threshold share 71% (8-Ball) and 69% (9-Ball) of all Unknowns |
| Race | Not used by any live engine; 8-Ball race chart is two-dimensional, 9-Ball points depend only on own level (`docs/win_probability.md`) | Matches the observed difference above |
| Value of skill information beyond M3 levels | n/a | Adds out-of-sample information in 8-Ball (all five rolling blocks), nothing in 9-Ball (`docs/research/issue119/`) |

## 3. Statistical claims checked independently

| Claim (source) | Result | Classification |
|---|---|---|
| Levels order next-game wins, 843k rows: 8-Ball 68.1 / 57.7 / 53.3 / 50.0 / 42.3; 9-Ball 61.1 / 54.3 / 51.4 / 50.0 / 46.0 (`docs/captain_confidence_framework.md`) | Production replay on the current archive **refuses to run** ("Duplicate or self-pair result observation"). With the 193 matches holding duplicate keys excluded via its own option: 8-Ball 68.1 / 57.6 / 53.3 / 50.0 / 42.4, 9-Ball 61.2 / 54.2 / 51.4 / 50.0 / 46.1 (841,686 rows). | Reproducible with exclusion (`replay_levels.json`) |
| "Unknown is a true coin flip" (same doc) | Unknown is 50.0% **by construction** (the level is symmetric for the two players). Conditional on skill gap it is not: 8-Ball lower player at gap -3 or more wins 27%; vs SL7 the level model predicts 46% against 34% actual. | Misleading as stated |
| Level points anchored to replay (+18/+8/+3/0/-8 and +11/+4/+1/0/-4) (`ultimate_coach_confidence.py`) | Arithmetic matches the replay table; only the 8-Ball ratios are used | Reproducible |
| Skill-only term "validated", +1 SL about 60%, +3 about 77% (`head_to_head.py`, `docs/prediction_validation.md`, 106 games) | Full archive, test period: +1 = 56.4% (8-Ball) / 49.3% (9-Ball); +3 or more = 67.6% / 52.6%. Original 106-game check uses the pipeline database, not rerun here. | Not supported on the full archive; original unreproduced here |
| M3 planner correctness: exact vs independent game tree, optimal boards vs brute force, JS/Python parity | 392 engine, confidence, replay, mirror and evidence tests pass, including the game-tree and brute-force tests | Reproducible |
| Issue #119 results (skill and evidence vs M3 levels) | Published script reproduces them under clean and raw policies; leakage probe 0 mismatches; rolling validation consistent | Reproducible |
| M3 validation studies (signal, captain-vs-M3, component, decomposition) | Rerun byte-identical earlier; snapshot hash matches | Reproducible |

## 4. Data quality

- 851,766 head-to-head rows. 388 repeated (match, player, opponent) keys: 228 identical, 160 conflicting (158 opposite results). Every decided row has its mirrored row (0 exceptions); 48 rows have no result; 15,592 decided rows lack a skill level; 8,138 rows are other formats.
- Decided rows per match: 10 in 78,061 matches; fewer in 8,285 (forfeits or partial capture).
- Recorded skill levels are pre-match values (a rise follows a win on the next match 5.5% vs 0.7% after a loss; on the same match 2.6% vs 3.7%).
- Identity layer in the captain file: 15,181 verified identities, 4,222 excluded, 11,808 indeterminate participants, 2 quarantined games, 218 source coverage issues; 423,296 of 434,987 game rows identity-verified.
- Impact: the duplicates break the production replay script outright; on prediction metrics the clean and raw policies agree to four decimals.

## 5. Adversarial scenarios (synthetic inputs, production code; `scenarios.json`)

| Scenario | Expected by design | Actual | Comment |
|---|---|---|---|
| SL3 newcomer (7 games) vs strong SL7 | Unknown | Unknown (0) | Same opponent, experienced SL3 (150 games) gets Caution (-3): the newcomer scores better |
| SL2 with 0 games vs strong SL7 | Unknown | Unknown (0) | Archive: SL2 vs SL7 in 8-Ball wins 10.9% |
| Experienced SL6 (59%) vs SL7 (64%) | Caution if form 5+ points worse | Unknown | Edge 4.7 points, under the .05 threshold |
| One lucky 1-0 over SL7, weaker form | Conflicted | Conflicted (0) | Same points as no evidence |
| 1-0 over SL7, newcomer (no form compare) | Thin | Thin (+1) | One game outranks Unknown and Caution |
| 3-0 direct but much weaker form | Conflicted | Conflicted (0) | |
| 9-1 direct, stronger form / skill changed since | Strong / Solid | Strong (6) / Solid (3) | As designed |
| No evidence anywhere (7 v 5) | all tie | all tie at 0; answer = first in roster order (the SL6); listing the roster low to high sends the SL3 | The pick is decided entirely by display order |
| Only the SL3 newcomer avoids Caution vs SL7 | | M3 sends the SL3 | The reproduced real case |
| Cap 23 with 7,6,6,5,2,2 | keep two 2s | board 7,6,6,2,2 | Cap logic correct |
| Next Send: 2-0, 1-0, 9-1 vs one opponent | direct by rate, then meetings | 2-0 #1, 1-0 #2, 9-1 #3 | M3 calls the 9-1 Strong and the 2-0 Thin: the two live orderings disagree on the same screen (small samples are labelled) |

## 6. Missing data, quantified

- Test nights (2025-09+, ten players who played): 26% (8-Ball) and 27% (9-Ball) of all 25 cross pairings per night are Unknown.
- M3's game-one answer to their top player is an Unknown pairing on 27% / 25% of nights, and an Unknown caused by the 20-game rule on 22% / 18%.
- Current Sunday rosters: 303 of 1,632 8-Ball roster slots (19%) and 208 of 1,263 9-Ball slots (16%) belong to players with fewer than 20 recorded games.
- Scoring those threshold-Unknowns as Caution changes 24% / 22% of game-one answers; scoring every Unknown -1 changes 15% / 14%.
- Outcomes (2023+, lower player vs higher): Unknown-because-under-20 games vs Caution with 20+ games: 8-Ball gap -1 47.6% vs 38.2%, gap -2 39.8% vs 32.6%, gap -3 or more 27.0% vs 27.5%; 9-Ball Unknown 49-52% vs Caution 43-47%.

## 7. Tie-break effects (`forensic_ties_clean.json`, production roster order)

- **Answer to their top player is an exact tie on 1,243 of 3,476 8-Ball nights (36%) and 1,104 of 3,132 9-Ball nights (35%).** The tied players differ in skill level on 1,051 and 986 of those; the roster-order tie-break picks the highest-level tied player every time.
- **Lead is tied on 65% (8-Ball) and 62% (9-Ball) of nights.** Lead ties are disclosed on screen ("N leads hold up equally well … first by roster order"); answer ties are not (the response text lists only alternatives that lose later value).
- Model-dependent value (two evaluators fitted only on pre-2023 games): highest-level-first beats lowest-level-first among tied players by 0.011-0.017 expected games; the evaluator's best tied player would add 0.012-0.018 expected games over the current tie-break. Small, but it is the deciding factor on a third of nights.
- Earlier decision-change counts in issue #119 used player-id order for ties; with production order the qualitative results are the same.

## 8. Night-level outcomes, separate from single-game prediction

- Single-game prediction (test period, log-loss gain over M3 levels): 8-Ball skill + evidence +0.0113, M3 + skill +0.0053; 9-Ball +0.0059 and +0.0008; consistent across five rolling blocks.
- Predicting the night on realized boards (expected vs actual games won; night-win AUC): 8-Ball M3 levels 0.18 / 0.591, skill + evidence 0.26 / 0.625; 9-Ball 0.10 / 0.547 and 0.16 / 0.586.
- Decision quality: the same planner fed calibrated estimates changes the game-one answer on most nights; its model-dependent value is +0.015 (8-Ball) and +0.006 (9-Ball) expected games per game-one decision. Whether this produces more nights won is not established: unplayed pairings are never observed and the bench is unrecorded.
- Cap management: correct in scenarios and protected by brute-force tests. Player preservation (holds) follows the point scale and therefore inherits its weaknesses.

## 9. Explainability gaps

1. Answer ties (about a third of nights) are resolved silently by roster order.
2. An Unknown caused by the 20-game rule reads "no direct history and no clear overall or shared-opponent edge"; it does not say the player has too few games to compare.
3. No skill-level context accompanies a level, so an Unknown SL3 vs SL7 looks as neutral as an Unknown SL5 vs SL5.
4. Next Send (rate first) and M3 levels can order the same players differently on the same screen.
5. Rest-of-night value is explained only when an alternative loses later value; its size is not shown.
6. Level labels carry no sample size or uncertainty; probabilities are withheld by contract (deliberate).

## 10. Findings ranked

**P1, proven**
1. M3 values Unknown as an even game regardless of skill gap; in 8-Ball it overstates lower players against stronger ones (vs SL7: 46% implied, 34% actual; SL3 vs SL7 actual 22%). 70% of Unknowns come from the 20-game rule, which affects about one roster slot in six.
2. The documented "Unknown is a true coin flip" holds only by construction, not conditionally.
3. A third of M3's game-one answers are exact ties broken by roster order and not disclosed.
4. The legacy skill-only win probability is format-blind (0.40 per level): it predicts 17% for SL3 vs SL7 in 9-Ball where the archive shows 50%, and overstates small 8-Ball gaps. Used on legacy surfaces (Lineup Lab, opponent risk profile), not the Sunday package.
5. 388 duplicate head-to-head keys (160 conflicting) stop the production confidence replay from running on the current archive.
6. Skill-level information adds out-of-sample predictive value beyond M3's levels in 8-Ball, consistently across time; it adds none in 9-Ball.

**P2, likely**
1. Better single-game estimates would improve game-one decisions slightly (about +0.015 expected games in 8-Ball, model-dependent).
2. Next Send's rate-first ordering and M3's levels give conflicting signals to captains on small samples.
3. Identity exclusions (4,222 identities, 11,808 indeterminate participants) and partial capture increase Unknowns beyond the 20-game rule; not quantified per recommendation.
4. A single level-point scale for both formats slightly misweights 9-Ball levels.

**P3, theoretical**
1. The adversarial-opponent assumption may not match real opponents' put-up behaviour (put-up order is unrecorded).
2. The opponent's cap is assumed when their skill levels are partly missing.
3. Same-date game order is not recorded, so last-10 windows can split a day arbitrarily.

## Reproduce

- `python -I docs/research/forensic/forensic_ties.py --db <snapshot> --out <dir>` (about 15 minutes)
- `python -I docs/research/forensic/forensic_scenarios.py` (synthetic, seconds)
- Production replay with exclusion: `python -I scripts/replay_confidence_levels.py <archive> out.json --exclude-match-ids-file <193 external ids of matches with duplicate keys>` (ids are private data and not committed)
- Engine tests: `pytest tests/test_match_night_engine.py tests/test_confidence_levels.py tests/test_replay_confidence_levels.py tests/test_war_room_js_mirror.py tests/test_ultimate_coach_matchup_evidence.py`
- Issue #119 experiment: `docs/research/issue119/README.md`

No implementation recommendations are made here, as instructed.
