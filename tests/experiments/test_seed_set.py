"""Seed-set judge gate, task gates, anchor checks, re-roll baselines and the seed selection rule on small synthetic
record sets (experiments/seed_set/gates.py, selection.py). No harness, no provider."""

import pytest

from experiments.seed_set import gates, selection

H, S = gates.HAIKU, gates.SONNET
HAIKU_RUNS = 4


def record(task, pool, role, arm, model, run, patch, hidden, scores, status="rated"):
    return {"task": task, "pool": pool, "role": role, "arm": arm, "model": model, "run": run, "patch": patch,
            "hidden": hidden, "scores": scores, "status": status, "reason": None}


def world(tasks=20, haiku=(2, 4, 6, 3), sonnet=6, ref=8, base=0, passes=lambda s: s >= 5, retest_shift=0, judge=None):
    """Records of `tasks` drawn tasks (the first ten retested): every judge rates the base `base`, the reference
    `ref`, the Haiku runs `haiku` and the Sonnet run `sonnet`; a candidate passes the hidden tests when `passes`
    says so. `judge` limits a non-default scoring to one judge, the other scoring the default world."""
    records, pools = [], []
    for i in range(tasks):
        task = f"t{i:02d}"
        for pool in ("first", "retest") if i < 10 else ("first",):
            shift = retest_shift if pool == "retest" else 0
            pools.append({"task": task, "pool": pool, "excluded_judges": {}})

            def scored(value, default):
                return {j: min(8, value + shift) if judge in (None, j) else min(8, default + shift) for j in gates.JUDGES}
            records.append(record(task, pool, "base", "anchor", None, None, gates.EMPTY_SHA, 0.5, scored(base, 0)))
            records.append(record(task, pool, "reference", "anchor", None, None, f"ref-{task}", 1.0, scored(ref, 8)))
            runs = [("direct", H, s, d) for s, d in zip(haiku, (2, 4, 6, 3))] + [("direct_sonnet", S, sonnet, 6)]
            for k, (arm, model, value, default) in enumerate(runs):
                records.append(record(task, pool, "candidate", arm, model, f"{task}/run-{k}", f"p-{task}-{k}",
                                      1.0 if passes(value) else 0.5, scored(value, default)))
    return records, pools


def tasks_of(n=20):
    return [f"t{i:02d}" for i in range(n)], [f"t{i:02d}" for i in range(min(n, 10))]


def gate(records, judge=H, n=20):
    tasks, retests = tasks_of(n)
    return gates.judge_gate(records, judge, tasks, retests)


def test_a_judge_that_separates_controls_ranks_the_reference_retests_stably_and_agrees_with_tests_passes():
    records, _ = world()
    result = gate(records)
    assert [result[k]["passed"] for k in ("V1", "V2", "V3", "V4")] + [result["passed"]] == [True] * 5


def test_a_judge_scoring_the_reference_below_its_candidates_fails_v2_only():
    records, _ = world(haiku=(6, 7, 7, 8), sonnet=8, ref=7)  # the October failure: the merged fix ranked low
    result = gate(records)
    assert (result["V1"]["passed"], result["V2"]["passed"], result["passed"]) == (True, False, False)


def test_a_judge_whose_retest_differs_by_a_point_on_identical_code_fails_v3():
    records, _ = world(retest_shift=1)  # the October failure: identical code scored 4, then 3
    result = gate(records)
    assert (result["V3"]["mean_abs"] > 0.75, result["V3"]["passed"], result["passed"]) == (True, False, False)


def test_a_judge_that_disagrees_with_the_hidden_tests_fails_v4():
    records, _ = world(passes=lambda s: s < 5)
    result = gate(records)
    assert (result["V4"]["probability"], result["V4"]["passed"], result["passed"]) == (0, False, False)


def test_v4_is_not_assessed_and_not_blocking_with_too_few_failing_candidates():
    records, _ = world(passes=lambda s: True)
    result = gate(records)
    assert (result["V4"]["assessed"], result["V4"]["passed"], result["passed"]) == (False, None, True)


def test_a_judge_blind_to_the_fix_fails_v1():
    records, _ = world(ref=1)
    assert gate(records)["V1"]["passed"] is False


def test_a_missing_control_fails_its_task_and_is_listed():
    records, _ = world()
    records = [r for r in records if not (r["task"] == "t00" and r["role"] == "reference")]
    assert gate(records)["V1"]["missing"] == ["t00"]


def test_v1_tolerates_two_of_twenty_tasks_below_the_gap():
    records, _ = world()
    for r in records:
        if r["task"] in ("t18", "t19") and r["role"] == "reference":
            r["scores"] = {j: 3 for j in gates.JUDGES}
    assert (gate(records)["V1"]["met"], gate(records)["V1"]["passed"]) == (18, True)


