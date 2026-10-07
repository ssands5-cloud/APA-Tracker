"""Match Day: find a verified viewer's real scheduled fixtures for a chosen
date, in both the HTML cockpit and the Excel companion, from the same
shared data this project already trusts (analytics.ultimate_coach_data_contract's
team_matches table, the same source build_verified_cockpit_payload() uses).

Identity, not name matching: "my team(s)" is derived from the *verified*
cockpit payload's own `players[].team_history` -- the exact same
identity-backed roster data every other selector in this project already
uses -- for whichever player's `external_id` matches a configured viewer
identity. There is no name-based guess anywhere in this module; an
unconfigured or unresolved viewer identity is disclosed, never defaulted.

Date handling: APA match_date strings arrive in two real shapes (see
database.models.Match.match_date's own docstring) -- a full ISO 8601
timestamp with an explicit UTC offset (e.g. "2026-08-09T11:00:00-06:00")
and a bare UTC timestamp ("2026-08-29T15:00:00Z"). Both are parsed with
their own embedded offset preserved end-to-end; the calendar date used for
matching/display is always read from that same offset, never from a
blind string slice and never by assuming one canonical local timezone for
every row -- "the match's calendar date" means whatever date the source
timestamp's own offset actually names, exactly as the project's existing
date-handling precedent (database.models.Match.match_date) already treats
the two source shapes as genuinely different and distinct from a derived
"normalized" datetime. An unparseable date is disclosed, never dropped
silently and never guessed into "today" or any other default.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any

CHANGE_ME_SENTINEL = "CHANGE_ME"


def load_viewer_external_id_from_config(config: dict[str, Any] | None) -> str | None:
    """Read `ultimate_coach.viewer_member_external_id` from apa_config.yaml's
    already-loaded dict. Returns None (never a guess) if the section/key is
    missing, blank, or still the documented CHANGE_ME placeholder -- the
    same "unset means disabled, not defaulted" contract apa_config.yaml
    already uses for `league.league_id`/`league.division_id`.
    """
    if not config:
        return None
    section = config.get("ultimate_coach") or {}
    value = section.get("viewer_member_external_id")
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == CHANGE_ME_SENTINEL:
        return None
    return text


def load_viewer_external_id_from_file(config_path: Path) -> str | None:
    """apa_config.yaml's own viewer identity, for the standalone CLI entry
    points -- same advisory, never-fatal contract as
    scripts.build_lineups._configured_weights(): a missing file, a parse
    error, or an absent/placeholder value all just mean "no viewer
    configured" (None), never a crash and never a guessed identity.
    """
    if not config_path.is_file():
        return None
    try:
        import yaml  # only needed to read the configured viewer identity

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory, never required
        return None
    return load_viewer_external_id_from_config(config)


def parse_match_date(raw: str | None) -> datetime | None:
    """Deliberately parse one of the two real match_date shapes, keeping
    whatever UTC offset the source string carries. Returns None for
    anything else -- never raises, never guesses a timezone or a date.
    """
    if not raw:
        return None
    text = str(raw).strip()
    if not text:
        return None
    # datetime.fromisoformat only accepts "Z" directly from Python 3.11;
    # normalizing it ourselves keeps this correct on any 3.x this project
    # targets without depending on that version-specific behavior.
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        # A naive timestamp names no calendar day with confidence -- the
        # two real shapes above are always offset-aware; anything else is
        # exactly the "unparseable/untrustworthy" case to disclose rather
        # than silently treat as some assumed zone.
        return None
    return parsed


def match_local_date(raw: str | None) -> date | None:
    """The calendar date a match_date string's own embedded offset names.
    None if the string doesn't parse -- the caller disclosed it, not this
    function silently dropping it.
    """
    parsed = parse_match_date(raw)
    return parsed.date() if parsed is not None else None


_FIXTURE_FIELDS = (
    "match_id", "match_external_id", "match_date", "format", "session_name",
    "week", "status", "location", "home_team_id", "home_team_name",
    "away_team_id", "away_team_name", "home_score", "away_score",
    "is_bye", "is_scored", "is_finalized",
)


def build_fixture_rows(team_matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize analytics.ultimate_coach_data_contract's own team_matches
    table into fixture rows Match Day can filter/display, adding the
    parsed local date (or an explicit unparsed flag) without discarding the
    original source string -- "date/time with source timezone retained"
    means the raw value always stays alongside the derived one.
    """
    fixtures: list[dict[str, Any]] = []
    for row in team_matches:
        fixture = {field: row.get(field) for field in _FIXTURE_FIELDS}
        local = match_local_date(row.get("match_date"))
        fixture["local_date"] = local.isoformat() if local is not None else None
        fixture["date_unparsed"] = bool(row.get("match_date")) and local is None
        fixtures.append(fixture)
    return fixtures


