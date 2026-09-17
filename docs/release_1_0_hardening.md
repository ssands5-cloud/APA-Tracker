# APA Tracker 1.0 Release Hardening

This document records the release-candidate gates being closed before promoting `1.0.0-rc1` to `1.0.0`.

## Code gates

- Stale PR #12: closed without merge. Its removal of standings win/loss fields would delete real derived fallback history merely for shape consistency.
- Stale PR #13: superseded by the current-main transplant in PR #15. Matchup volatility is a recent normalized rate (`changes / valid transitions`), not a capped raw count.
- APA Team Skill Level Limit: standard 5-player/23 path remains preferred; the verified 4-player/19 fallback is available only when the five-player path is proven impossible and the four-player path is proven legal. The fallback requires forfeiting match 5. Unknown skill levels never trigger a forfeit recommendation.
- Full pytest matrix, Playwright dashboard regression, and CI-mode pipeline smoke must pass on the exact hardening SHA before merge.

## Operational gates

The version must remain `1.0.0-rc1` until both operational gates below have direct evidence:

1. **Main-branch protection**: `main` must require the repository's Tests status before merge/push. A ruleset or branch protection rule must be visible in GitHub.
2. **Live-data production acceptance**: run the live GraphQL sync against the real configured APA account/database, then build the Coach Advantage Bundle from that resulting database and verify its manifest/checksums/READY marker. Fixture-only CI is necessary but not sufficient for this gate.

No `1.0.0` tag/version bump should be made from source review alone.