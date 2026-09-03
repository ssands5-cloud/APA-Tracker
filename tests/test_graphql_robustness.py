from __future__ import annotations

from unittest.mock import Mock

import pytest

import auth.graphql_client as client
from auth.graphql_client import GraphQLTransportError
from database.ingest import _to_float, _to_int
from scraper.graphql_scraper import roster_rows


def test_roster_rows_handles_missing_nested_member() -> None:
    rows = roster_rows(
        {
            "roster": [
                {
                    "id": 42,
                    "displayName": "Alice",
                    "matchesWon": 12,
                    "matchesPlayed": 20,
                    "skillLevel": 5,
                    "ppm": 1.5,
                    "pa": 2.5,
                }
            ]
        }
    )
    assert rows == [
        {
            "player_id": "42",
            "player_name": "Alice",
            "skill_level": 5,
            "matches_won": 12,
            "matches_played": 20,
            "win_pct": 0.6,
            "ppm": 1.5,
            "pa": 2.5,
        }
    ]


def test_numeric_parsing_handles_commas_and_percentages() -> None:
    assert _to_int("1,234") == 1234
    assert _to_int("12.0%") == 12
    assert _to_float("87.5%") == 87.5
    assert _to_float("1,250.75") == 1250.75


def test_execute_rejects_non_object_json_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    response = Mock(status_code=200)
    response.json.return_value = ["not", "an", "object"]
    monkeypatch.setattr(client.requests, "post", Mock(return_value=response))

    with pytest.raises(GraphQLTransportError, match="expected an object"):
        client.execute("query noop { __typename }", access_token="token", timeout=1, max_retries=0)
