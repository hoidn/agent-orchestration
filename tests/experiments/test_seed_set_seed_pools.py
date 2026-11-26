"""The seed evaluation's two judge batches per task (`study.seed_batches`) on hand-built usable runs, its tranche kept
apart from the calibration's (`study.runs_to_pool`, `study.write_readout`) on a fabricated work root, its report
(`seeds.report`) on hand-built records, and its task list, pool kind and judge criterion (`study.write_seed_tasks`,
`layout.arm_tasks`, `layout.require_pool_kind`, `layout.load_seed_criterion`, the freeze's binding of
`judge-seeds.json`). No pool is built here and no provider is called."""

import pytest

from experiments.compare.repos import dump, load, sha256_file
from experiments.orc_structural_search import metering
from experiments.seed_set import gates, layout, rules, seeds, spend, study
from tests.experiments.seed_set_offline_support import committed_runtime, write_frozen_criterion

ARMS = ["direct", "retry_until_check", "implement_check_repair", "implement_review_revise"]  # arms.json order
PLANNED = {"direct": 6, "retry_until_check": 2, "implement_check_repair": 3, "implement_review_revise": 3}


def usable(counts):
    """`pool.pool_runs`' usable shape: arm -> [(records path, record)], each record with a final patch."""
    return {arm: [(f"/runs/{arm}-{k}", {"arm": arm, "patches": {"final": f"{arm}-{k}.diff"}}) for k in range(n)]
            for arm, n in counts.items()}


def placed(batches):
    """Records path -> index of the batch holding it, for every member."""
    return {path: index for index, batch in enumerate(batches) for path, _, _ in batch}


def test_the_planned_fourteen_runs_give_seven_and_seven():
    assert [len(b) for b in study.seed_batches(usable(PLANNED), ARMS, 0)] == [7, 7]


def test_each_usable_run_is_dealt_once_as_its_final_patch():
    runs = usable(PLANNED)
    members = [m for batch in study.seed_batches(runs, ARMS, 0) for m in batch]
    assert sorted((path, labels) for path, _, labels in members) == sorted(
        (path, ["final"]) for rows in runs.values() for path, _ in rows)


def test_every_arm_alternates_between_the_batches():
    runs = usable(PLANNED)
    where = placed(study.seed_batches(runs, ARMS, 0))
    sequences = {arm: [where[path] for path, _ in rows] for arm, rows in runs.items()}
    assert all(s[1:] == [1 - i for i in s[:-1]] for s in sequences.values())


def three_run_arms_over(tasks):
    """Per three-run arm, its runs in batch 0 and batch 1 over consecutive tasks, each task's usable runs given."""
    counts = {arm: [0, 0] for arm in ("implement_check_repair", "implement_review_revise")}
    for index, runs in enumerate(tasks, start=4):
        where = placed(study.seed_batches(runs, ARMS, index))
        for arm, count in counts.items():
            for path, _ in runs[arm]:
                count[where[path]] += 1
    return counts


def test_over_two_consecutive_tasks_each_three_run_arm_has_three_runs_in_each_batch():
    counts = three_run_arms_over([usable(PLANNED), usable(PLANNED)])
    assert counts == {arm: [3, 3] for arm in counts}


def test_a_direct_run_missing_on_one_task_leaves_the_three_run_arms_balanced_over_the_pair():
    counts = three_run_arms_over([usable({**PLANNED, "direct": 5}), usable(PLANNED)])
    assert counts == {arm: [3, 3] for arm in counts}


def test_a_batch_above_eight_runs_is_refused():
    with pytest.raises(SystemExit, match="batch of 9"):
        study.seed_batches(usable({"direct": 9, "implement_check_repair": 7}), ARMS, 0)


def test_an_arm_alternates_within_a_task_whatever_the_task_index():
    runs = usable(PLANNED)
    where = placed(study.seed_batches(runs, ARMS, 1))
    assert [where[path] for path, _ in runs["direct"]] == [1, 0, 1, 0, 1, 0]


def test_sixteen_usable_runs_fill_both_batches_to_eight():
    assert [len(b) for b in study.seed_batches(usable({**PLANNED, "direct": 8}), ARMS, 0)] == [8, 8]


def test_seventeen_usable_runs_are_refused():
    with pytest.raises(SystemExit, match="17 usable runs"):
        study.seed_batches(usable({**PLANNED, "direct": 9}), ARMS, 0)


def test_one_usable_run_gives_one_batch():
    assert [len(b) for b in study.seed_batches(usable({"implement_review_revise": 1}), ARMS, 0)] == [1]


def test_a_run_without_a_final_patch_is_not_dealt():
    runs = usable({"direct": 2})
    runs["direct"][0][1]["patches"] = {}
    assert list(placed(study.seed_batches(runs, ARMS, 0))) == ["/runs/direct-1"]