def viewer_player(players: list[dict[str, Any]], viewer_external_id: str | None) -> dict[str, Any] | None:
    """The one verified player (if any) whose external_id is the
    configured viewer identity. Identity-backed match on external_id only
    -- never a name comparison anywhere in this function."""
    if not viewer_external_id:
        return None
    for player in players:
        if str(player.get("external_id") or "") == viewer_external_id:
            return player
    return None


def viewer_current_teams(players: list[dict[str, Any]], viewer_external_id: str | None) -> list[dict[str, Any]]:
    """All of the viewer's own CURRENT team_history scopes -- reuses the
    exact same identity-verified, scope-disambiguated rows every other
    selector in this project already builds from, so Match Day can never
    disagree with Player vs Player / Team vs Team about which teams exist.
    Empty (never a guess) if no viewer is configured or resolved.
    """
    player = viewer_player(players, viewer_external_id)
    if player is None:
        return []
    return [hist for hist in (player.get("team_history") or []) if hist.get("is_current")]


def _team_scope_key(hist_or_fixture_side: dict[str, Any], *, team_external_id: str, session_name: str) -> str:
    return f"{team_external_id}|{hist_or_fixture_side.get('division_id') or ''}|{session_name}"


def fixtures_for_team_on_date(
    fixtures: list[dict[str, Any]], team: dict[str, Any], local_date: str
) -> list[dict[str, Any]]:
    """Real fixtures where `team` (one of viewer_current_teams()'s own
    rows) plays, on exactly `local_date` (an ISO "YYYY-MM-DD" string) --
    scoped by the fixture's own session_name matching the team's session,
    not just a bare external id, so a same-external-id team that also
    played in a different session is never pulled in by mistake. Sorted by
    kickoff time; never auto-picks one when several exist -- that's the
    caller's job to surface, not this function's to hide.
    """
    team_external_id = str(team.get("team_external_id") or "")
    session_name = str(team.get("session_name") or "")
    if not team_external_id:
        return []
    matches = [
        f for f in fixtures
        if f.get("local_date") == local_date
        and str(f.get("session_name") or "") == session_name
        and (
            str(f.get("home_team_id") or "") == team_external_id
            or str(f.get("away_team_id") or "") == team_external_id
        )
    ]
    matches.sort(key=lambda f: str(f.get("match_date") or ""))
    return matches


def fixture_opponent(fixture: dict[str, Any], team_external_id: str) -> dict[str, Any] | None:
    """The other side of `fixture` relative to `team_external_id`, or None
    for a bye (a real schedule slot with no opponent -- never fabricated).
    """
    if fixture.get("is_bye"):
        return None
    home_id = str(fixture.get("home_team_id") or "")
    away_id = str(fixture.get("away_team_id") or "")
    if team_external_id == home_id:
        return {"team_external_id": away_id, "team_name": fixture.get("away_team_name") or "", "side": "away"}
    if team_external_id == away_id:
        return {"team_external_id": home_id, "team_name": fixture.get("home_team_name") or "", "side": "home"}
    return None
