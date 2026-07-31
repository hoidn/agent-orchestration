"""Pure protocol-frame rendering for phased provider turns."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from orchestrator._common.canonical import compact_ascii_json_dumps
from orchestrator.providers.types import INTERACTIVE_TERMINAL_SUBMIT_KEYS
from orchestrator.workflow.prompting import CanonicalPromptCut

from .diagnostics import PhasedDeliveryDiagnostic
from .models import (
    ByteDigestProjection,
    CountDigestProjection,
    TurnProjection,
)


PROTOCOL_FRAME_SCHEMA_VERSION = "provider_phased_protocol_frame.v1"
_SUBMIT_COMMAND = "orchestrator provider-materialization-submit"
_RETRY_REASON_ORDER = (
    "output_validation_failed",
    "structured_result_validation_failed",
)


def _byte_projection(payload: bytes) -> ByteDigestProjection:
    return ByteDigestProjection(
        bytes=len(payload),
        sha256=f"sha256:{hashlib.sha256(payload).hexdigest()}",
    )


def _canonical_json_bytes(value: object) -> bytes:
    return compact_ascii_json_dumps(
        value,
        allow_nan=True,
    ).encode("utf-8", errors="strict")


def _frame_bytes(payload: dict[str, object]) -> bytes:
    # The frame owns the complete boundary before its canonical slice.
    return _canonical_json_bytes(payload) + b"\n\n"


def _validated_cut(value: object) -> CanonicalPromptCut:
    if type(value) is not CanonicalPromptCut:
        raise TypeError("cut must be an exact CanonicalPromptCut")
    return value


def _submit_key_projection(
    submit_keys: object,
    *,
    required: bool,
) -> CountDigestProjection:
    if (
        type(submit_keys) is not tuple
        or any(
            type(key) is not str
            or not key
            or key not in INTERACTIVE_TERMINAL_SUBMIT_KEYS
            for key in submit_keys
        )
    ):
        raise TypeError("submit_keys must be a closed non-forcing key tuple")
    if required and not submit_keys:
        raise ValueError("materialization turns require submit keys")
    encoded = _canonical_json_bytes(list(submit_keys))
    return CountDigestProjection(
        count=len(submit_keys),
        sha256=f"sha256:{hashlib.sha256(encoded).hexdigest()}",
    )


@dataclass(frozen=True, slots=True, init=False)
class RenderedProtocolTurn:
    """Exact frame, canonical slice, delivered bytes, and sealed projection."""

    protocol_frame: bytes
    canonical_slice: bytes
    delivered_turn: bytes
    projection: TurnProjection

    def __init__(self) -> None:
        raise TypeError(
            "RenderedProtocolTurn is factory-only; use a render_*_turn function"
        )

    @classmethod
    def _create(
        cls,
        *,
        protocol_frame: bytes,
        canonical_slice: bytes,
        delivered_turn: bytes,
        projection: TurnProjection,
    ) -> RenderedProtocolTurn:
        value = object.__new__(cls)
        object.__setattr__(value, "protocol_frame", protocol_frame)
        object.__setattr__(value, "canonical_slice", canonical_slice)
        object.__setattr__(value, "delivered_turn", delivered_turn)
        object.__setattr__(value, "projection", projection)
        value.__post_init__()
        return value

    def __post_init__(self) -> None:
        for field in (
            "protocol_frame",
            "canonical_slice",
            "delivered_turn",
        ):
            value = getattr(self, field)
            if type(value) is not bytes:
                raise TypeError(f"{field} must be exact bytes")
            value.decode("utf-8", errors="strict")
        if self.delivered_turn != self.protocol_frame + self.canonical_slice:
            raise ValueError(
                "delivered_turn must equal protocol_frame plus canonical_slice"
            )
        if type(self.projection) is not TurnProjection:
            raise TypeError("projection must be an exact TurnProjection")
        if self.projection.protocol_frame != _byte_projection(
            self.protocol_frame
        ):
            raise ValueError("protocol_frame projection is inconsistent")
        if self.projection.canonical_slice != _byte_projection(
            self.canonical_slice
        ):
            raise ValueError("canonical_slice projection is inconsistent")
        if self.projection.delivered_turn != _byte_projection(
            self.delivered_turn
        ):
            raise ValueError("delivered_turn projection is inconsistent")


def _rendered_turn(
    *,
    frame: bytes,
    canonical_slice: bytes,
    delivery_ordinal: int,
    phase: str,
    submission_ordinal: int | None,
    submit_keys: CountDigestProjection,
) -> RenderedProtocolTurn:
    delivered = frame + canonical_slice
    return RenderedProtocolTurn._create(
        protocol_frame=frame,
        canonical_slice=canonical_slice,
        delivered_turn=delivered,
        projection=TurnProjection(
            delivery_ordinal=delivery_ordinal,
            phase=phase,
            submission_ordinal=submission_ordinal,
            protocol_frame=_byte_projection(frame),
            canonical_slice=_byte_projection(canonical_slice),
            delivered_turn=_byte_projection(delivered),
            submit_keys=submit_keys,
        ),
    )


def render_task_turn(
    *,
    cut: CanonicalPromptCut,
) -> RenderedProtocolTurn:
    """Render the one task turn without altering the canonical composition."""

    cut = _validated_cut(cut)
    frame = _frame_bytes(
        {
            "phase": "task",
            "protocol_schema_version": PROTOCOL_FRAME_SCHEMA_VERSION,
            "task_action": "execute_once",
            "transition": "await_materialization_turn",
        }
    )
    return _rendered_turn(
        frame=frame,
        canonical_slice=cut.task_slice,
        delivery_ordinal=0,
        phase="task",
        submission_ordinal=None,
        submit_keys=_submit_key_projection((), required=False),
    )


def render_initial_materialization_turn(
    *,
    cut: CanonicalPromptCut,
    submit_keys: tuple[str, ...],
) -> RenderedProtocolTurn:
    """Render the first materialization turn over the exact canonical T2."""

    cut = _validated_cut(cut)
    if not cut.materialization_slice:
        raise ValueError("materialization_slice must contain a contract suffix")
    frame = _frame_bytes(
        {
            "candidate_action": "recreate_all_bound_outputs",
            "phase": "initial_materialization",
            "protocol_schema_version": PROTOCOL_FRAME_SCHEMA_VERSION,
            "submission_ordinal": 1,
            "submit_command": _SUBMIT_COMMAND,
        }
    )
    return _rendered_turn(
        frame=frame,
        canonical_slice=cut.materialization_slice,
        delivery_ordinal=1,
        phase="initial_materialization",
        submission_ordinal=1,
        submit_keys=_submit_key_projection(submit_keys, required=True),
    )


def _retry_diagnostic_rows(
    diagnostics: object,
) -> list[dict[str, Any]]:
    if (
        type(diagnostics) is not tuple
        or not diagnostics
        or len(diagnostics) > len(_RETRY_REASON_ORDER)
        or any(
            type(diagnostic) is not PhasedDeliveryDiagnostic
            for diagnostic in diagnostics
        )
    ):
        raise TypeError(
            "diagnostics must be a bounded non-empty exact diagnostic tuple"
        )
    reasons = tuple(diagnostic.reason for diagnostic in diagnostics)
    if (
        len(set(reasons)) != len(reasons)
        or any(reason not in _RETRY_REASON_ORDER for reason in reasons)
        or tuple(_RETRY_REASON_ORDER.index(reason) for reason in reasons)
        != tuple(sorted(_RETRY_REASON_ORDER.index(reason) for reason in reasons))
    ):
        raise ValueError(
            "retry diagnostics require unique ordered Q2 validation reasons"
        )
    return [
        {
            "code": diagnostic.code,
            "reason": diagnostic.reason,
            "rejected_value": {
                "canonical_value": diagnostic.rejected_value.canonical_value,
                "type": diagnostic.rejected_value.type,
            },
        }
        for diagnostic in diagnostics
    ]


def render_retry_materialization_turn(
    *,
    cut: CanonicalPromptCut,
    submission_ordinal: int,
    diagnostics: tuple[PhasedDeliveryDiagnostic, ...],
    submit_keys: tuple[str, ...],
) -> RenderedProtocolTurn:
    """Render one diagnostic retry while reusing the exact canonical T2."""

    cut = _validated_cut(cut)
    if not cut.materialization_slice:
        raise ValueError("materialization_slice must contain a contract suffix")
    if (
        isinstance(submission_ordinal, bool)
        or not isinstance(submission_ordinal, int)
        or submission_ordinal not in {2, 3}
    ):
        raise ValueError("retry submission_ordinal must be two or three")
    diagnostic_rows = _retry_diagnostic_rows(diagnostics)
    frame = _frame_bytes(
        {
            "candidate_action": "recreate_all_bound_outputs",
            "diagnostics": diagnostic_rows,
            "phase": "retry_materialization",
            "protocol_schema_version": PROTOCOL_FRAME_SCHEMA_VERSION,
            "submission_ordinal": submission_ordinal,
            "submit_command": _SUBMIT_COMMAND,
        }
    )
    return _rendered_turn(
        frame=frame,
        canonical_slice=cut.materialization_slice,
        delivery_ordinal=submission_ordinal,
        phase="retry_materialization",
        submission_ordinal=submission_ordinal,
        submit_keys=_submit_key_projection(submit_keys, required=True),
    )
