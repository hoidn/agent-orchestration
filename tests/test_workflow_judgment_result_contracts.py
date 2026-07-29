"""Persisted-only result-contract resolution for Q4 judgment views."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from orchestrator.runtime_observability import (
    record_compiled_frontend_provenance,
)
from orchestrator.workflow.judgment_views import (
    JUDGMENT_RESULT_CONTRACT_MISMATCH,
    JUDGMENT_RESULT_COORDINATE_INVALID,
    JudgmentResultContractError,
    resolve_persisted_result_contract,
)
from orchestrator.workflow.persisted_surface import (
    PersistedSurfaceStep,
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    persisted_surface_sha256,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.surface_ast import SurfaceStepKind
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)


_SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.22")
  (defmodule judgment_views/task5_contract_fixture)
  (export orchestrate)
  (defprompt judge (:fills (item :value Int)) -> Int "Return {item}.")
  (defworkflow child ((item Int)) -> Int
    (provider-result providers.worker :prompt (judge :item item)))
  (defworkflow orchestrate ((items List[Int])) -> Int
    (let* ((root_result
             (provider-result providers.worker :prompt (judge :item 1)))
           (mapped
             (list/map-effect ((item items)) :max 3
               (provider-result providers.worker :prompt (judge :item item))))
           (child_result (call child :item root_result)))
      child_result)))
"""


def _fixture(tmp_path: Path) -> dict[str, Any]:
    source = (
        tmp_path
        / "judgment_views"
        / "task5_contract_fixture.orc"
    )
    source.parent.mkdir()
    source.write_text(_SOURCE, encoding="utf-8")
    providers = tmp_path / "providers.json"
    providers.write_text(
        json.dumps({"providers.worker": "test-provider"}),
        encoding="utf-8",
    )
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source,
            source_roots=(tmp_path,),
            entry_workflow="orchestrate",
            provider_externs_path=providers,
            workspace_root=tmp_path,
            lowering_route="wcc_m4",
        )
    )
    graph = decode_persisted_workflow_surface_graph(
        result.artifact_paths["persisted_workflow_surface"].read_bytes()
    )
    entry = graph.entry_node
    root_provider = next(
        step
        for step in entry.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    loop_owner = next(
        step
        for step in entry.steps
        if step.repeat_until is not None
    )
    assert loop_owner.repeat_until is not None
    loop_provider = next(
        step
        for step in _walk_steps(loop_owner.repeat_until.steps)
        if step.kind is SurfaceStepKind.PROVIDER
    )
    call = next(
        step for step in entry.steps if step.kind is SurfaceStepKind.CALL
    )
    assert call.call_alias is not None
    child = graph.imported_node(entry, call.call_alias)
    assert child is not None
    child_provider = next(
        step
        for step in child.steps
        if step.kind is SurfaceStepKind.PROVIDER
    )
    frame_id = f"{call.step_id}::visit::1"
    child_state = {
        "step_visits": {child_provider.name: 1},
        "call_frames": {},
    }
    state: dict[str, Any] = {
        "run_id": "task5-contracts",
        "status": "completed",
        "workflow_file": source.relative_to(tmp_path).as_posix(),
        "workflow_checksum": f"sha256:{result.manifest.source_sha256}",
        "step_visits": {
            root_provider.name: 1,
            loop_owner.name: 1,
        },
        "call_frames": {
            frame_id: {
                "call_frame_id": frame_id,
                "call_step_id": call.step_id,
                "import_alias": call.call_alias,
                "state": child_state,
            }
        },
    }
    record_compiled_frontend_provenance(
        state,
        result.validated_bundle.provenance,
    )
    return {
        "source": source,
        "result": result,
        "state": state,
        "root_provider": root_provider,
        "loop_owner": loop_owner,
        "loop_provider": loop_provider,
        "call": call,
        "child_provider": child_provider,
        "frame_id": frame_id,
    }


def _walk_steps(
    roots: tuple[PersistedSurfaceStep, ...],
) -> tuple[PersistedSurfaceStep, ...]:
    def walk(step: PersistedSurfaceStep) -> tuple[PersistedSurfaceStep, ...]:
        children = [
            *step.for_each_steps,
            *step.then_steps,
            *step.else_steps,
        ]
        for rows in step.match_cases.values():
            children.extend(rows)
        if step.repeat_until is not None:
            children.extend(step.repeat_until.steps)
        return (
            step,
            *(item for child in children for item in walk(child)),
        )

    return tuple(item for root in roots for item in walk(root))


def _scope(fixture: dict[str, Any], kind: str) -> ProviderAttemptScope:
    state = fixture["state"]
    if kind == "root":
        step = fixture["root_provider"]
        frames: list[str] = []
        runtime_step_id = step.step_id
        enclosing = {
            "step_name": step.name,
            "step_id": step.step_id,
            "visit_count": 1,
        }
        loop = None
    elif kind == "child":
        step = fixture["child_provider"]
        frames = [fixture["frame_id"]]
        runtime_step_id = step.step_id
        enclosing = {
            "step_name": step.name,
            "step_id": step.step_id,
            "visit_count": 1,
        }
        loop = None
    else:
        step = fixture["loop_provider"]
        owner = fixture["loop_owner"]
        frames = []
        prefix = f"{owner.step_id}."
        assert step.step_id.startswith(prefix)
        suffix = step.step_id[len(prefix) :]
        runtime_step_id = f"{owner.step_id}#1.{suffix}"
        enclosing = {
            "step_name": owner.name,
            "step_id": owner.step_id,
            "visit_count": 1,
        }
        loop = {
            "kind": "repeat_until",
            "loop_step_id": owner.step_id,
            "iteration": 1,
        }
    return ProviderAttemptScope.from_dict(
        {
            "run_id": state["run_id"],
            "resume_scope": {
                "root_workflow_file": state["workflow_file"],
                "call_frame_ids": frames,
            },
            "runtime_step_id": runtime_step_id,
            "enclosing_step": enclosing,
            "loop_iteration": loop,
            "adjudication_subject": None,
        }
    )


@pytest.mark.parametrize("kind", ("root", "child", "loop"))
def test_persisted_result_contract_resolves_root_child_and_loop_identically_state_only(
    tmp_path: Path,
    kind: str,
) -> None:
    fixture = _fixture(tmp_path)
    scope = _scope(fixture, kind)

    loaded = resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=fixture["state"],
        scope=scope,
    )
    state_only = resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=json.loads(json.dumps(fixture["state"])),
        scope=ProviderAttemptScope.from_dict(
            json.loads(json.dumps(scope.to_dict()))
        ),
    )

    assert loaded == state_only
    assert loaded.declared_shape == "root_value"
    assert loaded.contract_kind == "output_bundle"
    assert loaded.contract_sha256 == persisted_surface_sha256(
        canonical_persisted_surface_bytes(
            {"output_bundle": _thaw(loaded.contract)}
        )
    )


