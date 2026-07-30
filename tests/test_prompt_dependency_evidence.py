"""Functional immutable evidence for provider prompt dependencies."""

from __future__ import annotations

import ast
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from orchestrator.deps.content_snapshot import (
    AuthoredDependencyRow,
    DependencyContent,
    build_content_snapshot,
    render_content_snapshot,
)
from orchestrator.state import RunState, StateManager
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


def _reseal(record: dict) -> dict:
    payload = deepcopy(record)
    payload.pop("record_sha256", None)
    record["record_sha256"] = _sha(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    )
    return record


def _reseal_v3(record: dict) -> dict:
    from orchestrator.workflow.prompt_identity import (
        prompt_fragment_record_sha256,
    )

    record["record_sha256"] = prompt_fragment_record_sha256(record)
    return record


def _reseal_index(index: dict) -> dict:
    payload = deepcopy(index)
    payload.pop("index_sha256", None)
    index["index_sha256"] = _sha(
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("ascii")
    )
    return index


def _contract(*, authored_instruction: bool = True):
    return _build_compiler_prompt_dependency_contract(
        required_binding_refs=("required-document",),
        optional_binding_refs=("optional-notes",),
        position=PromptDependencyPosition.PREPEND,
        instruction="Read these inputs." if authored_instruction else None,
        source_origin_key="provider-result",
        source_workflow_bytes=b"(workflow evidence)",
    )


def _implicit_empty_contract():
    return _build_compiler_prompt_dependency_contract(
        required_binding_refs=(),
        optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key="provider-supervision:worker",
        source_workflow_bytes=b"(workflow evidence)",
        origin_kind=(
            PromptDependencyOriginKind
            .WORKFLOW_LISP_PROVIDER_SUPERVISION_MEMBER_IMPLICIT_EMPTY
        ),
    )


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


def _snapshot_and_render():
    rows = (
        AuthoredDependencyRow(
            "required", 0, "required-document", "inputs/document.md", "inputs/document.md"
        ),
        AuthoredDependencyRow(
            "optional", 0, "optional-notes", "inputs/missing.md", None
        ),
    )
    snapshot = build_content_snapshot(
        rows,
        (DependencyContent("inputs/document.md", b"alpha\r\nbeta\n"),),
    )
    rendered = render_content_snapshot(snapshot, "Read these inputs.")
    return snapshot, rendered


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


def _success_record(
    *,
    ordinal: int = 3,
    root: str | Path = "/tmp/aggregate-run",
    run_state: RunState | None = None,
    final_prompt: bytes = b"Read these inputs.\n\nbase prompt",
):
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    snapshot, _ = _snapshot_and_render()
    return build_success_evidence(
        run_state=run_state or _run_state(root),
        scope=_scope(),
        ordinal=ordinal,
        compiler_contract=_contract(),
        snapshot=snapshot,
        instruction="Read these inputs.",
        instruction_source="authored",
        compose_final_prompt=lambda _rendered: final_prompt,
    ).evidence


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


@pytest.mark.parametrize(
    "identity_schema_version",
    (
        "compiled_prompt_fragment_identity.v1",
        "compiled_prompt_fragment_identity.v2",
    ),
)
def test_fragment_v3_record_is_exact_content_free_and_cross_bound(
    identity_schema_version: str,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        FRAGMENT_SUCCESS_SCHEMA_V3,
        build_fragment_success_evidence_v3,
        canonical_record_bytes,
        validate_fragment_success_evidence_v3,
    )

    retained_v1 = _fragment_v1_record()
    cut = _canonical_cut()
    identity = _identity_v2(
        identity_schema_version=identity_schema_version,
        cut=cut,
    )

    record = build_fragment_success_evidence_v3(
        retained_v1=retained_v1,
        cut=cut,
        prompt_attempt_identity=identity,
        compiler_fragment_identity_schema_version=(
            identity_schema_version
        ),
    )

    assert set(record) == {
        "schema",
        "record_kind",
        "run",
        "compiler_contract",
        "attempt",
        "authored_rows",
        "canonical_groups",
        "instruction",
        "injection",
        "compiled_prompt_fragment_identity",
        "canonical_composed",
        "prompt_attempt_identity",
        "record_sha256",
    }
    assert record["schema"] == FRAGMENT_SUCCESS_SCHEMA_V3
    assert record["record_kind"] == "prompt_snapshot"
    assert "final_prompt" not in record
    assert record["canonical_composed"] == identity["canonical_composed"]
    assert record["canonical_composed"] == {
        "bytes": len(cut.canonical_composed),
        "sha256": _sha(cut.canonical_composed),
    }
    assert validate_fragment_success_evidence_v3(
        record,
        compiler_fragment_identity_schema_version=(
            identity_schema_version
        ),
    ) == record
    payload = canonical_record_bytes(
        record,
        compiler_fragment_identity_schema_version=(
            identity_schema_version
        ),
    )
    assert payload == json.dumps(
        record,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert b"base prompt" not in payload


def test_fragment_v3_builder_requires_the_validated_canonical_cut() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v3,
    )

    with pytest.raises(TypeError, match="CanonicalPromptCut"):
        build_fragment_success_evidence_v3(
            retained_v1=_fragment_v1_record(),
            cut=object(),  # pyright: ignore[reportArgumentType]
            prompt_attempt_identity=_identity_v2(),
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v1"
            ),
        )


def test_fragment_v3_uses_the_fragment_utf8_seal_owner_for_unicode() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v3,
        canonical_record_bytes,
        validate_fragment_success_evidence_v3,
    )
    from orchestrator.workflow.prompt_identity import (
        prompt_fragment_record_sha256,
    )

    record = build_fragment_success_evidence_v3(
        retained_v1=_fragment_v1_record(),
        cut=_canonical_cut(),
        prompt_attempt_identity=_identity_v2(model="gpt-5-λ"),
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )

    assert record["record_sha256"] == prompt_fragment_record_sha256(record)
    assert validate_fragment_success_evidence_v3(
        record,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    ) == record
    payload = canonical_record_bytes(
        record,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )
    assert "λ".encode("utf-8") in payload
    assert b"\\u03bb" not in payload

    cross_field_tamper = deepcopy(record)
    cross_field_tamper["compiled_prompt_fragment_identity"] = _sha(
        b"different-fragment"
    )
    _reseal_v3(cross_field_tamper)
    with pytest.raises(ValueError, match="fragment program disagrees"):
        validate_fragment_success_evidence_v3(
            cross_field_tamper,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v1"
            ),
        )


