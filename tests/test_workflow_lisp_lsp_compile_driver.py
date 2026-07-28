from __future__ import annotations

import hashlib
from dataclasses import replace
from importlib import import_module
from pathlib import Path
import shutil
from threading import Event, Lock, Thread
from types import SimpleNamespace

import pytest

from orchestrator.lsp import compile_driver
from orchestrator.lsp import state as lsp_state
from orchestrator.workflow_lisp import build
from orchestrator.workflow_lisp import compiler
from orchestrator.workflow_lisp.diagnostics import (
    LispFrontendCompileError,
    LispFrontendDiagnostic,
)
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.wcc.route import normalize_lowering_route


CLI_FIXTURES = (
    Path(__file__).parent / "fixtures" / "workflow_lisp" / "cli"
).resolve()


def _workspace_snapshot(root: Path) -> tuple[tuple[str, bytes], ...]:
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )


def _injected_success(
    diagnostics: tuple[object, ...] = (),
    *,
    configuration_revision_vector: tuple[tuple[Path, str], ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        diagnostics=diagnostics,
        configuration_trace=SimpleNamespace(
            revision_vector=configuration_revision_vector,
        ),
    )


def _injected_language_error(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
    *,
    configuration_revision_vector: tuple[tuple[Path, str], ...] | None = (),
) -> LispFrontendCompileError:
    return LispFrontendCompileError(
        diagnostics,
        configuration_revision_vector=configuration_revision_vector,
    )


def _translate_contributions(
    diagnostics: tuple[LispFrontendDiagnostic, ...],
    *,
    compile_entry_uri: str,
    accepted_generation: int,
    accepted_text_by_path: dict[Path, str],
) -> tuple[object, ...]:
    module = import_module("orchestrator.lsp.diagnostics")
    contribution_type = getattr(module, "DiagnosticContribution", None)
    translate = getattr(module, "translate_frontend_diagnostics", None)
    if not isinstance(contribution_type, type) or not callable(translate):
        pytest.fail("LSP diagnostic contribution translation is not implemented")
    contributions = translate(
        diagnostics,
        compile_entry_uri=compile_entry_uri,
        accepted_generation=accepted_generation,
        accepted_text_by_path=accepted_text_by_path,
    )
    assert all(isinstance(item, contribution_type) for item in contributions)
    return contributions


def _configured_initial_state(
    workspace: Path,
) -> tuple[lsp_state.LspState, dict[str, Path]]:
    config_root = workspace / "config"
    source_root = workspace / "src"
    config_root.mkdir(parents=True)
    source_root.mkdir(parents=True)
    configured_paths = {
        "provider_externs_path": config_root / "providers.json",
        "prompt_externs_path": config_root / "prompts.json",
        "command_boundaries_path": config_root / "commands.json",
        "imported_workflow_bundles_path": config_root / "imports.json",
    }
    configured_paths["provider_externs_path"].write_text("{}\n", encoding="utf-8")
    configured_paths["prompt_externs_path"].write_text("{}\n", encoding="utf-8")
    configured_paths["command_boundaries_path"].write_text("{}\n", encoding="utf-8")
    configured_paths["imported_workflow_bundles_path"].write_text(
        '{"selector-run":{"kind":"compiled","path":"../src/imported_selector.orc"}}\n',
        encoding="utf-8",
    )
    imported_source = source_root / "imported_selector.orc"
    shutil.copyfile(CLI_FIXTURES / "imported_selector.orc", imported_source)
    configured_paths["recursively_imported_source"] = imported_source
    state = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "source_roots": (source_root,),
            **{
                key: path
                for key, path in configured_paths.items()
                if key != "recursively_imported_source"
            },
        },
    )
    return state, configured_paths


def test_initialize_compile_driver_freezes_absent_production_configuration_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial = lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    production_loader = build.load_frontend_initialization_configuration
    calls: list[dict[str, object]] = []

    def load_once(**kwargs: object) -> build.FrontendInitializationConfiguration:
        calls.append(dict(kwargs))
        return production_loader(**kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(
        compile_driver,
        "load_frontend_initialization_configuration",
        load_once,
    )
    before = _workspace_snapshot(workspace)

    driver = compile_driver.initialize_compile_driver(initial)

    assert calls == [
        {
            "workspace_root": workspace.resolve(),
            "source_roots": (),
            "provider_externs_path": None,
            "prompt_externs_path": None,
            "command_boundaries_path": None,
            "imported_workflow_bundles_path": None,
            "lowering_route": normalize_lowering_route(None),
        }
    ]
    assert driver.state.configuration_vector == lsp_state.ImmutableConfigurationVector(
        configured_paths=(
            ("provider_externs_path", None),
            ("prompt_externs_path", None),
            ("imported_workflow_bundles_path", None),
            ("command_boundaries_path", None),
        ),
        configuration_revisions=(),
        recursively_imported_source_revisions=(),
        builtin_stdlib_source_root=initial.builtin_stdlib_source_root,
    )
    assert driver.initialization_configuration.provider_externs_path is None
    assert driver.initialization_configuration.configuration_trace.records == ()
    assert driver.initialization_configuration.source_read_trace.records == ()
    assert _workspace_snapshot(workspace) == before
    assert not (workspace / ".orchestrate").exists()


def test_initialize_compile_driver_captures_form_registry_once_after_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial = lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    production_loader = build.load_frontend_initialization_configuration
    production_root_validator = (
        compile_driver._validate_trace_paths_within_roots
    )
    events: list[object] = []
    live_heads = ["alpha-form", "zeta-form"]

    def load_then_capture(
        **kwargs: object,
    ) -> build.FrontendInitializationConfiguration:
        events.append("configuration")
        return production_loader(**kwargs)  # type: ignore[arg-type]

    def validate_roots_then_capture(
        revision_vector: tuple[tuple[Path, str], ...],
        *,
        workspace_root: Path,
        builtin_stdlib_source_root: Path,
    ) -> None:
        events.append("root-validation")
        production_root_validator(
            revision_vector,
            workspace_root=workspace_root,
            builtin_stdlib_source_root=builtin_stdlib_source_root,
        )

    def read_registry_once(
        *,
        target_dsl_version: str | None = None,
    ) -> tuple[str, ...]:
        events.append(("registry", target_dsl_version))
        return tuple(live_heads)

    monkeypatch.setattr(
        compile_driver,
        "load_frontend_initialization_configuration",
        load_then_capture,
    )
    monkeypatch.setattr(
        compile_driver,
        "_validate_trace_paths_within_roots",
        validate_roots_then_capture,
    )
    monkeypatch.setattr(
        compile_driver,
        "registered_form_heads",
        read_registry_once,
        raising=False,
    )

    driver = compile_driver.initialize_compile_driver(initial)
    captured = driver.frozen_form_completions
    live_heads[:] = ["changed-after-initialization"]

    assert events == [
        "configuration",
        "root-validation",
        ("registry", None),
    ]
    assert tuple(row.label for row in captured) == (
        "alpha-form",
        "zeta-form",
    )
    assert driver.frozen_form_completions is captured
    assert tuple(row.label for row in driver.frozen_form_completions) == (
        "alpha-form",
        "zeta-form",
    )


def test_initialize_compile_driver_does_not_read_registry_after_config_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial = lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    registry_calls: list[object] = []

    def fail_configuration(
        **_kwargs: object,
    ) -> build.FrontendInitializationConfiguration:
        raise RuntimeError("configuration rejected")

    def unexpected_registry_read(
        *,
        target_dsl_version: str | None = None,
    ) -> tuple[str, ...]:
        registry_calls.append(target_dsl_version)
        return ()

    monkeypatch.setattr(
        compile_driver,
        "load_frontend_initialization_configuration",
        fail_configuration,
    )
    monkeypatch.setattr(
        compile_driver,
        "registered_form_heads",
        unexpected_registry_read,
        raising=False,
    )

    with pytest.raises(RuntimeError, match="configuration rejected"):
        compile_driver.initialize_compile_driver(initial)

    assert registry_calls == []


def test_initialize_compile_driver_validates_roots_before_registry_capture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    external_source = tmp_path / "imported_selector.orc"
    shutil.copyfile(CLI_FIXTURES / "imported_selector.orc", external_source)
    imported_manifest = workspace / "imports.json"
    imported_manifest.write_text(
        (
            '{"external":{"kind":"compiled","path":"'
            f'{external_source.as_posix()}"}}}}\n'
        ),
        encoding="utf-8",
    )
    initial = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "imported_workflow_bundles_path": imported_manifest,
        },
    )
    production_loader = build.load_frontend_initialization_configuration
    production_root_validator = (
        compile_driver._validate_trace_paths_within_roots
    )
    events: list[object] = []

    def load_configuration(
        **kwargs: object,
    ) -> build.FrontendInitializationConfiguration:
        events.append("configuration")
        return production_loader(**kwargs)  # type: ignore[arg-type]

    def reject_external_root(
        revision_vector: tuple[tuple[Path, str], ...],
        *,
        workspace_root: Path,
        builtin_stdlib_source_root: Path,
    ) -> None:
        events.append("root-validation")
        production_root_validator(
            revision_vector,
            workspace_root=workspace_root,
            builtin_stdlib_source_root=builtin_stdlib_source_root,
        )

    def unexpected_registry_read(
        *,
        target_dsl_version: str | None = None,
    ) -> tuple[str, ...]:
        events.append(("registry", target_dsl_version))
        return ()

    monkeypatch.setattr(
        compile_driver,
        "load_frontend_initialization_configuration",
        load_configuration,
    )
    monkeypatch.setattr(
        compile_driver,
        "_validate_trace_paths_within_roots",
        reject_external_root,
    )
    monkeypatch.setattr(
        compile_driver,
        "registered_form_heads",
        unexpected_registry_read,
    )

    with pytest.raises(RuntimeError, match="outside the initialized roots"):
        compile_driver.initialize_compile_driver(initial)

    assert events == ["configuration", "root-validation"]


def test_initialize_compile_driver_rejects_real_loader_external_recursive_source(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    config_root = workspace / "config"
    config_root.mkdir()
    external_source = tmp_path / "imported_selector.orc"
    shutil.copyfile(CLI_FIXTURES / "imported_selector.orc", external_source)
    imported_manifest = config_root / "imports.json"
    imported_manifest.write_text(
        (
            '{"external":{"kind":"compiled","path":"'
            f'{external_source.as_posix()}"}}}}\n'
        ),
        encoding="utf-8",
    )
    initial = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "imported_workflow_bundles_path": imported_manifest,
        },
    )

    with pytest.raises(RuntimeError, match="outside the initialized roots"):
        compile_driver.initialize_compile_driver(initial)


