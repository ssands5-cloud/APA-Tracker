"""V2 input adapter: the exact inputs the HTML's V2 engine uses, computed in Python from the same compact payload.

The workbook must recommend exactly what the HTML recommends, so it must start from the same data in the same order.
This module reproduces, on the compact browser payload that the HTML embeds (`ui.ultimate_coach._browser_payload`), the
page's roster scopes (TEAM_INDEX), roster order (memberOrder), evidence lookups (rowsFor / oppMap), shared-opponent
sums (rankVsOpponent), recorded and recent form (v2Record) and V2 pairing inputs (v2ForRow), and returns rosters plus a
win-chance matrix keyed by stable player IDs, ready for `analytics.uc_v2_policy.V2Policy`.

Rules that matter for parity:
- Rows are read in compact-index order (production builds pop evidence, so same-date rows are reversed); the form
  sort is a stable sort by the match-date string, as in the browser.
- Direct records count every row against that opponent (oppMap); recorded/recent form counts W/L rows only (v2Record).
- Shared opponents are used only without a direct record, and only when both sides have games against them.
- Skill levels are the roster scope's (team history), not the meeting rows'; non-positive or missing = unknown.
No new model, coefficients or policy: probabilities come from `analytics.uc_v2_pair_model.win_probability`.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from analytics.uc_v2_pair_model import win_probability


def load_compact_from_html(path: str | Path) -> dict[str, Any]:
    """The compact payload embedded in a built HTML, rehydrated exactly as the browser does (strings, team history)."""
    html = Path(path).read_text(encoding="utf-8")
    m = re.search(r'<script id="uc-data" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise ValueError("no embedded uc-data payload")
    return rehydrate(json.loads(m.group(1)))


def rehydrate(d: dict[str, Any]) -> dict[str, Any]:
    strings = d.get("strings")
    if not strings:
        return d
    deref = (lambda v: strings[v] if isinstance(v, int) and not isinstance(v, bool) else v)
    for rows in (d.get("evidence_index") or {}).values():
        for r in rows:
            for j in d.get("evidence_interned_positions") or []:
                r[j] = deref(r[j])
    fields = d.get("team_history_fields")
    if fields:
        interned = set(d.get("team_history_interned_positions") or [])
        for p in d.get("players") or []:
            rows = p.get("team_history")
            if not rows or isinstance(rows[0], dict):
                continue
            p["team_history"] = [{f: (deref(r[i]) if i in interned else r[i]) for i, f in enumerate(fields)} for r in rows]
    return d


def team_scope_key(t: dict[str, Any]) -> str:
    return "|".join([str(t.get("team_external_id") or t.get("team_name") or ""), str(t.get("division_id") or ""),
                     str(t.get("session_name") or "")])


def _js_str(v: Any) -> str:
    return "" if v is None else str(v)


def _member_key(m: dict[str, Any]):
    """memberOrder: known skill first (higher first), then lowercase name, then external ID (string compare)."""
    sl = m.get("skill_level")
    known = sl is not None
    return (0 if known else 1, -sl if known else 0, _js_str(m.get("name")).lower(), _js_str(m.get("external_id")))


class V2Inputs:
    def __init__(self, compact: dict[str, Any]):
        self.d = compact
        fields = compact.get("evidence_row_fields") or []
        self.col = {f: i for i, f in enumerate(fields)}
        self.index = compact.get("evidence_index") or {}
        teams: dict[str, dict[str, Any]] = {}
        for p in compact.get("players") or []:
            for t in p.get("team_history") or []:
                if not t.get("is_current") or not t.get("team_name"):
                    continue
                key = team_scope_key(t)
                team = teams.setdefault(key, {"key": key, "name": t.get("team_name"), "format": t.get("format") or "",
                                              "seen": set(), "players": []})
                if p["id"] in team["seen"]:
                    continue
                team["seen"].add(p["id"])
                sl = t.get("skill_level")
                sl = sl if isinstance(sl, (int, float)) and not isinstance(sl, bool) and sl > 0 else None
                team["players"].append({"id": p["id"], "external_id": p.get("external_id"), "name": p.get("name"),
                                        "skill_level": sl})
        self.teams = teams
        # DISPLAY_LABELS: league-wide same-name groups get "(player i of n)", ordered by external ID (page: localeCompare).
        groups: dict[str, list[dict[str, Any]]] = {}
        for p in compact.get("players") or []:
            groups.setdefault(str(p.get("name") or "").strip().lower(), []).append(p)
        self.labels: dict[str, str] = {}
        for group in groups.values():
            group = sorted(group, key=lambda q: _js_str(q.get("external_id")))
            for i, q in enumerate(group):
                self.labels[str(q["id"])] = q["name"] + (f" (player {i + 1} of {len(group)})" if len(group) > 1 else "")
        self.rows_for = lru_cache(maxsize=None)(self._rows_for)
        self.opp_map = lru_cache(maxsize=None)(self._opp_map)
        self.record = lru_cache(maxsize=None)(self._record)

    def _val(self, row, name):
        return row[self.col[name]]

    def _rows_for(self, pid, fmt):
        return tuple(self.index.get(f"{pid}|{fmt}", ()))

    def _opp_map(self, pid, fmt):
        m: dict[str, list[int]] = {}
        for r in self.rows_for(pid, fmt):
            e = m.setdefault(str(self._val(r, "opponent_id")), [0, 0])
            e[1] += 1
            if self._val(r, "result") == "W":
                e[0] += 1
        return m

    def _record(self, pid, fmt):
        rows = [r for r in self.rows_for(pid, fmt) if self._val(r, "result") in ("W", "L")]
        rows.sort(key=lambda r: _js_str(self._val(r, "match_date")))        # stable, like Array.prototype.sort
        w = sum(1 for r in rows if self._val(r, "result") == "W")
        last = rows[-10:]
        lw = sum(1 for r in last if self._val(r, "result") == "W")
        return (w, len(rows)), (lw, len(last))

    def roster(self, team_key: str) -> list[dict[str, Any]]:
        return sorted(self.teams[team_key]["players"], key=_member_key)

    def display_name(self, member: dict[str, Any], roster: list[dict[str, Any]]) -> str:
        """wrDisplayName: within a roster, same-name players with distinct known skill levels read "Name (SL n)";
        otherwise the league-wide label."""
        key = str(member.get("name") or "").strip().lower()
        dupes = [m for m in roster if m["id"] != member["id"] and str(m.get("name") or "").strip().lower() == key]
        sl = member.get("skill_level")
        if dupes and sl is not None and not any(m.get("skill_level") == sl for m in dupes):
            return f"{member['name']} (SL {sl})"
        return self.labels.get(str(member["id"]), member.get("name"))

    def pair_inputs(self, member, opp, fmt) -> dict[str, Any]:
        mm, om = self.opp_map(member["id"], fmt), self.opp_map(opp["id"], fmt)
        d = mm.get(str(opp["id"]))
        direct = (d[0], d[1]) if d and d[1] > 0 else None
        shared_keys = [k for k in mm if k in om]
        ow = sum(mm[k][0] for k in shared_keys); og = sum(mm[k][1] for k in shared_keys)
        tw = sum(om[k][0] for k in shared_keys); tg = sum(om[k][1] for k in shared_keys)
        shared = (ow, og, tw, tg, len(shared_keys)) if shared_keys and og > 0 and tg > 0 else None
        form_p, recent_p = self.record(member["id"], fmt)
        form_o, recent_o = self.record(opp["id"], fmt)
        return dict(direct=direct, shared=shared, recent_p=recent_p, recent_o=recent_o, form_p=form_p, form_o=form_o)

    def matchup(self, ours_key: str, theirs_key: str, fmt: str):
        """Rosters in browser order (V2Policy shape) and the V2 win-chance matrix keyed by stable IDs."""
        ours, theirs = self.roster(ours_key), self.roster(theirs_key)
        p = {}
        for t in theirs:
            for m in ours:
                v = win_probability(fmt, m["skill_level"], t["skill_level"], **self.pair_inputs(m, t, fmt))
                if v is None:
                    raise ValueError(f"no V2 model for format {fmt}")
                p[(str(m["id"]), str(t["id"]))] = v
        shape = lambda xs: [{"id": str(x["id"]), "name": self.display_name(x, xs), "sl": x["skill_level"]} for x in xs]
        return shape(ours), shape(theirs), p
