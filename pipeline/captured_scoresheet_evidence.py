"""Convert captured APA scoresheets to verified directional matchup evidence."""
from collections import Counter, defaultdict
import json

from analytics.ultimate_coach_data_contract import normalize_format


def load_capture(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def add_captured_scoresheets(current, archive, folder, cutoff):
    aliases = defaultdict(set)
    names = {}
    for path in sorted((folder / "rosters").glob("*.json")):
        for team in load_capture(path)["teams"]:
            for player in team.get("roster") or []:
                member = (player.get("member") or {}).get("id")
                if player.get("id") and member:
                    aliases[(str(team["id"]), str(player["id"]))].add(str(member))
                    names[str(member)] = player["displayName"]

    profiles = {str(p["external_id"]): p["id"] for p in archive["players"]}
    next_id = max(profiles.values(), default=0) + 1
    existing = {
        str(row["match_external_id"])
        for payload in (current, archive) for row in payload["evidence"] if row.get("match_external_id")
    }
    counts = Counter()
    excluded = []
    for path in sorted((folder / "matches").glob("*.json")):
        match = load_capture(path)["match"]
        if str(match["id"]) != path.stem:
            raise ValueError(f"Scoresheet ID mismatch: {path.name}")
        counts["scoresheets"] += 1
        date = match.get("startTime") or ""
        positions = defaultdict(lambda: defaultdict(list))
        for side in match.get("results") or []:
            team = match.get(side.get("homeAway", "").lower()) or {}
            if not team.get("id"):
                continue
            for score in side.get("scores") or []:
                if score.get("matchPositionNumber") is not None:
                    positions[score["matchPositionNumber"]][side["homeAway"]].append((team, score))

        for position, sides in positions.items():
            if len(sides["HOME"]) != 1 or len(sides["AWAY"]) != 1:
                counts["unpaired_positions"] += 1
                continue
            pair = [sides[side][0] for side in ("HOME", "AWAY")]
            scores = [score for _, score in pair]
            players = [score.get("player") or {} for score in scores]
            if not all(p.get("id") for p in players) or {s.get("winLoss") for s in scores} != {"W", "L"}:
                continue
            counts["decided_pairs"] += 1
            reason = ""
            member_sets = [
                aliases[(str(team["id"]), str(p["id"]))] for (team, _), p in zip(pair, players)
            ]
            formats = {
                fmt for fmt, field in (("EIGHT", "eightBallWins"), ("NINE", "nineBallPoints"))
                if all(s.get(field) is not None for s in scores)
            }
            if path.stem in existing:
                counts["existing_pairs"] += 1
                continue
            if not date or date[:10] > cutoff or not match.get("isFinalized"):
                reason = "date_or_finalization"
            elif any(s.get("matchForfeited") or s.get("incompleteMatch") or s.get("doublesMatch") for s in scores):
                reason = "forfeit_incomplete_or_doubles"
            elif len(formats) != 1:
                reason = "unknown_format"
            elif any(len(members) != 1 for members in member_sets) or member_sets[0] == member_sets[1]:
                reason = "unresolved_identity"

            if reason:
                counts[reason] += 1
                excluded.append({"match": path.stem, "position": position, "reason": reason,
                                 "roster_ids": [str(p["id"]) for p in players]})
                continue

            fmt = formats.pop()
            ids = []
            for members in member_sets:
                member = next(iter(members))
                if member not in profiles:
                    profiles[member] = next_id
                    archive["players"].append({"id": next_id, "external_id": member, "name": names[member],
                                               "team_history": []})
                    next_id += 1
                ids.append(profiles[member])
            for i, score in enumerate(scores):
                other = 1 - i
                archive["evidence"].append({
                    "player_id": ids[i], "opponent_id": ids[other], "match_external_id": path.stem,
                    "game_key": f"catchup:{path.stem}:{position}", "match_date": date, "session_name": "",
                    "format": normalize_format(fmt), "result": score["winLoss"],
                    "own_skill_level": score.get("skillLevel"), "opponent_skill_level": scores[other].get("skillLevel"),
                    "points_earned": score.get("eightBallMatchPointsEarned" if fmt == "EIGHT" else "nineBallMatchPointsEarned"),
                    "nine_ball_points": score.get("nineBallPoints"),
                })
            counts["accepted_pairs"] += 1
    return {"counts": dict(counts), "excluded": excluded}