@pytest.mark.parametrize(
    "damage",
    ("missing_anchor", "state_digest", "surface_digest"),
)
def test_persisted_result_contract_rejects_missing_or_digest_invalid_graph(
    tmp_path: Path,
    damage: str,
) -> None:
    fixture = _fixture(tmp_path)
    state = fixture["state"]
    compiled = state["runtime_observability"]["compiled_frontend"]
    if damage == "missing_anchor":
        compiled.pop("persisted_workflow_surface")
    elif damage == "state_digest":
        compiled["persisted_workflow_surface"]["sha256"] = (
            "sha256:" + "0" * 64
        )
    else:
        path = fixture["result"].artifact_paths[
            "persisted_workflow_surface"
        ]
        path.write_bytes(path.read_bytes() + b" ")

    _assert_code(
        JUDGMENT_RESULT_CONTRACT_MISMATCH,
        lambda: resolve_persisted_result_contract(
            workspace_root=tmp_path,
            state=state,
            scope=_scope(fixture, "root"),
        ),
    )


def test_persisted_result_contract_rejects_unknown_call_frame_alias(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture["state"]["call_frames"][fixture["frame_id"]][
        "import_alias"
    ] = "unknown"

    _assert_code(
        JUDGMENT_RESULT_COORDINATE_INVALID,
        lambda: resolve_persisted_result_contract(
            workspace_root=tmp_path,
            state=fixture["state"],
            scope=_scope(fixture, "child"),
        ),
    )


@pytest.mark.parametrize(
    ("contract_kind", "declared_shape"),
    (
        ("output_bundle", "record_value"),
        ("variant_output", "union_value"),
    ),
)
def test_persisted_result_contract_classifies_record_and_union_carriers(
    tmp_path: Path,
    contract_kind: str,
    declared_shape: str,
) -> None:
    fixture = _fixture(tmp_path)
    provider_id = fixture["root_provider"].step_id

    def mutate(payload: dict[str, Any]) -> None:
        entry = payload["nodes"][payload["entry_workflow"]]
        common = _payload_step(entry["steps"], provider_id)["common"]
        if contract_kind == "output_bundle":
            common["output_bundle"]["fields"] = [
                {
                    "name": "approved",
                    "json_pointer": "/approved",
                    "type": "bool",
                }
            ]
            return
        common["output_bundle"] = None
        common["variant_output"] = {
            "path": "result.json",
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": ["APPROVE"],
            },
            "shared_fields": [],
            "variants": {"APPROVE": {"fields": []}},
        }

    _reanchor(fixture, mutate)

    resolved = resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=fixture["state"],
        scope=_scope(fixture, "root"),
    )

    assert resolved.contract_kind == contract_kind
    assert resolved.declared_shape == declared_shape


