"""Fixture-only runtime-closure rejection helpers.

This module models rejected runtime-closure shapes as test data only. It must
not participate in ordinary Workflow Lisp compilation, lowering, or execution.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
import yaml

from .diagnostics import LispFrontendDiagnostic, with_diagnostic_metadata
from .spans import SourcePosition, SourceSpan


@dataclass(frozen=True)
class RuntimeClosureFixtureLocation:
    """One authored location referenced by a runtime-closure fixture case."""

    label: str
    path: str
    line: int
    column: int
    form_path: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuntimeClosureFixtureCase:
    """One fixture-only rejected runtime-closure case."""

    fixture_id: str
    profile: str
    validation_surface: str
    case_kind: str
    payload: Mapping[str, object]
    primary_location: RuntimeClosureFixtureLocation
    expected_code: str
    expected_message_contains: tuple[str, ...] = ()
    expected_stage3_selector: str | None = None
    creation_location: RuntimeClosureFixtureLocation | None = None
    invocation_location: RuntimeClosureFixtureLocation | None = None
    family_declaration_location: RuntimeClosureFixtureLocation | None = None
    code_body_location: RuntimeClosureFixtureLocation | None = None
    accepted_family_location: RuntimeClosureFixtureLocation | None = None
    effect_bound_location: RuntimeClosureFixtureLocation | None = None
    capability_bound_location: RuntimeClosureFixtureLocation | None = None
    write_root_policy_location: RuntimeClosureFixtureLocation | None = None
    resume_validation_location: RuntimeClosureFixtureLocation | None = None
    capture_locations: tuple[RuntimeClosureFixtureLocation, ...] = ()


_FIXTURE_CODE_METADATA = {
    "runtime_closure_not_enabled": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_family_unknown": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_code_id_invalid": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_signature_invalid": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_dynamic_code_forbidden": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_provider_capture_forbidden": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_capture_mode_forbidden": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_capture_schema_invalid": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_runtime_transport_forbidden": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_effect_bound_invalid": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_capability_bound_invalid": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_write_root_ambiguous": {
        "validation_pass": "type",
        "authority_layer": "frontend",
    },
    "closure_resume_bundle_mismatch": {
        "validation_pass": "executable",
        "authority_layer": "frontend",
    },
    "closure_resume_code_mismatch": {
        "validation_pass": "executable",
        "authority_layer": "frontend",
    },
    "closure_source_map_missing": {
        "validation_pass": "source_map",
        "authority_layer": "frontend",
    },
}

_CASE_KIND_LOCATION_FIELDS = {
    "runtime_value": (),
    "invocation": ("creation_location", "invocation_location"),
    "dynamic_code": (),
    "transport": (),
    "capture": ("capture_locations",),
    "effect_bound": (
        "creation_location",
        "invocation_location",
        "effect_bound_location",
    ),
    "capability_bound": (
        "creation_location",
        "invocation_location",
        "capability_bound_location",
    ),
    "write_root_policy": ("write_root_policy_location",),
    "resume": ("resume_validation_location",),
    "source_map": (
        "creation_location",
        "invocation_location",
        "resume_validation_location",
    ),
}


def load_runtime_closure_fixture_cases(path: Path) -> tuple[RuntimeClosureFixtureCase, ...]:
    """Load the runtime-closure disabled-profile case matrix from YAML."""

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, Mapping):
        raise ValueError(f"{path}: expected top-level mapping")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list):
        raise ValueError(f"{path}: expected `cases` list")
    return tuple(
        _case_from_mapping(index, raw_case, path)
        for index, raw_case in enumerate(raw_cases)
    )


def validate_runtime_closure_fixture_case(
    case: RuntimeClosureFixtureCase,
) -> tuple[LispFrontendDiagnostic, ...]:
    """Validate one rejected runtime-closure fixture case.

    This validator only models fixture-owned rejection behavior. It does not
    compile, lower, or execute workflows.
    """

    if case.validation_surface != "fixture_validator":
        selector = case.expected_stage3_selector or "<unknown selector>"
        raise ValueError(
            "runtime closure fixture case is owned by "
            f"{case.validation_surface}: {selector}"
        )
    metadata = _FIXTURE_CODE_METADATA.get(case.expected_code)
    if metadata is None:
        raise ValueError(
            f"unsupported runtime-closure fixture diagnostic `{case.expected_code}` "
            f"for `{case.fixture_id}`"
        )
    diagnostic = LispFrontendDiagnostic(
        code=case.expected_code,
        message=_message_for_case(case),
        span=_span_from_location(case.primary_location),
        form_path=case.primary_location.form_path,
        notes=_notes_for_case(case),
    )
    return (
        with_diagnostic_metadata(
            diagnostic,
            validation_pass=metadata["validation_pass"],
            authority_layer=metadata["authority_layer"],
        ),
    )


def render_runtime_closure_fixture_location(
    location: RuntimeClosureFixtureLocation,
) -> str:
    """Render one fixture location in stable `path:line:column` form."""

    return f"{location.path}:{location.line}:{location.column}"


def _case_from_mapping(
    index: int,
    raw_case: object,
    path: Path,
) -> RuntimeClosureFixtureCase:
    if not isinstance(raw_case, Mapping):
        raise ValueError(f"{path}: case {index} must be a mapping")
    fixture_id = _require_str(raw_case, "fixture_id", path, f"case[{index}]")
    context = fixture_id
    payload = _require_mapping(raw_case, "payload", path, context)
    case = RuntimeClosureFixtureCase(
        fixture_id=fixture_id,
        profile=_require_str(raw_case, "profile", path, context),
        validation_surface=_require_str(raw_case, "validation_surface", path, context),
        case_kind=_require_str(raw_case, "case_kind", path, context),
        payload=dict(payload),
        primary_location=_location_from_mapping(
            _require_mapping(raw_case, "primary_location", path, context),
            path,
            context,
            "primary_location",
        ),
        expected_code=_require_str(raw_case, "expected_code", path, context),
        expected_message_contains=_tuple_of_strings(
            raw_case.get("expected_message_contains", ()),
            path,
            context,
            "expected_message_contains",
        ),
        expected_stage3_selector=_optional_str(raw_case.get("expected_stage3_selector"), path, context, "expected_stage3_selector"),
        creation_location=_optional_location(raw_case.get("creation_location"), path, context, "creation_location"),
        invocation_location=_optional_location(raw_case.get("invocation_location"), path, context, "invocation_location"),
        family_declaration_location=_optional_location(
            raw_case.get("family_declaration_location"),
            path,
            context,
            "family_declaration_location",
        ),
        code_body_location=_optional_location(raw_case.get("code_body_location"), path, context, "code_body_location"),
        accepted_family_location=_optional_location(
            raw_case.get("accepted_family_location"),
            path,
            context,
            "accepted_family_location",
        ),
        effect_bound_location=_optional_location(
            raw_case.get("effect_bound_location"),
            path,
            context,
            "effect_bound_location",
        ),
        capability_bound_location=_optional_location(
            raw_case.get("capability_bound_location"),
            path,
            context,
            "capability_bound_location",
        ),
        write_root_policy_location=_optional_location(
            raw_case.get("write_root_policy_location"),
            path,
            context,
            "write_root_policy_location",
        ),
        resume_validation_location=_optional_location(
            raw_case.get("resume_validation_location"),
            path,
            context,
            "resume_validation_location",
        ),
        capture_locations=_location_sequence(
            raw_case.get("capture_locations", ()),
            path,
            context,
            "capture_locations",
        ),
    )
    _validate_case_shape(case, path)
    return case


def _validate_case_shape(case: RuntimeClosureFixtureCase, path: Path) -> None:
    if case.case_kind not in _CASE_KIND_LOCATION_FIELDS:
        raise ValueError(
            f"{path}: fixture `{case.fixture_id}` uses unsupported case_kind "
            f"`{case.case_kind}`"
        )
    if case.validation_surface == "baseline_stage3_selector":
        if not case.expected_stage3_selector:
            raise ValueError(
                f"{path}: fixture `{case.fixture_id}` must record "
                "`expected_stage3_selector` for baseline-owned rows"
            )
        return
    if case.validation_surface != "fixture_validator":
        raise ValueError(
            f"{path}: fixture `{case.fixture_id}` uses unsupported "
            f"validation_surface `{case.validation_surface}`"
        )
    if case.expected_code not in _FIXTURE_CODE_METADATA:
        raise ValueError(
            f"{path}: fixture `{case.fixture_id}` uses unsupported expected_code "
            f"`{case.expected_code}`"
        )
    for field_name in _CASE_KIND_LOCATION_FIELDS[case.case_kind]:
        value = getattr(case, field_name)
        if value is None or value == ():
            raise ValueError(
                f"{path}: fixture `{case.fixture_id}` requires `{field_name}` "
                f"for case_kind `{case.case_kind}`"
            )
    if case.expected_code == "closure_family_unknown" and case.accepted_family_location is None:
        raise ValueError(
            f"{path}: fixture `{case.fixture_id}` requires "
            "`accepted_family_location`"
        )
    if case.expected_code == "closure_code_id_invalid":
        if case.family_declaration_location is None or case.code_body_location is None:
            raise ValueError(
                f"{path}: fixture `{case.fixture_id}` requires family and code-body "
                "locations for `closure_code_id_invalid`"
            )
    if case.expected_code == "closure_resume_code_mismatch" and case.code_body_location is None:
        raise ValueError(
            f"{path}: fixture `{case.fixture_id}` requires `code_body_location`"
        )


def _message_for_case(case: RuntimeClosureFixtureCase) -> str:
    payload = case.payload
    channel = str(payload.get("channel", "runtime channel")).replace("_", " ")
    producer = str(payload.get("producer", "dynamic"))
    messages = {
        "runtime_closure_not_enabled": (
            f"runtime closures remain disabled in profile `{case.profile}` for "
            f"`{case.fixture_id}`"
        ),
        "closure_family_unknown": (
            f"closure family `{payload.get('closure_family', 'unknown')}` is not in the "
            "accepted family list for this invocation site"
        ),
        "closure_code_id_invalid": (
            f"closure code id `{payload.get('code_id', 'unknown')}` is not accepted by "
            f"family `{payload.get('closure_family', 'unknown')}`"
        ),
        "closure_signature_invalid": (
            "closure signature does not match the invocation site contract"
        ),
        "closure_dynamic_code_forbidden": (
            f"{producer} produced code cannot become a runtime closure"
        ),
        "closure_provider_capture_forbidden": (
            "provider role capture is forbidden for runtime closures in V1"
        ),
        "closure_capture_mode_forbidden": (
            f"capture mode `{payload.get('capture_mode', 'unknown')}` is forbidden "
            "for this runtime closure"
        ),
        "closure_capture_schema_invalid": (
            "captured values do not match the closure capture schema"
        ),
        "closure_runtime_transport_forbidden": (
            f"runtime closure transport through {channel} is forbidden"
        ),
        "closure_effect_bound_invalid": (
            "closure effect bound exceeds the invocation site bound"
        ),
        "closure_capability_bound_invalid": (
            "closure capability bound exceeds the invocation site bound"
        ),
        "closure_write_root_ambiguous": (
            "deterministic write root policy is ambiguous for this closure invocation"
        ),
        "closure_resume_bundle_mismatch": (
            "runtime closure cannot resume under the current executable bundle id"
        ),
        "closure_resume_code_mismatch": (
            "runtime closure code identity changed and cannot resume"
        ),
        "closure_source_map_missing": (
            "runtime closure creation or invocation is missing required source map coverage"
        ),
    }
    message = messages[case.expected_code]
    for fragment in case.expected_message_contains:
        if fragment not in message:
            message = f"{message}; {fragment}"
    return message


def _notes_for_case(case: RuntimeClosureFixtureCase) -> tuple[str, ...]:
    notes: list[str] = []
    optional_locations = (
        ("creation_location", "closure creation site"),
        ("invocation_location", "closure invocation site"),
        ("accepted_family_location", "accepted family list"),
        ("family_declaration_location", "closure family declaration"),
        ("code_body_location", "closure code body"),
        ("effect_bound_location", "accepted effect bound"),
        ("capability_bound_location", "accepted capability bound"),
        ("write_root_policy_location", "write-root policy"),
        ("resume_validation_location", "resume validation"),
    )
    for field_name, label in optional_locations:
        location = getattr(case, field_name)
        if location is not None:
            notes.append(f"{label}: {render_runtime_closure_fixture_location(location)}")
    for capture_location in case.capture_locations:
        notes.append(
            "capture site: "
            f"{render_runtime_closure_fixture_location(capture_location)}"
        )
    if case.expected_stage3_selector is not None:
        notes.append(f"baseline selector: {case.expected_stage3_selector}")
    return tuple(notes)


def _span_from_location(location: RuntimeClosureFixtureLocation) -> SourceSpan:
    start = SourcePosition(
        path=location.path,
        line=location.line,
        column=location.column,
        offset=0,
    )
    end = SourcePosition(
        path=location.path,
        line=location.line,
        column=location.column + 1,
        offset=1,
    )
    return SourceSpan(start=start, end=end)


def _location_from_mapping(
    value: Mapping[str, object],
    path: Path,
    fixture_id: str,
    field_name: str,
) -> RuntimeClosureFixtureLocation:
    return RuntimeClosureFixtureLocation(
        label=_require_str(value, "label", path, fixture_id, field_name),
        path=_require_str(value, "path", path, fixture_id, field_name),
        line=_require_int(value, "line", path, fixture_id, field_name),
        column=_require_int(value, "column", path, fixture_id, field_name),
        form_path=_tuple_of_strings(
            value.get("form_path", ()),
            path,
            fixture_id,
            f"{field_name}.form_path",
        ),
    )


def _optional_location(
    value: object,
    path: Path,
    fixture_id: str,
    field_name: str,
) -> RuntimeClosureFixtureLocation | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{path}: fixture `{fixture_id}` field `{field_name}` must be a mapping"
        )
    return _location_from_mapping(value, path, fixture_id, field_name)


def _location_sequence(
    value: object,
    path: Path,
    fixture_id: str,
    field_name: str,
) -> tuple[RuntimeClosureFixtureLocation, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"{path}: fixture `{fixture_id}` field `{field_name}` must be a list"
        )
    locations: list[RuntimeClosureFixtureLocation] = []
    for index, item in enumerate(value):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"{path}: fixture `{fixture_id}` field `{field_name}[{index}]` "
                "must be a mapping"
            )
        locations.append(
            _location_from_mapping(item, path, fixture_id, f"{field_name}[{index}]")
        )
    return tuple(locations)


def _require_mapping(
    payload: Mapping[str, object],
    field_name: str,
    path: Path,
    fixture_id: str,
) -> Mapping[str, object]:
    value = payload.get(field_name)
    if not isinstance(value, Mapping):
        raise ValueError(
            f"{path}: fixture `{fixture_id}` field `{field_name}` must be a mapping"
        )
    return value


def _require_str(
    payload: Mapping[str, object],
    field_name: str,
    path: Path,
    fixture_id: str,
    parent_field_name: str | None = None,
) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        prefix = f"{parent_field_name}." if parent_field_name else ""
        raise ValueError(
            f"{path}: fixture `{fixture_id}` field `{prefix}{field_name}` must be a "
            "non-empty string"
        )
    return value


def _optional_str(
    value: object,
    path: Path,
    fixture_id: str,
    field_name: str,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"{path}: fixture `{fixture_id}` field `{field_name}` must be a "
            "non-empty string when present"
        )
    return value


def _require_int(
    payload: Mapping[str, object],
    field_name: str,
    path: Path,
    fixture_id: str,
    parent_field_name: str | None = None,
) -> int:
    value = payload.get(field_name)
    if not isinstance(value, int):
        prefix = f"{parent_field_name}." if parent_field_name else ""
        raise ValueError(
            f"{path}: fixture `{fixture_id}` field `{prefix}{field_name}` must be an int"
        )
    return value


def _tuple_of_strings(
    value: object,
    path: Path,
    fixture_id: str,
    field_name: str,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"{path}: fixture `{fixture_id}` field `{field_name}` must be a list of strings"
        )
    items: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise ValueError(
                f"{path}: fixture `{fixture_id}` field `{field_name}` must contain only strings"
            )
        items.append(item)
    return tuple(items)