def test_fragment_v3_retains_complete_validated_actual_delivery_prefix() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v3,
        validate_fragment_success_evidence_v3,
    )
    from orchestrator.workflow.prompt_identity import canonical_json_bytes
    from orchestrator.workflow.provider_phased_delivery.frames import (
        render_initial_materialization_turn,
        render_task_turn,
    )

    cut = _canonical_cut()
    deliveries = (
        render_task_turn(cut=cut),
        render_initial_materialization_turn(
            cut=cut,
            submit_keys=("ENTER",),
        ),
    )
    identity = _identity_v2(
        cut=cut,
        actual_deliveries=deliveries,
    )

    record = build_fragment_success_evidence_v3(
        retained_v1=_fragment_v1_record(),
        cut=cut,
        prompt_attempt_identity=identity,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )

    assert record["prompt_attempt_identity"]["actual_deliveries"] == json.loads(
        canonical_json_bytes(identity["actual_deliveries"])
    )
    assert [
        row["phase"]
        for row in record["prompt_attempt_identity"]["actual_deliveries"]
    ] == ["task", "initial_materialization"]
    assert validate_fragment_success_evidence_v3(
        record,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    ) == record


@pytest.mark.parametrize(
    "mutation",
    (
        "extra_key",
        "missing_key",
        "forbidden_final_prompt",
        "canonical_composed",
        "compiled_fragment",
        "resolved_document",
        "injected_dependencies",
        "record_seal",
    ),
)
def test_fragment_v3_rejects_resealed_cross_field_and_shape_tampering(
    mutation: str,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v3,
        validate_fragment_success_evidence_v3,
    )

    record = build_fragment_success_evidence_v3(
        retained_v1=_fragment_v1_record(),
        cut=_canonical_cut(),
        prompt_attempt_identity=_identity_v2(),
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )
    candidate = deepcopy(record)
    if mutation == "extra_key":
        candidate["unexpected"] = None
    elif mutation == "missing_key":
        candidate.pop("canonical_groups")
    elif mutation == "forbidden_final_prompt":
        candidate["final_prompt"] = deepcopy(
            _fragment_v1_record()["final_prompt"]
        )
    elif mutation == "canonical_composed":
        candidate["canonical_composed"]["sha256"] = _sha(
            b"different-composition"
        )
    elif mutation == "compiled_fragment":
        candidate["compiled_prompt_fragment_identity"] = _sha(
            b"different-fragment"
        )
    elif mutation == "resolved_document":
        candidate["authored_rows"][0]["evaluated_relpath"] = (
            "inputs/different.md"
        )
    elif mutation == "injected_dependencies":
        candidate["injection"]["block_sha256"] = _sha(
            b"different-injection"
        )
    elif mutation == "record_seal":
        candidate["record_sha256"] = _sha(b"wrong-record-seal")
    else:  # pragma: no cover
        raise AssertionError(mutation)
    if mutation not in {"record_seal"}:
        _reseal_v3(candidate)

    with pytest.raises((TypeError, ValueError)):
        validate_fragment_success_evidence_v3(
            candidate,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v1"
            ),
        )


def test_fragment_v3_rejects_identity_delivery_or_composition_tampering() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v3,
        validate_fragment_success_evidence_v3,
    )

    record = build_fragment_success_evidence_v3(
        retained_v1=_fragment_v1_record(),
        cut=_canonical_cut(),
        prompt_attempt_identity=_identity_v2(),
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )
    for field, replacement in (
        ("actual_deliveries", [{"delivery_ordinal": 0}]),
        ("composition_sha256", _sha(b"wrong-composition-seal")),
    ):
        candidate = deepcopy(record)
        candidate["prompt_attempt_identity"][field] = replacement
        _reseal_v3(candidate)
        with pytest.raises((TypeError, ValueError)):
            validate_fragment_success_evidence_v3(
                candidate,
                compiler_fragment_identity_schema_version=(
                    "compiled_prompt_fragment_identity.v1"
                ),
            )


def test_fragment_evidence_versions_remain_strictly_paired() -> None:
    from orchestrator.workflow import prompt_identity as identity
    from orchestrator.workflow.prompt_dependency_evidence import (
        FRAGMENT_SUCCESS_SCHEMA,
        FRAGMENT_SUCCESS_SCHEMA_V2,
        build_fragment_success_evidence_v2,
        build_fragment_success_evidence_v3,
        canonical_record_bytes,
        validate_fragment_success_evidence,
        validate_fragment_success_evidence_v2,
    )

    retained_v1 = _fragment_v1_record()
    final_prompt = b"Read these inputs.\n\nbase prompt"
    identity_v1 = identity.build_prompt_attempt_identity(
        roles=_identity_roles(
            identity_schema_version=(
                "compiled_prompt_fragment_identity.v1"
            ),
            phased=False,
        ),
        final_prompt=final_prompt,
    )
    retained_v2 = build_fragment_success_evidence_v2(
        retained_v1=retained_v1,
        prompt_attempt_identity=identity_v1,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )

    assert retained_v1["schema"] == FRAGMENT_SUCCESS_SCHEMA
    assert retained_v2["schema"] == FRAGMENT_SUCCESS_SCHEMA_V2
    assert validate_fragment_success_evidence(retained_v1) == retained_v1
    assert validate_fragment_success_evidence_v2(
        retained_v2,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    ) == retained_v2
    assert canonical_record_bytes(retained_v1)
    assert canonical_record_bytes(
        retained_v2,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )

    with pytest.raises((TypeError, ValueError)):
        build_fragment_success_evidence_v3(
            retained_v1=retained_v1,
            cut=_canonical_cut(),
            prompt_attempt_identity=identity_v1,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v1"
            ),
        )
    with pytest.raises((TypeError, ValueError)):
        build_fragment_success_evidence_v2(
            retained_v1=retained_v1,
            prompt_attempt_identity=_identity_v2(),
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v1"
            ),
        )


def test_fragment_v3_reuses_publication_owner_and_has_no_ledger_input() -> None:
    import inspect

    from orchestrator.workflow import prompt_dependency_evidence as evidence

    signature = inspect.signature(
        evidence.build_fragment_success_evidence_v3
    )
    assert "ledger" not in signature.parameters
    assert "phase_ledger" not in inspect.getsource(
        evidence.build_fragment_success_evidence_v3
    )
    assert evidence.evidence_relative_path(_scope(), 3) == Path(
        "workflow_lisp",
        "prompt_dependencies",
        hashlib.sha256(b"ProviderStep").hexdigest()[:24],
        _scope().key[7:31],
        "attempt-000003.json",
    )


