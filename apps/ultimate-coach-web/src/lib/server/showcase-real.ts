import 'server-only';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import type { RawSeason } from '../showcase/types.ts';

/**
 * LOCAL BETA ONLY. Loads the owner's own real division export for the ESPN-style showcase.
 *
 * It is on only when ALL of these hold: UC_SHOWCASE_REAL=1, NODE_ENV is "development" (that is,
 * `next dev`, never a build or `next start`), and no Vercel or CI variable is present. The file lives
 * in the git-ignored private-snapshots folder. A request-time host check in the showcase layout
 * additionally refuses any host other than localhost.
 */
export function realBetaEnabled(env: Record<string, string | undefined> = process.env): boolean {
  return env.UC_SHOWCASE_REAL === '1' && env.NODE_ENV === 'development' && !env.VERCEL && !env.VERCEL_ENV && !env.CI;
}

export const REAL_FILE = ['private-snapshots', 'showcase-real.json'] as const;

type Json = Record<string, unknown>;
const isObject = (v: unknown): v is Json => !!v && typeof v === 'object' && !Array.isArray(v);

export function parseRealSeason(text: string): RawSeason {
  const data = JSON.parse(text) as Json;
  if (data.schema !== 'ultimate-coach-showcase-real-v1') throw new Error('showcase real-data file has an unsupported schema');
  for (const key of ['league', 'teams', 'players', 'weeks', 'upcoming']) {
    if (!(key in data)) throw new Error(`showcase real-data file is missing "${key}"`);
  }
  const season = data as unknown as RawSeason & { league: Json };
  const teamCount = season.teams.length;
  const ids = new Set(season.players.map(p => p.id));
  if (!teamCount || !ids.size) throw new Error('showcase real-data file has no teams or players');
  for (const p of season.players) if (!(p.team >= 0 && p.team < teamCount)) throw new Error('a player points at a team that does not exist');
  for (const w of season.weeks) {
    for (const m of w.matches) {
      if (!(m.home >= 0 && m.home < teamCount && m.away >= 0 && m.away < teamCount)) throw new Error('a match points at a team that does not exist');
      for (const g of m.games) {
        if (!ids.has(g.home) || !ids.has(g.away) || (g.winner !== g.home && g.winner !== g.away)) throw new Error('a game references an unknown player');
      }
    }
  }
  const league = { ...(season.league as object), playoffSpots: null, mode: 'local-real' } as RawSeason['league'];
  return {
    league, myTeam: season.myTeam ?? 0, teams: season.teams, players: season.players, weeks: season.weeks,
    upcoming: season.upcoming.map(u => ({ home: u.home, away: u.away })), apaStandings: season.apaStandings, provenance: season.provenance,
  };
}

export function loadRealSeason(env: Record<string, string | undefined> = process.env, cwd: string = process.cwd()): RawSeason | null {
  if (!realBetaEnabled(env)) return null;
  // Opt out of build tracing: this path must never cause the project (or the private folder) to be bundled.
  const file = join(/*turbopackIgnore: true*/ cwd, ...REAL_FILE);
  if (!existsSync(file)) {
    console.warn('[showcase] UC_SHOWCASE_REAL=1 but no local export was found; showing the simulated league instead.');
    return null;
  }
  return parseRealSeason(readFileSync(file, 'utf8'));
}

/** True for the hosts a developer reaches `next dev --hostname 127.0.0.1` on. */
export function isLocalHost(host: string | null | undefined): boolean {
  return /^(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$/.test(host ?? '');
}
