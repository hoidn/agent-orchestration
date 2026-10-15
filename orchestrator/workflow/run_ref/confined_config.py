"""`run_ref_static_config.v2`: static configuration of one confined `(:workflow <name>)` site.

The `:commit` value is a runtime operand bound into the durable request
(`wire.confined_child_request`), never static configuration.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
from typing import Any

from .config import (
    _LOWERING_ROUTE,
    _LOWERING_SCHEMA_VERSION,
    _SHA256_RE,
    _SITE_DIGEST_RE,
    RunRefInput,
    _binding_from_record,
    _reject_duplicate_keys,
    _reject_nonfinite_constant,
    _require_exact_keys,
    _require_static_name,
    validate_run_ref_result_descriptor,
)
from .contracts import (
    CONFINED_IMAGE_RE,
    RUN_REF_CONFINED_LIMITS,
    RUN_REF_CONFINED_NETWORKS,
    RUN_REF_CONFINEMENT_CONSTANTS_MIB,
    RUN_REF_CONFINEMENT_PROFILE,
    canonical_json_bytes,
    canonical_sha256,
)


RUN_REF_CONFINED_STATIC_CONFIG_SCHEMA = "run_ref_static_config.v2"
_CONFINED_PROGRAM_KEYS = {
    "mode",
    "workflow_name",
    "child_program_digest",
    "owner_configuration_digest",
}
_CONFINED_ENVIRONMENT_KEYS = {
    "profile",
    "image",
    "network",
    "limits",
    "profile_constants_mib",
}
_CONFINED_CONFIG_KEYS = {
    "schema_version",
    "target_dsl_version",
    "lowering_route",
    "lowering_schema_version",
    "compiler_runtime_identity_digest",
    "site_digest",
    "generated_result_type",
    "generated_outcome_type",
    "source",
    "program",
    "environment",
    "inputs",
    "result_descriptor",
    "result_digest",
}


@dataclass(frozen=True)
class ConfinedPolicy:
    """Literal `run_ref_confinement.v1` image, network and ordered limits."""

    image: str
    network: str
    limits: tuple[tuple[str, int], ...]

    def __post_init__(self) -> None:
        if not isinstance(self.image, str) or CONFINED_IMAGE_RE.fullmatch(self.image) is None:
            raise ValueError("confined image must be a repository with a sha256 digest")
        if self.network not in RUN_REF_CONFINED_NETWORKS:
            raise ValueError("confined network must be none or model-only")
        if (
            not isinstance(self.limits, tuple)
            or tuple(row[0] if isinstance(row, tuple) else None for row in self.limits)
            != RUN_REF_CONFINED_LIMITS
            or any(len(row) != 2 or type(row[1]) is not int or row[1] < 1 for row in self.limits)
        ):
            raise ValueError("confined limits must be the six positive integer limits in order")

    @property
    def record(self) -> dict[str, object]:
        return {
            "profile": RUN_REF_CONFINEMENT_PROFILE,
            "image": self.image,
            "network": self.network,
            "limits": [list(row) for row in self.limits],
            "profile_constants_mib": [list(row) for row in RUN_REF_CONFINEMENT_CONSTANTS_MIB],
        }


@dataclass(frozen=True)
class WorkflowProgram:
    """A private child entry compiled into the parent's checked program."""

    workflow_name: str
    child_program_digest: str
    owner_configuration_digest: str

    def __post_init__(self) -> None:
        _require_static_name(self.workflow_name, context="workflow program name")
        for name in ("child_program_digest", "owner_configuration_digest"):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
                raise ValueError(f"workflow program {name} must be sha256:<64 lowercase hex>")

    @property
    def record(self) -> dict[str, str]:
        return {
            "mode": "workflow",
            "workflow_name": self.workflow_name,
            "child_program_digest": self.child_program_digest,
            "owner_configuration_digest": self.owner_configuration_digest,
        }


