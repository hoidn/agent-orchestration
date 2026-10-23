from tests.experiments.qualification_support import qualified
"""Structural search scoring: the blind pool of evaluations, the join of summarize's runs to evaluation records,
and the Phase 1 readout (Phase 2: test_orc_structural_search_scoring_phase2.py). Synthetic logs, memos, scoring
runs and results.json; no provider is called."""

import json
from pathlib import Path

import pytest

from experiments.compare import pool as pooling, prepare, summarize
from experiments.compare.repos import sha256_file
from experiments.orc_structural_search.records import UNAVAILABLE, append_record
from experiments.orc_structural_search.scoring import (
    contaminated_children, join_scores, log_only_pool, main, phase1_readout, pool_evaluations, read_pool,
    split_batches,
)
from tests.experiments.compare_harness_support import (  # noqa: F401 (world is a fixture)
    REPO, call, edit, skip_without_sandbox, world, write_memo,
)

CRITERION = REPO / "experiments" / "orc_structural_search" / "criteria" / "phase1.json"
TOKENS = {"upstream": ("S2",) * 4, "symptom": ("S0",) * 4}  # anchors; every evaluation is rated S1


def log_row(records_dir, *, eid, task="task", outcome="completed", mode="catalog", seed="direct", replicate=1):
    row = {"kind": "evaluation", "mode": mode, "evaluation_id": eid, "candidate_id": f"sha256:{eid}",
           "records_dir": str(records_dir), "task_id": task, "replicate": replicate, "outcome": outcome,
           "criterion_sha256": sha256_file(CRITERION)}
    return row | ({"seed": seed} if mode == "catalog" else {})


def evaluation(world, eid, body):
    """One evaluation arm (named by its id) with one call through the shim that edits the clone, its memo,
    and its scan, as the driver leaves it (not yet collected)."""
    root = world.outside / "archive" / eid
    root.mkdir(parents=True)
    spec = prepare.ArmSpec(source=root / "main.orc", entry="main::run", source_root=root,
                           providers=root / "providers.json", inputs=("task", "intent", "repo"),
                           state_dir=world.root / "runs" / eid)
    records = prepare.run_arm(world.task, eid, world.root, world.runtime, spec=spec)
    record = json.loads((records / "record.json").read_text())
    script = edit("$PWD", body)
    assert call(world, record, script).returncode == 0
    write_memo(record, [script], {"variant": "DONE"})
    prepare.scan(records, world.solution)
    return records


@pytest.fixture
def evaluations(world):
    skip_without_sandbox()
    log = world.outside / "evidence" / "log.jsonl"
    log.parent.mkdir(parents=True)
    runs = {"e1": evaluation(world, "e1", "a + b"), "e2": evaluation(world, "e2", "b + a")}
    q = qualified(world.tmp / 'quality', runtime=world.runtime, tasks=[world.task], judges=['judge-a', 'judge-b'],
                  providers={'judge-b': REPO / 'experiments/compare/providers/score_codex.json'})
    criterion = q.criterion
    for eid, records in runs.items():
        append_record(log, log_row(records, eid=eid, seed={"e1": "direct", "e2": "best_of_n"}[eid]) |
                      {"criterion_sha256": sha256_file(criterion)})
    append_record(log, log_row(world.root / "records" / "e3" / "run-1", eid="e3", outcome="incident") | {"criterion_sha256": sha256_file(criterion)})
    append_record(log, log_row(world.root / "records" / "e4" / "run-1", eid="e4", task="other") | {"criterion_sha256": sha256_file(criterion)})
    out = pool_evaluations(log.parent, world.task, out=world.outside / "pool", criterion=criterion,
                           judges=["judge-a", f"judge-b={REPO / 'experiments/compare/providers/score_codex.json'}"])
    return out, json.loads((out / "records" / "mapping.json").read_text()), runs, log, criterion


def test_pool_evaluations_pools_the_tasks_completed_evaluations_with_both_anchors_in_every_batch(evaluations):
    _, mapping, runs, _, _ = evaluations
    assert sorted((mapping["clones"][cid]["arm"], tuple(mapping["clones"][cid]["labels"]))
                  for batch in mapping["batches"] for cid in batch) == [
        ("anchor", ("symptom",)), ("anchor", ("upstream",)), ("e1", ("final",)), ("e2", ("final",))]


