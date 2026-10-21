import type { Pairing } from '@/lib/snapshot';

export function PlanBoard({ rows, caption }: { rows: Pairing[]; caption: string }) {
  return <div className="table-scroll" role="region" aria-label={caption} tabIndex={0}><table><caption>{caption}</caption><thead><tr>
    <th scope="col">Game</th><th scope="col">Our player</th><th scope="col">Opponent</th><th scope="col">Evidence level</th>
  </tr></thead><tbody>{rows.map((row, i) => <tr key={`${row.our}-${row.their}`}>
    <td>{row.game ?? i + 1}{row.leader ? <small>{row.leader === 'us' ? 'We put up' : 'They put up'}</small> : null}</td>
    <th scope="row">{row.our}</th><td>{row.their}</td><td><span className="pill">{row.level}</span></td>
  </tr>)}</tbody></table></div>;
}
