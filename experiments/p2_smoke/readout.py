#!/usr/bin/env python3
"""Read out the P2 live smoke against the frozen criterion.

Usage: readout.py RESULTS_DIR [--criterion PATH]
       readout.py --retry-check RESULTS_DIR   (for run_smoke.sh: exit 0 when the one retry is allowed: the first
                                               attempt did not complete, was killed as planned, has an
                                               infrastructure failure, no isolation failure and no spend stop)

Refuses (exit 2) unless every file `manifest.json` lists has the listed SHA-256; when a slot ran with another
manifest; when the smoke has a retry the first attempt did not allow; and when the records' rehearsal flag
disagrees with the binaries the wrapper executed. Reads `RESULTS_DIR/smoke` and, when the retry ran,
`RESULTS_DIR/smoke-retry`: `smoke.json` (the kill, the launches, the terminated calls, the native sessions),
`terminated.jsonl`, `report.json`, the run's `memo.jsonl`, each provider attempt's `stdout.txt` and
`usage.json`, the program copy, `run.log`, `nested-calls.log`, `codex-calls.log` and `refused-calls.log`.
Prints one JSON object whose `verdict` is pass, fail or undetermined (an infrastructure failure), with the
checks and facts. On a rehearsal it prints the checks with `verdict` null and exits 2. Measure-free: no
quality claim. Calls no model and runs no command.
"""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import sys

KIT = Path(__file__).resolve().parent
MANIFEST = KIT / "manifest.json"
INIT_KEYS = ("plugins", "mcp_servers", "skills", "slash_commands", "agents", "model", "session_id",
             "claude_code_version")
META_KEYS = ("slot", "rehearsal", "manifest_sha256", "run_id", "kill", "launches", "resume_exit", "report_exit",
             "native_sessions", "native_hook_traces", "claude_version", "fixture_commit", "runtime_dirty", "status",
             "source_sha256", "price_table_sha256", "kit_in_runtime", "terminated", "claude_path", "claude_sha256",
             "runtime_commit", "sweep_left_alone")
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


# --- one launched attempt's stream: infrastructure (the call did not run properly) and isolation (it ran with
# something the flags should have removed); the PQ-1c rule, with the CLI version ---

def _listed(value) -> list:
    return value if isinstance(value, list) else [value]


def _builtin(plugin) -> bool:
    return isinstance(plugin, dict) and plugin.get("path") == "builtin" and str(plugin.get("source", "")).endswith("@builtin")


def _not_removed(init: dict, criterion: dict) -> dict:
    builtin = criterion["isolation"]["builtin_agents"]
    shown = {"plugins": [plugin for plugin in _listed(init["plugins"]) if not _builtin(plugin)],
             "agents": [agent for agent in _listed(init["agents"]) if agent not in builtin],
             **{key: _listed(init[key]) for key in ("mcp_servers", "skills", "slash_commands")},
             "model": [] if init["model"] == criterion["model"] else [init["model"]]}
    return {key: value for key, value in shown.items() if value}


def _init(rows: list[dict], criterion: dict, version: str) -> tuple[list[str], list[str]]:
    """(infrastructure, isolation) problems of the attempt's init event."""
    inits = [row for row in rows if row.get("type") == "system" and row.get("subtype") == "init"]
    if len(inits) != 1:
        return [f"{len(inits)} init events, not one"], []
    missing = [key for key in INIT_KEYS if key not in inits[0]]
    if missing:
        return [f"the init event lacks {missing}"], []
    drift = [] if inits[0]["claude_code_version"] == version else [
        f"the init event's claude_code_version is {inits[0]['claude_code_version']}, not {version}"]
    shown = _not_removed(inits[0], criterion)
    return drift, [f"the init event shows {shown}"] if shown else []


def _api_error(row: dict) -> bool:
    return row.get("type") == "result" and row.get("is_error") is True and (
        row.get("api_error_status") is not None or str(row.get("result", "")).startswith("API Error"))


