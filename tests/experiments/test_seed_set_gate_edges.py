"""Every judge gate (V1-V4) and task gate (G1-G4) at its exact threshold: a value exactly at the line meets it
(exact arithmetic, coordinator ruling on B1), one step past it does not. Synthetic records, no harness."""

from fractions import Fraction

import pytest

from experiments.seed_set import gates

H, S = gates.HAIKU, gates.SONNET


def build(haiku, sonnet=lambda t: 6, ref=lambda t: 8, base=lambda t: 0, passes_from=5, retest_shift=None):
    """Records of 20 tasks, the first ten retested (identically unless `retest_shift` maps (task, run index) to a
    score shift): `haiku(t)` gives task t's four Haiku scores, `sonnet(t)` its Sonnet score, `ref(t)`/`base(t)`
    its anchors; a candidate passes its hidden tests from `passes_from` points."""
    records, pools = [], []
    for t in range(20):
        task = f"t{t:02d}"
        for pool in ("first", "retest") if t < 10 else ("first",):
            pools.append({"task": task, "pool": pool, "excluded_judges": {}})
            runs = [("base", "anchor", None, base(t), 0.5), ("reference", "anchor", None, ref(t), 1.0)]
            runs += [("candidate", "direct", H, s, None) for s in haiku(t)]
            runs += [("candidate", "direct_sonnet", S, sonnet(t), None)]
            for k, (role, arm, model, score, hidden) in enumerate(runs):
                shift = (retest_shift or {}).get((t, k), 0) if pool == "retest" else 0
                records.append({"task": task, "pool": pool, "role": role, "arm": arm, "model": model,
                                "run": f"{task}/{k}", "patch": f"{task}-{k}",
                                "hidden": hidden if hidden is not None else (1.0 if score >= passes_from else 0.5),
                                "scores": {H: score + shift, S: score + shift}, "status": "rated", "reason": None})
    tasks = [f"t{t:02d}" for t in range(20)]
    return records, pools, tasks


def task_gates(records, pools, tasks):
    return gates.task_gates(records, pools, H, tasks)["gates"]


def test_g3_gap_of_exactly_half_a_point_qualifies_with_haiku():  # the reviewer's B1 case: 3.6 against 4.1
    records, pools, tasks = build(lambda t: [4] * 4 if t < 12 else [3] * 4, lambda t: 4 if t < 18 else 5,
                                  passes_from=4)
    result = gates.calibration(records, pools, tasks, tasks[:10])
    assert (result["gates"]["G3"]["gap"], result["gates"]["G3"]["passed"], result["selected"]) == (
        Fraction(1, 2), True, H)


def test_g3_gap_just_under_half_a_point_fails():
    records, pools, tasks = build(lambda t: [4] * 4 if t < 13 else [3] * 4, lambda t: 4 if t < 18 else 5)
    assert task_gates(records, pools, tasks)["G3"]["passed"] is False  # 4.1 - 3.65


@pytest.mark.parametrize("last, passed", [([2, 2, 3, 3], True), ([2, 2, 2, 3], False)])  # 2.5, then 2.4875
def test_g2_lower_bound_is_inclusive(last, passed):
    records, pools, tasks = build(lambda t: last if t == 19 else [2, 2, 3, 3])
    assert task_gates(records, pools, tasks)["G2"]["passed"] is passed


@pytest.mark.parametrize("last, passed", [([6, 6, 7, 7], True), ([6, 7, 7, 7], False)])  # 6.5, then 6.5125
def test_g2_upper_bound_is_inclusive(last, passed):
    records, pools, tasks = build(lambda t: last if t == 19 else [6, 6, 7, 7], lambda t: 8)
    assert task_gates(records, pools, tasks)["G2"]["passed"] is passed


@pytest.mark.parametrize("scores, survivor", [([2, 2, 2, 2], True), ([6, 6, 7, 7], True), ([1, 2, 2, 2], False),
                                              ([6, 7, 7, 7], False)])
def test_survivor_bounds_two_and_six_and_a_half_are_inclusive(scores, survivor):
    records, _, tasks = build(lambda t: scores)
    assert gates.task_table(records, H, tasks)["t00"]["survivor"] is survivor


@pytest.mark.parametrize("survivors, passed", [(12, True), (11, False)])
def test_g1_needs_twelve_survivors(survivors, passed):
    records, pools, tasks = build(lambda t: [4] * 4 if t < survivors else [8] * 4, lambda t: 8)
    assert task_gates(records, pools, tasks)["G1"]["passed"] is passed