@pytest.mark.parametrize("n, v1, v2", [(20, 18, 17), (30, 27, 25)])
def test_counts_scale_to_the_plans_figures(n, v1, v2):
    assert (gates.required(0.9, n), gates.required(0.85, n)) == (v1, v2)


def test_a_retest_clone_without_a_first_judgment_is_refused():
    records, _ = world()
    next(r for r in records if r["pool"] == "retest" and r["role"] == "candidate")["patch"] = "other"
    with pytest.raises(SystemExit, match="matches no first judgment"):
        gate(records)


def test_a_qualified_task_set_passes_every_gate():
    records, pools = world()
    result = gates.calibration(records, pools, *tasks_of())
    assert (result["selected"], result["decision"], len(result["survivors"])) == (H, "qualified", 16)


def test_a_task_set_that_is_too_easy_has_no_survivors_and_is_redrawn():
    records, pools = world(haiku=(7, 8, 8, 7), sonnet=8)
    result = gates.calibration(records, pools, *tasks_of())
    g = result["gates"]
    assert (g["G1"]["passed"], g["G2"]["haiku_mean"], g["G2"]["passed"], result["decision"]) == (False, 7.5, False, "redraw")


def test_a_task_set_that_is_too_hard_fails_g2_and_stops_after_the_redraw():
    records, pools = world(haiku=(0, 1, 0, 1), sonnet=2, passes=lambda s: s >= 1)
    result = gates.calibration(records, pools, *tasks_of(), redrawn=True)
    g = result["gates"]
    assert (g["G1"]["survivors"], g["G2"]["passed"], result["decision"]) == (
        0, False, "stop: a gate still fails after the redraw; no quality claim")


def test_the_cheaper_judge_is_skipped_when_it_fails_its_gate():
    records, pools = world(ref=7, haiku=(6, 7, 7, 8), sonnet=8, judge=H)  # only Haiku ranks the reference low
    assert gates.calibration(records, pools, *tasks_of())["selected"] == S


def test_a_judge_insensitive_to_the_stronger_arm_hands_over_to_the_other_judge():
    # Haiku rates the Sonnet run like the Haiku runs; the tests (and Sonnet) see the stronger arm
    records, pools = world(sonnet=3, judge=H, passes=lambda s: s >= 5)
    for r in records:
        if r["model"] == S:
            r["hidden"] = 1.0
    result = gates.calibration(records, pools, *tasks_of())
    assert (result["insensitive"], result["selected"], result["gates"]["G3"]["passed"]) == (H, S, True)


def test_no_passing_judge_stops_with_the_hidden_tests_as_the_measure():
    records, pools = world(ref=1)
    result = gates.calibration(records, pools, *tasks_of())
    assert (result["selected"], result["decision"].startswith("stop"), "tests_primary" in result) == (None, True, True)


def test_a_failed_run_scores_zero_and_an_excluded_one_is_left_out():
    records, pools = world()
    runs = [r for r in records if r["task"] == "t00" and r["pool"] == "first" and r["model"] == H]
    runs[0].update(status="failed", scores={})
    runs[1].update(status="excluded", scores={}, reason="contaminated: read the fix")
    row = gates.task_table(records, H, ["t00"])["t00"]
    assert (row["haiku"], row["haiku_runs"], row["left_out"]) == ((0 + 6 + 3) / 3, 3, ["t00/run-1"])


def test_a_forbidden_model_run_fails_g4():
    records, pools = world()
    next(r for r in records if r["role"] == "candidate").update(
        status="excluded", scores={}, reason="Forbidden model used in 1 model record(s): ...")
    result = gates.task_gates(records, pools, H, tasks_of()[0])
    assert result["gates"]["G4"]["passed"] is False


def test_a_judge_excluded_on_three_pools_fails_g4():
    records, pools = world()
    for pool in pools[:3]:
        pool["excluded_judges"][S] = "contaminated: judge ran tests"
    assert gates.task_gates(records, pools, H, tasks_of()[0])["gates"]["G4"]["passed"] is False


def test_sound_anchors_raise_no_failure():
    records, pools = world()
    assert gates.anchor_failures(records, pools, tasks_of()[0]) == []


@pytest.mark.parametrize("role, change, expected", [
    ("base", {"patch": "changed"}, "not an unchanged clone"),
    ("reference", {"patch": gates.EMPTY_SHA}, "reference anchor is empty"),
    ("reference", {"hidden": 0.5}, "hidden tests give"),
    ("reference", {"scores": {H: 8}}, "did not rate both anchors"),
])
def test_a_damaged_anchor_is_reported(role, change, expected):
    records, pools = world()
    next(r for r in records if (r["task"], r["pool"], r["role"]) == ("t15", "first", role)).update(change)
    assert [expected in failure for failure in gates.anchor_failures(records, pools, tasks_of()[0])] == [True]