def test_success_record_is_closed_content_free_and_self_validating() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        SUCCESS_SCHEMA,
        canonical_record_bytes,
        validate_success_evidence,
    )

    record = _success_record()
    assert set(record) == {
        "schema", "record_kind", "run", "compiler_contract", "attempt", "authored_rows",
        "canonical_groups", "instruction", "injection", "final_prompt",
        "record_sha256",
    }
    assert record["schema"] == SUCCESS_SCHEMA
    assert record["record_kind"] == "prompt_snapshot"
    assert record["run"] == {
        "run_id": _scope().run_id,
        "workflow_file": "workflow.orc",
        "workflow_checksum": "sha256:" + "1" * 64,
    }
    assert record["authored_rows"][0]["row_id"].startswith("sha256:")
    assert record["attempt"]["ordinal"] == 3
    assert record["authored_rows"][1]["status"] == "absent"
    assert record["canonical_groups"][0]["retained_sha256"] == _sha(b"alpha\r\nbeta\n")
    assert record["instruction"] == {
        "source": "authored",
        "bytes": len(b"Read these inputs."),
        "sha256": _sha(b"Read these inputs."),
    }
    assert canonical_record_bytes(record).endswith(b"}")
    assert not canonical_record_bytes(record).endswith(b"\n")
    serialized = canonical_record_bytes(record)
    assert b"alpha" not in serialized
    assert b"base prompt" not in serialized
    assert validate_success_evidence(record) == record


def test_success_build_operation_renders_exactly_once_and_returns_authoritative_render(
    monkeypatch,
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    snapshot, _ = _snapshot_and_render()
    actual_render = evidence.render_content_snapshot
    calls: list[tuple[object, object]] = []

    def counted_render(snapshot_arg, instruction_arg):
        calls.append((snapshot_arg, instruction_arg))
        return actual_render(snapshot_arg, instruction_arg)

    monkeypatch.setattr(evidence, "render_content_snapshot", counted_render)
    result = evidence.build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=_contract(), snapshot=snapshot,
        instruction="Read these inputs.", instruction_source="authored",
        compose_final_prompt=lambda authoritative: authoritative.block + b"\n\nbase",
    )
    assert len(calls) == 1
    assert result.rendered == actual_render(snapshot, "Read these inputs.")
    assert result.final_prompt == result.rendered.block + b"\n\nbase"
    assert result.evidence["injection"]["block_sha256"] == _sha(result.rendered.block)
    assert result.evidence["final_prompt"]["sha256"] == _sha(result.final_prompt)


def test_implicit_empty_success_evidence_records_byte_exact_prompt_noop() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_success_evidence,
        validate_success_evidence,
    )

    snapshot = build_content_snapshot((), ())
    base_prompt = b"Unchanged base prompt.\n"
    composed_from = []

    def compose_final_prompt(rendered):
        composed_from.append(rendered)
        assert rendered.block == b""
        return base_prompt

    build = build_success_evidence(
        run_state=_run_state(),
        scope=_scope(),
        ordinal=1,
        compiler_contract=_implicit_empty_contract(),
        snapshot=snapshot,
        instruction="",
        instruction_source="none",
        compose_final_prompt=compose_final_prompt,
    )

    assert composed_from == [build.rendered]
    assert build.final_prompt == base_prompt
    assert build.rendered.block == b""
    assert build.rendered.pre_truncation_bytes == 0
    assert build.rendered.group_truncations == ()
    record = build.evidence
    assert record["authored_rows"] == []
    assert record["canonical_groups"] == []
    assert record["instruction"] == {
        "source": "none",
        "bytes": 0,
        "sha256": _sha(b""),
    }
    assert record["injection"] == {
        "mode": "content",
        "max_bytes": 262144,
        "instruction_max_bytes": 261630,
        "summary_reserve_bytes": 512,
        "position": "prepend",
        "was_truncated": False,
        "pre_truncation_bytes": 0,
        "block_bytes": 0,
        "block_sha256": _sha(b""),
        "normalized_total_bytes": 0,
        "retained_bytes": 0,
        "shown_bytes": 0,
        "files_total": 0,
        "files_shown": 0,
        "files_truncated": 0,
        "files_omitted": 0,
        "summary_bytes": 0,
        "summary_sha256": None,
    }
    assert record["final_prompt"] == {
        "bytes": len(base_prompt),
        "sha256": _sha(base_prompt),
    }
    assert validate_success_evidence(record) == record


@pytest.mark.parametrize(
    ("path", "replacement"),
    [
        (("attempt", "ordinal"), 0),
        (("authored_rows", 0, "binding_ref"), "wrong"),
        (("canonical_groups", 0, "shown_bytes"), 999),
        (("instruction", "source"), "default_optional"),
        (("injection", "position"), "append"),
        (("final_prompt", "sha256"), "sha256:" + "0" * 64),
    ],
)
def test_success_validator_rejects_cross_field_or_digest_tampering(path, replacement) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = deepcopy(_success_record())
    cursor = record
    for part in path[:-1]:
        cursor = cursor[part]
    cursor[path[-1]] = replacement
    with pytest.raises(ValueError):
        validate_success_evidence(record)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda record: record["compiler_contract"].__setitem__("origin_kind", "other"), "compiler"),
        (lambda record: record["authored_rows"][0].__setitem__("status", "absent"), "required"),
        (lambda record: record["canonical_groups"][0].__setitem__("effective_role", "optional"), "role"),
        (lambda record: record["canonical_groups"][0].__setitem__("shown_sha256", None), "digest"),
        (lambda record: record["injection"].__setitem__("mode", "list"), "injection"),
    ],
)
def test_success_validator_rejects_internally_resealed_contract_tampering(mutate, message) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _success_record()
    mutate(record)
    _reseal(record)
    with pytest.raises(ValueError, match=message):
        validate_success_evidence(record)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda record: record["instruction"].__setitem__("bytes", 261631),
        lambda record: record["injection"].__setitem__("summary_bytes", 513),
        lambda record: record["injection"].__setitem__("pre_truncation_bytes", 1),
        lambda record: record["injection"].__setitem__("block_bytes", 1),
        lambda record: record["injection"].__setitem__(
            "pre_truncation_bytes", record["injection"]["block_bytes"] + 1
        ),
        lambda record: record["authored_rows"][0].__setitem__("authored_index", False),
        lambda record: record["canonical_groups"][0].__setitem__("order", False),
    ],
)
def test_success_validator_rejects_internally_resealed_byte_cap_violations(mutate) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _success_record()
    mutate(record)
    _reseal(record)
    with pytest.raises(ValueError):
        validate_success_evidence(record)


