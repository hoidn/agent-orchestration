"""Read reached effect prefixes using stored values and structured order."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from orchestrator.workflow.pure_expr import PureExprEvaluationError

from .authority import workspace_result_locator
from .effect_inputs import effect_dependencies
from .machine import evaluate_closed_program
from .memo import JournalEntry, MemoError
from .memo_reducer import is_coordinator_class
from .provider_io import WorkflowIOReader
from .values import EvaluatedValue, coerce_evaluated_value


class MissingCommit(Exception):
    def __init__(self, identity: str):
        self.identity = identity


@dataclass(frozen=True)
class ReachedEffect:
    node: Mapping[str, Any]
    operands: tuple[EvaluatedValue, ...]
    identity: str
    owner: str
    reader: WorkflowIOReader | None
    commit: JournalEntry | None = None
    launch_workspace: EvaluatedValue | None = None


@dataclass
class _Order:
    predecessors: tuple[JournalEntry, ...] = ()
    parallel: bool = False
    map_barrier: int | float = -1


@dataclass
class Prefix:
    commits: list[ReachedEffect] = field(default_factory=list)
    frontiers: list[ReachedEffect] = field(default_factory=list)
    value: Any = None
    halted: bool = False
    fault: PureExprEvaluationError | None = None
    fault_in_parallel: bool = False


class _Discovery:
    def __init__(self, authority, snapshot):
        self.authority = authority
        self.snapshot = snapshot
        self.prefix = Prefix()
        self.consumed = set()
        self.frontiers = set()
        self.item_faults = set()
        self.order = _Order()
        self.starts = {}
        self.settlements = {}
        self.agent_cursor = {}
        for entry in snapshot.entries:
            row = entry.data
            if row['record'] in {'started', 'settled'}:
                key = row['identity'], row['attempt']
                target = self.starts if row['record'] == 'started' else self.settlements
                target[key] = entry

    def __call__(self, node, operands, identity, owner, reader, *, launch_workspace=None):
        if identity in self.consumed or identity in self.frontiers:
            raise MemoError('memo_inconsistent', 'effect identity is reached more than once')
        commit = self.snapshot.active_commits.get(identity)
        reached = ReachedEffect(node, operands, identity, owner, reader, commit, launch_workspace)
        if commit is None:
            self._frontier(reached)
            raise MissingCommit(identity)
        self._check_order(commit)
        dependencies = self._advance_agent_cursor(commit, effect_dependencies(operands, launch_workspace))
        if dependencies != commit.data['depends_on']:
            raise MemoError('memo_inconsistent', 'committed dependencies differ from reached operands')
        self.consumed.add(identity)
        self.prefix.commits.append(reached)
        self.order.predecessors = (commit,)
        return committed_value(self.authority, node, commit, identity, started=self.starts[(identity, commit.data["attempt"])], operands=operands)

    def _advance_agent_cursor(self, commit, dependencies):
        """Logical cursor: an `agent_turn` commit names the agent's previous replayed turn as its predecessor (and
        dependency), then becomes the agent's head. No native read: later turns may already exist natively."""
        if commit.data['effect_class'] != 'agent_turn':
            return dependencies
        proof = commit.data['proof']
        head = self.agent_cursor.get(proof['agent'])
        if proof['predecessor'] != head:
            raise MemoError('memo_inconsistent', 'agent turn predecessor differs from the replayed agent cursor')
        self.agent_cursor[proof['agent']] = commit.data['identity']
        return sorted(set(dependencies) | ({head} if head else set()))

    def _frontier(self, reached):
        self.frontiers.add(reached.identity)
        self.prefix.frontiers.append(reached)
        pending = self.snapshot.pending_starts.get(reached.identity)
        if pending is not None:
            if reached.node['class'] == 'request_input':
                from .host_input import validate_checked_request
                validate_checked_request(self.authority, reached.node, pending, operands=reached.operands)
            self._check_order(pending, committed=False)

    def _check_order(self, entry, *, committed=True):
        key = entry.data['identity'], entry.data['attempt']
        start = self.starts[key]
        for predecessor in self.order.predecessors:
            if committed and entry.offset <= predecessor.offset:
                raise MemoError('memo_inconsistent', 'active commits are not reachable in journal order')
            if self.order.parallel:
                barrier = self._settled_offset(predecessor)
                if start.offset <= barrier:
                    raise MemoError('memo_inconsistent', 'effect starts before its structured predecessor completes')
        if start.offset <= self.order.map_barrier:
            raise MemoError('memo_inconsistent', 'effect starts before its structured predecessor completes')

    def _settled_offset(self, commit):
        if not is_coordinator_class(commit.data['effect_class']):
            return commit.offset
        key = commit.data['identity'], commit.data['attempt']
        settlement = self.settlements.get(key)
        return float('inf') if settlement is None else settlement.offset

    def parallel_map(self, machine, node, environment, owner, activation, loops):
        source = machine._parallel_source(node, environment, owner, activation, loops)
        outer = self.order
        commits_before = len(self.prefix.commits)
        tails, results, faults = [], [], []
        try:
            for index, item in enumerate(source.value):
                self.order = _Order(outer.predecessors, True, outer.map_barrier)
                try:
                    result = self._item(machine, node, environment, owner, activation, loops, index, item, source)
                    results.append(result)
                except (MissingCommit, PureExprEvaluationError) as exc:
                    faults.append(exc)
                tails.extend(self.order.predecessors)
        finally:
            self.order = outer
        self._complete_map(outer, tails, commits_before)
        if faults:
            raise faults[0]
        dependencies = source.dependencies | frozenset(d for result in results for d in result.dependencies)
        return coerce_evaluated_value([result.json_value() for result in results],
            node['result'], dependencies=dependencies, context='parallel map result')

    def _complete_map(self, outer, tails, commits_before):
        if len(self.prefix.commits) == commits_before:
            return
        outer.predecessors = tuple({entry.offset: entry for entry in tails}.values())
        outer.map_barrier = max(outer.map_barrier, *(self._settled_offset(entry) for entry in tails))

    def _item(self, machine, node, environment, owner, activation, loops, index, item, source):
        local, workspace = machine._parallel_item(node, environment, owner, activation, loops,
            index, item, source)
        item_machine = replace(machine, launch_workspace=workspace)
        try:
            result = item_machine._body(node['body'], local, owner, activation, (*loops, (node['label'], index)))
        except PureExprEvaluationError as exc:
            self.item_faults.add(exc)
            raise
        result = machine._coerce_result(result, node['result']['item'], node)
        return machine._add_dependencies(result, workspace.dependencies | source.dependencies)

    def finish(self):
        if self.consumed != set(self.snapshot.active_commits):
            raise MemoError('memo_inconsistent', 'an active commit is unreachable from the evaluated program')
        if set(self.snapshot.pending_starts) - self.frontiers:
            raise MemoError('memo_inconsistent', 'a pending start is unreachable from the evaluated program')


