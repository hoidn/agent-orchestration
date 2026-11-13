"""Plan a resume under an edited program, or after a committed step's input changed (rule C10, Edit and Continue §3,
§5 and §6).

`compute_plan` is read-only. It replays the edited program against the journal leniently to find the cut (the first
commit it does not reuse, or pending start it does not keep), checks every refusal of design §5 on the result, runs
today's strict resume replay on the journal as it will be after the record, and names the plan by a token. Nothing
here writes a file: accepting a plan is Phase 3b T7. `plan_resume` is the read-only library entry (H-G3): a run
root and a workspace in, the plan or its refusal out.

Depends on: the run's checked authority and its journal (`memo.read_memo`), the evaluator (`machine`), resume replay
(`replay._Discovery`, `resume_prefix.checked_resume_prefix`), the C8 guards (`agent_guards`, `run_ref`), the
`declaration` comparison of `declaration.py` (comparison point 3), and the workspace files commands declare, which
are rehashed and never written. Holds no state.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
import hashlib
import json
import logging
from pathlib import Path
import re
import time
from typing import Any

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.pure_expr import PureExprEvaluationError
from orchestrator.workflow.run_ref.contracts import canonical_sha256

from . import effect_inputs
from .declaration import declaration_subject, replay_parts, written_subject
from .machine import evaluate_closed_program, site_classes, site_nodes
from .memo import _encode_record, earlier_tables, read_memo
from .memo_reducer import _DYNAMIC_INDEX, JournalEntry, is_coordinator_class, reduce_memo
from .replay import MissingCommit, _Discovery, discover_prefix

logger = logging.getLogger(__name__)

# Exactly the failures of conditions 2 to 4 that mean "not reusable": order, dependencies, the agent cursor and the
# host payload; the value fit is the one whose cause is a pure coercion fault. Any other `memo_inconsistent` refuses.
_NOT_REUSABLE = frozenset({
    "active commits are not reachable in journal order",
    "effect starts before its structured predecessor completes",
    "committed dependencies differ from reached operands",
    "agent turn predecessor differs from the replayed agent cursor",
    "request contracts differ from checked node",
    "request dependencies differ from reached operands",
    "request differs from reached operands",
    "question differs from reached operand",
})
_FIELDS = ("journal", "program", "cut", "sets")
_TOKEN = re.compile(r"plan-([0-9a-f]{8})-([0-9a-f]{8})-([0-9a-f]{8})-([0-9a-f]{8})")
_PROVIDER_CLASSES = frozenset({"provider", "provider_phased", "agent_turn"})


@dataclass(frozen=True)
class Plan:
    """What accepting would write and do. `record` is `rebased` (an edited program) or `invalidated` (a committed
    step's changed input under the run's program, whose `program` is None); `cut` is the journal offset from which
    commits are cancelled and pending starts retired, or None. `unproven` lists the unfinished command attempts the
    acceptance covers: identity, attempt, and the digest of their declared files as rehashed now, None when replay
    does not reach them yet, and `unproven_reasons` why each is not proven clean. `waiting` holds the pending host
    requests the plan keeps; `costs` each cancelled provider-class commit's priced cost (None: unknown)."""

    record: str
    program: ClosedProgram | None
    cut: int | None
    kept: tuple[JournalEntry, ...]
    cancelled: tuple[JournalEntry, ...]
    retired: tuple[JournalEntry, ...]
    asked_again: tuple[str, ...]
    unproven: tuple[tuple[str, int, str | None], ...]
    runs_first: tuple[str, ...]
    cut_reason: str
    token: str
    unproven_reasons: tuple[str, ...] = ()
    waiting: tuple[str, ...] = ()
    costs: tuple[tuple[str, float | None], ...] = ()
    # The `_EffectInputDiverged` at the cut when a changed input is why it is there; None otherwise.
    divergence: Exception | None = field(default=None, compare=False, repr=False)


class PlanRefusal(ValueError):
    """A plan that cannot be accepted (design §5), with its diagnostic code and the step it names."""

    def __init__(self, code: str, message: str, identity: str | None = None, **details: Any) -> None:
        self.code, self.identity = code, identity
        self.__dict__.update(details)
        super().__init__(message)


