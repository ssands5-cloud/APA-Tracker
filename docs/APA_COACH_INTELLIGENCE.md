# APA Coach Intelligence — Architect Analysis
**Date:** 2026-10-25  
**Role:** Repository Architect (Claude)  
**Scope:** Verified findings from source-code deep read of 5 analytics modules.

---

## Modules reviewed

| File | Lines | Core function |
|------|-------|---------------|
| `analytics/match_night_engine.py` | 504 | Dynamic minimax captain plan |
| `analytics/lineup_optimizer.py` | 440 | Linear assignment solver |
| `analytics/lineup_legality.py` | 272 | 23-Rule verifier |
| `analytics/captains_edge.py` | 318 | matchup_score / confidence / risk |
| `analytics/ultimate_coach_war_room.py` | 1093 | War Room: sends, threats, blind lead |

---

## What the engine already does well

The analytics engine is sophisticated. Knowing what it does prevents GPT from rebuilding what exists.

### match_night_engine.py — full minimax with cap constraints
- **Real minimax** (not greedy): tries all legal combinations with memoization, assumes the opposing captain makes their worst reply every time
- **23-Rule on both sides**: `their_legal()` limits opponent put-ups to what they can legally field under the same cap — uncommon in amateur tools
- **Six captain outputs in one pass**: lead pick, response table, hold-backs, sacrifices, best board, safest board, match confidence, fragility, cap safety
- **Deterministic**: candidates tried in roster order, only a strictly better value replaces — the JS mirror (`ui/ultimate_coach_war_room.js`) must produce the identical output

### lineup_optimizer.py — exact assignment solver
- Exhaustive search over all valid 1-to-1 assignments (correct at APA roster sizes of 3–5 players)
- Four-component objective: matchup_score 0.50, win_probability 0.30, confidence 0.15, risk_penalty 0.05
- Fifth signal (`modeled_win_probability`) is built but weight defaults to **0.0** — intentionally disabled
- Never fabricates: missing evidence defaults to neutral 0.5 for arithmetic, raw values shown in UI

### lineup_legality.py — verified 23-Rule with tri-state
- Exact tri-state: True / False / **None** (never guesses when data is missing)
- Checks duplicate players (same person in two slots) — added after a real code review finding
- 4-player/19 fallback path (`assess_completion_options`) for when a team cannot field 5 legal players
- Never adds unverified constraints (e.g., "no more than two SL6+") — documented design decision

### captains_edge.py — signal derivation
- matchup_score = 0.6×win_prob + 0.3×points_norm + 0.1×balls_norm (renormalizes for missing components — prevents 9-Ball pairings scoring lower purely for lacking an expected_points field)
- risk_factor = volatility × (1 − sl_stability) — squared-risk: swings in skill level penalized double
- confidence = CONFIDENCE_BASE[HOT/NEUTRAL/COLD] + regression_slope — slope adjusts before the flag catches up

### ultimate_coach_war_room.py — live-night workflow
- `next_send()`: ranked response table to each opposing put-up, with "consider saving" flag
- `blind_send()`: who to lead with when we go first, ranked by fewest concerning records
- `send_cost()`: exact count of opponents we lose coverage on by spending a player
- `live_threats()`: danger assessment filtered to **remaining roster tonight** (not historical full roster)
- `quick_read_badges()`: glanceable scouting card badges for phone use

---

## Bugs and stale code found

### BUG: `build_version()` hardcoded to "PR #83" (Low)
**File:** `analytics/ultimate_coach_war_room.py:1062`

```python
return f"PR #83 · {sha}" if sha else "unversioned"
```

Every artifact built from this code says "PR #83" regardless of the actual branch. Should read the current branch or be removed; it was left over from when the function was written on that branch.

**Fix:** Remove the `"PR #83 · "` prefix — the SHA alone is the version identifier.

### RISK: JS mirror must stay in sync (Medium)
**Files:** `analytics/match_night_engine.py` and `ui/ultimate_coach_war_room.js`

The docstring explicitly states the JS mirror "produces the identical plan." Any change to `match_plan()`, `_best_board()`, or `_board()` must be mirrored in the JS file. There is no automated test that cross-checks Python vs JS output for the same inputs.

**Fix (highest ROI):** Add a test in `tests/` that runs both engines on the same fixture and asserts identical plans. One test, very high regression catch rate.

---

## Top 5 highest-value captain features

### 1. Mid-match replan triggered by "Mark Sent" (Highest ROI)

**What exists:** `plan_for_war_room()` accepts `played_count` / `played_sl` / `remaining` / `unplayed` to replan the remainder of the night. The engine is complete.

**What is missing:** Sending a player via the War Room UI (tapping "✓ Sent") does NOT feed back into `plan_for_war_room()` and regenerate the lead pick / response table / hold-backs for the games still ahead.

**Why it matters:** A captain who sends their lead pick in game 1 is looking at a stale plan for games 2–5. The engine already handles this correctly; the UI just isn't calling it.

**Effort:** Medium — the Snapshot type already carries `players` with availability marks; the web app needs to call the engine with the updated remaining set on each "Mark Sent" event.

**Users would pay for this:** Yes. Every APA captain who plays 5-game matches needs a plan that updates as the night moves.

---

### 2. Visual cap tracker with "cheapest remaining" bar (High ROI)

**What exists:** `_cap_safety()` returns `cap`, `used`, `cheapest_rest`, `slack`, `incomplete`. `lineup_budget()` returns similar values with per-send legality checks.

