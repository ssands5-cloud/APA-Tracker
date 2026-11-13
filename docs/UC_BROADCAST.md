# Ultimate Coach: broadcast experience (`ui="broadcast"`)

The standalone offline Ultimate Coach page, presented in the "APA Pool App Redesign" artifact's experience: the artifact's
header, seven tabs, ticker, scoreboard hero, facts strip and matchup rows. The decision engine is unchanged.

Build it: `python scripts/build_ultimate_coach_production.py --db <staging.db> --out <dir> --ui broadcast`
(the default stays `--ui classic`). In code: `render(payload, ..., ui="broadcast")`.

## Tabs and what lives in them
| Tab | Contents (all existing capabilities) |
|---|---|
| Home | Scoreboard (team pickers, status), facts strip (date, format, **Reference Cap = the existing skill-cap input**, venue), Key Matchups: one row per "if they put up X, send Y" from the engine's Match Night Plan, with recorded head-to-head bars (sample sizes shown, never odds) and the engine's evidence level |
| Schedule Planner | Match Day: who I am, team, format, date, fixtures, coverage notes |
| Match Night | The live board: tap who they put up, **Send now** (the engine's answer), alternatives, risks accepted, bench (availability), Send, **Record result**, **Undo send**; the full classic evidence card behind "Full evidence" |
| Recommendations | Team/opponent/format selectors, matchup head, best sends, evidence matrix, team comparison, team matchups, meetings, Player vs Player |
| Threats | Top risks, scouting cards with coach notes, matchup notes |
| Team Status | Lineup Lab (availability, lineup, played, cap, snapshot) and both rosters |
| Summary | Start here, data freshness and trust |

## Rules
- Recommendations come from the same engine code as the classic page; a test compares the Home rows and the Match Night
  answer with the engine's own plan. Recorded results (tonight's local score) never change any evidence or recommendation.
- One file, offline, no network. Fonts: the artifact's Barlow faces are used when installed and fall back to system
  condensed fonts; bundling them is pending the owner's go-ahead.
- Printing (Captain Packet) includes every matchup section regardless of the tab on screen.
- Tests: `tests/test_ultimate_coach_broadcast_browser.py`; the full existing browser suites also run against this UI with
  `UC_TEST_UI=broadcast python -m pytest -p tests.uc_broadcast_plugin <suite>`.

## Companion workbook and historical evidence

**Recommended Lineup** follows Match Day and shows one row per teammate. Lock an opponent in the yellow dropdown to reserve that player and recalculate the other rows. **Five-Game Plan** shows the engine's two starting sequences and lets the captain compare trial pairings. Live replanning after confirmed sends remains in Broadcast Match Night.

To build matching local HTML and Excel files with historical evidence, supply a completed refresh folder, a local history archive, and the refresh configuration.

```powershell
python scripts/build_ultimate_coach_archive_evidence.py --refresh-root <refresh-folder> --archive-db <archive.sqlite> --config <apa_config.yaml> --out <new-output-folder>
```

The builder verifies the refresh database checksum, retains its rosters and fixtures, and adds identity-verified archive results involving the scoped players. Refreshed fixtures take precedence. It validates both artifacts and writes their hashes in `history-scope.json`. The scheduled refresh uses its configured seed and runs separately.

When the archive was checked after the refresh, pass its verified timestamp with `--archive-checked-at` and include the UTC offset. Use a refreshed fixture snapshot if a fixture in that snapshot gained or changed a result after it was captured.
