"""Provider-call ledger <evidence>/calls.json and the planned maximum of one launch.

The ledger is a JSON list with one entry per evaluation or episode launch, and (mode 2, judging.judge_generation)
one per judge scoring a pool: {kind, key, planned, calls, ...}; a judge entry (`kind: "judge"`, key
"gen <n> <task> <judge>") plans one call per batch of the pool (score.orc calls the judge once per batch) and
settles on the shim calls under <pool>/records/judges/<judge>.
`reserve` appends an entry with the launch's planned maximum before it starts; `settle` records the calls the
shims recorded for it (the calls/<n>/ directories under its records directory) after it ends. The ledger total
counts a settled entry's calls and an unsettled entry's planned maximum (a launch in flight, or one that died
before settling). `reserve` refuses a launch (CallCapExceeded) when that total plus its planned maximum would
exceed the cap. One lock covers reading and writing, so concurrent launches of one driver process cannot
overshoot the cap.
"""

import ast
import json
import math
import threading
from pathlib import Path

from experiments.orc_structural_search.config import ExperimentConfig
from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.sexpr import IntAtom, KeywordAtom, ListExpr, SExpr, SymbolAtom

LEDGER = "calls.json"
DEFINITIONS = ("defproc", "defworkflow", "defun")
BINDING_FORMS = ("let*", "list/map", "list/map-effect")  # (form ((name value) ...) body ...)
CALL_CAP = "MAX_PROVIDER_CALLS"  # an I3 module's frozen runtime cap on provider calls
_LOCK = threading.Lock()  # ponytail: per process; two driver processes on one evidence root are not serialized


class CallCapExceeded(RuntimeError):
    pass


def total(entries: list[dict]) -> int:
    return sum(entry["planned"] if entry["calls"] is None else entry["calls"] for entry in entries)


def _read(path: Path) -> list[dict]:
    return json.loads(path.read_text()) if path.exists() else []


def reserve(evidence_root: Path, *, kind: str, key: str, planned: int, cap: int) -> int:
    """Append the launch's entry and return its index; refuse it when the total plus `planned` exceeds `cap`."""
    path = evidence_root / LEDGER
    with _LOCK:
        entries = _read(path)
        if total(entries) + planned > cap:
            raise CallCapExceeded(f"{kind} {key}: {total(entries)} provider calls recorded or reserved in {path} "
                                  f"plus at most {planned} for this launch exceed the call cap {cap}")
        entries.append({"kind": kind, "key": key, "planned": planned, "calls": None})
        path.write_text(json.dumps(entries, indent=2) + "\n")
        return len(entries) - 1


def settle(evidence_root: Path, index: int, records: Path, **fields: object) -> int:
    """Record the shim calls under `records` (and `fields`) on entry `index`; return the call count."""
    calls = len(list((records / "calls").glob("*")))
    path = evidence_root / LEDGER
    with _LOCK:
        entries = _read(path)
        entries[index].update(calls=calls, **fields)
        path.write_text(json.dumps(entries, indent=2) + "\n")
    return calls


def settle_killed(evidence_root: Path, kind: str, key: str, records: Path) -> None:
    """Settle the first unsettled entry of `kind` and `key` (a launch killed before settling) from the shim calls
    under `records`; no such entry: nothing."""
    entries = _read(evidence_root / LEDGER)
    index = next((i for i, e in enumerate(entries) if (e["kind"], e["key"], e["calls"]) == (kind, key, None)), None)
    if index is not None:
        settle(evidence_root, index, records)


def settle_killed_episodes(evidence_root: Path) -> None:
    """Settle every unsettled episode entry whose records <evidence>/episodes/<key> exist (episodes killed in
    flight; a continue runs this before its first launch)."""
    for entry in _read(evidence_root / LEDGER):
        records = evidence_root / "episodes" / entry["key"]
        if entry["kind"] == "episode" and entry["calls"] is None and records.is_dir():
            settle_killed(evidence_root, "episode", entry["key"], records)


def entry_of(root: Path, config: ExperimentConfig) -> tuple[Path, str]:
    """(the entry module's source, the entry definition's name) of the candidate at `root`: <module>.py when that
    file is one of the mutable files (an I3 candidate), else <module>.orc."""
    module, entry = config.entry_workflow.split("::")
    python = Path(config.source_root, f"{module}.py") in {Path(name) for name in config.mutable_files}
    return (root / config.source_root / module).with_suffix(".py" if python else ".orc"), entry


def planned_calls(root: Path, config: ExperimentConfig, *, runtime: Path | None = None) -> int:
    """The planned maximum of one evaluation of the candidate at `root`: max_provider_calls of its entry, or for a
    Python entry module its frozen call cap (python_call_cap)."""
    source, entry = entry_of(root, config)
    if config.condition == "module" and source.suffix != ".py":
        from experiments.orc_structural_search.acceptance import require_candidate
        from experiments.orc_structural_search.closed_checks import closed_program, planned_maximum
        compiled = require_candidate(root, config, runtime=runtime or Path(__file__).resolve().parents[2])
        return planned_maximum(closed_program(root, compiled.build_key))
    return python_call_cap(source) if source.suffix == ".py" else max_provider_calls(source, entry)


