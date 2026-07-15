from __future__ import annotations

import json
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, is_dataclass
from enum import Enum
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import CallExpr, ProcedureCallExpr
from orchestrator.workflow_lisp.lowering import procedures as procedure_lowering
from orchestrator.workflow_lisp.source_map import build_source_map_document


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows"
EXAMPLE = WORKFLOWS / "examples" / "design_plan_impl_review_stack_v2_call.orc"
MIGRATION_INPUTS = WORKFLOWS / "examples" / "inputs" / "workflow_lisp_migrations"
BASELINE = REPO_ROOT / "tests" / "baselines" / "procedure_first" / "tracked_plan_phase.json"
MODULE_NAME = "examples/design_plan_impl_review_stack_v2_call"
PUBLIC_ENTRY = f"{MODULE_NAME}::design-plan-impl-review-stack"
TRACKED_PLAN = f"{MODULE_NAME}::tracked-plan-phase"
MODULE_TOKEN = "$module"
MODULE_SLUG = "examples_design_plan_impl_review_stack_v2_call"
PUBLIC_ENTRY_TOKEN = "$module::design-plan-impl-review-stack"
TRACKED_PLAN_TOKEN = "$module::tracked-plan-phase"
_OLD_CALL_NODE_ID = (
    "root.$module_slug_design_plan_impl_review_stack__plan__call_"
    "$module_slug_tracked_plan_phase"
)
_OLD_PRIVATE_NODE_BASE = "root.$module_slug_tracked_plan_phase"
_OLD_PRIVATE_STEP_ID_BASE = "$module_slug_tracked_plan_phase"
_OLD_PRIVATE_PRESENTATION_BASE = TRACKED_PLAN_TOKEN
_NEW_INLINE_STEP_ID_BASE = (
    "$module_slug_design_plan_impl_review_stack__plan__"
    "$module_slug_tracked_plan_phase_1"
)
_NEW_INLINE_NODE_BASE = f"root.{_NEW_INLINE_STEP_ID_BASE}"
_NEW_INLINE_PRESENTATION_BASE = (
    f"{PUBLIC_ENTRY_TOKEN}__plan__$module::tracked-plan-phase_1"
)


def _phase_resume_identities(
    *,
    node_base: str,
    step_id_base: str,
    presentation_base: str,
) -> tuple[tuple[str, str], ...]:
    match_node = f"{node_base}__match_review"
    match_presentation = f"{presentation_base}__match_review"
    rows = [
        (f"{node_base}__draft", f"{presentation_base}__draft"),
        (f"{node_base}__review", f"{presentation_base}__review"),
    ]
    for variant in ("APPROVE", "REVISE"):
        branch_id = f"{step_id_base}__match_review__{variant.lower()}"
        branch_presentation = f"{match_presentation}.{variant}"
        rows.extend(
            (
                (f"{match_node}.{branch_id}", branch_presentation),
                (
                    f"{match_node}.{branch_id}.{branch_id}__projection_anchor",
                    f"{branch_presentation}."
                    f"{presentation_base}__match_review__{variant.lower()}__projection_anchor",
                ),
            )
        )
    rows.append((match_node, match_presentation))
    return tuple(rows)


_RETIRED_OLD_WRITE_ROOT_KEYS = (
    "schema:2/$module::design-plan-impl-review-stack/"
    "$module::design-plan-impl-review-stack__plan__call_$module::tracked-plan-phase/"
    "$module::tracked-plan-phase/__write_root__$module_slug_tracked_plan_phase__draft__result_bundle",
    "schema:2/$module::design-plan-impl-review-stack/"
    "$module::design-plan-impl-review-stack__plan__call_$module::tracked-plan-phase/"
    "$module::tracked-plan-phase/__write_root__$module_slug_tracked_plan_phase__review__result_bundle",
    "schema:2/$module::tracked-plan-phase/"
    "$module::tracked-plan-phase__draft/result_bundle/entry",
    "schema:2/$module::tracked-plan-phase/"
    "$module::tracked-plan-phase__review/result_bundle/entry",
)
_RETIRED_OLD_RESUME_KEYS = (
    ("top_level_node", _OLD_CALL_NODE_ID),
    ("call_boundary", _OLD_CALL_NODE_ID),
    *(
        ("top_level_node", node_id)
        for node_id, _ in _phase_resume_identities(
            node_base=_OLD_PRIVATE_NODE_BASE,
            step_id_base=_OLD_PRIVATE_STEP_ID_BASE,
            presentation_base=_OLD_PRIVATE_PRESENTATION_BASE,
        )
    ),
)
_RETIRED_OLD_LEXICAL_KEYS = (
    "ckpt:8d1ba7e4a3f6208430f45807",
    "ckpt:7315195dfee583a7a632b770",
    "ckpt:18fd9e37be5bddb772f62f7e",
)