def test_split_batches_keeps_at_most_eight_per_batch_and_spreads_a_policys_replicates():
    finals = [(policy, k) for policy in "abcdefghi" for k in (1, 2)]
    batches = split_batches(finals, key=lambda final: final[0])
    assert ([len(b) for b in batches], [len({p for p, _ in b}) for b in batches],
            sorted(f for b in batches for f in b)) == ([6, 6, 6], [6, 6, 6], sorted(finals))


def score(out, mapping, judge, home):
    """A completed scoring run of `judge` where its --state-dir puts it, then the judge's scan."""
    inputs = json.loads((out / "records" / f"score-inputs-{judge}.json").read_text())
    value = [[dict(zip(summarize.CRITERIA, TOKENS.get(mapping["clones"][Path(p).name]["labels"][0], ("S1",) * 4)),
                   clone=p, reason="r") for p in batch["clones"]] for batch in inputs["batches"]]
    state = out / "judges" / mapping["judges"][judge]["dir"] / "state"
    (state / "r1").mkdir(parents=True)
    (state / "r1" / "run.json").write_text(json.dumps({"bound_inputs": inputs}))
    write_memo({"state_root": state}, [], value)
    native = mapping['judges'][judge].get('sandbox')
    pooling.scan_judge(out, judge, "f" * 40, home=Path(native['home']) if native else home)


def test_read_pool_joins_summarized_runs_to_their_evaluation_records(evaluations, world):
    out, mapping, runs, log, criterion = evaluations
    for judge in ("judge-a", "judge-b"):
        score(out, mapping, judge, world.tmp / "home")
    summarize.summarize(out, criterion)
    pool = read_pool(out / "records" / "results.json", log, criterion)
    assert (sorted((r["policy"], r["task"], r["replicate"], r["value"], r["calls"]) for r in pool["rows"]
                   if r["outcome"] == "completed"), pool["unpooled"]) == (
        [("best_of_n", "task", 1, 4, 1), ("direct", "task", 1, 4, 1)], [])


@pytest.fixture(autouse=True)
def qualified_readouts(request, tmp_path, monkeypatch):
    if 'read_pool' not in request.node.name and 'readout_cli_phase1' not in request.node.name:
        return
    from tests.experiments.readout_support import report_qualification
    template = CRITERION
    names = ['task'] if 'read_pool' in request.node.name else None
    q = report_qualification(tmp_path / 'readout-quality', template, names)
    monkeypatch.setattr(__import__(__name__, fromlist=['CRITERION']), 'CRITERION', q.criterion)
    monkeypatch.setattr(__import__(__name__, fromlist=['REPORT_Q']), 'REPORT_Q', q, raising=False)


def results_file(tmp_path, runs, sha="0" * 64):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"runs": runs, "criterion_sha256": sha, "anchors": [], "agreement": {},
                                "excluded_judges": {}}))
    if 'REPORT_Q' in globals():
        from tests.experiments.readout_support import report_pool
        report_pool(path, REPORT_Q, 'task')
    return path


def run_row(run, arm, value=5.0):
    return {"run": str(run), "arm": arm, "value": value, "hidden_value": 0.5, "calls": 2, "wall_clock_sec": 30.0}


def test_join_scores_reports_policy_identity_and_harness_values(tmp_path):
    log = tmp_path / "log.jsonl"
    append_record(log, log_row(tmp_path / "records" / "e9" / "run-1", eid="e9", mode="unguided", replicate=2))
    rows = join_scores(results_file(tmp_path, [run_row(tmp_path / "records" / "e9" / "run-1", "e9")]), log)
    assert rows == [{"evaluation_id": "e9", "candidate_id": "sha256:e9", "mode": "unguided",
                     "policy": "unguided:sha256:e9", "task": "task", "replicate": 2, "outcome": "completed",
                     "value": 5.0, "hidden": 0.5, "calls": 2, "wall_clock_sec": 30.0}]


