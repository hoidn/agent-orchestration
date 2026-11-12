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
    plan: Any = None        # rebase.Plan, or the error that says why no plan can be accepted

    def command(self, *words: str) -> str:
        return COMMAND_INDENT + self.launcher + " " + " ".join(shlex.quote(word) for word in words) + state_dir_flag(self.state_dir)

    def resume(self, *flags: str) -> str:
        return self.command("resume", self.run_id, *flags)

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
    """Committed or not is read from the memo; a committed step's change shared by an unfinished step that no
    clean failure covers adds `--accept-changes` to the `resume` after `invalidate`."""
    from orchestrator.workflow.evaluated.attempts import proven_unchanged

    identity = getattr(exc, "identity", None)
    changed = _names(getattr(exc, "changed_files", ()))
    files = ", ".join(changed) or "none recorded"
    snapshot = context.snapshot
    if identity is None or snapshot is None:
        return ["an effect's inputs differ from what this run recorded",
                "restore what changed and resume:", context.resume(),
                *context.fresh_run("otherwise start a new run:")]
    if identity not in snapshot.active_commits:
        return _unfinished_step(identity, changed, files, context)
    unfinished = _unfinished_users(snapshot, identity, changed)
    unproven = [other for other in unfinished if not proven_unchanged(snapshot, snapshot.latest_starts[other])]
    parts = ", ".join(getattr(exc, "changed_parts", ())) or "unknown"
    shared = ([f"the change also affects {', '.join(unfinished)}, whose last attempt did not finish"
               + ("; resuming accepts its changed files" if unproven else "")] if unfinished else [])
    return [f"step {identity} was committed with other inputs; changed: {parts}; files: {files}", *shared,
            *(_flag_accepts(context, unproven) if unproven else []),
            "to run this step and every later one again (workspace files are not rolled back):",
            context.command("invalidate", context.run_id, identity),
            context.resume("--accept-changes") if unproven else context.resume()]


def _unfinished_step(identity: str, changed: list[str], files: str, context: _Context) -> list[str]:
    """An uncommitted step: changed files can be accepted, since its last attempt is not proven clean (§8.1)."""
    if not changed:
        return [f"the inputs of step {identity} changed since its last attempt (see the message above)",
                "restore what changed and resume:", context.resume(),
                *context.fresh_run("otherwise start a new run:")]
    return [f"step {identity} did not finish, and its files changed since: {files}",
            *_flag_accepts(context, [identity]), context.resume("--accept-changes"),
            "or restore the files as they were and resume:", context.resume(),
            *context.fresh_run("or start a new run:")]


def _flag_accepts(context: _Context, named: list[str]) -> list[str]:
    """Every attempt `--accept-changes` would accept, each with why it is not proven clean (all, not only `named`)."""
    from orchestrator.workflow.evaluated.attempts import accepted_attempt_lines, unproven_command_retries

    snapshot = context.snapshot
    every = [] if context.stored_program is None else unproven_command_retries(snapshot)
    listed = [*named, *(identity for identity in every if identity not in named)]
    return ["with --accept-changes, each of these unfinished steps is retried with its files as they are now:",
            *accepted_attempt_lines(snapshot, listed)]


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


def _spend_cap_reached(exc, context: _Context) -> list[str]:
    higher = max(getattr(exc, "spent_usd", 0.0), getattr(exc, "cap_usd", 0.0)) * 2
    if higher <= 0:
        return ["no provider call started; to continue, resume without a cap:", context.resume()]
    return ["no provider call started; to continue, resume with a higher cap:",
            context.command("resume", context.run_id, "--max-cost-usd", f"{higher:.6g}")]


_UNMETERED_FIX = {
    "template_unmetered": "bind the step to its `<name>_metered` template and start a new run with the cap",
    "model_unpriced": "set the step's `:model` to a model id the price table prices and start a new run with the cap",
    "step_uncapped": "a run reference or phased provider step cannot run under a cap",
    "attempt_unmetered": "an earlier attempt was cut off or has no complete priced usage, so the cap cannot be checked",
}


def _spend_cap_unmetered(exc, context: _Context) -> list[str]:
    cause = getattr(exc, "cause", None) or "unknown"
    fix = _UNMETERED_FIX.get(cause, "the cap prices only metered calls")
    return [f"cause {cause}: {fix}", "to continue this run without a cap:", context.resume()]


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
    "spend_cap_reached": _spend_cap_reached,
    "spend_cap_unmetered": _spend_cap_unmetered,
}
REFUSAL_CODES: tuple[str, ...] = tuple(_RECOVERY)


