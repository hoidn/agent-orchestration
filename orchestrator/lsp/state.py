"""Immutable initialization state for the Workflow Lisp language server."""

from __future__ import annotations

import math
import os
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from urllib.parse import unquote_to_bytes, urlsplit

from orchestrator.workflow_lisp import compiler
from orchestrator.workflow_lisp.compiler import Stage3ValidationProfile
from orchestrator.workflow_lisp.lints import LINT_PROFILE_DEFAULT
from orchestrator.workflow_lisp.wcc.route import LoweringRoute, normalize_lowering_route

from .diagnostics import DiagnosticContribution

_CONFIGURATION_PATH_FIELDS = (
    "provider_externs_path",
    "prompt_externs_path",
    "imported_workflow_bundles_path",
    "command_boundaries_path",
)
_ALLOWED_INITIALIZATION_OPTIONS = frozenset(
    {
        "source_roots",
        "entry_workflows",
        *_CONFIGURATION_PATH_FIELDS,
    }
)
_L3_INITIALIZATION_ERROR_SCHEMA = "workflow_lisp_lsp_initialization_error.v1"


@dataclass(frozen=True, slots=True)
class LspConfigurationPaths:
    """Canonical optional paths that configure one server lifetime."""

    provider_externs_path: Path | None = None
    prompt_externs_path: Path | None = None
    imported_workflow_bundles_path: Path | None = None
    command_boundaries_path: Path | None = None


@dataclass(frozen=True, slots=True)
class LspInitializationOptions:
    """Normalized caller options and fixed production compile policy."""

    source_roots: tuple[Path, ...]
    entry_workflows: tuple[tuple[Path, str], ...]
    configuration: LspConfigurationPaths
    validation_profile: Stage3ValidationProfile
    lint_profile: str
    lowering_route: LoweringRoute


@dataclass(frozen=True, slots=True)
class ImmutableConfigurationVector:
    """Exact initialization context that remains fixed for one server lifetime."""

    configured_paths: tuple[tuple[str, Path | None], ...]
    configuration_revisions: tuple[tuple[Path, str], ...]
    recursively_imported_source_revisions: tuple[tuple[Path, str], ...]
    builtin_stdlib_source_root: Path


@dataclass(frozen=True, slots=True)
class DiskSourceSnapshot:
    """One exact raw-byte disk probe projected for clean-buffer comparison."""

    canonical_path: Path
    revision: str
    raw_decoded_text: str | None


BufferStatus = Literal["clean", "dirty", "unavailable"]
CompileStatus = Literal[
    "idle",
    "pending",
    "success",
    "language_error",
    "server_error",
]
CompletionRecoverySelection = Literal["static-incomplete", "empty"]


@dataclass(frozen=True, slots=True)
class AcceptedCompileSnapshot:
    """Opaque accepted build value bound to its exact source revision vector."""

    build_value: object
    source_revision_vector: tuple[tuple[Path, str], ...]
    accepted_text_by_path: tuple[tuple[Path, str], ...] = ()


@dataclass(frozen=True, slots=True)
class CompileEntryState:
    """One immutable compile-entry lifecycle placeholder."""

    path: Path
    disk_snapshot: DiskSourceSnapshot | None
    editor_text: str | None
    generation: int
    pending_generation: int | None
    buffer_status: BufferStatus
    compile_status: CompileStatus
    accepted_snapshot: AcceptedCompileSnapshot | None
    dependency_closure: frozenset[Path] | None = None
    dependency_revision_vector: tuple[tuple[Path, str], ...] | None = None
    diagnostic_contributions: tuple[DiagnosticContribution, ...] = ()

    @property
    def navigation_snapshot(self) -> AcceptedCompileSnapshot | None:
        """Expose navigation authority only for a clean successful completion."""

        if self.buffer_status == "clean" and self.compile_status == "success":
            return self.accepted_snapshot
        return None


@dataclass(frozen=True, slots=True)
class LspState:
    """Initialization-only state owned by one language-server process."""

    workspace_root: Path
    builtin_stdlib_source_root: Path
    options: LspInitializationOptions
    entries: tuple[CompileEntryState, ...]
    configuration_vector: ImmutableConfigurationVector | None = None
    configuration_stale: bool = False


@dataclass(frozen=True, slots=True)
class StateEffects:
    """Pure scheduling/publication effects emitted by one state transition."""

    scheduled_generations: tuple[tuple[Path, int], ...] = ()
    canceled_generations: tuple[tuple[Path, int], ...] = ()
    republish_uris: tuple[str, ...] = ()
    restart_notice_required: bool = False


@dataclass(frozen=True, slots=True)
class LspStateTransition:
    """One immutable state replacement plus its explicit effects."""

    state: LspState
    effects: StateEffects