def test_an_arm_outside_the_arm_order_is_refused():
    with pytest.raises(SystemExit, match="direct_sonnet"):
        study.seed_batches(usable({"direct": 1, "direct_sonnet": 1}), ARMS, 0)


# --- tranches kept apart (B2) ------------------------------------------------------------------------------

def fabricated_study(tmp_path, tranches):
    """A study whose work root holds one collected, scanned run of task `t0` per tranche named, and an empty
    ledger; nothing else exists."""
    s = layout.Study(tmp_path / "rt", tmp_path / "work", tmp_path / "pools", tmp_path / "results",
                     tmp_path / "tasks.jsonl", tmp_path / "judge-calibration.json", tmp_path / "state")
    for k, tranche in enumerate(tranches):
        records = s.work / "records" / "t0" / f"run-{k}"
        records.mkdir(parents=True)
        dump(records / "study.json", {"tranche": tranche, "task": "t0", "arm": "direct", "scan_hits": 0})
    return s


def tranches_pooled(s, kind):
    return sorted(load(path / "study.json")["tranche"] for path in study.runs_to_pool(s, "t0", kind))


EVERY_TRANCHE = ["calibration", "redraw", "smoke", layout.SEED_EVALUATION, layout.LUNA_SMOKE, "extension"]


def test_a_first_pool_holds_only_calibration_runs_beside_seed_runs_of_its_task(tmp_path):
    s = fabricated_study(tmp_path, EVERY_TRANCHE)
    assert tranches_pooled(s, "first") == ["calibration", "redraw", "smoke"]


def test_a_seed_pool_holds_only_seed_evaluation_runs(tmp_path):
    s = fabricated_study(tmp_path, EVERY_TRANCHE)
    assert tranches_pooled(s, layout.SEED_POOL) == [layout.SEED_EVALUATION]


def test_a_tranche_no_pool_kind_names_lands_in_no_pool(tmp_path):
    s = fabricated_study(tmp_path, ["extension"])
    assert [tranches_pooled(s, kind) for kind in ("first", "retest", layout.SEED_POOL, layout.LUNA_POOL)] == [[]] * 4


def test_the_luna_pool_still_holds_only_the_luna_smokes_runs(tmp_path):
    s = fabricated_study(tmp_path, ["calibration", layout.SEED_EVALUATION, layout.LUNA_SMOKE])
    assert tranches_pooled(s, layout.LUNA_POOL) == [layout.LUNA_SMOKE]


def test_the_calibration_readout_refuses_once_the_seed_task_list_is_written(tmp_path):
    s = fabricated_study(tmp_path, ["calibration"])
    spend.record(s.ledger, "seed_tasks", tasks_sha256="x", calibration_sha256="y")
    with pytest.raises(SystemExit, match="seed_tasks"):
        study.write_readout(s)


# --- the seed report (A4) ----------------------------------------------------------------------------------

J = gates.HAIKU
PROGRAMS = {name: {"source": f"{name}.orc", "lines": 30, "model": J, "effort": "medium"} for name in ARMS}
DIRECT_SCORES = (4, 5, 6, 4, 5, 6)


def candidate(task, arm, k, score, batch, calls=1, passed=True):
    """(path, run facts, its rated record, batch) of one seed run: USD 0.25 a call, all metered, no nested session."""
    path = f"/w/{task}/{arm}/run-{k}"
    facts = {"tranche": layout.SEED_EVALUATION, "task": task, "arm": arm, "model": J, "effort": "medium",
             "outcome": "completed", "calls": calls, "priced": {"usd": 0.25 * calls, "missing": []},
             "nested_sessions": 0, "tokens": 1000 * calls, "visible": {"passed": passed}}
    record = {"task": task, "pool": layout.SEED_POOL, "role": "candidate", "arm": arm, "model": J, "run": path,
              "clone": f"{task}-{arm}-{k}", "patch": f"p-{task}-{arm}-{k}", "hidden": 1.0 if score >= 5 else 0.5,
              "scores": {J: score}, "status": "rated", "reason": None}
    return path, facts, record, batch


def anchor(task, role, b, score):
    return {"task": task, "pool": layout.SEED_POOL, "role": role, "arm": "anchor", "model": None, "run": None,
            "clone": f"{task}-{role}-{b}", "patch": gates.EMPTY_SHA if role == "base" else f"ref-{task}",
            "hidden": 0.5 if role == "base" else 1.0, "scores": {J: score}, "status": "rated", "reason": None}


