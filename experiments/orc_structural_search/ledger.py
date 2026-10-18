"""Provider-call ledger <evidence>/calls.json and the planned maximum of one launch.

The ledger is a JSON list with one entry per evaluation or episode launch, and (mode 2, adaptive.judge_generation)
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

import json
import math
import threading
from pathlib import Path

from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.sexpr import IntAtom, KeywordAtom, ListExpr, SExpr, SymbolAtom

LEDGER = "calls.json"
DEFINITIONS = ("defproc", "defworkflow", "defun")
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


def max_provider_calls(source: Path, entry: str) -> int:
    """An upper bound on the provider calls one run of the definition `entry` of the module `source` makes: every
    `provider-result` counts once, a call of one of the module's own definitions (by name, or through `call`)
    counts that definition's calls, each times the `:max` of every enclosing form that has one (`loop/recur`,
    `list/map-effect`). Refuses (CallCapExceeded) a maximum that is unbounded: a provider call under a non-literal
    `:max`, or a recursive definition."""
    # ponytail: any list headed by a definition's name counts as its call (a `let*` binding of that name too);
    # an overcount only plans more calls
    definitions: dict[str, ListExpr] = {}
    _collect(read_sexpr_file(source), definitions)
    if entry not in definitions:
        raise ValueError(f"{source} defines no {entry}: no planned maximum")
    calls = _calls(definitions[entry], definitions, (entry,))
    if calls == math.inf:
        raise CallCapExceeded(f"{source}::{entry}: a provider call under a non-literal :max (or a recursive "
                              "definition) makes the planned maximum unbounded; the launch is refused")
    return int(calls)


def _head(form: SExpr) -> str | None:
    items = form.items if isinstance(form, ListExpr) else ()
    return items[0].value if items and isinstance(items[0], SymbolAtom) else None


def _collect(form: SExpr, definitions: dict[str, ListExpr]) -> None:
    if not isinstance(form, ListExpr):
        return
    if _head(form) in DEFINITIONS and len(form.items) > 1 and isinstance(form.items[1], SymbolAtom):
        definitions[form.items[1].value] = form
    for item in form.items:
        _collect(item, definitions)


def _bound(items: tuple) -> float:
    """The form's `:max` (inf when it is not an integer literal), or 1 without one."""
    for key, value in zip(items, items[1:]):
        if isinstance(key, KeywordAtom) and key.value == ":max":
            return value.value if isinstance(value, IntAtom) else math.inf
    return 1


def _calls(form: SExpr, definitions: dict[str, ListExpr], stack: tuple[str, ...]) -> float:
    if not isinstance(form, ListExpr):
        return 0
    items, head = form.items, _head(form)
    callee = items[1].value if head == "call" and len(items) > 1 and isinstance(items[1], SymbolAtom) else head
    inner = sum(_calls(item, definitions, stack) for item in items)
    if callee in definitions and head not in DEFINITIONS:
        inner += math.inf if callee in stack else _calls(definitions[callee], definitions, (*stack, callee))
    return (head == "provider-result") + (_bound(items) * inner if inner else 0)