def _reported(usage) -> bool:
    return isinstance(usage, dict) and usage.get("status") == "reported" and usage.get("complete") is True


def _usage(usage, model: str) -> tuple[list[str], list[str]]:
    """(infrastructure, isolation) problems of the attempt's usage.json."""
    if not _reported(usage):
        return [f"usage not reported and complete ({(usage or {}).get('status', 'absent')})"], []
    rows = [row for row in usage.get("rows") or [] if isinstance(row, dict)]
    others = sorted({str(row.get("model")) for row in rows} - {model})
    output = sum((row.get("tokens") or {}).get("output") or 0 for row in rows)
    return ([] if output > 0 else ["no output tokens"]), ([f"usage of another model: {others}"] if others else [])


def _stream(rows: list[dict]) -> tuple[list[str], list[str]]:
    """(an API error result, hook events): hook events are always in a stream-json stream when a hook ran."""
    hooks = sorted({str(row.get("subtype")) for row in rows if str(row.get("subtype", "")).startswith("hook_")})
    return (["an API error result"] if any(_api_error(row) for row in rows) else []), (
        [f"hook events in the stream: {hooks}"] if hooks else [])


def attempt(bundle: str, criterion: dict, version: str) -> dict:
    """One launched attempt: its infrastructure and isolation problems, sessions, budget stop, reported cost."""
    where = Path(bundle).parent
    rows, usage = _jsonl(where / "stdout.txt"), _json(where / "usage.json")
    init_infra, init_isolation = _init(rows, criterion, version)
    usage_infra, usage_isolation = _usage(usage, criterion["model"])
    stream_infra, stream_isolation = _stream(rows)
    infra, isolation = init_infra + usage_infra + stream_infra, init_isolation + usage_isolation + stream_isolation
    cost = usage.get("reported_cost_usd") if isinstance(usage, dict) else None
    named = f"{where.parent.name[:12]}/{where.name}"
    return {"infrastructure": [f"{named}: {p}" for p in infra], "isolation": [f"{named}: {p}" for p in isolation],
            "sessions": {str(row.get("session_id")) for row in rows if row.get("subtype") == "init"},
            "budget_stop": any(row.get("subtype") == "error_max_budget_usd" for row in rows),
            "reported_cost_usd": cost if isinstance(cost, (int, float)) else 0.0, "has_usage": _reported(usage)}


# --- the slot records ---

def _meta(slot_dir: Path, manifest_sha256: str) -> dict | None:
    meta = _json(slot_dir / "smoke.json")
    if not isinstance(meta, dict) or any(key not in meta for key in META_KEYS) or meta["slot"] != slot_dir.name:
        return None
    if meta["manifest_sha256"] != manifest_sha256:
        raise Refusal(f"{slot_dir} ran with manifest {meta['manifest_sha256']}, not {manifest_sha256}")
    return meta


def _standin(meta: dict) -> bool:
    """Whether the slot executed the stand-in: a launch says so, the version says so, or a binary that is not
    the recorded CLI, or that lies inside the kit, was executed."""
    targets = {launch.get("target") for launch in meta["launches"] if launch.get("target")}
    paths = targets | {meta["claude_path"]}
    inside = any(str(path).startswith(str(KIT) + os.sep) for path in paths)
    return any(launch.get("standin") for launch in meta["launches"]) or "stand-in" in str(meta["claude_version"]) \
        or inside or bool(targets - {meta["claude_path"]})


def rehearsal_of(metas: list[dict]) -> bool:
    """The records' rehearsal flag, refused unless it agrees with what the wrapper executed (a binary carrying
    the stand-in marker, the recorded CLI path, a path inside the kit) and with the CLI version recorded."""
    flags = {meta["rehearsal"] for meta in metas}
    standin = any(_standin(meta) for meta in metas)
    if len(flags) != 1 or flags != {standin}:
        executed = "a rehearsal stand-in" if standin else "a real CLI"
        raise Refusal(f"the records disagree: rehearsal flags {sorted(flags)}, but the wrapper executed {executed}")
    return standin


