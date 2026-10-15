"""Receipt-based agent guards (R1): the C8 write preflight and the resume-time prefix receipt check.

Depends on: the snapshot's journal entries, the checked site table, and each uncommitted agent attempt's
`receipt.json` / `abandoned.json` under the retained run root (`run_files.subroot`). The journal-only part of the
preflight *is* the reducer's `memo_reducer_agents.check_invalidation_cut`, so an `invalidated` row the preflight
admits always reduces; the receipt rules only add refusals. Committed turns are never checked against receipts:
their inline proof is the sole continuation authority. Every function reads; none writes.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from .agent_sessions import Receipt, read_receipt
from .memo_reducer import MemoError, _DYNAMIC_INDEX
from .memo_reducer_agents import DISPATCHED_FAILURE_CODES, check_invalidation_cut

_UNDISPATCHED = {"intent", "not_dispatched"}
_AFTER_DISPATCH = {"abandoned", "completed", "unknown"}


def check_invalidation_suffix(snapshot, chosen, run_files, site_classes) -> None:
    """Refuse a cut at `chosen` over agent attempt history before any write (C8, Agent Sessions).

    Only attempts started at or after the cut are affected (start order). An attempt started before the cut cannot
    depend on the suffix: the reducer requires an active allocation before a turn starts (`check_started`) and an
    active predecessor before it commits (`check_committed_proof`), so its real allocation and predecessor precede the
    cut; a receipt naming a later re-commit of the same identity is stale (R7). Raises
    `invalidate_agent_session_advanced` for a pending, dispatched, advanced or uncertain attempt in the suffix, and
    `memo_inconsistent` for an unreadable required receipt: that of an attempt in the suffix closed `failed` with a
    non-dispatched code.
    """
    cut = chosen.offset
    journal = SimpleNamespace(entries=snapshot.entries, site_class=lambda identity: _site_class(site_classes, identity),
                              inconsistent=_advanced_by_journal)
    check_invalidation_cut(journal, cut)        # the reducer's own rule: pending or dispatched-failure starts at/after the cut
    for entry, closing in _uncommitted_agent_attempts(snapshot, site_classes):
        if entry.offset < cut:
            continue
        row = entry.data                        # closed `failed` with a non-dispatched code: the journal rule passed
        receipt = _receipt(run_files, row)
        if receipt is not None and receipt.completion not in _UNDISPATCHED:
            raise MemoError("invalidate_agent_session_advanced", f"agent turn {row['identity']} #{row['attempt']} failed "
                            f"({closing['code']}) after launch; its receipt records {receipt.completion}")


def validate_prefix_receipts(authority, snapshot, site_classes) -> None:
    """At resume, receipts of pending and dispatched-failure agent attempts must agree with the journal
    (`memo_inconsistent`); a failed attempt with a non-dispatched code is never consulted."""
    for entry, closing in _uncommitted_agent_attempts(snapshot, site_classes):
        if closing is not None and closing["code"] not in DISPATCHED_FAILURE_CODES:
            continue
        row = entry.data
        problem = _receipt_disagreement(authority.run_files, row, closing, _receipt(authority.run_files, row))
        if problem is not None:
            raise MemoError("memo_inconsistent", f"agent turn {row['identity']} #{row['attempt']} {problem}")


def _receipt_disagreement(run_files, row, closing, receipt: Receipt | None) -> str | None:
    if receipt is not None and (receipt.turn, receipt.attempt, receipt.input_digest) != (
            row["identity"], row["attempt"], row["input_digest"]):
        return "has a receipt that disagrees with its started row"
    code = None if closing is None else closing["code"]
    if code in DISPATCHED_FAILURE_CODES and getattr(receipt, "completion", None) not in _AFTER_DISPATCH:
        return f"failed after dispatch ({code}) without a dispatched receipt"
    if code == "agent_bootstrap_restarted" and not run_files.exists(Path(row["result_path"]).parent / "abandoned.json"):
        return "was restarted by bootstrap without abandoned.json"
    return None


def _advanced_by_journal(detail: str) -> MemoError:
    return MemoError("invalidate_agent_session_advanced", f"{detail}; resume first: a pending agent turn must be "
                     "reconciled before its prefix can be cancelled, and a dispatched attempt's native history is never cut")


def _uncommitted_agent_attempts(snapshot, site_classes):
    """(`started` entry, closing `failed` row or None) for every agent turn attempt that did not commit."""
    closing = {(e.data["identity"], e.data["attempt"]): e.data for e in snapshot.entries
               if e.data["record"] in {"committed", "failed"}}
    for entry in snapshot.entries:
        row = entry.data
        if row["record"] != "started" or _site_class(site_classes, row["identity"]) != "agent_turn":
            continue
        closed = closing.get((row["identity"], row["attempt"]))
        if closed is None or closed["record"] == "failed":
            yield entry, closed


def _receipt(run_files, row) -> Receipt | None:
    """The attempt's receipt, or None when there is none (`started` precedes the attempt directory)."""
    if run_files is None:
        raise MemoError("memo_inconsistent", "agent attempt receipts can only be read under the retained run root")
    directory = Path(row["result_path"]).parent
    if not run_files.exists(directory):
        return None
    files = run_files.subroot(directory)
    try:
        return read_receipt(files)                 # malformed or unreadable -> memo_inconsistent
    finally:
        files.close()


def _site_class(site_classes, identity: str) -> str | None:
    return site_classes.get(identity) or site_classes.get(_DYNAMIC_INDEX.sub("[*]", identity))
