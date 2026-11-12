#!/usr/bin/env python3
"""Read out the four PQ-1c cells against the frozen criterion.

Usage: readout.py RESULTS_ROOT [--criterion PATH]

Reads, per cell (`RESULTS_ROOT/<cell>`, or `<cell>-retry` when the cell had its infrastructure retry):
`cell.json`, `report.json` (`report --format json`), the run's `memo.jsonl` and attempt `usage.json`
files under `workspace/.orchestrate/runs/<id>/`, `run.log` and `resume.log` (the terminal logs) and,
for a clean cell, `invalidate.json` (the invalidate check on a copy of the run). Computes the axes of
`criterion.json` and prints one JSON object whose `outcome` is Retire, Retain, Improve or
undetermined, with the reasons. Measure-free figures only: no quality claim. Calls no model and runs
no orchestrator command. Exits 0 with a readout, 2 when it refuses: the criterion's SHA-256 is not
`CRITERION_SHA256` (recorded at the rehearsal and in the plan's ledger), or a cell recorded another.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

CRITERION_SHA256 = "4e2aa4b4a15344f6b08abfbfb2e696e8e4bcc6bfeca6f2a0789f032b19928f00"
KIT = Path(__file__).resolve().parent
TURN_CLASSES = ("provider", "agent_turn")
FLAGGED_LINES = ("effect_rerun", "agent_bootstrap_restarted")
LOGS = ("run.log", "resume.log")


class Refusal(Exception):
    """The readout cannot be trusted against this criterion or these cells."""


def load_criterion(path: Path) -> dict:
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != CRITERION_SHA256:
        raise Refusal(f"{path} has sha256 {digest}, not the frozen {CRITERION_SHA256}")
    return json.loads(path.read_text(encoding="utf-8"))


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def _run_root(cell_dir: Path) -> Path | None:
    runs = sorted((cell_dir / "workspace" / ".orchestrate" / "runs").glob("*/memo.jsonl"))
    return runs[0].parent if len(runs) == 1 else None


def turn_facts(rows: list[dict]) -> dict:
    """Committed turns, turn identities started more than once, and committed turns started again."""
    sessions = {row["identity"] for row in rows if row["record"] == "committed" and row.get("effect_class") == "agent"}
    committed, redispatched = set(), set()
    started = Counter()
    for row in rows:
        identity = row.get("identity")
        if row["record"] == "started" and identity not in sessions:
            started[identity] += 1
            if identity in committed:
                redispatched.add(identity)
        elif row["record"] == "committed" and row.get("effect_class") in TURN_CLASSES:
            committed.add(identity)
    return {"committed_turns": sorted(committed), "redispatched": sorted(redispatched),
            "started_twice": sorted(identity for identity, count in started.items() if count > 1)}


def usage_facts(run_root: Path, model: str) -> dict:
    """Per provider attempt (an attempt directory holding prompt.txt): is its usage reported and complete."""
    attempts = sorted(path.parent for path in run_root.glob("effects/*/attempt-*/prompt.txt"))
    unmetered, models = [], set()
    for attempt in attempts:
        usage = _json(attempt / "usage.json") or {}
        models.update(row.get("model") for row in usage.get("rows", []))
        if usage.get("status") != "reported" or usage.get("complete") is not True:
            unmetered.append(f"{attempt.relative_to(run_root).as_posix()}: {usage.get('status', 'absent')}")
    return {"provider_attempts": len(attempts), "unmetered_attempts": unmetered,
            "usage_recorded": bool(attempts) and not unmetered, "models": sorted(map(str, models)),
            "other_models": sorted(str(name) for name in models if name != model)}


def cost(report: dict) -> tuple[float | None, str | None]:
    """`run.usage.cost_usd` when it is a whole figure; otherwise None and why."""
    usage = (report.get("run") or {}).get("usage")
    if not usage:
        return None, "no run.usage in the report"
    if usage.get("cost_usd") is None or usage.get("partial") or usage.get("unknown_attempts"):
        return None, (f"cost is partial or unknown (cost_usd {usage.get('cost_usd')}, partial {usage.get('partial')}, "
                      f"unknown attempts {usage.get('unknown_attempts')})")
    return float(usage["cost_usd"]), None


def _invalidate(cell_dir: Path, meta: dict) -> dict | None:
    """A clean cell's invalidate check; it passes when the variant refuses unchanged and the baseline allows it."""
    check = _json(cell_dir / "invalidate.json")
    if meta["mode"] != "clean":
        return None
    if check is None:
        return {"passed": None}
    wanted = (2, True, True) if meta["arm"] == "variant" else (0,)
    found = (check["exit"], check["coordinator_committed"], check["bytes_unchanged"])[:len(wanted)]
    return {"passed": found == wanted, **check}