def _launched(meta: dict) -> list[str]:
    """Bundles of the launches that reached the CLI: not refused, not stopped at the gate, with an attempt."""
    return [launch["bundle"] for launch in meta["launches"]
            if launch.get("bundle") and not launch.get("refused") and not launch.get("gated")]


def _unattached(meta: dict) -> list[str]:
    """Launches with no attempt (no bundle): a CLI started outside an orchestrator attempt."""
    return [f"a launch with no attempt: {launch.get('launch')}" for launch in meta["launches"] if not launch.get("bundle")]


def _effect_attempt(bundle: str) -> tuple[str, int]:
    where = Path(bundle).parent
    return str(where.parent), int(where.name.rsplit("-", 1)[-1]) if where.name.startswith("attempt-") else 0


def replaced_by_retry(first: dict, final: dict) -> set[str]:
    """First-slot launches the retry superseded: it launched a later attempt of the same effect."""
    later = [_effect_attempt(bundle) for bundle in set(_launched(final)) - set(_launched(first))]
    return {bundle for bundle in _launched(first)
            if any(effect == _effect_attempt(bundle)[0] and n > _effect_attempt(bundle)[1] for effect, n in later)}


def _memo(first: Path, meta: dict) -> list[dict]:
    return _jsonl(first / "workspace" / ".orchestrate" / "runs" / str(meta["run_id"]) / "memo.jsonl")


def kill_problem(kill, criterion: dict) -> str | None:
    """The planned kill: exactly the coders of committed_at_kill committed, the held_items held, nothing failed."""
    if not isinstance(kill, dict):
        return "no kill record"
    committed, held = kill.get("committed_before", []), kill.get("held", [])
    planned = sorted(criterion["committed_at_kill"])
    found = sorted(item for item in planned for identity in committed if item in identity)
    if found != planned or len(committed) != len(planned) or len(held) != len(criterion["held_items"]) \
            or kill.get("failed_before") or kill.get("timed_out"):
        return (f"the kill did not happen as planned: committed {len(committed)}, held {len(held)}, "
                f"failed {kill.get('failed_before')}, timed out {kill.get('timed_out')}")
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


def _pin_problems(first_dir: Path, meta: dict, criterion: dict, rehearsal: bool) -> list[str]:
    """The pins: fixture, program copy (recorded and on disk), price table; for a real slot, the CLI version,
    a clean runtime and the kit inside it."""
    copy = first_dir / "workspace" / "workflows" / "best_of_n.orc"
    problems = [] if meta["fixture_commit"] == criterion["fixture_commit"] else [f"fixture commit {meta['fixture_commit']}"]
    problems += [] if meta["source_sha256"] == criterion["program_sha256"] == _sha256(copy) else [
        "the program copy is not the pinned one"]
    problems += [] if meta["price_table_sha256"] == criterion["price_table_sha256"] else ["the price table is not the pinned one"]
    ledger_commit = os.environ.get("P2SMOKE_RUNTIME_COMMIT")
    problems += [] if ledger_commit in (None, meta["runtime_commit"]) else [
        f"runtime commit {meta['runtime_commit']}, not the ledger's {ledger_commit}"]
    if rehearsal:
        return problems
    problems += [] if str(meta["claude_version"]).split(" ")[0] == criterion["cli_version"] else [
        f"claude {meta['claude_version']}, not the pinned {criterion['cli_version']}"]
    problems += ["ran on a runtime with uncommitted changes"] if meta["runtime_dirty"] else []
    return problems + ([] if meta["kit_in_runtime"] else ["the kit was not the runtime's own experiments/p2_smoke"])


