"""Frozen neutral static configuration for one run-reference effect site."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
from pathlib import PurePosixPath
import re
from typing import Any, TypeAlias

from orchestrator.workflow.type_descriptor import (
    validate_compiler_normalized_type_descriptor,
)
from .contracts import canonical_json_bytes, canonical_sha256
from .result_contract import (
    RUN_REF_RESULT_CONTRACT_SCHEMA,
    is_transportable_type_descriptor,
    validate_run_ref_result_descriptor,
)
from .source import SourceRequest, canonical_source_request, source_request_from_dict


RUN_REF_STATIC_CONFIG_SCHEMA = "run_ref_static_config.v1"
RUN_REF_BUNDLE_CAPSULE_BINDING_SCHEMA = "run_ref_bundle_capsule_binding.v1"
_DEFAULT_TARGET_DSL_VERSION = "2.24"
_SUPPORTED_TARGET_DSL_VERSIONS = frozenset({"2.24", "2.25", "2.26"})
_LOWERING_ROUTE = "wcc_m4"
_LOWERING_SCHEMA_VERSION = 2
_PATH_ENVIRONMENT = "deterministic-effect-free"
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SITE_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_INPUT_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_STATIC_NAME_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_.-]*(?:(?:::|/)[A-Za-z_][A-Za-z0-9_.-]*)*\Z"
)
_REFERENCE_RE = re.compile(
    r"[A-Za-z_][A-Za-z0-9_-]*(?:\.[A-Za-z_][A-Za-z0-9_-]*)*\Z"
)


def _supports_nested_structural_transport(target_dsl_version: str) -> bool:
    """Return whether one validated target admits nested record/union transport."""

    from orchestrator.workflow_lisp.syntax import (
        target_dsl_supports_nested_structural_transport,
    )

    return target_dsl_supports_nested_structural_transport(target_dsl_version)


@dataclass(frozen=True)
class RunRefBundleCapsuleBinding:
    """Parent-owned content identity for one compiled mode-1 capsule."""

    capsule_digest: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capsule_digest, str)
            or _SHA256_RE.fullmatch(self.capsule_digest) is None
        ):
            raise ValueError(
                "run-ref bundle capsule digest must be sha256:<64 lowercase hex>"
            )

    @property
    def record(self) -> dict[str, str]:
        return {
            "schema_version": RUN_REF_BUNDLE_CAPSULE_BINDING_SCHEMA,
            "capsule_digest": self.capsule_digest,
        }


def validate_run_ref_bundle_capsule_binding(value: object) -> None:
    """Require an exact typed binding whose record matches its fields."""

    if type(value) is not RunRefBundleCapsuleBinding:
        raise TypeError(
            "run-ref bundle capsule authority requires "
            "RunRefBundleCapsuleBinding"
        )
    reconstructed = RunRefBundleCapsuleBinding(
        capsule_digest=value.record["capsule_digest"],
    )
    if reconstructed != value:
        raise ValueError(
            "run-ref bundle capsule authority does not match canonical fields"
        )


def _require_exact_keys(
    value: object,
    expected: set[str],
    *,
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    if set(value) != expected:
        raise ValueError(f"{context} has missing or extra fields")
    return value


def _require_static_name(value: object, *, context: str) -> str:
    if not isinstance(value, str) or _STATIC_NAME_RE.fullmatch(value) is None:
        raise ValueError(f"{context} must be a static non-empty name")
    return value


@dataclass(frozen=True)
class LiteralBinding:
    value: str | int | float | bool | None

    def __post_init__(self) -> None:
        if not isinstance(self.value, (str, int, float, bool, type(None))):
            raise TypeError("literal input binding must contain a JSON scalar")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("literal input binding must be finite")

    @property
    def record(self) -> dict[str, object]:
        return {"kind": "literal", "value": self.value}


@dataclass(frozen=True)
class ReferenceBinding:
    reference: str

    def __post_init__(self) -> None:
        if not isinstance(self.reference, str) or _REFERENCE_RE.fullmatch(
            self.reference
        ) is None:
            raise ValueError("reference input binding must be a canonical dotted name")

    @property
    def record(self) -> dict[str, object]:
        return {"kind": "reference", "reference": self.reference}


@dataclass(frozen=True)
class ArrayBinding:
    items: tuple["InputBinding", ...]

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple) or any(
            not isinstance(item, _BINDING_TYPES) for item in self.items
        ):
            raise TypeError("array input binding items must be immutable bindings")

    @property
    def record(self) -> dict[str, object]:
        return {"kind": "array", "items": [item.record for item in self.items]}


@dataclass(frozen=True)
class ObjectBinding:
    entries: tuple[tuple[str, "InputBinding"], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.entries, tuple):
            raise TypeError("object input binding entries must be a tuple")
        names: set[str] = set()
        for entry in self.entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise TypeError("object input binding entries must be name/binding pairs")
            name, binding = entry
            if not isinstance(name, str) or not name or "\0" in name:
                raise ValueError("object input binding entry name must be non-empty")
            if name in names:
                raise ValueError("object input binding entry names must be unique")
            if not isinstance(binding, _BINDING_TYPES):
                raise TypeError("object input binding entry value must be a binding")
            names.add(name)

    @property
    def record(self) -> dict[str, object]:
        return {
            "kind": "object",
            "entries": [
                {"name": name, "binding": binding.record}
                for name, binding in self.entries
            ],
        }


InputBinding: TypeAlias = (
    LiteralBinding | ReferenceBinding | ArrayBinding | ObjectBinding
)
_BINDING_TYPES = (LiteralBinding, ReferenceBinding, ArrayBinding, ObjectBinding)


def _binding_from_record(value: object, *, context: str) -> InputBinding:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    kind = value.get("kind")
    if kind == "literal":
        row = _require_exact_keys(value, {"kind", "value"}, context=context)
        return LiteralBinding(row["value"])
    if kind == "reference":
        row = _require_exact_keys(
            value,
            {"kind", "reference"},
            context=context,
        )
        return ReferenceBinding(row["reference"])
    if kind == "array":
        row = _require_exact_keys(value, {"kind", "items"}, context=context)
        if not isinstance(row["items"], list):
            raise TypeError(f"{context}.items must be a list")
        return ArrayBinding(
            tuple(
                _binding_from_record(item, context=f"{context}.items[{index}]")
                for index, item in enumerate(row["items"])
            )
        )
    if kind == "object":
        row = _require_exact_keys(value, {"kind", "entries"}, context=context)
        if not isinstance(row["entries"], list):
            raise TypeError(f"{context}.entries must be a list")
        entries: list[tuple[str, InputBinding]] = []
        for index, entry in enumerate(row["entries"]):
            entry_row = _require_exact_keys(
                entry,
                {"name", "binding"},
                context=f"{context}.entries[{index}]",
            )
            if not isinstance(entry_row["name"], str):
                raise TypeError(f"{context}.entries[{index}].name must be a string")
            entries.append(
                (
                    entry_row["name"],
                    _binding_from_record(
                        entry_row["binding"],
                        context=f"{context}.entries[{index}].binding",
                    ),
                )
            )
        return ObjectBinding(tuple(entries))
    raise ValueError(f"{context} uses an unsupported binding kind")


@dataclass(frozen=True, init=False)
class RunRefInput:
    name: str
    binding: InputBinding
    _type_descriptor_json: bytes = field(repr=False)

    def __init__(
        self,
        *,
        name: str,
        type_descriptor: Mapping[str, Any],
        binding: InputBinding,
        allow_nested_structures: bool = False,
    ) -> None:
        if not isinstance(name, str) or _INPUT_NAME_RE.fullmatch(name) is None:
            raise ValueError("run-ref input name must be a canonical static name")
        if not isinstance(binding, _BINDING_TYPES):
            raise TypeError("run-ref input binding must be an immutable binding")
        validate_compiler_normalized_type_descriptor(
            type_descriptor,
            context=f"run_ref_input.{name}.type_descriptor",
        )
        if not is_transportable_type_descriptor(
            type_descriptor,
            allow_nested_structures=allow_nested_structures,
        ):
            raise ValueError("run-ref input type descriptor is not transportable")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "binding", binding)
        object.__setattr__(
            self,
            "_type_descriptor_json",
            canonical_json_bytes(type_descriptor),
        )

    @property
    def type_descriptor(self) -> dict[str, Any]:
        return json.loads(self._type_descriptor_json)

    @property
    def record(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type_descriptor": self.type_descriptor,
            "binding": self.binding.record,
        }


def run_ref_input_identity(row: RunRefInput) -> str:
    """Derive the content identity of one ordered input row without persisting it."""

    if not isinstance(row, RunRefInput):
        raise TypeError("run-ref input identity requires a RunRefInput")
    return canonical_sha256(row.record)


@dataclass(frozen=True)
class BundleProgram:
    workflow_name: str

    def __post_init__(self) -> None:
        _require_static_name(self.workflow_name, context="bundle workflow name")

    @property
    def record(self) -> dict[str, str]:
        return {"mode": "bundle", "workflow_name": self.workflow_name}


@dataclass(frozen=True, init=False)
class PathProgram:
    path: str
    entry_name: str
    environment: str
    _return_refinement_json: bytes | None = field(repr=False)

    def __init__(
        self,
        *,
        path: str,
        entry_name: str,
        return_refinement: Mapping[str, Any] | None = None,
        environment: str = _PATH_ENVIRONMENT,
        allow_nested_structures: bool = False,
    ) -> None:
        if not isinstance(path, str) or not path or "\\" in path:
            raise ValueError("path program path must be a canonical relative path")
        parsed = PurePosixPath(path)
        if (
            parsed.is_absolute()
            or parsed.as_posix() != path
            or any(part in {"", ".", ".."} for part in parsed.parts)
            or parsed.suffix != ".orc"
        ):
            raise ValueError("path program path must be a canonical relative .orc path")
        _require_static_name(entry_name, context="path program entry name")
        if environment != _PATH_ENVIRONMENT:
            raise ValueError("path program environment is not the implemented v1 value")
        if return_refinement is None:
            refinement_json = None
        else:
            validate_compiler_normalized_type_descriptor(
                return_refinement,
                context="run_ref_path_program.return_refinement",
            )
            if not is_transportable_type_descriptor(
                return_refinement,
                allow_nested_structures=allow_nested_structures,
            ):
                raise ValueError("path program return refinement is not transportable")
            refinement_json = canonical_json_bytes(return_refinement)
        object.__setattr__(self, "path", path)
        object.__setattr__(self, "entry_name", entry_name)
        object.__setattr__(self, "environment", environment)
        object.__setattr__(self, "_return_refinement_json", refinement_json)

    @property
    def return_refinement(self) -> dict[str, Any] | None:
        if self._return_refinement_json is None:
            return None
        return json.loads(self._return_refinement_json)

    @property
    def record(self) -> dict[str, object]:
        return {
            "mode": "path",
            "path": self.path,
            "entry_name": self.entry_name,
            "environment": self.environment,
            "return_refinement": self.return_refinement,
        }


RunRefProgram: TypeAlias = BundleProgram | PathProgram


def _program_from_record(
    value: object,
    *,
    allow_nested_structures: bool = False,
) -> RunRefProgram:
    if not isinstance(value, Mapping):
        raise TypeError("run-ref program must be a mapping")
    mode = value.get("mode")
    if mode == "bundle":
        row = _require_exact_keys(
            value,
            {"mode", "workflow_name"},
            context="run-ref bundle program",
        )
        return BundleProgram(row["workflow_name"])
    if mode == "path":
        row = _require_exact_keys(
            value,
            {
                "mode",
                "path",
                "entry_name",
                "environment",
                "return_refinement",
            },
            context="run-ref path program",
        )
        return PathProgram(
            path=row["path"],
            entry_name=row["entry_name"],
            environment=row["environment"],
            return_refinement=row["return_refinement"],
            allow_nested_structures=allow_nested_structures,
        )
    raise ValueError("run-ref program mode is unsupported")


@dataclass(frozen=True, init=False)
class RunRefStaticConfig:
    target_dsl_version: str
    compiler_runtime_identity_digest: str
    site_digest: str
    generated_result_type: str
    source: SourceRequest
    program: RunRefProgram
    inputs: tuple[RunRefInput, ...]
    result_digest: str
    digest: str
    _result_descriptor_json: bytes = field(repr=False)
    _canonical_bytes: bytes = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "RunRefStaticConfig must be created by build_run_ref_static_config "
            "or decode_run_ref_static_config"
        )

    @property
    def result_descriptor(self) -> dict[str, Any]:
        return json.loads(self._result_descriptor_json)

    @property
    def record(self) -> dict[str, Any]:
        return json.loads(self._canonical_bytes)


def build_run_ref_static_config(
    *,
    compiler_runtime_identity_digest: str,
    site_digest: str,
    source: SourceRequest,
    program: RunRefProgram,
    inputs: tuple[RunRefInput, ...],
    result_descriptor: Mapping[str, Any],
    result_digest: str,
    target_dsl_version: str = _DEFAULT_TARGET_DSL_VERSION,
) -> RunRefStaticConfig:
    """Build one immutable, content-addressed static run-ref configuration."""

    if not isinstance(compiler_runtime_identity_digest, str) or _SHA256_RE.fullmatch(
        compiler_runtime_identity_digest
    ) is None:
        raise ValueError("compiler/runtime identity must be sha256:<64 lowercase hex>")
    if not isinstance(site_digest, str) or _SITE_DIGEST_RE.fullmatch(site_digest) is None:
        raise ValueError("run-ref site digest must be 64 lowercase hexadecimal characters")
    if (
        type(target_dsl_version) is not str
        or target_dsl_version not in _SUPPORTED_TARGET_DSL_VERSIONS
    ):
        raise ValueError("run-ref target DSL version is unsupported")
    allow_nested_structures = _supports_nested_structural_transport(
        target_dsl_version
    )
    generated_result_type = f"RunRefResult${site_digest[:16]}"
    if not isinstance(source, SourceRequest):
        raise TypeError("run-ref source must be a SourceRequest")
    if not isinstance(program, (BundleProgram, PathProgram)):
        raise TypeError("run-ref program must be a closed program variant")
    if not isinstance(inputs, tuple) or any(
        not isinstance(row, RunRefInput) for row in inputs
    ):
        raise TypeError("run-ref inputs must be a tuple of RunRefInput rows")
    names = [row.name for row in inputs]
    if len(set(names)) != len(names):
        raise ValueError("run-ref input names must be unique")
    for row in inputs:
        if not is_transportable_type_descriptor(
            row.type_descriptor,
            allow_nested_structures=allow_nested_structures,
        ):
            raise ValueError(
                "run-ref input type descriptor is not transportable for target"
            )
    if isinstance(program, PathProgram) and program.return_refinement is not None:
        if not is_transportable_type_descriptor(
            program.return_refinement,
            allow_nested_structures=allow_nested_structures,
        ):
            raise ValueError(
                "run-ref path return refinement is not transportable for target"
            )
    validate_run_ref_result_descriptor(
        result_descriptor,
        expected_generated_name=generated_result_type,
        expected_digest=result_digest,
        allow_nested_structures=allow_nested_structures,
    )
    if isinstance(program, PathProgram):
        value_descriptor = result_descriptor["envelope"]["fields"][0]["type"]
        refinement = program.return_refinement
        if refinement is None:
            if value_descriptor != {"kind": "primitive", "name": "Value"}:
                raise ValueError(
                    "path program without a return refinement requires Value"
                )
        elif refinement != value_descriptor:
            raise ValueError(
                "path program return refinement does not match the result value"
            )
    source_record = canonical_source_request(source)
    canonical_source = source_request_from_dict(source_record)
    record = {
        "schema_version": RUN_REF_STATIC_CONFIG_SCHEMA,
        "target_dsl_version": target_dsl_version,
        "lowering_route": _LOWERING_ROUTE,
        "lowering_schema_version": _LOWERING_SCHEMA_VERSION,
        "compiler_runtime_identity_digest": compiler_runtime_identity_digest,
        "site_digest": site_digest,
        "generated_result_type": generated_result_type,
        "source": source_record,
        "program": program.record,
        "inputs": [row.record for row in inputs],
        "result_descriptor": dict(result_descriptor),
        "result_digest": result_digest,
    }
    canonical_bytes = canonical_json_bytes(record)
    config = object.__new__(RunRefStaticConfig)
    object.__setattr__(config, "target_dsl_version", target_dsl_version)
    object.__setattr__(
        config,
        "compiler_runtime_identity_digest",
        compiler_runtime_identity_digest,
    )
    object.__setattr__(config, "site_digest", site_digest)
    object.__setattr__(config, "generated_result_type", generated_result_type)
    object.__setattr__(config, "source", canonical_source)
    object.__setattr__(config, "program", program)
    object.__setattr__(config, "inputs", inputs)
    object.__setattr__(config, "result_digest", result_digest)
    object.__setattr__(config, "digest", canonical_sha256(record))
    object.__setattr__(
        config,
        "_result_descriptor_json",
        canonical_json_bytes(result_descriptor),
    )
    object.__setattr__(config, "_canonical_bytes", canonical_bytes)
    return config


def encode_run_ref_static_config(config: RunRefStaticConfig) -> bytes:
    if not isinstance(config, RunRefStaticConfig):
        raise TypeError("run-ref config encoder requires RunRefStaticConfig")
    return bytes(config._canonical_bytes)


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant: {value}")


def decode_run_ref_static_config(payload: bytes) -> RunRefStaticConfig:
    """Decode exact canonical UTF-8 bytes and reconstruct immutable authority."""

    if not isinstance(payload, bytes):
        raise TypeError("run-ref config payload must be bytes")
    text = payload.decode("utf-8", errors="strict")
    value = json.loads(
        text,
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )
    row = _require_exact_keys(
        value,
        {
            "schema_version",
            "target_dsl_version",
            "lowering_route",
            "lowering_schema_version",
            "compiler_runtime_identity_digest",
            "site_digest",
            "generated_result_type",
            "source",
            "program",
            "inputs",
            "result_descriptor",
            "result_digest",
        },
        context="run-ref static config",
    )
    if (
        type(row["target_dsl_version"]) is not str
        or row["target_dsl_version"] not in _SUPPORTED_TARGET_DSL_VERSIONS
    ):
        raise ValueError("run-ref static config target_dsl_version is invalid")
    allow_nested_structures = _supports_nested_structural_transport(
        row["target_dsl_version"]
    )
    fixed = (
        ("schema_version", RUN_REF_STATIC_CONFIG_SCHEMA),
        ("lowering_route", _LOWERING_ROUTE),
        ("lowering_schema_version", _LOWERING_SCHEMA_VERSION),
    )
    for field_name, expected in fixed:
        if row[field_name] != expected or type(row[field_name]) is not type(expected):
            raise ValueError(f"run-ref static config {field_name} is invalid")
    if not isinstance(row["inputs"], list):
        raise TypeError("run-ref static config inputs must be a list")
    inputs: list[RunRefInput] = []
    for index, raw_input in enumerate(row["inputs"]):
        input_row = _require_exact_keys(
            raw_input,
            {"name", "type_descriptor", "binding"},
            context=f"run-ref input[{index}]",
        )
        inputs.append(
            RunRefInput(
                name=input_row["name"],
                type_descriptor=input_row["type_descriptor"],
                binding=_binding_from_record(
                    input_row["binding"],
                    context=f"run-ref input[{index}].binding",
                ),
                allow_nested_structures=allow_nested_structures,
            )
        )
    if not isinstance(row["generated_result_type"], str):
        raise TypeError("run-ref generated result type must be a string")
    config = build_run_ref_static_config(
        compiler_runtime_identity_digest=row["compiler_runtime_identity_digest"],
        site_digest=row["site_digest"],
        source=source_request_from_dict(row["source"]),
        program=_program_from_record(
            row["program"],
            allow_nested_structures=allow_nested_structures,
        ),
        inputs=tuple(inputs),
        result_descriptor=row["result_descriptor"],
        result_digest=row["result_digest"],
        target_dsl_version=row["target_dsl_version"],
    )
    if config.generated_result_type != row["generated_result_type"]:
        raise ValueError("run-ref generated result type does not match site digest")
    if config._canonical_bytes != payload:
        raise ValueError("run-ref static config bytes are not canonical")
    return config


def validate_run_ref_static_config_authority(value: object) -> None:
    """Require one exact static config to match its canonical reconstruction."""

    if type(value) is not RunRefStaticConfig:
        raise TypeError("run-ref static config authority requires RunRefStaticConfig")
    reconstructed = decode_run_ref_static_config(
        encode_run_ref_static_config(value)
    )
    if reconstructed != value:
        raise ValueError("run-ref static config authority does not match canonical bytes")


__all__ = [
    "RUN_REF_BUNDLE_CAPSULE_BINDING_SCHEMA",
    "RUN_REF_RESULT_CONTRACT_SCHEMA",
    "RUN_REF_STATIC_CONFIG_SCHEMA",
    "ArrayBinding",
    "BundleProgram",
    "LiteralBinding",
    "ObjectBinding",
    "PathProgram",
    "ReferenceBinding",
    "RunRefInput",
    "RunRefBundleCapsuleBinding",
    "RunRefStaticConfig",
    "build_run_ref_static_config",
    "decode_run_ref_static_config",
    "encode_run_ref_static_config",
    "run_ref_input_identity",
    "validate_run_ref_static_config_authority",
    "validate_run_ref_bundle_capsule_binding",
    "validate_run_ref_result_descriptor",
]
