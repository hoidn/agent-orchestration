"""Frozen compiler carrier for one Workflow Lisp prompt fragment application."""

from __future__ import annotations

import json
import hashlib
import math
import re
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA = "compiler_prompt_fragment_contract.v1"
COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2 = "compiler_prompt_fragment_contract.v2"
PROMPT_ATTEMPT_IDENTITY_VERSION = "workflow_prompt_attempt_identity.v1"
COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_SCHEMA = (
    "compiler_prompt_attempt_binding_plan.v1"
)
_IDENTITY_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PLACEHOLDER_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_RENDERERS_BY_KIND = {
    "text": "raw-utf8-string",
    "value": "canonical-json",
    "path": "posix-path-line",
}
_EXPECTED_OUTPUTS_UNSET = object()


def _freeze_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType(
            {
                str(key): _freeze_json(item)
                for key, item in value.items()
            }
        )
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError("prompt fragment contract values must be JSON-compatible")


def _thaw_json(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _thaw_json(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _thaw_json(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_compiler_prompt_attempt_binding_plan_sha256(
    value: Mapping[str, Any],
) -> str:
    """Digest one unsealed closed binding-plan projection."""

    if set(value) != {"schema_version", "rows"}:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "digest projection must contain exactly schema_version and rows"
        )
    return "sha256:" + hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _require_exact_keys(
    value: Mapping[str, Any],
    expected: set[str],
    *,
    context: str,
) -> None:
    if set(value) != expected:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            f"{context} must contain exactly {sorted(expected)}"
        )


def _require_non_empty_string(value: Any, *, context: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            f"{context} must be a non-empty string"
        )
    return value


def _validate_value_source(value_source: Mapping[str, Any]) -> None:
    _require_exact_keys(
        value_source,
        {"kind", "binding"},
        context="value_source",
    )
    if value_source["kind"] != "typed_binding_ref":
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "value_source.kind must be typed_binding_ref"
        )
    binding = value_source["binding"]
    if isinstance(binding, Mapping):
        _require_exact_keys(binding, {"ref"}, context="value_source.binding")
        ref = _require_non_empty_string(
            binding["ref"],
            context="value_source.binding.ref",
        )
        if not ref.startswith(
            ("inputs.", "root.steps.", "self.steps.", "parent.steps.")
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "value_source binding ref is outside the admitted runtime namespaces"
            )
        return
    if binding is None or isinstance(binding, (str, bool, int)):
        return
    if isinstance(binding, float) and math.isfinite(binding):
        return
    raise ValueError(
        "compiler_prompt_fragment_contract_invalid: "
        "value_source binding must be one admitted ref or JSON scalar literal"
    )


def _scan_placeholders(template: str) -> tuple[str, ...]:
    names: list[str] = []
    index = 0
    while index < len(template):
        char = template[index]
        if char == "{":
            if index + 1 < len(template) and template[index + 1] == "{":
                index += 2
                continue
            closing = template.find("}", index + 1)
            if closing < 0:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: malformed template placeholder"
                )
            name = template[index + 1 : closing]
            if not _PLACEHOLDER_NAME_RE.fullmatch(name):
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: malformed template placeholder"
                )
            names.append(name)
            index = closing + 1
            continue
        if char == "}":
            if index + 1 < len(template) and template[index + 1] == "}":
                index += 2
                continue
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: malformed template placeholder"
            )
        index += 1
    return tuple(names)


