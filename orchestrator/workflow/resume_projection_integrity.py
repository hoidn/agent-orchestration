"""Pure resume projection-integrity classification helpers."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, Iterator, Mapping

from .loaded_bundle import LoadedWorkflowBundle
from .state_projection import (
    ResumeProjectionSlotIndex,
    ResumeProjectionValidationError,
)


_RETRY_MARKER = "::retry::"
_POSITIVE_ORDINAL = re.compile(r"[1-9][0-9]*\Z")
_ALLOWED_FRAME_STATUSES = frozenset({"completed", "running", "failed"})
_DIAGNOSTIC_SCHEMA = "resume_projection_integrity_error.v1"
_ERROR_TYPE = "resume_projection_integrity_error"
_MAX_DIAGNOSTIC_STRING_LENGTH = 512


@dataclass(frozen=True)
class ResumeScopePath:
    """Immutable identity-only path from the root run to one audited scope."""

    root_workflow_file: str
    call_frame_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.root_workflow_file, str) or not self.root_workflow_file:
            raise ValueError("root_workflow_file must be a non-empty string")
        if any(
            not isinstance(frame_id, str) or not frame_id
            for frame_id in self.call_frame_ids
        ):
            raise ValueError("call_frame_ids must contain non-empty strings")

    @classmethod
    def root(cls, workflow_file: str) -> "ResumeScopePath":
        """Construct the root scope path for one resumed run."""
        return cls(root_workflow_file=workflow_file)

    def child(self, frame_id: str) -> "ResumeScopePath":
        """Return an immutable child scope path for one reached call frame."""
        if not isinstance(frame_id, str) or not frame_id:
            raise ValueError("frame_id must be a non-empty string")
        return ResumeScopePath(
            root_workflow_file=self.root_workflow_file,
            call_frame_ids=(*self.call_frame_ids, frame_id),
        )

    @property
    def projection_scope(self) -> str:
        """Return the stable current projection kind for diagnostics."""
        return "call_frame" if self.call_frame_ids else "root"

    def as_context(self) -> list[dict[str, str]]:
        """Serialize only root and call-frame identities."""
        return [
            {
                "kind": "root",
                "workflow_file": self.root_workflow_file,
            },
            *(
                {
                    "kind": "call_frame",
                    "frame_id": frame_id,
                }
                for frame_id in self.call_frame_ids
            ),
        ]


class ResumeProjectionIntegrityError(ValueError):
    """Stable diagnostic wrapper for one pure scoped audit failure."""

    def __init__(self, error: Mapping[str, Any]) -> None:
        self.error = error
        message = error.get("message")
        super().__init__(
            message
            if isinstance(message, str)
            else "Resume projection integrity audit failed"
        )


def audit_scope(
    bundle: LoadedWorkflowBundle,
    state: Mapping[str, Any],
    scope_path: ResumeScopePath,
) -> None:
    """Validate one persisted workflow scope against its exact current projection."""
    if not isinstance(bundle, LoadedWorkflowBundle):
        raise TypeError("LoadedWorkflowBundle required")
    if not isinstance(state, Mapping):
        _raise_integrity_error(
            bundle,
            {},
            scope_path,
            reason="unsupported_shape",
            field="state",
            offending_value=state,
        )
    if not isinstance(scope_path, ResumeScopePath):
        raise TypeError("ResumeScopePath required")

    try:
        slot_index = bundle.projection.enumerate_resume_slots(state)
    except ResumeProjectionValidationError as exc:
        _raise_integrity_error(
            bundle,
            state,
            scope_path,
            reason=exc.reason,
            field=_projection_failure_field(exc.message),
            offending_value=None,
        )

    _audit_explicit_step_results(bundle, state, scope_path, slot_index)
    _audit_current_step(bundle, state, scope_path, slot_index)
    _audit_call_frames(bundle, state, scope_path, slot_index)


def _audit_explicit_step_results(
    bundle: LoadedWorkflowBundle,
    state: Mapping[str, Any],
    scope_path: ResumeScopePath,
    slot_index: ResumeProjectionSlotIndex,
) -> None:
    steps = state.get("steps", {})
    assert isinstance(steps, Mapping)
    supported_presentations = {
        slot.presentation_key
        for candidates in slot_index.candidates_by_step_id.values()
        for slot in candidates
    }

    for presentation_key, step_id in _explicit_step_result_rows(steps):
        field = f"steps.{presentation_key}.step_id"
        if not isinstance(step_id, str) or not step_id:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="unsupported_shape",
                field=field,
                offending_value=step_id,
                candidate_count=0,
            )

        resolution = bundle.projection.resolve_resume_step_id(
            slot_index,
            step_id,
            presentation_key=presentation_key,
        )
        exact_count = resolution.exact_identity_candidate_count
        if exact_count == 0:
            reason = (
                "unknown_explicit_step_id"
                if presentation_key in supported_presentations
                else "unclaimed_explicit_step_row"
            )
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason=reason,
                field=field,
                offending_value=step_id,
                candidate_count=0,
            )
        if resolution.candidate_count == 0:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="presentation_slot_mismatch",
                field=field,
                offending_value=step_id,
                candidate_count=exact_count,
            )
        if exact_count != 1 or resolution.candidate_count != 1:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="out_of_scope_step_id",
                field=field,
                offending_value=step_id,
                candidate_count=resolution.candidate_count,
            )


def _audit_current_step(
    bundle: LoadedWorkflowBundle,
    state: Mapping[str, Any],
    scope_path: ResumeScopePath,
    slot_index: ResumeProjectionSlotIndex,
) -> None:
    if "current_step" not in state or state.get("current_step") is None:
        return
    current_step = state.get("current_step")
    if not isinstance(current_step, Mapping):
        _raise_integrity_error(
            bundle,
            state,
            scope_path,
            reason="unsupported_shape",
            field="current_step",
            offending_value=current_step,
        )

    step_id = current_step.get("step_id")
    if step_id is None or step_id == "":
        _raise_integrity_error(
            bundle,
            state,
            scope_path,
            reason="missing_required_identity",
            field="current_step.step_id",
            offending_value=None,
        )
    if not isinstance(step_id, str):
        _raise_integrity_error(
            bundle,
            state,
            scope_path,
            reason="unsupported_shape",
            field="current_step.step_id",
            offending_value=step_id,
            candidate_count=0,
        )

    resolution = bundle.projection.resolve_resume_step_id(slot_index, step_id)
    if resolution.exact_identity_candidate_count != 1:
        _raise_integrity_error(
            bundle,
            state,
            scope_path,
            reason="out_of_scope_step_id",
            field="current_step.step_id",
            offending_value=step_id,
            candidate_count=resolution.exact_identity_candidate_count,
        )

    presentation_key = current_step.get("name")
    if isinstance(presentation_key, str) and presentation_key:
        presentation_resolution = bundle.projection.resolve_resume_step_id(
            slot_index,
            step_id,
            presentation_key=presentation_key,
        )
        if presentation_resolution.candidate_count != 1:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="presentation_slot_mismatch",
                field="current_step.step_id",
                offending_value=step_id,
                candidate_count=resolution.exact_identity_candidate_count,
            )


def _audit_call_frames(
    bundle: LoadedWorkflowBundle,
    state: Mapping[str, Any],
    scope_path: ResumeScopePath,
    slot_index: ResumeProjectionSlotIndex,
) -> None:
    if "call_frames" not in state:
        return
    call_frames = state.get("call_frames")
    if not isinstance(call_frames, Mapping):
        _raise_integrity_error(
            bundle,
            state,
            scope_path,
            reason="unsupported_shape",
            field="call_frames",
            offending_value=call_frames,
        )

    grouped_frames: dict[
        str,
        tuple[Any, list[tuple[str, Mapping[str, Any]]]],
    ] = {}
    for frame_id, frame in call_frames.items():
        field_prefix = (
            f"call_frames.{frame_id}"
            if isinstance(frame_id, str) and frame_id
            else "call_frames"
        )
        if not isinstance(frame_id, str) or not frame_id:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="unsupported_shape",
                field="call_frames",
                offending_value=frame_id,
            )
        if not isinstance(frame, Mapping):
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="unsupported_shape",
                field=field_prefix,
                offending_value=frame,
            )

        call_step_id = frame.get("call_step_id")
        if call_step_id is None or call_step_id == "":
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="missing_required_identity",
                field=f"{field_prefix}.call_step_id",
                offending_value=None,
            )
        if not isinstance(call_step_id, str):
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="unsupported_shape",
                field=f"{field_prefix}.call_step_id",
                offending_value=call_step_id,
                candidate_count=0,
            )

        step_resolution = bundle.projection.resolve_resume_step_id(
            slot_index,
            call_step_id,
        )
        if step_resolution.exact_identity_candidate_count == 0:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="out_of_scope_step_id",
                field=f"{field_prefix}.call_step_id",
                offending_value=call_step_id,
                candidate_count=0,
                call_boundary_step_id=call_step_id,
            )

        boundary_resolution = bundle.projection.resolve_call_boundary(
            slot_index,
            call_step_id,
        )
        if boundary_resolution.candidate_count == 0:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="missing_call_boundary",
                field=f"{field_prefix}.call_step_id",
                offending_value=call_step_id,
                candidate_count=0,
                call_boundary_step_id=call_step_id,
            )
        if boundary_resolution.candidate_count != 1:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="ambiguous_call_boundary",
                field=f"{field_prefix}.call_step_id",
                offending_value=call_step_id,
                candidate_count=boundary_resolution.candidate_count,
                call_boundary_step_id=call_step_id,
            )
        assert boundary_resolution.boundary is not None
        current_alias = boundary_resolution.boundary.import_alias

        persisted_alias = frame.get("import_alias")
        if not isinstance(persisted_alias, str) or not persisted_alias:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="unsupported_shape",
                field=f"{field_prefix}.import_alias",
                offending_value=persisted_alias,
                candidate_count=1,
                call_boundary_step_id=call_step_id,
            )
        if persisted_alias != current_alias:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="persisted_import_alias_mismatch",
                field=f"{field_prefix}.import_alias",
                offending_value=persisted_alias,
                candidate_count=1,
                call_boundary_step_id=call_step_id,
            )

        imported_bundle = bundle.imports.get(current_alias)
        if not isinstance(imported_bundle, LoadedWorkflowBundle):
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason="missing_imported_bundle",
                field=f"imports.{current_alias}",
                offending_value=current_alias,
                candidate_count=1,
                call_boundary_step_id=call_step_id,
            )
        existing_group = grouped_frames.get(call_step_id)
        if existing_group is None:
            grouped_frames[call_step_id] = (
                imported_bundle,
                [(frame_id, frame)],
            )
        else:
            existing_group[1].append((frame_id, frame))

    for call_step_id, (imported_bundle, frame_items) in grouped_frames.items():
        try:
            index_retry_lineage(
                call_step_id,
                frame_items,
                frontend_kind=imported_bundle.provenance.frontend_kind,
            )
        except CallFrameRetryLineageError as exc:
            _raise_integrity_error(
                bundle,
                state,
                scope_path,
                reason=exc.reason,
                field="call_frames",
                offending_value=exc.offending_value,
                candidate_count=(
                    len(frame_items)
                    if exc.reason == "ambiguous_resumable_call_frame"
                    else None
                ),
                call_boundary_step_id=call_step_id,
            )


def _explicit_step_result_rows(
    steps: Mapping[str, Any],
) -> Iterator[tuple[str, Any]]:
    """Yield explicit step-result identities without inspecting result payloads."""
    for presentation_key, value in steps.items():
        if not isinstance(presentation_key, str):
            continue
        if isinstance(value, Mapping):
            if "step_id" in value:
                yield presentation_key, value.get("step_id")
            continue
        if not isinstance(value, list):
            continue
        for iteration_index, iteration_rows in enumerate(value):
            if not isinstance(iteration_rows, Mapping):
                continue
            for nested_key, nested_value in iteration_rows.items():
                if (
                    isinstance(nested_key, str)
                    and isinstance(nested_value, Mapping)
                    and "step_id" in nested_value
                ):
                    yield (
                        f"{presentation_key}[{iteration_index}].{nested_key}",
                        nested_value.get("step_id"),
                    )


def _projection_failure_field(message: str) -> str | None:
    """Extract the stable state-field prefix from a typed projection failure."""
    if not isinstance(message, str) or not message:
        return None
    field = message.split(" ", 1)[0]
    return field if field else None


def _identity_only_value(value: Any) -> Any:
    """Return bounded identity metadata, never whole state or private payloads."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:_MAX_DIAGNOSTIC_STRING_LENGTH]
    if isinstance(value, (list, tuple)) and len(value) <= 8:
        bounded = [_identity_only_value(item) for item in value]
        if all(item is not None for item in bounded):
            return bounded
    return None


