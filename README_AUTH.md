# APA Tracker – Authentication Guide

## Overview

The APA Tracker supports two login methods and full multi-user support so you
and your fiancée (or any number of users) can each log in with their own
portal credentials and track their own teams independently.

---

## Quick Start

### Option 1 – Environment Variables (CI / Automation)

Create a `.env` file in the project root (never commit this file):

```bash
cp .env.example .env
# Edit .env and fill in your credentials
```

Then run:

```bash
# Linux / macOS
export $(cat .env | xargs)
python scripts/scrape_league.py --fetch-all

# Or inline (single session)
APA_USERNAME=you@example.com APA_PASSWORD=yourpass python scripts/scrape_league.py --fetch-all
```

### Option 2 – Interactive Prompt

```bash
python scripts/scrape_league.py --interactive
```

You will be asked for your email and password (password is hidden as you type).
After a successful login you will be asked if you want to save the session for
future runs.

---

## Multi-User Support

Each user's session is stored in `~/.apa_tracker/sessions/<email>.pkl` with
permissions `0600` (only readable by you).

```bash
# First-time login for Alice
python scripts/scrape_league.py --interactive
# APA Username (email): alice@example.com
# APA Password: [hidden]
# ✓ Login successful! Session saved to ~/.apa_tracker/sessions/alice@example.com.pkl

# Bob logs in (his own terminal / account)
APA_USERNAME=bob@example.com APA_PASSWORD=bobpass python scripts/scrape_league.py --fetch-all

# Switch to Alice's session on next run
python scripts/scrape_league.py --user alice@example.com --fetch-all
# ✓ Loaded cached session for alice@example.com
```

---

## CLI Reference

```
python scripts/scrape_league.py [OPTIONS]

Options:
  --user EMAIL          APA login email (overrides APA_USERNAME env var)
  --interactive         Force interactive credential prompt
  --list-sessions       List all saved session files and exit
  --clear-session EMAIL Delete the saved session for EMAIL
  --match MATCH_ID      Fetch a single match page
  --league-id ID        Scrape a specific league by ID
  --output DIR          Output directory (default: data/)
  --fetch-all           Scrape all matches for the user's teams
  --force-relogin       Skip cached session and log in fresh
  --verbose             Enable DEBUG logging
```

### Examples

```bash
# List saved sessions
python scripts/scrape_league.py --list-sessions

# Clear an expired session
python scripts/scrape_league.py --clear-session bob@example.com

# Scrape a specific match
python scripts/scrape_league.py --match 51419746

# Scrape a league, save HTML to data/
python scripts/scrape_league.py --league-id 12345 --output data/

# Force fresh login (ignores cached session)
python scripts/scrape_league.py --user alice@example.com --force-relogin
```

---

## Environment Variables

| Variable         | Required | Description                                 |
|------------------|----------|---------------------------------------------|
| `APA_USERNAME`   | Yes*     | Your APA portal login email                 |
| `APA_PASSWORD`   | Yes*     | Your APA portal password                    |
| `APA_LEAGUE_ID`  | No       | Default league ID (overridable via CLI)     |
| `APA_LEAGUE_ARENA` | No     | Target arena name                           |

\* Required when running non-interactively. The CLI will prompt if not set.

---

## Session Storage

Sessions are stored in `~/.apa_tracker/sessions/` as pickle files:

```
~/.apa_tracker/
└── sessions/
    ├── alice@example.com.pkl   (mode 0600)
    └── bob@example.com.pkl     (mode 0600)
```

- Files are created with `chmod 600` – only the owning OS user can read them.
- Session cookies are automatically reused on subsequent runs.
- If a session expires the tool re-authenticates transparently.

---

## Troubleshooting

### "APA_USERNAME and APA_PASSWORD must be set"
Run with `--interactive` or set the env vars:
```bash
export APA_USERNAME=you@example.com
export APA_PASSWORD=yourpassword
```

### "Login submitted but session does not appear authenticated"
1. Double-check your credentials.
2. If the portal's HTML has changed, update `LOGIN_FORM['success_markers']` in
   `parser/apa_page_map.py`.

### Session not loading / always re-logging in
Run `--force-relogin` to create a fresh session:
```bash
python scripts/scrape_league.py --user you@example.com --force-relogin
```

### Clearing a stale session
```bash
python scripts/scrape_league.py --clear-session you@example.com
```

---

## Security Best Practices

1. **Never commit credentials** – `.env` is in `.gitignore`.
2. **Use environment variables in CI** – add `APA_USERNAME` / `APA_PASSWORD` as
   repository secrets.
3. **Session files are user-only** – stored as `chmod 600` pickles.
4. **Rotate credentials** if you suspect they have been exposed; then run
   `--clear-session` and `--force-relogin`.
5. **Do not share session files** – they grant portal access without a password.