class LspInitializationError(ValueError):
    """Coded fail-closed initialization refusal."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        data: dict[str, object] | None = None,
    ) -> None:
        self.code = code
        self.data = data
        super().__init__(f"{code}: {message}")


def initialize_lsp_state(
    *,
    root_uri: str | None = None,
    workspace_folder_uris: Iterable[str] = (),
    initialization_options: Mapping[str, object] | None = None,
    entry_paths: Iterable[str | Path] = (),
) -> LspState:
    """Create the immutable initialization state."""

    canonical_roots = canonicalize_workspace_roots(
        root_uri=root_uri,
        workspace_folder_uris=workspace_folder_uris,
    )
    if len(canonical_roots) != 1:
        raise LspInitializationError(
            "lsp_workspace_root_count_invalid",
            "initialization requires exactly one distinct canonical workspace root",
        )
    workspace_root = next(iter(canonical_roots))
    if initialization_options is None:
        raw_options: Mapping[str, object] = {}
    elif not isinstance(initialization_options, Mapping):
        raise LspInitializationError(
            "lsp_initialization_option_invalid",
            "initialization_options must be a mapping when supplied",
        )
    else:
        raw_options = initialization_options
    if any(not isinstance(key, str) for key in raw_options):
        raise TypeError("initialization option keys must be JSON strings")
    for l3_field in ("entry_workflow", "entry_workflows"):
        if l3_field in raw_options:
            _require_json_value(
                raw_options[l3_field],
                label=l3_field,
            )
    unsupported_options = tuple(
        sorted(key for key in raw_options if key not in _ALLOWED_INITIALIZATION_OPTIONS)
    )
    if unsupported_options:
        unsupported_field = unsupported_options[0]
        data = (
            _l3_initialization_error_data(
                code="lsp_initialization_option_unsupported",
                field="entry_workflow",
                rule="unsupported_field",
                rejected_value=raw_options[unsupported_field],
            )
            if unsupported_field == "entry_workflow"
            else None
        )
        raise LspInitializationError(
            "lsp_initialization_option_unsupported",
            f"unsupported initialization option: {unsupported_field!r}",
            data=data,
        )

    entry_workflows = _normalize_entry_workflows(
        raw_options.get("entry_workflows", {}),
        workspace_root=workspace_root,
    )
    source_roots = _canonical_source_roots(
        raw_options.get("source_roots", ()),
        workspace_root=workspace_root,
    )
    canonical_entry_paths = tuple(
        _canonical_contained_path(
            raw_entry,
            workspace_root=workspace_root,
            code="lsp_entry_path_uncontained",
            label="entry path",
        )
        for raw_entry in entry_paths
    )
    if len(frozenset(canonical_entry_paths)) != len(canonical_entry_paths):
        raise LspInitializationError(
            "lsp_entry_path_duplicate",
            "entry_paths must not contain duplicate canonical paths",
        )
    canonical_entries = tuple(
        CompileEntryState(
            path=entry_path,
            disk_snapshot=None,
            editor_text=None,
            generation=0,
            pending_generation=None,
            buffer_status="unavailable",
            compile_status="idle",
            accepted_snapshot=None,
        )
        for entry_path in canonical_entry_paths
    )
    return LspState(
        workspace_root=workspace_root,
        builtin_stdlib_source_root=_canonical_path(
            compiler._builtin_stdlib_source_root()
        ),
        options=LspInitializationOptions(
            source_roots=source_roots,
            entry_workflows=entry_workflows,
            configuration=LspConfigurationPaths(
                provider_externs_path=_canonical_optional_path(
                    raw_options.get("provider_externs_path"),
                    workspace_root=workspace_root,
                    field_name="provider_externs_path",
                ),
                prompt_externs_path=_canonical_optional_path(
                    raw_options.get("prompt_externs_path"),
                    workspace_root=workspace_root,
                    field_name="prompt_externs_path",
                ),
                imported_workflow_bundles_path=_canonical_optional_path(
                    raw_options.get("imported_workflow_bundles_path"),
                    workspace_root=workspace_root,
                    field_name="imported_workflow_bundles_path",
                ),
                command_boundaries_path=_canonical_optional_path(
                    raw_options.get("command_boundaries_path"),
                    workspace_root=workspace_root,
                    field_name="command_boundaries_path",
                ),
            ),
            validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
            lint_profile=LINT_PROFILE_DEFAULT,
            lowering_route=normalize_lowering_route(None),
        ),
        entries=canonical_entries,
    )


def _normalize_entry_workflows(
    raw_entry_workflows: object,
    *,
    workspace_root: Path,
) -> tuple[tuple[Path, str], ...]:
    if not isinstance(raw_entry_workflows, dict):
        raise LspInitializationError(
            "lsp_initialization_option_invalid",
            "entry_workflows must be a JSON object",
            data=_l3_initialization_error_data(
                code="lsp_initialization_option_invalid",
                field="entry_workflows",
                rule="mapping_required",
                rejected_value=raw_entry_workflows,
            ),
        )

    normalized_rows: list[tuple[Path, str, str]] = []
    for raw_key in sorted(raw_entry_workflows):
        if not raw_key:
            raise LspInitializationError(
                "lsp_initialization_option_invalid",
                "entry_workflows keys must be non-empty strings",
                data=_l3_initialization_error_data(
                    code="lsp_initialization_option_invalid",
                    field="entry_workflows",
                    rule="key_nonempty_string_required",
                    rejected_value=raw_key,
                ),
            )
        raw_value = raw_entry_workflows[raw_key]
        if not isinstance(raw_value, str) or not raw_value:
            raise LspInitializationError(
                "lsp_initialization_option_invalid",
                "entry_workflows values must be non-empty strings",
                data=_l3_initialization_error_data(
                    code="lsp_initialization_option_invalid",
                    field="entry_workflows",
                    rule="entry_value_nonempty_string_required",
                    rejected_value=raw_value,
                    entry_key=raw_key,
                ),
            )
        path = Path(raw_key)
        if not path.is_absolute():
            path = workspace_root / path
        try:
            canonical_path = _canonical_path(path)
        except (OSError, RuntimeError, ValueError) as exc:
            raise LspInitializationError(
                "lsp_initialization_option_invalid",
                "entry_workflows keys must canonicalize as filesystem paths",
                data=_l3_initialization_error_data(
                    code="lsp_initialization_option_invalid",
                    field="entry_workflows",
                    rule="canonical_path_required",
                    rejected_value=raw_key,
                    entry_key=raw_key,
                ),
            ) from exc
        if canonical_path.suffix != ".orc":
            raise LspInitializationError(
                "lsp_initialization_option_invalid",
                "entry_workflows keys must canonicalize to .orc paths",
                data=_l3_initialization_error_data(
                    code="lsp_initialization_option_invalid",
                    field="entry_workflows",
                    rule="orc_suffix_required",
                    rejected_value=raw_key,
                    entry_key=raw_key,
                    canonical_path=canonical_path.as_posix(),
                ),
            )
        try:
            canonical_path.relative_to(workspace_root)
        except ValueError as exc:
            raise LspInitializationError(
                "lsp_entry_workflow_path_uncontained",
                "entry_workflows keys must remain inside the workspace",
                data=_l3_initialization_error_data(
                    code="lsp_entry_workflow_path_uncontained",
                    field="entry_workflows",
                    rule="workspace_containment_required",
                    rejected_value=raw_key,
                    entry_key=raw_key,
                    canonical_path=canonical_path.as_posix(),
                ),
            ) from exc
        normalized_rows.append((canonical_path, raw_value, raw_key))

    rows_by_path: dict[Path, list[tuple[str, str]]] = {}
    for canonical_path, raw_value, raw_key in normalized_rows:
        rows_by_path.setdefault(canonical_path, []).append((raw_key, raw_value))
    for canonical_path in sorted(rows_by_path):
        rows = sorted(rows_by_path[canonical_path])
        if len(rows) > 1:
            conflicting_entry_key = rows[0][0]
            entry_key = rows[1][0]
            raise LspInitializationError(
                "lsp_entry_workflow_path_duplicate",
                "entry_workflows keys must identify unique canonical paths",
                data=_l3_initialization_error_data(
                    code="lsp_entry_workflow_path_duplicate",
                    field="entry_workflows",
                    rule="canonical_path_unique",
                    rejected_value=entry_key,
                    entry_key=entry_key,
                    canonical_path=canonical_path.as_posix(),
                    conflicting_entry_key=conflicting_entry_key,
                ),
            )
    return tuple(
        (canonical_path, raw_value)
        for canonical_path, raw_value, _raw_key in sorted(normalized_rows)
    )


def _l3_initialization_error_data(
    *,
    code: str,
    field: str,
    rule: str,
    rejected_value: object,
    entry_key: str | None = None,
    canonical_path: str | None = None,
    conflicting_entry_key: str | None = None,
) -> dict[str, object]:
    data: dict[str, object] = {
        "schema": _L3_INITIALIZATION_ERROR_SCHEMA,
        "code": code,
        "field": field,
        "rule": rule,
        "rejected_value": rejected_value,
    }
    if entry_key is not None:
        data["entry_key"] = entry_key
    if canonical_path is not None:
        data["canonical_path"] = canonical_path
    if conflicting_entry_key is not None:
        data["conflicting_entry_key"] = conflicting_entry_key
    return data


def _require_json_value(
    value: object,
    *,
    label: str,
    _active_container_ids: set[int] | None = None,
) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if math.isfinite(value):
            return
        raise TypeError(f"{label} must contain only JSON values")
    if isinstance(value, (list, dict)):
        active_container_ids = (
            set()
            if _active_container_ids is None
            else _active_container_ids
        )
        container_id = id(value)
        if container_id in active_container_ids:
            raise TypeError(f"{label} must not contain recursive containers")
        active_container_ids.add(container_id)
        try:
            if isinstance(value, list):
                items = value
            else:
                if any(not isinstance(key, str) for key in value):
                    raise TypeError(f"{label} object keys must be JSON strings")
                items = value.values()
            for item in items:
                _require_json_value(
                    item,
                    label=label,
                    _active_container_ids=active_container_ids,
                )
        finally:
            active_container_ids.remove(container_id)
        return
    raise TypeError(f"{label} must contain only JSON values")


def open_entry(
    state: LspState,
    *,
    document_uri: str,
    editor_text: str,
    disk_snapshot: DiskSourceSnapshot,
) -> LspStateTransition:
    """Open one contained entry and schedule only exact readable disk text."""

    path = _canonical_file_uri(document_uri)
    _require_contained_path(
        path,
        workspace_root=state.workspace_root,
        code="lsp_entry_path_uncontained",
        label="entry path",
    )
    if _canonical_path(disk_snapshot.canonical_path) != path:
        raise LspInitializationError(
            "lsp_entry_snapshot_path_mismatch",
            "disk snapshot path does not match the opened document URI",
        )
    disk_snapshot = replace(disk_snapshot, canonical_path=path)
    previous = next((entry for entry in state.entries if entry.path == path), None)
    generation = 1 if previous is None else previous.generation + 1
    readable = (
        disk_snapshot.revision.startswith("sha256:")
        and disk_snapshot.raw_decoded_text is not None
    )
    clean = readable and editor_text == disk_snapshot.raw_decoded_text
    schedulable = clean and not state.configuration_stale
    entry = CompileEntryState(
        path=path,
        disk_snapshot=disk_snapshot,
        editor_text=editor_text,
        generation=generation,
        pending_generation=generation if schedulable else None,
        buffer_status=(
            "clean" if clean else ("dirty" if readable else "unavailable")
        ),
        compile_status="pending" if schedulable else "idle",
        accepted_snapshot=None,
    )
    retained_entries = tuple(
        existing for existing in state.entries if existing.path != path
    )
    canceled = (
        ()
        if previous is None or previous.pending_generation is None
        else ((path, previous.pending_generation),)
    )
    scheduled = ((path, generation),) if schedulable else ()
    return LspStateTransition(
        state=replace(state, entries=(*retained_entries, entry)),
        effects=StateEffects(
            scheduled_generations=scheduled,
            canceled_generations=canceled,
        ),
    )


def change_entry(
    state: LspState,
    *,
    document_uri: str,
    editor_text: str,
) -> LspStateTransition:
    """Mark one open entry dirty and invalidate its requested generation."""

    path, entry = _open_entry_for_uri(state, document_uri=document_uri)
    updated = replace(
        entry,
        editor_text=editor_text,
        generation=entry.generation + 1,
        pending_generation=None,
        buffer_status="dirty",
        compile_status="idle",
        accepted_snapshot=None,
    )
    return LspStateTransition(
        state=replace(state, entries=_replace_entry(state.entries, updated)),
        effects=StateEffects(
            canceled_generations=_pending_generation_effect(path, entry),
        ),
    )


def save_entry(
    state: LspState,
    *,
    document_uri: str,
    disk_snapshot: DiskSourceSnapshot,
) -> LspStateTransition:
    """Apply one caller-probed save snapshot without reading notification text."""

    path, entry = _open_entry_for_uri(state, document_uri=document_uri)
    if _canonical_path(disk_snapshot.canonical_path) != path:
        raise LspInitializationError(
            "lsp_entry_snapshot_path_mismatch",
            "disk snapshot path does not match the saved document URI",
        )
    disk_snapshot = replace(disk_snapshot, canonical_path=path)
    generation = entry.generation + 1
    readable = (
        disk_snapshot.revision.startswith("sha256:")
        and disk_snapshot.raw_decoded_text is not None
    )
    clean = readable and entry.editor_text == disk_snapshot.raw_decoded_text
    schedulable = clean and not state.configuration_stale
    updated = replace(
        entry,
        disk_snapshot=disk_snapshot,
        generation=generation,
        pending_generation=generation if schedulable else None,
        buffer_status=(
            "clean" if clean else ("dirty" if readable else "unavailable")
        ),
        compile_status="pending" if schedulable else "idle",
        accepted_snapshot=None,
    )
    return LspStateTransition(
        state=replace(state, entries=_replace_entry(state.entries, updated)),
        effects=StateEffects(
            scheduled_generations=((path, generation),) if schedulable else (),
            canceled_generations=_pending_generation_effect(path, entry),
        ),
    )


def save_observed_entry(
    state: LspState,
    *,
    document_uri: str,
    observed_snapshot: DiskSourceSnapshot,
) -> LspStateTransition:
    """Select exactly one save transition from one supplied disk snapshot."""

    path, entry = _open_entry_for_uri(state, document_uri=document_uri)
    if _canonical_path(observed_snapshot.canonical_path) != path:
        raise LspInitializationError(
            "lsp_entry_snapshot_path_mismatch",
            "disk snapshot path does not match the saved document URI",
        )
    observed_snapshot = replace(observed_snapshot, canonical_path=path)
    retained_snapshot = entry.disk_snapshot
    if (
        retained_snapshot is not None
        and retained_snapshot.revision == observed_snapshot.revision
    ):
        return save_entry(
            state,
            document_uri=document_uri,
            disk_snapshot=observed_snapshot,
        )
    return observe_file_revision(state, observed_snapshot)


def accept_compile_success(
    state: LspState,
    *,
    document_uri: str,
    generation: int,
    snapshot: AcceptedCompileSnapshot,
    dependency_closure: frozenset[Path],
    diagnostic_contributions: tuple[DiagnosticContribution, ...],
) -> LspStateTransition:
    """Accept one current successful generation and its precise ownership."""

    current = _current_pending_completion(
        state,
        document_uri=document_uri,
        generation=generation,
    )
    if current is None:
        return LspStateTransition(state=state, effects=StateEffects())
    _path, entry = current
    normalized_revision_vector = _normalize_dependency_ownership(
        dependency_closure,
        snapshot.source_revision_vector,
    )
    assert normalized_revision_vector is not None
    normalized_snapshot = replace(
        snapshot,
        source_revision_vector=normalized_revision_vector,
        accepted_text_by_path=tuple(
            (
                _canonical_path(path),
                text,
            )
            for path, text in snapshot.accepted_text_by_path
        ),
    )
    _validate_diagnostic_contributions(
        diagnostic_contributions,
        owner_path=entry.path,
        generation=generation,
    )
    republish_uris = _merge_republish_uris(
        _diagnostic_target_uris(entry.diagnostic_contributions),
        _diagnostic_target_uris(diagnostic_contributions),
    )
    updated = replace(
        entry,
        pending_generation=None,
        compile_status="success",
        accepted_snapshot=normalized_snapshot,
        dependency_closure=dependency_closure,
        dependency_revision_vector=normalized_revision_vector,
        diagnostic_contributions=diagnostic_contributions,
    )
    return LspStateTransition(
        state=replace(state, entries=_replace_entry(state.entries, updated)),
        effects=StateEffects(republish_uris=republish_uris),
    )


def accept_compile_language_error(
    state: LspState,
    *,
    document_uri: str,
    generation: int,
    dependency_closure: frozenset[Path] | None,
    dependency_revision_vector: tuple[tuple[Path, str], ...] | None,
    diagnostic_contributions: tuple[DiagnosticContribution, ...],
) -> LspStateTransition:
    """Accept one current language-error completion with explicit ownership."""

    current = _current_pending_completion(
        state,
        document_uri=document_uri,
        generation=generation,
    )
    if current is None:
        return LspStateTransition(state=state, effects=StateEffects())
    _path, entry = current
    normalized_revision_vector = _normalize_dependency_ownership(
        dependency_closure,
        dependency_revision_vector,
    )
    _validate_diagnostic_contributions(
        diagnostic_contributions,
        owner_path=entry.path,
        generation=generation,
    )
    republish_uris = _merge_republish_uris(
        _diagnostic_target_uris(entry.diagnostic_contributions),
        _diagnostic_target_uris(diagnostic_contributions),
    )
    updated = replace(
        entry,
        pending_generation=None,
        compile_status="language_error",
        accepted_snapshot=None,
        dependency_closure=dependency_closure,
        dependency_revision_vector=normalized_revision_vector,
        diagnostic_contributions=diagnostic_contributions,
    )
    return LspStateTransition(
        state=replace(state, entries=_replace_entry(state.entries, updated)),
        effects=StateEffects(republish_uris=republish_uris),
    )


def record_server_failure(
    state: LspState,
    *,
    document_uri: str,
    generation: int,
) -> LspStateTransition:
    """Record one current server failure without synthesizing diagnostics."""

    current = _current_pending_completion(
        state,
        document_uri=document_uri,
        generation=generation,
    )
    if current is None:
        return LspStateTransition(state=state, effects=StateEffects())
    _path, entry = current
    updated = replace(
        entry,
        pending_generation=None,
        compile_status="server_error",
        accepted_snapshot=None,
        dependency_closure=None,
        dependency_revision_vector=None,
    )
    return LspStateTransition(
        state=replace(state, entries=_replace_entry(state.entries, updated)),
        effects=StateEffects(),
    )


def observe_file_revision(
    state: LspState,
    observed_snapshot: DiskSourceSnapshot,
) -> LspStateTransition:
    """Invalidate entries owned by one changed canonical file revision."""

    observed_path = _canonical_path(observed_snapshot.canonical_path)
    closure_unknown = any(
        entry.dependency_closure is None for entry in state.entries
    )
    affected_paths: frozenset[Path]
    if closure_unknown:
        affected_paths = frozenset(entry.path for entry in state.entries)
    else:
        affected_paths = frozenset(
            entry.path
            for entry in state.entries
            if _entry_owns_observed_path(entry, observed_path)
            and _known_entry_revision(entry, observed_path)
            != observed_snapshot.revision
        )
    if not affected_paths:
        return LspStateTransition(state=state, effects=StateEffects())

    updated_entries: list[CompileEntryState] = []
    scheduled: list[tuple[Path, int]] = []
    canceled: list[tuple[Path, int]] = []
    for entry in state.entries:
        if entry.path not in affected_paths:
            updated_entries.append(entry)
            continue
        generation = entry.generation + 1
        if entry.pending_generation is not None:
            canceled.append((entry.path, entry.pending_generation))
        disk_snapshot = entry.disk_snapshot
        buffer_status = entry.buffer_status
        if entry.path == observed_path:
            disk_snapshot = replace(
                observed_snapshot,
                canonical_path=observed_path,
            )
            if not _snapshot_has_decoded_text(disk_snapshot):
                buffer_status = "unavailable"
            elif entry.editor_text == disk_snapshot.raw_decoded_text:
                buffer_status = "clean"
            else:
                buffer_status = "dirty"
        schedulable = (
            not state.configuration_stale
            and buffer_status == "clean"
            and disk_snapshot is not None
            and _snapshot_has_decoded_text(disk_snapshot)
        )
        updated_entries.append(
            replace(
                entry,
                disk_snapshot=disk_snapshot,
                generation=generation,
                pending_generation=generation if schedulable else None,
                buffer_status=buffer_status,
                compile_status="pending" if schedulable else "idle",
                accepted_snapshot=None,
            )
        )
        if schedulable:
            scheduled.append((entry.path, generation))

    return LspStateTransition(
        state=replace(state, entries=tuple(updated_entries)),
        effects=StateEffects(
            scheduled_generations=tuple(scheduled),
            canceled_generations=tuple(canceled),
        ),
    )


def close_entry(
    state: LspState,
    *,
    document_uri: str,
) -> LspStateTransition:
    """Remove one open entry and expose its cancellation/publication effects."""

    path, entry = _open_entry_for_uri(state, document_uri=document_uri)
    return LspStateTransition(
        state=replace(
            state,
            entries=tuple(
                existing for existing in state.entries if existing.path != path
            ),
        ),
        effects=StateEffects(
            canceled_generations=_pending_generation_effect(path, entry),
            republish_uris=_diagnostic_target_uris(
                entry.diagnostic_contributions
            ),
        ),
    )


def _entry_owns_observed_path(
    entry: CompileEntryState,
    observed_path: Path,
) -> bool:
    if entry.path == observed_path:
        return True
    if entry.dependency_closure is not None and observed_path in entry.dependency_closure:
        return True
    return observed_path in _diagnostic_target_paths(entry)


def _diagnostic_target_paths(entry: CompileEntryState) -> frozenset[Path]:
    paths: set[Path] = set()
    for uri in _diagnostic_target_uris(entry.diagnostic_contributions):
        try:
            paths.add(_canonical_file_uri(uri))
        except LspInitializationError:
            continue
    return frozenset(paths)


def _known_entry_revision(
    entry: CompileEntryState,
    observed_path: Path,
) -> str | None:
    if entry.dependency_revision_vector is not None:
        for path, revision in entry.dependency_revision_vector:
            if path == observed_path:
                return revision
    if entry.path == observed_path and entry.disk_snapshot is not None:
        return entry.disk_snapshot.revision
    return None


def _normalize_dependency_ownership(
    dependency_closure: frozenset[Path] | None,
    dependency_revision_vector: tuple[tuple[Path, str], ...] | None,
) -> tuple[tuple[Path, str], ...] | None:
    if (dependency_closure is None) != (dependency_revision_vector is None):
        raise ValueError(
            "dependency closure and revision vector must either both be known "
            "or both be unknown"
        )
    normalized_revision_vector = (
        None
        if dependency_revision_vector is None
        else tuple(
            (_canonical_path(path), revision)
            for path, revision in dependency_revision_vector
        )
    )
    if normalized_revision_vector is not None:
        canonical_paths = tuple(
            path for path, _revision in normalized_revision_vector
        )
        if len(frozenset(canonical_paths)) != len(canonical_paths):
            raise ValueError(
                "dependency revision vector contains duplicate canonical paths"
            )
    if (
        normalized_revision_vector is not None
        and frozenset(path for path, _revision in normalized_revision_vector)
        != dependency_closure
    ):
        raise ValueError(
            "dependency revision vector canonical paths must exactly match "
            "dependency closure"
        )
    return normalized_revision_vector


def _snapshot_has_decoded_text(snapshot: DiskSourceSnapshot) -> bool:
    return (
        snapshot.revision.startswith("sha256:")
        and snapshot.raw_decoded_text is not None
    )


def _current_pending_completion(
    state: LspState,
    *,
    document_uri: str,
    generation: int,
) -> tuple[Path, CompileEntryState] | None:
    if state.configuration_stale:
        return None
    try:
        path = _canonical_file_uri(document_uri)
        _require_contained_path(
            path,
            workspace_root=state.workspace_root,
            code="lsp_entry_path_uncontained",
            label="entry path",
        )
    except LspInitializationError:
        return None
    entry = next((item for item in state.entries if item.path == path), None)
    if (
        entry is None
        or entry.buffer_status != "clean"
        or entry.compile_status != "pending"
        or entry.pending_generation != generation
        or entry.generation != generation
    ):
        return None
    return path, entry


def transition_workspace_root_set(
    state: LspState,
    *,
    canonical_roots: frozenset[Path],
) -> LspStateTransition:
    """Purely compare a canonical root set and latch restart-required staleness."""

    if state.configuration_stale:
        return LspStateTransition(state=state, effects=StateEffects())
    if canonical_roots == frozenset({state.workspace_root}):
        return LspStateTransition(state=state, effects=StateEffects())
    return latch_configuration_stale(state)


def latch_configuration_stale(state: LspState) -> LspStateTransition:
    """Permanently invalidate one initialized state and request one restart notice."""

    if state.configuration_stale:
        return LspStateTransition(state=state, effects=StateEffects())
    canceled = tuple(
        (entry.path, entry.pending_generation)
        for entry in state.entries
        if entry.pending_generation is not None
    )
    republish_uris = _merge_republish_uris(
        *(
            _diagnostic_target_uris(entry.diagnostic_contributions)
            for entry in state.entries
        )
    )
    return LspStateTransition(
        state=replace(
            state,
            entries=(),
            configuration_stale=True,
        ),
        effects=StateEffects(
            canceled_generations=canceled,
            republish_uris=republish_uris,
            restart_notice_required=True,
        ),
    )


def _validate_diagnostic_contributions(
    diagnostic_contributions: tuple[DiagnosticContribution, ...],
    *,
    owner_path: Path,
    generation: int,
) -> None:
    """Validate the structural contribution boundary without nominal coupling."""

    if not isinstance(diagnostic_contributions, tuple):
        raise TypeError("diagnostic contributions must be a tuple")
    owner_uri = owner_path.as_uri()
    for contribution in diagnostic_contributions:
        try:
            compile_entry_uri = contribution.compile_entry_uri
            target_uri = contribution.target_uri
            accepted_generation = contribution.accepted_generation
            parity_identity = contribution.parity_identity
        except AttributeError as error:
            raise TypeError(
                "diagnostic contributions must expose owner, target, "
                "generation, and parity identity"
            ) from error
        if not isinstance(compile_entry_uri, str):
            raise TypeError("diagnostic contribution owner URI must be a string")
        if _canonical_file_uri(compile_entry_uri).as_uri() != owner_uri:
            raise ValueError(
                "diagnostic contribution owner does not match compile entry"
            )
        if not isinstance(target_uri, str):
            raise TypeError("diagnostic contribution target URI must be a string")
        if _canonical_file_uri(target_uri).as_uri() != target_uri:
            raise ValueError(
                "diagnostic contribution target URI must be canonical"
            )
        if (
            type(accepted_generation) is not int
            or accepted_generation != generation
        ):
            raise ValueError(
                "diagnostic contribution generation does not match completion"
            )
        if not isinstance(parity_identity, tuple):
            raise TypeError(
                "diagnostic contribution parity identity must be a tuple"
            )


def _diagnostic_target_uris(
    diagnostic_contributions: tuple[DiagnosticContribution, ...],
) -> tuple[str, ...]:
    return _merge_republish_uris(
        tuple(
            contribution.target_uri
            for contribution in diagnostic_contributions
        )
    )


def _merge_republish_uris(
    *uri_groups: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(sorted({uri for group in uri_groups for uri in group}))


def current_navigation_snapshot(
    state: LspState,
    *,
    document_uri: str,
) -> AcceptedCompileSnapshot | None:
    """Return state-local navigation authority without filesystem judgments."""

    try:
        _path, entry = _open_entry_for_uri(state, document_uri=document_uri)
    except LspInitializationError:
        return None
    return entry.navigation_snapshot


def classify_completion_recovery(
    state: LspState,
    *,
    entry_path: Path,
) -> CompletionRecoverySelection:
    """Classify one already-canonical entry path without filesystem access."""

    if (
        not isinstance(state, LspState)
        or type(state.configuration_stale) is not bool
        or state.configuration_stale
        or not isinstance(entry_path, Path)
        or not entry_path.is_absolute()
        or not isinstance(state.entries, tuple)
    ):
        return "empty"
    matches = tuple(
        entry
        for entry in state.entries
        if isinstance(entry, CompileEntryState) and entry.path == entry_path
    )
    if len(matches) != 1:
        return "empty"
    entry = matches[0]
    if not _valid_completion_recovery_entry(entry):
        return "empty"
    if entry.buffer_status == "dirty":
        if entry.compile_status == "idle" and entry.pending_generation is None:
            return "static-incomplete"
        return "empty"
    if entry.buffer_status != "clean":
        return "empty"
    if entry.compile_status == "pending":
        if entry.pending_generation == entry.generation:
            return "static-incomplete"
        return "empty"
    if (
        entry.compile_status in {"language_error", "server_error"}
        and entry.pending_generation is None
    ):
        if (
            entry.compile_status == "server_error"
            and (
                entry.dependency_closure is not None
                or entry.dependency_revision_vector is not None
            )
        ):
            return "empty"
        return "static-incomplete"
    return "empty"


def _valid_completion_recovery_entry(entry: object) -> bool:
    if not isinstance(entry, CompileEntryState):
        return False
    if (
        not isinstance(entry.path, Path)
        or not entry.path.is_absolute()
        or type(entry.generation) is not int
        or entry.generation < 1
        or (
            entry.pending_generation is not None
            and (
                type(entry.pending_generation) is not int
                or entry.pending_generation < 1
            )
        )
        or type(entry.buffer_status) is not str
        or entry.buffer_status not in {"clean", "dirty", "unavailable"}
        or type(entry.compile_status) is not str
        or entry.compile_status
        not in {
            "idle",
            "pending",
            "success",
            "language_error",
            "server_error",
        }
        or entry.accepted_snapshot is not None
        or not _valid_recovery_disk_editor_shape(entry)
        or not _valid_recovery_dependency_shape(entry)
        or not _valid_recovery_contribution_shape(entry)
    ):
        return False
    return True


def _valid_recovery_disk_editor_shape(entry: CompileEntryState) -> bool:
    snapshot = entry.disk_snapshot
    if (
        not isinstance(snapshot, DiskSourceSnapshot)
        or not isinstance(snapshot.canonical_path, Path)
        or snapshot.canonical_path != entry.path
        or not snapshot.canonical_path.is_absolute()
        or type(snapshot.revision) is not str
        or len(snapshot.revision) != 71
        or not snapshot.revision.startswith("sha256:")
        or any(character not in "0123456789abcdef" for character in snapshot.revision[7:])
        or type(snapshot.raw_decoded_text) is not str
        or type(entry.editor_text) is not str
    ):
        return False
    text_is_current = entry.editor_text == snapshot.raw_decoded_text
    return (entry.buffer_status == "clean" and text_is_current) or (
        entry.buffer_status == "dirty"
        and not text_is_current
    )


def _valid_recovery_dependency_shape(entry: CompileEntryState) -> bool:
    closure = entry.dependency_closure
    revision_vector = entry.dependency_revision_vector
    if closure is None or revision_vector is None:
        return closure is None and revision_vector is None
    if (
        not isinstance(closure, frozenset)
        or not isinstance(revision_vector, tuple)
        or any(
            not isinstance(path, Path) or not path.is_absolute()
            for path in closure
        )
    ):
        return False
    revisions: list[tuple[Path, str]] = []
    for row in revision_vector:
        if (
            not isinstance(row, tuple)
            or len(row) != 2
            or not isinstance(row[0], Path)
            or not row[0].is_absolute()
            or type(row[1]) is not str
            or not row[1]
        ):
            return False
        revisions.append((row[0], row[1]))
    revision_paths = tuple(path for path, _revision in revisions)
    return (
        len(frozenset(revision_paths)) == len(revision_paths)
        and frozenset(revision_paths) == closure
    )


def _valid_recovery_contribution_shape(entry: CompileEntryState) -> bool:
    contributions = entry.diagnostic_contributions
    if not isinstance(contributions, tuple):
        return False
    for contribution in contributions:
        try:
            compile_entry_uri = contribution.compile_entry_uri
            target_uri = contribution.target_uri
            accepted_generation = contribution.accepted_generation
            parity_identity = contribution.parity_identity
        except AttributeError:
            return False
        if (
            type(compile_entry_uri) is not str
            or type(target_uri) is not str
            or type(accepted_generation) is not int
            or accepted_generation < 1
            or not isinstance(parity_identity, tuple)
        ):
            return False
    return True


def _open_entry_for_uri(
    state: LspState,
    *,
    document_uri: str,
) -> tuple[Path, CompileEntryState]:
    path = _canonical_file_uri(document_uri)
    _require_contained_path(
        path,
        workspace_root=state.workspace_root,
        code="lsp_entry_path_uncontained",
        label="entry path",
    )
    entry = next((item for item in state.entries if item.path == path), None)
    if entry is None:
        raise LspInitializationError(
            "lsp_entry_not_open",
            f"entry {path} is not open",
        )
    return path, entry


def _replace_entry(
    entries: tuple[CompileEntryState, ...],
    updated: CompileEntryState,
) -> tuple[CompileEntryState, ...]:
    return tuple(updated if entry.path == updated.path else entry for entry in entries)


def _pending_generation_effect(
    path: Path,
    entry: CompileEntryState,
) -> tuple[tuple[Path, int], ...]:
    if entry.pending_generation is None:
        return ()
    return ((path, entry.pending_generation),)


def canonicalize_workspace_roots(
    *,
    root_uri: str | None,
    workspace_folder_uris: Iterable[str],
) -> frozenset[Path]:
    """Normalize client URI spellings at the initialization/notification boundary."""

    root_uris = (
        *((root_uri,) if root_uri is not None else ()),
        *tuple(workspace_folder_uris),
    )
    return frozenset(_canonical_file_uri(uri) for uri in root_uris)


def _canonical_source_roots(
    raw_source_roots: object,
    *,
    workspace_root: Path,
) -> tuple[Path, ...]:
    if isinstance(raw_source_roots, (str, bytes, Mapping)) or not isinstance(
        raw_source_roots, Iterable
    ):
        raise LspInitializationError(
            "lsp_initialization_option_invalid",
            "source_roots must be an ordered sequence of path values",
        )
    return tuple(
        _canonical_contained_path(
            raw_root,
            workspace_root=workspace_root,
            code="lsp_source_root_uncontained",
            label="explicit source root",
        )
        for raw_root in raw_source_roots
    )


def _canonical_contained_path(
    raw_path: object,
    *,
    workspace_root: Path,
    code: str,
    label: str,
) -> Path:
    path = _canonical_configured_path(
        raw_path,
        workspace_root=workspace_root,
        field_name=label,
    )
    _require_contained_path(
        path,
        workspace_root=workspace_root,
        code=code,
        label=label,
    )
    return path


def _require_contained_path(
    path: Path,
    *,
    workspace_root: Path,
    code: str,
    label: str,
) -> None:
    try:
        path.relative_to(workspace_root)
    except ValueError as exc:
        raise LspInitializationError(
            code,
            f"{label} {path} is outside workspace root {workspace_root}",
        ) from exc


def _canonical_optional_path(
    raw_path: object,
    *,
    workspace_root: Path,
    field_name: str,
) -> Path | None:
    if raw_path is None:
        return None
    return _canonical_configured_path(
        raw_path,
        workspace_root=workspace_root,
        field_name=field_name,
    )


def _canonical_configured_path(
    raw_path: object,
    *,
    workspace_root: Path,
    field_name: str,
) -> Path:
    if not isinstance(raw_path, (str, os.PathLike)):
        raise LspInitializationError(
            "lsp_initialization_option_invalid",
            f"{field_name} must be a filesystem path",
        )
    path = Path(raw_path)
    if not path.is_absolute():
        path = workspace_root / path
    return _canonical_path(path)


def _canonical_file_uri(uri: str) -> Path:
    parsed = urlsplit(uri)
    if (
        parsed.scheme != "file"
        or parsed.netloc not in {"", "localhost"}
        or parsed.query
        or parsed.fragment
    ):
        raise LspInitializationError(
            "lsp_workspace_root_uri_invalid",
            f"workspace root must be a local file URI, got {uri!r}",
        )
    try:
        decoded_path = unquote_to_bytes(parsed.path).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise LspInitializationError(
            "lsp_workspace_root_uri_invalid",
            f"workspace root URI path is not valid UTF-8: {uri!r}",
        ) from exc
    return _canonical_path(decoded_path)


def _canonical_path(path: str | Path) -> Path:
    return Path(path).resolve(strict=False)
