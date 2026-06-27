"""Generic workflow-family profile catalog for compiler and lowering metadata."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .diagnostics import LispFrontendCompileError, LispFrontendDiagnostic
from .spans import SourcePosition, SourceSpan
from .typed_prompt_inputs import normalize_typed_prompt_input_entry


FAMILY_PROFILE_SCHEMA_VERSION = "workflow_lisp_family_profile.v1"


@dataclass(frozen=True)
class HiddenContextRule:
    workflow_name: str
    parameter_name: str
    phase_identity: str


@dataclass(frozen=True)
class WorkflowFamilyProfile:
    family_id: str
    source_path: Path
    workflow_name_prefixes: tuple[str, ...]
    target_workflows: frozenset[str]
    boundary_authority_registry_path: Path | None
    checked_public_inputs_by_workflow: Mapping[str, frozenset[str]]
    entry_phase_identities: Mapping[str, str]
    hidden_context_rules_by_workflow: Mapping[str, HiddenContextRule]
    typed_prompt_input_rows_by_key: Mapping[tuple[str, str], Mapping[str, Any]]

    def matches_workflow(self, workflow_name: str) -> bool:
        if workflow_name in self.target_workflows:
            return True
        return any(workflow_name.startswith(prefix) for prefix in self.workflow_name_prefixes)

    def typed_prompt_input_rows_for_workflow(
        self,
        workflow_name: str,
    ) -> Mapping[str, Mapping[str, Any]]:
        rows: dict[str, Mapping[str, Any]] = {}
        for (row_workflow_name, provider_binding), row in self.typed_prompt_input_rows_by_key.items():
            if row_workflow_name != workflow_name:
                continue
            rows[provider_binding] = row
        return rows


@dataclass(frozen=True)
class WorkflowFamilyProfileCatalog:
    profiles: tuple[WorkflowFamilyProfile, ...]

    def profiles_for_workflow(self, workflow_name: str) -> tuple[WorkflowFamilyProfile, ...]:
        return tuple(
            profile for profile in self.profiles if profile.matches_workflow(workflow_name)
        )

    def profile_for_workflow(self, workflow_name: str) -> WorkflowFamilyProfile | None:
        matches = self.profiles_for_workflow(workflow_name)
        if not matches:
            return None
        if len(matches) != 1:
            details = ", ".join(sorted(profile.family_id for profile in matches))
            raise _profile_error(
                code="workflow_family_profile_ambiguous",
                message=(
                    f"workflow `{workflow_name}` matches multiple workflow family profiles: {details}"
                ),
                path=matches[0].source_path,
            )
        return matches[0]

    def workflow_in_profile(self, workflow_name: str) -> bool:
        return self.profile_for_workflow(workflow_name) is not None

    def entry_phase_identity(self, workflow_name: str) -> str | None:
        profile = self.profile_for_workflow(workflow_name)
        if profile is None:
            return None
        return profile.entry_phase_identities.get(workflow_name)

    def checked_public_inputs(self, workflow_name: str) -> frozenset[str]:
        profile = self.profile_for_workflow(workflow_name)
        if profile is None:
            return frozenset()
        return profile.checked_public_inputs_by_workflow.get(workflow_name, frozenset())

    def hidden_context_rule(self, workflow_name: str) -> HiddenContextRule | None:
        profile = self.profile_for_workflow(workflow_name)
        if profile is None:
            return None
        return profile.hidden_context_rules_by_workflow.get(workflow_name)

    def typed_prompt_input_row(
        self,
        workflow_name: str,
        provider_call_locator: str | None = None,
    ) -> dict[str, Any] | None:
        profile = self.profile_for_workflow(workflow_name)
        if profile is None:
            return None
        if provider_call_locator is not None:
            row = profile.typed_prompt_input_rows_by_key.get(
                (workflow_name, provider_call_locator)
            )
            if isinstance(row, Mapping):
                return dict(row)
        return None

    def boundary_authority_registry_path(self, workflow_name: str) -> Path | None:
        profile = self.profile_for_workflow(workflow_name)
        if profile is None:
            return None
        return profile.boundary_authority_registry_path

    def typed_prompt_input_rows_for_workflow(
        self,
        workflow_name: str,
    ) -> Mapping[str, Mapping[str, Any]]:
        profile = self.profile_for_workflow(workflow_name)
        if profile is None:
            return {}
        return profile.typed_prompt_input_rows_for_workflow(workflow_name)

    def profile_metadata(self, workflow_name: str) -> dict[str, str] | None:
        profile = self.profile_for_workflow(workflow_name)
        if profile is None:
            return None
        return {
            "family_id": profile.family_id,
            "path": str(profile.source_path),
            "digest": _sha256_path(profile.source_path),
        }


def load_workflow_family_profile_catalog(
    profile_paths: Sequence[Path | str],
) -> WorkflowFamilyProfileCatalog:
    profiles = tuple(load_workflow_family_profile(Path(path)) for path in profile_paths)
    _validate_catalog_ambiguity(profiles)
    return WorkflowFamilyProfileCatalog(profiles=profiles)


def load_workflow_family_profile(path: Path) -> WorkflowFamilyProfile:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message=f"unable to read workflow family profile: {exc}",
            path=path,
        ) from exc
    except json.JSONDecodeError as exc:
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message=f"workflow family profile is not valid JSON: {exc}",
            path=path,
        ) from exc
    if not isinstance(payload, Mapping):
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message="workflow family profile must be a JSON object",
            path=path,
        )
    if payload.get("schema_version") != FAMILY_PROFILE_SCHEMA_VERSION:
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message=(
                "workflow family profile schema_version must be "
                f"{FAMILY_PROFILE_SCHEMA_VERSION}"
            ),
            path=path,
        )
    family_id = _require_non_empty_string(payload.get("family_id"), "family_id", path=path)
    target_workflows = frozenset(
        _normalize_string_list(
            payload.get("target_workflows"),
            field_name="target_workflows",
            path=path,
        )
    )
    workflow_name_prefixes = tuple(
        _normalize_string_list(
            payload.get("workflow_name_prefixes", ()),
            field_name="workflow_name_prefixes",
            path=path,
        )
    )
    boundary_authority_registry_path = _normalize_optional_relpath(
        payload.get("boundary_authority_registry"),
        field_name="boundary_authority_registry",
        path=path,
    )
    checked_public_inputs_by_workflow = _normalize_checked_public_inputs(
        payload.get("checked_public_inputs", {}),
        target_workflows=target_workflows,
        path=path,
    )
    entry_phase_identities = _normalize_entry_phase_identities(
        payload.get("entry_phase_identities", {}),
        target_workflows=target_workflows,
        path=path,
    )
    hidden_context_rules_by_workflow = _normalize_hidden_context_rules(
        payload.get("hidden_context_rules", ()),
        target_workflows=target_workflows,
        path=path,
    )
    typed_prompt_input_rows_by_key = _normalize_typed_prompt_input_rows(
        payload.get("typed_prompt_input_rows", ()),
        target_workflows=target_workflows,
        path=path,
    )
    return WorkflowFamilyProfile(
        family_id=family_id,
        source_path=path,
        workflow_name_prefixes=workflow_name_prefixes,
        target_workflows=target_workflows,
        boundary_authority_registry_path=boundary_authority_registry_path,
        checked_public_inputs_by_workflow=checked_public_inputs_by_workflow,
        entry_phase_identities=entry_phase_identities,
        hidden_context_rules_by_workflow=hidden_context_rules_by_workflow,
        typed_prompt_input_rows_by_key=typed_prompt_input_rows_by_key,
    )


def _normalize_checked_public_inputs(
    raw_value: object,
    *,
    target_workflows: frozenset[str],
    path: Path,
) -> Mapping[str, frozenset[str]]:
    if not isinstance(raw_value, Mapping):
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message="checked_public_inputs must be an object when present",
            path=path,
        )
    normalized: dict[str, frozenset[str]] = {}
    for workflow_name, raw_fields in raw_value.items():
        workflow_name = _require_non_empty_string(
            workflow_name,
            "checked_public_inputs workflow name",
            path=path,
        )
        _require_target_workflow(workflow_name, target_workflows=target_workflows, path=path)
        normalized[workflow_name] = frozenset(
            _normalize_string_list(
                raw_fields,
                field_name=f"checked_public_inputs.{workflow_name}",
                path=path,
            )
        )
    return normalized


def _normalize_entry_phase_identities(
    raw_value: object,
    *,
    target_workflows: frozenset[str],
    path: Path,
) -> Mapping[str, str]:
    if not isinstance(raw_value, Mapping):
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message="entry_phase_identities must be an object when present",
            path=path,
        )
    normalized: dict[str, str] = {}
    for workflow_name, phase_identity in raw_value.items():
        workflow_name = _require_non_empty_string(
            workflow_name,
            "entry_phase_identities workflow name",
            path=path,
        )
        _require_target_workflow(workflow_name, target_workflows=target_workflows, path=path)
        normalized[workflow_name] = _require_non_empty_string(
            phase_identity,
            f"entry_phase_identities.{workflow_name}",
            path=path,
        )
    return normalized


def _normalize_hidden_context_rules(
    raw_value: object,
    *,
    target_workflows: frozenset[str],
    path: Path,
) -> Mapping[str, HiddenContextRule]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message="hidden_context_rules must be an array when present",
            path=path,
        )
    normalized: dict[str, HiddenContextRule] = {}
    for index, raw_rule in enumerate(raw_value):
        if not isinstance(raw_rule, Mapping):
            raise _profile_error(
                code="workflow_family_profile_schema_invalid",
                message=f"hidden_context_rules[{index}] must be an object",
                path=path,
            )
        workflow_name = _require_non_empty_string(
            raw_rule.get("workflow_name"),
            f"hidden_context_rules[{index}].workflow_name",
            path=path,
        )
        _require_target_workflow(workflow_name, target_workflows=target_workflows, path=path)
        parameter_name = _require_non_empty_string(
            raw_rule.get("parameter_name"),
            f"hidden_context_rules[{index}].parameter_name",
            path=path,
        )
        if workflow_name in normalized:
            raise _profile_error(
                code="workflow_family_profile_hidden_context_invalid",
                message=f"workflow `{workflow_name}` declares duplicate hidden context rules",
                path=path,
            )
        normalized[workflow_name] = HiddenContextRule(
            workflow_name=workflow_name,
            parameter_name=parameter_name,
            phase_identity=_require_non_empty_string(
                raw_rule.get("phase_identity"),
                f"hidden_context_rules[{index}].phase_identity",
                path=path,
            ),
        )
    return normalized


def _normalize_typed_prompt_input_rows(
    raw_value: object,
    *,
    target_workflows: frozenset[str],
    path: Path,
) -> Mapping[tuple[str, str], Mapping[str, Any]]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message="typed_prompt_input_rows must be an array when present",
            path=path,
        )
    normalized: dict[tuple[str, str], Mapping[str, Any]] = {}
    row_ids_by_profile: set[tuple[str, str]] = set()
    for index, raw_row in enumerate(raw_value):
        if not isinstance(raw_row, Mapping):
            raise _profile_error(
                code="workflow_family_profile_schema_invalid",
                message=f"typed_prompt_input_rows[{index}] must be an object",
                path=path,
            )
        workflow_name = _require_non_empty_string(
            raw_row.get("workflow_name"),
            f"typed_prompt_input_rows[{index}].workflow_name",
            path=path,
        )
        _require_target_workflow(workflow_name, target_workflows=target_workflows, path=path)
        provider_binding = _require_non_empty_string(
            raw_row.get("provider_binding"),
            f"typed_prompt_input_rows[{index}].provider_binding",
            path=path,
        )
        normalized_row = normalize_typed_prompt_input_entry(
            {
                "schema_version": raw_row.get("schema_version", "workflow_lisp_typed_prompt_input.v1"),
                "binding_name": raw_row.get("binding_name"),
                "renderer": raw_row.get("renderer"),
                "value_source": raw_row.get("value_source"),
                "value_type_name": raw_row.get("value_type_name"),
                "source_map_origin_key": raw_row.get("source_map_origin_key"),
                "u0_row_id": raw_row.get("u0_row_id"),
                "c0_row_id": raw_row.get("c0_row_id"),
                "injection_order": raw_row.get("injection_order"),
                "preserve_request_record": raw_row.get("preserve_request_record"),
                "request_fields": raw_row.get("request_fields"),
            }
        )
        row_id_key = (
            str(normalized_row["u0_row_id"]),
            str(normalized_row["c0_row_id"]),
        )
        if row_id_key in row_ids_by_profile:
            raise _profile_error(
                code="workflow_family_profile_prompt_row_duplicate",
                message=(
                    "workflow family profile reuses typed prompt row ids "
                    f"{row_id_key[0]} / {row_id_key[1]}"
                ),
                path=path,
            )
        row_ids_by_profile.add(row_id_key)
        binding_key = (workflow_name, provider_binding)
        if binding_key in normalized:
            raise _profile_error(
                code="workflow_family_profile_prompt_row_duplicate",
                message=(
                    "workflow family profile reuses typed prompt binding "
                    f"`{workflow_name}` / `{provider_binding}`"
                ),
                path=path,
            )
        normalized[binding_key] = normalized_row
    return normalized


def _validate_catalog_ambiguity(profiles: Iterable[WorkflowFamilyProfile]) -> None:
    seen_targets: dict[str, WorkflowFamilyProfile] = {}
    for profile in profiles:
        for workflow_name in profile.target_workflows:
            existing = seen_targets.get(workflow_name)
            if existing is None:
                seen_targets[workflow_name] = profile
                continue
            raise _profile_error(
                code="workflow_family_profile_ambiguous",
                message=(
                    f"workflow `{workflow_name}` appears in multiple workflow family profiles: "
                    f"{existing.family_id}, {profile.family_id}"
                ),
                path=profile.source_path,
            )


def _normalize_optional_relpath(
    raw_value: object,
    *,
    field_name: str,
    path: Path,
) -> Path | None:
    if raw_value is None:
        return None
    value = _require_non_empty_string(raw_value, field_name, path=path)
    return (path.parent / value).resolve()


def _normalize_string_list(
    raw_value: object,
    *,
    field_name: str,
    path: Path,
) -> tuple[str, ...]:
    if not isinstance(raw_value, Sequence) or isinstance(raw_value, (str, bytes)):
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message=f"{field_name} must be an array of strings",
            path=path,
        )
    values = tuple(
        _require_non_empty_string(item, f"{field_name}[]", path=path)
        for item in raw_value
    )
    if len(set(values)) != len(values):
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message=f"{field_name} must not contain duplicate values",
            path=path,
        )
    return values


def _require_non_empty_string(
    value: object,
    field_name: str,
    *,
    path: Path,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _profile_error(
            code="workflow_family_profile_schema_invalid",
            message=f"{field_name} must be a non-empty string",
            path=path,
        )
    return value


def _require_target_workflow(
    workflow_name: str,
    *,
    target_workflows: frozenset[str],
    path: Path,
) -> None:
    if workflow_name not in target_workflows:
        raise _profile_error(
            code="workflow_family_profile_target_unknown",
            message=(
                f"workflow family profile references workflow `{workflow_name}` "
                "outside its declared target_workflows"
            ),
            path=path,
        )


def _profile_error(*, code: str, message: str, path: Path) -> LispFrontendCompileError:
    position = SourcePosition(path=str(path), line=1, column=1, offset=0)
    return LispFrontendCompileError(
        (
            LispFrontendDiagnostic(
                code=code,
                message=message,
                span=SourceSpan(start=position, end=position),
                phase="workflow_family_profile",
            ),
        )
    )


def _sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
