"""Immutable dependency-content snapshots and byte-exact prompt rendering."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal


MAX_INJECTION_BYTES = 262144
TRUNCATION_SUMMARY_RESERVE_BYTES = 512
MAX_INSTRUCTION_BYTES = 261630

DependencyRole = Literal["required", "optional"]
TruncationStatus = Literal["complete", "truncated", "omitted"]


def _validate_canonical_target(target: str) -> None:
    if not isinstance(target, str) or not target or "\\" in target:
        raise ValueError(f"invalid canonical POSIX target: {target!r}")
    path = PurePosixPath(target)
    if path.is_absolute() or ".." in path.parts or str(path) != target or target == ".":
        raise ValueError(f"invalid canonical POSIX target: {target!r}")


def _immutable_utf8_bytes(value: bytes) -> bytes:
    try:
        immutable = bytes(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("normalized dependency content must be bytes") from exc
    try:
        immutable.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("normalized dependency content must be valid UTF-8") from exc
    return immutable


def _strict_utf8_prefix(value: bytes, maximum_bytes: int) -> bytes:
    prefix = value[: max(0, maximum_bytes)]
    while prefix:
        try:
            prefix.decode("utf-8")
            return prefix
        except UnicodeDecodeError as exc:
            prefix = prefix[: exc.start]
    return b""


@dataclass(frozen=True)
class AuthoredDependencyRow:
    """One evaluated authored dependency row before canonical de-duplication."""

    role: DependencyRole
    authored_index: int
    binding_ref: str
    evaluated_relpath: str
    canonical_target: str | None

    def __post_init__(self) -> None:
        if self.role not in ("required", "optional"):
            raise ValueError(f"invalid dependency role: {self.role!r}")
        if not isinstance(self.authored_index, int) or self.authored_index < 0:
            raise ValueError("authored dependency index must be a non-negative integer")
        if not isinstance(self.binding_ref, str) or not self.binding_ref:
            raise ValueError("dependency binding_ref must be a non-empty string")
        if not isinstance(self.evaluated_relpath, str) or not self.evaluated_relpath:
            raise ValueError("dependency evaluated_relpath must be a non-empty string")
        if self.canonical_target is not None:
            _validate_canonical_target(self.canonical_target)


@dataclass(frozen=True)
class DependencyContent:
    """Verified normalized in-memory bytes for one canonical dependency target."""

    canonical_target: str
    normalized_bytes: bytes

    def __post_init__(self) -> None:
        _validate_canonical_target(self.canonical_target)
        object.__setattr__(self, "normalized_bytes", _immutable_utf8_bytes(self.normalized_bytes))


@dataclass(frozen=True)
class CanonicalDependencyGroup:
    """Canonical content plus every authored row that aliases it."""

    canonical_target: str
    effective_role: DependencyRole
    authored_rows: tuple[AuthoredDependencyRow, ...]
    normalized_bytes: bytes
    normalized_total_bytes: int

    def __post_init__(self) -> None:
        _validate_canonical_target(self.canonical_target)
        if self.effective_role not in ("required", "optional"):
            raise ValueError(f"invalid dependency role: {self.effective_role!r}")
        if not isinstance(self.authored_rows, tuple) or not all(
            isinstance(row, AuthoredDependencyRow) for row in self.authored_rows
        ):
            raise ValueError("canonical dependency group authored rows must be a tuple")
        if len(self.authored_rows) != len(set(self.authored_rows)):
            raise ValueError("canonical dependency group authored rows must be unique")
        identities = tuple((row.role, row.authored_index) for row in self.authored_rows)
        if len(identities) != len(set(identities)):
            raise ValueError("canonical dependency group authored identities must be unique")
        if self.authored_rows != tuple(sorted(self.authored_rows, key=_evidence_key)):
            raise ValueError("canonical dependency group rows must use evidence order")
        if not self.authored_rows or any(
            row.canonical_target != self.canonical_target for row in self.authored_rows
        ):
            raise ValueError("canonical dependency group membership is inconsistent")
        expected_role = (
            "required" if any(row.role == "required" for row in self.authored_rows) else "optional"
        )
        if self.effective_role != expected_role:
            raise ValueError("canonical dependency group effective role is inconsistent")
        immutable = _immutable_utf8_bytes(self.normalized_bytes)
        object.__setattr__(self, "normalized_bytes", immutable)
        if self.normalized_total_bytes < len(immutable):
            raise ValueError("canonical dependency group byte totals are inconsistent")


@dataclass(frozen=True)
class DependencyContentSnapshot:
    """Attempt-wide immutable dependency evidence and bounded retained content."""

    authored_rows: tuple[AuthoredDependencyRow, ...]
    absent_rows: tuple[AuthoredDependencyRow, ...]
    canonical_groups: tuple[CanonicalDependencyGroup, ...]
    retained_content_bytes: int

    def __post_init__(self) -> None:
        if not isinstance(self.authored_rows, tuple) or not all(
            isinstance(row, AuthoredDependencyRow) for row in self.authored_rows
        ):
            raise ValueError("snapshot authored rows must be a tuple")
        if not isinstance(self.absent_rows, tuple) or not all(
            isinstance(row, AuthoredDependencyRow) for row in self.absent_rows
        ):
            raise ValueError("snapshot absent rows must be a tuple")
        if not isinstance(self.canonical_groups, tuple) or not all(
            isinstance(group, CanonicalDependencyGroup) for group in self.canonical_groups
        ):
            raise ValueError("snapshot canonical groups must be a tuple")
        identities = tuple((row.role, row.authored_index) for row in self.authored_rows)
        if len(self.authored_rows) != len(set(self.authored_rows)) or len(identities) != len(
            set(identities)
        ):
            raise ValueError("snapshot authored rows must be unique")
        _validate_contiguous_indices(self.authored_rows)
        if self.authored_rows != tuple(sorted(self.authored_rows, key=_evidence_key)):
            raise ValueError("snapshot authored rows must use evidence order")
        if self.retained_content_bytes != sum(
            len(group.normalized_bytes) for group in self.canonical_groups
        ):
            raise ValueError("snapshot retained-content byte total is inconsistent")
        if self.retained_content_bytes > MAX_INJECTION_BYTES:
            raise ValueError("snapshot retained-content budget exceeded")
        if self.absent_rows != tuple(
            row for row in self.authored_rows if row.canonical_target is None
        ):
            raise ValueError("snapshot absent-row membership is inconsistent")
        if any(row.role != "optional" for row in self.absent_rows):
            raise ValueError("snapshot absent dependency rows must be optional")
        present_rows = tuple(
            row for row in self.authored_rows if row.canonical_target is not None
        )
        grouped_rows = tuple(
            row for group in self.canonical_groups for row in group.authored_rows
        )
        if Counter(grouped_rows) != Counter(present_rows):
            raise ValueError("snapshot canonical group membership must be exactly one-to-one")
        targets = tuple(group.canonical_target for group in self.canonical_groups)
        if targets != tuple(sorted(targets)) or len(targets) != len(set(targets)):
            raise ValueError("snapshot canonical groups must be sorted and unique")


@dataclass(frozen=True)
class DependencyGroupTruncation:
    """Rendered byte disposition for one canonical dependency group."""

    canonical_target: str
    status: TruncationStatus
    shown_bytes: int
    total_bytes: int


@dataclass(frozen=True)
class RenderedContentSnapshot:
    """Byte-exact dependency block and immutable per-group render metadata."""

    block: bytes
    pre_truncation_bytes: int
    was_truncated: bool
    summary: bytes
    group_truncations: tuple[DependencyGroupTruncation, ...]


def _evidence_key(row: AuthoredDependencyRow) -> tuple[int, int]:
    return (0 if row.role == "required" else 1, row.authored_index)


def _validate_contiguous_indices(rows: tuple[AuthoredDependencyRow, ...]) -> None:
    for role in ("required", "optional"):
        indices = sorted(row.authored_index for row in rows if row.role == role)
        if indices != list(range(len(indices))):
            raise ValueError(f"{role} authored dependency indices must be contiguous")


def build_content_snapshot(
    authored_rows: Iterable[AuthoredDependencyRow],
    contents: Iterable[DependencyContent],
) -> DependencyContentSnapshot:
    """Group aliases and retain at most one attempt-wide content budget."""

    rows = tuple(authored_rows)
    if not all(isinstance(row, AuthoredDependencyRow) for row in rows):
        raise ValueError("snapshot rows must be AuthoredDependencyRow values")
    _validate_contiguous_indices(rows)
    ordered_rows = tuple(sorted(rows, key=_evidence_key))

    payload_rows = tuple(contents)
    if not all(isinstance(content, DependencyContent) for content in payload_rows):
        raise ValueError("snapshot payloads must be DependencyContent values")
    payload_targets = tuple(content.canonical_target for content in payload_rows)
    if len(payload_targets) != len(set(payload_targets)):
        raise ValueError("dependency content targets must be unique")
    payloads = {content.canonical_target: content.normalized_bytes for content in payload_rows}

    referenced_targets = {
        row.canonical_target for row in ordered_rows if row.canonical_target is not None
    }
    if referenced_targets != set(payloads):
        raise ValueError("dependency payload membership must exactly match present authored rows")

    retained = 0
    groups: list[CanonicalDependencyGroup] = []
    for target in sorted(referenced_targets):
        aliases = tuple(row for row in ordered_rows if row.canonical_target == target)
        payload = payloads[target]
        retained_payload = _strict_utf8_prefix(payload, MAX_INJECTION_BYTES - retained)
        retained += len(retained_payload)
        groups.append(
            CanonicalDependencyGroup(
                canonical_target=target,
                effective_role=(
                    "required" if any(row.role == "required" for row in aliases) else "optional"
                ),
                authored_rows=aliases,
                normalized_bytes=retained_payload,
                normalized_total_bytes=len(payload),
            )
        )

    return DependencyContentSnapshot(
        authored_rows=ordered_rows,
        absent_rows=tuple(row for row in ordered_rows if row.canonical_target is None),
        canonical_groups=tuple(groups),
        retained_content_bytes=retained,
    )


def _render_header(target: str, shown_bytes: int, total_bytes: int) -> bytes:
    return f"\n\n=== File: {target} ({shown_bytes}/{total_bytes} bytes) ===\n".encode("utf-8")


def _render_truncation_summary(
    truncations: tuple[DependencyGroupTruncation, ...],
) -> bytes:
    files_shown = sum(row.status != "omitted" for row in truncations)
    files_truncated = sum(row.status == "truncated" for row in truncations)
    files_omitted = sum(row.status == "omitted" for row in truncations)
    return (
        f"\n\n... Injection truncated at {MAX_INJECTION_BYTES} bytes. "
        f"Files: {files_shown} shown, {files_truncated} truncated, "
        f"{files_omitted} omitted."
    ).encode("utf-8")


def _next_utf8_boundary(value: bytes, start: int) -> int:
    first = value[start]
    if first < 0x80:
        width = 1
    elif first < 0xE0:
        width = 2
    elif first < 0xF0:
        width = 3
    else:
        width = 4
    return min(len(value), start + width)


def _largest_fitting_prefix(
    group: CanonicalDependencyGroup,
    *,
    available_bytes: int,
    marker: bytes,
) -> bytes:
    zero_header = _render_header(group.canonical_target, 0, group.normalized_total_bytes)
    maximum_prefix = available_bytes - len(zero_header) - len(marker)
    prefix = _strict_utf8_prefix(group.normalized_bytes, maximum_prefix)

    while prefix:
        header = _render_header(
            group.canonical_target, len(prefix), group.normalized_total_bytes
        )
        overflow = len(header) + len(prefix) + len(marker) - available_bytes
        if overflow <= 0:
            break
        prefix = _strict_utf8_prefix(prefix, len(prefix) - overflow)

    while len(prefix) < len(group.normalized_bytes):
        next_boundary = _next_utf8_boundary(group.normalized_bytes, len(prefix))
        candidate = group.normalized_bytes[:next_boundary]
        header = _render_header(
            group.canonical_target, len(candidate), group.normalized_total_bytes
        )
        if len(header) + len(candidate) + len(marker) > available_bytes:
            break
        prefix = candidate

    return prefix


def _render_truncated_body(
    snapshot: DependencyContentSnapshot,
    instruction_bytes: bytes,
    *,
    summary_budget: int,
) -> tuple[bytes, tuple[DependencyGroupTruncation, ...]]:
    render_limit = MAX_INJECTION_BYTES - summary_budget
    block_parts = [instruction_bytes]
    rendered_bytes = len(instruction_bytes)
    truncations: list[DependencyGroupTruncation] = []
    stopped = False
    marker = b"\n... (truncated)"

    for group in snapshot.canonical_groups:
        if stopped:
            truncations.append(
                DependencyGroupTruncation(
                    group.canonical_target, "omitted", 0, group.normalized_total_bytes
                )
            )
            continue

        full_header = _render_header(
            group.canonical_target,
            group.normalized_total_bytes,
            group.normalized_total_bytes,
        )
        if (
            len(group.normalized_bytes) == group.normalized_total_bytes
            and rendered_bytes + len(full_header) + len(group.normalized_bytes) <= render_limit
        ):
            block_parts.extend((full_header, group.normalized_bytes))
            rendered_bytes += len(full_header) + len(group.normalized_bytes)
            truncations.append(
                DependencyGroupTruncation(
                    group.canonical_target,
                    "complete",
                    group.normalized_total_bytes,
                    group.normalized_total_bytes,
                )
            )
            continue

        prefix = _largest_fitting_prefix(
            group,
            available_bytes=render_limit - rendered_bytes,
            marker=marker,
        )
        if prefix:
            header = _render_header(
                group.canonical_target, len(prefix), group.normalized_total_bytes
            )
            block_parts.extend((header, prefix, marker))
            rendered_bytes += len(header) + len(prefix) + len(marker)
            truncations.append(
                DependencyGroupTruncation(
                    group.canonical_target,
                    "truncated",
                    len(prefix),
                    group.normalized_total_bytes,
                )
            )
        else:
            truncations.append(
                DependencyGroupTruncation(
                    group.canonical_target, "omitted", 0, group.normalized_total_bytes
                )
            )
        stopped = True

    return b"".join(block_parts), tuple(truncations)


def render_content_snapshot(
    snapshot: DependencyContentSnapshot,
    instruction: str | None,
    default_instruction: Callable[[str, bool], str] | None = None,
) -> RenderedContentSnapshot:
    """Render one immutable snapshot within the exact UTF-8 injection cap."""

    if not isinstance(snapshot, DependencyContentSnapshot):
        raise ValueError("content renderer requires a DependencyContentSnapshot")
    if instruction is None:
        if default_instruction is None:
            raise ValueError("content renderer requires an instruction selector")
        has_required = any(row.role == "required" for row in snapshot.authored_rows)
        instruction = default_instruction("content", has_required)
    if not isinstance(instruction, str):
        raise ValueError("dependency instruction must be a string")
    instruction_bytes = instruction.encode("utf-8")
    if len(instruction_bytes) > MAX_INSTRUCTION_BYTES:
        raise ValueError("dependency_instruction_exceeds_byte_limit")

    pre_truncation_bytes = len(instruction_bytes) + sum(
        len(
            _render_header(
                group.canonical_target,
                group.normalized_total_bytes,
                group.normalized_total_bytes,
            )
        )
        + group.normalized_total_bytes
        for group in snapshot.canonical_groups
    )
    content_was_retained = all(
        len(group.normalized_bytes) == group.normalized_total_bytes
        for group in snapshot.canonical_groups
    )

    if pre_truncation_bytes <= MAX_INJECTION_BYTES and content_was_retained:
        block_parts: list[bytes] = [instruction_bytes]
        truncations: list[DependencyGroupTruncation] = []
        for group in snapshot.canonical_groups:
            block_parts.extend(
                (
                    _render_header(
                        group.canonical_target,
                        group.normalized_total_bytes,
                        group.normalized_total_bytes,
                    ),
                    group.normalized_bytes,
                )
            )
            truncations.append(
                DependencyGroupTruncation(
                    group.canonical_target,
                    "complete",
                    group.normalized_total_bytes,
                    group.normalized_total_bytes,
                )
            )
        return RenderedContentSnapshot(
            block=b"".join(block_parts),
            pre_truncation_bytes=pre_truncation_bytes,
            was_truncated=False,
            summary=b"",
            group_truncations=tuple(truncations),
        )

    summary_budget = TRUNCATION_SUMMARY_RESERVE_BYTES
    seen_budget_indices: dict[int, int] = {}
    candidates: list[
        tuple[
            int,
            bytes,
            tuple[DependencyGroupTruncation, ...],
            bytes,
        ]
    ] = []
    while True:
        seen_budget_indices[summary_budget] = len(candidates)
        body, frozen_truncations = _render_truncated_body(
            snapshot,
            instruction_bytes,
            summary_budget=summary_budget,
        )
        summary = _render_truncation_summary(frozen_truncations)
        if len(summary) > TRUNCATION_SUMMARY_RESERVE_BYTES:
            raise ValueError("dependency_truncation_summary_exceeds_reserve")
        candidates.append((summary_budget, body, frozen_truncations, summary))
        if len(summary) == summary_budget:
            break
        next_budget = len(summary)
        if next_budget in seen_budget_indices:
            cycle_start = seen_budget_indices[next_budget]
            feasible_cycle = [
                (cycle_index, candidate)
                for cycle_index, candidate in enumerate(candidates[cycle_start:])
                if len(candidate[1]) + len(candidate[3]) <= MAX_INJECTION_BYTES
            ]
            if not feasible_cycle:
                raise ValueError("dependency_truncation_summary_cycle_has_no_feasible_render")
            _, selected = max(
                feasible_cycle,
                key=lambda item: (
                    sum(row.shown_bytes for row in item[1][2]),
                    len(item[1][1]),
                    -item[0],
                ),
            )
            _, body, frozen_truncations, summary = selected
            break
        summary_budget = next_budget

    block = body + summary
    if len(block) > MAX_INJECTION_BYTES:
        raise ValueError("dependency rendered block exceeds byte limit")
    return RenderedContentSnapshot(
        block=block,
        pre_truncation_bytes=pre_truncation_bytes,
        was_truncated=True,
        summary=summary,
        group_truncations=frozen_truncations,
    )


__all__ = [
    "MAX_INJECTION_BYTES",
    "MAX_INSTRUCTION_BYTES",
    "TRUNCATION_SUMMARY_RESERVE_BYTES",
    "AuthoredDependencyRow",
    "CanonicalDependencyGroup",
    "DependencyContent",
    "DependencyContentSnapshot",
    "DependencyGroupTruncation",
    "RenderedContentSnapshot",
    "build_content_snapshot",
    "render_content_snapshot",
]
