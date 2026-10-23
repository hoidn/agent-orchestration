"""Every launch boundary rejects unsupported compiled effects before reserving calls."""

import pytest

from experiments.orc_structural_search import acceptance, closed_checks, driver, evaluation, ledger, three_arm
from experiments.orc_structural_search.candidates import CompileOutcome, compile_candidate
from experiments.orc_structural_search.quota import QuotaGuard
from tests.experiments.test_orc_structural_search_module import SOURCE, REPO, cfg, pair
from tests.experiments.qualification_support import measure_free, sha


@pytest.mark.parametrize("condition", ["joint", "module"])
@pytest.mark.parametrize("boundary", ["episode", "evaluation", "direct_evaluation"])
def test_unsupported_parent_refuses_before_reservation_or_launch(tmp_path, monkeypatch, condition, boundary):
    source = SOURCE.replace("(let* ((change", '(let* ((session (agent providers.coder :model "gpt-6.1-sol" :effort "high")) (change')
    parent, _ = pair(tmp_path, source)
    (parent / "direct.orc").write_text(source)
    criterion = measure_free(tmp_path)
    config = cfg(condition=condition, criterion_sha256=sha(criterion))
    assert compile_candidate(parent, config, runtime=REPO).status == "accepted"
    monkeypatch.setattr(ledger, "reserve", lambda *a, **k: pytest.fail("unsupported parent reached reservation"))
    monkeypatch.setattr(evaluation, "run_arm", lambda *a, **k: pytest.fail("unsupported parent reached run_arm"))
    monkeypatch.setattr(driver, "run_agent", lambda *a, **k: pytest.fail("unsupported parent reached mutator"))
    monkeypatch.setattr(driver, "runtime_commit", lambda runtime: "frozen")
    monkeypatch.setattr(evaluation, "runtime_commit", lambda runtime: "frozen")
    common = dict(runtime=REPO, env={}, work_root=tmp_path / "work", criterion=criterion)
    with pytest.raises(ValueError, match="unsupported_effect_shape"):
        if boundary == "direct_evaluation":
            evaluation.evaluate(parent, config, task_package=tmp_path / "task", replicate=1, timeout_sec=1, **common)
        else:
            _, archived = driver.archive(parent, tmp_path / "evidence", REPO)
            common.update(evidence_root=tmp_path / "evidence", solutions={}, call_cap=10)
            if boundary == "episode":
                driver.run_episode(archived, config, interface="I1", mode="test", agent_cmd=["false"],
                                   episode_index=0, **common)
            else:
                driver.evaluate_and_scan(archived, config, task=tmp_path / "task", replicate=1, timeout_sec=1,
                                         holdouts=(), fields={}, **common)
    assert not (tmp_path / "evidence" / ledger.LEDGER).exists()


@pytest.mark.parametrize("code,outcome", [("compiler_crash", "incident"), ("type_mismatch", "rejected")])
def test_compile_failure_keeps_diagnostics_through_planning_and_gate(tmp_path, monkeypatch, code, outcome):
    diagnostic = {"code": code, "message": "broken compiler", "notes": ["all details retained"]}
    failure = CompileOutcome("rejected", None, None, (diagnostic,))
    from experiments.orc_structural_search import candidates
    monkeypatch.setattr(candidates, "compile_candidate", lambda *a, **k: failure)
    monkeypatch.setattr(acceptance, "compile_candidate", lambda *a, **k: failure)
    guard = three_arm.CapGate(QuotaGuard())
    with pytest.raises(ValueError) as raised:
        guard.run(lambda: ledger.planned_calls(tmp_path, cfg(), runtime=REPO))
    assert not isinstance(raised.value, ledger.CallCapExceeded)
    assert raised.value.verdict["outcome"] == outcome
    assert raised.value.verdict["diagnostics"] == [diagnostic]
    assert raised.value.verdict["compile_diagnostics"]["diagnostics"] == [diagnostic]
    result = ledger.unbounded_refusal(tmp_path, cfg(), runtime=REPO)
    assert result["outcome"] == outcome
    assert result["diagnostics"] == [diagnostic]
    assert "refusal_code" not in result


@pytest.mark.parametrize("node", [{"k": "future"}, {"k": "perform", "class": "future"}])
def test_future_accounting_node_or_effect_fails_closed(node):
    with pytest.raises(ledger.CallCapExceeded):
        closed_checks.planned_maximum({"body": {"k": "halt", "value": node}, "definitions": {}})


def test_parent_archive_rejects_unsupported_orc_before_other_parent_check(tmp_path, monkeypatch):
    import json
    from dataclasses import asdict
    source = SOURCE.replace("(let* ((change", '(let* ((session (agent providers.coder :model "gpt-6.1-sol" :effort "high")) (change')
    parent, _ = pair(tmp_path, source)
    (parent / "direct.orc").write_text(source)
    config = tmp_path / "config.json"
    config.write_text(json.dumps(asdict(cfg())))
    monkeypatch.setattr(three_arm, "archive", lambda root, *a: ("id", root))
    monkeypatch.setattr(three_arm, "check_parent", lambda *a, **k: pytest.fail("unsupported ORC reached Python check"))
    with pytest.raises(ValueError, match="unsupported_effect_shape"):
        three_arm.archive_parents({"orc": parent, "python": tmp_path / "python"}, config,
                                  evidence_root=tmp_path / "evidence", runtime=REPO, env={}, run_seed=0, subset_seed=0)


def test_judge_keeps_incident_when_bound_recompile_crashes(tmp_path, monkeypatch):
    parent, child = pair(tmp_path)
    accepted = CompileOutcome("accepted", "build", "digest", ())
    diagnostic = {"code": "compiler_crash", "message": "later compilation failed", "notes": ["retained"]}
    outcomes = iter([accepted, accepted, CompileOutcome("rejected", None, None, (diagnostic,))])
    monkeypatch.setattr(acceptance, "compile_candidate", lambda *a, **k: next(outcomes))
    monkeypatch.setattr(acceptance, "closed_program", lambda *a: {
        "params": [], "result": "String", "definitions": {}, "types": {},
        "body": {"k": "halt", "value": {"k": "lit", "v": "x"}}})
    verdict = acceptance.judge_child(parent, child, cfg(), runtime=REPO)
    assert verdict["outcome"] == "incident"
    assert verdict["diagnostics"] == [diagnostic]
    assert "refusal_code" not in verdict
