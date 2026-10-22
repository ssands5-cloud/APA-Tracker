-- Ultimate Coach Web Platform — database schema
-- Run via: scripts/init-db.ts (or Turso shell)
-- Engine: SQLite 3.x (Turso libsql)

CREATE TABLE IF NOT EXISTS users (
  id           TEXT PRIMARY KEY,
  email        TEXT NOT NULL UNIQUE,
  role         TEXT NOT NULL DEFAULT 'PENDING'
                 CHECK(role IN ('ADMIN','COACH','REVIEWER','PENDING','SUSPENDED')),
  display_name TEXT,
  created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
  updated_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS audit_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  actor_id   TEXT NOT NULL,
  action     TEXT NOT NULL
               CHECK(action IN ('approve','deny','promote','demote','suspend','remove','bootstrap')),
  target_id  TEXT,
  old_role   TEXT,
  new_role   TEXT,
  note       TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

CREATE TABLE IF NOT EXISTS user_activity (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id    TEXT NOT NULL,
  event_type TEXT NOT NULL,
  metadata   TEXT,
  created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- Seed: first admin (id replaced with real Clerk user_xxx on first sign-in).
-- Re-running is safe: INSERT OR IGNORE.
INSERT OR IGNORE INTO users (id, email, role)
  VALUES ('bootstrap-seed', 'ssands5@comcast.net', 'ADMIN');
