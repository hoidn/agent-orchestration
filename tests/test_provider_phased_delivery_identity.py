"""Identity-v2 contracts for phased provider delivery."""

from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Mapping

import pytest

from orchestrator.workflow.prompt_identity import (
    PROMPT_ATTEMPT_COMPOSITION_V2_SCHEMA,
    PROMPT_ATTEMPT_IDENTITY_V2_VERSION,
    PROVIDER_POLICY_V2_SCHEMA,
    ROLE_ORDER,
    build_fragment_program_role,
    build_injected_dependencies_role,
    build_prompt_attempt_identity_v2,
    build_provider_policy_role_v2,
    build_runtime_contributions_role,
    canonical_sha256,
    compare_prompt_attempt_records,
    PromptComparisonRecord,
    validate_prompt_attempt_identity,
    validate_prompt_attempt_identity_v2,
)
from orchestrator.workflow.prompting import CanonicalPromptCut
from orchestrator.workflow.provider_attempts import ProviderAttemptScope
from orchestrator.workflow.provider_phased_delivery.diagnostics import (
    DiagnosticSource,
    PhasedDeliveryDiagnostic,
    RejectedValue,
    diagnostic_definition,
)
from orchestrator.workflow.provider_phased_delivery.frames import (
    PROTOCOL_FRAME_SCHEMA_VERSION,
    RenderedProtocolTurn,
    render_initial_materialization_turn,
    render_retry_materialization_turn,
    render_task_turn,
)
from orchestrator.workflow.provider_phased_delivery.models import (
    ByteDigestProjection,
    CompositionProjection,
)
from orchestrator.workflow.prompt_identity import validate_prompt_identity_role


EMPTY_KEYS_SHA256 = (
    "sha256:"
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)