def test_persisted_union_contract_preserves_allowed_order_across_canonical_map_order(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    provider_id = fixture["root_provider"].step_id

    def mutate(payload: dict[str, Any]) -> None:
        entry = payload["nodes"][payload["entry_workflow"]]
        common = _payload_step(entry["steps"], provider_id)["common"]
        common["output_bundle"] = None
        common["variant_output"] = {
            "path": "result.json",
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": ["REVISE", "APPROVE"],
            },
            "shared_fields": [],
            "variants": {
                "APPROVE": {"fields": []},
                "REVISE": {"fields": []},
            },
        }

    _reanchor(fixture, mutate)

    resolved = resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=fixture["state"],
        scope=_scope(fixture, "root"),
    )

    assert tuple(resolved.contract["discriminant"]["allowed"]) == (
        "REVISE",
        "APPROVE",
    )
    assert set(resolved.contract["variants"]) == {
        "APPROVE",
        "REVISE",
    }


@pytest.mark.parametrize("damage", ("missing", "extra"))
def test_persisted_union_contract_rejects_variant_membership_mismatch(
    tmp_path: Path,
    damage: str,
) -> None:
    fixture = _fixture(tmp_path)
    provider_id = fixture["root_provider"].step_id

    def mutate(payload: dict[str, Any]) -> None:
        entry = payload["nodes"][payload["entry_workflow"]]
        common = _payload_step(entry["steps"], provider_id)["common"]
        variants = {"APPROVE": {"fields": []}}
        if damage == "extra":
            variants["BLOCKED"] = {"fields": []}
        common["output_bundle"] = None
        common["variant_output"] = {
            "path": "result.json",
            "discriminant": {
                "name": "variant",
                "json_pointer": "/variant",
                "type": "enum",
                "allowed": ["APPROVE", "REVISE"],
            },
            "shared_fields": [],
            "variants": variants,
        }

    _reanchor(fixture, mutate)

    _assert_code(
        JUDGMENT_RESULT_CONTRACT_MISMATCH,
        lambda: resolve_persisted_result_contract(
            workspace_root=tmp_path,
            state=fixture["state"],
            scope=_scope(fixture, "root"),
        ),
    )


@pytest.mark.parametrize(
    "damage",
    ("missing", "extra", "ambiguous"),
)
def test_persisted_result_contract_rejects_missing_extra_or_ambiguous_contract(
    tmp_path: Path,
    damage: str,
) -> None:
    fixture = _fixture(tmp_path)
    provider_id = fixture["root_provider"].step_id

    def mutate(payload: dict[str, Any]) -> None:
        entry = payload["nodes"][payload["entry_workflow"]]
        provider = _payload_step(entry["steps"], provider_id)
        if damage == "missing":
            provider["common"]["output_bundle"] = None
        elif damage == "extra":
            provider["common"]["variant_output"] = {
                "path": "result.json",
                "discriminant": {},
                "shared_fields": [],
                "variants": {"ok": {"fields": []}},
            }
        else:
            fields = provider["common"]["output_bundle"]["fields"]
            fields.append(deepcopy(fields[0]))

    _reanchor(fixture, mutate)

    _assert_code(
        JUDGMENT_RESULT_CONTRACT_MISMATCH,
        lambda: resolve_persisted_result_contract(
            workspace_root=tmp_path,
            state=fixture["state"],
            scope=_scope(fixture, "root"),
        ),
    )


@pytest.mark.parametrize(
    "damage",
    ("runtime_step_id", "loop_kind", "loop_step_id", "iteration"),
)
def test_persisted_result_contract_rejects_coordinate_tamper(
    tmp_path: Path,
    damage: str,
) -> None:
    fixture = _fixture(tmp_path)
    payload = _scope(fixture, "loop").to_dict()
    if damage == "runtime_step_id":
        payload["runtime_step_id"] += "-wrong"
    elif damage == "loop_kind":
        payload["loop_iteration"]["kind"] = "for_each"
    elif damage == "loop_step_id":
        payload["loop_iteration"]["loop_step_id"] += "-wrong"
    else:
        payload["loop_iteration"]["iteration"] = 2
    scope = ProviderAttemptScope.from_dict(payload)

    _assert_code(
        JUDGMENT_RESULT_COORDINATE_INVALID,
        lambda: resolve_persisted_result_contract(
            workspace_root=tmp_path,
            state=fixture["state"],
            scope=scope,
        ),
    )


