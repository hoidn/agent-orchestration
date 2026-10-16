"""Bounded item evaluation with one parent publication coordinator."""

from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, replace
from queue import Queue
import re
from threading import get_ident

from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.providers.registry import ProviderRegistry

from . import effect_execution, effect_inputs, run_ref
from .machine import site_nodes
from .memo import MemoError, read_memo
from .values import EvaluatedValue, coerce_evaluated_value
from .views import ViewPublicationError


class ParallelPublicationError(RuntimeError):
    preflight = True
    publication_failure = True

    def __init__(self, cause):
        super().__init__(str(cause))
        self.code = getattr(cause, 'code', 'evaluated_publication_failed')


@dataclass(frozen=True)
class _Item:
    machine: object
    node: object
    environment: object
    owner: str
    activation: tuple
    loops: tuple
    workspace: EvaluatedValue
    sites: tuple


def has_parallel(program):
    bodies = [program.tree['body'], *(row['body'] for row in program.tree['definitions'].values())]
    return any(node.get('k') == 'par-map' for body in bodies for node in _ast_nodes(body))


def _partial_identity(machine, path, loops):
    ordinals = iter(index for _, index in loops)
    return re.sub(r'\[\*\]', lambda match: f'[{next(ordinals)}]', path, count=len(loops))


def _item_sites(machine, body, activation, loops):
    sites = []
    for node in _ast_nodes(body):
        if node.get('k') == 'perform':
            path = machine._identity((*activation, *machine._segments(node['site'])))
            concrete = _partial_identity(machine, path, loops)
            pattern = re.escape(concrete).replace(r'\[\*\]', r'\[\d+\]')
            sites.append((re.compile(pattern), node))
        elif node.get('k') == 'call':
            frame = node.get('frame')
            child = activation if frame is None else (*activation, *machine._segments(frame))
            sites.extend(_item_sites(machine, machine.program.tree['definitions'][node['callee']]['body'], child, loops))
    return tuple(sites)


def _items(machine, node, environment, owner, activation, loops, root):
    source = machine._parallel_source(node, environment, owner, activation, loops)
    items, directories = [], {}
    for index, item in enumerate(source.value):
        local, workspace = machine._parallel_item(node, environment, owner, activation, loops,
            index, item, source)
        directory = effect_inputs.resolve_launch_cwd(root, workspace)
        if directory in directories:
            raise machine._error('parallel_workspace_shared',
                f'parallel items {directories[directory]} and {index} resolve to {directory}', node)
        directories[directory] = index
        item_loops = (*loops, (node['label'], index))
        items.append(_Item(machine, node, local, owner, activation, item_loops, workspace,
            _item_sites(machine, node['body'], activation, item_loops)))
    return source, items


class _Worker:
    def __init__(self, coordinator, token):
        self.coordinator, self.token = coordinator, token

    def __call__(self, node, operands, identity, owner, reader, **kwargs):
        prepared = self.coordinator.request('prepare', self.token, node, operands, identity, owner, reader, kwargs)
        if isinstance(prepared, EvaluatedValue):
            return prepared
        attempt, lifecycle = prepared
        try:
            try:
                outcome = self._perform(attempt, lifecycle)
            except Exception as exc:
                return self.coordinator.request('finish', self.token, attempt, None, exc)
            return self.coordinator.request('finish', self.token, attempt, outcome, None)
        finally:
            attempt.attempt_files.close()

    def _perform(self, attempt, lifecycle):
        if lifecycle is None:
            return effect_execution.perform_external(attempt)
        request, allocation, started = lifecycle
        from orchestrator.workflow.run_ref.runtime import drive_run_ref_lifecycle
        prepared = drive_run_ref_lifecycle(request, allocation=allocation, started_monotonic_ns=started,
            acknowledge=lambda event: self.coordinator.request('event', self.token, request, event))
        return effect_execution.ExternalOutcome(run_ref=prepared)

    def parallel_map(self, *args):
        return self.coordinator.parallel_map(*args)


def _evaluate_item(coordinator, token, item):
    machine = replace(item.machine, effect_handler=_Worker(coordinator, token), launch_workspace=item.workspace)
    result = machine._body(item.node['body'], item.environment, item.owner, item.activation, item.loops)
    result = machine._coerce_result(result, item.node['result']['item'], item.node)
    return machine._add_dependencies(result, item.workspace.dependencies)