def _sha(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _bytes_projection(payload: bytes) -> ByteDigestProjection:
    return ByteDigestProjection(bytes=len(payload), sha256=_sha(payload))


def _cut(
    *,
    task: bytes = b"perform the task",
    materialization: bytes = b"\n\nwrite the contract",
) -> CanonicalPromptCut:
    return CanonicalPromptCut(
        task_slice=task,
        materialization_slice=materialization,
        canonical_composed=task + materialization,
        projection=CompositionProjection(
            canonical_composed=_bytes_projection(task + materialization),
            task_slice=_bytes_projection(task),
            materialization_slice=_bytes_projection(materialization),
        ),
    )


def _policy(**updates: object) -> dict[str, object]:
    value: dict[str, object] = {
        "provider_name": "codex",
        "model": "gpt-5",
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
    value.update(updates)
    return value


def _roles() -> dict[str, Mapping[str, Any]]:
    return {
        "fragment_program": build_fragment_program_role(
            identity_schema_version="compiled_prompt_fragment_identity.v2",
            compiled_prompt_fragment_identity=_sha(b"fragment"),
        ),
        "resolved_bindings": {
            "schema_version": (
                "workflow_prompt_attempt_resolved_bindings.v1"
            ),
            "payload": {
                "binding_plan_sha256": _sha(b"plan"),
                "rows": [],
            },
            "sha256": canonical_sha256(
                {
                    "binding_plan_sha256": _sha(b"plan"),
                    "rows": [],
                }
            ),
        },
        "injected_dependencies": build_injected_dependencies_role(
            canonical_groups=(),
            injection={
                "position": "prepend",
                "block_bytes": 0,
                "block_sha256": _sha(b""),
            },
        ),
        "runtime_contributions": build_runtime_contributions_role(()),
        "provider_policy": build_provider_policy_role_v2(_policy()),
    }


def _diagnostic() -> PhasedDeliveryDiagnostic:
    reason = "output_validation_failed"
    definition = diagnostic_definition(reason)
    return PhasedDeliveryDiagnostic(
        code=definition.code,
        reason=reason,
        rejected_value=RejectedValue(
            type="validation_code",
            canonical_value="missing_output_file",
            summary=reason,
        ),
        primary_source=DiagnosticSource(
            kind="runtime_attempt",
            owner="q2_output_contract",
            path=None,
            span=None,
        ),
        related_sources=(
            DiagnosticSource(
                kind="runtime_attempt",
                owner="runtime_step",
                path=None,
                span=None,
            ),
            DiagnosticSource(
                kind="runtime_attempt",
                owner="candidate_set",
                path=None,
                span=None,
            ),
            DiagnosticSource(
                kind="runtime_attempt",
                owner="phase_lifecycle",
                path=None,
                span=None,
            ),
        ),
    )


def _turns(
    *,
    initial_keys: tuple[str, ...] = ("ENTER",),
) -> tuple[RenderedProtocolTurn, ...]:
    cut = _cut()
    return (
        render_task_turn(cut=cut),
        render_initial_materialization_turn(
            cut=cut,
            submit_keys=initial_keys,
        ),
        render_retry_materialization_turn(
            cut=cut,
            submission_ordinal=2,
            diagnostics=(_diagnostic(),),
            submit_keys=("ENTER",),
        ),
    )


def _identity(
    *,
    turns: tuple[RenderedProtocolTurn, ...] | None = None,
) -> Mapping[str, Any]:
    return build_prompt_attempt_identity_v2(
        roles=_roles(),
        cut=_cut(),
        actual_deliveries=_turns() if turns is None else turns,
    )


def _thaw(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _thaw(item) for key, item in value.items()}
    if hasattr(value, "items"):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_thaw(item) for item in value]
    return value


def _reseal(identity: dict[str, Any]) -> None:
    identity["composition_sha256"] = canonical_sha256(
        {
            "schema_version": PROMPT_ATTEMPT_COMPOSITION_V2_SCHEMA,
            "role_sha256": {
                key: identity["roles"][key]["sha256"]
                for key in ROLE_ORDER
            },
            "canonical_composed": identity["canonical_composed"],
            "protocol_schema_version": PROTOCOL_FRAME_SCHEMA_VERSION,
            "actual_deliveries": identity["actual_deliveries"],
        }
    )


def _scope() -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": "run-identity-v2",
            "resume_scope": {
                "root_workflow_file": "workflows/review.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "review",
            "enclosing_step": {
                "step_name": "Review",
                "step_id": "review",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def test_provider_policy_v2_is_exact_structural_and_sealed() -> None:
    role = build_provider_policy_role_v2(_policy())

    assert tuple(role) == ("schema_version", "payload", "sha256")
    assert role["schema_version"] == PROVIDER_POLICY_V2_SCHEMA
    assert _thaw(role["payload"]) == _policy()
    assert role["sha256"] == canonical_sha256(_policy())
    assert (
        validate_prompt_identity_role(
            "provider_policy",
            role,
            attempt_identity_version=PROMPT_ATTEMPT_IDENTITY_V2_VERSION,
        )
        == role
    )


@pytest.mark.parametrize(
    "mutate",
    (
        lambda value: value.update({"input_mode": "stdin"}),
        lambda value: value.update({"environment": {}}),
        lambda value: value["transport"].update({"extra": None}),
        lambda value: value["transport"].update({"kind": "stdin"}),
        lambda value: value["transport"].update(
            {"schema_version": "interactive_terminal_turn_queue.v2"}
        ),
        lambda value: value["phased_call_policy"].update({"extra": None}),
        lambda value: value["phased_call_policy"].update(
            {"delivery": "composed"}
        ),
        lambda value: value["phased_call_policy"].update(
            {"materialization_attempts": True}
        ),
        lambda value: value["phased_call_policy"].update(
            {"materialization_attempts": 4}
        ),
    ),
)
def test_provider_policy_v2_rejects_open_or_invalid_payloads(mutate) -> None:
    value = deepcopy(_policy())
    mutate(value)

    with pytest.raises(ValueError, match="prompt_attempt_identity_role_invalid"):
        build_provider_policy_role_v2(value)


def test_identity_v2_seals_five_roles_composition_and_exact_deliveries() -> None:
    identity = _identity()
    rows = identity["actual_deliveries"]
    delivered = _turns()

    assert tuple(identity) == (
        "schema_version",
        "roles",
        "canonical_composed",
        "actual_deliveries",
        "composition_sha256",
    )
    assert identity["schema_version"] == PROMPT_ATTEMPT_IDENTITY_V2_VERSION
    assert tuple(identity["roles"]) == ROLE_ORDER
    assert identity["canonical_composed"] == {
        "bytes": len(_cut().canonical_composed),
        "sha256": _sha(_cut().canonical_composed),
    }
    assert tuple(row["delivery_ordinal"] for row in rows) == (0, 1, 2)
    assert tuple(row["phase"] for row in rows) == (
        "task",
        "initial_materialization",
        "retry_materialization",
    )
    assert tuple(row["submission_ordinal"] for row in rows) == (None, 1, 2)
    assert rows[0]["submit_keys"] == {
        "count": 0,
        "sha256": EMPTY_KEYS_SHA256,
    }
    for source, row in zip(delivered, rows, strict=True):
        assert row["delivered_turn"]["bytes"] == (
            row["protocol_frame"]["bytes"] + row["canonical_slice"]["bytes"]
        )
        assert row["protocol_frame"] == {
            "bytes": len(source.protocol_frame),
            "sha256": _sha(source.protocol_frame),
        }
        assert row["canonical_slice"] == {
            "bytes": len(source.canonical_slice),
            "sha256": _sha(source.canonical_slice),
        }
        assert row["delivered_turn"] == {
            "bytes": len(source.delivered_turn),
            "sha256": _sha(source.delivered_turn),
        }
    assert identity["composition_sha256"] == canonical_sha256(
        {
            "schema_version": PROMPT_ATTEMPT_COMPOSITION_V2_SCHEMA,
            "role_sha256": {
                key: identity["roles"][key]["sha256"]
                for key in ROLE_ORDER
            },
            "canonical_composed": identity["canonical_composed"],
            "protocol_schema_version": PROTOCOL_FRAME_SCHEMA_VERSION,
            "actual_deliveries": identity["actual_deliveries"],
        }
    )
    assert validate_prompt_attempt_identity_v2(identity) == identity
    assert validate_prompt_attempt_identity(identity) == identity


@pytest.mark.parametrize("count", (0, 1, 2))
def test_failed_requested_turns_are_absent_from_successful_prefix(count: int) -> None:
    successful = _turns()[:count]

    identity = _identity(turns=successful)

    assert len(identity["actual_deliveries"]) == count
    assert tuple(
        row["delivery_ordinal"] for row in identity["actual_deliveries"]
    ) == tuple(range(count))


@pytest.mark.parametrize(
    "mutation",
    (
        "extra",
        "missing",
        "gap",
        "wrong_initial_phase",
        "task_keys",
        "materialization_slice",
        "protocol_frame_empty",
        "materialization_slice_empty",
        "byte_equation",
        "composition",
    ),
)
def test_identity_v2_rejects_schema_delivery_and_seal_tamper(
    mutation: str,
) -> None:
    identity = _thaw(_identity())
    if mutation == "extra":
        identity["extra"] = None
    elif mutation == "missing":
        identity.pop("canonical_composed")
    elif mutation == "gap":
        identity["actual_deliveries"][2]["delivery_ordinal"] = 3
        identity["actual_deliveries"][2]["submission_ordinal"] = 3
        _reseal(identity)
    elif mutation == "wrong_initial_phase":
        identity["actual_deliveries"][1]["phase"] = "retry_materialization"
        _reseal(identity)
    elif mutation == "task_keys":
        identity["actual_deliveries"][0]["submit_keys"]["count"] = 1
        _reseal(identity)
    elif mutation == "materialization_slice":
        identity["actual_deliveries"][2]["canonical_slice"]["sha256"] = _sha(
            b"different"
        )
        _reseal(identity)
    elif mutation == "protocol_frame_empty":
        row = identity["actual_deliveries"][0]
        row["protocol_frame"]["bytes"] = 0
        row["delivered_turn"]["bytes"] = row["canonical_slice"]["bytes"]
        _reseal(identity)
    elif mutation == "materialization_slice_empty":
        row = identity["actual_deliveries"][1]
        row["canonical_slice"]["bytes"] = 0
        row["delivered_turn"]["bytes"] = row["protocol_frame"]["bytes"]
        _reseal(identity)
    elif mutation == "byte_equation":
        identity["actual_deliveries"][1]["delivered_turn"]["bytes"] += 1
        _reseal(identity)
    elif mutation == "composition":
        identity["composition_sha256"] = _sha(b"tamper")

    with pytest.raises(ValueError):
        validate_prompt_attempt_identity_v2(identity)


@pytest.mark.parametrize(
    ("row_index", "field", "replacement"),
    (
        (0, "delivery_ordinal", False),
        (0, "delivery_ordinal", 0.0),
        (1, "delivery_ordinal", True),
        (1, "delivery_ordinal", 1.0),
        (1, "submission_ordinal", True),
        (1, "submission_ordinal", 1.0),
    ),
)
def test_identity_v2_rejects_noncanonical_numeric_ordinals(
    row_index: int,
    field: str,
    replacement: object,
) -> None:
    identity = _thaw(_identity())
    identity["actual_deliveries"][row_index][field] = replacement
    _reseal(identity)

    with pytest.raises(ValueError, match="ordinal"):
        validate_prompt_attempt_identity_v2(identity)


def test_identity_v2_accepts_exact_integer_ordinals_and_null_task_submission() -> None:
    identity = validate_prompt_attempt_identity_v2(_identity())
    task, materialization = identity["actual_deliveries"][:2]

    assert type(task["delivery_ordinal"]) is int
    assert task["delivery_ordinal"] == 0
    assert task["submission_ordinal"] is None
    assert type(materialization["delivery_ordinal"]) is int
    assert materialization["delivery_ordinal"] == 1
    assert type(materialization["submission_ordinal"]) is int
    assert materialization["submission_ordinal"] == 1


def test_identity_v1_remains_valid_and_cross_version_comparison_is_closed() -> None:
    from tests.test_prompt_identity import _attempt_identity

    v1 = _attempt_identity()
    assert validate_prompt_attempt_identity(v1) == v1
    previous = PromptComparisonRecord(
        scope=_scope(),
        ordinal=1,
        outcome="v2_snapshot",
        prompt_attempt_identity=v1,
    )
    current = PromptComparisonRecord(
        scope=_scope(),
        ordinal=2,
        outcome="v3_snapshot",
        prompt_attempt_identity=_identity(),
    )

    assert compare_prompt_attempt_records(current, previous) == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": (),
        "reason": "identity_version_mismatch",
    }


def test_comparison_records_require_exact_evidence_identity_version_pairing() -> None:
    from tests.test_prompt_identity import _attempt_identity

    with pytest.raises(ValueError, match="identity version"):
        PromptComparisonRecord(
            scope=_scope(),
            ordinal=1,
            outcome="v2_snapshot",
            prompt_attempt_identity=_identity(),
        )
    with pytest.raises(ValueError, match="identity version"):
        PromptComparisonRecord(
            scope=_scope(),
            ordinal=1,
            outcome="v3_snapshot",
            prompt_attempt_identity=_attempt_identity(),
        )


def test_functional_v2_rejects_identity_v2_as_a_closed_version_mismatch() -> None:
    from orchestrator.workflow.prompt_identity import (
        build_prompt_fragment_snapshot_v2,
    )
    from tests.test_prompt_identity import COMPILED_V1, _retained_v1

    with pytest.raises(
        ValueError,
        match="prompt_attempt_identity_role_invalid",
    ):
        build_prompt_fragment_snapshot_v2(
            validated_retained_v1=_retained_v1(),
            prompt_attempt_identity=_identity(),
            compiler_fragment_identity_schema_version=COMPILED_V1,
        )


def test_identity_v2_comparison_adds_only_actual_delivery_drift() -> None:
    previous = PromptComparisonRecord(
        scope=_scope(),
        ordinal=1,
        outcome="v3_snapshot",
        prompt_attempt_identity=_identity(turns=_turns()[:2]),
    )
    current = PromptComparisonRecord(
        scope=_scope(),
        ordinal=2,
        outcome="v3_snapshot",
        prompt_attempt_identity=_identity(
            turns=_turns(initial_keys=("TAB",))[:2],
        ),
    )

    assert compare_prompt_attempt_records(current, previous) == {
        "status": "available",
        "previous_attempt_ordinal": 1,
        "classifications": ("actual_delivery_drift",),
        "reason": None,
    }


def test_identity_v2_builder_requires_tuple_trace() -> None:
    with pytest.raises(TypeError, match="tuple"):
        build_prompt_attempt_identity_v2(
            roles=_roles(),
            cut=_cut(),
            actual_deliveries=list(_turns()),  # type: ignore[arg-type]
        )


def test_identity_v2_requires_nonempty_t2_even_without_deliveries() -> None:
    with pytest.raises(ValueError, match="materialization_slice"):
        build_prompt_attempt_identity_v2(
            roles=_roles(),
            cut=_cut(materialization=b""),
            actual_deliveries=(),
        )


def test_identity_v2_empty_prefix_rejects_zero_canonical_composition() -> None:
    identity = _thaw(_identity(turns=()))
    identity["canonical_composed"] = {
        "bytes": 0,
        "sha256": _sha(b""),
    }
    _reseal(identity)

    with pytest.raises(ValueError, match="canonical composed"):
        validate_prompt_attempt_identity_v2(identity)


def test_identity_v2_allows_empty_t1() -> None:
    cut = _cut(task=b"")
    task_turn = render_task_turn(cut=cut)

    identity = build_prompt_attempt_identity_v2(
        roles=_roles(),
        cut=cut,
        actual_deliveries=(task_turn,),
    )

    assert identity["actual_deliveries"][0]["canonical_slice"]["bytes"] == 0
