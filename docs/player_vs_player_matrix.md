# Player vs Player matrix

Option C separates two related products with different ownership:

| Capability | Analytics owner | Unit of work |
| --- | --- | --- |
| Explicit pair comparison | `analytics/player_vs_player.py` | one selected player against one selected opponent |
| Whole-matrix drill-down | `analytics/player_vs_player_matrix.py` | every feasible player/opponent pair in one Stage 1 scope |

The matrix module is a pure composition layer. It does not query SQLite and it
does not add a third prediction model. Callers supply one canonical
`PairingEvidenceMatrix` plus exact-pair `PlayerHeadToHead` histories. The
current `head_to_head_history` query returns chronological all-history for the
two IDs; it is not format/session filtered. The module then reuses
`analytics.player_vs_player.summarize` for each pair.

## Implemented analytics contract

The public matrix API is:

```python
build_matrix_export(
    matrix: PairingEvidenceMatrix,
    histories: Mapping[tuple[int, int], Sequence[PlayerHeadToHead]],
    *,
    recent_games: int = 5,
    match_dates: Mapping[int, str] | None = None,
) -> tuple[PlayerVsPlayerExportRow, ...]
```

`rows_for_player(rows, player_id)` returns one player's rows without changing
their canonical order. A `PlayerVsPlayerExportRow` carries:

- team IDs, format, and session from the Stage 1 matrix;
- both players' internal IDs, external IDs, names, and current roster skill
  levels;
- the Stage 1 evidence label, distinct DIRECT-match count, and observed rate;
- one complete `PlayerVsPlayerSummary` with recognized games, record, average
  skill delta, reliability, last-recorded skill probability, modeled
  probability, trends, projection alias, and chronological game records;
- fixed disclosures for innings, per-opponent defense, per-opponent break/run,
  and numeric volatility, which are unavailable in this contract.

An absent history key is treated as an empty history. The resulting pair stays
in the matrix and receives the honest zero/null summary produced by
`summarize([])`.

## Evidence semantics

`direct_matches` and `summary.total_games` answer different questions and must
remain separate. Stage 1 counts distinct authoritative team matches for its
DIRECT label. The pair summary counts recognized game rows; one team match can
contain multiple games for the same pair.

The numeric fields also remain separate:

- `observed_win_rate` is a Stage 1 DIRECT fact;
- `summary.reliability` is `n / (n + 3)` over recognized games;
- `summary.skill_only_probability` uses the posted skill levels in the last
  recognized game, so the export label is **Last recorded skill probability**;
- `summary.modeled_win_probability` combines the explicit pair's history and
  last recorded skill through the existing Head-to-Head function;
- `summary.next_match_projection` is currently an exact alias of the modeled
  probability, not a schedule lookup or a second forecast.

No renderer may blend these values. The full modeled probability and its
projection alias remain experimental context because current validation has no
held-out rematch observations for the history term. Neither may drive default
order, recommendation language, or styling that implies approval.

## Deterministic construction and ordering

`build_matrix_export` emits every item in `matrix.pairings` exactly once and
sorts structurally by:

1. session name, case-insensitive;
2. format, with 8-ball before 9-ball before other formats;
3. our player name and external ID;
4. opponent name and external ID.

Evidence, score, and probability never affect order. Filters may narrow an
interactive view but reset must restore this sequence.

Before rendering, the orchestrator must verify:

- the matrix scope is explicit, while nested history is labeled all-history
  unless a future query applies and records an audited format/session filter;
- the output pair-key set equals the matrix's expected pair-key set;
- `DIRECT + INDIRECT + UNKNOWN` equals the feasible-pair count;
- `wins + losses == total_games` for every summary;
- each history record belongs to its row's exact internal player IDs;
- no duplicate pair key exists.

## UNKNOWN and unavailable data

UNKNOWN rows are first-class rows. They are never dropped, converted to an
observed 0%, or assigned a neutral probability. With no recognized history,
they show a 0-0 record, zero reliability, null probabilities/projection,
`no data` trends, and no game records. UI text must explain that zero games is
a count while the missing probabilities are unavailable values.

The matrix repeats the module's named unavailable-field disclosures. Captured
APA data has no innings, no per-opponent defense average, and no defensible
per-opponent break/run attribution. Numeric volatility belongs to a different
analytics scope and is not joined here.

## Matrix HTML structure

The implemented matrix artifact is `exports/player_vs_player.html`, produced
by `ui/export_html_player_vs_player.py`:

```text
body
├── h1 (Player vs Player)
├── evidence summary (scope and feasible/DIRECT/INDIRECT/UNKNOWN counts)
├── table#pvp-export-summary
│   └── one row per PlayerVsPlayerExportRow
└── section (Pairing details)
    └── one anchored explicit-pair fragment per row
```

The current compact table shows session, format, identities, current roster
skills, evidence label, distinct DIRECT matches, observed rate, and the
experimental modeled probability. Its Details link jumps to the existing
`ui/tabs/player_vs_player.py` fragment for that row; the fragment supplies the
recognized record, reliability, last-recorded skill probability (`skill_prob`
in export terminology), full/recent trends, projection alias, and chronological
games. The future router may expose that anchor as an explicit-pair route, but
must select the existing row rather than recompute it in JavaScript.

The current HTML is UTF-8, self-contained, escaped, and uses text evidence
labels in addition to color. Null is displayed as `No data` and zero stays
numeric zero. Demo integration must add keyboard-operable sorting, a responsive
table wrapper, provenance, the held-out-validation warning, and all four named
unavailable-field disclosures before treating the page as release-complete.

## Matrix Excel structure

The implemented matrix workbook is `exports/player_vs_player.xlsx`, produced
by `ui/export_excel_player_vs_player.py`. It is values-only, macro-free, and
deterministic.

### `Player_vs_Player`

One row per feasible pair, in matrix order, with this fixed column sequence:

1. Session
2. Format
3. Our Team ID
4. Opponent Team ID
5. Player
6. Player External ID
7. Player SL
8. Opponent
9. Opponent External ID
10. Opponent SL
11. Evidence Label
12. Direct Matches
13. Observed Win Rate
14. Total Games
15. Wins
16. Losses
17. History Reliability (games)
18. Last Recorded Skill-Gap Probability
19. Modeled Win Probability (experimental)
20. Trend (whole history)
21. Trend (recent)
22. Forward-Looking Pair Projection (experimental)

### `PvP_Game_History`

Created only when at least one real game exists. It contains player/opponent
external IDs, match ID/date, result, posted skills, points, 9-ball balls,
format, and session. Rows follow parent matrix order and then each summary's
chronological game order. A header-only history sheet is not a successful data
artifact.

External IDs are text and probability/rate cells retain the raw analytics
floats. The current workbook applies fixed widths and header styles but no
percentage number format; any future presentation format must be deterministic
and must not alter the stored value. There are no volatile formulas, macros,
external links, locale-dependent dates, current-time formatting, or data-based
reordering.

## Export integration plan

| Module | Planned responsibility |
| --- | --- |
| `ui/export_html_player_vs_player.py` | Implemented whole-matrix page; reuses the explicit-pair tab renderer for anchored details |
| `ui/export_excel_player_vs_player.py` | Implemented matrix workbook and optional chronological history sheet |
| `scripts/build_player_vs_player_export.py` | Implemented read-only query/orchestration boundary; writes the two matrix artifacts |
| `exports/html_builder.py` | Future demo integration should delegate to the existing HTML renderer rather than duplicate it |
| `exports/excel_builder.py` | Future demo integration should delegate to the existing workbook renderer rather than duplicate it |
| `ui/router.py` | Register one Player vs Player tab; route `view=matrix` to all rows and `view=pair` to one existing row/detail |
| `demo.py` | Invoke the read-only matrix build once, encode the unified tab document, register artifacts, and verify parity |

The cross-module export rules are summarized in
`player_vs_player_exports.md`. The reusable explicit-pair component is
specified in `player_vs_player_html_structure.md`; the implemented matrix
workbook is specified in `player_vs_player_excel_structure.md`.

## Demo integration plan

The production sequence is:

```text
Tonight's Match → Player vs Player (Matrix View → Pair View)
→ Lineup Lab → Data Coverage → HTML/Excel review
```

Tonight's Match opens the unified tab in Matrix View with a canonical scope.
Selecting a matrix row switches the same tab to Pair View for that row. The
artifact index offers the HTML/XLSX; HTML script JSON carries both subviews'
source data and the workbook contains the matching all-pair summary and game
history.

Release validation compares matrix HTML and Excel by stable pair key before
display rounding, then compares each embedded explicit-pair detail with its
source row and game records. Any missing row, duplicate, UNKNOWN suppression,
null-to-zero conversion, source mismatch, or renderer-added calculation blocks
the demo.

This design changes documentation only. It does not modify
`analytics/player_vs_player.py` and does not require regenerating `BUILD_INFO`.