def slot_problems(first_dir: Path, slot_dir: Path, meta: dict, criterion: dict, rehearsal: bool) -> list[str]:
    """What the slot's record and logs show that is not the workflow's own outcome."""
    problems = [] if meta["report_exit"] == 0 else [f"report exited {meta['report_exit']}"]
    problems += ["the run could not meter a call (spend_cap_unmetered)"] if "spend_cap_unmetered" in _text(first_dir / "run.log") else []
    terminated = {row.get("launch") for path in {first_dir, slot_dir} for row in _jsonl(path / "terminated.jsonl")}
    problems += [f"{len(terminated)} calls in flight were terminated when the run stopped: {sorted(terminated)}"] if terminated else []
    return problems + _pin_problems(first_dir, meta, criterion, rehearsal)


def _outside_wrapper(rows_dir: Path, launched: set[str]) -> list[str]:
    """Provider attempts with output that no launch record names: a CLI ran without the wrapper."""
    return [str(path.parent) for path in rows_dir.glob("effects/*/attempt-*/stdout.txt")
            if path.stat().st_size and str(path.parent / "result.json") not in launched]


def isolation_problems(first_dir: Path, final: dict, seen: dict) -> list[str]:
    """Every attempt's isolation problems (never erased by a retry), and what ran outside the journal."""
    problems = [p for a in seen["attempts"].values() for p in a["isolation"]]
    problems += [f"{final['native_hook_traces']} hook records in the native transcripts"] if final["native_hook_traces"] else []
    problems += ["codex was called"] if (first_dir / "codex-calls.log").exists() else []
    problems += ["a claude was started inside the smoke (refused)"] if (first_dir / "nested-calls.log").exists() else []
    native = sorted(final["native_sessions"])
    problems += [] if native == seen["sessions"] else [
        f"{len(native)} native sessions for the workspace, {len(seen['sessions'])} in the launched attempts"]
    return problems + [f"output without a launch record: {where}" for where in seen["outside"]]


def evaluate(root: Path, criterion: dict, manifest_sha256: str, *, first_only: bool = False) -> dict:
    """The checks, infrastructure problems and facts of the smoke (the first attempt, or with its retry)."""
    first_dir, retry_dir = root / "smoke", root / "smoke-retry"
    first = _meta(first_dir, manifest_sha256)
    if first is None:
        return {"infrastructure": ["smoke/smoke.json is missing, incomplete or names another slot"], "present": False}
    use_retry = retry_dir.is_dir() and not first_only
    final = _meta(retry_dir, manifest_sha256) if use_retry else first
    if final is None:
        return {"infrastructure": ["smoke-retry/smoke.json is missing, incomplete or names another slot"],
                "present": False}
    rehearsal = rehearsal_of([first, final])
    replaced = replaced_by_retry(first, final) if use_retry else set()
    later = _meta(retry_dir, manifest_sha256) if retry_dir.is_dir() else None     # its launches are not "outside"
    known = set(_launched(later or final))
    return _evaluate(first_dir, first, retry_dir if use_retry else first_dir, final, replaced, criterion, rehearsal,
                     known)


def _stopped_launches(meta: dict) -> int:
    """Launches with an attempt that stopped before the CLI (refused or gated): unknown in the report."""
    return sum(bool(launch.get("bundle")) and bool(launch.get("refused") or launch.get("gated"))
               for launch in meta["launches"])


