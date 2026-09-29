"""Evaluation of the closed program with an environment of values and a memo of effects.

Design sections 5 and 8. A run and its resume are the same call: evaluation from
the entry with the memo of the run root. An effect whose identity has a
`committed` record with the same input digest returns the recorded value and
runs nothing.

`hook(event, identity)` is called at each moment of an attempt that the design's
table of crash windows names: `resolved` (before `started`), `started` (before
launch), `finished` (the result file is complete, `committed` not written) and
`committed`. Tests raise from it to stop the process at that moment.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.workflow.pure_expr import PureExprEvaluationError, evaluate_pure_expr

from .closed import ClosedProgram, canonical_digest
from .memo import Memo
from .performers import Performers, render_argument, result_path

Hook = Callable[[str, str], None]
_LOOP = re.compile(r"\[\*\]")


class EvaluationFailed(Exception):
    """The run stops with a diagnostic code, where it was raised, and what it compared."""

    def __init__(self, code: str, message: str, *, at: Any = None, detail: Mapping[str, Any] | None = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code, self.at, self.detail = code, at, dict(detail or {})


class EffectSuspended(Exception):
    """The run waits for a person: an effect has a `suspended` record and no commit."""

    def __init__(self, identity: str, request: Any) -> None:
        super().__init__(f"waiting for an answer at `{identity}`: {request}")
        self.identity, self.request = identity, request


@dataclass
class RunResult:
    value: Any
    trace: list[str] = field(default_factory=list)  # identities reached, in evaluation order
    diagnostics: list[dict[str, Any]] = field(default_factory=list)


def evaluate(
    program: ClosedProgram,
    *,
    inputs: Mapping[str, Any],
    workspace: Path,
    run_root: Path,
    hook: Hook | None = None,
) -> RunResult:
    """Run, or resume, the program in `run_root`."""

    run_root.mkdir(parents=True, exist_ok=True)
    _check_run(run_root, program, inputs)
    evaluator = _Evaluator(program, run_root, Performers(workspace), hook or (lambda _event, _identity: None))
    with Memo(run_root) as memo:
        evaluator.memo = memo
        value = evaluator.run(inputs)
    return RunResult(value, evaluator.trace, evaluator.diagnostics)


def _check_run(run_root: Path, program: ClosedProgram, inputs: Mapping[str, Any]) -> None:
    """The program identity and the bound inputs are fixed when the run starts; a resume must match them."""

    header = {"program": program.digest, "inputs": canonical_digest(dict(inputs))}
    path = run_root / "run.json"
    if not path.exists():
        (run_root / "closed-program.json").write_text(program.artifact(), encoding="utf-8")
        path.write_text(json.dumps(header, sort_keys=True), encoding="utf-8")
        return
    recorded = json.loads(path.read_text(encoding="utf-8"))
    for key, code in (("program", "resume_program_changed"), ("inputs", "resume_inputs_changed")):
        if recorded[key] != header[key]:
            raise EvaluationFailed(code, f"the run started with {key} {recorded[key]}, not {header[key]}",
                                   detail={"recorded": recorded[key], "resumed": header[key]})


def _expect_halt(outcome: tuple, what: str) -> Any:
    if outcome[0] != "halt":
        raise EvaluationFailed("compiler_defect", f"{what} ended with `{outcome[0]}`, not a value")
    return outcome[1]


class _Evaluator:
    def __init__(self, program: ClosedProgram, run_root: Path, performers: Performers, hook: Hook) -> None:
        self.program, self.run_root, self.performers, self.hook = program, run_root, performers, hook
        self.memo: Memo | None = None
        self.loops: list[int] = []  # the iteration of each enclosing loop, outermost first
        self.trace: list[str] = []
        self.diagnostics: list[dict[str, Any]] = []

    def run(self, inputs: Mapping[str, Any]) -> Any:
        tree = self.program.tree
        missing = [name for name, _ in tree["params"] if name not in inputs]
        if missing:
            raise EvaluationFailed("workflow_input_missing", f"inputs {missing} are not bound")
        env = {name: inputs[name] for name, _ in tree["params"]}
        return _expect_halt(self.body(tree["body"], env), "the workflow body")

    # Bodies: each returns ("halt", v), ("done", v), ("continue", [v]) or ("jump", join, [v]).
    # `let`, `if`, `case` and `join` continue in the same body; a step returns the next node or an outcome.

    def body(self, node: dict[str, Any], env: dict[str, Any]) -> tuple:
        env = dict(env)
        while node["k"] in ("let", "if", "case", "join"):
            node = getattr(self, "step_" + node["k"])(node, env)
            if isinstance(node, tuple):
                return node
        kind = node["k"]
        if kind == "loop":
            return ("halt", self.loop(node, env))
        if kind in ("halt", "done"):
            return (kind, self.value(node["value"], env))
        args = [self.value(a, env) for a in node["args"]]
        return ("continue", args) if kind == "continue" else ("jump", node["join"], args)

    def step_let(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        env[node["name"]] = self.bound(node["value"], env)
        return node["body"]

    def step_if(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        return node["then"] if self.condition(node["cond"], env) else node["else"]

    def step_case(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        subject = self.value(node["subject"], env)
        for arm in node["arms"]:
            if arm["variant"] == subject["variant"]:
                env[arm["bind"]] = subject
                return arm["body"]
        raise EvaluationFailed("compiler_defect", f"no arm for variant `{subject['variant']}`")

    def step_join(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any] | tuple:
        outcome = self.body(node["body"], env)
        if outcome[0] == "jump" and outcome[1] == node["name"]:
            env.update(zip(node["params"], outcome[2]))
        elif outcome[0] == "halt":  # a loop in tail position of the join body gives its value
            env[node["params"][0]] = outcome[1]
        else:
            return outcome
        return node["cont"]

    def condition(self, node: dict[str, Any], env: dict[str, Any]) -> bool:
        value = self.value(node, env)
        if type(value) is not bool:
            raise EvaluationFailed("compiler_defect", f"a condition evaluated to {value!r}, not a Bool")
        return value

    def loop(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        state, budget = self.value(node["init"], env), self.value(node["budget"], env)
        for iteration in range(1, budget + 1):
            self.loops.append(iteration)
            outcome = self.body(node["body"], {**env, node["param"]: state})
            self.loops.pop()
            if outcome[0] == "done":
                return outcome[1]
            if outcome[0] != "continue":
                raise EvaluationFailed("compiler_defect", f"a loop body ended with `{outcome[0]}`")
            state = outcome[1][0]
        if node["exhausted"] is None:
            raise EvaluationFailed(node["code"] or "loop_exhausted", f"the loop ran its {budget} iterations",
                                   detail={"budget": budget})
        return _expect_halt(self.body(node["exhausted"], {**env, node["param"]: state}), "a loop exhaustion")

    def bound(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        kind = node["k"]
        if kind == "perform":
            return self.perform(node, env)
        if kind == "call":
            args = dict(zip(node["params"], (self.value(a, env) for a in node["args"])))
            return _expect_halt(self.body(node["body"], args), f"the body of `{node['callee']}`")
        return self.value(node, env)

    # Values

    def value(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        return getattr(self, "value_" + node["k"])(node, env)

    def value_lit(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        return node["v"]

    def value_name(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        return env[node["n"]]

    def value_field(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        value = self.value(node["base"], env)
        for name in node["path"]:
            value = value[name]
        return value

    def value_record(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        return {name: self.value(item, env) for name, item in node["fields"]}

    def value_inject(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        return {"variant": node["variant"], **self.value_record(node, env)}

    def value_list(self, node: dict[str, Any], env: dict[str, Any]) -> list[Any]:
        return [self.value(item, env) for item in node["items"]]

    def value_select(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        arm = node["then"] if self.condition(node["cond"], env) else node["else"]
        local = dict(env)
        for let in arm["prefix"]:
            local[let["name"]] = self.bound(let["value"], local)
        return self.value(arm["value"], local)

    def value_block(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        return _expect_halt(self.body(node["body"], env), "a value block")

    def value_op(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        """One operator of the catalog of `pure_expr.py`, applied to values."""

        operands = {f"a{i}": self.value(arg, env) for i, arg in enumerate(node["args"])}
        try:
            return evaluate_pure_expr(node["payload"], resolved_bindings=operands)
        except PureExprEvaluationError as exc:
            raise EvaluationFailed(exc.code, str(exc), at=node.get("@"),
                                   detail={"operands": operands, **exc.metadata}) from exc

    # Effects

    def identity(self, site: str) -> str:
        if site.count("[*]") != len(self.loops):
            raise EvaluationFailed("compiler_defect", f"site `{site}` reached inside {len(self.loops)} loops")
        iterations = iter(self.loops)
        return _LOOP.sub(lambda _m: f"[{next(iterations)}]", site)

    def resolve(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        """Everything that determines what the effect is asked to do (section 7)."""

        kind = node["class"]
        if kind == "command":
            argv = [render_argument(self.value(a, env)) for a in node["argv"]]
            return {"class": kind, "command": [*node["command"], *argv], "contract": node["contract"]}
        if kind == "provider":
            prompt = self.performers.workspace / node["prompt"]
            return {"class": kind, "provider": node["provider"], "prompt": node["prompt"],
                    "prompt_digest": canonical_digest(prompt.read_text(encoding="utf-8")),
                    "inputs": [self.value(a, env) for a in node["inputs"]],
                    "policy": {k: self.value(v, env) for k, v in node["policy"].items()}, "contract": node["contract"]}
        return {"class": kind, "question": self.value(node["question"], env)}

    def perform(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        """The table of section 8: what the memo holds for the identity decides the action."""

        identity = self.identity(node["site"])
        resolved = self.resolve(node, env)
        digest = canonical_digest(resolved)
        parts = {key: canonical_digest(part) for key, part in resolved.items()}
        self.trace.append(identity)
        entry = self.memo.entry(identity)
        if entry.committed is not None:
            if entry.committed["input_digest"] == digest:
                return entry.committed["value"]
            recorded = entry.committed.get("input_parts", {})
            raise EvaluationFailed(
                "effect_input_diverged", f"`{identity}` committed with another input", at=node.get("@"),
                detail={"recorded": entry.committed["input_digest"], "resolved": digest,
                        "differs": sorted(key for key in parts if recorded.get(key) != parts[key])},
            )
        if entry.suspended is not None:
            raise EffectSuspended(identity, entry.suspended["request"])
        if entry.attempts:
            if node.get("repeat") == "never":
                raise EvaluationFailed("lexical_restore_pending_effect_unsafe",
                                       f"`{identity}` started without a commit and must not repeat",
                                       at=node.get("@"), detail={"attempts": entry.attempts})
            self.diagnostics.append({"code": "effect_rerun", "identity": identity, "after": list(entry.attempts)})
        return self.attempt(node, identity, max(entry.attempts, default=0) + 1, resolved, digest, parts)

    def attempt(self, node, identity, attempt, resolved, digest, parts) -> Any:
        path = result_path(self.run_root, identity, attempt)
        record = {"identity": identity, "attempt": attempt, "input_digest": digest}
        self.hook("resolved", identity)
        self.memo.append({**record, "record": "started", "input_parts": parts,
                          "result_path": path.relative_to(self.run_root).as_posix()})
        self.hook("started", identity)
        if node["class"] == "request_input":
            self.memo.append({**record, "record": "suspended", "request": resolved["question"]})
            raise EffectSuspended(identity, resolved["question"])
        value, failure = self.performers.perform(node, resolved, path)
        self.hook("finished", identity)
        if failure is not None:
            self.memo.append({**record, "record": "failed", **failure})
            raise EvaluationFailed(failure["code"], f"`{identity}` attempt {attempt} failed", at=node.get("@"),
                                   detail=failure)
        self.memo.append({**record, "record": "committed", "input_parts": parts, "value": value,
                          "result_path": path.relative_to(self.run_root).as_posix(),
                          "result_digest": canonical_digest(value)})
        self.hook("committed", identity)
        return value
