import type { Snapshot } from '../lib/snapshot-types';
import { evidenceLabel } from '../lib/evidence-label';

/** Presentation of the supplied plan only. No ranking or recommendation is calculated here. */
export function CaptainCommand({ snapshot: s, matchNight = false }: { snapshot: Snapshot; matchNight?: boolean }) {
  const threat = s.threats[0];
  const threatOpponent = s.opponents.find(player => player.name === threat?.name);
  const opportunity = s.plan.strongest;
  const opportunityOpponent = s.opponents.find(player => player.name === opportunity.their);
  const responseLink = (id?: string) => `/dashboard/match-night${id ? `?opponent=${encodeURIComponent(id)}` : ''}#response-explorer`;

  return <section className="captain-command" aria-label="Captain Command Center">
    <header className="command-fixture">
      <div>
        <p className="command-kicker">{matchNight ? 'Match Night · War Room' : "Tonight’s Match Plan"}</p>
        <h1>{s.fixture.team} <span>vs</span> {s.fixture.opponent}</h1>
        <p>{s.fixture.format} · {s.fixture.when} · {s.fixture.venue}</p>
      </div>
      <span className="command-scope">Historical reference{' '}<br/>Confirm tonight’s fixture &amp; roster</span>
    </header>

    <div className="command-intelligence">
      <div className="command-recommendation">
        <p className="command-kicker">Strategic Recommendation · If we put up first</p>
        <h2><span>Lead with</span> {s.plan.lead.player}</h2>
        <span className="command-confidence">{evidenceLabel(s.plan.lead.level)}</span>
        <p className="command-why"><strong>Why:</strong> {s.plan.lead.why}</p>
        <a className="command-primary" href={matchNight ? '#response-explorer' : '/dashboard/match-night'}>{matchNight ? 'If they put up → Find our response' : 'Open Tonight’s Plan →'}</a>
        <p className="command-limit">Historical plan, not a win prediction. Confirm attendance, skill levels and the current cap before sending.</p>
      </div>

      <div className="command-scouting">
        <article className="command-dossier command-dossier-threat">
          <p className="command-kicker">Biggest recorded threat</p>
          <h2>{threat?.name ?? 'No winning direct-record threat identified'}</h2>
          <p>{threat?.text ?? 'Unknown opponents are not cleared. Inspect the evidence before choosing a response.'}</p>
          <a href={threatOpponent ? responseLink(threatOpponent.id) : '/dashboard/threats'}>{threatOpponent ? 'Prepare a counter →' : 'Scout the opposition →'}</a>
        </article>
        <article className="command-dossier">
          <p className="command-kicker">Best-supported opportunity · within this plan</p>
          <h2>{opportunity.our} <span>vs</span> {opportunity.their}</h2>
          <p><strong>{evidenceLabel(opportunity.level)}.</strong> {opportunity.why}</p>
          <a href={responseLink(opportunityOpponent?.id)}>Inspect this matchup →</a>
        </article>
      </div>
    </div>
  </section>;
}
