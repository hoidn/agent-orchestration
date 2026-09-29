"""A view of a run derived from its memo and its closed program (design section 10), for `orchestrator report`.

The view is a state of the flat route's shape, so the present report projection
(`_state_only_snapshot`) renders it. Rows come from the memo; the run's status and its
outputs come from evaluating the program again against the memo without launching
anything (a pure `halt` is not an effect and leaves no record); whether an effect is in
flight right now comes from the memo's lock; a command's output preview from the
attempt's log file beside the memo.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .evaluator import EvaluationFailed, Pending, _Evaluator
from .memo import MemoSnapshot, read_records
from .performers import Performers
from .sites import ClosedProgram


def _flatten(prefix: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {prefix or "__result__": value}
    flat: dict[str, Any] = {}
    for key, item in value.items():
        flat.update(_flatten(f"{prefix}__{key}" if prefix else key, item))
    return flat


def _row(record: dict[str, Any], row: dict[str, Any], run_root: Path) -> None:
    kind = record["record"]
    if kind == "started":
        row.update(status="running", started=record["time"], attempt=record["attempt"])
        row.pop("error", None)
    elif kind == "committed":
        stdout = run_root / Path(record["result_path"]).parent / "stdout.txt"
        row.update(status="completed", exit_code=0, artifacts=_flatten("", record["value"]),
                   duration_ms=int((record["time"] - row.get("started", record["time"])) * 1000),
                   output=stdout.read_text(encoding="utf-8") if stdout.exists() else None)
    elif kind == "failed":
        row.update(status="failed", exit_code=record.get("exit_code", 1),
                   error={"type": record["code"], "message": record["code"], "context": record})
    else:
        row.update(status="running", waiting_for=record["request"])


def derive_state(program: ClosedProgram, run_root: Path) -> dict[str, Any]:
    header = json.loads((run_root / "run.json").read_text(encoding="utf-8"))
    steps: dict[str, dict[str, Any]] = {}
    for record in read_records(run_root):
        row = steps.setdefault(record["identity"], {
            "name": record["identity"], "step_id": hashlib.sha256(record["identity"].encode()).hexdigest()[:16]})
        _row(record, row, run_root)
    memo = MemoSnapshot(run_root)
    alive = memo.writer_alive()
    state: dict[str, Any] = {"run_id": run_root.name, "steps": steps, "bound_inputs": header["bound_inputs"],
                             "status": "running", "current_step": None}
    evaluator = _Evaluator(program, run_root, Performers(run_root), lambda _event, _identity: None)
    evaluator.memo, evaluator.dry = memo, True
    try:
        state["workflow_outputs"] = _flatten("return", evaluator.run(header["bound_inputs"]))
        state["status"] = "completed"
    except Pending as pending:
        if pending.entry.failed is not None and not alive:
            state["status"] = "failed"
            state["error"] = {"type": pending.entry.failed["code"], "message": pending.identity}
        elif pending.entry.attempts:
            state["current_step"] = {"name": pending.identity, "status": "running" if alive else "interrupted",
                                     "step_id": steps[pending.identity]["step_id"]}
        else:
            state["next_effect"] = pending.identity
    except EvaluationFailed as failed:
        state.update(status="failed", error={"type": failed.code, "message": str(failed)})
    return state
