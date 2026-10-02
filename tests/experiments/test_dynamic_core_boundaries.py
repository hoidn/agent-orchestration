"""DC-1b real leaf-boundary contract, frozen as E01a–E12b."""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "experiments" / "dynamic_core_evaluation" / "fixtures"


def _lit(value):
    return {"k": "lit", "v": value}


def _name(name):
    return {"k": "name", "n": name}


def _field(base, name):
    return {"k": "field", "base": base, "name": name}


def _record(**fields):
    return {"k": "record", "fields": [[key, node] for key, node in fields.items()]}


def _effect(operation, **fields):
    return {"k": "effect", "name": operation, "inputs": _record(**fields)}


def _artifact(body, *, effects, definitions=None, budget=500):
    defs = {
        "entry": {"params": ["unused"], "captures": [], "body": body},
        "identity": {"params": ["item"], "captures": [], "body": _name("item")},
    }
    defs.update(definitions or {})
    return json.dumps({
        "schema": "workflow-lisp/dynamic-spike/2",
        "entry": "entry",
        "budget": budget,
        "schemas": {
            "input": {"kind": "primitive", "name": "Int"},
            "result": {"kind": "primitive", "name": "Value"},
        },
        "inputs": [["unused", "input"]],
        "result": "result",
        "effects": list(effects),
        "definitions": defs,
    })


def _workspace(tmp_path, monkeypatch):
    workspace = tmp_path / "workspace"
    shutil.copytree(FIXTURES, workspace / "experiments/dynamic_core_evaluation/fixtures")
    (workspace / "docs").mkdir()
    (workspace / "docs/target.txt").write_text("DOC_A: reviewed boundary evidence\n", encoding="utf-8")
    dispatch_log = workspace / "dispatch.jsonl"
    monkeypatch.setenv("DYNAMIC_CORE_DISPATCH_LOG", str(dispatch_log))
    monkeypatch.delenv("DYNAMIC_CORE_FIRST_PATH_LOG", raising=False)
    monkeypatch.delenv("DYNAMIC_CORE_REPLACE_PATH_LOG", raising=False)
    return workspace, dispatch_log


def _bridge(workspace, operations=None):
    from orchestrator.providers.types import InputMode, ProviderTemplate
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
    from experiments.dynamic_core_evaluation.leaf_bridge import LeafBridge

    fixture_dir = workspace / "experiments/dynamic_core_evaluation/fixtures"
    command = ("python", "experiments/dynamic_core_evaluation/fixtures/scripted_leaf.py", "command")
    return LeafBridge.compile(
        fixture_dir / "leaf.orc",
        workspace,
        operations or {"review": "leaf::review", "annotate": "leaf::annotate"},
        provider_externs={"providers.review": "dynamic-fixture"},
        command_boundaries={"annotate": ExternalToolBinding(name="annotate", stable_command=command)},
        provider_templates=(ProviderTemplate(
            name="dynamic-fixture",
            command=[sys.executable, str(fixture_dir / "scripted_leaf.py"), "provider"],
            input_mode=InputMode.STDIN,
        ),),
    )


def _evaluate(artifact, bridge, *, inputs=None, read_only=False):
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    return evaluate(
        DynamicProgram.from_artifact(artifact),
        inputs or {"unused": 1},
        leaf_bridge=bridge,
        read_only=read_only,
    )


