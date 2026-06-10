from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any
from unittest.mock import patch

import orchestrator.workflow.loaded_bundle as loaded_bundle_helpers
from orchestrator.exec.output_capture import CaptureMode, CaptureResult
from orchestrator.exec.step_executor import ExecutionResult
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_public_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.providers.executor import ProviderExecutor
from tests.golden_state import _build_observation, _thaw
from tests.test_workflow_ir_lowering import _detach_core_ast_surface_links


REPO_ROOT = Path(__file__).resolve().parent.parent
CHARACTERIZATION_ROOT = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "characterization"
CHARACTERIZATION_MANIFEST_PATH = CHARACTERIZATION_ROOT / "manifest.json"


@dataclass(frozen=True)
class WorkspaceSeedFile:
    path: Path
    source_path: Path | None
    text_payload: str | None
    json_payload: dict[str, Any] | None


@dataclass(frozen=True)
class BehaviorRuntime:
    bound_inputs: dict[str, Any]
    workspace_seed_files: tuple[WorkspaceSeedFile, ...]
    fake_provider_scenario: dict[str, Any] | None


@dataclass(frozen=True)
class CharacterizationCase:
    case_id: str
    fixture_kind: str
    source_path: Path
    source_roots: tuple[Path, ...]
    entry_workflow: str | None
    provider_externs: dict[str, Any] | Path | None
    prompt_externs: dict[str, Any] | Path | None
    command_boundaries: dict[str, Any] | Path | None
    imported_workflow_bundles_path: Path | None
    evidence_mode: str
    behavior_runtime: BehaviorRuntime | None
    declared_rename_map: dict[str, dict[str, str]]
    dual_compile_routes: tuple[str, ...]
    tags: tuple[str, ...]
    golden_structural: Path
    golden_behavior: Path | None
    route_flip_corpus: bool = True
    historical_legacy_fixture: bool = False


