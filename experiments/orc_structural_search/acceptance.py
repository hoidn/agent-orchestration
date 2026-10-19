"""Child judging of an episode: validation, compilation, the I2 slot check, the bounded planned maximum and the
entry's result type (driver.run_episode calls judge_child); for an I3 child (a Python module) AST scope validation
over the mutable functions and a pyright check instead.

Design: docs/design/orc_structural_search_driver.md ("Edit Validation And Transactions", "Proposal Interfaces" I3).
"""

import ast
import builtins
import hashlib
import io
import json
import math
import os
import re
import subprocess
import tempfile
import tokenize
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import asdict
from pathlib import Path

from experiments.orc_structural_search import evaluation, ledger
from experiments.orc_structural_search.candidates import (
    ACCEPTED, CompileOutcome, Verdict, _file_names, _refuse, _same_file, compile_candidate, validate_frozen_surfaces,
    validate_one_site)
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.records import _PROMPT_SUFFIX, UNAVAILABLE, python_program_digest
from experiments.orc_structural_search.sites import (
    derive_receipt, drop_hypothesis, replacement_start, site_manifest, slot_type)


TUNING_ARGUMENTS = ("model", "effort")  # an I3 call's provider tuning keywords
SUPPRESSION = re.compile(r"#\s*(?:type:\s*ignore|pyright:)")  # a comment that silences pyright (pyright's forms)
ADAPTER = "provider_result"  # an I3 module's provider adapter: provider_result(provider, prompt, *, ...)
BUILTIN_NAMES = frozenset(dir(builtins))  # frozen code calls them, so an added function must not shadow one
_CLEAN_PARENTS: set[tuple[str, Path]] = set()  # (entry module sha256, runtime) checked clean in this process
COMPILER_INCIDENT_CODES = frozenset({
    "compiler_crash", "compiler_defect", "compiler_defect_loop_control_value",
    "compiler_defect_hoisted_binding_rename", "compiler_defect_constructor_type_dropped",
})


def entry_result(root: Path, build_key: str) -> object:
    return closed_program(root, build_key)["result"]


def closed_program(root: Path, build_key: str) -> dict:
    return json.loads((root / ".orchestrate" / "build" / build_key / "closed_program.json").read_text())


def compiled_refusal(parent: Mapping, child: Mapping, config: ExperimentConfig) -> dict | None:
    """Compare resolved entry contracts, then enforce module-only graph and effect policies."""
    for field in ("params", "result"):
        if parent[field] != child[field]:
            code = "slot_type_changed" if field == "result" and config.condition != "module" else "frozen_surface_changed"
            return {"refusal_code": code, "detail": f"resolved entry {field} of {config.entry_workflow} changed"}
    if config.condition != "module":
        return None
    own_module = config.entry_workflow.split("::")[0]

    def modules(program):
        # Callable keys carry a kind prefix; loop-state carriers belong to the compiler, not an import.
        qualifiers = {name.split("::")[0].rsplit(":", 1)[-1]
                      for key in ("definitions", "types") for name in program[key] if "::" in name}
        return qualifiers - {own_module, "workflow_lisp/private"}

    if modules(parent) != modules(child):
        return {"refusal_code": "frozen_surface_changed", "detail": "the resolved imported module graph changed"}
    pending = [child]
    while pending:
        node = pending.pop()
        if isinstance(node, Mapping):
            if node.get("k") == "perform":
                if node["class"] in {"provider_phased", "agent", "agent_turn"}:
                    return {"refusal_code": "unsupported_effect_shape", "detail": f"unsupported effect {node['class']}"}
                if node["class"] == "provider":
                    refusal = _provider_policy_refusal(node.get("policy", {}), config)
                    if refusal:
                        return refusal
            pending.extend(node.values())
        elif isinstance(node, list):
            pending.extend(node)
    return None


