# Claude surface-parity audit (auditor findings for the builder)

Claude audits; GPT builds. The latest audit is at the top. Each finding names an exact fixture,
the screens that disagree and the smallest fix. Ranking logic is not to be redesigned.

**Stopping condition:** phone, HTML, workbook and Packet cannot lead a captain to different decisions
from the same evidence. When met, the audit entry here says `SURFACE PARITY PASS`.

The phone needs no separate check: it renders through the same `ui.ultimate_coach` code and
`ultimate_coach_war_room.js` as the HTML, so it can differ only by snapshot date and local marks.

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
