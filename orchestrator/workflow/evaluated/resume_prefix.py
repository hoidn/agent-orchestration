"""Read-only resume prefix discovery and validation, moved out of `runtime.py`.

None of these helpers appends a memo record except through the run-ref reconcile
owner (`reconcile_evaluated_run_ref`), so every `runtime.append_record` kill-point
hook is unaffected. `runtime` imports them back under the same names.
"""

from __future__ import annotations

import logging

from orchestrator.workflow.run_ref.contracts import canonical_sha256

from . import agent_guards, effect_inputs
from .memo import MemoError, read_memo
from .replay import discover_prefix


def _runtime():
    """`reconcile_evaluated_run_ref` and `_resume_refusal` are called through `runtime`, the names existing
    spies and patches observe (they predate this module)."""
    from . import runtime
    return runtime

logger = logging.getLogger(__name__)


def _replay_resume_prefix(authority, inputs, *, run_id, workspace, provider_io, site_classes):
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    prefix = discover_prefix(authority, snapshot, inputs=inputs, run_id=run_id, provider_io=provider_io)
    _validate_discovered_prefix(authority, prefix, snapshot, workspace, site_classes, defer_parallel_fault=True)
    from .parallel import has_parallel
    if has_parallel(authority.program):
        from .run_ref import inventory_parallel_run_ref_recovery
        obligations = [reached for reached in prefix.commits if reached.node["class"] == "run_ref"
            and (reached.identity, reached.commit.data["attempt"]) not in snapshot.settlements]
        inventory_parallel_run_ref_recovery(authority, obligations, workspace)
    return snapshot, commits, len(prefix.commits), prefix.value, not prefix.halted


def _prepare_parallel_recovery(authority, inputs, run_id, workspace, provider_io, site_classes):
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    if not snapshot.entries:
        return frozenset()
    prefix = discover_prefix(authority, snapshot, inputs=inputs, run_id=run_id, provider_io=provider_io)
    _validate_discovered_prefix(authority, prefix, snapshot, workspace, site_classes, defer_parallel_fault=True)
    run_ref_obligations = []
    for reached in prefix.commits:
        if reached.node['class'] == 'run_ref' and (reached.identity, reached.commit.data['attempt']) not in snapshot.settlements:
            run_ref_obligations.append(reached)
    from .run_ref import inventory_parallel_run_ref_recovery, resolve_run_ref_input
    inventory_parallel_run_ref_recovery(authority, run_ref_obligations, workspace)
    for reached in run_ref_obligations:
        resolved, _parts = resolve_run_ref_input(reached.node, reached.operands)
        _runtime().reconcile_evaluated_run_ref(authority, resolved, reached.identity, workspace, reached.commit, site_classes)
    return frozenset(reached.identity for reached in prefix.frontiers)


def _validate_discovered_prefix(authority, prefix, snapshot, workspace, site_classes, *, defer_parallel_fault=False):
    for reached in sorted(prefix.commits, key=lambda reached: reached.commit.offset):
        effect_inputs._replay_committed_effect(authority, reached.node, reached.operands,
            reached.identity, reached.reader, reached.commit, workspace, snapshot, reached.owner,
            launch_workspace=reached.launch_workspace)
    agent_guards.validate_prefix_receipts(authority, snapshot, site_classes)
    frontiers = frozenset(reached.identity for reached in prefix.frontiers)
    for reached in prefix.frontiers:
        effect_inputs._check_resume_boundary(authority, snapshot, reached.node, reached.operands,
            reached.identity, reached.reader, workspace, reached.owner, reached_frontiers=frontiers,
            launch_workspace=reached.launch_workspace)
    if prefix.fault is not None and not (defer_parallel_fault and prefix.fault_in_parallel):
        raise prefix.fault


def _resume_refusal(exc: Exception) -> tuple[int, None]:
    code = getattr(exc, "code", "resume_preflight_failed")
    logger.error("[%s] %s", code, str(exc) or code)
    return 2, None


def _replayed_halt_result(snapshot, value, reached_boundary):
    if reached_boundary:
        return None
    if snapshot.pending_starts:
        return _runtime()._resume_refusal(
            MemoError("memo_inconsistent", "evaluated halt leaves active effect evidence unsettled")
        )
    terminal = snapshot.terminal
    if terminal is None or terminal.data["outcome"] != "completed":
        return None
    if canonical_sha256(value) != canonical_sha256(terminal.data["value"]):
        return _runtime()._resume_refusal(MemoError("memo_inconsistent", "completed terminal differs from evaluated halt"))
    return 0, terminal.data["value"]
