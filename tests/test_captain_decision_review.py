"""Captain Decision Review: the Recommendation Risk Register (RQ01-RQ12) run through M3.

Each case is the register's scenario, built from recorded records, levelled by the captain confidence rule
and planned by the Match Night Engine. The assertion is what a strong APA captain would do -- or, where the
register says the answer is a genuine judgment call, that the engine surfaces the trade-off instead of
hiding it. No probabilities anywhere.
"""
from __future__ import annotations

from analytics.match_night_engine import match_plan
from analytics.ultimate_coach_confidence import pair_confidence

NO_FORM = (0, 0)


def plan(ours, theirs, records, *, overall=None, shared=None, sl_changed=(), games=None, cap=None):
    """ours/theirs: {name: sl}. records: {(our, their): (wins, meetings)}. overall: {name: (w, g)}."""
    overall = overall or {}
    shared = shared or {}
    o = [{"id": n, "name": n, "sl": sl} for n, sl in ours.items()]
    t = [{"id": n, "name": n, "sl": sl} for n, sl in theirs.items()]
    value = {(a, x): pair_confidence(records.get((a, x)), own_overall=overall.get(a, NO_FORM),
                                     opp_overall=overall.get(x, NO_FORM), shared=shared.get((a, x)),
                                     sl_changed=(a, x) in sl_changed)
             for a in ours for x in theirs}
    p = match_plan(o, t, value, games_left=games or min(len(o), len(t)), cap=cap)
    return p, value


def answer(p, their):
    return next(r for r in p["responses"] if r["their"] == their)


def test_rq01_deeper_record_answers_the_thin_one():
    p, v = plan({"A": 4, "B": 4}, {"X": 4}, {("A", "X"): (1, 1), ("B", "X"): (8, 10)})
    assert v[("A", "X")]["level"] == "Thin" and v[("B", "X")]["level"] == "Strong"
    assert answer(p, "X")["our"] == "B"


def test_rq02_broader_record_counts_only_when_both_sides_have_one():
    # B 50-15 with no direct history vs X whose own record is thin: no basis to compare, A's 1-0 stands.
    p, v = plan({"A": 4, "B": 4}, {"X": 4}, {("A", "X"): (1, 1)},
                overall={"A": (3, 7), "B": (50, 65), "X": (8, 8)})
    assert v[("B", "X")]["level"] == "Unknown" and answer(p, "X")["our"] == "A"
    # With a real record on both sides, the 50-15 player is the Strong answer.
    p, v = plan({"A": 4, "B": 4}, {"X": 4}, {("A", "X"): (1, 1)},
                overall={"A": (3, 7), "B": (50, 65), "X": (30, 60)})
    assert v[("B", "X")]["level"] == "Strong" and answer(p, "X")["our"] == "B"


def test_rq03_recent_reversal_is_a_captain_call_not_an_engine_rule():
    # 6-3 vs 3-2: both Solid. The replay found recency barely matters (54.4% vs 53.5%), so the engine does
    # not reorder on dates; it shows both as Solid and the captain's read decides.
    p, v = plan({"A": 4, "B": 4}, {"X": 4}, {("A", "X"): (6, 9), ("B", "X"): (3, 5)})
    assert v[("A", "X")]["level"] == v[("B", "X")]["level"] == "Solid"


def test_rq04_skill_level_change_moves_the_answer():
    p, v = plan({"A": 4, "B": 4}, {"X": 7}, {("A", "X"): (4, 4), ("B", "X"): (3, 4)}, sl_changed={("A", "X")})
    assert v[("A", "X")]["level"] == "Thin" and "skill levels changed" in v[("A", "X")]["why"]
    assert v[("B", "X")]["level"] == "Solid" and answer(p, "X")["our"] == "B"


def test_rq05_one_loss_does_not_bench_a_player_with_two_strong_answers():
    p, v = plan({"A": 4, "B": 4, "C": 4}, {"X": 4, "Y": 4, "Z": 4},
                {("A", "X"): (1, 1), ("B", "X"): (0, 1), ("B", "Y"): (8, 10), ("B", "Z"): (8, 10)}, games=3)
    # B is our only Strong answer to Y and to Z: the plan holds B rather than leading with B.
    assert p["lead"]["our"] != "B"
    assert any(h["our"] == "B" for h in p["holds"])
    assert answer(p, "Y")["our"] == "B" and answer(p, "Z")["our"] == "B"


