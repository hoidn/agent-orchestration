"""Pure target-2.22 prompt-attempt identity contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any

import pytest

from orchestrator.workflow.prompt_fragment_contract import (
    CompilerPromptAttemptBindingPlan,
    CompilerPromptAttemptBindingPlanRow,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentRenderedSlot,
)
from orchestrator.workflow.prompting import (
    PromptFragmentRenderResult,
    render_prompt_fragment_base,
)
from orchestrator.workflow.provider_attempts import ProviderAttemptScope


ROLE_ORDER = (
    "fragment_program",
    "resolved_bindings",
    "injected_dependencies",
    "runtime_contributions",
    "provider_policy",
)
ROLE_SCHEMAS = {
    "fragment_program": "workflow_prompt_attempt_fragment_program.v1",
    "resolved_bindings": "workflow_prompt_attempt_resolved_bindings.v1",
    "injected_dependencies": (
        "workflow_prompt_attempt_injected_dependencies.v1"
    ),
    "runtime_contributions": (
        "workflow_prompt_attempt_runtime_contributions.v1"
    ),
    "provider_policy": "workflow_prompt_attempt_provider_policy.v1",
}
V1_SCHEMA = "workflow_prompt_fragment_snapshot.functional.v1"
V2_SCHEMA = "workflow_prompt_fragment_snapshot.functional.v2"
IDENTITY_SCHEMA = "workflow_prompt_attempt_identity.v1"
COMPILED_V1 = "compiled_prompt_fragment_identity.v1"


def _identity_module():
    try:
        return importlib.import_module(
            "orchestrator.workflow.prompt_identity"
        )
    except ModuleNotFoundError:
        pytest.fail(
            "prompt identity module is intentionally absent during RED",
            pytrace=False,
        )


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        _thaw(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _sha_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _sha_json(value: Any) -> str:
    return _sha_bytes(_canonical_bytes(value))


def _thaw(value: Any) -> Any:
    if isinstance(value, dict | MappingProxyType):
        return {key: _thaw(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_thaw(item) for item in value]
    return value


def _scope(*, run_id: str = "20260727T000000Z-q3") -> ProviderAttemptScope:
    return ProviderAttemptScope.from_dict(
        {
            "run_id": run_id,
            "resume_scope": {
                "root_workflow_file": "workflow.orc",
                "call_frame_ids": [],
            },
            "runtime_step_id": "Review",
            "enclosing_step": {
                "step_name": "Review",
                "step_id": "Review",
                "visit_count": 1,
            },
            "loop_iteration": None,
            "adjudication_subject": None,
        }
    )


def _run(scope: ProviderAttemptScope) -> dict[str, Any]:
    return {
        "run_id": scope.run_id,
        "workflow_file": scope.resume_scope.root_workflow_file,
        "workflow_checksum": _sha_bytes(b"workflow"),
    }


def _attempt(
    scope: ProviderAttemptScope,
    ordinal: int,
) -> dict[str, Any]:
    return {
        "scope": scope.to_dict(),
        "scope_sha256": scope.key,
        "step_key": hashlib.sha256(
            scope.runtime_step_id.encode("utf-8")
        ).hexdigest()[:24],
        "visit_key": scope.key[7:31],
        "ordinal": ordinal,
    }


def _plan() -> CompilerPromptAttemptBindingPlan:
    rows = (
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=0,
            slot_name="primary_doc",
            slot_kind="doc",
            refinement=None,
            output_role="none",
            delivery="dependency",
            runtime_source={
                "kind": "required_dependency",
                "ordinal": 0,
            },
            renderer=None,
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=1,
            slot_name="lexical_focus",
            slot_kind="text",
            refinement=None,
            output_role="none",
            delivery="template",
            runtime_source={"kind": "rendered_slot", "ordinal": 0},
            renderer={
                "renderer_id": "raw-utf8-string",
                "renderer_version": 1,
            },
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=2,
            slot_name="imported_value",
            slot_kind="value",
            refinement={"kind": "primitive", "name": "Value"},
            output_role="none",
            delivery="template",
            runtime_source={"kind": "rendered_slot", "ordinal": 1},
            renderer={
                "renderer_id": "canonical-json",
                "renderer_version": 1,
            },
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=3,
            slot_name="reference_doc",
            slot_kind="doc",
            refinement={
                "kind": "path",
                "name": "ReferenceDoc",
                "under": "inputs",
                "must_exist_target": True,
            },
            output_role="none",
            delivery="dependency",
            runtime_source={
                "kind": "required_dependency",
                "ordinal": 1,
            },
            renderer=None,
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=4,
            slot_name="unshown_doc",
            slot_kind="doc",
            refinement=None,
            output_role="none",
            delivery="dependency",
            runtime_source={
                "kind": "required_dependency",
                "ordinal": 2,
            },
            renderer=None,
        ),
        CompilerPromptAttemptBindingPlanRow(
            declaration_ordinal=5,
            slot_name="report_path",
            slot_kind="path",
            refinement={
                "kind": "path",
                "name": "ReportPath",
                "under": "artifacts/reports",
                "must_exist_target": False,
            },
            output_role="required_string_file",
            delivery="template",
            runtime_source={"kind": "rendered_slot", "ordinal": 2},
            renderer={
                "renderer_id": "posix-path-line",
                "renderer_version": 1,
            },
        ),
    )
    return CompilerPromptAttemptBindingPlan(
        schema_version="compiler_prompt_attempt_binding_plan.v1",
        rows=rows,
        plan_sha256=None,
    ).with_canonical_sha256()


def _replace_plan_row(
    plan: CompilerPromptAttemptBindingPlan,
    row_index: int,
    **changes: Any,
) -> CompilerPromptAttemptBindingPlan:
    rows = list(plan.rows)
    rows[row_index] = replace(rows[row_index], **changes)
    return CompilerPromptAttemptBindingPlan(
        schema_version=plan.schema_version,
        rows=tuple(rows),
        plan_sha256=None,
    ).with_canonical_sha256()


def _render_result(
    plan: CompilerPromptAttemptBindingPlan,
    *,
    lexical_value: str = "focus",
    imported_value: Any = None,
    report_path: str = "artifacts/reports/out.md",
) -> PromptFragmentRenderResult:
    if imported_value is None:
        imported_value = {"mode": "strict"}
    rendered_rows = tuple(
        row for row in plan.rows if row.slot_kind != "doc"
    )
    contract = CompilerPromptFragmentContract(
        schema_version="compiler_prompt_fragment_contract.v1",
        template_utf8=" ".join(
            f"{{{row.slot_name}}}" for row in rendered_rows
        ),
        rendered_slots=tuple(
            CompilerPromptFragmentRenderedSlot(
                name=row.slot_name,
                kind=row.slot_kind,
                static_type=(
                    row.refinement
                    or {"kind": "primitive", "name": "String"}
                ),
                renderer_id=row.renderer["renderer_id"],
                value_source={
                    "kind": "typed_binding_ref",
                    "binding": {"ref": f"inputs.{row.slot_name}"},
                },
                placeholder_ordinals=(ordinal,),
            )
            for ordinal, row in enumerate(rendered_rows)
        ),
        compiled_prompt_fragment_identity=_sha_bytes(
            b"owner-fragment-contract"
        ),
    )
    rendered_values_by_kind = {
        "text": lexical_value,
        "value": imported_value,
        "path": report_path,
    }
    result = render_prompt_fragment_base(
        contract,
        resolved_slot_values={
            row.slot_name: rendered_values_by_kind[row.slot_kind]
            for row in rendered_rows
        },
        target_dsl_version="2.22",
        compiler_prompt_attempt_binding_plan=plan,
    )
    assert isinstance(result, PromptFragmentRenderResult)
    return result


def _authored_rows() -> list[dict[str, Any]]:
    return [
        {
            "row_id": _sha_bytes(b"primary-row"),
            "role": "required",
            "authored_index": 0,
            "binding_ref": "required-document",
            "evaluated_relpath": "inputs/primary.md",
            "status": "present",
            "canonical_target": "inputs/primary.md",
        },
        {
            "row_id": _sha_bytes(b"reference-row"),
            "role": "required",
            "authored_index": 1,
            "binding_ref": "required-reference",
            "evaluated_relpath": "inputs/reference.md",
            "status": "present",
            "canonical_target": "inputs/reference.md",
        },
        {
            "row_id": _sha_bytes(b"unshown-row"),
            "role": "required",
            "authored_index": 2,
            "binding_ref": "required-unshown",
            "evaluated_relpath": "inputs/unshown.md",
            "status": "present",
            "canonical_target": "inputs/unshown.md",
        },
    ]


def _canonical_groups() -> list[dict[str, Any]]:
    return [
        {
            "order": 0,
            "canonical_target": "inputs/primary.md",
            "effective_role": "required",
            "authored_row_ids": [_sha_bytes(b"primary-row")],
            "normalized_total_bytes": 12,
            "retained_bytes": 12,
            "retained_sha256": _sha_bytes(b"primary-body"),
            "render_status": "complete",
            "shown_bytes": 12,
            "shown_sha256": _sha_bytes(b"primary-body"),
        },
        {
            "order": 1,
            "canonical_target": "inputs/reference.md",
            "effective_role": "required",
            "authored_row_ids": [_sha_bytes(b"reference-row")],
            "normalized_total_bytes": 100,
            "retained_bytes": 80,
            "retained_sha256": _sha_bytes(b"retained-reference"),
            "render_status": "truncated",
            "shown_bytes": 8,
            "shown_sha256": _sha_bytes(b"shown-re"),
        },
        {
            "order": 2,
            "canonical_target": "inputs/unshown.md",
            "effective_role": "optional",
            "authored_row_ids": [_sha_bytes(b"unshown-row")],
            "normalized_total_bytes": 44,
            "retained_bytes": 44,
            "retained_sha256": _sha_bytes(b"unshown-body"),
            "render_status": "omitted",
            "shown_bytes": 0,
            "shown_sha256": None,
        },
    ]


def _injection(*, block: bytes = b"dependency-block-with-summary") -> dict[str, Any]:
    return {
        "mode": "content",
        "max_bytes": 1000,
        "instruction_max_bytes": 100,
        "summary_reserve_bytes": 200,
        "position": "prepend",
        "was_truncated": True,
        "pre_truncation_bytes": 500,
        "block_bytes": len(block),
        "block_sha256": _sha_bytes(block),
        "normalized_total_bytes": 156,
        "retained_bytes": 136,
        "shown_bytes": 20,
        "files_total": 3,
        "files_shown": 2,
        "files_truncated": 1,
        "files_omitted": 1,
        "summary_bytes": 12,
        "summary_sha256": _sha_bytes(b"summary-data"),
    }


def _contributions() -> list[dict[str, Any]]:
    return [
        {
            "composition_ordinal": 0,
            "kind": "consumed_artifacts",
            "position": "prepend",
            "bytes": 7,
            "sha256": _sha_bytes(b"consume"),
        },
        {
            "composition_ordinal": 1,
            "kind": "output_positions",
            "position": "append",
            "bytes": 6,
            "sha256": _sha_bytes(b"output"),
        },
        {
            "composition_ordinal": 2,
            "kind": "structured_result",
            "position": "append",
            "bytes": 6,
            "sha256": _sha_bytes(b"result"),
        },
    ]


def _provider_policy(**updates: Any) -> dict[str, Any]:
    policy = {
        "provider_name": "codex",
        "model": "gpt-5",
        "effort": "high",
        "timeout_sec": 1800,
        "input_mode": "stdin",
    }
    policy.update(updates)
    return policy


def _roles(module=None, **changes: Any) -> dict[str, Any]:
    module = module or _identity_module()
    plan = changes.pop("plan", None)
    if plan is None:
        plan = _plan()
    render_result = changes.pop("render_result", None)
    if render_result is None:
        render_result = _render_result(
            plan,
            lexical_value=changes.pop("lexical_value", "focus"),
            imported_value=changes.pop(
                "imported_value",
                {"mode": "strict"},
            ),
        )
    authored_rows = changes.pop("authored_rows", _authored_rows())
    groups = changes.pop("groups", _canonical_groups())
    injection = changes.pop("injection", _injection())
    contributions = changes.pop("contributions", _contributions())
    policy = changes.pop("policy", _provider_policy())
    compiled_identity = changes.pop(
        "compiled_identity", _sha_bytes(b"compiled-fragment")
    )
    identity_schema = changes.pop("identity_schema", COMPILED_V1)
    assert not changes
    return {
        "fragment_program": module.build_fragment_program_role(
            identity_schema_version=identity_schema,
            compiled_prompt_fragment_identity=compiled_identity,
        ),
        "resolved_bindings": module.build_resolved_bindings_role(
            binding_plan=plan,
            fragment_render_result=render_result,
            authored_rows=authored_rows,
        ),
        "injected_dependencies": (
            module.build_injected_dependencies_role(
                canonical_groups=groups,
                injection=injection,
            )
        ),
        "runtime_contributions": (
            module.build_runtime_contributions_role(contributions)
        ),
        "provider_policy": module.build_provider_policy_role(policy),
    }


def _attempt_identity(
    module=None,
    *,
    final_prompt: bytes = b"prepared-final-prompt",
    roles: dict[str, Any] | None = None,
    **role_changes: Any,
):
    module = module or _identity_module()
    return module.build_prompt_attempt_identity(
        roles=roles or _roles(module, **role_changes),
        final_prompt=final_prompt,
    )


def _record_seal(record: dict[str, Any]) -> dict[str, Any]:
    body = deepcopy(record)
    body.pop("record_sha256", None)
    record["record_sha256"] = _sha_json(body)
    return record


def _retained_v1(
    *,
    scope: ProviderAttemptScope | None = None,
    ordinal: int = 1,
    final_prompt: bytes = b"prepared-final-prompt",
) -> dict[str, Any]:
    scope = scope or _scope()
    record = {
        "schema": V1_SCHEMA,
        "record_kind": "prompt_snapshot",
        "run": _run(scope),
        "compiler_contract": {
            "schema": "compiler_prompt_dependency_contract.v1",
            "origin_kind": "workflow_lisp_prompt_fragment",
        },
        "attempt": _attempt(scope, ordinal),
        "authored_rows": _authored_rows(),
        "canonical_groups": _canonical_groups(),
        "instruction": {
            "source": "default",
            "bytes": 0,
            "sha256": _sha_bytes(b""),
        },
        "injection": _injection(),
        "final_prompt": {
            "bytes": len(final_prompt),
            "sha256": _sha_bytes(final_prompt),
        },
        "compiled_prompt_fragment_identity": _sha_bytes(
            b"compiled-fragment"
        ),
    }
    return _record_seal(record)


def _valid_v2(module=None) -> tuple[dict[str, Any], dict[str, Any]]:
    module = module or _identity_module()
    retained = _retained_v1()
    record = module.build_prompt_fragment_snapshot_v2(
        validated_retained_v1=retained,
        prompt_attempt_identity=_attempt_identity(module),
        compiler_fragment_identity_schema_version=COMPILED_V1,
    )
    return retained, _thaw(record)


def _reseal_role(role: dict[str, Any]) -> None:
    role["sha256"] = _sha_json(role["payload"])


def _reseal_identity(identity: dict[str, Any]) -> None:
    identity["composition_sha256"] = _sha_json(
        {
            "schema_version": "workflow_prompt_attempt_composition.v1",
            "role_sha256": {
                role_key: identity["roles"][role_key]["sha256"]
                for role_key in ROLE_ORDER
            },
            "final_prompt": identity["final_prompt"],
        }
    )


def _set_path(value: dict[str, Any], path: tuple[Any, ...], replacement: Any) -> None:
    target: Any = value
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = replacement


def _all_strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, dict | MappingProxyType):
        return tuple(
            string
            for key, item in value.items()
            for string in (str(key), *_all_strings(item))
        )
    if isinstance(value, tuple | list):
        return tuple(
            string for item in value for string in _all_strings(item)
        )
    return (value,) if isinstance(value, str) else ()


def test_canonical_role_vectors_use_exact_tokens_utf8_json_and_lower_sha256() -> None:
    module = _identity_module()
    roles = _roles(module)

    assert tuple(roles) == ROLE_ORDER
    for role_key in ROLE_ORDER:
        role = roles[role_key]
        assert tuple(role) == ("schema_version", "payload", "sha256")
        assert role["schema_version"] == ROLE_SCHEMAS[role_key]
        assert role["sha256"] == _sha_json(_thaw(role["payload"]))
        assert role["sha256"] == role["sha256"].lower()
        assert module.validate_prompt_identity_role(role_key, role) == role

    unicode_payload = {
        "z": "雪",
        "a": {"β": 2, "a": 1},
    }
    assert module.canonical_json_bytes(unicode_payload) == (
        '{"a":{"a":1,"β":2},"z":"雪"}'.encode("utf-8")
    )
    assert module.canonical_sha256(unicode_payload) == _sha_json(
        unicode_payload
    )


def test_canonical_json_rejects_non_json_keys_and_nonfinite_numbers() -> None:
    module = _identity_module()

    for value in ({1: "not-a-json-object-key"}, {"number": float("nan")}):
        with pytest.raises((TypeError, ValueError)):
            module.canonical_json_bytes(value)


@pytest.mark.parametrize("role_key", ROLE_ORDER)
def test_role_wrappers_reject_each_missing_extra_or_mistokened_field(
    role_key: str,
) -> None:
    module = _identity_module()
    valid = _thaw(_roles(module)[role_key])

    for missing in tuple(valid):
        candidate = deepcopy(valid)
        candidate.pop(missing)
        with pytest.raises(
            ValueError, match="prompt_attempt_identity_role_invalid"
        ):
            module.validate_prompt_identity_role(role_key, candidate)

    extra = deepcopy(valid)
    extra["extra"] = None
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role(role_key, extra)

    wrong_token = deepcopy(valid)
    wrong_token["schema_version"] = ROLE_SCHEMAS[
        ROLE_ORDER[(ROLE_ORDER.index(role_key) + 1) % len(ROLE_ORDER)]
    ]
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role(role_key, wrong_token)

    uppercase_digest = deepcopy(valid)
    uppercase_digest["sha256"] = uppercase_digest["sha256"].upper()
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role(role_key, uppercase_digest)


@pytest.mark.parametrize("role_key", ROLE_ORDER)
def test_role_payloads_reject_each_missing_and_extra_field(
    role_key: str,
) -> None:
    module = _identity_module()
    valid = _thaw(_roles(module)[role_key])

    for missing in tuple(valid["payload"]):
        candidate = deepcopy(valid)
        candidate["payload"].pop(missing)
        _reseal_role(candidate)
        with pytest.raises(
            ValueError, match="prompt_attempt_identity_role_invalid"
        ):
            module.validate_prompt_identity_role(role_key, candidate)

    extra = deepcopy(valid)
    extra["payload"]["extra"] = None
    _reseal_role(extra)
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role(role_key, extra)


@pytest.mark.parametrize(
    ("role_key", "path", "replacement"),
    (
        (
            "fragment_program",
            ("identity_schema_version",),
            "compiled_prompt_fragment_identity.v9",
        ),
        (
            "fragment_program",
            ("compiled_prompt_fragment_identity",),
            "SHA256:" + "0" * 64,
        ),
        ("resolved_bindings", ("binding_plan_sha256",), None),
        ("resolved_bindings", ("rows",), {}),
        ("injected_dependencies", ("shown_groups",), {}),
        ("injected_dependencies", ("injection", "position"), "middle"),
        ("runtime_contributions", ("rows", 0, "bytes"), 0),
        (
            "runtime_contributions",
            ("rows", 0, "kind"),
            "provider_session",
        ),
        ("provider_policy", ("provider_name",), ""),
        ("provider_policy", ("timeout_sec",), 0),
        ("provider_policy", ("input_mode",), "file"),
    ),
)
def test_roles_reject_malformed_nested_fields(
    role_key: str,
    path: tuple[Any, ...],
    replacement: Any,
) -> None:
    module = _identity_module()
    candidate = _thaw(_roles(module)[role_key])
    _set_path(candidate["payload"], path, replacement)
    _reseal_role(candidate)

    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role(role_key, candidate)


@pytest.mark.parametrize("lane", ("builder", "persisted_role"))
@pytest.mark.parametrize(
    ("field_name", "absolute_path"),
    tuple(
        (field_name, absolute_path)
        for field_name in ("provider_name", "model", "effort")
        for absolute_path in (
            "/workspace/provider",
            r"\\server\share\provider",
            r"C:\workspace\provider",
        )
    ),
)
def test_provider_policy_rejects_absolute_paths_at_each_identity_ingress(
    lane: str,
    field_name: str,
    absolute_path: str,
) -> None:
    module = _identity_module()
    if lane == "builder":
        with pytest.raises(
            ValueError,
            match=r"^prompt_attempt_identity_role_invalid:",
        ):
            module.build_provider_policy_role(
                _provider_policy(**{field_name: absolute_path})
            )
        return

    role = _thaw(_roles(module)["provider_policy"])
    role["payload"][field_name] = absolute_path
    _reseal_role(role)
    with pytest.raises(
        ValueError,
        match=r"^prompt_attempt_identity_role_invalid:",
    ):
        module.validate_prompt_identity_role("provider_policy", role)


@pytest.mark.parametrize(
    "slot_name",
    (
        "not a valid Q1 slot",
        "9starts_with_digit",
        "-starts-with-hyphen",
        "contains.dot",
        "unicode_雪",
    ),
)
@pytest.mark.parametrize(
    "lane",
    ("compiler_binding_plan", "fragment_render_result", "persisted_role"),
)
def test_q1_slot_name_grammar_is_enforced_at_each_identity_ingress(
    lane: str,
    slot_name: str,
) -> None:
    module = _identity_module()

    if lane == "compiler_binding_plan":
        with pytest.raises(
            ValueError, match="prompt_attempt_binding_plan_invalid"
        ):
            plan = _plan()
            replace(plan.rows[1], slot_name=slot_name)
    elif lane == "fragment_render_result":
        with pytest.raises(
            ValueError, match="prompt_attempt_binding_plan_invalid"
        ):
            plan = _plan()
            render_result = _render_result(plan)
            object.__setattr__(
                render_result.trace[0],
                "slot_name",
                slot_name,
            )
            module.build_resolved_bindings_role(
                binding_plan=plan,
                fragment_render_result=render_result,
                authored_rows=_authored_rows(),
            )
    else:
        with pytest.raises(
            ValueError, match="prompt_attempt_identity_role_invalid"
        ):
            role = _thaw(_roles(module)["resolved_bindings"])
            role["payload"]["rows"][1]["slot_name"] = slot_name
            _reseal_role(role)
            module.validate_prompt_identity_role(
                "resolved_bindings", role
            )


def _nested_value_refinement() -> dict[str, Any]:
    return {
        "kind": "record",
        "name": "ReviewEnvelope",
        "fields": [
            {
                "name": "mode",
                "type": {
                    "kind": "enum",
                    "name": "ReviewMode",
                    "allowed": ["strict", "focused"],
                },
            },
            {
                "name": "items",
                "type": {
                    "kind": "list",
                    "item": {"kind": "primitive", "name": "Value"},
                },
            },
        ],
    }


def test_valid_compiler_normalized_refinement_passes_plan_and_role_validation() -> None:
    module = _identity_module()
    refinement = _nested_value_refinement()
    plan = _replace_plan_row(_plan(), 2, refinement=refinement)

    built = module.build_resolved_bindings_role(
        binding_plan=plan,
        fragment_render_result=_render_result(plan),
        authored_rows=_authored_rows(),
    )
    assert _thaw(built["payload"]["rows"][2]["refinement"]) == refinement

    resealed_role = _thaw(_roles(module)["resolved_bindings"])
    resealed_role["payload"]["rows"][2]["refinement"] = refinement
    _reseal_role(resealed_role)
    validated_refinement = module.validate_prompt_identity_role(
        "resolved_bindings", resealed_role
    )["payload"]["rows"][2]["refinement"]
    assert _thaw(validated_refinement) == refinement


@pytest.mark.parametrize(
    "invalid_refinement",
    (
        {
            "unexpected_absolute_workspace_path": (
                "/home/ollie/Documents/agent-orchestration"
            )
        },
        {
            "kind": "primitive",
            "name": "Value",
            "unexpected": True,
        },
    ),
)
def test_resealed_resolved_role_rejects_open_or_arbitrary_refinement(
    invalid_refinement: dict[str, Any],
) -> None:
    module = _identity_module()
    role = _thaw(_roles(module)["resolved_bindings"])
    role["payload"]["rows"][2]["refinement"] = invalid_refinement
    _reseal_role(role)

    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role("resolved_bindings", role)


def test_resolved_bindings_forbid_absolute_paths_in_refinements() -> None:
    module = _identity_module()
    role = _thaw(_roles(module)["resolved_bindings"])
    role["payload"]["rows"][-1]["refinement"]["under"] = (
        "/absolute/workspace"
    )
    _reseal_role(role)

    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role("resolved_bindings", role)


def test_dependency_role_rejects_duplicate_authored_row_membership() -> None:
    module = _identity_module()
    role = _thaw(_roles(module)["injected_dependencies"])
    duplicate = role["payload"]["shown_groups"][0]["authored_row_ids"][0]
    role["payload"]["shown_groups"][1]["authored_row_ids"].append(duplicate)
    _reseal_role(role)

    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_identity_role(
            "injected_dependencies", role
        )


def test_identity_schema_is_closed_fixed_order_and_composition_sealed() -> None:
    module = _identity_module()
    identity = _attempt_identity(module)

    assert tuple(identity) == (
        "schema_version",
        "roles",
        "final_prompt",
        "composition_sha256",
    )
    assert identity["schema_version"] == IDENTITY_SCHEMA
    assert tuple(identity["roles"]) == ROLE_ORDER
    assert identity["composition_sha256"] == _sha_json(
        {
            "schema_version": "workflow_prompt_attempt_composition.v1",
            "role_sha256": {
                key: identity["roles"][key]["sha256"]
                for key in ROLE_ORDER
            },
            "final_prompt": identity["final_prompt"],
        }
    )
    assert module.validate_prompt_attempt_identity(identity) == identity


def test_identity_rejects_closed_schema_role_and_composition_tamper() -> None:
    module = _identity_module()
    identity = _thaw(_attempt_identity(module))

    for missing in tuple(identity):
        candidate = deepcopy(identity)
        candidate.pop(missing)
        with pytest.raises(ValueError):
            module.validate_prompt_attempt_identity(candidate)

    extra = deepcopy(identity)
    extra["extra"] = None
    with pytest.raises(ValueError):
        module.validate_prompt_attempt_identity(extra)

    role_tamper = deepcopy(identity)
    role_tamper["roles"]["provider_policy"]["sha256"] = _sha_bytes(b"tamper")
    _reseal_identity(role_tamper)
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_attempt_identity(role_tamper)

    composition_tamper = deepcopy(identity)
    composition_tamper["composition_sha256"] = _sha_bytes(b"tamper")
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_composition_invalid"
    ):
        module.validate_prompt_attempt_identity(composition_tamper)


def test_pure_module_has_no_filesystem_runtime_provider_or_report_actions() -> None:
    module = _identity_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    forbidden = (
        "pathlib",
        "os.",
        "open(",
        "allocate",
        "publish",
        "prepare_invocation",
        "launch",
        "subprocess",
        "report",
        "prompt.split",
        "prompt.parse",
    )
    assert not any(token in source for token in forbidden)
