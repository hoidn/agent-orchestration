"""Filesystem boundary helpers for the Workflow Lisp LSP compile driver."""

from __future__ import annotations

from _thread import LockType
from collections.abc import Callable
from dataclasses import dataclass, field, replace
import hashlib
from pathlib import Path
from threading import Lock

from orchestrator.workflow_lisp import compiler
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    FrontendInMemoryBuildResult,
    FrontendInitializationConfiguration,
    build_frontend_bundle_in_memory,
    load_frontend_initialization_configuration,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.form_registry import registered_form_heads
from orchestrator.workflow_lisp.reader import SourceReadTrace

from .diagnostics import translate_frontend_diagnostics
from .navigation import NavigationCompletion, project_form_completion_rows
from .state import (
    AcceptedCompileSnapshot,
    DiskSourceSnapshot,
    ImmutableConfigurationVector,
    LspState,
    LspStateTransition,
    StateEffects,
    accept_compile_language_error,
    accept_compile_success,
    current_navigation_snapshot,
    latch_configuration_stale,
    observe_file_revision,
    record_server_failure,
    save_entry,
)

BuildInMemory = Callable[..., FrontendInMemoryBuildResult]
ServerErrorLogger = Callable[[Exception], None]
TransitionSink = Callable[[LspStateTransition], None]


def _ignore_server_error(_error: Exception) -> None:
    """Default library callback when transport logging is not wired yet."""


@dataclass(frozen=True, slots=True)
class _SourceCurrentnessProbe:
    """One postflight source proof and the exact text read by that proof."""

    transition: LspStateTransition | None
    snapshots: tuple[DiskSourceSnapshot, ...]

    @property
    def accepted_text_by_path(self) -> dict[Path, str]:
        return {
            snapshot.canonical_path: snapshot.raw_decoded_text
            for snapshot in self.snapshots
            if snapshot.raw_decoded_text is not None
        }


