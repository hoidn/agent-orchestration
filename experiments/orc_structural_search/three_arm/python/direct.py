"""The `direct` parent as a typed Python workflow: one coder call implements the task.

The I3 counterpart of ../orc/direct.orc (the seed with its coder on Codex gpt-6.1-sol). Everything above `run`
is frozen; a child may rewrite `run` and add top-level functions. `provider_result` sends the coder the prompt the
ORC runtime would send: the prompt body, then the runtime's file/2 output contract block for the result record
(orchestrator.contracts), whose `- path:` line names .orchestrate/runs/<run_id>/effects/<n>/attempt-1/result.json
relative to the working directory; it runs the registry template's argv (orchestrator.providers.registry) with the
call's model and effort, the prompt on stdin, and validates the result file as the runtime does. `dev_check` runs
the `python dev_check.py` command boundary of ../orc/commands.json in the working directory.

  python direct.py INPUTS_JSON    (cwd: the task clone; the runtime library on PYTHONPATH)

INPUTS_JSON holds `task`, `intent` and `repo`. The run writes .orchestrate/runs/<run_id>/terminal.json:
{"outcome": "completed"|"failed", "value", "failure": {"code", "message"}|None, "started_at", "finished_at",
"calls"} (times in epoch seconds, calls = provider calls launched) and exits 0 when completed, 1 when failed.
A provider failure, an invalid result or a call beyond MAX_PROVIDER_CALLS is a failed terminal.
"""

import json
import os
import subprocess
import sys
import time
import typing
from dataclasses import asdict, dataclass, is_dataclass
from pathlib import Path
from string import Template
from typing import Any, TypeVar

from orchestrator.contracts.prompt_json_shape import render_json_shape_contract_block
from orchestrator.providers.registry import ProviderRegistry
from orchestrator.workflow.evaluated.values import coerce_evaluated_value


@dataclass(frozen=True)
class Change:
    summary: str
    account: str


@dataclass(frozen=True)
class CheckReport:
    passed: bool
    failing: list[str]
    excerpt: str


@dataclass(frozen=True)
class DONE:
    summary: str


@dataclass(frozen=True)
class BLOCKED:
    reason: str


Outcome = DONE | BLOCKED

IMPLEMENT_PROMPT = (
    "Work in the git repository at {repo} and nowhere else. Implement this change there:\n\n{task}\n\n"
    "Report two things. `summary`: one sentence. `account`: what you changed and why, the alternatives you tried or "
    "considered and why you discarded them, and what you did not cover.")
PROVIDERS: dict[str, str] = json.loads((Path(__file__).resolve().parent / "providers.json").read_text())
MAX_PROVIDER_CALLS: int = 8
DEV_CHECK_COMMAND = ["python", "dev_check.py"]
RESULT_CONTRACT = {"kind": "output_bundle", "payload": {}}  # no field guidance: the shape comes from the record
PRIMITIVES = {str: "String", bool: "Bool", int: "Int", float: "Float"}
T = TypeVar("T", Change, CheckReport)


class ProviderFailure(Exception):
    """A failed effect: `code` as the runtime names it (provider_exit_nonzero, provider_result_invalid, ...)."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code, self.message = code, message


@dataclass
class RunState:
    root: Path = Path(".orchestrate/runs/unset")
    effects: int = 0
    calls: int = 0


STATE = RunState()


def descriptor(hint: Any) -> dict[str, Any]:
    """The runtime's type descriptor of a result record, a list or a primitive."""
    if isinstance(hint, type) and is_dataclass(hint):
        fields = typing.get_type_hints(hint).items()
        return {"kind": "record", "name": hint.__name__,
                "fields": [{"name": name, "type": descriptor(field)} for name, field in fields]}
    if typing.get_origin(hint) is list:
        return {"kind": "list", "item": descriptor(typing.get_args(hint)[0])}
    return {"kind": "primitive", "name": PRIMITIVES[hint]}


