"""Functional immutable evidence for provider prompt dependencies."""

from __future__ import annotations

import hashlib
from pathlib import Path

from orchestrator.deps.content_snapshot import (
    AuthoredDependencyRow,
    DependencyContent,
    build_content_snapshot,
)
from orchestrator.state import RunState
from orchestrator.workflow.prompt_dependency_contract import (
    PromptDependencyOriginKind,
    PromptDependencyPosition,
    _build_compiler_prompt_dependency_contract,
)
from orchestrator.workflow.prompting import CanonicalPromptCut
from orchestrator.workflow.provider_phased_delivery.models import (
    ByteDigestProjection,
    CompositionProjection,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope


def _sha(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _fragment_contract():
    return _build_compiler_prompt_dependency_contract(
        required_binding_refs=("required-document",),
        optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key="provider-result",
        source_workflow_bytes=b"(workflow evidence)",
        origin_kind=PromptDependencyOriginKind.WORKFLOW_LISP_PROMPT_FRAGMENT,
    )


def _scope() -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": "20260718T000000Z-evid1",
            "resume_scope": {
                "root_workflow_file": "workflow.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "ProviderStep",
            "enclosing_step": {
                "step_name": "Provider",
                "step_id": "ProviderStep",
                "visit_count": 2,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def _run_state(root: str | Path = "/tmp/aggregate-run") -> RunState:
    return RunState(
        schema_version="2.1",
        run_id=_scope().run_id,
        workflow_file="workflow.orc",
        workflow_checksum="sha256:" + "1" * 64,
        started_at="2026-07-18T00:00:00+00:00",
        updated_at="2026-07-18T00:00:00+00:00",
        status="running",
        run_root=str(root),
    )


def _byte_projection(value: bytes) -> ByteDigestProjection:
    return ByteDigestProjection(
        bytes=len(value),
        sha256=_sha(value),
    )


def _canonical_cut(
    canonical_composed: bytes = b"Read these inputs.\n\nbase prompt",
) -> CanonicalPromptCut:
    task_slice = b""
    materialization_slice = canonical_composed
    return CanonicalPromptCut(
        task_slice=task_slice,
        materialization_slice=materialization_slice,
        canonical_composed=canonical_composed,
        projection=CompositionProjection(
            canonical_composed=_byte_projection(canonical_composed),
            task_slice=_byte_projection(task_slice),
            materialization_slice=_byte_projection(materialization_slice),
        ),
    )


def _fragment_v1_record(
    *,
    canonical_composed: bytes = b"Read these inputs.\n\nbase prompt",
    run_state: RunState | None = None,
) -> dict:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence,
    )

    snapshot = build_content_snapshot(
        (
            AuthoredDependencyRow(
                "required",
                0,
                "required-document",
                "inputs/document.md",
                "inputs/document.md",
            ),
        ),
        (
            DependencyContent(
                "inputs/document.md",
                b"alpha\r\nbeta\n",
            ),
        ),
    )
    return build_fragment_success_evidence(
        run_state=run_state or _run_state(),
        scope=_scope(),
        ordinal=3,
        compiler_contract=_fragment_contract(),
        compiled_prompt_fragment_identity=_sha(b"compiled-fragment"),
        snapshot=snapshot,
        instruction="Read these inputs.",
        instruction_source="default_required",
        compose_final_prompt=lambda _rendered: canonical_composed,
    ).evidence


def _role(module, schema_version: str, payload: dict) -> dict:
    return {
        "schema_version": schema_version,
        "payload": payload,
        "sha256": module.canonical_sha256(payload),
    }


def _identity_roles(
    *,
    identity_schema_version: str,
    phased: bool,
    model: str = "gpt-5",
) -> dict:
    from orchestrator.workflow import prompt_identity as identity

    retained = _fragment_v1_record()
    resolved_rows = [
        {
            "slot_name": "required_document",
            "slot_kind": "doc",
            "refinement": None,
            "output_role": "none",
            "delivery": "dependency",
            "renderer": None,
            "value_sha256": identity.prompt_fragment_transport_value_sha256(
                retained["authored_rows"][0]["evaluated_relpath"]
            ),
            "rendered_bytes_sha256": None,
        },
    ]
    roles = {
        "fragment_program": identity.build_fragment_program_role(
            identity_schema_version=identity_schema_version,
            compiled_prompt_fragment_identity=(
                retained["compiled_prompt_fragment_identity"]
            ),
        ),
        "resolved_bindings": _role(
            identity,
            "workflow_prompt_attempt_resolved_bindings.v1",
            {
                "binding_plan_sha256": _sha(b"binding-plan"),
                "rows": resolved_rows,
            },
        ),
        "injected_dependencies": identity.build_injected_dependencies_role(
            canonical_groups=retained["canonical_groups"],
            injection=retained["injection"],
        ),
        "runtime_contributions": (
            identity.build_runtime_contributions_role(())
        ),
    }
    if phased:
        roles["provider_policy"] = identity.build_provider_policy_role_v2(
            {
                "provider_name": "codex",
                "model": model,
                "effort": "high",
                "timeout_sec": 1800,
                "transport": {
                    "kind": "interactive_terminal_turn_queue",
                    "schema_version": "interactive_terminal_turn_queue.v1",
                },
                "phased_call_policy": {
                    "delivery": "phased",
                    "materialization_attempts": 2,
                },
            }
        )
    else:
        roles["provider_policy"] = identity.build_provider_policy_role(
            {
                "provider_name": "codex",
                "model": "gpt-5",
                "effort": "high",
                "timeout_sec": 1800,
                "input_mode": "stdin",
            }
        )
    return roles


def _identity_v2(
    *,
    identity_schema_version: str = "compiled_prompt_fragment_identity.v1",
    cut: CanonicalPromptCut | None = None,
    actual_deliveries: tuple = (),
    model: str = "gpt-5",
) -> dict:
    from orchestrator.workflow import prompt_identity as identity

    return dict(
        identity.build_prompt_attempt_identity_v2(
            roles=_identity_roles(
                identity_schema_version=identity_schema_version,
                phased=True,
                model=model,
            ),
            cut=cut or _canonical_cut(),
            actual_deliveries=actual_deliveries,
        )
    )
