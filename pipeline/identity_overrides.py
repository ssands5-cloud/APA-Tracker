"""Explicit owner-reviewed bindings for individual captured scoresheet rows."""

from datetime import datetime
import json
from pathlib import Path

from pipeline.refresh_sources import digest

SCHEMA = "ultimate-coach-identity-overrides-v1"
SCOPE_FIELDS = (
    "match_id", "score_row_id", "scoresheet_player_id", "team_id",
    "division_id", "league_id", "session_id", "format",
)
REVIEW_FIELDS = ("canonical_member_id", "reviewed_by", "reviewed_at", "evidence_reference")


class IdentityOverrideError(ValueError):
    pass


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise IdentityOverrideError("duplicate field in identity override file")
        result[key] = value
    return result


class IdentityOverrides:
    def __init__(self, path: Path):
        try:
            document = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
        except (OSError, ValueError) as exc:
            raise IdentityOverrideError("identity override file is unreadable or invalid") from exc
        if (not isinstance(document, dict) or set(document) != {"schema", "overrides"}
                or document["schema"] != SCHEMA or not isinstance(document["overrides"], list)):
            raise IdentityOverrideError("invalid identity override schema")
        self.rows = {}
        self.applied = set()
        self.fingerprint = digest(document)
        for row in document["overrides"]:
            if (not isinstance(row, dict) or set(row) != set(SCOPE_FIELDS + REVIEW_FIELDS)
                    or any(not isinstance(value, str) or not value or value != value.strip()
                           for value in row.values())):
                raise IdentityOverrideError("identity override requires an exact scope and review record")
            if any(not row[field].isascii() or not row[field].isdigit()
                   for field in (*SCOPE_FIELDS[:-1], "canonical_member_id")):
                raise IdentityOverrideError("identity override identifiers must be decimal strings")
            if row["format"] not in {"EIGHT", "NINE"} or row["canonical_member_id"] == row["scoresheet_player_id"]:
                raise IdentityOverrideError("invalid format or canonical member namespace")
            try:
                reviewed_at = datetime.fromisoformat(row["reviewed_at"].replace("Z", "+00:00"))
            except ValueError as exc:
                raise IdentityOverrideError("identity review timestamp is invalid") from exc
            if reviewed_at.utcoffset() is None:
                raise IdentityOverrideError("identity review timestamp requires a timezone")
            key = tuple(row[field] for field in SCOPE_FIELDS)
            if key in self.rows:
                raise IdentityOverrideError("duplicate scoresheet identity override scope")
            self.rows[key] = row

    def audit(self):
        return {
            "input_sha256": self.fingerprint,
            "reviewed": list(self.rows.values()),
            "applied_scope_sha256": sorted(digest(key) for key in self.applied),
        }
