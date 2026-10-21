'use client';

import { useState } from 'react';
import { record, meetings, type Snapshot } from '@/lib/snapshot-types';

export function HistoricalOpponentView({ snapshot }: { snapshot: Snapshot }) {
  const { evidence, players, opponents, responses } = snapshot;
  const [selected, setSelected] = useState<string>(opponents[0].id);
  const answer = responses[selected];
  return <section className="card"><p className="eyebrow">Response explorer · view only</p>
    <label htmlFor="opponent">If they put up</label>
    <select id="opponent" value={selected} onChange={event => setSelected(event.target.value)}>
      {opponents.map(opponent => <option key={opponent.id} value={opponent.id}>{opponent.name} · SL {opponent.skill}</option>)}
    </select><div aria-live="polite" aria-atomic="true"><div className="answer"><span className="pill">M3 response · {answer.level}</span>
      <h2>{answer.player}</h2><p>{answer.why}</p></div><p className="notice"><strong>Future cost.</strong> {answer.cost}</p>
    <details><summary>Direct-record order and save-for-later cautions</summary><p className="muted">Direct-record order is separate from the M3 answer. Shared-only candidates remain unranked.</p>
      {answer.candidates.map((candidate, i) => <div className="candidate" key={`${candidate.name}-${i}`}><strong>{candidate.order ? `Direct-record order ${candidate.order}: ` : candidate.group === 'avoid' ? 'Losing direct record: ' : 'Shared, not ordered: '}{candidate.name}</strong><p>{candidate.reason}</p>{candidate.save ? <p className="notice">{candidate.save}</p> : null}</div>)}
    </details>
    <h3>Evidence behind the choice</h3><p className="muted">Roster order below; this is not a ranked list.</p>
    <div className="evidence-list">{players.map(player => { const row = evidence[selected][player.id]; return <div key={player.id} className="evidence-row">
      <strong>{player.name}</strong><span className="record">{record(row)}</span><span>{meetings(row)} {meetings(row) === 1 ? 'meeting' : 'meetings'}</span>
      <p><span className="pill">{row.level}</span> {row.confidenceWhy}</p><p>{row.note}</p></div>; })}</div></div>
  </section>;
}
