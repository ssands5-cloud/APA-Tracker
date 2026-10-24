import { Card, Notice, PageTitle } from './ui';
import { HistoricalOpponentView } from './historical-opponent-view';
import { PlanBoard } from './plan-board';
import { record, meetings, type Snapshot } from '@/lib/snapshot-types';

function Assumptions({ snapshot: s }: { snapshot: Snapshot }) { return <Notice>{s.simulation.availability} Reference cap: {s.simulation.cap}. {s.simulation.capNote} Historical fixture: {s.provenance.fixtureWhen}. Latest recorded result: {s.provenance.latestResult}.</Notice>; }
function PairSupport({ title, pair }: { title: string; pair: Snapshot['plan']['strongest'] }) { return <Card title={title}><span className="pill">{pair.level}</span><h3>{pair.our} → {pair.their}</h3><p>{pair.why}</p><p className="muted">Evidence strength within the conditional plan; not a predicted win or loss.</p></Card>; }
function Holds({ snapshot: s, protect = false }: { snapshot: Snapshot; protect?: boolean }) {
  const rows = protect ? s.plan.protect : s.plan.holds;
  return <Card kicker={protect ? 'Preserve the named opportunity' : 'Future lineup value'} title={protect ? 'Protect / designated answers' : 'Hold-back options'}>
    {rows.length ? rows.map(row => <div key={row.our} className="candidate"><h3>{row.our}</h3><p>{row.why}</p>{row.covers.length ? <p className="notice">Keep for {row.covers.join(', ')}; send when that matchup is put up. One player can cover only one match.</p> : <p className="muted">General remaining-plan value; no unique target is claimed.</p>}</div>) : <p>No designated hold is established under these assumptions.</p>}
  </Card>;
}