@dataclass(frozen=True)
class CompilerPromptFragmentRenderedSlot:
    """One rendered slot in declaration order."""

    name: str
    kind: str
    static_type: Mapping[str, Any]
    renderer_id: str
    value_source: Mapping[str, Any]
    placeholder_ordinals: tuple[int, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "static_type", _freeze_json(self.static_type))
        object.__setattr__(self, "value_source", _freeze_json(self.value_source))
        object.__setattr__(
            self,
            "placeholder_ordinals",
            tuple(self.placeholder_ordinals),
        )
        if not isinstance(self.name, str) or not _PLACEHOLDER_NAME_RE.fullmatch(
            self.name
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: rendered slot name is invalid"
            )
        expected_renderer = _RENDERERS_BY_KIND.get(self.kind)
        if expected_renderer is None or self.renderer_id != expected_renderer:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: rendered slot kind/renderer mismatch"
            )
        if not isinstance(self.static_type, Mapping) or not self.static_type:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: static_type is required"
            )
        if not isinstance(self.value_source, Mapping) or not self.value_source:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: value_source is required"
            )
        from orchestrator.workflow_lisp.lowering.pure_projection import (
            validate_compiler_normalized_type_descriptor,
        )

        try:
            validate_compiler_normalized_type_descriptor(
                self.static_type,
                context="static_type",
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "static_type is not a compiler normalized type descriptor"
            ) from exc
        _validate_value_source(self.value_source)
        if (
            not isinstance(self.placeholder_ordinals, tuple)
            or not self.placeholder_ordinals
            or any(
                not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 0
                for ordinal in self.placeholder_ordinals
            )
            or tuple(sorted(set(self.placeholder_ordinals)))
            != self.placeholder_ordinals
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: placeholder ordinals are invalid"
            )

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentRenderedSlot":
        return self


@dataclass(frozen=True)
class CompilerPromptFragmentContract:
    """Exact template plus the closed program needed to render it at runtime."""

    schema_version: str
    template_utf8: str
    rendered_slots: tuple[CompilerPromptFragmentRenderedSlot, ...]
    compiled_prompt_fragment_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rendered_slots", tuple(self.rendered_slots))
        validate_compiler_prompt_fragment_contract(self)

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentContract":
        return self


@dataclass(frozen=True)
class CompilerPromptFragmentOutputPosition:
    """One compiler-owned output-position row in slot declaration order."""

    slot_name: str
    output_role: str
    expected_output: Mapping[str, Any]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "expected_output",
            _freeze_json(self.expected_output),
        )
        if not isinstance(
            self.slot_name, str
        ) or not _PLACEHOLDER_NAME_RE.fullmatch(self.slot_name):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position slot name is invalid"
            )
        if self.output_role != "required_string_file":
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position role must be required_string_file"
            )
        if not isinstance(self.expected_output, Mapping):
            raise TypeError("expected_output must be a mapping")
        _require_exact_keys(
            self.expected_output,
            {"name", "path", "type", "required"},
            context="output_position.expected_output",
        )
        if self.expected_output["name"] != self.slot_name:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position name must match its slot"
            )
        _require_non_empty_string(
            self.expected_output["path"],
            context="output_position.expected_output.path",
        )
        if (
            self.expected_output["type"] != "string"
            or self.expected_output["required"] is not True
        ):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position must require one string file"
            )

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentOutputPosition":
        return self


@dataclass(frozen=True)
class CompilerPromptFragmentContractV2:
    """V2 renderer carrier with compiler-owned output-position obligations."""

    schema_version: str
    template_utf8: str
    rendered_slots: tuple[CompilerPromptFragmentRenderedSlot, ...]
    output_positions: tuple[CompilerPromptFragmentOutputPosition, ...]
    compiled_prompt_fragment_identity: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "rendered_slots", tuple(self.rendered_slots))
        object.__setattr__(self, "output_positions", tuple(self.output_positions))
        validate_compiler_prompt_fragment_contract(self)

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptFragmentContractV2":
        return self


CompilerPromptFragmentContractCarrier = (
    CompilerPromptFragmentContract | CompilerPromptFragmentContractV2
)


@dataclass(frozen=True)
class CompilerPromptAttemptBindingPlanRow:
    """One declaration-ordered Q3 runtime binding locator."""

    declaration_ordinal: int
    slot_name: str
    slot_kind: str
    refinement: Mapping[str, Any] | None
    output_role: str
    delivery: str
    runtime_source: Mapping[str, Any]
    renderer: Mapping[str, Any] | None

    def __post_init__(self) -> None:
        if self.refinement is not None:
            object.__setattr__(self, "refinement", _freeze_json(self.refinement))
        object.__setattr__(
            self,
            "runtime_source",
            _freeze_json(self.runtime_source),
        )
        if self.renderer is not None:
            object.__setattr__(self, "renderer", _freeze_json(self.renderer))
        _validate_compiler_prompt_attempt_binding_plan_row(self)

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptAttemptBindingPlanRow":
        return self