_NEW_INLINE_WRITE_ROOT_ROWS = (
    {
        "workflow": PUBLIC_ENTRY_TOKEN,
        "semantic_role": "entrypoint_managed_write_root",
        "stable_identity": f"schema:2/{PUBLIC_ENTRY_TOKEN}/"
        f"{_NEW_INLINE_PRESENTATION_BASE}__draft/result_bundle/entry",
    },
    {
        "workflow": PUBLIC_ENTRY_TOKEN,
        "semantic_role": "entrypoint_managed_write_root",
        "stable_identity": f"schema:2/{PUBLIC_ENTRY_TOKEN}/"
        f"{_NEW_INLINE_PRESENTATION_BASE}__review/result_bundle/entry",
    },
)
_NEW_INLINE_RESUME_IDENTITIES = _phase_resume_identities(
    node_base=_NEW_INLINE_NODE_BASE,
    step_id_base=_NEW_INLINE_STEP_ID_BASE,
    presentation_base=_NEW_INLINE_PRESENTATION_BASE,
)
_NEW_INLINE_RESUME_ROWS = tuple(
    {
        "checkpoint_kind": "top_level_node",
        "node_id": node_id,
        "presentation_key": presentation_key,
        "runtime_step_id_mode": "static",
    }
    for node_id, presentation_key in _NEW_INLINE_RESUME_IDENTITIES
)
_NEW_INLINE_LEXICAL_ROWS = (
    {
        "checkpoint_id": "ckpt:85bebe726bc9eed0e4ee7c63",
        "program_point_id": "pp:e3313af95c03607cfd0291b1",
        "point_kind": "effect_boundary",
        "origin_key": f"{PUBLIC_ENTRY_TOKEN}::step_id::{_NEW_INLINE_STEP_ID_BASE}__draft",
        "presentation_key": f"{_NEW_INLINE_PRESENTATION_BASE}__draft",
        "step_kind": "provider",
        "resume_policy_kind": "reuse_validated_structured_output",
    },
    {
        "checkpoint_id": "ckpt:da29481dd96843184de8136f",
        "program_point_id": "pp:1ce01c3ef1f9efb56700de21",
        "point_kind": "effect_boundary",
        "origin_key": f"{PUBLIC_ENTRY_TOKEN}::step_id::{_NEW_INLINE_STEP_ID_BASE}__review",
        "presentation_key": f"{_NEW_INLINE_PRESENTATION_BASE}__review",
        "step_kind": "provider",
        "resume_policy_kind": "reuse_validated_structured_output",
    },
)


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def tracked_plan_compile():
    return compile_stage3_entrypoint(
        EXAMPLE,
        source_roots=(WORKFLOWS,),
        provider_externs=_load_json(MIGRATION_INPUTS / "design_plan_impl_stack.providers.json"),
        prompt_externs=_load_json(MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json"),
        command_boundaries=_load_json(MIGRATION_INPUTS / "design_plan_impl_stack.commands.json"),
        validate_shared=True,
        workspace_root=REPO_ROOT,
    )


def _short_name(name: str) -> str:
    return name.rsplit("::", 1)[-1]


def _json_value(value):
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _portable_contract_value(value):
    if isinstance(value, str):
        return value.replace(MODULE_NAME, MODULE_TOKEN).replace(MODULE_SLUG, "$module_slug")
    if isinstance(value, Mapping):
        return {
            _portable_contract_value(key): _portable_contract_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_portable_contract_value(item) for item in value]
    return value


def _type_contract(type_ref) -> dict[str, object]:
    contract: dict[str, object] = {"type_name": type_ref.name}
    definition = getattr(type_ref, "definition", None)
    if definition is not None:
        for field_name in ("kind", "under", "must_exist"):
            if hasattr(definition, field_name):
                contract[field_name] = _json_value(getattr(definition, field_name))
    allowed_values = getattr(type_ref, "allowed_values", ())
    if allowed_values:
        contract["allowed_values"] = list(allowed_values)
    return contract


def _public_signature_contract(compile_result) -> dict[str, object]:
    workflow = next(
        workflow
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == PUBLIC_ENTRY
    )
    signature = workflow.signature
    return_type = signature.return_type_ref
    return {
        "inputs": [
            {
                "name": name,
                "default": _json_value(signature.param_defaults.get(name)),
                **_type_contract(type_ref),
            }
            for name, type_ref in signature.params
        ],
        "outputs": [
            {
                "name": field.name,
                **_type_contract(return_type.field_types[field.name]),
            }
            for field in return_type.definition.fields
        ],
        "return_type": return_type.name,
    }


def _effect_rows(effect_summary) -> list[dict[str, str]]:
    return sorted(
        (
            {
                "kind": type(effect).__name__,
                "subject": ".".join(effect.subject),
            }
            for effect in effect_summary.transitive_effects
        ),
        key=lambda row: (row["kind"], row["subject"]),
    )


def _artifact_contracts(compile_result) -> list[dict[str, object]]:
    def contract_field(field: Mapping[str, object]) -> dict[str, object]:
        return {
            key: _json_value(field[key])
            for key in (
                "name",
                "json_pointer",
                "type",
                "under",
                "must_exist_target",
                "allowed",
            )
            if key in field
        }

    def bundle_contract(bundle: Mapping[str, object] | None):
        if bundle is None:
            return None
        return {
            "fields": [contract_field(field) for field in bundle.get("fields", ())],
        }

    def variant_contract(variant: Mapping[str, object] | None):
        if variant is None:
            return None
        return {
            "discriminant": contract_field(variant["discriminant"]),
            "shared_fields": [
                contract_field(field) for field in variant.get("shared_fields", ())
            ],
            "variants": {
                name: {
                    "fields": [
                        contract_field(field)
                        for field in definition.get("fields", ())
                    ]
                }
                for name, definition in variant.get("variants", {}).items()
            },
        }

    rows: list[dict[str, object]] = []
    for workflow_name, bundle in sorted(compile_result.validated_bundles.items()):
        for step in bundle.surface.steps:
            output_bundle = step.common.output_bundle
            variant_output = step.common.variant_output
            publishes = step.common.publishes
            if output_bundle is None and variant_output is None and not publishes:
                continue
            is_tracked_plan_step = "tracked-plan-phase" in step.name
            step_role = (
                "draft"
                if "__draft" in step.name
                else "review"
                if "__review" in step.name
                else step.name
            )
            rows.append(
                {
                    "workflow": "tracked-plan-phase"
                    if is_tracked_plan_step
                    else workflow_name,
                    "step": step_role if is_tracked_plan_step else step.name,
                    "kind": step.kind.value,
                    "output_bundle_contract": bundle_contract(output_bundle),
                    "variant_output_contract": variant_contract(variant_output),
                    "publishes": _json_value(publishes),
                }
            )
    return sorted(rows, key=lambda row: (str(row["workflow"]), str(row["step"])))


def _source_map_rows(linked_result) -> dict[str, object]:
    document = build_source_map_document(
        linked_result,
        selected_name=PUBLIC_ENTRY,
        display_name_resolver=_short_name,
    )
    rows: dict[str, object] = {}
    for workflow_name in (PUBLIC_ENTRY, TRACKED_PLAN):
        workflow = document.workflows.get(workflow_name)
        if workflow is None:
            continue
        entries = (workflow.workflow_origin, *workflow.step_ids.values())
        lineage_by_origin: dict[str, object] = {}
        expansion_by_origin: dict[str, object] = {}
        form_path_overrides: dict[str, object] = {}
        workflow_form_path = list(workflow.workflow_origin.form_path)
        for entry in entries:
            expansion = [
                    {
                        key: _json_value(getattr(frame, key))
                        for key in (
                            "macro_name",
                            "expansion_id",
                            "template_path",
                            "function_name",
                        )
                        if hasattr(frame, key)
                    }
                    for frame in entry.expansion_stack
                ]
            lineage = sorted(
                {
                        "procedure_call_site"
                        if note.startswith("procedure call site at")
                        else "procedure_definition"
                        if note.startswith("procedure definition at")
                        else note
                        for note in entry.notes
                }
            )
            if expansion:
                expansion_by_origin[entry.origin_key] = expansion
            if lineage:
                lineage_by_origin[entry.origin_key] = lineage
            if list(entry.form_path) != workflow_form_path:
                form_path_overrides[entry.origin_key] = list(entry.form_path)
        rows[workflow_name] = {
            "workflow_origin": {
                "origin_key": workflow.workflow_origin.origin_key,
                "form_path": list(workflow.workflow_origin.form_path),
            },
            "step_origin_keys": sorted(entry.origin_key for entry in workflow.step_ids.values()),
            "expansion_by_origin": expansion_by_origin,
            "lineage_by_origin": lineage_by_origin,
            "form_path_overrides": form_path_overrides,
        }
    return rows


def _runtime_contract(compile_result) -> dict[str, object]:
    state_write_roots: list[dict[str, object]] = []
    resume_checkpoints: list[dict[str, object]] = []
    lexical_checkpoints: list[dict[str, object]] = []
    for workflow_name in (PUBLIC_ENTRY, TRACKED_PLAN):
        bundle = compile_result.validated_bundles.get(workflow_name)
        if bundle is None:
            continue
        state_write_roots.extend(
            {
                "workflow": workflow_name,
                "semantic_role": allocation.semantic_role.value,
                "stable_identity": allocation.stable_identity,
            }
            for allocation in bundle.provenance.generated_path_allocations
            if "write_root" in allocation.semantic_role.value
        )
        resume_checkpoints.extend(
            {
                "checkpoint_kind": checkpoint.checkpoint_kind,
                "node_id": checkpoint.node_id,
                "presentation_key": checkpoint.presentation_key,
                "runtime_step_id_mode": checkpoint.runtime_step_id_mode,
            }
            for checkpoint in bundle.runtime_plan.resume_checkpoints
        )
        lexical_checkpoints.extend(
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "program_point_id": checkpoint.program_point_id,
                "point_kind": checkpoint.point_kind,
                "origin_key": checkpoint.origin_key,
                "presentation_key": checkpoint.presentation_key,
                "step_kind": checkpoint.details.get("step_kind"),
                "resume_policy_kind": (
                    checkpoint.details.get("effect_boundary", {})
                    .get("policy", {})
                    .get("policy_kind")
                ),
            }
            for checkpoint in bundle.runtime_plan.lexical_checkpoint_points
        )
    return {
        "state_write_roots": sorted(
            state_write_roots,
            key=lambda row: (row["workflow"], row["semantic_role"], row["stable_identity"]),
        ),
        "resume_checkpoints": resume_checkpoints,
        "lexical_checkpoints": lexical_checkpoints,
    }


