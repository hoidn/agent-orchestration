#!/usr/bin/env python3
"""Read out the four PQ-1c cells against the frozen criterion.

Usage: readout.py RESULTS_ROOT [--criterion PATH]
       readout.py --retry-check CELL_DIR      (for run_cell.sh: exit 0 when CELL_DIR is an infrastructure failure)

Reads `manifest.json` beside itself and refuses unless every file it lists (this script, `criterion.json`,
the launcher, the wrapper, the bindings) has the listed SHA-256. Then reads, per cell (`RESULTS_ROOT/<cell>`,
or `<cell>-retry` when the cell had the kit's infrastructure retry): `cell.json`, `report.json`
(`report --format json`), the run's `memo.jsonl` and each provider attempt's `usage.json` and `stdout.txt`
under `workspace/.orchestrate/runs/<id>/`, `run.log` and `resume.log`, `codex-calls.log`,
`nested-calls.log` and, for a clean cell, `invalidate.json`. Computes the axes of `criterion.json` and prints
one JSON object whose `outcome` is Retire, Retain, Improve or undetermined, with the reasons. A cell whose
record is missing, incomplete or contaminated, or that stopped for a launch, login, metering or isolation
reason, is an infrastructure failure: it makes the readout undetermined, since only workflow-level outcomes
decide. A stop by the spend cap or the per-call budget is a cost outcome: the cell did not complete.
Measure-free figures only: no quality claim. Calls no model and runs no orchestrator command. Exits 0 with a
readout; 2 when it refuses: a kit file differs from the manifest, a cell recorded another manifest, or a cell
has a retry although its first attempt was not an infrastructure failure.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import sys

KIT = Path(__file__).resolve().parent
MANIFEST = KIT / "manifest.json"
TURN_CLASSES = ("provider", "agent_turn")
FLAGGED_LINES = ("effect_rerun", "agent_bootstrap_restarted")
UNMETERED_LINE = "spend_cap_unmetered"   # the cap could not meter a call: infrastructure
CAP_REACHED_LINE = "spend_cap_reached"    # the run spent its cap: a cost outcome
BUDGET_STOP = "error_max_budget_usd"      # the CLI's per-call budget stopped a call: a cost outcome
INIT_KEYS = ("plugins", "mcp_servers", "skills", "slash_commands", "agents", "model", "session_id")
LOGS = ("run.log", "resume.log")
META_KEYS = ("cell", "arm", "mode", "slot", "rehearsal", "runtime_commit", "runtime_dirty", "source_sha256",
             "fixture_commit", "run_exit", "stop", "resume_exit", "report_exit", "run_sec", "resume_sec",
             "manifest_sha256", "claude_version", "python_version", "price_table_sha256", "native_sessions")
# Cells must agree on these; a difference makes the readout undetermined.
SHARED_KEYS = ("rehearsal", "runtime_commit", "fixture_commit", "claude_version", "python_version", "price_table_sha256")
STOPPED = 75


class Refusal(Exception):
    """The readout cannot be trusted against this criterion or these cells."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_kit(criterion_path: Path) -> tuple[dict, str]:
    """(criterion, manifest SHA-256) once every file the manifest lists matches it; refuses otherwise."""
    for name, wanted in json.loads(MANIFEST.read_text(encoding="utf-8")).items():
        path = criterion_path if name == "criterion.json" else KIT / name
        if _sha256(path) != wanted:
            raise Refusal(f"{path} has sha256 {_sha256(path)}, not the manifest's {wanted}")
    return json.loads(criterion_path.read_text(encoding="utf-8")), _sha256(MANIFEST)