def test_scoring_refuses_unmapped_clone(tmp_path):
    log = tmp_path / "log.jsonl"
    append_record(log, log_row(tmp_path / "records" / "e1" / "run-1", eid="e1"))
    results = results_file(tmp_path, [run_row(tmp_path / "records" / "e1" / "run-1", "e1"),
                                      run_row(tmp_path / "records" / "stray" / "run-1", "stray")])
    with pytest.raises(ValueError, match="stray/run-1 maps to no evaluation record"):
        join_scores(results, log)


def test_join_scores_refuses_a_run_whose_arm_is_not_its_evaluation_id(tmp_path):
    log = tmp_path / "log.jsonl"
    append_record(log, log_row(tmp_path / "records" / "e1" / "run-1", eid="e1"))
    with pytest.raises(ValueError, match="arm e2 .* evaluation e1"):
        join_scores(results_file(tmp_path, [run_row(tmp_path / "records" / "e1" / "run-1", "e2")]), log)


def test_read_pool_refuses_results_summarized_under_another_criterion(tmp_path):
    log = tmp_path / "log.jsonl"
    append_record(log, log_row(tmp_path / "records" / "e1" / "run-1", eid="e1"))
    results = results_file(tmp_path, [run_row(tmp_path / "records" / "e1" / "run-1", "e1")])
    with pytest.raises(ValueError, match="summarized under criterion sha256 0{64}, not"):
        read_pool(results, log, CRITERION)


def test_read_pool_lists_completed_evaluations_of_the_task_that_no_run_names(tmp_path):
    log = tmp_path / "log.jsonl"
    for eid, outcome in (("e1", "completed"), ("e2", "completed"), ("e3", "incident")):
        append_record(log, log_row(tmp_path / "records" / eid / "run-1", eid=eid, outcome=outcome))
    results = results_file(tmp_path, [run_row(tmp_path / "records" / "e1" / "run-1", "e1")],
                           sha=sha256_file(CRITERION))
    assert read_pool(results, log, CRITERION)["unpooled"] == ["e2"]


def test_read_pool_counts_a_failure_or_incident_logged_twice_once(tmp_path):
    log = tmp_path / "log.jsonl"
    for eid, outcome in (("e1", "completed"), ("e2", "failed"), ("e2", "failed"), ("e3", "incident"),
                         ("e3", "incident"), ("e4", "incident"), ("e4", "failed")):  # e4: an incident resumed
        append_record(log, log_row(tmp_path / "records" / eid / "run-1", eid=eid, outcome=outcome))
    results = results_file(tmp_path, [run_row(tmp_path / "records" / "e1" / "run-1", "e1")],
                           sha=sha256_file(CRITERION))
    rows = read_pool(results, log, CRITERION)["rows"]
    assert [(r["evaluation_id"], r["outcome"]) for r in rows] == [
        ("e1", "completed"), ("e2", "failed"), ("e3", "incident"), ("e4", "failed")]


KILLED = "launch 0: no terminal row in run r1 (launcher exit -9; see launch-0.log)"


def test_an_incident_killed_at_its_envelope_is_a_timeout_and_other_incidents_stay_incidents(tmp_path):
    log = tmp_path / "log.jsonl"
    for eid, incidents in (("e2", ["launch 0: no terminal row in run r2 (launcher exit 1; see l)", KILLED]),
                           ("e3", [KILLED, "launch 1: no terminal row in run r3 (launcher exit 1; see l)"])):
        append_record(log, log_row(tmp_path / "records" / eid / "run-1", eid=eid, outcome="incident")
                      | {"incidents": incidents})
    rows = log_only_pool(log, "task")["rows"]
    assert [(r["evaluation_id"], r["outcome"]) for r in rows] == [("e2", "timeout"), ("e3", "incident")]


def test_read_pool_takes_failed_and_incident_evaluations_of_the_task_from_the_log(tmp_path):
    log = tmp_path / "log.jsonl"
    for eid, outcome, task in (("e1", "completed", "task"), ("e2", "failed", "task"), ("e3", "incident", "task"),
                               ("e4", "failed", "other")):
        append_record(log, log_row(tmp_path / "records" / eid / "run-1", eid=eid, outcome=outcome, task=task)
                      | {"provider_calls": 3, "wall_clock_sec": 9.0})
    results = results_file(tmp_path, [run_row(tmp_path / "records" / "e1" / "run-1", "e1")],
                           sha=sha256_file(CRITERION))
    rows = read_pool(results, log, CRITERION)["rows"]
    assert [(r["evaluation_id"], r["outcome"], r["value"], r["calls"]) for r in rows] == [
        ("e1", "completed", 5.0, 2), ("e2", "failed", None, 3), ("e3", "incident", None, 3)]


