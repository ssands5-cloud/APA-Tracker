"""Build the source-of-truth historical league/session/division catalog.

This module performs discovery only. It does not fetch rosters, schedules,
scoresheets, or write to the tracker database. Every id comes from an APA
response already reachable through captured, read-only GraphQL operations.

The output is intentionally explicit about source limitations. An empty APA
response is evidence that APA returned no rows for that call, not evidence that
the historical world is complete.
"""

from __future__ import annotations

from typing import Any

from scraper.graphql_scraper import (
    alias_session_rows,
    fetch_alias_sessions,
    fetch_formats_by_member_id,
    fetch_league_divisions,
    league_division_rows,
    member_aliases_rows,
)

_SUPPORTED_FORMATS = {"EIGHT", "NINE", "MASTERS"}


def _clean_formats(values: list[str] | tuple[str, ...] | None) -> list[str]:
    """Return only captured APA formats this catalog knows how to query."""
    return sorted(
        {
            str(value).strip().upper()
            for value in (values or [])
            if str(value).strip().upper() in _SUPPORTED_FORMATS
        }
    )


def build_historical_catalog(config: dict, member_id: int) -> dict[str, Any]:
    """Discover every historical session/division reachable from a member.

    Discovery path:
      member -> per-league aliases -> alias sessions per format
      -> league divisions for each real session id

    The same session can be returned through both EIGHT and NINE. It is fetched
    once at the league/session level, while formats_discovered preserves all
    format provenance.
    """
    member = fetch_formats_by_member_id(config, int(member_id))
    aliases = member_aliases_rows(member)
    if not aliases:
        return {
            "schema": "ultimate-coach-historical-catalog-v1",
            "member_id": str(member_id),
            "aliases": [],
            "sessions": [],
            "divisions": [],
            "source_limitations": ["FormatsByMemberId returned no league aliases"],
            "counts": {"aliases": 0, "sessions": 0, "divisions": 0},
        }

    safe_aliases: list[dict[str, Any]] = []
    session_index: dict[tuple[str, str], dict[str, Any]] = {}
    source_limitations: list[str] = []

    for alias in aliases:
        alias_id = alias.get("alias_id")
        league_id = str(alias.get("league_id") or "")
        league_slug = str(alias.get("league_slug") or "")
        formats = _clean_formats(alias.get("formats"))

        safe_aliases.append(
            {
                "alias_id": str(alias_id or ""),
                "league_id": league_id,
                "league_slug": league_slug,
                "formats": formats,
            }
        )

        if not alias_id or not league_slug:
            source_limitations.append(
                f"alias {alias_id or '(missing)'}: missing alias id or league slug"
            )
            continue
        if not formats:
            source_limitations.append(
                f"alias {alias_id}: no supported EIGHT/NINE/MASTERS formats"
            )
            continue

        for format_name in formats:
            alias_sessions = fetch_alias_sessions(config, int(alias_id), format_name)
            rows = alias_session_rows(alias_sessions, format_name)
            if not rows:
                source_limitations.append(
                    f"alias {alias_id} ({league_slug}, {format_name}): APA returned no sessions"
                )
                continue

            for row in rows:
                session_id = str(row.get("session_id") or "")
                if not session_id:
                    continue
                key = (league_slug, session_id)
                existing = session_index.setdefault(
                    key,
                    {
                        "league_id": league_id,
                        "league_slug": league_slug,
                        "session_id": session_id,
                        "session_name": row.get("session_name") or "",
                        "_formats": set(),
                        "_alias_ids": set(),
                    },
                )
                if not existing["session_name"] and row.get("session_name"):
                    existing["session_name"] = row["session_name"]
                existing["_formats"].add(format_name)
                existing["_alias_ids"].add(str(alias_id))

    sessions: list[dict[str, Any]] = []
    divisions_by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for (league_slug, session_id), session in sorted(
        session_index.items(), key=lambda item: (item[0][0], int(item[0][1]))
    ):
        formats_discovered = sorted(session.pop("_formats"))
        alias_ids = sorted(session.pop("_alias_ids"))
        session["formats_discovered"] = formats_discovered
        session["alias_ids"] = alias_ids
        sessions.append(session)

        league = fetch_league_divisions(config, league_slug, int(session_id))
        division_rows = league_division_rows(league)
        if not division_rows:
            source_limitations.append(
                f"league {league_slug} session {session_id} "
                f"({session['session_name']}): APA returned zero divisions"
            )
            continue

        for division in division_rows:
            division_id = str(division.get("division_id") or "")
            if not division_id:
                continue
            returned_session = str(division.get("session_id") or "")
            if returned_session and returned_session != session_id:
                source_limitations.append(
                    f"division {division_id}: requested session {session_id} "
                    f"but APA labeled it session {returned_session}"
                )
                continue

            key = (session_id, division_id)
            enriched = dict(division)
            enriched["league_slug"] = league_slug
            enriched["catalog_session_id"] = session_id
            enriched["catalog_session_name"] = session["session_name"]
            divisions_by_key[key] = enriched

    divisions = [
        divisions_by_key[key]
        for key in sorted(divisions_by_key, key=lambda item: (int(item[0]), int(item[1])))
    ]

    return {
        "schema": "ultimate-coach-historical-catalog-v1",
        "member_id": str(member_id),
        "aliases": safe_aliases,
        "sessions": sessions,
        "divisions": divisions,
        "source_limitations": sorted(set(source_limitations)),
        "counts": {
            "aliases": len(safe_aliases),
            "sessions": len(sessions),
            "divisions": len(divisions),
        },
    }
