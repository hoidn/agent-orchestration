import copy
import json

import pytest

from experiments.compare.studies.prr_direct_orc import runner


def observations(scores=((1, 4), (2, 5))):
    result = []
    for ordinal, (baseline, partial) in enumerate(scores):
        clones = {f"a{ordinal}": {"ratings": {runner.JUDGE: {"quality": baseline}}},
                  f"b{ordinal}": {"ratings": {runner.JUDGE: {"quality": partial}}}}
        result.append({"unit_key": f"evaluator-{ordinal + 1}", "pool": str(runner.POOLS / f"evaluator-{ordinal + 1}"),
                       "native_session_id": f"session-{ordinal}",
                       "native_snapshot": {"path": f"native-{ordinal}.jsonl", "sha256": str(ordinal) * 64},
                       "mapping": {"criterion_sha256": "criterion", "task": str(runner.TASK), "runs": {},
                         "clones": {cid: {} for cid in clones}, "batches": [list(clones)], "rubric": runner.RUBRIC},
                       "results": {"criterion_sha256": "criterion", "task": str(runner.TASK), "runs": [],
                         "judges": [runner.JUDGE], "excluded_judges": {}, "clones": clones},
                       "patch_hashes": {f"a{ordinal}": "empty", f"b{ordinal}": "partial"}})
    return result


def test_both_independent_gaps_required_and_harness_calibration_stays_absent():
    result = runner.evaluator_gate(observations(), "criterion", {"baseline": "empty", "natural_partial": "partial"})
    assert result["passed"] and result["gaps"] == [3, 3]
    assert not runner.evaluator_gate(observations(((1, 4), (4, 4))), "criterion",
                                    {"baseline": "empty", "natural_partial": "partial"})["passed"]


def test_evaluator_gate_cannot_count_one_pool_or_native_session_twice():
    values = observations()
    with pytest.raises(runner.StudyError):
        runner.evaluator_gate([values[0], values[0]], "criterion", {"baseline": "empty", "natural_partial": "partial"})
    values[1]["native_session_id"] = values[0]["native_session_id"]
    with pytest.raises(runner.StudyError):
        runner.evaluator_gate(values, "criterion", {"baseline": "empty", "natural_partial": "partial"})


@pytest.mark.parametrize("change", ["missing", "excluded", "duplicate-patch", "wrong-criterion", "noninteger", "calibration"])
def test_evaluator_gate_rejects_invalid_or_smaller_denominators(change):
    values = observations()
    if change == "missing": values.pop()
    elif change == "excluded": values[0]["results"]["excluded_judges"] = {runner.JUDGE: "excluded"}
    elif change == "duplicate-patch": values[0]["patch_hashes"]["b0"] = "empty"
    elif change == "wrong-criterion": values[0]["mapping"]["criterion_sha256"] = "changed"
    elif change == "noninteger": values[0]["results"]["clones"]["a0"]["ratings"][runner.JUDGE]["quality"] = True
    else: values[0]["results"]["calibration"] = {"passed": True}
    with pytest.raises(runner.StudyError):
        runner.evaluator_gate(values, "criterion", {"baseline": "empty", "natural_partial": "partial"})


def test_failed_or_missing_final_never_becomes_smaller_comparison():
    rows = {f"{arm}-{n}": {"arm": arm, "outcome": "completed", "excluded": None, "calls": 1}
            for arm in runner.ARMS for n in (1, 2)}
    assert runner.complete_finals(rows, set(rows))
    broken = copy.deepcopy(rows); broken["direct-1"]["outcome"] = "failed"
    assert not runner.complete_finals(broken, set(rows))
    broken.pop("direct-2")
    assert not runner.complete_finals(broken, set(rows))
    rows["implement_check_diagnose_repair-1"]["calls"] = 2
    assert not runner.complete_finals(rows, set(rows))


def test_cost_uses_per_request_not_cumulative_and_refuses_unknown_cache_retention():
    usage = {"model": runner.AUTHOR, "charge_tokens": {"input": 100, "cache_read": 20, "cache_write": 0, "output": 30},
             "provenance": {"complete_native_transcript": True}}
    receipt = {"provider_calls": 1, "receipt_usage": [{"call_id": "1", "provider": "codex", "status": "complete", "usage": [usage]}]}
    facts = [{"complete": True, "request_inputs": [150, 200], "context_windows": [258400], "cumulative_input": 99999999}]
    assert runner.standard_cost(receipt, facts)["value"] != "unavailable"

    facts[0]["request_inputs"].append(272001)
    assert runner.standard_cost(receipt, facts)["value"] == "unavailable"
    facts[0]["request_inputs"] = [200]; usage["charge_tokens"]["cache_write"] = 1
    assert runner.standard_cost(receipt, facts)["value"] == "unavailable"
    usage["cache_write_retention"] = "default"
    assert runner.standard_cost(receipt, facts)["value"] != "unavailable"