@dataclass(frozen=True)
class CompilerPromptAttemptBindingPlan:
    """Closed compiler-owned Q3 declaration-to-runtime binding plan."""

    schema_version: str
    rows: tuple[CompilerPromptAttemptBindingPlanRow, ...]
    plan_sha256: str | None
    _compiler_expected_plan_sha256: str | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "rows", tuple(self.rows))
        validate_compiler_prompt_attempt_binding_plan(
            self,
            require_digest=self.plan_sha256 is not None,
        )

    def with_canonical_sha256(self) -> "CompilerPromptAttemptBindingPlan":
        """Seal one already validated unsealed plan."""

        projection = {
            "schema_version": self.schema_version,
            "rows": [
                serialize_compiler_prompt_attempt_binding_plan_row(row)
                for row in self.rows
            ],
        }
        return CompilerPromptAttemptBindingPlan(
            schema_version=self.schema_version,
            rows=self.rows,
            plan_sha256=(
                canonical_compiler_prompt_attempt_binding_plan_sha256(
                    projection
                )
            ),
            _compiler_expected_plan_sha256=(
                self._compiler_expected_plan_sha256
            ),
        )

    def with_compiler_expected_plan_authority(
        self,
    ) -> "CompilerPromptAttemptBindingPlan":
        """Bind this compiler-created plan to its initial validation bytes."""

        validate_compiler_prompt_attempt_binding_plan(self)
        assert self.plan_sha256 is not None
        return CompilerPromptAttemptBindingPlan(
            schema_version=self.schema_version,
            rows=self.rows,
            plan_sha256=self.plan_sha256,
            _compiler_expected_plan_sha256=self.plan_sha256,
        )

    def __deepcopy__(
        self,
        memo: dict[int, Any],
    ) -> "CompilerPromptAttemptBindingPlan":
        return self


def _validate_compiler_prompt_attempt_binding_plan_row(
    row: CompilerPromptAttemptBindingPlanRow,
) -> None:
    if (
        not isinstance(row.declaration_ordinal, int)
        or isinstance(row.declaration_ordinal, bool)
        or row.declaration_ordinal < 0
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "declaration ordinal must be a non-negative integer"
        )
    if (
        not isinstance(row.slot_name, str)
        or not _PLACEHOLDER_NAME_RE.fullmatch(row.slot_name)
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: slot name is invalid"
        )
    if row.slot_kind not in {"doc", "text", "value", "path"}:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: slot kind is invalid"
        )
    if row.refinement is not None:
        if not isinstance(row.refinement, Mapping):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: refinement is invalid"
            )
        from orchestrator.workflow_lisp.lowering.pure_projection import (
            validate_compiler_normalized_type_descriptor,
        )

        try:
            validate_compiler_normalized_type_descriptor(
                row.refinement,
                context="refinement",
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: refinement is invalid"
            ) from exc
    if row.slot_kind == "text" and row.refinement is not None:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "text slots forbid refinements"
        )
    if (
        row.refinement is not None
        and row.slot_kind in {"doc", "path"}
        and row.refinement.get("kind") != "path"
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "document and path refinements must be path descriptors"
        )
    if row.output_role not in {"none", "required_string_file"}:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: output role is invalid"
        )
    if (
        row.output_role == "required_string_file"
        and row.slot_kind != "path"
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "required output role requires a path slot"
        )
    expected_delivery = (
        "dependency" if row.slot_kind == "doc" else "template"
    )
    if row.delivery != expected_delivery:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: delivery is invalid"
        )
    if not isinstance(row.runtime_source, Mapping) or set(
        row.runtime_source
    ) != {"kind", "ordinal"}:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: runtime source is invalid"
        )
    expected_source_kind = (
        "required_dependency"
        if row.slot_kind == "doc"
        else "rendered_slot"
    )
    if row.runtime_source["kind"] != expected_source_kind:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: runtime source kind is invalid"
        )
    source_ordinal = row.runtime_source["ordinal"]
    if (
        not isinstance(source_ordinal, int)
        or isinstance(source_ordinal, bool)
        or source_ordinal < 0
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "runtime source ordinal is invalid"
        )
    if row.slot_kind == "doc":
        if row.renderer is not None:
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                "document renderer must be null"
            )
        return
    if not isinstance(row.renderer, Mapping) or set(row.renderer) != {
        "renderer_id",
        "renderer_version",
    }:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: renderer is invalid"
        )
    renderer_version = row.renderer["renderer_version"]
    if (
        row.renderer["renderer_id"] != _RENDERERS_BY_KIND[row.slot_kind]
        or type(renderer_version) is not int
        or renderer_version != 1
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: renderer is invalid"
        )


