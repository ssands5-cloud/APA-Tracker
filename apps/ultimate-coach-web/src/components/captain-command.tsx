import type { Snapshot } from '../lib/snapshot-types';
import { evidenceLabel } from '../lib/evidence-label';

/** Presentation of the supplied plan only. No ranking or recommendation is calculated here. */
export function CaptainCommand({ snapshot: s, matchNight = false }: { snapshot: Snapshot; matchNight?: boolean }) {
  const threat = s.threats[0];
  const threatOpponent = s.opponents.find(player => player.name === threat?.name);
  const protectedOptions = s.plan.protect;
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
        <div className="command-risk">
          <p><strong>Biggest recorded concern:</strong> {threat?.text ?? 'Missing matchup evidence. No named threat does not mean a safe matchup.'}</p>
          <p>Risk is not rated by the historical engine.</p>
        </div>
        {protectedOptions.length > 0 && <p className="command-preserve"><strong>Don’t spend your next answer.</strong> Sending a protected player now uses an option this plan is saving for a later matchup.</p>}
        <a className="command-primary" href={matchNight ? '#response-explorer' : '/dashboard/match-night'}>{matchNight ? 'If they put up → Find our response' : 'Open Tonight’s Plan →'}</a>
        <p className="command-limit">Historical plan, not a win prediction. Confirm attendance, skill levels and the current cap before sending.</p>
      </div>

      <div className="command-scouting">
        <article className="command-dossier command-protect">
          <p className="command-kicker">Who to protect</p>
          {protectedOptions.length ? <>
            <ul className="command-protected-players">
              {protectedOptions.map(option => <li key={option.our}><strong>{option.our}</strong><span>Save for {option.covers.join(' or ')}.</span></li>)}
            </ul>
            <p><strong>Why:</strong> These are the plan’s designated answers. Use each player when their target is put up; one player can cover only one match.</p>
            <a href={matchNight ? '#protected-options' : '/dashboard/match-night#protected-options'}>See protection reasoning →</a>
          </> : <>
            <h2>No designated protection</h2>
            <p>The current plan does not identify a matchup-specific player to save. Check response tradeoffs before spending an option.</p>
            <a href={responseLink()}>Check response tradeoffs →</a>
          </>}
        </article>
        <article className="command-dossier command-dossier-threat">
          <p className="command-kicker">Biggest recorded threat</p>
          <h2>{threat?.name ?? 'No winning direct-record threat identified'}</h2>
          <p>{threat?.text ?? 'Unknown opponents are not cleared. Inspect the evidence before choosing a response.'}</p>
          <a href={threatOpponent ? responseLink(threatOpponent.id) : '/dashboard/threats'}>{threatOpponent ? 'Prepare a counter →' : 'Scout the opposition →'}</a>
        </article>
      </div>
    </div>
  </section>;
}
