import { Card, Notice, PageTitle } from './ui';
import { CaptainCommand } from './captain-command';
import { CaptainBriefing, ThreatDossiers } from './captain-decisions';
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
  return <>
    <PageTitle eyebrow="Shark Tank · Opponent dossiers" title="Prepare the counter before they put up.">
      {s.threats.length} opponents with winning recorded results against the captured roster. Start with the counter options, then inspect the evidence.
    </PageTitle>

    <ThreatDossiers snapshot={s}/>

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
    <PageTitle eyebrow="Captain’s Briefing · One-minute team plan" title="Here’s our plan.">
      {fixture.team} vs {fixture.opponent} · {fixture.format} · Historical reference. Confirm the current fixture and roster.
    </PageTitle>
    <CaptainBriefing snapshot={s}/>

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
