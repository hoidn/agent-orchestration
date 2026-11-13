#!/usr/bin/env python3
"""Read out the P2 live smoke against the frozen criterion.

Usage: readout.py RESULTS_DIR [--criterion PATH]
       readout.py --retry-check RESULTS_DIR   (for run_smoke.sh: exit 0 when the first attempt is an
                                               infrastructure failure, so the one retry is allowed)

Refuses (exit 2) unless every file `manifest.json` lists has the listed SHA-256, and when a slot ran with
another manifest or has a retry although its first attempt is a valid observation. Reads `RESULTS_DIR/smoke`
and, when the retry ran, `RESULTS_DIR/smoke-retry`: `smoke.json` (the kill, the launches, the native
sessions), `report.json`, the run's `memo.jsonl` and each launched attempt's `stdout.txt` and `usage.json`,
`run.log`, `resume.log`, `nested-calls.log`, `codex-calls.log` and `refused-calls.log`. Prints one JSON object
whose `verdict` is pass, fail or undetermined (an infrastructure failure), with the checks and facts. On a
rehearsal it prints the checks with `verdict` null and exits 2. Measure-free: no quality claim. Calls no model
and runs no orchestrator command.
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
INIT_KEYS = ("plugins", "mcp_servers", "skills", "slash_commands", "agents", "model", "session_id",
             "claude_code_version")
META_KEYS = ("slot", "rehearsal", "manifest_sha256", "run_id", "kill", "launches", "resume_exit", "report_exit",
             "native_sessions", "native_hook_traces", "claude_version", "fixture_commit", "runtime_dirty", "status")
JUDGE = " / selection"
CODER = "par-map:repo["


class Refusal(Exception):
    """The readout cannot be trusted against this criterion or these results."""


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else "absent"


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


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


# --- one launched attempt's stream (the PQ-1c isolation rule, with the CLI version) ---

def _listed(value) -> list:
    return value if isinstance(value, list) else [value]


def _not_removed(init: dict, criterion: dict, version: str) -> dict:
    builtin = criterion["isolation"]["builtin_agents"]
    shown = {"plugins": [p for p in _listed(init["plugins"]) if not (isinstance(p, dict) and p.get("path") == "builtin"
                                                                     and str(p.get("source", "")).endswith("@builtin"))],
             "agents": [agent for agent in _listed(init["agents"]) if agent not in builtin],
             **{key: _listed(init[key]) for key in ("mcp_servers", "skills", "slash_commands")},
             "model": [] if init["model"] == criterion["model"] else [init["model"]],
             "claude_code_version": [] if init["claude_code_version"] == version else [init["claude_code_version"]]}
    return {key: value for key, value in shown.items() if value}


def _init_problem(rows: list[dict], criterion: dict, version: str) -> str | None:
    inits = [row for row in rows if row.get("type") == "system" and row.get("subtype") == "init"]
    if len(inits) != 1:
        return f"{len(inits)} init events, not one"
    missing = [key for key in INIT_KEYS if key not in inits[0]]
    if missing:
        return f"the init event lacks {missing}"
    shown = _not_removed(inits[0], criterion, version)
    return f"the init event shows {shown}" if shown else None


def _api_error(row: dict) -> bool:
    return row.get("type") == "result" and row.get("is_error") is True and (
        row.get("api_error_status") is not None or str(row.get("result", "")).startswith("API Error"))


def _reported(usage) -> bool:
    return isinstance(usage, dict) and usage.get("status") == "reported" and usage.get("complete") is True


def _usage_problem(usage, model: str) -> str | None:
    if not _reported(usage):
        return f"usage not reported and complete ({(usage or {}).get('status', 'absent')})"
    rows = [row for row in usage.get("rows") or [] if isinstance(row, dict)]
    others = sorted({str(row.get("model")) for row in rows} - {model})
    if others:
        return f"usage of another model: {others}"
    output = sum((row.get("tokens") or {}).get("output") or 0 for row in rows)
    return None if output > 0 else "no output tokens"


def _stream_problems(rows: list[dict]) -> list[str]:
    hooks = sorted({str(row.get("subtype")) for row in rows if str(row.get("subtype", "")).startswith("hook_")})
    return ([f"hook events in the stream: {hooks}"] if hooks else []) + (
        ["an API error result"] if any(_api_error(row) for row in rows) else [])


def attempt(bundle: str, criterion: dict, version: str) -> dict:
    """One launched attempt: its problems (infrastructure), sessions, budget stop and the CLI's reported cost."""
    where = Path(bundle).parent
    rows, usage = _jsonl(where / "stdout.txt"), _json(where / "usage.json")
    found = [_init_problem(rows, criterion, version.split()[0]), _usage_problem(usage, criterion["model"])]
    problems = [p for p in found if p] + _stream_problems(rows)
    cost = usage.get("reported_cost_usd") if isinstance(usage, dict) else None
    return {"problems": [f"{where.parent.name[:12]}/{where.name}: {p}" for p in problems],
            "sessions": {str(row.get("session_id")) for row in rows if row.get("subtype") == "init"},
            "budget_stop": any(row.get("subtype") == "error_max_budget_usd" for row in rows),
            "reported_cost_usd": cost if isinstance(cost, (int, float)) else 0.0, "has_usage": _reported(usage)}