def _tracked_plan_projection(linked_result) -> dict[str, object]:
    compile_result = linked_result.entry_result
    public_bundle = compile_result.validated_bundles[PUBLIC_ENTRY]
    public_workflow = next(
        workflow
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == PUBLIC_ENTRY
    )
    public_plan_steps = [
        step
        for step in public_bundle.surface.steps
        if "tracked-plan-phase" in step.name
    ]
    lowered_step_order = {
        workflow_name: [
            (
                f"{step.kind.value}:tracked-plan-phase:"
                + (
                    "draft"
                    if "__draft" in step.name
                    else "review"
                    if "__review" in step.name
                    else "match"
                    if step.kind.value == "match"
                    else "call"
                )
                if "tracked-plan-phase" in step.name
                else f"{step.kind.value}:{step.name}"
            )
            for step in bundle.surface.steps
        ]
        for workflow_name, bundle in sorted(compile_result.validated_bundles.items())
    }
    projection = {
        "schema_version": "procedure_first.tracked_plan_phase_contract.v1",
        "public_contract": {
            "module": compile_result.module.module_name,
            "entry_workflow": PUBLIC_ENTRY,
            "exported_workflows": sorted(compile_result.module.exports),
            **_public_signature_contract(compile_result),
            "terminal_outcome": {
                "terminal_node_id": public_bundle.runtime_plan.ordered_node_ids[-1],
                "terminal_node_kind": public_bundle.runtime_plan.nodes[
                    public_bundle.runtime_plan.ordered_node_ids[-1]
                ].kind,
                "finalization_entry_node_id": public_bundle.ir.finalization_entry_node_id,
            },
        },
        "artifact_contracts": _artifact_contracts(compile_result),
        "caller_visible_effects": [
            row
            for row in _effect_rows(public_workflow.effect_summary)
            if not (
                row["kind"] == "CallsWorkflowEffect"
                and row["subject"] == TRACKED_PLAN
            )
        ],
        "runtime_contract": _runtime_contract(compile_result),
        "internal_route": {
            "lowered_step_order": lowered_step_order,
            "registered_workflows": sorted(
                workflow.typed_workflow.definition.name
                for workflow in compile_result.lowered_workflows
            ),
            "public_plan_nodes": [
                {
                    "kind": step.kind.value,
                    "name": step.name,
                    "step_id": step.step_id,
                    "call_alias": step.call_alias,
                }
                for step in public_plan_steps
            ],
            "source_map": _source_map_rows(linked_result),
        },
    }
    return _portable_contract_value(projection)