def validate_compiler_prompt_attempt_binding_plan(
    plan: CompilerPromptAttemptBindingPlan,
    *,
    require_digest: bool = True,
) -> CompilerPromptAttemptBindingPlan:
    """Validate the closed schema, order, locators, and canonical seal."""

    if type(plan) is not CompilerPromptAttemptBindingPlan:
        raise TypeError(
            "prompt_attempt_binding_plan_invalid: "
            "expected CompilerPromptAttemptBindingPlan"
        )
    if plan.schema_version != COMPILER_PROMPT_ATTEMPT_BINDING_PLAN_SCHEMA:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: unsupported schema"
        )
    if not isinstance(plan.rows, tuple):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: rows must be a tuple"
        )
    if any(
        type(row) is not CompilerPromptAttemptBindingPlanRow
        for row in plan.rows
    ):
        raise TypeError(
            "prompt_attempt_binding_plan_invalid: rows have invalid type"
        )
    for row in plan.rows:
        _validate_compiler_prompt_attempt_binding_plan_row(row)
    if tuple(row.declaration_ordinal for row in plan.rows) != tuple(
        range(len(plan.rows))
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: "
            "declaration ordinals must be contiguous and ordered"
        )
    names = tuple(row.slot_name for row in plan.rows)
    if len(set(names)) != len(names):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: slot names must be unique"
        )
    for source_kind in ("required_dependency", "rendered_slot"):
        ordinals = tuple(
            int(row.runtime_source["ordinal"])
            for row in plan.rows
            if row.runtime_source["kind"] == source_kind
        )
        if ordinals != tuple(range(len(ordinals))):
            raise ValueError(
                "prompt_attempt_binding_plan_invalid: "
                f"{source_kind} locators must be contiguous and ordered"
            )
    if not require_digest and plan.plan_sha256 is None:
        return plan
    if (
        not isinstance(plan.plan_sha256, str)
        or not _IDENTITY_RE.fullmatch(plan.plan_sha256)
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: plan digest is malformed"
        )
    expected = canonical_compiler_prompt_attempt_binding_plan_sha256(
        {
            "schema_version": plan.schema_version,
            "rows": [
                serialize_compiler_prompt_attempt_binding_plan_row(row)
                for row in plan.rows
            ],
        }
    )
    if expected != plan.plan_sha256:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: plan digest mismatch"
        )
    return plan


def validate_compiler_prompt_attempt_binding_plan_authority(
    plan: CompilerPromptAttemptBindingPlan,
) -> None:
    """Check the ephemeral compiler seal at initial mapping validation."""

    validate_compiler_prompt_attempt_binding_plan(plan)
    expected = plan._compiler_expected_plan_sha256
    if (
        not isinstance(expected, str)
        or not _IDENTITY_RE.fullmatch(expected)
        or expected != plan.plan_sha256
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_mismatch: "
            "binding plan disagrees with compiler-owned declaration authority"
        )


