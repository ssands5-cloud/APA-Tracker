'use client';

import { useState } from 'react';
import { evidence, players, opponents, responses, record, meetings } from '@/lib/demo';

export function OpponentView() {
  const [selected, setSelected] = useState<string>(opponents[0].id);
  const answer = responses[selected];
  return <section className="card"><p className="eyebrow">Response explorer · view only</p>
    <label htmlFor="opponent">If they put up</label>
    <select id="opponent" value={selected} onChange={event => setSelected(event.target.value)}>
      {opponents.map(opponent => <option key={opponent.id} value={opponent.id}>{opponent.name} · SL {opponent.skill}</option>)}
    </select><div aria-live="polite" aria-atomic="true"><div className="answer"><span className="pill">Illustrative answer</span>
      <h2>Consider {answer.player}</h2><p><strong>Why:</strong> {answer.why}</p></div><p className="notice"><strong>Tradeoff:</strong> {answer.cost}</p>
    <h3>Evidence behind the choice</h3><p className="muted">Roster order below; this is not a ranked list.</p>
    <div className="evidence-list">{players.map(player => { const row = evidence[selected][player.id]; return <div key={player.id} className="evidence-row">
      <strong>{player.name}</strong><span className="record">{record(row)}</span><span>{meetings(row)} {meetings(row) === 1 ? 'meeting' : 'meetings'}</span>
      <p>{row?.note ?? 'Unknown evidence · not a weak player'}</p></div>; })}</div></div>
  </section>;
}