def recovery_lines(exc: Exception, *, run_id: str, launcher: str, state_dir: str | None,
                   header: Mapping[str, Any] | None = None, stored_program: Any = None,
                   snapshot: Any = None, plan: Any = None) -> list[str]:
    """What changed and which command continues; one pointer line for any other code; then the plan, if any.

    `snapshot` is the run's memo, read after the refusal was decided; without it no step is called committed.
    `plan` (computed read-only after the refusal was decided) is a `rebase.Plan` or the reason none can be accepted.
    """
    code = getattr(exc, "code", "resume_preflight_failed")
    recover = _RECOVERY.get(code)
    if recover is None:
        return [f"about [{code}]: see \"Diagnostics\" in the CLI contract (specs/cli.md)"]
    context = _Context(run_id, launcher, state_dir, header, stored_program, snapshot, plan)
    return [*recover(exc, context), *([] if plan is None else plan_lines(context))]


def plan_lines(context: _Context) -> list[str]:
    """The plan an acceptance would apply, then its `plan token:` line; or why no plan can be accepted (design §6)."""
    plan = context.plan
    if isinstance(plan, Exception):
        return _no_plan(plan, context)
    costs = dict(plan.costs)
    return [("if accepted, this run continues under the edited program:" if plan.record == "rebased"
             else "if accepted, this run cancels from the changed step, as invalidate does:"),
            *_plan_section("kept     ", [_id(entry) for entry in plan.kept], ""),
            *_plan_section("cancelled", [_id(entry) + _cost(costs, _id(entry)) for entry in plan.cancelled],
                           ", which run again when reached"),
            *_plan_section("retired  ", [_id(entry) for entry in plan.retired], ", unfinished attempts that are dropped",
                           noun="pending start"),
            f"  the cut is at {plan.cut_reason}" if plan.cut is not None else "  the cut: none, nothing is cancelled",
            "  asked again: " + (", ".join(plan.asked_again) or "none"),
            *(f"  question {identity} cannot be answered until the edit is accepted or the source restored"
              for identity in plan.waiting),
            *_retried(plan),
            "  runs first: " + (", ".join(plan.runs_first) or "nothing: the run is complete"),
            *(["  files that cancelled steps wrote in the workspace are not rolled back"] if plan.cancelled else []),
            f"plan token: {plan.token}"]


def _cost(costs: Mapping[str, float | None], identity: str) -> str:
    if identity not in costs:
        return ""
    return "   (provider cost unknown)" if costs[identity] is None else f"   (provider cost USD {costs[identity]:.6g})"


def _retried(plan) -> list[str]:
    """The unfinished command attempts the acceptance covers, each with why it is not proven clean."""
    lines = [f"    {identity}: {reason}, with its files as they are {'now' if evidence is not None else 'when it is reached'}"
             for (identity, _attempt, evidence), reason in zip(plan.unproven, plan.unproven_reasons)]
    return ["  unfinished steps retried:" + ("" if lines else " none"), *_capped(lines)]


def _id(entry) -> str:
    return entry.data["identity"]


def _capped(lines: list[str]) -> list[str]:
    shown = lines[:_LISTED_COMMITS]
    return [*shown, *([f"    ... and {len(lines) - len(shown)} more"] if len(lines) > len(shown) else [])]


def _plan_section(title: str, items: list[str], suffix: str, *, noun: str = "committed step") -> list[str]:
    if not items:
        return [f"  {title} none"]
    count = f"{len(items)} {noun}" + ("" if len(items) == 1 else "s")
    return [f"  {title} {count}{suffix}:", *_capped([f"    {item}" for item in items])]


def _no_plan(failure: Exception, context: _Context) -> list[str]:
    """The reason no plan is shown; a committed `must_not_repeat` step names the command that lets it repeat."""
    code = getattr(failure, "code", "resume_preflight_failed")
    lines = [f"no plan can be accepted: [{code}] {failure}"]
    if code == "lexical_restore_pending_effect_unsafe" and getattr(failure, "committed", False):
        lines += ["to let that step run again, invalidate it explicitly; resume then prints a new plan:",
                  context.command("invalidate", context.run_id, failure.identity)]
    return lines
