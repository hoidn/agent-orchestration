"""Frame-clean pygls transport for the Workflow Lisp language server."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from pathlib import Path

from lsprotocol import types
from pygls.exceptions import JsonRpcInvalidParams
from pygls.lsp.server import LanguageServer

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError

from .compile_driver import (
    BuildInMemory,
    LspCompileDriver,
    PreparedCompile,
    initialize_compile_driver,
    probe_disk_source,
)
from .diagnostics import (
    DiagnosticContribution,
    aggregate_diagnostic_contributions,
)
from .coordinates import CoordinateTranslationError, source_span_to_lsp_range
from .navigation import (
    NavigationCompletion,
    NavigationIndex,
    build_navigation_index,
    completion_for_document,
    definition_at_lsp_position,
    symbols_for_document,
)
from .progress import (
    ProgressController,
    ProgressEffect,
    ProgressTransition,
    SettlementReason,
)
from .state import (
    AcceptedCompileSnapshot,
    LspInitializationError,
    LspStateTransition,
    canonicalize_workspace_roots,
    change_entry,
    classify_completion_recovery,
    close_entry,
    current_diagnostic_contributions,
    initialize_lsp_state,
    open_entry,
    save_observed_entry,
    transition_workspace_root_set,
)


_DOCUMENT_SYMBOL_KIND_BY_INTERNAL_KIND: dict[str, types.SymbolKind] = {
    "module": types.SymbolKind.Module,
    "procedure": types.SymbolKind.Function,
    "workflow": types.SymbolKind.Function,
    "enum": types.SymbolKind.Enum,
    "path": types.SymbolKind.Class,
    "record": types.SymbolKind.Struct,
    "union": types.SymbolKind.Enum,
    "schema": types.SymbolKind.Interface,
    "resource": types.SymbolKind.Object,
    "transition": types.SymbolKind.Event,
}

_COMPLETION_ITEM_KIND_BY_INTERNAL_KIND: dict[
    str,
    types.CompletionItemKind,
] = {
    "procedure": types.CompletionItemKind.Function,
    "workflow": types.CompletionItemKind.Function,
    "form": types.CompletionItemKind.Keyword,
}


class WorkflowLispLanguageServer(LanguageServer):
    """One stdio server process with one atomically initialized compile driver."""

    def __init__(
        self,
        *,
        build_in_memory: BuildInMemory | None = None,
        _defer_compiles: bool = False,
    ) -> None:
        super().__init__(
            "workflow-lisp",
            "0.1.0",
            text_document_sync_kind=types.TextDocumentSyncKind.Full,
        )
        self.driver: LspCompileDriver | None = None
        self._build_in_memory = build_in_memory
        self._defer_compiles = _defer_compiles
        self._compile_task: asyncio.Task[None] | None = None
        self._progress_create_tasks: set[asyncio.Task[None]] = set()
        self.progress_controller = ProgressController(supported=False)
        self.watcher_registration_supported = False
        self._watcher_registration_sent = False

    def initialize_runtime(self, params: types.InitializeParams) -> None:
        """Build the immutable runtime locally before exposing it to handlers."""

        try:
            state = initialize_lsp_state(
                root_uri=params.root_uri,
                workspace_folder_uris=tuple(
                    folder.uri for folder in params.workspace_folders or ()
                ),
                initialization_options=params.initialization_options,
            )
        except LspInitializationError as error:
            raise JsonRpcInvalidParams(
                message=str(error),
                data=error.data,
            ) from error
        try:
            if self._build_in_memory is None:
                driver = initialize_compile_driver(
                    state,
                    log_server_error=self.log_internal_error,
                )
            else:
                driver = initialize_compile_driver(
                    state,
                    build_in_memory=self._build_in_memory,
                    log_server_error=self.log_internal_error,
                )
        except LispFrontendCompileError as error:
            diagnostic_rows = [
                {
                    "code": diagnostic.code,
                    "path": _initialization_diagnostic_path(
                        diagnostic.span.start.path
                    ),
                }
                for diagnostic in error.diagnostics
            ]
            raise JsonRpcInvalidParams(
                message=(
                    "Workflow Lisp initialization failed "
                    f"({len(diagnostic_rows)} compiler diagnostics); see data"
                ),
                data={"diagnostics": diagnostic_rows},
            ) from error
        self.driver = driver
        window_capabilities = getattr(params.capabilities, "window", None)
        self.progress_controller = ProgressController(
            supported=(
                getattr(
                    window_capabilities,
                    "work_done_progress",
                    None,
                )
                is True
            )
        )
        watched_files = getattr(
            getattr(params.capabilities, "workspace", None),
            "did_change_watched_files",
            None,
        )
        self.watcher_registration_supported = bool(
            getattr(watched_files, "dynamic_registration", False)
        )

    def register_watcher_if_supported(self) -> None:
        """Register eager source and frozen-context watchers when supported."""

        if (
            not self.watcher_registration_supported
            or self._watcher_registration_sent
        ):
            return
        driver = self._require_driver()
        vector = driver.state.configuration_vector
        if vector is None:
            raise RuntimeError("compile driver state has no configuration vector")
        frozen_paths = tuple(
            sorted(
                {
                    path
                    for path, _revision in (
                        *vector.configuration_revisions,
                        *vector.recursively_imported_source_revisions,
                    )
                    if not (
                        path.suffix == ".orc"
                        and (
                            path == driver.state.workspace_root
                            or driver.state.workspace_root in path.parents
                        )
                    )
                },
                key=lambda path: path.as_posix(),
            )
        )
        watchers = (
            types.FileSystemWatcher(glob_pattern="**/*.orc"),
            *(
                types.FileSystemWatcher(
                    glob_pattern=types.RelativePattern(
                        base_uri=path.parent.as_uri(),
                        pattern=path.name,
                    )
                )
                for path in frozen_paths
            ),
        )
        self._watcher_registration_sent = True
        self.client_register_capability(
            types.RegistrationParams(
                registrations=(
                    types.Registration(
                        id="workflow-lisp-orc-watch-v1",
                        method=types.WORKSPACE_DID_CHANGE_WATCHED_FILES,
                        register_options=(
                            types.DidChangeWatchedFilesRegistrationOptions(
                                watchers=watchers
                            )
                        ),
                    ),
                )
            )
        )

    def open_document(self, params: types.DidOpenTextDocumentParams) -> None:
        """Adopt one opened disk-equal buffer and run its queued generation."""

        driver = self._require_driver()
        uri = params.text_document.uri
        transition = open_entry(
            driver.state,
            document_uri=uri,
            editor_text=params.text_document.text,
            disk_snapshot=probe_disk_source(_file_uri_path(uri)),
        )
        driver.apply_transition(transition)
        self._drain_and_publish(transition)

    def change_document(
        self,
        params: types.DidChangeTextDocumentParams,
    ) -> None:
        """Adopt the full in-memory overlay and publish visibility effects."""

        driver = self._require_driver()
        document = self.workspace.get_text_document(
            params.text_document.uri
        )
        transition = change_entry(
            driver.state,
            document_uri=params.text_document.uri,
            editor_text=document.source,
        )
        driver.apply_transition(transition)
        self._emit_transition_effects((transition,))

    def save_document(self, params: types.DidSaveTextDocumentParams) -> None:
        """Re-probe authoritative disk text and run any resulting generation."""

        driver = self._require_driver()
        uri = params.text_document.uri
        transition = save_observed_entry(
            driver.state,
            document_uri=uri,
            observed_snapshot=probe_disk_source(_file_uri_path(uri)),
        )
        driver.apply_transition(transition)
        self._drain_and_publish(transition)

    def observe_watched_files(
        self,
        params: types.DidChangeWatchedFilesParams,
    ) -> None:
        """Route delivered `.orc` changes through the existing disk observer."""

        driver = self._require_driver()
        vector = driver.state.configuration_vector
        if vector is None:
            raise RuntimeError("compile driver state has no configuration vector")
        frozen_paths = {
            frozen_path
            for frozen_path, _revision in (
                *vector.configuration_revisions,
                *vector.recursively_imported_source_revisions,
            )
        }
        transitions: list[LspStateTransition] = []
        for change in params.changes:
            path = _file_uri_path(change.uri)
            inside_workspace = (
                path == driver.state.workspace_root
                or driver.state.workspace_root in path.parents
            )
            if not (
                (path.suffix == ".orc" and inside_workspace)
                or path in frozen_paths
            ):
                continue
            transitions.append(driver.observe_disk_path(path))
        if self._defer_compiles:
            self._emit_transition_effects(transitions)
            self._schedule_compile_pump()
            return
        transitions.extend(driver.drain())
        self._emit_transition_effects(transitions)

    def change_workspace_folders(
        self,
        params: types.DidChangeWorkspaceFoldersParams,
    ) -> None:
        """Latch stale state when the client changes the immutable root set."""

        driver = self._require_driver()
        added = canonicalize_workspace_roots(
            root_uri=None,
            workspace_folder_uris=tuple(
                folder.uri for folder in params.event.added
            ),
        )
        removed = canonicalize_workspace_roots(
            root_uri=None,
            workspace_folder_uris=tuple(
                folder.uri for folder in params.event.removed
            ),
        )
        canonical_roots = (
            frozenset({driver.state.workspace_root}) - removed
        ) | added
        transition = transition_workspace_root_set(
            driver.state,
            canonical_roots=canonical_roots,
        )
        driver.apply_transition(transition)
        self._emit_transition_effects((transition,))

    def close_document(self, params: types.DidCloseTextDocumentParams) -> None:
        """Drop one entry and clear only diagnostic targets it formerly owned."""

        driver = self._require_driver()
        transition = close_entry(
            driver.state,
            document_uri=params.text_document.uri,
        )
        driver.apply_transition(transition)
        self._emit_transition_effects((transition,))

    def definition(
        self,
        params: types.DefinitionParams,
    ) -> types.Location | None:
        """Resolve only an exact compiler-authored direct call head."""

        uri = params.text_document.uri
        navigation = self._current_navigation(uri)
        if navigation is None:
            return None
        snapshot, index = navigation
        source_path = _file_uri_path(uri)
        target_span = definition_at_lsp_position(
            index,
            source_path=source_path,
            line=params.position.line,
            character=params.position.character,
            accepted_text_by_path=dict(snapshot.accepted_text_by_path),
        )
        if target_span is None:
            return None
        return _location_for_span(
            target_span,
            accepted_text_by_path=dict(snapshot.accepted_text_by_path),
        )

    def document_symbols(
        self,
        params: types.DocumentSymbolParams,
    ) -> tuple[types.DocumentSymbol, ...] | None:
        """Return compiler-proven authored definitions with exact ranges."""

        uri = params.text_document.uri
        navigation = self._current_navigation(uri)
        if navigation is None:
            return None
        snapshot, index = navigation
        source_path = _file_uri_path(uri)
        accepted_text = dict(snapshot.accepted_text_by_path).get(source_path)
        if accepted_text is None:
            return None
        result: list[types.DocumentSymbol] = []
        for symbol in symbols_for_document(index, source_path=source_path):
            symbol_kind = _DOCUMENT_SYMBOL_KIND_BY_INTERNAL_KIND.get(
                symbol.kind
            )
            if symbol_kind is None:
                return None
            try:
                definition_range = _lsp_range(
                    source_span_to_lsp_range(
                        symbol.definition_span,
                        accepted_text,
                    )
                )
                selection_range = _lsp_range(
                    source_span_to_lsp_range(
                        symbol.selection_span,
                        accepted_text,
                    )
                )
            except CoordinateTranslationError:
                return None
            result.append(
                types.DocumentSymbol(
                    name=symbol.name,
                    kind=symbol_kind,
                    range=definition_range,
                    selection_range=selection_range,
                )
            )
        return tuple(result)

    def completion(
        self,
        params: types.CompletionParams,
    ) -> types.CompletionList:
        """Return full, frozen recovery, or exact empty completion."""

        uri = params.text_document.uri
        driver = self._require_driver()
        transitions: list[LspStateTransition] = []
        snapshot = driver.snapshot_if_current(
            uri,
            transition_sink=transitions.append,
        )
        self._emit_transition_effects(transitions)
        if snapshot is None and not transitions:
            return _completion_list((), is_incomplete=False)
        source_path = _file_uri_path(uri)
        if snapshot is not None:
            compile_result = getattr(
                snapshot.build_value,
                "compile_result",
                None,
            )
            try:
                index = build_navigation_index(
                    compile_result,
                    frozen_form_completions=driver.frozen_form_completions,
                )
            except (TypeError, ValueError) as error:
                self.log_internal_error(error)
                return _completion_list((), is_incomplete=False)
            return _completion_list(
                completion_for_document(
                    index,
                    source_path=source_path,
                ),
                is_incomplete=False,
            )

        recovery_selection = classify_completion_recovery(
            driver.state,
            entry_path=source_path,
        )
        if self._defer_compiles:
            self._schedule_compile_pump()
        else:
            self._emit_transition_effects(driver.drain())
        if recovery_selection == "static-incomplete":
            return _completion_list(
                driver.frozen_form_completions,
                is_incomplete=True,
            )
        return _completion_list((), is_incomplete=False)

    def log_internal_error(self, error: Exception) -> None:
        """Report an internal failure without creating a language diagnostic."""

        self.window_log_message(
            types.LogMessageParams(
                type=types.MessageType.Error,
                message=f"{type(error).__name__}: {error}",
            )
        )

    def cancel_progress_presentation(
        self,
        params: types.WorkDoneProgressCancelParams,
    ) -> None:
        """Honor client cancellation as presentation-only suppression."""

        self._apply_progress_transition(
            self.progress_controller.cancel_presentation(str(params.token))
        )

    def _require_driver(self) -> LspCompileDriver:
        driver = self.driver
        if driver is None:
            raise RuntimeError("language server is not initialized")
        return driver

    def _schedule_compile_pump(self) -> None:
        """Ensure the real transport has one event-loop-owned compile pump."""

        if not self._defer_compiles:
            return
        self._reconcile_progress()
        task = self._compile_task
        if task is not None and not task.done():
            return
        self._compile_task = asyncio.create_task(self._run_compile_pump())

    async def _run_compile_pump(self) -> None:
        """Run blocking compiles off-loop while retaining state ownership."""

        driver = self._require_driver()
        try:
            while True:
                prepared = driver.begin_next()
                if prepared is None:
                    return
                if not isinstance(prepared, PreparedCompile):
                    self._emit_transition_effects((prepared,))
                    continue
                completion = await asyncio.to_thread(
                    driver.execute_prepared,
                    prepared,
                )
                transition = driver.finish_prepared(completion)
                self._emit_transition_effects((transition,))
        except asyncio.CancelledError:
            self._settle_progress("pump_task_cancellation")
            raise
        except Exception as error:
            self._settle_progress("pump_exception")
            self._log_internal_error_best_effort(error)
        finally:
            self._compile_task = None
            if driver.queued_generations:
                self._schedule_compile_pump()

    def _current_navigation(
        self,
        document_uri: str,
    ) -> tuple[AcceptedCompileSnapshot, NavigationIndex] | None:
        """Recheck through the sole driver authority and retain all effects."""

        driver = self._require_driver()
        transitions: list[LspStateTransition] = []
        snapshot = driver.snapshot_if_current(
            document_uri,
            transition_sink=transitions.append,
        )
        self._emit_transition_effects(transitions)
        if snapshot is None:
            if self._defer_compiles:
                self._schedule_compile_pump()
            else:
                self._emit_transition_effects(driver.drain())
            return None
        compile_result = getattr(snapshot.build_value, "compile_result", None)
        try:
            index = build_navigation_index(
                compile_result,
                frozen_form_completions=driver.frozen_form_completions,
            )
        except (TypeError, ValueError) as error:
            self.log_internal_error(error)
            return None
        return snapshot, index

    def _drain_and_publish(
        self,
        initial_transition: LspStateTransition,
    ) -> None:
        driver = self._require_driver()
        if self._defer_compiles:
            self._emit_transition_effects((initial_transition,))
            self._schedule_compile_pump()
            return
        self._emit_transition_effects(
            (initial_transition, *driver.drain())
        )

    def _emit_transition_effects(
        self,
        transitions: Iterable[LspStateTransition],
    ) -> None:
        driver = self._require_driver()
        retained_transitions = tuple(transitions)
        republish_uris = tuple(
            sorted(
                {
                    uri
                    for transition in retained_transitions
                    for uri in transition.effects.republish_uris
                }
            )
        )
        if republish_uris:
            try:
                aggregated = aggregate_diagnostic_contributions(
                    current_diagnostic_contributions(driver.state)
                )
                publications = tuple(
                    types.PublishDiagnosticsParams(
                        uri=uri,
                        diagnostics=tuple(
                            _lsp_diagnostic(contribution)
                            for contribution in aggregated.get(uri, ())
                        ),
                    )
                    for uri in republish_uris
                )
            except Exception as error:
                self.log_internal_error(error)
            else:
                for publication in publications:
                    self.text_document_publish_diagnostics(publication)
        self._reconcile_progress()
        if not any(
            transition.effects.restart_notice_required
            for transition in retained_transitions
        ):
            return
        message = (
            "Workflow Lisp initialization context changed; restart the "
            "language server to reinitialize its immutable workspace."
        )
        self.window_show_message(
            types.ShowMessageParams(
                type=types.MessageType.Warning,
                message=message,
            )
        )
        self.window_log_message(
            types.LogMessageParams(
                type=types.MessageType.Warning,
                message=message,
            )
        )

    def _logical_compile_busy(self) -> bool:
        """Project only open, clean, current pending generations as busy."""

        state = self._require_driver().state
        return (
            not state.configuration_stale
            and any(
                entry.editor_text is not None
                and entry.buffer_status == "clean"
                and entry.compile_status == "pending"
                and entry.pending_generation == entry.generation
                for entry in state.entries
            )
        )

    def _reconcile_progress(self) -> None:
        """Reconcile transport presentation after adopted driver state."""

        if not self._defer_compiles:
            return
        self._apply_progress_transition(
            self.progress_controller.observe_busy(
                self._logical_compile_busy()
            )
        )

    def _settle_progress(self, reason: SettlementReason) -> None:
        """Settle local presentation after a pump-level terminal path."""

        self._apply_progress_transition(
            self.progress_controller.settle(reason)
        )

    def _apply_progress_transition(
        self,
        transition: ProgressTransition,
    ) -> None:
        """Adopt pure progress state before interpreting ordered effects."""

        self.progress_controller = transition.controller
        for effect in transition.effects:
            self._interpret_progress_effect(effect)

    def _interpret_progress_effect(self, effect: ProgressEffect) -> None:
        """Interpret one transport-only progress instruction."""

        if effect.kind == "create":
            task = asyncio.create_task(
                self._create_progress_token(
                    token=effect.token,
                    interval=effect.interval,
                )
            )
            self._progress_create_tasks.add(task)
            task.add_done_callback(
                lambda completed,
                token=effect.token,
                interval=effect.interval: self._finish_progress_create_task(
                    completed,
                    token=token,
                    interval=interval,
                )
            )
            return
        if effect.kind == "begin":
            try:
                self.work_done_progress.begin(
                    effect.token,
                    types.WorkDoneProgressBegin(
                        title="Workflow Lisp compile",
                        cancellable=False,
                    ),
                )
            except Exception as error:
                self._apply_progress_transition(
                    self.progress_controller.begin_failed(
                        token=effect.token,
                        interval=effect.interval,
                        error=error,
                    )
                )
            return
        if effect.kind == "end":
            try:
                self.work_done_progress.end(
                    effect.token,
                    types.WorkDoneProgressEnd(),
                )
            except Exception as error:
                self._log_internal_error_best_effort(error)
            return
        if effect.kind == "retire":
            self._retire_progress_token(effect.token)
            return
        if effect.kind == "log_transport_error":
            error = effect.error
            if error is None:
                error = RuntimeError("progress transport failed")
            self._log_internal_error_best_effort(error)
            return
        raise RuntimeError(f"unknown progress effect: {effect.kind}")

    def _finish_progress_create_task(
        self,
        task: asyncio.Task[None],
        *,
        token: str,
        interval: int,
    ) -> None:
        """Consume one create task result and settle any stale Creating state."""

        self._progress_create_tasks.discard(task)
        try:
            task.result()
        except asyncio.CancelledError:
            error: Exception | None = None
        except Exception as task_error:
            error = task_error
        else:
            return
        transition = self.progress_controller.create_task_settled(
            token=token,
            interval=interval,
            error=error,
        )
        try:
            self._apply_progress_transition(transition)
        except Exception as settlement_error:
            self.progress_controller = transition.controller
            self._retire_progress_token(token)
            if error is not None:
                self._log_internal_error_best_effort(error)
            self._log_internal_error_best_effort(settlement_error)

    def _log_internal_error_best_effort(self, error: Exception) -> None:
        """Keep internal logging outside progress and compile authority."""

        try:
            self.log_internal_error(error)
        except Exception:
            return

    async def _create_progress_token(
        self,
        *,
        token: str,
        interval: int,
    ) -> None:
        """Await token acknowledgment off the compile critical path."""

        try:
            await self.work_done_progress.create_async(token)
        except Exception as error:
            transition = self.progress_controller.create_failed(
                token=token,
                interval=interval,
                error=error,
            )
        else:
            transition = self.progress_controller.create_succeeded(
                token=token,
                interval=interval,
            )
        self._apply_progress_transition(transition)

    def _retire_progress_token(self, token: str) -> None:
        """Retire one acknowledged pygls token through the reviewed adapter."""

        self.work_done_progress.tokens.pop(token, None)


def _initialization_diagnostic_path(raw_path: str) -> str:
    """Prefer one canonical diagnostic path and retain unresolvable text."""

    try:
        return Path(raw_path).resolve(strict=False).as_posix()
    except (OSError, RuntimeError, ValueError):
        return raw_path


def create_server(
    *,
    build_in_memory: BuildInMemory | None = None,
) -> WorkflowLispLanguageServer:
    """Create one server and bind its initialization contract."""

    server = WorkflowLispLanguageServer(
        build_in_memory=build_in_memory,
        _defer_compiles=True,
    )

    @server.feature(types.INITIALIZE)
    def initialize(params: types.InitializeParams) -> None:
        server.initialize_runtime(params)

    @server.feature(types.INITIALIZED)
    def initialized(_params: types.InitializedParams) -> None:
        server.register_watcher_if_supported()

    @server.feature(types.TEXT_DOCUMENT_DID_OPEN)
    def did_open(params: types.DidOpenTextDocumentParams) -> None:
        server.open_document(params)

    @server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
    def did_change(params: types.DidChangeTextDocumentParams) -> None:
        server.change_document(params)

    @server.feature(types.TEXT_DOCUMENT_DID_SAVE)
    def did_save(params: types.DidSaveTextDocumentParams) -> None:
        server.save_document(params)

    @server.feature(types.TEXT_DOCUMENT_DID_CLOSE)
    def did_close(params: types.DidCloseTextDocumentParams) -> None:
        server.close_document(params)

    @server.feature(types.WORKSPACE_DID_CHANGE_WATCHED_FILES)
    def did_change_watched_files(
        params: types.DidChangeWatchedFilesParams,
    ) -> None:
        server.observe_watched_files(params)

    @server.feature(types.WORKSPACE_DID_CHANGE_WORKSPACE_FOLDERS)
    def did_change_workspace_folders(
        params: types.DidChangeWorkspaceFoldersParams,
    ) -> None:
        server.change_workspace_folders(params)

    @server.feature(types.WINDOW_WORK_DONE_PROGRESS_CANCEL)
    def work_done_progress_cancel(
        params: types.WorkDoneProgressCancelParams,
    ) -> None:
        server.cancel_progress_presentation(params)

    @server.feature(types.TEXT_DOCUMENT_DEFINITION)
    def definition(params: types.DefinitionParams) -> types.Location | None:
        return server.definition(params)

    @server.feature(types.TEXT_DOCUMENT_DOCUMENT_SYMBOL)
    def document_symbol(
        params: types.DocumentSymbolParams,
    ) -> tuple[types.DocumentSymbol, ...] | None:
        return server.document_symbols(params)

    @server.feature(types.TEXT_DOCUMENT_COMPLETION)
    def completion(params: types.CompletionParams) -> types.CompletionList:
        return server.completion(params)

    return server


def _file_uri_path(uri: str) -> Path:
    canonical_paths = canonicalize_workspace_roots(
        root_uri=uri,
        workspace_folder_uris=(),
    )
    return next(iter(canonical_paths))


def _completion_list(
    rows: Iterable[NavigationCompletion],
    *,
    is_incomplete: bool,
) -> types.CompletionList:
    return types.CompletionList(
        is_incomplete=is_incomplete,
        items=tuple(
            types.CompletionItem(
                label=item.label,
                kind=_COMPLETION_ITEM_KIND_BY_INTERNAL_KIND[item.kind],
                detail=item.detail,
                sort_text=item.label,
            )
            for item in rows
        ),
    )


def _lsp_diagnostic(
    contribution: DiagnosticContribution,
) -> types.Diagnostic:
    notes = contribution.data["notes"]
    if not isinstance(notes, tuple) or not all(
        isinstance(note, str) for note in notes
    ):
        raise TypeError("diagnostic notes must be an ordered tuple of strings")
    visible_message = contribution.message + "".join(
        f"\n\nNote: {note}" for note in notes
    )
    return types.Diagnostic(
        range=_lsp_range(contribution.range),
        message=visible_message,
        severity=types.DiagnosticSeverity(contribution.severity),
        code=contribution.code,
        source=contribution.source,
        related_information=tuple(
            types.DiagnosticRelatedInformation(
                location=types.Location(
                    uri=item["location"]["uri"],
                    range=_lsp_range(item["location"]["range"]),
                ),
                message=(
                    f"{item['frame_role']} {item['location_role']}: "
                    f"{item['name']}"
                    + (
                        f" [{item['expansion_id']}]"
                        if item["expansion_id"] is not None
                        else ""
                    )
                ),
            )
            for item in contribution.related_information
        ),
        data=_plain_value(contribution.data),
    )


def _lsp_range(value: Mapping[str, object]) -> types.Range:
    start = value["start"]
    end = value["end"]
    if not isinstance(start, Mapping) or not isinstance(end, Mapping):
        raise TypeError("diagnostic range endpoints must be mappings")
    return types.Range(
        start=types.Position(
            line=int(start["line"]),
            character=int(start["character"]),
        ),
        end=types.Position(
            line=int(end["line"]),
            character=int(end["character"]),
        ),
    )


def _location_for_span(
    span: object,
    *,
    accepted_text_by_path: Mapping[Path, str],
) -> types.Location | None:
    try:
        path = Path(span.start.path).resolve(strict=False)
        accepted_text = accepted_text_by_path.get(path)
        if accepted_text is None:
            return None
        return types.Location(
            uri=path.as_uri(),
            range=_lsp_range(source_span_to_lsp_range(span, accepted_text)),
        )
    except (AttributeError, CoordinateTranslationError, TypeError, ValueError):
        return None


def _plain_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_value(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_value(item) for item in value]
    return value


__all__ = [
    "WorkflowLispLanguageServer",
    "create_server",
]
