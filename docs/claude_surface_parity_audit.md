# Claude surface-parity audit (auditor findings for the builder)

Claude audits; GPT builds. The latest audit is at the top. Each finding names an exact fixture,
the screens that disagree and the smallest fix. Ranking logic is not to be redesigned.

**Stopping condition:** phone, HTML, workbook and Packet cannot lead a captain to different decisions
from the same evidence. When met, the audit entry here says `SURFACE PARITY PASS`.

The phone needs no separate check: it renders through the same `ui.ultimate_coach` code and
`ultimate_coach_war_room.js` as the HTML, so it can differ only by snapshot date and local marks.

## Re-checks after the pass

- **2026-10-18 09:47, 3f7d9aa (docs only).** Product code and tests are unchanged since afa0169. The five
  combined suites passed 346 of 346, and the Avoid-order, live-threat and per-opponent caution fixtures
  agree across surfaces. The pass holds.
- **2026-10-18 10:10, a02fc39 and 3c1bd8b (refresh standings fix and docs).** These touch only
  `pipeline/ultimate_coach_refresh.py`, its tests and docs, with no `ui/`, `analytics/` or captain-surface
  change. `tests/test_ultimate_coach_refresh.py` passed 29 of 29. The pass holds.

## Claude implementation of T1, T2, T4 and final audit (2026-10-17) — SURFACE PARITY PASS

GPT became unavailable, so Claude implemented the last three required trust fixes in `ui/excel_war_room.py`.
No ranking, category, eligibility, save or budget logic changed.