def _durably_failed(snapshot, attempt):
    return (attempt.identity not in snapshot.pending_starts
        and attempt.identity not in snapshot.active_commits
        and (attempt.identity, attempt.ordinal) not in snapshot.unsettled_coordinators
        and any(row.data['record'] == 'failed' and row.data['identity'] == attempt.identity
            and row.data['attempt'] == attempt.ordinal for row in snapshot.entries))


class ParallelCoordinator:
    def __init__(self, serial, authority, context, *, frontiers=()):
        self.serial, self.authority, self.context = serial, authority, context
        self.thread = get_ident()
        self.queue = Queue()
        self.items = {}
        self.active = {}
        self.frontiers = set(frontiers)
        self.e1_owner = None
        self.e1_lifecycle = None
        self.e1_sequence = 1
        self.e1_ack = None
        self.deferred = deque()
        self.granting_deferred = False
        self.fatal = None
        self.checked_sites = site_nodes(authority.program)

    def __call__(self, *args, **kwargs):
        return self.serial(*args, **kwargs)

    def request(self, kind, *args):
        reply = Future()
        request = (kind, args, reply)
        if get_ident() == self.thread:
            self._service(request)
        else:
            self.queue.put(request)
        return reply.result()

    def parallel_map(self, machine, node, environment, owner, activation, loops):
        source, items = _items(machine, node, environment, owner, activation, loops, self.context['workspace'])
        if not items:
            return coerce_evaluated_value([], node['result'], dependencies=source.dependencies)
        tokens = self.request('register', items)
        with ThreadPoolExecutor(max_workers=node['parallel']) as pool:
            futures = [pool.submit(_evaluate_item, self, token, item) for token, item in zip(tokens, items)]
            for future in futures:
                future.add_done_callback(lambda done: self.queue.put(('wake', (), None)))
            if get_ident() == self.thread:
                try:
                    self._drain(futures)
                except BaseException as exc:
                    self._stop(exc)
                    self._drain(futures)
            results = self._results(futures)
        self.request('unregister', tokens)
        dependencies = source.dependencies | frozenset(d for result in results for d in result.dependencies)
        return coerce_evaluated_value([result.json_value() for result in results], node['result'], dependencies=dependencies)

    def _results(self, futures):
        results, failures = [], []
        for future in futures:
            try:
                results.append(future.result())
            except BaseException as exc:
                failures.append(exc)
        if self.fatal is not None:
            raise self.fatal
        if failures:
            raise failures[0]
        return results

    def _drain(self, futures):
        while not all(future.done() for future in futures):
            self._service(self.queue.get())
        while not self.queue.empty():
            self._service(self.queue.get_nowait())

    def _service(self, request):
        kind, args, reply = request
        if kind == 'wake':
            return
        if self.fatal is not None:
            reply.set_exception(self.fatal)
            return
        if kind == 'prepare' and args[1]['class'] == 'run_ref' and self.e1_owner is not None:
            self.deferred.append(request)
            return
        try:
            result = getattr(self, '_' + kind)(*args)
        except BaseException as exc:
            try:
                fatal = self._fatal_request(kind, args, exc)
            except BaseException as classification_error:
                exc, fatal = classification_error, True
            if fatal:
                self._stop(exc)
            reply.set_exception(self.fatal or exc)
        else:
            reply.set_result(result)
        self._grant_deferred()

    def _fatal_request(self, kind, args, exc):
        if kind == 'event' or isinstance(exc, (ParallelPublicationError, ViewPublicationError)) or getattr(exc, 'code', '') == 'reserved_run_root_changed':
            return True
        if kind == 'finish':
            attempt = args[1]
            snapshot = self._snapshot()
            return not _durably_failed(snapshot, attempt)
        if kind == 'prepare' and args[3] in self.active:
            return True
        if kind == 'prepare' and getattr(exc, 'code', '') in {'run_ref_ledger_invalid', 'run_ref_child_launch_failed'}:
            return True
        return isinstance(exc, (OSError, MemoError, ViewPublicationError))

    def _stop(self, exc):
        self.fatal = exc if isinstance(exc, ParallelPublicationError) else ParallelPublicationError(exc)
        while self.deferred:
            self.deferred.popleft()[2].set_exception(self.fatal)

    def _grant_deferred(self):
        if self.granting_deferred:
            return
        self.granting_deferred = True
        try:
            while self.fatal is None and self.e1_owner is None and self.deferred:
                self._service(self.deferred.popleft())
        finally:
            self.granting_deferred = False

    def _register(self, items):
        tokens = []
        for item in items:
            if item.machine.program is not self.authority.program:
                raise MemoError('memo_inconsistent', 'parallel item lacks checked program authority')
            token = object()
            self.items[token] = item
            tokens.append(token)
        return tokens

    def _unregister(self, tokens):
        for token in tokens:
            self.items.pop(token, None)

    def _owned_identity(self, token, node, identity):
        item = self.items.get(token)
        if item is None or not any(pattern.fullmatch(identity) and checked is node for pattern, checked in item.sites):
            raise MemoError('memo_inconsistent', 'effect does not belong to its registered parallel item')
        static = re.sub(r'\[\d+\]', '[*]', identity)
        if self.checked_sites.get(static) is not node:
            raise MemoError('memo_inconsistent', 'parallel effect identity differs from checked site')
        return item

    def _prepare(self, token, node, operands, identity, owner, reader, kwargs):
        from . import runtime
        if node.get("class") == "provider_phased":
            raise MemoError('parallel_provider_boundary', 'phased provider cannot execute inside a parallel item')
        self._owned_identity(token, node, identity)
        if identity in self.active:
            raise MemoError('memo_inconsistent', 'parallel identity is already active')
        context = dict(self.context, owner=owner, reader=reader, **kwargs)
        context['provider_executor'] = (ProviderExecutor(context['workspace'], ProviderRegistry(),
            provider_observation_enabled=False) if node['class'] == 'provider' else None)
        snapshot = self._snapshot()
        owned_unsettled = self.e1_owner is not None and all(
            self.active.get(identity) is self.e1_owner for identity, _attempt in snapshot.unsettled_coordinators)
        effect_inputs._ensure_effect_can_start(snapshot, identity,
            reached_frontiers=frozenset(self.frontiers | self.active.keys()),
            allow_unsettled=owned_unsettled)
        attempt = runtime.prepare_effect(self.authority, node, operands, identity,
            parallel_frontiers=frozenset(self.frontiers | self.active.keys()),
            parallel_unsettled=owned_unsettled, **context)
        if isinstance(attempt, EvaluatedValue):
            return attempt
        self.active[identity] = token
        if node['class'] == 'run_ref':
            self.e1_owner = token
            try:
                lifecycle = run_ref.prepare_parallel_run_ref(attempt)
                self.e1_lifecycle, self.e1_sequence, self.e1_ack = lifecycle, 1, None
            except Exception as exc:
                if not run_ref.parallel_run_ref_preparation_failure_is_ordinary(exc):
                    attempt.attempt_files.close()
                    raise ParallelPublicationError(exc) from exc
                return self._finish(token, attempt, None, exc)
        else:
            lifecycle = None
        return attempt, lifecycle

    def _event(self, token, request, event):
        if token is not self.e1_owner or self.e1_lifecycle is None or request is not self.e1_lifecycle[0]:
            raise MemoError('memo_inconsistent', 'run-reference event has no active coordinator owner')
        acknowledgement = run_ref.persist_parallel_run_ref_event(self.e1_lifecycle, event,
            self.e1_sequence, self.e1_ack)
        self.e1_sequence += 1
        self.e1_ack = acknowledgement
        return acknowledgement

    def _finish(self, token, attempt, outcome, error):
        from . import runtime
        if self.active.get(attempt.identity) is not token:
            raise MemoError('memo_inconsistent', 'attempt has no registered item owner')
        successful = False
        try:
            if error is not None and run_ref.parallel_run_ref_authority_failure(error):
                raise ParallelPublicationError(error) from error
            result = runtime.finish_effect(attempt, outcome, error=error, fatal_publication=True)
            successful = True
            return result
        finally:
            snapshot = self._snapshot()
            if (successful or _durably_failed(snapshot, attempt)) and attempt.identity not in snapshot.pending_starts and (attempt.identity, attempt.ordinal) not in snapshot.unsettled_coordinators:
                self.active.pop(attempt.identity, None)
                self.frontiers.discard(attempt.identity)
                if self.e1_owner is token:
                    self.e1_owner = None
                    self.e1_lifecycle = None

    def _snapshot(self):
        return read_memo(self.authority.memo_path, self.context['site_classes'], run_files=self.authority.run_files)