# --- the slot records ---

def _meta(slot_dir: Path, manifest_sha256: str) -> dict | None:
    meta = _json(slot_dir / "smoke.json")
    if not isinstance(meta, dict) or any(key not in meta for key in META_KEYS):
        return None
    if meta["manifest_sha256"] != manifest_sha256:
        raise Refusal(f"{slot_dir} ran with manifest {meta['manifest_sha256']}, not {manifest_sha256}")
    return meta


def _memo(first: Path, meta: dict) -> list[dict]:
    return _jsonl(first / "workspace" / ".orchestrate" / "runs" / str(meta["run_id"]) / "memo.jsonl")


def kill_problem(kill, items: int) -> str | None:
    """The kill evidence: some but not all coders committed, the rest held, nothing failed, no timeout."""
    if not isinstance(kill, dict):
        return "no kill record"
    committed, held = len(kill.get("committed_before", [])), len(kill.get("held", []))
    if not 1 <= committed < items or committed + held != items or kill.get("failed_before") or kill.get("timed_out"):
        return f"the kill did not happen as planned: {committed} committed, {held} held, failed {kill.get('failed_before')}, timed out {kill.get('timed_out')}"
    return None


def redispatched(rows: list[dict], before: list[str]) -> list[str]:
    """Identities started again after their commit, and coders committed before the kill started twice."""
    committed, again, started = set(), set(), Counter()
    for row in rows:
        if row.get("record") == "started":
            started[row.get("identity")] += 1
            again |= {row.get("identity")} & committed
        elif row.get("record") == "committed":
            committed.add(row.get("identity"))
    return sorted(again | {identity for identity in before if started[identity] != 1})


def _provider_steps(rows: list[dict]) -> set[str]:
    """The five provider identities of the memo: the coders and the judge."""
    identities = {row.get("identity", "") for row in rows if row.get("record") == "started"}
    return {identity for identity in identities if CODER in identity or identity.endswith(JUDGE)}


def _summed(steps: dict) -> dict:
    keys = ("input", "output", "cache_read", "cache_write")
    return {key: sum((usage.get("tokens") or {}).get(key, 0) for usage in steps.values()) for key in keys}


def report_facts(report, rows: list[dict]) -> dict:
    """The report's per-step and run usage, and whether it shows tokens for every provider step and their sum."""
    report = report if isinstance(report, dict) else {}
    steps = {step["identity"]: step["usage"] for step in report.get("steps", []) if "usage" in step}
    run = (report.get("run") or {}).get("usage") or {}
    provider = _provider_steps(rows)
    shown = bool(provider) and all((steps.get(identity) or {}).get("tokens") for identity in provider)
    return {"status": (report.get("run") or {}).get("status"), "steps": steps, "run": run,
            "report_tokens": shown and run.get("tokens") == _summed(steps)}


def _cost(run: dict, reported: float, ceiling: float) -> tuple[float | None, bool]:
    value = run.get("cost_usd")
    number = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0
    return (float(value) if number else None), number and value <= ceiling and reported <= ceiling


