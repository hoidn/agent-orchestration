"""The long-horizon oracle summary (`experiments/long_horizon_tasks/summarize.py`) on constructed job trees."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks"
_spec = importlib.util.spec_from_file_location("lh_summarize", KIT / "summarize.py")
summarize = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(summarize)

META = ("label=t1\nagent=oracle\nround=1\ncpus=8-31\ngate=none\noverlay_sha256=abc\n"
        "images=agent:aaa verifier:vvv\nload_start=40.10 50.20 55.30\nrc=0\nwall_s=300\nload_end=60.00 52.00 55.00\n")
SAMPLES = ("load 40.10\nfree 50000000000 70000000000\n"
           "container t1__x__env_main_1 peak=100 affinity=8-31\n"
           "container t1__x__env_harbor-docker-egress-control-sidecar_1 peak=7 affinity=8-31\n"
           "load 61.50\nfree 49000000000 71000000000\ncontainer t1__x__env_main_1 peak=250 affinity=8-31\n"
           "container t1__x__verifier__main__env_main_1 peak=90 affinity=8-31|0-31\n")


def _result(reward=1.0, error=None):
    return {"verifier_result": {"rewards": {"reward": reward}} if reward is not None else None,
            "exception_info": {"exception_type": error} if error else None,
            "environment_setup": {"started_at": "2026-11-14T10:00:00+00:00", "finished_at": "2026-11-14T10:01:00+00:00"},
            "agent_execution": {"started_at": "2026-11-14T10:01:00+00:00", "finished_at": "2026-11-14T10:01:30+00:00"},
            "verifier": {"started_at": "2026-11-14T10:01:30+00:00", "finished_at": None}}


def _trial(jobs, label, agent, rnd, reward=1.0, error=None, stdout=b"3 passed\n", meta=META, result=True):
    out = jobs / agent / label / str(rnd)
    trial = out / "2026-11-14__10-00-00" / f"{label}__AbC1234"
    (trial / "verifier").mkdir(parents=True)
    (out / "meta.txt").write_text(meta.replace("label=t1", f"label={label}").replace("agent=oracle", f"agent={agent}")
                                  .replace("round=1", f"round={rnd}"))
    (out / "samples").write_text(SAMPLES)
    if result:
        (trial / "result.json").write_text(json.dumps(_result(reward, error)))
    (trial / "verifier" / "test-stdout.txt").write_bytes(stdout)
    (trial / "verifier" / "ctrf.json").write_text(json.dumps(
        {"results": {"summary": {"tests": 3, "passed": 3, "failed": 0, "skipped": 0, "start": 1, "stop": 2}}}))
    return out


def test_samples_give_the_highest_load_the_lowest_free_space_and_each_container_s_peak_and_affinity():
    got = summarize.parse_samples(SAMPLES)
    assert got == {"load_max": 61.5, "free_min": {"/": 49 * 10**9, "/home": 70 * 10**9}, "containers": [
        {"role": "agent main", "peak_bytes": 250, "affinity": ["8-31"]},
        {"role": "agent sidecar", "peak_bytes": 7, "affinity": ["8-31"]},
        {"role": "verifier main", "peak_bytes": 90, "affinity": ["0-31", "8-31"]}]}


def test_a_trial_record_holds_outcome_timing_load_and_digests_but_no_log_text(tmp_path):
    record = summarize.trial_record(_trial(tmp_path, "t1", "oracle", 1))
    assert {k: record[k] for k in ("label", "task", "agent", "round", "reward", "error", "rc", "wall_s", "env_s",
                                   "agent_s", "verify_s", "load_start", "load_end", "images", "verifier_output",
                                   "ctrf")} == {
        "label": "t1", "task": "t1", "agent": "oracle", "round": 1, "reward": 1.0, "error": None, "rc": 0,
        "wall_s": 300, "env_s": 60, "agent_s": 30, "verify_s": None, "load_start": [40.1, 50.2, 55.3],
        "load_end": [60.0, 52.0, 55.0], "images": {"agent": "aaa", "verifier": "vvv"},
        "verifier_output": {"sha256": hashlib.sha256(b"3 passed\n").hexdigest(), "bytes": 9},
        "ctrf": {"tests": 3, "passed": 3, "failed": 0, "skipped": 0}}


def test_a_trial_without_a_harness_result_is_recorded_as_such(tmp_path):
    record = summarize.trial_record(_trial(tmp_path, "t1", "oracle", 1, result=False))
    assert (record["reward"], record["error"]) == (None, "no result.json")


def test_the_uidfix_label_belongs_to_its_task(tmp_path):
    assert summarize.trial_record(_trial(tmp_path, "vba-userform-port-uidfix", "nop", 1))["task"] == "vba-userform-port"


def _records(tmp_path, spec):
    return [summarize.trial_record(_trial(tmp_path, label, agent, rnd, reward, error))
            for label, agent, rnd, reward, error in spec]


def test_counts_are_passes_of_runs_for_the_reference_and_the_untouched_environment(tmp_path):
    recs = _records(tmp_path, [("t1", "oracle", 1, 1.0, None), ("t1", "oracle", 2, 0.0, None),
                               ("t1", "nop", 1, 0.0, None), ("t1", "nop", 2, 1.0, None),
                               ("t1", "install", 1, None, None)])
    got = summarize.counts(recs)["t1"]
    assert (got["reference"], got["untouched"], got["install"], got["passes"]) == ([1, 2], [1, 2], "ok", False)


def test_a_trial_without_a_reward_counts_as_a_run_and_an_error(tmp_path):
    recs = _records(tmp_path, [("t1", "oracle", 1, None, "VerifierTimeoutError"), ("t1", "nop", 1, 0.0, None)])
    got = summarize.counts(recs)["t1"]
    assert (got["reference"], got["errors"], got["passes"]) == ([0, 1], ["oracle 1: VerifierTimeoutError"], False)


def test_a_task_passes_when_every_reference_run_passes_and_no_untouched_run_does(tmp_path):
    recs = _records(tmp_path, [("t1", "oracle", 1, 1.0, None), ("t1", "nop", 1, 0.0, None)])
    assert summarize.counts(recs)["t1"]["passes"] is True


def test_the_table_prints_one_line_per_label_with_its_counts(tmp_path):
    recs = _records(tmp_path, [("t1", "oracle", 1, 1.0, None), ("t1", "nop", 1, 0.0, None)])
    line = summarize.table(summarize.counts(recs))[-1]
    assert ("t1" in line, "reference 1 of 1" in line, "untouched 0 of 1" in line) == (True, True, True)


def test_writing_fills_each_task_s_oracle_evidence_and_overlay_digest(tmp_path):
    recs = _records(tmp_path, [("t1", "oracle", 1, 1.0, None), ("t1", "nop", 1, 0.0, None)])
    tasks = {"tasks": [{"name": "terminal-bench/t1", "overlay_digest": None, "oracle_evidence": None},
                       {"name": "terminal-bench/t2", "overlay_digest": None, "oracle_evidence": None}]}
    summarize.fill_tasks(tasks, recs, "oracle_first_pass")
    t1, t2 = tasks["tasks"]
    assert (t1["overlay_digest"], t1["oracle_evidence"]["oracle_first_pass"][0]["reference"], t2["oracle_evidence"]) == (
        "abc", [1, 1], None)


def test_two_overlay_digests_for_one_task_are_an_error(tmp_path):
    recs = _records(tmp_path, [("t1", "oracle", 1, 1.0, None)])
    recs.append(recs[0] | {"overlay_sha256": "other"})
    with pytest.raises(ValueError):
        summarize.fill_tasks({"tasks": [{"name": "terminal-bench/t1"}]}, recs, "oracle_first_pass")
