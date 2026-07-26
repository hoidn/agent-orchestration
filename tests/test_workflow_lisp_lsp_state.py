from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
import hashlib
from pathlib import Path

import pytest

from orchestrator.lsp.compile_driver import probe_disk_source
from orchestrator.lsp.state import (
    AcceptedCompileSnapshot,
    CompileEntryState,
    LspConfigurationPaths,
    LspInitializationError,
    LspStateTransition,
    StateEffects,
    accept_compile_language_error,
    accept_compile_success,
    canonicalize_workspace_roots,
    change_entry,
    close_entry,
    initialize_lsp_state,
    observe_file_revision,
    open_entry,
    record_server_failure,
    save_entry,
    transition_workspace_root_set,
)
from orchestrator.workflow_lisp import compiler
from orchestrator.workflow_lisp.compiler import (
    Stage3ValidationProfile,
    _builtin_stdlib_source_root,
)
from orchestrator.workflow_lisp.lints import LINT_PROFILE_DEFAULT
from orchestrator.workflow_lisp.wcc.route import normalize_lowering_route


def test_disk_source_probe_reads_once_hashes_raw_bytes_and_preserves_crlf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "entry.orc"
    payload = b"(workflow-lisp\r\n)\r\n"
    calls: list[Path] = []

    def read_bytes_once(self: Path) -> bytes:
        calls.append(self)
        return payload

    monkeypatch.setattr(Path, "read_bytes", read_bytes_once)

    snapshot = probe_disk_source(path)

    assert calls == [path.resolve()]
    assert snapshot.canonical_path == path.resolve()
    assert snapshot.revision == f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert snapshot.raw_decoded_text == payload.decode("utf-8")


def test_disk_source_probe_distinguishes_missing_and_unreadable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing = tmp_path / "missing.orc"

    missing_snapshot = probe_disk_source(missing)

    assert missing_snapshot.revision == "missing"
    assert missing_snapshot.raw_decoded_text is None

    unreadable = tmp_path / "unreadable.orc"
    calls: list[Path] = []

    def deny_read(self: Path) -> bytes:
        calls.append(self)
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_bytes", deny_read)

    unreadable_snapshot = probe_disk_source(unreadable)

    assert calls == [unreadable.resolve()]
    assert unreadable_snapshot.revision == "unreadable"
    assert unreadable_snapshot.raw_decoded_text is None


def test_disk_source_probe_retains_revision_when_strict_utf8_decode_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "invalid.orc"
    payload = b"\xff\xfe"
    monkeypatch.setattr(Path, "read_bytes", lambda _self: payload)

    snapshot = probe_disk_source(path)

    assert snapshot.revision == f"sha256:{hashlib.sha256(payload).hexdigest()}"
    assert snapshot.raw_decoded_text is None


