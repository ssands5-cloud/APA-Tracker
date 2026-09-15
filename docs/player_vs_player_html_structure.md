# Unified Player vs Player HTML structure

The target experience is one top-level **Player vs Player** tab with two
presentation subviews:

- **Pair View** — one explicit player/opponent comparison owned by
  `analytics/player_vs_player.py`;
- **Matrix View** — every feasible pair in the selected scope, owned by
  `analytics/player_vs_player_matrix.py`.

The subviews share scope, identity, and provenance, but they do not share or
blend analytics formulas. The current standalone matrix export already embeds
the existing pair fragment at row anchors; the unified tab formalizes that
relationship inside the existing `ui/tabs` composition model.

## Page structure

```text
section#player-vs-player-tab
├── header#pvp-header
│   ├── team / opponent / format / session
│   ├── capture timestamp and source-manifest ID
│   └── model-validation and snapshot banners
├── nav#pvp-subviews (tablist)
│   ├── button#pvp-pair-tab   "Pair View"
│   └── button#pvp-matrix-tab "Matrix View"
├── section#pvp-pair-view (tabpanel)
│   ├── player and opponent selectors
│   ├── evidence / record cards
│   ├── table#pvp-pair-metrics
│   ├── figure#pvp-game-timeline
│   ├── table#pvp-game-history
│   ├── section#pvp-risk-profile
│   └── unavailable-data disclosure
├── section#pvp-matrix-view (tabpanel)
│   ├── player / opponent / evidence filters and Reset
│   ├── figure#pvp-coverage-chart
│   ├── table#pvp-matrix-table
│   └── matrix-level audit disclosure
└── footer#pvp-provenance
```

Pair View is the default when valid pair IDs are present in the route; Matrix
View is the default when only a scope is present. Switching subviews changes
visibility and URL state only. It never refetches data or recalculates a field.

## Routing model

The future `ui/router.py` owns one navigation entry, `player-vs-player`, with a
`view` parameter:

```text
player-vs-player?view=matrix&our_team_id=...&opponent_team_id=...&format=...&session=...
player-vs-player?view=pair&player_id=...&opponent_id=...&our_team_id=...&opponent_team_id=...&format=...&session=...
```

IDs in the static export may be encoded in fragment state instead of a query
string. In either form, external IDs plus the complete scope are authoritative;
names are display metadata. A pair route is valid only when its key exists in
the already-built matrix. Invalid, ambiguous, or stale state opens Matrix View
with an explicit error and no guessed selection.

Back/forward navigation must restore both subview and selected pair. Selecting
a matrix row changes the subview to Pair View and focuses the pair heading.
Returning to Matrix View restores the previous filters and scroll position.

## Script JSON contract

The orchestrator serializes one escaped JSON document into a non-executable
`<script type="application/json" id="pvp-data">` element. The document contains:

- schema version, run ID, capture time, and source hash;
- canonical scope and expected pair keys;
- ordered matrix rows and counts;
- each row's nested explicit `PlayerVsPlayerSummary` and chronological games;
- source/model status and unavailable-field disclosures;
- optional, audit-gated risk flag values plus threshold version/status.

The tab reads this element once with `textContent` and `JSON.parse`. It validates
the schema version and pair-key uniqueness before enabling controls. Script JSON
must use the repository's safe serializer so `<`, `>`, `&`, and script-closing
sequences cannot break out of the element. No captured string is inserted with
`innerHTML`; DOM text uses `textContent` or server-rendered escaped markup.

The browser may select, filter, sort a copy for display, switch subviews, and
draw inline SVG from delivered values. It may not query SQLite, fetch a URL,
call an analytics formula, fill a null, or write a recommendation.

## Pair View

The player and opponent selectors list only canonical matrix identities. The
selected pair shows:

- evidence label, distinct DIRECT matches, and observed win rate;
- an explicit label that Stage 1 evidence is selected-scope while the current
  pair summary is chronological all-history across formats/sessions;
- current roster skill levels, clearly separated from last-recorded game skills;
- recognized games, wins/losses, average skill delta, and reliability;
- last-recorded skill-only probability;
- experimental modeled win probability and identical projection alias;
- full-history and recent trends;
- an **Opponent Risk Profile** panel described below;
- chronological game history and the existing inline-SVG result timeline.

The metric table never collapses observed rate, reliability, skill probability,
and modeled probability into one score. The timeline sits below the evidence
cards and above the game table; it contains one accessible marker per real
game. Missing dates use match ID, not a generated date.

### Opponent Risk Profile

This panel is a sourced summary, not a new model. It lists evidence class,
sample counts, observed record, last-recorded skill probability, modeled-value
validation status, trends, and availability state. `Recommended Avoid` and
`Recommended Target` are shown only when an approved threshold specification
names its input, cohort, validation results, version, and effective date.

At the current validation state both flags render **Not available — threshold
not validated**. They must not be inferred from `modeled_win_probability`,
volatility, a color, or an arbitrary cutoff. If a future approved flag exists,
Pair View displays the delivered boolean and threshold version without
recomputing it.

## Matrix View

The initial table order is structural: session, 8-ball before 9-ball, player
name/external ID, then opponent name/external ID. The required columns are:

1. Player and current SL
2. Opponent and current SL
3. Evidence label
4. Distinct DIRECT matches
5. Observed win rate
6. Recognized games and W-L record
7. History reliability
8. Last-recorded skill probability
9. Modeled win probability (experimental)
10. Full/recent trend
11. Recommended Avoid
12. Recommended Target
13. Details action

The coverage chart sits above the table and shows counts—not scores—for DIRECT,
INDIRECT, and UNKNOWN. It is an accessible inline SVG or semantic bar group with
the numeric counts repeated in text. It never ranks players.

Filters hide rows only by explicit user action. Reset restores every row and
the canonical source order. Sorting is keyboard-operable, declares direction,
places `No data` last, and never changes the exported source order. Details
opens the same row in Pair View.

## UNKNOWN and missing data

UNKNOWN rows remain visible by default. A no-history pair shows 0 games, 0-0,
zero reliability, null probabilities, `no data` trends, and no timeline
markers. A missing value displays `No data` plus a reason; a measured zero stays
numeric zero. There is no 50% fallback.

Innings, per-opponent defense, per-opponent break/run rate, and numeric
volatility are named unavailable fields. The UI never substitutes lifetime
defense or differently scoped trend volatility. Missing roster identity blocks
matrix construction instead of inferring membership from historical play.

### Data Coverage bridge

Matrix View's evidence-count heading and every UNKNOWN row include a
presentation link to the unified Data Coverage tab. Pair View links missing
skill, sample-size, refresh, and unavailable-field disclosures to the matching
Data Coverage section. The route carries only a stable section/pair key; the
coverage report is already embedded and is never recalculated or narrowed at
the source. Returning to Player vs Player restores the prior subview, selection,
filters, and scroll position.

## Accessibility, safety, and deterministic formatting

- Subview controls implement tab/tabpanel roles, keyboard arrows, focus
  management, and visible focus.
- Tables use captions, scoped headers, and a horizontal overflow container.
- Evidence and flags use text/icons as well as color.
- HTML is UTF-8 and self-contained, with no external scripts, fonts, images, or
  runtime network requests.
- Percentages display as whole percentages to match the current renderer;
  reliability and skill delta use three decimals. Parity uses raw values before
  rounding.
- IDs, element order, disclosures, and initial row order derive from stable
  source keys, never random values or the viewer's clock.
