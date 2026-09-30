"""Evaluation of the closed program with an environment of values and a memo of effects.

Design sections 5 and 8. A run and its resume are the same call: evaluation from
the entry with the memo of the run root. An effect whose identity has a
`committed` record with the same input digest returns the recorded value and
runs nothing.

`hook(event, identity)` is called at each moment of an attempt that the design's
table of crash windows names: `resolved` (before `started`), `started` (before
launch), `finished` (the result file is complete, `committed` not written) and
`committed`; for a coordinator's effect also `settled`. Tests raise from it to
stop the process at that moment.

The run ends with a `terminal` record, written after every effect is committed
and every coordinator's effect settled or reconciled. A view reports a run
completed only from that record.

Value dependence: every value computed carries the identities of the effects
whose results it read (`self.reads`), through names, calls, loop state, join
parameters and the conditions that chose a branch's outcome. A committed record
keeps the identities its resolved input read (`depends_on`); `invalidate`
follows them.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from orchestrator.workflow.pure_expr import PureExprEvaluationError, evaluate_pure_expr

from .sites import SEPARATOR, ClosedProgram, canonical_digest
from .memo import Memo
from .performers import Performers, render_argument, result_path

Hook = Callable[[str, str], None]
_LOOP = re.compile(r"\[\*\]")
_PC = ("pc",)  # in an environment: the effects read by the conditions that chose the current branch
_NONE: frozenset[str] = frozenset()


def _dep(name: str) -> tuple[str, str]:
    """In an environment: the key of the effects whose results the value of `name` read."""

    return ("dep", name)


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


class Pending(Exception):
    """A view's evaluation reached an effect without a commit: the run stands there."""

    def __init__(self, identity: str, entry: Any) -> None:
        super().__init__(identity)
        self.identity, self.entry = identity, entry


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
    coordinators: Mapping[str, Any] | None = None,
) -> RunResult:
    """Run, or resume, the program in `run_root`. `coordinators` maps an effect class to a coordinator
    with its own ledger: `prepare(node, resolved, identity, attempt)` (its pending commit), `settle(node,
    identity, proof)` (its final commit, after the memo's `committed`) and `reconcile(node, resolved,
    identity, proof)` (on resume, when the memo holds the commit)."""

    run_root.mkdir(parents=True, exist_ok=True)
    bound = bind_inputs(program, inputs)
    performers = Performers(workspace)
    performers.pins = _check_run(run_root, program, bound, performers)
    evaluator = _Evaluator(program, run_root, performers, hook or (lambda _event, _identity: None))
    evaluator.coordinators = dict(coordinators or {})
    with Memo(run_root) as memo:
        evaluator.memo = memo
        try:
            value = evaluator.run(bound)
        except EvaluationFailed as failed:
            memo.append({"record": "terminal", "outcome": "failed", "code": failed.code, "message": str(failed)})
            raise
        memo.append({"record": "terminal", "outcome": "completed", "value": value})
    return RunResult(value, evaluator.trace, evaluator.diagnostics)


def invalidate(run_root: Path, identity: str, *, follow: str = "suffix") -> list[str]:
    """The explicit continuation after a divergence: `identity` and the effects that follow it lose their
    commits, one `invalidated` record each, appended; the next resume runs exactly these again.

    `follow="suffix"` (the rule): every effect committed after `identity` in the journal, since a dependence
    through a file is not recorded. `follow="values"`: only the effects whose resolved input read its result,
    directly or through another invalidated effect's result. Refused while an evaluator holds the memo
    (`MemoBusy`), and when one of them is a coordinator's committed effect."""

    with Memo(run_root) as memo:
        if memo.entry(identity).committed is None:
            raise EvaluationFailed("invalidate_not_committed", f"`{identity}` has no commit to invalidate")
        chosen = (_later_commits if follow == "suffix" else _value_dependents)(memo, identity)
        ordered = sorted(chosen, key=lambda name: memo.entries[name].committed_at)
        coordinated = [name for name in ordered if "proof" in memo.entries[name].committed]
        if coordinated:
            raise EvaluationFailed(
                "invalidate_coordinator_committed",
                f"{coordinated} committed through a coordinator whose own ledger holds the visit: the design must "
                "decide whether a committed visit can be superseded (a new visit key or attempt for the same "
                "identity) and what becomes of the superseded child run and its workspace delta",
                detail={"coordinated": coordinated, "settled": [memo.entries[n].settled for n in coordinated]})
        for name in ordered:
            memo.append({"record": "invalidated", "identity": name, "attempt": memo.entries[name].committed["attempt"],
                         "by": identity})
    return ordered


