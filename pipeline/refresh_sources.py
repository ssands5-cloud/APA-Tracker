"""Private, content-addressed APA response fixtures for the unified refresh.

Recording returns the response read back from disk. Replay never calls HTTP.
The existing normalizers/ingestion therefore consume exactly the captured
source, without a second definition of roster or scoresheet semantics.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

SCHEMA = "apa-refresh-fixtures-v1"


def encoded(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value) -> str:
    return hashlib.sha256(encoded(value)).hexdigest()


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


class FixtureError(RuntimeError):
    pass


class ResponseFixtures:
    def __init__(self, root: Path, *, replay: bool = False):
        self.root = Path(root)
        self.replay = replay
        self.entries = {}
        if replay:
            document = json.loads((self.root / "sources.json").read_text(encoding="utf-8"))
            if document.get("schema") != SCHEMA:
                raise FixtureError("unsupported refresh fixture schema")
            self.entries = document["entries"]
            if digest(self.entries) != document.get("content_sha256"):
                raise FixtureError("source index checksum mismatch")
            # Quick mode can skip ingestion. Validate every indexed response
            # before deciding to reuse a generation, not only on later reads.
            for key, entry in self.entries.items():
                if not re.fullmatch(r"[0-9a-f]{64}", key):
                    raise FixtureError("invalid source fixture identity")
                path = self.root / "responses" / (key + ".json")
                if not path.is_file() or sha256(path) != entry.get("sha256"):
                    raise FixtureError("source fixture checksum mismatch")

    @staticmethod
    def key(query, variables):
        return digest({"query": query, "variables": variables})

    def __call__(self, query, variables, fetch):
        match = re.search(r"\b(query|mutation)\s+([A-Za-z_][A-Za-z0-9_]*)", query)
        operation = match.group(2) if match else "anonymous"
        if (match and match.group(1) == "mutation") or any(
            word in operation.lower() for word in ("token", "login", "authorize", "logout")
        ):
            raise FixtureError("authentication/mutation responses cannot be refresh fixtures")
        key = self.key(query, variables)
        path = self.root / "responses" / (key + ".json")
        if key not in self.entries:
            if self.replay:
                raise FixtureError(f"required source fixture missing: {operation}")
            data = fetch()
            if not isinstance(data, dict) or not data:
                raise FixtureError(f"empty or invalid source response: {operation}")
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded({"operationName": operation, "query": query,
                                      "variables": variables, "response": {"data": data}}))
            self.entries[key] = {"operation": operation, "sha256": sha256(path)}
        if not path.is_file() or sha256(path) != self.entries[key]["sha256"]:
            raise FixtureError(f"source fixture checksum mismatch: {operation}")
        body = json.loads(path.read_text(encoding="utf-8"))
        if self.key(body.get("query"), body.get("variables")) != key:
            raise FixtureError("source fixture request does not match its identity")
        return body["response"]["data"]

    def save_index(self):
        if self.replay:
            return
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sources.json").write_bytes(encoded({
            "schema": SCHEMA, "entries": self.entries, "content_sha256": digest(self.entries),
        }))

    @property
    def content_sha256(self):
        return digest(self.entries)


def acquire_current_sources(config, seed_database: Path | None, fixtures: ResponseFixtures):
    """Capture every team/roster/schedule and scored sheet in the viewer's current divisions.

    No first-N cap and no inference from unchanged team totals. Career requests
    are also captured before replay, using the existing exact league-context
    and unique-alias rules. Old historical game rows are retained in the seed;
    this is not a claim to recrawl every historical APA league/session.
    """
    from sqlalchemy.orm import Session
    from auth.graphql_client import use_fixture_provider
    from database.engine import create_db_engine
    from database.models import Player
    from scraper import graphql_scraper as api
    from scraper.historical_catalog import build_historical_catalog
    from scraper.player_enrichment import player_league_contexts

    with use_fixture_provider(fixtures):
        viewer = api.fetch_dashboard_teams(config)
        if not viewer.get("id"):
            raise FixtureError("APA did not return an authenticated viewer")
        teams = api.dashboard_teams_rows(viewer)
        divisions = {}
        for team in teams:
            key = str(team.get("division_id") or "")
            if not key or not team.get("session_name") or not team.get("division_type") or not team.get("league_id"):
                raise FixtureError("current team lacks an exact division/session/format")
            scope = {"division_id": key, "format": team["division_type"], "session_name": team["session_name"],
                     "league_id": str(team.get("league_id") or ""), "league_slug": team.get("league_slug") or ""}
            if key in divisions and divisions[key] != scope:
                raise FixtureError("current division has conflicting format/session scope")
            divisions[key] = scope
        if not divisions:
            raise FixtureError("APA returned no current divisions; nothing can be called refreshed")
        catalog = build_historical_catalog(config, int(viewer["id"]))
        # Dashboard is itself authoritative for current division/session/league
        # ownership. Retain that exact context even if historical discovery has
        # not yet listed a newly started session; never infer from a name.
        for scope in divisions.values():
            matches = [d for d in catalog["divisions"]
                       if str(d.get("division_id")) == scope["division_id"]
                       and (d.get("catalog_session_name") or d.get("session_name")) == scope["session_name"]]
            if any(str(d.get("league_id")) != scope["league_id"] for d in matches):
                raise FixtureError("dashboard and historical catalog disagree about league ownership")
            if not matches:
                catalog["divisions"].append({**scope, "catalog_session_name": scope["session_name"],
                                             "context_source": "dashboardTeams"})
        # Fetch all source objects used by the existing division sync/reconcile.
        members, team_ids = {}, set()
        for scope in divisions.values():
            did = scope["division_id"]
            rosters = api.fetch_division_rosters(config, did)
            roster_teams = api.division_roster_team_rows(rosters)
            if not roster_teams:
                raise FixtureError("current division has no readable roster teams")
            schedule = api.fetch_division_schedule(config, did)
            if not api.division_standings_rows(api.fetch_division_standings(config, did)):
                raise FixtureError("current division standings are unreadable")
            for team in roster_teams:
                team_ids.add(str(team["team_id"]))
                data = api.fetch_team_data(config, team["team_id"])
                identity = api.team_row(data)
                if identity["team_id"] != str(team["team_id"]) or identity["division_id"] != did or identity["session_name"] != scope["session_name"]:
                    raise FixtureError("team page does not match its requested division/session")
                for row in team["roster"]:
                    if row.get("player_id"):
                        members.setdefault(str(row["player_id"]), set()).add(scope["league_id"])
            for row in api.division_schedule_rows(schedule):
                if row["is_scored"] and not row["is_bye"]:
                    api.fetch_match_detail(config, row["match_id"])

        # Existing retained players plus newly captured roster players. Fetching
        # stats for all numeric IDs lets the audited enrichment routine decide
        # exact league ownership on replay; no guessed/name-based match here.
        if seed_database and Path(seed_database).is_file():
            engine = create_db_engine({"database": {"path": str(seed_database)}}, create_tables=False)
            try:
                with Session(engine) as db:
                    contexts = player_league_contexts(db, catalog)
                    for player in db.query(Player).all():
                        if player.id in contexts:
                            members.setdefault(str(player.external_id), set()).update(k[0] for k in contexts[player.id])
            finally:
                engine.dispose()
        for member_id in sorted(members):
            if not member_id.isdigit():
                continue
            member = api.fetch_formats_by_member_id(config, int(member_id))
            aliases = api.member_aliases_rows(member)
            for league_id in sorted(members[member_id]):
                candidates = [a for a in aliases if str(a.get("league_id") or "") == league_id]
                if len(candidates) == 1 and candidates[0].get("alias_id"):
                    api.fetch_eight_ball_stats(config, int(candidates[0]["alias_id"]))
        fixtures.save_index()
        return {"viewer_id": str(viewer["id"]), "divisions": list(divisions.values()),
                "team_ids": sorted(team_ids), "catalog": catalog}
