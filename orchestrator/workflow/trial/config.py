"""Frozen static configuration for one target-2.25 trial effect site."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json
import math
import re
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from orchestrator.workflow.run_ref.config import (
    RunRefStaticConfig,
    decode_run_ref_static_config,
    validate_run_ref_static_config_authority,
)
from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes, canonical_sha256
from orchestrator.workflow.type_descriptor import (
    validate_compiler_normalized_type_descriptor,
)

if TYPE_CHECKING:
    from orchestrator.workflow.executable_ir import TrialStepConfig


TRIAL_STATIC_CONFIG_SCHEMA = "trial_static_config.v1"
TRIAL_RESULT_CONTRACT_SCHEMA = "workflow_lisp.trial_result_contract.v1"
_DEFAULT_TARGET_DSL_VERSION = "2.25"
_LOWERING_ROUTE = "wcc_m4"
_LOWERING_SCHEMA_VERSION = 2
_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_SITE_DIGEST_RE = re.compile(r"[0-9a-f]{64}\Z")
_RESULT_NAME_RE = re.compile(r"TrialResult\$[0-9a-f]{16}\Z")
_OBSERVATION_INCLUDES = frozenset(
    {
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
        "failure_evidence",
    }
)

def _supports_trial(target_dsl_version: str) -> bool:
    """Return whether one currently admitted target enables static trials."""

    from orchestrator.workflow_lisp.syntax import (
        SUPPORTED_TARGET_DSL_VERSIONS,
        target_dsl_supports_trial,
    )

    return (
        target_dsl_version in SUPPORTED_TARGET_DSL_VERSIONS
        and target_dsl_supports_trial(target_dsl_version)
    )


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("trial static config contains duplicate keys")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ValueError(f"trial static config contains non-finite value {value}")


def _require_exact_mapping(
    value: object,
    keys: set[str],
    *,
    context: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{context} must be a mapping")
    if set(value) != keys:
        raise ValueError(f"{context} has missing or extra fields")
    return value


def _require_positive_int(value: object, *, context: str) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{context} must be a positive integer")
    return value


def _validate_evaluation(value: object) -> dict[str, Any]:
    row = _require_exact_mapping(
        value,
        {
            "checks",
            "provider",
            "rubric_asset",
            "evidence_confidentiality",
            "max_item_bytes",
            "max_packet_bytes",
            "observation_include",
            "diff_cap_bytes",
            "reveal_provider_identity",
            "aggregation_mode",
            "rep_combine",
            "tie",
            "min_abs_improvement",
            "max_cost_ratio",
            "min_cost_reduction",
            "count_failures_as_outcomes",
        },
        context="trial evaluation",
    )
    checks = row["checks"]
    if not isinstance(checks, (list, tuple)):
        raise TypeError("trial evaluation checks must be a sequence")
    normalized_checks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw_check in enumerate(checks):
        check = _require_exact_mapping(
            raw_check,
            {"check_id", "command", "authority", "required", "timeout_ms"},
            context=f"trial check[{index}]",
        )
        check_id = check["check_id"]
        command = check["command"]
        if not isinstance(check_id, str) or not check_id or check_id in seen:
            raise ValueError("trial check ids must be unique non-empty strings")
        if (
            not isinstance(command, (list, tuple))
            or not command
            or any(not isinstance(item, str) or not item for item in command)
        ):
            raise ValueError("trial check command must be non-empty literal argv")
        if check["authority"] not in {"correctness", "invariant"}:
            raise ValueError("trial check authority is invalid")
        if type(check["required"]) is not bool:
            raise TypeError("trial check required flag must be boolean")
        _require_positive_int(check["timeout_ms"], context="trial check timeout")
        seen.add(check_id)
        normalized_checks.append(
            {
                "check_id": check_id,
                "command": list(command),
                "authority": check["authority"],
                "required": check["required"],
                "timeout_ms": check["timeout_ms"],
            }
        )
    for name in ("provider", "rubric_asset"):
        if not isinstance(row[name], str) or not row[name]:
            raise ValueError(f"trial evaluation {name} must be non-empty")
    rubric = PurePosixPath(row["rubric_asset"])
    if (
        rubric.is_absolute()
        or rubric.as_posix() != row["rubric_asset"]
        or any(part in {"", ".", ".."} for part in rubric.parts)
    ):
        raise ValueError("trial evaluation rubric_asset must be normalized and relative")
    if row["evidence_confidentiality"] != "same_trust_boundary":
        raise ValueError("trial evidence confidentiality is invalid")
    max_item_bytes = _require_positive_int(
        row["max_item_bytes"], context="trial max item bytes"
    )
    max_packet_bytes = _require_positive_int(
        row["max_packet_bytes"], context="trial max packet bytes"
    )
    if max_packet_bytes < max_item_bytes:
        raise ValueError("trial packet bytes must cover one item")
    includes = row["observation_include"]
    if not isinstance(includes, (list, tuple)) or any(
        not isinstance(item, str) or item not in _OBSERVATION_INCLUDES
        for item in includes
    ):
        raise ValueError("trial observation include must use the closed vocabulary")
    if len(set(includes)) != len(includes):
        raise ValueError("trial observation include values must be unique")
    _require_positive_int(row["diff_cap_bytes"], context="trial diff cap")
    if row["reveal_provider_identity"] is not False:
        raise ValueError("trial provider identity reveal must be false")
    if row["aggregation_mode"] != "independent_rubric":
        raise ValueError("trial aggregation mode is invalid")
    if row["rep_combine"] != "median":
        raise ValueError("trial repetition combine rule is invalid")
    if row["tie"] != "authored_order":
        raise ValueError("trial tie rule is invalid")
    for name in (
        "min_abs_improvement",
        "max_cost_ratio",
        "min_cost_reduction",
    ):
        if type(row[name]) not in {int, float}:
            raise TypeError(f"trial evaluation {name} must be numeric")
        try:
            numeric_value = float(row[name])
        except OverflowError as exc:
            raise ValueError(f"trial evaluation {name} is outside its range") from exc
        if not math.isfinite(numeric_value):
            raise ValueError(f"trial evaluation {name} must be finite")
        if numeric_value < 0 or (
            name == "max_cost_ratio" and numeric_value <= 0
        ):
            raise ValueError(f"trial evaluation {name} is outside its range")
    if row["count_failures_as_outcomes"] is not True:
        raise ValueError("trial failures must count as outcomes")
    return {
        **dict(row),
        "checks": normalized_checks,
        "observation_include": list(includes),
    }


def _validate_budget(value: object) -> dict[str, int]:
    row = _require_exact_mapping(
        value,
        {
            "arm_timeout_ms",
            "trial_timeout_ms",
            "max_evaluator_attempts",
            "max_evaluator_concurrency",
        },
        context="trial budget",
    )
    normalized = {
        name: _require_positive_int(raw, context=f"trial budget {name}")
        for name, raw in row.items()
    }
    if normalized["max_evaluator_concurrency"] > normalized["max_evaluator_attempts"]:
        raise ValueError("trial evaluator concurrency exceeds attempts")
    return normalized


@dataclass(frozen=True)
class TrialArmStaticConfig:
    """One authored arm ID paired with one exact E1 static configuration."""

    arm_id: str
    run_ref: RunRefStaticConfig

    def __post_init__(self) -> None:
        if not isinstance(self.arm_id, str) or not self.arm_id:
            raise ValueError("trial arm id must be a non-empty string")
        validate_run_ref_static_config_authority(self.run_ref)
        if not _supports_trial(self.run_ref.target_dsl_version):
            raise ValueError("trial arm run-ref must target DSL 2.25 or later")

    @property
    def record(self) -> dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "run_ref": self.run_ref.record,
            "run_ref_config_digest": self.run_ref.digest,
        }


@dataclass(frozen=True, init=False)
class TrialStaticConfig:
    """Immutable content-addressed static authority for one trial site."""

    target_dsl_version: str
    compiler_runtime_identity_digest: str
    site_digest: str
    generated_result_type: str
    arms: tuple[TrialArmStaticConfig, ...]
    reps: int
    max_concurrency: int
    result_digest: str
    arms_digest: str
    evaluation_digest: str
    budget_digest: str
    digest: str
    _evaluation_json: bytes = field(repr=False)
    _budget_json: bytes = field(repr=False)
    _result_descriptor_json: bytes = field(repr=False)
    _canonical_bytes: bytes = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "TrialStaticConfig must be created by build_trial_static_config "
            "or decode_trial_static_config"
        )

    @property
    def evaluation(self) -> dict[str, Any]:
        return json.loads(self._evaluation_json)

    @property
    def budget(self) -> dict[str, int]:
        return json.loads(self._budget_json)

    @property
    def result_descriptor(self) -> dict[str, Any]:
        return json.loads(self._result_descriptor_json)

    @property
    def record(self) -> dict[str, Any]:
        return json.loads(self._canonical_bytes)


def build_trial_static_config(
    *,
    compiler_runtime_identity_digest: str,
    site_digest: str,
    arms: tuple[TrialArmStaticConfig, ...],
    reps: int,
    max_concurrency: int,
    evaluation: Mapping[str, Any],
    budget: Mapping[str, Any],
    result_descriptor: Mapping[str, Any],
    result_digest: str,
    target_dsl_version: str = _DEFAULT_TARGET_DSL_VERSION,
) -> TrialStaticConfig:
    """Build one exact static trial configuration and component identities."""

    if not _supports_trial(target_dsl_version):
        raise ValueError("trial static config requires target DSL 2.25 or later")
    if (
        not isinstance(compiler_runtime_identity_digest, str)
        or _SHA256_RE.fullmatch(compiler_runtime_identity_digest) is None
    ):
        raise ValueError("trial compiler/runtime identity is invalid")
    if not isinstance(site_digest, str) or _SITE_DIGEST_RE.fullmatch(site_digest) is None:
        raise ValueError("trial site digest is invalid")
    if not isinstance(arms, tuple) or not 2 <= len(arms) <= 16 or any(
        not isinstance(arm, TrialArmStaticConfig) for arm in arms
    ):
        raise ValueError("trial requires 2-16 typed static arms")
    arm_ids = tuple(arm.arm_id for arm in arms)
    if len(set(arm_ids)) != len(arm_ids):
        raise ValueError("trial arm ids must be unique")
    if any(arm.run_ref.target_dsl_version != target_dsl_version for arm in arms):
        raise ValueError("trial arm run-ref targets must match the trial target")
    if type(reps) is not int or not 1 <= reps <= 64 or len(arms) * reps > 256:
        raise ValueError("trial repetition count is invalid")
    if (
        type(max_concurrency) is not int
        or not 1 <= max_concurrency <= 32
        or max_concurrency > len(arms) * reps
    ):
        raise ValueError("trial concurrency is invalid")
    normalized_evaluation = _validate_evaluation(evaluation)
    normalized_budget = _validate_budget(budget)
    descriptor_row = _require_exact_mapping(
        result_descriptor,
        {"schema", "envelope"},
        context="trial result descriptor",
    )
    if descriptor_row["schema"] != TRIAL_RESULT_CONTRACT_SCHEMA:
        raise ValueError("trial result descriptor schema is invalid")
    validate_compiler_normalized_type_descriptor(
        descriptor_row["envelope"],
        context="trial_static_config.result_descriptor",
    )
    generated_result_type = descriptor_row["envelope"].get("name")
    if (
        not isinstance(generated_result_type, str)
        or _RESULT_NAME_RE.fullmatch(generated_result_type) is None
        or generated_result_type.removeprefix("TrialResult$") != site_digest[:16]
    ):
        raise ValueError("trial generated result identity is invalid")
    if result_digest != canonical_sha256(dict(descriptor_row)):
        raise ValueError("trial result digest is invalid")
    arm_records = [arm.record for arm in arms]
    arms_digest = canonical_sha256(arm_records)
    evaluation_digest = canonical_sha256(normalized_evaluation)
    schedule_budget = {
        "reps": reps,
        "max_concurrency": max_concurrency,
        "budget": normalized_budget,
    }
    budget_digest = canonical_sha256(schedule_budget)
    record = {
        "schema_version": TRIAL_STATIC_CONFIG_SCHEMA,
        "target_dsl_version": target_dsl_version,
        "lowering_route": _LOWERING_ROUTE,
        "lowering_schema_version": _LOWERING_SCHEMA_VERSION,
        "compiler_runtime_identity_digest": compiler_runtime_identity_digest,
        "site_digest": site_digest,
        "generated_result_type": generated_result_type,
        "arms": arm_records,
        "arms_digest": arms_digest,
        "reps": reps,
        "max_concurrency": max_concurrency,
        "evaluation": normalized_evaluation,
        "evaluation_digest": evaluation_digest,
        "budget": normalized_budget,
        "budget_digest": budget_digest,
        "result_descriptor": dict(descriptor_row),
        "result_digest": result_digest,
    }
    config = object.__new__(TrialStaticConfig)
    for name, value in (
        ("target_dsl_version", target_dsl_version),
        ("compiler_runtime_identity_digest", compiler_runtime_identity_digest),
        ("site_digest", site_digest),
        ("generated_result_type", generated_result_type),
        ("arms", arms),
        ("reps", reps),
        ("max_concurrency", max_concurrency),
        ("result_digest", result_digest),
        ("arms_digest", arms_digest),
        ("evaluation_digest", evaluation_digest),
        ("budget_digest", budget_digest),
        ("digest", canonical_sha256(record)),
    ):
        object.__setattr__(config, name, value)
    object.__setattr__(config, "_evaluation_json", canonical_json_bytes(normalized_evaluation))
    object.__setattr__(config, "_budget_json", canonical_json_bytes(normalized_budget))
    object.__setattr__(config, "_result_descriptor_json", canonical_json_bytes(descriptor_row))
    object.__setattr__(config, "_canonical_bytes", canonical_json_bytes(record))
    return config


def encode_trial_static_config(config: TrialStaticConfig) -> bytes:
    if type(config) is not TrialStaticConfig:
        raise TypeError("trial config encoder requires TrialStaticConfig")
    return bytes(config._canonical_bytes)


def decode_trial_static_config(payload: bytes) -> TrialStaticConfig:
    if not isinstance(payload, bytes):
        raise TypeError("trial static config payload must be bytes")
    value = json.loads(
        payload.decode("utf-8", errors="strict"),
        object_pairs_hook=_reject_duplicate_keys,
        parse_constant=_reject_nonfinite_constant,
    )
    row = _require_exact_mapping(
        value,
        {
            "schema_version",
            "target_dsl_version",
            "lowering_route",
            "lowering_schema_version",
            "compiler_runtime_identity_digest",
            "site_digest",
            "generated_result_type",
            "arms",
            "arms_digest",
            "reps",
            "max_concurrency",
            "evaluation",
            "evaluation_digest",
            "budget",
            "budget_digest",
            "result_descriptor",
            "result_digest",
        },
        context="trial static config",
    )
    if row["schema_version"] != TRIAL_STATIC_CONFIG_SCHEMA:
        raise ValueError("trial static config schema is invalid")
    if row["lowering_route"] != _LOWERING_ROUTE:
        raise ValueError("trial static config lowering route is invalid")
    if row["lowering_schema_version"] != _LOWERING_SCHEMA_VERSION:
        raise ValueError("trial static config lowering schema is invalid")
    if not isinstance(row["arms"], list):
        raise TypeError("trial static config arms must be a list")
    arms: list[TrialArmStaticConfig] = []
    for index, raw_arm in enumerate(row["arms"]):
        arm = _require_exact_mapping(
            raw_arm,
            {"arm_id", "run_ref", "run_ref_config_digest"},
            context=f"trial arm[{index}]",
        )
        run_ref = decode_run_ref_static_config(canonical_json_bytes(arm["run_ref"]))
        if run_ref.digest != arm["run_ref_config_digest"]:
            raise ValueError("trial arm run-ref digest is invalid")
        arms.append(TrialArmStaticConfig(arm_id=arm["arm_id"], run_ref=run_ref))
    config = build_trial_static_config(
        compiler_runtime_identity_digest=row["compiler_runtime_identity_digest"],
        site_digest=row["site_digest"],
        arms=tuple(arms),
        reps=row["reps"],
        max_concurrency=row["max_concurrency"],
        evaluation=row["evaluation"],
        budget=row["budget"],
        result_descriptor=row["result_descriptor"],
        result_digest=row["result_digest"],
        target_dsl_version=row["target_dsl_version"],
    )
    if config.generated_result_type != row["generated_result_type"]:
        raise ValueError("trial static config generated result type is invalid")
    for name in ("arms_digest", "evaluation_digest", "budget_digest"):
        if getattr(config, name) != row[name]:
            raise ValueError(f"trial static config {name} is invalid")
    if encode_trial_static_config(config) != payload:
        raise ValueError("trial static config bytes are not canonical")
    return config


def validate_trial_static_config_authority(value: object) -> None:
    if type(value) is not TrialStaticConfig:
        raise TypeError("trial static config authority requires TrialStaticConfig")
    decoded = decode_trial_static_config(bytes(value._canonical_bytes))
    if decoded != value or decoded.digest != value.digest:
        raise ValueError("trial static config authority disagrees with canonical bytes")


@dataclass(frozen=True, init=False)
class TrialRuntimeRequest:
    """Path-neutral runtime identity for one exact reached trial visit."""

    step_config: TrialStepConfig
    static_config: TrialStaticConfig
    visit: RunRefVisitKey
    cell_domain: tuple[object, ...]
    static_config_digest: str
    trial_step_config_digest: str
    evaluation_digest: str
    budget_digest: str
    result_contract_digest: str
    compiler_runtime_identity_digest: str
    digest: str
    _resolved_inputs_json: bytes = field(repr=False)
    _canonical_bytes: bytes = field(repr=False)

    def __init__(self, *args: object, **kwargs: object) -> None:
        raise TypeError(
            "TrialRuntimeRequest must be created by build_trial_runtime_request"
        )

    @property
    def resolved_inputs_by_arm(self) -> dict[str, dict[str, Any]]:
        rows = json.loads(self._resolved_inputs_json)
        return {row["arm_id"]: row["inputs"] for row in rows}

    @property
    def arm_run_ref_authorities(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {
                "arm_id": arm.arm_id,
                "run_ref_step_config_digest": arm.run_ref.step_config_digest,
                "result_contract_digest": arm.run_ref.run_ref.result_digest,
            }
            for arm in self.step_config.arms
        )

    @property
    def record(self) -> dict[str, Any]:
        return json.loads(self._canonical_bytes)


def build_trial_runtime_request(
    *,
    step_config: TrialStepConfig,
    visit: RunRefVisitKey,
    resolved_inputs_by_arm: Mapping[str, Mapping[str, Any]],
) -> TrialRuntimeRequest:
    """Bind exact parent visit and resolved inputs to existing static identities."""

    from orchestrator.workflow.executable_ir import TrialStepConfig

    from .contracts import TrialCellKey

    if type(step_config) is not TrialStepConfig:
        raise TypeError("trial runtime step config must be exact TrialStepConfig")
    TrialStepConfig(
        common=step_config.common,
        trial=step_config.trial,
        arms=step_config.arms,
    )
    static_config = step_config.trial
    validate_trial_static_config_authority(static_config)
    if type(visit) is not RunRefVisitKey:
        raise TypeError("trial runtime visit must be exact RunRefVisitKey")
    if not isinstance(resolved_inputs_by_arm, Mapping):
        raise TypeError("resolved trial inputs must be a mapping")
    arm_ids = tuple(arm.arm_id for arm in static_config.arms)
    if set(resolved_inputs_by_arm) != set(arm_ids):
        raise ValueError("resolved trial inputs must cover the exact arm domain")
    resolved_rows: list[dict[str, Any]] = []
    for arm in static_config.arms:
        values = resolved_inputs_by_arm[arm.arm_id]
        if not isinstance(values, Mapping) or any(
            not isinstance(name, str) for name in values
        ):
            raise TypeError("resolved trial arm inputs must be string-keyed mappings")
        expected_names = tuple(row.name for row in arm.run_ref.inputs)
        if set(values) != set(expected_names):
            raise ValueError("resolved trial arm inputs disagree with static authority")
        ordered_values = {name: values[name] for name in expected_names}
        try:
            frozen_values = json.loads(canonical_json_bytes(ordered_values))
        except (TypeError, ValueError) as exc:
            raise ValueError("resolved trial arm inputs are not canonical JSON") from exc
        resolved_rows.append({"arm_id": arm.arm_id, "inputs": frozen_values})
    cell_domain = tuple(
        TrialCellKey(arm_id=arm.arm_id, rep=rep)
        for arm in static_config.arms
        for rep in range(1, static_config.reps + 1)
    )
    arm_run_ref_authorities = [
        {
            "arm_id": arm.arm_id,
            "run_ref_step_config_digest": arm.run_ref.step_config_digest,
            "result_contract_digest": arm.run_ref.run_ref.result_digest,
        }
        for arm in step_config.arms
    ]
    record = {
        "schema_version": "trial_runtime_request.v1",
        "trial_static_config_digest": static_config.digest,
        "trial_step_config_digest": step_config.step_config_digest,
        "arm_run_ref_authorities": arm_run_ref_authorities,
        "evaluation_digest": static_config.evaluation_digest,
        "budget_digest": static_config.budget_digest,
        "result_contract_digest": static_config.result_digest,
        "compiler_runtime_identity_digest": (
            static_config.compiler_runtime_identity_digest
        ),
        "visit": visit.record,
        "resolved_inputs_by_arm": resolved_rows,
        "cell_domain": [cell.record for cell in cell_domain],
        "cell_domain_digest": canonical_sha256(
            [cell.record for cell in cell_domain]
        ),
    }
    request = object.__new__(TrialRuntimeRequest)
    for name, value in (
        ("step_config", step_config),
        ("static_config", static_config),
        ("visit", visit),
        ("cell_domain", cell_domain),
        ("static_config_digest", static_config.digest),
        ("trial_step_config_digest", step_config.step_config_digest),
        ("evaluation_digest", static_config.evaluation_digest),
        ("budget_digest", static_config.budget_digest),
        ("result_contract_digest", static_config.result_digest),
        (
            "compiler_runtime_identity_digest",
            static_config.compiler_runtime_identity_digest,
        ),
        ("digest", canonical_sha256(record)),
    ):
        object.__setattr__(request, name, value)
    object.__setattr__(
        request,
        "_resolved_inputs_json",
        canonical_json_bytes(resolved_rows),
    )
    object.__setattr__(request, "_canonical_bytes", canonical_json_bytes(record))
    return request


__all__ = [
    "TRIAL_RESULT_CONTRACT_SCHEMA",
    "TRIAL_STATIC_CONFIG_SCHEMA",
    "TrialArmStaticConfig",
    "TrialRuntimeRequest",
    "TrialStaticConfig",
    "build_trial_runtime_request",
    "build_trial_static_config",
    "decode_trial_static_config",
    "encode_trial_static_config",
    "validate_trial_static_config_authority",
]