CRIT = json.loads(CRITERION.read_text()) | {  # the frozen rules with two synthetic tasks
    "tasks": ["tasks/t1", "tasks/t2"], "anchors": {t: {"upstream": "up", "stub": "stub"} for t in ("t1", "t2")}}
TRUSTED = [{"batch": 0, "judge": "j", "anchor": "up", "total": 8},
           {"batch": 0, "judge": "j", "anchor": "stub", "total": 1}]
DIVERSE = {"episodes": {"accepted": 4}, "distinct_skeletons": 3, "revisit_rate": 0.25, "terminal_only_share": 0.25,
           "allocation_distinct": 0, "collapsed": False, "catalog": {}}
WIDE = {"direct": [4, 5], "best_of_n": [7, 8], "plan_then_implement": [5, 6]}  # pooled SD 0.71, gap 3


FAILED, INCIDENT = "failed", "incident"  # in a pool_of value list: an evaluation with that outcome
OUTCOMES = (FAILED, INCIDENT, "timeout")


def pool_of(task, values, *, children=None, anchors=TRUSTED):
    """A read_pool result: `values` maps catalog policy -> its replicate values, `children` child -> its values;
    a value of FAILED or INCIDENT is an evaluation with that outcome (no value)."""
    rows = [{"evaluation_id": f"{policy}-{k}", "candidate_id": f"sha256:{policy}", "mode": mode, "policy": policy,
             "task": task, "replicate": k + 1, "outcome": v if v in OUTCOMES else "completed",
             "value": None if v in OUTCOMES else v, "hidden": None, "calls": 1, "wall_clock_sec": 10.0}
            for mode, group in (("catalog", values), ("unguided", children or {}))
            for policy, vs in group.items() for k, v in enumerate(vs)]
    return {"task": task, "rows": rows, "anchors": anchors, "agreement": {}, "excluded_judges": {}, "unpooled": [],
            "no_pool": False}


def readout(t1, t2=None, driver=DIVERSE, **pool):
    return phase1_readout([pool_of("t1", t1, **pool), pool_of("t2", t2 or t1)], driver, CRIT)


def test_phase1_readout_within_tolerance_is_not_separated():
    close = {"direct": [4, 6], "best_of_n": [5, 7]}  # pooled SD sqrt(2), gap 1 < 2 * sqrt(2)
    result = readout(close)
    assert (result["tasks"]["t1"]["separated"], result["phase2_selected"], result["rule"]) == (
        False, False, "within_tolerance")


def test_phase1_readout_tolerance_never_falls_below_half_a_rubric_point():
    flat = {"direct": [4, 4], "best_of_n": [4.4, 4.4]}  # pooled SD 0: 2 x SD would separate any gap
    task = readout(flat)["tasks"]["t1"]
    assert (task["threshold"], task["separated"]) == (0.5, False)


def test_phase1_readout_reports_mean_sd_and_direct_rank_per_task():
    task = readout(WIDE)["tasks"]["t1"]
    assert (task["policies"]["best_of_n"]["mean"], task["policies"]["best_of_n"]["sd"], task["pooled_sd"],
            task["direct_rank"]) == (7.5, pytest.approx(0.7071, abs=1e-4), pytest.approx(0.7071, abs=1e-4), 3)


def test_phase1_readout_selects_phase2_when_both_tasks_separate_without_a_direct_winner():
    result = readout(WIDE)
    assert (result["phase2_selected"], result["rule"]) == (True, "separated")


def test_phase1_readout_does_not_select_phase2_when_direct_is_the_sole_winner():
    result = readout({"direct": [8, 8], "best_of_n": [3, 4]})
    assert (result["tasks"]["t1"]["direct_rank"], result["phase2_selected"], result["rule"]) == (
        1, False, "direct_sole_winner")