/* ─── Home ─────────────────────────────────────────────────────────────────── */
export function HomePage({ snapshot: s }: { snapshot: Snapshot }) {
  const { players, opponents, fixture } = s;
  return <>
    {/* ARENA HERO */}
    <div className="arena-hero">
      <svg viewBox="0 0 900 270" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
        <defs>
          <radialGradient id="ah-sg1" cx="18%" cy="3%" r="52%">
            <stop offset="0%" stopColor="rgba(220,190,80,0.18)"/>
            <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
          </radialGradient>
          <radialGradient id="ah-sg2" cx="50%" cy="3%" r="55%">
            <stop offset="0%" stopColor="rgba(220,190,80,0.22)"/>
            <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
          </radialGradient>
          <radialGradient id="ah-sg3" cx="75%" cy="3%" r="42%">
            <stop offset="0%" stopColor="rgba(220,190,80,0.14)"/>
            <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
          </radialGradient>
          <linearGradient id="ah-gold" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="transparent"/>
            <stop offset="20%" stopColor="#c9a840"/>
            <stop offset="50%" stopColor="#e8c85a"/>
            <stop offset="80%" stopColor="#c9a840"/>
            <stop offset="100%" stopColor="transparent"/>
          </linearGradient>
          <linearGradient id="ah-lv" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgba(4,11,5,0.88)"/>
            <stop offset="50%" stopColor="rgba(4,11,5,0.35)"/>
            <stop offset="100%" stopColor="rgba(4,11,5,0)"/>
          </linearGradient>
          <linearGradient id="ah-bv" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(4,11,5,0)"/>
            <stop offset="100%" stopColor="rgba(4,11,5,0.94)"/>
          </linearGradient>
        </defs>
        {/* Arena background */}
        <rect width="900" height="270" fill="#040b05"/>
        {/* Spotlight cones */}
        <polygon points="155,0 100,270 210,270" fill="rgba(201,168,64,0.042)"/>
        <polygon points="380,0 305,270 455,270" fill="rgba(201,168,64,0.058)"/>
        <polygon points="630,0 578,270 682,270" fill="rgba(201,168,64,0.048)"/>
        {/* Spotlight fixtures */}
        <circle cx="155" cy="5" r="8" fill="rgba(255,242,160,0.75)"/>
        <circle cx="380" cy="5" r="10" fill="rgba(255,242,160,0.88)"/>
        <circle cx="630" cy="5" r="8" fill="rgba(255,242,160,0.72)"/>
        {/* Pool table outer rail */}
        <rect x="468" y="28" width="408" height="214" rx="14" fill="#2a1204"/>
        <rect x="468" y="28" width="408" height="5" rx="4" fill="rgba(201,168,64,0.14)"/>
        {/* Felt surface */}
        <rect x="492" y="48" width="358" height="176" rx="5" fill="#0b3a0d"/>
        {/* Center light on felt */}
        <ellipse cx="672" cy="136" rx="145" ry="60" fill="rgba(14,70,16,0.38)"/>
        {/* 6 pockets */}
        <circle cx="494" cy="50" r="13" fill="#030904"/>
        <circle cx="848" cy="50" r="13" fill="#030904"/>
        <circle cx="494" cy="222" r="13" fill="#030904"/>
        <circle cx="848" cy="222" r="13" fill="#030904"/>
        <circle cx="671" cy="42" r="11" fill="#030904"/>
        <circle cx="671" cy="230" r="11" fill="#030904"/>
        {/* Rail diamond markers */}
        <polygon points="547,43 551,48 547,53 543,48" fill="rgba(201,168,64,0.5)"/>
        <polygon points="609,43 613,48 609,53 605,48" fill="rgba(201,168,64,0.5)"/>
        <polygon points="733,43 737,48 733,53 729,48" fill="rgba(201,168,64,0.5)"/>
        <polygon points="794,43 798,48 794,53 790,48" fill="rgba(201,168,64,0.5)"/>
        {/* Ball rack — 15-ball triangle */}
        {/* Row 5 back */}
        <circle cx="855" cy="152" r="8.5" fill="#f0c000"/>
        <circle cx="838" cy="152" r="8.5" fill="#1a6cc4"/>
        <circle cx="820" cy="152" r="8.5" fill="#ab1a1a"/>
        <circle cx="803" cy="152" r="8.5" fill="#6e22a8"/>
        <circle cx="786" cy="152" r="8.5" fill="#d45f00"/>
        {/* Row 4 */}
        <circle cx="846" cy="137" r="8.5" fill="#1a7a43"/>
        <circle cx="829" cy="137" r="8.5" fill="#5c1a1a"/>
        <circle cx="812" cy="137" r="8.5" fill="#f0c000"/>
        <circle cx="795" cy="137" r="8.5" fill="#1a6cc4"/>
        {/* Row 3 */}
        <circle cx="837" cy="122" r="8.5" fill="#ab1a1a"/>
        <circle cx="820" cy="122" r="8.5" fill="#050505"/>
        <circle cx="803" cy="122" r="8.5" fill="#6e22a8"/>
        {/* 8-ball white circle */}
        <circle cx="820" cy="122" r="4" fill="rgba(255,255,255,0.92)"/>
        {/* Row 2 */}
        <circle cx="828" cy="107" r="8.5" fill="#d45f00"/>
        <circle cx="811" cy="107" r="8.5" fill="#1a7a43"/>
        {/* Row 1 apex */}
        <circle cx="820" cy="92" r="8.5" fill="#5c1a1a"/>
        {/* Cue ball */}
        <circle cx="566" cy="136" r="12" fill="white"/>
        <circle cx="562" cy="132" r="4.5" fill="rgba(255,255,255,0.55)"/>
        {/* Cue stick */}
        <rect x="508" y="170" width="258" height="3.5" rx="1.75" fill="#d4a96a" opacity="0.4" transform="rotate(-15 508 170)"/>
        {/* Spotlight radial glows */}
        <rect width="900" height="270" fill="url(#ah-sg1)"/>
        <rect width="900" height="270" fill="url(#ah-sg2)"/>
        <rect width="900" height="270" fill="url(#ah-sg3)"/>
        {/* Gold top rail */}
        <rect x="0" y="0" width="900" height="4" fill="url(#ah-gold)"/>
        {/* Left text vignette */}
        <rect x="0" y="0" width="900" height="270" fill="url(#ah-lv)"/>
        {/* Bottom vignette */}
        <rect x="0" y="215" width="900" height="55" fill="url(#ah-bv)"/>
      </svg>
      <div className="arena-hero-overlay">
        <p className="arena-eyebrow">Historical Match Simulation · {fixture.format} · {fixture.scope}</p>
        <h2 className="arena-matchup">{fixture.team}<span className="arena-matchup-vs">vs</span>{fixture.opponent}</h2>
        <p className="arena-meta">{fixture.when} · Reference cap {s.simulation.cap}</p>
        <p className="match-readiness">Match readiness: <strong>Historical plan available</strong></p>
        <ul className="match-brief-points">
          <li><span aria-hidden="true">✓</span> {s.totals.favorablePairs} favorable direct {s.totals.favorablePairs === 1 ? 'record' : 'records'} identified</li>
          <li><span aria-hidden="true">!</span> {s.threats.length} {s.threats.length === 1 ? 'opponent' : 'opponents'} with winning direct records to scout</li>
          <li><span aria-hidden="true">●</span> {s.plan.lead.player ? `Opening option: ${s.plan.lead.player}` : 'Opening option unavailable'}</li>
        </ul>
        <a className="arena-cta" href="/dashboard/match-night">Open match plan <span aria-hidden="true">→</span></a>
      </div>
    </div>

    <nav className="captain-next" aria-label="Captain's next steps">
      <a href="/dashboard/match-night"><strong>01 · Make the call</strong><span>Explore responses to their put-up →</span></a>
      <a href="/dashboard/threats"><strong>02 · Scout the opposition</strong><span>Review recorded threats →</span></a>
      <a href="/dashboard/recommendations"><strong>03 · Check the evidence</strong><span>Compare matchup support →</span></a>
    </nav>

    <section className="captain-brief" aria-label="Captain's briefing">
      <div><p className="captain-kicker">Best opening move · historical plan</p><h2>Lead with {s.plan.lead.player}.</h2><p>{s.plan.lead.why}</p><a href="/dashboard/match-night">Open the match plan →</a></div>
      <div className="captain-brief-note"><p className="captain-kicker">Threat to scout</p><p>{s.threats[0] ? <><strong>{s.threats[0].name}</strong> — {s.threats[0].text}</> : 'No winning direct-record threat is established in this snapshot.'}</p><span>Historical simulation · confirm tonight’s roster</span></div>
    </section>

    <Card kicker="Captain readiness · confirm before the first put-up" title="Make the historical plan usable tonight">
      <div className="readiness-checks"><div><strong>1. Confirm the fixture</strong><p>This plan is for {fixture.team} vs {fixture.opponent}, {fixture.when}. Verify tonight’s opponent and format.</p></div><div><strong>2. Confirm who is here</strong><p>{s.simulation.availability} Attendance has not been verified.</p></div><div><strong>3. Confirm the rules</strong><p>The reference cap is {s.simulation.cap}; verify the current cap and player skill levels.</p></div></div>
      <a className="text-link" href="/dashboard/match-night">Review the opening and responses →</a>
    </Card>

    {/* BLIND SEND + OPPORTUNITIES */}
    <div className="two-columns">
      <Card kicker="Blind Send · M3 lead" title={s.plan.lead.player}>
        <span className="pill">{s.plan.lead.level} evidence vs worst reply</span>
        <p>{s.plan.lead.why}</p>
        <a className="text-link" href="/dashboard/match-night">See responses and holds →</a>
      </Card>
      <Card kicker="Team strengths, with limits" title="Use the opportunities we have">
        <p>{s.totals.favorablePairs} favorable direct pair records and {s.totals.concerningPairs} losing direct pair records are captured.</p>
        <p className="notice">{s.totals.possiblePairs - s.totals.directPairs} pairings have no verified direct meetings here. A full roster does not mean full evidence.</p>
        <p>Plan fragility: <strong>{s.plan.fragility.rating}</strong>{s.plan.fragility.player ? ` · leans most on ${s.plan.fragility.player}` : ''}.</p>
      </Card>
    </div>

    {/* KEY THREATS PREVIEW */}
    <Card kicker="Read before the first put-up" title="Key opposing threats">
      {s.threats.length ? s.threats.slice(0, 3).map(t => <p key={t.name}><strong>{t.name}</strong> — {t.wins}–{t.meetings - t.wins} vs the simulated available roster in {t.meetings} {t.meetings === 1 ? 'meeting' : 'meetings'}, covering {t.playersMet} of {players.length} players.{t.meetings < 3 ? ' Small sample.' : ''}</p>) : <p>No winning direct-record threat is established; missing evidence is not clearance.</p>}
      <a className="text-link" href="/dashboard/threats">See every threat and caution →</a>
    </Card>

    <Assumptions snapshot={s}/>
  </>;
}