def _assert_reviewed_structural_delta(
    expected_route: dict[str, object],
    actual_route: dict[str, object],
) -> None:
    if actual_route == expected_route:
        return

    assert actual_route["registered_workflows"] == [
        name
        for name in expected_route["registered_workflows"]
        if name != TRACKED_PLAN_TOKEN
    ]
    expected_orders = expected_route["lowered_step_order"]
    actual_orders = actual_route["lowered_step_order"]
    expected_public_order = expected_orders[PUBLIC_ENTRY_TOKEN]
    tracked_order = expected_orders[TRACKED_PLAN_TOKEN]
    expected_inline_public_order: list[str] = []
    for step in expected_public_order:
        if step == "call:tracked-plan-phase:call":
            expected_inline_public_order.extend(tracked_order)
        else:
            expected_inline_public_order.append(step)
    assert actual_orders[PUBLIC_ENTRY_TOKEN] == expected_inline_public_order
    assert {
        name: order
        for name, order in actual_orders.items()
        if name != PUBLIC_ENTRY_TOKEN
    } == {
        name: order
        for name, order in expected_orders.items()
        if name not in {PUBLIC_ENTRY_TOKEN, TRACKED_PLAN_TOKEN}
    }
    old_call_node = expected_route["public_plan_nodes"]
    assert len(old_call_node) == 1
    old_call_node = old_call_node[0]
    assert old_call_node["kind"] == "call"
    assert old_call_node["call_alias"] == TRACKED_PLAN_TOKEN
    inline_name_prefix = old_call_node["name"].replace(
        f"__call_{TRACKED_PLAN_TOKEN}",
        f"__{TRACKED_PLAN_TOKEN}_1",
    )
    inline_step_id_prefix = old_call_node["step_id"].replace(
        "__call_$module_slug_tracked_plan_phase",
        "__$module_slug_tracked_plan_phase_1",
    )
    inline_roles = [step.rsplit(":", 1)[-1] for step in tracked_order]
    assert inline_roles == ["draft", "review", "match"]
    expected_inline_nodes = [
        {
            "kind": "provider",
            "name": f"{inline_name_prefix}__draft",
            "step_id": f"{inline_step_id_prefix}__draft",
            "call_alias": None,
        },
        {
            "kind": "provider",
            "name": f"{inline_name_prefix}__review",
            "step_id": f"{inline_step_id_prefix}__review",
            "call_alias": None,
        },
        {
            "kind": "match",
            "name": f"{inline_name_prefix}__match_review",
            "step_id": f"{inline_step_id_prefix}__match_review",
            "call_alias": None,
        },
    ]
    assert actual_route["public_plan_nodes"] == expected_inline_nodes

    expected_source_map = expected_route["source_map"]
    actual_source_map = actual_route["source_map"]
    assert TRACKED_PLAN_TOKEN not in actual_source_map
    assert set(actual_source_map) == {PUBLIC_ENTRY_TOKEN}
    expected_public_source = expected_source_map[PUBLIC_ENTRY_TOKEN]
    actual_public_source = actual_source_map[PUBLIC_ENTRY_TOKEN]
    assert actual_public_source["workflow_origin"] == expected_public_source["workflow_origin"]

    def without_tracked_plan_origins(values):
        def is_inline_route_origin(origin_key: str) -> bool:
            return (
                "tracked-plan-phase" in origin_key
                or "tracked_plan_phase" in origin_key
            )

        if isinstance(values, list):
            return [value for value in values if not is_inline_route_origin(value)]
        return {
            origin_key: value
            for origin_key, value in values.items()
            if not is_inline_route_origin(origin_key)
        }

    for field_name in (
        "step_origin_keys",
        "expansion_by_origin",
        "lineage_by_origin",
        "form_path_overrides",
    ):
        assert without_tracked_plan_origins(actual_public_source[field_name]) == (
            without_tracked_plan_origins(expected_public_source[field_name])
        )
    inline_origin_keys = {
        origin_key
        for origin_key in actual_public_source["step_origin_keys"]
        if "tracked-plan-phase" in origin_key or "tracked_plan_phase" in origin_key
    }
    for node in expected_inline_nodes:
        assert any(node["name"] in origin_key for origin_key in inline_origin_keys)
        assert any(
            node["step_id"].removeprefix("root.") in origin_key
            for origin_key in inline_origin_keys
        )
    inline_form_paths = actual_public_source["form_path_overrides"]
    assert {
        tuple(form_path)
        for origin_key, form_path in inline_form_paths.items()
        if origin_key in inline_origin_keys
    } == {("workflow-lisp", "defproc", "tracked-plan-phase")}
    assert inline_origin_keys - set(inline_form_paths)
    inline_lineage_labels = {
        lineage
        for origin_key, lineages in actual_public_source["lineage_by_origin"].items()
        if origin_key in inline_origin_keys
        for lineage in lineages
    }
    assert inline_lineage_labels >= {
        "procedure_call_site",
        "procedure_definition",
    }