@dataclass(frozen=True, init=False)
class RunRefConfinedStaticConfig:
    """Static facts of one confined site; the `:commit` value is a runtime operand."""

    target_dsl_version: str
    compiler_runtime_identity_digest: str
    site_digest: str
    generated_result_type: str
    generated_outcome_type: str
    repo: str
    program: WorkflowProgram
    policy: ConfinedPolicy
    inputs: tuple[RunRefInput, ...]
    result_digest: str
    digest: str
    _result_descriptor_json: bytes = field(repr=False)
    _canonical_bytes: bytes = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "RunRefConfinedStaticConfig must be created by "
            "build_run_ref_confined_static_config or "
            "decode_run_ref_confined_static_config"
        )

    @property
    def result_descriptor(self) -> dict[str, Any]:
        return json.loads(self._result_descriptor_json)

    @property
    def outcome_descriptor(self) -> dict[str, Any]:
        """The site type: `COMPLETED (result <envelope>)` or `FAILED (code detail accounting)`."""

        envelope = self.result_descriptor["envelope"]
        accounting = envelope["fields"][2]["type"]
        string = {"kind": "primitive", "name": "String"}
        return {
            "kind": "union",
            "name": self.generated_outcome_type,
            "variants": [
                {"name": "COMPLETED", "fields": [{"name": "result", "type": envelope}]},
                {
                    "name": "FAILED",
                    "fields": [
                        {"name": "code", "type": string},
                        {"name": "detail", "type": string},
                        {"name": "accounting", "type": accounting},
                    ],
                },
            ],
        }

    @property
    def record(self) -> dict[str, Any]:
        return json.loads(self._canonical_bytes)


def build_run_ref_confined_static_config(
    *,
    target_dsl_version: str,
    compiler_runtime_identity_digest: str,
    site_digest: str,
    repo: str,
    program: WorkflowProgram,
    policy: ConfinedPolicy,
    inputs: tuple[RunRefInput, ...],
    result_descriptor: Mapping[str, Any],
    result_digest: str,
) -> RunRefConfinedStaticConfig:
    """Build one immutable `run_ref_static_config.v2` record."""

    from orchestrator.contracts.closed_program.targets import target_dsl_supports_run_ref_confined
    from .source import normalize_repository_locator

    if type(target_dsl_version) is not str or not target_dsl_supports_run_ref_confined(target_dsl_version):
        raise ValueError("confined run-ref target DSL version is unsupported")
    if not isinstance(compiler_runtime_identity_digest, str) or _SHA256_RE.fullmatch(
        compiler_runtime_identity_digest
    ) is None:
        raise ValueError("compiler/runtime identity must be sha256:<64 lowercase hex>")
    if not isinstance(site_digest, str) or _SITE_DIGEST_RE.fullmatch(site_digest) is None:
        raise ValueError("run-ref site digest must be 64 lowercase hexadecimal characters")
    if not isinstance(repo, str) or normalize_repository_locator(repo) != repo:
        raise ValueError("confined run-ref repo must be a normalized literal locator")
    if type(program) is not WorkflowProgram or type(policy) is not ConfinedPolicy:
        raise TypeError("confined run-ref requires a WorkflowProgram and ConfinedPolicy")
    if not isinstance(inputs, tuple) or any(type(row) is not RunRefInput for row in inputs):
        raise TypeError("run-ref inputs must be a tuple of RunRefInput rows")
    names = [row.name for row in inputs]
    if len(set(names)) != len(names):
        raise ValueError("run-ref input names must be unique")
    generated_result_type = f"RunRefResult${site_digest[:16]}"
    validate_run_ref_result_descriptor(
        result_descriptor,
        expected_generated_name=generated_result_type,
        expected_digest=result_digest,
        allow_nested_structures=True,
    )
    record = {
        "schema_version": RUN_REF_CONFINED_STATIC_CONFIG_SCHEMA,
        "target_dsl_version": target_dsl_version,
        "lowering_route": _LOWERING_ROUTE,
        "lowering_schema_version": _LOWERING_SCHEMA_VERSION,
        "compiler_runtime_identity_digest": compiler_runtime_identity_digest,
        "site_digest": site_digest,
        "generated_result_type": generated_result_type,
        "generated_outcome_type": f"RunRefOutcome${site_digest[:16]}",
        "source": {"normalized_locator": repo},
        "program": program.record,
        "environment": policy.record,
        "inputs": [row.record for row in inputs],
        "result_descriptor": dict(result_descriptor),
        "result_digest": result_digest,
    }
    config = object.__new__(RunRefConfinedStaticConfig)
    for name, value in (
        ("target_dsl_version", target_dsl_version),
        ("compiler_runtime_identity_digest", compiler_runtime_identity_digest),
        ("site_digest", site_digest),
        ("generated_result_type", generated_result_type),
        ("generated_outcome_type", record["generated_outcome_type"]),
        ("repo", repo),
        ("program", program),
        ("policy", policy),
        ("inputs", inputs),
        ("result_digest", result_digest),
        ("digest", canonical_sha256(record)),
        ("_result_descriptor_json", canonical_json_bytes(result_descriptor)),
        ("_canonical_bytes", canonical_json_bytes(record)),
    ):
        object.__setattr__(config, name, value)
    return config