def test_success_groups_may_be_lexical_when_authored_target_order_differs() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=("z-binding", "a-binding"), optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND, instruction="Read.",
        source_origin_key="provider-result", source_workflow_bytes=b"workflow",
    )
    snapshot = build_content_snapshot(
        (
            AuthoredDependencyRow("required", 0, "z-binding", "z.txt", "z.txt"),
            AuthoredDependencyRow("required", 1, "a-binding", "a.txt", "a.txt"),
        ),
        (DependencyContent("z.txt", b"z"), DependencyContent("a.txt", b"a")),
    )
    record = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot,
        instruction="Read.", instruction_source="authored",
        compose_final_prompt=lambda _rendered: b"final",
    ).evidence
    assert [group["canonical_target"] for group in record["canonical_groups"]] == ["a.txt", "z.txt"]


def _three_group_success_record() -> dict:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=("a", "b", "c"), optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND, instruction="Read.",
        source_origin_key="provider-result", source_workflow_bytes=b"workflow",
    )
    snapshot = build_content_snapshot(
        tuple(
            AuthoredDependencyRow("required", index, name, f"{name}.txt", f"{name}.txt")
            for index, name in enumerate(("a", "b", "c"))
        ),
        tuple(DependencyContent(f"{name}.txt", name.encode() * 2) for name in ("a", "b", "c")),
    )
    return build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot, instruction="Read.",
        instruction_source="authored",
        compose_final_prompt=lambda rendered: rendered.block + b"\nbase",
    ).evidence


def _make_resealed_truncated_injection(record: dict) -> None:
    injection = record["injection"]
    injection["was_truncated"] = True
    injection["pre_truncation_bytes"] = injection["block_bytes"] + 1
    injection["summary_bytes"] = 1
    injection["summary_sha256"] = _sha(b"s")


def test_success_validator_rejects_omitted_group_before_complete_group() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _three_group_success_record()
    first = record["canonical_groups"][0]
    first["render_status"] = "omitted"
    first["shown_bytes"] = 0
    first["shown_sha256"] = None
    injection = record["injection"]
    injection["shown_bytes"] -= first["normalized_total_bytes"]
    injection["files_shown"] = 2
    injection["files_omitted"] = 1
    _make_resealed_truncated_injection(record)
    _reseal(record)
    with pytest.raises(ValueError, match="order"):
        validate_success_evidence(record)


def test_success_validator_rejects_multiple_truncated_groups() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_success_evidence

    record = _three_group_success_record()
    for group in record["canonical_groups"][1:]:
        group["render_status"] = "truncated"
        group["shown_bytes"] = 1
        group["shown_sha256"] = _sha(group["canonical_target"][0].encode())
    injection = record["injection"]
    injection["shown_bytes"] = 4
    injection["files_truncated"] = 2
    _make_resealed_truncated_injection(record)
    _reseal(record)
    with pytest.raises(ValueError, match="truncated"):
        validate_success_evidence(record)


@pytest.mark.parametrize(
    ("sizes", "expected_statuses"),
    [
        ((16, 262144, 10), ["complete", "truncated", "omitted"]),
        ((261960, 1000), ["complete", "omitted"]),
    ],
)
def test_success_builder_accepts_real_renderer_disposition_sequences(
    sizes, expected_statuses
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_success_evidence,
        validate_success_evidence,
    )

    names = tuple(chr(ord("a") + index) for index in range(len(sizes)))
    contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=names, optional_binding_refs=(),
        position=PromptDependencyPosition.PREPEND, instruction="Read.",
        source_origin_key="provider-result", source_workflow_bytes=b"workflow",
    )
    snapshot = build_content_snapshot(
        tuple(
            AuthoredDependencyRow("required", index, name, f"{name}.txt", f"{name}.txt")
            for index, name in enumerate(names)
        ),
        tuple(
            DependencyContent(f"{name}.txt", name.encode() * size)
            for name, size in zip(names, sizes)
        ),
    )
    result = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot, instruction="Read.",
        instruction_source="authored",
        compose_final_prompt=lambda rendered: rendered.block + b"\nbase",
    )
    assert [row.status for row in result.rendered.group_truncations] == expected_statuses
    assert [group["render_status"] for group in result.evidence["canonical_groups"]] == expected_statuses
    assert validate_success_evidence(result.evidence) == result.evidence


@pytest.mark.parametrize("invalid", [3, True, [65, 66]])
def test_success_builder_requires_exact_final_prompt_bytes(invalid) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    snapshot, _ = _snapshot_and_render()
    with pytest.raises(TypeError, match="final_prompt"):
        build_success_evidence(
            run_state=_run_state(), scope=_scope(), ordinal=1,
            compiler_contract=_contract(), snapshot=snapshot,
            instruction="Read these inputs.", instruction_source="authored",
            compose_final_prompt=lambda _rendered: invalid,
        )

def test_default_instruction_source_is_derived_from_compiler_contract() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import build_success_evidence

    snapshot, _ = _snapshot_and_render()
    contract = _contract(authored_instruction=False)
    instruction = "Default required instruction."
    rendered = render_content_snapshot(snapshot, instruction)
    build = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=contract, snapshot=snapshot,
        instruction=instruction, instruction_source="default_required",
        compose_final_prompt=lambda authoritative: authoritative.block + b"\n\nbase",
    )
    assert build.evidence["instruction"]["source"] == "default_required"
    assert build.rendered == rendered
    with pytest.raises(ValueError, match="source"):
        build_success_evidence(
            run_state=_run_state(), scope=_scope(), ordinal=1,
            compiler_contract=contract, snapshot=snapshot,
            instruction=instruction, instruction_source="default_optional",
            compose_final_prompt=lambda _rendered: b"base",
        )

    optional_contract = _build_compiler_prompt_dependency_contract(
        required_binding_refs=(),
        optional_binding_refs=("optional-notes",),
        position=PromptDependencyPosition.PREPEND,
        instruction=None,
        source_origin_key="provider-result",
        source_workflow_bytes=b"(workflow evidence)",
    )
    optional_snapshot = build_content_snapshot(
        (
            AuthoredDependencyRow(
                "optional", 0, "optional-notes", "inputs/notes.md", "inputs/notes.md"
            ),
        ),
        (DependencyContent("inputs/notes.md", b"notes"),),
    )
    optional_instruction = "Default optional instruction."
    optional = build_success_evidence(
        run_state=_run_state(), scope=_scope(), ordinal=1,
        compiler_contract=optional_contract, snapshot=optional_snapshot,
        instruction=optional_instruction,
        instruction_source="default_optional",
        compose_final_prompt=lambda _rendered: b"base",
    )
    assert optional.evidence["instruction"]["source"] == "default_optional"


