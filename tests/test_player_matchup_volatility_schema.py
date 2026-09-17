"""Release gate: normalized matchup volatility must not be integer storage."""

from sqlalchemy import Float

from database.models import PlayerMatchup


def test_player_matchup_volatility_uses_float_storage():
    assert isinstance(PlayerMatchup.__table__.c.volatility.type, Float)