def slot_problems(slot_dir: Path, meta: dict, criterion: dict) -> list[str]:
    """What the slot's record and logs show that is not the workflow's own outcome."""
    problems = [] if meta["report_exit"] == 0 else [f"report exited {meta['report_exit']}"]
    problems += [] if meta["fixture_commit"] == criterion["fixture_commit"] else [f"fixture commit {meta['fixture_commit']}"]
    problems += ["ran on a runtime with uncommitted changes"] if not meta["rehearsal"] and meta["runtime_dirty"] else []
    problems += ["the run could not meter a call (spend_cap_unmetered)"] if "spend_cap_unmetered" in _text(slot_dir / "run.log") else []
    problems += [f"{meta['native_hook_traces']} hook records in the native transcripts"] if meta["native_hook_traces"] else []
    return problems


def evaluate(root: Path, criterion: dict, manifest_sha256: str, *, first_only: bool = False) -> dict:
    """The checks, infrastructure problems and facts of the smoke (the first attempt, or with its retry)."""
    first_dir, retry_dir = root / "smoke", root / "smoke-retry"
    first = _meta(first_dir, manifest_sha256)
    if first is None or first["slot"] != "smoke":
        return {"infrastructure": ["smoke/smoke.json is missing, incomplete or names another slot"], "present": False}
    use_retry = retry_dir.is_dir() and not first_only
    final = _meta(retry_dir, manifest_sha256) if use_retry else first
    if final is None:
        return {"infrastructure": ["smoke-retry/smoke.json is missing or incomplete"], "present": False}
    replaced = set()
    if use_retry:
        replaced = {launch["bundle"] for launch in first["launches"]
                    if attempt(launch["bundle"] or "", criterion, first["claude_version"])["problems"]}
    return _evaluate(first_dir, first, retry_dir if use_retry else first_dir, final, replaced, criterion)


def _evaluate(first_dir: Path, first: dict, final_dir: Path, final: dict, replaced: set, criterion: dict) -> dict:
    rows, kill = _memo(first_dir, first), first["kill"] if isinstance(first["kill"], dict) else {}
    launches = [launch["bundle"] or "" for launch in final["launches"]]
    attempts = {bundle: attempt(bundle, criterion, final["claude_version"]) for bundle in launches}
    report = report_facts(_json(final_dir / "report.json"), rows)
    reported = sum(a["reported_cost_usd"] for a in attempts.values())
    sessions = sorted(set().union(*(a["sessions"] for a in attempts.values())))
    committed = {row.get("identity") for row in rows if row.get("record") == "committed"}
    seen = {"rows": rows, "kill": kill, "launches": launches, "attempts": attempts, "report": report,
            "reported": reported, "sessions": sessions, "committed": committed, "replaced": replaced}
    cost_usd, _ = _cost(report["run"], reported, criterion["spend"]["smoke_ceiling_usd"])
    facts = {"run_id": first["run_id"], "claude_version": final["claude_version"], "status": report["status"],
             "committed_before_kill": kill.get("committed_before"), "held": kill.get("held", []),
             "committed_after": sorted(committed), "redispatched": redispatched(rows, []),
             "paid_calls": len(launches), "replaced_attempts": sorted(replaced), "native_sessions": sessions,
             "cost_usd": cost_usd, "cli_reported_cost_usd": round(reported, 6), "run_usage": report["run"],
             "step_usage": report["steps"], "rehearsal": first["rehearsal"] or final["rehearsal"]}
    return {"present": True, "infrastructure": infrastructure(first_dir, final_dir, final, seen, criterion),
            "checks": checks(first_dir, final, seen, criterion), "facts": facts}


def infrastructure(first_dir: Path, final_dir: Path, final: dict, seen: dict, criterion: dict) -> list[str]:
    """Problems that are not the workflow's own outcome; a replaced attempt's problems no longer count."""
    problems = slot_problems(final_dir, final, criterion)
    problems += [p for bundle, a in seen["attempts"].items() if bundle not in seen["replaced"] for p in a["problems"]]
    problems += [p for p in [kill_problem(seen["kill"], criterion["items"])] if p]
    problems += ["codex was called"] if (first_dir / "codex-calls.log").exists() else []
    problems += ["a claude was started inside the smoke (refused)"] if (first_dir / "nested-calls.log").exists() else []
    native = sorted(final["native_sessions"])
    return problems + ([] if native == seen["sessions"] else [
        f"{len(native)} native sessions for the workspace, {len(seen['sessions'])} in the launched attempts"])


def _completed(final: dict, seen: dict, criterion: dict) -> bool:
    coders = sum(CODER in identity for identity in seen["committed"])
    judged = any(identity.endswith(JUDGE) for identity in seen["committed"])
    return seen["report"]["status"] == "completed" and final["resume_exit"] == 0 and coders == criterion["items"] and judged