def _provider_policy_refusal(policy: Mapping, config: ExperimentConfig) -> dict | None:
    values = {key: value.get("v") for key, value in policy.items() if value.get("k") == "lit"}
    model, effort = values.get("model"), values.get("effort")
    if not (isinstance(model, str) and "fable" not in model.lower() and isinstance(effort, str)
            and effort in config.models.get(model, ())):
        return {"refusal_code": "model_not_allowed", "detail": "model and effort must be allowlisted string literals"}
    timeout = values.get("timeout_sec")
    if (type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
            or timeout > config.per_call_timeout_sec or set(policy) - {"model", "effort", "timeout_sec", "delivery"}):
        return {"refusal_code": "per_call_ceiling_exceeded",
                "detail": f"timeout_sec must be a positive literal at most {config.per_call_timeout_sec}; "
                          "additional per-call ceilings are not admitted"}
    return None


def judge_child(parent: Path, child: Path, config: ExperimentConfig, *, runtime: Path, site: Mapping | None = None,
                parent_candidate_id: str | None = None) -> dict:
    """Validation, full compilation with the runtime's orchestrator (a compiler crash is an incident), the I2 slot
    check, a bounded planned maximum of provider calls (`unbounded_calls`), then the entry's result type against
    the parent's. Without `site`: frozen-surface validation. With
    `site` (I2): the receipt is derived from the child (`receipt` in the verdict), <child>/HYPOTHESIS.txt is then
    removed, and the one-site transaction validates the child; it applies the frozen-surface rule itself with the
    receipt's helpers allowed (a plain frozen-surface check would refuse any helper). An I3 child
    (evaluation.is_python) is judged by judge_python_child."""
    if evaluation.is_python(config):
        return judge_python_child(parent, child, config, runtime=runtime)
    receipt = None
    if site is None:
        verdict = validate_frozen_surfaces(parent, child, config)
    else:
        receipt = derive_receipt(parent, child, site, config, parent_candidate_id=parent_candidate_id)
        drop_hypothesis(child)
        verdict = validate_one_site(parent, child, receipt, config)
    shown = {"receipt": asdict(receipt) if receipt else None}
    if not verdict.accepted:
        return {**shown, "outcome": "rejected", "refusal_code": verdict.code, "detail": verdict.detail}
    compiled = compile_candidate(child, config, runtime=runtime)
    if compiled.status != "accepted":
        outcome = "incident" if any(d.get("code") in COMPILER_INCIDENT_CODES for d in compiled.diagnostics) else "rejected"
        return {**shown, "outcome": outcome, "diagnostics": list(compiled.diagnostics), **diagnosis(compiled)}
    refusal = slot_refusal(parent, child, site, config, runtime=runtime) if site else None
    if config.condition != "module":
        refusal = refusal or ledger.unbounded_refusal(child, config)
    if refusal is None:
        parent_compiled = compile_candidate(parent, config, runtime=runtime)
        if parent_compiled.status != "accepted":
            return {**shown, "outcome": "incident", "diagnostics": list(parent_compiled.diagnostics),
                    **diagnosis(parent_compiled)}
        refusal = compiled_refusal(closed_program(parent, parent_compiled.build_key),
                                   closed_program(child, compiled.build_key), config)
    if config.condition == "module":
        refusal = refusal or ledger.unbounded_refusal(child, config)
    if refusal is not None:
        return {**shown, "outcome": "rejected", **refusal}
    return {**shown, "outcome": "accepted", "program_digest": compiled.program_digest,
            "build_key": compiled.build_key}


def slot_refusal(parent: Path, child: Path, site: Mapping, config: ExperimentConfig, *, runtime: Path) -> dict | None:
    """The slot check of an accepted one-site child: the child manifest's type at the replacement's start against
    the parent site's (`slot_type_changed`; `slot_type_unavailable` when the manifest reports none, e.g. for a
    literal replacement), or None when they are equal."""
    file_name, line, column = replacement_start(parent, child, site)  # the one-site transaction located it
    found = slot_type(site_manifest(child, config, runtime=runtime), site["owner"]["name"], file_name, line, column)
    expected = site["result_type"]["canonical"]
    if found is None:
        return {"refusal_code": "slot_type_unavailable",
                "detail": f"the manifest reports no type at {file_name}:{line}:{column}"}
    if found != expected:
        return {"refusal_code": "slot_type_changed", "detail": f"the replacement is {found}, the site {expected}"}
    return None


