"""Pure target-2.22 prompt-attempt identity contracts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
import hashlib
import importlib
import inspect
import json
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

import pytest

from orchestrator.workflow.prompt_fragment_contract import (
    CompilerPromptAttemptBindingPlan,
    CompilerPromptAttemptBindingPlanRow,
    CompilerPromptFragmentContract,
    CompilerPromptFragmentRenderedSlot,
)
from orchestrator.workflow.prompting import (
    PromptFragmentRenderResult,
    prompt_fragment_transport_value_sha256 as owner_transport_value_sha256,
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
PREPARATION_FAILURE_SCHEMA = (
    "workflow_prompt_fragment_preparation_failure.functional.v1"
)
COMPILED_V1 = "compiled_prompt_fragment_identity.v1"
ATTEMPT_IDENTITY_VERSION = "workflow_prompt_attempt_identity.v1"


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


def _replace_identity_role(
    identity: dict[str, Any],
    role_key: str,
    role: Any,
) -> dict[str, Any]:
    changed = _thaw(identity)
    changed["roles"][role_key] = _thaw(role)
    _reseal_identity(changed)
    return changed


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


def test_provider_policy_preserves_nullable_and_relative_slash_identifiers() -> None:
    module = _identity_module()

    nullable = module.build_provider_policy_role(
        _provider_policy(model=None, effort=None)
    )
    relative = module.build_provider_policy_role(
        _provider_policy(
            provider_name="providers/codex",
            model="models/gpt-5",
            effort="efforts/high",
        )
    )

    assert nullable["payload"]["model"] is None
    assert nullable["payload"]["effort"] is None
    assert relative["payload"] == _provider_policy(
        provider_name="providers/codex",
        model="models/gpt-5",
        effort="efforts/high",
    )


def test_provider_policy_preserves_positive_fractional_timeout() -> None:
    module = _identity_module()

    role = module.build_provider_policy_role(
        _provider_policy(timeout_sec=0.1)
    )

    assert role["payload"]["timeout_sec"] == 0.1


def test_provider_policy_builder_preserves_huge_positive_exact_int_timeout() -> None:
    module = _identity_module()
    huge_timeout = 10**309

    role = module.build_provider_policy_role(
        _provider_policy(timeout_sec=huge_timeout)
    )

    preserved = role["payload"]["timeout_sec"]
    assert type(preserved) is int
    assert preserved == huge_timeout


def test_resolved_bindings_follow_plan_order_and_owned_trace_projections() -> None:
    module = _identity_module()
    plan = _plan()
    role = module.build_resolved_bindings_role(
        binding_plan=plan,
        fragment_render_result=_render_result(plan),
        authored_rows=_authored_rows(),
    )

    assert [row["slot_name"] for row in role["payload"]["rows"]] == [
        "primary_doc",
        "lexical_focus",
        "imported_value",
        "reference_doc",
        "unshown_doc",
        "report_path",
    ]
    primary, lexical, imported, reference, unshown, output_path = (
        role["payload"]["rows"]
    )
    assert primary["renderer"] is None
    assert primary["rendered_bytes_sha256"] is None
    assert primary["value_sha256"] == _sha_bytes(b"inputs/primary.md")
    assert reference["renderer"] is None
    assert reference["rendered_bytes_sha256"] is None
    assert reference["value_sha256"] == _sha_bytes(
        b"inputs/reference.md"
    )
    assert unshown["value_sha256"] == _sha_bytes(b"inputs/unshown.md")
    assert lexical["value_sha256"] == _sha_bytes(b"focus")
    assert imported["value_sha256"] == _sha_bytes(b'{"mode":"strict"}')
    assert output_path["output_role"] == "required_string_file"
    assert output_path["rendered_bytes_sha256"] == _sha_bytes(
        b"artifacts/reports/out.md"
    )


def test_transport_value_identity_reuses_owner_key_normalization() -> None:
    module = _identity_module()
    value = {1: "x"}

    assert module.prompt_fragment_transport_value_sha256(
        value
    ) == owner_transport_value_sha256(value)


def test_text_refinement_failure_preserves_compiler_owner_diagnostic() -> None:
    module = _identity_module()
    plan = _plan()
    render_result = _render_result(plan)
    object.__setattr__(
        plan.rows[1],
        "refinement",
        MappingProxyType({"kind": "primitive", "name": "String"}),
    )

    with pytest.raises(
        ValueError,
        match=r"^prompt_attempt_binding_plan_invalid:",
    ) as raised:
        module.build_resolved_bindings_role(
            binding_plan=plan,
            fragment_render_result=render_result,
            authored_rows=_authored_rows(),
        )

    assert "prompt_attempt_identity_role_invalid" not in str(raised.value)


@pytest.mark.parametrize("corrupt_owner", ("plan", "trace"))
def test_corrupt_binding_owners_preserve_binding_plan_diagnostic(
    corrupt_owner: str,
) -> None:
    module = _identity_module()
    plan = _plan()
    render_result = _render_result(plan)
    if corrupt_owner == "plan":
        object.__setattr__(
            plan,
            "plan_sha256",
            _sha_bytes(b"corrupt-plan"),
        )
    else:
        object.__setattr__(
            render_result,
            "_trace_sha256",
            _sha_bytes(b"corrupt-trace"),
        )

    with pytest.raises(
        ValueError,
        match=r"^prompt_attempt_binding_plan_invalid:",
    ) as raised:
        module.build_resolved_bindings_role(
            binding_plan=plan,
            fragment_render_result=render_result,
            authored_rows=_authored_rows(),
        )

    assert "prompt_attempt_identity_role_invalid" not in str(raised.value)


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


@pytest.mark.parametrize(
    ("lane", "row_index", "ordinal"),
    (
        ("compiler_binding_plan", 0, False),
        ("compiler_binding_plan", 1, True),
        ("fragment_render_result", 0, False),
        ("fragment_render_result", 1, True),
    ),
)
def test_identity_ingress_ordinals_reject_booleans_that_equal_integers(
    lane: str,
    row_index: int,
    ordinal: bool,
) -> None:
    module = _identity_module()

    with pytest.raises(
        ValueError, match="prompt_attempt_binding_plan_invalid"
    ):
        if lane == "compiler_binding_plan":
            plan = _plan()
            replace(
                plan.rows[row_index],
                declaration_ordinal=ordinal,
            )
        else:
            plan = _plan()
            render_result = _render_result(plan)
            replace(
                render_result.trace[row_index],
                rendered_slot_ordinal=ordinal,
            )


def test_combined_resealed_q1_name_and_boolean_ordinal_vector_rejects() -> None:
    module = _identity_module()
    plan = _plan()
    render_result = _render_result(plan)
    object.__setattr__(plan.rows[0], "declaration_ordinal", False)
    object.__setattr__(
        plan.rows[1],
        "slot_name",
        "not a valid Q1 slot",
    )
    object.__setattr__(
        render_result.trace[0],
        "rendered_slot_ordinal",
        False,
    )
    object.__setattr__(
        render_result.trace[0],
        "slot_name",
        "not a valid Q1 slot",
    )

    with pytest.raises(
        ValueError, match="prompt_attempt_binding_plan_invalid"
    ):
        module.build_resolved_bindings_role(
            binding_plan=plan,
            fragment_render_result=render_result,
            authored_rows=_authored_rows(),
        )


@pytest.mark.parametrize(
    "slot_name",
    ("slot", "_slot", "slot-name_1", "A9-_"),
)
def test_q1_slot_name_grammar_preserves_valid_ascii_names(
    slot_name: str,
) -> None:
    module = _identity_module()
    plan = _replace_plan_row(_plan(), 1, slot_name=slot_name)
    render_result = _render_result(plan)

    role = module.build_resolved_bindings_role(
        binding_plan=plan,
        fragment_render_result=render_result,
        authored_rows=_authored_rows(),
    )

    assert role["payload"]["rows"][1]["slot_name"] == slot_name


def test_only_referenced_lexical_and_imported_inputs_affect_binding_identity() -> None:
    module = _identity_module()
    builder = module.build_resolved_bindings_role
    parameters = inspect.signature(builder).parameters
    assert tuple(parameters) == (
        "binding_plan",
        "fragment_render_result",
        "authored_rows",
    )
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY
        for parameter in parameters.values()
    )

    def build_from_owner_projection(
        *,
        unused_lexical_bindings: dict[str, Any],
        unreferenced_imported_constants: dict[str, Any],
    ):
        plan = _plan()
        owner_state = {
            "binding_plan": plan,
            "fragment_render_result": _render_result(plan),
            "authored_rows": _authored_rows(),
            "unused_lexical_bindings": unused_lexical_bindings,
            "unreferenced_imported_constants": (
                unreferenced_imported_constants
            ),
        }
        accepted_projection = {
            name: owner_state[name] for name in parameters
        }
        return builder(**accepted_projection)

    baseline = build_from_owner_projection(
        unused_lexical_bindings={"unused": "first"},
        unreferenced_imported_constants={"UNUSED_CONSTANT": 1},
    )
    changed_ambient = build_from_owner_projection(
        unused_lexical_bindings={"unused": "changed"},
        unreferenced_imported_constants={"UNUSED_CONSTANT": 99},
    )
    assert changed_ambient["sha256"] == baseline["sha256"]
    persisted_strings = set(_all_strings(changed_ambient))
    assert {
        "unused",
        "changed",
        "UNUSED_CONSTANT",
    }.isdisjoint(persisted_strings)

    for forbidden_argument in (
        {"unused_lexical_bindings": {"unused": "changed"}},
        {
            "unreferenced_imported_constants": {
                "UNUSED_CONSTANT": 99
            }
        },
    ):
        with pytest.raises(TypeError):
            plan = _plan()
            builder(
                binding_plan=plan,
                fragment_render_result=_render_result(plan),
                authored_rows=_authored_rows(),
                **forbidden_argument,
            )

    lexical_changed = _roles(
        module,
        lexical_value="new-focus",
    )["resolved_bindings"]
    imported_changed = _roles(
        module,
        imported_value={"mode": "new"},
    )["resolved_bindings"]
    assert lexical_changed["sha256"] != baseline["sha256"]
    assert imported_changed["sha256"] != baseline["sha256"]


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
def test_compiler_binding_plan_rejects_open_or_arbitrary_refinement(
    invalid_refinement: dict[str, Any],
) -> None:
    module = _identity_module()
    plan = _plan()
    render_result = _render_result(plan)
    object.__setattr__(
        plan.rows[2],
        "refinement",
        MappingProxyType(invalid_refinement),
    )

    with pytest.raises(
        ValueError, match="prompt_attempt_binding_plan_invalid"
    ):
        module.build_resolved_bindings_role(
            binding_plan=plan,
            fragment_render_result=render_result,
            authored_rows=_authored_rows(),
        )


def test_roles_are_content_free_and_immutable() -> None:
    module = _identity_module()
    roles = _roles(module)
    persisted_strings = set(_all_strings(roles))

    for forbidden in (
        "primary-body",
        "retained-reference",
        "unshown-body",
        "focus",
        '{"mode":"strict"}',
        "/absolute/workspace",
        "--dangerous-argv",
        "SECRET_ENV",
    ):
        assert forbidden not in persisted_strings

    assert isinstance(roles["resolved_bindings"], MappingProxyType)
    assert isinstance(
        roles["resolved_bindings"]["payload"]["rows"], tuple
    )
    with pytest.raises(TypeError):
        roles["provider_policy"]["payload"]["model"] = "changed"

    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.build_provider_policy_role(
            {
                **_provider_policy(),
                "argv": ["tool", "--dangerous-argv"],
            }
        )
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.build_provider_policy_role(
            {**_provider_policy(), "environment": {"SECRET_ENV": "value"}}
        )


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


def test_dependency_role_projects_only_shown_groups_and_prepared_block() -> None:
    module = _identity_module()
    role = _roles(module)["injected_dependencies"]

    assert [group["order"] for group in role["payload"]["shown_groups"]] == [
        0,
        1,
    ]
    assert [
        group["render_status"]
        for group in role["payload"]["shown_groups"]
    ] == ["complete", "truncated"]
    assert role["payload"]["injection"] == {
        "position": "prepend",
        "block_bytes": len(b"dependency-block-with-summary"),
        "block_sha256": _sha_bytes(b"dependency-block-with-summary"),
    }
    strings = set(_all_strings(role))
    assert "retained_sha256" not in strings
    assert "canonical_target" not in strings


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


@pytest.mark.parametrize("group_index", (0, 1))
def test_complete_and_truncated_shown_bytes_change_dependency_identity(
    group_index: int,
) -> None:
    module = _identity_module()
    baseline = _roles(module)["injected_dependencies"]
    groups = _canonical_groups()
    groups[group_index]["shown_sha256"] = _sha_bytes(
        f"changed-shown-{group_index}".encode()
    )
    groups[group_index]["retained_sha256"] = _sha_bytes(
        f"changed-retained-{group_index}".encode()
    )
    changed = _roles(
        module,
        groups=groups,
        injection=_injection(block=b"changed-prepared-block"),
    )["injected_dependencies"]

    assert changed["sha256"] != baseline["sha256"]


def test_unshown_dependency_bytes_are_digest_neutral_until_prompt_material_changes() -> None:
    module = _identity_module()
    baseline = _roles(module)["injected_dependencies"]
    groups = _canonical_groups()
    groups[1]["normalized_total_bytes"] += 200
    groups[1]["retained_bytes"] += 100
    groups[1]["retained_sha256"] = _sha_bytes(b"new-truncated-tail")
    groups[2]["normalized_total_bytes"] += 400
    groups[2]["retained_bytes"] += 400
    groups[2]["retained_sha256"] = _sha_bytes(b"new-omitted-content")
    same_injection = _injection()
    same_injection["normalized_total_bytes"] += 600
    same_injection["retained_bytes"] += 500
    same_injection["pre_truncation_bytes"] += 600

    same_prepared_prompt = _roles(
        module,
        groups=groups,
        injection=same_injection,
    )["injected_dependencies"]
    changed_injection = deepcopy(same_injection)
    replacement_block = b"new-summary-framing"
    changed_injection["block_bytes"] = len(replacement_block)
    changed_injection["block_sha256"] = _sha_bytes(replacement_block)
    changed_summary = _roles(
        module,
        groups=groups,
        injection=changed_injection,
    )["injected_dependencies"]

    assert same_prepared_prompt == baseline
    assert changed_summary["sha256"] != baseline["sha256"]


def test_runtime_contributions_are_exact_nonempty_fixed_order_rows() -> None:
    module = _identity_module()
    role = _roles(module)["runtime_contributions"]

    assert [
        row["kind"] for row in role["payload"]["rows"]
    ] == [
        "consumed_artifacts",
        "output_positions",
        "structured_result",
    ]
    assert [row["composition_ordinal"] for row in role["payload"]["rows"]] == [
        0,
        1,
        2,
    ]
    for mutation in (
        list(reversed(_contributions())),
        _contributions()[1:],
        [*_contributions(), _contributions()[-1]],
    ):
        with pytest.raises(
            ValueError, match="prompt_attempt_identity_role_invalid"
        ):
            module.build_runtime_contributions_role(mutation)


def test_output_and_result_contributions_are_append_only() -> None:
    module = _identity_module()
    for index in (1, 2):
        rows = _contributions()
        rows[index]["position"] = "prepend"
        with pytest.raises(
            ValueError, match="prompt_attempt_identity_role_invalid"
        ):
            module.build_runtime_contributions_role(rows)


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


def _valid_v2(module=None) -> tuple[dict[str, Any], dict[str, Any]]:
    module = module or _identity_module()
    retained = _retained_v1()
    record = module.build_prompt_fragment_snapshot_v2(
        validated_retained_v1=retained,
        prompt_attempt_identity=_attempt_identity(module),
        compiler_fragment_identity_schema_version=COMPILED_V1,
    )
    return retained, _thaw(record)


def _reseal_v2_identity(record: dict[str, Any]) -> None:
    _reseal_identity(record["prompt_attempt_identity"])
    _record_seal(record)


@pytest.mark.parametrize(
    ("relation", "tamper"),
    (
        (
            "final prompt",
            lambda record: record["final_prompt"].__setitem__(
                "sha256", _sha_bytes(b"other-final")
            ),
        ),
        (
            "fragment identity",
            lambda record: record.__setitem__(
                "compiled_prompt_fragment_identity",
                _sha_bytes(b"other-fragment"),
            ),
        ),
        (
            "fragment identity version",
            lambda record: record["prompt_attempt_identity"]["roles"][
                "fragment_program"
            ]["payload"].__setitem__(
                "identity_schema_version",
                "compiled_prompt_fragment_identity.v2",
            ),
        ),
        (
            "document authored rows",
            lambda record: record["prompt_attempt_identity"]["roles"][
                "resolved_bindings"
            ]["payload"]["rows"][0].__setitem__(
                "value_sha256", _sha_bytes(b"other-relpath")
            ),
        ),
        (
            "canonical shown groups",
            lambda record: record["prompt_attempt_identity"]["roles"][
                "injected_dependencies"
            ]["payload"]["shown_groups"][0].__setitem__(
                "shown_sha256", _sha_bytes(b"other-shown")
            ),
        ),
        (
            "injection",
            lambda record: record["prompt_attempt_identity"]["roles"][
                "injected_dependencies"
            ]["payload"]["injection"].__setitem__(
                "block_sha256", _sha_bytes(b"other-block")
            ),
        ),
    ),
)
def test_v2_cross_field_validator_rejects_each_independently_resealed_mismatch(
    relation: str,
    tamper: Callable[[dict[str, Any]], None],
) -> None:
    module = _identity_module()
    retained, record = _valid_v2(module)
    tamper(record)
    if relation not in {"final prompt", "fragment identity"}:
        changed_role = {
            "fragment identity version": "fragment_program",
            "document authored rows": "resolved_bindings",
            "canonical shown groups": "injected_dependencies",
            "injection": "injected_dependencies",
        }[relation]
        _reseal_role(
            record["prompt_attempt_identity"]["roles"][changed_role]
        )
        _reseal_v2_identity(record)
    else:
        _record_seal(record)

    with pytest.raises(ValueError):
        module.validate_prompt_fragment_snapshot_v2_q3(
            record,
            validated_retained_v1=retained,
            compiler_fragment_identity_schema_version=COMPILED_V1,
        )


def test_v2_validator_rejects_resealed_retained_projection_disagreement() -> None:
    module = _identity_module()
    retained, record = _valid_v2(module)
    record["instruction"]["sha256"] = _sha_bytes(b"other-instruction")
    _record_seal(record)

    with pytest.raises(ValueError):
        module.validate_prompt_fragment_snapshot_v2_q3(
            record,
            validated_retained_v1=retained,
            compiler_fragment_identity_schema_version=COMPILED_V1,
        )


def test_v2_validator_rejects_role_composition_and_record_seal_tamper() -> None:
    module = _identity_module()
    retained, record = _valid_v2(module)

    role_tamper = deepcopy(record)
    role_tamper["prompt_attempt_identity"]["roles"][
        "provider_policy"
    ]["sha256"] = _sha_bytes(b"tampered-role-seal")
    _reseal_v2_identity(role_tamper)
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_role_invalid"
    ):
        module.validate_prompt_fragment_snapshot_v2_q3(
            role_tamper,
            validated_retained_v1=retained,
            compiler_fragment_identity_schema_version=COMPILED_V1,
        )

    composition_tamper = deepcopy(record)
    composition_tamper["prompt_attempt_identity"][
        "composition_sha256"
    ] = _sha_bytes(b"tampered-composition")
    _record_seal(composition_tamper)
    with pytest.raises(
        ValueError, match="prompt_attempt_identity_composition_invalid"
    ):
        module.validate_prompt_fragment_snapshot_v2_q3(
            composition_tamper,
            validated_retained_v1=retained,
            compiler_fragment_identity_schema_version=COMPILED_V1,
        )

    record_tamper = deepcopy(record)
    record_tamper["record_sha256"] = _sha_bytes(b"tampered-record")
    with pytest.raises(ValueError):
        module.validate_prompt_fragment_snapshot_v2_q3(
            record_tamper,
            validated_retained_v1=retained,
            compiler_fragment_identity_schema_version=COMPILED_V1,
        )


def test_v2_validator_is_pure_and_has_no_publication_dependency() -> None:
    module = _identity_module()
    source = Path(module.__file__).read_text(encoding="utf-8")

    assert "prompt_dependency_evidence" not in source
    assert "publish" not in source
    assert "open(" not in source


def _failure_fragment() -> dict[str, Any]:
    return {
        "identity_schema_version": COMPILED_V1,
        "compiled_prompt_fragment_identity": _sha_bytes(
            b"compiled-fragment"
        ),
        "prompt_attempt_identity_version": ATTEMPT_IDENTITY_VERSION,
        "binding_plan_sha256": _plan().plan_sha256,
    }


def _failure_record(module=None):
    module = module or _identity_module()
    scope = _scope()
    return module.build_prompt_fragment_preparation_failure(
        run=_run(scope),
        attempt=_attempt(scope, 1),
        fragment=_failure_fragment(),
    )


def test_preparation_failure_has_one_exact_closed_content_free_shape() -> None:
    module = _identity_module()
    record = _failure_record(module)

    assert tuple(record) == (
        "schema",
        "record_kind",
        "run",
        "attempt",
        "fragment",
        "failure",
        "provider_calls",
        "record_sha256",
    )
    assert record["schema"] == PREPARATION_FAILURE_SCHEMA
    assert record["record_kind"] == "failure"
    assert record["fragment"] == _failure_fragment()
    assert record["failure"] == {
        "category": "provider_policy_unresolved",
        "phase": "invocation_preparation",
    }
    assert record["provider_calls"] == {
        "preparation": True,
        "execution": False,
    }
    assert module.validate_prompt_fragment_preparation_failure(record) == (
        record
    )
    forbidden = {
        "error",
        "message",
        "parameters",
        "command",
        "argv",
        "environment",
        "provider_policy",
        "model",
        "effort",
        "timeout_sec",
        "input_mode",
    }
    assert forbidden.isdisjoint(_all_strings(record))


@pytest.mark.parametrize(
    "field",
    (
        "compiled_prompt_fragment_identity",
        "binding_plan_sha256",
    ),
)
def test_preparation_failure_can_require_exact_runtime_fragment_carriers(
    field: str,
) -> None:
    module = _identity_module()
    expected_fragment = _failure_fragment()
    candidate = _thaw(_failure_record(module))
    candidate["fragment"][field] = _sha_bytes(
        f"different-{field}".encode()
    )
    _record_seal(candidate)

    with pytest.raises(ValueError):
        module.validate_prompt_fragment_preparation_failure(
            candidate,
            expected_fragment=expected_fragment,
        )


@pytest.mark.parametrize(
    ("path", "replacement"),
    (
        (("schema",), PREPARATION_FAILURE_SCHEMA + ".other"),
        (("record_kind",), "prompt_snapshot"),
        (("run", "run_id"), "different-run"),
        (("run", "workflow_file"), "different.orc"),
        (("run", "workflow_checksum"), "SHA256:" + "0" * 64),
        (("attempt", "scope"), {}),
        (("attempt", "scope_sha256"), _sha_bytes(b"wrong-scope")),
        (("attempt", "step_key"), "0" * 24),
        (("attempt", "visit_key"), "0" * 24),
        (("attempt", "ordinal"), 0),
        (
            ("fragment", "identity_schema_version"),
            "compiled_prompt_fragment_identity.v9",
        ),
        (
            ("fragment", "compiled_prompt_fragment_identity"),
            "SHA256:" + "0" * 64,
        ),
        (
            ("fragment", "prompt_attempt_identity_version"),
            "workflow_prompt_attempt_identity.v9",
        ),
        (("fragment", "binding_plan_sha256"), None),
        (("failure", "category"), "unknown"),
        (("failure", "phase"), "provider_execution"),
        (("provider_calls", "preparation"), False),
        (("provider_calls", "execution"), True),
        (("record_sha256",), _sha_bytes(b"tampered-seal")),
    ),
)
def test_preparation_failure_rejects_every_tampered_field(
    path: tuple[Any, ...],
    replacement: Any,
) -> None:
    module = _identity_module()
    candidate = _thaw(_failure_record(module))
    _set_path(candidate, path, replacement)
    if path != ("record_sha256",):
        _record_seal(candidate)

    with pytest.raises(ValueError):
        module.validate_prompt_fragment_preparation_failure(candidate)


@pytest.mark.parametrize(
    ("owner", "forbidden_key"),
    (
        ("root", "error_message"),
        ("fragment", "parameters"),
        ("failure", "command"),
        ("provider_calls", "provider_policy"),
    ),
)
def test_preparation_failure_forbids_extra_or_missing_fields(
    owner: str,
    forbidden_key: str,
) -> None:
    module = _identity_module()
    candidate = _thaw(_failure_record(module))
    target = candidate if owner == "root" else candidate[owner]
    target[forbidden_key] = "forbidden"
    _record_seal(candidate)
    with pytest.raises(ValueError):
        module.validate_prompt_fragment_preparation_failure(candidate)

    candidate = _thaw(_failure_record(module))
    target = candidate if owner == "root" else candidate[owner]
    for missing in tuple(target):
        missing_candidate = _thaw(_failure_record(module))
        missing_target = (
            missing_candidate
            if owner == "root"
            else missing_candidate[owner]
        )
        missing_target.pop(missing)
        if not (owner == "root" and missing == "record_sha256"):
            _record_seal(missing_candidate)
        with pytest.raises(ValueError):
            module.validate_prompt_fragment_preparation_failure(
                missing_candidate
            )


def _comparison_record(
    module,
    *,
    ordinal: int,
    outcome: str = "v2_snapshot",
    identity: Any = None,
    scope: ProviderAttemptScope | None = None,
):
    if identity is None and outcome == "v2_snapshot":
        identity = _attempt_identity(module)
    return module.PromptComparisonRecord(
        scope=scope or _scope(),
        ordinal=ordinal,
        outcome=outcome,
        prompt_attempt_identity=identity,
    )


@pytest.mark.parametrize(
    ("role_key", "classification"),
    (
        ("fragment_program", "instruction_drift"),
        ("resolved_bindings", "input_drift"),
        ("injected_dependencies", "dependency_content_drift"),
        ("runtime_contributions", "runtime_prelude_drift"),
        ("provider_policy", "provider_policy_drift"),
    ),
)
def test_comparator_classifies_each_role_in_fixed_order(
    role_key: str,
    classification: str,
) -> None:
    module = _identity_module()
    baseline_roles = _roles(module)
    changed_roles = dict(baseline_roles)
    replacements = {
        "fragment_program": _roles(
            module,
            compiled_identity=_sha_bytes(b"new-program"),
        )["fragment_program"],
        "resolved_bindings": _roles(
            module,
            lexical_value="new-input",
        )["resolved_bindings"],
        "injected_dependencies": _roles(
            module,
            injection=_injection(block=b"new-dependency-block"),
        )["injected_dependencies"],
        "runtime_contributions": _roles(
            module,
            contributions=[
                {
                    **row,
                    "sha256": (
                        _sha_bytes(b"new-runtime")
                        if row["kind"] == "structured_result"
                        else row["sha256"]
                    ),
                }
                for row in _contributions()
            ],
        )["runtime_contributions"],
        "provider_policy": _roles(
            module,
            policy=_provider_policy(model="gpt-5.1"),
        )["provider_policy"],
    }
    changed_roles[role_key] = replacements[role_key]
    previous = _comparison_record(
        module,
        ordinal=1,
        identity=_attempt_identity(module, roles=baseline_roles),
    )
    current = _comparison_record(
        module,
        ordinal=2,
        identity=_attempt_identity(
            module,
            roles=changed_roles,
            final_prompt=b"changed-final",
        ),
    )

    result = module.compare_prompt_attempt_records(current, previous)
    assert result == {
        "status": "available",
        "previous_attempt_ordinal": 1,
        "classifications": (classification,),
        "reason": None,
    }


def test_comparator_emits_all_role_drift_in_fixed_order() -> None:
    module = _identity_module()
    previous = _comparison_record(module, ordinal=1)
    current = _comparison_record(
        module,
        ordinal=2,
        identity=_attempt_identity(
            module,
            roles=_roles(
                module,
                compiled_identity=_sha_bytes(b"new-program"),
                lexical_value="new-input",
                injection=_injection(block=b"new-dependency-block"),
                contributions=[
                    {
                        **row,
                        "sha256": _sha_bytes(
                            f"runtime-{index}".encode()
                        ),
                    }
                    for index, row in enumerate(_contributions())
                ],
                policy=_provider_policy(model="gpt-5.1"),
            ),
            final_prompt=b"all-changed",
        ),
    )

    assert module.compare_prompt_attempt_records(
        current, previous
    )["classifications"] == (
        "instruction_drift",
        "input_drift",
        "dependency_content_drift",
        "runtime_prelude_drift",
        "provider_policy_drift",
    )


def test_comparator_reports_unchanged_and_exact_attribution_controls() -> None:
    module = _identity_module()
    roles = _roles(module)
    previous = _comparison_record(
        module,
        ordinal=1,
        identity=_attempt_identity(module, roles=roles),
    )
    unchanged = _comparison_record(
        module,
        ordinal=2,
        identity=_attempt_identity(module, roles=roles),
    )
    template_only_roles = dict(roles)
    template_only_roles["fragment_program"] = _roles(
        module,
        compiled_identity=_sha_bytes(b"template-only"),
    )["fragment_program"]
    template_only = _comparison_record(
        module,
        ordinal=2,
        identity=_attempt_identity(
            module,
            roles=template_only_roles,
            final_prompt=b"template-changed-final",
        ),
    )
    input_only_roles = dict(roles)
    input_only_roles["resolved_bindings"] = _roles(
        module,
        lexical_value="binding-only",
    )["resolved_bindings"]
    input_only = _comparison_record(
        module,
        ordinal=2,
        identity=_attempt_identity(
            module,
            roles=input_only_roles,
            final_prompt=b"binding-changed-final",
        ),
    )

    assert module.compare_prompt_attempt_records(
        unchanged, previous
    )["classifications"] == ("prompt_context_unchanged",)
    assert module.compare_prompt_attempt_records(
        template_only, previous
    )["classifications"] == ("instruction_drift",)
    assert module.compare_prompt_attempt_records(
        input_only, previous
    )["classifications"] == ("input_drift",)


def test_equal_roles_with_unequal_final_prompt_is_only_composition_mismatch() -> None:
    module = _identity_module()
    roles = _roles(module)
    previous = _comparison_record(
        module,
        ordinal=1,
        identity=_attempt_identity(
            module, roles=roles, final_prompt=b"first-final"
        ),
    )
    current = _comparison_record(
        module,
        ordinal=2,
        identity=_attempt_identity(
            module, roles=roles, final_prompt=b"second-final"
        ),
    )

    assert module.compare_prompt_attempt_records(current, previous) == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": (),
        "reason": "prompt_identity_composition_mismatch",
    }


@pytest.mark.parametrize(
    ("current_outcome", "previous_outcome", "reason"),
    (
        ("invalid_snapshot", "v2_snapshot", "current_record_invalid"),
        ("missing_snapshot", "v2_snapshot", "current_record_invalid"),
        ("legacy_snapshot", "v2_snapshot", "legacy_snapshot_only"),
        (
            "preparation_failure",
            "v2_snapshot",
            "provider_policy_unresolved",
        ),
        ("failure", "v2_snapshot", "current_record_missing"),
        ("allocation_only", "v2_snapshot", "current_record_missing"),
        ("v2_snapshot", "invalid_snapshot", "previous_record_invalid"),
        ("v2_snapshot", "missing_snapshot", "previous_record_invalid"),
        ("v2_snapshot", "legacy_snapshot", "legacy_snapshot_only"),
    ),
)
def test_comparator_closed_unavailability_matrix(
    current_outcome: str,
    previous_outcome: str,
    reason: str,
) -> None:
    module = _identity_module()
    current = _comparison_record(
        module,
        ordinal=2,
        outcome=current_outcome,
    )
    previous = _comparison_record(
        module,
        ordinal=1,
        outcome=previous_outcome,
    )

    assert module.compare_prompt_attempt_records(current, previous) == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": (),
        "reason": reason,
    }


def test_history_comparator_covers_missing_current_and_no_predecessor() -> None:
    module = _identity_module()
    assert module.compare_prompt_attempt_history(None, ()) == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": (),
        "reason": "current_record_missing",
    }
    current = _comparison_record(module, ordinal=2)
    assert module.compare_prompt_attempt_history(current, ()) == {
        "status": "unavailable",
        "previous_attempt_ordinal": None,
        "classifications": (),
        "reason": "no_predecessor",
    }


@pytest.mark.parametrize(
    ("newer_outcome", "reason"),
    (
        ("legacy_snapshot", "legacy_snapshot_only"),
        ("invalid_snapshot", "previous_record_invalid"),
        ("missing_snapshot", "previous_record_invalid"),
    ),
)
def test_history_never_skips_newer_legacy_or_invalid_snapshot(
    newer_outcome: str,
    reason: str,
) -> None:
    module = _identity_module()
    current = _comparison_record(module, ordinal=4)
    older_valid = _comparison_record(module, ordinal=1)
    skipped_failure = _comparison_record(
        module, ordinal=2, outcome="failure"
    )
    newer = _comparison_record(
        module, ordinal=3, outcome=newer_outcome
    )

    result = module.compare_prompt_attempt_history(
        current,
        (newer, older_valid, skipped_failure),
    )
    assert result["reason"] == reason
    assert result["status"] == "unavailable"


def test_history_uses_greatest_ordinal_not_mapping_or_sequence_order() -> None:
    module = _identity_module()
    current = _comparison_record(module, ordinal=5)
    first = _comparison_record(module, ordinal=1)
    greatest = _comparison_record(module, ordinal=4)
    middle = _comparison_record(module, ordinal=3)

    result = module.compare_prompt_attempt_history(
        current, (greatest, first, middle)
    )
    assert result["status"] == "available"
    assert result["previous_attempt_ordinal"] == 4


def test_composition_tamper_is_record_invalid_not_cross_record_mismatch() -> None:
    module = _identity_module()
    valid = _attempt_identity(module)
    tampered = _thaw(valid)
    tampered["composition_sha256"] = _sha_bytes(b"tampered")

    invalid_current = _comparison_record(
        module,
        ordinal=2,
        identity=tampered,
    )
    valid_previous = _comparison_record(
        module,
        ordinal=1,
        identity=valid,
    )
    assert module.compare_prompt_attempt_records(
        invalid_current, valid_previous
    )["reason"] == "current_record_invalid"

    valid_current = _comparison_record(
        module,
        ordinal=2,
        identity=valid,
    )
    invalid_previous = _comparison_record(
        module,
        ordinal=1,
        identity=tampered,
    )
    assert module.compare_prompt_attempt_records(
        valid_current, invalid_previous
    )["reason"] == "previous_record_invalid"


def test_history_validates_current_composition_before_predecessor_selection() -> None:
    module = _identity_module()
    tampered = _thaw(_attempt_identity(module))
    tampered["composition_sha256"] = _sha_bytes(b"tampered")
    current = _comparison_record(
        module,
        ordinal=2,
        identity=tampered,
    )

    assert module.compare_prompt_attempt_history(current, ())["reason"] == (
        "current_record_invalid"
    )


def test_comparator_requires_same_scope_and_strictly_increasing_ordinal() -> None:
    module = _identity_module()
    scope = _scope()
    other_scope = _scope(run_id="20260727T000001Z-other")
    valid_previous = _comparison_record(
        module, ordinal=1, scope=scope
    )
    valid_current = _comparison_record(
        module, ordinal=2, scope=scope
    )
    assert module.compare_prompt_attempt_records(
        valid_current, valid_previous
    )["status"] == "available"

    for current, previous in (
        (
            _comparison_record(module, ordinal=2, scope=other_scope),
            valid_previous,
        ),
        (
            _comparison_record(module, ordinal=1, scope=scope),
            valid_previous,
        ),
        (
            _comparison_record(module, ordinal=1, scope=scope),
            _comparison_record(module, ordinal=2, scope=scope),
        ),
    ):
        with pytest.raises(ValueError, match="scope or ordinal"):
            module.compare_prompt_attempt_records(current, previous)


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