def plan_resume(run_root: Path, workspace: Path, *, run_files=None) -> Plan:
    """The plan `resume` would print for this run root and workspace, or the refusal that replaces it (H-G3).

    Read-only: resume preflight steps 1 to 9 as `resume` runs them, then `compute_plan`. Takes no lock; `resume`
    computes the same plan under the run writer lock."""
    from orchestrator.workflow.workspace_files import WorkspaceFiles

    if run_files is not None:
        return _plan_with(Path(run_root), Path(workspace), run_files)
    files = WorkspaceFiles(Path(run_root))      # the retained run-root owner the run-reference and map checks need
    try:
        return _plan_with(Path(run_root), Path(workspace), files)
    finally:
        files.close()


def _plan_with(run_root: Path, workspace: Path, run_files) -> Plan:
    from orchestrator.cli.commands.evaluated import candidate_preflight, prepare_evaluated_resume

    try:
        authority, inputs, provider_io = prepare_evaluated_resume(run_root, workspace=workspace, run_files=run_files)
        candidate = authority.program
    except ValueError as exc:
        if getattr(exc, "code", None) != "resume_program_changed" or not hasattr(exc, "fresh_program"):
            raise
        authority, candidate, inputs, provider_io = candidate_preflight(exc, run_root, workspace, run_files)
    return compute_plan(authority, candidate, inputs, workspace=workspace, provider_io=provider_io)


def compute_plan(authority, candidate: ClosedProgram, inputs, *, workspace: Path, provider_io, diverged=None) -> Plan:
    """Rule C10 for `candidate` against the run's journal, the refusals of design §5, then the strict replay on the
    journal as it will be. Raises `PlanRefusal` (or the strict pass's own coded error) when no plan can be accepted,
    `resume_preflight_failed` when nothing needs accepting.

    `diverged`: the `_EffectInputDiverged` today's strict pass just raised under the run's program (`candidate` is
    that program). That pass compared, in offset order, every reached commit before the divergent one, so neither
    the cut nor the strict replay on the journal as it will be compares them again."""
    rebased = candidate.digest != authority.program.digest
    if rebased:
        _check_candidate(authority, candidate)
    snapshot = read_memo(authority.memo_path, site_classes(authority.program), run_files=authority.run_files)
    planning = _planning_authority(authority, candidate, snapshot) if rebased else authority
    cut, reason, divergence = _cut(planning, snapshot, inputs, workspace, provider_io, diverged)
    if not rebased and cut is None:
        raise PlanRefusal("resume_preflight_failed", "no committed step's input changed under the run's program: "
                          "there is no plan to accept")
    # A cut cancels rows the plan's passes do not read again: check first that the journal is consistent under the
    # program that wrote it, so corrupt evidence refuses (`memo_inconsistent`) and is never cancelled as "not reusable".
    written = None if cut is None else discover_prefix(authority, snapshot)
    kept, cancelled, retired = _split(snapshot, cut)
    _refuse(authority, snapshot, candidate, cut, cancelled, retired, written)
    after = _journal_after(authority, snapshot, candidate if rebased else None, cut)
    prefix = _strict_replay(planning, after, inputs, workspace, provider_io, commits_proven=diverged is not None)
    from .attempts import unproven_reason
    asked = _of_class(snapshot, (*cancelled, *retired), "request_input")
    unproven = _unproven(after, prefix, workspace)
    record = "rebased" if rebased else "invalidated"
    return Plan(record, candidate if rebased else None, cut, kept, cancelled, retired, tuple(map(_id, asked)), unproven,
                tuple(item.identity for item in prefix.frontiers), reason,
                _token(authority, snapshot, candidate, record, cut, cancelled, retired, asked, unproven),
                tuple(unproven_reason(after, identity) for identity, _attempt, _evidence in unproven),
                tuple(map(_id, _of_class(after, after.pending_starts.values(), "request_input"))),
                _costs(authority, snapshot, cancelled), divergence)


def _split(snapshot, cut):
    """(kept commits, cancelled commits, retired pending starts), each in journal order."""
    commits = sorted(snapshot.active_commits.values(), key=lambda entry: entry.offset)
    if cut is None:
        return tuple(commits), (), ()
    pending = sorted(snapshot.pending_starts.values(), key=lambda entry: entry.offset)
    return (tuple(entry for entry in commits if entry.offset < cut), tuple(entry for entry in commits if entry.offset >= cut),
            tuple(entry for entry in pending if entry.offset >= cut))


