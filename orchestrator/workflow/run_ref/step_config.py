"""Executable config of one run-reference step: `RunRefStepConfig` and its `StepCommonConfig`.

Moved verbatim from `orchestrator/workflow/executable_ir.py`; `empty_frozen_mapping` is a copy of
the helper in `orchestrator/workflow/surface_ast.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping, Optional

from .config import (
    BundleProgram,
    RunRefBundleCapsuleBinding,
    RunRefStaticConfig,
    validate_run_ref_bundle_capsule_binding,
    validate_run_ref_static_config_authority,
)
from .confined_config import (
    RunRefConfinedStaticConfig,
    decode_run_ref_confined_static_config,
    encode_run_ref_confined_static_config,
)
from .contracts import canonical_sha256


RUN_REF_STEP_CONFIG_IDENTITY_SCHEMA = "run_ref_step_config_identity.v1"


def empty_frozen_mapping() -> Mapping[str, Any]:
    """Return an immutable empty mapping."""
    return MappingProxyType({})


def _validate_static_config(config: RunRefStaticConfig | RunRefConfinedStaticConfig) -> None:
    """v1 configs and confined v2 configs (`run_ref_static_config.v2`) match their canonical bytes."""
    if type(config) is RunRefConfinedStaticConfig:
        if decode_run_ref_confined_static_config(encode_run_ref_confined_static_config(config)) != config:
            raise ValueError("confined run-ref static config does not match canonical bytes")
        return
    validate_run_ref_static_config_authority(config)


def _serialize_run_ref_static_config(
    config: RunRefStaticConfig | RunRefConfinedStaticConfig,
) -> dict[str, Any]:
    _validate_static_config(config)
    return config.record


def _serialize_run_ref_capsule_binding(
    binding: RunRefBundleCapsuleBinding,
) -> dict[str, str]:
    validate_run_ref_bundle_capsule_binding(binding)
    return binding.record


@dataclass(frozen=True)
class StepCommonConfig:
    """Runtime-relevant common step fields carried by executable nodes."""

    on: Mapping[str, Any] = field(default_factory=empty_frozen_mapping)
    consumes: tuple[Any, ...] = ()
    consume_bundle: Any = None
    publishes: tuple[Any, ...] = ()
    expected_outputs: tuple[Any, ...] = ()
    output_bundle: Any = None
    variant_output: Any = None
    pre_snapshot: Any = None
    requires_variant: Any = None
    persist_artifacts_in_state: Optional[bool] = None
    provider_session: Optional[Mapping[str, Any]] = None
    max_visits: Optional[int] = None
    retries: Any = None
    env: Optional[Mapping[str, Any]] = None
    secrets: tuple[str, ...] = ()
    timeout_sec: Any = None
    output_capture: Any = None
    output_file: Any = None
    allow_parse_error: Optional[bool] = None


@dataclass(frozen=True)
class RunRefStepConfig:
    """Closed executable config for one pinned child-run reference."""

    common: StepCommonConfig
    run_ref: RunRefStaticConfig | RunRefConfinedStaticConfig = field(
        metadata={"json_serializer": _serialize_run_ref_static_config},
    )
    capsule_binding: RunRefBundleCapsuleBinding | None = field(
        default=None,
        metadata={
            "json_omit_if_none": True,
            "json_serializer": _serialize_run_ref_capsule_binding,
        },
    )

    def __post_init__(self) -> None:
        if type(self.common) is not StepCommonConfig:
            raise TypeError("run_ref executable common config must be StepCommonConfig")
        _validate_static_config(self.run_ref)
        if self.capsule_binding is not None:
            validate_run_ref_bundle_capsule_binding(self.capsule_binding)
            if not isinstance(self.run_ref.program, BundleProgram):
                raise ValueError(
                    "run_ref capsule binding is valid only for a bundle program"
                )

    @property
    def step_config_digest(self) -> str:
        """Bind runtime reuse to both static semantics and capsule content."""

        return canonical_sha256(
            {
                "schema_version": RUN_REF_STEP_CONFIG_IDENTITY_SCHEMA,
                "run_ref_static_config_digest": self.run_ref.digest,
                "capsule_binding": (
                    self.capsule_binding.record
                    if self.capsule_binding is not None
                    else None
                ),
            }
        )
