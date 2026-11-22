# V2 candidate — recovery checkpoint (Sat Nov 21 2026, 20:45 MT, before the owner's restart)

## State at checkpoint
- Branch `claude/uc-v2-candidate`, worktree `D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\.worktrees\uc-v2`,
  pushed; draft PR #120 (stacked on PR #114 `claude/captain-value-plan`). Nothing merged or deployed.
- Untracked files in the worktree that are NOT part of V2 (another session's league catch-up work; never commit them):
  `pipeline/league_catchup_import.py`, `scripts/import_league_catchup.py`, `tests/test_league_catchup_import.py`.
- Sunday package unchanged: `tmp\ultimate-coach-release\broadcast-v7-ui-6d74dc8\Ultimate_Coach_Broadcast.html`,
  sha256 `a5077731d0b10fc668f858d70cf8f14f373a785e1b8791b40dccbc36e2071a31`.
- Owner review file (last verified, verifier PASS): `D:\APA Tracker Scorekeeper\OWNER REVIEW - Ultimate Coach V2 Candidate\OWNER_REVIEW_ONLY_Ultimate_Coach_V2_Candidate.html`,
  build e22310e (built Sat Nov 21 2026 8:08 PM MT), sha256 `2c3c2fc0462410e24f1960aae7e842b3e1c80825166f96c56b7aaa791b150c8b`.
- Later code (not yet in the owner file): 424b9e0 GPT-008 + V2 risk overwrite fixes; 49963cb provenance manifest.
  Built but not verified: `tmp\...\claude-captain-workflow\v2-build\v2_candidate_424b9e0.html` (+ `.manifest.json`).

## Evidence on D: (kept)
`D:\APA Tracker Scorekeeper\ssands5-cloud\APA-Tracker\tmp\ultimate-coach-release\claude-captain-workflow\v2-build\`
- `evidence-v1\` division audit harness v1 (72 pairs, 360 states, 2 contradictions -> fixed e22310e; 29 quantified exceptions).
- `v2_candidate_e22310e.html` exact build of the interrupted harness-v2 audit; `audit_v2_progress_s1..4.txt` and
  `audit_v2_partial_at_stop.txt`: stopped at 7/72 pairs, 84 states; shards 3-4 reported 13 contradictions (details are
  only written at the end of a shard, so they are NOT yet diagnosed). Re-run is needed.
- `repro_pair.py` (local helper: reproduce one pair; args: html, pair index).

## Interrupted / not mine
- The other session's `scripts/import_league_catchup.py` (PIDs 3544/9164, started 18:14) was still running at the
  checkpoint; its output DB `APA-Tracker-Ultimate-Coach-Live\data\ultimate_coach_staging_catchup-20261121.db` was last
  written 19:39 with no journal/WAL open. Re-run it from that session if needed; Claude did not touch it.

## Recovery commands (run from the uc-v2 worktree)
```bash
cd "D:/APA Tracker Scorekeeper/ssands5-cloud/APA-Tracker/.worktrees/uc-v2"
git fetch origin && git status -sb && git log --oneline -1          # expect claude/uc-v2-candidate in sync
python -m pytest -q tests/test_uc_v2_candidate.py tests/test_uc_contradiction_audit.py   # locked V2 + detector suites
```
Rebuild the candidate at HEAD (with provenance manifest):
```bash
R=../../tmp/ultimate-coach-release; B=$R/claude-captain-workflow/v2-build; C=$(git rev-parse --short HEAD)
python docs/v2/build_review_package.py --worktree . --base 6d74dc8 --package $R/broadcast-v7-ui-6d74dc8/Ultimate_Coach_Broadcast.html --upstream $R/broadcast-refreshed-career-v7-20261120 --out $B/v2_candidate_$C.html --label "$C (V2 candidate)" --built "$(date '+%a %b %-d %Y %-I:%M %p MT')"
```
Reproduce the shard 3/4 contradictions first (pair indexes 2 and 3), then re-run the full audit:
```bash
python $B/repro_pair.py $B/v2_candidate_$C.html 2
for i in 1 2 3 4; do (python docs/v2/contradiction_audit.py --html $B/v2_candidate_$C.html --division 436647 --shard $i/4 --out $B/audit_v2_s$i.json --summary $B/audit_v2_summary_s$i.json 2> $B/audit_v2_progress_s$i.txt &); done
```
Verify before handing the owner a file:
```bash
python docs/v2/verify_review_package.py --review $B/v2_candidate_$C.html --package $R/broadcast-v7-ui-6d74dc8/Ultimate_Coach_Broadcast.html --ours "13082718|436647|Fall 2026" --theirs "13092274|436647|Fall 2026" --opponent "Paul Richardson"
```

## Remaining work, in order
1. DONE (after restart): the 13 harness-v2 contradictions were GPT-008 instances, fixed in 424b9e0, re-verified on 2 pairs x 12 states.
2. DONE: regression-lock matrix in `AUDIT_FINDINGS.md`; S5 test strengthened; T1/GPT-009/S7 tests added with fail-before evidence.
3. GA-03: reclassify D1 (the Sunday data is the v7 build: base run `run-20261119T183918Z-1cdb65c6` + 8,440 catch-up pairs,
   cutoff 2026-11-19, Codex-verified 0 differences over 549,936 pair records; the base run's input folder was not found on
   disk); GPT-010/011 train/live parity.
4. GA-01 remaining: 9-Ball division run; played 0-4 under both toss orders; absent-answer check on the real page.
5. Final gate: candidate at final commit + manifest, full local suite, final harness-v2 audit on that exact build,
   verifier, owner file update, PR #120 report. Then GPT review and owner acceptance. No merge/deploy without approval.

## Update Sat Nov 21 2026, 21:17 MT (after the restart)
- Done since the restart: harness-v2 contradictions diagnosed (all GPT-008, fixed 424b9e0, re-verified); regression-lock
  matrix in AUDIT_FINDINGS.md (S5 test strengthened; T1, GPT-009, S7, GPT-008-on-real-page detector cases added, each
  with fail-before evidence); GA-01 coverage: 9-Ball support and played 1-4 under both toss orders (683d5f5).
- Final candidate: `tmp\...\v2-build\final-683d5f5\v2_candidate_683d5f5.html`, sha256
  `46618509c44cdb4310ef2cb4041a556da8dac3db1c67f621f13b9d29dda21154`, clean commit 683d5f5, verifier PASS.
  Not yet copied to the owner folder (that waits for the final audit).
- Final audit RUNNING since 21:16 on that exact build: 8-Ball division 436647 (6 shards) + 9-Ball division 436654
  (2 shards), outputs in `final-683d5f5\` (`eight_*`, `nine_*`). If interrupted, re-run the same commands:
```bash
F=../../tmp/ultimate-coach-release/claude-captain-workflow/v2-build/final-683d5f5
for i in 1 2 3 4 5 6; do (python docs/v2/contradiction_audit.py --html $F/v2_candidate_683d5f5.html --division 436647 --format EIGHT --shard $i/6 --out $F/eight_s$i.json --summary $F/eight_summary_s$i.json 2> $F/eight_progress_s$i.txt &); done
for i in 1 2; do (python docs/v2/contradiction_audit.py --html $F/v2_candidate_683d5f5.html --division 436654 --format NINE --shard $i/2 --out $F/nine_s$i.json --summary $F/nine_summary_s$i.json 2> $F/nine_progress_s$i.txt &); done
```
- After it finishes: if 0 contradictions with coverage_ok, copy the candidate to the owner folder (keep the e22310e file
  as the previous verified checkpoint), update README, publish results to PR #120; otherwise diagnose first.