def _of_class(snapshot, entries, kind: str) -> tuple[JournalEntry, ...]:
    """The rows among `entries` of class `kind` by the program that wrote each."""
    return tuple(entry for entry in entries if snapshot.lineage.class_at(entry.offset, _id(entry)) == kind)


def token_difference(printed: str, current: str) -> list[str]:
    """The names of the token fields (`journal`, `program`, `cut`, `sets`) in which two plan tokens differ."""
    fields = [_TOKEN.fullmatch(token) for token in (printed, current)]
    if None in fields:
        raise ValueError("a plan token is `plan-` and four fields of eight hex digits")
    return [name for name, old, new in zip(_FIELDS, fields[0].groups(), fields[1].groups()) if old != new]


# ---- the cut (rule C10) ------------------------------------------------------------------------------------------

def _id(entry: JournalEntry) -> str:
    return entry.data["identity"]


def _planning_authority(authority, candidate, snapshot):
    """The candidate as the current program, with the run's program in force up to the end of the complete journal,
    where the record would be appended: each existing row is read under the program that wrote it."""
    return replace(authority, program=candidate,
                   earlier=(*authority.earlier, (authority.program, snapshot.complete_bytes)))


class _Lenient:
    """Resume discovery (`replay._Discovery`) that turns exactly the "not reusable" failures into the end of the
    effect's thread, taking back the commit it consumed or the start it reached; records why per identity."""

    def __init__(self, discovery: _Discovery) -> None:
        self.discovery, self.parallel_map, self.why = discovery, discovery.parallel_map, {}

    def __call__(self, node, operands, identity, owner, reader, *, launch_workspace=None):
        snapshot = self.discovery.snapshot
        row = snapshot.active_commits.get(identity) or snapshot.pending_starts.get(identity)
        if row is not None and snapshot.lineage.class_at(row.offset, identity) != node["class"]:
            self.why[identity] = f"it is a {node['class']} step in the edited program"
            raise MissingCommit(identity)                           # condition 1: a site of the same class
        try:
            return self.discovery(node, operands, identity, owner, reader, launch_workspace=launch_workspace)
        except ValueError as exc:         # MemoError, and HostInputError for the host payload check
            detail = _not_reusable(exc)
            if detail is None:
                raise
            self._take_back(identity)
            self.why[identity] = detail
            raise MissingCommit(identity) from exc

    def _take_back(self, identity: str) -> None:
        discovery = self.discovery
        discovery.consumed.discard(identity)
        discovery.frontiers.discard(identity)
        discovery.prefix.commits[:] = [item for item in discovery.prefix.commits if item.identity != identity]
        discovery.prefix.frontiers[:] = [item for item in discovery.prefix.frontiers if item.identity != identity]


def _not_reusable(exc: Exception) -> str | None:
    """The detail of a "not reusable" failure (conditions 2 to 4), None for any other error."""
    if getattr(exc, "code", None) != "memo_inconsistent":
        return None
    if isinstance(exc.__cause__, PureExprEvaluationError):
        return "its stored value does not fit the edited step's result type"
    detail = getattr(exc, "detail", None) or str(exc).removeprefix("memo_inconsistent: ")
    return detail if detail in _NOT_REUSABLE else None