def encode_run_ref_confined_static_config(config: RunRefConfinedStaticConfig) -> bytes:
    if type(config) is not RunRefConfinedStaticConfig:
        raise TypeError("confined run-ref config encoder requires RunRefConfinedStaticConfig")
    return bytes(config._canonical_bytes)


def decode_run_ref_confined_static_config(payload: bytes) -> RunRefConfinedStaticConfig:
    """Decode exact canonical v2 bytes; v1, mixed and unknown records refuse."""

    if not isinstance(payload, bytes):
        raise TypeError("run-ref config payload must be bytes")
    value = json.loads(
        payload.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )
    row = _require_exact_keys(value, _CONFINED_CONFIG_KEYS, context="confined run-ref config")
    if row["schema_version"] != RUN_REF_CONFINED_STATIC_CONFIG_SCHEMA:
        raise ValueError("confined run-ref config schema_version is invalid")
    if row["lowering_route"] != _LOWERING_ROUTE or row["lowering_schema_version"] != _LOWERING_SCHEMA_VERSION or type(
        row["lowering_schema_version"]
    ) is not int:
        raise ValueError("confined run-ref config lowering identity is invalid")
    source = _require_exact_keys(row["source"], {"normalized_locator"}, context="confined run-ref source")
    program = _require_exact_keys(row["program"], _CONFINED_PROGRAM_KEYS, context="confined run-ref program")
    if program["mode"] != "workflow":
        raise ValueError("confined run-ref program mode must be workflow")
    environment = _require_exact_keys(
        row["environment"], _CONFINED_ENVIRONMENT_KEYS, context="confined run-ref environment"
    )
    if environment["profile"] != RUN_REF_CONFINEMENT_PROFILE:
        raise ValueError("confined run-ref environment profile is unsupported")
    if environment["profile_constants_mib"] != [list(item) for item in RUN_REF_CONFINEMENT_CONSTANTS_MIB]:
        raise ValueError("confined run-ref profile constants differ from the profile")
    limits = environment["limits"]
    if not isinstance(limits, list) or any(not isinstance(item, list) for item in limits):
        raise ValueError("confined run-ref limits must be ordered pairs")
    if not isinstance(row["inputs"], list):
        raise TypeError("confined run-ref inputs must be a list")
    inputs = []
    for index, raw in enumerate(row["inputs"]):
        item = _require_exact_keys(raw, {"name", "type_descriptor", "binding"}, context=f"run-ref input[{index}]")
        inputs.append(RunRefInput(
            name=item["name"],
            type_descriptor=item["type_descriptor"],
            binding=_binding_from_record(item["binding"], context=f"run-ref input[{index}].binding"),
            allow_nested_structures=True,
        ))
    config = build_run_ref_confined_static_config(
        target_dsl_version=row["target_dsl_version"],
        compiler_runtime_identity_digest=row["compiler_runtime_identity_digest"],
        site_digest=row["site_digest"],
        repo=source["normalized_locator"],
        program=WorkflowProgram(
            workflow_name=program["workflow_name"],
            child_program_digest=program["child_program_digest"],
            owner_configuration_digest=program["owner_configuration_digest"],
        ),
        policy=ConfinedPolicy(
            image=environment["image"],
            network=environment["network"],
            limits=tuple(tuple(item) for item in limits),
        ),
        inputs=tuple(inputs),
        result_descriptor=row["result_descriptor"],
        result_digest=row["result_digest"],
    )
    if config._canonical_bytes != payload:
        raise ValueError("confined run-ref static config bytes are not canonical")
    return config


__all__ = [
    "RUN_REF_CONFINED_STATIC_CONFIG_SCHEMA",
    "ConfinedPolicy",
    "RunRefConfinedStaticConfig",
    "WorkflowProgram",
    "build_run_ref_confined_static_config",
    "decode_run_ref_confined_static_config",
    "encode_run_ref_confined_static_config",
]
