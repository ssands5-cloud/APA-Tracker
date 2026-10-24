import { PageTitle, Card, Notice } from '@/components/ui';
import { players, opponents } from '@/lib/demo';
import { DecisionBrief } from '@/components/decision-brief';

export default function TeamStatus() { return <>
  <PageTitle eyebrow="Know who is in the picture" title="Team Status">Illustrative rosters only. No attendance, lineup or participation changes can be made here.</PageTitle>
  <DecisionBrief action="Confirm who is available before making a plan." why="The example roster is a reference, not a confirmed lineup." tradeoff="If availability or skill levels differ, an example response may not fit the actual match." href="/match-night" link="Review example responses"/>
  <div className="two-columns">{[{ title: 'Evergreen', kicker: 'Our demo team', roster: players }, { title: 'Copper Ridge', kicker: 'Opponent demo team', roster: opponents }].map(team => <Card key={team.title} title={team.title} kicker={team.kicker}><ul className="roster">{team.roster.map(player => <li key={player.id}><span className="avatar" aria-hidden="true">{player.name.slice(0,1)}</span><div><strong>{player.name}</strong><small>Availability not confirmed</small></div><span className="skill">SL {player.skill}</span></li>)}</ul></Card>)}</div>
  <Notice>No player is marked present, unavailable or played. A displayed roster is not a confirmed lineup, and skill totals are not a tournament legality check.</Notice>
</>; }