def test_live_native_audit_only_tolerates_unfinished_last_record(tmp_path):
    path = tmp_path / "native.jsonl"
    header = {"type": "session_meta", "payload": {"id": "one", "cwd": str(tmp_path)}}
    path.write_text("")
    assert runner.native_facts(path, live=True)["pending_tail"]
    assert not runner.native_facts(path)["complete"]
    path.write_text(json.dumps(header) + '\n{"type":"event_msg","payload":')
    facts = runner.native_facts(path, live=True)
    assert facts["id"] == "one" and facts["pending_tail"]
    with pytest.raises(runner.StudyError): runner.native_facts(path)
    path.write_text('{"type":"session_meta","payload":')
    assert runner.native_facts(path, live=True)["pending_tail"]
    path.write_text(json.dumps(header) + '\n{"type":"event_msg","payload":\n')
    with pytest.raises(ValueError): runner.native_facts(path, live=True)


@pytest.mark.parametrize("failure", ["no-judge", "receipt", "completion", "canonical"])
def test_failed_final_closes_with_all_costs_and_no_quality(monkeypatch, tmp_path, failure):
    monkeypatch.setattr(runner, "E", tmp_path)
    monkeypatch.setattr(runner, "bindings", lambda: None)
    monkeypatch.setattr(runner, "require_evaluator", lambda: None)
    monkeypatch.setattr(runner, "inventory", lambda: {})
    attempts = [{"stage": "authors", "arm": "direct", "cost": {"value": "unavailable"}, "wall_clock_sec": 5}]
    monkeypatch.setattr(runner, "costs_and_outcomes", lambda: attempts)
    monkeypatch.setattr(runner, "units", lambda: [] if failure == "no-judge" else [{"stage": "pilot-judge"}])
    def receipt(unit):
        if failure == "receipt": raise runner.StudyError("incomplete receipt")
    monkeypatch.setattr(runner, "receipt_proof", receipt)
    if failure == "canonical":
        runner.write_new(tmp_path / "pilot-judge.completion.json", {"errors": {}, "exit_code": 0, "original_terminal": {"outcome": "completed"}})
        class Pool:
            def verify_pool(self, path): pass
        class Summary:
            def summarize(self, *args): return {"runs": [], "clones": [], "excluded_judges": {}}
        monkeypatch.setattr(runner, "api", lambda: (None, Pool(), Summary()))
    runner.close_pilot()
    readout = runner.read(tmp_path / "pilot-readout.json")
    assert not readout["complete"] and readout["comparison"] == "unavailable"
    assert readout["all_attempts"] == attempts
    assert readout["consumption"]["total_study"]["standard_usd"] == "unavailable"


def test_failed_pool_intake_retains_measure_free_attempts(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "E", tmp_path)
    def broken(): raise runner.StudyError("missing final")
    monkeypatch.setattr(runner, "_pilot_pool", broken)
    monkeypatch.setattr(runner, "costs_and_outcomes", lambda: [{"outcome": "failed"}])
    runner.pilot_pool()
    value = runner.read(tmp_path / "pilot-incomplete.json")
    assert value["quality_comparison"] == "unavailable" and value["all_attempts"] == [{"outcome": "failed"}]


@pytest.mark.parametrize("started", ["call", "run", "launch"])
def test_public_execute_refuses_any_started_unit_without_launch(monkeypatch, tmp_path, started):
    evidence = tmp_path / "evidence"; evidence.mkdir()
    frozen = tmp_path / "freeze"; frozen.mkdir()
    monkeypatch.setattr(runner, "E", evidence); monkeypatch.setattr(runner, "F", frozen)
    monkeypatch.setattr(runner, "bindings", lambda: None)
    packet = frozen / "evaluator-packet.json"; runner.write_new(packet, {"files": []})
    approval = tmp_path / "review.json"; runner.write_new(approval, {})
    authorization = tmp_path / "authorization.json"; runner.write_new(authorization, {})
    monkeypatch.setattr(runner, "AUTHORIZATION", authorization)
    runner.write_new(evidence / "evaluator-declaration.json", {"packet": runner.ref(packet), "authorization": runner.ref(authorization),
        "new_cap": 11, "historical_starts": 76, "overall_cap": 87, "independent_review": runner.ref(approval)})
    records = tmp_path / "records"; (records / "calls").mkdir(parents=True)
    state = tmp_path / "state"; state.mkdir()
    unit = {"key": "evaluator-1", "stage": "evaluator", "records": str(records), "state_root": str(state)}
    monkeypatch.setattr(runner, "units", lambda: [unit])
    if started == "call": (records / "calls/1").mkdir()
    elif started == "run": (state / "existing").mkdir(); (state / "existing/run.json").write_text("{}")
    else: runner.write_new(evidence / "evaluator-1.launch.json", {})
    with pytest.raises(runner.StudyError, match="no retry"):
        runner.execute("evaluator")
    assert not (evidence / "evaluator-before.json").exists()