def _typed_prompt_input_by_name(
    typed_prompt_inputs: tuple[Any, ...],
) -> dict[str, Mapping[str, Any]]:
    by_name: dict[str, Mapping[str, Any]] = {}
    for value in typed_prompt_inputs:
        if not isinstance(value, Mapping):
            raise ValueError(
                "prompt_attempt_binding_plan_mismatch: "
                "typed prompt input row is invalid"
            )
        name = value.get("binding_name")
        if not isinstance(name, str) or name in by_name:
            raise ValueError(
                "prompt_attempt_binding_plan_mismatch: "
                "typed prompt input names are invalid"
            )
        by_name[name] = value
    return by_name


def validate_compiler_prompt_attempt_pair(
    identity_version: str | None,
    plan: CompilerPromptAttemptBindingPlan | None,
    *,
    fragment_contract: CompilerPromptFragmentContractCarrier | None,
    dependency_contract: Any = None,
    typed_prompt_inputs: tuple[Any, ...] = (),
    required: bool = False,
    target_dsl_version: str | None = None,
) -> None:
    """Validate the target-gated Q3 pair and its existing carrier locators."""

    pair_present = identity_version is not None or plan is not None
    if target_dsl_version is not None:
        try:
            target_parts = tuple(
                int(part) for part in target_dsl_version.split(".")
            )
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError(
                "prompt_attempt_identity_version_invalid: "
                "target DSL version is invalid"
            ) from exc
        target_supports_pair = target_parts >= (2, 22)
        if not target_supports_pair and pair_present:
            raise ValueError(
                "prompt_attempt_identity_version_invalid: "
                "Q3 prompt-attempt carriers require target DSL 2.22"
            )
        required = (
            required
            or target_supports_pair
            and fragment_contract is not None
        )
    if identity_version is None and plan is None:
        if required:
            raise ValueError(
                "prompt_attempt_identity_version_missing: "
                "target-2.22 fragment application requires the Q3 pair"
            )
        return
    if identity_version is None:
        raise ValueError(
            "prompt_attempt_identity_version_missing: "
            "identity version and binding plan must be paired"
        )
    if plan is None:
        raise ValueError(
            "prompt_attempt_binding_plan_missing: "
            "identity version and binding plan must be paired"
        )
    if identity_version != PROMPT_ATTEMPT_IDENTITY_VERSION:
        raise ValueError(
            "prompt_attempt_identity_version_invalid: "
            "unsupported prompt-attempt identity version"
        )
    try:
        validate_compiler_prompt_attempt_binding_plan(plan)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "prompt_attempt_binding_plan_invalid: binding plan is invalid"
        ) from exc
    if fragment_contract is None:
        raise ValueError(
            "prompt_attempt_binding_plan_mismatch: "
            "binding plan requires a fragment contract"
        )
    rendered_plan_rows = tuple(
        row for row in plan.rows if row.slot_kind != "doc"
    )
    if len(rendered_plan_rows) != len(fragment_contract.rendered_slots):
        raise ValueError(
            "prompt_attempt_binding_plan_mismatch: rendered rows disagree"
        )
    for row, fragment_row in zip(
        rendered_plan_rows,
        fragment_contract.rendered_slots,
        strict=True,
    ):
        if (
            row.slot_name != fragment_row.name
            or row.slot_kind != fragment_row.kind
            or row.renderer is None
            or row.renderer["renderer_id"] != fragment_row.renderer_id
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_mismatch: "
                "rendered row disagrees with fragment contract"
            )
    output_roles = {
        row.slot_name: row.output_role for row in plan.rows
    }
    expected_output_names = tuple(
        row.slot_name
        for row in getattr(fragment_contract, "output_positions", ())
    )
    observed_output_names = tuple(
        row.slot_name
        for row in plan.rows
        if row.output_role == "required_string_file"
    )
    if expected_output_names != observed_output_names or any(
        role == "required_string_file" and name not in expected_output_names
        for name, role in output_roles.items()
    ):
        raise ValueError(
            "prompt_attempt_binding_plan_mismatch: "
            "output roles disagree with fragment contract"
        )
    typed_by_name = _typed_prompt_input_by_name(typed_prompt_inputs)
    expected_typed_names = {
        row.slot_name
        for row in plan.rows
        if row.slot_kind in {"value", "path"}
    }
    if set(typed_by_name) != expected_typed_names:
        raise ValueError(
            "prompt_attempt_binding_plan_mismatch: "
            "typed input coverage disagrees with binding plan"
        )
    for row in plan.rows:
        if row.slot_kind not in {"value", "path"}:
            continue
        typed_renderer = typed_by_name[row.slot_name].get("renderer")
        if (
            not isinstance(typed_renderer, Mapping)
            or row.renderer is None
            or typed_renderer.get("renderer_id")
            != row.renderer["renderer_id"]
            or typed_renderer.get("renderer_version")
            != row.renderer["renderer_version"]
        ):
            raise ValueError(
                "prompt_attempt_binding_plan_mismatch: "
                "typed renderer disagrees with binding plan"
            )
    if dependency_contract is not None:
        doc_rows = tuple(row for row in plan.rows if row.slot_kind == "doc")
        dependency_refs = tuple(
            getattr(dependency_contract, "required_binding_refs", ())
        )
        if len(doc_rows) != len(dependency_refs):
            raise ValueError(
                "prompt_attempt_binding_plan_mismatch: "
                "dependency coverage disagrees with binding plan"
            )