/* ─── Match Night ───────────────────────────────────────────────────────────── */
export function MatchNightPage({ snapshot: s }: { snapshot: Snapshot }) {
  const { players, opponents, fixture } = s;
  const lead = players.find(p => p.name === s.plan.lead.player);
  const leadSL = lead?.skill;
  const leadRecords = opponents.map(opponent => lead ? s.evidence[opponent.id]?.[lead.id] : undefined);
  const recorded = leadRecords.filter(row => row?.hasDirect);
  const favorable = recorded.filter(row => row!.wins > row!.losses).length;
  const neutral = recorded.filter(row => row!.wins === row!.losses).length;
  const concern = recorded.filter(row => row!.wins < row!.losses).length;
  return <>
    {/* WAR ROOM HERO */}
    <div className="war-room-hero">
      <svg viewBox="0 0 900 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
        <defs>
          <radialGradient id="wr-sg1" cx="15%" cy="5%" r="60%">
            <stop offset="0%" stopColor="rgba(220,190,80,0.2)"/>
            <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
          </radialGradient>
          <radialGradient id="wr-sg2" cx="85%" cy="5%" r="55%">
            <stop offset="0%" stopColor="rgba(220,190,80,0.18)"/>
            <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
          </radialGradient>
          <linearGradient id="wr-gold" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="transparent"/>
            <stop offset="20%" stopColor="#c9a840"/>
            <stop offset="50%" stopColor="#e8c85a"/>
            <stop offset="80%" stopColor="#c9a840"/>
            <stop offset="100%" stopColor="transparent"/>
          </linearGradient>
          <linearGradient id="wr-bv" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(4,11,5,0)"/>
            <stop offset="100%" stopColor="rgba(4,11,5,0.95)"/>
          </linearGradient>
        </defs>
        <rect width="900" height="200" fill="#060e08"/>
        {/* Crosshair lines (war room grid feel) */}
        <line x1="0" y1="100" x2="900" y2="100" stroke="rgba(201,168,64,0.06)" strokeWidth="1"/>
        <line x1="450" y1="0" x2="450" y2="200" stroke="rgba(201,168,64,0.06)" strokeWidth="1"/>
        {/* Corner spotlights */}
        <polygon points="0,0 200,0 0,140" fill="rgba(201,168,64,0.03)"/>
        <polygon points="900,0 700,0 900,140" fill="rgba(201,168,64,0.03)"/>
        {/* 8-ball graphic top-right */}
        <circle cx="845" cy="38" r="28" fill="#141414"/>
        <circle cx="845" cy="38" r="12" fill="white" opacity="0.9"/>
        <circle cx="840" cy="34" r="5" fill="#141414"/>
        {/* Rack dots bottom right */}
        <circle cx="780" cy="170" r="5" fill="rgba(201,168,64,0.35)"/>
        <circle cx="796" cy="170" r="5" fill="rgba(171,26,26,0.35)"/>
        <circle cx="812" cy="170" r="5" fill="rgba(26,108,196,0.35)"/>
        <circle cx="788" cy="158" r="5" fill="rgba(110,34,168,0.35)"/>
        <circle cx="804" cy="158" r="5" fill="rgba(212,95,0,0.35)"/>
        <circle cx="796" cy="146" r="5" fill="rgba(26,122,67,0.35)"/>
        <rect width="900" height="200" fill="url(#wr-sg1)"/>
        <rect width="900" height="200" fill="url(#wr-sg2)"/>
        <rect x="0" y="0" width="900" height="4" fill="url(#wr-gold)"/>
        <rect x="0" y="155" width="900" height="45" fill="url(#wr-bv)"/>
      </svg>
      <div className="war-room-hero-overlay">
        <p className="arena-eyebrow">Match Night War Room · {fixture.format} · Cap {s.simulation.cap}</p>
        <h1>{fixture.team} <span style={{ color:'var(--gold)', fontWeight: 400 }}>vs</span> {fixture.opponent}</h1>
        <p>{fixture.when} · Historical simulation · {s.simulation.games} games</p>
      </div>
    </div>

    <div className="captain-decision-grid">
    <div className="captain-explorer">
      <HistoricalOpponentView snapshot={s}/>
    </div>
    <aside className="recommendation-primary" aria-label="Blind Send recommendation">
      <p className="rec-eyebrow">If we put up first · Blind Send</p>
      <div className="rec-player-row">
        {leadSL != null && (
          <div className="sl-ball" data-sl={leadSL} aria-label={`SL ${leadSL}`}>{leadSL !== 8 ? leadSL : ''}</div>
        )}
        <div style={{ flex: 1, minWidth: 0 }}>
          <p className="rec-player-name">{s.plan.lead.player}</p>
          <p className="rec-player-meta">{s.plan.lead.level} evidence</p>
        </div>
      </div>
      <p className="coverage-heading">Direct-record coverage</p>
      <div className="coverage-grid">
        <span>Favorable <strong>{favorable}</strong></span><span>Neutral <strong>{neutral}</strong></span>
        <span>Concern <strong>{concern}</strong></span><span>Unknown <strong>{opponents.length - recorded.length}</strong></span>
      </div>
      <p className="rec-player-meta">Evidence coverage: {recorded.length} of {opponents.length} opposing pairings contain a recorded direct meeting.</p>
      {s.plan.lead.alternatives.length > 0 && (
        <p className="rec-alternatives"><strong>Equally Supported Alternatives</strong><br/>{s.plan.lead.alternatives.join(', ')}</p>
      )}
      <details className="blind-send-details"><summary>View full analysis</summary><p>{s.plan.lead.why}</p></details>
    </aside>
    </div>

    {/* RESPONSE TABLE */}
    <Card kicker="If they lead instead" title="Response table">
      <div className="table-scroll" role="region" aria-label="Responses to every opposing player" tabIndex={0}>
        <table><thead><tr><th scope="col">Their put-up</th><th scope="col">Our response</th><th scope="col">Evidence</th><th scope="col">Future cost</th></tr></thead>
        <tbody>{opponents.map(opp => <tr key={opp.id}><th scope="row"><a href={`/dashboard/match-night?opponent=${encodeURIComponent(opp.id)}#response-explorer`} aria-label={`Explore the response to ${opp.name}`}>{opp.name}</a></th><td>{s.responses[opp.id].player}</td><td>{s.responses[opp.id].level}</td><td>{s.responses[opp.id].cost}</td></tr>)}</tbody></table>
      </div>
    </Card>

    <div className="two-columns"><Holds snapshot={s}/><Holds snapshot={s} protect/></div>

    <Card kicker="Tradeoffs, not instructions to lose" title="Sacrifice / concession candidates">
      {s.plan.sacrifices.length ? s.plan.sacrifices.map(p => <div className="candidate" key={`${p.our}-${p.their}`}><h3>{p.our} → {p.their}</h3><p><span className="pill caution">{p.level}</span> {p.why}</p></div>) : <p>No concession is proposed by this plan.</p>}
      <p className="muted">These are lowest-cost concessions within the current engine&apos;s assumptions, not predicted defeats or required sends.</p>
    </Card>

    <Card kicker="Five games · one conditional sequence" title="If we lead"><PlanBoard rows={s.plan.ifWeLead} caption="Conditional game plan if we put up first"/></Card>
    <Card kicker="Five games · the other opening" title="If they lead"><PlanBoard rows={s.plan.ifTheyLead} caption="Conditional game plan if they put up first"/></Card>
    <div className="two-columns">
      <Card title="Best-case board"><PlanBoard rows={s.plan.bestBoard} caption="Cooperative pairing reference; opponent may not allow it"/></Card>
      <Card title="Safest board"><PlanBoard rows={s.plan.safestBoard} caption="Evidence-floor pairing reference, not a guaranteed outcome"/></Card>
    </div>
    <Assumptions snapshot={s}/>
  </>;
}

