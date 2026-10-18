"""Structural search scoring: the blind pool of evaluations, the join of summarize's runs to evaluation records,
and the Phase 1 readout. Synthetic logs, memos, scoring runs and results.json; no provider is called."""

import json
from pathlib import Path

import pytest

from experiments.compare import pool as pooling, prepare, summarize
from experiments.compare.repos import sha256_file
from experiments.orc_structural_search.records import UNAVAILABLE, append_record
from experiments.orc_structural_search.scoring import DIRECT
from experiments.orc_structural_search.scoring import (
    join_scores, main, phase1_readout, pool_evaluations, read_pool, split_batches,
)
from experiments.orc_structural_search.scoring_phase2 import phase2_readout
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
    pooling.scan_judge(out, judge, "f" * 40, home=home)


def test_read_pool_joins_summarized_runs_to_their_evaluation_records(evaluations, world):
    out, mapping, runs, log, criterion = evaluations
    for judge in ("judge-a", "judge-b"):
        score(out, mapping, judge, world.tmp / "home")
    summarize.summarize(out, criterion)
    pool = read_pool(out / "records" / "results.json", log, criterion)
    assert (sorted((r["policy"], r["task"], r["replicate"], r["value"], r["calls"]) for r in pool["rows"]),
            pool["unpooled"]) == ([("best_of_n", "task", 1, 4, 1), ("direct", "task", 1, 4, 1)], [])


def results_file(tmp_path, runs, sha="0" * 64):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"runs": runs, "criterion_sha256": sha, "anchors": [], "agreement": {},
                                "excluded_judges": {}}))
    return path


def run_row(run, arm, value=5.0):
    return {"run": str(run), "arm": arm, "value": value, "hidden_value": 0.5, "calls": 2, "wall_clock_sec": 30.0}


def test_join_scores_reports_policy_identity_and_harness_values(tmp_path):
    log = tmp_path / "log.jsonl"
    append_record(log, log_row(tmp_path / "records" / "e9" / "run-1", eid="e9", mode="unguided", replicate=2))
    rows = join_scores(results_file(tmp_path, [run_row(tmp_path / "records" / "e9" / "run-1", "e9")]), log)
    assert rows == [{"evaluation_id": "e9", "candidate_id": "sha256:e9", "mode": "unguided",
                     "policy": "unguided:sha256:e9", "task": "task", "replicate": 2, "value": 5.0, "hidden": 0.5,
                     "calls": 2, "wall_clock_sec": 30.0}]


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


CRIT = json.loads(CRITERION.read_text()) | {  # the frozen rules with two synthetic tasks
    "tasks": ["tasks/t1", "tasks/t2"], "anchors": {t: {"upstream": "up", "stub": "stub"} for t in ("t1", "t2")}}
TRUSTED = [{"batch": 0, "judge": "j", "anchor": "up", "total": 8},
           {"batch": 0, "judge": "j", "anchor": "stub", "total": 1}]
DIVERSE = {"episodes": {"accepted": 4}, "distinct_skeletons": 3, "revisit_rate": 0.25, "terminal_only_share": 0.25,
           "allocation_distinct": 0, "collapsed": False, "catalog": {}}
WIDE = {"direct": [4, 5], "best_of_n": [7, 8], "plan_then_implement": [5, 6]}  # pooled SD 0.71, gap 3


def pool_of(task, values, *, children=None, anchors=TRUSTED):
    """A read_pool result: `values` maps catalog policy -> its replicate values, `children` child -> its values."""
    rows = [{"evaluation_id": f"{policy}-{k}", "candidate_id": f"sha256:{policy}", "mode": mode, "policy": policy,
             "task": task, "replicate": k + 1, "value": v, "hidden": None, "calls": 1, "wall_clock_sec": 10.0}
            for mode, group in (("catalog", values), ("unguided", children or {}))
            for policy, vs in group.items() for k, v in enumerate(vs)]
    return {"task": task, "rows": rows, "anchors": anchors, "agreement": {}, "excluded_judges": {}, "unpooled": []}


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
    assert ([(p / "base_commit").read_text().strip() for p in packages],
            [sorted(a.stem for a in (p / "anchors").glob("*.diff")) for p in packages],
            criterion["judges"], criterion["primary"], criterion["written_before_scoring"]) == (
        [criterion["base_commits"][p.name] for p in packages],
        [sorted(criterion["anchors"][p.name].values()) for p in packages], ["claude-opus-5-5", "gpt-6-sol"], [], True)