def _cut(planning, snapshot, inputs, workspace, provider_io, known=None):
    """(cut, what is at the cut and why, the divergence when that is why): the smallest offset among commits not
    reused and pending starts not kept."""
    lenient = _Lenient(_Discovery(planning, snapshot))
    try:
        evaluate_closed_program(planning.program, inputs, effect_handler=lenient, run_id=planning.header["run_id"],
                                provider_io=provider_io)
    except (MissingCommit, PureExprEvaluationError):
        pass        # evaluation stops at the first effect it cannot reuse; a pure fault is the strict pass's to report
    discovery = lenient.discovery
    new = [item.identity for item in discovery.prefix.frontiers if item.identity not in snapshot.latest_starts]
    unreached = ("the edited program runs " + ", ".join(new) + " before it") if new else \
        "the edited program does not reach it next"
    stale = [(entry.offset, identity, lenient.why.get(identity, unreached))
             for identity, entry in snapshot.active_commits.items() if identity not in discovery.consumed]
    stale += _pending_not_kept(planning, snapshot, discovery, workspace, lambda identity: lenient.why.get(identity, unreached))
    if known is None:
        diverged = _first_divergence(planning, snapshot, discovery.prefix.commits, workspace,
                                     min(stale)[0] if stale else None)
    else:           # today's strict pass refused here, having compared every commit before it
        diverged = snapshot.active_commits[known.identity].offset, known.identity, _what_changed(known), known
    stale += [diverged[:3]] if diverged is not None else []
    if not stale:
        return None, "", None
    offset, identity, why = min(stale)
    return offset, f"{identity}: {why}", diverged[3] if diverged is not None and diverged[0] == offset else None


def _pending_not_kept(planning, snapshot, discovery, workspace, why_unreached):
    """(offset, identity, why) of each pending start the edited program does not keep."""
    reached = {item.identity: item for item in discovery.prefix.frontiers}
    stale = []
    for identity, pending in snapshot.pending_starts.items():
        why = why_unreached(identity) if identity not in reached else \
            _pending_changed(planning, snapshot, reached[identity], pending, workspace)
        if why is not None:
            stale.append((pending.offset, identity, why))
    return stale


def _first_divergence(planning, snapshot, reused, workspace, before):
    """Condition 5, in journal-offset order up to `before`: the first reused commit whose fresh input differs."""
    for item in sorted(reused, key=lambda item: item.commit.offset):
        if before is not None and item.commit.offset >= before:
            return None
        try:
            effect_inputs._replay_committed_effect(planning, item.node, item.operands, item.identity, item.reader,
                                                   item.commit, workspace, snapshot, item.owner,
                                                   launch_workspace=item.launch_workspace)
        except effect_inputs._EffectInputDiverged as exc:
            return item.commit.offset, item.identity, _what_changed(exc), exc
    return None


def _what_changed(exc) -> str:
    """The parts and files a divergence names, or its own detail when it names neither (a launch directory)."""
    if not exc.changed_parts and not exc.changed_files:
        return f"its input changed ({exc})"
    files = ", ".join(_file_names(exc.changed_files)) or "none"
    return f"its input changed (parts: {', '.join(exc.changed_parts) or 'none'}; files: {files})"


def _file_names(keys) -> list[str]:
    """Implementation-file keys are JSON `[root, path, line]` rows; each path once, in order."""
    names = []
    for key in keys:
        try:
            name = json.loads(key)[1]
        except (ValueError, TypeError, IndexError, KeyError):
            name = key
        if name not in names:
            names.append(name)
    return names


def _pending_changed(planning, snapshot, reached, pending, workspace) -> str | None:
    """Why a pending start reached next at a site of its class is not kept, None when it is: a host request or a
    coordinator attempt must resolve to its `started` input digest (comparison point 3 for the `declaration`)."""
    node = reached.node
    if node["class"] == "request_input":
        from .host_input import resolve_request_input
        parts = dict(resolve_request_input(node, reached.operands, workspace=workspace).input_parts)
    elif is_coordinator_class(node["class"]):
        launch_cwd = effect_inputs.resolve_launch_cwd(workspace, reached.launch_workspace, identity=reached.identity,
                                                      previous=pending)
        resolved, parts, _files = effect_inputs._resolve_effect_input(
            planning, node, reached.operands, reached.identity, workspace, reached.reader, None, pending, None,
            pending.data["result_path"], owner=reached.owner, launch_cwd=launch_cwd, snapshot=snapshot)
        parts = replay_parts(parts, pending.data["input_parts"], declaration_subject(node, resolved),
                             written_subject(planning, pending, node, resolved))          # comparison point 3
    else:
        return None
    return None if canonical_sha256(parts) == pending.data["input_digest"] else "its input changed since it started"


# ---- refusals (design §5) ----------------------------------------------------------------------------------------