def test_phase1_readout_does_not_select_phase2_when_unguided_i1_collapsed():
    result = readout(WIDE, driver=DIVERSE | {"terminal_only_share": 0.8})
    assert (result["unguided"]["collapsed"], result["phase2_selected"], result["rule"]) == (True, False, "collapsed")


def test_phase1_readout_does_not_select_phase2_without_a_collapse_figure():
    result = readout(WIDE, driver=DIVERSE | {"terminal_only_share": UNAVAILABLE})
    assert (result["phase2_selected"], result["rule"]) == (False, "collapse_unavailable")


def test_phase1_readout_leaves_out_unvalued_runs_and_has_no_sd_for_a_single_value():
    task = readout({"direct": [4, None], "best_of_n": [6]})["tasks"]["t1"]
    assert (task["policies"]["direct"]["runs"], task["policies"]["direct"]["sd"], task["pooled_sd"],
            task["separated"]) == (1, UNAVAILABLE, UNAVAILABLE, False)


def test_phase1_readout_primary_mean_counts_a_failed_evaluation_as_zero():
    stats = readout({"direct": [4, 5], "best_of_n": [6, FAILED]})["tasks"]["t1"]["policies"]["best_of_n"]
    assert stats["mean"] == 3


def test_phase1_readout_valued_mean_leaves_out_a_failed_evaluation():
    stats = readout({"direct": [4, 5], "best_of_n": [6, FAILED]})["tasks"]["t1"]["policies"]["best_of_n"]
    assert (stats["valued_mean"], stats["failed"], stats["failure_rate"]) == (6, 1, 0.5)


def test_phase1_readout_scores_a_timeout_as_a_zero_failure_and_counts_it_apart():
    stats = readout({"direct": [4, 5], "best_of_n": [6, "timeout", FAILED]})["tasks"]["t1"]["policies"]["best_of_n"]
    assert (stats["mean"], stats["failed"], stats["timeouts"], stats["incidents"]) == (2, 2, 1, 0)


def test_phase1_readout_excludes_and_counts_incidents_and_unvalued_completed_runs():
    stats = readout({"direct": [4, 5, INCIDENT, None], "best_of_n": [6, 7]})["tasks"]["t1"]["policies"]["direct"]
    assert (stats["runs"], stats["mean"], stats["incidents"], stats["excluded"]) == (2, 4.5, 1, 1)


def test_phase1_readout_separation_uses_failure_inclusive_values():
    task = readout({"direct": [4, 4], "best_of_n": [6, FAILED]})["tasks"]["t1"]  # best_of_n primary [6, 0]
    assert (task["compared"], task["pooled_sd"], task["max_gap"]) == (["best_of_n", "direct"], 3, 1)


def test_phase1_readout_pooled_unguided_arm_counts_a_childs_failure_as_zero():
    task = readout(WIDE, children={"unguided:c1": [8], "unguided:c2": [FAILED]})["tasks"]["t1"]
    assert (task["unguided"]["mean"], task["unguided"]["valued_mean"], "unguided" in task["compared"]) == (4, 8, True)


def test_phase1_readout_scores_a_task_whose_evaluations_all_failed_from_the_log_alone(tmp_path):
    log = tmp_path / "log.jsonl"
    for k, seed in enumerate(("direct", "direct", "best_of_n", "best_of_n")):
        append_record(log, log_row(tmp_path / "records" / f"e{k}", eid=f"e{k}", task="t2", outcome="failed",
                                   seed=seed, replicate=k % 2 + 1))
    result = phase1_readout([pool_of("t1", WIDE), log_only_pool(log, "t2")], DIVERSE, CRIT)
    task = result["tasks"]["t2"]
    assert (task["no_pool"], task["anchors_ok"], task["policies"]["direct"]["mean"], task["separated"],
            result["rule"]) == (True, UNAVAILABLE, 0, False, "within_tolerance")