# Phase 2: synthetic run evidence (log, judging results, archive files, candidate roots); no provider is called.
CRITERION2 = REPO / "experiments" / "orc_structural_search" / "criteria" / "phase2.json"
CRIT2 = json.loads(CRITERION2.read_text())
ADAPTIVE = [Path(t).name for t in CRIT2["adaptive_tasks"]]
VALIDATION = Path(CRIT2["validation_task"]).name
BODY = "(provider-result providers.coder :prompt (p :task task))"
BRANCHED = f'(if true {BODY} (record Change :summary "s" :account "a"))'


def program(body=BODY):
    return f"(workflow-lisp (defmodule direct) (defworkflow run ((task String)) -> Outcome {body}))"


def anchors_of(task, up=8, stub=1, batch=0):
    roles = CRIT2["anchors"][task]
    return [{"batch": batch, "judge": "j", "anchor": roles["upstream"], "total": up},
            {"batch": batch, "judge": "j", "anchor": roles["stub"], "total": stub}]


def results_json(path, runs, anchors):
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"runs": runs, "criterion_sha256": sha256_file(CRITERION2), "anchors": anchors,
                                "agreement": {}, "excluded_judges": {}}))
    return path


class Run:
    """One Phase 2 run: its log (with the reference row), archive directory and candidate roots under `root`."""

    def __init__(self, root: Path, reference="P"):
        self.root, self.log, self.archive = root, root / "log.jsonl", root / "archive"
        self.archive.mkdir(parents=True)
        self.candidate("P", program())
        if reference:
            append_record(self.log, {"kind": "reference", "candidate_id": reference, "run": root.name})

    def candidate(self, cid, source):
        path = self.root / "candidates" / cid
        path.mkdir(parents=True)
        (path / "direct.orc").write_text(source)
        (path / "common.orc").write_text("(workflow-lisp (defmodule common))")
        return path

    def archived(self, generation, *entries):
        """gen-<n>.json: (candidate_id, mean_value, mean_calls) entries; P is the direct seed."""
        (self.archive / f"gen-{generation}.json").write_text(json.dumps([
            {"candidate_id": cid, "candidate_root": str(self.root / "candidates" / cid),
             "seed": DIRECT if cid == "P" else None, "values": {t: [value] for t in ADAPTIVE}, "mean_value": value,
             "mean_calls": calls, "evidence": "adaptive", "generation": generation} for cid, value, calls in entries]))

    def episode(self, cid, *, interface, outcome="accepted", value=None, source=None, generation=1, skeleton=None,
                up=8):
        """An episode against P; an accepted child with `value` is evaluated and judged on both adaptive tasks
        in pools whose upstream anchor scores `up` (the stub 1)."""
        if outcome == "accepted":
            self.candidate(cid, source or program())
        append_record(self.log, {
            "kind": "episode", "interface": interface, "generation": generation, "episode_id": f"ep-{cid}",
            "outcome": outcome, "candidate_id": cid, "parent_candidate_id": "P",
            "candidate_root": str(self.root / "candidates" / cid) if outcome == "accepted" else None,
            "skeleton": (skeleton or f"sk-{cid}") if outcome == "accepted" else None, "parent_skeleton": "sk-P",
            "provider_allocation": {"run": ["coder"]} if outcome == "accepted" else None,
            "parent_provider_allocation": {"run": ["coder"]}})
        if value is not None:
            for task in ADAPTIVE:
                self.judged(cid, task, value, generation=generation, up=up)

    def judged(self, cid, task, value, *, generation, up):
        eid = f"{cid}-{task}"
        records = self.root / "records" / eid / "run-1"
        append_record(self.log, {"kind": "evaluation", "mode": "adaptive", "evaluation_id": eid, "candidate_id": cid,
                                 "records_dir": str(records), "task_id": task, "replicate": 1,
                                 "outcome": "completed", "split": "adaptive", "generation": generation})
        results = results_json(self.root / "pools" / eid / "results.json", [run_row(records, eid, value)],
                               anchors_of(task, up))
        append_record(self.log, {"kind": "judging", "generation": generation, "task": task,
                                 "pool": str(results.parent), "results": str(results)})