def _later_commits(memo: Memo, identity: str) -> set[str]:
    at = memo.entry(identity).committed_at
    return {name for name, entry in memo.entries.items() if entry.committed is not None and entry.committed_at >= at}


def _value_dependents(memo: Memo, identity: str) -> set[str]:
    chosen, grew = {identity}, True
    while grew:
        grown = {name for name, entry in memo.entries.items()
                 if entry.committed is not None and chosen & set(entry.committed.get("depends_on", ()))}
        grew, chosen = not grown <= chosen, chosen | grown
    return chosen


def bind_inputs(program: ClosedProgram, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """The run's inputs: declared defaults applied, then each value checked against its declared type by the
    catalog's coercion. The run's input digest is taken over these."""

    params, defaults = program.tree["params"], program.tree.get("defaults", {})
    unknown = sorted(set(inputs) - {name for name, _ in params})
    missing = [name for name, _ in params if name not in inputs and name not in defaults]
    if unknown or missing:
        raise EvaluationFailed("workflow_input_missing" if missing else "workflow_input_unknown",
                               f"inputs {missing or unknown} are not bound or not declared",
                               detail={"missing": missing, "unknown": unknown})
    bound = {}
    for name, desc in params:
        value = inputs[name] if name in inputs else defaults[name]
        payload = {"pure_expr_schema_version": 2, "result_type": desc, "bindings": {"v": {"type": desc}},
                   "expr": {"kind": "binding", "name": "v"}}
        try:
            bound[name] = evaluate_pure_expr(payload, resolved_bindings={"v": value})
        except PureExprEvaluationError as exc:
            raise EvaluationFailed("workflow_input_invalid", f"input `{name}` is not a {desc.get('name', desc['kind'])}",
                                   detail={"input": name, "value": value, "cause": exc.code}) from exc
    return bound


def _check_run(run_root: Path, program: ClosedProgram, inputs: Mapping[str, Any], performers: Performers) -> dict:
    """The program identity and the bound inputs are fixed when the run starts; a resume must match them. So
    are the programs its commands name bare (the interpreter): resolved on PATH once, and returned."""

    header = {"program": program.digest, "inputs": canonical_digest(dict(inputs))}
    path = run_root / "run.json"
    if not path.exists():
        pins = {} if program.tree.get("closure") == "trusting" else performers.pin(program.tree)
        (run_root / "closed-program.json").write_text(program.artifact(), encoding="utf-8")
        path.write_text(json.dumps({**header, "bound_inputs": dict(inputs), "programs": pins}, sort_keys=True),
                        encoding="utf-8")
        return pins
    recorded = json.loads(path.read_text(encoding="utf-8"))
    for key, code in (("program", "resume_program_changed"), ("inputs", "resume_inputs_changed")):
        if recorded[key] != header[key]:
            raise EvaluationFailed(code, f"the run started with {key} {recorded[key]}, not {header[key]}",
                                   detail={"recorded": recorded[key], "resumed": header[key]})
    return recorded.get("programs", {})


def _expect_halt(outcome: tuple, what: str) -> Any:
    if outcome[0] != "halt":
        raise EvaluationFailed("compiler_defect", f"{what} ended with `{outcome[0]}`, not a value")
    return outcome[1]


class _Evaluator:
    def __init__(self, program: ClosedProgram, run_root: Path, performers: Performers, hook: Hook) -> None:
        self.program, self.run_root, self.performers, self.hook = program, run_root, performers, hook
        self.memo: Memo | None = None
        self.loops: list[int] = []  # the iteration of each enclosing loop, outermost first
        self.frames: list[str] = []  # the call sites of the activation path, in the table form
        self.coordinators: dict[str, Any] = {}
        self.dry = False  # a view's evaluation: stop at the first effect without a commit
        self.trace: list[str] = []
        self.diagnostics: list[dict[str, Any]] = []
        self.reads: set[str] = set()  # the effects whose results the value being computed read
        self.result_file = ""  # the result file of the last effect reached, relative to the workspace

    def traced(self, compute: Callable[[], Any]) -> tuple[Any, frozenset[str]]:
        """`compute()`, and the identities of the effects whose results it read."""

        outer, self.reads = self.reads, set()
        try:
            return compute(), frozenset(self.reads)
        finally:
            self.reads = outer

    def run(self, inputs: Mapping[str, Any]) -> Any:
        return _expect_halt(self.body(self.program.tree["body"], dict(inputs)), "the workflow body")

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
        self.reads |= env.get(_PC, _NONE)  # an outcome depends on the conditions that chose it
        if kind in ("halt", "done"):
            return (kind, self.value(node["value"], env))
        args = [self.value(a, env) for a in node["args"]]
        return ("continue", args) if kind == "continue" else ("jump", node["join"], args)

    def step_let(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        env[node["name"]], env[_dep(node["name"])] = self.traced(lambda: self.bound(node["value"], env))
        if node["value"]["k"] == "perform":
            env[("path", node["name"])] = self.result_file
        return node["body"]

    def step_if(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        cond, reads = self.traced(lambda: self.condition(node["cond"], env))
        env[_PC] = env.get(_PC, _NONE) | reads
        return node["then"] if cond else node["else"]

    def step_case(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        subject, reads = self.traced(lambda: self.value(node["subject"], env))
        env[_PC] = env.get(_PC, _NONE) | reads
        for arm in node["arms"]:
            if arm["variant"] == subject["variant"]:
                env[arm["bind"]], env[_dep(arm["bind"])] = subject, reads
                return arm["body"]
        raise EvaluationFailed("compiler_defect", f"no arm for variant `{subject['variant']}`")

    def step_join(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any] | tuple:
        outcome, reads = self.traced(lambda: self.body(node["body"], env))
        if outcome[0] == "jump" and outcome[1] == node["name"]:
            env.update(zip(node["params"], outcome[2]))
        elif outcome[0] == "halt":  # a loop in tail position of the join body gives its value
            env[node["params"][0]] = outcome[1]
        else:
            self.reads |= reads
            return outcome
        env.update({_dep(param): reads for param in node["params"]})
        return node["cont"]

    def condition(self, node: dict[str, Any], env: dict[str, Any]) -> bool:
        value = self.value(node, env)
        if type(value) is not bool:
            raise EvaluationFailed("compiler_defect", f"a condition evaluated to {value!r}, not a Bool")
        return value

    def loop(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        (state, budget), reads = self.traced(lambda: (self.value(node["init"], env), self.value(node["budget"], env)))
        param = node["param"]
        for iteration in range(1, budget + 1):
            self.loops.append(iteration)
            outcome, reads = self.traced(lambda: self.body(node["body"], {**env, param: state, _dep(param): reads}))
            self.loops.pop()
            if outcome[0] == "done":
                self.reads |= reads
                return outcome[1]
            if outcome[0] != "continue":
                raise EvaluationFailed("compiler_defect", f"a loop body ended with `{outcome[0]}`")
            state = outcome[1][0]
        if node["exhausted"] is None:
            raise EvaluationFailed(node["code"] or "loop_exhausted", f"the loop ran its {budget} iterations",
                                   detail={"budget": budget})
        return _expect_halt(self.body(node["exhausted"], {**env, param: state, _dep(param): reads}), "a loop exhaustion")

    def bound(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        kind = node["k"]
        if kind == "perform":
            return self.perform(node, env)
        if kind == "call":  # the table form keeps the body in `definitions` and names the call site `frame`
            definition = node if "body" in node else self.program.tree["definitions"][node["callee"]]
            args = {}
            for param, arg in zip(definition["params"], node["args"]):
                args[param], args[_dep(param)] = self.traced(lambda arg=arg: self.value(arg, env))
            self.frames.extend([node["frame"]] if "frame" in node else [])
            value = _expect_halt(self.body(definition["body"], args), f"the body of `{node['callee']}`")
            del self.frames[len(self.frames) - ("frame" in node):]
            return value
        return self.value(node, env)

    # Values

    def value(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        return getattr(self, "value_" + node["k"])(node, env)

    def value_lit(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        return node["v"]

    def value_name(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        self.reads |= env.get(_dep(node["n"]), _NONE)
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

    def value_result_path(self, node: dict[str, Any], env: dict[str, Any]) -> str:
        """`provider-bundle-path`: the committed attempt's result file, relative to the workspace."""

        self.reads |= env.get(_dep(node["n"]), _NONE)
        return env[("path", node["n"])]

    def value_context(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        """A value of the run itself, the same on every resume: its identity is the run root's name."""

        return {"run-id": self.run_root.name}[node["field"]]

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
        site = SEPARATOR.join([*self.frames, site])
        if site.count("[*]") != len(self.loops):
            raise EvaluationFailed("compiler_defect", f"site `{site}` reached inside {len(self.loops)} loops")
        iterations = iter(self.loops)
        return _LOOP.sub(lambda _m: f"[{next(iterations)}]", site)

    def resolve(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        """Everything that determines what the effect is asked to do (section 7), with the digest of every
        file its boundary declares: a command's program files, a provider's prompt asset and dependencies."""

        if node["class"] == "command":
            return self.resolve_command(node, env)
        if node["class"] == "provider":
            return self.resolve_provider(node, env)
        if node["class"] == "request_input":
            return {"class": node["class"], "question": self.value(node["question"], env)}
        if node["class"] == "run_ref":
            return {"class": node["class"], "inputs": {name: self.value(v, env) for name, v in node.get("inputs", [])}}
        return {"class": node["class"], "inputs": [self.value(v, env) for v in node.get("inputs", [])]}

    def resolve_command(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        argv = [render_argument(self.value(a, env)) for a in node["argv"]]
        if "document" in node:  # a certified adapter: one JSON object, fields in signature order
            document = {key: self.value(v, env) for key, v in node["document"]}
            argv.append(json.dumps(document, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
        trusting = self.program.tree.get("closure") == "trusting"
        program = [self.performers.pins.get(node["command"][0], node["command"][0]), *node["command"][1:]]
        return {"class": "command", "command": [*program, *argv], "contract": node["contract"],
                "declared": {} if trusting else self.performers.declared_files(node["command"], node.get("closure"))}

    def resolve_provider(self, node: dict[str, Any], env: dict[str, Any]) -> dict[str, Any]:
        prompt, dependencies = node["prompt"], node.get("dependencies")
        if isinstance(prompt, dict):
            prompt = {**prompt, "fills": [[n, r, self.value(v, env)] for n, r, v in prompt["fills"]]}
        if dependencies:
            dependencies = {**dependencies, **{role: [self.value(v, env) for v in dependencies[role]]
                                               for role in ("required", "optional")}}
        return {"class": "provider", "provider": node["provider"], "prompt": prompt, "dependencies": dependencies,
                "inputs": [[n, r, self.value(v, env)] for n, r, v in node["inputs"]],
                "policy": {k: self.value(v, env) for k, v in node["policy"].items()}, "contract": node["contract"],
                "declared": self.performers.provider_files(prompt, dependencies)}

    def perform(self, node: dict[str, Any], env: dict[str, Any]) -> Any:
        """The table of section 8: what the memo holds for the identity decides the action."""

        identity = self.identity(node["site"])
        if self.dry:
            return self.dry_perform(identity)
        resolved, reads = self.traced(lambda: self.resolve(node, env))
        self.reads.add(identity)
        digest = canonical_digest(resolved)
        parts = {key: canonical_digest(part) for key, part in resolved.items()}
        self.trace.append(identity)
        entry = self.memo.entry(identity)
        if entry.committed is not None:
            self.result_file = self.performers.relative(self.run_root / entry.committed.get("result_path", "."))
            if entry.committed["input_digest"] == digest:
                if node["class"] in self.coordinators:
                    self.coordinators[node["class"]].reconcile(node, resolved, identity, entry.committed.get("proof"))
                    if not entry.settled:
                        self.memo.append({"record": "settled", "identity": identity,
                                          "attempt": entry.committed["attempt"], "by": "reconcile"})
                return entry.committed["value"]
            recorded = entry.committed.get("input_parts", {})
            files = entry.committed.get("declared", {})
            raise EvaluationFailed(
                "effect_input_diverged", f"`{identity}` committed with another input", at=node.get("@"),
                detail={"recorded": entry.committed["input_digest"], "resolved": digest,
                        "differs": sorted(key for key in parts if recorded.get(key) != parts[key]),
                        "files": sorted(f for f in {*files, *resolved.get("declared", {})}
                                        if files.get(f) != resolved.get("declared", {}).get(f))},
            )
        if entry.suspended is not None:
            raise EffectSuspended(identity, entry.suspended["request"])
        if entry.attempts and not entry.invalidated:
            if node.get("repeat") == "never":
                raise EvaluationFailed("lexical_restore_pending_effect_unsafe",
                                       f"`{identity}` started without a commit and must not repeat",
                                       at=node.get("@"), detail={"attempts": entry.attempts})
            self.diagnostics.append({"code": "effect_rerun", "identity": identity, "after": list(entry.attempts)})
        return self.attempt(node, identity, max(entry.attempts, default=0) + 1, resolved, digest,
                            {"input_parts": parts, "depends_on": sorted(reads)})

    def dry_perform(self, identity: str) -> Any:
        entry = self.memo.entry(identity)
        self.trace.append(identity)
        if entry.committed is None:
            raise Pending(identity, entry)
        self.result_file = self.performers.relative(self.run_root / entry.committed.get("result_path", "."))
        return entry.committed["value"]

    def attempt(self, node, identity, attempt, resolved, digest, inputs) -> Any:
        """`inputs`: the digest of each part of the resolved input, and the effects whose results it read."""

        path = result_path(self.run_root, identity, attempt)
        self.result_file = self.performers.relative(path)
        record = {"identity": identity, "attempt": attempt, "input_digest": digest}
        self.hook("resolved", identity)
        self.memo.append({**record, "record": "started", "input_parts": inputs["input_parts"],
                          "result_path": path.relative_to(self.run_root).as_posix()})
        self.hook("started", identity)
        if node["class"] == "request_input":
            self.memo.append({**record, **inputs, "record": "suspended", "request": resolved["question"]})
            raise EffectSuspended(identity, resolved["question"])
        coordinator, proof = self.coordinators.get(node["class"]), None
        if coordinator is not None:
            value, failure, proof = coordinator.prepare(node, resolved, identity, attempt)
        else:
            value, failure = self.performers.perform(node, resolved, path, identity)
        self.hook("finished", identity)
        if failure is not None:
            self.memo.append({**record, "record": "failed", **failure})
            raise EvaluationFailed(failure["code"], f"`{identity}` attempt {attempt} failed", at=node.get("@"),
                                   detail=failure)
        self.memo.append({**record, **inputs, "record": "committed", "value": value,
                          "declared": resolved.get("declared", {}),
                          "result_path": path.relative_to(self.run_root).as_posix(),
                          "result_digest": canonical_digest(value), **({"proof": proof} if proof is not None else {})})
        self.hook("committed", identity)
        if coordinator is not None:
            coordinator.settle(node, identity, proof)
            self.memo.append({**record, "record": "settled", "by": "settle"})
            self.hook("settled", identity)
        return value
