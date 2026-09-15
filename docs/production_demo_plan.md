# Production demo plan

The production demo is assembled from one fresh authenticated scrape, one
regenerated database, and a versioned set of static exports. The detailed
architecture, regeneration, test, release, and walkthrough contracts live in
the adjacent `demo_*.md` documents.

## Player vs Player section

### Placement in the flow

Player vs Player appears after Tonight's Match establishes the real scope and
before Lineup Lab shows an assignment:

```text
Tonight's Match → Player vs Player → Lineup Lab → Data Coverage → Exports
```

This order makes the evidence inspectable before the assignment. It does not
replace the complete pairing matrix or hide UNKNOWN rows.

### Trigger

The captain can open Player vs Player from the primary navigation or from a
pairing row. A row-level link carries the two external player IDs plus the
selected team/opponent/format/session scope. `ui/router.py` resolves only
against the prebuilt analytics document; names are display metadata.

### Display

The HTML opens with the full canonical row order and the selected pair's detail
when launched from a matrix row. It shows Stage 1 DIRECT evidence, the current
analytics summary's recognized-game record, history reliability, last-recorded
skill probability, separately labeled experimental model output, whole/recent
pair trends, named innings/defense/break-run/volatility gaps, and the existing
forward pair-projection alias. No export-layer combined score exists.

### Export

`demo.py` writes `player_vs_player.html`, `player_vs_player.xlsx`, and the
optional versioned `player_vs_player.json` from the same in-memory document.
The run manifest records all three hashes and row counts. The demo index links
the HTML view and workbook download alongside the existing captain-first and
analysis artifacts.

### Validation

The build verifies pair-key reconciliation, DIRECT result arithmetic, null
semantics, formula/source tags, stable ordering, HTML escaping, workbook
readability, no formulas/macros/external links, and HTML/Excel/JSON parity.
Any mismatch blocks presentation.

## Current blockers

- `analytics/player_vs_player.py` and its single-pair UI reporter are in a
  separate implementation lane; the export builders, router, and `demo.py`
  integration are not implemented.
- A fresh authenticated scrape and regenerated schema are still required for a
  rich production dataset.
- Data Coverage remains a planned Stage 3 follow-up at the current repository
  head.
- The full history-plus-skill modeled probability and its identical
  `next_match_projection` alias are display-only until real held-out rematch
  validation exists; the current module does not establish a scheduled meeting.
- Per-opponent innings and defense averages have no captured APA source and
  must remain explicit gaps.
- Break/run is captured per team match, not per opponent, and numeric volatility
  is not produced by the current pair analytics contract; both remain explicit
  export gaps.