def validation_pool(values, anchors=None):
    """A read_pool result for the validation task: candidate -> [(value, calls, wall_clock_sec)]."""
    rows = [{"evaluation_id": f"v-{cid}-{k}", "candidate_id": cid, "mode": "validation", "policy": cid,
             "task": VALIDATION, "replicate": k + 1, "value": v, "hidden": None, "calls": c, "wall_clock_sec": w}
            for cid, runs in values.items() for k, (v, c, w) in enumerate(runs)]
    return {"task": VALIDATION, "rows": rows, "anchors": anchors_of(VALIDATION) if anchors is None else anchors,
            "agreement": {}, "excluded_judges": {}, "unpooled": [], "criterion_sha256": sha256_file(CRITERION2)}


@pytest.fixture
def run(tmp_path):
    run = Run(tmp_path / "run-1")
    run.archived(0, ("P", 4.0, 2))
    return run


def readout2(runs, pool=None):
    return phase2_readout([r.log for r in runs], [r.archive for r in runs], pool, CRITERION2)


def finalists(run):
    """gen-1 archive: C1 and C2 are the top two; P (direct, the reference) joins them on validation."""
    run.episode("C1", interface="I1", value=6.0)
    run.episode("C2", interface="I2", value=5.5)
    run.archived(1, ("P", 4.0, 2), ("C1", 6.0, 3), ("C2", 5.5, 1), ("C3", 4.5, 1))


WITHIN = {"P": [(4.0, 2, 3000.0)] * 2, "C1": [(4.4, 3, 2000.0)] * 2, "C2": [(5.0, 1, 20000.0)] * 2}


def test_phase2_readout_counts_improvements_per_completed_episode_per_interface(run):
    run.episode("C1", interface="I1", value=5.0)  # gain 1.0 > 0.5
    run.episode("C2", interface="I1", value=4.3)  # gain 0.3
    run.episode("R1", interface="I1", outcome="rejected")
    run.episode("T1", interface="I1", outcome="exhausted")  # not completed
    run.episode("C3", interface="I2", value=4.6)  # gain 0.6
    figures = readout2([run])["runs"][0]["interfaces"]
    assert [(figures[i]["completed"], figures[i]["accepted"], figures[i]["improvements"],
             figures[i]["improvements_per_episode"]) for i in ("I1", "I2")] == [(3, 2, 1, pytest.approx(1 / 3)),
                                                                                (1, 1, 1, 1.0)]


def test_phase2_readout_marks_improvements_untrusted_when_a_generations_anchors_are_inverted(run):
    run.episode("C1", interface="I1", value=6.0)
    run.episode("C2", interface="I2", value=6.0, up=0)  # the stub (1) above the upstream anchor
    result = readout2([run])["runs"][0]
    assert (result["improvement_rule"], result["interfaces"]["I1"]["improvements"],
            result["anchors"][ADAPTIVE[0]]["generations"]) == ("anchors_inverted", "untrusted", {1: False})


def test_phase2_readout_marks_improvements_untrusted_when_anchors_spread_across_generations(run):
    run.episode("C1", interface="I1", value=6.0, generation=1)
    run.archived(1, ("P", 4.0, 2), ("C1", 6.0, 3))
    run.episode("C2", interface="I2", value=6.0, generation=2, up=5)  # upstream 8 then 5: spread 3 > 2
    result = readout2([run])["runs"][0]
    assert (result["improvement_rule"], result["interfaces"]["I2"]["improvements_per_episode"],
            result["anchors"][ADAPTIVE[0]]["anchor_spread"]) == ("anchor_spread", "untrusted", {"j": 3})


def test_phase2_readout_refuses_an_adaptive_pool_summarized_under_another_criterion(run, tmp_path):
    run.episode("C1", interface="I1", value=6.0)
    other = tmp_path / "other.json"
    other.write_text(CRITERION2.read_text() + " ")
    with pytest.raises(ValueError, match="summarized under criterion sha256"):
        phase2_readout([run.log], [run.archive], None, other)


