"""Seed-set judge gate, task gates, anchor checks, re-roll baselines and the seed selection rule on small synthetic
record sets (experiments/seed_set/gates.py, selection.py). No harness, no provider."""

from fractions import Fraction

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


def test_a_task_set_that_is_too_easy_has_no_survivors_and_stops_without_a_later_redraw():
    records, pools = world(haiku=(7, 8, 8, 7), sonnet=8)
    result = gates.calibration(records, pools, *tasks_of())
    g = result["gates"]
    assert (g["G1"]["passed"], g["G2"]["haiku_mean"], g["G2"]["passed"], result["decision"]) == (
        False, 7.5, False, "stop: a gate fails and the ladder probe was the one redraw; no quality claim")


def test_a_task_set_that_is_too_hard_fails_g2_and_stops():
    records, pools = world(haiku=(0, 1, 0, 1), sonnet=2, passes=lambda s: s >= 1)
    result = gates.calibration(records, pools, *tasks_of())
    g = result["gates"]
    assert (g["G1"]["survivors"], g["G2"]["passed"], result["decision"]) == (
        0, False, "stop: a gate fails and the ladder probe was the one redraw; no quality claim")


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
    hashes = {"c1": "a", "c2": "b", "c3": "c"}
    records, _ = gates.pool_records("t", "first", results, hashes, {"direct": H}, {H: hashes})
    assert [(r["role"], r["run"], r["status"], r["scores"]) for r in records] == [
        ("base", None, "rated", {H: 0}), ("reference", None, "rated", {H: 8}), ("candidate", "/r/1", "rated", {H: 6}),
        ("candidate", "/r/2", "failed", {}), ("candidate", "/r/3", "excluded", {})]


def test_a_rating_of_another_patch_than_the_pooled_one_is_refused():
    results = {"excluded_judges": {}, "runs": [], "clones": {
        "c1": {"arm": "anchor", "labels": ["t-base"], "run": None, "hidden": 0.5, "ratings": {H: {"quality": 0}}},
        "c2": {"arm": "direct", "labels": ["final"], "run": "/r/1", "hidden": 1.0,
               "ratings": {H: {"quality": 6}, S: {"quality": 7}}}}}
    hashes = {"c1": "a", "c2": "c"}
    records, _ = gates.pool_records("t", "first", results, hashes, {"direct": H}, {H: {"c1": "a", "c2": "x"},
                                                                                   S: hashes})
    assert ([r["scores"] for r in records], len(gates.binding_failures(records))) == ([{H: 0}, {S: 7}], 1)


def test_an_unexpected_anchor_is_refused():
    with pytest.raises(SystemExit, match="unexpected anchor"):
        gates.anchor_role("t-mutant")


def test_rerolls_average_every_ordered_triple():
    out = selection.rerolls([(8, True), (2, False), (5, False)])
    # Q2 over the six orders: 8 8 (first passes), 8 8 (second passes), 5 2 (neither: the second attempt)
    assert (out["Q1"], out["Q2"], out["Q2_calls"], out["Q3"], out["Q3_calls"]) == (5, 6.5, Fraction(10, 6), 8, 2)


def test_rerolls_need_three_runs():
    with pytest.raises(SystemExit, match="three direct runs"):
        selection.rerolls([(8, True), (2, False)])


def arm(scores, calls=1, completed=1, distinctive=Fraction(1, 2), parity=None, lines=40, priced_worst=None,
        priced_metered=None, nested=0, model=H, effort="medium"):
    return {"tasks": dict(enumerate(scores)), "calls": calls, "completed": completed, "priced_worst": priced_worst,
            "priced_metered": priced_metered, "distinctive": distinctive, "parity": parity, "lines": lines,
            "nested": nested, "model": model, "effort": effort}


DIRECT = arm([4, 5, 6, 5])
HALF = Fraction(11, 2)
REROLLED = {"tasks": {t: {"Q1": q, "Q2": HALF, "Q3": HALF} for t, q in enumerate([4, 5, 6, 5])},
            "Q1": 5, "Q2": HALF, "Q3": HALF}


