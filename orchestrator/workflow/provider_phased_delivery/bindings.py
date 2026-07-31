"""Exact private semantic bindings for one phased provider attempt."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Mapping, Protocol

from orchestrator._common.canonical import sha256_compact_ascii_json
from orchestrator.providers.interactive_terminal import (
    CloseOfferReceipt,
    FailedCleanupProof,
    InteractiveMemberHandle,
    InteractiveMemberInvocation,
    InteractiveTerminalStartOutcome,
    NaturalShutdownProof,
    NoBackendAllocationProof,
    OfferReceipt,
    PhasedFailedCleanupEvidence,
)
from orchestrator.providers.types import (
    escape_provider_command_token,
    extract_provider_command_placeholders,
    restore_provider_command_token,
)
from orchestrator.workflow.prompting import CanonicalPromptCut
from orchestrator.workflow.provider_attempts import ProviderAttemptScope

from .diagnostics import PhasedDeliveryDiagnostic
from .endpoint import (
    SubmitEndpointEvent,
    SubmitEndpointShutdownOutcome,
)
from .frames import RenderedProtocolTurn
from .models import (
    CandidateDigestManifest,
    CandidateDigestRow,
    PhasedLifecycleState,
    SubmitReceipt,
)
from .protocol import (
    PHASED_PROVIDER_BINDING_ENV,
    PhasedSubmitBinding,
    SubmitEndpointLocator,
)


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")


def _digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical SHA-256 digest")
    return value


def _positive(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise TypeError(f"{field} must be a positive non-Boolean integer")
    return value


def _nonnegative(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise TypeError(f"{field} must be a nonnegative non-Boolean integer")
    return value


def _nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field} must be a non-empty string")
    return value


def _relative_path(value: object) -> str:
    text = _nonempty(value, field="workspace_relative_path")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or "." in path.parts
        or ".." in path.parts
        or path.as_posix() != text
    ):
        raise ValueError(
            "workspace_relative_path must be normalized relative POSIX text"
        )
    return text


@dataclass(frozen=True, slots=True)
class AttemptAllocation:
    """The exact existing attempt identity allocated once by the root owner."""

    scope: ProviderAttemptScope
    attempt_ordinal: int

    def __post_init__(self) -> None:
        if type(self.scope) is not ProviderAttemptScope:
            raise TypeError("scope must be an exact ProviderAttemptScope")
        _positive(self.attempt_ordinal, field="attempt_ordinal")


@dataclass(frozen=True, slots=True)
class AttemptComposition:
    """One canonical cut plus inert attempt-local transport preparation."""

    cut: CanonicalPromptCut
    materialization_attempts: int
    task_turn: RenderedProtocolTurn
    initial_materialization_turn: RenderedProtocolTurn
    pre_prompt_command: tuple[str, ...]
    invocation: InteractiveMemberInvocation
    submit_binding: PhasedSubmitBinding
    endpoint_locator: SubmitEndpointLocator
    deadline: float

    def __post_init__(self) -> None:
        if type(self.cut) is not CanonicalPromptCut:
            raise TypeError("cut must be an exact CanonicalPromptCut")
        attempts = _positive(
            self.materialization_attempts,
            field="materialization_attempts",
        )
        if attempts not in {1, 2, 3}:
            raise ValueError("materialization_attempts must be in 1..3")
        if (
            type(self.task_turn) is not RenderedProtocolTurn
            or self.task_turn.projection.phase != "task"
        ):
            raise TypeError("task_turn must be an exact task turn")
        if (
            type(self.initial_materialization_turn)
            is not RenderedProtocolTurn
            or self.initial_materialization_turn.projection.phase
            != "initial_materialization"
        ):
            raise TypeError(
                "initial_materialization_turn must be exact"
            )
        if self.task_turn.canonical_slice != self.cut.task_slice:
            raise ValueError("task turn disagrees with canonical cut")
        if (
            self.initial_materialization_turn.canonical_slice
            != self.cut.materialization_slice
        ):
            raise ValueError(
                "initial materialization turn disagrees with canonical cut"
            )
        if type(self.invocation) is not InteractiveMemberInvocation:
            raise TypeError(
                "invocation must be an exact InteractiveMemberInvocation"
            )
        if type(self.submit_binding) is not PhasedSubmitBinding:
            raise TypeError(
                "submit_binding must be an exact PhasedSubmitBinding"
            )
        if (
            not isinstance(self.pre_prompt_command, tuple)
            or not self.pre_prompt_command
            or any(
                type(token) is not str or not token
                for token in self.pre_prompt_command
            )
        ):
            raise TypeError(
                "pre_prompt_command must be a non-empty exact string tuple"
            )
        placeholders = tuple(
            placeholder
            for token in self.pre_prompt_command
            for placeholder in extract_provider_command_placeholders(token)
        )
        pre_prompt_indexes = tuple(
            index
            for index, token in enumerate(self.pre_prompt_command)
            if "PROMPT" in extract_provider_command_placeholders(token)
        )
        support_prompt_indexes = tuple(
            index
            for index, token in enumerate(self.invocation.support.command)
            if "PROMPT" in extract_provider_command_placeholders(token)
        )
        if (
            placeholders != ("PROMPT",)
            or pre_prompt_indexes != support_prompt_indexes
        ):
            raise ValueError(
                "pre_prompt_command requires exactly one unresolved PROMPT"
            )
        task_text = self.task_turn.delivered_turn.decode(
            "utf-8",
            errors="strict",
        )
        resolved_command = tuple(
            restore_provider_command_token(
                escape_provider_command_token(token).replace(
                    "${PROMPT}",
                    task_text,
                )
            )
            for token in self.pre_prompt_command
        )
        if (
            resolved_command != self.invocation.resolved_command
        ):
            raise ValueError(
                "invocation prompt carriage must equal the exact task turn"
            )
        if self.invocation.env.get(PHASED_PROVIDER_BINDING_ENV) != (
            self.submit_binding.opaque_value
        ):
            raise ValueError(
                "invocation binding carriage must equal the submit binding"
            )
        initial_submit_keys = (
            self.initial_materialization_turn.projection.submit_keys
        )
        support_submit_keys = (
            self.invocation.support.message_submit_keys
        )
        if (
            initial_submit_keys.count != len(support_submit_keys)
            or initial_submit_keys.sha256
            != sha256_compact_ascii_json(
                list(support_submit_keys),
                allow_nan=False,
            )
        ):
            raise ValueError(
                "initial materialization submit keys disagree with support"
            )
        if type(self.endpoint_locator) is not SubmitEndpointLocator:
            raise TypeError(
                "endpoint_locator must be an exact SubmitEndpointLocator"
            )
        if (
            self.submit_binding.endpoint_instance_id
            != self.endpoint_locator.endpoint_instance_id
            or self.submit_binding.socket_path
            != self.endpoint_locator.socket_path
        ):
            raise ValueError(
                "submit binding and endpoint locator must agree"
            )
        if (
            isinstance(self.deadline, bool)
            or not isinstance(self.deadline, (int, float))
            or self.deadline != self.submit_binding.deadline
        ):
            raise ValueError("deadline must equal the submit binding deadline")


@dataclass(frozen=True, slots=True)
class CandidatePathBinding:
    contract_ordinal: int
    role: str
    logical_name: str
    workspace_relative_path: str

    def __post_init__(self) -> None:
        _nonnegative(self.contract_ordinal, field="contract_ordinal")
        if self.role not in {"expected_output", "structured_bundle"}:
            raise ValueError("candidate path role is invalid")
        _nonempty(self.logical_name, field="logical_name")
        _relative_path(self.workspace_relative_path)
        if (
            self.role == "structured_bundle"
            and self.logical_name != "__structured_result_bundle__"
        ):
            raise ValueError(
                "structured bundle requires its reserved logical name"
            )
        if (
            self.role == "expected_output"
            and self.logical_name == "__structured_result_bundle__"
        ):
            raise ValueError("expected output cannot use the reserved name")

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_ordinal": self.contract_ordinal,
            "role": self.role,
            "logical_name": self.logical_name,
            "workspace_relative_path": self.workspace_relative_path,
        }


@dataclass(frozen=True, slots=True)
class CandidatePreflight:
    bindings: tuple[CandidatePathBinding, ...]
    preflight_sha256: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.bindings, tuple)
            or not self.bindings
            or any(
                type(binding) is not CandidatePathBinding
                for binding in self.bindings
            )
        ):
            raise TypeError(
                "bindings must be a non-empty exact binding tuple"
            )
        if tuple(
            binding.contract_ordinal for binding in self.bindings
        ) != tuple(range(len(self.bindings))):
            raise ValueError("candidate path ordinals must be contiguous")
        structured = tuple(
            index
            for index, binding in enumerate(self.bindings)
            if binding.role == "structured_bundle"
        )
        if structured != (len(self.bindings) - 1,):
            raise ValueError(
                "one structured bundle must be the final candidate binding"
            )
        paths = tuple(
            binding.workspace_relative_path for binding in self.bindings
        )
        if len(set(paths)) != len(paths):
            raise ValueError("candidate paths must be pairwise distinct")
        expected = sha256_compact_ascii_json(
            [binding.to_dict() for binding in self.bindings],
            allow_nan=False,
        )
        if self.preflight_sha256 != expected:
            raise ValueError("preflight_sha256 does not seal the bindings")

    @classmethod
    def create(
        cls,
        *,
        bindings: tuple[CandidatePathBinding, ...],
    ) -> CandidatePreflight:
        if not isinstance(bindings, tuple):
            raise TypeError("bindings must be a tuple")
        return cls(
            bindings=bindings,
            preflight_sha256=sha256_compact_ascii_json(
                [binding.to_dict() for binding in bindings],
                allow_nan=False,
            ),
        )


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    preflight_sha256: str
    submission_ordinal: int
    rows: tuple[CandidateDigestRow, ...]
    snapshot_sha256: str

    def __post_init__(self) -> None:
        _digest(self.preflight_sha256, field="preflight_sha256")
        _positive(self.submission_ordinal, field="submission_ordinal")
        if (
            not isinstance(self.rows, tuple)
            or not self.rows
            or any(type(row) is not CandidateDigestRow for row in self.rows)
        ):
            raise TypeError("rows must be a non-empty exact row tuple")
        if tuple(row.contract_ordinal for row in self.rows) != tuple(
            range(len(self.rows))
        ):
            raise ValueError("snapshot rows must be contiguous")
        binding_shape = [
            {
                "contract_ordinal": row.contract_ordinal,
                "role": row.role,
                "logical_name": row.logical_name,
                "workspace_relative_path": row.workspace_relative_path,
            }
            for row in self.rows
        ]
        if (
            sha256_compact_ascii_json(
                binding_shape,
                allow_nan=False,
            )
            != self.preflight_sha256
        ):
            raise ValueError(
                "snapshot rows disagree with preflight binding identity"
            )
        expected = sha256_compact_ascii_json(
            {
                "preflight_sha256": self.preflight_sha256,
                "submission_ordinal": self.submission_ordinal,
                "rows": [row.to_dict() for row in self.rows],
            },
            allow_nan=False,
        )
        if self.snapshot_sha256 != expected:
            raise ValueError("snapshot_sha256 does not seal the snapshot")

    @classmethod
    def create(
        cls,
        *,
        preflight: CandidatePreflight,
        submission_ordinal: int,
        rows: tuple[CandidateDigestRow, ...],
    ) -> CandidateSnapshot:
        if type(preflight) is not CandidatePreflight:
            raise TypeError("preflight must be an exact CandidatePreflight")
        if tuple(
            (
                row.contract_ordinal,
                row.role,
                row.logical_name,
                row.workspace_relative_path,
            )
            for row in rows
        ) != tuple(
            (
                binding.contract_ordinal,
                binding.role,
                binding.logical_name,
                binding.workspace_relative_path,
            )
            for binding in preflight.bindings
        ):
            raise ValueError("snapshot rows disagree with preflight bindings")
        payload = {
            "preflight_sha256": preflight.preflight_sha256,
            "submission_ordinal": submission_ordinal,
            "rows": [row.to_dict() for row in rows],
        }
        return cls(
            preflight_sha256=preflight.preflight_sha256,
            submission_ordinal=submission_ordinal,
            rows=rows,
            snapshot_sha256=sha256_compact_ascii_json(
                payload,
                allow_nan=False,
            ),
        )

    def manifest(self, disposition: str) -> CandidateDigestManifest:
        return CandidateDigestManifest.create(
            submission_ordinal=self.submission_ordinal,
            disposition=disposition,
            rows=self.rows,
        )


@dataclass(frozen=True, slots=True)
class ValidatedArtifact:
    logical_name: str
    workspace_relative_path: str

    def __post_init__(self) -> None:
        _nonempty(self.logical_name, field="logical_name")
        _relative_path(self.workspace_relative_path)


@dataclass(frozen=True, slots=True)
class ValidatedStructuredResult:
    canonical_bundle: bytes

    def __post_init__(self) -> None:
        if type(self.canonical_bundle) is not bytes or not self.canonical_bundle:
            raise TypeError("canonical_bundle must be non-empty exact bytes")

    @property
    def sha256(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_bundle).hexdigest()


@dataclass(frozen=True, slots=True)
class OutputPositionValidation:
    snapshot_sha256: str
    artifacts: tuple[ValidatedArtifact, ...]
    diagnostic: PhasedDeliveryDiagnostic | None

    def __post_init__(self) -> None:
        _digest(self.snapshot_sha256, field="snapshot_sha256")
        if not isinstance(self.artifacts, tuple) or any(
            type(artifact) is not ValidatedArtifact
            for artifact in self.artifacts
        ):
            raise TypeError("artifacts must be an exact tuple")
        if self.diagnostic is not None and (
            type(self.diagnostic) is not PhasedDeliveryDiagnostic
            or self.diagnostic.reason != "output_validation_failed"
        ):
            raise TypeError(
                "output validation diagnostic must be exact and reason-bound"
            )

    @property
    def valid(self) -> bool:
        return self.diagnostic is None


@dataclass(frozen=True, slots=True)
class StructuredResultValidation:
    snapshot_sha256: str
    result: ValidatedStructuredResult | None
    diagnostic: PhasedDeliveryDiagnostic | None

    def __post_init__(self) -> None:
        _digest(self.snapshot_sha256, field="snapshot_sha256")
        if (self.result is None) == (self.diagnostic is None):
            raise ValueError(
                "structured validation requires exactly one result or diagnostic"
            )
        if self.result is not None and (
            type(self.result) is not ValidatedStructuredResult
        ):
            raise TypeError("result must be exact")
        if self.diagnostic is not None and (
            type(self.diagnostic) is not PhasedDeliveryDiagnostic
            or self.diagnostic.reason
            != "structured_result_validation_failed"
        ):
            raise TypeError(
                "structured validation diagnostic must be exact and reason-bound"
            )

    @property
    def valid(self) -> bool:
        return self.diagnostic is None


@dataclass(frozen=True, slots=True)
class CandidateResetResult:
    snapshot_sha256: str
    preflight_sha256: str
    postcondition: str

    def __post_init__(self) -> None:
        _digest(self.snapshot_sha256, field="snapshot_sha256")
        _digest(self.preflight_sha256, field="preflight_sha256")
        if self.postcondition != "all_bound_paths_absent":
            raise ValueError("candidate reset postcondition is invalid")


@dataclass(frozen=True, slots=True)
class FrozenCandidateFile:
    binding: CandidatePathBinding
    content: bytes

    def __post_init__(self) -> None:
        if type(self.binding) is not CandidatePathBinding:
            raise TypeError("binding must be exact")
        if type(self.content) is not bytes:
            raise TypeError("content must be exact bytes")


@dataclass(frozen=True, slots=True)
class FrozenCandidate:
    snapshot_sha256: str
    manifest: CandidateDigestManifest
    files: tuple[FrozenCandidateFile, ...]
    frozen_sha256: str

    def __post_init__(self) -> None:
        _digest(self.snapshot_sha256, field="snapshot_sha256")
        if (
            type(self.manifest) is not CandidateDigestManifest
            or self.manifest.disposition != "frozen"
        ):
            raise TypeError("manifest must be an exact frozen manifest")
        if (
            not isinstance(self.files, tuple)
            or len(self.files) != len(self.manifest.rows)
            or any(type(item) is not FrozenCandidateFile for item in self.files)
        ):
            raise TypeError("files must be the complete exact frozen tuple")
        for item, row in zip(self.files, self.manifest.rows, strict=True):
            if item.binding.to_dict() != {
                key: row.to_dict()[key]
                for key in (
                    "contract_ordinal",
                    "role",
                    "logical_name",
                    "workspace_relative_path",
                )
            }:
                raise ValueError("frozen file binding disagrees with manifest")
            if (
                row.byte_length != len(item.content)
                or row.sha256
                != "sha256:" + hashlib.sha256(item.content).hexdigest()
            ):
                raise ValueError("frozen file bytes disagree with manifest")
        expected = sha256_compact_ascii_json(
            {
                "snapshot_sha256": self.snapshot_sha256,
                "manifest_sha256": self.manifest.manifest_sha256,
                "files": [
                    {
                        **item.binding.to_dict(),
                        "byte_length": len(item.content),
                        "sha256": (
                            "sha256:" + hashlib.sha256(item.content).hexdigest()
                        ),
                    }
                    for item in self.files
                ],
            },
            allow_nan=False,
        )
        if self.frozen_sha256 != expected:
            raise ValueError("frozen_sha256 does not seal the frozen candidate")

    @classmethod
    def create(
        cls,
        *,
        snapshot: CandidateSnapshot,
        files: tuple[FrozenCandidateFile, ...],
    ) -> FrozenCandidate:
        if type(snapshot) is not CandidateSnapshot:
            raise TypeError("snapshot must be exact")
        manifest = snapshot.manifest("frozen")
        payload = {
            "snapshot_sha256": snapshot.snapshot_sha256,
            "manifest_sha256": manifest.manifest_sha256,
            "files": [
                {
                    **item.binding.to_dict(),
                    "byte_length": len(item.content),
                    "sha256": (
                        "sha256:" + hashlib.sha256(item.content).hexdigest()
                    ),
                }
                for item in files
            ],
        }
        return cls(
            snapshot_sha256=snapshot.snapshot_sha256,
            manifest=manifest,
            files=files,
            frozen_sha256=sha256_compact_ascii_json(
                payload,
                allow_nan=False,
            ),
        )


def _deliveries_sha256(
    actual_deliveries: tuple[RenderedProtocolTurn, ...],
) -> str:
    if (
        not isinstance(actual_deliveries, tuple)
        or len(actual_deliveries) < 2
        or any(
            type(turn) is not RenderedProtocolTurn
            for turn in actual_deliveries
        )
    ):
        raise TypeError(
            "actual_deliveries must be a complete exact turn tuple"
        )
    payload = [
        {
            "delivery_ordinal": turn.projection.delivery_ordinal,
            "phase": turn.projection.phase,
            "submission_ordinal": turn.projection.submission_ordinal,
            "protocol_frame": {
                "bytes": turn.projection.protocol_frame.bytes,
                "sha256": turn.projection.protocol_frame.sha256,
            },
            "canonical_slice": {
                "bytes": turn.projection.canonical_slice.bytes,
                "sha256": turn.projection.canonical_slice.sha256,
            },
            "delivered_turn": {
                "bytes": turn.projection.delivered_turn.bytes,
                "sha256": turn.projection.delivered_turn.sha256,
            },
            "submit_keys": {
                "count": turn.projection.submit_keys.count,
                "sha256": turn.projection.submit_keys.sha256,
            },
        }
        for turn in actual_deliveries
    ]
    return sha256_compact_ascii_json(payload, allow_nan=False)


def _validate_delivery_grammar(
    actual_deliveries: tuple[RenderedProtocolTurn, ...],
) -> int:
    first = actual_deliveries[0].projection
    second = actual_deliveries[1].projection
    if (
        first.phase != "task"
        or first.delivery_ordinal != 0
        or first.submission_ordinal is not None
        or second.phase != "initial_materialization"
        or second.delivery_ordinal != 1
        or second.submission_ordinal != 1
    ):
        raise ValueError("actual delivery grammar is invalid")
    for expected_ordinal, turn in enumerate(
        actual_deliveries[2:],
        start=2,
    ):
        projection = turn.projection
        if (
            projection.phase != "retry_materialization"
            or projection.delivery_ordinal != expected_ordinal
            or projection.submission_ordinal != expected_ordinal
        ):
            raise ValueError("actual delivery grammar is invalid")
    final_submission = actual_deliveries[-1].projection.submission_ordinal
    if final_submission is None:
        raise ValueError("actual delivery grammar has no final submission")
    return final_submission


@dataclass(frozen=True, slots=True)
class FunctionalEvidencePublication:
    frozen_sha256: str
    actual_deliveries_sha256: str
    relative_path: str
    evidence_sha256: str

    def __post_init__(self) -> None:
        _digest(self.frozen_sha256, field="frozen_sha256")
        _digest(
            self.actual_deliveries_sha256,
            field="actual_deliveries_sha256",
        )
        _relative_path(self.relative_path)
        _digest(self.evidence_sha256, field="evidence_sha256")

    @classmethod
    def create(
        cls,
        *,
        frozen: FrozenCandidate,
        actual_deliveries: tuple[RenderedProtocolTurn, ...],
        relative_path: str,
        evidence_sha256: str,
    ) -> FunctionalEvidencePublication:
        if type(frozen) is not FrozenCandidate:
            raise TypeError("frozen must be exact")
        return cls(
            frozen_sha256=frozen.frozen_sha256,
            actual_deliveries_sha256=_deliveries_sha256(actual_deliveries),
            relative_path=relative_path,
            evidence_sha256=evidence_sha256,
        )


@dataclass(frozen=True, slots=True)
class FrozenCandidateRestoration:
    frozen_sha256: str
    restored_paths: int

    def __post_init__(self) -> None:
        _digest(self.frozen_sha256, field="frozen_sha256")
        _nonnegative(self.restored_paths, field="restored_paths")


@dataclass(frozen=True, slots=True)
class FrozenCandidateVerification:
    frozen_sha256: str
    verified: bool

    def __post_init__(self) -> None:
        _digest(self.frozen_sha256, field="frozen_sha256")
        if self.verified is not True:
            raise ValueError("frozen candidate verification must be true")


@dataclass(frozen=True, slots=True)
class AtomicSuccessCommitReceipt:
    evidence_sha256: str
    frozen_sha256: str
    status: str

    def __post_init__(self) -> None:
        _digest(self.evidence_sha256, field="evidence_sha256")
        _digest(self.frozen_sha256, field="frozen_sha256")
        if self.status != "authoritative_state_committed":
            raise ValueError("atomic success commit status is invalid")


@dataclass(frozen=True, slots=True)
class PreparedSuccessCommit:
    allocation: AttemptAllocation
    output: OutputPositionValidation
    structured: StructuredResultValidation
    frozen: FrozenCandidate
    evidence: FunctionalEvidencePublication
    verification: FrozenCandidateVerification

    def __post_init__(self) -> None:
        expected = (
            (self.allocation, AttemptAllocation),
            (self.output, OutputPositionValidation),
            (self.structured, StructuredResultValidation),
            (self.frozen, FrozenCandidate),
            (self.evidence, FunctionalEvidencePublication),
            (self.verification, FrozenCandidateVerification),
        )
        if any(type(value) is not kind for value, kind in expected):
            raise TypeError("prepared success commit fields must be exact")


@dataclass(frozen=True, slots=True)
class SerializedAttemptEvent:
    kind: str
    submit: SubmitEndpointEvent | None = None

    def __post_init__(self) -> None:
        if self.kind not in {
            "submit",
            "provider_exit",
            "interrupted",
            "deadline",
        }:
            raise ValueError("serialized attempt event kind is invalid")
        if self.kind == "submit":
            if type(self.submit) is not SubmitEndpointEvent:
                raise TypeError("submit event requires exact payload")
        elif self.submit is not None:
            raise ValueError("control event forbids submit payload")


@dataclass(frozen=True, slots=True)
class PhasedProviderAttemptSuccess:
    allocation: AttemptAllocation
    lifecycle: PhasedLifecycleState
    submission_ordinal: int
    actual_deliveries: tuple[RenderedProtocolTurn, ...]
    frozen: FrozenCandidate
    evidence: FunctionalEvidencePublication
    commit: AtomicSuccessCommitReceipt

    def __post_init__(self) -> None:
        if type(self.allocation) is not AttemptAllocation:
            raise TypeError("allocation must be exact")
        if (
            type(self.lifecycle) is not PhasedLifecycleState
            or self.lifecycle.phase != "PUBLISHED"
        ):
            raise TypeError("lifecycle must be an exact published state")
        _positive(self.submission_ordinal, field="submission_ordinal")
        deliveries_sha256 = _deliveries_sha256(self.actual_deliveries)
        final_submission = _validate_delivery_grammar(
            self.actual_deliveries
        )
        if type(self.frozen) is not FrozenCandidate:
            raise TypeError("frozen must be exact")
        if (
            self.submission_ordinal != self.frozen.manifest.submission_ordinal
            or self.submission_ordinal != final_submission
        ):
            raise ValueError(
                "submission ordinal must bind frozen and final delivery"
            )
        if (
            type(self.evidence) is not FunctionalEvidencePublication
            or self.evidence.frozen_sha256 != self.frozen.frozen_sha256
            or self.evidence.actual_deliveries_sha256 != deliveries_sha256
        ):
            raise ValueError(
                "evidence must bind the frozen candidate and deliveries"
            )
        if (
            type(self.commit) is not AtomicSuccessCommitReceipt
            or self.commit.evidence_sha256 != self.evidence.evidence_sha256
            or self.commit.frozen_sha256 != self.frozen.frozen_sha256
        ):
            raise ValueError("commit must bind the evidence and frozen candidate")


@dataclass(frozen=True, slots=True)
class PhasedNaturalShutdownEvidence:
    disposition: str
    return_code: int
    pane_absent: bool
    server_absent: bool
    proof_complete: bool

    def __post_init__(self) -> None:
        if (
            self.disposition != "natural_exit"
            or self.return_code != 0
            or self.pane_absent is not True
            or self.server_absent is not True
            or self.proof_complete is not True
        ):
            raise ValueError("natural shutdown evidence must be complete")

    def to_dict(self) -> dict[str, object]:
        return {
            "disposition": self.disposition,
            "return_code": self.return_code,
            "pane_absent": self.pane_absent,
            "server_absent": self.server_absent,
            "proof_complete": self.proof_complete,
        }


@dataclass(frozen=True, slots=True)
class PhasedProviderAttemptFailure:
    allocation: AttemptAllocation
    lifecycle: PhasedLifecycleState
    first_diagnostic: PhasedDeliveryDiagnostic
    cleanup_diagnostic: PhasedDeliveryDiagnostic | None
    provider_cleanup_proof: (
        NoBackendAllocationProof | PhasedFailedCleanupEvidence | None
    )
    endpoint_shutdown_status: str
    natural_shutdown_proof: PhasedNaturalShutdownEvidence | None
    terminalization_tier: str
    frozen: FrozenCandidate | None
    evidence: FunctionalEvidencePublication | None

    def __post_init__(self) -> None:
        if type(self.allocation) is not AttemptAllocation:
            raise TypeError("allocation must be exact")
        if (
            type(self.lifecycle) is not PhasedLifecycleState
            or self.lifecycle.phase != "FAILED"
        ):
            raise TypeError("lifecycle must be an exact failed state")
        if type(self.first_diagnostic) is not PhasedDeliveryDiagnostic:
            raise TypeError("first_diagnostic must be exact")
        if self.cleanup_diagnostic is not None and (
            type(self.cleanup_diagnostic) is not PhasedDeliveryDiagnostic
        ):
            raise TypeError("cleanup_diagnostic must be exact or null")
        if self.endpoint_shutdown_status not in {
            "not_allocated",
            "complete",
            "incomplete",
        }:
            raise ValueError("endpoint_shutdown_status is invalid")
        if self.terminalization_tier not in {
            "T0",
            "T1",
            "T2a",
            "T2b",
            "T3",
            "T4",
        }:
            raise ValueError("terminalization_tier is invalid")
        if self.frozen is not None and type(self.frozen) is not FrozenCandidate:
            raise TypeError("frozen must be exact or null")
        if self.evidence is not None and (
            type(self.evidence) is not FunctionalEvidencePublication
        ):
            raise TypeError("evidence must be exact or null")
        proof = self.provider_cleanup_proof
        cleanup = self.lifecycle.provider_cleanup
        if self.lifecycle.natural_join_proven:
            if (
                self.terminalization_tier != "T4"
                or cleanup != "NOT_REQUIRED"
                or proof is not None
                or self.cleanup_diagnostic is not None
                or type(self.natural_shutdown_proof)
                is not PhasedNaturalShutdownEvidence
                or self.endpoint_shutdown_status != "complete"
            ):
                raise ValueError("post-proof failure evidence is inconsistent")
            return
        if self.natural_shutdown_proof is not None:
            raise ValueError("pre-proof failure forbids natural proof")
        if cleanup == "NOT_REQUIRED":
            if (
                type(proof) is not NoBackendAllocationProof
                or self.cleanup_diagnostic is not None
            ):
                raise ValueError("not-required cleanup requires exact proof")
        elif cleanup == "COMPLETE":
            if (
                type(proof) is not PhasedFailedCleanupEvidence
                or proof.cleanup_complete is not True
                or self.cleanup_diagnostic is not None
            ):
                raise ValueError("complete cleanup evidence is inconsistent")
        elif cleanup == "INCOMPLETE":
            if (
                proof is not None
                and (
                    type(proof) is not PhasedFailedCleanupEvidence
                    or proof.cleanup_complete is not False
                )
            ):
                raise ValueError("incomplete cleanup proof is invalid")
            if type(self.cleanup_diagnostic) is not PhasedDeliveryDiagnostic:
                raise ValueError(
                    "incomplete cleanup requires a supplemental diagnostic"
                )
        else:
            raise ValueError("failed result cannot retain pending cleanup")


class PhasedOperationFailure(RuntimeError):
    """One exact semantic binding failure awaiting coordinator terminalization."""

    def __init__(self, diagnostic: PhasedDeliveryDiagnostic) -> None:
        if type(diagnostic) is not PhasedDeliveryDiagnostic:
            raise TypeError("diagnostic must be exact")
        super().__init__(diagnostic.code)
        self.diagnostic = diagnostic


class PhasedAdapter(Protocol):
    def start(
        self,
        invocation: InteractiveMemberInvocation,
        *,
        deadline: float,
    ) -> InteractiveTerminalStartOutcome: ...

    def offer(
        self,
        handle: InteractiveMemberHandle,
        literal_message: str,
        *,
        deadline: float,
    ) -> OfferReceipt: ...

    def offer_close(
        self,
        handle: InteractiveMemberHandle,
        *,
        deadline: float,
    ) -> CloseOfferReceipt: ...

    def join(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> NaturalShutdownProof: ...

    def abort(
        self,
        handle: InteractiveMemberHandle,
        deadline: float,
    ) -> FailedCleanupProof: ...


class PhaseLedger(Protocol):
    def append(
        self,
        event: str,
        payload: Mapping[str, object],
        *,
        observed_at: str,
    ) -> None: ...

    def close(self) -> None: ...


class SubmitEndpoint(Protocol):
    @property
    def binding(self) -> PhasedSubmitBinding: ...

    def start(self) -> None: ...

    def open_admission(self, lifecycle: str) -> None: ...

    def receive_event(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointEvent: ...

    def resolve(
        self,
        event: SubmitEndpointEvent,
        receipt: SubmitReceipt,
        *,
        rearm_retry: bool = False,
    ) -> None: ...

    def stop_admission(self) -> None: ...

    def shutdown(
        self,
        *,
        deadline: float | None = None,
    ) -> SubmitEndpointShutdownOutcome: ...


class PhasedProviderAttemptCoordinatorBindings(Protocol):
    adapter: PhasedAdapter

    def observed_at(self) -> str: ...

    def monotonic_now(self) -> float: ...

    def prestart_no_backend_allocation_proof(
        self,
    ) -> NoBackendAllocationProof: ...

    def allocate_attempt(self) -> AttemptAllocation: ...

    def derive_attempt_deadline(
        self,
        allocation: AttemptAllocation,
    ) -> float: ...

    def compose_attempt(
        self,
        allocation: AttemptAllocation,
        *,
        deadline: float,
    ) -> AttemptComposition: ...

    def preflight_candidates(
        self,
        composition: AttemptComposition,
    ) -> CandidatePreflight: ...

    def create_ledger(
        self,
        allocation: AttemptAllocation,
        composition: AttemptComposition,
    ) -> PhaseLedger: ...

    def create_endpoint(
        self,
        composition: AttemptComposition,
    ) -> SubmitEndpoint: ...

    def receive_attempt_event(
        self,
        *,
        boundary: str,
        endpoint: SubmitEndpoint,
        deadline: float,
    ) -> SerializedAttemptEvent | None: ...

    def snapshot_candidates(
        self,
        preflight: CandidatePreflight,
        submission_ordinal: int,
    ) -> CandidateSnapshot: ...

    def validate_output_positions(
        self,
        snapshot: CandidateSnapshot,
    ) -> OutputPositionValidation: ...

    def validate_structured_result(
        self,
        snapshot: CandidateSnapshot,
    ) -> StructuredResultValidation: ...

    def reset_candidates(
        self,
        snapshot: CandidateSnapshot,
    ) -> CandidateResetResult: ...

    def freeze_candidate(
        self,
        snapshot: CandidateSnapshot,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
    ) -> FrozenCandidate: ...

    def publish_functional_evidence(
        self,
        frozen: FrozenCandidate,
        actual_deliveries: tuple[RenderedProtocolTurn, ...],
    ) -> FunctionalEvidencePublication: ...

    def restore_frozen_candidate(
        self,
        frozen: FrozenCandidate,
    ) -> FrozenCandidateRestoration: ...

    def verify_frozen_candidate(
        self,
        frozen: FrozenCandidate,
        restoration: FrozenCandidateRestoration,
    ) -> FrozenCandidateVerification: ...

    def prepare_success_commit(
        self,
        *,
        allocation: AttemptAllocation,
        output: OutputPositionValidation,
        structured: StructuredResultValidation,
        frozen: FrozenCandidate,
        evidence: FunctionalEvidencePublication,
        verification: FrozenCandidateVerification,
    ) -> PreparedSuccessCommit: ...

    def atomic_success_commit(
        self,
        prepared: PreparedSuccessCommit,
        *,
        deadline: float,
    ) -> AtomicSuccessCommitReceipt: ...

    def finalize_failure(
        self,
        first_diagnostic: PhasedDeliveryDiagnostic,
        lifecycle: PhasedLifecycleState,
    ) -> None: ...


__all__ = [
    "AtomicSuccessCommitReceipt",
    "AttemptAllocation",
    "AttemptComposition",
    "CandidatePathBinding",
    "CandidatePreflight",
    "CandidateResetResult",
    "CandidateSnapshot",
    "FrozenCandidate",
    "FrozenCandidateFile",
    "FrozenCandidateRestoration",
    "FrozenCandidateVerification",
    "FunctionalEvidencePublication",
    "OutputPositionValidation",
    "PhasedAdapter",
    "PhasedOperationFailure",
    "PhasedNaturalShutdownEvidence",
    "PhasedProviderAttemptFailure",
    "PhasedProviderAttemptSuccess",
    "PreparedSuccessCommit",
    "SerializedAttemptEvent",
    "PhasedProviderAttemptCoordinatorBindings",
    "PhaseLedger",
    "StructuredResultValidation",
    "SubmitEndpoint",
    "ValidatedArtifact",
    "ValidatedStructuredResult",
]