@pytest.mark.parametrize("rated, passed", [(90, True), (89, False)])  # of 100 natural candidates
def test_g4_needs_exactly_ninety_percent_rated(rated, passed):
    records, pools, tasks = build(lambda t: [4] * 4)
    for r in [r for r in records if r["pool"] == "first" and r["role"] == "candidate"][rated:]:
        r["status"], r["scores"] = "incident", {}
    assert task_gates(records, pools, tasks)["G4"]["passed"] is passed


@pytest.mark.parametrize("pools_lost, passed", [(2, True), (3, False)])
def test_g4_allows_a_judge_excluded_on_two_pools(pools_lost, passed):
    records, pools, tasks = build(lambda t: [4] * 4)
    for pool in pools[:pools_lost]:
        pool["excluded_judges"] = {S: "judge_failed"}
    assert task_gates(records, pools, tasks)["G4"]["passed"] is passed


@pytest.mark.parametrize("short, passed", [(2, True), (3, False)])  # 18 then 17 tasks with reference - base >= 4
def test_v1_needs_the_control_gap_on_eighteen_tasks(short, passed):
    records, _, tasks = build(lambda t: [4] * 4, ref=lambda t: 4 if t < short else 8,
                              base=lambda t: 1 if t < short else 0)
    assert gates.v1_controls(records, H, tasks)["passed"] is passed


@pytest.mark.parametrize("low, passed", [(4, True), (3, False)])  # mean reference exactly 6, then 5.95
def test_v1_mean_reference_of_six_is_enough(low, passed):
    records, _, tasks = build(lambda t: [4] * 4, ref=lambda t: 8 if t < 10 else (low if t == 19 else 4))
    assert gates.v1_controls(records, H, tasks)["passed"] is passed


@pytest.mark.parametrize("extra, passed", [(0, True), (1, False)])  # mean base exactly 1, then 1.05
def test_v1_mean_base_of_one_is_allowed(extra, passed):
    records, _, tasks = build(lambda t: [4] * 4, base=lambda t: 4 if t < 5 else (extra if t == 19 else 0))
    assert gates.v1_controls(records, H, tasks)["passed"] is passed


@pytest.mark.parametrize("ref, met", [(6, 20), (5, 0)])  # the reference equal to its batch mean ranks
def test_v2_reference_equal_to_its_batch_mean_ranks(ref, met):
    records, _, tasks = build(lambda t: [6] * 4, ref=lambda t: ref, base=lambda t: 0)
    assert gates.v2_reference_rank(records, H, tasks)["met"] == met


@pytest.mark.parametrize("shifted, passed", [(7, True), (8, False)])  # 7 of 70 clones differ by 2: exactly 10%
def test_v3_allows_exactly_ten_percent_large_differences(shifted, passed):
    shifts = {(t % 10, 2 + t // 10): 2 for t in range(shifted)}
    records, _, tasks = build(lambda t: [2] * 4, lambda t: 2, retest_shift=shifts)
    assert gates.v3_retest(records, H, tasks[:10])["passed"] is passed


@pytest.mark.parametrize("shifted, passed", [(42, True), (43, False)])  # over 8 tasks' 56 clones: exactly 3/4
def test_v3_mean_difference_of_exactly_three_quarters_passes(shifted, passed):
    shifts = {(t % 8, t // 8): 1 for t in range(shifted)}
    records, _, tasks = build(lambda t: [2] * 4, lambda t: 2, retest_shift=shifts)
    out = gates.v3_retest(records, H, tasks[:8])
    assert (out["mean_abs"], out["passed"]) == (Fraction(shifted, 56), passed)


def v4_records(failing_ties):
    """20 hidden-passing candidates scoring 6; 20 failing, `failing_ties` of them scoring 6 and the rest 4."""
    def rec(k, score, hidden):
        return {"task": f"t{k // 5:02d}", "pool": "first", "role": "candidate", "arm": "direct", "model": H,
                "run": f"r{k}", "patch": f"p{k}", "hidden": hidden, "scores": {H: score}, "status": "rated",
                "reason": None}
    return [rec(k, 6, 1.0) for k in range(20)] + [rec(20 + k, 6 if k < failing_ties else 4, 0.5) for k in range(20)]


@pytest.mark.parametrize("ties, passed", [(10, True), (11, False)])  # P = 3/4 exactly, then 0.725
def test_v4_probability_of_exactly_three_quarters_passes(ties, passed):
    out = gates.v4_agreement(v4_records(ties), H, [f"t{t:02d}" for t in range(8)])
    assert (out["passed"], out["probability"] == Fraction(3, 4)) == (passed, passed)


@pytest.mark.parametrize("per_class, assessed", [(15, True), (14, False)])
def test_v4_needs_fifteen_in_each_class(per_class, assessed):
    records = v4_records(10)
    keep = records[:per_class] + records[20:20 + per_class]
    assert gates.v4_agreement(keep, H, [f"t{t:02d}" for t in range(8)])["assessed"] is assessed