def test_a_workflow_at_direct_quality_and_two_calls_is_a_seed():
    result = selection.select_seeds({"direct": DIRECT, "implement_review_revise": arm([4, 5, 6, 5], calls=Fraction(11, 5))},
                                    REROLLED)
    assert result["seeds"] == ["direct", "implement_review_revise"]


@pytest.mark.parametrize("name, candidate, rule", [
    ("retry_until_check", arm([3, 4, 5, 4], calls=Fraction(7, 5), parity=True), "2_quality"),
    ("implement_check_repair", arm([Fraction(9, 2)] * 4, calls=Fraction(13, 5)), "3_reroll"),
    ("implement_check_repair", arm([5, 5, 6, 5], calls=Fraction(16, 5)), "4_cost"),
    ("implement_check_repair", arm([5, 5, 6, 5], completed=Fraction(9, 10)), "1_completes"),
    ("implement_check_repair", arm([5, 5, 6, 5], distinctive=Fraction(1, 10)), "5_distinctive"),
    ("retry_until_check", arm([5, 5, 6, 5], calls=Fraction(13, 5), parity=False), "6_parity"),
    ("implement_review_revise", arm([5, 5, 6, 5], calls=Fraction(11, 5), lines=50), "7_lines"),
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


def test_direct_stays_in_the_set_as_the_reference_whatever_its_size():
    result = selection.select_seeds({"direct": {**DIRECT, "lines": 50}}, REROLLED)
    assert (result["seeds"], result["arms"]["direct"]["lines"]) == (["direct"], 50)


def test_a_quality_exactly_half_a_point_under_direct_in_thirds_passes_rule_2():
    # q = 11/3 and q_direct = 25/6: exactly q_direct - 0.5, which a float mean of these thirds misses
    thirds = lambda *n: dict(enumerate(Fraction(k, 3) for k in n))
    direct = {**DIRECT, "tasks": thirds(23, 7, 18, 2)}
    candidate = {**arm([0]), "tasks": thirds(0, 22, 14, 8)}
    result = selection.select_seeds({"direct": direct, "implement_check_repair": candidate}, REROLLED)
    assert result["arms"]["implement_check_repair"]["rules"]["2_quality"] is True


def test_select_seeds_runs_its_dominance_test_on_exact_inputs():
    # equal quality at 2.2 times direct's calls, every figure a Fraction: direct dominates
    exact = lambda summary, calls: {**summary, "tasks": {t: Fraction(v) for t, v in summary["tasks"].items()},
                                    "calls": Fraction(calls)}
    result = selection.select_seeds({"direct": exact(DIRECT, 1), "implement_review_revise": exact(DIRECT, Fraction(11, 5))},
                                    REROLLED)
    assert result["arms"]["implement_review_revise"]["dominated_by_direct"] is True


@pytest.mark.parametrize("field, value", [("completed", 0.95), ("nested", 0.1), ("distinctive", 0.2),
                                          ("calls", 2.0)])
def test_a_float_figure_at_a_threshold_is_refused_by_name(field, value):
    with pytest.raises(SystemExit, match=f"{field} is {value!r}"):
        selection.rules("implement_check_repair", {**arm([5] * 4), field: value}, DIRECT, REROLLED)


def test_a_float_task_mean_is_refused():
    with pytest.raises(SystemExit, match="tasks is 4.5"):
        selection.rules("implement_check_repair", arm([4.5] * 4), DIRECT, REROLLED)


def test_rule_1_passes_at_exactly_19_of_20_runs_complete():
    rules = selection.rules("implement_check_repair", arm([5] * 4, completed=Fraction(19, 20)), DIRECT, REROLLED)
    assert rules["1_completes"] is True


def test_rule_4_passes_at_exactly_three_times_directs_calls():
    rules = selection.rules("implement_check_repair", arm([5] * 4, calls=3), DIRECT, REROLLED)
    assert rules["4_cost"] is True


@pytest.mark.parametrize("worst, metered", [(0.5, 0.07), (0.7, 0.05)])  # direct 0.2 and 0.02: 3 times is 0.6, 0.06
def test_rule_4_fails_an_arm_over_the_limit_at_either_priced_bound(worst, metered):
    candidate = arm([5] * 4, calls=2, priced_worst=worst, priced_metered=metered)
    direct = arm([4, 5, 6, 5], priced_worst=0.2, priced_metered=0.02)
    assert selection.rules("implement_check_repair", candidate, direct, REROLLED)["4_cost"] is False


def test_rule_4_passes_an_arm_within_the_limit_at_both_priced_bounds():
    candidate = arm([5] * 4, calls=2, priced_worst=0.5, priced_metered=0.05)
    direct = arm([4, 5, 6, 5], priced_worst=0.2, priced_metered=0.02)
    assert selection.rules("implement_check_repair", candidate, direct, REROLLED)["4_cost"] is True


def run(task="t0", outcome="completed", calls=1, score=0, **facts):
    """A run's study.json facts as the selection functions read them, with the caller's `score`."""
    return {"task": task, "outcome": outcome, "calls": calls, "score": score, **facts}


def checked(passed):
    return run(visible={"passed": passed, "failing": [], "excerpt": ""})


@pytest.mark.parametrize("failing, launch", [(19, False), (20, True)])
def test_the_visible_check_launches_the_check_arms_from_a_20_percent_failure_rate(failing, launch):
    runs = [checked(False) for _ in range(failing)] + [checked(True) for _ in range(100 - failing)]
    assert selection.visible_power(runs)["launch"] is launch


def test_the_visible_rate_counts_only_runs_whose_patch_the_check_ran_on():
    runs = [checked(False), checked(True), checked(True), checked(True),
            run(outcome="failed", failure={"code": "provider_timeout"}),  # cut at the call limit: no patch
            run(visible={"passed": None, "failing": [], "excerpt": "", "timed_out": "past its bound"}),
            checked(False) | {"incident": "provider: error"}, checked(False) | {"cut": {"text": "limit"}}]
    out = selection.visible_power(runs)
    assert (out["failed"], out["checked"], out["rate"]) == (1, 4, Fraction(1, 4))


def test_completion_keeps_call_limit_cuts_and_drops_incidents_and_contaminated_runs():
    runs = [run(), run(outcome="failed", failure={"code": "provider_timeout"}), run(incident="session audit: x"),
            run(excluded="contaminated: fix hash"), run(cut={"text": "limit"})]
    assert selection.completion(runs) == Fraction(1, 2)


PARITY_TASKS = [f"t{k}" for k in range(6)]
OFFLINE = {"tasks": {t: {"Q3": 5, "Q3_calls": Fraction(3, 2)} for t in PARITY_TASKS}}


def retry_runs(calls, score=5):
    return [run(t, "completed", calls, score) for t in PARITY_TASKS for _ in range(2)]


@pytest.mark.parametrize("runs, passed", [
    (retry_runs(calls=2), True),  # half a call off, scores equal
    (retry_runs(calls=Fraction(21, 10)), False),  # 0.6 calls off
    (retry_runs(calls=2, score=Fraction(13, 2)), True),  # 1.5 points off
    (retry_runs(calls=2, score=7), False),
])
def test_retry_parity_needs_calls_within_half_a_call_and_score_within_1_5_points(runs, passed):
    assert selection.parity(runs, OFFLINE)["passed"] is passed


def test_retry_parity_fails_when_a_run_does_not_complete():
    runs = retry_runs(calls=2)
    runs[0] = run(PARITY_TASKS[0], "failed", 2, 5, failure={"code": "provider_timeout"})
    assert selection.parity(runs, OFFLINE)["passed"] is False


def test_retry_parity_fails_and_lists_a_task_without_a_baseline():
    offline = {"tasks": {t: row for t, row in OFFLINE["tasks"].items() if t != "t5"}}
    out = selection.parity(retry_runs(calls=2), offline)
    assert (out["passed"], out["no_baseline"]) == (False, ["t5"])


@pytest.mark.parametrize("name, calls, share", [
    ("implement_review_revise", [3] * 19 + [2] * 81, Fraction(19, 100)),  # the revision is its third call
    ("implement_check_repair", [2] * 20 + [1] * 80, Fraction(1, 5)),  # a repair is its second call
    ("retry_until_check", [3] * 10 + [2] * 10 + [1] * 80, Fraction(1, 5)),  # a second attempt is its second call
])
def test_the_distinctive_step_is_read_from_physical_calls(name, calls, share):
    assert selection.distinctive(name, [run(calls=c) for c in calls]) == share


def test_rule_5_fails_an_arm_whose_third_call_ran_in_19_percent_of_runs():
    share = selection.distinctive("implement_review_revise", [run(calls=c) for c in [3] * 19 + [2] * 81])
    candidate = arm([4, 5, 6, 5], calls=Fraction(11, 5), distinctive=share)
    result = selection.select_seeds({"direct": DIRECT, "implement_review_revise": candidate}, REROLLED)
    assert result["arms"]["implement_review_revise"]["rules"]["5_distinctive"] is False


def test_rule_2_compares_an_arm_on_six_tasks_with_direct_on_those_six():
    # direct scores 5 on the six tasks retry ran and 0 on ten others: over all 16 its line (11/8) would pass 4
    direct = {**DIRECT, "tasks": {t: 5 if t < 6 else 0 for t in range(16)}}
    rolled = {"tasks": {t: {"Q3": 5} for t in range(16)}}
    retry = arm([4] * 6, calls=2, parity=True)
    rules = selection.select_seeds({"direct": direct, selection.RETRY: retry}, rolled)["arms"][selection.RETRY]["rules"]
    assert rules["2_quality"] is False


def test_rules_2_and_3_leave_out_a_task_without_three_usable_direct_runs():
    rolled = {"tasks": {t: {"Q2": 5} for t in range(3)}}  # task 3 had fewer than three usable direct runs
    candidate = arm([5, 5, 5, 0], calls=2)
    result = selection.select_seeds({"direct": DIRECT, "implement_check_repair": candidate}, rolled)
    report = result["arms"]["implement_check_repair"]
    assert (report["rules"]["2_quality"], report["rules"]["3_reroll"], report["left_out"]) == (True, True, [3])


@pytest.mark.parametrize("arm_nested, direct_nested, dominated", [
    (0, 0, True),
    (Fraction(1, 10), 0, True),  # exactly a tenth: calls stay the cost
    (Fraction(11, 100), 0, False),
    (0, Fraction(11, 100), False),  # direct's own nested sessions switch the comparison too
])
def test_nested_sessions_in_over_10_percent_of_either_arms_runs_make_priced_tokens_the_cost(
        arm_nested, direct_nested, dominated):
    # twice direct's calls at direct's priced cost: dominated on calls, not on priced tokens
    candidate = arm([4, 5, 6, 5], calls=2, priced_worst=0.02, nested=arm_nested)
    direct = arm([4, 5, 6, 5], priced_worst=0.02, nested=direct_nested)
    result = selection.select_seeds({"direct": direct, "implement_review_revise": candidate}, REROLLED)
    assert result["arms"]["implement_review_revise"]["dominated_by_direct"] is dominated


def test_arms_on_different_models_are_compared_on_priced_cost():
    candidate = arm([4, 5, 6, 5], calls=2, priced_worst=0.02, model="gpt-6-luna")
    result = selection.select_seeds({"direct": arm([4, 5, 6, 5], priced_worst=0.02), "retry_until_check_luna": candidate},
                                    REROLLED)
    assert result["arms"]["retry_until_check_luna"]["cost_basis"] == "priced_worst"


def test_a_priced_cost_basis_refuses_an_arm_without_a_priced_figure():
    with pytest.raises(SystemExit, match="priced"):
        selection.rules("implement_review_revise", arm([5] * 4, nested=Fraction(1, 5)), DIRECT, REROLLED)


@pytest.mark.parametrize("score, eligible", [
    (Fraction(17, 4), True),  # a quarter point under rule 2's line (4.5)
    (Fraction(19, 4), True),  # a quarter point over it
    (5, False),
    (Fraction(21, 5), False),
])
def test_an_arm_within_a_quarter_point_of_rule_2s_line_is_extension_eligible(score, eligible):
    rolled = {"tasks": {t: {"Q2": 0} for t in range(4)}}  # rule 3's line far below
    assert selection.extension_eligible("implement_check_repair", arm([score] * 4, calls=2), DIRECT, rolled) is eligible


def test_an_arm_within_a_quarter_point_of_rule_3s_line_is_extension_eligible():
    rolled = {"tasks": {t: {"Q2": 7} for t in range(4)}}  # rule 3's line 6.5, rule 2's 4.5
    candidate = arm([Fraction(25, 4)] * 4, calls=2)
    assert selection.extension_eligible("implement_check_repair", candidate, DIRECT, rolled) is True



def test_rerolls_return_exact_means():
    out = selection.rerolls([(1, True), (1, False), (2, False)])
    assert (out["Q1"], out["random_of_3"]) == (Fraction(4, 3), Fraction(4, 3))


def test_a_pool_incident_costs_its_task_and_suppresses_nothing_else():
    records, pools = world()
    records = [r for r in records if not (r["task"] == "t05" and r["pool"] == "first")]
    pools = [p for p in pools if (p["task"], p["pool"]) != ("t05", "first")]
    pools.append({"task": "t05", "pool": "first", "incident": "judge run failed", "excluded_judges": {H: "judge_failed"}})
    tasks, retests = tasks_of()
    result = gates.calibration(records, pools, tasks, retests)
    assert (gates.anchor_failures(records, pools, tasks), gates.missing_pools(pools, tasks, retests),
            result["judges"][H]["V1"]["missing"], result["gates"]["G4"]["judge_exclusions"][H]) == (
        [], {"t05/first": "judge run failed"}, ["t05"], 1)


def test_a_task_never_summarized_is_missing_not_a_global_anchor_failure():
    records, pools = world()
    tasks, retests = tasks_of()
    assert (gates.anchor_failures(records, pools, tasks + ["t99"]),
            gates.missing_pools(pools, tasks + ["t99"], retests)) == ([], {"t99/first": "not summarized"})


def test_g2_and_g3_compare_only_tasks_with_both_arms():
    records, pools = world()
    for r in records:  # t00's Sonnet run is an incident; its Haiku runs must leave the means too
        if r["task"] == "t00" and r["model"] == S:
            r.update(status="incident", scores={})
            r["scores"] = {}
    for r in records:
        if r["task"] == "t00" and r["model"] == H and r["pool"] == "first":
            r["scores"] = {j: 8 for j in gates.JUDGES}
    g = gates.task_gates(records, pools, H, tasks_of()[0])["gates"]
    assert (g["G2"]["tasks"], g["G2"]["haiku_mean"], g["G3"]["gap"]) == (19, 3.75, 2.25)


def test_a_retest_pool_missing_a_first_pool_clone_makes_its_task_missing():
    records, _ = world()
    records.remove(next(r for r in records if r["pool"] == "retest" and r["role"] == "candidate"))
    assert gate(records)["V3"]["missing"] == ["t00"]


def test_v3_reports_the_candidate_only_difference_beside_the_all_clone_one():
    records, _ = world(retest_shift=1)
    v3 = gate(records)["V3"]
    assert (v3["mean_abs"], v3["candidate_mean_abs"]) == (gates.Fraction(6, 7), 1)


def test_g4_ignores_judge_exclusions_on_pools_outside_the_gated_tasks():
    records, pools = world()
    pools += [{"task": "smoke", "pool": "first", "excluded_judges": {S: "judge_failed"}}]
    for pool in pools[:2]:
        pool["excluded_judges"][S] = "judge_failed"
    assert gates.task_gates(records, pools, H, tasks_of()[0])["gates"]["G4"]["passed"] is True


def test_the_decision_states_when_v4_was_not_assessed_for_the_selected_judge():
    from experiments.seed_set import readout
    records, pools = world(passes=lambda s: True)
    tasks, retests = tasks_of()
    report = readout.report(records, pools, tasks, retests, {"T3": 20}, {}, {}, {}, 100)
    decision = readout.markdown(report).split("Decision: ", 1)[1].splitlines()[0]
    assert ("V4" in decision and "not assessed" in decision, report["calibration"]["v4_note"] is not None) == (True, True)


def test_the_decision_carries_no_v4_statement_when_v4_was_assessed():
    from experiments.seed_set import readout
    records, pools = world()
    tasks, retests = tasks_of()
    assert readout.report(records, pools, tasks, retests, {"T3": 20}, {}, {}, {}, 100)["calibration"]["v4_note"] is None


def test_incidents_over_a_tenth_of_the_planned_runs_make_the_decision_a_stop():
    from experiments.seed_set import readout
    records, pools = world()
    tasks, retests = tasks_of()
    runs = {f"r{k}": {"tranche": "calibration", "task": "t00", "arm": "direct", "outcome": "failed",
                    "incident": "provider: 429"}
            for k in range(11)}
    decision = readout.report(records, pools, tasks, retests, {"T3": 20}, runs, {}, {}, 100)["calibration"]["decision"]
    assert decision.startswith("stop: 11 of 100 planned runs are incidents")


def shifted(world_kwargs, edit):
    records, pools = world(**world_kwargs)
    for r in records:
        edit(r)
    return records, pools


def test_v1_a_gap_of_exactly_four_counts():
    records, _ = world(ref=5, base=1)
    assert gate(records)["V1"]["met"] == 20


def test_v1_a_mean_reference_of_exactly_six_passes():
    records, _ = world(ref=6, base=0, haiku=(2, 2, 2, 2), sonnet=2)
    assert gate(records)["V1"]["passed"] is True


def test_v1_mean_base_exactly_one_passes_and_above_fails():
    for base, passed in ((1, True), (2, False)):
        records, _ = world(ref=8, base=base)
        assert gate(records)["V1"]["passed"] is passed


def test_v2_reference_equal_to_the_candidate_mean_counts():
    records, _ = world(haiku=(6, 6, 6, 6), sonnet=6, ref=6)
    assert gate(records)["V2"]["met"] == 20


def v3_of(differences):
    """V3 over ten retest tasks whose seventy clones differ from their first judgment by `differences`."""
    records, _ = world(haiku=(4, 4, 4, 4), sonnet=4, ref=7, base=1)
    retest = [r for r in records if r["pool"] == "retest"]
    for r, d in zip(retest, differences):
        r["scores"] = {j: v + d for j, v in r["scores"].items()}
    return gate(records)["V3"]


def test_v3_at_exactly_three_quarters_passes():
    assert v3_of([1] * 52 + [0] * 18)["passed"] is True  # 52/70 = 0.743 <= 0.75


def test_v3_just_above_three_quarters_fails():
    assert v3_of([1] * 53 + [0] * 17)["passed"] is False  # 53/70 = 0.757


def test_v3_at_exactly_ten_percent_large_differences_passes():
    assert v3_of([2] * 7 + [0] * 63)["passed"] is True  # 7/70 = 0.10, mean 0.2


def test_v3_just_above_ten_percent_large_differences_fails():
    assert v3_of([2] * 8 + [0] * 62)["passed"] is False


def test_v3_a_difference_of_exactly_two_counts_as_large():
    assert v3_of([2] * 8 + [0] * 62)["large_fraction"] == gates.Fraction(8, 70)


@pytest.mark.parametrize("haiku, survivor", [((2, 2, 2, 2), True), ((6, 7, 6, 7), True), ((1, 2, 2, 2), False),
                                             ((7, 7, 6, 7), False)])
def test_the_survivor_band_is_inclusive_at_two_and_six_and_a_half(haiku, survivor):
    records, _ = world(haiku=haiku)
    assert gates.task_table(records, H, ["t00"])["t00"]["survivor"] is survivor


@pytest.mark.parametrize("haiku, passed", [((2, 3, 2, 3), True), ((6, 7, 6, 7), True), ((2, 2, 3, 2), False),
                                           ((7, 7, 6, 7), False)])
def test_g2_is_inclusive_at_two_and_a_half_and_six_and_a_half(haiku, passed):
    records, pools = world(haiku=haiku, sonnet=8)
    assert gates.task_gates(records, pools, H, tasks_of()[0])["gates"]["G2"]["passed"] is passed


@pytest.mark.parametrize("haiku, passed", [((3, 4, 4, 4), False), ((3, 3, 4, 4), True)])  # 0.25; exactly 0.5
def test_g3_needs_a_gap_of_at_least_half_a_point(haiku, passed):
    records, pools = world(haiku=haiku, sonnet=4)
    assert gates.task_gates(records, pools, H, tasks_of()[0])["gates"]["G3"]["passed"] is passed


@pytest.mark.parametrize("unrated, passed", [(10, True), (11, False)])
def test_g4_needs_at_least_ninety_percent_rated(unrated, passed):
    records, pools = world()
    for r in [r for r in records if r["pool"] == "first" and r["role"] == "candidate"][:unrated]:
        r.update(status="incident", scores={})
    assert gates.task_gates(records, pools, H, tasks_of()[0])["gates"]["G4"]["passed"] is passed


@pytest.mark.parametrize("exclusions, passed", [(2, True), (3, False)])
def test_g4_allows_two_judge_exclusions_and_not_three(exclusions, passed):
    records, pools = world()
    for pool in pools[:exclusions]:
        pool["excluded_judges"][S] = "judge_failed"
    assert gates.task_gates(records, pools, H, tasks_of()[0])["gates"]["G4"]["passed"] is passed


@pytest.mark.parametrize("failing, assessed", [(15, True), (14, False)])
def test_v4_needs_fifteen_in_each_class(failing, assessed):
    records, _ = world(passes=lambda s: True)
    candidates = [r for r in records if r["pool"] == "first" and r["role"] == "candidate"]
    for r in candidates[:failing]:
        r["hidden"] = 0.5
    assert gate(records)["V4"]["assessed"] is assessed


@pytest.mark.parametrize("calls, k", [(Fraction(149, 100), 1), (Fraction(3, 2), 2), (Fraction(5, 2), 3),
                                     (Fraction(249, 100), 2), (Fraction(2, 5), 1), (Fraction(18, 5), 3)])
def test_mean_calls_round_halves_up_to_one_two_or_three(calls, k):
    assert selection.calls_k(calls) == k


def test_v3_a_mean_of_exactly_three_quarters_passes():
    records, _ = world(haiku=(4, 4, 4, 4), sonnet=4, ref=7, base=1)
    retests = ["t00", "t01", "t02", "t03"]  # 28 clones, 21 of them one point apart: a mean of 0.75
    for r in [r for r in records if r["pool"] == "retest" and r["task"] in retests][:21]:
        r["scores"] = {j: v + 1 for j, v in r["scores"].items()}
    v3 = gates.v3_retest(records, H, retests)
    assert (v3["mean_abs"], v3["passed"]) == (0.75, True)

