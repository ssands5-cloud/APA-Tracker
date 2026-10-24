import { Card, Notice, PageTitle } from './ui';
import { CaptainCommand } from './captain-command';
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
  const { fixture } = s;
  return <>
    <CaptainCommand snapshot={s}/>

    <nav className="captain-next" aria-label="Captain’s next steps">
      <a href="/dashboard/match-night"><strong>Make the call</strong><span>Explore responses to their put-up →</span></a>
      <a href="/dashboard/threats"><strong>Scout the opposition</strong><span>Read opponent dossiers →</span></a>
      <a href="/dashboard/summary"><strong>Read the briefing</strong><span>Opening strategy, holds and contingencies →</span></a>
    </nav>

    <Card kicker="Captain readiness · confirm before the first put-up" title="Make the historical plan usable tonight">
      <div className="readiness-checks"><div><strong>1. Confirm the fixture</strong><p>This plan is for {fixture.team} vs {fixture.opponent}, {fixture.when}. Verify tonight’s opponent and format.</p></div><div><strong>2. Confirm who is here</strong><p>{s.simulation.availability} Attendance has not been verified.</p></div><div><strong>3. Confirm the rules</strong><p>The reference cap is {s.simulation.cap}; verify the current cap and player skill levels.</p></div></div>
      <a className="text-link" href="/dashboard/match-night">Review the opening and responses →</a>
    </Card>

    <Assumptions snapshot={s}/>
  </>;
}

/* ─── Match Night ───────────────────────────────────────────────────────────── */
export function MatchNightPage({ snapshot: s }: { snapshot: Snapshot }) {
  const { players, opponents } = s;
  const lead = players.find(p => p.name === s.plan.lead.player);
  const leadSL = lead?.skill;
  const leadRecords = opponents.map(opponent => lead ? s.evidence[opponent.id]?.[lead.id] : undefined);
  const recorded = leadRecords.filter(row => row?.hasDirect);
  const favorable = recorded.filter(row => row!.wins > row!.losses).length;
  const neutral = recorded.filter(row => row!.wins === row!.losses).length;
  const concern = recorded.filter(row => row!.wins < row!.losses).length;
  return <>
    <CaptainCommand snapshot={s} matchNight/>

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

    {/* SUPPORTING REFERENCE — below the fold */}
    <div className="two-columns"><Holds snapshot={s}/><div id="protected-options"><Holds snapshot={s} protect/></div></div>

    <Card kicker="If they lead instead" title="Response table">
      <div className="table-scroll" role="region" aria-label="Responses to every opposing player" tabIndex={0}>
        <table><thead><tr><th scope="col">Their put-up</th><th scope="col">Our response</th><th scope="col">Evidence</th><th scope="col">Future cost</th></tr></thead>
        <tbody>{opponents.map(opp => <tr key={opp.id}><th scope="row"><a href={`/dashboard/match-night?opponent=${encodeURIComponent(opp.id)}#response-explorer`} aria-label={`Explore the response to ${opp.name}`}>{opp.name}</a></th><td>{s.responses[opp.id].player}</td><td>{s.responses[opp.id].level}</td><td>{s.responses[opp.id].cost}</td></tr>)}</tbody></table>
      </div>
    </Card>

    <Card kicker="Tradeoffs, not instructions to lose" title="Sacrifice / concession candidates">
      {s.plan.sacrifices.length ? s.plan.sacrifices.map(p => <div className="candidate" key={`${p.our}-${p.their}`}><h3>{p.our} → {p.their}</h3><p><span className="pill caution">{p.level}</span> {p.why}</p></div>) : <p>No concession is proposed by this plan.</p>}
      <p className="muted">These are lowest-cost concessions within the current engine&apos;s assumptions, not predicted defeats or required sends.</p>
    </Card>

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
    <PageTitle eyebrow="Shark Tank · Opponent dossiers" title="Prepare the counter before they put up.">
      {s.threats.length} opponents with winning recorded results against the captured roster. Start with the counter options, then inspect the evidence.
    </PageTitle>

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
              <div style={{ flex: 1, minWidth: 0 }}>
                <p className="spc-name">{t.name}</p>
                <div>
                  <span className="spc-record">{t.wins}W – {t.meetings - t.wins}L</span>
                  <span className="spc-coverage">{t.playersMet} of {players.length} players met</span>
                </div>
              </div>
            </div>
            <div className="spc-body">
              {response && <div className="scouting-action"><span>Counter option</span><strong>Consider {response.player}</strong><p>{response.why}</p><p>Future cost: {response.cost}</p></div>}
              <p className="spc-threat-level">Historical record — {threatPct}% wins in recorded meetings</p>
              <div className="spc-threat-bar"><div className="spc-threat-fill" style={{ width: fillWidth }}/></div>
              <p><strong>Why dangerous:</strong> {t.text}</p>
              <p><strong>Recorded opportunities:</strong> {favorablePlayers.length ? favorablePlayers.map(player => { const row = s.evidence[opponent!.id][player.id]; const count = meetings(row); return `${player.name} (${record(row)}; ${count} ${count === 1 ? 'meeting' : 'meetings'})`; }).join(' · ') : 'No favorable direct record is established in this snapshot.'}</p>

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
    <PageTitle eyebrow="Captured rosters, explicit assumptions" title="Team Status">Your historical roster and the opponent&apos;s roster. Every availability label below is simulated, not a live attendance check.</PageTitle>
    <div className="two-columns">
      {[{ title: fixture.team, kicker: 'Our captured roster', roster: players, ours: true }, { title: fixture.opponent, kicker: 'Opponent captured roster', roster: opponents, ours: false }].map(team => (
        <Card key={team.title} title={team.title} kicker={team.kicker}>
          <ul className="roster">
            {team.roster.map(player => (
              <li key={player.id}>
                <span className="avatar" aria-hidden="true">{player.name.slice(0, 1)}</span>
                <div><strong>{player.name}</strong><small>{player.availability}</small>{team.ours && player.name === s.plan.lead.player && <small className="captain-player-tag">Opening option · historical plan</small>}{team.ours && s.plan.protect.some(item => item.our === player.name) && <small className="captain-player-tag">Protect for a matchup</small>}</div>
                <span className="skill" aria-label={`Skill level ${player.skill ?? 'unknown'}`}><span>SL</span><b>{player.skill ?? '?'}</b></span>
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