def test_initialize_compile_driver_accepts_real_loader_frozen_builtin_sources(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    imported_source = workspace / "phase_scope_stdlib_targets.orc"
    shutil.copyfile(
        CLI_FIXTURES.parent / "valid" / "phase_scope_stdlib_targets.orc",
        imported_source,
    )
    imported_manifest = workspace / "imports.json"
    imported_manifest.write_text(
        (
            '{"phase-scope":{"kind":"compiled",'
            '"path":"phase_scope_stdlib_targets.orc"}}\n'
        ),
        encoding="utf-8",
    )
    initial = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "source_roots": (workspace,),
            "imported_workflow_bundles_path": imported_manifest,
        },
    )

    driver = compile_driver.initialize_compile_driver(initial)

    vector = driver.state.configuration_vector
    assert vector is not None
    builtin_source = (
        initial.builtin_stdlib_source_root / "std" / "context.orc"
    ).resolve()
    assert builtin_source.is_file()
    assert builtin_source in {
        path
        for path, _revision in vector.recursively_imported_source_revisions
    }


def test_probe_raw_revision_reads_once_and_retains_binary_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = (tmp_path / "configuration.json").resolve()
    raw_bytes = b"\xff\x00configuration"
    calls: list[Path] = []

    def read_bytes_once(self: Path) -> bytes:
        calls.append(self)
        return raw_bytes

    monkeypatch.setattr(Path, "read_bytes", read_bytes_once)

    revision = compile_driver.probe_raw_revision(path)

    assert calls == [path]
    assert revision == (
        path,
        f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}",
    )


def test_recheck_reads_complete_configured_and_recursive_vector_once_without_writes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    driver = compile_driver.initialize_compile_driver(initial)
    vector = driver.state.configuration_vector
    assert vector is not None
    assert vector.configured_paths == (
        ("provider_externs_path", paths["provider_externs_path"].resolve()),
        ("prompt_externs_path", paths["prompt_externs_path"].resolve()),
        (
            "imported_workflow_bundles_path",
            paths["imported_workflow_bundles_path"].resolve(),
        ),
        (
            "command_boundaries_path",
            paths["command_boundaries_path"].resolve(),
        ),
    )
    assert {path for path, _revision in vector.configuration_revisions} == {
        paths["provider_externs_path"].resolve(),
        paths["prompt_externs_path"].resolve(),
        paths["command_boundaries_path"].resolve(),
        paths["imported_workflow_bundles_path"].resolve(),
    }
    assert vector.recursively_imported_source_revisions == (
        compile_driver.probe_raw_revision(
            paths["recursively_imported_source"],
        ),
    )
    expected_read_paths = {
        path
        for path, _revision in (
            *vector.configuration_revisions,
            *vector.recursively_imported_source_revisions,
        )
    }
    calls: list[Path] = []
    read_bytes = Path.read_bytes

    def observe_read(path: Path) -> bytes:
        calls.append(path.resolve())
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", observe_read)
    before = _workspace_snapshot(workspace)
    calls.clear()

    transition = driver.recheck_configuration()

    assert transition.state is driver.state
    assert transition.effects == lsp_state.StateEffects()
    assert set(calls) == expected_read_paths
    assert len(calls) == len(expected_read_paths)
    assert _workspace_snapshot(workspace) == before
    assert not (workspace / ".orchestrate").exists()