def test_phase2_readout_reports_a_control_flow_change_when_a_child_adds_a_branch(run):
    run.episode("C1", interface="I2", value=5.0, source=program(BRANCHED))
    run.episode("C2", interface="I2", value=5.0, source=program(), skeleton="sk-P")
    assert readout2([run])["runs"][0]["interfaces"]["I2"]["control_flow_changes"] == [
        {"candidate_id": "C1", "parent_candidate_id": "P",
         "parent": {"if": 0, "cond": 0, "match": 0, "loop/recur": 0, "list/map-effect": 0},
         "child": {"if": 1, "cond": 0, "match": 0, "loop/recur": 0, "list/map-effect": 0}}]


def test_phase2_readout_shrinkage_is_screening_minus_validation(run):
    run.episode("C1", interface="I1", value=6.0)
    run.archived(1, ("P", 4.0, 2), ("C1", 6.0, 3))
    pool = validation_pool({"P": [(3.0, 2, 100.0), (3.5, 2, 100.0)], "C1": [(4.0, 3, 50.0), (5.0, 3, 50.0)]})
    rows = {r["candidate_id"]: r for r in readout2([run], pool)["validation"]}
    assert [(rows[c]["screening_mean"], rows[c]["validation_mean"], rows[c]["shrinkage"]) for c in ("P", "C1")] == [
        (4.0, 3.25, 0.75), (6.0, 4.5, 1.5)]


def test_phase2_readout_final_choice_follows_the_frozen_criterion_and_includes_the_reference(run):
    finalists(run)
    result = readout2([run], validation_pool(WITHIN))  # C2 is above the cost ceiling; C1 within 0.5 of P, cheaper
    assert (result["final_choice"], result["rule"],
            [(r["candidate_id"], r["is_reference"]) for r in result["validation"]], result["anchors_ok"]) == ("C1", "chosen", [("C1", False), ("C2", False), ("P", True)], True)


@pytest.mark.parametrize("anchors, rule", [
    (anchors_of(VALIDATION, up=0), "anchors_inverted"),
    (anchors_of(VALIDATION) + anchors_of(VALIDATION, up=5, batch=1), "anchor_spread")])
def test_phase2_readout_withholds_the_final_choice_when_the_validation_anchors_fail(run, anchors, rule):
    finalists(run)
    result = readout2([run], validation_pool(WITHIN, anchors=anchors))
    assert (result["rule"], result["final_choice"]) == (rule, UNAVAILABLE)


def test_phase2_readout_refuses_a_validation_pool_that_is_not_the_finalists_reference_and_direct(run):
    finalists(run)
    with pytest.raises(ValueError, match="validation pool holds"):
        readout2([run], validation_pool(WITHIN | {"C3": [(4.0, 1, 10.0)] * 2}))


def test_phase2_readout_refuses_a_validation_candidate_without_its_replicates(run):
    finalists(run)
    with pytest.raises(ValueError, match="without 2 replicates"):
        readout2([run], validation_pool(WITHIN | {"C1": [(4.4, 3, 2000.0)]}))


def test_phase2_readout_reports_a_finalist_without_a_valued_run_as_unvalued(run):
    finalists(run)
    result = readout2([run], validation_pool(WITHIN | {"C1": [(None, 3, 2000.0)] * 2}))
    assert (result["unvalued"], result["final_choice"]) == (["C1"], "P")


def test_phase2_readout_reads_the_reference_from_the_logs_and_refuses_disagreement(tmp_path):
    runs = [Run(tmp_path / "run-1"), Run(tmp_path / "run-2", reference="C1")]
    for r in runs:
        r.archived(0, ("P", 4.0, 2))
    with pytest.raises(ValueError, match="runs disagree on the reference seed"):
        readout2(runs)


def test_phase2_readout_refuses_a_run_without_a_reference_row(tmp_path):
    run = Run(tmp_path / "run-1", reference=None)
    run.archived(0, ("P", 4.0, 2))
    run.episode("C1", interface="I1", outcome="rejected")
    with pytest.raises(ValueError, match="expected one reference row, found 0"):
        readout2([run])


def test_phase2_readout_refuses_a_run_with_two_reference_rows(run):
    append_record(run.log, {"kind": "reference", "candidate_id": "P", "run": "run-1"})
    with pytest.raises(ValueError, match="expected one reference row, found 2"):
        readout2([run])