def _check_candidate(authority, candidate) -> None:
    """A run keeps its entry workflow, target and representation, and a later program uses only pinned interpreters."""
    from .authority import _emitted_bare_interpreters, _validate_interpreter_pins

    for key, name in (("entry", "entry workflow"), ("target", "target"), ("representation", "representation")):
        before, after = authority.program.tree.get(key), candidate.tree.get(key)
        if before != after:
            raise PlanRefusal("resume_program_changed", f"the edited program's {name} is {after!r}, the run's is "
                              f"{before!r}: a run keeps its entry workflow, target and representation")
    pins = authority.header["interpreters"]
    try:
        _validate_interpreter_pins(candidate, pins, later=True)
    except ValueError as exc:
        unpinned = sorted(set(_emitted_bare_interpreters(candidate)) - set(pins))
        raise PlanRefusal("resume_program_changed", "the edited program uses a bare interpreter the run did not pin: "
                          f"{', '.join(unpinned) or exc}; spell it by path or start a new run") from exc


def _refuse(authority, snapshot, candidate, cut, cancelled, retired, written) -> None:
    """Design §5 on the plan, before anything could be written; each raises its own code."""
    _refuse_repeat(authority, snapshot, candidate, cancelled)
    if cut is None:
        return
    coordinators = [_id(entry) for entry in cancelled if is_coordinator_class(entry.data["effect_class"])]
    if coordinators:
        raise PlanRefusal("invalidate_coordinator_committed", "the plan would cancel a committed run reference, agent "
                          f"turn or phased provider: {', '.join(coordinators)}", coordinators[0], coordinators=coordinators)
    from .agent_guards import check_invalidation_suffix
    from .run_ref import guard_confined_invalidation
    check_invalidation_suffix(snapshot, next(entry for entry in snapshot.entries if entry.offset == cut),
                              authority.run_files)
    guard_confined_invalidation(authority, snapshot, cut, prefix=written)
    if candidate.digest == authority.program.digest:
        return              # under the run's program the range is C8's, which retires such a start (`invalidate`)
    for start in retired:
        if snapshot.lineage.class_at(start.offset, _id(start)) in {"run_ref", "provider_phased"}:
            raise PlanRefusal("resume_program_changed", f"the pending attempt of {_id(start)} would not be kept: restore "
                              "the source and resume, so that it settles under the program that started it", _id(start))


def _refuse_repeat(authority, snapshot, candidate, cancelled) -> None:
    """Decisions 3a and 3b: `must_not_repeat` read in the program that wrote the row and in the edited program."""
    from .attempts import _retry_baseline

    tables: dict[str, dict] = {}

    def never(entry) -> bool:
        for program in (authority.program_at(entry.offset), candidate):
            if program.digest not in tables:
                tables[program.digest] = site_nodes(program)
            table = tables[program.digest]
            node = table.get(_id(entry)) or table.get(_DYNAMIC_INDEX.sub("[*]", _id(entry))) or {}
            if node.get("repeat") == "never":
                return True
        return False

    for commit in cancelled:
        if never(commit):
            raise PlanRefusal("lexical_restore_pending_effect_unsafe", f"{_id(commit)} declares that it must not be "
                              "repeated, and the plan would cancel its commit", _id(commit), committed=True)
    for identity, start in snapshot.latest_starts.items():
        if identity not in snapshot.active_commits and _retry_baseline(snapshot, identity, start) is not None \
                and never(start):
            raise PlanRefusal("lexical_restore_pending_effect_unsafe", f"{identity} declares that it must not be "
                              "repeated, and its last attempt did not finish", identity)


# ---- the journal as it will be -----------------------------------------------------------------------------------

def _journal_after(authority, snapshot, candidate, cut):
    """The complete journal plus the record an acceptance appends, reduced in memory (the artifact is not stored
    yet, so the tables are supplied here)."""
    raw = snapshot.raw[:snapshot.complete_bytes]
    if candidate is None:
        row = {"record": "invalidated", "from_commit": cut, "time": 0.0}
        return reduce_memo(raw + _encode_record(row), site_classes(authority.program), earlier_tables(authority))
    row = {"record": "rebased", "program_digest": candidate.digest, "from_offset": cut, "time": 0.0}
    return reduce_memo(raw + _encode_record(row), site_classes(candidate),
                       (*earlier_tables(authority), site_classes(authority.program)))


