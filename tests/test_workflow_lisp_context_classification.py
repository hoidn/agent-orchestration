from __future__ import annotations

import importlib

import pytest

from orchestrator.workflow_lisp.contracts import FlattenedContractField
from orchestrator.workflow_lisp.definitions import PathDef, RecordDef, RecordField, UnionDef, UnionVariant
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.type_env import (
    ListTypeRef,
    MapTypeRef,
    OptionalTypeRef,
    PathTypeRef,
    PrimitiveTypeRef,
    RecordTypeRef,
    UnionTypeRef,
)


def _context_module():
    return importlib.import_module("orchestrator.workflow_lisp.context_classification")


def _span(label: str = "context-classification") -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(path=f"<{label}>", line=1, column=1, offset=0),
        end=SourcePosition(path=f"<{label}>", line=1, column=1, offset=1),
    )


def _path_type(name: str, *, under: str, must_exist: bool = False) -> PathTypeRef:
    definition = PathDef(
        name=name,
        kind="relpath",
        under=under,
        must_exist=must_exist,
        span=_span(name),
    )
    return PathTypeRef(name=name, definition=definition)


def _record_type(name: str, fields: dict[str, object]) -> RecordTypeRef:
    definition = RecordDef(
        name=name,
        fields=tuple(
            RecordField(name=field_name, type_name=getattr(field_type, "name", str(field_type)), span=_span(name))
            for field_name, field_type in fields.items()
        ),
        span=_span(name),
    )
    return RecordTypeRef(name=name, definition=definition, field_types=fields)


def _union_type(name: str, variants: dict[str, dict[str, object]]) -> UnionTypeRef:
    definition = UnionDef(
        name=name,
        variants=tuple(
            UnionVariant(
                name=variant_name,
                fields=tuple(
                    RecordField(
                        name=field_name,
                        type_name=getattr(field_type, "name", str(field_type)),
                        span=_span(name),
                    )
                    for field_name, field_type in field_map.items()
                ),
                span=_span(name),
            )
            for variant_name, field_map in variants.items()
        ),
        span=_span(name),
    )
    return UnionTypeRef(name=name, definition=definition, variant_field_types=variants)


def _run_ctx_type(*, state_under: str = "state", artifact_under: str = "artifacts") -> RecordTypeRef:
    return _record_type(
        "RunCtx",
        {
            "run-id": PrimitiveTypeRef(name="RunId"),
            "state-root": _path_type("Path.state-root", under=state_under),
            "artifact-root": _path_type("Path.artifact-root", under=artifact_under),
        },
    )


def _legacy_context_shapes() -> list[tuple[str, RecordTypeRef, tuple[str, ...]]]:
    run_ctx = _run_ctx_type()
    state_file = _path_type("StateFile", under="state")
    state_existing = _path_type("StateExisting", under="state", must_exist=True)
    return [
        ("RunCtx", run_ctx, ()),
        (
            "PhaseCtx",
            _record_type(
                "PhaseCtx",
                {
                    "run": run_ctx,
                    "phase-name": PrimitiveTypeRef(name="Symbol"),
                    "state-root": _path_type("Path.state-root", under="state"),
                    "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
                },
            ),
            ("run",),
        ),
        (
            "ItemCtx",
            _record_type(
                "ItemCtx",
                {
                    "run": run_ctx,
                    "item-id": PrimitiveTypeRef(name="String"),
                    "state-root": _path_type("Path.state-root", under="state"),
                    "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
                    "ledger": state_file,
                },
            ),
            ("run",),
        ),
        (
            "DrainCtx",
            _record_type(
                "DrainCtx",
                {
                    "run": run_ctx,
                    "state-root": _path_type("Path.state-root", under="state"),
                    "manifest": state_existing,
                    "ledger": state_file,
                },
            ),
            ("run",),
        ),
        (
            "SelectionCtx",
            _record_type(
                "SelectionCtx",
                {
                    "run": run_ctx,
                    "state-root": _path_type("Path.state-root", under="state"),
                    "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
                },
            ),
            ("run",),
        ),
        (
            "RecoveryCtx",
            _record_type(
                "RecoveryCtx",
                {
                    "run": run_ctx,
                    "state-root": _path_type("Path.state-root", under="state"),
                    "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
                },
            ),
            ("run",),
        ),
    ]


@pytest.mark.parametrize(
    ("legacy_family", "type_ref", "expected_anchor_path"),
    _legacy_context_shapes(),
)
def test_structural_classification_recognizes_legacy_private_exec_context_shapes(
    legacy_family: str,
    type_ref: RecordTypeRef,
    expected_anchor_path: tuple[str, ...],
) -> None:
    context_classification = _context_module()

    classification = context_classification.classify_structural_private_exec_context(type_ref)

    assert classification is not None
    assert tuple(anchor.kind for anchor in classification.anchors) == (
        context_classification.ContextAnchorKind.RUN_CTX,
    )
    assert tuple(anchor.field_path for anchor in classification.anchors) == (expected_anchor_path,)
    assert classification.derived_capabilities == ("run",)
    assert classification.legacy_family == legacy_family


