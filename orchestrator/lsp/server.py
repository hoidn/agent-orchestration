"""Frame-clean pygls transport for the Workflow Lisp language server."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from pathlib import Path

from lsprotocol import types
from pygls.exceptions import JsonRpcInvalidParams
from pygls.lsp.server import LanguageServer

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
    NavigationIndex,
    build_navigation_index,
    completion_for_document,
    definition_at_lsp_position,
    symbols_for_document,
)
from .state import (
    AcceptedCompileSnapshot,
    LspInitializationError,
    LspStateTransition,
    canonicalize_workspace_roots,
    change_entry,
    close_entry,
    initialize_lsp_state,
    open_entry,
    save_observed_entry,
    transition_workspace_root_set,
)


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
        except LspInitializationError as error:
            raise JsonRpcInvalidParams(message=str(error)) from error
        self.driver = driver
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
        """Adopt the full in-memory overlay without compiling or publishing."""

        driver = self._require_driver()
        document = self.workspace.get_text_document(
            params.text_document.uri
        )
        driver.apply_transition(
            change_entry(
                driver.state,
                document_uri=params.text_document.uri,
                editor_text=document.source,
            )
        )

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
        """Return only authored module, procedure, and workflow definitions."""

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
            try:
                symbol_range = _lsp_range(
                    source_span_to_lsp_range(symbol.span, accepted_text)
                )
            except CoordinateTranslationError:
                return None
            result.append(
                types.DocumentSymbol(
                    name=symbol.name,
                    kind=(
                        types.SymbolKind.Module
                        if symbol.kind == "module"
                        else types.SymbolKind.Function
                    ),
                    range=symbol_range,
                    selection_range=symbol_range,
                )
            )
        return tuple(result)

    def completion(
        self,
        params: types.CompletionParams,
    ) -> types.CompletionList:
        """Return the exact visibility-plus-form-registry completion set."""

        uri = params.text_document.uri
        navigation = self._current_navigation(uri)
        if navigation is None:
            return types.CompletionList(is_incomplete=False, items=())
        _snapshot, index = navigation
        source_path = _file_uri_path(uri)
        return types.CompletionList(
            is_incomplete=False,
            items=tuple(
                types.CompletionItem(
                    label=item.label,
                    kind=(
                        types.CompletionItemKind.Function
                        if item.kind == "callable"
                        else types.CompletionItemKind.Keyword
                    ),
                    sort_text=item.label,
                )
                for item in completion_for_document(
                    index,
                    source_path=source_path,
                )
            ),
        )

    def log_internal_error(self, error: Exception) -> None:
        """Report an internal failure without creating a language diagnostic."""

        self.window_log_message(
            types.LogMessageParams(
                type=types.MessageType.Error,
                message=f"{type(error).__name__}: {error}",
            )
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
        except Exception as error:
            self.log_internal_error(error)
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
            index = build_navigation_index(compile_result)
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
            aggregated = aggregate_diagnostic_contributions(
                {
                    entry.path.as_uri(): entry.diagnostic_contributions
                    for entry in driver.state.entries
                }
            )
            for uri in republish_uris:
                self.text_document_publish_diagnostics(
                    types.PublishDiagnosticsParams(
                        uri=uri,
                        diagnostics=tuple(
                            _lsp_diagnostic(contribution)
                            for contribution in aggregated.get(uri, ())
                        ),
                    )
                )
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


def _lsp_diagnostic(
    contribution: DiagnosticContribution,
) -> types.Diagnostic:
    return types.Diagnostic(
        range=_lsp_range(contribution.range),
        message=contribution.message,
        severity=types.DiagnosticSeverity(contribution.severity),
        code=contribution.code,
        source=contribution.source,
        related_information=tuple(
            types.DiagnosticRelatedInformation(
                location=types.Location(
                    uri=item["location"]["uri"],
                    range=_lsp_range(item["location"]["range"]),
                ),
                message=f"{item['kind']}: {item['name']}",
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
