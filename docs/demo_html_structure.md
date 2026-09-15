# Demo HTML structure

The HTML is static and self-contained so a captain can open it from a local
file or a loopback server. No page may depend on a CDN, API call, or Python
process after generation.

## Primary page shell

```text
document
└── main#captain-first-edge
    ├── header#demo-header
    │   ├── title
    │   ├── capture/provenance line
    │   └── data-status banner
    ├── section#tonights-match-controls
    │   ├── team select
    │   ├── opponent select
    │   ├── format select
    │   ├── session select
    │   └── availability controls (both sides)
    ├── section#evidence-summary
    │   ├── DIRECT count/percentage
    │   ├── INDIRECT count/percentage
    │   └── UNKNOWN count/percentage
    ├── section#pairing-matrix
    ├── section#lineup-lab
    │   ├── approved assignments
    │   ├── unassigned players
    │   ├── unassigned opponents
    │   └── legality/blocked reason
    ├── section#data-coverage
    │   ├── missing skill levels
    │   ├── sample sizes
    │   ├── refresh timestamps
    │   └── unavailable fields
    └── footer#provenance
```

The existing `ui/tabs/tonights_match.py` data payload remains the sole source
for embedded scope/matrix data. Stage 3 additions may project that payload into
Lineup Lab and Coverage panels, but they must not reclassify rows in JavaScript.

## Rendering and security

- Serialize embedded data with safe JSON that cannot terminate a script tag.
- Escape every captured name, ID, reason, and model-source string at the HTML
  insertion point.
- Keep unknown/unavailable states visible in the DOM, not only in a console log.
- Use semantic headings, labels, fieldsets, table headers, and keyboard-focus
  states. Color is supplemental to the evidence label text.
- Keep the page usable at a narrow viewport; the matrix may scroll
  horizontally, but controls and coverage cards must remain readable.
- Include a visible generated-at/capture-at distinction and the source database
  or manifest identifier.

## Supporting page

`analysis_tabs.html` wraps independent sections in a common shell. It may omit
a section when its source JSON is absent, but it must never emit an empty
placeholder card. The page order is Captain's Edge (if present), Lineup
Optimizer (if present), Head-to-Head, then Player Trends.

