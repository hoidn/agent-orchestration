"""Stable procedure-lowering identity observations for compatibility tests."""

from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


REPO_ROOT = Path(__file__).resolve().parents[1]
_DEBUG_ONLY_WCC_KEYS = frozenset({"wcc_node_id", "wcc_scope_id"})
_PYTEST_SESSION_ROOT_PATTERN = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:"
    r"[A-Za-z]:[\\/](?:[^\\/\r\n'\"]+[\\/])*"
    r"pytest-of-[^\\/\r\n'\"]+[\\/]pytest-\d+"
    r"|"
    r"/(?:[^/\r\n'\"]+/)*pytest-of-[^/\r\n'\"]+/pytest-\d+"
    r")"
)
_PYTEST_ELAPSED_SUMMARY_PATTERN = re.compile(
    r"^(?P<prefix>\d+ "
    r"(?:failed|passed|skipped|deselected|xfailed|xpassed|error|errors|warning|warnings)"
    r"(?:, \d+ "
    r"(?:failed|passed|skipped|deselected|xfailed|xpassed|error|errors|warning|warnings)"
    r")* in )\d+(?:\.\d+)?s(?=\s*$)",
    flags=re.MULTILINE,
)
_PYTHON_REPR_ADDRESS_PATTERN = re.compile(
    r"(?P<prefix><[^\s<][^\r\n]*?\bat )0x[0-9A-Fa-f]+(?=>)"
)


def normalize_procedure_prerequisite_failure_log(
    text: str,
    *,
    repo_root: Path,
) -> str:
    """Normalize only nondeterministic prerequisite failure-log fragments."""

    normalized = text.replace(repo_root.resolve().as_posix(), "$REPO")
    normalized = _PYTEST_SESSION_ROOT_PATTERN.sub("$PYTEST_TMP", normalized)
    normalized = _PYTEST_ELAPSED_SUMMARY_PATTERN.sub(
        lambda match: f"{match.group('prefix')}$TIME",
        normalized,
    )
    return _PYTHON_REPR_ADDRESS_PATTERN.sub(
        lambda match: f"{match.group('prefix')}$ADDR",
        normalized,
    )


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"expected a JSON object in {path}")
    return payload