@pytest.mark.parametrize(
    "type_ref",
    [
        _record_type(
            "MissingRunIdCtx",
            {
                "state-root": _path_type("Path.state-root", under="state"),
                "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
            },
        ),
        _record_type(
            "WrongUnderRunCtx",
            {
                "run-id": PrimitiveTypeRef(name="RunId"),
                "state-root": _path_type("Path.state-root", under="artifacts"),
                "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
            },
        ),
        _record_type(
            "UnionWrappedRunCtx",
            {
                "run": _union_type("RunCarrier", {"RUN": {"run": _run_ctx_type()}, "MISSING": {}}),
                "state-root": _path_type("Path.state-root", under="state"),
                "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
            },
        ),
        _record_type(
            "OptionalWrappedRunCtx",
            {
                "run": OptionalTypeRef(name="Optional[RunCtx]", item_type_ref=_run_ctx_type()),
                "state-root": _path_type("Path.state-root", under="state"),
                "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
            },
        ),
        _record_type(
            "ListWrappedRunCtx",
            {
                "run": ListTypeRef(name="List[RunCtx]", item_type_ref=_run_ctx_type()),
                "state-root": _path_type("Path.state-root", under="state"),
                "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
            },
        ),
        _record_type(
            "MapWrappedRunCtx",
            {
                "run": MapTypeRef(
                    name="Map[String, RunCtx]",
                    key_type_ref=PrimitiveTypeRef(name="String"),
                    value_type_ref=_run_ctx_type(),
                ),
                "state-root": _path_type("Path.state-root", under="state"),
                "artifact-root": _path_type("Path.artifact-root", under="artifacts"),
            },
        ),
    ],
)
def test_structural_classification_rejects_near_miss_context_shapes(type_ref: RecordTypeRef) -> None:
    context_classification = _context_module()

    assert context_classification.classify_structural_private_exec_context(type_ref) is None


def test_structural_bootstrap_plan_assigns_run_anchor_and_default_roles() -> None:
    context_classification = _context_module()
    phase_ctx = next(
        type_ref
        for legacy_family, type_ref, _anchor_path in _legacy_context_shapes()
        if legacy_family == "PhaseCtx"
    )
    classification = context_classification.classify_structural_private_exec_context(phase_ctx)

    assert classification is not None

    flattened_fields = (
        FlattenedContractField(
            generated_name="phase-ctx__run__run-id",
            source_path=("phase-ctx", "run", "run-id"),
            contract_definition={"type": "string"},
        ),
        FlattenedContractField(
            generated_name="phase-ctx__run__state-root",
            source_path=("phase-ctx", "run", "state-root"),
            contract_definition={"type": "relpath", "under": "state"},
        ),
        FlattenedContractField(
            generated_name="phase-ctx__run__artifact-root",
            source_path=("phase-ctx", "run", "artifact-root"),
            contract_definition={"type": "relpath", "under": "artifacts"},
        ),
        FlattenedContractField(
            generated_name="phase-ctx__phase-name",
            source_path=("phase-ctx", "phase-name"),
            contract_definition={"type": "string", "default": "plan"},
        ),
        FlattenedContractField(
            generated_name="phase-ctx__state-root",
            source_path=("phase-ctx", "state-root"),
            contract_definition={"type": "relpath", "under": "state", "default": "state/plan"},
        ),
        FlattenedContractField(
            generated_name="phase-ctx__artifact-root",
            source_path=("phase-ctx", "artifact-root"),
            contract_definition={"type": "relpath", "under": "artifacts", "default": "artifacts/plan"},
        ),
    )

    plan = context_classification.structural_bootstrap_plan(flattened_fields, classification)

    assert plan is not None
    assert plan.input_roles == {
        "phase-ctx__run__run-id": "run_anchor:run-id",
        "phase-ctx__run__state-root": "run_anchor:state-root",
        "phase-ctx__run__artifact-root": "run_anchor:artifact-root",
        "phase-ctx__phase-name": "compile_time_default",
        "phase-ctx__state-root": "compile_time_default",
        "phase-ctx__artifact-root": "compile_time_default",
    }


def test_structural_bootstrap_plan_returns_none_for_roleless_generated_input() -> None:
    context_classification = _context_module()
    phase_ctx = next(
        type_ref
        for legacy_family, type_ref, _anchor_path in _legacy_context_shapes()
        if legacy_family == "PhaseCtx"
    )
    classification = context_classification.classify_structural_private_exec_context(phase_ctx)

    assert classification is not None

    flattened_fields = (
        FlattenedContractField(
            generated_name="phase-ctx__run__run-id",
            source_path=("phase-ctx", "run", "run-id"),
            contract_definition={"type": "string"},
        ),
        FlattenedContractField(
            generated_name="phase-ctx__phase-name",
            source_path=("phase-ctx", "phase-name"),
            contract_definition={"type": "string"},
        ),
    )

    assert context_classification.structural_bootstrap_plan(flattened_fields, classification) is None


def test_name_lane_fallback_accounting_starts_zero_and_is_deterministic() -> None:
    context_classification = _context_module()

    assert context_classification.name_lane_fallback_counts() == {}

    context_classification.record_name_lane_fallback("compatibility_consumer")
    context_classification.record_name_lane_fallback("compatibility_consumer")
    context_classification.record_name_lane_fallback("legacy_table")

    assert context_classification.name_lane_fallback_counts() == {
        "compatibility_consumer": 2,
        "legacy_table": 1,
    }