def diagnosis(checked: CompileOutcome) -> dict:
    """The rejection fields of a failed compilation or type check: its first diagnostic's code and message."""
    first = checked.diagnostics[0] if checked.diagnostics else {}
    return {"diagnostics_class": first.get("code", UNAVAILABLE),
            "detail": first.get("message") or first.get("stderr", "")}


def judge_python_child(parent: Path, child: Path, config: ExperimentConfig, *, runtime: Path) -> dict:
    """judge_child for an I3 child: validate_python_scope, suppression_check, check_parent, check_python, then a
    bounded planned maximum (the module's frozen call cap); no slot or entry-result check (the scope rule freezes
    the signature of `run`)."""
    shown = {"receipt": None}
    verdict = validate_python_scope(parent, child, config)
    if not verdict.accepted:
        return {**shown, "outcome": "rejected", "refusal_code": verdict.code, "detail": verdict.detail}
    suppressed = suppression_check(parent, child, config)
    if suppressed is not None:
        return {**shown, "outcome": "rejected", **diagnosis(suppressed)}
    check_parent(parent, config, runtime=runtime)
    checked = check_python(child, config, runtime=runtime)
    if checked.status != "accepted":
        return {**shown, "outcome": "rejected", **diagnosis(checked)}
    refusal = ledger.unbounded_refusal(child, config)
    if refusal is not None:
        return {**shown, "outcome": "rejected", **refusal}
    return {**shown, "outcome": "accepted", "program_digest": checked.program_digest, "build_key": checked.build_key}


def suppressions(source: Path) -> list[tuple[int, str]]:
    """(line, text) of each comment of the Python module `source` (decoded as UTF-8, a coding cookie ignored) that
    silences pyright."""
    tokens = tokenize.generate_tokens(io.StringIO(source.read_text()).readline)
    return [(token.start[0], token.string) for token in tokens
            if token.type == tokenize.COMMENT and SUPPRESSION.search(token.string)]


def suppression_check(parent: Path, child: Path, config: ExperimentConfig) -> CompileOutcome | None:
    """A rejection (`type_check_failed`, rule `suppression_comment`) of a child whose entry module has a comment
    silencing pyright (`type: ignore`, `pyright: ...`) that the parent's lacks, else None."""
    (before, _), (after, _) = ledger.entry_of(parent, config), ledger.entry_of(child, config)
    known = Counter(text for _, text in suppressions(before))
    for line, text in suppressions(after):
        if known[text] == 0:
            diagnostic = {"code": "type_check_failed", "rule": "suppression_comment",
                          "message": f"{after.name}:{line}: {text}"}
            return CompileOutcome("rejected", None, None, (diagnostic,))
        known[text] -= 1
    return None


def check_parent(parent: Path, config: ExperimentConfig, *, runtime: Path) -> None:
    """Raise RuntimeError unless the parent type-checks clean against `runtime` (check_python; once per entry
    module content and runtime in this process): a runtime that does not resolve or no longer matches the frozen
    imports must never be what rejects a child."""
    source, _ = ledger.entry_of(parent, config)
    key = (hashlib.sha256(source.read_bytes()).hexdigest(), runtime.resolve())
    if key in _CLEAN_PARENTS:
        return
    checked = check_python(parent, config, runtime=runtime)
    if checked.status != "accepted":
        raise RuntimeError(f"the parent does not type-check against {runtime}: {diagnosis(checked)['detail']}")
    _CLEAN_PARENTS.add(key)


