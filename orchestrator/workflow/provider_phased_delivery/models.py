"""Pure immutable foundations for phased provider delivery."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
import re
from types import MappingProxyType
from typing import Mapping

from orchestrator._common.canonical import sha256_compact_ascii_json
from orchestrator.providers.interactive_terminal import (
    InteractiveTerminalStartOutcome,
)
from orchestrator.providers.types import canonical_workflow_call_policy
from .diagnostics import PhasedDeliveryDiagnostic


_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}")
_U63_MAX = 2**63 - 1
_EMPTY_SUBMIT_KEYS_SHA256 = (
    "sha256:"
    "4f53cda18c2baa0c0354bb5f9a3ecbe5ed12ab4d8e11ba873c2f11161202b945"
)
_TURN_PHASES = frozenset(
    {"task", "initial_materialization", "retry_materialization"}
)
_LIFECYCLE_PHASES = frozenset(
    {
        "ALLOCATED",
        "STARTING",
        "LIVE",
        "INITIAL_MATERIALIZATION_QUEUED",
        "VALIDATING",
        "RETRY_QUEUED",
        "VALID_FROZEN",
        "CLOSING",
        "INGRESS_STOPPING",
        "JOINING",
        "JOINED_PENDING_COMMIT",
        "PUBLISHED",
        "TERMINALIZING",
        "FAILED",
    }
)
_PROVIDER_CLEANUP_STATES = frozenset(
    {"NOT_REQUIRED", "PENDING", "COMPLETE", "INCOMPLETE"}
)
_INGRESS_STATES = frozenset(
    {"NOT_ALLOCATED", "NOT_STARTED", "STARTED", "COMPLETE", "INCOMPLETE"}
)
_FORWARD_LIFECYCLE_SUBSTATES = MappingProxyType(
    {
        "ALLOCATED": ("NOT_REQUIRED", frozenset({"NOT_ALLOCATED"}), False),
        "STARTING": ("PENDING", frozenset({"NOT_ALLOCATED"}), False),
        "LIVE": (
            "PENDING",
            frozenset({"NOT_ALLOCATED", "NOT_STARTED", "STARTED"}),
            False,
        ),
        "INITIAL_MATERIALIZATION_QUEUED": (
            "PENDING",
            frozenset({"STARTED"}),
            False,
        ),
        "VALIDATING": ("PENDING", frozenset({"STARTED"}), False),
        "RETRY_QUEUED": ("PENDING", frozenset({"STARTED"}), False),
        "VALID_FROZEN": ("PENDING", frozenset({"STARTED"}), False),
        "CLOSING": ("PENDING", frozenset({"STARTED"}), False),
        "INGRESS_STOPPING": ("PENDING", frozenset({"STARTED"}), False),
        "JOINING": ("PENDING", frozenset({"COMPLETE"}), False),
        "JOINED_PENDING_COMMIT": (
            "NOT_REQUIRED",
            frozenset({"COMPLETE"}),
            True,
        ),
        "PUBLISHED": ("NOT_REQUIRED", frozenset({"COMPLETE"}), True),
    }
)
PROVIDER_CALL_POLICY_KEYS = MappingProxyType(
    {
        "model": "provider",
        "effort": "provider",
        "delivery": "runtime",
        "materialization_attempts": "runtime",
    }
)


def _require_u63(value: object, *, field: str, positive: bool = False) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < (1 if positive else 0)
        or value > _U63_MAX
    ):
        domain = "positive_u63" if positive else "u63"
        raise TypeError(f"{field} must be a non-Boolean {domain}")
    return value


def _require_digest(value: object, *, field: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a canonical SHA-256 digest")
    return value


def _require_nonempty_string(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise TypeError(f"{field} must be a non-empty string")
    return value


def _require_workspace_relative_path(value: object) -> str:
    text = _require_nonempty_string(
        value,
        field="workspace_relative_path",
    )
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
class ProviderBoundPolicy:
    """The exact provider-owned policy partition."""

    model: str | None = None
    effort: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("model", "effort"):
            value = getattr(self, field_name)
            if value is not None:
                _require_nonempty_string(value, field=field_name)


@dataclass(frozen=True, slots=True)
class PhasedRuntimePolicy:
    """The exact runtime-owned delivery-policy partition."""

    delivery: str
    materialization_attempts: int | None

    def __post_init__(self) -> None:
        if self.delivery not in {"composed", "phased"}:
            raise ValueError("delivery must be composed or phased")
        attempts = self.materialization_attempts
        if self.delivery == "composed":
            if attempts is not None:
                raise ValueError(
                    "composed delivery forbids materialization_attempts"
                )
            return
        _require_u63(
            attempts,
            field="materialization_attempts",
            positive=True,
        )
        if attempts not in {1, 2, 3}:
            raise ValueError("materialization_attempts must be in 1..3")


def partition_provider_call_policy(
    policy: Mapping[str, object],
) -> tuple[ProviderBoundPolicy, PhasedRuntimePolicy | None]:
    """Partition closed call policy without inventing runtime defaults."""

    copied = canonical_workflow_call_policy(policy)
    provider_values = {
        "model": copied.get("model"),
        "effort": copied.get("effort"),
    }

    delivery_present = "delivery" in copied
    if not delivery_present:
        runtime = None
    else:
        delivery = copied["delivery"]
        runtime = PhasedRuntimePolicy(
            delivery=delivery,
            materialization_attempts=copied.get(
                "materialization_attempts"
            ),
        )
    return (
        ProviderBoundPolicy(
            model=provider_values["model"],
            effort=provider_values["effort"],
        ),
        runtime,
    )


@dataclass(frozen=True, slots=True)
class ByteDigestProjection:
    bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _require_u63(self.bytes, field="bytes")
        _require_digest(self.sha256, field="sha256")


@dataclass(frozen=True, slots=True)
class CountDigestProjection:
    count: int
    sha256: str

    def __post_init__(self) -> None:
        _require_u63(self.count, field="count")
        _require_digest(self.sha256, field="sha256")


@dataclass(frozen=True, slots=True)
class CompositionProjection:
    canonical_composed: ByteDigestProjection
    task_slice: ByteDigestProjection
    materialization_slice: ByteDigestProjection

    def __post_init__(self) -> None:
        for field_name in (
            "canonical_composed",
            "task_slice",
            "materialization_slice",
        ):
            if type(getattr(self, field_name)) is not ByteDigestProjection:
                raise TypeError(
                    f"{field_name} must be an exact ByteDigestProjection"
                )
        if self.canonical_composed.bytes != (
            self.task_slice.bytes + self.materialization_slice.bytes
        ):
            raise ValueError(
                "canonical_composed bytes must equal task plus materialization"
            )


@dataclass(frozen=True, slots=True)
class TurnProjection:
    delivery_ordinal: int
    phase: str
    submission_ordinal: int | None
    protocol_frame: ByteDigestProjection
    canonical_slice: ByteDigestProjection
    delivered_turn: ByteDigestProjection
    submit_keys: CountDigestProjection

    def __post_init__(self) -> None:
        _require_u63(self.delivery_ordinal, field="delivery_ordinal")
        if self.phase not in _TURN_PHASES:
            raise ValueError("turn phase is invalid")
        for field_name in (
            "protocol_frame",
            "canonical_slice",
            "delivered_turn",
        ):
            if type(getattr(self, field_name)) is not ByteDigestProjection:
                raise TypeError(
                    f"{field_name} must be an exact ByteDigestProjection"
                )
        if type(self.submit_keys) is not CountDigestProjection:
            raise TypeError(
                "submit_keys must be an exact CountDigestProjection"
            )
        if self.delivered_turn.bytes != (
            self.protocol_frame.bytes + self.canonical_slice.bytes
        ):
            raise ValueError(
                "delivered_turn bytes must equal frame plus canonical slice"
            )
        if self.phase == "task":
            if self.delivery_ordinal != 0 or self.submission_ordinal is not None:
                raise ValueError(
                    "task turn requires ordinal zero and null submission"
                )
            if (
                self.submit_keys.count != 0
                or self.submit_keys.sha256 != _EMPTY_SUBMIT_KEYS_SHA256
            ):
                raise ValueError(
                    "task turn requires the canonical empty submit-key digest"
                )
            return
        submission_ordinal = _require_u63(
            self.submission_ordinal,
            field="submission_ordinal",
            positive=True,
        )
        if self.delivery_ordinal != submission_ordinal:
            raise ValueError(
                "materialization delivery ordinal must equal submission ordinal"
            )
        if self.submit_keys.count == 0:
            raise ValueError(
                "materialization turns require non-empty submit keys"
            )
        if self.phase == "initial_materialization":
            if submission_ordinal != 1:
                raise ValueError(
                    "initial materialization submission ordinal must be one"
                )
        elif submission_ordinal < 2:
            raise ValueError(
                "retry materialization submission ordinal must be at least two"
            )


@dataclass(frozen=True, slots=True)
class AdapterReceiptProjection:
    status: str
    handle_id_sha256: str

    def __post_init__(self) -> None:
        if self.status not in {"started", "offered", "close_offered"}:
            raise ValueError("adapter receipt status is invalid")
        _require_digest(self.handle_id_sha256, field="handle_id_sha256")


@dataclass(frozen=True, slots=True)
class CandidateDigestRow:
    contract_ordinal: int
    role: str
    logical_name: str
    workspace_relative_path: str
    presence: str
    byte_length: int | None
    sha256: str | None

    def __post_init__(self) -> None:
        _require_u63(self.contract_ordinal, field="contract_ordinal")
        if self.role not in {"expected_output", "structured_bundle"}:
            raise ValueError("candidate role is invalid")
        _require_nonempty_string(self.logical_name, field="logical_name")
        if (
            self.role == "structured_bundle"
            and self.logical_name != "__structured_result_bundle__"
        ):
            raise ValueError(
                "structured bundle requires the reserved logical name"
            )
        if (
            self.role == "expected_output"
            and self.logical_name == "__structured_result_bundle__"
        ):
            raise ValueError("expected output cannot use the reserved name")
        _require_workspace_relative_path(self.workspace_relative_path)
        if self.presence not in {"missing", "regular", "invalid"}:
            raise ValueError("candidate presence is invalid")
        if self.presence == "regular":
            _require_u63(self.byte_length, field="byte_length")
            _require_digest(self.sha256, field="sha256")
        elif self.byte_length is not None or self.sha256 is not None:
            raise ValueError(
                "non-regular candidates require null length and digest"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract_ordinal": self.contract_ordinal,
            "role": self.role,
            "logical_name": self.logical_name,
            "workspace_relative_path": self.workspace_relative_path,
            "presence": self.presence,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
        }


def _manifest_payload(
    *,
    submission_ordinal: int,
    disposition: str,
    rows: tuple[CandidateDigestRow, ...],
) -> dict[str, object]:
    return {
        "schema_version": "provider_phased_candidate_digest_manifest.v1",
        "submission_ordinal": submission_ordinal,
        "disposition": disposition,
        "rows": [row.to_dict() for row in rows],
    }


@dataclass(frozen=True, slots=True)
class CandidateDigestManifest:
    submission_ordinal: int
    disposition: str
    rows: tuple[CandidateDigestRow, ...]
    manifest_sha256: str

    schema_version = "provider_phased_candidate_digest_manifest.v1"

    def __post_init__(self) -> None:
        _require_u63(
            self.submission_ordinal,
            field="submission_ordinal",
            positive=True,
        )
        if self.disposition not in {"rejected", "frozen"}:
            raise ValueError("manifest disposition is invalid")
        if not isinstance(self.rows, tuple) or not self.rows:
            raise TypeError("manifest rows must be a non-empty tuple")
        if any(type(row) is not CandidateDigestRow for row in self.rows):
            raise TypeError("manifest rows must be exact CandidateDigestRow")
        if tuple(row.contract_ordinal for row in self.rows) != tuple(
            range(len(self.rows))
        ):
            raise ValueError("manifest contract ordinals must be contiguous")
        structured_bundle_indexes = tuple(
            index
            for index, row in enumerate(self.rows)
            if row.role == "structured_bundle"
        )
        if (
            len(structured_bundle_indexes) != 1
            or structured_bundle_indexes[0] != len(self.rows) - 1
        ):
            raise ValueError(
                "one structured bundle must be the final candidate row"
            )
        if self.disposition == "frozen" and any(
            row.presence != "regular" for row in self.rows
        ):
            raise ValueError("frozen manifest requires every row regular")
        _require_digest(self.manifest_sha256, field="manifest_sha256")
        expected = sha256_compact_ascii_json(
            _manifest_payload(
                submission_ordinal=self.submission_ordinal,
                disposition=self.disposition,
                rows=self.rows,
            ),
            allow_nan=False,
        )
        if self.manifest_sha256 != expected:
            raise ValueError("manifest_sha256 does not seal the manifest")

    @classmethod
    def create(
        cls,
        *,
        submission_ordinal: int,
        disposition: str,
        rows: tuple[CandidateDigestRow, ...],
    ) -> CandidateDigestManifest:
        if not isinstance(rows, tuple):
            raise TypeError("manifest rows must be a tuple")
        if not rows or any(type(row) is not CandidateDigestRow for row in rows):
            raise TypeError(
                "manifest rows must contain exact CandidateDigestRow values"
            )
        digest = sha256_compact_ascii_json(
            _manifest_payload(
                submission_ordinal=submission_ordinal,
                disposition=disposition,
                rows=rows,
            ),
            allow_nan=False,
        )
        return cls(
            submission_ordinal=submission_ordinal,
            disposition=disposition,
            rows=rows,
            manifest_sha256=digest,
        )


@dataclass(frozen=True, slots=True)
class PhasedLifecycleState:
    phase: str
    provider_cleanup: str
    ingress: str
    natural_join_proven: bool
    abort_calls: int

    def __post_init__(self) -> None:
        if self.phase not in _LIFECYCLE_PHASES:
            raise ValueError("phase lifecycle state is invalid")
        if self.provider_cleanup not in _PROVIDER_CLEANUP_STATES:
            raise ValueError("provider cleanup state is invalid")
        if self.ingress not in _INGRESS_STATES:
            raise ValueError("ingress state is invalid")
        if type(self.natural_join_proven) is not bool:
            raise TypeError("natural_join_proven must be a Boolean")
        _require_u63(self.abort_calls, field="abort_calls")
        if self.abort_calls not in {0, 1}:
            raise ValueError("abort_calls must be zero or one")
        if (
            self.provider_cleanup == "COMPLETE"
            and self.ingress != "NOT_ALLOCATED"
            and self.abort_calls != 1
        ):
            raise ValueError(
                "complete cleanup after endpoint allocation requires one abort"
            )
        if self.phase in _FORWARD_LIFECYCLE_SUBSTATES:
            cleanup, ingress_states, natural_proof = (
                _FORWARD_LIFECYCLE_SUBSTATES[self.phase]
            )
            if (
                self.provider_cleanup != cleanup
                or self.ingress not in ingress_states
                or self.natural_join_proven is not natural_proof
                or self.abort_calls != 0
            ):
                raise ValueError(
                    "forward lifecycle phase/substate combination is invalid"
                )
            return
        if self.phase == "TERMINALIZING":
            if self.natural_join_proven:
                raise ValueError(
                    "terminalizing is limited to pre-natural-proof failure"
                )
            if self.provider_cleanup in {"NOT_REQUIRED", "PENDING"}:
                if self.abort_calls != 0:
                    raise ValueError(
                        "unresolved cleanup state forbids recorded abort"
                    )
                if (
                    self.provider_cleanup == "NOT_REQUIRED"
                    and self.ingress != "NOT_ALLOCATED"
                ):
                    raise ValueError(
                        "no-cleanup terminalization requires no endpoint"
                    )
            if (
                self.provider_cleanup == "PENDING"
                and self.ingress == "INCOMPLETE"
            ):
                raise ValueError(
                    "incomplete ingress requires a finished cleanup outcome"
                )
            return
        if self.phase == "FAILED":
            if self.provider_cleanup == "PENDING" or self.ingress in {
                "NOT_STARTED",
                "STARTED",
            }:
                raise ValueError("terminal failure has unresolved substates")
            if self.natural_join_proven:
                if (
                    self.provider_cleanup != "NOT_REQUIRED"
                    or self.ingress != "COMPLETE"
                    or self.abort_calls != 0
                ):
                    raise ValueError(
                        "post-proof terminal failure forbids cleanup"
                    )
            elif (
                self.provider_cleanup == "NOT_REQUIRED"
                and (
                    self.ingress != "NOT_ALLOCATED"
                    or self.abort_calls != 0
                )
            ):
                raise ValueError(
                    "no-cleanup terminal failure requires no endpoint"
                )
            return
        raise RuntimeError("unhandled phased lifecycle phase")


@dataclass(frozen=True, slots=True)
class SubmitReceipt:
    status: str
    attempt_scope_sha256: str
    client_request_id: str
    submission_ordinal: int
    configured_total: int
    remaining_submissions: int
    diagnostic: PhasedDeliveryDiagnostic | None

    schema_version = "provider_phased_submit_receipt.v1"

    def __post_init__(self) -> None:
        if self.status not in {"retry_queued", "accepted_closing", "failed"}:
            raise ValueError("submit receipt status is invalid")
        _require_digest(
            self.attempt_scope_sha256,
            field="attempt_scope_sha256",
        )
        _require_nonempty_string(
            self.client_request_id,
            field="client_request_id",
        )
        submission = _require_u63(
            self.submission_ordinal,
            field="submission_ordinal",
            positive=True,
        )
        total = _require_u63(
            self.configured_total,
            field="configured_total",
            positive=True,
        )
        if total not in {1, 2, 3} or submission > total:
            raise ValueError("receipt submission range is invalid")
        remaining = _require_u63(
            self.remaining_submissions,
            field="remaining_submissions",
        )
        if remaining != total - submission:
            raise ValueError("remaining_submissions is inconsistent")
        if self.status == "retry_queued":
            if remaining == 0 or self.diagnostic is not None:
                raise ValueError(
                    "retry receipt requires remaining budget and null diagnostic"
                )
        elif self.status == "accepted_closing":
            if self.diagnostic is not None:
                raise ValueError(
                    "accepted closing receipt requires null diagnostic"
                )
        else:
            if self.diagnostic is None:
                raise ValueError("failed receipt requires a diagnostic")
            if type(self.diagnostic) is not PhasedDeliveryDiagnostic:
                raise TypeError(
                    "failed receipt requires an exact phased diagnostic"
                )


def validated_start_outcome(
    outcome: InteractiveTerminalStartOutcome,
) -> InteractiveTerminalStartOutcome:
    """Revalidate the exact P1 closed start union without projecting a handle."""

    if type(outcome) is not InteractiveTerminalStartOutcome:
        raise TypeError(
            "outcome must be an exact InteractiveTerminalStartOutcome"
        )
    # Construction already validates every closed success/failure
    # combination. Reconstructing from its exact fields catches any object
    # whose invariants were bypassed before it crosses into Q5.
    reconstructed = InteractiveTerminalStartOutcome(
        status=outcome.status,
        handle=outcome.handle,
        error_code=outcome.error_code,
        backend_allocation=outcome.backend_allocation,
        cleanup_status=outcome.cleanup_status,
        provider_zero_survivor_proven=(
            outcome.provider_zero_survivor_proven
        ),
        proof=outcome.proof,
    )
    if reconstructed != outcome:
        raise ValueError("start outcome did not revalidate exactly")
    return outcome
