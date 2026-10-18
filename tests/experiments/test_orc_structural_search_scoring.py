"""Structural search scoring: the blind pool of evaluations, the join of summarize's runs to evaluation records,
and the Phase 1 readout. Synthetic logs, memos, scoring runs and results.json; no provider is called."""

import json
from pathlib import Path

import pytest

from experiments.compare import pool as pooling, prepare, summarize
from experiments.orc_structural_search.records import UNAVAILABLE, append_record
from experiments.orc_structural_search.scoring import join_scores, phase1_readout, pool_evaluations
from tests.experiments.compare_harness_support import (  # noqa: F401 (world is a fixture)
    REPO, call, edit, skip_without_sandbox, world, write_memo,
)

CRITERION = REPO / "experiments" / "orc_structural_search" / "criteria" / "phase1.json"
TOKENS = {"upstream": ("S2",) * 4, "symptom": ("S0",) * 4}  # anchors; every evaluation is rated S1


def log_row(records_dir, *, eid, task="task", outcome="completed", mode="catalog", seed="direct", replicate=1):
    row = {"kind": "evaluation", "mode": mode, "evaluation_id": eid, "candidate_id": f"sha256:{eid}",
           "records_dir": str(records_dir), "task_id": task, "replicate": replicate, "outcome": outcome}
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
    prepare.scan(records, world.solution, home=world.tmp / "home")
    return records


@pytest.fixture
def evaluations(world):
    skip_without_sandbox()
    log = world.outside / "evidence" / "log.jsonl"
    log.parent.mkdir(parents=True)
    runs = {"e1": evaluation(world, "e1", "a + b"), "e2": evaluation(world, "e2", "b + a")}
    for eid, records in runs.items():
        append_record(log, log_row(records, eid=eid, seed={"e1": "direct", "e2": "best_of_n"}[eid]))
    append_record(log, log_row(world.root / "records" / "e3" / "run-1", eid="e3", outcome="incident"))
    append_record(log, log_row(world.root / "records" / "e4" / "run-1", eid="e4", task="other"))
    criterion = world.tmp / "criterion.json"
    criterion.write_text(json.dumps({"judges": ["judge-a", "judge-b"], "primary": [], "secondary": []}))
    out = pool_evaluations(log.parent, world.task, out=world.outside / "pool", criterion=criterion,
                           judges=["judge-a", f"judge-b={REPO / 'experiments/compare/providers/score_codex.json'}"])
    return out, json.loads((out / "records" / "mapping.json").read_text()), runs, log, criterion


def test_pool_evaluations_pools_the_tasks_completed_evaluations_in_one_batch_with_both_anchors(evaluations):
    _, mapping, runs, _, _ = evaluations
    assert sorted((mapping["clones"][cid]["arm"], tuple(mapping["clones"][cid]["labels"]))
                  for batch in mapping["batches"] for cid in batch) == [
        ("anchor", ("symptom",)), ("anchor", ("upstream",)), ("e1", ("final",)), ("e2", ("final",))]


def score(out, mapping, judge, home):
    """A completed scoring run of `judge` where its --state-dir puts it, then the judge's scan."""
    inputs = json.loads((out / "records" / f"score-inputs-{judge}.json").read_text())
    value = [[dict(zip(summarize.CRITERIA, TOKENS.get(mapping["clones"][Path(p).name]["labels"][0], ("S1",) * 4)),
                   clone=p, reason="r") for p in batch["clones"]] for batch in inputs["batches"]]
    state = out / "judges" / mapping["judges"][judge]["dir"] / "state"
    (state / "r1").mkdir(parents=True)
    (state / "r1" / "run.json").write_text(json.dumps({"bound_inputs": inputs}))
    write_memo({"state_root": state}, [], value)
    pooling.scan_judge(out, judge, "f" * 40, home=home)


def test_join_scores_maps_summarized_runs_to_their_evaluation_records(evaluations, world):
    out, mapping, runs, log, criterion = evaluations
    for judge in ("judge-a", "judge-b"):
        score(out, mapping, judge, world.tmp / "home")
    summarize.summarize(out, criterion)
    rows = join_scores(out / "records" / "results.json", log)
    assert sorted((r["policy"], r["task"], r["replicate"], r["value"], r["calls"]) for r in rows) == [
        ("best_of_n", "task", 1, 4, 1), ("direct", "task", 1, 4, 1)]


def results_file(tmp_path, runs):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"runs": runs}))
    return path


def run_row(run, arm, value=5.0):
    return {"run": str(run), "arm": arm, "value": value, "hidden_value": 0.5, "calls": 2, "wall_clock_sec": 30.0}