def _path_template_from_rendered_slot(
    slot: CompilerPromptFragmentRenderedSlot,
) -> str:
    """Derive one output template solely from the frozen Q1 value source."""

    _validate_value_source(slot.value_source)
    binding = slot.value_source["binding"]
    if isinstance(binding, Mapping):
        return "${" + str(binding["ref"]) + "}"
    if isinstance(binding, str):
        return binding
    raise ValueError(
        "compiler_prompt_fragment_contract_invalid: "
        "output-position value source must be a binding ref or string literal"
    )


def _validate_compiler_prompt_fragment_contract_v2(
    contract: CompilerPromptFragmentContractV2,
) -> CompilerPromptFragmentContractV2:
    if contract.schema_version != COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA_V2:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: unsupported schema"
        )
    if not isinstance(contract.template_utf8, str):
        raise TypeError("template_utf8 must be a string")
    if not isinstance(contract.rendered_slots, tuple):
        raise TypeError("rendered_slots must be a tuple")
    if not isinstance(contract.output_positions, tuple):
        raise TypeError("output_positions must be a tuple")
    if not contract.output_positions:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "v2 contract requires at least one output-position row"
        )
    if not _IDENTITY_RE.fullmatch(contract.compiled_prompt_fragment_identity):
        raise ValueError(
            "compiled_prompt_fragment_identity_invalid: identity is malformed"
        )

    placeholders = _scan_placeholders(contract.template_utf8)
    rendered_names: set[str] = set()
    claimed_ordinals: set[int] = set()
    path_slots: dict[str, tuple[int, CompilerPromptFragmentRenderedSlot]] = {}
    for index, slot in enumerate(contract.rendered_slots):
        if type(slot) is not CompilerPromptFragmentRenderedSlot:
            raise TypeError(
                "rendered_slots must contain CompilerPromptFragmentRenderedSlot"
            )
        slot.__post_init__()
        if slot.name in rendered_names:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "rendered slot names must be unique"
            )
        rendered_names.add(slot.name)
        if slot.kind == "path":
            path_slots[slot.name] = (index, slot)
        for ordinal in slot.placeholder_ordinals:
            if ordinal >= len(placeholders) or placeholders[ordinal] != slot.name:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: "
                    "placeholder row mismatch"
                )
            if ordinal in claimed_ordinals:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: "
                    "placeholder ordinal is duplicated"
                )
            claimed_ordinals.add(ordinal)
    if claimed_ordinals != set(range(len(placeholders))):
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "placeholder rows are incomplete"
        )

    output_names: set[str] = set()
    declaration_indexes: list[int] = []
    for row in contract.output_positions:
        if type(row) is not CompilerPromptFragmentOutputPosition:
            raise TypeError(
                "output_positions must contain "
                "CompilerPromptFragmentOutputPosition"
            )
        row.__post_init__()
        if row.slot_name in output_names:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position names must be unique"
            )
        output_names.add(row.slot_name)
        path_slot = path_slots.get(row.slot_name)
        if path_slot is None:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position must name one rendered path slot"
            )
        declaration_index, slot = path_slot
        declaration_indexes.append(declaration_index)
        if row.expected_output["path"] != _path_template_from_rendered_slot(slot):
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: "
                "output-position path differs from its normalized value source"
            )
    if declaration_indexes != sorted(declaration_indexes):
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: "
            "output positions must follow slot declaration order"
        )
    return contract