def test_open_entry_schedules_one_generation_only_for_exact_lf_text(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    editor_text = "(workflow-lisp\n)\n"
    path.write_bytes(editor_text.encode("utf-8"))
    initial = initialize_lsp_state(root_uri=workspace.as_uri())

    transition = open_entry(
        initial,
        document_uri=path.as_uri(),
        editor_text=editor_text,
        disk_snapshot=probe_disk_source(path),
    )

    assert isinstance(transition, LspStateTransition)
    assert transition.effects == StateEffects(
        scheduled_generations=((path.resolve(), 1),),
    )
    assert transition.state.entries == (
        CompileEntryState(
            path=path.resolve(),
            disk_snapshot=probe_disk_source(path),
            editor_text=editor_text,
            generation=1,
            pending_generation=1,
            buffer_status="clean",
            compile_status="pending",
            accepted_snapshot=None,
        ),
    )
    assert transition.state.entries[0].dependency_closure is None
    assert transition.state.entries[0].dependency_revision_vector is None


@pytest.mark.parametrize(
    ("disk_payload", "editor_text"),
    (
        (b"(workflow-lisp\r\n)\r\n", "(workflow-lisp\n)\n"),
        (b"(workflow-lisp\n)\n", "(workflow-lisp\r\n)\r\n"),
    ),
)
def test_open_entry_marks_newline_normalization_mismatch_dirty_without_compile(
    tmp_path: Path,
    disk_payload: bytes,
    editor_text: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    path.write_bytes(disk_payload)
    initial = initialize_lsp_state(root_uri=workspace.as_uri())

    transition = open_entry(
        initial,
        document_uri=path.as_uri(),
        editor_text=editor_text,
        disk_snapshot=probe_disk_source(path),
    )

    entry = transition.state.entries[0]
    assert entry.buffer_status == "dirty"
    assert entry.compile_status == "idle"
    assert entry.pending_generation is None
    assert entry.navigation_snapshot is None
    assert transition.effects.scheduled_generations == ()


@pytest.mark.parametrize(
    "snapshot_kind",
    ("missing", "unreadable", "invalid_utf8"),
)
def test_open_entry_marks_unavailable_disk_state_without_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    if snapshot_kind == "unreadable":
        monkeypatch.setattr(
            Path,
            "read_bytes",
            lambda _self: (_ for _ in ()).throw(PermissionError("denied")),
        )
    elif snapshot_kind == "invalid_utf8":
        monkeypatch.setattr(Path, "read_bytes", lambda _self: b"\xff")
    snapshot = probe_disk_source(path)
    initial = initialize_lsp_state(root_uri=workspace.as_uri())

    transition = open_entry(
        initial,
        document_uri=path.as_uri(),
        editor_text="",
        disk_snapshot=snapshot,
    )

    entry = transition.state.entries[0]
    assert entry.buffer_status == "unavailable"
    assert entry.compile_status == "idle"
    assert entry.pending_generation is None
    assert entry.navigation_snapshot is None
    assert transition.effects == StateEffects()


def test_open_entry_rejects_uncontained_uri_and_snapshot_before_state(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external = tmp_path / "external.orc"
    external.write_text("(workflow-lisp)\n", encoding="utf-8")
    initial = initialize_lsp_state(root_uri=workspace.as_uri())

    with pytest.raises(LspInitializationError, match="lsp_entry_path_uncontained"):
        open_entry(
            initial,
            document_uri=external.as_uri(),
            editor_text=external.read_text(encoding="utf-8"),
            disk_snapshot=probe_disk_source(external),
        )

    assert initial.entries == ()


@pytest.mark.parametrize("transition_kind", ("open", "save"))
@pytest.mark.parametrize("spelling_kind", ("equivalent", "symlink"))
def test_open_and_save_store_canonical_snapshot_paths(
    tmp_path: Path,
    transition_kind: str,
    spelling_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    canonical_snapshot = probe_disk_source(path)
    if spelling_kind == "equivalent":
        caller_path = workspace / "nested" / ".." / "entry.orc"
    else:
        caller_path = workspace / "entry-alias.orc"
        caller_path.symlink_to(path)
    caller_snapshot = replace(
        canonical_snapshot,
        canonical_path=caller_path,
    )
    initial = initialize_lsp_state(root_uri=workspace.as_uri())

    if transition_kind == "open":
        transition = open_entry(
            initial,
            document_uri=path.as_uri(),
            editor_text=text,
            disk_snapshot=caller_snapshot,
        )
    else:
        opened = open_entry(
            initial,
            document_uri=path.as_uri(),
            editor_text=text,
            disk_snapshot=canonical_snapshot,
        )
        transition = save_entry(
            opened.state,
            document_uri=path.as_uri(),
            disk_snapshot=caller_snapshot,
        )

    assert caller_snapshot.canonical_path == caller_path
    assert transition.state.entries[0].disk_snapshot.canonical_path == path.resolve()


def test_change_entry_bumps_generation_cancels_pending_and_schedules_nothing(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )

    changed = change_entry(
        opened.state,
        document_uri=path.as_uri(),
        editor_text="(workflow-lisp changed)\n",
    )

    entry = changed.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation is None
    assert entry.buffer_status == "dirty"
    assert entry.compile_status == "idle"
    assert entry.navigation_snapshot is None
    assert changed.effects == StateEffects(
        canceled_generations=((path.resolve(), 1),),
    )


def test_change_and_save_clear_navigation_without_erasing_trusted_ownership(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    dependency_revision_vector = (
        (path.resolve(), opened.state.entries[0].disk_snapshot.revision),
    )
    accepted_entry = replace(
        opened.state.entries[0],
        pending_generation=None,
        compile_status="success",
        accepted_snapshot=AcceptedCompileSnapshot(
            build_value=("accepted",),
            source_revision_vector=dependency_revision_vector,
        ),
        dependency_closure=frozenset({path.resolve()}),
        dependency_revision_vector=dependency_revision_vector,
        diagnostic_target_uris=(path.as_uri(),),
        contribution_keys=frozenset({"diagnostic-key"}),
    )
    accepted_state = replace(opened.state, entries=(accepted_entry,))

    changed = change_entry(
        accepted_state,
        document_uri=path.as_uri(),
        editor_text="(workflow-lisp changed)\n",
    )

    entry = changed.state.entries[0]
    assert entry.navigation_snapshot is None
    assert entry.dependency_closure == frozenset({path.resolve()})
    assert entry.dependency_revision_vector == dependency_revision_vector
    assert entry.diagnostic_target_uris == (path.as_uri(),)
    assert entry.contribution_keys == frozenset({"diagnostic-key"})
    assert changed.effects == StateEffects()

    path.write_text("(workflow-lisp changed)\n", encoding="utf-8")
    saved = save_entry(
        changed.state,
        document_uri=path.as_uri(),
        disk_snapshot=probe_disk_source(path),
    )

    assert saved.state.entries[0].dependency_closure == frozenset(
        {path.resolve()}
    )
    assert (
        saved.state.entries[0].dependency_revision_vector
        == dependency_revision_vector
    )


@pytest.mark.parametrize(
    ("disk_text", "editor_text", "expected_buffer_status", "scheduled"),
    (
        ("(workflow-lisp)\n", "(workflow-lisp)\n", "clean", True),
        ("(workflow-lisp)\r\n", "(workflow-lisp)\n", "dirty", False),
    ),
)
def test_save_entry_uses_caller_snapshot_and_exact_stored_editor_text(
    tmp_path: Path,
    disk_text: str,
    editor_text: str,
    expected_buffer_status: str,
    scheduled: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    path.write_text("(workflow-lisp)\n", encoding="utf-8", newline="")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text="(workflow-lisp)\n",
        disk_snapshot=probe_disk_source(path),
    )
    changed = change_entry(
        opened.state,
        document_uri=path.as_uri(),
        editor_text=editor_text,
    )
    path.write_text(disk_text, encoding="utf-8", newline="")
    snapshot = probe_disk_source(path)

    saved = save_entry(
        changed.state,
        document_uri=path.as_uri(),
        disk_snapshot=snapshot,
    )

    entry = saved.state.entries[0]
    assert entry.disk_snapshot == snapshot
    assert entry.generation == 3
    assert entry.buffer_status == expected_buffer_status
    assert entry.compile_status == ("pending" if scheduled else "idle")
    assert entry.pending_generation == (3 if scheduled else None)
    assert saved.effects.scheduled_generations == (
        ((path.resolve(), 3),) if scheduled else ()
    )


@pytest.mark.parametrize(
    "snapshot_kind",
    ("missing", "unreadable", "invalid_utf8"),
)
def test_save_entry_keeps_unreadable_states_unavailable_without_self_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    snapshot_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    path.write_text("(workflow-lisp)\n", encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text="(workflow-lisp)\n",
        disk_snapshot=probe_disk_source(path),
    )
    if snapshot_kind == "missing":
        path.unlink()
    elif snapshot_kind == "unreadable":
        monkeypatch.setattr(
            Path,
            "read_bytes",
            lambda _self: (_ for _ in ()).throw(PermissionError("denied")),
        )
    else:
        monkeypatch.setattr(Path, "read_bytes", lambda _self: b"\xff")
    snapshot = probe_disk_source(path)

    saved = save_entry(
        opened.state,
        document_uri=path.as_uri(),
        disk_snapshot=snapshot,
    )

    entry = saved.state.entries[0]
    assert entry.buffer_status == "unavailable"
    assert entry.compile_status == "idle"
    assert entry.pending_generation is None
    assert entry.navigation_snapshot is None
    assert saved.effects == StateEffects(
        canceled_generations=((path.resolve(), 1),),
    )


def test_close_entry_removes_only_owner_and_returns_cancel_republish_effects(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = workspace / "first.orc"
    second = workspace / "second.orc"
    first.write_text("(workflow-lisp)\n", encoding="utf-8")
    second.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = initialize_lsp_state(root_uri=workspace.as_uri())
    for path in (first, second):
        state = open_entry(
            state,
            document_uri=path.as_uri(),
            editor_text="(workflow-lisp)\n",
            disk_snapshot=probe_disk_source(path),
        ).state
    first_entry = replace(
        state.entries[0],
        dependency_closure=frozenset({first.resolve(), second.resolve()}),
        dependency_revision_vector=(
            (first.resolve(), probe_disk_source(first).revision),
            (second.resolve(), probe_disk_source(second).revision),
        ),
        diagnostic_target_uris=(first.as_uri(), second.as_uri()),
        contribution_keys=frozenset({"first-contribution"}),
    )
    state = replace(state, entries=(first_entry, state.entries[1]))

    closed = close_entry(state, document_uri=first.as_uri())

    assert tuple(entry.path for entry in closed.state.entries) == (second.resolve(),)
    assert closed.effects == StateEffects(
        canceled_generations=((first.resolve(), 1),),
        republish_uris=(first.as_uri(), second.as_uri()),
    )


def test_configuration_stale_blocks_open_and_save_scheduling(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    initial = initialize_lsp_state(root_uri=workspace.as_uri())
    stale_initial = replace(initial, configuration_stale=True)

    opened_stale = open_entry(
        stale_initial,
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    saved_stale = save_entry(
        opened_stale.state,
        document_uri=path.as_uri(),
        disk_snapshot=probe_disk_source(path),
    )

    assert opened_stale.state.entries[0].pending_generation is None
    assert opened_stale.effects == StateEffects()
    assert saved_stale.state.entries[0].pending_generation is None
    assert saved_stale.effects == StateEffects()


def test_current_compile_success_stores_exact_snapshot_and_ownership(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    snapshot = AcceptedCompileSnapshot(
        build_value=("opaque-build", 1),
        source_revision_vector=(
            (path.resolve(), opened.state.entries[0].disk_snapshot.revision),
        ),
    )
    raw_diagnostics = (object(),)

    accepted = accept_compile_success(
        opened.state,
        document_uri=path.as_uri(),
        generation=1,
        snapshot=snapshot,
        dependency_closure=frozenset({path.resolve()}),
        diagnostic_target_uris=(path.as_uri(),),
        contribution_keys=frozenset({"success-contribution"}),
        diagnostics=raw_diagnostics,
    )

    entry = accepted.state.entries[0]
    assert entry.buffer_status == "clean"
    assert entry.compile_status == "success"
    assert entry.pending_generation is None
    assert entry.accepted_snapshot == snapshot
    assert entry.navigation_snapshot == snapshot
    assert entry.dependency_closure == frozenset({path.resolve()})
    assert entry.dependency_revision_vector == snapshot.source_revision_vector
    assert entry.diagnostic_target_uris == (path.as_uri(),)
    assert entry.contribution_keys == frozenset({"success-contribution"})
    assert entry.diagnostics == raw_diagnostics


def test_compile_success_canonicalizes_snapshot_revision_paths(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    path.write_text("(workflow-lisp)\n", encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text="(workflow-lisp)\n",
        disk_snapshot=probe_disk_source(path),
    )
    revision = opened.state.entries[0].disk_snapshot.revision
    snapshot = AcceptedCompileSnapshot(
        build_value=("opaque-build",),
        source_revision_vector=(
            (workspace / "nested" / ".." / "entry.orc", revision),
        ),
    )

    accepted = accept_compile_success(
        opened.state,
        document_uri=path.as_uri(),
        generation=1,
        snapshot=snapshot,
        dependency_closure=frozenset({path.resolve()}),
        diagnostic_target_uris=(),
        contribution_keys=frozenset(),
    )

    expected_vector = ((path.resolve(), revision),)
    assert (
        accepted.state.entries[0].accepted_snapshot.source_revision_vector
        == expected_vector
    )
    assert (
        accepted.state.entries[0].dependency_revision_vector
        == expected_vector
    )


@pytest.mark.parametrize("include_extra_path", (False, True))
def test_compile_success_rejects_missing_or_extra_revision_vector_path(
    tmp_path: Path,
    include_extra_path: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    extra_path = workspace / "extra.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    extra_path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    source_revision_vector = (
        (
            (path.resolve(), probe_disk_source(path).revision),
            (extra_path.resolve(), probe_disk_source(extra_path).revision),
        )
        if include_extra_path
        else ()
    )

    with pytest.raises(
        ValueError,
        match="revision vector canonical paths must exactly match dependency closure",
    ):
        accept_compile_success(
            opened.state,
            document_uri=path.as_uri(),
            generation=1,
            snapshot=AcceptedCompileSnapshot(
                build_value=("must-not-accept",),
                source_revision_vector=source_revision_vector,
            ),
            dependency_closure=frozenset({path.resolve()}),
            diagnostic_target_uris=(),
            contribution_keys=frozenset(),
        )


@pytest.mark.parametrize("completion_kind", ("success", "language_error"))
@pytest.mark.parametrize("conflicting_revision", (False, True))
def test_current_completion_rejects_duplicate_canonical_revision_paths(
    tmp_path: Path,
    completion_kind: str,
    conflicting_revision: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    revision = probe_disk_source(path).revision
    duplicate_revision = (
        "sha256:" + ("0" * 64)
        if conflicting_revision
        else revision
    )
    revision_vector = (
        (path.resolve(), revision),
        (
            workspace / "nested" / ".." / "entry.orc",
            duplicate_revision,
        ),
    )

    with pytest.raises(
        ValueError,
        match="revision vector contains duplicate canonical paths",
    ):
        if completion_kind == "success":
            accept_compile_success(
                opened.state,
                document_uri=path.as_uri(),
                generation=1,
                snapshot=AcceptedCompileSnapshot(
                    build_value=("must-not-accept",),
                    source_revision_vector=revision_vector,
                ),
                dependency_closure=frozenset({path.resolve()}),
                diagnostic_target_uris=(),
                contribution_keys=frozenset(),
            )
        else:
            accept_compile_language_error(
                opened.state,
                document_uri=path.as_uri(),
                generation=1,
                dependency_closure=frozenset({path.resolve()}),
                dependency_revision_vector=revision_vector,
                diagnostic_target_uris=(),
                contribution_keys=frozenset(),
            )


@pytest.mark.parametrize(
    "dependency_closure",
    (frozenset(), None),
)
def test_language_error_replaces_contribution_with_precise_or_unknown_closure(
    tmp_path: Path,
    dependency_closure: frozenset[Path] | None,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    supplied_closure = (
        frozenset({path.resolve()})
        if dependency_closure == frozenset()
        else None
    )
    supplied_revision_vector = (
        ((path.resolve(), probe_disk_source(path).revision),)
        if supplied_closure is not None
        else None
    )
    raw_diagnostics = (object(),)

    accepted = accept_compile_language_error(
        opened.state,
        document_uri=path.as_uri(),
        generation=1,
        dependency_closure=supplied_closure,
        dependency_revision_vector=supplied_revision_vector,
        diagnostic_target_uris=(path.as_uri(),),
        contribution_keys=frozenset({"language-error"}),
        diagnostics=raw_diagnostics,
    )

    entry = accepted.state.entries[0]
    assert entry.compile_status == "language_error"
    assert entry.pending_generation is None
    assert entry.accepted_snapshot is None
    assert entry.navigation_snapshot is None
    assert entry.dependency_closure == supplied_closure
    assert entry.dependency_revision_vector == supplied_revision_vector
    assert entry.diagnostic_target_uris == (path.as_uri(),)
    assert entry.contribution_keys == frozenset({"language-error"})
    assert entry.diagnostics == raw_diagnostics


@pytest.mark.parametrize(
    ("dependency_closure", "dependency_revision_vector"),
    (
        (frozenset(), None),
        (None, ()),
    ),
)
def test_language_error_rejects_dependency_knownness_mismatch(
    tmp_path: Path,
    dependency_closure: frozenset[Path] | None,
    dependency_revision_vector: tuple[tuple[Path, str], ...] | None,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )

    with pytest.raises(
        ValueError,
        match="closure and revision vector must either both be known or both be unknown",
    ):
        accept_compile_language_error(
            opened.state,
            document_uri=path.as_uri(),
            generation=1,
            dependency_closure=dependency_closure,
            dependency_revision_vector=dependency_revision_vector,
            diagnostic_target_uris=(path.as_uri(),),
            contribution_keys=frozenset({"must-not-publish"}),
        )


def test_language_error_requires_dependency_revision_vector(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )

    with pytest.raises(TypeError, match="dependency_revision_vector"):
        accept_compile_language_error(
            opened.state,
            document_uri=path.as_uri(),
            generation=1,
            dependency_closure=frozenset({path.resolve()}),
            diagnostic_target_uris=(path.as_uri(),),
            contribution_keys=frozenset({"must-not-publish"}),
        )


@pytest.mark.parametrize("include_extra_path", (False, True))
def test_language_error_rejects_missing_or_extra_revision_vector_path(
    tmp_path: Path,
    include_extra_path: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    extra_path = workspace / "extra.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    extra_path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    dependency_revision_vector = (
        (
            (path.resolve(), probe_disk_source(path).revision),
            (extra_path.resolve(), probe_disk_source(extra_path).revision),
        )
        if include_extra_path
        else ()
    )

    with pytest.raises(
        ValueError,
        match="revision vector canonical paths must exactly match dependency closure",
    ):
        accept_compile_language_error(
            opened.state,
            document_uri=path.as_uri(),
            generation=1,
            dependency_closure=frozenset({path.resolve()}),
            dependency_revision_vector=dependency_revision_vector,
            diagnostic_target_uris=(path.as_uri(),),
            contribution_keys=frozenset({"must-not-publish"}),
        )


def test_server_failure_preserves_prior_contributions_and_clears_navigation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    first_snapshot = AcceptedCompileSnapshot(
        build_value=("first-build",),
        source_revision_vector=(
            (path.resolve(), opened.state.entries[0].disk_snapshot.revision),
        ),
    )
    raw_diagnostics = (object(),)
    accepted = accept_compile_success(
        opened.state,
        document_uri=path.as_uri(),
        generation=1,
        snapshot=first_snapshot,
        dependency_closure=frozenset({path.resolve()}),
        diagnostic_target_uris=(path.as_uri(),),
        contribution_keys=frozenset({"prior-contribution"}),
        diagnostics=raw_diagnostics,
    )
    saved = save_entry(
        accepted.state,
        document_uri=path.as_uri(),
        disk_snapshot=probe_disk_source(path),
    )

    failed = record_server_failure(
        saved.state,
        document_uri=path.as_uri(),
        generation=2,
    )

    entry = failed.state.entries[0]
    assert entry.compile_status == "server_error"
    assert entry.pending_generation is None
    assert entry.accepted_snapshot is None
    assert entry.navigation_snapshot is None
    assert entry.dependency_closure is None
    assert entry.dependency_revision_vector is None
    assert entry.diagnostic_target_uris == (path.as_uri(),)
    assert entry.contribution_keys == frozenset({"prior-contribution"})
    assert entry.diagnostics == raw_diagnostics
    assert failed.effects == StateEffects()


def test_late_closed_dirty_and_configuration_stale_completions_are_discarded(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    snapshot = AcceptedCompileSnapshot(
        build_value=("late-build",),
        source_revision_vector=(
            (path.resolve(), opened.state.entries[0].disk_snapshot.revision),
        ),
    )
    malformed_snapshot = AcceptedCompileSnapshot(
        build_value=("malformed-late-build",),
        source_revision_vector=(),
    )
    duplicate_snapshot = AcceptedCompileSnapshot(
        build_value=("duplicate-late-build",),
        source_revision_vector=(
            (path.resolve(), probe_disk_source(path).revision),
            (
                workspace / "nested" / ".." / "entry.orc",
                probe_disk_source(path).revision,
            ),
        ),
    )
    changed = change_entry(
        opened.state,
        document_uri=path.as_uri(),
        editor_text="(workflow-lisp changed)\n",
    )
    closed = close_entry(opened.state, document_uri=path.as_uri())
    stale = replace(opened.state, configuration_stale=True)

    for candidate, generation in (
        (opened.state, 0),
        (changed.state, 2),
        (closed.state, 1),
        (stale, 1),
    ):
        discarded = accept_compile_success(
            candidate,
            document_uri=path.as_uri(),
            generation=generation,
            snapshot=snapshot,
            dependency_closure=frozenset({path.resolve()}),
            diagnostic_target_uris=(path.as_uri(),),
            contribution_keys=frozenset({"must-not-publish"}),
        )
        assert discarded.state is candidate
        assert discarded.effects == StateEffects()

        malformed = accept_compile_success(
            candidate,
            document_uri=path.as_uri(),
            generation=generation,
            snapshot=malformed_snapshot,
            dependency_closure=frozenset({path.resolve()}),
            diagnostic_target_uris=(path.as_uri(),),
            contribution_keys=frozenset({"must-not-publish"}),
        )
        assert malformed.state is candidate
        assert malformed.effects == StateEffects()

        duplicate = accept_compile_success(
            candidate,
            document_uri=path.as_uri(),
            generation=generation,
            snapshot=duplicate_snapshot,
            dependency_closure=frozenset({path.resolve()}),
            diagnostic_target_uris=(path.as_uri(),),
            contribution_keys=frozenset({"must-not-publish"}),
        )
        assert duplicate.state is candidate
        assert duplicate.effects == StateEffects()


def test_malformed_dirty_closed_and_stale_language_errors_are_discarded(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    text = "(workflow-lisp)\n"
    path.write_text(text, encoding="utf-8")
    opened = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=path.as_uri(),
        editor_text=text,
        disk_snapshot=probe_disk_source(path),
    )
    dirty = change_entry(
        opened.state,
        document_uri=path.as_uri(),
        editor_text="(workflow-lisp changed)\n",
    )
    closed = close_entry(opened.state, document_uri=path.as_uri())
    stale = replace(opened.state, configuration_stale=True)
    duplicate_revision_vector = (
        (path.resolve(), probe_disk_source(path).revision),
        (
            workspace / "nested" / ".." / "entry.orc",
            probe_disk_source(path).revision,
        ),
    )

    for candidate in (dirty.state, closed.state, stale):
        for malformed_revision_vector in (
            None,
            duplicate_revision_vector,
        ):
            discarded = accept_compile_language_error(
                candidate,
                document_uri=path.as_uri(),
                generation=1,
                dependency_closure=frozenset({path.resolve()}),
                dependency_revision_vector=malformed_revision_vector,
                diagnostic_target_uris=(path.as_uri(),),
                contribution_keys=frozenset({"must-not-publish"}),
            )

            assert discarded.state is candidate
            assert discarded.effects == StateEffects()


def test_observed_dependency_change_invalidates_and_schedules_clean_importer(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "a.orc"
    dependency_path = workspace / "b.orc"
    entry_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    dependency_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=entry_path,
        closure=frozenset({entry_path.resolve(), dependency_path.resolve()}),
        revision_paths=(entry_path, dependency_path),
        contribution_key="a-contribution",
    )
    dependency_path.write_text("(workflow-lisp changed)\n", encoding="utf-8")

    observed = observe_file_revision(state, probe_disk_source(dependency_path))

    entry = observed.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation == 2
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert entry.navigation_snapshot is None
    assert entry.contribution_keys == frozenset({"a-contribution"})
    assert observed.effects == StateEffects(
        scheduled_generations=((entry_path.resolve(), 2),),
    )


@pytest.mark.parametrize(
    ("editor_text", "disk_text", "expected_status", "scheduled"),
    (
        ("(workflow-lisp new)\n", "(workflow-lisp new)\n", "clean", True),
        ("(workflow-lisp editor)\n", "(workflow-lisp disk)\n", "dirty", False),
    ),
)
def test_observed_self_revision_reproves_exact_stored_editor_text(
    tmp_path: Path,
    editor_text: str,
    disk_text: str,
    expected_status: str,
    scheduled: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    path = workspace / "entry.orc"
    path.write_text("(workflow-lisp old)\n", encoding="utf-8")
    accepted = _accepted_state(
        workspace=workspace,
        entry_path=path,
        closure=frozenset({path.resolve()}),
        revision_paths=(path,),
    )
    changed = change_entry(
        accepted,
        document_uri=path.as_uri(),
        editor_text=editor_text,
    )
    path.write_text(disk_text, encoding="utf-8")

    observed = observe_file_revision(changed.state, probe_disk_source(path))

    entry = observed.state.entries[0]
    assert entry.editor_text == editor_text
    assert entry.buffer_status == expected_status
    assert entry.pending_generation == (3 if scheduled else None)
    assert observed.effects.scheduled_generations == (
        ((path.resolve(), 3),) if scheduled else ()
    )


def test_unchanged_or_unrelated_observation_leaves_known_entry_untouched(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "a.orc"
    dependency_path = workspace / "b.orc"
    unrelated_path = workspace / "c.orc"
    for path in (entry_path, dependency_path, unrelated_path):
        path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=entry_path,
        closure=frozenset({entry_path.resolve(), dependency_path.resolve()}),
        revision_paths=(entry_path, dependency_path),
    )

    unchanged = observe_file_revision(state, probe_disk_source(dependency_path))
    unrelated_path.write_text("(workflow-lisp changed)\n", encoding="utf-8")
    unrelated = observe_file_revision(state, probe_disk_source(unrelated_path))

    assert unchanged.state is state
    assert unchanged.effects == StateEffects()
    assert unrelated.state is state
    assert unrelated.effects == StateEffects()


def test_unknown_unavailable_entry_conservatively_invalidates_all_open_entries(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    unavailable_path = workspace / "a.orc"
    known_path = workspace / "b.orc"
    unrelated_path = workspace / "c.orc"
    known_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    unrelated_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    unavailable = open_entry(
        initialize_lsp_state(root_uri=workspace.as_uri()),
        document_uri=unavailable_path.as_uri(),
        editor_text="(workflow-lisp)\n",
        disk_snapshot=probe_disk_source(unavailable_path),
    )
    state = _accepted_state(
        workspace=workspace,
        entry_path=known_path,
        closure=frozenset({known_path.resolve()}),
        revision_paths=(known_path,),
        initial_state=unavailable.state,
    )

    observed = observe_file_revision(
        state,
        probe_disk_source(unrelated_path),
    )

    by_path = {entry.path: entry for entry in observed.state.entries}
    assert by_path[unavailable_path.resolve()].generation == 2
    assert by_path[unavailable_path.resolve()].buffer_status == "unavailable"
    assert by_path[unavailable_path.resolve()].pending_generation is None
    assert by_path[known_path.resolve()].generation == 2
    assert by_path[known_path.resolve()].pending_generation == 2
    assert observed.effects == StateEffects(
        scheduled_generations=((known_path.resolve(), 2),),
    )


def test_precise_language_error_unchanged_dependency_revision_is_not_invalidated(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "a.orc"
    dependency_path = workspace / "b.orc"
    for path in (entry_path, dependency_path):
        path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=entry_path,
        closure=frozenset({entry_path.resolve(), dependency_path.resolve()}),
        revision_paths=(entry_path, dependency_path),
        language_error=True,
    )

    observed = observe_file_revision(state, probe_disk_source(dependency_path))

    assert observed.state is state
    assert observed.effects == StateEffects()


def test_precise_language_error_changed_dependency_revision_is_invalidated(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "a.orc"
    dependency_path = workspace / "b.orc"
    for path in (entry_path, dependency_path):
        path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=entry_path,
        closure=frozenset({entry_path.resolve(), dependency_path.resolve()}),
        revision_paths=(entry_path, dependency_path),
        language_error=True,
    )
    dependency_path.write_text("(workflow-lisp changed)\n", encoding="utf-8")

    observed = observe_file_revision(state, probe_disk_source(dependency_path))

    entry = observed.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation == 2
    assert entry.compile_status == "pending"
    assert entry.dependency_revision_vector is not None
    assert observed.effects == StateEffects(
        scheduled_generations=((entry_path.resolve(), 2),),
    )


@pytest.mark.parametrize("unavailable_kind", ("missing", "unreadable"))
def test_closed_unavailable_dependency_still_schedules_importer_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    unavailable_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "a.orc"
    dependency_path = workspace / "b.orc"
    entry_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    dependency_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=entry_path,
        closure=frozenset({entry_path.resolve(), dependency_path.resolve()}),
        revision_paths=(entry_path, dependency_path),
    )
    if unavailable_kind == "missing":
        dependency_path.unlink()
    else:
        original_read_bytes = Path.read_bytes

        def deny_dependency(self: Path) -> bytes:
            if self == dependency_path.resolve():
                raise PermissionError("denied")
            return original_read_bytes(self)

        monkeypatch.setattr(Path, "read_bytes", deny_dependency)

    observed = observe_file_revision(state, probe_disk_source(dependency_path))

    assert tuple(entry.path for entry in observed.state.entries) == (
        entry_path.resolve(),
    )
    assert observed.effects.scheduled_generations == (
        (entry_path.resolve(), 2),
    )


def test_open_dependency_becoming_unavailable_is_not_self_scheduled(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "a.orc"
    dependency_path = workspace / "b.orc"
    for path in (entry_path, dependency_path):
        path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=entry_path,
        closure=frozenset({entry_path.resolve(), dependency_path.resolve()}),
        revision_paths=(entry_path, dependency_path),
    )
    opened_dependency = open_entry(
        state,
        document_uri=dependency_path.as_uri(),
        editor_text="(workflow-lisp)\n",
        disk_snapshot=probe_disk_source(dependency_path),
    )
    dependency_path.unlink()

    observed = observe_file_revision(
        opened_dependency.state,
        probe_disk_source(dependency_path),
    )

    by_path = {entry.path: entry for entry in observed.state.entries}
    assert by_path[entry_path.resolve()].pending_generation == 2
    assert by_path[dependency_path.resolve()].buffer_status == "unavailable"
    assert by_path[dependency_path.resolve()].pending_generation is None
    assert observed.effects == StateEffects(
        scheduled_generations=((entry_path.resolve(), 2),),
        canceled_generations=((dependency_path.resolve(), 1),),
    )


def test_unknown_closure_observation_invalidates_and_schedules_all_clean_entries(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = workspace / "a.orc"
    second = workspace / "b.orc"
    observed_path = workspace / "unrelated.orc"
    for path in (first, second, observed_path):
        path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=first,
        closure=None,
        revision_paths=(first,),
        language_error=True,
    )
    second_state = _accepted_state(
        workspace=workspace,
        entry_path=second,
        closure=frozenset({second.resolve()}),
        revision_paths=(second,),
        initial_state=state,
    )

    observed = observe_file_revision(
        second_state,
        probe_disk_source(observed_path),
    )

    assert tuple(entry.generation for entry in observed.state.entries) == (2, 2)
    assert tuple(entry.pending_generation for entry in observed.state.entries) == (
        2,
        2,
    )
    assert observed.effects.scheduled_generations == (
        (first.resolve(), 2),
        (second.resolve(), 2),
    )


def test_configuration_stale_observation_invalidates_without_scheduling(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "a.orc"
    dependency_path = workspace / "b.orc"
    entry_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    dependency_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=entry_path,
        closure=frozenset({entry_path.resolve(), dependency_path.resolve()}),
        revision_paths=(entry_path, dependency_path),
    )
    stale = replace(state, configuration_stale=True)
    dependency_path.write_text("(workflow-lisp changed)\n", encoding="utf-8")

    observed = observe_file_revision(stale, probe_disk_source(dependency_path))

    entry = observed.state.entries[0]
    assert entry.generation == 2
    assert entry.compile_status == "idle"
    assert entry.pending_generation is None
    assert observed.effects.scheduled_generations == ()


def test_closed_diagnostic_owner_does_not_remove_other_owner_edge(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first = workspace / "a.orc"
    second = workspace / "b.orc"
    target = workspace / "target.orc"
    for path in (first, second, target):
        path.write_text("(workflow-lisp)\n", encoding="utf-8")
    state = _accepted_state(
        workspace=workspace,
        entry_path=first,
        closure=frozenset({first.resolve()}),
        revision_paths=(first,),
        diagnostic_targets=(target.as_uri(),),
    )
    state = _accepted_state(
        workspace=workspace,
        entry_path=second,
        closure=frozenset({second.resolve()}),
        revision_paths=(second,),
        diagnostic_targets=(target.as_uri(),),
        initial_state=state,
    )
    closed = close_entry(state, document_uri=first.as_uri())
    target.write_text("(workflow-lisp changed)\n", encoding="utf-8")

    observed = observe_file_revision(
        closed.state,
        probe_disk_source(target),
    )

    assert tuple(entry.path for entry in observed.state.entries) == (
        second.resolve(),
    )
    assert observed.state.entries[0].generation == 2
    assert observed.effects.scheduled_generations == ((second.resolve(), 2),)


def _accepted_state(
    *,
    workspace: Path,
    entry_path: Path,
    closure: frozenset[Path] | None,
    revision_paths: tuple[Path, ...],
    contribution_key: str = "contribution",
    diagnostic_targets: tuple[str, ...] = (),
    language_error: bool = False,
    initial_state=None,
):
    state = initial_state or initialize_lsp_state(root_uri=workspace.as_uri())
    opened = open_entry(
        state,
        document_uri=entry_path.as_uri(),
        editor_text=entry_path.read_text(encoding="utf-8"),
        disk_snapshot=probe_disk_source(entry_path),
    )
    if language_error:
        dependency_revision_vector = (
            tuple(
                (path.resolve(), probe_disk_source(path).revision)
                for path in revision_paths
            )
            if closure is not None
            else None
        )
        return accept_compile_language_error(
            opened.state,
            document_uri=entry_path.as_uri(),
            generation=opened.state.entries[-1].generation,
            dependency_closure=closure,
            dependency_revision_vector=dependency_revision_vector,
            diagnostic_target_uris=diagnostic_targets,
            contribution_keys=frozenset({contribution_key}),
        ).state
    assert closure is not None
    snapshot = AcceptedCompileSnapshot(
        build_value=("accepted", entry_path.name),
        source_revision_vector=tuple(
            (path.resolve(), probe_disk_source(path).revision)
            for path in revision_paths
        ),
    )
    return accept_compile_success(
        opened.state,
        document_uri=entry_path.as_uri(),
        generation=opened.state.entries[-1].generation,
        snapshot=snapshot,
        dependency_closure=closure,
        diagnostic_target_uris=diagnostic_targets,
        contribution_keys=frozenset({contribution_key}),
    ).state


def test_initialization_freezes_one_canonical_root_without_implicit_source_roots(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    state = initialize_lsp_state(root_uri=workspace.as_uri())

    assert state.workspace_root == workspace.resolve()
    assert state.options.source_roots == ()
    assert state.options.configuration == LspConfigurationPaths()
    assert state.builtin_stdlib_source_root == _builtin_stdlib_source_root().resolve()
    with pytest.raises(FrozenInstanceError):
        state.workspace_root = tmp_path  # type: ignore[misc]


@pytest.mark.parametrize(
    ("use_root_uri", "folder_spellings"),
    (
        (True, ()),
        (False, ("canonical",)),
        (True, ("equivalent",)),
    ),
)
def test_initialization_accepts_exactly_one_distinct_canonical_root(
    tmp_path: Path,
    use_root_uri: bool,
    folder_spellings: tuple[str, ...],
) -> None:
    workspace = tmp_path / "workspace"
    equivalent = workspace / "nested" / ".."
    folders = tuple(
        workspace.as_uri() if spelling == "canonical" else equivalent.as_uri()
        for spelling in folder_spellings
    )

    state = initialize_lsp_state(
        root_uri=workspace.as_uri() if use_root_uri else None,
        workspace_folder_uris=folders,
    )

    assert state.workspace_root == workspace


def test_initialization_rejects_zero_or_multiple_distinct_roots(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    with pytest.raises(
        LspInitializationError, match="lsp_workspace_root_count_invalid"
    ):
        initialize_lsp_state()
    with pytest.raises(
        LspInitializationError, match="lsp_workspace_root_count_invalid"
    ):
        initialize_lsp_state(
            root_uri=first.as_uri(),
            workspace_folder_uris=(second.as_uri(),),
        )


def test_initialization_deduplicates_symlink_spellings_of_one_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    alias = tmp_path / "workspace-alias"
    alias.symlink_to(workspace, target_is_directory=True)

    state = initialize_lsp_state(
        root_uri=workspace.as_uri(),
        workspace_folder_uris=(alias.as_uri(),),
    )

    assert state.workspace_root == workspace.resolve()


@pytest.mark.parametrize(
    "invalid_options",
    (
        [],
        False,
        0,
        "",
        ["entry_workflow"],
        True,
        1,
        "entry_workflow",
        object(),
    ),
)
def test_initialization_rejects_every_supplied_non_mapping_options_value(
    tmp_path: Path,
    invalid_options: object,
) -> None:
    with pytest.raises(
        LspInitializationError,
        match="lsp_initialization_option_invalid",
    ):
        initialize_lsp_state(
            root_uri=(tmp_path / "workspace").as_uri(),
            initialization_options=invalid_options,  # type: ignore[arg-type]
        )


def test_initialization_accepts_absent_or_empty_mapping_options(
    tmp_path: Path,
) -> None:
    workspace_uri = (tmp_path / "workspace").as_uri()

    absent = initialize_lsp_state(
        root_uri=workspace_uri,
        initialization_options=None,
    )
    supplied_empty = initialize_lsp_state(
        root_uri=workspace_uri,
        initialization_options={},
    )

    assert absent.options == supplied_empty.options


def test_explicit_source_roots_are_canonical_ordered_and_preserve_multiplicity(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    first = workspace / "src"
    equivalent_first = workspace / "nested" / ".." / "src"
    second = workspace / "lib"

    state = initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "source_roots": (
                first,
                equivalent_first,
                second,
                workspace,
            )
        },
    )

    assert state.options.source_roots == (
        first,
        first,
        second,
        workspace,
    )
    assert state.builtin_stdlib_source_root not in state.options.source_roots


def test_initialization_rejects_uncontained_entry_and_explicit_source_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    external = tmp_path / "external"

    with pytest.raises(
        LspInitializationError, match="lsp_source_root_uncontained"
    ):
        initialize_lsp_state(
            root_uri=workspace.as_uri(),
            initialization_options={"source_roots": (external,)},
        )
    with pytest.raises(LspInitializationError, match="lsp_entry_path_uncontained"):
        initialize_lsp_state(
            root_uri=workspace.as_uri(),
            entry_paths=(external / "entry.orc",),
        )


def test_initialization_preserves_contained_entry_placeholders(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    entry = workspace / "flows" / "entry.orc"

    state = initialize_lsp_state(
        root_uri=workspace.as_uri(),
        entry_paths=(entry,),
    )

    assert tuple(item.path for item in state.entries) == (entry,)
    assert state.entries[0].dependency_closure is None
    assert state.entries[0].dependency_revision_vector is None


@pytest.mark.parametrize("alias_kind", ("equivalent", "symlink"))
def test_initialization_rejects_duplicate_canonical_entry_paths(
    tmp_path: Path,
    alias_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry = workspace / "entry.orc"
    entry.write_text("(workflow-lisp)\n", encoding="utf-8")
    if alias_kind == "equivalent":
        alias = workspace / "nested" / ".." / "entry.orc"
    else:
        alias = workspace / "entry-alias.orc"
        alias.symlink_to(entry)

    with pytest.raises(
        LspInitializationError,
        match="lsp_entry_path_duplicate",
    ):
        initialize_lsp_state(
            root_uri=workspace.as_uri(),
            entry_paths=(entry, alias),
        )


def test_initialization_freezes_fixed_production_policy_and_optional_configuration(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    providers = workspace / "config" / "providers.json"
    prompts = workspace / "config" / "prompts.json"
    commands = workspace / "config" / "commands.json"
    imports = workspace / "config" / "imports.json"

    absent = initialize_lsp_state(root_uri=workspace.as_uri())
    configured = initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "entry_workflow": "main",
            "provider_externs_path": "config/providers.json",
            "prompt_externs_path": prompts,
            "command_boundaries_path": commands,
            "imported_workflow_bundles_path": imports,
        },
    )

    assert absent.options.entry_workflow is None
    assert absent.options.configuration == LspConfigurationPaths()
    assert configured.options.entry_workflow == "main"
    assert configured.options.configuration == LspConfigurationPaths(
        provider_externs_path=providers,
        prompt_externs_path=prompts,
        imported_workflow_bundles_path=imports,
        command_boundaries_path=commands,
    )
    assert configured.options.validation_profile is Stage3ValidationProfile.SHARED_CALLABLE
    assert configured.options.lint_profile == LINT_PROFILE_DEFAULT
    assert configured.options.lowering_route is normalize_lowering_route(None)
    with pytest.raises(FrozenInstanceError):
        configured.options.entry_workflow = "other"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        configured.options.configuration.provider_externs_path = None  # type: ignore[misc]


@pytest.mark.parametrize(
    "unsupported_option",
    ("lint_profile", "lowering_route", "validation_profile"),
)
def test_initialization_rejects_compile_policy_overrides(
    tmp_path: Path,
    unsupported_option: str,
) -> None:
    with pytest.raises(
        LspInitializationError, match="lsp_initialization_option_unsupported"
    ):
        initialize_lsp_state(
            root_uri=(tmp_path / "workspace").as_uri(),
            initialization_options={unsupported_option: "override"},
        )


def test_initialization_rejects_unknown_options_without_nominal_extension_taxonomy(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        LspInitializationError, match="lsp_initialization_option_unsupported"
    ):
        initialize_lsp_state(
            root_uri=(tmp_path / "workspace").as_uri(),
            initialization_options={"completion_type_taxonomy": "nominal"},
        )


def test_builtin_root_is_canonicalized_from_the_production_owner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owned_root = tmp_path / "compiler" / "nested" / ".." / "stdlib"
    monkeypatch.setattr(
        compiler,
        "_builtin_stdlib_source_root",
        lambda: owned_root,
    )

    state = initialize_lsp_state(root_uri=(tmp_path / "workspace").as_uri())

    assert state.builtin_stdlib_source_root == tmp_path / "compiler" / "stdlib"
    assert state.options.source_roots == ()


def test_root_set_change_latches_stale_invalidates_entries_and_notifies_once(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    placeholder = workspace / "placeholder.orc"
    pending = workspace / "pending.orc"
    pending.write_text("(workflow-lisp)\n", encoding="utf-8")
    other = tmp_path / "other"
    initial = initialize_lsp_state(
        root_uri=workspace.as_uri(),
        entry_paths=(placeholder,),
    )
    opened = open_entry(
        initial,
        document_uri=pending.as_uri(),
        editor_text="(workflow-lisp)\n",
        disk_snapshot=probe_disk_source(pending),
    )

    unchanged_roots = canonicalize_workspace_roots(
        root_uri=workspace.as_uri(),
        workspace_folder_uris=((workspace / "nested" / "..").as_uri(),),
    )
    changed_roots = canonicalize_workspace_roots(
        root_uri=workspace.as_uri(),
        workspace_folder_uris=(other.as_uri(),),
    )
    reverted_roots = canonicalize_workspace_roots(
        root_uri=workspace.as_uri(),
        workspace_folder_uris=(),
    )

    unchanged = transition_workspace_root_set(
        opened.state,
        canonical_roots=unchanged_roots,
    )
    changed = transition_workspace_root_set(
        unchanged.state,
        canonical_roots=changed_roots,
    )
    repeated = transition_workspace_root_set(
        changed.state,
        canonical_roots=changed_roots,
    )
    reverted = transition_workspace_root_set(
        repeated.state,
        canonical_roots=reverted_roots,
    )

    assert unchanged.state is opened.state
    assert unchanged.effects == StateEffects()
    assert changed.state.configuration_stale is True
    assert changed.state.entries == ()
    assert changed.effects == StateEffects(
        canceled_generations=((pending.resolve(), 1),),
        restart_notice_required=True,
    )
    assert repeated.state is changed.state
    assert repeated.effects == StateEffects()
    assert reverted.state is changed.state
    assert reverted.state.configuration_stale is True
    assert reverted.effects == StateEffects()
