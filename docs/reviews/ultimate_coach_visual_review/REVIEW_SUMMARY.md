# Ultimate Coach — Visual Review Package

**Purpose:** an honest external UX and coaching review. The question is whether this feels like **a
professional APA captain's war room** or **a sophisticated data workbook**. It shows the real experience,
rough edges included; nothing was retouched or hidden.

| | |
|---|---|
| Captured | 2026-10-07 (evening, America/Denver) |
| Build | PR #83 code revision `45659f4` (draft, not accepted) |
| Artifacts captured | `Ultimate_Coach_FINAL_UAT.html` SHA256 `8A35EAF0…258F` and `Ultimate_Coach_FINAL_UAT.xlsx` SHA256 `9E432DB0…AF28`, both from `build-45659f4`. Hashes re-checked after capture: unchanged. |
| Data | Real staging snapshot: 15,180 identity-verified players and 828,316 evidence rows. Latest recorded result Sun Sep 20, 2026. |
| Fixture shown | **Sun Oct 11, 2026 · 11:00 AM MDT — Brunch Ballers (home) vs Spiraling Out Of Control · 8-Ball Open**. This is the real next fixture for the configured captain, Paul Smith. |
| Excel | Microsoft 365 Excel on Windows (1920×1080, 100% zoom), driven by keystrokes and captured from the screen. A scratch copy was used and closed without saving. No COM, no macros. |
| HTML | Chromium: desktop 1440×900, phone 390×844. |

**Read before reviewing:**
- **Real people.** Screenshots show real APA players' names and APA record IDs. The Match Day tab also shows the captain's league card number. Paul chose to publish them unredacted.
- **Illustrative planning marks.** To show the tool in use, the captain is marked Available + Planned, two teammates Available, and one opponent (Bob Waldvogel) "already played". These marks are illustrative, not real availability.
- **No coach notes.** Coach Notes are deliberately left empty: no observations were invented about real players.
- **Player vs Player example.** Paul Smith vs Miriam Goetzke, chosen because it is a real 1-0 direct meeting.

---

## WORKBOOK TOUR

- **Match Day** (`excel_03_*`, `html_04_*`): the one setup point. Pick player → team → format → scheduled date → fixture. Every other view follows it. In the HTML, a date with no fixture or a bye clears the matchup and says why (`html_15_*`).
- **Coach Dashboard / Command Center**
  - The **Command Center** (Excel tab `excel_02_*`; HTML "Tonight" panel `html_03_*`, `html_05_*`) is "tonight in 30 seconds": fixture, venue, freshness, our availability counts, the opponent roster, evidence counts, and the best-supported send per opponent with its reason.
  - The Excel tab named **Coach Dashboard** (`excel_09_*`) is a different thing: one player vs one player, showing direct record and meetings. The fuller HTML **Player vs Player** (`html_12_*`) adds profiles and shared opponents.
- **Lineup Lab** (`excel_05_*`, `html_08_*`): mark our players Available / Unavailable / Unknown and Planned / Played, and opponents already played. Marks are bound to one exact fixture. It shows remaining and selected skill totals with missing-SL disclosure, roster flexibility, best remaining sends **with reasons**, and protected players (the only remaining favorable option against an unplayed opponent).
- **Opponent Scouting** (`excel_06_*`, `html_10_*`): one card per opponent: team record, league lifetime, sample size, record vs our roster, meetings with our players, shared-opponent summary, record by opponent skill level, missing information, and coach observations (tags + note, labeled opinion).
- **Matchup Matrix** (`excel_04_part4-6`, `html_07_*`): our players (rows) × their players (columns).
  - Green = more direct wins than losses; red = more losses; yellow = even direct, or shared-opponent evidence only (≈); gray = none. Numbers are records with sample sizes.
  - HTML: tap a cell for the meetings and the shared-opponent breakdown.
  - **Excel shows no colors — see Known Gaps.**
- **Captain's Playbook / Captain Packet** (`excel_07_*`, `excel_08_*` print preview pages 1–5; `html_14_*`):
  - Page 1: fixture, both rosters with availability, best sends, risks.
  - Page 2: scouting cards.
  - Pages 3–4: evidence by opponent.
  - Page 5: meeting history.
- **Also included:** War Room overview (`excel_04_part1-3`, `html_06_*`), team comparison and ranking (`html_09_*`), START HERE onboarding (`excel_01_*`, `html_02_*`), phone (`html_16/17`), the bye-week state (`html_15_*`), and a raw reference tab (`excel_11_*`).

## WHAT HAS BEEN COMPLETED

