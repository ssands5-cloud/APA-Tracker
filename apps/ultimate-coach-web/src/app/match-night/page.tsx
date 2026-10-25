import { PageTitle, Card, Notice } from '@/components/ui';
import { OpponentView } from '@/components/opponent-view';
import { players, opponents, evidence, record, meetings } from '@/lib/demo';

export default function MatchNight() { return <>
  <PageTitle eyebrow="Evergreen vs Copper Ridge · demo 8-ball" title="Match Night">A view of possible responses. Selecting an opponent does not record a put-up or send a player.</PageTitle>
  <div className="captain-decision-grid"><OpponentView/><Card kicker="If we put up first · illustrative" title="Consider Jordan"><p>Favorable direct records against 2 of 3 demo opponents.</p><Notice>Only one recorded meeting each against Yara and Zane; the Xeno record accounts for most of the evidence.</Notice><p className="muted">This is an authored example, not an engine recommendation.</p></Card></div>
  <Card kicker="Same fixture, every pair" title="Matchup board"><p className="muted">Our perspective. SL and availability can change; no live updates are supplied.</p>
    <div className="table-scroll" role="region" aria-label="Matchup board, scroll horizontally" tabIndex={0}><table><thead><tr><th scope="col">Our player</th>{opponents.map(opponent => <th scope="col" key={opponent.id}>{opponent.name}<small>SL {opponent.skill}</small></th>)}</tr></thead><tbody>{players.map(player => <tr key={player.id}><th scope="row">{player.name}<small>SL {player.skill}</small></th>{opponents.map(opponent => { const row = evidence[opponent.id][player.id]; return <td key={opponent.id}><strong>{record(row)}</strong><small>{meetings(row)} meetings</small><span>{row?.note ?? 'Unknown · not weak'}</span></td>; })}</tr>)}</tbody></table></div></Card>
</>; }