def test_failure_record_is_closed_functional_and_self_validating() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        FAILURE_SCHEMA,
        build_failure_evidence,
        validate_failure_evidence,
    )

    record = build_failure_evidence(
        run_state=_run_state(),
        scope=_scope(),
        ordinal=3,
        compiler_contract=_contract(),
        category="missing_required_dependency",
        operation="resolve",
    )
    assert set(record) == {
        "schema", "record_kind", "run", "compiler_contract", "attempt", "failure",
        "provider_calls", "record_sha256",
    }
    assert record["schema"] == FAILURE_SCHEMA
    assert record["record_kind"] == "failure"
    assert record["provider_calls"] == {"preparation": False, "execution": False}
    assert record["failure"]["authored_row_id"] is None
    assert record["failure"]["evaluated_relpath"] is None
    assert validate_failure_evidence(record) == record

    for field, bad in (("category", "permission_denied"), ("operation", "stat")):
        tampered = deepcopy(record)
        tampered["failure"][field] = bad
        with pytest.raises(ValueError):
            validate_failure_evidence(tampered)

    with pytest.raises(ValueError, match="authored row"):
        build_failure_evidence(
            run_state=_run_state(), scope=_scope(), ordinal=3,
            compiler_contract=_contract(), category="unreadable_dependency",
            operation="read", authored_row_id="sha256:" + "0" * 64,
            evaluated_relpath="inputs/document.md",
        )


def test_evidence_path_is_derived_only_from_attempt_identity() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import evidence_relative_path

    path = evidence_relative_path(_scope(), 3)
    assert path.as_posix().startswith("workflow_lisp/prompt_dependencies/")
    assert path.as_posix().endswith("/attempt-000003.json")
    assert len(path.parts[-3]) == len(path.parts[-2]) == 24
    assert evidence_relative_path(_scope(), 3) == path


def _manager_with_allocations(tmp_path: Path, count: int = 3) -> StateManager:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "workflow.orc").write_text("(workflow evidence)\n", encoding="utf-8")
    manager = StateManager(
        workspace,
        run_id=_scope().run_id,
        state_dir=tmp_path / "runs",
    )
    manager.initialize("workflow.orc")
    assert manager.state is not None
    manager.state.step_visits["Provider"] = 2
    manager.state.current_step = {
        "name": "Provider", "step_id": "ProviderStep", "visit_count": 2,
    }
    manager._write_state()
    for expected in range(1, count + 1):
        assert manager.allocate_provider_attempt(_scope()) == expected
    return manager