def _evaluate(first_dir: Path, first: dict, final_dir: Path, final: dict, replaced: set, criterion: dict,
              rehearsal: bool, known: set[str]) -> dict:
    rows, kill = _memo(first_dir, first), first["kill"] if isinstance(first["kill"], dict) else {}
    launches = _launched(final)
    attempts = {bundle: attempt(bundle, criterion, str(final["claude_version"]).split(" ")[0]) for bundle in launches}
    report = report_facts(_json(final_dir / "report.json"), rows)
    reported = sum(a["reported_cost_usd"] for a in attempts.values())
    sessions = sorted(set().union(*(a["sessions"] for a in attempts.values())))
    committed = {row.get("identity") for row in rows if row.get("record") == "committed"}
    run_root = first_dir / "workspace" / ".orchestrate" / "runs" / str(first["run_id"])
    seen = {"rows": rows, "kill": kill, "launches": launches, "attempts": attempts, "report": report,
            "reported": reported, "sessions": sessions, "committed": committed, "replaced": replaced,
            "outside": _outside_wrapper(run_root, known), "stopped_launches": _stopped_launches(final)}
    isolation = isolation_problems(first_dir, final, seen)
    infra = slot_problems(first_dir, final_dir, final, criterion, rehearsal)
    infra += [p for bundle, a in attempts.items() if bundle not in replaced for p in a["infrastructure"]]
    infra += [p for p in [kill_problem(kill, criterion)] if p] + _unattached(final)
    seen["model_failures"] = model_failures(rows, attempts)
    cost_usd, _ = _cost(report["run"], reported, criterion["spend"]["smoke_ceiling_usd"])
    facts = {"run_id": first["run_id"], "runtime_commit": first.get("runtime_commit"),
             "claude_version": final["claude_version"], "status": report["status"],
             "committed_before_kill": kill.get("committed_before"), "held": kill.get("held", []),
             "committed_after": sorted(committed), "redispatched": redispatched(rows, []),
             "paid_calls": len(launches), "refused_calls": len(final["launches"]) - len(launches),
             "terminated_calls": final["terminated"], "replaced_attempts": sorted(replaced),
             "native_sessions": sessions, "cost_usd": cost_usd, "cli_reported_cost_usd": round(reported, 6),
             "run_usage": report["run"], "step_usage": report["steps"], "rehearsal": rehearsal}
    facts["model_failures"] = seen["model_failures"]
    return {"present": True, "infrastructure": infra, "isolation_problems": isolation,
            "checks": checks(first_dir, final, seen, criterion, isolation), "facts": facts}


def _effects_key(path: str) -> str:
    return path[path.index("effects/"):] if "effects/" in path else path


def model_failures(rows: list[dict], attempts: dict) -> list[str]:
    """Failed rows whose launched attempt shows no infrastructure problem: the model's own failure (an invalid
    result, a wrong path), a workflow outcome that is never retried."""
    started = {(row.get("identity"), row.get("attempt")): row.get("result_path") for row in rows
               if row.get("record") == "started"}
    by_key = {_effects_key(bundle): found for bundle, found in attempts.items()}
    failures = []
    for row in rows:
        result = started.get((row.get("identity"), row.get("attempt"))) if row.get("record") == "failed" else None
        found = by_key.get(_effects_key(result)) if result else None
        if found is not None and not found["infrastructure"]:
            failures.append(f"{row.get('identity')} attempt {row.get('attempt')}: {row.get('code')}")
    return failures


def _completed(final: dict, seen: dict, criterion: dict) -> bool:
    coders = sum(CODER in identity for identity in seen["committed"])
    judged = any(identity.endswith(JUDGE) for identity in seen["committed"])
    return seen["report"]["status"] == "completed" and final["resume_exit"] == 0 and coders == criterion["items"] and judged


def _usage_recorded(seen: dict) -> bool:
    attempts, replaced = seen["attempts"], seen["replaced"]
    unknown = len(seen["kill"].get("held", [])) + sum(not attempts[b]["has_usage"] for b in replaced if b in attempts) \
        + seen["stopped_launches"]
    whole = all(attempts[bundle]["has_usage"] for bundle in seen["launches"] if bundle not in replaced)
    return whole and seen["report"]["run"].get("unknown_attempts") == unknown


def _no_cost_stop(first_dir: Path, seen: dict) -> bool:
    stopped = any(a["budget_stop"] for a in seen["attempts"].values()) or (first_dir / "refused-calls.log").exists()
    return not stopped and "spend_cap_reached" not in _text(first_dir / "run.log")


