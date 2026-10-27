import type { Snapshot } from '../lib/snapshot-types';
import { evidenceLabel } from '../lib/evidence-label';

/** Presentation of the supplied plan only. No ranking or recommendation is calculated here. */
export function CaptainCommand({ snapshot: s, matchNight = false }: { snapshot: Snapshot; matchNight?: boolean }) {
  const threat = s.threats[0];
  const protectedOptions = s.plan.protect;
  const firstProtection = protectedOptions[0];

  return <section className="captain-command" aria-label="Captain Command Center">
    <header className="command-fixture">
      <div>
        <p className="command-kicker">{matchNight ? 'Match Night · War Room' : "Tonight's Match Plan"}</p>
        <h1>{s.fixture.team} <span>vs</span> {s.fixture.opponent}</h1>
        <p>{s.fixture.format} · {s.fixture.when} · {s.fixture.venue}</p>
      </div>
      <span className="command-scope">Historical reference{' '}<br/>Confirm tonight's fixture &amp; roster</span>
    </header>

    <dl className="command-glance" aria-label="Five-second captain decisions">
      <div><dt>SEND · if we lead</dt><dd>{s.plan.lead.player}</dd><p>{evidenceLabel(s.plan.lead.level)}</p></div>
      <div><dt>PROTECT</dt><dd>{firstProtection?.our ?? 'No designated hold'}</dd><p>{firstProtection ? `For ${firstProtection.covers.join(' or ')}${protectedOptions.length > 1 ? ` · +${protectedOptions.length - 1} other protected options` : ''}` : 'Check response costs first'}</p></div>
      <div><dt>THREAT</dt><dd>{threat?.name ?? 'Not established'}</dd><p>{threat ? 'Recorded concern · inspect coverage' : 'Unknown does not mean safe'}</p></div>
      <div><dt>TRADEOFF</dt><dd>{firstProtection ? "Don't spend your next answer" : 'Check what sending costs'}</dd><p>{firstProtection ? 'Keep the designated matchup available' : 'No extra safety is implied'}</p></div>
    </dl>
    {matchNight ? <details className="command-opening-details"><summary>Opening strategy and protection · if we put up first</summary><CommandReasoning snapshot={s} matchNight/></details> : <CommandReasoning snapshot={s}/>}
  </section>;
}

function CommandReasoning({ snapshot: s, matchNight = false }: { snapshot: Snapshot; matchNight?: boolean }) {
  const threat = s.threats[0];
  const threatOpponent = s.opponents.find(player => player.name === threat?.name);
  const protectedOptions = s.plan.protect;
  const alternatives = s.plan.lead.alternatives ?? [];
  const responseLink = (id?: string) => `/dashboard/match-night${id ? `?opponent=${encodeURIComponent(id)}` : ''}#response-explorer`;
  return <div className="command-intelligence">
      <div className="command-recommendation">
        <p className="command-kicker">Strategic Recommendation · If we put up first</p>
        <h2><span>Lead with</span> {s.plan.lead.player}</h2>
        <span className="command-confidence">{evidenceLabel(s.plan.lead.level)}</span>
        <p className="command-why"><strong>Why:</strong> {s.plan.lead.why}</p>
        <p className="command-cost">Opening-specific cost is not established in this snapshot.</p>
        {alternatives.length > 0 && <p className="command-alternative"><strong>Equally Supported Alternatives:</strong> {alternatives.join(' · ')}</p>}
        <div className="command-risk">
          <p><strong>Biggest recorded concern:</strong> {threat?.text ?? 'Missing matchup evidence. No named threat does not mean a safe matchup.'}</p>
          <p>Risk is not rated by the historical engine.</p>
        </div>
        {protectedOptions.map(opt => <p className="command-preserve" key={opt.our}><strong>{opt.our} is designated for {opt.covers.join(' or ')}.</strong> {opt.why}</p>)}
        <a className="command-primary" href={matchNight ? '#response-explorer' : '/dashboard/match-night'}>{matchNight ? 'If they put up → Find our response' : "Open Tonight's Plan →"}</a>
        <p className="command-limit">Historical plan, not a win prediction. Confirm attendance, skill levels and the current cap before sending.</p>
      </div>

      <div className="command-scouting">
        <article className="command-dossier command-protect">
          <p className="command-kicker">Who to protect</p>
          {protectedOptions.length ? <>
            <ul className="command-protected-players">
              {protectedOptions.map(option => <li key={option.our}><strong>{option.our}</strong><span>Save for {option.covers.join(' or ')}.</span></li>)}
            </ul>
            <p><strong>Why:</strong> These are the plan's designated answers. Use each player when their target is put up; one player can cover only one match.</p>
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
  </div>;
}
