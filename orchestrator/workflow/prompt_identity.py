"""Pure, content-free identity for prepared fragment prompt attempts."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .prompt_fragment_contract import (
    COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_SCHEMA,
    CompilerPromptAttemptBindingPlan,
    serialize_compiler_prompt_attempt_binding_plan_row,
    validate_compiler_prompt_attempt_binding_plan,
)
from .prompting import (
    PromptFragmentRenderResult,
    prompt_fragment_transport_value_sha256,
    validate_prompt_fragment_render_trace,
)
from .provider_attempts import ProviderAttemptScope


PROMPT_ATTEMPT_IDENTITY_VERSION = "workflow_prompt_attempt_identity.v1"
PROMPT_ATTEMPT_COMPOSITION_SCHEMA = (
    "workflow_prompt_attempt_composition.v1"
)
PROMPT_FRAGMENT_SNAPSHOT_V1_SCHEMA = (
    "workflow_prompt_fragment_snapshot.functional.v1"
)
PROMPT_FRAGMENT_SNAPSHOT_V2_SCHEMA = (
    "workflow_prompt_fragment_snapshot.functional.v2"
)
PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA = (
    "workflow_prompt_fragment_preparation_failure.functional.v1"
)
ROLE_ORDER = (
    "fragment_program",
    "resolved_bindings",
    "injected_dependencies",
    "runtime_contributions",
    "provider_policy",
)
ROLE_SCHEMAS = MappingProxyType(
    {
        "fragment_program": (
            "workflow_prompt_attempt_fragment_program.v1"
        ),
        "resolved_bindings": (
            "workflow_prompt_attempt_resolved_bindings.v1"
        ),
        "injected_dependencies": (
            "workflow_prompt_attempt_injected_dependencies.v1"
        ),
        "runtime_contributions": (
            "workflow_prompt_attempt_runtime_contributions.v1"
        ),
        "provider_policy": (
            "workflow_prompt_attempt_provider_policy.v1"
        ),
    }
)
ROLE_CLASSIFICATIONS = MappingProxyType(
    {
        "fragment_program": "instruction_drift",
        "resolved_bindings": "input_drift",
        "injected_dependencies": "dependency_content_drift",
        "runtime_contributions": "runtime_prelude_drift",
        "provider_policy": "provider_policy_drift",
    }
)

_COMPILED_FRAGMENT_IDENTITY_SCHEMAS = {
    "compiled_prompt_fragment_identity.v1",
    "compiled_prompt_fragment_identity.v2",
}
_Q1_SLOT_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_SLOT_KINDS = {"doc", "text", "value", "path"}
_OUTPUT_ROLES = {"none", "required_string_file"}
_RENDERERS_BY_KIND = {
    "text": "raw-utf8-string",
    "value": "canonical-json",
    "path": "posix-path-line",
}
_CONTRIBUTION_KINDS = (
    "consumed_artifacts",
    "output_positions",
    "structured_result",
)
_COMPARISON_OUTCOMES = {
    "v2_snapshot",
    "legacy_snapshot",
    "invalid_snapshot",
    "missing_snapshot",
    "preparation_failure",
    "failure",
    "allocation_only",
}
_SNAPSHOT_OUTCOMES = {
    "v2_snapshot",
    "legacy_snapshot",
    "invalid_snapshot",
    "missing_snapshot",
}
_UNAVAILABLE_REASONS = {
    "no_predecessor",
    "current_record_missing",
    "current_record_invalid",
    "previous_record_invalid",
    "legacy_snapshot_only",
    "provider_policy_unresolved",
    "prompt_identity_composition_mismatch",
}
_V1_FRAGMENT_KEYS = {
    "schema",
    "record_kind",
    "run",
    "compiler_contract",
    "attempt",
    "authored_rows",
    "canonical_groups",
    "instruction",
    "injection",
    "final_prompt",
    "compiled_prompt_fragment_identity",
    "record_sha256",
}
_V2_FRAGMENT_KEYS = _V1_FRAGMENT_KEYS | {"prompt_attempt_identity"}


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return {
            key: _thaw_json(item)
            for key, item in value.items()
        }
    if isinstance(value, (tuple, list)):
        return [_thaw_json(item) for item in value]
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("value must contain JSON literals only")


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("JSON object keys must be strings")
        return MappingProxyType(
            {
                key: _freeze_json(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (tuple, list)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise TypeError("value must contain JSON literals only")


def canonical_json_bytes(value: Any) -> bytes:
    """Return canonical UTF-8 JSON with no trailing newline."""

    return json.dumps(
        _thaw_json(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    """Return the lower-case SHA-256 identity of canonical JSON."""

    return "sha256:" + hashlib.sha256(
        canonical_json_bytes(value)
    ).hexdigest()


def _bytes_sha256(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _is_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 71
        and value.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in value[7:])
    )


def _closed(
    value: Any,
    keys: set[str],
    *,
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != keys:
        raise ValueError(f"{context} must be a closed object")
    return value


def _integer(
    value: Any,
    *,
    context: str,
    minimum: int = 0,
) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(
            f"{context} must be an integer >= {minimum}"
        )
    return value


def _nonempty_string(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context} must be a non-empty string")
    return value


def _require_sha256(value: Any, *, context: str) -> str:
    if not _is_sha256(value):
        raise ValueError(f"{context} must be a canonical sha256")
    return value


def _role_invalid(message: str) -> ValueError:
    return ValueError(f"prompt_attempt_identity_role_invalid: {message}")


def _role_closed(
    value: Any,
    keys: set[str],
    *,
    context: str,
) -> Mapping[str, Any]:
    try:
        return _closed(value, keys, context=context)
    except ValueError as exc:
        raise _role_invalid(str(exc)) from exc


def _role_integer(
    value: Any,
    *,
    context: str,
    minimum: int = 0,
) -> int:
    try:
        return _integer(value, context=context, minimum=minimum)
    except ValueError as exc:
        raise _role_invalid(str(exc)) from exc


def _role_string(value: Any, *, context: str) -> str:
    try:
        return _nonempty_string(value, context=context)
    except ValueError as exc:
        raise _role_invalid(str(exc)) from exc


def _role_slot_name(value: Any, *, context: str) -> str:
    name = _role_string(value, context=context)
    if not _Q1_SLOT_NAME_RE.fullmatch(name):
        raise _role_invalid(f"{context} is invalid")
    return name


def _role_sha(value: Any, *, context: str) -> str:
    try:
        return _require_sha256(value, context=context)
    except ValueError as exc:
        raise _role_invalid(str(exc)) from exc


def _is_absolute_path_text(value: str) -> bool:
    return (
        value.startswith(("/", "\\\\"))
        or (
            len(value) >= 3
            and value[0].isalpha()
            and value[1] == ":"
            and value[2] in {"/", "\\"}
        )
    )


def _validate_refinement_paths(value: Any) -> None:
    if isinstance(value, Mapping):
        if (
            value.get("kind") == "path"
            and isinstance(value.get("under"), str)
            and _is_absolute_path_text(value["under"])
        ):
            raise _role_invalid(
                "path refinement must not contain an absolute root"
            )
        for item in value.values():
            _validate_refinement_paths(item)
    elif isinstance(value, (tuple, list)):
        for item in value:
            _validate_refinement_paths(item)


def _validate_normalized_refinement(
    value: Any,
    *,
    context: str,
) -> None:
    if not isinstance(value, Mapping):
        raise _role_invalid(f"{context} is invalid")
    from orchestrator.workflow_lisp.lowering.pure_projection import (
        validate_compiler_normalized_type_descriptor,
    )

    try:
        validate_compiler_normalized_type_descriptor(
            value,
            context=context,
        )
    except (TypeError, ValueError) as exc:
        raise _role_invalid(f"{context} is invalid") from exc
    _validate_refinement_paths(value)


def _validate_fragment_program_payload(
    value: Any,
) -> Mapping[str, Any]:
    payload = _role_closed(
        value,
        {
            "identity_schema_version",
            "compiled_prompt_fragment_identity",
        },
        context="fragment-program payload",
    )
    if (
        payload["identity_schema_version"]
        not in _COMPILED_FRAGMENT_IDENTITY_SCHEMAS
    ):
        raise _role_invalid(
            "fragment identity schema version is invalid"
        )
    _role_sha(
        payload["compiled_prompt_fragment_identity"],
        context="compiled prompt fragment identity",
    )
    return payload


def _validate_renderer(
    value: Any,
    *,
    slot_kind: str,
) -> Mapping[str, Any] | None:
    if slot_kind == "doc":
        if value is not None:
            raise _role_invalid("document renderer must be null")
        return None
    renderer = _role_closed(
        value,
        {"renderer_id", "renderer_version"},
        context="resolved binding renderer",
    )
    if (
        renderer["renderer_id"] != _RENDERERS_BY_KIND[slot_kind]
        or type(renderer["renderer_version"]) is not int
        or renderer["renderer_version"] != 1
    ):
        raise _role_invalid("resolved binding renderer is invalid")
    return renderer


def _validate_resolved_binding_row(
    value: Any,
) -> Mapping[str, Any]:
    row = _role_closed(
        value,
        {
            "slot_name",
            "slot_kind",
            "refinement",
            "output_role",
            "delivery",
            "renderer",
            "value_sha256",
            "rendered_bytes_sha256",
        },
        context="resolved binding row",
    )
    _role_slot_name(
        row["slot_name"],
        context="resolved binding slot name",
    )
    slot_kind = row["slot_kind"]
    if slot_kind not in _SLOT_KINDS:
        raise _role_invalid("resolved binding slot kind is invalid")
    refinement = row["refinement"]
    if refinement is not None:
        _validate_normalized_refinement(
            refinement,
            context="resolved binding refinement",
        )
    if slot_kind == "text" and refinement is not None:
        raise _role_invalid("text refinement must be null")
    if (
        slot_kind in {"doc", "path"}
        and refinement is not None
        and refinement.get("kind") != "path"
    ):
        raise _role_invalid(
            "document and path refinements must be path descriptors"
        )
    output_role = row["output_role"]
    if output_role not in _OUTPUT_ROLES:
        raise _role_invalid("resolved binding output role is invalid")
    if output_role == "required_string_file" and slot_kind != "path":
        raise _role_invalid(
            "required output role requires a path slot"
        )
    expected_delivery = (
        "dependency" if slot_kind == "doc" else "template"
    )
    if row["delivery"] != expected_delivery:
        raise _role_invalid("resolved binding delivery is invalid")
    _validate_renderer(row["renderer"], slot_kind=slot_kind)
    _role_sha(row["value_sha256"], context="resolved value identity")
    rendered_identity = row["rendered_bytes_sha256"]
    if slot_kind == "doc":
        if rendered_identity is not None:
            raise _role_invalid(
                "document rendered-byte identity must be null"
            )
    else:
        _role_sha(
            rendered_identity,
            context="rendered substitution identity",
        )
    return row


def _validate_resolved_bindings_payload(
    value: Any,
) -> Mapping[str, Any]:
    payload = _role_closed(
        value,
        {"binding_plan_sha256", "rows"},
        context="resolved-bindings payload",
    )
    _role_sha(
        payload["binding_plan_sha256"],
        context="binding plan identity",
    )
    rows = payload["rows"]
    if not isinstance(rows, (tuple, list)):
        raise _role_invalid("resolved binding rows must be an array")
    names: list[str] = []
    for raw_row in rows:
        row = _validate_resolved_binding_row(raw_row)
        names.append(row["slot_name"])
    if len(names) != len(set(names)):
        raise _role_invalid("resolved binding slot names must be unique")
    return payload


def _validate_dependency_group(value: Any) -> Mapping[str, Any]:
    group = _role_closed(
        value,
        {
            "order",
            "authored_row_ids",
            "render_status",
            "shown_bytes",
            "shown_sha256",
        },
        context="shown dependency group",
    )
    _role_integer(group["order"], context="shown dependency order")
    row_ids = group["authored_row_ids"]
    if (
        not isinstance(row_ids, (tuple, list))
        or not row_ids
    ):
        raise _role_invalid(
            "shown dependency authored row identities are invalid"
        )
    for row_id in row_ids:
        _role_sha(row_id, context="shown dependency authored row identity")
    status = group["render_status"]
    if status not in {"complete", "truncated"}:
        raise _role_invalid("shown dependency status is invalid")
    shown_bytes = _role_integer(
        group["shown_bytes"],
        context="shown dependency bytes",
    )
    if status == "truncated" and shown_bytes == 0:
        raise _role_invalid(
            "truncated dependency must contain shown bytes"
        )
    _role_sha(group["shown_sha256"], context="shown dependency identity")
    return group


def _validate_injected_dependencies_payload(
    value: Any,
) -> Mapping[str, Any]:
    payload = _role_closed(
        value,
        {"shown_groups", "injection"},
        context="injected-dependencies payload",
    )
    groups = payload["shown_groups"]
    if not isinstance(groups, (tuple, list)):
        raise _role_invalid("shown dependency groups must be an array")
    phase = "complete"
    seen_row_ids: set[str] = set()
    for index, raw_group in enumerate(groups):
        group = _validate_dependency_group(raw_group)
        if group["order"] != index:
            raise _role_invalid(
                "shown dependency order must be contiguous"
            )
        if group["render_status"] == "complete":
            if phase != "complete":
                raise _role_invalid(
                    "shown dependency statuses are out of order"
                )
        elif phase == "truncated":
            raise _role_invalid(
                "shown dependencies contain multiple truncations"
            )
        else:
            phase = "truncated"
        row_ids = tuple(group["authored_row_ids"])
        if any(row_id in seen_row_ids for row_id in row_ids):
            raise _role_invalid(
                "shown dependency authored row membership is duplicated"
            )
        seen_row_ids.update(row_ids)
    injection = _role_closed(
        payload["injection"],
        {"position", "block_bytes", "block_sha256"},
        context="dependency injection",
    )
    if injection["position"] not in {"prepend", "append"}:
        raise _role_invalid("dependency injection position is invalid")
    _role_integer(
        injection["block_bytes"],
        context="dependency injection bytes",
    )
    _role_sha(
        injection["block_sha256"],
        context="dependency injection identity",
    )
    return payload


def _validate_runtime_contribution_row(
    value: Any,
) -> Mapping[str, Any]:
    row = _role_closed(
        value,
        {
            "composition_ordinal",
            "kind",
            "position",
            "bytes",
            "sha256",
        },
        context="runtime contribution row",
    )
    _role_integer(
        row["composition_ordinal"],
        context="runtime contribution ordinal",
    )
    if row["kind"] not in _CONTRIBUTION_KINDS:
        raise _role_invalid("runtime contribution kind is invalid")
    if row["position"] not in {"prepend", "append"}:
        raise _role_invalid("runtime contribution position is invalid")
    if (
        row["kind"] in {"output_positions", "structured_result"}
        and row["position"] != "append"
    ):
        raise _role_invalid(
            "runtime suffix contribution must be appended"
        )
    _role_integer(
        row["bytes"],
        context="runtime contribution bytes",
        minimum=1,
    )
    _role_sha(row["sha256"], context="runtime contribution identity")
    return row


def _validate_runtime_contributions_payload(
    value: Any,
) -> Mapping[str, Any]:
    payload = _role_closed(
        value,
        {"rows"},
        context="runtime-contributions payload",
    )
    rows = payload["rows"]
    if not isinstance(rows, (tuple, list)):
        raise _role_invalid("runtime contribution rows must be an array")
    kinds: list[str] = []
    for index, raw_row in enumerate(rows):
        row = _validate_runtime_contribution_row(raw_row)
        if row["composition_ordinal"] != index:
            raise _role_invalid(
                "runtime contribution ordinals must be contiguous"
            )
        kinds.append(row["kind"])
    kind_ordinals = [_CONTRIBUTION_KINDS.index(kind) for kind in kinds]
    if kind_ordinals != sorted(set(kind_ordinals)):
        raise _role_invalid(
            "runtime contribution kinds are duplicated or out of order"
        )
    return payload


def _validate_provider_policy_payload(
    value: Any,
) -> Mapping[str, Any]:
    payload = _role_closed(
        value,
        {
            "provider_name",
            "model",
            "effort",
            "timeout_sec",
            "input_mode",
        },
        context="provider-policy payload",
    )
    provider_name = _role_string(
        payload["provider_name"],
        context="provider name",
    )
    if _is_absolute_path_text(provider_name):
        raise _role_invalid(
            "provider policy must not contain absolute paths"
        )
    for key in ("model", "effort"):
        if payload[key] is not None:
            value = _role_string(
                payload[key],
                context=f"provider {key}",
            )
            if _is_absolute_path_text(value):
                raise _role_invalid(
                    "provider policy must not contain absolute paths"
                )
    if payload["timeout_sec"] is not None:
        _role_integer(
            payload["timeout_sec"],
            context="provider timeout",
            minimum=1,
        )
    if payload["input_mode"] not in {"argv", "stdin"}:
        raise _role_invalid("provider input mode is invalid")
    return payload


_ROLE_PAYLOAD_VALIDATORS = {
    "fragment_program": _validate_fragment_program_payload,
    "resolved_bindings": _validate_resolved_bindings_payload,
    "injected_dependencies": _validate_injected_dependencies_payload,
    "runtime_contributions": _validate_runtime_contributions_payload,
    "provider_policy": _validate_provider_policy_payload,
}


def validate_prompt_identity_role(
    role_key: str,
    value: Any,
) -> Mapping[str, Any]:
    """Validate and freeze one exact role wrapper."""

    if role_key not in ROLE_SCHEMAS:
        raise _role_invalid("role key is invalid")
    wrapper = _role_closed(
        value,
        {"schema_version", "payload", "sha256"},
        context=f"{role_key} role",
    )
    if wrapper["schema_version"] != ROLE_SCHEMAS[role_key]:
        raise _role_invalid(f"{role_key} schema version is invalid")
    payload = _ROLE_PAYLOAD_VALIDATORS[role_key](wrapper["payload"])
    claimed = wrapper["sha256"]
    _role_sha(claimed, context=f"{role_key} identity")
    if claimed != canonical_sha256(payload):
        raise _role_invalid(f"{role_key} identity does not match payload")
    return _freeze_json(
        {
            "schema_version": wrapper["schema_version"],
            "payload": payload,
            "sha256": claimed,
        }
    )


def _build_role(
    role_key: str,
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    wrapper = {
        "schema_version": ROLE_SCHEMAS[role_key],
        "payload": _thaw_json(payload),
        "sha256": canonical_sha256(payload),
    }
    return validate_prompt_identity_role(role_key, wrapper)


def build_fragment_program_role(
    *,
    identity_schema_version: str,
    compiled_prompt_fragment_identity: str,
) -> Mapping[str, Any]:
    """Build Role 1 from the unchanged compiler fragment identity."""

    return _build_role(
        "fragment_program",
        {
            "identity_schema_version": identity_schema_version,
            "compiled_prompt_fragment_identity": (
                compiled_prompt_fragment_identity
            ),
        },
    )


def build_resolved_bindings_role(
    *,
    binding_plan: CompilerPromptAttemptBindingPlan,
    fragment_render_result: PromptFragmentRenderResult,
    authored_rows: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Build Role 2 by walking one validated declaration-order plan."""

    plan = validate_compiler_prompt_attempt_binding_plan(binding_plan)
    trace = validate_prompt_fragment_render_trace(
        fragment_render_result,
        compiler_prompt_attempt_binding_plan=plan,
    )
    if not isinstance(authored_rows, (tuple, list)):
        raise _role_invalid("authored dependency rows must be an array")
    resolved_rows: list[dict[str, Any]] = []
    for owner_plan_row in plan.rows:
        plan_row = serialize_compiler_prompt_attempt_binding_plan_row(
            owner_plan_row
        )
        source = plan_row["runtime_source"]
        kind = plan_row["slot_kind"]
        if kind == "doc":
            source_ordinal = source["ordinal"]
            if source_ordinal >= len(authored_rows):
                raise _role_invalid(
                    "document locator is outside authored rows"
                )
            authored_row = authored_rows[source_ordinal]
            if not isinstance(authored_row, Mapping):
                raise _role_invalid("authored dependency row is invalid")
            evaluated_relpath = authored_row.get("evaluated_relpath")
            _role_string(
                evaluated_relpath,
                context="document evaluated relpath",
            )
            value_sha256 = prompt_fragment_transport_value_sha256(
                evaluated_relpath
            )
            rendered_bytes_sha256 = None
        else:
            source_ordinal = source["ordinal"]
            if source_ordinal >= len(trace):
                raise _role_invalid(
                    "rendered locator is outside fragment trace"
                )
            trace_row = trace[source_ordinal]
            if (
                trace_row.slot_name != plan_row["slot_name"]
                or trace_row.renderer != plan_row["renderer"]
            ):
                raise _role_invalid(
                    "fragment trace disagrees with binding plan"
                )
            value_sha256 = trace_row.value_sha256
            rendered_bytes_sha256 = (
                trace_row.substitution_bytes_sha256
            )
        resolved_rows.append(
            {
                "slot_name": plan_row["slot_name"],
                "slot_kind": kind,
                "refinement": _thaw_json(plan_row["refinement"]),
                "output_role": plan_row["output_role"],
                "delivery": plan_row["delivery"],
                "renderer": _thaw_json(plan_row["renderer"]),
                "value_sha256": value_sha256,
                "rendered_bytes_sha256": rendered_bytes_sha256,
            }
        )
    return _build_role(
        "resolved_bindings",
        {
            "binding_plan_sha256": plan.plan_sha256,
            "rows": resolved_rows,
        },
    )