@dataclass(frozen=True, slots=True)
class PreparedCompile:
    """One opaque, controller-prepared invocation of the blocking compiler."""

    ticket: int
    path: Path
    generation: int
    request: FrontendBuildRequest
    source_read_trace: SourceReadTrace
    _build_in_memory: BuildInMemory = field(repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class PreparedCompileCompletion:
    """The state-free outcome of executing one prepared compiler invocation."""

    prepared: PreparedCompile
    result: object | None
    error: Exception | None


@dataclass(slots=True)
class LspCompileDriver:
    """Mutable process-local owner around immutable LSP state replacements."""

    state: LspState
    initialization_configuration: FrontendInitializationConfiguration
    frozen_form_completions: tuple[NavigationCompletion, ...]
    _build_in_memory: BuildInMemory
    _queue: list[tuple[Path, int]]
    _latest_generation_by_path: dict[Path, int]
    _log_server_error: ServerErrorLogger
    _run_lock: LockType = field(default_factory=Lock, repr=False)
    _running: bool = False
    _next_ticket: int = 1
    _active_prepared: PreparedCompile | None = field(default=None, repr=False)
    _invalidated_tickets: set[int] = field(default_factory=set, repr=False)

    @property
    def queued_generations(self) -> tuple[tuple[Path, int], ...]:
        """Expose the deterministic pending order for tests and server wiring."""

        return tuple(self._queue)

    @property
    def running(self) -> bool:
        """Report whether the sole serialized build slot is occupied."""

        return self._running

    def apply_transition(self, transition: LspStateTransition) -> None:
        """Adopt immutable state and coalesce its scheduling effects."""

        self.state = transition.state
        canceled = set(transition.effects.canceled_generations)
        active = self._active_prepared
        if (
            active is not None
            and (active.path, active.generation) in canceled
        ):
            self._invalidated_tickets.add(active.ticket)
        if canceled:
            self._queue[:] = [
                item for item in self._queue if item not in canceled
            ]
            for path, generation in canceled:
                if self._latest_generation_by_path.get(path) == generation:
                    self._latest_generation_by_path.pop(path, None)
        for path, generation in transition.effects.scheduled_generations:
            self._queue[:] = [
                item for item in self._queue if item[0] != path
            ]
            self._latest_generation_by_path[path] = generation
            self._queue.append((path, generation))

    def begin_next(
        self,
    ) -> PreparedCompile | LspStateTransition | None:
        """Prepare at most one current generation on the controller thread."""

        if not self._run_lock.acquire(blocking=False):
            raise RuntimeError("LSP compile driver is already running")
        self._running = True
        try:
            queued = self._pop_current_generation()
            if queued is None:
                self._release_run_slot()
                return None
            path, generation = queued
            try:
                configuration_preflight = self.recheck_configuration()
            except Exception as error:
                self._log_server_error(error)
                transition = record_server_failure(
                    self.state,
                    document_uri=path.as_uri(),
                    generation=generation,
                )
                self.apply_transition(transition)
                self._release_run_slot()
                return transition
            self.apply_transition(configuration_preflight)
            if self.state.configuration_stale:
                self._release_run_slot()
                return configuration_preflight
            source_read_trace = SourceReadTrace()
            try:
                request = self._build_request(path)
            except Exception as error:
                transition = self._accept_server_failure(
                    path=path,
                    generation=generation,
                    error=error,
                    source_read_trace=source_read_trace,
                )
                self._release_run_slot()
                return transition
            prepared = PreparedCompile(
                ticket=self._next_ticket,
                path=path,
                generation=generation,
                request=request,
                source_read_trace=source_read_trace,
                _build_in_memory=self._build_in_memory,
            )
            self._next_ticket += 1
            self._active_prepared = prepared
            return prepared
        except BaseException:
            if self._active_prepared is None:
                self._release_run_slot()
            raise

    @staticmethod
    def execute_prepared(
        prepared: PreparedCompile,
    ) -> PreparedCompileCompletion:
        """Run only the blocking compiler call, without consulting driver state."""

        if not isinstance(prepared, PreparedCompile):
            raise TypeError("prepared compile must be a PreparedCompile value")
        try:
            result = prepared._build_in_memory(
                prepared.request,
                source_read_trace=prepared.source_read_trace,
            )
        except Exception as error:
            return PreparedCompileCompletion(
                prepared=prepared,
                result=None,
                error=error,
            )
        return PreparedCompileCompletion(
            prepared=prepared,
            result=result,
            error=None,
        )

    def finish_prepared(
        self,
        completion: PreparedCompileCompletion,
    ) -> LspStateTransition:
        """Adjudicate one exact active ticket on the controller thread."""

        if not isinstance(completion, PreparedCompileCompletion):
            raise TypeError(
                "prepared completion must be a PreparedCompileCompletion value"
            )
        active = self._active_prepared
        if active is None:
            raise RuntimeError("LSP compile driver has no active prepared build")
        if completion.prepared is not active:
            raise RuntimeError(
                "LSP compile completion does not match the active ticket"
            )
        if completion.error is not None and not isinstance(
            completion.error,
            Exception,
        ):
            raise TypeError("prepared compile error must be an Exception")

        path = active.path
        generation = active.generation
        source_read_trace = active.source_read_trace
        invalidated = active.ticket in self._invalidated_tickets
        try:
            if invalidated:
                if (
                    completion.error is not None
                    and not isinstance(
                        completion.error,
                        LispFrontendCompileError,
                    )
                ):
                    self._log_server_error(completion.error)
                return LspStateTransition(
                    state=self.state,
                    effects=StateEffects(),
                )
            try:
                if isinstance(
                    completion.error,
                    LispFrontendCompileError,
                ):
                    return self._accept_language_error(
                        path=path,
                        generation=generation,
                        source_read_trace=source_read_trace,
                        error=completion.error,
                    )
                if completion.error is not None:
                    return self._accept_server_failure(
                        path=path,
                        generation=generation,
                        error=completion.error,
                        source_read_trace=source_read_trace,
                    )
                result = completion.result
                configuration_postflight = self.recheck_configuration()
                self.apply_transition(configuration_postflight)
                if self.state.configuration_stale:
                    return configuration_postflight
                attempt_configuration_mismatch = (
                    self._latch_attempt_configuration_mismatch(
                        getattr(
                            getattr(result, "configuration_trace", None),
                            "revision_vector",
                            None,
                        )
                    )
                )
                if attempt_configuration_mismatch is not None:
                    return attempt_configuration_mismatch
                revision_vector = source_read_trace.revision_vector
                self._validate_success_trace(
                    compile_entry_path=path,
                    revision_vector=revision_vector,
                )
                self._validate_trace_paths(revision_vector)
                source_probe = self._probe_source_currentness(
                    revision_vector,
                    compile_entry_path=path,
                    generation=generation,
                    force_entry_reproof=bool(
                        source_read_trace.revision_conflict_paths
                    ),
                )
                if source_probe.transition is not None:
                    return source_probe.transition
                diagnostics = tuple(result.diagnostics)
                diagnostic_contributions = translate_frontend_diagnostics(
                    diagnostics,
                    compile_entry_uri=path.as_uri(),
                    accepted_generation=generation,
                    accepted_text_by_path=source_probe.accepted_text_by_path,
                )
                transition = accept_compile_success(
                    self.state,
                    document_uri=path.as_uri(),
                    generation=generation,
                    snapshot=AcceptedCompileSnapshot(
                        build_value=result,
                        source_revision_vector=revision_vector,
                        accepted_text_by_path=tuple(
                            (
                                snapshot.canonical_path,
                                snapshot.raw_decoded_text,
                            )
                            for snapshot in source_probe.snapshots
                            if snapshot.raw_decoded_text is not None
                        ),
                    ),
                    dependency_closure=frozenset(
                        trace_path
                        for trace_path, _revision in revision_vector
                    ),
                    diagnostic_contributions=diagnostic_contributions,
                )
                self.apply_transition(transition)
                return transition
            except Exception as error:
                return self._accept_server_failure(
                    path=path,
                    generation=generation,
                    error=error,
                )
        finally:
            self._invalidated_tickets.discard(active.ticket)
            self._active_prepared = None
            self._release_run_slot()

    def run_next(self) -> LspStateTransition | None:
        """Run at most one current queued generation in the sole build slot."""

        prepared = self.begin_next()
        if not isinstance(prepared, PreparedCompile):
            return prepared
        try:
            completion = self.execute_prepared(prepared)
        except BaseException:
            self._invalidated_tickets.discard(prepared.ticket)
            self._active_prepared = None
            self._release_run_slot()
            raise
        return self.finish_prepared(completion)

    def drain(self) -> tuple[LspStateTransition, ...]:
        """Run queued generations serially until no current item remains."""

        transitions: list[LspStateTransition] = []
        while True:
            transition = self.run_next()
            if transition is None:
                return tuple(transitions)
            transitions.append(transition)

    def _release_run_slot(self) -> None:
        self._running = False
        self._run_lock.release()

    def snapshot_if_current(
        self,
        document_uri: str,
        *,
        transition_sink: TransitionSink | None = None,
    ) -> AcceptedCompileSnapshot | None:
        """Return navigation authority only after mandatory live-disk checks."""

        try:
            configuration_transition = self.recheck_configuration()
            self.apply_transition(configuration_transition)
            if transition_sink is not None:
                transition_sink(configuration_transition)
            if self.state.configuration_stale:
                return None
            snapshot = current_navigation_snapshot(
                self.state,
                document_uri=document_uri,
            )
            if snapshot is None:
                return None
            self._validate_trace_paths(snapshot.source_revision_vector)
            if (
                self._observe_source_drift(
                    snapshot.source_revision_vector,
                    transition_sink=transition_sink,
                )
                is not None
            ):
                return None
        except Exception as error:
            self._log_server_error(error)
            return None
        return current_navigation_snapshot(
            self.state,
            document_uri=document_uri,
        )

    def observe_disk_path(self, path: str | Path) -> LspStateTransition:
        """Route one delivered path through configuration or source authority."""

        canonical_path = Path(path).resolve(strict=False)
        vector = self.state.configuration_vector
        if vector is None:
            raise RuntimeError("compile driver state has no configuration vector")
        frozen_configuration_paths = {
            frozen_path
            for frozen_path, _revision in (
                *vector.configuration_revisions,
                *vector.recursively_imported_source_revisions,
            )
        }
        if canonical_path in frozen_configuration_paths:
            transition = self.recheck_configuration()
        else:
            transition = observe_file_revision(
                self.state,
                probe_disk_source(canonical_path),
            )
        self.apply_transition(transition)
        return transition

    def _pop_current_generation(self) -> tuple[Path, int] | None:
        while self._queue:
            path, generation = self._queue.pop(0)
            if self._latest_generation_by_path.get(path) != generation:
                continue
            self._latest_generation_by_path.pop(path, None)
            entry = next(
                (candidate for candidate in self.state.entries if candidate.path == path),
                None,
            )
            if (
                entry is not None
                and entry.pending_generation == generation
                and entry.generation == generation
                and entry.buffer_status == "clean"
                and entry.compile_status == "pending"
            ):
                return path, generation
        return None

    def _validate_trace_paths(
        self,
        revision_vector: tuple[tuple[Path, str], ...],
    ) -> None:
        _validate_trace_paths_within_roots(
            revision_vector,
            workspace_root=self.state.workspace_root,
            builtin_stdlib_source_root=self.state.builtin_stdlib_source_root,
        )

    @staticmethod
    def _validate_success_trace(
        *,
        compile_entry_path: Path,
        revision_vector: tuple[tuple[Path, str], ...],
    ) -> None:
        canonical_entry_path = compile_entry_path.resolve(strict=False)
        if not revision_vector:
            raise RuntimeError("successful compiler trace is empty")
        if not any(path == canonical_entry_path for path, _revision in revision_vector):
            raise RuntimeError(
                "successful compiler trace does not contain its canonical entry"
            )
        for path, revision in revision_vector:
            if not LspCompileDriver._is_sha256_revision(revision):
                raise RuntimeError(
                    "successful compiler trace contains a non-sha256 revision "
                    f"for `{path}`"
                )

    @staticmethod
    def _is_sha256_revision(revision: str) -> bool:
        digest = revision.removeprefix("sha256:")
        return (
            revision.startswith("sha256:")
            and len(digest) == 64
            and all(character in "0123456789abcdef" for character in digest)
        )

    def _accept_language_error(
        self,
        *,
        path: Path,
        generation: int,
        source_read_trace: SourceReadTrace,
        error: LispFrontendCompileError,
    ) -> LspStateTransition:
        configuration_postflight = self.recheck_configuration()
        self.apply_transition(configuration_postflight)
        if self.state.configuration_stale:
            return configuration_postflight
        attempt_configuration_mismatch = (
            self._latch_attempt_configuration_mismatch(
                error.configuration_revision_vector,
            )
        )
        if attempt_configuration_mismatch is not None:
            return attempt_configuration_mismatch
        revision_vector = source_read_trace.revision_vector
        self._validate_trace_paths(revision_vector)
        source_probe = self._probe_source_currentness(
            revision_vector,
            compile_entry_path=path,
            generation=generation,
            force_entry_reproof=bool(
                source_read_trace.revision_conflict_paths
            ),
        )
        if source_probe.transition is not None:
            return source_probe.transition
        diagnostics = tuple(error.diagnostics)
        diagnostic_contributions = translate_frontend_diagnostics(
            diagnostics,
            compile_entry_uri=path.as_uri(),
            accepted_generation=generation,
            accepted_text_by_path=source_probe.accepted_text_by_path,
        )
        (
            dependency_closure,
            dependency_revision_vector,
        ) = self._language_error_dependency_state(
            source_read_trace,
            outer_entry_path=path,
        )
        transition = accept_compile_language_error(
            self.state,
            document_uri=path.as_uri(),
            generation=generation,
            dependency_closure=dependency_closure,
            dependency_revision_vector=dependency_revision_vector,
            diagnostic_contributions=diagnostic_contributions,
        )
        self.apply_transition(transition)
        return transition

    def _accept_server_failure(
        self,
        *,
        path: Path,
        generation: int,
        error: Exception,
        source_read_trace: SourceReadTrace | None = None,
    ) -> LspStateTransition:
        self._log_server_error(error)
        try:
            configuration_postflight = self.recheck_configuration()
        except Exception as recheck_error:
            self._log_server_error(recheck_error)
        else:
            self.apply_transition(configuration_postflight)
            if self.state.configuration_stale:
                return configuration_postflight
        attempt_configuration_mismatch = (
            self._latch_generic_attempt_configuration_mismatch(error)
        )
        if attempt_configuration_mismatch is not None:
            return attempt_configuration_mismatch
        if source_read_trace is not None:
            revision_vector = source_read_trace.revision_vector
            try:
                self._validate_trace_paths(revision_vector)
            except RuntimeError:
                pass
            else:
                source_drift = self._observe_source_drift(
                    revision_vector,
                    compile_entry_path=path,
                    generation=generation,
                    force_entry_reproof=bool(
                        source_read_trace.revision_conflict_paths
                    ),
                )
                if source_drift is not None:
                    return source_drift
        transition = record_server_failure(
            self.state,
            document_uri=path.as_uri(),
            generation=generation,
        )
        self.apply_transition(transition)
        return transition

    def _latch_generic_attempt_configuration_mismatch(
        self,
        error: Exception,
    ) -> LspStateTransition | None:
        missing = object()
        observed_revision_vector = getattr(
            error,
            "configuration_revision_vector",
            missing,
        )
        revision_conflict_paths = getattr(
            error,
            "configuration_revision_conflict_paths",
            missing,
        )
        if (
            observed_revision_vector is missing
            and revision_conflict_paths is missing
        ):
            return None
        configuration_vector = self.state.configuration_vector
        if (
            configuration_vector is not None
            and observed_revision_vector
            == configuration_vector.configuration_revisions
            and not (
                revision_conflict_paths is not missing
                and bool(revision_conflict_paths)
            )
        ):
            return None
        transition = latch_configuration_stale(self.state)
        self.apply_transition(transition)
        return transition

    def _latch_attempt_configuration_mismatch(
        self,
        observed_revision_vector: object,
    ) -> LspStateTransition | None:
        configuration_vector = self.state.configuration_vector
        if (
            configuration_vector is not None
            and observed_revision_vector
            == configuration_vector.configuration_revisions
        ):
            return None
        transition = latch_configuration_stale(self.state)
        self.apply_transition(transition)
        return transition

    @staticmethod
    def _language_error_dependency_state(
        source_read_trace: SourceReadTrace,
        *,
        outer_entry_path: Path,
    ) -> tuple[
        frozenset[Path] | None,
        tuple[tuple[Path, str], ...] | None,
    ]:
        canonical_outer = outer_entry_path.resolve(strict=False)
        attempts = source_read_trace.module_graph_read_attempts
        if any(
            attempt.completed_at_ordinal is None or attempt.module_paths is None
            for attempt in attempts
        ):
            return None, None
        matching_attempts = tuple(
            attempt
            for attempt in attempts
            if attempt.canonical_entry_path == canonical_outer
        )
        if len(matching_attempts) != 1:
            return None, None
        attempt = matching_attempts[0]
        if attempt.completed_at_ordinal is None or attempt.module_paths is None:
            return None, None
        revision_vector = source_read_trace.revision_vector
        revision_paths = frozenset(
            path for path, _revision in revision_vector
        )
        if canonical_outer not in revision_paths:
            return None, None
        if any(
            not LspCompileDriver._is_sha256_revision(revision)
            for _path, revision in revision_vector
        ):
            return None, None
        attempted_module_paths = frozenset(
            module_path
            for graph_attempt in attempts
            for module_path in graph_attempt.module_paths or ()
        )
        if not attempted_module_paths.issubset(revision_paths):
            return None, None
        return revision_paths, revision_vector

    def _observe_source_drift(
        self,
        expected_revisions: tuple[tuple[Path, str], ...],
        *,
        compile_entry_path: Path | None = None,
        generation: int | None = None,
        force_entry_reproof: bool = False,
        transition_sink: TransitionSink | None = None,
    ) -> LspStateTransition | None:
        return self._probe_source_currentness(
            expected_revisions,
            compile_entry_path=compile_entry_path,
            generation=generation,
            force_entry_reproof=force_entry_reproof,
            transition_sink=transition_sink,
        ).transition

    def _probe_source_currentness(
        self,
        expected_revisions: tuple[tuple[Path, str], ...],
        *,
        compile_entry_path: Path | None = None,
        generation: int | None = None,
        force_entry_reproof: bool = False,
        transition_sink: TransitionSink | None = None,
    ) -> _SourceCurrentnessProbe:
        """Recheck one trace and retain the exact text from those same reads."""

        compile_entry = None
        if compile_entry_path is not None:
            compile_entry = next(
                (
                    entry
                    for entry in self.state.entries
                    if entry.path == compile_entry_path
                    and entry.buffer_status == "clean"
                    and entry.compile_status == "pending"
                    and entry.pending_generation == generation
                    and entry.generation == generation
                ),
                None,
            )
        expected_by_path: dict[Path, str] = {}
        ordered_paths: list[Path] = []
        for raw_path, expected_revision in expected_revisions:
            path = raw_path.resolve(strict=False)
            if path not in expected_by_path:
                ordered_paths.append(path)
                expected_by_path[path] = expected_revision
        if compile_entry is not None and compile_entry.path not in expected_by_path:
            ordered_paths.append(compile_entry.path)
        observed_by_path = {
            path: probe_disk_source(path)
            for path in ordered_paths
        }
        latest_transition: LspStateTransition | None = None
        for path in ordered_paths:
            observed = observed_by_path[path]
            trace_revision = expected_by_path.get(path)
            trace_matches = (
                trace_revision is None or observed.revision == trace_revision
            )
            entry_proof_matches = True
            if compile_entry is not None and path == compile_entry.path:
                retained = compile_entry.disk_snapshot
                entry_proof_matches = (
                    retained is not None
                    and observed.revision == retained.revision
                    and observed.raw_decoded_text == retained.raw_decoded_text
                    and observed.raw_decoded_text == compile_entry.editor_text
                )
            if trace_matches and entry_proof_matches:
                continue
            latest_transition = observe_file_revision(self.state, observed)
            self.apply_transition(latest_transition)
            if transition_sink is not None:
                transition_sink(latest_transition)
        if (
            (latest_transition is not None or force_entry_reproof)
            and compile_entry is not None
            and any(
                entry.path == compile_entry.path
                and entry.buffer_status == "clean"
                and entry.compile_status == "pending"
                and entry.pending_generation == generation
                and entry.generation == generation
                for entry in self.state.entries
            )
        ):
            latest_transition = save_entry(
                self.state,
                document_uri=compile_entry.path.as_uri(),
                disk_snapshot=observed_by_path[compile_entry.path],
            )
            self.apply_transition(latest_transition)
            if transition_sink is not None:
                transition_sink(latest_transition)
        return _SourceCurrentnessProbe(
            transition=latest_transition,
            snapshots=tuple(observed_by_path[path] for path in ordered_paths),
        )

    def _build_request(self, source_path: Path) -> FrontendBuildRequest:
        paths = self.state.options.configuration
        return FrontendBuildRequest(
            source_path=source_path,
            source_roots=self.state.options.source_roots,
            entry_workflow=self.state.options.entry_workflow,
            provider_externs_path=paths.provider_externs_path,
            prompt_externs_path=paths.prompt_externs_path,
            imported_workflow_bundles_path=paths.imported_workflow_bundles_path,
            command_boundaries_path=paths.command_boundaries_path,
            emit_debug_yaml=False,
            workspace_root=self.state.workspace_root,
            lint_profile=self.state.options.lint_profile,
            lowering_route=self.state.options.lowering_route,
        )

    def recheck_configuration(self) -> LspStateTransition:
        """Re-read the frozen configuration/root identity without decoding it."""

        if self.state.configuration_stale:
            return LspStateTransition(state=self.state, effects=StateEffects())
        vector = self.state.configuration_vector
        if vector is None:
            raise RuntimeError("compile driver state has no configuration vector")
        expected_revisions = (
            *vector.configuration_revisions,
            *vector.recursively_imported_source_revisions,
        )
        revisions_current = recheck_raw_revision_vector(expected_revisions)
        builtin_root_current = (
            Path(compiler._builtin_stdlib_source_root()).resolve(strict=False)
            == vector.builtin_stdlib_source_root
        )
        if not revisions_current or not builtin_root_current:
            transition = latch_configuration_stale(self.state)
            self.state = transition.state
            return transition
        return LspStateTransition(state=self.state, effects=StateEffects())


def initialize_compile_driver(
    state: LspState,
    *,
    build_in_memory: BuildInMemory = build_frontend_bundle_in_memory,
    log_server_error: ServerErrorLogger = _ignore_server_error,
) -> LspCompileDriver:
    """Load and freeze the production frontend context exactly once."""

    paths = state.options.configuration
    configuration = load_frontend_initialization_configuration(
        workspace_root=state.workspace_root,
        source_roots=state.options.source_roots,
        provider_externs_path=paths.provider_externs_path,
        prompt_externs_path=paths.prompt_externs_path,
        command_boundaries_path=paths.command_boundaries_path,
        imported_workflow_bundles_path=paths.imported_workflow_bundles_path,
        lowering_route=state.options.lowering_route,
    )
    _validate_trace_paths_within_roots(
        configuration.source_read_trace.revision_vector,
        workspace_root=state.workspace_root,
        builtin_stdlib_source_root=state.builtin_stdlib_source_root,
    )
    frozen_form_completions = project_form_completion_rows(
        tuple(registered_form_heads(target_dsl_version=None))
    )
    vector = ImmutableConfigurationVector(
        configured_paths=(
            ("provider_externs_path", paths.provider_externs_path),
            ("prompt_externs_path", paths.prompt_externs_path),
            (
                "imported_workflow_bundles_path",
                paths.imported_workflow_bundles_path,
            ),
            ("command_boundaries_path", paths.command_boundaries_path),
        ),
        configuration_revisions=configuration.configuration_trace.revision_vector,
        recursively_imported_source_revisions=(
            configuration.source_read_trace.revision_vector
        ),
        builtin_stdlib_source_root=state.builtin_stdlib_source_root,
    )
    return LspCompileDriver(
        state=replace(state, configuration_vector=vector),
        initialization_configuration=configuration,
        frozen_form_completions=frozen_form_completions,
        _build_in_memory=build_in_memory,
        _queue=[],
        _latest_generation_by_path={},
        _log_server_error=log_server_error,
    )


def probe_raw_revision(path: str | Path) -> tuple[Path, str]:
    """Read one path once and return its exact raw-byte revision or sentinel."""

    canonical_path, _raw_bytes, revision = _read_raw_revision(path)
    return canonical_path, revision


def recheck_raw_revision_vector(
    expected_revisions: tuple[tuple[Path, str], ...],
) -> bool:
    """Read every unique expected path once and compare exact raw revisions."""

    expected_by_path: dict[Path, str] = {}
    for raw_path, expected_revision in expected_revisions:
        canonical_path = Path(raw_path).resolve(strict=False)
        previous = expected_by_path.setdefault(canonical_path, expected_revision)
        if previous != expected_revision:
            return False
    observed = tuple(
        probe_raw_revision(path)
        for path in sorted(expected_by_path, key=lambda item: item.as_posix())
    )
    return observed == tuple(
        sorted(expected_by_path.items(), key=lambda item: item[0].as_posix())
    )


def probe_disk_source(path: str | Path) -> DiskSourceSnapshot:
    """Read one source once and retain its exact revision and decoded text."""

    canonical_path, raw_bytes, revision = _read_raw_revision(path)
    if raw_bytes is None:
        return DiskSourceSnapshot(
            canonical_path=canonical_path,
            revision=revision,
            raw_decoded_text=None,
        )
    try:
        raw_decoded_text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raw_decoded_text = None
    return DiskSourceSnapshot(
        canonical_path=canonical_path,
        revision=revision,
        raw_decoded_text=raw_decoded_text,
    )


def _read_raw_revision(path: str | Path) -> tuple[Path, bytes | None, str]:
    canonical_path = Path(path).resolve(strict=False)
    try:
        raw_bytes = canonical_path.read_bytes()
    except FileNotFoundError:
        return canonical_path, None, "missing"
    except OSError:
        return canonical_path, None, "unreadable"
    revision = f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
    return canonical_path, raw_bytes, revision


def _path_is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_trace_paths_within_roots(
    revision_vector: tuple[tuple[Path, str], ...],
    *,
    workspace_root: Path,
    builtin_stdlib_source_root: Path,
) -> None:
    allowed_roots = (
        workspace_root.resolve(strict=False),
        builtin_stdlib_source_root.resolve(strict=False),
    )
    for raw_path, _revision in revision_vector:
        path = raw_path.resolve(strict=False)
        if any(_path_is_within(path, root) for root in allowed_roots):
            continue
        raise RuntimeError(
            f"compiler trace path `{path}` is outside the initialized roots"
        )