def test_configuration_drift_latches_cancels_and_notifies_once_across_reversion(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(entry_text, encoding="utf-8")
    driver = compile_driver.initialize_compile_driver(initial)
    opened = lsp_state.open_entry(
        driver.state,
        document_uri=entry_path.as_uri(),
        editor_text=entry_text,
        disk_snapshot=compile_driver.probe_disk_source(entry_path),
    )
    driver.state = opened.state
    original_bytes = paths["provider_externs_path"].read_bytes()
    paths["provider_externs_path"].write_text(
        '{"providers.execute":"changed"}\n',
        encoding="utf-8",
    )

    changed = driver.recheck_configuration()
    repeated = driver.recheck_configuration()
    paths["provider_externs_path"].write_bytes(original_bytes)
    reverted = driver.recheck_configuration()

    assert changed.state is driver.state
    assert changed.state.configuration_stale is True
    assert changed.state.entries == ()
    assert changed.effects == lsp_state.StateEffects(
        canceled_generations=((entry_path.resolve(), 1),),
        restart_notice_required=True,
    )
    assert repeated.state is changed.state
    assert repeated.effects == lsp_state.StateEffects()
    assert reverted.state is changed.state
    assert reverted.state.configuration_stale is True
    assert reverted.effects == lsp_state.StateEffects()


@pytest.mark.parametrize(
    "drift_kind",
    ("recursive_source_changed", "configuration_missing", "configuration_unreadable"),
)
def test_recursive_changed_missing_and_unreadable_rechecks_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    drift_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    driver = compile_driver.initialize_compile_driver(initial)
    if drift_kind == "recursive_source_changed":
        paths["recursively_imported_source"].write_bytes(
            paths["recursively_imported_source"].read_bytes() + b"\n"
        )
    elif drift_kind == "configuration_missing":
        paths["imported_workflow_bundles_path"].unlink()
    else:
        unreadable = paths["command_boundaries_path"].resolve()
        read_bytes = Path.read_bytes

        def deny_one(path: Path) -> bytes:
            if path.resolve() == unreadable:
                raise PermissionError("unreadable after initialization")
            return read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", deny_one)

    transition = driver.recheck_configuration()

    assert transition.state.configuration_stale is True
    assert transition.effects.restart_notice_required is True


def test_builtin_root_drift_latches_and_reversion_never_unlatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial = lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    driver = compile_driver.initialize_compile_driver(initial)
    original_root = initial.builtin_stdlib_source_root
    monkeypatch.setattr(
        compile_driver.compiler,
        "_builtin_stdlib_source_root",
        lambda: tmp_path / "different-stdlib",
    )

    changed = driver.recheck_configuration()
    monkeypatch.setattr(
        compile_driver.compiler,
        "_builtin_stdlib_source_root",
        lambda: original_root,
    )
    reverted = driver.recheck_configuration()

    assert changed.state.configuration_stale is True
    assert changed.effects.restart_notice_required is True
    assert reverted.state is changed.state
    assert reverted.effects == lsp_state.StateEffects()


def test_recheck_observes_builtin_identity_even_when_a_file_already_drifted(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    driver = compile_driver.initialize_compile_driver(initial)
    paths["provider_externs_path"].write_text(
        '{"providers.execute":"changed"}\n',
        encoding="utf-8",
    )
    calls: list[None] = []

    def current_builtin_root() -> Path:
        calls.append(None)
        return initial.builtin_stdlib_source_root

    monkeypatch.setattr(
        compile_driver.compiler,
        "_builtin_stdlib_source_root",
        current_builtin_root,
    )

    transition = driver.recheck_configuration()

    assert transition.state.configuration_stale is True
    assert calls == [None]


@pytest.mark.parametrize(
    ("failure_kind", "expected_exception"),
    (
        ("missing", build.LispFrontendCompileError),
        ("invalid", build.LispFrontendCompileError),
        ("unreadable", PermissionError),
    ),
)
def test_configured_bootstrap_failure_prevents_driver_initialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_kind: str,
    expected_exception: type[Exception],
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider_path = workspace / "providers.json"
    if failure_kind == "invalid":
        provider_path.write_text("[]\n", encoding="utf-8")
    elif failure_kind == "unreadable":
        provider_path.write_text("{}\n", encoding="utf-8")
        read_bytes = Path.read_bytes

        def deny_provider(path: Path) -> bytes:
            if path.resolve() == provider_path.resolve():
                raise PermissionError("unreadable during initialization")
            return read_bytes(path)

        monkeypatch.setattr(Path, "read_bytes", deny_provider)
    initial = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={"provider_externs_path": provider_path},
    )

    with pytest.raises(expected_exception):
        compile_driver.initialize_compile_driver(initial)

    assert not (workspace / ".orchestrate").exists()


def test_driver_coalesces_latest_generation_and_accepts_one_injected_success(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(entry_text, encoding="utf-8")
    calls: list[tuple[build.FrontendBuildRequest, SourceReadTrace]] = []
    result = _injected_success()

    def build_once(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        calls.append((request, source_read_trace))
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        return result

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=build_once,
    )
    opened = lsp_state.open_entry(
        driver.state,
        document_uri=entry_path.as_uri(),
        editor_text=entry_text,
        disk_snapshot=compile_driver.probe_disk_source(entry_path),
    )
    driver.apply_transition(opened)
    saved = lsp_state.save_entry(
        driver.state,
        document_uri=entry_path.as_uri(),
        disk_snapshot=compile_driver.probe_disk_source(entry_path),
    )
    driver.apply_transition(saved)

    transitions = driver.drain()

    assert driver.queued_generations == ()
    assert len(calls) == 1
    request, trace = calls[0]
    assert request == build.FrontendBuildRequest(
        source_path=entry_path.resolve(),
        source_roots=(),
        entry_workflow=None,
        provider_externs_path=None,
        prompt_externs_path=None,
        imported_workflow_bundles_path=None,
        command_boundaries_path=None,
        emit_debug_yaml=False,
        workspace_root=workspace.resolve(),
        lint_profile=driver.state.options.lint_profile,
        lowering_route=driver.state.options.lowering_route,
    )
    assert trace.revision_vector == (
        compile_driver.probe_raw_revision(entry_path),
    )
    assert len(transitions) == 1
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation is None
    assert entry.compile_status == "success"
    assert entry.accepted_snapshot == lsp_state.AcceptedCompileSnapshot(
        build_value=result,
        source_revision_vector=trace.revision_vector,
        accepted_text_by_path=((entry_path.resolve(), entry_text),),
    )
    assert entry.dependency_closure == frozenset({entry_path.resolve()})
    assert entry.diagnostic_contributions == ()


def _opened_split_phase_driver(
    tmp_path: Path,
) -> tuple[compile_driver.LspCompileDriver, Path, str]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(entry_text, encoding="utf-8")

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=request.source_path,
            revision=compile_driver.probe_disk_source(
                request.source_path
            ).revision,
        )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=successful_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    return driver, entry_path.resolve(), entry_text


def test_split_phase_close_reopen_invalidates_aliasing_old_completion(
    tmp_path: Path,
) -> None:
    driver, entry_path, entry_text = _opened_split_phase_driver(tmp_path)
    prepared = driver.begin_next()
    assert prepared is not None
    assert prepared.generation == 1
    outcome = driver.execute_prepared(prepared)

    driver.apply_transition(
        lsp_state.close_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
        )
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    reopened = driver.state.entries[0]
    assert reopened.generation == prepared.generation == 1
    assert driver.queued_generations == ((entry_path, 1),)

    driver.finish_prepared(outcome)

    reopened = driver.state.entries[0]
    assert reopened.compile_status == "pending"
    assert reopened.pending_generation == 1
    assert reopened.accepted_snapshot is None
    assert driver.queued_generations == ((entry_path, 1),)
    assert driver.running is False


def test_split_phase_wrong_completion_ticket_preserves_active_job(
    tmp_path: Path,
) -> None:
    driver, _entry_path, _entry_text = _opened_split_phase_driver(tmp_path)
    prepared = driver.begin_next()
    assert prepared is not None
    outcome = driver.execute_prepared(prepared)
    wrong_outcome = replace(
        outcome,
        prepared=replace(outcome.prepared, ticket=object()),
    )

    with pytest.raises(RuntimeError):
        driver.finish_prepared(wrong_outcome)

    assert driver.running is True
    driver.finish_prepared(outcome)
    assert driver.running is False
    assert driver.state.entries[0].compile_status == "success"


def test_split_phase_duplicate_completion_fails_closed(
    tmp_path: Path,
) -> None:
    driver, _entry_path, _entry_text = _opened_split_phase_driver(tmp_path)
    prepared = driver.begin_next()
    assert prepared is not None
    outcome = driver.execute_prepared(prepared)

    driver.finish_prepared(outcome)
    completed_state = driver.state

    with pytest.raises(RuntimeError):
        driver.finish_prepared(outcome)

    assert driver.state is completed_state
    assert driver.running is False


def test_split_phase_stale_completion_leaves_newer_generation_queued(
    tmp_path: Path,
) -> None:
    driver, entry_path, _entry_text = _opened_split_phase_driver(tmp_path)
    prepared = driver.begin_next()
    assert prepared is not None
    assert prepared.generation == 1
    outcome = driver.execute_prepared(prepared)

    driver.apply_transition(
        lsp_state.save_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    assert driver.queued_generations == ((entry_path, 2),)

    driver.finish_prepared(outcome)

    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation == 2
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert driver.queued_generations == ((entry_path, 2),)
    assert driver.running is False


def test_driver_rechecks_configuration_before_calling_builder_without_notification(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(entry_text, encoding="utf-8")
    calls: list[build.FrontendBuildRequest] = []

    def must_not_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        calls.append(request)
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        initial,
        build_in_memory=must_not_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    paths["provider_externs_path"].write_text(
        '{"providers.execute":"changed"}\n',
        encoding="utf-8",
    )

    transition = driver.run_next()

    assert transition is not None
    assert transition.state.configuration_stale is True
    assert transition.effects.restart_notice_required is True
    assert calls == []
    assert driver.queued_generations == ()


def test_driver_logs_preflight_exception_settles_generation_and_continues_queue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first_path = workspace / "first.orc"
    second_path = workspace / "second.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (first_path, second_path):
        path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []
    built: list[Path] = []

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        built.append(request.source_path)
        source_read_trace._record(
            canonical_path=request.source_path,
            revision=compile_driver.probe_disk_source(
                request.source_path
            ).revision,
        )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=successful_build,
        log_server_error=logged.append,
    )
    for path in (first_path, second_path):
        driver.apply_transition(
            lsp_state.open_entry(
                driver.state,
                document_uri=path.as_uri(),
                editor_text=text,
                disk_snapshot=compile_driver.probe_disk_source(path),
            )
        )
    builtin_root = driver.state.builtin_stdlib_source_root
    root_probe_calls = 0

    def fail_first_root_probe() -> Path:
        nonlocal root_probe_calls
        root_probe_calls += 1
        if root_probe_calls == 1:
            raise RuntimeError("preflight builtin probe failed")
        return builtin_root

    monkeypatch.setattr(
        compile_driver.compiler,
        "_builtin_stdlib_source_root",
        fail_first_root_probe,
    )

    first_transition = driver.run_next()

    assert first_transition is not None
    assert root_probe_calls == 1
    assert tuple(str(error) for error in logged) == (
        "preflight builtin probe failed",
    )
    first = next(entry for entry in driver.state.entries if entry.path == first_path)
    assert first.compile_status == "server_error"
    assert first.pending_generation is None
    assert built == []

    second_transition = driver.run_next()

    assert second_transition is not None
    second = next(entry for entry in driver.state.entries if entry.path == second_path)
    assert second.compile_status == "success"
    assert built == [second_path.resolve()]
    assert root_probe_calls == 3
    assert driver.queued_generations == ()


def test_driver_discards_success_when_configuration_drifts_during_build(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(entry_text, encoding="utf-8")

    def drift_during_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        paths["prompt_externs_path"].write_text(
            '{"prompts.execute":"changed"}\n',
            encoding="utf-8",
        )
        return _injected_success(("must-not-publish",))

    driver = compile_driver.initialize_compile_driver(
        initial,
        build_in_memory=drift_during_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    assert transition.state.configuration_stale is True
    assert transition.effects.restart_notice_required is True
    assert driver.state.entries == ()
    assert driver.queued_generations == ()


@pytest.mark.parametrize("outcome", ("success", "language_error"))
@pytest.mark.parametrize("attempt_drift", (False, True))
def test_driver_real_core_requires_exact_attempt_configuration_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
    attempt_drift: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    provider_path = workspace / "providers.json"
    revision_a = b'{"provider":"revision-a"}\n'
    revision_b = b'{"provider":"revision-b"}\n'
    provider_path.write_bytes(revision_a)
    if outcome == "success":
        entry_path = workspace / "std" / "context.orc"
        entry_path.parent.mkdir()
        shutil.copyfile(
            Path(compiler.__file__).parent
            / "stdlib_modules"
            / "std"
            / "context.orc",
            entry_path,
        )
    else:
        entry_path = workspace / "entry.orc"
        shutil.copyfile(
            CLI_FIXTURES.parent / "invalid" / "unknown_type.orc",
            entry_path,
        )
    initial = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "source_roots": (workspace,),
            "provider_externs_path": provider_path,
        },
    )
    driver = compile_driver.initialize_compile_driver(initial)
    text = entry_path.read_text(encoding="utf-8")
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    read_bytes = Path.read_bytes
    provider_reads = 0

    def observe_attempt_configuration(path: Path) -> bytes:
        nonlocal provider_reads
        if path.resolve(strict=False) != provider_path.resolve():
            return read_bytes(path)
        provider_reads += 1
        if attempt_drift and provider_reads == 2:
            path.write_bytes(revision_b)
            try:
                return read_bytes(path)
            finally:
                path.write_bytes(revision_a)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", observe_attempt_configuration)

    transition = driver.run_next()

    assert transition is not None
    assert provider_path.read_bytes() == revision_a
    if attempt_drift:
        assert driver.state.configuration_stale is True
        assert driver.state.entries == ()
        assert transition.effects.restart_notice_required is True
        assert transition.effects.republish_uris == ()
        assert driver.queued_generations == ()

        reverted = driver.recheck_configuration()

        assert reverted.state is driver.state
        assert reverted.effects == lsp_state.StateEffects()
        assert reverted.state.configuration_stale is True
    else:
        entry = driver.state.entries[0]
        assert entry.compile_status == outcome
        assert entry.pending_generation is None
        assert driver.state.configuration_stale is False


@pytest.mark.parametrize("outcome", ("success", "language_error"))
@pytest.mark.parametrize(
    "evidence_kind",
    ("missing", "extra", "replaced", "reordered"),
)
def test_driver_latches_injected_attempt_configuration_evidence_mismatch(
    tmp_path: Path,
    outcome: str,
    evidence_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    diagnostic = LispFrontendDiagnostic(
        code="must_not_publish",
        message="attempt configuration mismatch",
        span=SourceSpan(
            start=SourcePosition(
                path=entry_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
            end=SourcePosition(
                path=entry_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
        ),
    )
    holder: dict[str, compile_driver.LspCompileDriver] = {}

    def return_mismatched_evidence(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        vector = holder["driver"].state.configuration_vector
        assert vector is not None
        expected = vector.configuration_revisions
        assert (
            paths["recursively_imported_source"].resolve()
            not in {path for path, _revision in expected}
        )
        if evidence_kind == "missing":
            observed = None
        elif evidence_kind == "extra":
            observed = tuple(
                sorted(
                    (
                        *expected,
                        (
                            (workspace / "extra.json").resolve(),
                            "sha256:" + ("e" * 64),
                        ),
                    ),
                    key=lambda item: item[0].as_posix(),
                )
            )
        elif evidence_kind == "replaced":
            observed = (
                (expected[0][0], "sha256:" + ("0" * 64)),
                *expected[1:],
            )
        else:
            observed = tuple(reversed(expected))
        if outcome == "success":
            if observed is None:
                return SimpleNamespace(diagnostics=("must-not-publish",))
            return _injected_success(
                ("must-not-publish",),
                configuration_revision_vector=observed,
            )
        raise _injected_language_error(
            (diagnostic,),
            configuration_revision_vector=observed,
        )

    driver = compile_driver.initialize_compile_driver(
        initial,
        build_in_memory=return_mismatched_evidence,
    )
    holder["driver"] = driver
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    assert driver.state.configuration_stale is True
    assert driver.state.entries == ()
    assert transition.effects.restart_notice_required is True
    assert transition.effects.republish_uris == ()
    assert driver.queued_generations == ()


def test_source_mutation_during_build_routes_through_revision_observation(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    changed_text = entry_text + "\n"
    entry_path.write_text(entry_text, encoding="utf-8")
    result = _injected_success(("must-not-publish",))

    def mutate_after_trace(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        entry_path.write_text(changed_text, encoding="utf-8")
        return result

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=mutate_after_trace,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.buffer_status == "dirty"
    assert entry.compile_status == "idle"
    assert entry.pending_generation is None
    assert entry.accepted_snapshot is None
    assert entry.disk_snapshot == compile_driver.probe_disk_source(entry_path)
    assert entry.diagnostic_contributions == ()
    assert driver.queued_generations == ()


def test_driver_rejects_success_built_from_disk_newer_than_clean_editor_proof(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    editor_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    newer_disk_text = editor_text + "\n"
    entry_path.write_text(editor_text, encoding="utf-8")

    def build_after_disk_moves(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        entry_path.write_text(newer_disk_text, encoding="utf-8")
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        return _injected_success(("must-not-publish",))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=build_after_disk_moves,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=editor_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation is None
    assert entry.buffer_status == "dirty"
    assert entry.compile_status == "idle"
    assert entry.accepted_snapshot is None
    assert entry.disk_snapshot == compile_driver.probe_disk_source(entry_path)
    assert entry.diagnostic_contributions == ()
    assert driver.queued_generations == ()


def test_driver_rejects_language_error_from_disk_newer_than_clean_editor_proof(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    editor_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    newer_disk_text = editor_text + "\n"
    entry_path.write_text(editor_text, encoding="utf-8")
    diagnostic = LispFrontendDiagnostic(
        code="must_not_publish",
        message="diagnostic belongs to newer disk text",
        span=SourceSpan(
            start=SourcePosition(
                path=entry_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
            end=SourcePosition(
                path=entry_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
        ),
    )

    def fail_after_disk_moves(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        entry_path.write_text(newer_disk_text, encoding="utf-8")
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=fail_after_disk_moves,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=editor_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation is None
    assert entry.buffer_status == "dirty"
    assert entry.compile_status == "idle"
    assert entry.accepted_snapshot is None
    assert entry.disk_snapshot == compile_driver.probe_disk_source(entry_path)
    assert entry.diagnostic_contributions == ()
    assert driver.queued_generations == ()


def test_trace_drift_without_prior_ownership_reproves_and_reschedules_entry(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    new_dependency = workspace / "new-dependency.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    new_dependency.write_text(text, encoding="utf-8")
    build_count = 0

    def add_then_mutate_dependency(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        nonlocal build_count
        build_count += 1
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        if build_count == 2:
            source_read_trace._record(
                canonical_path=new_dependency.resolve(),
                revision=compile_driver.probe_disk_source(new_dependency).revision,
            )
            new_dependency.write_text(text + "\n", encoding="utf-8")
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=add_then_mutate_dependency,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.run_next()
    driver.apply_transition(
        lsp_state.save_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.generation == 3
    assert entry.pending_generation == 3
    assert entry.buffer_status == "clean"
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert entry.diagnostic_contributions == ()
    assert driver.queued_generations == ((entry_path.resolve(), 3),)


def test_driver_accepts_success_trace_under_exact_frozen_builtin_root(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    initial = lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    builtin_source = (
        initial.builtin_stdlib_source_root / "std" / "context.orc"
    ).resolve()
    assert builtin_source.is_file()

    def return_builtin_trace(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        for path in (entry_path, builtin_source):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        initial,
        build_in_memory=return_builtin_trace,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    entry = driver.state.entries[0]
    assert entry.compile_status == "success"
    assert entry.accepted_snapshot is not None
    assert builtin_source in entry.dependency_closure
    assert builtin_source in {
        path
        for path, _revision in entry.accepted_snapshot.source_revision_vector
    }


def test_driver_routes_external_trace_to_logged_failure_and_continues_queue(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    second_path = workspace / "second.orc"
    external_path = tmp_path / "external.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, second_path):
        path.write_text(entry_text, encoding="utf-8")
    external_path.write_text(entry_text, encoding="utf-8")
    logged: list[Exception] = []

    def return_external_trace(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        paths = (
            (entry_path, external_path)
            if request.source_path == entry_path.resolve()
            else (second_path,)
        )
        for path in paths:
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=return_external_trace,
        log_server_error=logged.append,
    )
    for path in (entry_path, second_path):
        driver.apply_transition(
            lsp_state.open_entry(
                driver.state,
                document_uri=path.as_uri(),
                editor_text=entry_text,
                disk_snapshot=compile_driver.probe_disk_source(path),
            )
        )

    transitions = driver.drain()

    assert len(transitions) == 2
    assert len(logged) == 1
    assert "outside" in str(logged[0])
    entry = next(item for item in driver.state.entries if item.path == entry_path)
    second = next(item for item in driver.state.entries if item.path == second_path)
    assert entry.compile_status == "server_error"
    assert entry.accepted_snapshot is None
    assert entry.dependency_closure is None
    assert entry.diagnostic_contributions == ()
    assert second.compile_status == "success"
    assert driver.running is False


@pytest.mark.parametrize(
    "invalid_trace",
    ("empty", "entry_missing", "sentinel_member"),
)
def test_driver_rejects_invalid_success_trace_and_continues_queue(
    tmp_path: Path,
    invalid_trace: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first_path = workspace / "first.orc"
    second_path = workspace / "second.orc"
    dependency_path = workspace / "dependency.orc"
    missing_path = workspace / "missing.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (first_path, second_path, dependency_path):
        path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []

    def return_invalid_then_valid_trace(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        if request.source_path == second_path.resolve():
            source_read_trace._record(
                canonical_path=second_path.resolve(),
                revision=compile_driver.probe_disk_source(second_path).revision,
            )
            return _injected_success()
        if invalid_trace == "entry_missing":
            source_read_trace._record(
                canonical_path=dependency_path.resolve(),
                revision=compile_driver.probe_disk_source(
                    dependency_path
                ).revision,
            )
        elif invalid_trace == "sentinel_member":
            source_read_trace._record(
                canonical_path=first_path.resolve(),
                revision=compile_driver.probe_disk_source(first_path).revision,
            )
            source_read_trace._record(
                canonical_path=missing_path.resolve(),
                revision="missing",
            )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=return_invalid_then_valid_trace,
        log_server_error=logged.append,
    )
    for path in (first_path, second_path):
        driver.apply_transition(
            lsp_state.open_entry(
                driver.state,
                document_uri=path.as_uri(),
                editor_text=text,
                disk_snapshot=compile_driver.probe_disk_source(path),
            )
        )

    first_transition = driver.run_next()
    second_transition = driver.run_next()

    assert first_transition is not None
    assert second_transition is not None
    first = next(entry for entry in driver.state.entries if entry.path == first_path)
    second = next(entry for entry in driver.state.entries if entry.path == second_path)
    assert first.compile_status == "server_error"
    assert first.pending_generation is None
    assert first.accepted_snapshot is None
    assert first.dependency_closure is None
    assert first.diagnostic_contributions == ()
    assert second.compile_status == "success"
    assert len(logged) == 1
    assert "successful compiler trace" in str(logged[0])


def test_driver_routes_language_error_external_trace_to_logged_server_failure(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    external_path = tmp_path / "external.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, external_path):
        path.write_text(text, encoding="utf-8")
    diagnostic = LispFrontendDiagnostic(
        code="must_not_publish",
        message="external trace invalidates this language result",
        span=SourceSpan(
            start=SourcePosition(
                path=entry_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
            end=SourcePosition(
                path=entry_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
        ),
    )
    logged: list[Exception] = []

    def raise_with_external_trace(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        for path in (entry_path, external_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=raise_with_external_trace,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.compile_status == "server_error"
    assert entry.accepted_snapshot is None
    assert entry.dependency_closure is None
    assert entry.diagnostic_contributions == ()
    assert len(logged) == 1
    assert "outside" in str(logged[0])
    assert driver.running is False


def test_driver_records_server_failure_when_postflight_recheck_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        return _injected_success(("must-not-publish",))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=successful_build,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    builtin_root = driver.state.builtin_stdlib_source_root
    calls = 0

    def fail_after_preflight() -> Path:
        nonlocal calls
        calls += 1
        if calls == 1:
            return builtin_root
        raise RuntimeError("postflight root probe failed")

    monkeypatch.setattr(
        compile_driver.compiler,
        "_builtin_stdlib_source_root",
        fail_after_preflight,
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.compile_status == "server_error"
    assert entry.accepted_snapshot is None
    assert entry.dependency_closure is None
    assert entry.diagnostic_contributions == ()
    assert tuple(str(error) for error in logged) == (
        "postflight root probe failed",
        "postflight root probe failed",
    )
    assert driver.running is False


@pytest.mark.parametrize("late_transition", ("dirty", "closed"))
def test_driver_discards_dirty_or_closed_completion(
    tmp_path: Path,
    late_transition: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(entry_text, encoding="utf-8")
    holder: dict[str, compile_driver.LspCompileDriver] = {}

    def complete_late(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        driver = holder["driver"]
        transition = (
            lsp_state.change_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
                editor_text=entry_text + " ",
            )
            if late_transition == "dirty"
            else lsp_state.close_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
            )
        )
        driver.apply_transition(transition)
        return _injected_success(("late",))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=complete_late,
    )
    holder["driver"] = driver
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    if late_transition == "closed":
        assert driver.state.entries == ()
    else:
        entry = driver.state.entries[0]
        assert entry.buffer_status == "dirty"
        assert entry.accepted_snapshot is None


def test_driver_reentrant_run_is_rejected_while_single_builder_is_running(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    entry_text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(entry_text, encoding="utf-8")
    holder: dict[str, compile_driver.LspCompileDriver] = {}

    def assert_serialized(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        driver = holder["driver"]
        assert driver.running is True
        with pytest.raises(RuntimeError, match="already running"):
            driver.run_next()
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=assert_serialized,
    )
    holder["driver"] = driver
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=entry_text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    assert driver.running is False
    assert driver.state.entries[0].compile_status == "success"


def test_driver_process_local_guard_prevents_two_threads_from_consuming_together(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_paths = tuple(workspace / f"entry-{index}.orc" for index in range(2))
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in entry_paths:
        path.write_text(text, encoding="utf-8")

    first_preflight_entered = Event()
    release_first_preflight = Event()
    second_caller_finished = Event()
    counter_lock = Lock()
    preflight_calls = 0
    active_builds = 0
    max_active_builds = 0
    original_recheck = compile_driver.LspCompileDriver.recheck_configuration

    def gate_first_preflight(
        driver: compile_driver.LspCompileDriver,
    ) -> lsp_state.LspStateTransition:
        nonlocal preflight_calls
        with counter_lock:
            preflight_calls += 1
            call_number = preflight_calls
        if call_number == 1:
            first_preflight_entered.set()
            if not release_first_preflight.wait(timeout=3):
                raise RuntimeError("test did not release the first preflight")
        return original_recheck(driver)

    def detect_concurrent_builds(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        nonlocal active_builds, max_active_builds
        with counter_lock:
            active_builds += 1
            max_active_builds = max(max_active_builds, active_builds)
        try:
            source_read_trace._record(
                canonical_path=request.source_path.resolve(),
                revision=compile_driver.probe_disk_source(
                    request.source_path
                ).revision,
            )
            return _injected_success()
        finally:
            with counter_lock:
                active_builds -= 1

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=detect_concurrent_builds,
    )
    for path in entry_paths:
        driver.apply_transition(
            lsp_state.open_entry(
                driver.state,
                document_uri=path.as_uri(),
                editor_text=text,
                disk_snapshot=compile_driver.probe_disk_source(path),
            )
        )
    monkeypatch.setattr(
        compile_driver.LspCompileDriver,
        "recheck_configuration",
        gate_first_preflight,
    )
    results: list[lsp_state.LspStateTransition | None] = []
    errors: list[Exception] = []
    result_lock = Lock()

    def run_one(*, record_finished: bool = False) -> None:
        try:
            result = driver.run_next()
        except Exception as error:
            with result_lock:
                errors.append(error)
        else:
            with result_lock:
                results.append(result)
        finally:
            if record_finished:
                second_caller_finished.set()

    first_worker = Thread(target=run_one)
    first_worker.start()
    assert first_preflight_entered.wait(timeout=3)
    second_worker = Thread(target=run_one, kwargs={"record_finished": True})
    second_worker.start()
    second_finished_before_release = second_caller_finished.wait(timeout=3)
    with counter_lock:
        preflight_calls_before_release = preflight_calls
    release_first_preflight.set()
    first_worker.join(timeout=3)
    second_worker.join(timeout=3)

    assert not first_worker.is_alive()
    assert not second_worker.is_alive()
    assert second_finished_before_release is True
    assert preflight_calls_before_release == 1
    assert max_active_builds == 1
    assert len(results) == 1
    assert results[0] is not None
    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)
    assert str(errors[0]) == "LSP compile driver is already running"
    assert driver.running is False
    assert sorted(entry.compile_status for entry in driver.state.entries) == [
        "pending",
        "success",
    ]
    assert len(driver.queued_generations) == 1

    monkeypatch.setattr(
        compile_driver.LspCompileDriver,
        "recheck_configuration",
        original_recheck,
    )
    final_transition = driver.run_next()

    assert final_transition is not None
    assert {entry.compile_status for entry in driver.state.entries} == {
        "success"
    }
    assert driver.queued_generations == ()


def test_driver_run_next_consults_mutex_before_touching_queued_work(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    build_calls: list[Path] = []

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        build_calls.append(request.source_path)
        source_read_trace._record(
            canonical_path=request.source_path,
            revision=compile_driver.probe_disk_source(
                request.source_path
            ).revision,
        )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=successful_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    state_before = driver.state
    queue_before = driver.queued_generations
    errors: list[Exception] = []
    caller_finished = Event()

    def run_while_mutex_is_owned() -> None:
        try:
            driver.run_next()
        except Exception as error:
            errors.append(error)
        finally:
            caller_finished.set()

    assert driver._run_lock.acquire(blocking=False) is True
    try:
        caller = Thread(target=run_while_mutex_is_owned)
        caller.start()
        assert caller_finished.wait(timeout=3) is True
        caller.join(timeout=3)

        assert not caller.is_alive()
        assert len(errors) == 1
        assert isinstance(errors[0], RuntimeError)
        assert str(errors[0]) == "LSP compile driver is already running"
        assert driver.state is state_before
        assert driver.queued_generations == queue_before
        assert build_calls == []
        assert driver.running is False
    finally:
        driver._run_lock.release()

    transition = driver.run_next()

    assert transition is not None
    assert driver.state.entries[0].compile_status == "success"
    assert driver.queued_generations == ()
    assert build_calls == [entry_path.resolve()]


@pytest.mark.parametrize(
    "stdlib_module",
    ("context", "drain", "phase", "resource"),
)
def test_library_only_entry_uses_one_full_shared_stage3_build_and_never_stage1(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdlib_module: str,
) -> None:
    workspace = tmp_path / "workspace"
    source_root = workspace
    entry_path = workspace / "std" / f"{stdlib_module}.orc"
    entry_path.parent.mkdir(parents=True)
    shutil.copyfile(
        Path(compiler.__file__).parent
        / "stdlib_modules"
        / "std"
        / f"{stdlib_module}.orc",
        entry_path,
    )
    calls: list[build.FrontendBuildRequest] = []
    stage3_calls: list[tuple[Path, dict[str, object]]] = []
    compile_stage3 = build.compile_stage3_entrypoint
    compile_stage1 = compiler.compile_stage1_entrypoint

    assert all(
        value is not compile_stage1
        for value in vars(build).values()
    )
    assert all(
        value is not compile_stage1
        for value in vars(compile_driver).values()
    )

    def observe_full_stage3(
        path: Path,
        **kwargs: object,
    ) -> object:
        stage3_calls.append((path.resolve(), dict(kwargs)))
        return compile_stage3(path, **kwargs)

    monkeypatch.setattr(build, "compile_stage3_entrypoint", observe_full_stage3)

    def one_real_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> build.FrontendInMemoryBuildResult:
        calls.append(request)
        return build.build_frontend_bundle_in_memory(
            request,
            source_read_trace=source_read_trace,
        )

    monkeypatch.setattr(
        compiler,
        "compile_stage1_entrypoint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Stage 1 must not be called")
        ),
    )
    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=workspace.as_uri(),
            initialization_options={"source_roots": (source_root,)},
        ),
        build_in_memory=one_real_build,
    )
    text = entry_path.read_text(encoding="utf-8")
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.drain()

    assert len(calls) == 1
    assert calls[0].entry_workflow is None
    assert len(stage3_calls) == 1
    assert stage3_calls[0][0] == entry_path.resolve()
    assert stage3_calls[0][1]["entry_workflow"] is None
    assert (
        stage3_calls[0][1]["validation_profile"]
        is compiler.Stage3ValidationProfile.SHARED_CALLABLE
    )
    assert "validate_shared" not in stage3_calls[0][1]
    result = driver.state.entries[0].accepted_snapshot.build_value
    assert result.entry_selection is None
    assert result.selected_workflow_name is None
    assert (
        result.compile_result.validation_profile
        is compiler.Stage3ValidationProfile.SHARED_CALLABLE
    )
    assert driver.state.entries[0].compile_status == "success"


@pytest.mark.parametrize("listed_first", (True, False))
def test_l3_build_request_uses_only_exact_per_source_entry_selection(
    tmp_path: Path,
    listed_first: bool,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir()
    listed = workspace / "apps" / "main.orc"
    unlisted = workspace / "libs" / "library.orc"
    same_basename = workspace / "other" / "main.orc"
    descendant = listed / "nested.orc"
    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=workspace.as_uri(),
            initialization_options={
                "entry_workflows": {
                    "apps/main.orc": "selected-exactly",
                }
            },
        )
    )
    ordered_paths = (
        (listed, unlisted)
        if listed_first
        else (unlisted, listed)
    )

    requests = tuple(driver._build_request(path) for path in ordered_paths)

    assert {
        request.source_path: request.entry_workflow
        for request in requests
    } == {
        listed: "selected-exactly",
        unlisted: None,
    }
    assert driver._build_request(same_basename).entry_workflow is None
    assert driver._build_request(descendant).entry_workflow is None


def test_each_eligible_generation_runs_one_full_shared_stage3_without_cache_or_provisional_phase(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The accepted 1.87-second observation is evidence, not a timing gate."""

    workspace = tmp_path / "workspace"
    entry_path = workspace / "std" / "context.orc"
    entry_path.parent.mkdir(parents=True)
    shutil.copyfile(
        Path(compiler.__file__).parent / "stdlib_modules" / "std" / "context.orc",
        entry_path,
    )
    build_requests: list[build.FrontendBuildRequest] = []
    stage3_calls: list[dict[str, object]] = []
    compile_stage3 = build.compile_stage3_entrypoint

    def observe_full_stage3(
        path: Path,
        **kwargs: object,
    ) -> object:
        stage3_calls.append({"path": path.resolve(), **kwargs})
        return compile_stage3(path, **kwargs)

    def one_real_build_per_generation(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> build.FrontendInMemoryBuildResult:
        build_requests.append(request)
        return build.build_frontend_bundle_in_memory(
            request,
            source_read_trace=source_read_trace,
        )

    monkeypatch.setattr(build, "compile_stage3_entrypoint", observe_full_stage3)
    monkeypatch.setattr(
        compiler,
        "compile_stage1_entrypoint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Stage 1 must not be called")
        ),
    )
    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=workspace.as_uri(),
            initialization_options={"source_roots": (workspace,)},
        ),
        build_in_memory=one_real_build_per_generation,
    )
    text = entry_path.read_text(encoding="utf-8")
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    opened = driver.drain()
    first_compile_result = (
        driver.state.entries[0].accepted_snapshot.build_value.compile_result
    )
    driver.apply_transition(
        lsp_state.save_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    saved = driver.drain()
    second_compile_result = (
        driver.state.entries[0].accepted_snapshot.build_value.compile_result
    )

    assert len(opened) == len(saved) == 1
    assert [request.entry_workflow for request in build_requests] == [None, None]
    assert len(stage3_calls) == 2
    assert {
        (
            call["path"],
            call["entry_workflow"],
            call["validation_profile"],
        )
        for call in stage3_calls
    } == {
        (
            entry_path.resolve(),
            None,
            compiler.Stage3ValidationProfile.SHARED_CALLABLE,
        )
    }
    assert all("validate_shared" not in call for call in stage3_calls)
    assert first_compile_result is not second_compile_result
    assert (
        first_compile_result.validation_profile
        is second_compile_result.validation_profile
        is compiler.Stage3ValidationProfile.SHARED_CALLABLE
    )
    assert driver.state.entries[0].generation == 2
    assert driver.state.entries[0].compile_status == "success"


def test_success_translates_diagnostics_to_exact_target_contributions(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    target_path = workspace / "imported.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, target_path):
        path.write_text(text, encoding="utf-8")
    position = SourcePosition(
        path=target_path.as_posix(),
        line=1,
        column=1,
        offset=0,
    )
    diagnostic = LispFrontendDiagnostic(
        code="test_diagnostic",
        message="raw",
        span=SourceSpan(start=position, end=position),
    )

    def diagnostic_success(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        for path in (entry_path, target_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        return _injected_success((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=diagnostic_success,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    entry = driver.state.entries[0]
    assert tuple(item.code for item in entry.diagnostic_contributions) == (
        diagnostic.code,
    )
    assert tuple(item.target_uri for item in entry.diagnostic_contributions) == (
        target_path.resolve().as_uri(),
    )


def test_completed_outer_graph_language_error_translates_precise_contribution(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    dependency_path = workspace / "dependency.orc"
    guidance_path = workspace / "guidance.md"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, dependency_path):
        path.write_text(text, encoding="utf-8")
    guidance_path.write_text("guidance\n", encoding="utf-8")
    position = SourcePosition(
        path=dependency_path.as_posix(),
        line=1,
        column=1,
        offset=0,
    )
    diagnostic = LispFrontendDiagnostic(
        code="expected_language_error",
        message="broken dependency",
        span=SourceSpan(start=position, end=position),
    )
    calls: list[SourceReadTrace] = []

    def raise_language_error(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        calls.append(source_read_trace)
        attempt_id = source_read_trace._begin_module_graph_read_attempt(entry_path)
        for path in (entry_path, dependency_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        source_read_trace._complete_module_graph_read_attempt(
            attempt_id,
            module_paths=(entry_path.resolve(), dependency_path.resolve()),
        )
        source_read_trace._record(
            canonical_path=guidance_path.resolve(),
            revision=compile_driver.probe_disk_source(guidance_path).revision,
        )
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=raise_language_error,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    assert len(calls) == 1
    entry = driver.state.entries[0]
    assert entry.compile_status == "language_error"
    assert entry.pending_generation is None
    assert entry.accepted_snapshot is None
    assert entry.dependency_closure == frozenset(
        {
            entry_path.resolve(),
            dependency_path.resolve(),
            guidance_path.resolve(),
        }
    )
    assert entry.dependency_revision_vector == calls[0].revision_vector
    assert tuple(item.code for item in entry.diagnostic_contributions) == (
        diagnostic.code,
    )
    assert tuple(item.target_uri for item in entry.diagnostic_contributions) == (
        dependency_path.resolve().as_uri(),
    )


@pytest.mark.parametrize(
    "outcome",
    ("real_success", "injected_success", "language_error"),
)
def test_driver_translates_raw_diagnostics_with_exact_text_and_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    outcome: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    if outcome == "real_success":
        entry_path = workspace / "lint_warning_variant_output.orc"
        shutil.copyfile(
            CLI_FIXTURES.parent / "valid" / entry_path.name,
            entry_path,
        )
        text = entry_path.read_text(encoding="utf-8")
        (workspace / "prompt.md").write_text("prompt\n", encoding="utf-8")
        providers = workspace / "providers.json"
        prompts = workspace / "prompts.json"
        providers.write_text(
            '{"providers.execute":"test-provider"}\n',
            encoding="utf-8",
        )
        prompts.write_text(
            '{"prompts.implementation.execute":"prompt.md"}\n',
            encoding="utf-8",
        )
        initial = lsp_state.initialize_lsp_state(
            root_uri=workspace.as_uri(),
            initialization_options={
                "source_roots": (workspace,),
                "entry_workflows": {str(entry_path): "orchestrate"},
                "provider_externs_path": providers,
                "prompt_externs_path": prompts,
            },
        )
        driver = compile_driver.initialize_compile_driver(initial)
        raw_diagnostics: tuple[LispFrontendDiagnostic, ...] | None = None
    else:
        entry_path = workspace / "entry.orc"
        text = "a😀bc\n"
        entry_path.write_text(text, encoding="utf-8")
        diagnostic = LispFrontendDiagnostic(
            code=f"{outcome}_diagnostic",
            message="raw compiler diagnostic",
            span=SourceSpan(
                start=SourcePosition(
                    path=entry_path.as_posix(),
                    line=1,
                    column=2,
                    offset=1,
                ),
                end=SourcePosition(
                    path=entry_path.as_posix(),
                    line=1,
                    column=4,
                    offset=3,
                ),
            ),
        )
        raw_diagnostics = (diagnostic,)

        def injected_build(
            request: build.FrontendBuildRequest,
            *,
            source_read_trace: SourceReadTrace,
        ) -> object:
            attempt = source_read_trace._begin_module_graph_read_attempt(
                entry_path
            )
            source_read_trace._record(
                canonical_path=entry_path.resolve(),
                revision=compile_driver.probe_disk_source(entry_path).revision,
            )
            source_read_trace._complete_module_graph_read_attempt(
                attempt,
                module_paths=(entry_path.resolve(),),
            )
            if outcome == "language_error":
                raise _injected_language_error(raw_diagnostics)
            return _injected_success(raw_diagnostics)

        driver = compile_driver.initialize_compile_driver(
            lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
            build_in_memory=injected_build,
        )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.apply_transition(
        lsp_state.save_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    entry_reads: list[Path] = []
    original_read_bytes = Path.read_bytes

    def counting_read_bytes(path: Path) -> bytes:
        if path.resolve(strict=False) == entry_path.resolve():
            entry_reads.append(path.resolve(strict=False))
        return original_read_bytes(path)

    if outcome != "real_success":
        monkeypatch.setattr(Path, "read_bytes", counting_read_bytes)

    driver.run_next()

    entry = driver.state.entries[0]
    if raw_diagnostics is None:
        assert entry.accepted_snapshot is not None
        raw_diagnostics = tuple(entry.accepted_snapshot.build_value.diagnostics)
        assert tuple(item.code for item in raw_diagnostics) == (
            "variant_output_without_variant_specific_fields",
        )
    expected = _translate_contributions(
        raw_diagnostics,
        compile_entry_uri=entry_path.as_uri(),
        accepted_generation=2,
        accepted_text_by_path={entry_path.resolve(): text},
    )
    assert entry.diagnostic_contributions == expected
    assert tuple(
        contribution.accepted_generation
        for contribution in entry.diagnostic_contributions
    ) == (2,)
    assert all(
        not isinstance(contribution, LispFrontendDiagnostic)
        for contribution in entry.diagnostic_contributions
    )
    if outcome != "real_success":
        assert entry_reads == [entry_path.resolve(), entry_path.resolve()]
        assert entry.diagnostic_contributions[0].range == {
            "start": {"line": 0, "character": 1},
            "end": {"line": 0, "character": 4},
        }
    assert not hasattr(entry, "diagnostics")
    assert not hasattr(entry, "diagnostic_target_uris")
    assert not hasattr(entry, "contribution_keys")


@pytest.mark.parametrize(
    "attempt_shape",
    (
        "absent",
        "outer_incomplete",
        "child_only",
        "incomplete_child_completed_outer",
        "ambiguous_outer",
        "entry_missing",
        "sentinel_revision",
        "module_member_missing",
    ),
)
def test_language_error_trace_completeness_fails_closed_to_unknown_state(
    tmp_path: Path,
    attempt_shape: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    child_path = workspace / "child.orc"
    missing_path = workspace / "missing.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, child_path):
        path.write_text(text, encoding="utf-8")
    position = SourcePosition(
        path=entry_path.as_posix(),
        line=1,
        column=1,
        offset=0,
    )
    diagnostic = LispFrontendDiagnostic(
        code="expected_language_error",
        message="incomplete graph",
        span=SourceSpan(start=position, end=position),
    )

    def raise_with_attempt_shape(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        if attempt_shape == "child_only":
            child = source_read_trace._begin_module_graph_read_attempt(child_path)
            source_read_trace._record(
                canonical_path=child_path.resolve(),
                revision=compile_driver.probe_disk_source(child_path).revision,
            )
            source_read_trace._complete_module_graph_read_attempt(
                child,
                module_paths=(child_path.resolve(),),
            )
            raise _injected_language_error((diagnostic,))

        outer = None
        if attempt_shape != "absent":
            outer = source_read_trace._begin_module_graph_read_attempt(entry_path)
        if attempt_shape != "entry_missing":
            source_read_trace._record(
                canonical_path=entry_path.resolve(),
                revision=compile_driver.probe_disk_source(entry_path).revision,
            )
        if attempt_shape == "absent":
            pass
        elif attempt_shape == "outer_incomplete":
            pass
        elif attempt_shape == "incomplete_child_completed_outer":
            assert outer is not None
            source_read_trace._begin_module_graph_read_attempt(child_path)
            source_read_trace._record(
                canonical_path=child_path.resolve(),
                revision=compile_driver.probe_disk_source(child_path).revision,
            )
            source_read_trace._complete_module_graph_read_attempt(
                outer,
                module_paths=(entry_path.resolve(), child_path.resolve()),
            )
        elif attempt_shape == "ambiguous_outer":
            assert outer is not None
            second_outer = source_read_trace._begin_module_graph_read_attempt(
                entry_path
            )
            source_read_trace._complete_module_graph_read_attempt(
                outer,
                module_paths=(entry_path.resolve(),),
            )
            source_read_trace._complete_module_graph_read_attempt(
                second_outer,
                module_paths=(entry_path.resolve(),),
            )
        elif attempt_shape == "entry_missing":
            assert outer is not None
            source_read_trace._complete_module_graph_read_attempt(
                outer,
                module_paths=(entry_path.resolve(),),
            )
        elif attempt_shape == "sentinel_revision":
            assert outer is not None
            source_read_trace._record(
                canonical_path=missing_path.resolve(),
                revision="missing",
            )
            source_read_trace._complete_module_graph_read_attempt(
                outer,
                module_paths=(entry_path.resolve(), missing_path.resolve()),
            )
        elif attempt_shape == "module_member_missing":
            assert outer is not None
            source_read_trace._record(
                canonical_path=child_path.resolve(),
                revision=compile_driver.probe_disk_source(child_path).revision,
            )
            source_read_trace._complete_module_graph_read_attempt(
                outer,
                module_paths=(
                    entry_path.resolve(),
                    missing_path.resolve(),
                ),
            )
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=raise_with_attempt_shape,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    entry = driver.state.entries[0]
    assert entry.compile_status == "language_error"
    assert entry.dependency_closure is None
    assert entry.dependency_revision_vector is None
    assert tuple(item.code for item in entry.diagnostic_contributions) == (
        diagnostic.code,
    )


def test_language_error_complete_child_and_outer_attempts_remain_precise(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    child_path = workspace / "child.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, child_path):
        path.write_text(text, encoding="utf-8")
    diagnostic = LispFrontendDiagnostic(
        code="expected_language_error",
        message="complete nested graph",
        span=SourceSpan(
            start=SourcePosition(
                path=child_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
            end=SourcePosition(
                path=child_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
        ),
    )
    traces: list[SourceReadTrace] = []

    def raise_with_complete_attempts(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        traces.append(source_read_trace)
        outer = source_read_trace._begin_module_graph_read_attempt(entry_path)
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        child = source_read_trace._begin_module_graph_read_attempt(child_path)
        source_read_trace._record(
            canonical_path=child_path.resolve(),
            revision=compile_driver.probe_disk_source(child_path).revision,
        )
        source_read_trace._complete_module_graph_read_attempt(
            child,
            module_paths=(child_path.resolve(),),
        )
        source_read_trace._complete_module_graph_read_attempt(
            outer,
            module_paths=(entry_path.resolve(), child_path.resolve()),
        )
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=raise_with_complete_attempts,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    entry = driver.state.entries[0]
    assert entry.compile_status == "language_error"
    assert entry.dependency_closure == frozenset(
        {entry_path.resolve(), child_path.resolve()}
    )
    assert entry.dependency_revision_vector == traces[0].revision_vector


def test_precise_language_error_revision_vector_drives_reverse_relevance(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    dependency_path = workspace / "dependency.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, dependency_path):
        path.write_text(text, encoding="utf-8")
    diagnostic = LispFrontendDiagnostic(
        code="expected_language_error",
        message="broken dependency",
        span=SourceSpan(
            start=SourcePosition(
                path=dependency_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
            end=SourcePosition(
                path=dependency_path.as_posix(),
                line=1,
                column=1,
                offset=0,
            ),
        ),
    )

    def raise_precise_language_error(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        outer = source_read_trace._begin_module_graph_read_attempt(entry_path)
        for path in (entry_path, dependency_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        source_read_trace._complete_module_graph_read_attempt(
            outer,
            module_paths=(entry_path.resolve(), dependency_path.resolve()),
        )
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=raise_precise_language_error,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.run_next()
    precise_state = driver.state

    unchanged = driver.observe_disk_path(dependency_path)

    assert unchanged.state is precise_state
    assert unchanged.effects == lsp_state.StateEffects()
    assert driver.queued_generations == ()

    dependency_path.write_text(text + "\n", encoding="utf-8")
    changed = driver.observe_disk_path(dependency_path)

    assert changed.state is driver.state
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation == 2
    assert entry.compile_status == "pending"
    assert driver.queued_generations == ((entry_path.resolve(), 2),)


def test_server_failure_preserves_contribution_logs_and_continues_queue(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    first_path = workspace / "first.orc"
    second_path = workspace / "second.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (first_path, second_path):
        path.write_text(text, encoding="utf-8")
    initial = lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    opened = lsp_state.open_entry(
        initial,
        document_uri=first_path.as_uri(),
        editor_text=text,
        disk_snapshot=compile_driver.probe_disk_source(first_path),
    )
    position = SourcePosition(
        path=first_path.as_posix(),
        line=1,
        column=1,
        offset=0,
    )
    prior_diagnostic = LispFrontendDiagnostic(
        code="prior",
        message="prior",
        span=SourceSpan(start=position, end=position),
    )
    prior_contributions = _translate_contributions(
        (prior_diagnostic,),
        compile_entry_uri=first_path.as_uri(),
        accepted_generation=1,
        accepted_text_by_path={first_path.resolve(): text},
    )
    accepted = lsp_state.accept_compile_success(
        opened.state,
        document_uri=first_path.as_uri(),
        generation=1,
        snapshot=lsp_state.AcceptedCompileSnapshot(
            build_value="prior",
            source_revision_vector=(
                compile_driver.probe_raw_revision(first_path),
            ),
        ),
        dependency_closure=frozenset({first_path.resolve()}),
        diagnostic_contributions=prior_contributions,
    )
    logged: list[Exception] = []
    calls: list[Path] = []

    def fail_first_then_succeed(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        calls.append(request.source_path)
        if request.source_path == first_path.resolve():
            raise RuntimeError("server boom")
        source_read_trace._record(
            canonical_path=second_path.resolve(),
            revision=compile_driver.probe_disk_source(second_path).revision,
        )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        accepted.state,
        build_in_memory=fail_first_then_succeed,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.save_entry(
            driver.state,
            document_uri=first_path.as_uri(),
            disk_snapshot=compile_driver.probe_disk_source(first_path),
        )
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=second_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(second_path),
        )
    )

    transitions = driver.drain()

    assert len(transitions) == 2
    assert calls == [first_path.resolve(), second_path.resolve()]
    assert len(logged) == 1
    assert str(logged[0]) == "server boom"
    first = next(entry for entry in driver.state.entries if entry.path == first_path)
    second = next(entry for entry in driver.state.entries if entry.path == second_path)
    assert first.compile_status == "server_error"
    assert first.accepted_snapshot is None
    assert first.dependency_closure is None
    assert first.diagnostic_contributions is prior_contributions
    assert second.compile_status == "success"


def test_repeated_read_mismatch_reproves_and_reschedules_clean_entry(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    dependency_path = workspace / "dependency.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, dependency_path):
        path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []

    def fail_on_repeated_dependency_read(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        source_read_trace._record(
            canonical_path=dependency_path.resolve(),
            revision=compile_driver.probe_disk_source(dependency_path).revision,
        )
        dependency_path.write_text(text + "\n", encoding="utf-8")
        source_read_trace._record(
            canonical_path=dependency_path.resolve(),
            revision=compile_driver.probe_disk_source(dependency_path).revision,
        )
        raise AssertionError("repeated-read mismatch must raise first")

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=fail_on_repeated_dependency_read,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation == 2
    assert entry.buffer_status == "clean"
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert entry.diagnostic_contributions == ()
    assert driver.queued_generations == ((entry_path.resolve(), 2),)
    assert len(logged) == 1
    assert "changed during one compiler read trace" in str(logged[0])


def test_repeated_read_conflict_reschedules_after_dependency_bytes_revert(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    dependency_path = workspace / "dependency.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    changed_text = text + "\n"
    for path in (entry_path, dependency_path):
        path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []

    def fail_then_revert_dependency(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        for path in (entry_path, dependency_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        dependency_path.write_text(changed_text, encoding="utf-8")
        try:
            source_read_trace._record(
                canonical_path=dependency_path.resolve(),
                revision=compile_driver.probe_disk_source(
                    dependency_path
                ).revision,
            )
        finally:
            dependency_path.write_text(text, encoding="utf-8")
        raise AssertionError("repeated-read conflict must raise first")

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=fail_then_revert_dependency,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation == 2
    assert entry.buffer_status == "clean"
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert driver.queued_generations == ((entry_path.resolve(), 2),)
    assert dependency_path.read_text(encoding="utf-8") == text
    assert len(logged) == 1
    assert "changed during one compiler read trace" in str(logged[0])


@pytest.mark.parametrize("outcome", ("success", "language_error"))
def test_caught_read_conflict_reproves_before_accepting_terminal_outcome(
    tmp_path: Path,
    outcome: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    dependency_path = workspace / "dependency.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    changed_text = text + "\n"
    for path in (entry_path, dependency_path):
        path.write_text(text, encoding="utf-8")
    position = SourcePosition(
        path=entry_path.as_posix(),
        line=1,
        column=1,
        offset=0,
    )
    diagnostic = LispFrontendDiagnostic(
        code="must_not_publish_after_caught_conflict",
        message="caught read conflict requires reproof",
        span=SourceSpan(start=position, end=position),
    )
    logged: list[Exception] = []

    def catch_conflict_then_return_terminal_outcome(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        for path in (entry_path, dependency_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        dependency_path.write_text(changed_text, encoding="utf-8")
        try:
            with pytest.raises(
                RuntimeError,
                match="changed during one compiler read trace",
            ):
                source_read_trace._record(
                    canonical_path=dependency_path.resolve(),
                    revision=compile_driver.probe_disk_source(
                        dependency_path
                    ).revision,
                )
        finally:
            dependency_path.write_text(text, encoding="utf-8")
        if outcome == "success":
            return _injected_success((diagnostic,))
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=catch_conflict_then_return_terminal_outcome,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.pending_generation == 2
    assert entry.buffer_status == "clean"
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert entry.diagnostic_contributions == ()
    assert driver.queued_generations == ((entry_path.resolve(), 2),)
    assert dependency_path.read_text(encoding="utf-8") == text
    assert logged == []


def test_generic_exception_with_unchanged_internal_trace_remains_server_error(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []

    def fail_after_current_read(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        raise RuntimeError("unchanged generic failure")

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=fail_after_current_read,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.compile_status == "server_error"
    assert entry.pending_generation is None
    assert entry.accepted_snapshot is None
    assert driver.queued_generations == ()
    assert tuple(str(error) for error in logged) == (
        "unchanged generic failure",
    )


@pytest.mark.parametrize(
    ("evidence_kind", "expected_stale"),
    (
        ("exact", False),
        ("mismatched_vector", True),
        ("conflict", True),
    ),
)
def test_generic_exception_uses_only_exact_structural_configuration_evidence(
    tmp_path: Path,
    evidence_kind: str,
    expected_stale: bool,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, _configured_paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    holder: dict[str, compile_driver.LspCompileDriver] = {}
    logged: list[Exception] = []

    def raise_with_structural_evidence(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        vector = holder["driver"].state.configuration_vector
        assert vector is not None
        expected = vector.configuration_revisions
        assert expected
        error = RuntimeError(f"generic {evidence_kind} evidence")
        if evidence_kind == "mismatched_vector":
            error.configuration_revision_vector = expected[:-1]
            error.configuration_revision_conflict_paths = ()
        elif evidence_kind == "conflict":
            error.configuration_revision_vector = expected
            error.configuration_revision_conflict_paths = (expected[0][0],)
        else:
            error.configuration_revision_vector = expected
            error.configuration_revision_conflict_paths = ()
        raise error

    driver = compile_driver.initialize_compile_driver(
        initial,
        build_in_memory=raise_with_structural_evidence,
        log_server_error=logged.append,
    )
    holder["driver"] = driver
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    assert driver.state.configuration_stale is expected_stale
    assert len(logged) == 1
    assert str(logged[0]) == f"generic {evidence_kind} evidence"
    if expected_stale:
        assert transition.effects.restart_notice_required is True
        assert driver.state.entries == ()
        assert driver.queued_generations == ()
    else:
        entry = driver.state.entries[0]
        assert entry.compile_status == "server_error"
        assert entry.pending_generation is None
        assert entry.accepted_snapshot is None
        assert transition.effects.restart_notice_required is False


def test_real_recursive_configuration_aba_generic_error_latches_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    source_root = workspace / "src"
    config_root = workspace / "config"
    shutil.copytree(
        CLI_FIXTURES.parent
        / "modules"
        / "valid"
        / "imported_bundle_mix",
        source_root,
    )
    config_root.mkdir()
    for name in (
        "providers.json",
        "prompts.json",
        "commands.json",
        "imported_selector.orc",
        "imported_workflow_bundles.json",
    ):
        shutil.copyfile(CLI_FIXTURES / name, config_root / name)
    provider_path = (config_root / "providers.json").resolve()
    revision_a = provider_path.read_bytes()
    revision_b = b'{"providers.execute":"provider-b"}\n'
    entry_path = (source_root / "neurips" / "entry.orc").resolve()
    initial = lsp_state.initialize_lsp_state(
        root_uri=workspace.as_uri(),
        initialization_options={
            "source_roots": (source_root,),
            "entry_workflows": {str(entry_path): "orchestrate"},
            "provider_externs_path": provider_path,
            "prompt_externs_path": config_root / "prompts.json",
            "command_boundaries_path": config_root / "commands.json",
            "imported_workflow_bundles_path": (
                config_root / "imported_workflow_bundles.json"
            ),
        },
    )
    logged: list[Exception] = []
    driver = compile_driver.initialize_compile_driver(
        initial,
        log_server_error=logged.append,
    )
    vector = driver.state.configuration_vector
    assert vector is not None
    expected_vector = vector.configuration_revisions
    text = entry_path.read_text(encoding="utf-8")
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    read_bytes = Path.read_bytes
    provider_reads = 0

    def return_b_on_recursive_attempt_read(path: Path) -> bytes:
        nonlocal provider_reads
        if path.resolve(strict=False) != provider_path:
            return read_bytes(path)
        provider_reads += 1
        if provider_reads == 3:
            provider_path.write_bytes(revision_b)
            try:
                return revision_b
            finally:
                provider_path.write_bytes(revision_a)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", return_b_on_recursive_attempt_read)

    transition = driver.run_next()

    assert transition is not None
    assert provider_reads == 4
    assert read_bytes(provider_path) == revision_a
    assert driver.state.configuration_stale is True
    assert transition.effects.restart_notice_required is True
    assert driver.state.entries == ()
    assert driver.queued_generations == ()
    assert len(logged) == 1
    assert logged[0].configuration_revision_vector == expected_vector
    assert logged[0].configuration_revision_conflict_paths == (provider_path,)


def test_generic_exception_external_trace_logs_once_and_remains_server_error(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    external_path = tmp_path / "external.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, external_path):
        path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []

    def fail_after_external_read(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=external_path.resolve(),
            revision=compile_driver.probe_disk_source(external_path).revision,
        )
        raise RuntimeError("generic external failure")

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=fail_after_external_read,
        log_server_error=logged.append,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    transition = driver.run_next()

    assert transition is not None
    entry = driver.state.entries[0]
    assert entry.compile_status == "server_error"
    assert entry.pending_generation is None
    assert entry.accepted_snapshot is None
    assert driver.queued_generations == ()
    assert tuple(str(error) for error in logged) == (
        "generic external failure",
    )


@pytest.mark.parametrize("late_kind", ("dirty", "closed", "configuration_stale"))
def test_late_or_configuration_stale_language_errors_are_discarded(
    tmp_path: Path,
    late_kind: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    if late_kind == "configuration_stale":
        initial, configured_paths = _configured_initial_state(workspace)
    else:
        initial = lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
        configured_paths = {}
    position = SourcePosition(
        path=entry_path.as_posix(),
        line=1,
        column=1,
        offset=0,
    )
    diagnostic = LispFrontendDiagnostic(
        code="late_language_error",
        message="discard",
        span=SourceSpan(start=position, end=position),
    )
    holder: dict[str, compile_driver.LspCompileDriver] = {}

    def fail_after_state_moves(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        driver = holder["driver"]
        if late_kind == "dirty":
            driver.apply_transition(
                lsp_state.change_entry(
                    driver.state,
                    document_uri=entry_path.as_uri(),
                    editor_text=text + " ",
                )
            )
        elif late_kind == "closed":
            driver.apply_transition(
                lsp_state.close_entry(
                    driver.state,
                    document_uri=entry_path.as_uri(),
                )
            )
        else:
            configured_paths["provider_externs_path"].write_text(
                '{"providers.execute":"changed"}\n',
                encoding="utf-8",
            )
        raise _injected_language_error((diagnostic,))

    driver = compile_driver.initialize_compile_driver(
        initial,
        build_in_memory=fail_after_state_moves,
    )
    holder["driver"] = driver
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    if late_kind == "closed":
        assert driver.state.entries == ()
    elif late_kind == "configuration_stale":
        assert driver.state.configuration_stale is True
        assert driver.state.entries == ()
    else:
        entry = driver.state.entries[0]
        assert entry.buffer_status == "dirty"
        assert entry.diagnostic_contributions == ()


def test_late_server_failure_logs_but_does_not_synthesize_or_accept(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    logged: list[Exception] = []
    holder: dict[str, compile_driver.LspCompileDriver] = {}

    def fail_after_dirty(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        driver = holder["driver"]
        driver.apply_transition(
            lsp_state.change_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
                editor_text=text + " ",
            )
        )
        raise RuntimeError("late server error")

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=fail_after_dirty,
        log_server_error=logged.append,
    )
    holder["driver"] = driver
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )

    driver.run_next()

    entry = driver.state.entries[0]
    assert entry.buffer_status == "dirty"
    assert entry.compile_status == "idle"
    assert entry.diagnostic_contributions == ()
    assert tuple(str(error) for error in logged) == ("late server error",)


def test_snapshot_if_current_returns_only_live_clean_success(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    result = _injected_success()

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        return result

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=successful_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    expected = driver.state.entries[0].accepted_snapshot

    snapshot = driver.snapshot_if_current(entry_path.as_uri())

    assert snapshot is expected


@pytest.mark.parametrize(
    ("buffer_status", "compile_status"),
    (
        ("clean", "pending"),
        ("dirty", "idle"),
        ("clean", "language_error"),
        ("clean", "server_error"),
    ),
)
def test_snapshot_if_current_returns_none_for_non_success_state(
    tmp_path: Path,
    buffer_status: str,
    compile_status: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    entry_path.write_text("(workflow-lisp)\n", encoding="utf-8")
    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    )
    opened = lsp_state.open_entry(
        driver.state,
        document_uri=entry_path.as_uri(),
        editor_text="(workflow-lisp)\n",
        disk_snapshot=compile_driver.probe_disk_source(entry_path),
    )
    entry = replace(
        opened.state.entries[0],
        buffer_status=buffer_status,
        compile_status=compile_status,
        accepted_snapshot=None,
    )
    driver.state = replace(opened.state, entries=(entry,))

    assert driver.snapshot_if_current(entry_path.as_uri()) is None

    driver.state = lsp_state.close_entry(
        opened.state,
        document_uri=entry_path.as_uri(),
    ).state
    assert driver.snapshot_if_current(entry_path.as_uri()) is None


def test_snapshot_if_current_observes_source_drift_without_notification(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    dependency_path = workspace / "dependency.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, dependency_path):
        path.write_text(text, encoding="utf-8")

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        for path in (entry_path, dependency_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=successful_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    dependency_path.write_text(text + "\n", encoding="utf-8")

    snapshot = driver.snapshot_if_current(entry_path.as_uri())

    assert snapshot is None
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert driver.queued_generations == ((entry_path.resolve(), 2),)


def test_snapshot_if_current_latches_config_drift_without_notification(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    holder: dict[str, compile_driver.LspCompileDriver] = {}

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        source_read_trace._record(
            canonical_path=entry_path.resolve(),
            revision=compile_driver.probe_disk_source(entry_path).revision,
        )
        vector = holder["driver"].state.configuration_vector
        assert vector is not None
        return _injected_success(
            configuration_revision_vector=vector.configuration_revisions,
        )

    driver = compile_driver.initialize_compile_driver(
        initial,
        build_in_memory=successful_build,
    )
    holder["driver"] = driver
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    paths["command_boundaries_path"].write_text(
        '{"run":{"kind":"external_tool","stable_command":["changed"]}}\n',
        encoding="utf-8",
    )

    snapshot = driver.snapshot_if_current(entry_path.as_uri())

    assert snapshot is None
    assert driver.state.configuration_stale is True
    assert driver.state.entries == ()


def test_snapshot_if_current_fails_closed_on_external_trace_member(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    external_path = tmp_path / "external.orc"
    text = "(workflow-lisp)\n"
    for path in (entry_path, external_path):
        path.write_text(text, encoding="utf-8")
    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri())
    )
    opened = lsp_state.open_entry(
        driver.state,
        document_uri=entry_path.as_uri(),
        editor_text=text,
        disk_snapshot=compile_driver.probe_disk_source(entry_path),
    )
    snapshot = lsp_state.AcceptedCompileSnapshot(
        build_value="invalid",
        source_revision_vector=(
            compile_driver.probe_raw_revision(entry_path),
            compile_driver.probe_raw_revision(external_path),
        ),
    )
    accepted = lsp_state.accept_compile_success(
        opened.state,
        document_uri=entry_path.as_uri(),
        generation=1,
        snapshot=snapshot,
        dependency_closure=frozenset({entry_path.resolve(), external_path.resolve()}),
        diagnostic_contributions=(),
    )
    driver.state = accepted.state

    assert driver.snapshot_if_current(entry_path.as_uri()) is None


@pytest.mark.parametrize(
    "candidate_state",
    ("pending", "dirty", "language_error", "server_error", "closed"),
)
def test_snapshot_rechecks_configuration_before_non_candidate_return(
    tmp_path: Path,
    candidate_state: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    driver = compile_driver.initialize_compile_driver(initial)
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    if candidate_state == "dirty":
        driver.apply_transition(
            lsp_state.change_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
                editor_text=text + " ",
            )
        )
    elif candidate_state in {"language_error", "server_error"}:
        entry = replace(
            driver.state.entries[0],
            pending_generation=None,
            compile_status=candidate_state,
        )
        driver.state = replace(driver.state, entries=(entry,))
    elif candidate_state == "closed":
        driver.apply_transition(
            lsp_state.close_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
            )
        )
    paths["command_boundaries_path"].write_bytes(
        paths["command_boundaries_path"].read_bytes() + b"\n"
    )

    snapshot = driver.snapshot_if_current(entry_path.as_uri())

    assert snapshot is None
    assert driver.state.configuration_stale is True
    assert driver.state.entries == ()


def test_snapshot_configuration_drift_requests_restart_notice_once_without_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    driver = compile_driver.initialize_compile_driver(initial)
    paths["provider_externs_path"].write_bytes(
        paths["provider_externs_path"].read_bytes() + b"\n"
    )
    restart_notices: list[bool] = []
    recheck_configuration = compile_driver.LspCompileDriver.recheck_configuration

    def record_recheck(
        current: compile_driver.LspCompileDriver,
    ) -> lsp_state.LspStateTransition:
        transition = recheck_configuration(current)
        restart_notices.append(transition.effects.restart_notice_required)
        return transition

    monkeypatch.setattr(
        compile_driver.LspCompileDriver,
        "recheck_configuration",
        record_recheck,
    )

    assert driver.snapshot_if_current(entry_path.as_uri()) is None
    assert driver.snapshot_if_current(entry_path.as_uri()) is None

    assert restart_notices == [True, False]
    assert driver.state.configuration_stale is True


def test_snapshot_logs_configuration_recheck_exception_without_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    logged: list[Exception] = []
    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        log_server_error=logged.append,
    )

    def fail_builtin_root_probe() -> Path:
        raise RuntimeError("snapshot configuration recheck failed")

    monkeypatch.setattr(
        compile_driver.compiler,
        "_builtin_stdlib_source_root",
        fail_builtin_root_probe,
    )

    snapshot = driver.snapshot_if_current(entry_path.as_uri())

    assert snapshot is None
    assert tuple(str(error) for error in logged) == (
        "snapshot configuration recheck failed",
    )


def test_observe_disk_path_probes_source_once_and_applies_invalidation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    entry_path = workspace / "entry.orc"
    dependency_path = workspace / "dependency.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    for path in (entry_path, dependency_path):
        path.write_text(text, encoding="utf-8")

    def successful_build(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        for path in (entry_path, dependency_path):
            source_read_trace._record(
                canonical_path=path.resolve(),
                revision=compile_driver.probe_disk_source(path).revision,
            )
        return _injected_success()

    driver = compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(root_uri=workspace.as_uri()),
        build_in_memory=successful_build,
    )
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    dependency_path.write_text(text + "\n", encoding="utf-8")
    calls: list[Path] = []
    read_bytes = Path.read_bytes

    def observe_read(path: Path) -> bytes:
        calls.append(path.resolve(strict=False))
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", observe_read)

    transition = driver.observe_disk_path(dependency_path)

    assert transition is not None
    assert calls == [dependency_path.resolve()]
    entry = driver.state.entries[0]
    assert entry.generation == 2
    assert entry.compile_status == "pending"
    assert entry.accepted_snapshot is None
    assert driver.queued_generations == ((entry_path.resolve(), 2),)


@pytest.mark.parametrize(
    "configuration_member",
    ("command_boundaries_path", "recursively_imported_source"),
)
def test_observe_disk_path_routes_frozen_member_to_configuration_latch(
    tmp_path: Path,
    configuration_member: str,
) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    initial, paths = _configured_initial_state(workspace)
    entry_path = workspace / "entry.orc"
    text = "(workflow-lisp (:language \"0.1\") (:target-dsl \"2.14\"))\n"
    entry_path.write_text(text, encoding="utf-8")
    driver = compile_driver.initialize_compile_driver(initial)
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=compile_driver.probe_disk_source(entry_path),
        )
    )
    changed_path = paths[configuration_member]
    changed_path.write_bytes(changed_path.read_bytes() + b"\n")

    transition = driver.observe_disk_path(changed_path)

    assert transition is not None
    assert driver.state.configuration_stale is True
    assert driver.state.entries == ()
    assert transition.effects.restart_notice_required is True