def _relpath(value: str, *, field_name: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        raise ValueError(f"{field_name} must be repo-relative: {value}")
    return path


def _load_seed_file(payload: dict[str, Any], *, case_id: str) -> WorkspaceSeedFile:
    path = _relpath(str(payload["path"]), field_name=f"{case_id}.workspace_seed_files.path")
    source_path_value = payload.get("source_path")
    text_payload = payload.get("text_payload")
    json_payload = payload.get("json_payload")
    populated = [value is not None for value in (source_path_value, text_payload, json_payload)]
    if sum(populated) != 1:
        raise ValueError(f"{case_id} seed file {path} must declare exactly one payload source")
    source_path = (
        _relpath(str(source_path_value), field_name=f"{case_id}.workspace_seed_files.source_path")
        if source_path_value is not None
        else None
    )
    if json_payload is not None and not isinstance(json_payload, dict):
        raise ValueError(f"{case_id} seed file {path} json_payload must be an object")
    return WorkspaceSeedFile(
        path=path,
        source_path=source_path,
        text_payload=text_payload,
        json_payload=json_payload,
    )


def _load_behavior_runtime(payload: dict[str, Any], *, case_id: str) -> BehaviorRuntime:
    bound_inputs = payload.get("bound_inputs")
    if not isinstance(bound_inputs, dict) or not bound_inputs:
        raise ValueError(f"{case_id} behavior_runtime.bound_inputs must be a non-empty object")
    workspace_seed_payloads = payload.get("workspace_seed_files", [])
    if not isinstance(workspace_seed_payloads, list):
        raise ValueError(f"{case_id} behavior_runtime.workspace_seed_files must be a list")
    fake_provider_scenario = payload.get("fake_provider_scenario")
    if fake_provider_scenario is not None and not isinstance(fake_provider_scenario, dict):
        raise ValueError(f"{case_id} behavior_runtime.fake_provider_scenario must be an object")
    return BehaviorRuntime(
        bound_inputs=bound_inputs,
        workspace_seed_files=tuple(
            _load_seed_file(seed_payload, case_id=case_id) for seed_payload in workspace_seed_payloads
        ),
        fake_provider_scenario=fake_provider_scenario,
    )


def _load_mapping_or_path(value: Any, *, case_id: str, field_name: str) -> dict[str, Any] | Path | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return _relpath(value, field_name=f"{case_id}.{field_name}")
    raise ValueError(f"{case_id}.{field_name} must be an object, path string, or null")


def _load_case(payload: dict[str, Any]) -> CharacterizationCase:
    case_id = str(payload["case_id"])
    evidence_mode = str(payload["evidence_mode"])
    if evidence_mode not in {"structural_only", "structural_and_behavioral"}:
        raise ValueError(f"{case_id}.evidence_mode is invalid: {evidence_mode}")

    behavior_runtime_payload = payload.get("behavior_runtime")
    if evidence_mode == "structural_and_behavioral":
        if behavior_runtime_payload is None:
            raise ValueError(f"{case_id} must declare behavior_runtime")
        if payload.get("golden_behavior") is None:
            raise ValueError(f"{case_id} must declare golden_behavior")
        behavior_runtime = _load_behavior_runtime(behavior_runtime_payload, case_id=case_id)
        golden_behavior = _relpath(str(payload["golden_behavior"]), field_name=f"{case_id}.golden_behavior")
    else:
        if behavior_runtime_payload is not None:
            raise ValueError(f"{case_id} must omit behavior_runtime for structural_only evidence")
        if payload.get("golden_behavior") is not None:
            raise ValueError(f"{case_id} must omit golden_behavior for structural_only evidence")
        behavior_runtime = None
        golden_behavior = None

    declared_rename_map = payload.get("declared_rename_map")
    if not isinstance(declared_rename_map, dict):
        raise ValueError(f"{case_id}.declared_rename_map must be an object")
    for domain, mapping in declared_rename_map.items():
        if not isinstance(domain, str) or not isinstance(mapping, dict):
            raise ValueError(f"{case_id}.declared_rename_map entries must map strings to objects")
        for old_name, new_name in mapping.items():
            if not isinstance(old_name, str) or not isinstance(new_name, str):
                raise ValueError(f"{case_id}.declared_rename_map.{domain} must map strings to strings")

    source_roots = payload.get("source_roots")
    if not isinstance(source_roots, list) or not source_roots:
        raise ValueError(f"{case_id}.source_roots must be a non-empty list")
    tags = payload.get("tags")
    if not isinstance(tags, list) or not tags or not all(isinstance(tag, str) for tag in tags):
        raise ValueError(f"{case_id}.tags must be a non-empty list of strings")
    dual_compile_routes = payload.get("dual_compile_routes", [])
    if not isinstance(dual_compile_routes, list) or not all(isinstance(route, str) for route in dual_compile_routes):
        raise ValueError(f"{case_id}.dual_compile_routes must be a list of strings")

    fixture_kind = str(payload["fixture_kind"])
    if fixture_kind not in {"module", "entrypoint"}:
        raise ValueError(f"{case_id}.fixture_kind is invalid: {fixture_kind}")

    entry_workflow = payload.get("entry_workflow")
    if fixture_kind == "entrypoint" and not isinstance(entry_workflow, str):
        raise ValueError(f"{case_id}.entry_workflow is required for entrypoint cases")
    if fixture_kind == "module" and entry_workflow is not None:
        raise ValueError(f"{case_id}.entry_workflow must be omitted for module cases")

    imported_bundles = payload.get("imported_workflow_bundles_path")
    if imported_bundles is not None:
        imported_bundles_path = _relpath(
            str(imported_bundles), field_name=f"{case_id}.imported_workflow_bundles_path"
        )
    else:
        imported_bundles_path = None

    return CharacterizationCase(
        case_id=case_id,
        fixture_kind=fixture_kind,
        source_path=_relpath(str(payload["source_path"]), field_name=f"{case_id}.source_path"),
        source_roots=tuple(_relpath(str(root), field_name=f"{case_id}.source_roots") for root in source_roots),
        entry_workflow=entry_workflow,
        provider_externs=_load_mapping_or_path(payload.get("provider_externs"), case_id=case_id, field_name="provider_externs"),
        prompt_externs=_load_mapping_or_path(payload.get("prompt_externs"), case_id=case_id, field_name="prompt_externs"),
        command_boundaries=_load_mapping_or_path(
            payload.get("command_boundaries"), case_id=case_id, field_name="command_boundaries"
        ),
        imported_workflow_bundles_path=imported_bundles_path,
        evidence_mode=evidence_mode,
        behavior_runtime=behavior_runtime,
        declared_rename_map=declared_rename_map,
        dual_compile_routes=tuple(dual_compile_routes),
        route_flip_corpus=bool(payload.get("route_flip_corpus", True)),
        historical_legacy_fixture=bool(payload.get("historical_legacy_fixture", False)),
        tags=tuple(tags),
        golden_structural=_relpath(str(payload["golden_structural"]), field_name=f"{case_id}.golden_structural"),
        golden_behavior=golden_behavior,
    )


def load_characterization_cases() -> tuple[CharacterizationCase, ...]:
    payload = json.loads(CHARACTERIZATION_MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("characterization manifest must be an object with a cases array")
    return tuple(_load_case(case_payload) for case_payload in payload["cases"])


def _json_mapping_from_path(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object at {path}")
    return payload


def _materialize_mapping_manifest(name: str, payload: dict[str, Any], workspace: Path) -> Path:
    target = workspace / f"{name}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target


def _resolve_string_mapping(value: dict[str, Any] | Path | None) -> dict[str, str] | None:
    if value is None:
        return None
    mapping = _json_mapping_from_path(REPO_ROOT / value) if isinstance(value, Path) else value
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in mapping.items()):
        raise ValueError("expected string-to-string mapping")
    return dict(sorted(mapping.items()))


def _resolve_command_boundaries(value: dict[str, Any] | Path | None) -> dict[str, ExternalToolBinding] | None:
    if value is None:
        return None
    mapping = _json_mapping_from_path(REPO_ROOT / value) if isinstance(value, Path) else value
    bindings: dict[str, ExternalToolBinding] = {}
    for name, payload in mapping.items():
        if not isinstance(payload, dict):
            raise ValueError(f"command boundary {name} must be an object")
        if payload.get("kind") != "external_tool":
            raise ValueError(f"unsupported command boundary kind for {name}: {payload.get('kind')}")
        stable_command = payload.get("stable_command")
        if not isinstance(stable_command, list) or not all(isinstance(item, str) for item in stable_command):
            raise ValueError(f"command boundary {name} stable_command must be a string array")
        bindings[name] = ExternalToolBinding(name=name, stable_command=tuple(stable_command))
    return bindings


def _compile_case(case: CharacterizationCase, workspace: Path, *, lowering_route: str | None = "legacy") -> dict[str, Any]:
    source_path = REPO_ROOT / case.source_path
    source_roots = tuple(REPO_ROOT / root for root in case.source_roots)
    if case.fixture_kind == "module":
        result = compile_stage3_module(
            source_path,
            provider_externs=_resolve_string_mapping(case.provider_externs),
            prompt_externs=_resolve_string_mapping(case.prompt_externs),
            command_boundaries=_resolve_command_boundaries(case.command_boundaries),
            validate_shared=True,
            workspace_root=workspace,
            lowering_route=lowering_route,
        )
        return {
            "kind": "module",
            "compile_result": result,
            "compiled_module_names": [result.module.module_name or source_path.stem],
            "imported_workflow_bundles": [],
            "selected_workflow_name": None,
            "lowering_route": lowering_route,
        }
    build = __import__("orchestrator.workflow_lisp.build", fromlist=["FrontendBuildRequest", "build_frontend_bundle"])
    request_cls = getattr(build, "FrontendBuildRequest")
    provider_path = (
        REPO_ROOT / case.provider_externs
        if isinstance(case.provider_externs, Path)
        else _materialize_mapping_manifest(f"{case.case_id}.providers", case.provider_externs or {}, workspace)
    )
    prompt_path = (
        REPO_ROOT / case.prompt_externs
        if isinstance(case.prompt_externs, Path)
        else _materialize_mapping_manifest(f"{case.case_id}.prompts", case.prompt_externs or {}, workspace)
    )
    command_path = (
        REPO_ROOT / case.command_boundaries
        if isinstance(case.command_boundaries, Path)
        else _materialize_mapping_manifest(f"{case.case_id}.commands", case.command_boundaries or {}, workspace)
    )
    imported_bundles_path = (
        REPO_ROOT / case.imported_workflow_bundles_path if case.imported_workflow_bundles_path else None
    )
    build_result = build.build_frontend_bundle(
        request_cls(
            source_path=source_path,
            source_roots=source_roots,
            entry_workflow=case.entry_workflow,
            provider_externs_path=provider_path,
            prompt_externs_path=prompt_path,
            imported_workflow_bundles_path=imported_bundles_path,
            command_boundaries_path=command_path,
            emit_debug_yaml=False,
            workspace_root=workspace,
            lowering_route=lowering_route,
        )
    )
    return {
        "kind": "entrypoint",
        "compile_result": build_result.compile_result.entry_result,
        "linked_compile_result": build_result.compile_result,
        "compiled_module_names": sorted(build_result.compile_result.compiled_results_by_name),
        "imported_workflow_bundles": build_result.imported_workflow_bundles,
        "selected_workflow_name": build_result.selected_workflow_name,
        "lowering_route": lowering_route,
    }


def _thaw(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, MappingProxyType):
        value = dict(value)
    if isinstance(value, tuple):
        return [_thaw(item) for item in value]
    if isinstance(value, list):
        return [_thaw(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _thaw(item) for key, item in value.items()}
    if is_dataclass(value):
        detached = _detach_core_ast_surface_links(value)
        return {field.name: _thaw(getattr(detached, field.name)) for field in fields(detached)}
    return value


def _normalize_string(value: str, *, workspace: Path) -> str:
    if value.startswith(str(REPO_ROOT) + "/"):
        return Path(value).relative_to(REPO_ROOT).as_posix()
    if value.startswith(str(workspace) + "/"):
        return Path(value).relative_to(workspace).as_posix()
    return value


def _normalize_json_like(value: Any, *, workspace: Path) -> Any:
    if isinstance(value, str):
        return _normalize_string(value, workspace=workspace)
    if isinstance(value, list):
        return [_normalize_json_like(item, workspace=workspace) for item in value]
    if isinstance(value, dict):
        normalized = {
            key: _normalize_json_like(item, workspace=workspace)
            for key, item in sorted(value.items(), key=lambda item: item[0])
            if key not in {"_surface_step", "_surface_workflow"}
        }
        return normalized
    return value


def _source_digest(case: CharacterizationCase) -> str:
    source = (REPO_ROOT / case.source_path).read_bytes()
    return hashlib.sha256(source).hexdigest()


def _iter_step_labels(steps: list[dict[str, Any]]) -> list[str]:
    labels: list[str] = []
    for step in steps:
        name = step.get("name")
        if isinstance(name, str):
            labels.append(name)
        for key, value in step.items():
            if key in {"repeat_until", "for_each", "if", "then", "else"} and isinstance(value, dict):
                nested_steps = value.get("steps")
                if isinstance(nested_steps, list):
                    labels.extend(_iter_step_labels(nested_steps))
            if key == "match" and isinstance(value, dict):
                for case_payload in value.get("cases", {}).values():
                    if isinstance(case_payload, dict):
                        labels.extend(_iter_step_labels(case_payload.get("steps", [])))
    return labels


def _normalize_lowered_workflow(workflow: Any, *, workspace: Path) -> dict[str, Any]:
    authored_mapping = _normalize_json_like(_thaw(workflow.authored_mapping), workspace=workspace)
    return {
        "workflow_name": workflow.typed_workflow.definition.name,
        "step_labels": _iter_step_labels(authored_mapping.get("steps", [])),
        "generated_input_names": sorted(
            key for key in authored_mapping.get("inputs", {}) if isinstance(key, str) and key.startswith("__")
        ),
        "authored_mapping": authored_mapping,
    }


def _ordered_node_ids(projection: Any) -> list[str]:
    ordered = projection.ordered_execution_node_ids
    if callable(ordered):
        ordered = ordered()
    return list(ordered)


def _bundle_inputs(bundle: Any) -> dict[str, Any]:
    return loaded_bundle_helpers.workflow_input_contracts(bundle)


def _bundle_outputs(bundle: Any) -> dict[str, Any]:
    helper = getattr(loaded_bundle_helpers, "workflow_output_contracts")
    return helper(bundle)


def _generated_path_summary(bundle: Any, *, workspace: Path) -> list[dict[str, Any]]:
    helper = getattr(loaded_bundle_helpers, "workflow_generated_path_allocations")
    allocations = []
    for allocation in helper(bundle):
        thawed = _normalize_json_like(_thaw(allocation), workspace=workspace)
        allocations.append(
            {
                "allocation_id": thawed["allocation_id"],
                "semantic_role": thawed["semantic_role"],
                "privacy": thawed["privacy"],
                "resume_scope": thawed["resume_scope"],
                "stable_identity": thawed["stable_identity"],
                "concrete_path_template": thawed["concrete_path_template"],
                "generated_input_name": thawed["generated_input_name"],
                "path_safety_policy": thawed["path_safety_policy"],
            }
        )
    return allocations


def _projection_summary(bundle: Any, *, workspace: Path) -> dict[str, Any]:
    projection = _detach_core_ast_surface_links(bundle.projection)
    ordered_node_ids = _ordered_node_ids(projection)
    node_summaries = []
    for node_id in ordered_node_ids:
        entry = projection.entries_by_node_id[node_id]
        step_definition = entry.step_definition
        node_summaries.append(
            {
                "node_id": _normalize_string(entry.node_id, workspace=workspace),
                "step_id": _normalize_string(entry.step_id, workspace=workspace),
                "presentation_key": entry.presentation_key,
                "display_name": entry.display_name,
                "region": entry.region.value,
                "compatibility_index": entry.compatibility_index,
                "finalization_index": entry.finalization_index,
                "report_kind": step_definition.report_kind,
                "provider": step_definition.provider,
                "command": _normalize_json_like(_thaw(step_definition.command), workspace=workspace),
                "consumes": _normalize_json_like(_thaw(step_definition.consumes), workspace=workspace),
                "expected_outputs": _normalize_json_like(_thaw(step_definition.expected_outputs), workspace=workspace),
                "max_visits": step_definition.max_visits,
            }
        )
    return {
        "ordered_node_ids": ordered_node_ids,
        "node_summaries": node_summaries,
        "match_cases": _normalize_json_like(_thaw(projection.structured_match_cases), workspace=workspace),
        "repeat_until_nodes": _normalize_json_like(_thaw(projection.repeat_until_nodes), workspace=workspace),
        "for_each_nodes": _normalize_json_like(_thaw(projection.for_each_nodes), workspace=workspace),
        "call_boundaries": _normalize_json_like(_thaw(projection.call_boundaries), workspace=workspace),
    }


def _normalize_bundle(bundle: Any, *, workspace: Path) -> dict[str, Any]:
    return {
        "workflow_name": bundle.surface.name,
        "input_keys": sorted(_bundle_inputs(bundle)),
        "output_keys": sorted(_bundle_outputs(bundle)),
        "artifact_keys": sorted(bundle.surface.artifacts),
        "generated_input_names": sorted(
            key for key in _bundle_inputs(bundle) if isinstance(key, str) and key.startswith("__")
        ),
        "generated_paths": _generated_path_summary(bundle, workspace=workspace),
        "projection": _projection_summary(bundle, workspace=workspace),
    }


def _normalize_diagnostic(diagnostic: Any, *, workspace: Path) -> dict[str, Any]:
    return _normalize_json_like(
        {
            "code": diagnostic.code,
            "message": diagnostic.message,
            "severity": diagnostic.severity,
            "diagnostic_kind": diagnostic.diagnostic_kind,
            "phase": diagnostic.phase,
            "form_path": list(diagnostic.form_path),
            "notes": list(diagnostic.notes),
            "span": _thaw(diagnostic.span),
        },
        workspace=workspace,
    )


def build_structural_snapshot(
    case: CharacterizationCase,
    tmp_path: Path,
    *,
    lowering_route: str | None = "legacy",
) -> dict[str, Any]:
    compiled = _compile_case(case, tmp_path, lowering_route=lowering_route)
    compile_result = compiled["compile_result"]
    diagnostics = [_normalize_diagnostic(item, workspace=tmp_path) for item in compile_result.diagnostics]
    lowered_workflows = [
        _normalize_lowered_workflow(workflow, workspace=tmp_path)
        for workflow in sorted(compile_result.lowered_workflows, key=lambda item: item.typed_workflow.definition.name)
    ]
    validated_bundles = [
        _normalize_bundle(bundle, workspace=tmp_path)
        for _, bundle in sorted(compile_result.validated_bundles.items())
    ]
    imported_workflow_bundles = [
        {
            "canonical_key": binding.canonical_key,
            "manifest_entry_path": binding.manifest_entry_path,
            "resolved_bundle_path": _normalize_string(str(binding.resolved_bundle_path), workspace=tmp_path),
            "bundle_kind": binding.bundle_kind,
            "workflow_name": binding.workflow_name,
            "bundle_fingerprint": binding.bundle_fingerprint,
            "load_status": binding.load_status,
        }
        for binding in compiled["imported_workflow_bundles"]
    ]
    return {
        "schema_version": "workflow_lisp.characterization.v1",
        "case_id": case.case_id,
        "source_digest": _source_digest(case),
        "compiled_module_names": compiled["compiled_module_names"],
        "selected_workflow_name": compiled["selected_workflow_name"],
        "workflow_names": [workflow["workflow_name"] for workflow in lowered_workflows],
        "lowered_workflows": lowered_workflows,
        "validated_bundles": validated_bundles,
        "imported_workflow_bundles": imported_workflow_bundles,
        "diagnostics": diagnostics,
    }


def build_structural_snapshot_metadata(
    case: CharacterizationCase,
    tmp_path: Path,
    *,
    lowering_route: str | None = "legacy",
) -> dict[str, Any]:
    compiled = _compile_case(case, tmp_path, lowering_route=lowering_route)
    return {
        "case_id": case.case_id,
        "fixture_kind": case.fixture_kind,
        "lowering_route": compiled["lowering_route"],
        "compiled_module_names": compiled["compiled_module_names"],
        "selected_workflow_name": compiled["selected_workflow_name"],
    }


def _apply_declared_renames(value: Any, declared_rename_map: dict[str, dict[str, str]]) -> Any:
    if isinstance(value, list):
        return [_apply_declared_renames(item, declared_rename_map) for item in value]
    if isinstance(value, dict):
        rewritten: dict[str, Any] = {}
        for key, item in value.items():
            if key in declared_rename_map and isinstance(item, list):
                rewritten[key] = [declared_rename_map[key].get(entry, entry) for entry in item]
            elif key in declared_rename_map and isinstance(item, str):
                rewritten[key] = declared_rename_map[key].get(item, item)
            else:
                rewritten[key] = _apply_declared_renames(item, declared_rename_map)
        return rewritten
    return value


def compare_structural_snapshots(
    actual: dict[str, Any],
    golden: dict[str, Any],
    declared_rename_map: dict[str, dict[str, str]],
) -> str:
    if actual == golden:
        return "identical"
    if _apply_declared_renames(actual, declared_rename_map) == golden:
        return "rename_only"
    return "divergent"


def _materialize_seed_file(seed_file: WorkspaceSeedFile, workspace: Path) -> None:
    target = workspace / seed_file.path
    target.parent.mkdir(parents=True, exist_ok=True)
    if seed_file.source_path is not None:
        source = REPO_ROOT / seed_file.source_path
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        return
    if seed_file.json_payload is not None:
        target.write_text(json.dumps(seed_file.json_payload, indent=2) + "\n", encoding="utf-8")
        return
    assert seed_file.text_payload is not None
    target.write_text(seed_file.text_payload, encoding="utf-8")


def _write_fake_provider_scenario(workspace: Path, payload: dict[str, Any]) -> None:
    target = workspace / "state" / "fake_provider_scenario.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _token_score(case_id: str, workflow_name: str) -> tuple[int, int, str]:
    case_tokens = {token for token in re.split(r"[^a-z0-9]+", case_id.lower()) if token}
    workflow_tokens = {token for token in re.split(r"[^a-z0-9]+", workflow_name.lower()) if token}
    return (len(case_tokens & workflow_tokens), len(workflow_tokens), workflow_name)


def _select_behavior_bundle(case: CharacterizationCase, compile_result: Any) -> Any:
    bundles = dict(compile_result.validated_bundles)
    if not bundles:
        raise ValueError(f"{case.case_id} has no validated bundles to execute")
    if len(bundles) == 1:
        return next(iter(bundles.values()))
    if case.behavior_runtime is not None:
        provided_names = set(case.behavior_runtime.bound_inputs)

        def _input_score(item: tuple[str, Any]) -> tuple[int, int, int, str]:
            name, bundle = item
            public_names = set(workflow_public_input_contracts(bundle))
            missing = len(public_names - provided_names)
            unexpected = len(provided_names - public_names)
            token_score = _token_score(case.case_id, name)
            return (-missing, -unexpected, token_score[0], name)

        best_name, best_bundle = max(bundles.items(), key=_input_score)
        public_names = set(workflow_public_input_contracts(best_bundle))
        if public_names.issubset(provided_names):
            return best_bundle
    best_name = max(bundles, key=lambda name: _token_score(case.case_id, name))
    return bundles[best_name]


def _bundle_path_from_prompt(prompt: str) -> Path:
    match = re.search(r"(?m)^-?\s*path: (.+)$", prompt)
    if match is None:
        raise ValueError("provider prompt did not advertise a result bundle path")
    return Path(match.group(1).strip())


def _iter_relpaths(value: Any) -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            paths.extend(_iter_relpaths(item))
    elif isinstance(value, list):
        for item in value:
            paths.extend(_iter_relpaths(item))
    elif isinstance(value, str) and value.startswith(("artifacts/", "state/", "docs/")):
        paths.append(value)
    return paths


def _default_json_payload(path: str) -> dict[str, Any]:
    if "findings" in path:
        return {"items": []}
    return {}


def _materialize_relpath(relpath: str, workspace: Path) -> None:
    target = workspace / relpath
    if target.exists():
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.suffix == ".json":
        target.write_text(json.dumps(_default_json_payload(relpath), indent=2) + "\n", encoding="utf-8")
    else:
        target.write_text(f"{target.name}\n", encoding="utf-8")


def _write_runtime_bundle(path: str | Path, payload: dict[str, Any], workspace: Path) -> None:
    bundle_path = Path(path)
    if not bundle_path.is_absolute():
        bundle_path = workspace / bundle_path
    bundle_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _load_provider_scenario(workspace: Path) -> dict[str, Any]:
    return json.loads((workspace / "state" / "fake_provider_scenario.json").read_text(encoding="utf-8"))


def _provider_payload_for_invocation(
    *,
    provider_name: str,
    workspace: Path,
    provider_counts: dict[str, int],
) -> dict[str, Any]:
    scenario = _load_provider_scenario(workspace)
    sequences = scenario.get("provider_sequences", {})
    if isinstance(sequences, dict) and provider_name in sequences:
        payloads = sequences[provider_name]
        if not isinstance(payloads, list) or not payloads:
            raise ValueError(f"provider sequence for {provider_name} must be a non-empty list")
        index = provider_counts.get(provider_name, 0)
        provider_counts[provider_name] = index + 1
        payload = payloads[index] if index < len(payloads) else payloads[-1]
        if not isinstance(payload, dict):
            raise ValueError(f"provider sequence payload for {provider_name} must be an object")
        return payload
    payloads = scenario.get("provider_payloads", {})
    payload = payloads.get(provider_name) if isinstance(payloads, dict) else None
    if not isinstance(payload, dict):
        raise ValueError(f"missing fake provider payload for {provider_name}")
    provider_counts[provider_name] = provider_counts.get(provider_name, 0) + 1
    return payload


def build_behavior_observation(
    case: CharacterizationCase,
    tmp_path: Path,
    *,
    lowering_route: str | None = "legacy",
) -> dict[str, Any]:
    if case.behavior_runtime is None:
        raise ValueError(f"{case.case_id} is not a behavioral characterization case")

    for seed_file in case.behavior_runtime.workspace_seed_files:
        _materialize_seed_file(seed_file, tmp_path)
    if case.behavior_runtime.fake_provider_scenario is not None:
        _write_fake_provider_scenario(tmp_path, case.behavior_runtime.fake_provider_scenario)

    compiled = _compile_case(case, tmp_path, lowering_route=lowering_route)
    bundle = _select_behavior_bundle(case, compiled["compile_result"])
    bound_inputs = bind_workflow_inputs(
        workflow_public_input_contracts(bundle),
        case.behavior_runtime.bound_inputs,
        tmp_path,
    )
    state_manager = StateManager(workspace=tmp_path, run_id="oracle-run")
    context_payload = _thaw(workflow_context(bundle))
    lowering_schema_version = getattr(compiled["compile_result"], "lowering_schema_version", None)
    if lowering_schema_version is not None:
        context_payload.setdefault("workflow_lisp", {})["lowering_schema_version"] = lowering_schema_version
    state_manager.initialize((REPO_ROOT / case.source_path).as_posix(), context_payload, bound_inputs)

    provider_counts: dict[str, int] = {}

    def _prepare_invocation(_self, provider_name=None, prompt_content=None, **_kwargs):
        return type(
            "ProviderInvocationStub",
            (),
            {
                "input_mode": "stdin",
                "prompt": prompt_content or "",
                "provider_name": provider_name,
            },
        )(), None

    def _execute(_self, invocation, **_kwargs):
        provider_name = getattr(invocation, "provider_name", None)
        if not isinstance(provider_name, str):
            raise ValueError("provider invocation did not carry provider_name")
        payload = _provider_payload_for_invocation(
            provider_name=provider_name,
            workspace=tmp_path,
            provider_counts=provider_counts,
        )
        bundle_path = tmp_path / _bundle_path_from_prompt(getattr(invocation, "prompt", ""))
        for relpath in _iter_relpaths(payload):
            _materialize_relpath(relpath, tmp_path)
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return type(
            "ProviderExecutionStub",
            (),
            {
                "exit_code": 0,
                "stdout": b"ok",
                "stderr": b"",
                "duration_ms": 1,
                "error": None,
                "missing_placeholders": None,
                "invalid_prompt_placeholder": False,
                "raw_stdout": None,
                "normalized_stdout": None,
                "provider_session": None,
            },
        )()

    def _execute_command(_self, step_name, command, env=None, **_kwargs):
        bundle_path = (env or {}).get("ORCHESTRATOR_OUTPUT_BUNDLE_PATH")
        if not isinstance(bundle_path, str) or not bundle_path:
            raise ValueError(f"command step {step_name!r} did not receive an output bundle path")
        if str(step_name).endswith("__managed_write_roots"):
            args = list(command[4:]) if isinstance(command, list) else []
            payload = {str(args[index]): str(args[index + 1]) for index in range(0, len(args), 2)}
        elif str(step_name).endswith("__run_checks"):
            payload = {"checks_report_path": "artifacts/work/checks_report.md"}
        elif str(step_name).endswith("__validate_review_findings_v1"):
            items_path = command[-1] if isinstance(command, list) and command else "artifacts/work/findings.json"
            payload = {
                "schema_version": "ReviewFindings.v1",
                "items_path": items_path,
            }
        else:
            raise AssertionError(f"unexpected command step {step_name!r}: {command!r}")
        for relpath in _iter_relpaths(payload):
            _materialize_relpath(relpath, tmp_path)
        _write_runtime_bundle(bundle_path, payload, tmp_path)
        return ExecutionResult(
            step_name=step_name,
            exit_code=0,
            capture_result=CaptureResult(mode=CaptureMode.TEXT, output="ok", exit_code=0),
            duration_ms=1,
        )

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ), patch(
        "orchestrator.exec.step_executor.StepExecutor.execute_command",
        _execute_command,
    ):
        state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="continue")

    observation = _build_observation(tmp_path, state)
    if lowering_route is None:
        observation["state"] = {
            "context": state_manager.load().to_dict().get("context", {}),
        }
    return observation
