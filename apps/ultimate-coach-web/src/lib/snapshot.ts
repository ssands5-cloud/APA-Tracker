import raw from '../../data/snapshot.json';

export type Player = { id: string; name: string; skill: number | null; availability: string };
export type Evidence = { wins: number; losses: number; hasDirect: boolean; note: string; level: string; confidenceWhy: string; category: string; sharedCount: number };
export type Pairing = { our: string; their: string; level: string; game?: number; leader?: string };
export type Hold = { our: string; why: string; covers: string[] };
export type Response = { player: string; why: string; level: string; cost: string; candidates: { name: string; reason: string; save: string; group: string; order: number | null }[] };
export type Snapshot = {
  schema: string; mode: string; label: string;
  provenance: { capturedAt: string; latestResult: string; fixtureWhen: string; notice: string };
  fixture: { team: string; opponent: string; format: string; when: string; venue: string; scope: string; source: string };
  simulation: { cap: number; games: number; availability: string; capNote: string };
  players: Player[]; opponents: Player[];
  evidence: Record<string, Record<string, Evidence>>; responses: Record<string, Response>;
  threats: { name: string; text: string; wins: number; meetings: number; playersMet: number }[];
  plan: { lead: { player: string; level: string; why: string; alternatives: string[] }; holds: Hold[]; protect: Hold[];
    sacrifices: (Pairing & { why: string })[]; responses: string; summary: string;
    ifWeLead: Pairing[]; ifTheyLead: Pairing[]; bestBoard: Pairing[]; safestBoard: Pairing[];
    cap: { cap: number; used: number; cheapest_rest: number; slack: number; incomplete: boolean } | null;
    fragility: { rating: string; player: string | null; thinPairings: string[] };
    strongest: Pairing & { why: string }; weakest: Pairing & { why: string } };
  totals: { meetings: number; directPairs: number; possiblePairs: number; favorablePairs: number; concerningPairs: number };
};

// Fail the build on a wrong contract instead of silently falling back to invented players.
if (raw.schema !== 'ultimate-coach-dashboard-snapshot-v1' || raw.mode !== 'historical-simulation'
    || raw.label !== 'REALISTIC DEMO USING HISTORICAL DATA' || !raw.players.length || !raw.opponents.length) {
  throw new Error('Dashboard snapshot contract is invalid');
}
export const snapshot = raw as Snapshot;
export const { players, opponents, fixture, evidence, responses } = snapshot;
export function record(row?: Evidence): string { return row?.hasDirect ? `${row.wins}–${row.losses}` : 'No direct record'; }
export function meetings(row?: Evidence): number { return row?.hasDirect ? row.wins + row.losses : 0; }