def _assert_provisional_runtime_delta(
    expected_runtime: dict[str, object],
    actual_runtime: dict[str, object],
) -> None:
    frozen_runtime = _load_json(BASELINE)["runtime_contract"]
    assert expected_runtime == frozen_runtime

    def partition_rows(rows, *, key, candidate_keys):
        candidate_key_set = set(candidate_keys)
        candidates = [row for row in rows if key(row) in candidate_key_set]
        preserved = [row for row in rows if key(row) not in candidate_key_set]
        assert tuple(key(row) for row in candidates) == candidate_keys
        assert len({key(row) for row in rows}) == len(rows)
        return candidates, preserved

    expected_write_roots = expected_runtime["state_write_roots"]
    actual_write_roots = actual_runtime["state_write_roots"]
    expected_resume = expected_runtime["resume_checkpoints"]
    actual_resume = actual_runtime["resume_checkpoints"]
    expected_lexical = expected_runtime["lexical_checkpoints"]
    actual_lexical = actual_runtime["lexical_checkpoints"]
    for rows in (
        expected_write_roots,
        actual_write_roots,
        expected_resume,
        actual_resume,
        expected_lexical,
        actual_lexical,
    ):
        assert isinstance(rows, list)

    old_write_roots, preserved_write_roots = partition_rows(
        expected_write_roots,
        key=lambda row: row["stable_identity"],
        candidate_keys=_RETIRED_OLD_WRITE_ROOT_KEYS,
    )
    old_resume, preserved_resume = partition_rows(
        expected_resume,
        key=lambda row: (row["checkpoint_kind"], row["node_id"]),
        candidate_keys=_RETIRED_OLD_RESUME_KEYS,
    )
    old_lexical, preserved_lexical = partition_rows(
        expected_lexical,
        key=lambda row: row["checkpoint_id"],
        candidate_keys=_RETIRED_OLD_LEXICAL_KEYS,
    )

    new_write_root_keys = tuple(
        row["stable_identity"] for row in _NEW_INLINE_WRITE_ROOT_ROWS
    )
    new_resume_keys = tuple(
        (row["checkpoint_kind"], row["node_id"])
        for row in _NEW_INLINE_RESUME_ROWS
    )
    new_lexical_keys = tuple(row["checkpoint_id"] for row in _NEW_INLINE_LEXICAL_ROWS)
    new_write_roots, actual_preserved_write_roots = partition_rows(
        actual_write_roots,
        key=lambda row: row["stable_identity"],
        candidate_keys=new_write_root_keys,
    )
    new_resume, actual_preserved_resume = partition_rows(
        actual_resume,
        key=lambda row: (row["checkpoint_kind"], row["node_id"]),
        candidate_keys=new_resume_keys,
    )
    new_lexical, actual_preserved_lexical = partition_rows(
        actual_lexical,
        key=lambda row: row["checkpoint_id"],
        candidate_keys=new_lexical_keys,
    )

    assert old_write_roots == [
        row
        for row in frozen_runtime["state_write_roots"]
        if row["stable_identity"] in set(_RETIRED_OLD_WRITE_ROOT_KEYS)
    ]
    assert old_resume == [
        row
        for row in frozen_runtime["resume_checkpoints"]
        if (row["checkpoint_kind"], row["node_id"])
        in set(_RETIRED_OLD_RESUME_KEYS)
    ]
    assert old_lexical == [
        row
        for row in frozen_runtime["lexical_checkpoints"]
        if row["checkpoint_id"] in set(_RETIRED_OLD_LEXICAL_KEYS)
    ]
    assert new_write_roots == list(_NEW_INLINE_WRITE_ROOT_ROWS)
    assert new_resume == list(_NEW_INLINE_RESUME_ROWS)
    assert new_lexical == list(_NEW_INLINE_LEXICAL_ROWS)

    assert actual_preserved_write_roots == preserved_write_roots
    assert actual_preserved_resume == preserved_resume
    assert actual_preserved_lexical == preserved_lexical
    assert len(preserved_write_roots) == 4
    assert len(preserved_resume) == 4
    assert len(preserved_lexical) == 2

    assert actual_write_roots == [*new_write_roots, *preserved_write_roots]
    assert actual_resume == [
        preserved_resume[0],
        *new_resume,
        *preserved_resume[1:],
    ]
    assert actual_lexical == [
        preserved_lexical[0],
        *new_lexical,
        preserved_lexical[1],
    ]


