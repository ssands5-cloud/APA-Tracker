/** Shapes shared by the showcase engine, the simulator and the local real-data loader. */

export type SeasonMode = 'simulated' | 'local-real';

export type LeagueMeta = {
  name: string; division: string; season: string; format: string; cap: number;
  currentWeek: number; totalWeeks: number; matchDate: string; matchTime: string;
  /** Highest team score seen so far; used only to scale charts and wording. */
  maxMatchPoints: number;
  /** Highest points one individual match can award (3 in APA 8-ball). */
  maxGamePoints: number;
  /** Playoff places, or null when the rule is not known. Nothing is invented for real data. */
  playoffSpots: number | null;
  venueKnown: boolean;
  mode: SeasonMode;
};

export type RawSlEvent = { week: number; from: number; to: number; announcedWeek?: number; note?: string };
export type RawPlayer = { id: string; name: string; team: number; sl: number; startSl: number; slEvents: RawSlEvent[] };
export type RawGame = { home: string; away: string; homePts: number; awayPts: number; winner: string };
export type RawMatch = { home: number; away: number; homePts: number; awayPts: number; homeWins: number; awayWins: number; games: RawGame[] };
export type RawWeek = { week: number; matches: RawMatch[] };
export type RawFixture = { home: number; away: number; homeLineup?: string[]; awayLineup?: string[] };
export type RawApaStanding = { team: number; rank: number; points: number; pointsLastWeek?: number | null; tied?: boolean; individualMatches?: number | null };

export type RawSeason = {
  league: LeagueMeta;
  myTeam: number;
  teams: { name: string; short: string; venue: string | null }[];
  players: RawPlayer[];
  weeks: RawWeek[];
  upcoming: RawFixture[];
  apaStandings?: RawApaStanding[];
  provenance?: { run: string; capturedAt: string | null; exportedAt: string; coverage: string; note: string };
};

/* ── Computed season ─────────────────────────────────────────────────────────── */
export type Player = {
  id: string; name: string; team: number; sl: number; startSl: number;
  rating: number; ratingHistory: number[];
  played: number; wins: number; losses: number; points: number; shutouts: number;
  form: ('W' | 'L')[]; weekly: { week: number; result: 'W' | 'L'; points: number; opp: string }[];
};
export type Team = { id: number; name: string; short: string; venue: string | null; roster: string[] };
export type IndividualMatch = { home: string; away: string; homePts: number; awayPts: number; winner: string; homeProb: number };
export type TeamMatch = { week: number; home: number; away: number; homePts: number; awayPts: number; homeWins: number; awayWins: number; games: IndividualMatch[]; homeProb: number };
export type Fixture = { week: number; home: number; away: number };
export type ActivityItem = { week: number; kind: 'upset' | 'shutout' | 'streak' | 'skill' | 'sweep' | 'milestone' | 'clinch'; text: string; team: number };
export type StandingRow = {
  team: Team; rank: number; tied: boolean; w: number; l: number; points: number; pointsPerWeek: number;
  indivW: number; indivL: number; winPct: number; streak: string; last5: ('W' | 'L')[]; behind: number; matchesPlayed: number;
};
export type PowerRow = { team: Team; rank: number; prev: number; score: number; avgRating: number; recentPts: number; blurb: string };
export type Preview = {
  fixture: Fixture; homeLineup: string[]; awayLineup: string[]; pairProbs: number[];
  homeProb: number; projHome: number; projAway: number;
};