def _json(path: Path):
    """The file's JSON value, or None when it is absent or unreadable."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _jsonl(path: Path) -> list[dict]:
    """The JSON objects of a JSON-lines file; other lines are skipped."""
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if path.is_file() else []:
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue
    return [row for row in rows if isinstance(row, dict)]


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


def _attempts(run_root: Path | None) -> list[Path]:
    """Provider attempts: attempt directories holding prompt.txt."""
    return sorted(path.parent for path in run_root.glob("effects/*/attempt-*/prompt.txt")) if run_root else []


def _attempt_usage(attempt: Path) -> tuple[dict, list[dict], bool]:
    """(usage.json, its rows, whether the model produced output) of one attempt."""
    usage = _json(attempt / "usage.json")
    usage = usage if isinstance(usage, dict) else {}
    rows = [row for row in usage.get("rows") or [] if isinstance(row, dict)]
    output = sum((row.get("tokens") or {}).get("output") or 0 for row in rows)
    return usage, rows, usage.get("status") == "reported" and output > 0


def usage_facts(run_root: Path | None, model: str) -> dict:
    """Per provider attempt: is its usage reported and complete, and did the model produce any output."""
    attempts = _attempts(run_root)
    unmetered, silent, models = [], [], set()
    for attempt in attempts:
        usage, rows, spoke = _attempt_usage(attempt)
        models.update(str(row.get("model")) for row in rows)
        where = attempt.relative_to(run_root).as_posix()
        if usage.get("status") != "reported" or usage.get("complete") is not True:
            unmetered.append(f"{where}: {usage.get('status', 'absent')}")
        if not spoke:
            silent.append(f"{where}: no model output recorded ({usage.get('reason', usage.get('status', 'absent'))})")
    return {"provider_attempts": len(attempts), "unmetered_attempts": unmetered, "silent_attempts": silent,
            "usage_recorded": bool(attempts) and not unmetered, "models": sorted(models),
            "other_models": sorted(name for name in models if name != model)}


def _listed(value) -> list:
    """A list as found; anything else is kept as one flagged entry (fails closed)."""
    return value if isinstance(value, list) else [value]


def _builtin_plugin(plugin) -> bool:
    return isinstance(plugin, dict) and plugin.get("path") == "builtin" and str(plugin.get("source", "")).endswith("@builtin")


def _not_removed(init: dict, criterion: dict) -> dict:
    """What an isolated session's init event should not list: user plugins and agents, MCP servers, skills,
    slash commands, another model."""
    builtin_agents = criterion["isolation"]["builtin_agents"]
    shown = {"plugins": [plugin for plugin in _listed(init["plugins"]) if not _builtin_plugin(plugin)],
             "agents": [agent for agent in _listed(init["agents"]) if agent not in builtin_agents],
             **{key: _listed(init[key]) for key in ("mcp_servers", "skills", "slash_commands")},
             "model": [] if init["model"] == criterion["model"] else [init["model"]]}
    return {key: value for key, value in shown.items() if value}


def _init_problem(rows: list[dict], criterion: dict) -> str | None:
    """The attempt has exactly one stream-json init event, with every key read here, listing nothing the
    isolation flags should have removed. A missing event or key is a problem (fails closed)."""
    inits = [row for row in rows if row.get("type") == "system" and row.get("subtype") == "init"]
    if len(inits) != 1:
        return f"{len(inits)} init events, not one"
    missing = [key for key in INIT_KEYS if key not in inits[0]]
    if missing:
        return f"the init event lacks {missing}"
    shown = _not_removed(inits[0], criterion)
    return f"the init event shows what isolation should have removed: {shown}" if shown else None


def attempt_facts(run_root: Path | None, criterion: dict) -> dict:
    """Per provider attempt: its init-event problems, the sessions it names and whether the CLI's budget stopped it."""
    problems, sessions, budget_stops = [], set(), []
    for attempt in _attempts(run_root):
        where, rows = attempt.relative_to(run_root).as_posix(), _jsonl(attempt / "stdout.txt")
        problem = _init_problem(rows, criterion)
        problems += [f"{where}: {problem}"] if problem else []
        sessions |= {str(row.get("session_id")) for row in rows if row.get("subtype") == "init"}
        budget_stops += [f"{where}: {BUDGET_STOP}"] if any(row.get("subtype") == BUDGET_STOP for row in rows) else []
    return {"init_problems": problems, "sessions": sorted(sessions), "budget_stops": budget_stops}


