"""
Credential helpers: read from environment variables or interactive prompt.

Never stores raw passwords to disk. Passwords are only held in memory for
the duration of the current process.
"""

from __future__ import annotations

import getpass
import os
from pathlib import Path
from typing import Optional, Tuple


def get_credentials_from_env() -> Tuple[Optional[str], Optional[str]]:
    """Return (username, password) from APA_USERNAME / APA_PASSWORD env vars.

    Returns (None, None) if either variable is missing so callers can fall
    back to another source without raising.
    """
    username = os.environ.get("APA_USERNAME")
    password = os.environ.get("APA_PASSWORD")
    if username and password:
        return username, password
    return None, None


def get_credentials_from_prompt() -> Tuple[str, str]:
    """Interactively ask the user for their APA portal credentials.

    Uses :func:`getpass.getpass` so the password is not echoed to the
    terminal.
    """
    print("APA Portal Login")
    print("-" * 40)
    username = input("APA Username (email): ").strip()
    password = getpass.getpass("APA Password: ")
    return username, password


def get_user_session_path(username: str) -> Path:
    """Return the path where a user's session cookies should be stored.

    Creates the parent directory (mode 0700) if it does not yet exist so
    that session files are only accessible by the current OS user.

    Args:
        username: The user's APA login email, used as the filename stem.

    Returns:
        A :class:`~pathlib.Path` such as
        ``~/.apa_tracker/sessions/alice@example.com.json``.
    """
    sessions_dir = Path.home() / ".apa_tracker" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    sessions_dir.chmod(0o700)
    # Sanitize the username so it is safe to use as a filename.
    safe_name = username.replace("/", "_").replace("\\", "_")
    return sessions_dir / f"{safe_name}.json"


def save_credentials_option() -> bool:
    """Ask the user whether to persist the session for future runs.

    Returns:
        ``True`` if the user answered yes, ``False`` otherwise.
    """
    answer = input("Remember this session? (y/n): ").strip().lower()
    return answer in ("y", "yes")


def list_saved_sessions() -> list[Path]:
    """Return all saved session files for the current OS user."""
    sessions_dir = Path.home() / ".apa_tracker" / "sessions"
    if not sessions_dir.exists():
        return []
    return sorted(sessions_dir.glob("*.json"))
