"""Recovery lines printed after a refusal's unchanged `[code] message` line.

One function per refusal code says what changed and which command continues;
specs/cli.md ("Diagnostics") owns the table. Commands are printed on their own
lines, indented by four spaces, ready to run from the run's workspace.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

COMMAND_INDENT = "    "
_REPEAT_WARNING = "that step and every later one run again; workspace files are not rolled back"
_MANIFEST_FLAGS = (
    ("provider_externs_path", "--provider-externs-file"),
    ("prompt_externs_path", "--prompt-externs-file"),
    ("imported_workflow_bundles_path", "--imported-workflow-bundles-file"),
    ("command_boundaries_path", "--command-boundaries-file"),
)


def state_dir_flag(state_dir: str | None) -> str:
    return f" --state-dir {shlex.quote(state_dir)}" if state_dir else ""


@dataclass(frozen=True)
class _Context:
    run_id: str
    launcher: str
    state_dir: str | None
    header: Mapping[str, Any] | None
    stored_program: Any
    snapshot: Any = None

    def command(self, *words: str) -> str:
        return COMMAND_INDENT + self.launcher + " " + " ".join(shlex.quote(word) for word in words) + state_dir_flag(self.state_dir)

    def resume(self) -> str:
        return self.command("resume", self.run_id)

    def fresh_run(self, why: str) -> list[str]:
        if self.header is None or "resume_request" not in self.header:
            return []
        return [why, COMMAND_INDENT + run_command(self.header, launcher=self.launcher, state_dir=self.state_dir)]


def run_command(header: Mapping[str, Any], *, launcher: str, state_dir: str | None) -> str:
    """A fresh `run` with the source, roots, entry, manifests and inputs the header recorded."""
    recipe = header["resume_request"]
    words = ["run", header["workflow_file"]]
    for root in recipe["source_roots"]:
        words += ["--source-root", root]
    if recipe["entry_workflow"]:
        words += ["--entry-workflow", recipe["entry_workflow"]]
    words += [word for field, flag in _MANIFEST_FLAGS if recipe[field] for word in (flag, recipe[field])]
    if recipe["input_file"]:
        words += ["--input-file", recipe["input_file"]]
    for name, value in recipe["input_overrides"].items():
        words += ["--input", f"{name}={value}"]
    return launcher + " " + " ".join(shlex.quote(word) for word in words) + state_dir_flag(state_dir)


def _names(keys) -> list[str]:
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


def _file_names(keys) -> str:
    return ", ".join(_names(keys)) or "none recorded"


def _unfinished_users(snapshot, identity: str, changed: list[str]) -> list[str]:
    """Other steps whose latest attempt is pending or failed and whose files include a changed one (any, if unknown).

    An invalidated step is not one: it has no attempt to retry, so invalidating and resuming runs it afresh.
    """
    from orchestrator.workflow.evaluated.memo import _uncommitted_state

    return [other for other, start in snapshot.latest_starts.items()
            if other != identity and other not in snapshot.active_commits
            and _uncommitted_state(snapshot, other) in {"pending", "failed"}
            and (not changed or set(changed) & set(_names(start.data.get("implementation_files") or {})))]


def _changed_sites(stored_program, fresh_program) -> list[str]:
    from orchestrator.workflow.evaluated.machine import site_nodes
    from orchestrator.workflow_lisp.closed.build import _strip_provenance

    def semantic(program):
        return {identity: json.dumps(_strip_provenance(node), sort_keys=True)
                for identity, node in site_nodes(program).items()}

    stored, fresh = semantic(stored_program), semantic(fresh_program)
    return ([f"  added   {identity}" for identity in fresh if identity not in stored]
            + [f"  removed {identity}" for identity in stored if identity not in fresh]
            + [f"  changed {identity}" for identity in stored if identity in fresh and stored[identity] != fresh[identity]])


def _program_changed(exc, context: _Context) -> list[str]:
    fresh = getattr(exc, "fresh_program", None)
    if fresh is None or context.stored_program is None:
        lines = ["the source or a manifest differs from the one this run was started with"]
    else:
        changed = _changed_sites(context.stored_program, fresh)
        lines = (["effect sites that differ from the recorded program:", *changed] if changed
                 else ["no effect site changed: only code between effects differs"])
    return [*lines, "restore the source as it was and resume:", context.resume(),
            *context.fresh_run("or start a new run, in which every step runs again:")]


def _inputs_changed(exc, context: _Context) -> list[str]:
    names = ", ".join(getattr(exc, "changed_inputs", ())) or "unknown"
    return [f"inputs whose value differs from the recorded run: {names}",
            "restore them and resume:", context.resume(),
            *context.fresh_run("or start a new run with the new values:")]


def _effect_diverged(exc, context: _Context) -> list[str]:
    """Committed or not is read from the memo; `invalidate` is offered only when nothing unfinished shares the change."""
    identity = getattr(exc, "identity", None)
    changed = _names(getattr(exc, "changed_files", ()))
    files = ", ".join(changed) or "none recorded"
    snapshot = context.snapshot
    if identity is None or snapshot is None:
        return ["an effect's inputs differ from what this run recorded",
                "restore what changed and resume:", context.resume(),
                *context.fresh_run("otherwise start a new run:")]
    if identity not in snapshot.active_commits:
        what = (f"step {identity} did not finish, and its files changed since: {files}" if changed
                else f"the inputs of step {identity} changed since its last attempt (see the message above)")
        return [what, "restore what changed and resume:", context.resume(),
                *context.fresh_run("otherwise start a new run; a step that did not finish cannot yet be "
                                   "retried with changed files in the same run:")]
    unfinished = _unfinished_users(snapshot, identity, changed)
    if unfinished:
        return [f"the change ({files}) also affects {', '.join(unfinished)}, whose last attempt did not finish",
                "a script fix after a failure cannot be resumed in this run: invalidating would run committed "
                "steps again and resume would still refuse",
                "restore the files as they were and resume:", context.resume(),
                *context.fresh_run("or start a new run with the fixed files:")]
    parts = ", ".join(getattr(exc, "changed_parts", ())) or "unknown"
    return [f"step {identity} was committed with other inputs; changed: {parts}; files: {files}",
            f"to run this step and every later one again ({_REPEAT_WARNING}):",
            context.command("invalidate", context.run_id, identity), context.resume()]


_NOT_COMMITTED = {
    "pending": "step {} has an attempt that has not finished; resume settles it:",
    "failed": "step {} failed and has no commit to invalidate; resume runs it again:",
    "invalidated": "step {} was invalidated and has no active commit; resume runs it again:",
}
_LISTED_COMMITS = 20


def _not_committed(exc, context: _Context) -> list[str]:
    identity = getattr(exc, "identity", None) or str(exc)
    state = getattr(exc, "state", None)
    if state == "pending":
        return [_NOT_COMMITTED[state].format(identity), context.resume()]
    lines = ([_NOT_COMMITTED[state].format(identity), context.resume()] if state in _NOT_COMMITTED
             else [f"no step has the identity {identity}"])
    committed = list(getattr(exc, "committed", ()))
    if not committed:
        return [*lines, "this run has no committed step"]
    shown = committed[:_LISTED_COMMITS]
    more = [f"    ... and {len(committed) - len(shown)} more"] if len(committed) > len(shown) else []
    return [*lines, f"to run a committed step again instead, invalidate it ({_REPEAT_WARNING}); in order:",
            *(context.command("invalidate", context.run_id, item) for item in shown), *more]


def _coordinator_committed(exc, context: _Context) -> list[str]:
    names = ", ".join(getattr(exc, "coordinators", ())) or "unknown"
    return [f"the steps from this one on include a committed run reference or agent turn: {names}",
            *context.fresh_run("they cannot be invalidated; start a new run:")]


def _result_root_changed(exc, context: _Context) -> list[str]:
    recorded = (context.header or {}).get("result_root")
    if recorded is None:
        return ["the run root differs from where this run was recorded"]
    parent = str(PurePosixPath(recorded).parent)
    flags = () if parent == ".orchestrate/runs" else ("--state-dir", parent)
    return [f"this run was recorded at {recorded} relative to its workspace; from that workspace run:",
            COMMAND_INDENT + context.launcher + " " + " ".join(shlex.quote(w) for w in ("resume", context.run_id, *flags))]


def _run_ref_root_changed(exc, context: _Context) -> list[str]:
    recorded = (context.header or {}).get("run_ref_root")
    if recorded is None:
        return ["the run-reference root differs from the one this run recorded"]
    return [f"this run recorded the run-reference root {recorded}:",
            context.command("resume", context.run_id, "--run-ref-root", recorded)]


def _with_fresh_run(reason: str):
    return lambda exc, context: [reason, *context.fresh_run("start a new run instead:")]


def _not_repeatable(exc, context: _Context) -> list[str]:
    identity = getattr(exc, "identity", None) or "a step"
    return [f"{identity} declares that it must not be repeated, and its last attempt did not finish",
            "check whether that attempt took effect: a new run performs it again",
            *context.fresh_run("start a new run:")]


_RECOVERY = {
    "resume_program_changed": _program_changed,
    "resume_inputs_changed": _inputs_changed,
    "effect_input_diverged": _effect_diverged,
    "invalidate_not_committed": _not_committed,
    "invalidate_coordinator_committed": _coordinator_committed,
    "resume_result_root_changed": _result_root_changed,
    "resume_run_ref_root_changed": _run_ref_root_changed,
    "evaluated_execution_unavailable": _with_fresh_run("evaluated runs cannot be restarted in place"),
    "resume_request_missing": lambda exc, context: [
        "this run was recorded without a rebuild recipe, so it cannot be resumed; start it again with run"],
    "lexical_restore_pending_effect_unsafe": _not_repeatable,
}
REFUSAL_CODES: tuple[str, ...] = tuple(_RECOVERY)


def recovery_lines(exc: Exception, *, run_id: str, launcher: str, state_dir: str | None,
                   header: Mapping[str, Any] | None = None, stored_program: Any = None,
                   snapshot: Any = None) -> list[str]:
    """What changed and which command continues; one pointer line for any other code.

    `snapshot` is the run's memo, read after the refusal was decided; without it no step is called committed.
    """
    code = getattr(exc, "code", "resume_preflight_failed")
    recover = _RECOVERY.get(code)
    if recover is None:
        return [f"about [{code}]: see \"Diagnostics\" in the CLI contract (specs/cli.md)"]
    return recover(exc, _Context(run_id, launcher, state_dir, header, stored_program, snapshot))
