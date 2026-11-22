"""GA-02: the contradiction detector must catch seeded faults (synthetic states only, no real data).

A clean positive-control state passes every invariant with nonzero coverage; each mutation injects one fault and
must fail the expected invariant. Tests never weaken the detector to reach zero.
"""
import copy
import importlib.util
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location("ca", Path(__file__).resolve().parents[1] / "docs" / "v2" / "contradiction_audit.py")
ca = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ca)

OURS, THEIRS = "us|d|s", "them|d|s"


def _clean():
    """Two of ours (A SL6, B SL4), two of theirs (X, Y); A answers X, B answers Y; cap 23."""
    trace_x = {"rows": [{"name": "A", "p": 0.60, "pick": True}, {"name": "B", "p": 0.45, "pick": False}],
               "strategic": False, "gainWorst": 0.0, "gainAvg": 0.0, "summary": "Strongest matchup available (60%)."}
    trace_y = {"rows": [{"name": "B", "p": 0.55, "pick": True}, {"name": "A", "p": 0.50, "pick": False}],
               "strategic": False, "gainWorst": 0.0, "gainAvg": 0.0, "summary": "Strongest matchup available (55%)."}
    rows = [{"their": "X", "theirId": "x", "our": "A", "ourId": "a", "level": "Favored"},
            {"their": "Y", "theirId": "y", "our": "B", "ourId": "b", "level": "Edge"}]
    plan_them = [{"leader": "them", "our": "A", "our_id": "a", "their": "X", "their_id": "x", "level": "Favored", "p": 0.60},
                 {"leader": "us", "our": "B", "our_id": "b", "their": "Y", "their_id": "y", "level": "Edge", "p": 0.55}]
    plan_lead = [{"leader": "us", "our": "A", "our_id": "a", "their": "X", "their_id": "x", "level": "Favored", "p": 0.60},
                 {"leader": "them", "our": "B", "our_id": "b", "their": "Y", "their_id": "y", "level": "Edge", "p": 0.55}]
    return {
        "engine": "v2", "ourKey": OURS, "theirKey": THEIRS, "format": "8-Ball", "cap": 23, "played": 0,
        "badge": "ENGINE: V2 CANDIDATE · build test", "rows": rows, "games": [],
        "bench": {"ours": [{"id": "a", "name": "A", "sl": 6, "rem": True}, {"id": "b", "name": "B", "sl": 4, "rem": True}],
                  "theirs": [{"id": "x", "name": "X", "unplayed": True, "out": False}, {"id": "y", "name": "Y", "unplayed": True, "out": False}]},
        "command": {"v2": True, "cards": [
            {"name": "A", "role": "core", "grade": "A", "v2": True, "answers": [{"opp": "X", "role": "Recommended competitive matchup", "p": 0.60}], "avoid": []},
            {"name": "B", "role": "save", "grade": "B", "v2": True, "answers": [{"opp": "Y", "role": "Recommended competitive matchup", "p": 0.55}], "avoid": []}]},
        "compare": {"rows": [{"their": "X", "v2": {"our": "A", "p": 0.60}}, {"their": "Y", "v2": {"our": "B", "p": 0.55}}],
                    "v2Them": {"w": 1.15, "a": 1.2}},
        "plan": {"responses": rows, "plan_if_they_lead": plan_them, "plan_if_we_lead": plan_lead,
                 "total_if_they_lead": 1150, "total_if_we_lead": 1150, "lead": {"our": "A"}},
        "per": [{"their": "X", "theirId": "x", "answer": {"our": "A", "p": 0.60}, "trace": trace_x, "avoid": [], "notes": "",
                 "rendered": "A", "scen": [{"name": "A", "level": "Favored 60%", "recommended": True}]},
                {"their": "Y", "theirId": "y", "answer": {"our": "B", "p": 0.55}, "trace": trace_y, "avoid": [], "notes": "",
                 "rendered": "B", "scen": [{"name": "B", "level": "Edge 55%", "recommended": True}]}],
    }


def _run(state, expect=(OURS, THEIRS, "8-Ball")):
    fails, exc = [], []
    counts = ca.check(state, "synthetic", fails, exc, None, expect)
    return fails, counts


def test_positive_control_is_clean_with_coverage():
    fails, counts = _run(_clean())
    assert fails == []
    for inv in ("I0", "I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9"):
        assert counts.c[inv]["checked"] > 0, inv


def _m(path, value):
    def apply(s):
        cur = s
        for k in path[:-1]:
            cur = cur[k]
        cur[path[-1]] = value
    return apply