def test_rq06_count_tie_is_broken_by_depth_not_roster_order():
    p, v = plan({"A": 4, "B": 4}, {"X": 4, "Y": 4}, {("A", "X"): (1, 1), ("A", "Y"): (1, 1),
                                                     ("B", "X"): (8, 10), ("B", "Y"): (8, 10)})
    # Lead the thin option and keep the deep one for whoever they put up; either answer order yields one
    # Strong and one Thin pairing, so the engine's roster-order choice between them is equally good.
    assert p["lead"]["our"] == "A"
    assert p["confidence"] == {"Strong": 1, "Thin": 1}
    assert {b["our"]: b["level"] for b in p["best_board"]}["B"] == "Strong"


def test_rq07_save_strength_follows_the_saved_record():
    # A is the only favorable option vs future Y. Thin 1-0: spend A on X now. Strong 5-0: keep A for Y.
    thin, _ = plan({"A": 4, "B": 4}, {"X": 4, "Y": 4}, {("A", "X"): (3, 4), ("B", "X"): (1, 2), ("A", "Y"): (1, 1)})
    deep, _ = plan({"A": 4, "B": 4}, {"X": 4, "Y": 4}, {("A", "X"): (3, 4), ("B", "X"): (1, 2), ("A", "Y"): (5, 5)})
    assert answer(thin, "X")["our"] == "A"
    assert answer(deep, "X")["our"] == "B" and "keep A" in answer(deep, "X")["cost_later"]


def test_rq08_spend_the_strong_counter_now_over_a_thin_future_edge():
    p, _ = plan({"A": 4, "B": 4}, {"X": 4, "Y": 4}, {("A", "X"): (5, 5), ("B", "X"): (0, 3),
                                                     ("A", "Y"): (1, 1), ("B", "Y"): (0, 3)})
    assert answer(p, "X")["our"] == "A" and answer(p, "X")["cost_later"] == ""


def test_rq09_one_loss_is_a_real_caution_backed_by_history():
    # The replay split losing records by depth: 1-2 meetings won their next game 44.0% (8-Ball) vs 41.7% for
    # deeper ones (docs/recommendation_review/replay_thin_caution_split.json). A single loss is nearly as
    # informative as several, so it stays Caution and the plan prefers a player with no record.
    p, v = plan({"A": 4, "B": 4}, {"X": 4}, {("A", "X"): (0, 1)})
    assert v[("A", "X")]["level"] == "Caution" and v[("B", "X")]["level"] == "Unknown"
    assert answer(p, "X")["our"] == "B"


def test_rq10_the_actual_counter_decides_not_the_roster_aggregate():
    p, v = plan({"A": 4, "B": 4}, {"X": 4}, {("A", "X"): (0, 10), ("B", "X"): (2, 2)})
    assert answer(p, "X")["our"] == "B" and v[("A", "X")]["level"] == "Caution"


def test_rq11_a_strong_broader_record_with_one_direct_loss_is_conflicted_not_benched():
    p, v = plan({"A": 4, "B": 4}, {"X": 4}, {("A", "X"): (0, 1), ("B", "X"): (0, 6)},
                overall={"A": (50, 65), "B": (20, 40), "X": (30, 60)})
    assert v[("A", "X")]["level"] == "Conflicted" and v[("B", "X")]["level"] == "Caution"
    assert answer(p, "X")["our"] == "A"


def test_rq12_two_sided_shared_evidence_is_used_when_there_is_no_direct_record():
    # B 8-2 vs a shared opponent S that X went 0-5 against: Thin through one shared opponent; Solid through three.
    _, v1 = plan({"B": 4}, {"X": 4}, {}, shared={("B", "X"): (8, 10, 0, 5, 1)})
    _, v3 = plan({"B": 4}, {"X": 4}, {}, shared={("B", "X"): (8, 10, 0, 5, 3)})
    assert v1[("B", "X")]["level"] == "Thin" and v3[("B", "X")]["level"] == "Solid"