/* ─── Recommendations ───────────────────────────────────────────────────────── */
export function RecommendationsPage({ snapshot: s }: { snapshot: Snapshot }) {
  const { players, opponents, evidence } = s;
  return <>
    <PageTitle eyebrow="The actual evidence behind each response" title="Recommendations">Existing M3 answers and direct-record ordering are shown separately. Counts and cautions stay beside the player.</PageTitle>
    <div className="two-columns">
      <HistoricalOpponentView snapshot={s}/>
      <div>
        <PairSupport title="Strongest evidence within the plan" pair={s.plan.strongest}/>
        <PairSupport title="Weakest evidence within the plan" pair={s.plan.weakest}/>
        <Card title="What these levels consider"><p>The existing engine evaluates direct record and meeting count, overall records, shared opponents and captured skill-level changes.</p><p>Recency and matchups are historical. Current form, presence, actual put-up order and tournament-rule clearance are not established by this snapshot.</p></Card>
      </div>
    </div>
    <Card kicker="Direct, shared and unknown evidence" title="Full matchup board">
      <p className="muted">Our perspective. No direct record is different from no evidence.</p>
      <div className="table-scroll" role="region" aria-label="Historical matchup board, scroll horizontally" tabIndex={0}>
        <table><thead><tr><th scope="col">Our player</th>{opponents.map(opp => <th scope="col" key={opp.id}>{opp.name}<small>Captured SL {opp.skill ?? 'unknown'}</small></th>)}</tr></thead>
        <tbody>{players.map(player => <tr key={player.id}><th scope="row">{player.name}<small>SL {player.skill ?? 'unknown'}</small></th>{opponents.map(opp => { const row = evidence[opp.id][player.id]; return <td key={opp.id}><strong>{record(row)}</strong><small>{meetings(row)} {meetings(row) === 1 ? 'meeting' : 'meetings'}</small><span className="pill">{row.level}</span><p>{row.confidenceWhy}</p><span>{row.note}</span></td>; })}</tr>)}</tbody>
        </table>
      </div>
    </Card>
  </>;
}