def test_join_scores_reports_policy_identity_and_harness_values(tmp_path):
    log = tmp_path / "log.jsonl"
    append_record(log, log_row(tmp_path / "records" / "e9" / "run-1", eid="e9", mode="unguided", replicate=2))
    rows = join_scores(results_file(tmp_path, [run_row(tmp_path / "records" / "e9" / "run-1", "e9")]), log)
    assert rows == [{"candidate_id": "sha256:e9", "policy": "unguided:sha256:e9", "task": "task", "replicate": 2,
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


def rows_of(task, values):
    """Joined rows: `values` maps policy -> its replicate values on `task`."""
    return [{"candidate_id": f"sha256:{policy}", "policy": policy, "task": task, "replicate": k + 1, "value": v,
             "hidden": None, "calls": 1, "wall_clock_sec": 10.0}
            for policy, vs in values.items() for k, v in enumerate(vs)]


DIVERSE = {"episodes": {"accepted": 4}, "distinct_skeletons": 3, "revisit_rate": 0.25, "terminal_only_share": 0.25,
           "allocation_distinct": 0, "collapsed": False, "catalog": {}}
WIDE = {"direct": [4, 5], "best_of_n": [7, 8], "plan_then_implement": [5, 6]}  # pooled SD 0.71, gap 3


def test_phase1_readout_within_tolerance_is_not_separated():
    close = {"direct": [4, 6], "best_of_n": [5, 7]}  # pooled SD sqrt(2), gap 1 < 2 * sqrt(2)
    readout = phase1_readout(rows_of("t1", close) + rows_of("t2", close), DIVERSE)
    assert (readout["tasks"]["t1"]["separated"], readout["phase2_selected"], readout["rule"]) == (
        False, False, "within_tolerance")


def test_phase1_readout_reports_mean_sd_and_direct_rank_per_task():
    task = phase1_readout(rows_of("t1", WIDE), DIVERSE)["tasks"]["t1"]
    assert (task["policies"]["best_of_n"]["mean"], task["policies"]["best_of_n"]["sd"], task["pooled_sd"],
            task["direct_rank"]) == (7.5, pytest.approx(0.7071, abs=1e-4), pytest.approx(0.7071, abs=1e-4), 3)


def test_phase1_readout_selects_phase2_when_both_tasks_separate_without_a_direct_winner():
    readout = phase1_readout(rows_of("t1", WIDE) + rows_of("t2", WIDE), DIVERSE)
    assert (readout["phase2_selected"], readout["rule"]) == (True, "separated")


def test_phase1_readout_does_not_select_phase2_when_direct_is_the_sole_winner():
    direct_wins = {"direct": [8, 8], "best_of_n": [3, 4]}
    readout = phase1_readout(rows_of("t1", direct_wins) + rows_of("t2", direct_wins), DIVERSE)
    assert (readout["tasks"]["t1"]["direct_rank"], readout["phase2_selected"], readout["rule"]) == (
        1, False, "direct_sole_winner")


def test_phase1_readout_does_not_select_phase2_when_unguided_i1_collapsed():
    readout = phase1_readout(rows_of("t1", WIDE) + rows_of("t2", WIDE), DIVERSE | {"collapsed": True})
    assert (readout["unguided"]["collapsed"], readout["phase2_selected"], readout["rule"]) == (
        True, False, "collapsed")


def test_phase1_readout_leaves_out_unvalued_runs_and_has_no_sd_for_a_single_value():
    rows = rows_of("t1", {"direct": [4, None], "best_of_n": [6]})
    task = phase1_readout(rows, DIVERSE)["tasks"]["t1"]
    assert (task["policies"]["direct"]["runs"], task["policies"]["direct"]["sd"], task["pooled_sd"],
            task["separated"]) == (1, UNAVAILABLE, UNAVAILABLE, False)


def test_phase1_criterion_is_frozen_for_both_packages_with_their_anchors_and_judges():
    criterion = json.loads(CRITERION.read_text())
    packages = [REPO / task for task in criterion["tasks"]]
    assert ([(p / "base_commit").read_text().strip() for p in packages],
            [sorted(a.stem for a in (p / "anchors").glob("*.diff")) for p in packages],
            criterion["judges"], criterion["primary"], criterion["written_before_scoring"]) == (
        [criterion["base_commits"][p.name] for p in packages], [sorted(criterion["anchors"][p.name]) for p in packages],
        ["claude-opus-5-5", "gpt-6-sol"], [], True)
