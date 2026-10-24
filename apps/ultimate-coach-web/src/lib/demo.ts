/** Entirely invented display fixture. No engine execution, external source or private identity. */
export type Evidence = { wins: number; losses: number; note: string };
export const players = [
  { id: 'demo-quinn', name: 'Quinn', skill: 4 },
  { id: 'demo-jordan', name: 'Jordan', skill: 5 },
  { id: 'demo-alex', name: 'Alex', skill: 3 },
] as const;
export const opponents = [
  { id: 'demo-xeno', name: 'Xeno', skill: 5 },
  { id: 'demo-yara', name: 'Yara', skill: 4 },
  { id: 'demo-zane', name: 'Zane', skill: 3 },
] as const;
export const fixture = {
  id: 'demo-night-01', team: 'Evergreen', opponent: 'Copper Ridge', format: '8-ball',
  when: 'Illustrative league night', venue: 'Demo room · Table 4',
  scope: '3-player demonstration roster', source: 'Synthetic fixture v1',
} as const;
export const evidence: Readonly<Record<string, Readonly<Record<string, Evidence>>>> = {
  'demo-xeno': {
    'demo-quinn': { wins: 1, losses: 0, note: 'Small sample · only 1 meeting' },
    'demo-jordan': { wins: 8, losses: 2, note: 'Deeper direct record · 10 meetings' },
    'demo-alex': { wins: 0, losses: 1, note: 'Lost once · only 1 meeting' },
  },
  'demo-yara': {
    'demo-quinn': { wins: 0, losses: 1, note: 'Lost once · only 1 meeting' },
    'demo-jordan': { wins: 0, losses: 1, note: 'Lost once · only 1 meeting' },
  },
  'demo-zane': {
    'demo-quinn': { wins: 2, losses: 1, note: '3 meetings · favorable direct record' },
    'demo-jordan': { wins: 1, losses: 0, note: 'Small sample · only 1 meeting' },
    'demo-alex': { wins: 1, losses: 1, note: 'Even direct record · 2 meetings' },
  },
};
export const responses: Readonly<Record<string, { player: string; why: string; cost: string }>> = {
  'demo-xeno': { player: 'Jordan', why: '8–2 across 10 direct meetings. This example favors deeper support over Quinn’s one-meeting edge.', cost: 'Sending Jordan spends the 1–0 record against Zane. That opportunity is also based on only 1 meeting.' },
  'demo-yara': { player: 'Alex', why: 'An illustrative unknown-evidence response. Quinn and Jordan each lost their only meeting with Yara; Alex has no direct record.', cost: 'No record does not establish a favorable matchup. This is a demonstration choice, not an engine recommendation.' },
  'demo-zane': { player: 'Quinn', why: '2–1 across 3 direct meetings. Jordan’s 1–0 is thinner; Alex’s record is even.', cost: 'Using Quinn here leaves Jordan available for the deeper Xeno record. Opponent order is not known.' },
};
export function record(row?: Evidence): string { return row ? `${row.wins}–${row.losses}` : 'No record'; }
export function meetings(row?: Evidence): number { return row ? row.wins + row.losses : 0; }
export function coverage(opponentId: string) {
  const rows = Object.values(evidence[opponentId] ?? {});
  return { players: rows.length, meetings: rows.reduce((sum, row) => sum + meetings(row), 0) };
}