def seed_world(n=16, workflow=5):
    """A sound seed evaluation on `n` tasks: per task direct's six runs (scores `DIRECT_SCORES`, the first run's
    visible check failing), retry's two on the first six tasks (2 calls), implement-check-repair's three (2 calls)
    and implement-review-revise's three (3 calls), the workflows scoring `workflow`; every batch holds base 0 and
    reference 8; runs alternate between the two batches; each pool's judge made 2 calls at USD 0.25."""
    w = {"tasks": [f"t{i:02d}" for i in range(n)], "records": [], "pools": [], "runs": {}, "judges": []}
    for i, task in enumerate(w["tasks"]):
        members = [candidate(task, "direct", k, s, (i + k) % 2, passed=k > 0) for k, s in enumerate(DIRECT_SCORES)]
        members += [candidate(task, "retry_until_check", k, workflow, (i + k) % 2, 2) for k in range(2 if i < 6 else 0)]
        members += [candidate(task, arm, k, workflow, (i + k) % 2, calls) for arm, calls in
                    (("implement_check_repair", 2), ("implement_review_revise", 3)) for k in range(3)]
        batches = [[], []]
        for b in (0, 1):
            for role, score in (("base", 0), ("reference", 8)):
                w["records"].append(anchor(task, role, b, score))
                batches[b].append(f"{task}-{role}-{b}")
        for path, facts, record, b in members:
            w["runs"][path] = facts
            w["records"].append(record)
            batches[b].append(record["clone"])
        w["pools"].append({"task": task, "pool": layout.SEED_POOL, "excluded_judges": {}, "batches": batches})
        w["judges"].append({"calls": 2, "priced": {"usd": 0.5, "missing": []}})
    return w


def seed_report(w, withheld=()):
    return seeds.report(w["records"], w["pools"], w["runs"], J, w["tasks"], PROGRAMS, w["judges"], withheld=withheld)


def anchor_record(w, task, role, b):
    return next(r for r in w["records"] if r["clone"] == f"{task}-{role}-{b}")