def test_log_only_pool_accepts_a_task_whose_completed_evaluations_are_all_contaminated(tmp_path):
    log = tmp_path / "log.jsonl"
    for eid, outcome in (("e1", "completed"), ("e2", "failed")):
        records = tmp_path / "records" / eid / "run-1"
        records.mkdir(parents=True)
        (records / "record.json").write_text(json.dumps({"outcome": outcome, "calls": 1, "scan": {
            "calls": 1, "hits": [], "verdict": {"verdict": "contaminated", "reason": "solution seen"}}}))
        append_record(log, log_row(records, eid=eid, outcome=outcome))
    stats = phase1_readout([pool_of("t1", WIDE), log_only_pool(log, "task") | {"task": "t2"}], DIVERSE,
                           CRIT)["tasks"]["t2"]["policies"]["direct"]
    assert (stats["runs"], stats["excluded"], stats["failed"], stats["mean"]) == (1, 1, 1, 0)


def test_log_only_pool_refuses_a_task_with_an_uncontaminated_completed_evaluation(tmp_path):
    log = tmp_path / "log.jsonl"
    records = tmp_path / "records" / "e1" / "run-1"
    records.mkdir(parents=True)
    (records / "record.json").write_text(json.dumps({"outcome": "completed", "calls": 1,
                                                     "scan": {"calls": 1, "hits": [], "verdict": None}}))
    append_record(log, log_row(records, eid="e1"))
    with pytest.raises(ValueError, match="pass its pool's results.json"):
        log_only_pool(log, "task")


def test_phase1_readout_singleton_child_outlier_does_not_separate_a_null_catalog():
    null = {"direct": [4, 4.5], "best_of_n": [4.5, 4], "plan_then_implement": [4, 4.5]}
    task = readout(null, children={"unguided:c1": [8]})["tasks"]["t1"]
    assert (task["compared"], task["children"]["unguided:c1"]["mean"], task["unguided"]["runs"], task["separated"]) == (
        ["best_of_n", "direct", "plan_then_implement"], 8, 1, False)


def test_phase1_readout_refuses_phase2_when_a_pools_anchors_are_inverted():
    inverted = [{"batch": 0, "judge": "j", "anchor": "up", "total": 1},
                {"batch": 0, "judge": "j", "anchor": "stub", "total": 5}]
    result = readout(WIDE, anchors=inverted)
    assert (result["tasks"]["t1"]["anchors_ok"], result["phase2_selected"], result["rule"]) == (
        False, False, "anchors_inverted")


def test_phase1_readout_an_anchor_spread_above_the_limit_cannot_separate_its_task():
    drifting = TRUSTED + [{"batch": 1, "judge": "j", "anchor": "up", "total": 5},
                          {"batch": 1, "judge": "j", "anchor": "stub", "total": 1}]
    task = readout(WIDE, anchors=drifting)["tasks"]["t1"]
    assert (task["anchor_spread"], task["gap_separated"], task["separated"]) == ({"j": 3}, True, False)


def test_phase1_readout_refuses_pools_that_are_not_one_per_criterion_task():
    with pytest.raises(ValueError, match="one pool per criterion task"):
        phase1_readout([pool_of("t1", WIDE)], DIVERSE, CRIT)


def test_phase1_criterion_is_frozen_for_both_packages_with_their_anchors_and_judges():
    criterion = json.loads(CRITERION.read_text())
    packages = [REPO / task for task in criterion["tasks"]]
    expected_roles = [{"upstream": f"{p.name}-upstream", "stub": f"{p.name}-stub"} for p in packages]
    expected_package_anchors = [sorted([*roles.values(), f"{p.name}-partial", f"{p.name}-mutant"])
                                for p, roles in zip(packages, expected_roles)]
    assert sha256_file(CRITERION) == "84ee6307ab39e74710154654133585e53aaa9b329e5c7f9918dc9ee2f055cc80"
    assert ([(p / "base_commit").read_text().strip() for p in packages],
            [criterion["anchors"][p.name] for p in packages],
            criterion["judges"], criterion["primary"], criterion["written_before_scoring"]) == (
        [criterion["base_commits"][p.name] for p in packages],
        expected_roles, ["claude-opus-5-5", "gpt-6-sol"], [], True)
    assert [sorted(a.stem for a in (p / "anchors").glob("*.diff")) for p in packages] == expected_package_anchors


