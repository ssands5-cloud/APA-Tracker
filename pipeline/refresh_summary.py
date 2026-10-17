"""Operator completion counts from the exact captured current-roster fixtures."""
import json
from parser.apa_graphql import DIVISION_ROSTERS_QUERY
from scraper.graphql_scraper import division_roster_team_rows


def completion_counts(store, scope):
    teams, players = set(), set()
    for division in scope["divisions"]:
        key = store.key(DIVISION_ROSTERS_QUERY, {"id": int(division["division_id"])})
        # Read only already verified, indexed fixtures; never make another API call.
        if key not in store.entries:
            raise ValueError("completion summary requires captured division rosters")
        body = json.loads((store.root / "responses" / (key + ".json")).read_text(encoding="utf-8"))
        for team in division_roster_team_rows(body["response"]["data"]["division"]):
            teams.add(str(team["team_id"]))
            players.update(str(row["player_id"]) for row in team["roster"] if row.get("player_id"))
    return {"fixtures": len(store.entries), "teams": len(teams), "players": len(players)}


def completion_summary(counts, *, live, data_reused, reused, directory, elapsed):
    seconds = max(0, int(elapsed))
    minutes, seconds = divmod(seconds, 60)
    def updated(kind):
        count = counts[kind]
        return f"0 ({count} checked; database reused)" if data_reused else str(count)
    return "\n".join([
        "=================================",
        "APA REFRESH COMPLETE" + (" (OFFLINE VALIDATION)" if not live else ""),
        "=================================",
        f"Fixtures {'Captured' if live else 'Loaded'}: {counts['fixtures']}",
        f"Teams Updated: {updated('teams')}",
        f"Players Updated: {updated('players')}",
        "Matchups Rebuilt: " + ("No (up to date; reused)" if data_reused else "Yes"),
        "Workbook Built: " + ("No (up to date; reused)" if "Ultimate_Coach.xlsx" in reused else "Yes"),
        "HTML Built: " + ("No (up to date; reused)" if "ultimate_coach.html" in reused else "Yes"),
        "Validation: Passed",
        "", "Output Folder:", str(directory),
        "", "Total Time:", f"{minutes}m {seconds:02d}s",
    ])