def weaken_controls(w, count):
    """Give `count` batches, from the first task on, a reference of 3 (reference minus base under 4)."""
    for k in range(count):
        anchor_record(w, w["tasks"][k // 2], "reference", k % 2)["scores"][J] = 3


def make_pool_incident(w, task):
    w["records"] = [r for r in w["records"] if r["task"] != task]
    w["pools"] = [p for p in w["pools"] if p["task"] != task] + [
        {"task": task, "pool": layout.SEED_POOL, "incident": "arm-identifying text in judged content"}]


def test_a_sound_seed_evaluation_selects_both_live_workflows_beside_direct():
    assert seed_report(seed_world())["selection"]["seeds"] == ["direct", "implement_check_repair",
                                                               "implement_review_revise"]


def test_two_base_anchors_in_one_batch_give_an_anchor_failure_and_no_figure():
    w = seed_world()
    anchor_record(w, "t03", "reference", 1).update(role="base", patch=gates.EMPTY_SHA, hidden=0.5)
    result = seed_report(w)
    assert (len(result["anchor_failures"]), result["controls"], result["selection"], "q" in result["arms"]["direct"]) \
        == (1, None, None, False)


def test_a_rating_bound_to_another_patch_gives_no_figure():
    w = seed_world()
    w["records"][-1]["unbound"] = [J]
    assert seed_report(w)["selection"] is None


@pytest.mark.parametrize("under, claim", [(3, True), (4, False)])
def test_more_than_three_of_32_batches_under_four_withhold_the_quality_figure(under, claim):
    w = seed_world()
    weaken_controls(w, under)
    assert (seed_report(w)["selection"] is not None) == claim


@pytest.mark.parametrize("under, claim", [(2, True), (3, False)])
def test_with_12_survivors_the_batch_bound_is_three_32nds_of_24_batches(under, claim):
    w = seed_world(n=12)
    weaken_controls(w, under)
    assert (seed_report(w)["selection"] is not None) == claim


def test_a_reference_exactly_four_above_the_base_is_not_under():
    w = seed_world()
    for b in (0, 1):
        for task in w["tasks"][:2]:
            anchor_record(w, task, "reference", b)["scores"][J] = 4
    assert seed_report(w)["controls"]["under"] == 0


@pytest.mark.parametrize("weak, claim", [(1, True), (2, False)])
def test_a_pool_incident_counts_its_two_batches_under_four(weak, claim):
    w = seed_world()
    make_pool_incident(w, "t15")
    weaken_controls(w, weak)
    assert (seed_report(w)["selection"] is not None) == claim


def test_the_missing_second_batch_of_a_one_batch_pool_counts_under_four():
    w = seed_world()
    pool = next(p for p in w["pools"] if p["task"] == "t15")
    pool["batches"] = pool["batches"][:1]
    assert seed_report(w)["controls"]["under_batches"] == ["t15#1"]


def test_only_direct_passing_gives_no_workflow_qualified_and_seeds_json_names_that_stop():
    out = seeds.seeds_json(seed_report(seed_world(workflow=3)), PROGRAMS)
    assert (out["decision"], out["stop"], [s["arm"] for s in out["seeds"]]) == (
        seeds.NO_WORKFLOW, seeds.NO_WORKFLOW, ["direct"])


def test_seeds_json_lists_the_selected_programs_with_their_figures_and_no_stop():
    out = seeds.seeds_json(seed_report(seed_world()), PROGRAMS)
    assert (out["stop"], [(s["arm"], s["q"], s["c"]) for s in out["seeds"]]) == (None, [
        ("direct", 5.0, 1.0), ("implement_check_repair", 5.0, 2.0), ("implement_review_revise", 5.0, 3.0)])


def test_seeds_json_after_a_failed_check_names_the_stop_and_lists_no_program():
    w = seed_world()
    weaken_controls(w, 4)
    out = seeds.seeds_json(seed_report(w), PROGRAMS)
    assert (out["stop"].startswith(seeds.NO_CLAIM), out["seeds"]) == (True, [])


def unpool(w, task, arm, k, facts, status, reason):
    """Run `k` of `arm` on `task` with `facts` added and no clone: its record becomes one of `status` (an unpooled
    or unrated run's record, as `gates.pool_records` or `study.unpooled_runs` make it)."""
    path = f"/w/{task}/{arm}/run-{k}"
    w["runs"][path] |= facts
    clone = f"{task}-{arm}-{k}"
    next(r for r in w["records"] if r["run"] == path).update(clone=None, patch=None, hidden=None, scores={},
                                                             status=status, reason=reason)
    for pool in w["pools"]:
        for batch in pool.get("batches", []):
            if clone in batch:
                batch.remove(clone)
    return path


def make_incident(w, task, arm, k):
    """A run the harness could not collect: an incident."""
    return unpool(w, task, arm, k, {"incident": "provider: error", "outcome": None}, "incident", "provider: error")


def make_failed(w, task, arm, k, code):
    """A run that failed with failure `code`: it scores 0."""
    return unpool(w, task, arm, k, {"outcome": "failed", "failure": {"code": code}}, "failed", code)


def test_an_incidents_left_out_row_gives_its_incident_as_the_reason():
    w = seed_world()
    make_incident(w, "t00", "direct", 2)
    assert [row["why"] for row in seed_report(w)["left_out"]] == ["provider: error"]


def test_a_contaminated_run_leaves_the_denominators_and_is_listed():
    w = seed_world()
    path = unpool(w, "t00", "implement_check_repair", 0, {}, "excluded", "contaminated: fix hash")
    result = seed_report(w)
    arm = result["arms"]["implement_check_repair"]
    assert (arm["runs"], arm["completed"], result["left_out"]) == (47, 1.0, [
        {"run": path, "task": "t00", "arm": "implement_check_repair", "why": "contaminated: fix hash"}])


def test_an_observed_failed_run_that_no_record_holds_is_refused():
    w = seed_world()
    path = make_failed(w, "t00", "direct", 0, "wall_clock_timeout")
    w["records"] = [r for r in w["records"] if r["run"] != path]
    with pytest.raises(SystemExit, match="no record holds"):
        seed_report(w)


def test_a_wall_clock_timeout_counts_as_a_cut():
    w = seed_world()
    make_failed(w, "t00", "implement_check_repair", 0, "wall_clock_timeout")
    assert seed_report(w)["arms"]["implement_check_repair"]["cut"]["runs"] == 1


def test_q_is_a_mean_over_tasks_of_per_task_means_not_over_runs():
    w = seed_world()
    make_incident(w, "t00", "implement_check_repair", 0)  # t00 keeps two runs, scored 8; the other tasks three at 5
    for r in w["records"]:
        if r["arm"] == "implement_check_repair" and r["task"] == "t00" and r["status"] == "rated":
            r["scores"][J] = 8
    assert seed_report(w)["arms"]["implement_check_repair"]["q"] == (8 + 15 * 5) / 16


def test_a_pool_never_summarized_is_lost_and_its_failed_runs_are_not_scored():
    w = seed_world()
    w["pools"] = [p for p in w["pools"] if p["task"] != "t15"]
    w["records"] = [r for r in w["records"] if r["task"] != "t15"]
    failed = "/w/t15/direct/run-0"
    w["runs"][failed] |= {"outcome": "failed", "failure": {"code": "provider_timeout"}}
    w["records"].append({"task": "t15", "pool": layout.SEED_POOL, "role": "candidate", "arm": "direct", "model": J,
                         "run": failed, "clone": None, "patch": None, "hidden": None, "scores": {}, "status": "failed",
                         "reason": None})
    result = seed_report(w)
    assert ("t15" in result["arms"]["direct"]["tasks"], result["missing_pools"]) == (False, {"t15": "not summarized"})


def test_the_hidden_pass_rate_leaves_out_the_runs_of_a_task_whose_pool_is_an_incident():
    w = seed_world()
    make_pool_incident(w, "t15")
    assert seed_report(w)["arms"]["direct"]["hidden"] == 60 / 90


def test_a_retry_run_that_did_not_complete_on_a_task_whose_pool_is_an_incident_fails_parity():
    w = seed_world()
    make_pool_incident(w, "t00")  # retry runs on the first six tasks
    w["runs"]["/w/t00/retry_until_check/run-0"] |= {"outcome": "failed", "failure": {"code": "provider_timeout"}}
    parity = seed_report(w)["arms"]["retry_until_check"]["parity"]
    assert (parity["completes"], parity["passed"]) == (False, False)


def test_an_arm_at_exactly_three_times_directs_priced_cost_in_the_recorded_decimals_passes_rule_4():
    w = seed_world()
    for facts in w["runs"].values():
        if facts["arm"] in ("direct", "implement_check_repair"):
            facts["priced"] = {"usd": 0.010003 if facts["arm"] == "direct" else 0.030009, "missing": []}
    assert seed_report(w)["selection"]["arms"]["implement_check_repair"]["rules"]["4_cost"] is True


def test_a_run_left_out_as_an_incident_is_listed_and_not_scored():
    w = seed_world()
    path = make_incident(w, "t00", "direct", 2)  # its score would have been 6
    result = seed_report(w)
    assert ([row["run"] for row in result["left_out"]], result["arms"]["direct"]["tasks"]["t00"]) == ([path], 4.8)


def test_an_incident_leaves_the_completion_and_cost_denominators():
    w = seed_world()
    make_incident(w, "t00", "implement_check_repair", 0)
    arm = seed_report(w)["arms"]["implement_check_repair"]
    assert (arm["runs"], arm["completed"]) == (47, 1.0)


def pool_incident_with_failed_direct_runs():
    """A seed world whose t15 pool is an incident while three of t15's direct runs failed (unpooled records)."""
    w = seed_world()
    make_pool_incident(w, "t15")
    for k in range(3):
        failed = f"/w/t15/direct/run-{k}"
        w["runs"][failed] |= {"outcome": "failed", "failure": {"code": "provider_timeout"}}
        w["records"].append({"task": "t15", "pool": layout.SEED_POOL, "role": "candidate", "arm": "direct",
                             "model": J, "run": failed, "clone": None, "patch": None, "hidden": None, "scores": {},
                             "status": "failed", "reason": None})
    return w


def test_a_task_whose_pool_is_an_incident_has_no_score_even_for_its_failed_runs():
    assert "t15" not in seed_report(pool_incident_with_failed_direct_runs())["arms"]["direct"]["tasks"]


def test_a_task_whose_pool_is_an_incident_has_no_baseline():
    assert "t15" not in seed_report(pool_incident_with_failed_direct_runs())["baselines"]["tasks"]


def cut_world():
    """A seed world where implement-review-revise's first run on t00 is cut at the call limit on its second call,
    that call's usage missing and priced at a worst case of USD 1 (USD 1.25 in all), and its second run is cut by a
    usage limit (no observation)."""
    w = seed_world()
    w["runs"]["/w/t00/implement_review_revise/run-0"] |= {"outcome": "failed", "failure": {"code": "provider_timeout"},
                                                          "calls": 2, "priced": {"usd": 1.25, "missing": ["2"]}}
    w["runs"]["/w/t00/implement_review_revise/run-1"] |= {"cut": {"text": "limit"}, "calls": 1}
    return w


def test_a_call_limit_cut_is_in_the_cut_table_at_its_call_and_priced_apart():
    cut = seed_report(cut_world())["arms"]["implement_review_revise"]["cut"]
    assert (cut["runs"], cut["by_call"], cut["priced_usd"], cut["rate"]) == (1, {2: 1}, 1.25, 1 / 47)


def test_calls_count_a_call_limit_cut_and_leave_out_a_usage_limit_cut():
    arm = seed_report(cut_world())["arms"]["implement_review_revise"]
    assert (arm["runs"], arm["calls"]) == (47, (46 * 3 + 2) / 47)


def test_priced_cost_is_given_at_the_worst_case_bound_and_over_metered_runs_only():
    arm = seed_report(cut_world())["arms"]["implement_review_revise"]
    assert (arm["priced_worst"], arm["priced_metered"], arm["priced_metered_runs"]) == ((46 * 0.75 + 1.25) / 47,
                                                                                         0.75, 46)


def test_a_call_limit_cut_counts_against_completion():
    assert seed_report(cut_world())["arms"]["implement_review_revise"]["completed"] == 46 / 47


def test_the_share_of_runs_with_a_nested_session_is_reported():
    w = seed_world()
    w["runs"]["/w/t00/implement_check_repair/run-0"]["nested_sessions"] = 1
    assert seed_report(w)["arms"]["implement_check_repair"]["nested"] == 1 / 48


def test_the_hidden_pass_rate_is_over_an_arms_scored_runs():
    w = seed_world()
    make_incident(w, "t00", "direct", 2)  # a hidden-passing run, now left out
    assert seed_report(w)["arms"]["direct"]["hidden"] == 63 / 95


@pytest.mark.parametrize("score, seed", [(5, True), (7, False)])
def test_retry_is_a_seed_only_when_its_parity_with_the_offline_figure_holds(score, seed):
    """Direct's offline Q3 is 5.2 at 7/6 calls; retry runs one call, a second on a quarter of its runs."""
    w = seed_world()
    retry = [path for path, facts in w["runs"].items() if facts["arm"] == "retry_until_check"]
    for k, path in enumerate(retry):
        w["runs"][path] |= {"calls": 2 if k % 4 == 0 else 1}
        next(r for r in w["records"] if r["run"] == path)["scores"][J] = score
    assert ("retry_until_check" in seed_report(w)["selection"]["seeds"]) == seed


def test_an_arms_summary_has_exactly_the_keys_the_selection_takes():
    arm = {"tasks": {}, "completed": 1, "calls": 1, "priced_worst": 1, "priced_metered": None, "nested": 0,
           "distinctive": None, "parity": None, "runs": 6, "cut": {}}
    assert set(seeds.summary(arm, PROGRAMS["direct"])) == {
        "tasks", "completed", "calls", "priced_worst", "priced_metered", "nested", "model", "effort", "distinctive",
        "parity", "lines"}


def test_the_visible_checks_rate_is_shown_beside_the_rerolls_fail_rate():
    w = seed_world()
    w["runs"]["/w/t00/direct/run-1"]["visible"] = {"passed": None, "timed_out": "past its bound"}
    power = seed_report(w)["visible_power"]
    assert (power["failed"], power["checked"], power["visible_fail_rate"]) == (16, 95, (15 / 6 + 1 / 5) / 16)


def test_another_tranches_run_of_a_seed_task_is_not_read():
    w = seed_world()
    w["runs"]["/w/t00/direct/calibration-run"] = {"tranche": "calibration", "task": "t00", "arm": "direct",
                                                  "outcome": "completed", "calls": 1}
    assert list(seed_report(w)["measure_free"]) == [f"{layout.SEED_EVALUATION}/{name}" for name in ARMS]


def test_judge_calls_and_their_priced_cost_are_reported_apart():
    result = seed_report(seed_world())
    assert (result["judge_cost"], result["arms"]["direct"]["priced_worst"]) == (
        {"units": 16, "calls": 32, "priced_usd": 8.0, "missing_usage": 0}, 0.25)


CHECK_ARMS = ("retry_until_check", "implement_check_repair")  # what the checkpoint withholds without selecting power


def without(w, arms):
    """`w` with no run and no record of `arms`, as when they never started."""
    w["runs"] = {p: f for p, f in w["runs"].items() if f["arm"] not in arms}
    w["records"] = [r for r in w["records"] if r["arm"] not in arms]
    return w


def test_with_the_check_arms_withheld_and_implement_review_revise_run_the_report_is_made():
    result = seed_report(without(seed_world(), CHECK_ARMS), withheld=CHECK_ARMS)
    assert (result["withheld"], result["selection"]["seeds"]) == (list(CHECK_ARMS),
                                                                  ["direct", "implement_review_revise"])


def test_a_report_before_the_workflow_arms_have_run_is_refused_naming_them():
    w = without(seed_world(), ARMS[1:])
    with pytest.raises(SystemExit, match="implement_review_revise"):
        seed_report(w, withheld=CHECK_ARMS)


def test_an_observed_run_without_its_settled_facts_is_refused():
    w = seed_world()
    del w["runs"]["/w/t00/direct/run-0"]["nested_sessions"]
    with pytest.raises(SystemExit, match="nested_sessions"):
        seed_report(w)


def test_an_arm_exactly_on_rule_2s_line_is_named_extension_eligible():
    w = seed_world()
    for r in w["records"]:
        if r["arm"] == "implement_check_repair" and r["task"] in w["tasks"][:8]:
            r["scores"][J] = 4  # its mean 4.5, direct's 5 less half a point
    assert seed_report(w)["extension_eligible"] == ["implement_check_repair"]


def test_metered_tokens_sum_the_providers_that_made_calls_and_none_when_unavailable():
    receipt = {"consumption": {"claude": {"calls": 2, "tokens": 300}, "codex": {"calls": 0, "tokens": "unavailable"}}}
    assert (seeds.metered_tokens(receipt), seeds.metered_tokens({"consumption": metering.UNAVAILABLE})) == (300, None)


@pytest.mark.parametrize("edit", [lambda w: None, lambda w: weaken_controls(w, 4),
                                  lambda w: anchor_record(w, "t00", "base", 0).update(patch="x")])
def test_the_seed_section_renders_on_every_branch_with_its_decision(edit):
    w = seed_world()
    edit(w)
    result = seed_report(w)
    assert f"Decision: {result['decision']}." in seeds.markdown(result)


# --- the seed task list, pool kind and judge criterion (B1) ------------------------------------------------

SURVIVORS = [f"t{i:02d}" for i in (3, 1, 7, 0, 2, 5, 4, 6)]  # in the chosen list's order


def calibrated(tmp_path, decision="qualified"):
    """A fabricated study whose results hold a calibration.json with `decision`, the survivors and the judge."""
    s = fabricated_study(tmp_path, [])
    s.results.mkdir()
    dump(s.results / "calibration.json", {"calibration": {"decision": decision, "selected": J, "insensitive": None,
                                                          "v4_note": "v4", "survivors": SURVIVORS}})
    return s


def test_seed_tasks_writes_the_survivors_in_order_with_the_judge_and_records_both_hashes(tmp_path):
    s = calibrated(tmp_path)
    row = study.write_seed_tasks(s)
    path = s.results / layout.SEED_TASKS
    assert (load(path), row["event"], row["tasks_sha256"], row["calibration_sha256"]) == (
        {"tasks": SURVIVORS, "judge": J, "insensitive": None, "v4_note": "v4"}, "seed_tasks",
        sha256_file(path), sha256_file(s.results / "calibration.json"))


@pytest.mark.parametrize("decision", ["stop: G4 failed", None])
def test_seed_tasks_refuses_a_calibration_that_did_not_qualify(tmp_path, decision):
    s = calibrated(tmp_path, decision)
    with pytest.raises(SystemExit, match="not qualified"):
        study.write_seed_tasks(s)
    assert (s.results / layout.SEED_TASKS).exists() is False


def test_seed_tasks_refuses_a_calibration_without_a_decision(tmp_path):  # an anchor failure leaves no calibration
    s = calibrated(tmp_path)
    dump(s.results / "calibration.json", {"calibration": None})
    with pytest.raises(SystemExit, match="not qualified"):
        study.write_seed_tasks(s)


@pytest.mark.parametrize("left", ["file and event", "event", "file"])
def test_seed_tasks_is_written_once(tmp_path, left):
    s = calibrated(tmp_path)
    study.write_seed_tasks(s)
    if left == "event":
        (s.results / layout.SEED_TASKS).unlink()
    if left == "file":
        s.ledger.unlink()
    with pytest.raises(SystemExit, match="written once"):
        study.write_seed_tasks(s)


def test_the_seed_evaluations_tasks_are_the_seed_task_list_and_none_before_it(tmp_path):
    s = calibrated(tmp_path)
    before = layout.tranche_tasks(s, layout.SEED_EVALUATION)
    study.write_seed_tasks(s)
    assert (before, layout.tranche_tasks(s, layout.SEED_EVALUATION)) == ([], SURVIVORS)


def test_retry_runs_on_the_first_six_survivors_and_every_other_arm_on_all(tmp_path):
    s = calibrated(tmp_path)
    study.write_seed_tasks(s)
    assert {arm: layout.arm_tasks(s, layout.SEED_EVALUATION, arm) for arm in ARMS} == {
        "direct": SURVIVORS, "retry_until_check": SURVIVORS[:6], "implement_check_repair": SURVIVORS,
        "implement_review_revise": SURVIVORS}


@pytest.mark.parametrize("command", [["pool", "--tranche", layout.SEED_EVALUATION], ["judge", "--tranche",
                                     layout.SEED_EVALUATION], ["summarize"]])
def test_pool_judge_and_summarize_take_the_seed_kind(command):
    assert study.parser().parse_args([*command, "--kind", layout.SEED_POOL, "t00"]).kind == layout.SEED_POOL


def test_a_retry_start_beyond_the_first_six_survivors_is_refused(tmp_path):
    s = calibrated(tmp_path)
    study.write_seed_tasks(s)
    with pytest.raises(SystemExit, match="takes tasks among"):
        layout.require_tasks(s, layout.SEED_EVALUATION, [SURVIVORS[6]], arm="retry_until_check")


@pytest.mark.parametrize("tranche, kind", [(layout.SEED_EVALUATION, "first"), (layout.SEED_EVALUATION, "retest"),
                                           (layout.SEED_EVALUATION, layout.LUNA_POOL), ("calibration", layout.SEED_POOL),
                                           ("smoke", layout.SEED_POOL), (layout.LUNA_SMOKE, layout.SEED_POOL)])
def test_a_pool_kind_the_tranche_does_not_build_is_refused(tranche, kind):
    with pytest.raises(SystemExit, match="pools, not"):
        layout.require_pool_kind(tranche, kind)


def test_the_seed_evaluation_builds_seed_pools():
    assert layout.require_pool_kind(layout.SEED_EVALUATION, layout.SEED_POOL) is None


GOOD = {"judges": [J], "rubric": layout.RUBRIC, "primary": [], "secondary": []}  # judge-seeds.json as frozen


def seed_criterion(tmp_path, value):
    """A study with its seed task list (judge `J`) and `value` as its judge-seeds.json."""
    s = calibrated(tmp_path)
    study.write_seed_tasks(s)
    dump(s.seed_criterion, value)
    return s


def test_a_seed_pool_is_built_and_summarized_under_judge_seeds_json(tmp_path):
    s = seed_criterion(tmp_path, GOOD)
    assert (layout.pool_criterion(s, layout.SEED_POOL), s.seed_criterion.name) == (s.seed_criterion,
                                                                                   "judge-seeds.json")


@pytest.mark.parametrize("change", [{"judges": [gates.HAIKU, gates.SONNET]}, {"judges": [gates.SONNET]},
                                    {"judges": []}, {"calibration": {"margin": 1}}, {"purpose": "calibration"},
                                    {"rubric": {"workflow": "score.orc"}}])
def test_a_seed_judge_criterion_other_than_the_selected_judge_alone_and_the_functional_rubric_is_refused(
        tmp_path, change):
    s = seed_criterion(tmp_path, GOOD | change)
    with pytest.raises(SystemExit, match="names one judge, the selected"):
        layout.pool_criterion(s, layout.SEED_POOL)


def test_the_seed_judge_criterion_is_refused_before_the_seed_task_list(tmp_path):
    s = fabricated_study(tmp_path, [])
    dump(s.seed_criterion, GOOD)
    with pytest.raises(SystemExit, match="seed-tasks"):
        layout.pool_criterion(s, layout.SEED_POOL)


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    """A study whose runtime is a git checkout holding the programs, the rubric and a task list, with the criterion
    files and `judge-seeds.json` written into the runtime after its commit (as on the machine) and criterion.json
    naming the seed judge criterion's sha256; frozen."""
    runtime = tmp_path / "runtime"
    tasks = committed_runtime(runtime, [{"id": "t1", "set": "smoke", "commit": "f" * 40, "tier": "T3",
                                         "form": "in-tree"}])
    monkeypatch.setattr(rules, "loaded_elsewhere", lambda runtime: [])  # the tests import this checkout's modules
    seed_set = runtime / "experiments" / "seed_set"
    s = layout.Study(runtime, tmp_path / "work", tmp_path / "pools", seed_set / "results", tasks,
                     seed_set / "judge-calibration.json", tmp_path / "state")
    dump(s.criterion, {"judges": [gates.HAIKU, gates.SONNET], "rubric": layout.RUBRIC})
    dump(s.seed_criterion, GOOD)
    write_frozen_criterion(s, sha256=rules.required_hashes(s) | {"judge-seeds.json": sha256_file(s.seed_criterion)})
    rules.record_freeze(s)
    return s


def test_a_named_seed_judge_criterion_written_into_the_runtime_freezes_and_lets_a_start_pass(frozen):
    assert rules.require_order(frozen, "smoke") is None


def test_an_edit_to_the_seed_judge_criterion_after_the_freeze_refuses_the_next_start(frozen):
    dump(frozen.seed_criterion, GOOD | {"primary": ["edited"]})
    with pytest.raises(SystemExit, match=r"does not name the current sha256 of \['judge-seeds.json'\]"):
        rules.require_order(frozen, "smoke")


def test_a_named_seed_judge_criterion_that_is_missing_refuses_the_next_start(frozen):
    frozen.seed_criterion.unlink()
    with pytest.raises(SystemExit, match=r"does not name the current sha256 of \['judge-seeds.json'\]"):
        rules.require_order(frozen, "smoke")


def test_a_criterion_that_does_not_name_the_seed_judge_criterion_does_not_bind_it(frozen):
    named = load(frozen.frozen)["sha256"]
    named.pop("judge-seeds.json")
    write_frozen_criterion(frozen, sha256=named)
    rules.record_freeze(frozen)
    dump(frozen.seed_criterion, GOOD | {"primary": ["edited"]})
    assert rules.require_order(frozen, "smoke") is None