def _flagged(cell_dir: Path) -> list[str]:
    logs = [(log, (cell_dir / log).read_text(encoding="utf-8", errors="replace")) for log in LOGS
            if (cell_dir / log).is_file()]
    return [f"{log}: {flag} line" for log, text in logs for flag in FLAGGED_LINES if flag in text]


def read_cell(cell_dir: Path, criterion: dict) -> dict:
    meta = _json(cell_dir / "cell.json")
    if meta is None:
        return {"present": False}
    if meta.get("criterion_sha256") != CRITERION_SHA256:
        raise Refusal(f"{cell_dir} recorded criterion sha256 {meta.get('criterion_sha256')}")
    report = _json(cell_dir / "report.json") or {}
    run = report.get("run") or {}
    run_root = _run_root(cell_dir) or cell_dir / "no-run"
    memo = run_root / "memo.jsonl"
    turns = turn_facts([json.loads(line) for line in memo.read_text().splitlines()] if memo.is_file() else [])
    cost_usd, cost_reason = cost(report)
    bound = run.get("bound_inputs") or {}
    repeated = [f"{identity}: started more than once" for identity in turns["started_twice"]]
    return {"present": True, "dir": cell_dir.name, "meta": meta, "status": run.get("status"),
            "completed": run.get("status") == "completed" and len(turns["committed_turns"]) == criterion["turns_per_run"],
            **turns, "repeated_work": repeated + _flagged(cell_dir), **usage_facts(run_root, criterion["model"]),
            "cost_usd": cost_usd, "cost_reason": cost_reason,
            "bound_models": sorted({bound.get("planner_model"), bound.get("reviewer_model")} - {None}),
            "invalidate": _invalidate(cell_dir, meta), "elapsed_sec": meta["run_sec"] + meta["resume_sec"]}


def _stop_invalid(meta: dict) -> bool:
    """The wrapper stopped a resumed cell with a turn in flight, or elsewhere than after the reviewer's first turn."""
    stop = meta.get("stop")
    return bool(meta["mode"] == "resumed" and stop and stop["exit"] == 75
                and (stop["pending"] or not stop["last_identity"].endswith("/ feedback")))


def _cell_invalid(name: str, cell: dict, model: str) -> list[str]:
    if not cell["present"]:
        return [f"{name}: missing"]
    meta, reasons = cell["meta"], []
    if cell["other_models"] or cell["bound_models"] not in ([], [model]):
        reasons.append(f"{name}: a model other than {model} ({cell['other_models'] or cell['bound_models']})")
    if not meta["rehearsal"] and meta["runtime_dirty"]:
        reasons.append(f"{name}: ran on a runtime with uncommitted changes")
    if _stop_invalid(meta):
        reasons.append(f"{name}: the wrapper stop left a turn in flight or stopped elsewhere ({meta['stop']})")
    return reasons


def invalid(cells: dict, model: str) -> list[str]:
    reasons = [reason for name, cell in cells.items() for reason in _cell_invalid(name, cell, model)]
    present = [cell["meta"] for cell in cells.values() if cell["present"]]
    differing = {key: {meta[key] for meta in present} for key in ("rehearsal", "runtime_commit", "fixture_commit")}
    differing |= {f"{arm} source_sha256": {meta["source_sha256"] for meta in present if meta["arm"] == arm}
                  for arm in ("variant", "baseline")}
    return reasons + [f"cells differ in {key}" for key, values in differing.items() if len(values) > 1]