def validate_compiler_prompt_fragment_contract(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2,
) -> CompilerPromptFragmentContract | CompilerPromptFragmentContractV2:
    """Validate a typed fragment contract without coercing mappings."""

    if type(contract) is CompilerPromptFragmentContractV2:
        return _validate_compiler_prompt_fragment_contract_v2(contract)
    if type(contract) is not CompilerPromptFragmentContract:
        raise TypeError("expected CompilerPromptFragmentContract")
    if contract.schema_version != COMPILER_PROMPT_FRAGMENT_CONTRACT_SCHEMA:
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: unsupported schema"
        )
    if not isinstance(contract.template_utf8, str):
        raise TypeError("template_utf8 must be a string")
    if not isinstance(contract.rendered_slots, tuple):
        raise TypeError("rendered_slots must be a tuple")
    if not _IDENTITY_RE.fullmatch(contract.compiled_prompt_fragment_identity):
        raise ValueError(
            "compiled_prompt_fragment_identity_invalid: identity is malformed"
        )
    placeholders = _scan_placeholders(contract.template_utf8)
    names: set[str] = set()
    claimed_ordinals: set[int] = set()
    for slot in contract.rendered_slots:
        if type(slot) is not CompilerPromptFragmentRenderedSlot:
            raise TypeError(
                "rendered_slots must contain CompilerPromptFragmentRenderedSlot"
            )
        slot.__post_init__()
        if slot.name in names:
            raise ValueError(
                "compiler_prompt_fragment_contract_invalid: rendered slot names must be unique"
            )
        names.add(slot.name)
        for ordinal in slot.placeholder_ordinals:
            if ordinal >= len(placeholders) or placeholders[ordinal] != slot.name:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: placeholder row mismatch"
                )
            if ordinal in claimed_ordinals:
                raise ValueError(
                    "compiler_prompt_fragment_contract_invalid: placeholder ordinal is duplicated"
                )
            claimed_ordinals.add(ordinal)
    if claimed_ordinals != set(range(len(placeholders))):
        raise ValueError(
            "compiler_prompt_fragment_contract_invalid: placeholder rows are incomplete"
        )
    return contract


def validate_compiler_prompt_fragment_pair(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2 | None,
    identity: str | None,
    expected_outputs: object = _EXPECTED_OUTPUTS_UNSET,
) -> None:
    """Reject absent, malformed, or contradictory fragment carriage."""

    if contract is None and identity is None:
        return
    if contract is None or identity is None:
        if type(contract) is CompilerPromptFragmentContractV2:
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "v2 fragment contract and identity must be paired"
            )
        raise ValueError(
            "compiled_prompt_fragment_identity_missing: contract and identity must be paired"
        )
    try:
        validate_compiler_prompt_fragment_contract(contract)
    except (TypeError, ValueError) as exc:
        if type(contract) is CompilerPromptFragmentContractV2:
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "v2 fragment contract is invalid"
            ) from exc
        raise
    if not isinstance(identity, str) or not _IDENTITY_RE.fullmatch(identity):
        if type(contract) is CompilerPromptFragmentContractV2:
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "v2 fragment identity is malformed"
            )
        raise ValueError(
            "compiled_prompt_fragment_identity_invalid: identity is malformed"
        )
    if contract.compiled_prompt_fragment_identity != identity:
        if type(contract) is CompilerPromptFragmentContractV2:
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "v2 fragment identity differs from its carrier"
            )
        raise ValueError(
            "compiled_prompt_fragment_identity_mismatch: contract identity differs"
        )
    if type(contract) is CompilerPromptFragmentContractV2:
        if expected_outputs is _EXPECTED_OUTPUTS_UNSET:
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "v2 fragment pair validation requires expected_outputs"
            )
        if not isinstance(expected_outputs, (list, tuple)):
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "v2 fragment contract requires paired expected_outputs"
            )
        carrier_rows = [
            _thaw_json(row.expected_output)
            for row in contract.output_positions
        ]
        if (
            any(not isinstance(row, Mapping) for row in expected_outputs)
            or [_thaw_json(row) for row in expected_outputs] != carrier_rows
        ):
            raise ValueError(
                "prompt_output_position_contract_mismatch: "
                "v2 fragment output positions differ from expected_outputs"
            )