def build_injected_dependencies_role(
    *,
    canonical_groups: Sequence[Mapping[str, Any]],
    injection: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Build Role 3 from shown group metadata and the prepared block."""

    if not isinstance(canonical_groups, (tuple, list)):
        raise _role_invalid("canonical dependency groups must be an array")
    shown_groups: list[dict[str, Any]] = []
    phase = "complete"
    for order, group in enumerate(canonical_groups):
        if not isinstance(group, Mapping):
            raise _role_invalid("canonical dependency group is invalid")
        required = {
            "order",
            "authored_row_ids",
            "render_status",
            "shown_bytes",
            "shown_sha256",
        }
        if not required.issubset(group):
            raise _role_invalid(
                "canonical dependency group projection is incomplete"
            )
        if group["order"] != order:
            raise _role_invalid(
                "canonical dependency group order is invalid"
            )
        status = group["render_status"]
        if status not in {"complete", "truncated", "omitted"}:
            raise _role_invalid(
                "canonical dependency render status is invalid"
            )
        if status == "complete" and phase != "complete":
            raise _role_invalid(
                "canonical dependency statuses are out of order"
            )
        if status == "truncated":
            if phase != "complete":
                raise _role_invalid(
                    "canonical dependency truncation is duplicated"
                )
            phase = "truncated"
        if status == "omitted":
            phase = "omitted"
        shown_bytes = _role_integer(
            group["shown_bytes"],
            context="canonical dependency shown bytes",
        )
        if status == "omitted":
            if shown_bytes != 0 or group["shown_sha256"] is not None:
                raise _role_invalid(
                    "omitted dependency has shown content"
                )
            continue
        if status == "truncated" and shown_bytes == 0:
            raise _role_invalid(
                "truncated dependency has no shown content"
            )
        _role_sha(
            group["shown_sha256"],
            context="canonical dependency shown identity",
        )
        row_ids = group["authored_row_ids"]
        if not isinstance(row_ids, (tuple, list)) or not row_ids:
            raise _role_invalid(
                "canonical dependency authored rows are invalid"
            )
        for row_id in row_ids:
            _role_sha(
                row_id,
                context="canonical dependency authored row identity",
            )
        shown_groups.append(
            {
                "order": order,
                "authored_row_ids": list(row_ids),
                "render_status": status,
                "shown_bytes": shown_bytes,
                "shown_sha256": group["shown_sha256"],
            }
        )
    if not isinstance(injection, Mapping):
        raise _role_invalid("dependency injection projection is invalid")
    required_injection = {"position", "block_bytes", "block_sha256"}
    if not required_injection.issubset(injection):
        raise _role_invalid(
            "dependency injection projection is incomplete"
        )
    return _build_role(
        "injected_dependencies",
        {
            "shown_groups": shown_groups,
            "injection": {
                "position": injection["position"],
                "block_bytes": injection["block_bytes"],
                "block_sha256": injection["block_sha256"],
            },
        },
    )


def build_runtime_contributions_role(
    contributions: Sequence[Mapping[str, Any]],
) -> Mapping[str, Any]:
    """Build Role 4 from exact non-empty composition segments."""

    if not isinstance(contributions, (tuple, list)):
        raise _role_invalid("runtime contributions must be an array")
    rows = [_thaw_json(row) for row in contributions]
    return _build_role(
        "runtime_contributions",
        {"rows": rows},
    )


def build_provider_policy_role(
    policy: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Build Role 5 from the resolved closed invocation policy."""

    if not isinstance(policy, Mapping):
        raise _role_invalid("provider policy must be an object")
    return _build_role("provider_policy", _thaw_json(policy))


def _validate_final_prompt(value: Any) -> Mapping[str, Any]:
    final_prompt = _closed(
        value,
        {"bytes", "sha256"},
        context="final prompt",
    )
    _integer(
        final_prompt["bytes"],
        context="final prompt bytes",
    )
    _require_sha256(
        final_prompt["sha256"],
        context="final prompt identity",
    )
    return final_prompt


def _composition_projection(
    roles: Mapping[str, Mapping[str, Any]],
    final_prompt: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": PROMPT_ATTEMPT_COMPOSITION_SCHEMA,
        "role_sha256": {
            role_key: roles[role_key]["sha256"]
            for role_key in ROLE_ORDER
        },
        "final_prompt": _thaw_json(final_prompt),
    }


def build_prompt_attempt_identity(
    *,
    roles: Mapping[str, Mapping[str, Any]],
    final_prompt: bytes,
) -> Mapping[str, Any]:
    """Build the closed five-role identity for exact prepared bytes."""

    if type(final_prompt) is not bytes:
        raise TypeError("final_prompt must be exact bytes")
    if not isinstance(roles, Mapping) or set(roles) != set(ROLE_ORDER):
        raise _role_invalid("identity roles are incomplete or open")
    validated_roles = {
        role_key: validate_prompt_identity_role(
            role_key, roles[role_key]
        )
        for role_key in ROLE_ORDER
    }
    final_projection = {
        "bytes": len(final_prompt),
        "sha256": _bytes_sha256(final_prompt),
    }
    identity = {
        "schema_version": PROMPT_ATTEMPT_IDENTITY_VERSION,
        "roles": validated_roles,
        "final_prompt": final_projection,
        "composition_sha256": canonical_sha256(
            _composition_projection(validated_roles, final_projection)
        ),
    }
    return validate_prompt_attempt_identity(identity)


def validate_prompt_attempt_identity(
    value: Any,
) -> Mapping[str, Any]:
    """Validate and freeze one closed attempt identity."""

    identity = _closed(
        value,
        {
            "schema_version",
            "roles",
            "final_prompt",
            "composition_sha256",
        },
        context="prompt attempt identity",
    )
    if identity["schema_version"] != PROMPT_ATTEMPT_IDENTITY_VERSION:
        raise _role_invalid("attempt identity schema version is invalid")
    roles = identity["roles"]
    if not isinstance(roles, Mapping) or set(roles) != set(ROLE_ORDER):
        raise _role_invalid("attempt identity roles are incomplete or open")
    validated_roles = {
        role_key: validate_prompt_identity_role(
            role_key, roles[role_key]
        )
        for role_key in ROLE_ORDER
    }
    final_prompt = _validate_final_prompt(identity["final_prompt"])
    claimed = identity["composition_sha256"]
    if (
        not _is_sha256(claimed)
        or claimed
        != canonical_sha256(
            _composition_projection(validated_roles, final_prompt)
        )
    ):
        raise ValueError(
            "prompt_attempt_identity_composition_invalid: "
            "composition identity does not match"
        )
    return _freeze_json(
        {
            "schema_version": identity["schema_version"],
            "roles": validated_roles,
            "final_prompt": final_prompt,
            "composition_sha256": claimed,
        }
    )


def _record_sha256(record: Mapping[str, Any]) -> str:
    body = _thaw_json(record)
    body.pop("record_sha256", None)
    return canonical_sha256(body)


def build_prompt_fragment_snapshot_v2(
    *,
    validated_retained_v1: Mapping[str, Any],
    prompt_attempt_identity: Mapping[str, Any],
    compiler_fragment_identity_schema_version: str,
) -> Mapping[str, Any]:
    """Add Q3 identity to an already validated retained-v1 projection."""

    retained = _closed(
        validated_retained_v1,
        _V1_FRAGMENT_KEYS,
        context="validated retained-v1 projection",
    )
    record = _thaw_json(retained)
    record["schema"] = PROMPT_FRAGMENT_SNAPSHOT_V2_SCHEMA
    record["prompt_attempt_identity"] = _thaw_json(
        prompt_attempt_identity
    )
    record["record_sha256"] = _record_sha256(record)
    return validate_prompt_fragment_snapshot_v2_q3(
        record,
        validated_retained_v1=validated_retained_v1,
        compiler_fragment_identity_schema_version=(
            compiler_fragment_identity_schema_version
        ),
    )


def validate_prompt_fragment_snapshot_v2_q3(
    value: Any,
    *,
    validated_retained_v1: Mapping[str, Any],
    compiler_fragment_identity_schema_version: str,
) -> Mapping[str, Any]:
    """Apply Q3 checks after the caller validates the retained-v1 record."""

    record = _closed(
        value,
        _V2_FRAGMENT_KEYS,
        context="prompt fragment v2 snapshot",
    )
    retained = _closed(
        validated_retained_v1,
        _V1_FRAGMENT_KEYS,
        context="validated retained-v1 projection",
    )
    if (
        record["schema"] != PROMPT_FRAGMENT_SNAPSHOT_V2_SCHEMA
        or retained["schema"] != PROMPT_FRAGMENT_SNAPSHOT_V1_SCHEMA
        or record["record_kind"] != "prompt_snapshot"
        or retained["record_kind"] != "prompt_snapshot"
    ):
        raise ValueError("prompt fragment snapshot schema is invalid")
    if (
        compiler_fragment_identity_schema_version
        not in _COMPILED_FRAGMENT_IDENTITY_SCHEMAS
    ):
        raise _role_invalid(
            "paired compiler fragment identity schema is invalid"
        )
    retained_keys = _V1_FRAGMENT_KEYS - {"schema", "record_sha256"}
    for key in retained_keys:
        if _thaw_json(record[key]) != _thaw_json(retained[key]):
            raise ValueError(
                f"prompt fragment retained-v1 field {key} disagrees"
            )
    if (
        not _is_sha256(record["record_sha256"])
        or record["record_sha256"] != _record_sha256(record)
    ):
        raise ValueError("prompt fragment v2 record identity is invalid")
    identity = validate_prompt_attempt_identity(
        record["prompt_attempt_identity"]
    )
    if _thaw_json(identity["final_prompt"]) != _thaw_json(
        record["final_prompt"]
    ):
        raise ValueError(
            "prompt_attempt_identity_final_prompt_mismatch: "
            "identity and retained final prompt disagree"
        )
    fragment_payload = identity["roles"]["fragment_program"]["payload"]
    if (
        fragment_payload["compiled_prompt_fragment_identity"]
        != record["compiled_prompt_fragment_identity"]
        or fragment_payload["identity_schema_version"]
        != compiler_fragment_identity_schema_version
    ):
        raise _role_invalid(
            "fragment program disagrees with retained authority"
        )
    resolved_rows = identity["roles"]["resolved_bindings"]["payload"][
        "rows"
    ]
    document_rows = [
        row for row in resolved_rows if row["slot_kind"] == "doc"
    ]
    authored_rows = record["authored_rows"]
    if (
        not isinstance(authored_rows, (tuple, list))
        or len(document_rows) != len(authored_rows)
    ):
        raise _role_invalid(
            "document bindings disagree with authored dependency rows"
        )
    for document_row, authored_row in zip(
        document_rows, authored_rows, strict=True
    ):
        if not isinstance(authored_row, Mapping):
            raise _role_invalid("retained authored dependency row is invalid")
        evaluated_relpath = authored_row.get("evaluated_relpath")
        _role_string(
            evaluated_relpath,
            context="retained evaluated relpath",
        )
        if (
            document_row["value_sha256"]
            != prompt_fragment_transport_value_sha256(evaluated_relpath)
            or document_row["renderer"] is not None
            or document_row["rendered_bytes_sha256"] is not None
        ):
            raise _role_invalid(
                "document binding disagrees with retained authored row"
            )
    expected_dependency_role = build_injected_dependencies_role(
        canonical_groups=record["canonical_groups"],
        injection=record["injection"],
    )
    if (
        _thaw_json(identity["roles"]["injected_dependencies"])
        != _thaw_json(expected_dependency_role)
    ):
        raise _role_invalid(
            "dependency role disagrees with retained injection"
        )
    return _freeze_json(record)


def _validate_run_and_attempt(
    run_value: Any,
    attempt_value: Any,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    run = _closed(
        run_value,
        {"run_id", "workflow_file", "workflow_checksum"},
        context="preparation failure run",
    )
    attempt = _closed(
        attempt_value,
        {
            "scope",
            "scope_sha256",
            "step_key",
            "visit_key",
            "ordinal",
        },
        context="preparation failure attempt",
    )
    try:
        scope = ProviderAttemptScope.from_dict(
            _thaw_json(attempt["scope"])
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("preparation failure attempt scope is invalid") from exc
    ordinal = _integer(
        attempt["ordinal"],
        context="preparation failure attempt ordinal",
        minimum=1,
    )
    expected_attempt = {
        "scope": scope.to_dict(),
        "scope_sha256": scope.key,
        "step_key": hashlib.sha256(
            scope.runtime_step_id.encode("utf-8")
        ).hexdigest()[:24],
        "visit_key": scope.key[7:31],
        "ordinal": ordinal,
    }
    if _thaw_json(attempt) != expected_attempt:
        raise ValueError(
            "preparation failure attempt contradicts its scope"
        )
    if (
        run["run_id"] != scope.run_id
        or run["workflow_file"]
        != scope.resume_scope.root_workflow_file
    ):
        raise ValueError("preparation failure run contradicts its scope")
    _require_sha256(
        run["workflow_checksum"],
        context="preparation failure workflow identity",
    )
    return run, attempt


def _validate_failure_fragment(value: Any) -> Mapping[str, Any]:
    fragment = _closed(
        value,
        {
            "identity_schema_version",
            "compiled_prompt_fragment_identity",
            "prompt_attempt_identity_version",
            "binding_plan_sha256",
        },
        context="preparation failure fragment",
    )
    if (
        fragment["identity_schema_version"]
        not in _COMPILED_FRAGMENT_IDENTITY_SCHEMAS
    ):
        raise ValueError(
            "preparation failure fragment identity schema is invalid"
        )
    _require_sha256(
        fragment["compiled_prompt_fragment_identity"],
        context="preparation failure compiled fragment identity",
    )
    if (
        fragment["prompt_attempt_identity_version"]
        != PROMPT_ATTEMPT_IDENTITY_VERSION
    ):
        raise ValueError(
            "preparation failure attempt identity version is invalid"
        )
    _require_sha256(
        fragment["binding_plan_sha256"],
        context="preparation failure binding plan identity",
    )
    return fragment


def build_prompt_fragment_preparation_failure(
    *,
    run: Mapping[str, Any],
    attempt: Mapping[str, Any],
    fragment: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Build the exact unresolved-policy preparation failure record."""

    record = {
        "schema": PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA,
        "record_kind": "failure",
        "run": _thaw_json(run),
        "attempt": _thaw_json(attempt),
        "fragment": _thaw_json(fragment),
        "failure": {
            "category": "provider_policy_unresolved",
            "phase": "invocation_preparation",
        },
        "provider_calls": {
            "preparation": True,
            "execution": False,
        },
    }
    record["record_sha256"] = _record_sha256(record)
    return validate_prompt_fragment_preparation_failure(
        record,
        expected_fragment=fragment,
    )


def validate_prompt_fragment_preparation_failure(
    value: Any,
    *,
    expected_fragment: Mapping[str, Any] | None = None,
) -> Mapping[str, Any]:
    """Validate and freeze the exact Q3 preparation failure record."""

    record = _closed(
        value,
        {
            "schema",
            "record_kind",
            "run",
            "attempt",
            "fragment",
            "failure",
            "provider_calls",
            "record_sha256",
        },
        context="preparation failure record",
    )
    if (
        record["schema"] != PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA
        or record["record_kind"] != "failure"
    ):
        raise ValueError("preparation failure schema is invalid")
    _validate_run_and_attempt(record["run"], record["attempt"])
    fragment = _validate_failure_fragment(record["fragment"])
    if expected_fragment is not None:
        expected = _validate_failure_fragment(expected_fragment)
        if _thaw_json(fragment) != _thaw_json(expected):
            raise ValueError(
                "preparation failure fragment contradicts runtime carriers"
            )
    failure = _closed(
        record["failure"],
        {"category", "phase"},
        context="preparation failure",
    )
    if failure != {
        "category": "provider_policy_unresolved",
        "phase": "invocation_preparation",
    }:
        raise ValueError("preparation failure classification is invalid")
    provider_calls = _closed(
        record["provider_calls"],
        {"preparation", "execution"},
        context="preparation failure provider calls",
    )
    if (
        type(provider_calls["preparation"]) is not bool
        or type(provider_calls["execution"]) is not bool
        or provider_calls["preparation"] is not True
        or provider_calls["execution"] is not False
    ):
        raise ValueError("preparation failure provider calls are invalid")
    if (
        not _is_sha256(record["record_sha256"])
        or record["record_sha256"] != _record_sha256(record)
    ):
        raise ValueError("preparation failure record identity is invalid")
    return _freeze_json(record)


@dataclass(frozen=True)
class PromptComparisonRecord:
    """One immutable validation outcome supplied to the pure comparator."""

    scope: ProviderAttemptScope
    ordinal: int
    outcome: str
    prompt_attempt_identity: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, ProviderAttemptScope):
            raise TypeError("PromptComparisonRecord scope is invalid")
        _integer(
            self.ordinal,
            context="PromptComparisonRecord ordinal",
            minimum=1,
        )
        if self.outcome not in _COMPARISON_OUTCOMES:
            raise ValueError("PromptComparisonRecord outcome is invalid")
        if self.outcome == "v2_snapshot":
            if not isinstance(self.prompt_attempt_identity, Mapping):
                raise ValueError(
                    "v2 comparison record requires an identity"
                )
            object.__setattr__(
                self,
                "prompt_attempt_identity",
                _freeze_json(self.prompt_attempt_identity),
            )
        elif self.prompt_attempt_identity is not None:
            raise ValueError(
                "non-v2 comparison record forbids an identity"
            )


def _unavailable(reason: str) -> Mapping[str, Any]:
    if reason not in _UNAVAILABLE_REASONS:
        raise ValueError("comparison unavailable reason is invalid")
    return _freeze_json(
        {
            "status": "unavailable",
            "previous_attempt_ordinal": None,
            "classifications": [],
            "reason": reason,
        }
    )


def _current_unavailability(
    current: PromptComparisonRecord,
) -> str | None:
    if current.outcome in {"invalid_snapshot", "missing_snapshot"}:
        return "current_record_invalid"
    if current.outcome == "legacy_snapshot":
        return "legacy_snapshot_only"
    if current.outcome == "preparation_failure":
        return "provider_policy_unresolved"
    if current.outcome in {"failure", "allocation_only"}:
        return "current_record_missing"
    return None


def _previous_unavailability(
    previous: PromptComparisonRecord,
) -> str | None:
    if previous.outcome in {"invalid_snapshot", "missing_snapshot"}:
        return "previous_record_invalid"
    if previous.outcome == "legacy_snapshot":
        return "legacy_snapshot_only"
    if previous.outcome != "v2_snapshot":
        return "previous_record_invalid"
    return None


def compare_prompt_attempt_records(
    current: PromptComparisonRecord,
    previous: PromptComparisonRecord,
) -> Mapping[str, Any]:
    """Compare one strictly later record with one same-scope predecessor."""

    if (
        not isinstance(current, PromptComparisonRecord)
        or not isinstance(previous, PromptComparisonRecord)
    ):
        raise TypeError("prompt comparison records are required")
    if (
        current.scope != previous.scope
        or current.ordinal <= previous.ordinal
    ):
        raise ValueError(
            "prompt comparison scope or ordinal is invalid"
        )
    reason = _current_unavailability(current)
    if reason is not None:
        return _unavailable(reason)
    reason = _previous_unavailability(previous)
    if reason is not None:
        return _unavailable(reason)
    if current.prompt_attempt_identity is None:
        return _unavailable("current_record_invalid")
    if previous.prompt_attempt_identity is None:
        return _unavailable("previous_record_invalid")
    try:
        current_identity = validate_prompt_attempt_identity(
            current.prompt_attempt_identity
        )
    except (TypeError, ValueError):
        return _unavailable("current_record_invalid")
    try:
        previous_identity = validate_prompt_attempt_identity(
            previous.prompt_attempt_identity
        )
    except (TypeError, ValueError):
        return _unavailable("previous_record_invalid")
    classifications = tuple(
        ROLE_CLASSIFICATIONS[role_key]
        for role_key in ROLE_ORDER
        if (
            current_identity["roles"][role_key]["sha256"]
            != previous_identity["roles"][role_key]["sha256"]
        )
    )
    if not classifications:
        if (
            _thaw_json(current_identity["final_prompt"])
            != _thaw_json(previous_identity["final_prompt"])
        ):
            return _unavailable(
                "prompt_identity_composition_mismatch"
            )
        classifications = ("prompt_context_unchanged",)
    return _freeze_json(
        {
            "status": "available",
            "previous_attempt_ordinal": previous.ordinal,
            "classifications": list(classifications),
            "reason": None,
        }
    )


def compare_prompt_attempt_history(
    current: PromptComparisonRecord | None,
    candidates: Sequence[PromptComparisonRecord],
) -> Mapping[str, Any]:
    """Select the greatest earlier same-scope snapshot, then compare it."""

    if current is None:
        return _unavailable("current_record_missing")
    if not isinstance(current, PromptComparisonRecord):
        raise TypeError("current prompt comparison record is invalid")
    if not isinstance(candidates, (tuple, list)):
        raise TypeError("prompt comparison candidates must be an array")
    reason = _current_unavailability(current)
    if reason is not None:
        return _unavailable(reason)
    if current.prompt_attempt_identity is None:
        return _unavailable("current_record_invalid")
    try:
        validate_prompt_attempt_identity(
            current.prompt_attempt_identity
        )
    except (TypeError, ValueError):
        return _unavailable("current_record_invalid")
    eligible: list[PromptComparisonRecord] = []
    for candidate in candidates:
        if not isinstance(candidate, PromptComparisonRecord):
            raise TypeError("prompt comparison candidate is invalid")
        if (
            candidate.scope == current.scope
            and candidate.ordinal < current.ordinal
            and candidate.outcome in _SNAPSHOT_OUTCOMES
        ):
            eligible.append(candidate)
    if not eligible:
        return _unavailable("no_predecessor")
    greatest_ordinal = max(candidate.ordinal for candidate in eligible)
    greatest = [
        candidate
        for candidate in eligible
        if candidate.ordinal == greatest_ordinal
    ]
    if len(greatest) != 1:
        raise ValueError(
            "prompt comparison predecessor ordinal is ambiguous"
        )
    return compare_prompt_attempt_records(current, greatest[0])


__all__ = [
    "COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_SCHEMA",
    "PROMPT_ATTEMPT_COMPOSITION_SCHEMA",
    "PROMPT_ATTEMPT_IDENTITY_VERSION",
    "PROMPT_FRAGMENT_PREPARATION_FAILURE_SCHEMA",
    "PROMPT_FRAGMENT_SNAPSHOT_V1_SCHEMA",
    "PROMPT_FRAGMENT_SNAPSHOT_V2_SCHEMA",
    "PromptComparisonRecord",
    "ROLE_CLASSIFICATIONS",
    "ROLE_ORDER",
    "ROLE_SCHEMAS",
    "build_fragment_program_role",
    "build_injected_dependencies_role",
    "build_prompt_attempt_identity",
    "build_prompt_fragment_preparation_failure",
    "build_prompt_fragment_snapshot_v2",
    "build_provider_policy_role",
    "build_resolved_bindings_role",
    "build_runtime_contributions_role",
    "canonical_json_bytes",
    "canonical_sha256",
    "compare_prompt_attempt_history",
    "compare_prompt_attempt_records",
    "prompt_fragment_transport_value_sha256",
    "validate_prompt_attempt_identity",
    "validate_prompt_fragment_preparation_failure",
    "validate_prompt_fragment_snapshot_v2_q3",
    "validate_prompt_identity_role",
]
