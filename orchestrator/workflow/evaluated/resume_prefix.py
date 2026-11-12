"""Read-only resume prefix discovery and validation, moved out of `runtime.py`.

None of these helpers appends a memo record except through the run-ref reconcile
owner (`reconcile_evaluated_run_ref`), so every `runtime.append_record` kill-point
hook is unaffected. `runtime` imports them back under the same names.
"""

from __future__ import annotations

import logging

from orchestrator.workflow.run_ref.contracts import canonical_sha256

from . import agent_guards, effect_inputs
from .attempts import accepted_attempt_lines, unproven_command_retries
from .closure import resolve_command_evidence
from .memo import MemoError, read_memo
from .replay import discover_prefix


def _runtime():
    """`reconcile_evaluated_run_ref` and `_resume_refusal` are called through `runtime`, the names existing
    spies and patches observe (they predate this module)."""
    from . import runtime
    return runtime

logger = logging.getLogger(__name__)


def checked_resume_prefix(authority, inputs, *, run_id, workspace, provider_io, site_classes, confined=None,
                          snapshot=None):
    """The complete read-only reached-prefix preflight for resume and host settlement.

    `snapshot`: an in-memory reduction to check instead of the journal on disk (the plan's journal as it will be,
    `rebase.py`); None reads the journal."""
    if snapshot is None:
        snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    prefix = discover_prefix(authority, snapshot, inputs=inputs, run_id=run_id, provider_io=provider_io)
    _validate_discovered_prefix(authority, prefix, snapshot, workspace, defer_parallel_fault=True, confined=confined)
    from .parallel import has_parallel
    if has_parallel(authority.program):
        from .run_ref import inventory_parallel_run_ref_recovery
        obligations = [reached for reached in prefix.commits if reached.node["class"] == "run_ref"
            and (reached.identity, reached.commit.data["attempt"]) not in snapshot.settlements]
        inventory_parallel_run_ref_recovery(authority, obligations, workspace)
    return snapshot, prefix


def _replay_resume_prefix(authority, inputs, *, run_id, workspace, provider_io, site_classes, confined=None):
    snapshot, prefix = checked_resume_prefix(authority, inputs, run_id=run_id, workspace=workspace,
        provider_io=provider_io, site_classes=site_classes, confined=confined)
    if authority.accept_changes:
        _require_changes_to_accept(snapshot, prefix, workspace)
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    return snapshot, commits, len(prefix.commits), prefix.value, not prefix.halted


def _require_changes_to_accept(snapshot, prefix, workspace) -> None:
    """The flag needs an unproven command attempt whose declared files differ from its `started` evidence, or one
    preflight does not reach yet (it runs after other steps, as after an `invalidate`): those cannot be rehashed
    before they run, so they count, and are printed now as the flag accepts them unseen."""
    reached = {item.identity: item for item in prefix.frontiers}
    unproven = unproven_command_retries(snapshot)
    unreached = [identity for identity in unproven if identity not in reached]
    if unreached:
        logger.warning("[accept_changes_unreached] --accept-changes also accepts steps resume reaches later, "
                       "with their files as they are then:")
        for line in accepted_attempt_lines(snapshot, unreached):
            logger.warning("%s", line)
    elif not any(_evidence_differs(reached[identity], snapshot.latest_starts[identity], workspace)
                 for identity in unproven):
        raise effect_inputs._PreflightRefusal("resume_preflight_failed",
            "--accept-changes: no unfinished command attempt needs it; resume without the flag")


def _evidence_differs(item, start, workspace) -> bool:
    recorded = start.data["implementation_files"]
    try:
        current = resolve_command_evidence(item.node["command"], item.node["closure"], workspace_root=workspace,
            prior=recorded, launch_cwd=effect_inputs.resolve_launch_cwd(workspace, item.launch_workspace))
    except Exception:  # noqa: BLE001 - the boundary check already refused unreadable evidence; count it, so that check decides
        return True
    return current != recorded


def _prepare_parallel_recovery(authority, inputs, run_id, workspace, provider_io, site_classes, confined=None):
    snapshot = read_memo(authority.memo_path, site_classes, run_files=authority.run_files)
    if not snapshot.entries:
        return frozenset()
    prefix = discover_prefix(authority, snapshot, inputs=inputs, run_id=run_id, provider_io=provider_io)
    _validate_discovered_prefix(authority, prefix, snapshot, workspace, defer_parallel_fault=True, confined=confined)
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


def _validate_discovered_prefix(authority, prefix, snapshot, workspace, *, defer_parallel_fault=False, confined=None, proof_only=False):
    for reached in sorted(prefix.commits, key=lambda reached: reached.commit.offset):
        effect_inputs._replay_committed_effect(authority, reached.node, reached.operands,
            reached.identity, reached.reader, reached.commit, workspace, snapshot, reached.owner,
            launch_workspace=reached.launch_workspace, confined=confined)
    agent_guards.validate_prefix_receipts(authority, snapshot)
    if proof_only:
        return
    frontiers = frozenset(reached.identity for reached in prefix.frontiers)
    for reached in prefix.frontiers:
        effect_inputs._check_resume_boundary(authority, snapshot, reached.node, reached.operands,
            reached.identity, reached.reader, workspace, reached.owner, reached_frontiers=frontiers,
            launch_workspace=reached.launch_workspace, confined=confined)
    if prefix.fault is not None and not (defer_parallel_fault and prefix.fault_in_parallel):
        raise prefix.fault


def _resume_refusal(exc: Exception) -> tuple[int, None]:
    code = getattr(exc, "code", "resume_preflight_failed")
    logger.error("[%s] %s", code, str(exc) or code)
    return 2, None


def _replayed_halt_result(snapshot, value, reached_boundary, refuse):
    if reached_boundary:
        return None
    if snapshot.pending_starts:
        return refuse(
            MemoError("memo_inconsistent", "evaluated halt leaves active effect evidence unsettled")
        )
    terminal = snapshot.terminal
    if terminal is None or terminal.data["outcome"] != "completed":
        return None
    if canonical_sha256(value) != canonical_sha256(terminal.data["value"]):
        return refuse(MemoError("memo_inconsistent", "completed terminal differs from evaluated halt"))
    return 0, terminal.data["value"]