MUTATIONS = {
    "unavailable player recommended": (lambda s: s["bench"]["ours"][0].update(rem=False), "I1"),
    "already-played opponent offered": (lambda s: s["bench"]["theirs"][0].update(unplayed=False), "I1"),
    "duplicate player in a planned line": (lambda s: s["plan"]["plan_if_they_lead"][1].update(our="A", our_id="a"), "I1"),
    "cap exceeded including prior play": (lambda s: (s.update(cap=9)), "I7"),
    "four shown as five over the cap": (lambda s: (s.update(cap=12, games=[{"ourId": "a"}, {"ourId": "b"}, {"ourId": "a"}])), "I7"),
    "inconsistent pairing probability (send card vs trace)": (lambda s: s["per"][0]["answer"].update(p=0.61), "I5"),
    "inconsistent pairing probability (comparison vs trace)": (lambda s: s["compare"]["rows"][0]["v2"].update(p=0.59), "I5"),
    "missing expected trace": (lambda s: s["per"][0].update(trace=None), "I5"),
    "send card answer differs from trace": (lambda s: s["per"][0]["answer"].update(our="B"), "I5"),
    "wrong engine": (lambda s: s.update(engine="m3"), "I0"),
    "badge not V2": (lambda s: s.update(badge="ENGINE: M3 BASELINE"), "I0"),
    "wrong teams shown": (lambda s: s.update(theirKey="other|d|s"), "I0"),
    "wrong format shown": (lambda s: s.update(format="9-Ball"), "I0"),
    "rendered advice contradicts the model": (lambda s: s["per"][0].update(rendered="B"), "I8"),
    "no rendered send card": (lambda s: s["per"][0].update(rendered=None), "I8"),
    "board says avoid the recommended opponent": (lambda s: s["command"]["cards"][0]["avoid"].append({"opp": "X 60%"}), "I2"),
    "board does not list Match Night's answer": (lambda s: s["command"]["cards"][0].update(answers=[]), "I2"),
    "planned answer marked Not planned": (lambda s: s["command"]["cards"][1].update(role="situational", grade="C"), "I2"),
    "save role without an answer": (lambda s: s["command"]["cards"].append({"name": "C", "role": "save", "grade": "C", "v2": True, "answers": [], "avoid": []}), "I3"),
    "grade D despite answers": (lambda s: s["command"]["cards"][0].update(grade="D"), "I4"),
    "Send button without an engine answer (GPT-008)": (lambda s: s["per"][0].update(answer=None, sendButtons=1, rendered="A"), "I8"),
    "graded B but Not planned (S7)": (lambda s: s["command"]["cards"].append({"name": "C", "role": "situational", "grade": "B", "v2": True, "answers": [], "avoid": []}), "I4"),
    "board card built by M3 logic": (lambda s: s["command"]["cards"][0].update(v2=False), "I8"),
    "M3 level in a V2 recommendation": (lambda s: s["rows"][0].update(level="Strong"), "I8"),
    "M3 level in send scenarios": (lambda s: s["per"][0]["scen"][0].update(level="Caution"), "I8"),
    "legacy consider-saving note": (lambda s: s["per"][0].update(notes="consider saving — our only favorable option"), "I8"),
    "answer listed under avoid on the send card": (lambda s: s["per"][0].update(avoid=["A"]), "I2"),
    "plan first game differs from the card": (lambda s: s["plan"]["plan_if_they_lead"][0].update(our="B", our_id="b"), "I6"),
    "total from a different policy": (lambda s: s["plan"].update(total_if_they_lead=1300), "I6"),
    "comparison scores a different policy": (lambda s: s["compare"]["v2Them"].update(w=1.30), "I6"),
    "missing plan": (lambda s: s.update(plan=None), "I6"),
    "missing comparison in V2": (lambda s: s.update(compare=None), "I6"),
    "weaker player chosen without qualifying explanation": (lambda s: (s["per"][0]["trace"]["rows"][1].update(p=0.70)), "I9"),
}


@pytest.mark.parametrize("name", sorted(MUTATIONS))
def test_seeded_fault_is_detected(name):
    mutate, inv = MUTATIONS[name]
    s = copy.deepcopy(_clean())
    mutate(s)
    fails, _ = _run(s)
    assert any(f["invariant"] == inv for f in fails), (name, fails)


def test_unknown_skill_level_is_incomplete_never_zero():
    s = copy.deepcopy(_clean())
    s["cap"] = 5                      # would be over the cap if the unknown SL counted
    s["bench"]["ours"][0]["sl"] = None
    fails, counts = _run(s)
    assert not any(f["invariant"] == "I7" for f in fails), "unknown SL must not be judged against the cap"
    assert counts.c["I7"]["skipped"] > 0 and counts.c["I7"]["checked"] == 0


def test_strategic_exception_with_quantified_gains_is_not_a_contradiction():
    s = copy.deepcopy(_clean())
    t = s["per"][0]["trace"]
    t["rows"][1]["p"] = 0.70
    t.update(strategic=True, gainWorst=0.12, gainAvg=0.11, summary="Strategic choice: A (60%) instead of the strongest matchup B (70%).")
    fails, _ = _run(s)
    assert not any(f["invariant"] == "I9" for f in fails)


def test_empty_state_fails_coverage_rather_than_passing():
    s = copy.deepcopy(_clean())
    s.update(rows=[], per=[], plan={})
    fails, counts = _run(s)
    assert counts.c["I2"]["checked"] == 0 and counts.c["I5"]["checked"] == 0   # nothing to compare is NOT a pass


def test_our_put_up_turn_checks_the_lead_card_not_the_answer():
    s = copy.deepcopy(_clean())
    for x in s["per"]:
        x["nextLeader"] = "us"; x["rendered"] = "A"           # V2's lead is A
    fails, _ = _run(s)
    assert not any(f["invariant"] == "I8" for f in fails)
    s["per"][0]["rendered"] = "B"                              # a put-up card naming someone else is a contradiction
    fails, _ = _run(s)
    assert any(f["invariant"] == "I8" and "put-up card" in f["detail"] for f in fails)