def cost(report: dict) -> tuple[float | None, str | None]:
    """`run.usage.cost_usd` when it is a whole, finite figure above zero; otherwise None and why."""
    usage = (report.get("run") or {}).get("usage")
    if not usage:
        return None, "no run.usage in the report"
    value = usage.get("cost_usd")
    if usage.get("partial") or usage.get("unknown_attempts"):
        return None, f"cost is partial (partial {usage.get('partial')}, unknown attempts {usage.get('unknown_attempts')})"
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        return None, f"cost {value!r} is not a finite number above zero"
    return float(value), None


def _invalidate(cell_dir: Path, meta: dict) -> dict | None:
    """A clean cell's invalidate check; it passes when the variant refuses unchanged and the baseline allows it."""
    check = _json(cell_dir / "invalidate.json")
    if meta["mode"] != "clean":
        return None
    if not isinstance(check, dict):
        return {"passed": None}
    wanted = (2, True, True) if meta["arm"] == "variant" else (0,)
    found = (check.get("exit"), check.get("coordinator_committed"), check.get("bytes_unchanged"))[:len(wanted)]
    return {"passed": found == wanted, **check}


def _found(cell_dir: Path, flags: tuple[str, ...]) -> list[str]:
    logs = [(log, (cell_dir / log).read_text(encoding="utf-8", errors="replace")) for log in LOGS
            if (cell_dir / log).is_file()]
    return [f"{log}: {flag} line" for log, text in logs for flag in flags if flag in text]


def _stop_problems(meta: dict) -> list[str]:
    """A resumed cell needs the evidence of its stop and its resume; a run that failed before the stop stands."""
    stop, run_exit = meta.get("stop") or {}, meta["run_exit"]
    if meta["mode"] != "resumed" or run_exit not in (0, STOPPED):
        return []
    if run_exit == 0:
        return ["the resumed cell ran to the end: its stop never fired"]
    if stop.get("pending") != 0 or not str(stop.get("last_identity", "")).endswith("/ feedback"):
        return [f"the wrapper stop left a turn in flight or stopped elsewhere ({stop})"]
    return [] if meta["resume_exit"] is not None else ["the resumed cell was stopped but never resumed"]


def _tree_problems(cell_dir: Path, report: dict | None, run_root: Path | None, facts: dict) -> list[str]:
    """What the run tree shows that is not the workflow's own outcome."""
    problems = [] if isinstance(report, dict) else ["no readable report.json"]
    problems += [] if run_root else ["no run tree"]
    problems += [] if facts["committed_turns"] or facts["cost_stops"] else ["no turn committed"]
    problems += [f"the cap could not meter a call: {line}" for line in _found(cell_dir, (UNMETERED_LINE,))]
    problems += ["codex was called"] if (cell_dir / "codex-calls.log").exists() else []
    problems += [f"{_line_count(cell_dir / 'nested-calls.log')} claude started inside the cell (refused)"] \
        if (cell_dir / "nested-calls.log").exists() else []
    return problems + facts["init_problems"]


def _meta_problems(name: str, cell_dir: Path, meta: dict, criterion: dict) -> list[str]:
    named = meta["cell"] == name and meta["slot"] in (name, f"{name}-retry") and meta["slot"] == cell_dir.name
    problems = [] if named else [f"cell.json names {meta['cell']} / {meta['slot']}, not {name} in {cell_dir.name}"]
    problems += [] if meta["report_exit"] == 0 else [f"report exited {meta['report_exit']}"]
    problems += ["ran on a runtime with uncommitted changes"] if not meta["rehearsal"] and meta["runtime_dirty"] else []
    problems += [] if meta["fixture_commit"] == criterion["fixture_commit"] else [
        f"fixture commit {meta['fixture_commit']}, not {criterion['fixture_commit']}"]
    return problems + _stop_problems(meta)


