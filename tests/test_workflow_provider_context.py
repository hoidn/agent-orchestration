"""Runtime characterization for the future ordinary provider-context map."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.exceptions import WorkflowValidationError
from orchestrator.providers.executor import ProviderExecutionResult, ProviderExecutor
from orchestrator.providers.portable_context import PORTABLE_CONTEXT_V1_DESCRIPTOR
from orchestrator.state import StateManager
from orchestrator.workflow.elaboration import elaborate_surface_workflow
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.lowering import build_loaded_workflow_bundle
from orchestrator.workflow.type_descriptor import transport_schema_for_descriptor


_ANSWER_DESCRIPTOR = {
    "kind": "record",
    "name": "Answer",
    "fields": [
        {
            "name": "answer",
            "type": {"kind": "primitive", "name": "String"},
        }
    ],
}


class _PostCommitInterruption(BaseException):
    pass


def _portable_context() -> dict[str, object]:
    return {
        "schema": "portable-context.v1",
        "events": [
            {
                "variant": "TASK",
                "origin": {"variant": "AUTHORED", "label": "seed"},
                "sequence": 0,
                "text": "prior task",
            }
        ],
        "coverage": [
            {
                "origin": {"variant": "AUTHORED", "label": "seed"},
                "scope": "authored",
                "retained_kinds": ["TASK"],
                "omitted_kinds": [],
                "conversions": [],
            }
        ],
        "lineage": [],
    }


def _settled_codex_stdout() -> bytes:
    return b"\n".join(
        json.dumps(event, sort_keys=True).encode("utf-8")
        for event in (
            {"type": "thread.started", "thread_id": "thread-1"},
            {"type": "turn.started"},
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "id": "message-1",
                    "text": "fresh answer",
                },
            },
            {"type": "turn.completed"},
        )
    )


def _bundle(
    *,
    input_context: bool,
    capture_context: bool,
    result_schema: dict[str, object] | None = None,
    result_descriptor: dict[str, object] | None = None,
    provider: str = "codex",
    workflow_path: Path = Path("provider-context-runtime.yaml"),
    downstream: bool = False,
    nested: bool = False,
    with_consume: bool = False,
):
    result_descriptor = _ANSWER_DESCRIPTOR if result_descriptor is None else result_descriptor
    provider_context: dict[str, object] = {}
    if input_context:
        provider_context["input"] = {"ref": "inputs.history"}
    if capture_context:
        provider_context.update(
            {
                "capture": "portable",
                "result_descriptor": result_descriptor,
            }
        )
    answer_schema = result_schema or transport_schema_for_descriptor(
        result_descriptor,
        allow_nested_structures=True,
    )
    step: dict[str, object] = {
        "name": "Ask",
        "provider": provider,
        "output_bundle": {
            "path": "state/provider-result.json",
            "fields": [
                {"name": "__result__", "json_pointer": "", **answer_schema}
            ],
        },
    }
    if provider_context:
        step["provider_context"] = provider_context
    if with_consume:
        step["consumes"] = [
            {
                "artifact": "seed",
                "producers": ["Seed"],
                "policy": "latest_successful",
                "freshness": "any",
            }
        ]
    steps: list[dict[str, object]] = [step]
    if with_consume:
        steps.insert(
            0,
            {
                "name": "Seed",
                "set_scalar": {"artifact": "seed", "value": "seed"},
                "publishes": [{"artifact": "seed", "from": "seed"}],
            },
        )
    if nested:
        steps = [{"name": "Each", "for_each": {"items": ["only"], "steps": [step]}}]
    elif downstream:
        steps.append({"name": "Downstream", "command": ["bash", "-lc", "true"]})
    surface = elaborate_surface_workflow(
        {
            "version": "2.31",
            "name": "provider-context-runtime",
            "artifacts": (
                {"seed": {"kind": "scalar", "type": "string"}}
                if with_consume
                else {}
            ),
            "inputs": {
                "history": transport_schema_for_descriptor(
                    PORTABLE_CONTEXT_V1_DESCRIPTOR,
                    allow_nested_structures=True,
                )
            },
            "steps": steps,
        },
        workflow_path=workflow_path,
        imported_bundles={},
    )
    assert surface is not None
    return build_loaded_workflow_bundle(surface, imports={})


def _run(
    tmp_path: Path,
    *,
    input_context: bool,
    capture_context: bool,
    raw_stdout: bytes | None = None,
    run_id: str = "provider-context-runtime",
    result_schema: dict[str, object] | None = None,
    result_descriptor: dict[str, object] | None = None,
    model_json: str = '{"answer": "fresh"}',
    provider: str = "codex",
    downstream: bool = False,
    nested: bool = False,
    with_consume: bool = False,
):
    workflow_path = tmp_path / "provider-context-runtime.yaml"
    workflow_path.write_text(
        "{}\n", encoding="utf-8"
    )
    manager = StateManager(workspace=tmp_path, run_id=run_id)
    manager.initialize(
        str(workflow_path),
        bound_inputs={"history": _portable_context()},
    )
    executor = WorkflowExecutor(
        _bundle(
            input_context=input_context,
            capture_context=capture_context,
            result_schema=result_schema,
            result_descriptor=result_descriptor,
            provider=provider,
            workflow_path=workflow_path,
            downstream=downstream,
            nested=nested,
            with_consume=with_consume,
        ),
        tmp_path,
        manager,
        retry_delay_ms=0,
    )
    calls: list[dict[str, object]] = []

    def prepare(_self, **kwargs):
        calls.append(dict(kwargs))
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(model_json, encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"provider output",
            stderr=b"",
            duration_ms=1,
            raw_stdout=raw_stdout,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ):
        state = executor.execute(on_error="stop")
    return state, calls


@pytest.mark.parametrize(("schema", "model", "expected"), [
    ({"type": "bool"}, "true", True),
    ({"type": "bool"}, '"false"', False),
    ({
        "type": "union", "union_name": "Choice",
        "discriminant": {"name": "variant", "type": "enum", "allowed": ["YES", "NO"]},
        "variants": {
            "YES": {"fields": [{"name": "score", "type": "integer"}]},
            "NO": {"fields": []},
        },
    }, '{"variant":"YES","score":3}', {"variant": "YES", "score": 3}),
    ({
        "type": "record", "record_name": "Collision", "fields": [
            {"name": "a__b", "type": "string"},
            {"name": "a", "type": "record", "record_name": "Nested", "fields": [
                {"name": "b", "type": "bool"},
            ]},
        ],
    }, '{"a__b":"flat","a":{"b":true}}', {"a__b": "flat", "a": {"b": True}}),
])
def test_capture_preserves_validated_model_roots(tmp_path, schema, model, expected):
    from orchestrator.workflow.type_descriptor import transport_descriptor_for_schema

    state, calls = _run(
        tmp_path, input_context=False, capture_context=True,
        raw_stdout=_settled_codex_stdout(),
        result_descriptor=transport_descriptor_for_schema(schema), model_json=model,
    )

    assert len(calls) == 1
    assert state["status"] == "completed"
    assert state["steps"]["Ask"]["artifacts"]["result"] == expected


@pytest.mark.parametrize("model", [
    '{"answer":"false"}', '{}', '{"answer":false,"extra":0}',
])
def test_capture_rejects_invalid_structural_model_without_a_pair(tmp_path, model):
    descriptor = {
        "kind": "record", "name": "Answer", "fields": [
            {"name": "answer", "type": {"kind": "primitive", "name": "Bool"}},
        ],
    }
    state, calls = _run(
        tmp_path, input_context=False, capture_context=True,
        raw_stdout=_settled_codex_stdout(), result_descriptor=descriptor, model_json=model,
    )

    assert len(calls) == 1
    assert state["status"] == "failed"
    assert not state["steps"]["Ask"].get("artifacts")


@pytest.mark.parametrize("value", ["artifacts/evidence.txt", "artifacts/missing.txt", "../escape.txt"])
def test_capture_checks_nested_paths_before_publication(tmp_path, value):
    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/evidence.txt").write_text("evidence", encoding="utf-8")
    descriptor = {
        "kind": "record", "name": "Evidence", "fields": [{
            "name": "files", "type": {"kind": "list", "item": {
                "kind": "path", "name": "EvidencePath", "under": "artifacts",
                "must_exist_target": True,
            }},
        }],
    }

    state, calls = _run(
        tmp_path, input_context=False, capture_context=True,
        raw_stdout=_settled_codex_stdout(), result_descriptor=descriptor,
        model_json=json.dumps({"files": [value]}),
    )

    assert len(calls) == 1
    if value == "artifacts/evidence.txt":
        assert state["status"] == "completed"
        assert state["steps"]["Ask"]["artifacts"]["result"] == {"files": [value]}
    else:
        assert state["status"] == "failed"
        assert not state["steps"]["Ask"].get("artifacts")


def test_capture_enforces_combined_pair_size_not_just_member_sizes(tmp_path, monkeypatch):
    import orchestrator.workflow.type_descriptor as transport

    model = "x" * 2000
    args = {
        "input_context": False, "capture_context": True,
        "raw_stdout": _settled_codex_stdout(),
        "result_descriptor": {"kind": "primitive", "name": "String"},
        "model_json": json.dumps(model),
    }
    baseline, _ = _run(tmp_path, **args)
    assert baseline["status"] == "completed"
    pair = baseline["steps"]["Ask"]["artifacts"]

    def size(value):
        return len(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode())

    member_limit = max(size(member) for member in pair.values()) + 32
    assert size(pair) > member_limit
    monkeypatch.setattr(transport, "MAX_TRANSPORT_VALUE_BYTES", member_limit)

    state, calls = _run(tmp_path, run_id="capture-budget", **args)

    assert len(calls) == 1
    assert state["status"] == "failed"
    assert state["steps"]["Ask"]["error"]["type"] == "provider_context_capture_failed"
    assert not state["steps"]["Ask"].get("artifacts")


def test_capture_accounts_for_wrapper_depth(tmp_path):
    from orchestrator.workflow.type_descriptor import MAX_TRANSPORT_VALUE_DEPTH, validate_transport_value

    descriptor = {"kind": "primitive", "name": "Value"}
    model = "leaf"
    for _ in range(MAX_TRANSPORT_VALUE_DEPTH):
        model = [model]
    assert validate_transport_value(model, descriptor) == model

    state, calls = _run(
        tmp_path, input_context=False, capture_context=True,
        raw_stdout=_settled_codex_stdout(), result_descriptor=descriptor,
        model_json=json.dumps(model),
    )

    assert len(calls) == 1
    assert state["status"] == "failed"
    assert state["steps"]["Ask"]["error"]["type"] == "provider_context_capture_failed"
    assert not state["steps"]["Ask"].get("artifacts")


def test_provider_context_input_is_included_in_the_actual_invocation(tmp_path: Path) -> None:
    state, calls = _run(
        tmp_path,
        input_context=True,
        capture_context=False,
    )

    assert state["status"] == "completed"
    assert len(calls) == 1
    prompt = calls[0]["prompt_content"]
    assert isinstance(prompt, str)
    assert json.dumps(_portable_context(), sort_keys=True, separators=(",", ":")) in prompt


def test_provider_context_capture_replaces_model_artifacts_with_one_typed_pair(
    tmp_path: Path,
) -> None:
    state, calls = _run(
        tmp_path,
        input_context=False,
        capture_context=True,
        raw_stdout=_settled_codex_stdout(),
    )

    assert len(calls) == 1
    assert state["status"] == "completed"
    artifacts = state["steps"]["Ask"]["artifacts"]
    assert artifacts["result"] == {"answer": "fresh"}
    assert artifacts["context"]["schema"] == "portable-context.v1"
    assert artifacts["context"]["events"][0]["variant"] == "TASK"
    assert artifacts["context"]["events"][1]["variant"] == "ASSISTANT"
    assert set(artifacts) == {"result", "context"}


def test_provider_context_input_then_capture_preserves_one_seed_and_one_new_turn(
    tmp_path: Path,
) -> None:
    state, calls = _run(
        tmp_path,
        input_context=True,
        capture_context=True,
        raw_stdout=_settled_codex_stdout(),
    )

    assert len(calls) == 1
    captured = state["steps"]["Ask"]["artifacts"]["context"]
    assert [event["variant"] for event in captured["events"]] == [
        "TASK",
        "TASK",
        "ASSISTANT",
    ]
    assert [event.get("text") for event in captured["events"]].count("prior task") == 1
    assert "orchestrator-portable-context" not in captured["events"][1]["text"]
    assert captured["lineage"] == [{
        "operation": "bind-as-quoted-json",
        "sources": [row["origin"] for row in _portable_context()["coverage"]],
        "loss": [],
    }]


def test_nested_provider_context_capture_uses_the_existing_atomic_loop_finalizer(
    tmp_path: Path,
) -> None:
    with patch.object(
        StateManager,
        "update_loop_step",
        side_effect=AssertionError("nested result was written outside the finalizer"),
    ):
        state, calls = _run(
            tmp_path,
            input_context=False,
            capture_context=True,
            raw_stdout=_settled_codex_stdout(),
            nested=True,
        )

    assert len(calls) == 1
    assert state["status"] == "completed"
    assert state["steps"]["Each"][0]["Ask"]["artifacts"]["result"] == {
        "answer": "fresh"
    }


def test_provider_context_capture_failure_publishes_no_model_half(
    tmp_path: Path,
) -> None:
    state, calls = _run(
        tmp_path,
        input_context=False,
        capture_context=True,
        raw_stdout=b"{not-json}\n",
    )

    assert len(calls) == 1
    assert state["status"] == "failed"
    failed = state["steps"]["Ask"]
    assert failed["error"]["type"] == "provider_context_capture_failed"
    assert "artifacts" not in failed


def test_provider_context_capture_commits_consumption_with_the_typed_pair(
    tmp_path: Path,
) -> None:
    state, calls = _run(
        tmp_path,
        input_context=False,
        capture_context=True,
        raw_stdout=_settled_codex_stdout(),
        with_consume=True,
    )

    assert len(calls) == 1
    assert state["steps"]["Ask"]["artifacts"]["result"] == {"answer": "fresh"}
    assert state["artifact_consumes"]["root.ask"] == {"seed": 1}


def test_provider_context_capture_precommit_failure_leaves_no_consume_half(
    tmp_path: Path,
) -> None:
    workflow_path = tmp_path / "provider-context-runtime.yaml"
    workflow_path.write_text("{}\n", encoding="utf-8")
    manager = StateManager(workspace=tmp_path, run_id="capture-consume-precommit")
    manager.initialize(str(workflow_path), bound_inputs={"history": _portable_context()})
    executor = WorkflowExecutor(
        _bundle(
            input_context=False,
            capture_context=True,
            workflow_path=workflow_path,
            with_consume=True,
        ),
        tmp_path,
        manager,
        retry_delay_ms=0,
    )

    def prepare(_self, **kwargs):
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps({"answer": "fresh"}), encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"provider output",
            stderr=b"",
            duration_ms=1,
            raw_stdout=_settled_codex_stdout(),
        )

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(
        StateManager,
        "finalize_step_with_dataflow",
        side_effect=TimeoutError("precommit rejected"),
    ), pytest.raises(TimeoutError, match="precommit rejected"):
        executor.execute(on_error="stop")

    persisted = StateManager(
        workspace=tmp_path,
        run_id="capture-consume-precommit",
    ).load().to_dict()
    assert "Ask" not in persisted["artifact_consumes"]
    assert "Ask" not in persisted["steps"]


def test_provider_context_capture_rejects_a_nonmatching_root_schema_prelaunch(
    tmp_path: Path,
) -> None:
    with pytest.raises(WorkflowValidationError, match="disagrees with result_descriptor"):
        _bundle(
            input_context=False,
            capture_context=True,
            result_schema={"type": "string"},
            workflow_path=tmp_path / "provider-context-runtime.yaml",
        )


def test_provider_context_capture_rejects_an_unsupported_adapter_prelaunch(
    tmp_path: Path,
) -> None:
    state, calls = _run(
        tmp_path,
        input_context=False,
        capture_context=True,
        raw_stdout=_settled_codex_stdout(),
        provider="codex_unrestricted_workspace",
    )

    assert calls == []
    assert state["status"] == "failed"
    assert state["steps"]["Ask"]["error"]["context"]["reason"] == (
        "portable_context_adapter_unsupported"
    )


def test_provider_context_absence_keeps_the_existing_result_artifact_shape(
    tmp_path: Path,
) -> None:
    state, calls = _run(
        tmp_path,
        input_context=False,
        capture_context=False,
    )

    assert len(calls) == 1
    assert calls[0]["session_request"] is None
    assert state["status"] == "completed"
    assert state["steps"]["Ask"]["artifacts"] == {"__result__": {"answer": "fresh"}}


def test_post_commit_capture_interruption_resumes_downstream_without_provider_replay(
    tmp_path: Path,
) -> None:
    run_id = "captured-provider-interruption"
    workflow_path = tmp_path / "provider-context-runtime.yaml"
    workflow_path.write_text("{}\n", encoding="utf-8")
    manager = StateManager(workspace=tmp_path, run_id=run_id)
    manager.initialize(str(workflow_path), bound_inputs={"history": _portable_context()})
    executor = WorkflowExecutor(
        _bundle(
            input_context=False,
            capture_context=True,
            workflow_path=workflow_path,
            downstream=True,
        ),
        tmp_path,
        manager,
        retry_delay_ms=0,
    )
    calls: list[dict[str, object]] = []

    def prepare(_self, **kwargs):
        calls.append(dict(kwargs))
        return SimpleNamespace(input_mode="stdin", env=kwargs["env"]), None

    def execute(_self, invocation, **_kwargs):
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps({"answer": "fresh"}), encoding="utf-8")
        return ProviderExecutionResult(
            exit_code=0,
            stdout=b"provider output",
            stderr=b"",
            duration_ms=1,
            raw_stdout=_settled_codex_stdout(),
        )

    original_finalize = StateManager.finalize_step_with_dataflow
    interrupted = False

    def interrupt_after_capture_commit(self, step_name, *args, **kwargs):
        nonlocal interrupted
        original_finalize(self, step_name, *args, **kwargs)
        if step_name == "Ask" and not interrupted:
            interrupted = True
            raise _PostCommitInterruption

    with patch.object(ProviderExecutor, "prepare_invocation", prepare), patch.object(
        ProviderExecutor, "execute", execute
    ), patch.object(
        StateManager,
        "finalize_step_with_dataflow",
        interrupt_after_capture_commit,
    ), pytest.raises(_PostCommitInterruption):
        executor.execute(on_error="stop")

    assert len(calls) == 1
    resume_manager = StateManager(workspace=tmp_path, run_id=run_id)
    committed_pair = resume_manager.load().to_dict()["steps"]["Ask"]["artifacts"]
    resumed_executor = WorkflowExecutor(
        _bundle(
            input_context=False,
            capture_context=True,
            workflow_path=workflow_path,
            downstream=True,
        ),
        tmp_path,
        resume_manager,
        retry_delay_ms=0,
    )

    with patch.object(
        ProviderExecutor,
        "prepare_invocation",
        side_effect=AssertionError("completed provider was replayed"),
    ):
        resumed = resumed_executor.execute(resume=True, on_error="stop")

    assert resumed["status"] == "completed"
    assert resumed["steps"]["Ask"]["artifacts"] == committed_pair
    assert resumed["steps"]["Downstream"]["status"] == "completed"