**Major functionality:**
- One-setup Match Day that drives every view.
- War Room: rosters, best sends, dangerous opponents, avoid sends, open risks, matrix, Inspect.
- Lineup Lab with exact-fixture marks.
- Scouting cards with Coach Notes.
- Command Center.
- START HERE onboarding.
- Printable Captain Packet.
- Player vs Player.
- Both artifacts are generated from the same data and share wording.

**Data sources:**
- Recorded APA league results and schedules, captured into a local SQLite snapshot.
- Only identity-verified players (APA record IDs) and identity-verified games feed evidence.
- Quarantined or unresolved records are counted, never blended in.
- The snapshot never refreshes itself.

**Evidence engine:**
- Direct head-to-head records first, ranked by record and then number of meetings.
- Shared-opponent results are shown as "ours vs theirs" and deliberately not ranked against each other.
- Ties are shown. Every number carries its sample size.
- Each pairing's color category is only the sign of the recorded direct record. No thresholds, weights, odds or win probability ("NOT CALIBRATED").

**Scouting features:** per-opponent cards; record by opponent skill level, with winning and losing levels; meetings with our players; missing-information line; durable coach tags and observations, kept separate from evidence.

**Lineup planning features:**
- Availability (Unknown ≠ Unavailable) and Planned / Played marks.
- Opponent already-played marks.
- Remaining and selected skill totals that disclose missing SLs.
- An optional user-entered cap; none is assumed.
- Best remaining sends with reasons, open risks, protected players and roster flexibility.

## KNOWN GAPS

**Defects found while capturing this package** (visible in the screenshots, not yet fixed):
1. **Excel matrix has no colors** (`excel_04_part4-6`).
   - Conditional-format fills are written with a foreground color only, and Excel draws conditional fills from the background color. The tests check the rules exist, not how Excel paints them.
   - The same bug makes **Captain Packet page 2 card headers invisible** (white text on no fill, `excel_08_p2`): cards print without the opponent's name.
   - It also removes the evidence-row highlight (pages 3–4) and the meeting-row shading (page 5).
2. **#VALUE! errors in Excel War Room → Inspect** when no opponent or player is picked (`excel_04_part5-6`). Excel evaluates every argument of `OR()`, so the blank-input guard does not protect the lookups. The repo's formula evaluator effectively skipped the erroring arguments, so the tests missed it.
3. **Helper clutter in Excel:**
   - The matrix's category letters (G/I/E/X) are visible to the right of the matrix.
   - The Coach Dashboard shows "Pair key / Pair row" debug rows.
   - Reserved empty rows leave gaps in the War Room.
4. **Captain Packet page 5** (`excel_08_p5`): small text in the top third of the page, and the second line of each meeting is clipped by the row height.
5. **HTML matrix headers** run name and skill level together, e.g. "JD BOYESL 6 · ID 861925" (`html_07_*`).
6. **HTML Player vs Player** shows raw ISO dates ("2026-08-16T00:00:00+00:00") and format codes ("EIGHT").
7. **HTML page title** still says "Ultimate Coach — Scout & Compare", not War Room branding.

**Usability limitations:**
- Most matrix cells are "≈ shared-opponent only": 55 of 72 for this fixture. Direct meetings between two specific rosters are rare, so the color grid is mostly yellow and dense.
- A captain must interpret "≈ 27-14 vs 19-30 (26 shared)". This is honest, but it is not a quick read.
- The Excel War Room is long (about 190 rows) and needs scrolling. The Command Center is the intended quick view.
- 451 earlier fixtures still show UNPLAYED in this snapshot, so results after Sep 20 are missing.
- Rosters are current captured rosters, not who played on a past date. Venue is blank in the source ("No data").

**Areas still under development:** fixing defects 1–7; Excel Player vs Player (head-to-head only); a shared store for HTML and Excel planning marks and notes (none exists; each artifact keeps its own); Excel evidence comparisons are precomputed only for team pairs scheduled to play each other.

**Areas requiring UAT (PENDING PAUL REVIEW):**
- Real-Excel look and feel of every tab.
- The printed Captain Packet on paper.
- The 3-minute START HERE flow for a first-time captain.
- Whether the Command Center answers "who next?" in 30 seconds.
- Phone use at the table.

**Planned improvements:**
- Fix 1–7 above.
- Make the matrix scannable: separate direct records from shared-only, or show shared-only as a quieter state.
- A one-screen "next send" decision card that updates as the night goes.
- Shorter, captain-language evidence phrasing.

## COACHING GOAL

Ultimate Coach is meant to help an APA captain answer one question during a match:

> **"Who should I put up next?"**

Everything should serve that decision:
- who we play
- who's available
- which of our remaining players has the best recorded evidence against each opponent still to play
- which opponents are dangerous
- which pairings to avoid
- what we don't know

It uses recorded results only, and always shows sample sizes. It never shows odds, a confidence score or a "best lineup" verdict.