- **T1.** The workbook Next Send avoid line reads "⚠ Avoid records — recorded losses, not exclusions:". A
  single-meeting loss adds "· Lost once · Only 1 meeting". This matches the phone ("Avoid records — recorded
  losses" and "Lost once") and the Packet ("recorded losses, not exclusions").
- **T2.** The Packet evidence-page Basis column prints the direction, then the caution, for example
  "Favorable direct · SMALL SAMPLE" or "Concerning direct · SMALL SAMPLE". A thin 1-0 and a thin 0-1 no
  longer print alike.
- **T4.** The Packet Blind Send line carries the phone's exact evidence text: "N direct meetings total
  across P opponents · K small-sample pairings". The new `wr_OurLiveSmall` counts direct pairings of 1–2
  meetings against unplayed opponents, the same rule as the phone's `bs-evidence`.

Each fix has a new test in `tests/test_cross_surface_trust.py`. The tests read displayed workbook and
Packet text, and the T4 test also reads the rendered phone page. All three failed on 54898fb and pass after
the change.

Four browser tests were already failing on 54898fb. All four were stale expectations left by earlier
builder wording changes, not product regressions, so they were repaired without product changes:
- **Two tests** expected the old War Room send-list text "2-0 (2)". The HTML now prints "2-0 (2 meetings) ·
  SMALL SAMPLE", the same as the workbook and Packet.
- **Two avoid-panel cases (390 and 1280 px)** compared whole list items. Those items now also contain the
  meeting badge. They now compare each item's caution text, which keeps the check that no pairing is
  dropped and that the order is unchanged.
- **Two workbook formula tests** pinned the old wording: the Basis column printing only "SMALL SAMPLE" (the
  T2 defect) and the "Avoid:" label (T1). Both were updated to the fixed text.

**Tests:** one combined run of `tests/test_cross_surface_trust.py`, `tests/test_next_send_boundaries.py`,
`tests/test_excel_war_room_formulas.py`, `tests/test_ultimate_coach_war_room.py` and
`tests/test_ultimate_coach_war_room_browser.py`: 346 passed in 401.97s. Formula results come from the
repository's formula evaluator. Native Excel and physical-device checks were not run in this pass.

**Final sweep: no decision-changing differences remain** across phone, HTML, workbook and Packet for:
- Next Send order and ties;
- save-for-later;
- per-opponent loss cautions;
- deeper records;
- reference-budget warnings;
- live threat scope;
- Blind Send pick, ties and evidence strength;
- Quick Read and Scouting scope (full-roster history, disclosed on every surface).

**Cosmetic or wording-only items (do not change a decision):**
- Phone Next Send says "Direct-record order #1". The HTML Lineup Lab and workbook best-send lines say
  "first by recorded direct results". The pick and its visible sample are the same.
- For a losing deeper record, the phone says "concerning" and the Packet and workbook say "recorded loss".
- The phone uses badges where the Packet and workbook print uppercase "SMALL SAMPLE" and "MEETINGS".
- The workbook and Packet always print the reference-budget scope line when a cap is entered. The phone
  shows it only when the check is incomplete. The candidate warnings themselves are identical.
- The workbook best-send and War Room list lines also carry the budget warning. The HTML shows it in Next
  Send and the Blind Send card on the same page, but not repeated in its Lineup Lab and War Room lists.
- HTML Top risks loss cautions say the sample twice. The shared text ends "· SMALL SAMPLE · Lost once" and
  the badge beside it repeats "Lost once · 1 meeting · small sample".
- Preview lengths differ by design: the Packet shows 2 options and 3 flags, and the War Room shows 5 loss
  cautions. Each opponent's own cautions, save warnings and deeper records are on its Packet line.

## Audit of 54898fb (2026-10-17) — NOT A PASS

The parity, Next Send and workbook formula suites passed 106 of 106 on a clean detached checkout of 54898fb.

- **P4 closed.** `wr_CandidateBudget` mirrors the phone's `wrLineupBudget`:
  - integer cap greater than 0;
  - slots = unplayed opponents;
  - played known SL summed, and unknown played or remaining SL counted as incomplete;
  - cheapest remaining (slots − 1) after this send;
  - no warning when too few captured SLs.

  The same text ("Reference comparison: this choice exceeds your entered skill budget", or "…check
  incomplete") appears beside the same named candidates on the Command Center, Next Send, Packet options
  lines and the Packet Blind Send pick. As on the phone, it is not attached to shared-only (≈) candidates.
  The test cross-checks nine mark states against the reference arithmetic.
- **All decision-changing gaps (P1–P4) are closed.**
- **Remaining trust findings required for the pass:**
  - **T1:** workbook `wr_NsAvoidLine` still says "⚠ Avoid:" for a single loss. The phone and Packet say
    "Lost once · 1 meeting — Recorded loss" and "recorded losses, not exclusions". A captain could exclude
    a player on the workbook who the phone treats as a caution.
  - **T2:** the Packet evidence-page Basis column still prints only "SMALL SAMPLE" for rows under 3
    meetings, dropping favorable or concerning. On black-and-white print, a 1-0 and a 0-1 read alike apart
    from the record digits.
  - **T4:** the Packet Blind Send line still lacks "· K small-sample pairings". The phone shows that count
    beside the first-up pick, so thin first-up evidence looks stronger on paper.

  Fixes are as in the b00eb79 entry.
- **Reclassified to wording-only (does not block the pass):** T3, workbook "first by recorded direct
  results" versus phone "Direct-record order #1". It names the same pick, and the workbook reason already
  carries the meeting count and small-sample tag.

## Audit of cc10c66 (2026-10-17) — NOT A PASS

The parity, Next Send and workbook formula suites passed 96 of 96 on a clean detached checkout of cc10c66.

- **P3 closed.** The workbook Command Center has a "Deeper record context" card, and each Packet options
  line has "Deeper direct records — more meetings, not a new order". Both use the phone's
  `wrNextSendEvidence` rule:
  - it fires only when the first favorable or even direct option has 1–2 meetings;
  - it lists remaining players with more direct meetings, in existing order;
  - the opponent must be unplayed.
- The test reads the displayed Packet and Command Center text for 1-0 against 9-1 and 8-2, and checks
  that an Unavailable mark removes the deeper row.
- Cosmetic only: for a losing deeper record the phone says "concerning" and the Packet and workbook say
  "recorded loss".
- **Still open:** P4 skill-cap warning, and T1–T4. See the b00eb79 entry. **Next in priority: P4.**

## Audit of e328d37 (2026-10-17) — NOT A PASS

The parity, Next Send and workbook formula suites passed 95 of 95 on a clean detached checkout of e328d37.

- **P2 closed.** Each Packet options line now lists that opponent's own losing records under "Loss cautions —
  recorded losses, not exclusions". They follow the shared net-losses order, are filtered to remaining
  players, and carry SMALL SAMPLE and "Lost once · Only 1 meeting" tags. This is the same rule as the
  phone's Next Send avoid list.
- `test_packet_opponent_caution_survives_other_opponents_higher_global_losses` is my P2 fixture: 0-5, 0-4
  and 0-3 against one opponent, and 0-2 against the other. It reads the displayed Packet line. Another
  test checks that an Unavailable mark removes the caution and that it does not leak across opponents.
- **Still open:** P3 deeper record, P4 skill-cap warning, and T1–T4. See the b00eb79 entry. **Next in
  priority: P3.**

## Audit of a009e83 (2026-10-17) — NOT A PASS

The parity, Next Send and workbook formula suites passed 93 of 93 on a clean detached checkout of a009e83.

- **P1 closed.** Each Packet "vs <opponent>" options line now carries "<player> — consider saving for
  <opponent> (record · Only 1 meeting)". It is computed per printed opponent from the same
  unique-favorable flags as the Command Center, for the same G/E/I candidates the phone flags. The new
  test reads the displayed Packet text and checks that marking the protected pairing Played clears it.
  The phone save record also gains "· Only 1 meeting", so the wording now matches.
- **Still open, unchanged at a009e83:** P2 per-opponent loss caution, P3 deeper record, P4 skill-cap
  warning, and T1–T4. Fixtures and fixes are in the b00eb79 entry below.
- **Next in priority: P2.** The Packet options line that now carries the save warning is the natural
  place for that opponent's own loss cautions.

## Audit of b00eb79 (2026-10-17) — NOT A PASS

The builder's parity, Next Send and workbook formula suites (`tests/test_cross_surface_trust.py`,
`tests/test_next_send_boundaries.py`, `tests/test_excel_war_room_formulas.py`) gave 92 passed and 1 failed.
That run used the builder's uncommitted working tree on top of b00eb79. The failure is the builder's own
uncommitted test `test_packet_preserves_the_same_future_save_warning_and_single_meeting_caution`, which
fails with a TypeError. It is work in progress on finding P1, not a regression.

### Verified fixed at b00eb79

- **Avoid order.** Losing records sort by most net losses, then meetings, on every surface: Python,
  HTML Next Send, Quick Read, workbook Command Center, Top risks and Packet. Example: Ann 0-1 and Bob 0-6
  against Xavier. Every surface lists Bob first. Favorable and even order is unchanged.
- **Threat scope.** War Room and Packet use the phone's remaining-player and unplayed-opponent scope.
  The Packet no longer prints "Dangerous:" from full-roster history.

### Decision-changing findings (block the pass, in priority order)

**P1. Packet has no save-for-later warning.**
- Fixture (Eight-Ball):

  | Our player | Vs Xavier | Vs Yara |
  |---|---|---|
  | Ann | 1-0 | 1-0 |
  | Bob | 8-2 | none |
  | Cy | 3-0, marked Unavailable | none |

- Phone, HTML and workbook Command Center, Ann's Next Send row: "consider saving — our only favorable
  direct option vs Yara (1-0 in 1 meeting, small sample)". The phone also shows "⚠ Only 1 meeting".
- Packet "Recorded options preview", vs Xavier: Ann is listed with no warning. There is no save text
  anywhere in the Packet.
- Decision: with the Packet the captain spends Ann on Xavier; with the phone they likely save her.
- Smallest fix: append the existing `wr_NsSaveDetails` text, as `wr_NsMedalText` already does, to each
  Packet options line.

**P2. Packet can omit the loss caution for the opponent who is put up.**
- Fixture: Ann 0-5, Bob 0-4, Cy 0-3 against Yara; Di 0-2 against Xavier.
- Phone Next Send for Xavier: "⚠ Avoid record — recorded losses: Di — 0-2 (2 meetings · small sample)".
- Packet Top risks: three loss lines, all against Yara. There is nothing for Xavier on the page.
- Decision: with the Packet the captain can send Di against Xavier.
- The "first 3" disclosure in the header is accurate, but it does not fix this, because the captain's
  question is per opponent.
- Smallest fix: add that opponent's own loss cautions (`wr_NsAvoidJoin` for opponent k, same order and
  SMALL SAMPLE tags) to each Packet "vs <opponent>" options line.