def test_pool_records_join_clones_and_unrated_runs_by_clone_id():
    results = {"excluded_judges": {}, "clones": {
        "c1": {"arm": "anchor", "labels": ["t-base"], "run": None, "hidden": 0.5, "ratings": {H: {"quality": 0}}},
        "c2": {"arm": "anchor", "labels": ["t-upstream"], "run": None, "hidden": 1.0, "ratings": {H: {"quality": 8}}},
        "c3": {"arm": "direct", "labels": ["final"], "run": "/r/1", "hidden": 1.0, "ratings": {H: {"quality": 6}}}},
        "runs": [{"run": "/r/1", "arm": "direct", "excluded": None, "failure": None},
                 {"run": "/r/2", "arm": "direct", "excluded": None, "failure": {"code": "provider_timeout"}},
                 {"run": "/r/3", "arm": "direct", "excluded": "contaminated: x", "failure": None}]}
    records, _ = gates.pool_records("t", "first", results, {"c1": "a", "c2": "b", "c3": "c"}, {"direct": H})
    assert [(r["role"], r["run"], r["status"], r["scores"]) for r in records] == [
        ("base", None, "rated", {H: 0}), ("reference", None, "rated", {H: 8}), ("candidate", "/r/1", "rated", {H: 6}),
        ("candidate", "/r/2", "failed", {}), ("candidate", "/r/3", "excluded", {})]


def test_an_unexpected_anchor_is_refused():
    with pytest.raises(SystemExit, match="unexpected anchor"):
        gates.anchor_role("t-mutant")


def test_rerolls_average_every_ordered_triple():
    out = selection.rerolls([(8, True), (2, False), (5, False)])
    # Q2 over the six orders: 8 8 (first passes), 8 8 (second passes), 5 2 (neither: the second attempt)
    assert (out["Q1"], out["Q2"], out["Q2_calls"], out["Q3"], out["Q3_calls"]) == (5, 6.5, 10 / 6, 8, 2)


def test_rerolls_need_three_runs():
    with pytest.raises(SystemExit, match="three direct runs"):
        selection.rerolls([(8, True), (2, False)])


def arm(scores, calls=1.0, completed=1.0, distinctive=0.5, parity=None, lines=40):
    return {"tasks": dict(enumerate(scores)), "calls": calls, "completed": completed, "tokens": None,
            "distinctive": distinctive, "parity": parity, "lines": lines}


DIRECT = arm([4, 5, 6, 5])
REROLLED = {"Q1": 5, "Q2": 5.5, "Q3": 5.5}


def test_a_workflow_at_direct_quality_and_two_calls_is_a_seed():
    result = selection.select_seeds({"direct": DIRECT, "implement_review_revise": arm([4, 5, 6, 5], calls=2.2)}, REROLLED)
    assert result["seeds"] == ["direct", "implement_review_revise"]


@pytest.mark.parametrize("name, candidate, rule", [
    ("retry_until_check", arm([3, 4, 5, 4], calls=1.4, parity=True), "2_quality"),
    ("implement_check_repair", arm([4.5] * 4, calls=2.6), "3_reroll"),
    ("implement_check_repair", arm([5, 5, 6, 5], calls=3.2), "4_cost"),
    ("implement_check_repair", arm([5, 5, 6, 5], completed=0.9), "1_completes"),
    ("implement_check_repair", arm([5, 5, 6, 5], distinctive=0.1), "5_distinctive"),
    ("retry_until_check", arm([5, 5, 6, 5], calls=2.6, parity=False), "6_parity"),
    ("implement_review_revise", arm([5, 5, 6, 5], calls=2.2, lines=50), "7_lines"),
])
def test_each_selection_rule_can_reject_a_workflow(name, candidate, rule):
    result = selection.select_seeds({"direct": DIRECT, name: candidate}, REROLLED)
    rules = result["arms"][name]["rules"]
    assert (result["seeds"], [k for k, ok in rules.items() if not ok]) == (["direct"], [rule])


def test_the_bootstrap_interval_is_fixed_by_its_seed_and_spans_the_mean():
    differences = [0.5, -1.0, 2.0, 0.0, 1.0]
    low, high = selection.bootstrap(differences)
    assert (selection.bootstrap(differences) == (low, high), low < 0.5 < high) == (True, True)


def test_a_program_file_counts_every_physical_line(tmp_path):
    program = tmp_path / "p.orc"
    program.write_text("(workflow-lisp\n\n  ;; a comment\n)\n")
    assert selection.program_lines(program) == 4


def test_a_direct_program_at_the_line_limit_is_not_a_seed():
    assert selection.select_seeds({"direct": {**DIRECT, "lines": 50}}, REROLLED)["seeds"] == []