def python_call_cap(source: Path) -> int:
    """The integer literal of the Python module's last top-level `MAX_PROVIDER_CALLS` assignment: the runtime cap
    its provider adapter enforces. Refuses (CallCapExceeded) a module without one."""
    caps = [node.value for node in ast.parse(source.read_text()).body if isinstance(node, (ast.Assign, ast.AnnAssign))
            and any(isinstance(target, ast.Name) and target.id == CALL_CAP
                    for target in (node.targets if isinstance(node, ast.Assign) else [node.target]))]
    cap = caps[-1] if caps else None
    if not (isinstance(cap, ast.Constant) and type(cap.value) is int):
        raise CallCapExceeded(f"{source}: no top-level {CALL_CAP} integer literal, so the planned maximum is "
                              "unbounded; the launch is refused")
    return cap.value


def unbounded_refusal(root: Path, config: ExperimentConfig, *, runtime: Path | None = None) -> dict | None:
    """The `unbounded_calls` refusal of a candidate whose planned maximum is unbounded, else None: such a child
    is refused at episode acceptance, so it never reaches an evaluation. Compilation failures retain their envelope."""
    from experiments.orc_structural_search.acceptance import CandidateAdmissionError
    try:
        planned_calls(root, config, runtime=runtime)
    except CandidateAdmissionError as error:
        return error.verdict
    except CallCapExceeded as error:
        return {"refusal_code": "unbounded_calls", "detail": str(error)}
    return None


def max_provider_calls(source: Path, entry: str) -> int:
    """An upper bound on the provider calls one run of the definition `entry` of the module `source` makes: every
    `provider-result` counts once, a call of one of the module's own definitions (by name, or through `call`, in
    an expression position: binder names, parameter lists and match patterns are none) counts that definition's
    calls, each times the `:max` of every enclosing form that has one (`loop/recur`, `list/map-effect`). Refuses
    (CallCapExceeded) a maximum that is unbounded: a provider call under a non-literal `:max`, or a recursive call
    path that reaches a provider call (a recursion reaching none plans 0)."""
    # ponytail: a list in expression position headed by a definition's name counts as its call; a local function
    # shadowing that name would overcount, which only plans more calls
    definitions: dict[str, ListExpr] = {}
    _collect(read_sexpr_file(source), definitions)
    if entry not in definitions:
        raise ValueError(f"{source} defines no {entry}: no planned maximum")
    calls = _calls(definitions[entry], definitions, (entry,))
    if calls == math.inf:
        raise CallCapExceeded(f"{source}::{entry}: a provider call under a non-literal :max, or a recursion reaching "
                              "one, makes the planned maximum unbounded; the launch is refused")
    return int(calls)


def _head(form: SExpr) -> str | None:
    items = form.items if isinstance(form, ListExpr) else ()
    return items[0].value if items and isinstance(items[0], SymbolAtom) else None


def _callee(form: ListExpr) -> str | None:
    items, head = form.items, _head(form)
    return items[1].value if head == "call" and len(items) > 1 and isinstance(items[1], SymbolAtom) else head


def _collect(form: SExpr, definitions: dict[str, ListExpr]) -> None:
    if not isinstance(form, ListExpr):
        return
    if _head(form) in DEFINITIONS and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom):
        definitions[form.items[1].value] = form
    for item in form.items:
        _collect(item, definitions)


def _pairs(forms: tuple, skip: int) -> list:
    """The values of binder entries (each a list whose first `skip` items are a name and a type)."""
    return [x for entry in forms if isinstance(entry, ListExpr) for x in entry.items[skip:]]


def _children(form: ListExpr) -> list:
    """The forms of `form` in expression position: binder names, parameter lists and match patterns left out."""
    items, head = form.items, _head(form)
    if head in DEFINITIONS:  # (defproc name params ...)
        return list(items[3:])
    if head == "fn":
        return list(items[2:])
    if head in BINDING_FORMS and len(items) > 1 and isinstance(items[1], ListExpr):
        return _pairs(items[1].items, 1) + list(items[2:])
    if head == "loop-state":  # (loop-state (name Type init) ...)
        return _pairs(items[1:], 2)
    if head == "match":  # (match subject ((Pattern binder) body) ...)
        return list(items[1:2]) + _pairs(items[2:], 1)
    return list(items)


def _bound(items: tuple) -> float:
    """The form's `:max` (inf when it is not an integer literal), or 1 without one."""
    for key, value in zip(items, items[1:]):
        if isinstance(key, KeywordAtom) and key.value == ":max":
            return value.value if isinstance(value, IntAtom) else math.inf
    return 1


def _reaches_provider(form: SExpr, definitions: dict[str, ListExpr], seen: frozenset) -> bool:
    if not isinstance(form, ListExpr):
        return False
    callee = _callee(form)
    if _head(form) == "provider-result" or (
            callee in definitions and callee not in seen and _head(form) not in DEFINITIONS
            and _reaches_provider(definitions[callee], definitions, seen | {callee})):
        return True
    return any(_reaches_provider(item, definitions, seen) for item in _children(form))


def _call(callee: str, definitions: dict[str, ListExpr], stack: tuple[str, ...]) -> float:
    """The calls of one call of `callee`: its definition's, or for a recursive call inf when it reaches a provider
    call, else 0."""
    if callee in stack:
        return math.inf if _reaches_provider(definitions[callee], definitions, frozenset({callee})) else 0
    return _calls(definitions[callee], definitions, (*stack, callee))


def _calls(form: SExpr, definitions: dict[str, ListExpr], stack: tuple[str, ...]) -> float:
    if not isinstance(form, ListExpr):
        return 0
    head, callee = _head(form), _callee(form)
    inner = sum(_calls(item, definitions, stack) for item in _children(form))
    if callee in definitions and head not in DEFINITIONS:
        inner += _call(callee, definitions, stack)
    return (head == "provider-result") + (_bound(form.items) * inner if inner else 0)