def _dispatches(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _bundle_path(workspace, row):
    path = Path(row["bundle"])
    return path if path.is_absolute() else workspace / path


def _review_inputs(goal="draft risks", rubric="clarity", target_doc="docs/target.txt"):
    return {
        "goal": _lit(goal),
        "rubric": _lit(rubric),
        "target_doc": _lit(target_doc),
    }


def test_E01a_provider_leaf_can_select_and_invoke_an_ordinary_closure(tmp_path, monkeypatch):
    """The checked Bool result selects which lexical closure is called."""

    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    reviewed = _name("reviewed")
    feedback = _field(reviewed, "return__feedback")
    selected = {
        "k": "if",
        "cond": _field(reviewed, "return__approved"),
        "then": {"k": "fn", "code": "accepted", "captures": [feedback]},
        "else": {"k": "fn", "code": "rejected", "captures": [feedback]},
    }
    body = {
        "k": "let",
        "bindings": [["reviewed", _effect("review", **_review_inputs(goal="reject draft"))]],
        "body": {"k": "call", "callee": selected, "args": []},
    }
    definitions = {
        "accepted": {
            "params": [], "captures": ["message"],
            "body": {"k": "record", "fields": [["path", _lit("accepted")], ["message", _name("message")]]},
        },
        "rejected": {
            "params": [], "captures": ["message"],
            "body": {"k": "record", "fields": [["path", _lit("rejected")], ["message", _name("message")]]},
        },
    }

    result = _evaluate(_artifact(body, effects=("review",), definitions=definitions), bridge)

    assert result.json_value() == {
        "path": "rejected",
        "message": "reject draft|clarity|DOC_A",
    }
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider"]


def test_E09a_leaf_input_contracts_refuse_bad_values_before_launch(tmp_path, monkeypatch):
    """Actual compiled scalar/list/union contracts reject before the command starts."""

    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"check-inputs": "leaf::check-inputs"})
    valid = {
        "flag": _lit(True),
        "number": _lit(3),
        "ratio": _lit(3),
        "items": {"k": "list", "items": [_record(count=_lit(7))]},
        "decisions": {"k": "list", "items": [_record(variant=_lit("ACCEPTED"), confidence=_lit(2))]},
    }
    invalid_vectors = []
    for missing in ("number",):
        invalid_vectors.append({name: value for name, value in valid.items() if name != missing})
    invalid_vectors.append({**valid, "extra": _lit("unexpected")})
    invalid_vectors.append({**valid, "number": _lit(True)})
    invalid_vectors.append({**valid, "number": _lit("3")})
    invalid_vectors.append({**valid, "ratio": _lit("3.0")})
    invalid_vectors.append({**valid, "items": {"k": "list", "items": [_record(count=_lit("7"))]}})
    invalid_vectors.append({**valid, "decisions": {"k": "list", "items": [_record(variant=_lit("ACCEPTED"), confidence=_lit(2), reason=_lit("inactive"))]}})
    invalid_vectors.append({**valid, "ratio": {"k": "fn", "code": "identity", "captures": []}})

    for values in invalid_vectors:
        body = _effect("check-inputs", **values)
        with pytest.raises(ValueError) as caught:
            _evaluate(_artifact(body, effects=("check-inputs",)), bridge)
        assert getattr(caught.value, "code", None) == "dynamic_boundary_invalid"
    assert _dispatches(dispatch_log) == []

    result = _evaluate(_artifact(_effect("check-inputs", **valid), effects=("check-inputs",)), bridge)
    assert result.json_value()["return__feedback"] == "3.0"
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["command"]


def test_E01b_command_result_uses_the_same_closure_boundary(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"annotate": "leaf::annotate"})
    body = {
        "k": "let",
        "bindings": [["annotated", _effect("annotate", feedback=_lit("command-value"))]],
        "body": {
            "k": "call",
            "callee": {
                "k": "if",
                "cond": _field(_name("annotated"), "return__approved"),
                "then": {"k": "fn", "code": "use", "captures": [_field(_name("annotated"), "return__feedback")]},
                "else": {"k": "fn", "code": "fallback", "captures": [_field(_name("annotated"), "return__feedback")]},
            },
            "args": [],
        },
    }
    defs = {
        "use": {"params": [], "captures": ["value"], "body": _name("value")},
        "fallback": {"params": [], "captures": ["value"], "body": _lit("unexpected")},
    }
    result = _evaluate(_artifact(body, effects=("annotate",), definitions=defs), bridge)
    assert result.json_value() == "command-value"
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["command"]


