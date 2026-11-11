# ESPN-style showcase (`/showcase`)

A broadcast-style league experience for APA pool, in `apps/ultimate-coach-web`: Home, Matchup, Standings, Power Rankings, Players, and Results & Stats. It is separate from the protected `/dashboard`, which it does not touch.

**Local and GitHub only.** Nothing here is deployed. `apps/ultimate-coach-web/vercel.json` opts `claude/*` branches out of Vercel (see "Deployment safety"). Any Vercel deployment needs Paul's explicit approval.

## Two data sources, one engine

| | Simulated (default) | Local real-data beta |
|---|---|---|
| Source | `src/lib/showcase/simulate.ts`: a deterministic invented 8-team division | A git-ignored export of Paul's own division |
| When | Always, unless the gate below is open | Only under `next dev`, on localhost, with `UC_SHOWCASE_REAL=1` |
| Labels | "SIMULATED" badge and footer | Amber "LOCAL BETA · REAL APA DATA" banner |

Both produce the same `RawSeason` shape (`src/lib/showcase/types.ts`); `src/lib/showcase/engine.ts` turns it into everything the screens show. `src/lib/showcase/league.ts` is the single module the pages import.

## What the engine computes

- **Ratings:** every player starts at 1500 and is updated game by game in order, `K = 28`, expected score `1 / (1 + 10^((opponent − player) / 400))`.
- **Win probability (individual):** the rating formula above, evaluated before each game. **Team win probability:** the chance the home team wins a majority of its individual matches, from the individual probabilities. These are model estimates, **not calibrated**, and are not the production evidence engine. Probability publication for real data stays forbidden until Paul decides otherwise.
- **Projected score:** each pairing contributes `p × avg winner points + (1 − p) × avg loser points`, using the averages of the season's real or simulated games.
- **Projected lineups:** the best-rated five whose skill levels fit under the cap (default 23), chosen from players who appeared in the team's last five matches, paired in rating order. Real captains choose the order at the table.
- **Standings:** computed from the scoresheets. In real mode **rank and points are APA's own session standings** (they include bye-week points; ties share a rank), and win-loss is computed from the scoresheets.
- **Power index:** `5 × points per week + 3 × points per match over the last three weeks + (average roster rating − 1500) / 6`.
- **League activity:** upsets (a winner under 36% going in), shutouts, five-match win streaks, ten-win milestones, 5-0 sweeps, and skill-level changes as recorded in the scoresheets.

Real divisions have byes (9 teams, 4 matches a week), ties, unrated players and unknown playoff rules; none of that is invented. Byes show as "—", unrated players with no games are omitted from the export and counted in its notes, and the playoff line is hidden when the rule is unknown.

## Run it

All commands from `apps/ultimate-coach-web`. Node 24 and pnpm 11 are bundled under `C:\Users\ssand\.cache\codex-runtimes\codex-primary-runtime\dependencies\node`.

```bash
pnpm install --frozen-lockfile
node node_modules/next/dist/bin/next dev --hostname 127.0.0.1 --port 3011   # then open http://127.0.0.1:3011/showcase
```

**Real-data beta**

1. Export a division from a refresh run (read-only on the run's database; writes only into the git-ignored `private-snapshots/`):
   ```bash
   python scripts/export_showcase_snapshot.py --run ultimate-coach-runs/refresh/<run-folder> [--division <id>]
   ```
   It defaults to the viewer's first division, merges duplicate scoresheet aliases only on an exact team and name match, and records a coverage note saying whether the run's coverage gaps fall in that division.
2. Create `apps/ultimate-coach-web/.env.local` (git-ignored) containing `UC_SHOWCASE_REAL=1`.
3. Restart `next dev`. The export is read once at startup.

## Deployment safety

- Real data is read only when **all** hold: `UC_SHOWCASE_REAL=1`, `NODE_ENV=development`, no `VERCEL`, `VERCEL_ENV` or `CI` variable (`src/lib/server/showcase-real.ts`).
- The layout answers any non-localhost `Host` header with a 404.
- The file lives in `private-snapshots/` and `.env.local` is covered by `.env*`; both are git-ignored. The build never traces that folder.
- Browser (`'use client'`) files may not import season data or server code; `nav-items.ts` exists so the tab bar stays data-free.
- Before any push, scan the diff against every real name in the export; none may appear in code, docs, commit messages or GitHub comments.
- `git.deploymentEnabled` in `apps/ultimate-coach-web/vercel.json` sets `false` for `feat/phase1-war-room`, `claude/espn-broadcast-dashboard` and `claude/*`. Vercel reads it from the pushed commit, so it works on a branch's first push. Verified by commit statuses, check runs and deployment records (all empty) after each push. Other branches, including `codex/*`, still get a preview unless they carry an entry.

## Tests

```bash
node --conditions=react-server --experimental-strip-types --test tests/*.test.ts
node node_modules/typescript/bin/tsc --noEmit
node node_modules/next/dist/bin/next build
```

`tests/showcase.test.ts` covers: simulated-season consistency (standings add up, probabilities in (0, 1), lineups fit the cap), the real-data gate (production, Vercel, CI and non-local hosts all refuse), no browser file importing season data, no private file tracked, no placeholder text or network calls in showcase source, and the engine on a real-shaped division (byes, tied APA ranks, fewer than five players).

## Known limits

- Ratings in a 14-week season stay within a few points of even, so most pairings read as toss-ups. That is what the data supports, not a styling choice.
- Real skill levels change up and down during the season in APA's own scoresheets; the feed reports them as recorded.
- No Playwright suite is committed; layout was checked with ad hoc headless runs at 1280 px and 390 px. A committed visual test is the obvious next step.
- Fonts load from Google Fonts; a self-hosted copy would remove that external request.
