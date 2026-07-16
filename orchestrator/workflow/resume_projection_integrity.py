"""Pure resume projection-integrity classification helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Mapping


_RETRY_MARKER = "::retry::"
_POSITIVE_ORDINAL = re.compile(r"[1-9][0-9]*\Z")
_ALLOWED_FRAME_STATUSES = frozenset({"completed", "running", "failed"})


@dataclass(frozen=True)
class CallFrameMember:
    """One validated persisted call-frame member."""

    frame_id: str
    frame: Mapping[str, Any]
    status: str
    call_step_id: str
    import_alias: str


@dataclass(frozen=True)
class RetryFrameMember(CallFrameMember):
    """One validated member of a Workflow Lisp retry lineage."""

    ordinal: int


@dataclass(frozen=True)
class CallFrameRetryLineage:
    """Deterministic resumable-frame classification for one call boundary."""

    base_frame_id: str
    completed_members: tuple[CallFrameMember, ...]
    failed_predecessors: tuple[RetryFrameMember, ...]
    running_member: CallFrameMember | None


class CallFrameRetryLineageError(ValueError):
    """Reject malformed or ambiguous persisted call-frame lineage."""

    def __init__(
        self,
        reason: str,
        *,
        frame_id: str | None = None,
        offending_value: Any = None,
    ) -> None:
        self.reason = reason
        self.frame_id = frame_id
        self.offending_value = offending_value
        super().__init__(reason)


def _retry_identity(frame_id: str) -> tuple[str, int]:
    """Return the current frame's base ID and ordinal without parsing ancestors."""
    marker_index = frame_id.rfind(_RETRY_MARKER)
    visit_index = frame_id.rfind("::visit::")
    if marker_index < 0 or marker_index < visit_index:
        return frame_id, 0

    base_frame_id = frame_id[:marker_index]
    ordinal_text = frame_id[marker_index + len(_RETRY_MARKER) :]
    if not base_frame_id or _POSITIVE_ORDINAL.fullmatch(ordinal_text) is None:
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            frame_id=frame_id,
            offending_value=frame_id,
        )

    prior_marker_index = base_frame_id.rfind(_RETRY_MARKER)
    base_visit_index = base_frame_id.rfind("::visit::")
    if prior_marker_index >= 0 and prior_marker_index > base_visit_index:
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            frame_id=frame_id,
            offending_value=frame_id,
        )
    return base_frame_id, int(ordinal_text)


def _validated_member(
    boundary_step_id: str,
    frame_id: Any,
    frame: Any,
) -> CallFrameMember:
    if not isinstance(frame_id, str) or not frame_id or not isinstance(frame, Mapping):
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            frame_id=frame_id if isinstance(frame_id, str) else None,
            offending_value=frame,
        )

    call_step_id = frame.get("call_step_id")
    if not isinstance(call_step_id, str) or not call_step_id:
        raise CallFrameRetryLineageError(
            "missing_required_identity",
            frame_id=frame_id,
            offending_value=call_step_id,
        )
    if call_step_id != boundary_step_id:
        raise CallFrameRetryLineageError(
            "missing_call_boundary",
            frame_id=frame_id,
            offending_value=call_step_id,
        )

    import_alias = frame.get("import_alias")
    if not isinstance(import_alias, str) or not import_alias:
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            frame_id=frame_id,
            offending_value=import_alias,
        )

    status = frame.get("status")
    if not isinstance(status, str) or status not in _ALLOWED_FRAME_STATUSES:
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            frame_id=frame_id,
            offending_value=status,
        )

    return CallFrameMember(
        frame_id=frame_id,
        frame=frame,
        status=status,
        call_step_id=call_step_id,
        import_alias=import_alias,
    )


