# Demo release plan

The release is a versioned evidence bundle, not a claim that every analytics
module in the repository is validated.

## Stages

1. **Internal rehearsal** — fresh authenticated scrape, scratch regeneration,
   full checklist, manual walkthrough, and redacted evidence capture.
2. **Demo candidate** — freeze the source commit and capture manifest, rerun
   from a clean environment, review all artifacts, and have a second reviewer
   verify the captain-first claims.
3. **Presentation release** — publish the candidate bundle to the approved
   internal location, with capture timestamp and known limitations attached.
4. **Post-demo archive** — retain the manifest, checksums, test report, and
   rollback pointer; expire raw authenticated data according to policy.

## Release gates

- Fresh authenticated data and current-roster TeamStat rows are present.
- No stale schema or unavailable required scope is hidden.
- All required artifacts pass the checklist and tests.
- The narrative does not call excluded analytics validated advice.
- Issue #14 comment links the documentation commit and factual test evidence.

## Rollback

If a page, workbook, or data claim is found wrong, withdraw the bundle and
restore the previous approved bundle. Do not patch a generated artifact by
hand; regenerate from a corrected source commit and new manifest. Preserve the
failed manifest and redacted logs for diagnosis.