def _strict_replay(planning, after, inputs, workspace, provider_io, *, commits_proven=False):
    """Today's resume preflight, unchanged, on the journal as it will be (design §7: the planner is not trusted for
    it). The token binds the unfinished command attempts the plan lists, so their changed files are accepted here as
    the token accepts them. `commits_proven`: today's strict pass has just compared the kept commits' fresh inputs
    (it refused at the cut's commit), so that comparison is not run a second time."""
    from .resume_prefix import checked_resume_prefix

    _snapshot, prefix = checked_resume_prefix(
        replace(planning, accept_changes=True), inputs, run_id=planning.header["run_id"], workspace=workspace,
        provider_io=provider_io, site_classes=site_classes(planning.program), snapshot=after, commits_proven=commits_proven)
    return prefix


def _unproven(after, prefix, workspace) -> tuple[tuple[str, int, str | None], ...]:
    from .attempts import unproven_command_retries

    reached = {item.identity: item for item in prefix.frontiers}
    rows = []
    for identity in unproven_command_retries(after):
        start, item = after.latest_starts[identity], reached.get(identity)
        evidence = None if item is None else canonical_sha256(effect_inputs._resolve_command_implementation(
            item.node, workspace, identity, start.data["implementation_files"], (),
            effect_inputs.resolve_launch_cwd(workspace, item.launch_workspace)))
        rows.append((identity, start.data["attempt"], evidence))
    return tuple(rows)


# ---- the token and the cost --------------------------------------------------------------------------------------

def _token(authority, snapshot, candidate, record, cut, cancelled, retired, asked, unproven) -> str:
    """`plan-` and four fields of eight hex digits (design §6): journal, program, cut, sets."""
    complete = snapshot.raw[:snapshot.complete_bytes]
    last = complete[complete.rfind(b"\n", 0, len(complete) - 1) + 1:]
    values = {
        "journal": [authority.header["run_id"], len(complete), "sha256:" + hashlib.sha256(last).hexdigest()],
        "program": [authority.program.digest, candidate.digest],
        "cut": [record, cut],
        "sets": {"cancelled": [[_id(entry), entry.data["attempt"]] for entry in cancelled],
                 "retired": [[_id(entry), entry.data["attempt"]] for entry in retired],
                 "asked_again": [[_id(entry), _request_id(snapshot, entry)] for entry in asked],
                 "unproven": [list(row) for row in unproven]},
    }
    return "plan-" + "-".join(canonical_sha256(values[name]).removeprefix("sha256:")[:8] for name in _FIELDS)


def _request_id(snapshot, entry) -> str | None:
    start = entry if entry.data["record"] == "started" else next(
        row for row in snapshot.entries if row.data["record"] == "started" and _id(row) == _id(entry)
        and row.data["attempt"] == entry.data["attempt"])
    return start.data.get("host_request", {}).get("request_id")


def _costs(authority, snapshot, cancelled) -> tuple[tuple[str, float | None], ...]:
    """Each cancelled provider-class step's attempts so far, priced as `report` prices a step (None: not metered)."""
    metered = [entry.data for entry in cancelled if snapshot.lineage.class_at(entry.offset, _id(entry)) in _PROVIDER_CLASSES]
    if not metered:
        return ()
    from orchestrator.providers.pricing import load_price_table
    from orchestrator.providers.usage import run_usage

    per_step, _total = run_usage(authority.run_root, metered, load_price_table())
    return tuple((row["identity"], per_step[row["identity"]]["cost_usd"]) for row in metered)


# ---- acceptance: step 10's gate and step 11's write (design §4, §6) ------------------------------------------------

_STALE = {
    "journal": lambda plan: "the journal has new records",
    "program": lambda plan: "the program changed again",
    "cut": lambda plan: f"the cut moved; it is now at {plan.cut_reason}" if plan.cut is not None else "the cut moved",
    "sets": lambda plan: "the cancelled steps, the questions asked again, or the unfinished steps or their files changed",
}


def plan_token_argument(text: str) -> str:
    """argparse `type` of `--accept-changes=TOKEN`. A run id written after the flag is never taken for a token."""
    import argparse

    if _TOKEN.fullmatch(text) is None:
        raise argparse.ArgumentTypeError("expected a plan token; write the run id before --accept-changes")
    return text