def _raise_integrity_error(
    bundle: LoadedWorkflowBundle,
    state: Mapping[str, Any],
    scope_path: ResumeScopePath,
    *,
    reason: str,
    field: str | None,
    offending_value: Any,
    candidate_count: int | None = None,
    call_boundary_step_id: str | None = None,
) -> None:
    workflow_file = str(bundle.provenance.workflow_path)
    workflow_checksum = state.get("workflow_checksum")
    error = {
        "type": _ERROR_TYPE,
        "message": f"Resume projection integrity audit failed: {reason}",
        "context": {
            "diagnostic_schema": _DIAGNOSTIC_SCHEMA,
            "reason": reason,
            "scope_path": scope_path.as_context(),
            "field": field,
            "offending_value": _identity_only_value(offending_value),
            "expected_owner": {
                "workflow_file": workflow_file,
                "workflow_checksum": (
                    workflow_checksum if isinstance(workflow_checksum, str) else None
                ),
                "projection_scope": scope_path.projection_scope,
            },
            "candidate_count": (
                candidate_count
                if isinstance(candidate_count, int)
                and not isinstance(candidate_count, bool)
                else None
            ),
            "call_boundary_step_id": (
                call_boundary_step_id
                if isinstance(call_boundary_step_id, str)
                else None
            ),
        },
    }
    raise ResumeProjectionIntegrityError(error)


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