def ratios(cells: dict, criterion: dict) -> dict:
    found = {}
    for pair, (variant, baseline) in criterion["pairs"].items():
        v, b = (cells[name].get("cost_usd") for name in (variant, baseline))
        found[pair] = v / b if v is not None and b else None
    return found


def _retire_without_cost(cells: dict, criterion: dict) -> list[str]:
    pairs = criterion["pairs"].values()
    reasons = [f"{variant} did not complete while {baseline} did" for variant, baseline in pairs
               if not cells[variant]["completed"] and cells[baseline]["completed"]]
    return reasons + [f"{variant}: committed turn dispatched again: {identity}" for variant, _ in pairs
                      for identity in cells[variant]["redispatched"]]


def _by_cost(found: dict, holds, outcome: str, rule: str) -> tuple[str, list[str]] | None:
    """`outcome` when `holds` is true of both ratios; undetermined when an unknown ratio could still give it."""
    known = [ratio for ratio in found.values() if ratio is not None]
    if not all(holds(ratio) for ratio in known):
        return None
    unknown = [f"{pair}: cost ratio undetermined" for pair, ratio in found.items() if ratio is None]
    if unknown:
        return "undetermined", [*unknown, f"{outcome} by cost is not excluded"]
    return outcome, [f"cost ratio {rule} in both pairs: {found}"]


def decide(cells: dict, found: dict, criterion: dict, bad: list[str]) -> tuple[str, list[str]]:
    """The criterion's `decision_order`: invalid, Retire without cost, Retire by cost, Retain, Improve."""
    if bad:
        return "undetermined", bad
    retire = _retire_without_cost(cells, criterion)
    if retire:
        return "Retire", retire
    high = criterion["thresholds"]["retire_cost_ratio_at_or_above"]
    low = criterion["thresholds"]["retain_cost_ratio_at_or_below"]
    by_cost = _by_cost(found, lambda ratio: ratio >= high, "Retire", f"at or above {high}")
    if by_cost:
        return by_cost
    not_clean = [f"{name}: not completed" for name, cell in cells.items() if not cell["completed"]]
    not_clean += [f"{name}: {reason}" for name, cell in cells.items() for reason in cell["repeated_work"]]
    by_cost = None if not_clean else _by_cost(found, lambda ratio: ratio <= low, "Retain", f"at or below {low}")
    return by_cost or ("Improve", [*not_clean, f"cost ratios {found} meet neither the Retire nor the Retain rule"])


def _shown(cell: dict) -> dict:
    if not cell["present"]:
        return cell
    meta = cell["meta"]
    return {**{key: value for key, value in cell.items() if key != "meta"},
            **{key: meta[key] for key in ("claude_version", "run_exit", "resume_exit", "stop", "retry_reason")}}


def readout(root: Path, criterion_path: Path) -> dict:
    criterion = load_criterion(criterion_path)
    chosen = {name: (root / f"{name}-retry" if (root / f"{name}-retry").is_dir() else root / name)
              for name in criterion["cells"]}
    cells = {name: read_cell(path, criterion) for name, path in chosen.items()}
    bad = invalid(cells, criterion["model"])
    found = ratios(cells, criterion)
    outcome, reasons = decide(cells, found, criterion, bad)
    return {"outcome": outcome, "reasons": reasons, "ratios": found, "criterion_sha256": CRITERION_SHA256,
            "rehearsal": any(cell["meta"]["rehearsal"] for cell in cells.values() if cell["present"]),
            "claims": criterion["claims"], "cannot_decide": criterion["cannot_decide"],
            "owner_judgment": criterion["owner_judgment"], "cells": {name: _shown(cell) for name, cell in cells.items()}}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--criterion", type=Path, default=KIT / "criterion.json")
    args = parser.parse_args(argv)
    try:
        shown = readout(args.root.resolve(), args.criterion)
    except Refusal as refused:
        print(f"readout.py: refused: {refused}", file=sys.stderr)
        return 2
    print(json.dumps(shown, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