def remove_reviewed_synthetic_inline_call_checkpoint(
    observation: Mapping[str, Any],
    *,
    checkpoint_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Remove one explicitly reviewed baseline-only inline call checkpoint."""

    normalized = deepcopy(dict(observation))
    matches: list[tuple[list[dict[str, Any]], int, dict[str, Any]]] = []
    for bundle in normalized.get("bundles", []):
        runtime_identities = bundle.get("runtime_identities", {})
        points = runtime_identities.get("lexical_checkpoint_points", [])
        for index, point in enumerate(points):
            if point.get("checkpoint_id") == checkpoint_id:
                matches.append((points, index, point))

    if len(matches) != 1:
        raise AssertionError(
            "reviewed synthetic inline call checkpoint must identify exactly one row; "
            f"found {len(matches)} for {checkpoint_id}"
        )
    points, index, point = matches[0]
    effect_boundary = point.get("effect_boundary")
    policy = effect_boundary.get("policy") if isinstance(effect_boundary, Mapping) else None
    if not (
        point.get("point_kind") == "effect_boundary"
        and point.get("step_kind") == "call"
        and isinstance(effect_boundary, Mapping)
        and effect_boundary.get("effect_kind") == "call"
        and effect_boundary.get("boundary_kind") == "call"
        and isinstance(policy, Mapping)
        and policy.get("policy_kind") == "reuse_validated_workflow_call"
    ):
        raise AssertionError(
            f"reviewed checkpoint {checkpoint_id} is not a synthetic workflow-call policy row"
        )
    removed = points.pop(index)
    return normalized, removed


def _fixture_manifests(path: Path) -> tuple[dict[str, str], dict[str, str], dict[str, ExternalToolBinding]]:
    stem = path.with_suffix("")
    providers = _load_json(Path(f"{stem}.providers.json"))
    prompts = _load_json(Path(f"{stem}.prompts.json"))
    command_payload = _load_json(Path(f"{stem}.commands.json"))
    commands: dict[str, ExternalToolBinding] = {}
    for name, payload in command_payload.items():
        if not isinstance(payload, Mapping) or payload.get("kind") != "external_tool":
            raise ValueError(f"identity fixture command {name!r} must be an external_tool")
        stable_command = payload.get("stable_command")
        if not isinstance(stable_command, list) or not all(isinstance(part, str) for part in stable_command):
            raise ValueError(f"identity fixture command {name!r} needs stable_command strings")
        commands[name] = ExternalToolBinding(name=name, stable_command=tuple(stable_command))
    return providers, prompts, commands


def _plain(value: Any, *, workspace: Path, repo_root: Path) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        value = value.as_posix()
    if isinstance(value, str):
        replacements = (
            (workspace.resolve().as_posix(), "$WORKSPACE"),
            (repo_root.resolve().as_posix(), "$REPO"),
        )
        for old, new in replacements:
            value = value.replace(old, new)
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _plain(item, workspace=workspace, repo_root=repo_root)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
            if str(key) not in _DEBUG_ONLY_WCC_KEYS
        }
    if isinstance(value, (set, frozenset)):
        normalized_items = [
            _plain(item, workspace=workspace, repo_root=repo_root) for item in value
        ]
        return sorted(
            normalized_items,
            key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
        )
    if isinstance(value, (list, tuple)):
        return [_plain(item, workspace=workspace, repo_root=repo_root) for item in value]
    if is_dataclass(value):
        return {
            field.name: _plain(getattr(value, field.name), workspace=workspace, repo_root=repo_root)
            for field in fields(value)
            if field.name not in _DEBUG_ONLY_WCC_KEYS
        }
    return value


def _canonical(value: Any, *, workspace: Path, repo_root: Path) -> Any:
    return json.loads(
        json.dumps(
            _plain(value, workspace=workspace, repo_root=repo_root),
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _generated_path_allocations(lowered_workflow: Any, *, workspace: Path, repo_root: Path) -> list[dict[str, Any]]:
    rows = [
        _canonical(allocation, workspace=workspace, repo_root=repo_root)
        for allocation in lowered_workflow.generated_path_allocations
    ]
    return sorted(rows, key=lambda row: (row["allocation_id"], row["stable_identity"]))


def _semantic_identities(bundle: Any, *, workspace: Path, repo_root: Path) -> dict[str, Any]:
    semantic_ir = bundle.semantic_ir
    workflows = []
    for name, workflow in sorted(semantic_ir.workflows.items()):
        statements = [
            {
                "statement_id": statement.statement_id,
                "step_id": statement.step_id,
                "step_name": statement.step_name,
                "step_kind": statement.step_kind,
                "executable_node_ids": list(statement.executable_node_ids),
                "presentation_keys": list(statement.presentation_keys),
                "effect_ids": list(statement.effect_ids),
            }
            for _, statement in sorted(workflow.statements.items())
        ]
        workflows.append(
            {
                "workflow_name": name,
                "authored_statement_ids": list(workflow.authored_statement_ids),
                "statements": statements,
                "executable_bridge": {
                    "workflow_name": workflow.executable_bridge.workflow_name,
                    "node_ids": list(workflow.executable_bridge.node_ids),
                    "presentation_keys": list(workflow.executable_bridge.presentation_keys),
                    "resume_checkpoint_ids": list(
                        workflow.executable_bridge.resume_checkpoint_ids
                    ),
                },
            }
        )
    effects = [
        {
            "effect_id": effect.effect_id,
            "workflow_name": effect.workflow_name,
            "statement_id": effect.statement_id,
            "effect_kind": effect.effect_kind,
            "boundary_kind": effect.boundary_kind,
            "boundary_name": effect.boundary_name,
            "call_target": effect.call_target,
        }
        for _, effect in sorted(semantic_ir.effects.items())
    ]
    return _canonical(
        {"workflows": workflows, "effects": effects},
        workspace=workspace,
        repo_root=repo_root,
    )


def _runtime_identities(bundle: Any, *, workspace: Path, repo_root: Path) -> dict[str, Any]:
    runtime_plan = bundle.runtime_plan
    resume_checkpoints = [
        {
            "checkpoint_kind": checkpoint.checkpoint_kind,
            "node_id": checkpoint.node_id,
            "step_id": checkpoint.step_id,
            "presentation_key": checkpoint.presentation_key,
            "runtime_step_id_mode": checkpoint.runtime_step_id_mode,
            "iteration_owner_node_id": checkpoint.iteration_owner_node_id,
            "iteration_step_id_suffix": checkpoint.iteration_step_id_suffix,
        }
        for checkpoint in runtime_plan.resume_checkpoints
    ]
    lexical_points = []
    for point in runtime_plan.lexical_checkpoint_points:
        details = point.details
        effect_boundary = details.get("effect_boundary") if isinstance(details, Mapping) else None
        policy = effect_boundary.get("policy") if isinstance(effect_boundary, Mapping) else None
        lexical_points.append({
            "checkpoint_id": point.checkpoint_id,
            "program_point_id": point.program_point_id,
            "point_kind": point.point_kind,
            "workflow_name": point.workflow_name,
            "step_id": point.step_id,
            "node_id": point.node_id,
            "presentation_key": point.presentation_key,
            "origin_key": point.origin_key,
            "step_kind": details.get("step_kind") if isinstance(details, Mapping) else None,
            "effect_boundary": (
                {
                    "effect_kind": effect_boundary.get("effect_kind"),
                    "boundary_kind": effect_boundary.get("boundary_kind"),
                    "policy": {
                        key: policy.get(key)
                        for key in (
                            "schema_version",
                            "policy_kind",
                            "effect_kind",
                            "boundary_kind",
                            "step_id",
                            "source_map_origin_key",
                            "policy_digest",
                        )
                    },
                }
                if isinstance(effect_boundary, Mapping) and isinstance(policy, Mapping)
                else None
            ),
            "loop_back_edge_policy_digest": (
                details.get("loop_back_edge", {}).get("policy", {}).get("policy_digest")
                if isinstance(details, Mapping)
                and isinstance(details.get("loop_back_edge"), Mapping)
                and isinstance(details.get("loop_back_edge", {}).get("policy"), Mapping)
                else None
            ),
        })
    return _canonical(
        {
            "ordered_node_ids": list(runtime_plan.ordered_node_ids),
            "resume_checkpoints": resume_checkpoints,
            "lexical_checkpoint_points": lexical_points,
        },
        workspace=workspace,
        repo_root=repo_root,
    )


def _sorted_identity_rows(
    rows: list[dict[str, Any]],
    *,
    workspace: Path,
    repo_root: Path,
) -> list[dict[str, Any]]:
    normalized = [
        _canonical(row, workspace=workspace, repo_root=repo_root) for row in rows
    ]
    return sorted(
        normalized,
        key=lambda row: json.dumps(row, sort_keys=True, separators=(",", ":")),
    )


def _mapped_origin_rows(
    entries: Mapping[str, Any],
    *,
    subject_field: str,
    workspace: Path,
    repo_root: Path,
) -> list[dict[str, Any]]:
    return _sorted_identity_rows(
        [
            {subject_field: subject, "origin_key": entry.origin_key}
            for subject, entry in entries.items()
        ],
        workspace=workspace,
        repo_root=repo_root,
    )


def _source_map_identities(source_map: Any, *, workspace: Path, repo_root: Path) -> list[dict[str, Any]]:
    workflows = []
    for name, workflow in sorted(source_map.workflows.items()):
        workflows.append(
            {
                "workflow_name": name,
                "workflow_origin": {
                    "entity_kind": workflow.workflow_origin.entity_kind,
                    "workflow_name": workflow.workflow_origin.workflow_name,
                    "origin_key": workflow.workflow_origin.origin_key,
                },
                "step_ids": _mapped_origin_rows(
                    workflow.step_ids,
                    subject_field="step_id",
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "generated_inputs": _mapped_origin_rows(
                    workflow.generated_inputs,
                    subject_field="generated_input_name",
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "generated_outputs": _mapped_origin_rows(
                    workflow.generated_outputs,
                    subject_field="generated_output_name",
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "contract_fields": _mapped_origin_rows(
                    workflow.contract_fields,
                    subject_field="contract_field",
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "generated_paths": _mapped_origin_rows(
                    workflow.generated_paths,
                    subject_field="generated_path",
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "generated_internal_inputs": _mapped_origin_rows(
                    workflow.generated_internal_inputs,
                    subject_field="generated_internal_input_name",
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "generated_path_allocations": _sorted_identity_rows(
                    [
                        {
                            "allocation_id": row.allocation_id,
                            "semantic_role": row.semantic_role,
                            "privacy": row.privacy,
                            "resume_scope": row.resume_scope,
                            "stable_identity": row.stable_identity,
                            "concrete_path_template": row.concrete_path_template,
                            "generated_input_name": row.generated_input_name,
                            "path_safety_policy": row.path_safety_policy,
                            "origin_key": row.origin_key,
                        }
                        for row in workflow.generated_path_allocations
                    ],
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "generated_semantic_effects": _sorted_identity_rows(
                    [
                        {
                            "effect_key": row.effect_key,
                            "step_id": row.step_id,
                            "effect_kind": row.effect_kind,
                            "origin_key": row.origin_key,
                        }
                        for row in workflow.generated_semantic_effects
                    ],
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "core_nodes": _sorted_identity_rows(
                    [
                        {
                            "statement_id": row.statement_id,
                            "step_id": row.step_id,
                            "step_kind": row.step_kind,
                            "origin_key": row.origin_key,
                        }
                        for row in workflow.core_nodes
                    ],
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "command_boundaries": _sorted_identity_rows(
                    [
                        {
                            "step_id": row.step_id,
                            "command_name": row.command_name,
                            "boundary_kind": row.boundary_kind,
                            "adapter_name": row.adapter_name,
                            "source_map_behavior": row.source_map_behavior,
                            "declared_effects": list(row.declared_effects),
                            "origin_key": row.origin_key,
                        }
                        for row in workflow.command_boundaries
                    ],
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "validation_subjects": _sorted_identity_rows(
                    [
                        {
                            "subject_kind": row.subject_ref.subject_kind,
                            "subject_name": row.subject_ref.subject_name,
                            "workflow_name": row.subject_ref.workflow_name,
                            "origin_key": row.origin_key,
                        }
                        for row in workflow.validation_subjects
                    ],
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "executable_nodes": _sorted_identity_rows(
                    [
                        {
                            "node_id": row.node_id,
                            "step_id": row.step_id,
                            "kind": row.kind,
                            "region": row.region,
                            "presentation_name": row.presentation_name,
                            "origin_key": row.origin_key,
                        }
                        for row in workflow.executable_nodes
                    ],
                    workspace=workspace,
                    repo_root=repo_root,
                ),
            }
        )
    return _canonical(workflows, workspace=workspace, repo_root=repo_root)


def build_procedure_identity_observation(
    path: Path,
    route: str,
    workspace: Path,
    *,
    entry_workflow: str = "orchestrate",
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any]:
    """Compile one fixture and return its normalized persisted identity projection."""

    path = path.resolve()
    providers, prompts, commands = _fixture_manifests(path)
    compile_result = compile_stage3_entrypoint(
        path,
        source_roots=(path.parent,),
        entry_workflow=entry_workflow,
        provider_externs=providers,
        prompt_externs=prompts,
        command_boundaries=commands,
        validate_shared=True,
        workspace_root=workspace,
        lowering_route=route,
    )
    module_result = compile_result.entry_result
    resolved = {
        procedure.definition.name: procedure
        for procedure in module_result.typed_procedures
    }
    source_map = build_source_map_document(
        compile_result,
        selected_name=f"{module_result.module.module_name}::{entry_workflow}",
        display_name_resolver=lambda name: name.rsplit("::", 1)[-1],
    )

    lowered_workflows = []
    private_workflows = []
    for lowered in sorted(
        module_result.lowered_workflows,
        key=lambda workflow: workflow.typed_workflow.definition.name,
    ):
        name = lowered.typed_workflow.definition.name
        authored_mapping = _canonical(lowered.authored_mapping, workspace=workspace, repo_root=repo_root)
        lowered_workflows.append(
            {
                "workflow_name": name,
                "generated_private_workflow": lowered.is_generated_private_workflow,
                "authored_mapping": authored_mapping,
                "generated_path_allocations": _generated_path_allocations(
                    lowered,
                    workspace=workspace,
                    repo_root=repo_root,
                ),
            }
        )
        if lowered.is_generated_private_workflow:
            content = json.dumps(authored_mapping, indent=2, sort_keys=True) + "\n"
            content_bytes = content.encode("utf-8")
            private_workflows.append(
                {
                    "workflow_name": name,
                    "content_utf8": content,
                    "byte_length": len(content_bytes),
                    "sha256": hashlib.sha256(content_bytes).hexdigest(),
                }
            )

    bundles = []
    for name, bundle in sorted(compile_result.validated_bundles_by_name.items()):
        projection_entries = [
            {
                "node_id": entry.node_id,
                "step_id": entry.step_id,
                "presentation_key": entry.presentation_key,
                "display_name": entry.display_name,
                "region": entry.region.value,
                "compatibility_index": entry.compatibility_index,
                "finalization_index": entry.finalization_index,
            }
            for _, entry in sorted(bundle.projection.entries_by_node_id.items())
        ]
        bundles.append(
            {
                "workflow_name": name,
                "executable_projection": projection_entries,
                "semantic_identities": _semantic_identities(
                    bundle,
                    workspace=workspace,
                    repo_root=repo_root,
                ),
                "runtime_identities": _runtime_identities(
                    bundle,
                    workspace=workspace,
                    repo_root=repo_root,
                ),
            }
        )

    observation = {
        "schema": "procedure_lowering_identity_observation.v1",
        "route": route,
        "resolved_typed_procedures": [
            {
                "name": procedure.definition.name,
                "requested_mode": procedure.signature.requested_lowering_mode.value,
                "resolved_mode": procedure.resolved_lowering_mode.value,
                "generated_workflow_name": procedure.generated_workflow_name,
            }
            for _, procedure in sorted(resolved.items())
        ],
        "lowered_workflows": lowered_workflows,
        "bundles": bundles,
        "source_map_origin_keys": _source_map_identities(
            source_map,
            workspace=workspace,
            repo_root=repo_root,
        ),
        "generated_private_workflows": private_workflows,
    }
    return _canonical(observation, workspace=workspace, repo_root=repo_root)