def _session_problems(meta: dict, sessions: list[str]) -> list[str]:
    """The CLI's transcripts for the workspace are exactly the sessions the attempts name; more means a CLI ran
    outside the journal (detected, not prevented)."""
    found = sorted(map(str, _listed(meta["native_sessions"])))
    return [] if found == sessions else [f"{len(found)} native session transcripts for the workspace, "
                                         f"{len(sessions)} sessions in its attempts"]


def _model_problems(usage: dict, run: dict, model: str) -> list[str]:
    """Every recorded usage model and both bound model inputs are exactly `model`."""
    bound = run.get("bound_inputs") or {}
    bound_models = sorted({bound.get("planner_model"), bound.get("reviewer_model")} - {None})
    other = usage["other_models"] or [name for name in bound_models if name != model]
    return [f"a model other than {model}: {other}"] if other else []


def _meta(cell_dir: Path, manifest_sha256: str) -> dict | None:
    """The finished cell's record, or None when it is missing or incomplete; refuses another manifest."""
    meta = _json(cell_dir / "cell.json")
    if not isinstance(meta, dict) or any(key not in meta for key in META_KEYS):
        return None
    if meta["manifest_sha256"] != manifest_sha256:
        raise Refusal(f"{cell_dir} ran with manifest {meta['manifest_sha256']}, not {manifest_sha256}")
    return meta


def _line_count(path: Path) -> int:
    return len(path.read_text(errors="replace").splitlines()) if path.is_file() else 0


def recorded_cost(cell_dir: Path) -> float | None:
    """What the cell recorded as spent, whole or partial: the report's figure, else the attempts' reported costs."""
    report = _json(cell_dir / "report.json")
    value = ((report.get("run") or {}).get("usage") or {}).get("cost_usd") if isinstance(report, dict) else None
    if value is not None:
        return value
    run_root = _run_root(cell_dir)
    costs = [(_json(attempt / "usage.json") or {}).get("reported_cost_usd") for attempt in _attempts(run_root)]
    costs = [cost for cost in costs if isinstance(cost, (int, float))]
    return sum(costs) if costs else None


def read_cell(name: str, cell_dir: Path, criterion: dict, manifest_sha256: str) -> dict:
    """The cell's facts and its `problems` (empty for a valid workflow-level observation)."""
    meta, model = _meta(cell_dir, manifest_sha256), criterion["model"]
    if meta is None:
        return {"present": False, "problems": [f"{name}: {cell_dir.name} has no complete cell.json (did not finish)"]}
    report = _json(cell_dir / "report.json")
    report = report if isinstance(report, dict) else None
    run = (report or {}).get("run") or {}
    run_root = _run_root(cell_dir)
    facts = {**turn_facts(_jsonl(run_root / "memo.jsonl") if run_root else []), **attempt_facts(run_root, criterion)}
    facts["cost_stops"] = facts["budget_stops"] + _found(cell_dir, (CAP_REACHED_LINE,))
    usage = usage_facts(run_root, model)
    cost_usd, cost_reason = cost(report or {})
    problems = _meta_problems(name, cell_dir, meta, criterion) + _tree_problems(cell_dir, report, run_root, facts)
    problems += usage["silent_attempts"] + _model_problems(usage, run, model) + _session_problems(meta, facts["sessions"])
    return {"present": True, "dir": cell_dir.name, "meta": meta, "status": run.get("status"),
            "completed": run.get("status") == "completed" and len(facts["committed_turns"]) == criterion["turns_per_run"]
            and not facts["cost_stops"], **facts,
            "repeated_work": [f"{identity}: started more than once" for identity in facts["started_twice"]]
            + _found(cell_dir, FLAGGED_LINES), **usage, "cost_usd": cost_usd, "cost_reason": cost_reason,
            "recorded_cost_usd": recorded_cost(cell_dir), "invalidate": _invalidate(cell_dir, meta),
            "elapsed_sec": meta["run_sec"] + meta["resume_sec"], "problems": [f"{name}: {p}" for p in problems]}