def index_retry_lineage(
    boundary_step_id: str,
    frame_items: Iterable[tuple[str, Any]],
    *,
    frontend_kind: str | None,
) -> CallFrameRetryLineage:
    """Validate and deterministically classify one call boundary's frames."""
    if not isinstance(boundary_step_id, str) or not boundary_step_id:
        raise CallFrameRetryLineageError(
            "missing_required_identity",
            offending_value=boundary_step_id,
        )

    completed_members: list[CallFrameMember] = []
    noncompleted_members: list[CallFrameMember] = []
    seen_frame_ids: set[str] = set()
    import_alias: str | None = None

    for raw_frame_id, raw_frame in frame_items:
        member = _validated_member(boundary_step_id, raw_frame_id, raw_frame)
        if member.frame_id in seen_frame_ids:
            raise CallFrameRetryLineageError(
                "ambiguous_resumable_call_frame",
                frame_id=member.frame_id,
                offending_value=member.frame_id,
            )
        seen_frame_ids.add(member.frame_id)

        if import_alias is None:
            import_alias = member.import_alias
        elif member.import_alias != import_alias:
            raise CallFrameRetryLineageError(
                "persisted_import_alias_mismatch",
                frame_id=member.frame_id,
                offending_value=member.import_alias,
            )

        if member.status == "completed":
            completed_members.append(member)
        else:
            noncompleted_members.append(member)

    completed = tuple(sorted(completed_members, key=lambda member: member.frame_id))
    if frontend_kind != "workflow_lisp":
        if len(noncompleted_members) > 1:
            raise CallFrameRetryLineageError(
                "ambiguous_resumable_call_frame",
                offending_value=len(noncompleted_members),
            )
        resumable_member = noncompleted_members[0] if noncompleted_members else None
        return CallFrameRetryLineage(
            base_frame_id=resumable_member.frame_id if resumable_member is not None else "",
            completed_members=completed,
            failed_predecessors=(),
            running_member=resumable_member,
        )

    retry_members: list[RetryFrameMember] = []
    lineage_bases: set[str] = set()
    ordinals: set[int] = set()
    for member in noncompleted_members:
        base_frame_id, ordinal = _retry_identity(member.frame_id)
        lineage_bases.add(base_frame_id)
        if ordinal in ordinals:
            raise CallFrameRetryLineageError(
                "ambiguous_resumable_call_frame",
                frame_id=member.frame_id,
                offending_value=ordinal,
            )
        ordinals.add(ordinal)
        retry_members.append(
            RetryFrameMember(
                frame_id=member.frame_id,
                frame=member.frame,
                status=member.status,
                call_step_id=member.call_step_id,
                import_alias=member.import_alias,
                ordinal=ordinal,
            )
        )

    if len(lineage_bases) > 1:
        raise CallFrameRetryLineageError(
            "ambiguous_resumable_call_frame",
            offending_value=tuple(sorted(lineage_bases)),
        )
    if not retry_members:
        return CallFrameRetryLineage(
            base_frame_id="",
            completed_members=completed,
            failed_predecessors=(),
            running_member=None,
        )

    ordered_members = sorted(retry_members, key=lambda member: member.ordinal)
    if [member.ordinal for member in ordered_members] != list(range(len(ordered_members))):
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            offending_value=tuple(member.ordinal for member in ordered_members),
        )

    running_members = [
        member for member in ordered_members if member.status == "running"
    ]
    if len(running_members) > 1:
        raise CallFrameRetryLineageError(
            "ambiguous_resumable_call_frame",
            offending_value=len(running_members),
        )
    if running_members and running_members[0] is not ordered_members[-1]:
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            frame_id=running_members[0].frame_id,
            offending_value=running_members[0].ordinal,
        )

    return CallFrameRetryLineage(
        base_frame_id=next(iter(lineage_bases)),
        completed_members=completed,
        failed_predecessors=tuple(
            member for member in ordered_members if member.status == "failed"
        ),
        running_member=running_members[0] if running_members else None,
    )


def next_unused_retry_frame_id(lineage: CallFrameRetryLineage) -> str:
    """Allocate the lowest unused positive retry ordinal deterministically."""
    if not isinstance(lineage.base_frame_id, str) or not lineage.base_frame_id:
        raise CallFrameRetryLineageError(
            "unsupported_shape",
            offending_value=lineage.base_frame_id,
        )

    used_frame_ids = {
        member.frame_id
        for member in (
            *lineage.completed_members,
            *lineage.failed_predecessors,
        )
    }
    if lineage.running_member is not None:
        used_frame_ids.add(lineage.running_member.frame_id)

    ordinal = 1
    while True:
        candidate = f"{lineage.base_frame_id}{_RETRY_MARKER}{ordinal}"
        if candidate not in used_frame_ids:
            return candidate
        ordinal += 1