def serialize_compiler_prompt_fragment_rendered_slot(
    slot: CompilerPromptFragmentRenderedSlot,
) -> dict[str, Any]:
    """Serialize one validated rendered-slot row."""

    slot.__post_init__()
    return {
        "name": slot.name,
        "kind": slot.kind,
        "static_type": _thaw_json(slot.static_type),
        "renderer_id": slot.renderer_id,
        "value_source": _thaw_json(slot.value_source),
        "placeholder_ordinals": list(slot.placeholder_ordinals),
    }


def serialize_compiler_prompt_attempt_binding_plan_row(
    row: CompilerPromptAttemptBindingPlanRow,
) -> dict[str, Any]:
    """Serialize one validated binding-plan row."""

    _validate_compiler_prompt_attempt_binding_plan_row(row)
    return {
        "declaration_ordinal": row.declaration_ordinal,
        "slot_name": row.slot_name,
        "slot_kind": row.slot_kind,
        "refinement": (
            None if row.refinement is None else _thaw_json(row.refinement)
        ),
        "output_role": row.output_role,
        "delivery": row.delivery,
        "runtime_source": _thaw_json(row.runtime_source),
        "renderer": (
            None if row.renderer is None else _thaw_json(row.renderer)
        ),
    }


def serialize_compiler_prompt_attempt_binding_plan(
    plan: CompilerPromptAttemptBindingPlan,
) -> dict[str, Any]:
    """Serialize one sealed plan to its closed wire representation."""

    validate_compiler_prompt_attempt_binding_plan(plan)
    assert plan.plan_sha256 is not None
    return {
        "schema_version": plan.schema_version,
        "rows": [
            serialize_compiler_prompt_attempt_binding_plan_row(row)
            for row in plan.rows
        ],
        "plan_sha256": plan.plan_sha256,
    }


def serialize_compiler_prompt_fragment_contract(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2,
) -> dict[str, Any]:
    """Serialize one validated contract to its closed wire representation."""

    validate_compiler_prompt_fragment_contract(contract)
    serialized = {
        "schema_version": contract.schema_version,
        "template_utf8": contract.template_utf8,
        "rendered_slots": [
            serialize_compiler_prompt_fragment_rendered_slot(slot)
            for slot in contract.rendered_slots
        ],
        "compiled_prompt_fragment_identity": (
            contract.compiled_prompt_fragment_identity
        ),
    }
    if type(contract) is CompilerPromptFragmentContractV2:
        serialized["output_positions"] = [
            {
                "slot_name": row.slot_name,
                "output_role": row.output_role,
                "expected_output": _thaw_json(row.expected_output),
            }
            for row in contract.output_positions
        ]
    return serialized


def canonical_compiler_prompt_fragment_contract_json(
    contract: CompilerPromptFragmentContract | CompilerPromptFragmentContractV2,
) -> str:
    """Return compact canonical UTF-8 JSON with no trailing newline."""

    return _canonical_json_bytes(
        serialize_compiler_prompt_fragment_contract(contract)
    ).decode("utf-8")


def freeze_prompt_fragment_json(value: Mapping[str, Any]) -> Mapping[str, Any]:
    """Freeze compiler-owned JSON projections before putting them in the IR."""

    frozen = _freeze_json(value)
    assert isinstance(frozen, Mapping)
    return frozen