def choose(name: str, root: Path, criterion: dict, manifest_sha256: str) -> dict:
    """The cell's first attempt, or its retry when the first was an infrastructure failure."""
    first = read_cell(name, root / name, criterion, manifest_sha256)
    if not (root / f"{name}-retry").is_dir():
        return {**first, "attempt_used": "first"}
    if not first["problems"]:
        raise Refusal(f"{name} has a retry, but its first attempt is a valid observation")
    retry = read_cell(name, root / f"{name}-retry", criterion, manifest_sha256)
    replaced = {"status": first.get("status"), "recorded_cost_usd": recorded_cost(root / name),
                "why": first["problems"]}
    replaced |= {key: first["meta"].get(key) for key in ("run_exit", "resume_exit")} if first["present"] else {}
    return {**retry, "attempt_used": "retry", "replaced": replaced}


def invalid(cells: dict) -> list[str]:
    reasons = [problem for cell in cells.values() for problem in cell["problems"]]
    present = [cell["meta"] for cell in cells.values() if cell["present"]]
    differing = {key: {str(meta[key]) for meta in present} for key in SHARED_KEYS}
    differing |= {f"{arm} source_sha256": {meta["source_sha256"] for meta in present if meta["arm"] == arm}
                  for arm in ("variant", "baseline")}
    return reasons + [f"cells differ in {key}: {sorted(values)}" for key, values in differing.items() if len(values) > 1]


def ratios(cells: dict, criterion: dict) -> dict:
    """Variant over baseline cost per pair; None unless both cells completed with a whole cost."""
    found = {}
    for pair, (variant, baseline) in criterion["pairs"].items():
        both = [cells[name] for name in (variant, baseline)]
        whole = all(cell.get("completed") and cell.get("cost_usd") for cell in both)
        found[pair] = both[0]["cost_usd"] / both[1]["cost_usd"] if whole else None
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
            **{key: meta.get(key) for key in ("claude_version", "run_exit", "resume_exit", "stop", "retry_reason",
                                              "native_sessions")}}


def readout(root: Path, criterion_path: Path) -> dict:
    criterion, manifest_sha256 = load_kit(criterion_path)
    cells = {name: choose(name, root, criterion, manifest_sha256) for name in criterion["cells"]}
    bad = invalid(cells)
    found = ratios(cells, criterion)
    outcome, reasons = decide(cells, found, criterion, bad)
    return {"outcome": outcome, "reasons": reasons, "ratios": found, "manifest_sha256": manifest_sha256,
            "rehearsal": any(cell["meta"]["rehearsal"] for cell in cells.values() if cell["present"]),
            "claims": criterion["claims"], "cannot_decide": criterion["cannot_decide"],
            "owner_judgment": criterion["owner_judgment"], "cells": {name: _shown(cell) for name, cell in cells.items()}}


def retry_check(cell_dir: Path, criterion_path: Path) -> int:
    """0 when the finished attempt in `cell_dir` is an infrastructure failure (a retry is allowed), else 4."""
    name = cell_dir.name.removesuffix("-retry")
    criterion, manifest_sha256 = load_kit(criterion_path)
    problems = read_cell(name, cell_dir, criterion, manifest_sha256)["problems"]
    print(json.dumps({"cell": name, "infrastructure_failure": bool(problems), "problems": problems}, indent=2))
    return 0 if problems else 4


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--criterion", type=Path, default=KIT / "criterion.json")
    parser.add_argument("--retry-check", action="store_true", help="ROOT is one finished cell directory")
    args = parser.parse_args(argv)
    try:
        if args.retry_check:
            return retry_check(args.root.resolve(), args.criterion)
        shown = readout(args.root.resolve(), args.criterion)
    except Refusal as refused:
        print(f"readout.py: refused: {refused}", file=sys.stderr)
        return 2
    print(json.dumps(shown, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