def checks(first_dir: Path, final: dict, seen: dict, criterion: dict, isolation: list[str]) -> dict:
    """The criterion's checks, each true or false."""
    kill, held = seen["kill"], seen["kill"].get("held", [])
    launched_held = set(held) & set(seen["launches"]) or any((Path(b).parent / "usage.json").exists() for b in held)
    return {"stopped_mid_map": kill_problem(kill, criterion) is None,
            "completed": _completed(final, seen, criterion),
            "no_redispatch": not redispatched(seen["rows"], kill.get("committed_before", [])),
            "held_never_launched": not launched_held,
            "usage_recorded": _usage_recorded(seen),
            "report_tokens": seen["report"]["report_tokens"],
            "cost_under_ceiling": _cost(seen["report"]["run"], seen["reported"], criterion["spend"]["smoke_ceiling_usd"])[1],
            "no_cost_stop": _no_cost_stop(first_dir, seen),
            "isolation": not isolation,
            "no_model_failure": not seen["model_failures"]}


def verdict(found: dict) -> tuple[str, list[str]]:
    """fail on an isolation problem whatever else holds; undetermined on infrastructure; else the checks."""
    if not found["checks"]["isolation"]:
        return "fail", ["isolation", *found["isolation_problems"]]
    if not found["checks"]["no_model_failure"]:
        return "fail", ["no_model_failure", *found["facts"]["model_failures"]]
    if found["infrastructure"]:
        return "undetermined", found["infrastructure"]
    failing = [name for name, held in found["checks"].items() if not held]
    return ("fail", failing) if failing else ("pass", ["every check holds"])


def retry_allowed(found: dict) -> bool:
    """The one retry by resume: a first attempt that did not complete, was killed as planned (a resume cannot
    redo a kill), has an infrastructure failure, no isolation failure and no spend stop."""
    if not found["present"]:
        return False
    held = found["checks"]
    return bool(found["infrastructure"]) and held["stopped_mid_map"] and held["isolation"] and held["no_cost_stop"] \
        and held["no_model_failure"] and not held["completed"]


def readout(root: Path, criterion_path: Path) -> tuple[dict, int]:
    criterion, manifest_sha256 = load_kit(criterion_path)
    if (root / "smoke-retry").is_dir() and not retry_allowed(evaluate(root, criterion, manifest_sha256, first_only=True)):
        raise Refusal("the smoke has a retry, but its first attempt did not allow one")
    found = evaluate(root, criterion, manifest_sha256)
    rehearsal = found.get("facts", {}).get("rehearsal", False)
    if not rehearsal and not os.environ.get("P2SMOKE_RUNTIME_COMMIT"):
        raise Refusal("set P2SMOKE_RUNTIME_COMMIT to the runtime commit recorded in the plan's ledger")
    outcome, reasons = verdict(found) if found["present"] else ("undetermined", found["infrastructure"])
    shown = {"verdict": None if rehearsal else outcome, "reasons": reasons, "manifest_sha256": manifest_sha256,
             "rehearsal": rehearsal, "claims": criterion["claims"], "cannot_decide": criterion["cannot_decide"],
             "attempt_used": "retry" if (root / "smoke-retry").is_dir() else "first", **found}
    if rehearsal:
        shown["refused"] = f"a rehearsal gets no verdict (its checks would give {outcome})"
    return shown, 2 if rehearsal else 0


def retry_check(root: Path, criterion_path: Path) -> int:
    """0 when the one retry is allowed (`retry_allowed`), else 4."""
    criterion, manifest_sha256 = load_kit(criterion_path)
    found = evaluate(root, criterion, manifest_sha256, first_only=True)
    checks_found = found.get("checks", {})
    print(json.dumps({"infrastructure_failure": found["infrastructure"], "isolation": found.get("isolation_problems"),
                      "completed": checks_found.get("completed"), "cost_stop": not checks_found.get("no_cost_stop", True),
                      "killed_as_planned": checks_found.get("stopped_mid_map", False),
                      "retry_allowed": retry_allowed(found)}, indent=2))
    return 0 if retry_allowed(found) else 4


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
