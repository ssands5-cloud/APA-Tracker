'use client';

import { useEffect, useState } from 'react';
import { record, meetings, type Snapshot } from '@/lib/snapshot-types';
import { opponentFromSearch } from './opponent-link';

export function HistoricalOpponentView({ snapshot }: { snapshot: Snapshot }) {
  const { evidence, players, opponents, responses } = snapshot;
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => {
    const requested = opponentFromSearch(window.location.search, opponents);
    setSelected(requested ?? opponents[0]?.id ?? null);
  }, [opponents]);
  if (!selected) return <section id="response-explorer" className="response-explorer" aria-live="polite"><div className="re-header"><p className="re-eyebrow">Response Explorer · War Room</p><p>{opponents.length ? 'Preparing the selected matchup…' : 'No opponents are available for this fixture.'}</p></div></section>;
  const answer = responses[selected];
  const recommendedPlayer = players.find(player => player.name === answer.player);
  const directEvidence = recommendedPlayer ? evidence[selected]?.[recommendedPlayer.id] : undefined;
  return (
    <section id="response-explorer" className="response-explorer">
      <div className="re-header">
        <p className="re-eyebrow">Response Explorer · War Room</p>
        <label htmlFor="opponent-re">If they put up</label>
        <select
          id="opponent-re"
          className="re-select"
          value={selected}
          onChange={event => setSelected(event.target.value)}
        >
          {opponents.map(opponent => (
            <option key={opponent.id} value={opponent.id}>
              {opponent.name} · SL {opponent.skill ?? 'unknown'}
            </option>
          ))}
        </select>
      </div>

      <div className="re-answer-dominant" aria-live="polite" aria-atomic="true">
        <span className="pill">Send · {answer.level} evidence</span>
        <h2 className="re-answer-name">{answer.player}</h2>
        <p className="re-answer-why"><strong>Why:</strong> {answer.why}</p>
        <p className="decision-evidence"><strong>Head-to-head:</strong> {directEvidence?.hasDirect ? `${record(directEvidence)} in ${meetings(directEvidence)} ${meetings(directEvidence) === 1 ? 'recorded meeting' : 'recorded meetings'}` : 'No recorded direct meeting; review the supporting evidence below.'}</p>
        <div className="decision-cautions"><p><strong>Risk:</strong> Not rated by the historical engine.</p><p className="command-cost decision-cost"><strong>Sending now costs:</strong> {answer.cost}</p></div>
        <details style={{ marginTop: 8 }}>
          <summary className="re-details-summary">Direct-record order and save-for-later cautions</summary>
          <p className="muted" style={{ marginTop: 8 }}>Direct-record order is separate from the M3 answer. Shared-only candidates remain unranked.</p>
          {answer.candidates.map((candidate, i) => (
            <div className="candidate" key={`${candidate.name}-${i}`}>
              <strong>{candidate.order ? `Direct-record order ${candidate.order}: ` : candidate.group === 'avoid' ? 'Losing direct record: ' : 'Shared, not ordered: '}{candidate.name}</strong>
              <p>{candidate.reason}</p>
              {candidate.save ? <p className="notice">{candidate.save}</p> : null}
            </div>
          ))}
        </details>
      </div>

      <div className="re-evidence-body">
        <h3>Evidence behind the choice</h3>
        <p className="muted re-evidence-note">Roster order below; this is not a ranked list.</p>
        <div className="evidence-list">
          {players.map(player => {
            const row = evidence[selected][player.id];
            return (
              <div key={player.id} className="evidence-row">
                <strong>{player.name}</strong>
                <span className="record">{record(row)}</span>
                <span>{meetings(row)} {meetings(row) === 1 ? 'meeting' : 'meetings'}</span>
                <p><span className="pill">{row.level}</span> {row.confidenceWhy}</p>
                <p>{row.note}</p>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