def check_python(root: Path, config: ExperimentConfig, *, runtime: Path, pyright: str = "pyright") -> CompileOutcome:
    """Type-check the candidate's entry module (ledger.entry_of) with pyright from `root`; `orchestrator` resolves
    against `runtime` (the runtime the candidate runs with) through the extraPaths of a generated
    pyrightconfig.json, wherever `root` lies (PYTHONPATH is dropped from pyright's environment, so the interpreter's
    path cannot resolve it elsewhere), and `type: ignore` comments are disabled. Accepted, with the module's program
    digest and no build key, when pyright reports no error; else rejected with one `type_check_failed` diagnostic
    per error. RuntimeError when pyright is missing or fails (an exit status other than 0 or 1)."""
    source, _ = ledger.entry_of(root, config)
    settings = {"extraPaths": [str(runtime.resolve())], "enableTypeIgnoreComments": False}
    env = {name: value for name, value in os.environ.items() if name != "PYTHONPATH"}
    with tempfile.TemporaryDirectory() as project:
        (Path(project) / "pyrightconfig.json").write_text(json.dumps(settings))
        try:
            done = subprocess.run([pyright, "--outputjson", "--project", project, str(source.relative_to(root))],
                                  cwd=root, capture_output=True, text=True, env=env)
        except FileNotFoundError as error:
            raise RuntimeError(f"{pyright} is not installed: an I3 child cannot be type-checked") from error
    if done.returncode not in (0, 1):
        raise RuntimeError(f"{pyright} exited {done.returncode} on {source}: "
                           f"{done.stdout[-2000:]}{done.stderr[-2000:]}")
    report = json.loads(done.stdout)
    if report["summary"]["errorCount"] == 0:
        return CompileOutcome("accepted", UNAVAILABLE, python_program_digest(source.read_text()), ())
    return CompileOutcome("rejected", None, None, tuple(
        {"code": "type_check_failed", "rule": d.get("rule", UNAVAILABLE),
         "message": f"{Path(d['file']).name}:{d['range']['start']['line'] + 1}: {d['message']}"}
        for d in report["generalDiagnostics"] if d["severity"] == "error"))


def validate_python_scope(parent: Path, child: Path, config: ExperimentConfig) -> Verdict:
    """Refuse an I3 child whose change leaves the mutable functions of its mutable Python file.

    Top-level nodes are compared by `ast.dump` (comments and formatting are free; suppression_check covers
    comments that silence pyright). `frozen_surface_changed`: a top-level node other than a mutable function
    (`mutable_definitions`) changed; a mutable function's parameters, return annotation or decorators changed;
    inside the mutable or added functions a `global`/`nonlocal` or import statement, a store (or `del`) whose
    target's base name is bound at the parent's top level, or a non-constant `model=`/`effort=` value; or
    (topology-only) a `model=`/`effort=` constant there that is new to the parent module. `scope_exceeded`: a
    mutable function was removed, an added top-level node is not an undecorated function, or another file differs
    (bytes; `.orc` forms). `declaration_collision`: an added function's name is already bound at top level (an
    import included) or is a builtin's. Topology-only also refuses (`frozen_surface_changed`) an ADAPTER call in
    those functions whose prompt is not a top-level prompt constant's `.format(...)` (_prompt_verdict).
    `unreadable_child`: `ast` rejects the child's mutable file, decoded as UTF-8 or with its coding cookie. Not
    refused (a recorded limitation; the shims record every provider call): calls that mutate frozen state
    (`STATE.__init__()`, `PROVIDERS.update(...)`), a `**` splat of tuning values, and direct subprocess or CLI
    calls."""
    for name in _file_names(parent, child):
        before, after = parent / name, child / name
        if name in config.mutable_files and before.is_file() and after.is_file():
            verdict = _python_file_verdict(before, after, config)
        elif _same_file(before, after):
            continue
        else:
            change = "was added" if not before.is_file() else "was removed" if not after.is_file() else "changed"
            verdict = _refuse("scope_exceeded", f"{name} {change}: only {', '.join(config.mutable_files)} may change")
        if not verdict.accepted:
            return verdict
    return ACCEPTED