@pytest.mark.parametrize(
    "corruption",
    ("preserved_public", "retired_old_candidate", "inline_candidate"),
)
def test_provisional_runtime_delta_rejects_identity_corruption(
    tracked_plan_compile,
    corruption: str,
) -> None:
    expected_runtime = deepcopy(_load_json(BASELINE)["runtime_contract"])
    actual_runtime = deepcopy(
        _tracked_plan_projection(tracked_plan_compile)["runtime_contract"]
    )

    if corruption == "preserved_public":
        row = next(
            row
            for row in actual_runtime["resume_checkpoints"]
            if row["presentation_key"]
            == f"{PUBLIC_ENTRY_TOKEN}__design__call_$module::tracked-design-phase"
            and row["checkpoint_kind"] == "call_boundary"
        )
        row["runtime_step_id_mode"] = "corrupt"
    elif corruption == "retired_old_candidate":
        row = next(
            row
            for row in expected_runtime["lexical_checkpoints"]
            if row["presentation_key"] == "$module::tracked-plan-phase__draft"
        )
        row["checkpoint_id"] = f"{row['checkpoint_id']}:corrupt"
    else:
        row = next(
            row
            for row in actual_runtime["state_write_roots"]
            if "tracked-plan-phase_1__draft" in row["stable_identity"]
        )
        row["stable_identity"] = f"{row['stable_identity']}:corrupt"

    with pytest.raises(AssertionError):
        _assert_provisional_runtime_delta(expected_runtime, actual_runtime)