**P3. The deeper direct record is phone-only.**
- Fixture: against Xavier, Ann 1-0, Cy 3-0, Bob 8-2.
- Phone: "Direct-record order #1 — Ann 1-0 · 1 meeting ⚠ Small sample", plus "Deeper direct records:
  Cy 3-0 in 3 meetings, Bob 8-2 in 10 meetings".
- Packet: "1. Ann — 1-0 · SMALL SAMPLE · 2. Cy — 3-0". Bob is not on paper.
- Workbook: three options and no deeper line.
- Decision: the phone shows the 10-meeting record; the Packet cannot.
- Smallest fix: when the first option has fewer than 3 meetings, add one "Deeper record:" line to the
  Packet options line and the Command Center. Use the same rule as `wrNextSendEvidence`: remaining
  players with more direct meetings, in existing order. Do not change the order.

**P4. The skill-cap warning is phone-only.**
- Fixture: any reference cap entered in Lineup Lab, where the first pick exceeds it.
- Phone row: "Reference comparison: this choice exceeds your entered skill budget".
- Workbook Next Send row (`wr_NsMedalText`) and Packet: no such text.
- Smallest fix: append the same text when `ll_Cap` is set. Otherwise print
  "skill-cap checks: phone only" beside each pick.

### Trust and wording findings (also required before the pass)

**T1. The word "Avoid" on one loss differs by surface.**
- Workbook `wr_NsAvoidLine`: "⚠ Avoid: Ann — 0-1 · SMALL SAMPLE".
- Phone: "Lost once · 1 meeting — Recorded loss". Packet: "Recorded loss:".
- Smallest fix: use the phone and Packet wording in `wr_NsAvoidLine`.

**T2. The Packet evidence-page Basis column hides direction on thin rows.**
- Rows under 3 meetings print only "SMALL SAMPLE", so a 1-0 and a 0-1 get the same label.
- Smallest fix: print both, for example "Favorable direct · SMALL SAMPLE".

**T3. The workbook uses "first by recorded direct results".**
- It appears in `best_text` (Lineup Lab, Command Center) and the War Room "Top opportunities" heading.
- The phone says "Direct-record order #1".
- Smallest fix: use the phone wording.

**T4. The Packet Blind Send line lacks the small-sample count.**
- The phone shows "· K small-sample pairings"; the Packet shows only the meeting total
  (`wr_BlindMeetingNote`).
- Smallest fix: add the same count.

### Not findings

The Packet's 3-line and War Room's 5-line preview limits are acceptable once P2 puts each opponent's own
cautions on its options line. Scouting and Quick Read stay full-roster history; this is disclosed on
every surface.