def _python_file_verdict(before: Path, after: Path, config: ExperimentConfig) -> Verdict:
    parent = ast.parse(before.read_text()).body
    try:
        child = ast.parse(after.read_text(), filename=after.name).body  # UTF-8, as pyright and the records read it
        ast.parse(after.read_bytes(), filename=after.name)  # with its coding cookie, as Python runs it
    except (SyntaxError, ValueError) as error:  # ValueError: undecodable bytes, a null byte
        return _refuse("unreadable_child", f"{after.name}: {error}")
    mutable = set(config.mutable_definitions)
    parent_functions, parent_frozen = _split_python(parent, mutable)
    child_functions, child_rest = _split_python(child, mutable)
    changed = _unmatched(parent_frozen, child_rest)
    if changed:
        return _refuse("frozen_surface_changed", f"the top-level {_label(changed[0])} changed")
    added = _unmatched(child_rest, parent_frozen)
    functions = [*child_functions.values(), *(node for node in added if isinstance(node, ast.FunctionDef))]
    frozen = _top_names(parent)
    verdicts = [_signature_verdict(parent_functions, child_functions), _added_verdict(added, frozen | BUILTIN_NAMES),
                _body_verdict(functions, frozen)]
    if config.condition == "topology-only":
        prompts = {name for name in frozen if name.endswith(_PROMPT_SUFFIX)}
        verdicts += [_tuning_verdict(parent, functions), _prompt_verdict(functions, prompts)]
    return next((verdict for verdict in verdicts if not verdict.accepted), ACCEPTED)


def _unmatched(nodes: Sequence[ast.stmt], others: Sequence[ast.stmt]) -> list[ast.stmt]:
    """The `nodes` left after each of `others` cancels at most one equal node (by `ast.dump`)."""
    pending = Counter(ast.dump(node) for node in others)
    left = []
    for node in nodes:
        if pending[ast.dump(node)] > 0:
            pending[ast.dump(node)] -= 1
        else:
            left.append(node)
    return left


def _split_python(nodes: Sequence[ast.stmt], mutable: set[str]) -> tuple[dict[str, ast.FunctionDef], list[ast.stmt]]:
    """(the first top-level function of each mutable name, every other top-level node)."""
    functions: dict[str, ast.FunctionDef] = {}
    rest = []
    for node in nodes:
        if isinstance(node, ast.FunctionDef) and node.name in mutable and node.name not in functions:
            functions[node.name] = node
        else:
            rest.append(node)
    return functions, rest


def _signature_verdict(parent: Mapping[str, ast.FunctionDef], child: Mapping[str, ast.FunctionDef]) -> Verdict:
    for name, before in parent.items():
        after = child.get(name)
        if after is None:
            return _refuse("scope_exceeded", f"the mutable function {name} was removed")
        if _signature(before) != _signature(after):
            return _refuse("frozen_surface_changed", f"exported signature of {name} changed")
    return ACCEPTED


def _signature(function: ast.FunctionDef) -> tuple[str, ...]:
    """A function's parameters, return annotation and decorators."""
    return (ast.dump(function.args), function.returns and ast.dump(function.returns),
            *(ast.dump(decorator) for decorator in function.decorator_list))


def _added_verdict(added: Sequence[ast.stmt], bound: set[str]) -> Verdict:
    """Added top-level nodes must be functions with fresh names."""
    names = set(bound)
    for node in added:
        if not isinstance(node, ast.FunctionDef) or node.decorator_list:
            return _refuse("scope_exceeded", f"the top-level {_label(node)} was added: only undecorated functions "
                                             "may be")
        if node.name in names:
            return _refuse("declaration_collision", f"the added function {node.name} is already bound at top level")
        names.add(node.name)
    return ACCEPTED


def _body_verdict(functions: Sequence[ast.FunctionDef], frozen: set[str]) -> Verdict:
    """Refuse, inside `functions`, what rebinds or reaches past the frozen surface at run time (_body_problem)."""
    for function in functions:
        for node in ast.walk(function):
            problem = _body_problem(node, frozen)
            if problem:
                return _refuse("frozen_surface_changed", f"{function.name}, line {node.lineno}: {problem}")
    return ACCEPTED