def accept_plan(authority, candidate: ClosedProgram, inputs, token: str, *, workspace: Path, provider_io,
                report=None):
    """Accept the plan `token` names, under the run writer lock the caller holds; return the authority in force.

    The plan is recomputed with the full strict pass and compared with the token here, at one place, before any
    write (design §6). Then the edited program is published, or a verified artifact of its digest reused; a torn
    tail is repaired; the record is appended and synchronized; the view is published under the program in force.
    `report(plan)` runs once the record is durable. A failed sync, or any failure after the record, carries
    `change_in_force` ("may" or "is"): the caller stops, dispatches nothing and says so."""
    if authority.confined:
        raise PlanRefusal("resume_program_changed", "a confined run-reference child never changes program; resume "
                          "its parent run")
    plan = compute_plan(authority, candidate, inputs, workspace=workspace, provider_io=provider_io)
    changed = token_difference(token, plan.token)
    if changed:
        raise _stale(authority, candidate, plan, changed)
    entry = _write(authority, plan)
    from .authority import load_run_authority
    from .memo import remember_tables

    try:
        current = load_run_authority(authority.run_root, header=dict(authority.header), run_files=authority.run_files)
        remember_tables(current)
        logger.warning("[changes_accepted] %s: record %s at journal byte %d", token, plan.record, entry.offset)
        if report is not None:
            report(plan)
        _views().publish_evaluated_view(current, entry)
    except Exception as exc:
        exc.change_in_force = "is"
        raise
    return current


def _views():
    from . import views
    return views


def _stale(authority, candidate, plan, changed) -> PlanRefusal:
    """The refusal plain `resume` gives now, naming what changed; it carries the new plan for the recovery lines."""
    why = "; ".join(_STALE[name](plan) for name in changed)
    message = f"the plan token names another plan: {why}"
    if plan.record == "rebased":
        error = PlanRefusal("resume_program_changed", message, fresh_program=candidate)
    else:
        divergence = plan.divergence
        error = PlanRefusal("effect_input_diverged", message, getattr(divergence, "identity", None),
                            changed_parts=getattr(divergence, "changed_parts", []),
                            changed_files=getattr(divergence, "changed_files", []))
    error.plan = plan
    error.snapshot = read_memo(authority.memo_path, site_classes(authority.program), run_files=authority.run_files)
    return error


def _write(authority, plan) -> JournalEntry:
    """Store the program (W1, W2), repair a torn tail (W3), append and synchronize the record (W4). Any failure
    after the program is stored carries `change_in_force = "may"`."""
    from . import memo

    files = authority.run_files
    if files is None:
        raise ValueError("accepting a plan requires the run's retained file owner")
    snapshot = read_memo(authority.memo_path, site_classes(authority.program), run_files=files)
    if plan.record == "rebased":
        _store(authority, plan.program)
        row = {"record": "rebased", "program_digest": plan.program.digest, "from_offset": plan.cut, "time": time.time()}
    else:
        row = {"record": "invalidated", "from_commit": plan.cut, "time": time.time()}
    try:
        memo.repair_torn_tail(authority.memo_path, snapshot, run_files=files)
        return memo.append_record(authority.memo_path, row, run_files=files)
    except Exception as exc:        # after the artifact is stored: a record may have been appended (W4)
        exc.change_in_force = "may"
        raise


def _store(authority, program) -> None:
    """Publish `closed_program.<digest>.json` without replacing, or reuse the file of that name if it verifies."""
    from orchestrator._common.io_atomic import RenameNoreplaceError, RenameNoreplaceUnavailableError
    from .authority import _read_file, program_artifact_name, verified_program

    files, name = authority.run_files, program_artifact_name(program.digest)
    if not files.exists(name):
        try:
            files.publish_new(name, program.artifact().encode("utf-8"))
            return
        except FileExistsError:
            pass                    # published since the check: verified below like any other
        except (RenameNoreplaceUnavailableError, RenameNoreplaceError) as exc:
            raise PlanRefusal("resume_preflight_failed", "the run root's file system cannot publish the edited "
                              f"program without replacing a file ({exc}); nothing was written") from exc
    verified_program(lambda file: _read_file(authority.run_root / file, files), program.digest)
