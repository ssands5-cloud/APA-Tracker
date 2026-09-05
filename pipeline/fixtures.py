"""Read the scraper's fixture tree.

Implements the load side of the contract in README-scraper.md:

  * every JSON file under ``scraper/sanitized_fixtures``
  * ``payload.get("response", payload)`` -- two schemas exist on disk, the raw
    GraphQL payload this scraper writes and the capture envelope
    ``tools/capture_apa_graphql.py`` writes
  * **ids come from payloads, never from directory names**

That last rule is why :class:`FixtureStore` exposes ``team_ids()`` and friends
by reading ``dashboardTeams`` rather than by listing directories. The folder
layout is a convenience for humans reading the tree; an operation whose name
does not match the scraper's prefix table lands in ``global/`` with its real
id only inside the JSON, and anything keyed off folder names would silently
mis-file it.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE_ROOT = PROJECT_ROOT / "scraper" / "sanitized_fixtures"


def unwrap(payload: dict[str, Any]) -> dict[str, Any]:
    """The GraphQL ``data`` object, whichever schema the file uses.

    Reading the wrong shape is not hypothetical: match discovery once
    reported 0 matches on a run that had captured 56, because it looked for
    ``data`` on a file whose payload was nested under ``response``.
    """
    if not isinstance(payload, dict):
        return {}
    body = payload.get("response", payload)
    if not isinstance(body, dict):
        return {}
    data = body.get("data")
    return data if isinstance(data, dict) else {}


class FixtureStore:
    """Every captured fixture, indexed by (entity, id, operation)."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else DEFAULT_FIXTURE_ROOT
        # {entity: {entity_id: {operation: data}}}
        self._index: dict[str, dict[str, dict[str, dict]]] = {}
        self._loaded = 0
        self._unreadable: list[str] = []

    # -- loading --------------------------------------------------------

    def load(self) -> "FixtureStore":
        if not self.root.is_dir():
            raise FileNotFoundError(
                f"No fixture directory at {self.root}.\n"
                "Run the scraper first:  python scraper/full_auto_scrape.py"
            )
        for path in sorted(self.root.rglob("*.json")):
            relative = path.relative_to(self.root)
            if len(relative.parts) != 3:
                # <entity>/<id>/<Operation>.json is the contract; anything
                # else is not ours to interpret.
                self._unreadable.append(f"{relative} (unexpected depth)")
                continue
            entity, entity_id, filename = relative.parts
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                self._unreadable.append(f"{relative} ({type(exc).__name__})")
                continue
            data = unwrap(payload)
            if not data:
                # A captured error or an empty response: real, but nothing to
                # ingest. Not an error worth failing the run over.
                continue
            self._index.setdefault(entity, {}).setdefault(entity_id, {})[
                filename[: -len(".json")]
            ] = data
            self._loaded += 1

        logger.info(
            "Loaded %d fixture(s) from %s across %s",
            self._loaded, self.root,
            ", ".join(f"{e}={len(ids)}" for e, ids in sorted(self._index.items())) or "nothing",
        )
        for problem in self._unreadable:
            logger.warning("Skipped fixture %s", problem)
        return self

    # -- access ---------------------------------------------------------

    @property
    def count(self) -> int:
        return self._loaded

    def get(self, entity: str, entity_id: Any, operation: str) -> dict[str, Any]:
        return self._index.get(entity, {}).get(str(entity_id), {}).get(operation, {})

    def ids(self, entity: str) -> list[str]:
        """Directory ids for an entity -- for iteration only, never as the
        authoritative id of a row (that comes from the payload)."""
        return sorted(self._index.get(entity, {}))

    def each(self, entity: str, operation: str) -> Iterator[tuple[str, dict[str, Any]]]:
        for entity_id in self.ids(entity):
            data = self.get(entity, entity_id, operation)
            if data:
                yield entity_id, data

    # -- composed views -------------------------------------------------

    def dashboard_viewer(self) -> dict[str, Any]:
        """``viewer`` from dashboardTeams -- the entry point that lists every
        team, its division, session and league slug."""
        return self.get("global", "global", "dashboardTeams").get("viewer") or {}

    def team_data(self, team_id: Any) -> dict[str, Any]:
        """Re-compose the shape ``scraper.graphql_scraper.fetch_team_data``
        returns, so the existing row-mappers and
        ``scheduler.graphql_sync.ingest_team_data`` work unchanged against
        fixtures instead of the network.

        The live fetcher issues three queries and merges them; the scraper
        saved those same three responses as teamPage / teamRoster /
        teamSchedule, so this puts them back together.
        """
        page = self.get("team", team_id, "teamPage").get("team") or {}
        roster = self.get("team", team_id, "teamRoster").get("team") or {}
        schedule = self.get("team", team_id, "teamSchedule").get("team") or {}
        return {
            "team": page,
            "roster": roster.get("roster") or [],
            "schedule": schedule.get("matches") or [],
            "points": {
                key: schedule.get(key)
                for key in ("sessionPoints", "sessionBonusPoints", "sessionTotalPoints")
            },
        }

    def matches(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """(match_id_from_payload, match) for every captured MatchPage.

        The id comes from ``match["id"]``, not the directory, per the
        contract. The directory id is only used to find the file.
        """
        for _, data in self.each("match", "MatchPage"):
            match = data.get("match") or {}
            if match.get("id"):
                yield str(match["id"]), match

    def aliases(self) -> Iterator[tuple[str, dict[str, Any]]]:
        """(alias_id_from_payload, alias) for every captured TeamStat.

        TeamStat is alias-scoped: its id is a member's identity within a
        league, not a team id. Filing it under ``team/`` was a real bug; the
        payload is the authority either way.
        """
        for _, data in self.each("alias", "TeamStat"):
            alias = data.get("alias") or {}
            if alias.get("id"):
                yield str(alias["id"]), alias