/* ─── Shark Tank (Threats) ──────────────────────────────────────────────────── */
export function ThreatsPage({ snapshot: s }: { snapshot: Snapshot }) {
  const { players } = s;
  return <>
    {/* SHARK TANK HERO */}
    <div className="shark-hero">
      <svg viewBox="0 0 900 200" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
        <defs>
          <radialGradient id="st-sr" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="rgba(192,57,43,0.22)"/>
            <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
          </radialGradient>
          <linearGradient id="st-water" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#020a12"/>
            <stop offset="100%" stopColor="#040e18"/>
          </linearGradient>
          <linearGradient id="st-gold" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="transparent"/>
            <stop offset="20%" stopColor="#c9a840"/>
            <stop offset="50%" stopColor="#e8c85a"/>
            <stop offset="80%" stopColor="#c9a840"/>
            <stop offset="100%" stopColor="transparent"/>
          </linearGradient>
          <linearGradient id="st-bv" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(2,10,18,0)"/>
            <stop offset="100%" stopColor="rgba(2,10,18,0.96)"/>
          </linearGradient>
          <linearGradient id="st-lv" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgba(2,10,18,0.88)"/>
            <stop offset="55%" stopColor="rgba(2,10,18,0.3)"/>
            <stop offset="100%" stopColor="rgba(2,10,18,0)"/>
          </linearGradient>
        </defs>
        {/* Deep water background */}
        <rect width="900" height="200" fill="url(#st-water)"/>
        {/* Water depth lines */}
        {[40,70,100,130,160].map(y => <line key={y} x1="0" y1={y} x2="900" y2={y} stroke="rgba(30,80,140,0.08)" strokeWidth="1"/>)}
        {/* Shark silhouette (right side) */}
        {/* Body */}
        <ellipse cx="680" cy="110" rx="160" ry="38" fill="rgba(10,20,30,0.85)"/>
        {/* Dorsal fin */}
        <polygon points="640,72 660,110 700,110 710,72" fill="rgba(10,20,30,0.85)"/>
        {/* Tail fin */}
        <polygon points="840,80 818,108 818,112 840,140 826,110" fill="rgba(10,20,30,0.8)"/>
        {/* Pectoral fin */}
        <polygon points="630,116 640,145 680,118" fill="rgba(10,20,30,0.7)"/>
        {/* Shark eye */}
        <circle cx="525" cy="108" r="5" fill="rgba(192,57,43,0.9)"/>
        <circle cx="524" cy="107" r="2" fill="rgba(0,0,0,0.9)"/>
        {/* Shark grin lines */}
        <path d="M 508 116 Q 520 126 532 116" stroke="rgba(10,20,30,0.9)" strokeWidth="2" fill="none"/>
        {/* Blood-red glow around shark */}
        <ellipse cx="650" cy="110" rx="200" ry="60" fill="url(#st-sr)"/>
        {/* Bubbles */}
        {[[510,85,3],[498,65,2],[520,55,4],[490,95,2.5]].map(([x,y,r],i) => <circle key={i} cx={x} cy={y} r={r} fill="rgba(100,160,220,0.18)"/>)}
        {/* Spotlight glows */}
        <rect width="900" height="200" fill="url(#st-sr)" opacity="0.4"/>
        {/* Gold top rail */}
        <rect x="0" y="0" width="900" height="4" fill="url(#st-gold)"/>
        {/* Left text vignette */}
        <rect x="0" y="0" width="900" height="200" fill="url(#st-lv)"/>
        {/* Bottom vignette */}
        <rect x="0" y="148" width="900" height="52" fill="url(#st-bv)"/>
      </svg>
      <div className="shark-hero-overlay">
        <p className="arena-eyebrow" style={{ color: 'var(--shark-bright)' }}>Shark Tank · Threat Intelligence</p>
        <h1>Know the water before you send.</h1>
        <p style={{ fontSize: 14, fontWeight: 650, color: '#eee4e4', margin: 0 }}>{s.threats.length} {s.threats.length === 1 ? 'threat' : 'threats'} with winning direct records · {players.length} players scouted</p>
      </div>
    </div>

    {/* SCOUTING REPORT CARDS */}
    <div className="two-columns" style={{ marginBottom: 20 }}>
      {s.threats.map(t => {
        const threatPct = Math.min(100, Math.round((t.wins / Math.max(t.meetings, 1)) * 100));
        const fillWidth = `${threatPct}%`;
        const opponent = s.opponents.find(player => player.name === t.name);
        const response = opponent ? s.responses[opponent.id] : undefined;
        const favorablePlayers = opponent ? players.filter(player => { const row = s.evidence[opponent.id]?.[player.id]; return row?.hasDirect && row.wins > row.losses; }) : [];
        return (
          <div className="shark-profile-card" key={t.name}>
            <div className="spc-header">
              <div className="spc-shark-icon" aria-hidden="true">🦈</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p className="spc-name">{t.name}</p>
                <div>
                  <span className="spc-record">{t.wins}W – {t.meetings - t.wins}L in {t.meetings} {t.meetings === 1 ? 'meeting' : 'meetings'}</span>
                  <span className="spc-coverage">{t.playersMet} of {players.length} met</span>
                </div>
              </div>
            </div>
            <div className="spc-body">
              <p className="spc-threat-level">Historical record — {threatPct}% wins in recorded meetings</p>
              <div className="spc-threat-bar"><div className="spc-threat-fill" style={{ width: fillWidth }}/></div>
              <p><strong>Why dangerous:</strong> {t.text}</p>
              <p><strong>Recorded opportunities:</strong> {favorablePlayers.length ? favorablePlayers.map(player => { const row = s.evidence[opponent!.id][player.id]; const count = meetings(row); return `${player.name} (${record(row)}; ${count} ${count === 1 ? 'meeting' : 'meetings'})`; }).join(' · ') : 'No favorable direct record is established in this snapshot.'}</p>
              {response && <div className="scouting-action"><span>Counter option</span><strong>Consider {response.player}</strong><p>{response.why}</p><p>Future cost: {response.cost}</p></div>}
              <Notice>{t.meetings < 3 ? 'Thin record: a small number of meetings is limited evidence, not a proven matchup.' : 'This is a winning recorded roster-level result; inspect each player\'s evidence before responding.'}</Notice>
            </div>
            <div className="spc-footer">
              <a href={opponent ? `/dashboard/recommendations?opponent=${encodeURIComponent(opponent.id)}` : '/dashboard/recommendations'}>Inspect response evidence →</a>
            </div>
          </div>
        );
      })}
    </div>

    <Card title="Why the warning is limited">
      <p>All captured players are assumed available. Changing availability can change the relevant threat scope. A record against only a few players is not evidence against every player on the roster.</p>
      <p>There are no predicted win percentages. Opponents without a listed winning direct record are not automatically safe.</p>
    </Card>
    <Assumptions snapshot={s}/>
  </>;
}