**What is missing:** There is no visual representation of the cap budget on the match night phone UI. Captains currently calculate this in their head.

**Why it matters:** The 23-Rule is the #1 source of illegal lineups. A visual "X used / 23 cap / cheapest remaining = Y / slack = Z" bar prevents both over-budget sends and overly conservative ones.

**Implementation:** A narrow sticky bar at the top of the Match Night page. `lineup_budget()` already computes `sending_keeps_legal` per player — this can drive a green/red highlight on each send button.

**Effort:** Low — data already in the plan; pure UI addition.

---

### 3. Send-cost preview before committing a send (High ROI)

**What exists:** `send_cost()` returns exactly: how many opponents have coverage before vs after sending this player, and which coverage we lose.

**What is missing:** This data is not shown to the captain before they confirm a send. It's computed but not surfaced in the Next Send flow.

**Why it matters:** A captain who sends their only direct-record option vs opponent A, not realizing it costs their only direct-record option vs opponent B, makes a preventable mistake. `send_cost()` already catches this — it just runs silently.

**Implementation:** When a captain taps a ranked send candidate, show: "Sending this player costs you direct coverage against: [names]" before they confirm. One extra call, zero new data.

**Effort:** Low — function already exists; UI needs a pre-confirm step.

---

### 4. Forfeit path indicator (Medium ROI)

**What exists:** `assess_completion_options()` distinguishes: (a) standard 5-player/23 completion possible, (b) only the 4-player/19 forfeit path available, (c) unknown (missing SL data).

**What is missing:** When a team is shorthanded and the forfeit path is the only legal option, no warning is shown to the captain. They discover it when the lineup check fails.

**Why it matters:** Forfeiting match 5 is a legitimate APA rule, not an error — but a captain needs to know before they arrive which path they're on.

**Implementation:** On the War Room summary banner, when `requires_forfeit=True`, show a clear indicator: "⚠ 5-player lineup not possible with tonight's available players — 4-player/19 path active, match 5 forfeited."

**Effort:** Low — `assess_completion_options()` is production-ready; just needs a UI surface.

---

### 5. Activate modeled_win_probability in lineup_optimizer (Medium ROI — requires validation first)

**What exists:** `PairingCandidate.modeled_win_probability` is a full, separately-computed signal (logistic model over sl_delta / wr_sl / wr_h2h / volatility) built into `lineup_optimizer.py`. Weight currently = 0.0 — deliberately disabled.

**Why it was disabled:** Two correct reasons in the code: (a) it's a computed estimate, not an observed H2H rate — conflating them would misrepresent what kind of number the captain sees; (b) no chronological backtesting has been done.

**Why it has high potential:** The existing four-term objective ignores the skill-level gap between players. A SL3 player sent against a SL7 opponent scores identically to a SL7 vs SL7 on matchup_score if H2H records are missing. The modeled_win_probability signal fills that gap using skill-level information the current formula ignores.

**How to activate safely:**
1. Run a chronological backtest: split historical data by date, train on the past, predict on the future, measure calibration
2. If calibrated, set `WEIGHT_MODELED_WIN_PROBABILITY` to a small value (e.g., 0.05) and reduce `WEIGHT_WIN_PROBABILITY` to 0.25
3. Show in UI as "skill-level estimate" with its own label, never as "win probability"
4. Never display the raw probability value — display only the lineup rank change it caused

**Effort:** Medium (backtest) + Low (activation once validated). High-quality output improvement.

---

## Improvement summary table

| Feature | Effort | User Value | Status |
|---------|--------|-----------|--------|
| Mid-match replan on "Mark Sent" | Medium | Very High — live plan stays current all night | Engine complete, UI wiring needed |
| Visual cap tracker + per-send legality | Low | High — prevents illegal lineups | Data exists (`_cap_safety`), UI missing |
| Send-cost preview before confirm | Low | High — prevents wasting sole coverage | `send_cost()` exists, not surfaced |
| Forfeit path indicator | Low | Medium — prevents surprise forfeit | `assess_completion_options()` ready |
| Activate modeled_win_probability | Medium+validation | Medium — better picks vs unknown opponents | Disabled by design; needs backtest first |

---

## What NOT to rebuild

These already exist and are correct. GPT should read before implementing:

| Area | Don't rebuild | Read instead |
|------|--------------|-------------|
| Captain's minimax plan | match_plan() / plan_for_war_room() | match_night_engine.py |
| 23-Rule check | check_lineup_legality() / assess_completion_options() | lineup_legality.py |
| Who to send next | next_send() / blind_send() | ultimate_coach_war_room.py:536 |
| Send cost analysis | send_cost() | ultimate_coach_war_room.py:828 |
| Live threat filtering | live_threats() | ultimate_coach_war_room.py:761 |
| Lineup assignment | solve_lineup_assignment() | lineup_optimizer.py:300 |

---

## Phase 1 web app — what the Snapshot already supports

All five features above can be built using data already in the `Snapshot` type — no new backend calls required:

- `players[].availability` → which players are remaining
- `plan.cap` → cap arithmetic / slack
- `plan.lead` / `plan.holds` / `plan.responses` → current plan
- `threats[]` → live threat list
- `totals` → overall matchup coverage

The only new server-side logic needed for feature #1 (mid-match replan) is calling `plan_for_war_room()` with a filtered remaining set — this requires a server action or API route, NOT a new Snapshot structure.