def test_tracked_plan_phase_is_explicit_inline_procedure(tracked_plan_compile) -> None:
    compile_result = tracked_plan_compile.entry_result
    procedure = next(
        (
            procedure
            for procedure in compile_result.typed_procedures
            if procedure.definition.name == TRACKED_PLAN
        ),
        None,
    )

    assert procedure is not None, (
        "tracked-plan-phase remains a defworkflow; expected defproc with requested/resolved "
        "lowering inline"
    )
    assert procedure.signature.requested_lowering_mode.value == "inline"
    assert procedure.resolved_lowering_mode.value == "inline"
    assert TRACKED_PLAN not in {
        workflow.typed_workflow.definition.name
        for workflow in compile_result.lowered_workflows
    }
    public_bundle = compile_result.validated_bundles[PUBLIC_ENTRY]
    assert [
        step.kind.value
        for step in public_bundle.surface.steps
        if "tracked-plan-phase" in step.name
    ] == ["provider", "provider", "match"]


def test_post_edit_tracked_plan_phase_does_not_use_schema1_iteration_override_across_routes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_predicate = procedure_lowering._schema1_iteration_private_override_applies
    active_route: list[str | None] = [None]
    predicate_call_counts = {"legacy": 0, "wcc_m4": 0}
    tracked_plan_decisions = {"legacy": [], "wcc_m4": []}

    def spy_on_override_predicate(procedure, *, context):
        route = active_route[0]
        assert route is not None
        predicate_call_counts[route] += 1
        decision = original_predicate(procedure, context=context)
        if procedure.definition.name == TRACKED_PLAN:
            tracked_plan_decisions[route].append(decision)
        return decision

    monkeypatch.setattr(
        procedure_lowering,
        "_schema1_iteration_private_override_applies",
        spy_on_override_predicate,
    )

    compile_results = {}
    for route in ("legacy", "wcc_m4"):
        active_route[0] = route
        compile_results[route] = compile_stage3_entrypoint(
            EXAMPLE,
            source_roots=(WORKFLOWS,),
            entry_workflow="design-plan-impl-review-stack",
            provider_externs=_load_json(
                MIGRATION_INPUTS / "design_plan_impl_stack.providers.json"
            ),
            prompt_externs=_load_json(
                MIGRATION_INPUTS / "design_plan_impl_stack.prompts.json"
            ),
            command_boundaries=_load_json(
                MIGRATION_INPUTS / "design_plan_impl_stack.commands.json"
            ),
            validate_shared=True,
            workspace_root=REPO_ROOT,
            lowering_route=route,
        )
    active_route[0] = None

    assert tracked_plan_decisions["legacy"]
    assert not any(tracked_plan_decisions["legacy"])
    assert predicate_call_counts["wcc_m4"] == 0
    assert tracked_plan_decisions["wcc_m4"] == []
    for linked_result in compile_results.values():
        compile_result = linked_result.entry_result
        procedure = next(
            procedure
            for procedure in compile_result.typed_procedures
            if procedure.definition.name == TRACKED_PLAN
        )
        assert procedure.signature.requested_lowering_mode.value == "inline"
        assert procedure.resolved_lowering_mode.value == "inline"
        assert procedure.generated_workflow_name is None
        assert not any(
            workflow.typed_workflow.definition.name == TRACKED_PLAN
            or workflow.typed_workflow.definition.name.startswith(f"{TRACKED_PLAN}.")
            for workflow in compile_result.lowered_workflows
        )