def next_result_path() -> Path:
    """The next effect's result file, relative to the working directory."""
    STATE.effects += 1
    attempt = STATE.root / "effects" / str(STATE.effects) / "attempt-1"
    attempt.mkdir(parents=True)
    return attempt / "result.json"


def read_result(path: Path, result: type[T], kind: str) -> T:
    """The effect's result file validated against `result`'s record type."""
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        raise ProviderFailure(f"{kind}_result_missing", f"{kind} did not create {path}") from None
    try:
        value = coerce_evaluated_value(json.loads(raw), descriptor(result), context=f"{kind} result").json_value()
    except ValueError as exc:
        raise ProviderFailure(f"{kind}_result_invalid", str(exc)) from exc
    return result(**value)


def provider_result(provider: str, prompt: str, *, model: str, effort: str, timeout_sec: int, result: type[T]) -> T:
    """One provider call: the prompt with the result's output contract, through the registry template's argv."""
    if STATE.calls >= MAX_PROVIDER_CALLS:
        raise ProviderFailure("call_budget_exceeded", f"provider call {STATE.calls + 1} exceeds {MAX_PROVIDER_CALLS}")
    template = ProviderRegistry().get(provider)
    if template is None:
        raise ProviderFailure("provider_preparation_failed", f"no provider template {provider!r}")
    STATE.calls += 1
    path = next_result_path()
    contract = render_json_shape_contract_block(RESULT_CONTRACT, descriptor(result), str(path))
    composed = prompt + ("\n" if prompt.endswith("\n") else "\n\n") + contract  # the runtime's separator
    bindings = template.call_policy_bindings
    params = {bindings["model"].target_param: model, bindings["effort"].target_param: effort}
    argv = [Template(arg).substitute(params) for arg in template.command]
    env = {**os.environ, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(path.resolve())}
    try:
        done = subprocess.run(argv, input=composed.encode(), env=env, timeout=timeout_sec)
    except subprocess.TimeoutExpired:
        raise ProviderFailure("provider_timeout", f"{provider} ran over {timeout_sec}s") from None
    if done.returncode:
        raise ProviderFailure("provider_exit_nonzero", f"{provider} exited {done.returncode}")
    return read_result(path, result, "provider")


def dev_check() -> CheckReport:
    """The task's agent-visible checks through the dev-check command boundary."""
    path = next_result_path()
    done = subprocess.run(DEV_CHECK_COMMAND, env={**os.environ, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(path.resolve())})
    if done.returncode:
        raise ProviderFailure("command_exit_nonzero", f"{' '.join(DEV_CHECK_COMMAND)} exited {done.returncode}")
    return read_result(path, CheckReport, "command")


def main(argv: list[str]) -> int:
    inputs = json.loads(Path(argv[0]).read_text())
    STATE.root = Path(".orchestrate", "runs", time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + f"-{os.getpid()}")
    STATE.root.mkdir(parents=True)
    started = time.time()
    try:
        outcome = run(inputs["task"], inputs["intent"], inputs["repo"])
        terminal = {"outcome": "completed", "value": {"variant": type(outcome).__name__, **asdict(outcome)},
                    "failure": None}
    except ProviderFailure as failure:
        terminal = {"outcome": "failed", "value": None, "failure": {"code": failure.code, "message": failure.message}}
    terminal |= {"started_at": started, "finished_at": time.time(), "calls": STATE.calls}
    (STATE.root / "terminal.json").write_text(json.dumps(terminal, indent=2) + "\n")
    return 0 if terminal["outcome"] == "completed" else 1


def run(task: str, intent: str, repo: str) -> Outcome:
    change = provider_result(PROVIDERS["coder"], IMPLEMENT_PROMPT.format(task=task, repo=repo),
                             model="gpt-6.1-sol", effort="high", timeout_sec=5400, result=Change)
    return DONE(summary=change.summary)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