# CLI: the live Phase 1 readout passes one --log.
def test_readout_cli_phase1_takes_one_log_and_each_tasks_results(tmp_path, capsys):
    criterion, log, results = json.loads(CRITERION.read_text()), tmp_path / "log.jsonl", []
    for task in (Path(t).name for t in criterion["tasks"]):
        roles = criterion["anchors"][task]
        runs = []
        for policy, values in WIDE.items():
            for k, value in enumerate(values):
                records = tmp_path / "records" / f"{task}-{policy}-{k}" / "run-1"
                append_record(log, log_row(records, eid=f"{task}-{policy}-{k}", task=task, seed=policy,
                                           replicate=k + 1))
                runs.append(run_row(records, f"{task}-{policy}-{k}", value))
        path = tmp_path / task / "results.json"
        path.parent.mkdir()
        path.write_text(json.dumps({"runs": runs, "criterion_sha256": sha256_file(CRITERION), "agreement": {},
                                    "excluded_judges": {}, "anchors": [
                                        {"batch": 0, "judge": "j", "anchor": roles["upstream"], "total": 8},
                                        {"batch": 0, "judge": "j", "anchor": roles["stub"], "total": 1}]}))
        results.append(str(path))
    (tmp_path / "readout.json").write_text(json.dumps(DIVERSE))
    from tests.experiments.readout_support import report_pool
    for result_path in results:
        report_pool(Path(result_path), REPORT_Q, Path(result_path).parent.name)
    main(["readout", "--log", str(log), "--driver-readout", str(tmp_path / "readout.json"), "--criterion",
          str(CRITERION), "--joined-out", str(tmp_path / "joined.json"), *results])
    result = json.loads(capsys.readouterr().out)
    assert (result["rule"], result["phase2_selected"]) == ("separated", True)


def test_readout_cli_phase1_writes_every_tasks_rows_with_their_outcomes_for_phase2(tmp_path, capsys):
    criterion, log, results = json.loads(CRITERION.read_text()), tmp_path / "log.jsonl", []
    pooled, failing = (Path(t).name for t in criterion["tasks"])
    roles = criterion["anchors"][pooled]
    records = tmp_path / "records" / "p" / "run-1"
    append_record(log, log_row(records, eid="p", task=pooled))
    append_record(log, log_row(tmp_path / "records" / "f", eid="f", task=failing, outcome="failed"))
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"runs": [run_row(records, "p")], "criterion_sha256": sha256_file(CRITERION),
                                "agreement": {}, "excluded_judges": {}, "anchors": [
                                    {"batch": 0, "judge": "j", "anchor": roles["upstream"], "total": 8},
                                    {"batch": 0, "judge": "j", "anchor": roles["stub"], "total": 1}]}))
    (tmp_path / "readout.json").write_text(json.dumps(DIVERSE))
    from tests.experiments.readout_support import report_pool
    report_pool(path, REPORT_Q, pooled)
    main(["readout", "--log", str(log), "--driver-readout", str(tmp_path / "readout.json"), "--criterion",
          str(CRITERION), "--joined-out", str(tmp_path / "joined.json"), str(path)])
    joined = json.loads((tmp_path / "joined.json").read_text())
    assert [(r["evaluation_id"], r["task"], r["outcome"]) for r in joined] == [
        ("p", pooled, "completed"), ("f", failing, "failed")]


def test_readout_cli_phase1_writes_no_joined_rows_when_the_readout_fails(tmp_path):
    criterion, log = json.loads(CRITERION.read_text()), tmp_path / "log.jsonl"
    for task in (Path(t).name for t in criterion["tasks"]):
        append_record(log, log_row(tmp_path / "records" / task, eid=task, task=task, outcome="failed"))
    (tmp_path / "readout.json").write_text(json.dumps({}))  # no diversity figures: phase1_readout raises
    with pytest.raises(ValueError, match="scoring pool provenance"):
        main(["readout", "--log", str(log), "--driver-readout", str(tmp_path / "readout.json"), "--criterion",
              str(CRITERION), "--joined-out", str(tmp_path / "joined.json")])
    assert not (tmp_path / "joined.json").exists()