def test_tracked_plan_phase_wrapper_uses_procedure_call(tracked_plan_compile) -> None:
    compile_result = tracked_plan_compile.entry_result
    public_workflow = next(
        workflow
        for workflow in compile_result.typed_workflows
        if workflow.definition.name == PUBLIC_ENTRY
    )
    expression_nodes = tuple(walk_expr(public_workflow.typed_body.expr))
    workflow_calls = {
        node.callee_name for node in expression_nodes if isinstance(node, CallExpr)
    }
    procedure_calls = {
        node.callee_name for node in expression_nodes if isinstance(node, ProcedureCallExpr)
    }

    assert TRACKED_PLAN in procedure_calls and TRACKED_PLAN not in workflow_calls, (
        "design-plan-impl-review-stack still uses (call tracked-plan-phase ...); expected "
        "an ordinary positional procedure call"
    )


def test_tracked_plan_phase_contract_matches_frozen_pre_migration_baseline(
    tracked_plan_compile,
) -> None:
    expected = _load_json(BASELINE)
    actual = _tracked_plan_projection(tracked_plan_compile)

    assert expected["schema_version"] == "procedure_first.tracked_plan_phase_contract.v1"
    assert expected["public_contract"]["entry_workflow"] == PUBLIC_ENTRY_TOKEN
    assert len(expected["public_contract"]["inputs"]) == 7
    assert len(expected["public_contract"]["outputs"]) == 9
    assert {row["subject"] for row in expected["caller_visible_effects"]} >= {
        "providers.plan.draft",
        "providers.plan.review",
    }
    assert expected["runtime_contract"]["resume_checkpoints"]
    assert expected["runtime_contract"]["lexical_checkpoints"]
    expected_route = expected.pop("internal_route")
    actual_route = actual.pop("internal_route")
    expected_runtime = expected.pop("runtime_contract")
    actual_runtime = actual.pop("runtime_contract")
    assert expected == actual
    _assert_reviewed_structural_delta(expected_route, actual_route)
    _assert_provisional_runtime_delta(expected_runtime, actual_runtime)
