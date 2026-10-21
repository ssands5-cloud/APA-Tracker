import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
const s = JSON.parse(readFileSync('data/snapshot.json', 'utf8'));

test('historical snapshot has explicit simulation and source-date disclosures', () => {
  assert.equal(s.schema, 'ultimate-coach-dashboard-snapshot-v1');
  assert.equal(s.label, 'REALISTIC DEMO USING HISTORICAL DATA');
  assert.equal(s.mode, 'historical-simulation');
  assert.ok(s.provenance.capturedAt && s.provenance.latestResult && s.provenance.fixtureWhen);
  assert.match(s.simulation.availability, /assumed available/i);
  assert.ok(s.players.length >= 5 && s.opponents.length >= 5);
});
test('every pair is represented and direct meeting totals agree', () => {
  let pairs = 0, total = 0, favorable = 0, concerning = 0;
  for (const opponent of s.opponents) {
    assert.ok(s.players.some((p: {name:string}) => p.name === s.responses[opponent.id].player));
    for (const player of s.players) {
      const row = s.evidence[opponent.id][player.id];
      assert.ok(row.level && row.confidenceWhy);
      assert.ok(Number.isInteger(row.wins) && row.wins >= 0);
      assert.ok(Number.isInteger(row.losses) && row.losses >= 0);
      if (row.hasDirect) { pairs++; total += row.wins + row.losses; }
      if (row.hasDirect && row.wins + row.losses === 1) assert.match(row.note, /small sample|1 meeting/i);
      favorable += row.hasDirect && row.category === 'G' ? 1 : 0;
      concerning += row.hasDirect && row.category === 'R' ? 1 : 0;
    }
  }
  assert.equal(pairs, s.totals.directPairs); assert.equal(total,s.totals.meetings);
  assert.equal(favorable,s.totals.favorablePairs); assert.equal(concerning,s.totals.concerningPairs);
  assert.equal(s.players.length*s.opponents.length,s.totals.possiblePairs);
});
test('five-game plans and boards use unique roster members within simulated caps', () => {
  for (const key of ['ifWeLead','ifTheyLead','bestBoard','safestBoard']) {
    const rows = s.plan[key];
    assert.equal(rows.length, s.simulation.games);
    assert.equal(new Set(rows.map((r: {our:string})=>r.our)).size, rows.length);
    assert.equal(new Set(rows.map((r: {their:string})=>r.their)).size, rows.length);
    const ourSL=rows.reduce((sum:number,r:{our:string})=>sum+s.players.find((p:{name:string})=>p.name===r.our).skill,0);
    const theirSL=rows.reduce((sum:number,r:{their:string})=>sum+s.opponents.find((p:{name:string})=>p.name===r.their).skill,0);
    assert.ok(ourSL<=s.simulation.cap,`${key}: our cap`);
    assert.ok(theirSL<=s.simulation.cap,`${key}: their cap`);
  }
  for (const hold of s.plan.protect) assert.ok(hold.covers.length && s.plan.holds.some((h:{our:string})=>h.our===hold.our));
});
test('only projected display data is committed; no private identity or credential keys', () => {
  const text=JSON.stringify(s);
  assert.doesNotMatch(text, /"(?:external_id|player_id|memberNumber|card_number|cookie|access_token|password|source_db|evidence_index|strings)":|Bearer |C:\\\\/);
  assert.ok(s.players.every((p:{id:string})=>/^our-\d+$/.test(p.id)));
  assert.ok(s.opponents.every((p:{id:string})=>/^their-\d+$/.test(p.id)));
});
test('web code has no APA, database, persistence or refresh integration', () => {
  function files(folder: string): string[] {return readdirSync(folder,{withFileTypes:true}).flatMap(e=>e.isDirectory()?files(join(folder,e.name)):[join(folder,e.name)]);}
  for (const file of files('src')) {
    const text=readFileSync(file,'utf8');
    assert.doesNotMatch(text,/fetch\(|XMLHttpRequest|localStorage|sessionStorage|indexedDB|process\.env|dangerouslySetInnerHTML|use server|\.db["']/i,file);
    assert.doesNotMatch(text,/export\s+(?:async\s+)?function\s+(?:POST|PUT|PATCH|DELETE)\b/,file);
    assert.doesNotMatch(text,/next\/link|<Link\b/,file);
  }
});
