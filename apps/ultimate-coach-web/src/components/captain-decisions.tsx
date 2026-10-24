import type { Snapshot } from '../lib/snapshot-types';
import { evidenceLabel } from '../lib/evidence-label';

/** These cards narrate existing plan answers; they never rank or score players. */
export function ThreatDossiers({ snapshot: s }: { snapshot: Snapshot }) {
  if (!s.threats.length) return <section className="card"><h2>No named threat is established</h2><p>Missing evidence is not clearance. Start with the selected opponent’s response and its tradeoff.</p><a className="text-link" href="/dashboard/match-night#response-explorer">Find a response →</a></section>;
  return <div className="two-columns">
    {s.threats.map(threat => {
      const opponent = s.opponents.find(player => player.name === threat.name);
      const response = opponent ? s.responses[opponent.id] : undefined;
      const protections = s.plan.protect.filter(option => option.covers.includes(threat.name));
      const link = opponent ? `/dashboard/match-night?opponent=${encodeURIComponent(opponent.id)}#response-explorer` : '/dashboard/match-night#response-explorer';
      return <section className="card threat-dossier" key={threat.name}>
        <p className="eyebrow">Opponent dossier · historical reference</p>
        <h2>{threat.name}</h2>
        <dl className="dossier-actions">
          <div><dt>Plan’s counter</dt><dd>{response?.player ?? 'No response supplied'}</dd></div>
          <div><dt>Who to preserve</dt><dd>{protections.length ? protections.map(option => option.our).join(' · ') : 'No designated answer for this opponent'}</dd></div>
        </dl>
        <p><strong>Why dangerous:</strong> {threat.text}</p>
        <p><strong>Mistake to avoid:</strong> {protections.length ? 'Do not spend the designated answer before this matchup appears. One player can cover only one match.' : 'Do not treat a winning roster-level record as a proven advantage against every player.'}</p>
        {response ? <>
          <p><strong>Why this counter:</strong> {response.why}</p>
          <p><strong>Sending now costs:</strong> {response.cost}</p>
          <span className="pill">{evidenceLabel(response.level)}</span>
        </> : <p>No counter is established here. Inspect the recorded matchup evidence before sending.</p>}
        <p className="muted">Recorded meetings cover {threat.playersMet} of {s.players.length} captured players. {threat.meetings < 3 ? 'Small sample; this is not a proven dangerous matchup.' : 'Other pairings can remain unknown.'}</p>
        <a className="text-link" href={link}>Prepare this response →</a>
      </section>;
    })}
  </div>;
}

export function CaptainBriefing({ snapshot: s }: { snapshot: Snapshot }) {
  const threat = s.threats[0];
  return <section className="card captain-minute" aria-label="One-minute team briefing">
    <h2>Tell the team our plan</h2>
    <ol>
      <li><strong>Opening:</strong> If we put up first, lead with <b>{s.plan.lead.player}</b>. Evidence: {evidenceLabel(s.plan.lead.level)}.</li>
      <li><strong>Protect:</strong> {s.plan.protect.length ? s.plan.protect.map(option => `${option.our} for ${option.covers.join(' or ')}`).join('; ') + '.' : 'No matchup-specific protection is designated.'} One player can cover only one match.</li>
      <li><strong>Watch:</strong> {threat ? `${threat.name}. The recorded concern does not establish an advantage against everyone.` : 'No named threat is established. Unknown opponents are not cleared.'}</li>
      <li><strong>Tradeoff:</strong> {s.plan.protect.length ? 'Sending a protected player early spends a later answer. Keep the named matchups available.' : 'Check the future cost of each response; no designated hold does not mean no cost.'}</li>
      <li><strong>Before we start:</strong> Confirm who is here, the selected fixture and the actual cap. This is a historical plan.</li>
    </ol>
    <a className="command-primary" href="/dashboard/match-night#response-explorer">They put up? Find our response →</a>
    <details><summary>Why this opening and what the threat record says</summary><p><strong>Opening reason:</strong> {s.plan.lead.why}</p><p><strong>Threat evidence:</strong> {threat?.text ?? 'No winning direct-record threat is established.'}</p>{s.plan.protect.map(option => <p key={option.our}><strong>Preserve {option.our}:</strong> {option.why}</p>)}</details>
  </section>;
}
