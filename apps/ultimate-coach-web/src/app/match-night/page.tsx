import { PageTitle, Card, Notice } from '@/components/ui';
import { OpponentView } from '@/components/opponent-view';
import { players, opponents, evidence, record, meetings } from '@/lib/demo';

export default function MatchNight() { return <>
  <PageTitle eyebrow="Evergreen vs Copper Ridge · demo 8-ball" title="Match Night">A view of possible responses. Selecting an opponent does not record a put-up or send a player.</PageTitle>
  <div className="two-columns"><OpponentView/><Card kicker="If we put up first" title="Blind Send"><span className="pill">Illustrative lead</span><p className="big-name">Jordan</p><p>9–3 across 12 direct meetings against this demo roster: favorable records against 2 of 3 opponents.</p><Notice>Only 1 meeting each against Yara and Zane. The 10-meeting Xeno record accounts for most of the evidence.</Notice><p className="muted">This demo does not calculate a game tree, a safest board or a win estimate.</p></Card></div>
  <Card kicker="Same fixture, every pair" title="Matchup board"><p className="muted">Our perspective. SL and availability can change; no live updates are supplied.</p>
    <div className="table-scroll" role="region" aria-label="Matchup board, scroll horizontally" tabIndex={0}><table><thead><tr><th scope="col">Our player</th>{opponents.map(opponent => <th scope="col" key={opponent.id}>{opponent.name}<small>SL {opponent.skill}</small></th>)}</tr></thead><tbody>{players.map(player => <tr key={player.id}><th scope="row">{player.name}<small>SL {player.skill}</small></th>{opponents.map(opponent => { const row = evidence[opponent.id][player.id]; return <td key={opponent.id}><strong>{record(row)}</strong><small>{meetings(row)} meetings</small><span>{row?.note ?? 'Unknown · not weak'}</span></td>; })}</tr>)}</tbody></table></div></Card>
</>; }
