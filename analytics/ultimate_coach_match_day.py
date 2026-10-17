"""Match Day: find a verified viewer's real scheduled fixtures for a chosen
date, in both the HTML cockpit and the Excel companion, from the same
shared data this project already trusts (analytics.ultimate_coach_data_contract's
team_matches table, the same source build_verified_cockpit_payload() uses).

Identity, not name matching: "my team(s)" is derived from the *verified*
cockpit payload's own `players[].team_history` -- the exact same
identity-backed roster data every other selector in this project already
uses -- for whichever player's `external_id` (APA's own member *record ID*,
GraphQL `member.id`) matches the chosen viewer. There is no name-based guess
anywhere in this module; an unconfigured or unresolved viewer identity is
disclosed, never defaulted.

Two different APA identifiers exist and must never be conflated:
- the member RECORD ID (`member.id`, stored here as `external_id`) -- one per
  person, the identity key every artifact uses;
- the member CARD NUMBER (`alias.memberNumber`, e.g. "80100001") -- one per
  league alias, printed on the player's card, and NOT stored in the staging
  database at all. A configured card number is display provenance only.

Date handling: APA match_date strings arrive in two real shapes (see
database.models.Match.match_date's own docstring) -- a full ISO 8601
timestamp with an explicit UTC offset (e.g. "2026-08-09T11:00:00-06:00")
and a bare UTC timestamp ("2026-08-30T01:00:00Z"). The source offset is
NOT the league's local calendar: a bare-UTC evening match lands on the next
UTC day (real example: match 51545390, stored 2026-08-30T01:00:00Z, is
Saturday 2026-08-29 at 7:00 PM in Denver). So every fixture's calendar date,
weekday and kickoff are derived in ONE explicitly disclosed Match Day display
timezone (default America/Denver, configurable), computed once here and
shared by both exports. The raw source string is always kept alongside for
provenance. A missing or unparseable date is disclosed, never dropped
silently and never guessed into "today" or any other default.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

CHANGE_ME_SENTINEL = "CHANGE_ME"
DEFAULT_MATCH_DAY_TIMEZONE = "America/Denver"
# Machine-local, git-ignored override (see .gitignore): lets a real viewer
# identity drive the UAT build without committing a person's APA identity to
# this public repository.
LOCAL_CONFIG_NAME = "apa_config.local.yaml"

# Format filter values shared by the HTML and Excel Match Day pickers.
FORMAT_FILTER_EIGHT_NINE = ""      # default: every 8-Ball and 9-Ball variant
FORMAT_FILTER_ALL = "*"            # every recorded format
FORMAT_FILTER_EIGHT_NINE_LABEL = "8-Ball & 9-Ball"
FORMAT_FILTER_ALL_LABEL = "All recorded formats"
EIGHT_NINE_CATEGORIES = ("EIGHT", "NINE")

_FORMAT_CODE_LABELS = {"EIGHT": "8-Ball", "NINE": "9-Ball", "MASTERS": "Masters", "MASTERS ALT": "Masters Alt"}
_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


@dataclass(frozen=True)
class MatchDaySettings:
    viewer_member_external_id: str | None
    viewer_card_number: str | None
    timezone: str
    viewer_source: str


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text == CHANGE_ME_SENTINEL:
        return None
    return text


def validate_timezone(name: str) -> str:
    """An unknown display timezone is a build error, never a silent fallback:
    every Match Day date would otherwise be computed in a zone nobody chose."""
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError(f"Unknown Match Day display timezone: {name!r}") from exc
    return name


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
    return _clean(section.get("viewer_member_external_id"))


def _read_yaml(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import yaml  # only needed to read the configured viewer identity

        loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # pragma: no cover - config is advisory, never required
        return None
    return loaded if isinstance(loaded, dict) else None


def load_viewer_external_id_from_file(config_path: Path) -> str | None:
    """apa_config.yaml's own viewer identity, for the standalone CLI entry
    points -- same advisory, never-fatal contract as
    scripts.build_lineups._configured_weights(): a missing file, a parse
    error, or an absent/placeholder value all just mean "no viewer
    configured" (None), never a crash and never a guessed identity.
    """
    return load_viewer_external_id_from_config(_read_yaml(config_path))


def load_match_day_settings(config_path: Path) -> MatchDaySettings:
    """The one loader every Ultimate Coach build entrypoint uses, so the HTML
    and Excel exports always receive the SAME viewer identity and display
    timezone. `config_path` (normally apa_config.yaml) is read first; a
    sibling apa_config.local.yaml, if present, overrides its
    `ultimate_coach` keys. Viewer identity stays advisory (missing ->
    None); an invalid timezone raises rather than silently defaulting.
    """
    base = (_read_yaml(config_path) or {}).get("ultimate_coach") or {}
    local_path = config_path.with_name(LOCAL_CONFIG_NAME)
    local = (_read_yaml(local_path) or {}).get("ultimate_coach") or {}

    viewer = _clean(local.get("viewer_member_external_id"))
    source = LOCAL_CONFIG_NAME if viewer else ""
    card = _clean(local.get("viewer_card_number")) if viewer else None
    if viewer is None:
        viewer = _clean(base.get("viewer_member_external_id"))
        source = config_path.name if viewer else "not configured"
        card = _clean(base.get("viewer_card_number")) if viewer else None
    tz_name = _clean(local.get("match_day_timezone")) or _clean(base.get("match_day_timezone")) or DEFAULT_MATCH_DAY_TIMEZONE
    return MatchDaySettings(
        viewer_member_external_id=viewer,
        viewer_card_number=card,
        timezone=validate_timezone(tz_name),
        viewer_source=source,
    )


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
        # A naive timestamp names no instant with confidence -- the two real
        # shapes above are always offset-aware; anything else is exactly
        # the "unparseable/untrustworthy" case to disclose rather than
        # silently treat as some assumed zone.
        return None
    return parsed


def _offset_text(local: datetime) -> str:
    offset = local.utcoffset()
    total = int(offset.total_seconds()) if offset is not None else 0
    sign = "-" if total < 0 else "+"
    total = abs(total)
    return f"{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


def localize_match_date(raw: str | None, display_timezone: str = DEFAULT_MATCH_DAY_TIMEZONE) -> dict[str, Any]:
    """Every display/filter field Match Day needs for one source timestamp,
    all derived in `display_timezone`. `date_status` is "ok", "missing" or
    "unparseable"; the local_* fields are None unless it is "ok"."""
    result: dict[str, Any] = {
        "date_status": "ok", "local_date": None, "local_weekday": None,
        "local_time": None, "local_tz_abbrev": None, "local_utc_offset": None,
        "local_sort": None, "local_display": None,
    }
    if raw is None or not str(raw).strip():
        result["date_status"] = "missing"
        return result
    parsed = parse_match_date(raw)
    if parsed is None:
        result["date_status"] = "unparseable"
        return result
    local = parsed.astimezone(ZoneInfo(display_timezone))
    hour12 = local.hour % 12 or 12
    time_text = f"{hour12}:{local.minute:02d} {'AM' if local.hour < 12 else 'PM'}"
    weekday = _WEEKDAYS[local.weekday()]
    result.update(
        local_date=local.date().isoformat(),
        local_weekday=weekday,
        local_time=time_text,
        local_tz_abbrev=local.tzname(),
        local_utc_offset=_offset_text(local),
        local_sort=local.isoformat(),
        local_display=f"{weekday[:3]} {_MONTHS[local.month - 1]} {local.day}, {local.year} · {time_text} {local.tzname()}",
    )
    return result


def match_local_date(raw: str | None, display_timezone: str = DEFAULT_MATCH_DAY_TIMEZONE) -> date | None:
    """The calendar date `raw` falls on in the Match Day display timezone
    (NOT the source string's own offset). None if missing/unparseable."""
    local = localize_match_date(raw, display_timezone)
    return date.fromisoformat(local["local_date"]) if local["local_date"] else None


def excel_date_serial(iso_date: str | None) -> int | None:
    """Excel's 1900-system serial for an ISO date (what a typed date cell
    holds), so Excel lookups can key on a number rather than locale-
    dependent date text."""
    if not iso_date:
        return None
    return (date.fromisoformat(iso_date) - date(1899, 12, 30)).days


_FIXTURE_FIELDS = (
    "match_id", "match_external_id", "match_date", "format", "session_name",
    "week", "status", "location", "home_team_id", "home_team_name",
    "away_team_id", "away_team_name", "home_score", "away_score",
    "is_bye", "is_scored", "is_finalized",
)


def build_fixture_rows(
    team_matches: list[dict[str, Any]], *, display_timezone: str = DEFAULT_MATCH_DAY_TIMEZONE
) -> list[dict[str, Any]]:
    """Normalize analytics.ultimate_coach_data_contract's own team_matches
    table into fixture rows Match Day can filter/display. The raw source
    timestamp and raw recorded format label stay alongside every derived
    value; `format` stays the normalized category (EIGHT/NINE/...)."""
    fixtures: list[dict[str, Any]] = []
    for row in team_matches:
        fixture = {field: row.get(field) for field in _FIXTURE_FIELDS}
        fixture["format_raw"] = row.get("format_raw") or row.get("format") or ""
        raw = fixture["format_raw"]
        # A few legacy rows record a bare category code ("EIGHT"); show it
        # readably without hiding what was actually recorded.
        fixture["format_display"] = (
            f"{_FORMAT_CODE_LABELS[raw]} (recorded as {raw})" if raw in _FORMAT_CODE_LABELS else raw
        )
        fixture.update(localize_match_date(row.get("match_date"), display_timezone))
        fixture["date_unparsed"] = fixture["date_status"] == "unparseable"
        fixtures.append(fixture)
    return fixtures


def fixture_matches_format_filter(fixture: dict[str, Any], filter_value: str) -> bool:
    """FORMAT_FILTER_EIGHT_NINE (default) keeps every 8-Ball/9-Ball variant
    by normalized category; FORMAT_FILTER_ALL keeps everything; any other
    value is an exact raw recorded format label."""
    if filter_value == FORMAT_FILTER_ALL:
        return True
    if filter_value == FORMAT_FILTER_EIGHT_NINE:
        return fixture.get("format") in EIGHT_NINE_CATEGORIES
    return (fixture.get("format_raw") or "") == filter_value


def viewer_player(players: list[dict[str, Any]], viewer_external_id: str | None) -> dict[str, Any] | None:
    """The one verified player (if any) whose external_id (APA record ID) is
    the configured viewer identity. Identity-backed match on external_id
    only -- never a name comparison anywhere in this function."""
    if not viewer_external_id:
        return None
    for player in players:
        if str(player.get("external_id") or "") == viewer_external_id:
            return player
    return None


def viewer_current_teams(players: list[dict[str, Any]], viewer_external_id: str | None) -> list[dict[str, Any]]:
    """All of the viewer's own CURRENT team_history scopes -- each one kept
    separate (a player on two divisions of the same team name has two
    scopes). Empty (never a guess) if no viewer is configured or resolved.
    """
    player = viewer_player(players, viewer_external_id)
    if player is None:
        return []
    return [hist for hist in (player.get("team_history") or []) if hist.get("is_current")]


def team_scope_key(hist: dict[str, Any]) -> str:
    """(team_external_id, division_id, session_name) -- the same roster-scope
    identity key the HTML's TEAM_INDEX and analytics.ultimate_coach_excel_payload
    use. Team display names are never identities."""
    return "|".join([
        str(hist.get("team_external_id") or hist.get("team_name") or ""),
        str(hist.get("division_id") or ""),
        str(hist.get("session_name") or ""),
    ])


def current_team_scopes(players: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    scopes: dict[str, dict[str, Any]] = {}
    for player in players:
        for hist in player.get("team_history") or []:
            if not hist.get("is_current") or not hist.get("team_external_id"):
                continue
            key = team_scope_key(hist)
            scopes.setdefault(key, {
                "scope_key": key,
                "team_external_id": str(hist.get("team_external_id") or ""),
                "team_name": hist.get("team_name") or "",
                "division_id": str(hist.get("division_id") or ""),
                "session_name": str(hist.get("session_name") or ""),
                "format": hist.get("format") or "",
            })
    return scopes


def fixtures_for_team_on_date(
    fixtures: list[dict[str, Any]], team: dict[str, Any], local_date: str
) -> list[dict[str, Any]]:
    """Real fixtures where `team` (one of viewer_current_teams()'s own
    rows) plays on exactly `local_date` (ISO date in the display timezone)
    -- scoped by the fixture's session_name too, not just a bare external
    id. Sorted by kickoff; never auto-picks one when several exist."""
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
    matches.sort(key=lambda f: str(f.get("local_sort") or f.get("match_date") or ""))
    return matches


def fixture_opponent(fixture: dict[str, Any], team_external_id: str) -> dict[str, Any] | None:
    """The other side of `fixture` relative to `team_external_id`, or None
    for a bye (a real schedule slot with no opponent -- never fabricated,
    and the placeholder "Bye"/"BYE" names real bye rows carry are never
    treated as an opponent)."""
    if fixture.get("is_bye"):
        return None
    home_id = str(fixture.get("home_team_id") or "")
    away_id = str(fixture.get("away_team_id") or "")
    if team_external_id == home_id:
        return {"team_external_id": away_id, "team_name": fixture.get("away_team_name") or "", "side": "away"}
    if team_external_id == away_id:
        return {"team_external_id": home_id, "team_name": fixture.get("home_team_name") or "", "side": "home"}
    return None


def resolve_opponent_scope(
    opponent_external_id: str, session_name: str, scopes_by_team_session: dict[tuple[str, str], list[str]]
) -> dict[str, Any]:
    """Exact identity + session match against current roster scopes:
    exactly one -> "resolved"; none -> "no_current_roster"; several ->
    "ambiguous" (all candidates disclosed, never the first or last)."""
    if not opponent_external_id:
        return {"status": "missing", "scope_key": None, "candidate_scope_keys": []}
    candidates = sorted(scopes_by_team_session.get((opponent_external_id, session_name), []))
    if len(candidates) == 1:
        return {"status": "resolved", "scope_key": candidates[0], "candidate_scope_keys": candidates}
    if not candidates:
        return {"status": "no_current_roster", "scope_key": None, "candidate_scope_keys": []}
    return {"status": "ambiguous", "scope_key": None, "candidate_scope_keys": candidates}


def build_match_day_section(
    team_matches: list[dict[str, Any]],
    players: list[dict[str, Any]],
    *,
    display_timezone: str = DEFAULT_MATCH_DAY_TIMEZONE,
) -> dict[str, Any]:
    """The shared Match Day section of the verified cockpit payload.

    Match Day's team picker offers only CURRENT roster scopes, and fixtures
    are matched by (team_external_id, session_name), so a fixture where
    neither side is a current scope can never be reached from it. Only
    reachable fixtures are embedded; the rest are counted and disclosed
    (their individual game evidence is unaffected -- it stays in the
    scouting evidence index).

    `schedule` maps each current scope_key to its fixture "sides": the
    fixture index, which side the team is on, and the opponent resolution
    (bye / resolved / no_current_roster / ambiguous / missing).
    """
    validate_timezone(display_timezone)
    all_fixtures = build_fixture_rows(team_matches, display_timezone=display_timezone)
    scopes = current_team_scopes(players)
    scopes_by_team_session: dict[tuple[str, str], list[str]] = defaultdict(list)
    for key, scope in scopes.items():
        scopes_by_team_session[(scope["team_external_id"], scope["session_name"])].append(key)

    fixtures: list[dict[str, Any]] = []
    schedule: dict[str, list[dict[str, Any]]] = defaultdict(list)
    excluded = 0
    for fixture in all_fixtures:
        session_name = str(fixture.get("session_name") or "")
        home_id = str(fixture.get("home_team_id") or "")
        away_id = str(fixture.get("away_team_id") or "")
        home_scopes = scopes_by_team_session.get((home_id, session_name), []) if home_id else []
        away_scopes = scopes_by_team_session.get((away_id, session_name), []) if away_id else []
        if not home_scopes and not away_scopes:
            excluded += 1
            continue
        index = len(fixtures)
        fixtures.append(fixture)
        for side, own_scopes, opp_id, opp_name in (
            ("home", home_scopes, away_id, fixture.get("away_team_name")),
            ("away", away_scopes, home_id, fixture.get("home_team_name")),
        ):
            for scope_key in own_scopes:
                if fixture.get("is_bye"):
                    opponent = {"status": "bye", "scope_key": None, "candidate_scope_keys": [],
                                "team_external_id": None, "team_name": None}
                else:
                    opponent = resolve_opponent_scope(opp_id, session_name, scopes_by_team_session)
                    opponent["team_external_id"] = opp_id or None
                    opponent["team_name"] = (str(opp_name).strip() or None) if opp_name else None
                schedule[scope_key].append({
                    "fixture_index": index,
                    "side": side,
                    # Fixtures carry no division, so a same-id/same-session
                    # team rostered in two divisions can't be told apart --
                    # disclosed per row rather than silently assigned.
                    "own_scope_ambiguous": len(own_scopes) > 1,
                    "opponent": opponent,
                })

    for sides in schedule.values():
        sides.sort(key=lambda s: (
            fixtures[s["fixture_index"]].get("local_sort") is None,
            str(fixtures[s["fixture_index"]].get("local_sort") or fixtures[s["fixture_index"]].get("match_date") or ""),
            str(fixtures[s["fixture_index"]].get("match_external_id") or ""),
        ))

    status_counts: dict[str, int] = defaultdict(int)
    for fixture in fixtures:
        status_counts[fixture["date_status"]] += 1
    return {
        "display_timezone": display_timezone,
        "fixtures": fixtures,
        "schedule": dict(schedule),
        "coverage": {
            "stored_fixture_count": len(all_fixtures),
            "embedded_fixture_count": len(fixtures),
            "excluded_fixture_count": excluded,
            "current_sessions": sorted({s["session_name"] for s in scopes.values()}),
            "current_scope_count": len(scopes),
            "date_status_counts": dict(status_counts),
            "location_missing_count": sum(1 for f in fixtures if not str(f.get("location") or "").strip()),
            "bye_count": sum(1 for f in fixtures if f.get("is_bye")),
        },
    }
