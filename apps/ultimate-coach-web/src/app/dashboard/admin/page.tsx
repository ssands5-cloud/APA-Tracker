import { notFound } from 'next/navigation';
import { historicalAccess } from '@/lib/server/authorization';
import { listUsers, type User, type Role } from '@/lib/db/users';
import { listAuditLog, type AuditEntry } from '@/lib/db/audit';
import { approveUser, denyUser, promoteUser, demoteUser, suspendUser, removeAccess } from './actions';

export const dynamic = 'force-dynamic';
export const revalidate = 0;
export const runtime = 'nodejs';

// No redirect — 404 so the page's existence is not disclosed to non-admins.
export default async function AdminPage() {
  const access = await historicalAccess();
  if (!access.ok || access.role !== 'ADMIN') notFound();

  const [pending, allUsers, auditLog] = await Promise.all([
    listUsers('PENDING'),
    listUsers(),
    listAuditLog(100),
  ]);

  return (
    <div className="admin-shell">
      <header className="admin-header">
        <h1>Admin</h1>
        <span className="pill">ADMIN</span>
      </header>

      {pending.length > 0 && (
        <section className="admin-section">
          <h2>Pending Access ({pending.length})</h2>
          <div className="admin-list">
            {pending.map(u => (
              <div key={u.id} className="admin-row">
                <div className="admin-identity">
                  <strong>{u.display_name ?? u.email}</strong>
                  <span className="muted">{u.display_name ? u.email : ''}</span>
                  <span className="muted">Requested {u.created_at.slice(0, 10)}</span>
                </div>
                <div className="admin-actions">
                  <form action={approveUser}>
                    <input type="hidden" name="userId" value={u.id} />
                    <button type="submit" className="button secondary approve">Approve → COACH</button>
                  </form>
                  <form action={denyUser}>
                    <input type="hidden" name="userId" value={u.id} />
                    <button type="submit" className="button secondary deny">Deny</button>
                  </form>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="admin-section">
        <h2>All Users</h2>
        <div className="table-scroll" role="region" aria-label="User roster" tabIndex={0}>
          <table>
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Email</th>
                <th scope="col">Role</th>
                <th scope="col">Since</th>
                <th scope="col">Actions</th>
              </tr>
            </thead>
            <tbody>
              {allUsers.map(u => (
                <tr key={u.id}>
                  <td>{u.display_name ?? '—'}</td>
                  <td>{u.email}</td>
                  <td><span className={`pill ${u.role.toLowerCase()}`}>{u.role}</span></td>
                  <td>{u.created_at.slice(0, 10)}</td>
                  <td><UserActions user={u} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="admin-section">
        <h2>Audit Log</h2>
        <div className="audit-log">
          {auditLog.length === 0 && <p className="muted">No actions recorded yet.</p>}
          {auditLog.map(e => <AuditRow key={e.id} entry={e} />)}
        </div>
      </section>
    </div>
  );
}

function UserActions({ user: u }: { user: User }) {
  return (
    <div className="admin-actions">
      {u.role === 'PENDING' && <>
        <form action={approveUser}><input type="hidden" name="userId" value={u.id} /><button type="submit" className="secondary approve">Approve</button></form>
        <form action={denyUser}><input type="hidden" name="userId" value={u.id} /><button type="submit" className="secondary deny">Deny</button></form>
      </>}
      {(u.role === 'COACH' || u.role === 'REVIEWER') && <>
        <form action={promoteUser}><input type="hidden" name="userId" value={u.id} /><button type="submit" className="secondary">Promote</button></form>
        <form action={demoteUser}><input type="hidden" name="userId" value={u.id} /><button type="submit" className="secondary">Demote</button></form>
        <form action={suspendUser}><input type="hidden" name="userId" value={u.id} /><button type="submit" className="secondary deny">Suspend</button></form>
      </>}
      {u.role === 'SUSPENDED' && <>
        <form action={approveUser}><input type="hidden" name="userId" value={u.id} /><button type="submit" className="secondary approve">Restore → COACH</button></form>
        <form action={removeAccess}><input type="hidden" name="userId" value={u.id} /><button type="submit" className="secondary deny">Remove</button></form>
      </>}
      {u.role === 'ADMIN' && <span className="muted">—</span>}
    </div>
  );
}

function AuditRow({ entry: e }: { entry: AuditEntry }) {
  return (
    <div className="audit-row">
      <span className="audit-time">{e.created_at.slice(0, 19).replace('T', ' ')}</span>
      <span className="audit-actor">{e.actor_email ?? e.actor_id.slice(0, 12)}</span>
      <span className={`pill audit-action ${e.action}`}>{e.action}</span>
      {e.target_email && <span className="audit-target">→ {e.target_email}</span>}
      {e.old_role && e.new_role && (
        <span className="muted">{e.old_role} → {e.new_role}</span>
      )}
      {e.note && <span className="muted">({e.note})</span>}
    </div>
  );
}
