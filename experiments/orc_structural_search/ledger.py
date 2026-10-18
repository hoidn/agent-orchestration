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
import threading
from pathlib import Path

from orchestrator.workflow_lisp.reader import read_sexpr_file
from orchestrator.workflow_lisp.sexpr import IntAtom, KeywordAtom, ListExpr, SExpr, SymbolAtom

LEDGER = "calls.json"
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


def max_provider_calls(source: Path) -> int:
    """An upper bound on the provider calls one run of the module `source` makes: every `provider-result` counts
    once, times the `:max` of each enclosing form that has one (`loop/recur`, `list/map-effect`)."""
    # ponytail: a provider call inside a definition the entry calls several times counts once; the seeds call none
    return _calls(read_sexpr_file(source))


def _calls(form: SExpr) -> int:
    if not isinstance(form, ListExpr):
        return 0
    items = form.items
    bound = next((value.value for key, value in zip(items, items[1:])
                  if isinstance(key, KeywordAtom) and key.value == ":max" and isinstance(value, IntAtom)), 1)
    own = bool(items) and isinstance(items[0], SymbolAtom) and items[0].value == "provider-result"
    return own + bound * sum(_calls(item) for item in items)