def test_phase2_readout_anchor_spread_sees_every_pool_of_a_task_in_one_generation(run):
    run.episode("C1", interface="I1", value=6.0)  # generation 1, upstream anchor 8
    run.episode("C2", interface="I2", value=6.0, up=5)  # generation 1, another pool of each task: upstream 5
    result = readout2([run])["runs"][0]
    assert (result["anchors"][ADAPTIVE[0]]["anchor_spread"], result["improvement_rule"]) == ({"j": 3}, "anchor_spread")


def test_phase2_readout_never_pools_interfaces(run):
    run.episode("R1", interface="I1", outcome="rejected")
    run.episode("C1", interface="I2", value=5.0)
    run.episode("C2", interface="I2", value=5.0, skeleton="sk-P")  # terminal-only: parent skeleton and allocation
    figures = readout2([run])["runs"][0]["interfaces"]
    assert ([figures["I1"][k] for k in ("accepted", "terminal_only_share", "revisit_rate", "collapsed")],
            [figures["I2"][k] for k in ("accepted", "terminal_only_share", "collapsed")]) == (
        [0, UNAVAILABLE, UNAVAILABLE, UNAVAILABLE], [2, 0.5, False])


def test_phase2_readout_reports_the_incumbent_mean_per_generation_and_no_validation_without_a_pool(run):
    run.episode("C1", interface="I1", value=6.0)
    run.archived(1, ("P", 4.0, 2), ("C1", 6.0, 3))
    result = readout2([run])
    assert (result["runs"][0]["trajectory"], result["reference"], result["final_choice"], result["rule"]) == (
        [{"generation": 0, "incumbent_mean": 4.0}, {"generation": 1, "incumbent_mean": 6.0}], "P",
        UNAVAILABLE, UNAVAILABLE)


def test_phase2_criterion_is_frozen_with_three_packages_and_their_anchors():
    packages = [REPO / t for t in [*CRIT2["adaptive_tasks"], CRIT2["validation_task"]]]
    assert ([(p / "base_commit").read_text().strip() for p in packages],
            [sorted(a.stem for a in (p / "anchors").glob("*.diff")) for p in packages],
            CRIT2["judges"], CRIT2["improvement"]["min_gain"], CRIT2["collapse_threshold"],
            CRIT2["final_choice"]["mean_cost_ceiling"], CRIT2["written_before_scoring"]) == (
        [CRIT2["base_commits"][p.name] for p in packages],
        [sorted(CRIT2["anchors"][p.name].values()) for p in packages], ["claude-opus-5-5", "gpt-6-sol"],
        0.5, 0.75, 14400, True)


# CLI: the live Phase 1 readout passes one --log; Phase 2 passes a run and the validation pool.
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
    main(["readout", "--log", str(log), "--driver-readout", str(tmp_path / "readout.json"), "--criterion",
          str(CRITERION), *results])
    result = json.loads(capsys.readouterr().out)
    assert (result["rule"], result["phase2_selected"]) == ("separated", True)


def test_readout_cli_phase2_reads_runs_and_the_validation_pool(run, tmp_path, capsys):
    finalists(run)
    vlog, runs = tmp_path / "validation" / "log.jsonl", []
    vlog.parent.mkdir()
    for cid, rows in WITHIN.items():
        for k, (value, _, _) in enumerate(rows):
            records = tmp_path / "validation" / "records" / f"v-{cid}-{k}" / "run-1"
            append_record(vlog, log_row(records, eid=f"v-{cid}-{k}", task=VALIDATION, mode="validation",
                                        replicate=k + 1) | {"candidate_id": cid})
            runs.append(run_row(records, f"v-{cid}-{k}", value) | {"calls": rows[k][1], "wall_clock_sec": rows[k][2]})
    results = results_json(tmp_path / "validation" / "pool" / "results.json", runs, anchors_of(VALIDATION))
    main(["readout", "--phase", "2", "--criterion", str(CRITERION2), "--log", str(run.log), "--archive",
          str(run.archive), "--validation-log", str(vlog), str(results)])
    result = json.loads(capsys.readouterr().out)
    assert (result["final_choice"], result["runs"][0]["interfaces"]["I1"]["improvements"]) == ("C1", 1)