def episode(log, name, verdict, *, hits=1, outcome="accepted", skeleton="parent"):
    """An unguided episode row whose child is sha256:<name> (its skeleton `skeleton`, the parent's `parent`, one
    provider allocation), and its scan record under E/episodes/."""
    records = log.parent / "episodes" / name
    records.mkdir(parents=True)
    (records / "record.json").write_text(json.dumps({"scan": {
        "calls": 1, "hits": [{"pattern": "synthetic"}] * hits, "verdict": verdict and {"verdict": verdict, "reason": "r"}}}))
    append_record(log, {"kind": "episode", "episode_id": name, "outcome": outcome, "candidate_id": f"sha256:{name}",
                        "scan_pending": bool(hits), "provider_calls": 1, "skeleton": skeleton, "parent_skeleton": "parent",
                        "provider_allocation": "a", "parent_provider_allocation": "a"})


def test_contaminated_children_are_the_children_of_episodes_with_a_contaminated_verdict(tmp_path):
    log = tmp_path / "log.jsonl"
    for name, verdict, hits in (("c1", "contaminated", 2), ("c2", "cleared", 1), ("c3", None, 0)):
        episode(log, name, verdict, hits=hits)
    assert contaminated_children(log) == {"sha256:c1"}


def test_contaminated_children_leaves_a_contaminated_episode_that_was_not_accepted(tmp_path):
    log = tmp_path / "log.jsonl"
    episode(log, "c1", "contaminated", outcome="incident")
    assert contaminated_children(log) == set()


def test_contaminated_children_refuses_an_episode_with_hits_and_no_verdict(tmp_path):
    log = tmp_path / "log.jsonl"
    episode(log, "c1", None)
    with pytest.raises(ValueError, match="no verdict"):
        contaminated_children(log)


def phase1_with_a_contaminated_child(tmp_path):
    """A readout whose pooled task has a catalog run `p` and a failed run of the contaminated episode c's
    terminal-only child, a clean episode k with another skeleton, and a failed catalog run on the other task; the
    readout goes to stdout, the joined rows to <tmp_path>/joined.json."""
    criterion, log = json.loads(CRITERION.read_text()), tmp_path / "log.jsonl"
    pooled, failing = (Path(t).name for t in criterion["tasks"])
    roles = criterion["anchors"][pooled]
    records = tmp_path / "records" / "p" / "run-1"
    append_record(log, log_row(records, eid="p", task=pooled))
    episode(log, "c", "contaminated")
    episode(log, "k", None, hits=0, skeleton="other")
    append_record(log, log_row(tmp_path / "records" / "c", eid="c", task=pooled, outcome="failed", mode="unguided"))
    append_record(log, log_row(tmp_path / "records" / "f", eid="f", task=failing, outcome="failed"))
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"runs": [run_row(records, "p")], "criterion_sha256": sha256_file(CRITERION),
                                "agreement": {}, "excluded_judges": {}, "anchors": [
                                    {"batch": 0, "judge": "j", "anchor": roles["upstream"], "total": 8},
                                    {"batch": 0, "judge": "j", "anchor": roles["stub"], "total": 1}]}))
    (tmp_path / "readout.json").write_text(json.dumps(DIVERSE))
    from tests.experiments.readout_support import report_pool
    report_pool(path, REPORT_Q, pooled)
    main(["readout", "--log", str(log), "--driver-readout", str(tmp_path / "readout.json"), "--criterion",
          str(CRITERION), "--joined-out", str(tmp_path / "joined.json"), str(path)])


def test_readout_cli_phase1_leaves_out_every_row_of_a_contaminated_episodes_child(tmp_path, capsys):
    phase1_with_a_contaminated_child(tmp_path)
    assert [r["evaluation_id"] for r in json.loads((tmp_path / "joined.json").read_text())] == ["p", "f"]


def test_readout_cli_phase1_lists_the_excluded_children(tmp_path, capsys):
    phase1_with_a_contaminated_child(tmp_path)
    assert json.loads(capsys.readouterr().out)["excluded_children"] == ["sha256:c"]


def test_readout_cli_phase1_recomputes_diversity_without_the_excluded_children(tmp_path, capsys):
    phase1_with_a_contaminated_child(tmp_path)
    assert json.loads(capsys.readouterr().out)["unguided"]["terminal_only_share"] == 0.0