/* ─── Team Status ───────────────────────────────────────────────────────────── */
export function TeamStatusPage({ snapshot: s }: { snapshot: Snapshot }) {
  const { players, opponents, fixture } = s;
  return <>
    <PageTitle eyebrow="Player intelligence · historical reference" title="Team Status">Know who to lean on, protect, and scout before the first put-up. Availability is simulated, not a live attendance check.</PageTitle>
    <section className="roster-command" aria-label="Captain roster priorities">
      <div><p className="roster-command-label">Opening option</p><strong>{s.plan.lead.player}</strong><span>{s.plan.lead.level} evidence in the historical plan</span></div>
      <div><p className="roster-command-label">Protect</p><strong>{s.plan.protect.length ? s.plan.protect.map(item => item.our).join(' · ') : 'No designated answer'}</strong><span>Save matchup-specific options until their target appears.</span></div>
      <div><p className="roster-command-label">Scout first</p><strong>{s.threats[0]?.name ?? 'No named threat'}</strong><span>{s.threats[0] ? s.threats[0].text : 'Missing evidence is not clearance.'}</span></div>
    </section>
    <div className="two-columns">
      {[{ title: fixture.team, kicker: 'Our captured roster', roster: players, ours: true }, { title: fixture.opponent, kicker: 'Opponent captured roster', roster: opponents, ours: false }].map(team => (
        <Card key={team.title} title={team.title} kicker={team.kicker}>
          <ul className="roster">
            {team.roster.map(player => (
              <li className="player-intel-card" key={player.id}>
                <span className="avatar" aria-hidden="true">{player.name.slice(0, 1)}</span>
                <div className="player-intel-main"><strong>{player.name}</strong><small>{player.availability}</small>{team.ours && player.name === s.plan.lead.player && <small className="captain-player-tag">Opening option · historical plan</small>}{team.ours && s.plan.protect.some(item => item.our === player.name) && <small className="captain-player-tag">Protect for a matchup</small>}{!team.ours && s.threats.some(item => item.name === player.name) && <small className="captain-player-tag threat-tag">Scout · winning direct record</small>}</div>
                <span className="skill" aria-label={`Skill level ${player.skill ?? 'unknown'}`}><span>SL</span><b>{player.skill ?? '?'}</b></span>
                {team.ours && (() => {
                  const rows = opponents.map(opponent => s.evidence[opponent.id]?.[player.id]).filter(Boolean);
                  const direct = rows.filter(row => row!.hasDirect);
                  const favorable = direct.filter(row => row!.wins > row!.losses).length;
                  const concern = direct.filter(row => row!.wins < row!.losses).length;
                  return <p className="player-intel-evidence"><strong>{favorable}</strong> favorable · <strong>{concern}</strong> concern · {direct.length} recorded {direct.length === 1 ? 'pairing' : 'pairings'}</p>;
                })()}
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
    <Card kicker="Reference arithmetic · no legality claim" title="Skill-cap impact">
      <p><strong>{s.simulation.games} games remaining · simulated cap {s.simulation.cap}</strong></p>
      {s.plan.cap ? <>
        <p>Cheapest captured remaining lineup: {s.plan.cap.cheapest_rest} SL. Reference slack: {s.plan.cap.slack}. {s.plan.cap.incomplete ? 'Missing skill levels make this check incomplete.' : 'No missing skill level in this captured roster check.'}</p>
        <p>The M3 plan restricts both sides to the same supplied cap; no actual cap or local rule was verified.</p>
      </> : <p>No complete cap reference is available.</p>}
      <p className="notice">No one is marked played. This page cannot record presence, send players or change the cap.</p>
    </Card>
    <Card kicker="Team momentum" title="Recent form is not established">
      <p>The snapshot records its latest result as <strong>{s.provenance.latestResult}</strong>. It does not provide a verified sequence of recent results for each player, so streaks and current momentum cannot be determined here.</p>
      <p>Before match night, check attendance and recent play with your team, then use the historical matchups as supporting evidence.</p>
    </Card>
    <Assumptions snapshot={s}/>
  </>;
}

/* ─── Captain's Briefing (Summary) ─────────────────────────────────────────── */
export function SummaryPage({ snapshot: s }: { snapshot: Snapshot }) {
  const { fixture } = s;
  return <>
    {/* CAPTAIN'S BRIEFING HERO */}
    <div className="briefing-hero">
      <svg viewBox="0 0 900 190" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" preserveAspectRatio="xMidYMid slice">
        <defs>
          <radialGradient id="cb-sg" cx="50%" cy="10%" r="70%">
            <stop offset="0%" stopColor="rgba(220,190,80,0.24)"/>
            <stop offset="100%" stopColor="rgba(0,0,0,0)"/>
          </radialGradient>
          <linearGradient id="cb-gold" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="transparent"/>
            <stop offset="20%" stopColor="#c9a840"/>
            <stop offset="50%" stopColor="#e8c85a"/>
            <stop offset="80%" stopColor="#c9a840"/>
            <stop offset="100%" stopColor="transparent"/>
          </linearGradient>
          <linearGradient id="cb-bv" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="rgba(4,11,5,0)"/>
            <stop offset="100%" stopColor="rgba(4,11,5,0.95)"/>
          </linearGradient>
          <linearGradient id="cb-lv" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="rgba(4,11,5,0.85)"/>
            <stop offset="60%" stopColor="rgba(4,11,5,0.2)"/>
            <stop offset="100%" stopColor="rgba(4,11,5,0)"/>
          </linearGradient>
        </defs>
        <rect width="900" height="190" fill="#040b05"/>
        {/* Main spotlight */}
        <polygon points="450,0 320,190 580,190" fill="rgba(201,168,64,0.06)"/>
        <polygon points="450,0 370,190 530,190" fill="rgba(201,168,64,0.06)"/>
        <circle cx="450" cy="6" r="12" fill="rgba(255,242,160,0.92)"/>
        {/* Trophy art (right side) */}
        {/* Cup body */}
        <path d="M 730 140 Q 720 100 700 80 L 800 80 Q 780 100 770 140 Z" fill="rgba(201,168,64,0.25)"/>
        {/* Cup base */}
        <rect x="730" y="140" width="40" height="8" rx="2" fill="rgba(201,168,64,0.3)"/>
        <rect x="722" y="148" width="56" height="6" rx="3" fill="rgba(201,168,64,0.35)"/>
        {/* Cup handles */}
        <path d="M 700 90 Q 680 105 700 120 L 712 120 Q 694 106 712 90 Z" fill="rgba(201,168,64,0.2)"/>
        <path d="M 800 90 Q 820 105 800 120 L 788 120 Q 806 106 788 90 Z" fill="rgba(201,168,64,0.2)"/>
        {/* Star on trophy */}
        <polygon points="750,95 752,103 760,103 754,108 756,116 750,111 744,116 746,108 740,103 748,103" fill="rgba(201,168,64,0.45)"/>
        {/* Side spotlights */}
        <polygon points="100,0 60,190 140,190" fill="rgba(201,168,64,0.035)"/>
        <polygon points="800,0 760,190 840,190" fill="rgba(201,168,64,0.03)"/>
        <circle cx="100" cy="5" r="7" fill="rgba(255,242,160,0.6)"/>
        <circle cx="800" cy="5" r="7" fill="rgba(255,242,160,0.6)"/>
        <rect width="900" height="190" fill="url(#cb-sg)"/>
        <rect x="0" y="0" width="900" height="4" fill="url(#cb-gold)"/>
        <rect x="0" y="0" width="900" height="190" fill="url(#cb-lv)"/>
        <rect x="0" y="140" width="900" height="50" fill="url(#cb-bv)"/>
      </svg>
      <div className="briefing-hero-overlay">
        <p className="arena-eyebrow">Captain&rsquo;s Briefing · Historical Replay</p>
        <h1 className="briefing-hero-title">{fixture.team} <span style={{ color: 'var(--gold)', fontWeight: 400 }}>vs</span> {fixture.opponent}</h1>
        <p style={{ fontSize: 12, color: 'var(--chalk-muted)', margin: 0 }}>{fixture.when} · Cap {s.simulation.cap}</p>
      </div>
    </div>

    {/* BRIEFING ITEMS */}
    <div className="briefing-items">
      <div className="briefing-item lead">
        <span className="briefing-item-icon" aria-hidden="true">🎯</span>
        <div>
          <p className="briefing-item-type">Opening strategy</p>
          <p className="briefing-item-content"><strong>Lead with {s.plan.lead.player}.</strong> {s.plan.lead.why}</p>
        </div>
      </div>
      <div className="briefing-item protect">
        <span className="briefing-item-icon" aria-hidden="true">🛡</span>
        <div>
          <p className="briefing-item-type">Protect these players</p>
          <p className="briefing-item-content">{s.plan.protect.length ? s.plan.protect.map(h => `${h.our} for ${h.covers.join(', ')}; send when that matchup is put up.`).join(' ') : 'No unique designated-answer protection is established.'}</p>
        </div>
      </div>
      <div className="briefing-item threat">
        <span className="briefing-item-icon" aria-hidden="true">🦈</span>
        <div>
          <p className="briefing-item-type">Threat to scout</p>
          <p className="briefing-item-content">{s.threats[0]?.text ?? 'No winning direct-record threat established; inspect missing evidence.'}</p>
        </div>
      </div>
      <div className="briefing-item lead">
        <span className="briefing-item-icon" aria-hidden="true">🎱</span><div><p className="briefing-item-type">Best opportunity in the plan</p><p className="briefing-item-content"><strong>{s.plan.strongest.our} against {s.plan.strongest.their}.</strong> {s.plan.strongest.why}</p></div>
      </div>
      <div className="briefing-item verify">
        <span className="briefing-item-icon" aria-hidden="true">↗</span><div><p className="briefing-item-type">When the plan changes</p><p className="briefing-item-content">Open the response explorer, select their put-up, and review the suggested answer and future cost.</p><a className="text-link" href="/dashboard/match-night">Open the war room →</a></div>
      </div>
      <div className="briefing-item verify">
        <span className="briefing-item-icon" aria-hidden="true">✓</span>
        <div>
          <p className="briefing-item-type">Verify Before Acting</p>
          <p className="briefing-item-content">{s.simulation.availability} Cap {s.simulation.cap} is simulated. The historical fixture is not a claim about tonight&apos;s actual schedule.</p>
        </div>
      </div>
    </div>

    <div className="two-columns">
      <PairSupport title="Strongest evidence in the planned matchups" pair={s.plan.strongest}/>
      <PairSupport title="Weakest evidence in the planned matchups" pair={s.plan.weakest}/>
    </div>
    <Card title="Match Night Engine briefing">
      <p>{s.plan.summary}</p>
      <h3>Thin pairings in the conditional plan</h3>
      <p>{s.plan.fragility.thinPairings.join(' · ') || 'No thin pairing flagged in this plan.'}</p>
    </Card>
    <Assumptions snapshot={s}/>
  </>;
}