def test_E02a_validated_record_is_captured_stored_passed_and_used_by_second_leaf(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace)
    callback = {"k": "fn", "code": "continue", "captures": [_name("reviewed")]}
    body = {
        "k": "let",
        "bindings": [["reviewed", _effect("review", **_review_inputs(goal="capture this"))]],
        "body": {
            "k": "let",
            "bindings": [["continuation", callback]],
            "body": {"k": "call", "callee": {"k": "fn", "code": "apply", "captures": []}, "args": [_name("continuation")]},
        },
    }
    defs = {
        "continue": {
            "params": [], "captures": ["snapshot"],
            "body": _effect("annotate", feedback=_field(_name("snapshot"), "return__feedback")),
        },
        "apply": {
            "params": ["callback"], "captures": [],
            "body": {"k": "call", "callee": _name("callback"), "args": []},
        },
    }
    result = _evaluate(_artifact(body, effects=("review", "annotate"), definitions=defs), bridge)
    assert result.json_value()["return__feedback"] == "capture this|clarity|DOC_A"
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider", "command"]


def test_E02b_tagged_result_snapshot_survives_shadowing_and_later_leaf_write(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    first_path_log = workspace / "first-paths.txt"
    monkeypatch.setenv("DYNAMIC_CORE_FIRST_PATH_LOG", str(first_path_log))
    monkeypatch.setenv("DYNAMIC_CORE_REPLACE_PATH_LOG", str(first_path_log))
    bridge = _bridge(workspace)
    decision = {
        "k": "at",
        "base": _field(_name("snapshot"), "return__decisions"),
        "index": _lit(0),
    }
    callback = {"k": "fn", "code": "continue", "captures": [_name("reviewed")]}
    body = {
        "k": "let",
        "bindings": [["reviewed", _effect("review", **_review_inputs(goal="snapshot tag"))]],
        "body": {
            "k": "let",
            "bindings": [["continuation", callback]],
            "body": {
                "k": "let",
                "bindings": [["reviewed", _record(return__feedback=_lit("shadow"))]],
                "body": {"k": "call", "callee": _name("continuation"), "args": []},
            },
        },
    }
    defs = {
        "continue": {
            "params": [], "captures": ["snapshot"],
            "body": {
                "k": "let",
                "bindings": [["second", _effect("annotate", feedback=_lit("after-tagged-effect"))]],
                "body": _record(
                    tag=_field(decision, "variant"),
                    feedback=_field(_name("second"), "return__feedback"),
                ),
            },
        },
    }
    result = _evaluate(_artifact(body, effects=("review", "annotate"), definitions=defs), bridge)
    assert result.json_value() == {"tag": "ACCEPTED", "feedback": "after-tagged-effect"}
    original_path = Path(first_path_log.read_text(encoding="utf-8").splitlines()[0])
    assert json.loads(original_path.read_text(encoding="utf-8")) == {"replaced": True}
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider", "command"]


def test_E03a_pre_action_failure_dispatches_nothing_then_fresh_entry_runs(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    invalid = _effect("review", goal=_lit("missing other inputs"))
    with pytest.raises(ValueError) as caught:
        _evaluate(_artifact(invalid, effects=("review",)), bridge)
    assert caught.value.code == "dynamic_boundary_invalid"
    assert _dispatches(dispatch_log) == []

    valid = _effect("review", **_review_inputs(goal="fresh entry"))
    result = _evaluate(_artifact(valid, effects=("review",)), bridge)
    assert result.json_value()["return__feedback"] == "fresh entry|clarity|DOC_A"
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider"]


def test_E03b_failure_after_first_action_keeps_effect_and_fresh_run_repeats_it(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace)
    body = {
        "k": "let",
        "bindings": [["reviewed", _effect("review", **_review_inputs(goal="first action"))]],
        "body": _effect("annotate", feedback=_lit("fail-after-write")),
    }
    artifact = _artifact(body, effects=("review", "annotate"))
    for _ in range(2):
        with pytest.raises(ValueError) as caught:
            _evaluate(artifact, bridge)
        assert caught.value.code == "dynamic_effect_failed"
    rows = _dispatches(dispatch_log)
    assert [row["mode"] for row in rows] == ["provider", "command", "provider", "command"]
    failed_command_bundle = _bundle_path(workspace, rows[1])
    assert failed_command_bundle.exists()
    assert json.loads(failed_command_bundle.read_text(encoding="utf-8"))["feedback"] == "fail-after-write"


def test_E04a_unknown_and_unlinked_leaf_references_fail_before_dispatch(tmp_path, monkeypatch):
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    unreachable = _artifact(
        _effect("review", **_review_inputs()),
        effects=("review",),
        definitions={"unreachable": {"params": [], "captures": [], "body": _effect("ghost")}},
    )
    with pytest.raises(ValueError) as invalid:
        DynamicProgram.from_artifact(unreachable)
    assert invalid.value.code == "dynamic_spike_invalid"

    unlinked = _artifact(_effect("ghost"), effects=("ghost",))
    with pytest.raises(ValueError) as link_error:
        _evaluate(unlinked, bridge)
    assert link_error.value.code == "dynamic_effect_unlinked"
    assert _dispatches(dispatch_log) == []


def test_E04b_failed_leaf_has_call_context_without_boundary_values(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    body = {"k": "call", "callee": {"k": "fn", "code": "dispatch", "captures": [_lit("TOPSECRET") ]}, "args": []}
    defs = {
        "dispatch": {
            "params": [], "captures": ["secret"],
            "body": _effect("review", goal=_lit("bad-bool"), rubric=_name("secret"), target_doc=_lit("docs/target.txt")),
        },
    }
    with pytest.raises(ValueError) as caught:
        _evaluate(_artifact(body, effects=("review",), definitions=defs), bridge)
    assert caught.value.code == "dynamic_effect_failed"
    frames = caught.value.metadata["call_context"]
    assert frames[-1][2] == "dispatch"
    assert caught.value.metadata["leaf_run_id"]
    assert "TOPSECRET" not in str(caught.value.metadata)
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider"]


def test_E05a_budget_exhaustion_during_effect_arguments_prevents_launch(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    body = _effect("review", **_review_inputs())
    with pytest.raises(ValueError) as caught:
        _evaluate(_artifact(body, effects=("review",), budget=3), bridge)
    assert caught.value.code == "dynamic_budget_exhausted"
    assert caught.value.metadata["steps"] == 3
    assert _dispatches(dispatch_log) == []


def test_E05b_effect_does_not_reset_budget_and_fresh_call_gets_new_budget(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"annotate": "leaf::annotate"})
    body = {
        "k": "let",
        "bindings": [["result", _effect("annotate", feedback=_lit("budget proof"))]],
        "body": _field(_name("result"), "return__feedback"),
    }
    artifact = _artifact(body, effects=("annotate",), budget=4)
    for _ in range(2):
        with pytest.raises(ValueError) as caught:
            _evaluate(artifact, bridge)
        assert caught.value.code == "dynamic_budget_exhausted"
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["command", "command"]


def test_E06a_stale_runtime_bundle_is_cleared_before_missing_result_call(tmp_path, monkeypatch):
    from orchestrator.workflow.executor import WorkflowExecutor

    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    original = WorkflowExecutor._prepare_absent_runtime_output_bundle
    seeded_paths = []

    def seed_then_clear(executor, step, resolved):
        relative = resolved["path"]
        target = executor.workspace / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({
            "approved": True,
            "feedback": "stale",
            "score": 1,
            "evidence": {"count": 1},
            "decisions": [{"variant": "ACCEPTED", "confidence": 1}],
        }), encoding="utf-8")
        seeded_paths.append(target)
        return original(executor, step, resolved)

    monkeypatch.setattr(WorkflowExecutor, "_prepare_absent_runtime_output_bundle", seed_then_clear)
    with pytest.raises(ValueError) as caught:
        _evaluate(_artifact(_effect("review", **_review_inputs(goal="no-file")), effects=("review",)), bridge)
    assert caught.value.code == "dynamic_effect_failed"
    assert len(seeded_paths) == 1 and not seeded_paths[0].exists()
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider"]


def test_E06b_successful_calls_get_distinct_runs_and_result_locations(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    first_path_log = workspace / "first-paths.txt"
    monkeypatch.setenv("DYNAMIC_CORE_FIRST_PATH_LOG", str(first_path_log))
    bridge = _bridge(workspace, {"review": "leaf::review"})
    artifact = _artifact(_effect("review", **_review_inputs(goal="fresh")), effects=("review",))
    results = [_evaluate(artifact, bridge).json_value() for _ in range(2)]
    paths = first_path_log.read_text(encoding="utf-8").splitlines()
    assert results[0] == results[1]
    assert len(paths) == 2 and paths[0] != paths[1]
    assert all(Path(path).is_file() for path in paths)
    assert [str(_bundle_path(workspace, row).resolve()) for row in _dispatches(dispatch_log)] == paths


def test_E07a_changed_ordinary_input_is_bound_on_next_invocation(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    body = _effect("review", goal=_name("goal"), rubric=_lit("clarity"), target_doc=_lit("docs/target.txt"))
    artifact = _artifact(body, effects=("review",))
    # Replace the entry contract with the real String input used by the effect.
    payload = json.loads(artifact)
    payload["schemas"]["input"] = {"kind": "primitive", "name": "String"}
    payload["inputs"] = [["goal", "input"]]
    payload["definitions"]["entry"]["params"] = ["goal"]
    artifact = json.dumps(payload)
    first = _evaluate(artifact, bridge, inputs={"goal": "first goal"}).json_value()
    second = _evaluate(artifact, bridge, inputs={"goal": "changed goal"}).json_value()
    assert first["return__feedback"] == "first goal|clarity|DOC_A"
    assert second["return__feedback"] == "changed goal|clarity|DOC_A"
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider", "provider"]


def test_E07b_changed_document_is_resnapshotted_on_next_invocation(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    artifact = _artifact(_effect("review", **_review_inputs(goal="same goal")), effects=("review",))
    first = _evaluate(artifact, bridge).json_value()
    (workspace / "docs/target.txt").write_text("DOC_B: revised source content\n", encoding="utf-8")
    second = _evaluate(artifact, bridge).json_value()
    assert first["return__feedback"] == "same goal|clarity|DOC_A"
    assert second["return__feedback"] == "same goal|clarity|DOC_B"
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider", "provider"]


def test_E08a_successful_prefix_repeats_after_later_leaf_failure_exactly(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace)
    body = {
        "k": "let",
        "bindings": [["reviewed", _effect("review", **_review_inputs(goal="fail-after"))]],
        "body": _effect("annotate", feedback=_field(_name("reviewed"), "return__feedback")),
    }
    artifact = _artifact(body, effects=("review", "annotate"))
    for _ in range(2):
        with pytest.raises(ValueError) as caught:
            _evaluate(artifact, bridge)
        assert caught.value.code == "dynamic_effect_failed"
    rows = _dispatches(dispatch_log)
    assert [row["mode"] for row in rows] == ["provider", "command", "provider", "command"]
    assert sum(row["mode"] == "provider" for row in rows) == 2


def test_E08b_failed_leaf_keeps_its_output_without_rollback_or_no_repeat_claim(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"annotate": "leaf::annotate"})
    artifact = _artifact(_effect("annotate", feedback=_lit("fail-after-write")), effects=("annotate",))
    for _ in range(2):
        with pytest.raises(ValueError) as caught:
            _evaluate(artifact, bridge)
        assert caught.value.code == "dynamic_effect_failed"
    rows = _dispatches(dispatch_log)
    assert [row["mode"] for row in rows] == ["command", "command"]
    assert rows[0]["bundle"] != rows[1]["bundle"]
    assert all(json.loads(_bundle_path(workspace, row).read_text(encoding="utf-8"))["feedback"] == "fail-after-write" for row in rows)


def test_E09b_raw_results_fail_strictly_and_shared_validation_uses_one_snapshot(tmp_path, monkeypatch):
    from experiments.dynamic_core_evaluation import leaf_bridge as bridge_module

    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    for goal in ("bad-bool", "bad-int", "missing-field", "extra-field", "bad-nested", "inactive-field", "non-finite", "non-finite-json"):
        with pytest.raises(ValueError) as caught:
            _evaluate(_artifact(_effect("review", **_review_inputs(goal=goal)), effects=("review",)), bridge)
        assert caught.value.code == "dynamic_effect_failed"
        state_path = workspace / ".orchestrate/runs" / caught.value.metadata["leaf_run_id"] / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "failed"
        assert state.get("workflow_outputs", {}) == {}
        assert all(not step.get("artifacts") for step in state.get("steps", {}).values())

    # Mutate the runtime-owned path after strict validation; shared validation
    # must consume the same captured bytes and return the original validated value.
    first_path_log = workspace / "race-path.txt"
    monkeypatch.setenv("DYNAMIC_CORE_FIRST_PATH_LOG", str(first_path_log))
    original = bridge_module.validate_transport_value
    replacements = []

    def replace_after_raw_validation(value, descriptor, **kwargs):
        normalized = original(value, descriptor, **kwargs)
        if descriptor.get("name") == "ReviewResult":
            path = Path(first_path_log.read_text(encoding="utf-8").splitlines()[0])
            path.write_text('{"broken":true}', encoding="utf-8")
            replacements.append(path)
        return normalized

    monkeypatch.setattr(bridge_module, "validate_transport_value", replace_after_raw_validation)
    result = _evaluate(_artifact(_effect("review", **_review_inputs(goal="snapshot-safe")), effects=("review",)), bridge)
    assert result.json_value()["return__feedback"] == "snapshot-safe|clarity|DOC_A"
    assert len(replacements) == 1
    assert json.loads(replacements[0].read_text(encoding="utf-8")) == {"broken": True}


def test_E10a_registry_is_closed_and_read_only_closure_cannot_dispatch(tmp_path, monkeypatch):
    from experiments.dynamic_core_evaluation.program import DynamicProgram

    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    extra_bridge = _bridge(workspace, {"review": "leaf::review", "annotate": "leaf::annotate"})
    for operations, selected_bridge in ((('review',), extra_bridge), (('review', 'annotate'), bridge), (('host',), bridge)):
        artifact = _artifact(_effect(operations[0]), effects=operations)
        with pytest.raises(ValueError) as caught:
            _evaluate(artifact, selected_bridge)
        assert caught.value.code == "dynamic_effect_unlinked"

    unreachable = _artifact(
        _lit("done"), effects=("review",),
        definitions={"unreachable": {"params": [], "captures": [], "body": _effect("ghost")} },
    )
    with pytest.raises(ValueError) as invalid:
        DynamicProgram.from_artifact(unreachable)
    assert invalid.value.code == "dynamic_spike_invalid"

    inline = _effect("review", **_review_inputs())
    inline["command"] = ["python", "untrusted.py"]
    with pytest.raises(ValueError) as injected:
        DynamicProgram.from_artifact(_artifact(inline, effects=("review",)))
    assert injected.value.code == "dynamic_spike_invalid"

    with pytest.raises(ValueError) as non_leaf:
        _bridge(workspace, {"forward": "leaf::forward-annotate"})
    assert non_leaf.value.code == "dynamic_effect_unlinked"

    body = {"k": "call", "callee": {"k": "fn", "code": "dispatch", "captures": []}, "args": []}
    defs = {"dispatch": {"params": [], "captures": [], "body": _effect("review", **_review_inputs())}}
    with pytest.raises(ValueError) as forbidden:
        _evaluate(_artifact(body, effects=("review",), definitions=defs), bridge, read_only=True)
    assert forbidden.value.code == "dynamic_effect_forbidden"
    assert _dispatches(dispatch_log) == []

    program = DynamicProgram.from_artifact(_artifact(_lit("safe"), effects=("review",)))
    from experiments.dynamic_core_evaluation.evaluator import evaluate
    with pytest.raises(ValueError) as host_value:
        evaluate(program, {"unused": lambda: None}, leaf_bridge=bridge)
    assert host_value.value.code == "dynamic_boundary_invalid"
    assert _dispatches(dispatch_log) == []


def test_E10b_workspace_paths_refuse_escape_and_symlink_before_launch(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    outside = workspace / "outside.txt"
    outside.write_text("outside\n", encoding="utf-8")
    symlink = workspace / "docs/escape.txt"
    symlink.symlink_to(outside)
    for target in ("../outside.txt", "docs/escape.txt"):
        with pytest.raises(ValueError) as caught:
            _evaluate(_artifact(_effect("review", **_review_inputs(target_doc=target)), effects=("review",)), bridge)
        assert caught.value.code == "dynamic_boundary_invalid"
    assert _dispatches(dispatch_log) == []


def test_E11a_real_prompt_and_document_inputs_reach_provider_from_snapshot(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    document_path = workspace / "docs/target.txt"
    monkeypatch.setenv("DYNAMIC_CORE_MUTATE_DOC_PATH", str(document_path))
    monkeypatch.setenv("DYNAMIC_CORE_MUTATE_DOC_CONTENT", "DOC_B: changed during provider launch\n")
    bridge = _bridge(workspace, {"review": "leaf::review"})
    result = _evaluate(_artifact(_effect("review", **_review_inputs(goal="semantic goal", rubric="specific evidence")), effects=("review",)), bridge)
    assert result.json_value()["return__feedback"] == "semantic goal|specific evidence|DOC_A"
    assert len(_dispatches(dispatch_log)) == 1
    assert document_path.read_text(encoding="utf-8").startswith("DOC_B:")


def test_E11b_required_output_and_valid_handoff_follow_compiled_return_shape(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review-report": "leaf::review-output"})

    def report_inputs(goal):
        return {**_review_inputs(goal=goal), "report": _lit(f"artifacts/review/{goal}.txt")}

    valid = _evaluate(_artifact(_effect("review-report", **report_inputs("out-valid")), effects=("review-report",)), bridge).json_value()
    report_path = workspace / "artifacts/review/out-valid.txt"
    assert valid["return__feedback"].startswith("out-valid|")
    assert report_path.read_text(encoding="utf-8") == "review report\n"

    for goal in ("out-missing", "out-invalid"):
        with pytest.raises(ValueError) as caught:
            _evaluate(_artifact(_effect("review-report", **report_inputs(goal)), effects=("review-report",)), bridge)
        assert caught.value.code == "dynamic_effect_failed"
        state_path = workspace / ".orchestrate/runs" / caught.value.metadata["leaf_run_id"] / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "failed" and state.get("workflow_outputs", {}) == {}
        assert all(not step.get("artifacts") for step in state.get("steps", {}).values())
    assert [row["mode"] for row in _dispatches(dispatch_log)] == ["provider", "provider", "provider"]


def test_E12a_missing_wrong_path_and_stdout_are_not_result_channels(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    for goal in ("no-file", "wrong-path", "stdout-only"):
        with pytest.raises(ValueError) as caught:
            _evaluate(_artifact(_effect("review", **_review_inputs(goal=goal)), effects=("review",)), bridge)
        assert caught.value.code == "dynamic_effect_failed"
    rows = _dispatches(dispatch_log)
    assert len(rows) == 3
    assert all(row["mode"] == "provider" for row in rows)


def test_E12b_malformed_duplicate_and_nonfinite_json_never_publish(tmp_path, monkeypatch):
    workspace, dispatch_log = _workspace(tmp_path, monkeypatch)
    bridge = _bridge(workspace, {"review": "leaf::review"})
    for goal in ("malformed-json", "duplicate-json", "non-finite-json"):
        with pytest.raises(ValueError) as caught:
            _evaluate(_artifact(_effect("review", **_review_inputs(goal=goal)), effects=("review",)), bridge)
        assert caught.value.code == "dynamic_effect_failed"
        assert "approved\":false" not in str(caught.value)
        state_path = workspace / ".orchestrate/runs" / caught.value.metadata["leaf_run_id"] / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "failed" and state.get("workflow_outputs", {}) == {}
        assert all(not step.get("artifacts") for step in state.get("steps", {}).values())
    assert len(_dispatches(dispatch_log)) == 3