def _usage_recorded(seen: dict) -> bool:
    attempts, replaced = seen["attempts"], seen["replaced"]
    unknown = len(seen["kill"].get("held", [])) + sum(not attempts[b]["has_usage"] for b in replaced if b in attempts)
    whole = all(attempts[bundle]["has_usage"] for bundle in seen["launches"] if bundle not in replaced)
    return whole and seen["report"]["run"].get("unknown_attempts") == unknown


def _no_cost_stop(first_dir: Path, seen: dict) -> bool:
    stopped = any(a["budget_stop"] for a in seen["attempts"].values()) or (first_dir / "refused-calls.log").exists()
    return not stopped and "spend_cap_reached" not in _text(first_dir / "run.log")


def checks(first_dir: Path, final: dict, seen: dict, criterion: dict) -> dict:
    """The criterion's checks, each true or false."""
    kill, held = seen["kill"], seen["kill"].get("held", [])
    launched_held = set(held) & set(seen["launches"]) or any((Path(b).parent / "usage.json").exists() for b in held)
    return {"stopped_mid_map": kill_problem(kill, criterion["items"]) is None,
            "completed": _completed(final, seen, criterion),
            "no_redispatch": not redispatched(seen["rows"], kill.get("committed_before", [])),
            "held_never_launched": not launched_held,
            "usage_recorded": _usage_recorded(seen),
            "report_tokens": seen["report"]["report_tokens"],
            "cost_under_ceiling": _cost(seen["report"]["run"], seen["reported"], criterion["spend"]["smoke_ceiling_usd"])[1],
            "no_cost_stop": _no_cost_stop(first_dir, seen)}


def verdict(found: dict) -> tuple[str, list[str]]:
    if found["infrastructure"]:
        return "undetermined", found["infrastructure"]
    failing = [name for name, held in found["checks"].items() if not held]
    return ("fail", failing) if failing else ("pass", ["every check holds"])


def readout(root: Path, criterion_path: Path) -> tuple[dict, int]:
    criterion, manifest_sha256 = load_kit(criterion_path)
    if (root / "smoke-retry").is_dir():
        first = evaluate(root, criterion, manifest_sha256, first_only=True)
        if first["present"] and not first["infrastructure"]:
            raise Refusal("the smoke has a retry, but its first attempt is a valid observation")
    found = evaluate(root, criterion, manifest_sha256)
    outcome, reasons = verdict(found)
    rehearsal = found.get("facts", {}).get("rehearsal", False)
    shown = {"verdict": None if rehearsal else outcome, "reasons": reasons, "manifest_sha256": manifest_sha256,
             "rehearsal": rehearsal, "claims": criterion["claims"], "cannot_decide": criterion["cannot_decide"],
             "attempt_used": "retry" if (root / "smoke-retry").is_dir() else "first", **found}
    if rehearsal:
        shown["refused"] = f"a rehearsal gets no verdict (its checks would give {outcome})"
    return shown, 2 if rehearsal else 0


def retry_check(root: Path, criterion_path: Path) -> int:
    """0 when the first attempt is an infrastructure failure after a kill as planned, with no cost stop, else 4."""
    criterion, manifest_sha256 = load_kit(criterion_path)
    found = evaluate(root, criterion, manifest_sha256, first_only=True)
    cost_stop = found["present"] and not found["checks"]["no_cost_stop"]
    killed = found["present"] and found["checks"]["stopped_mid_map"]   # a resume cannot redo a kill that failed
    allowed = bool(found["infrastructure"]) and killed and not cost_stop
    print(json.dumps({"infrastructure_failure": found["infrastructure"], "cost_stop": cost_stop,
                      "killed_as_planned": killed, "retry_allowed": allowed}, indent=2))
    return 0 if allowed else 4


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("root", type=Path)
    parser.add_argument("--criterion", type=Path, default=KIT / "criterion.json")
    parser.add_argument("--retry-check", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.retry_check:
            return retry_check(args.root.resolve(), args.criterion)
        shown, code = readout(args.root.resolve(), args.criterion)
    except Refusal as refused:
        print(f"readout.py: refused: {refused}", file=sys.stderr)
        return 2
    print(json.dumps(shown, indent=2, sort_keys=True))
    if code:
        print(f"readout.py: refused: {shown['refused']}", file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
