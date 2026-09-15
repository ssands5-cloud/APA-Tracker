# Production demo walkthrough

This walkthrough uses either a database already regenerated according to
`database_regeneration_plan.md` or the optional guarded acquisition phase in
`scrape_and_ingest_pipeline.md`.

## Build

From the canonical APA Tracker root, use the future launcher contract:

```powershell
python scripts/run_production_demo.py --live --config apa_config.yaml --serve
```

For a no-network rehearsal, use a committed or explicitly approved fixture
tree instead:

```powershell
python scripts/run_production_demo.py --fixtures tests/fixtures/sample_pipeline --config tests/fixtures/ci_pipeline_config.yaml
```

The fixture run is expected to demonstrate fail-closed behavior when current
roster history is absent; it is not a rich production dataset.

For the full production path, first run the future guarded acquisition command
with an approved credential source, then point the demo launcher at that run's
verified database. Never put a token/password value directly on the command
line. Skip this step when a verified fresh database already exists.

## Browser sequence

1. Open the printed local URL and confirm the capture/provenance banner.
2. Select the real team, opponent, format, and session. Verify the opponent
   came from a scheduled match.
3. Read the DIRECT/INDIRECT/UNKNOWN cards and confirm their sum equals the
   matrix's feasible-pair count.
4. Inspect a DIRECT row: observed rate and distinct-match count are separate
   from any modeled probability.
5. Inspect an INDIRECT row when present: both current skill levels and the
   validated skill-only model source are visible.
6. Inspect an UNKNOWN row: it remains present and reads “No data.”
7. Toggle an unavailable player and use the page's availability view to verify
   the player is not silently lost.
8. Open the single Player vs Player navigation tab. In Matrix View, verify every
   feasible pair remains present in canonical structural order, including
   UNKNOWN, and confirm the coverage chart repeats the numeric counts.
9. Select one matrix row and confirm the same tab switches to Pair View.
   Verify the pair IDs/scope, compare distinct DIRECT matches with recognized
   game rows, review chronological history, and confirm unsupported metrics say
   “No data.”
10. Use browser Back/Forward and the subview buttons to confirm route state and
    filters restore without a refetch or recomputation.
11. Open Captain's Edge Opponent Risk Profile for the same pair. Verify values
    match Pair View, the capture/availability labels are visible, and Avoid and
    Target read “Not available — threshold not validated.”
12. Compare Matrix HTML/XLSX values and verify the selected Pair View matches
    its row and workbook history; inspect both artifact hashes in the manifest.
13. Open Lineup Lab. Review assignments, unassigned sides, total score, and the
   complete/partial/blocked legality state.
14. Open Data Coverage. Call out missing skills, sample sizes, capture/update
   dates, and unavailable fields.
15. Open `analysis_tabs.html`, then the workbook and JSON links. Confirm the
   selected snapshot and provenance match the primary page.
16. Open `demo_manifest.json` and record the run ID, commit, hashes, warnings,
   and test result in the presentation notes.

## Closing language

End with: “This is a decision aid whose confidence is visible. Where APA gave
us a real result or current skill level, we show it and name the source. Where
the snapshot cannot support a claim, the demo keeps the row visible and says
so.”
