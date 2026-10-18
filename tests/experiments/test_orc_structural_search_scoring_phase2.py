"""Structural search scoring: the Phase 2 readout (scoring_phase2) over synthetic run evidence (log, judging
results, archive files, candidate roots) and its CLI. No provider is called."""

import json
from pathlib import Path

import pytest

from experiments.compare.repos import sha256_file
from experiments.orc_structural_search.records import UNAVAILABLE, append_record
from experiments.orc_structural_search.scoring import DIRECT, main
from experiments.orc_structural_search.scoring_phase2 import phase2_readout
from tests.experiments.compare_harness_support import REPO
from tests.experiments.test_orc_structural_search_scoring import FAILED, INCIDENT, log_row, run_row


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

    def failed(self, cid, task, *, generation=1, replicate=2):
        """A failed adaptive evaluation of `cid` on `task`: in the log only, no pool row."""
        append_record(self.log, {"kind": "evaluation", "mode": "adaptive", "evaluation_id": f"{cid}-{task}-failed",
                                 "candidate_id": cid, "records_dir": str(self.root / "records" / "failed"),
                                 "task_id": task, "replicate": replicate, "outcome": "failed", "split": "adaptive",
                                 "generation": generation})

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
    """A read_pool result for the validation task: candidate -> [(value, calls, wall_clock_sec)]; a value of
    FAILED or INCIDENT is an evaluation with that outcome."""
    rows = [{"evaluation_id": f"v-{cid}-{k}", "candidate_id": cid, "mode": "validation", "policy": cid,
             "task": VALIDATION, "replicate": k + 1, "outcome": v if v in (FAILED, INCIDENT) else "completed",
             "value": None if v in (FAILED, INCIDENT) else v, "hidden": None, "calls": c, "wall_clock_sec": w}
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


def test_phase2_readout_child_adaptive_mean_counts_a_failed_evaluation_as_zero(run):
    run.episode("C1", interface="I1", value=6.0)
    run.failed("C1", ADAPTIVE[0])  # task 0: [6, 0] -> 3; task 1: 6; adaptive mean 4.5, gain 0.5
    figures = readout2([run])["runs"][0]["interfaces"]["I1"]
    assert (figures["gains"]["C1"], figures["improvements"]) == (0.5, 0)


def test_phase2_readout_validation_mean_counts_a_failed_replicate_as_zero(run):
    finalists(run)
    pool = validation_pool(WITHIN | {"C1": [(4.4, 3, 2000.0), (FAILED, 3, 2000.0)]})
    row = next(r for r in readout2([run], pool)["validation"] if r["candidate_id"] == "C1")
    assert (row["validation_mean"], row["valued_mean"], row["failed"]) == (2.2, 4.4, 1)


def test_phase2_readout_child_adaptive_mean_counts_a_timeout_as_zero(run):
    run.episode("C1", interface="I1", value=6.0)
    run.failed("C1", ADAPTIVE[0])
    append_record(run.log, {"kind": "evaluation", "mode": "adaptive", "evaluation_id": "C1-timeout",
                            "candidate_id": "C1", "records_dir": str(run.root / "records" / "t"),
                            "task_id": ADAPTIVE[1], "replicate": 2, "outcome": "incident", "split": "adaptive",
                            "generation": 1, "incidents": ["launch 0: no terminal row in run r (launcher exit -9; "
                                                           "see launch-0.log)"]})
    # task 0: [6, 0] -> 3; task 1: [6, 0] -> 3; adaptive mean 3, gain -1
    assert readout2([run])["runs"][0]["interfaces"]["I1"]["gains"]["C1"] == -1


def test_phase2_readout_validation_replicates_exclude_incidents(run):
    finalists(run)
    with pytest.raises(ValueError, match="without 2 replicates"):
        readout2([run], validation_pool(WITHIN | {"C1": [(4.4, 3, 2000.0), (INCIDENT, 3, 2000.0)]}))


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


# CLI: Phase 2 passes a run and the validation pool.
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