def _body_problem(node: ast.AST, frozen: set[str]) -> str | None:
    if isinstance(node, (ast.Global, ast.Nonlocal, ast.Import, ast.ImportFrom)):
        return f"a {type(node).__name__} statement ({ast.unparse(node)})"
    if isinstance(node, ast.keyword) and node.arg in TUNING_ARGUMENTS and not isinstance(node.value, ast.Constant):
        return f"a non-constant {node.arg}= value ({ast.unparse(node.value)})"
    if isinstance(getattr(node, "ctx", None), (ast.Store, ast.Del)):
        base = node
        while isinstance(base, (ast.Attribute, ast.Subscript, ast.Starred)):
            base = base.value
        if isinstance(base, ast.Name) and base.id in frozen:
            return f"a store to the frozen top-level name {base.id} ({ast.unparse(node)})"
    return None


def _top_names(nodes: Sequence[ast.stmt]) -> set[str]:
    """The names the top-level `nodes` bind."""
    names: set[str] = set()
    for node in nodes:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= {alias.asname or alias.name.split(".")[0] for alias in node.names}
        else:
            names |= {n.id for n in ast.walk(node) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
    return names


def _label(node: ast.stmt) -> str:
    """A top-level node by the names it binds, else by its first line."""
    return ", ".join(sorted(_top_names([node]))) or ast.unparse(node).splitlines()[0]


def _tuning_verdict(parent: Sequence[ast.stmt], functions: Sequence[ast.FunctionDef]) -> Verdict:
    """Topology-only: the functions may use only `model=`/`effort=` constants the parent module already uses."""
    new = _tuning(functions) - _tuning(parent)
    if new:
        return _refuse("frozen_surface_changed",
                       f":model/:effort values {sorted(new, key=repr)} are new to the module under topology-only")
    return ACCEPTED


def _prompt_verdict(functions: Sequence[ast.FunctionDef], prompts: set[str]) -> Verdict:
    """Topology-only (ORC's frozen defprompt): in `functions`, every ADAPTER call passes as its prompt a call
    `<prompt constant>.format(...)` written in place (the format arguments are free), and ADAPTER is used only by
    calls."""
    for function in functions:
        names, calls = _adapter_uses(function)
        if len(calls) != len(names):
            return _refuse("frozen_surface_changed", f"{function.name}: {ADAPTER} used other than as a direct call")
        bad = next((call for call in calls if not _frozen_prompt(_prompt_argument(call), prompts)), None)
        if bad is not None:
            prompt = _prompt_argument(bad)
            return _refuse("frozen_surface_changed", f"{function.name}, line {bad.lineno}: a {ADAPTER} prompt other "
                           f"than <a top-level *{_PROMPT_SUFFIX}>.format(...) under topology-only "
                           f"({ast.unparse(prompt) if prompt else 'no prompt argument'})")
    return ACCEPTED


def _adapter_uses(function: ast.FunctionDef) -> tuple[list[ast.Name], list[ast.Call]]:
    """(every ADAPTER name in `function`, the calls whose callee is one of them)."""
    names = [node for node in ast.walk(function) if isinstance(node, ast.Name) and node.id == ADAPTER]
    return names, [node for node in ast.walk(function) if isinstance(node, ast.Call) and node.func in names]


def _frozen_prompt(prompt: ast.expr | None, prompts: set[str]) -> bool:
    """`prompt` is `<one of prompts>.format(...)`."""
    return (isinstance(prompt, ast.Call) and isinstance(prompt.func, ast.Attribute) and prompt.func.attr == "format"
            and isinstance(prompt.func.value, ast.Name) and prompt.func.value.id in prompts)


def _prompt_argument(call: ast.Call) -> ast.expr | None:
    """The prompt argument of an ADAPTER call: the second positional argument or `prompt=`."""
    if len(call.args) > 1:
        return call.args[1]
    return next((keyword.value for keyword in call.keywords if keyword.arg == "prompt"), None)


def _tuning(nodes: Sequence[ast.AST]) -> set[tuple[str | None, object]]:
    """The (keyword, value) of every `model=`/`effort=` keyword with a constant value under `nodes`."""
    return {(k.arg, k.value.value) for node in nodes for k in ast.walk(node)
            if isinstance(k, ast.keyword) and k.arg in TUNING_ARGUMENTS and isinstance(k.value, ast.Constant)}