The success test is an experienced captain saying "this gives you an edge," not "that's a lot of data." Reviewers: please judge it against that.

## SCREENSHOT INDEX

**Excel** (real Excel, full window; tall tabs are captured in sequential parts top to bottom):

| File | What it shows |
|---|---|
| `excel_01_start_here_part1-3.png` | START HERE tab (opens first): what it does, quick start, workflow, worked example from this build, workbook tour, limitations, build info |
| `excel_02_command_center_part1-2.png` | Command Center: tonight's fixture, my team counts (3 Available, 6 Unknown, 1 planned), opponent roster, coaching summary, best-supported send per opponent with reason |
| `excel_03_match_day_part1-2.png` | Match Day control panel: inputs (yellow) and effective selections (calculated) |
| `excel_04_war_room_part1.png` | War Room: following status, overrides, match summary, both rosters with availability |
| `excel_04_war_room_part2-3.png` | War Room: best sends per opponent, top risks (dangerous / avoid / open), Lineup Lab snapshot |
| `excel_04_war_room_part4.png` | War Room: unique favorable options, empty reserved rows, start of the matrix (**no colors**) |
| `excel_04_war_room_part5.png` | War Room: rest of the matrix with visible helper letters; Inspect section showing **#VALUE!** errors |
| `excel_04_war_room_part6-7.png` | War Room: Inspect sections and direct meetings |
| `excel_05_lineup_lab_part1-3.png` | Lineup Lab with illustrative marks: availability/lineup, opponent played, results, best remaining sends with reasons |
| `excel_06_scouting_cards_part1-4.png` | Opponent scouting cards (sheet view; headers do render here) |
| `excel_07_captain_packet_sheet_part1-2.png` | Captain Packet tab in normal view |
| `excel_08_captain_packet_print_preview_p1.png` | Print preview page 1: fixture, both rosters with marks, best sends, top risks |
| `excel_08_captain_packet_print_preview_p2.png` | Page 2: scouting cards. **Card headers (names) invisible** |
| `excel_08_captain_packet_print_preview_p3-4.png` | Pages 3–4: evidence by opponent, opponent named on every line |
| `excel_08_captain_packet_print_preview_p5.png` | Page 5: meeting history, two across (small text, second lines clipped) |
| `excel_09_coach_dashboard_part1-2.png` | Coach Dashboard: Paul Smith vs Miriam Goetzke, 1-0 direct (with visible debug rows) |
| `excel_10_coach_notes_part1.png` | Coach Notes input sheet (empty by design) |
| `excel_11_schedule_reference_part1.png` | A raw reference tab (Schedule), to show what sits behind the coach tabs |

**HTML** (Chromium):

| File | What it shows |
|---|---|
| `html_01_first_screen_desktop.png` | What a captain sees on opening: header, freshness pills, Tonight panel, top of Start here |
| `html_02_start_here_card.png` | Start here card |
| `html_03_tonight_command_center.png` | Tonight (Command Center) before any marks: 9 Unknown |
| `html_04_match_day.png` | Match Day controls and fixture card |
| `html_05_tonight_with_marks.png` | Tonight after illustrative marks |
| `html_06_war_room_overview.png` | War Room: status, matchup header, both rosters, best sends, top risks |
| `html_07_matchup_matrix_with_detail.png` | Color matrix plus the tapped cell's evidence (Paul Smith vs Miriam Goetzke) |
| `html_08_lineup_lab.png` | Lineup Lab with marks, snapshot, best remaining sends with reasons, protected players |
| `html_09_team_comparison_and_ranking.png` | Team comparison and the evidence ranking of our players per opponent (Team vs Team) |
| `html_10_scouting_cards.png` | Scouting cards with empty coach-observation controls |
| `html_11_meeting_history.png` | Direct meetings between the rosters |
| `html_12_player_vs_player.png` | Player vs Player: Paul Smith vs Miriam Goetzke |
| `html_13_full_page.png` | The whole HTML page top to bottom (very tall) |
| `html_14_captain_packet_print_view.png` / `html_14_captain_packet.pdf` | The HTML Captain Packet as printed |
| `html_15_bye_week_state.png` | Tonight with Match Day set to the Nov 1 bye: no stale opponent or sends |
| `html_16_phone_first_screen.png` | Phone first screen (390×844) |
| `html_17_phone_full_page.png` | Phone full page (very tall) |

## Questions for the reviewer

1. In under a minute, can you tell who to put up against each opponent, and why?
2. Does the Command Center or Tonight panel help more than the War Room, or the other way round?
3. Is the "≈ shared-opponent" evidence useful at the table, or noise?
4. Would you carry the Captain Packet into the pool hall? What would you cut?
5. Where did you get lost or have to hunt?