# ── New findings from Oct-20 audit ─────────────────────────────────────────────

def test_rq13_hold_back_and_response_table_name_the_same_player():
    """F1: when the plan designates a player for specific opponents, that player appears
    in both holds ('Hold back Alice') AND the response table ('If Xavier → Alice').
    The two sections are complementary -- holds is the designation, responses is the
    execution -- but the 'Hold back' label sounds like 'don't use tonight', contradicting
    the response-table instruction.  This test documents the existing behavior so that
    any UI relabelling change can be verified against it.
    """
    # Carol leads (neutral); Alice and Bob are kept as designated answers.
    p, _ = plan(
        {"Alice": 4, "Bob": 4, "Carol": 4},
        {"Xavier": 5, "Yvonne": 4, "Zed": 4},
        {("Alice", "Xavier"): (3, 3), ("Alice", "Yvonne"): (2, 2),
         ("Bob", "Xavier"): (1, 1), ("Bob", "Zed"): (4, 5),
         ("Bob", "Yvonne"): (0, 3)},
        games=3,
    )
    holds_players = {h["our"] for h in p["holds"]}
    response_players = {r["our"] for r in p["responses"]}
    # Alice and Bob both appear in holds AND in the response table.
    # The 'Hold back' label is therefore shown for players the plan actively uses.
    assert holds_players & response_players, (
        "Expected overlap between holds and responses (F1 scenario); "
        f"holds={holds_players}, responses={response_players}"
    )
    from analytics.match_night_engine import plan_text
    assert 'send when that matchup is put up' in plan_text(p)['holds']


def test_rq14_cost_later_is_silent_when_tonight_values_are_equal_but_futures_differ():
    """F3: cost_later fires only when the naive (best-tonight) choice differs in tonight-value
    from the plan's choice.  When both players are equally good tonight but one is needed
    more for a future opponent, the plan silently picks the one with the better future --
    without saying why.  A captain who sees 'If Xavier → Alice (Solid)' and knows Bob is also
    Solid vs Xavier gets no explanation of why Alice was chosen over Bob.

    GPT qualification (ff72ef2): in the true equal case the roster-first naive answer IS the
    plan's answer (both Alice), so the 'naive != i' guard is False and changing '>' to '>='
    would still not fire cost_later.  A working fix must inspect equal-value alternatives
    rejected by the plan, not just the single roster-first naive pick.
    """
    # Both Alice and Bob are Solid (3) vs Xavier: 4-2 in 6 meetings each.
    # Bob is Strong (6) vs Yvonne; Alice is Caution (-3) vs Yvonne.
    # Plan: send Alice vs Xavier (saves Bob for Yvonne). Both are equal tonight (Solid=3).
    # cost_later is '' even though choosing Bob vs Xavier would cost 9 planning points.
    p, v = plan(
        {"Alice": 4, "Bob": 4},
        {"Xavier": 4, "Yvonne": 4},
        {("Alice", "Xavier"): (4, 6),   # Solid: 4-2 in 6 meetings
         ("Alice", "Yvonne"): (0, 3),   # Caution
         ("Bob",   "Xavier"): (4, 6),   # Solid: 4-2 in 6 meetings (exact tie)
         ("Bob",   "Yvonne"): (6, 7)},  # Strong
        games=2,
    )
    assert v[("Alice", "Xavier")]["level"] == v[("Bob", "Xavier")]["level"] == "Solid", (
        "Fixture must produce equal Solid levels to characterise the true equal-tonight gap"
    )
    xavier_resp = answer(p, "Xavier")
    assert xavier_resp["our"] == "Alice", (
        "Plan should send Alice vs Xavier to preserve Bob for Yvonne; "
        f"got {xavier_resp['our']!r}"
    )
    # Document the gap: no cost_later fires even though sending Bob vs Xavier
    # would leave only Caution-level Alice for Yvonne (delta = 9 planning points).
    assert xavier_resp["cost_later"] == "", (
        "F3: cost_later is expected to be silent in the equal-tonight case; "
        "this test documents the gap -- a future fix should add an explanation here"
    )
