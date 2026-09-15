# Production demo walkthrough

This walkthrough assumes a fresh authenticated database has already been
regenerated according to `database_regeneration_plan.md`.

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
8. Open Player vs Player from a matrix row. Verify the pair IDs/scope, compare
   distinct DIRECT matches with recognized game rows, review the chronological
   history, and confirm unsupported metrics say “No data.”
9. Compare the Player vs Player HTML and workbook pair values and inspect their
   matching artifact hashes in the manifest.
10. Open Lineup Lab. Review assignments, unassigned sides, total score, and the
   complete/partial/blocked legality state.
11. Open Data Coverage. Call out missing skills, sample sizes, capture/update
   dates, and unavailable fields.
12. Open `analysis_tabs.html`, then the workbook and JSON links. Confirm the
    selected snapshot and provenance match the primary page.
13. Open `demo_manifest.json` and record the run ID, commit, hashes, warnings,
    and test result in the presentation notes.

## Closing language

End with: “This is a decision aid whose confidence is visible. Where APA gave
us a real result or current skill level, we show it and name the source. Where
the snapshot cannot support a claim, the demo keeps the row visible and says
so.”