def test_persisted_result_contract_rejects_loop_descendant_outside_owner_identity(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    provider_id = fixture["loop_provider"].step_id
    owner = fixture["loop_owner"]

    def mutate(payload: dict[str, Any]) -> None:
        entry = payload["nodes"][payload["entry_workflow"]]
        provider = _payload_step(entry["steps"], provider_id)
        provider["step_id"] = "detached.provider"

    _reanchor(fixture, mutate)
    scope_payload = _scope(fixture, "loop").to_dict()
    scope_payload["runtime_step_id"] = f"{owner.step_id}#1.provider"

    _assert_code(
        JUDGMENT_RESULT_COORDINATE_INVALID,
        lambda: resolve_persisted_result_contract(
            workspace_root=tmp_path,
            state=fixture["state"],
            scope=ProviderAttemptScope.from_dict(scope_payload),
        ),
    )


def test_persisted_result_contract_ignores_current_source_edit_and_deletion(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    scope = _scope(fixture, "root")
    expected = resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=fixture["state"],
        scope=scope,
    )
    fixture["source"].write_text("not Workflow Lisp\n", encoding="utf-8")
    assert resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=fixture["state"],
        scope=scope,
    ) == expected
    fixture["source"].unlink()
    assert resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=fixture["state"],
        scope=scope,
    ) == expected


@pytest.mark.parametrize("damage", ("state", "manifest"))
def test_persisted_result_contract_rejects_persisted_source_binding_tamper(
    tmp_path: Path,
    damage: str,
) -> None:
    fixture = _fixture(tmp_path)
    if damage == "state":
        fixture["state"]["workflow_checksum"] = "sha256:" + "0" * 64
    else:
        manifest_path = fixture["result"].manifest_path
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["source_sha256"] = "0" * 64
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    _assert_code(
        JUDGMENT_RESULT_COORDINATE_INVALID,
        lambda: resolve_persisted_result_contract(
            workspace_root=tmp_path,
            state=fixture["state"],
            scope=_scope(fixture, "root"),
        ),
    )


def test_persisted_result_contract_never_enters_source_compiler(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _fixture(tmp_path)

    def forbidden(*_args: Any, **_kwargs: Any) -> None:
        raise AssertionError("source compiler was entered")

    for target in (
        "orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint",
        "orchestrator.workflow_lisp.reader.read_sexpr_file",
        "orchestrator.workflow_lisp.syntax.build_syntax_module",
        "orchestrator.workflow_lisp.workflows.elaborate_workflow_definitions",
    ):
        monkeypatch.setattr(target, forbidden)

    resolve_persisted_result_contract(
        workspace_root=tmp_path,
        state=fixture["state"],
        scope=_scope(fixture, "child"),
    )


def _reanchor(
    fixture: dict[str, Any],
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    result = fixture["result"]
    path = result.artifact_paths["persisted_workflow_surface"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    mutate(payload)
    encoded = canonical_persisted_surface_bytes(payload)
    path.write_bytes(encoded)
    digest = persisted_surface_sha256(encoded)
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    manifest["persisted_workflow_surface"]["sha256"] = digest
    result.manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    fixture["state"]["runtime_observability"]["compiled_frontend"][
        "persisted_workflow_surface"
    ]["sha256"] = digest


def _payload_step(
    roots: list[dict[str, Any]],
    step_id: str,
) -> dict[str, Any]:
    pending = list(roots)
    while pending:
        step = pending.pop()
        if step["step_id"] == step_id:
            return step
        pending.extend(step["for_each_steps"])
        pending.extend(step["then_steps"])
        pending.extend(step["else_steps"])
        pending.extend(
            item
            for rows in step["match_cases"].values()
            for item in rows
        )
        repeat = step["repeat_until"]
        if repeat is not None:
            pending.extend(repeat["steps"])
    raise AssertionError(f"missing step {step_id}")


def _assert_code(code: str, call: Callable[[], object]) -> None:
    with pytest.raises(JudgmentResultContractError) as excinfo:
        call()
    assert excinfo.value.code == code


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    return value