def test_publish_is_immutable_no_clobber_and_leaves_allocator_state_unchanged(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import publish_evidence_file

    manager = _manager_with_allocations(tmp_path)
    assert manager.state is not None
    record = _success_record(run_state=manager.state)
    state_before = manager.state_file.read_bytes()
    result = publish_evidence_file(
        manager,
        _scope(),
        3,
        record,
    )
    assert (manager.run_root / result.relative_path).read_bytes() == result.payload
    assert manager.state_file.read_bytes() == state_before
    assert list((manager.run_root / result.relative_path.parent).glob(".*.tmp")) == []

    with pytest.raises(FileExistsError):
        publish_evidence_file(manager, _scope(), 3, record)
    assert (manager.run_root / result.relative_path).read_bytes() == result.payload
    assert manager.state_file.read_bytes() == state_before


def test_fragment_v3_reuses_existing_immutable_publication_owner(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        build_fragment_success_evidence_v3,
        publish_evidence_file,
    )

    manager = _manager_with_allocations(tmp_path)
    assert manager.state is not None
    record = build_fragment_success_evidence_v3(
        retained_v1=_fragment_v1_record(run_state=manager.state),
        cut=_canonical_cut(),
        prompt_attempt_identity=_identity_v2(),
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )

    state_before = manager.state_file.read_bytes()
    result = publish_evidence_file(
        manager,
        _scope(),
        3,
        record,
        compiler_fragment_identity_schema_version=(
            "compiled_prompt_fragment_identity.v1"
        ),
    )

    assert (manager.run_root / result.relative_path).read_bytes() == (
        result.payload
    )
    assert manager.state_file.read_bytes() == state_before
    with pytest.raises(FileExistsError):
        publish_evidence_file(
            manager,
            _scope(),
            3,
            record,
            compiler_fragment_identity_schema_version=(
                "compiled_prompt_fragment_identity.v1"
            ),
        )
    assert manager.state_file.read_bytes() == state_before


def test_publish_rejects_same_or_conflicting_crash_orphan(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
        evidence_relative_path,
        publish_evidence_file,
    )

    manager = _manager_with_allocations(tmp_path)
    record = _success_record(run_state=manager.state)
    state_before = manager.state_file.read_bytes()
    destination = manager.run_root / evidence_relative_path(_scope(), 3)
    destination.parent.mkdir(parents=True)
    original_payload = canonical_record_bytes(record)
    destination.write_bytes(original_payload)
    with pytest.raises(FileExistsError):
        publish_evidence_file(manager, _scope(), 3, record)
    changed = _success_record(
        ordinal=3, run_state=manager.state, final_prompt=b"different final prompt"
    )
    with pytest.raises(FileExistsError):
        publish_evidence_file(manager, _scope(), 3, changed)
    assert destination.read_bytes() == original_payload
    assert manager.state_file.read_bytes() == state_before


def test_stale_counter_collision_preserves_prior_evidence_and_advances(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        evidence_relative_path,
        publish_evidence_file,
    )

    manager = _manager_with_allocations(tmp_path, count=1)
    destination = manager.run_root / evidence_relative_path(_scope(), 2)
    destination.parent.mkdir(parents=True)
    sentinel = b'{"partial":"stale-counter-collision"'
    destination.write_bytes(sentinel)

    assert manager.allocate_provider_attempt(_scope()) == 2
    with pytest.raises(FileExistsError):
        publish_evidence_file(
            manager,
            _scope(),
            2,
            _success_record(ordinal=2, run_state=manager.state),
        )

    assert destination.read_bytes() == sentinel
    assert manager.allocate_provider_attempt(_scope()) == 3


def test_publish_link_failure_leaves_allocator_state_unchanged(
    tmp_path: Path, monkeypatch
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    manager = _manager_with_allocations(tmp_path)
    state_before = manager.state_file.read_bytes()
    monkeypatch.setattr(evidence.os, "link", lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("link failed")))
    with pytest.raises(OSError, match="link failed"):
        evidence.publish_evidence_file(
            manager, _scope(), 3, _success_record(run_state=manager.state),
        )
    assert manager.state_file.read_bytes() == state_before


def test_publish_rejects_unallocated_attempt_before_linking_record(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        evidence_relative_path,
        publish_evidence_file,
    )

    manager = _manager_with_allocations(tmp_path, count=2)
    with pytest.raises(ValueError, match="allocation ordinal"):
        publish_evidence_file(
            manager, _scope(), 3,
            _success_record(ordinal=3, run_state=manager.state),
        )
    assert not (manager.run_root / evidence_relative_path(_scope(), 3)).exists()


def test_publish_completes_short_writes_without_mutating_allocator_state(
    tmp_path: Path, monkeypatch
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    manager = _manager_with_allocations(tmp_path)
    actual_write = evidence.os.write
    write_sizes: list[tuple[int, int]] = []

    def short_write(fd, payload):
        requested = len(payload)
        written = actual_write(fd, payload[: max(1, requested // 3)])
        write_sizes.append((requested, written))
        return written

    state_before = manager.state_file.read_bytes()
    monkeypatch.setattr(evidence.os, "write", short_write)
    result = evidence.publish_evidence_file(
        manager, _scope(), 3, _success_record(run_state=manager.state)
    )
    assert (manager.run_root / result.relative_path).read_bytes() == result.payload
    assert len(write_sizes) > 1
    assert all(0 < written <= requested for requested, written in write_sizes)
    assert manager.state_file.read_bytes() == state_before


def test_publish_fsync_failure_propagates_without_mutating_allocator_state(
    tmp_path: Path, monkeypatch
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    manager = _manager_with_allocations(tmp_path)
    state_before = manager.state_file.read_bytes()
    monkeypatch.setattr(
        evidence.os,
        "fsync",
        lambda _fd: (_ for _ in ()).throw(OSError("fsync failed")),
    )
    with pytest.raises(OSError, match="fsync failed"):
        evidence.publish_evidence_file(
            manager, _scope(), 3, _success_record(run_state=manager.state)
        )
    assert manager.state_file.read_bytes() == state_before


@pytest.mark.parametrize(
    "writer_name", ("_write_current_no_replace", "_write_index_no_replace")
)
def test_first_publication_durably_syncs_every_new_directory_in_missing_chain(
    tmp_path: Path, monkeypatch, writer_name: str
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    anchor = tmp_path / "existing-anchor"
    anchor.mkdir()
    first = anchor / "first"
    leaf = first / "leaf"
    destination = leaf / "record.json"
    synced: list[Path] = []
    monkeypatch.setattr(evidence, "_fsync_directory", lambda path: synced.append(path))

    getattr(evidence, writer_name)(destination, b"payload", anchor)

    assert destination.read_bytes() == b"payload"
    assert synced == [first, anchor, leaf, first, leaf, leaf]


@pytest.mark.parametrize(
    "writer_name", ("_write_current_no_replace", "_write_index_no_replace")
)
def test_publication_reuses_complete_directory_chain_without_recreating_it(
    tmp_path: Path, monkeypatch, writer_name: str
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    anchor = tmp_path / "anchor"
    leaf = anchor / "existing" / "leaf"
    leaf.mkdir(parents=True)
    destination = leaf / "record.json"
    mkdir_calls: list[Path] = []
    synced: list[Path] = []
    actual_mkdir = Path.mkdir

    def observed_mkdir(path: Path, *args, **kwargs) -> None:
        mkdir_calls.append(path)
        actual_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", observed_mkdir)
    monkeypatch.setattr(evidence, "_fsync_directory", lambda path: synced.append(path))

    getattr(evidence, writer_name)(destination, b"payload", anchor)

    assert destination.read_bytes() == b"payload"
    assert mkdir_calls == []
    assert synced == [leaf.parent, anchor, leaf, leaf.parent, leaf, leaf]


@pytest.mark.parametrize(
    "writer_name", ("_write_current_no_replace", "_write_index_no_replace")
)
def test_publication_retry_resyncs_chain_after_parent_fsync_left_residue(
    tmp_path: Path, monkeypatch, writer_name: str
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    anchor = tmp_path / "durable-anchor"
    anchor.mkdir()
    first = anchor / "first"
    leaf = first / "leaf"
    destination = leaf / "record.json"
    failed_syncs: list[Path] = []

    def fail_first_parent_sync(path: Path) -> None:
        failed_syncs.append(path)
        if path == anchor:
            raise OSError("parent fsync failed")

    monkeypatch.setattr(evidence, "_fsync_directory", fail_first_parent_sync)
    with pytest.raises(OSError, match="parent fsync failed"):
        getattr(evidence, writer_name)(destination, b"payload", anchor)
    assert failed_syncs == [first, anchor]
    assert first.is_dir()
    assert not leaf.exists()

    retry_syncs: list[Path] = []
    monkeypatch.setattr(
        evidence, "_fsync_directory", lambda path: retry_syncs.append(path)
    )
    getattr(evidence, writer_name)(destination, b"payload", anchor)

    assert destination.read_bytes() == b"payload"
    assert retry_syncs == [first, anchor, leaf, first, leaf, leaf]


def test_durable_directory_chain_rejects_non_directory_anchor(tmp_path: Path) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    anchor = tmp_path / "anchor"
    anchor.write_text("not a directory", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        evidence._ensure_durable_directory_chain(anchor / "leaf", anchor)


def test_durable_directory_chain_rejects_target_outside_anchor(tmp_path: Path) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    anchor = tmp_path / "anchor"
    anchor.mkdir()

    with pytest.raises(ValueError, match="below durable anchor"):
        evidence._ensure_durable_directory_chain(tmp_path / "outside", anchor)


def test_serialized_success_evidence_recursively_excludes_body_sentinels() -> None:
    from orchestrator.workflow.prompt_dependency_evidence import canonical_record_bytes

    serialized = canonical_record_bytes(_success_record())
    for sentinel in (b"alpha", b"beta", b"base prompt", b"Read these inputs."):
        assert sentinel not in serialized


def _terminal_state(root: Path) -> RunState:
    scope = _scope()
    state = _run_state(root)
    state.status = "completed"
    state.provider_attempt_allocations = {
        scope.key: {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 1,
        }
    }
    return state


def test_allocator_projection_is_closed_sorted_and_externally_digestible(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        ALLOCATION_PROJECTION_SCHEMA,
        allocator_projection_sha256,
        build_allocator_projection,
        validate_allocator_projection,
    )

    projection = build_allocator_projection(_terminal_state(tmp_path))
    assert set(projection) == {"schema", "run", "scopes"}
    assert projection["schema"] == ALLOCATION_PROJECTION_SCHEMA
    assert projection["run"] == {
        "run_id": _scope().run_id,
        "workflow_file": "workflow.orc",
        "workflow_checksum": "sha256:" + "1" * 64,
    }
    row = projection["scopes"][0]
    assert set(row) == {
        "scope_sha256",
        "scope",
        "last_allocated_ordinal",
    }
    assert row["scope_sha256"] == _scope().key
    original_digest = allocator_projection_sha256(projection)
    assert original_digest.startswith("sha256:")
    assert validate_allocator_projection(projection) == projection

    advanced = deepcopy(projection)
    advanced["scopes"][0]["last_allocated_ordinal"] = 2
    assert validate_allocator_projection(advanced) == advanced
    assert allocator_projection_sha256(advanced) != original_digest

    open_row = deepcopy(projection)
    open_row["scopes"][0]["events"] = []
    with pytest.raises(ValueError, match="closed"):
        validate_allocator_projection(open_row)


def test_terminal_validation_builds_immutable_index_and_discloses_gap(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        INDEX_SCHEMA,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")

    result = validate_terminal_evidence(root, state_file)
    assert result.index["schema"] == INDEX_SCHEMA
    assert set(result.index) == {
        "schema", "run", "allocator_projection", "publications",
        "allocation_only_gaps", "index_sha256",
    }
    assert result.index["publications"] == []
    assert result.index["allocation_only_gaps"] == [
        {
            "scope_sha256": _scope().key,
            "runtime_step_id": "ProviderStep",
            "visit_key": _scope().key[7:31],
            "attempt_ordinal": 1,
        }
    ]
    assert result.initial_state_bytes == len(state_file.read_bytes())
    assert result.initial_state_sha256 == _sha(state_file.read_bytes())
    assert result.path.read_bytes() == result.payload
    assert validate_terminal_evidence(root, state_file).created is False


def test_terminal_validation_preserves_pre_q3_v1_snapshot_without_schema_authority(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    _install_published_record(root, state)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

    result = validate_terminal_evidence(root, state_file)

    assert (
        "prompt_fragment_identity_schema_version"
        not in state.provider_attempt_allocations[_scope().key]
    )
    assert result.index["publications"][0]["record_kind"] == "prompt_snapshot"


def test_terminal_validation_does_not_alias_equal_runtime_step_ids_across_scopes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow import prompt_dependency_evidence as evidence

    root = tmp_path / "run"
    root.mkdir()
    root_scope = _scope()
    call_scope_node = root_scope.to_dict()
    call_scope_node["resume_scope"]["call_frame_ids"] = ["frame-a"]
    call_scope = ProviderAttemptScope.from_dict(call_scope_node)
    authorities = {
        root_scope.key: "compiled_prompt_fragment_identity.v1",
        call_scope.key: "compiled_prompt_fragment_identity.v2",
    }
    scopes_by_path: dict[str, ProviderAttemptScope] = {}
    payloads: dict[str, bytes] = {}
    state = _run_state(root)
    state.status = "completed"
    state.provider_attempt_allocations = {}
    for scope in (root_scope, call_scope):
        relative = str(evidence.evidence_relative_path(scope, 1))
        scopes_by_path[relative] = scope
        payload = f"record:{scope.key}".encode("ascii")
        payloads[relative] = payload
        state.provider_attempt_allocations[scope.key] = {
            "scope": scope.to_dict(),
            "last_allocated_ordinal": 1,
            "prompt_fragment_identity_schema_version": authorities[
                scope.key
            ],
        }
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    observed: dict[str, str | None] = {}

    def read_record(
        path: Path,
        kind: str | None,
        *,
        compiler_fragment_identity_schema_version: str | None = None,
    ):
        relative = str(path.relative_to(root))
        scope = scopes_by_path[relative]
        observed[scope.key] = compiler_fragment_identity_schema_version
        return (
            {
                "record_kind": "prompt_snapshot",
                "run": evidence._state_run(state),
                "attempt": evidence._attempt(scope, 1),
                "record_sha256": _sha(f"record:{scope.key}".encode("ascii")),
            },
            payloads[relative],
        )

    monkeypatch.setattr(evidence, "_read_manifest_record", read_record)

    evidence.validate_terminal_evidence(root, state_file)

    assert observed == authorities
    assert root_scope.runtime_step_id == call_scope.runtime_step_id


def test_terminal_validation_rejects_misbound_scope_authority(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    scope = _scope()
    state.provider_attempt_allocations[scope.key][
        "prompt_fragment_identity_schema_version"
    ] = "compiled_prompt_fragment_identity.v2"
    misbound_key = "sha256:" + "0" * 64
    state.provider_attempt_allocations[misbound_key] = (
        state.provider_attempt_allocations.pop(scope.key)
    )
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="terminal state file is invalid",
    ):
        validate_terminal_evidence(root, state_file)


def test_index_rejects_conflicting_runtime_step_for_same_scope(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_index,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    entry = state.provider_attempt_allocations[_scope().key]
    entry["last_allocated_ordinal"] = 2
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    index = validate_terminal_evidence(root, state_file).index
    tampered = deepcopy(index)
    tampered["allocation_only_gaps"][1]["runtime_step_id"] = "ZProviderStep"
    _reseal_index(tampered)
    with pytest.raises(ValueError, match="runtime"):
        validate_index(tampered)


def test_index_rejects_unsorted_duplicate_and_self_digest_tampering(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_index,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    entry = state.provider_attempt_allocations[_scope().key]
    entry["last_allocated_ordinal"] = 2
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    index = validate_terminal_evidence(root, state_file).index

    unsorted = deepcopy(index)
    unsorted["allocation_only_gaps"].reverse()
    _reseal_index(unsorted)
    with pytest.raises(ValueError, match="unsorted"):
        validate_index(unsorted)

    duplicate = deepcopy(index)
    duplicate["allocation_only_gaps"].append(
        deepcopy(duplicate["allocation_only_gaps"][-1])
    )
    _reseal_index(duplicate)
    with pytest.raises(ValueError, match="duplicate|unsorted|overlap"):
        validate_index(duplicate)

    digest = deepcopy(index)
    digest["index_sha256"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="index_sha256"):
        validate_index(digest)


def test_later_allocator_projection_publishes_new_index_not_stale_one(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    first = validate_terminal_evidence(root, state_file)

    entry = state.provider_attempt_allocations[_scope().key]
    entry["last_allocated_ordinal"] = 2
    state.updated_at = "2026-07-18T02:00:00+00:00"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    second = validate_terminal_evidence(root, state_file)
    assert second.path != first.path
    assert second.index["allocator_projection"]["sha256"] != first.index["allocator_projection"]["sha256"]
    assert first.path.is_file() and second.path.is_file()


def _install_published_record(root: Path, state: RunState) -> Path:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
        evidence_relative_path,
    )

    record = _success_record(ordinal=1, run_state=state)
    relative = evidence_relative_path(_scope(), 1)
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_record_bytes(record)
    destination.write_bytes(payload)
    return destination


def test_terminal_validation_indexes_manifest_bound_publication(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    destination = _install_published_record(root, state)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    result = validate_terminal_evidence(root, state_file)
    publication = result.index["publications"][0]
    assert publication["runtime_step_id"] == "ProviderStep"
    assert publication["record_sha256"] == json.loads(destination.read_bytes())["record_sha256"]
    assert publication["record_file_sha256"] == _sha(destination.read_bytes())
    assert result.index["allocation_only_gaps"] == []

    from orchestrator.workflow.prompt_dependency_evidence import validate_index

    for field in ("scope_count", "event_count"):
        tampered = deepcopy(result.index)
        tampered["allocator_projection"][field] = 99
        _reseal_index(tampered)
        with pytest.raises(ValueError, match="count"):
            validate_index(tampered)
    tampered = deepcopy(result.index)
    tampered["publications"][0]["visit_key"] = "0" * 24
    _reseal_index(tampered)
    with pytest.raises(ValueError, match="visit"):
        validate_index(tampered)


def test_terminal_validation_rejects_nonterminal_and_corrupt_expected_record(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state.status = "running"
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="terminal"):
        validate_terminal_evidence(root, state_file)

    copied_terminal = _terminal_state(root)
    copied_state = root / "copied-state.json"
    copied_state.write_text(json.dumps(copied_terminal.to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="authoritative"):
        validate_terminal_evidence(root, copied_state)

    state.status = "completed"
    published = _install_published_record(root, state)
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    published.write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="digest|corrupt"):
        validate_terminal_evidence(root, state_file)


def test_terminal_validation_treats_missing_record_as_gap_and_rejects_true_orphan(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

    result = validate_terminal_evidence(root, state_file)
    assert result.index["publications"] == []
    assert result.index["allocation_only_gaps"] == [
        {
            "scope_sha256": _scope().key,
            "runtime_step_id": "ProviderStep",
            "visit_key": _scope().key[7:31],
            "attempt_ordinal": 1,
        }
    ]

    orphan = (
        root
        / "workflow_lisp"
        / "prompt_dependencies"
        / "unexpected-step"
        / "unexpected-visit"
        / "attempt-000002.json"
    )
    orphan.parent.mkdir(parents=True)
    orphan.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="orphan"):
        validate_terminal_evidence(root, state_file)


@pytest.mark.parametrize("fault", ["wrong_kind", "wrong_identity"])
def test_terminal_validation_rejects_deterministic_record_mismatch(
    tmp_path: Path, fault: str
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        canonical_record_bytes,
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    destination = _install_published_record(root, state)
    if fault == "wrong_kind":
        record = json.loads(destination.read_bytes())
        record["record_kind"] = "unsupported"
        destination.write_text(json.dumps(record), encoding="utf-8")
    else:
        record = _success_record(ordinal=2, run_state=state)
        destination.write_bytes(canonical_record_bytes(record))
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    with pytest.raises(ValueError, match="wrong kind|identity"):
        validate_terminal_evidence(root, state_file)


def test_terminal_validation_rejects_recursive_wrong_depth_orphan(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    orphan = root / "workflow_lisp/prompt_dependencies/unexpected/depth/more/attempt-000001.json"
    orphan.parent.mkdir(parents=True)
    orphan.write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="orphan"):
        validate_terminal_evidence(root, state_file)


def test_terminal_validation_rejects_conflicting_existing_index(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")
    first = validate_terminal_evidence(root, state_file)
    first.path.write_bytes(b"conflict")
    with pytest.raises(FileExistsError):
        validate_terminal_evidence(root, state_file)


def test_terminal_validation_detects_bypass_state_drift_and_removes_new_index(tmp_path: Path) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import validate_terminal_evidence

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

    def bypass() -> None:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        payload["updated_at"] = "2026-07-18T01:00:00+00:00"
        state_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="changed"):
        validate_terminal_evidence(root, state_file, _after_index_publish=bypass)
    indexes = root / "workflow_lisp/prompt_dependencies/validated-indexes"
    assert not indexes.exists() or list(indexes.glob("*.json")) == []


def test_terminal_validation_detects_state_drift_before_index_publish(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.prompt_dependency_evidence import (
        validate_terminal_evidence,
    )

    root = tmp_path / "run"
    root.mkdir()
    state = _terminal_state(root)
    state_file = root / "state.json"
    state_file.write_text(json.dumps(state.to_dict()), encoding="utf-8")

    def advance_counter() -> None:
        payload = json.loads(state_file.read_text(encoding="utf-8"))
        payload["provider_attempt_allocations"][_scope().key][
            "last_allocated_ordinal"
        ] = 2
        state_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="changed"):
        validate_terminal_evidence(
            root,
            state_file,
            _after_initial_read=advance_counter,
        )
    indexes = root / "workflow_lisp/prompt_dependencies/validated-indexes"
    assert not indexes.exists() or list(indexes.glob("*.json")) == []


def _offline_validator_references(source: str) -> set[str]:
    forbidden = {
        "validate_terminal_evidence",
        "validate_index",
        "_build_terminal_index",
        "_write_index_no_replace",
        "build_allocator_projection",
        "validate_allocator_projection",
        "allocator_projection_sha256",
    }
    tree = ast.parse(source)
    referenced = {
        node.id for node in ast.walk(tree) if isinstance(node, ast.Name)
    } | {
        node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    return referenced & forbidden


def test_runtime_ast_guard_rejects_aliased_offline_validator_import() -> None:
    source = (
        "from orchestrator.workflow.prompt_dependency_evidence "
        "import validate_terminal_evidence as v\nv('root', 'state')\n"
    )
    assert _offline_validator_references(source) == {"validate_terminal_evidence"}
    assert _offline_validator_references(
        "from orchestrator.workflow.prompt_dependency_evidence import validate_index as v\n"
    ) == {"validate_index"}


def test_runtime_modules_do_not_import_or_call_offline_prompt_dependency_validator() -> None:
    paths = [
        "orchestrator/workflow/executor.py",
        "orchestrator/workflow/prompting.py",
        "orchestrator/workflow/adjudication_runtime.py",
        "orchestrator/cli/commands/run.py",
        "orchestrator/cli/commands/resume.py",
    ]
    for relative in paths:
        assert not _offline_validator_references(
            Path(relative).read_text(encoding="utf-8")
        ), relative