def committed_value(authority, node, commit, identity, *, started=None, operands=None):
    if node['class'] == 'request_input':
        from .host_input import validate_checked_request
        if started is None:
            raise MemoError('memo_inconsistent', 'host replay requires its matching start')
        validate_checked_request(authority, node, started, commit, operands=operands)
    try:
        return coerce_evaluated_value(commit.data['value'], node['result'],
            dependencies=(*commit.data['depends_on'], identity),
            committed_result_path=workspace_result_locator(authority.header, commit.data['result_path']),
            context=f"committed {node['class']} result")
    except PureExprEvaluationError as exc:
        raise MemoError('memo_inconsistent', str(exc)) from exc


def discover_prefix(authority, snapshot, *, inputs=None, run_id=None, provider_io=None,
                    evaluate=evaluate_closed_program):
    discovery = _Discovery(authority, snapshot)
    arguments = dict(effect_handler=discovery, run_id=run_id or authority.header['run_id'])
    if provider_io is not None:
        arguments['provider_io'] = provider_io
    try:
        result = evaluate(authority.program,
            authority.header['bound_inputs'] if inputs is None else inputs, **arguments)
        discovery.prefix.value = result.json_value()
        discovery.prefix.halted = True
    except MissingCommit:
        pass
    except PureExprEvaluationError as exc:
        discovery.prefix.fault = exc
        discovery.prefix.fault_in_parallel = exc in discovery.item_faults
    discovery.finish()
    return discovery.prefix
