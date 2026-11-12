"""Order and stop rules of the seed-set study, the physical audit of its ledger, and the smoke check (plan Step 2,
Stop rules, Ledger).

Order: no start before a `freeze` event whose criterion, judge-criterion and runtime commit still match; no
calibration start before a passing `smoke` event; no redraw start before a `redraw` decision and with fewer than
ten unused reserve tasks (coordinator ruling). Stops (a `stop` event, after which `spend.reserve` refuses
everything): a forbidden-model answer in a run or a judge, three tasks with a contaminated run or judgment, more
than 10% of a tranche's planned runs ending as incidents, and a `stop:` decision of the readout. The audit refuses
when a unit made calls the ledger does not hold (a missing or foreign ledger) or more calls than it reserved.
"""

from pathlib import Path

from experiments.compare.repos import load, runtime_commit, sha256_file
from experiments.seed_set import layout, spend, units
from experiments.seed_set.layout import PLANNED, REDRAW_TASKS, study_runs, task_rows, tranche_tasks

JUDGE_EFFORT = "high"  # score_functional.orc's fixed judge effort


def frozen_identity(study):
    for path in (study.frozen, study.criterion):
        if not path.is_file():
            raise SystemExit(f"{path} is missing: freeze the criterion first (plan Step 1f)")
    return {"criterion_sha256": sha256_file(study.frozen), "judge_criterion_sha256": sha256_file(study.criterion),
            "runtime_commit": runtime_commit(study.runtime)}


def record_freeze(study):
    """Record the frozen criterion's hashes and the runtime commit in the ledger: the first spend needs it."""
    layout.load_criterion(study)
    return spend.record(study.ledger, "freeze", **frozen_identity(study))


def require_order(study, tranche):
    entries = spend.rows(study.ledger)
    freeze = spend.latest(entries, "freeze")
    if freeze is None:
        raise SystemExit("no freeze in the ledger: record-freeze after the criterion is frozen (plan Step 1f)")
    current = frozen_identity(study)
    if any(freeze[key] != value for key, value in current.items()):
        raise SystemExit(f"the criterion or runtime changed since the freeze: {current} against {freeze}")
    smoke, decision = spend.latest(entries, "smoke"), spend.latest(entries, "decision")
    if tranche == "calibration" and not (smoke and smoke["passed"]):
        raise SystemExit("no passed smoke in the ledger: run the smoke and smoke-check first")
    if tranche == "redraw":
        if not (decision and decision["decision"] == "redraw"):
            raise SystemExit("the redraw starts only after a readout decided \"redraw\"")
        unused = tranche_tasks(task_rows(study), "redraw")
        if len(unused) < REDRAW_TASKS:
            raise SystemExit(f"the redraw needs {REDRAW_TASKS} unused reserve tasks, {len(unused)} exist: mine more "
                             "tasks first (coordinator ruling: no scaled-down redraw)")


def audit_ledger(study):
    """Every unit with calls has its ledger row and made no more calls than it reserved."""
    reserved = {row["unit"]: row["calls"] for row in spend.starts(spend.rows(study.ledger))}
    found = [(str(path.parent), path.parent, "exit" in load(path)) for path in study_runs(study)]
    found += [(f"{pool}#{judge}", pool / "records" / "judges" / judge, False)
              for _, _, pool, judge in layout.judge_units(study)]
    for unit, records, launched in found:
        made = units.physical_calls(records)
        if unit not in reserved and (made or launched):
            raise SystemExit(f"{unit} made {made} calls but has no row in {study.ledger}: the ledger is missing or "
                             "belongs to another study; nothing starts")
        if made > reserved.get(unit, 0):
            raise SystemExit(f"{unit}: {made} calls made, {reserved.get(unit, 0)} reserved")


def contaminated_tasks(study):
    tasks = {load(path)["task"] for path in study_runs(study)
             if ((load(path.parent / "record.json").get("scan") or {}).get("verdict") or {}).get("verdict") == "contaminated"}
    for task, _, pool, judge in layout.judge_units(study):
        scan = pool / "records" / "judges" / judge / "scan.json"
        if scan.is_file() and (load(scan).get("verdict") or {}).get("verdict") == "contaminated":
            tasks.add(task)
    return sorted(tasks)


def planned_runs(study, tranche):
    return sum(PLANNED[tranche].values()) * len(tranche_tasks(task_rows(study), tranche))


def stop_reasons(study):
    reasons = []
    if len(contaminated := contaminated_tasks(study)) >= 3:
        reasons.append(f"three or more contaminated tasks: {contaminated}")
    facts = [load(path) for path in study_runs(study)]
    for tranche in PLANNED:
        incidents = sum(f["tranche"] == tranche and "incident" in f for f in facts)
        if incidents > 0.10 * planned_runs(study, tranche):
            reasons.append(f"{incidents} incidents in the {tranche} tranche, over 10% of its planned runs")
    return reasons


def stop(study, reason):
    """Record a stop once; spend.reserve then refuses every start."""
    if not spend.latest(spend.rows(study.ledger), "stop"):
        spend.record(study.ledger, "stop", reason=reason)
    print(f"STOP: {reason}")


def enforce(study, tranche):
    """Everything a start needs: order, a sound ledger, no stop rule fired."""
    require_order(study, tranche)
    audit_ledger(study)
    for reason in stop_reasons(study):
        stop(study, reason)
    spend.refuse_stopped(spend.rows(study.ledger))


def bound_argv(records, model, effort):
    """Every recorded call passes `--model <model>` and `--effort <effort>`."""
    for call in units.calls(records):
        args = (call / "argv.nul").read_bytes().split(b"\0") if (call / "argv.nul").is_file() else []
        pairs = {(a, b) for a, b in zip(args, args[1:])}
        if not {(b"--model", model.encode()), (b"--effort", effort.encode())} <= pairs:
            return False
    return True


def tokens(records):
    receipt = Path(records) / "metering.json"
    consumption = load(receipt).get("consumption") if receipt.is_file() else None
    return (consumption.get("claude") or {}).get("tokens") if isinstance(consumption, dict) else "unavailable"


def smoke_units(study, task):
    """(name, records, model, effort, facts) of every smoke unit: the runs and the pool's judges."""
    found = [(f"{facts['arm']}", path.parent, facts["model"], facts["effort"], facts)
             for path in study_runs(study) if (facts := load(path))["tranche"] == "smoke"]
    for _, _, pool, judge in [u for u in layout.judge_units(study) if u[:2] == (task, "first")]:
        facts_path = pool / "records" / f"study-{judge}.json"
        found.append((f"judge {judge}", pool / "records" / "judges" / judge, judge, JUDGE_EFFORT,
                      load(facts_path) if facts_path.is_file() else {}))
    return found


def smoke_check(study):
    """The mechanical part of the smoke checklist; records pass or fail in the ledger and returns it."""
    (task,) = tranche_tasks(task_rows(study), "smoke")
    found = smoke_units(study, task)
    runs = [f for name, _, _, _, f in found if not name.startswith("judge")]
    results_path = study.results / "pools" / f"{task}-first" / "results.json"
    results = load(results_path) if results_path.is_file() else {"clones": {}, "excluded_judges": {"pool": "missing"}}
    clones = results["clones"].values()
    reserved = {row["unit"]: row["calls"] for row in spend.starts(spend.rows(study.ledger)) if row["tranche"] == "smoke"}
    checks = {
        "every_program_ran_without_incident": sorted(f["arm"] for f in runs) == sorted(PLANNED["smoke"])
        and not any("incident" in f for f in runs),
        "clone_count": len(results["clones"]) == sum(f.get("outcome") == "completed" for f in runs) + 2,
        "both_judges_rated_every_clone": not results["excluded_judges"] and all(
            set(c.get("ratings", {})) == {spend.HAIKU, spend.SONNET} for c in clones) and bool(clones),
        "hidden_result_on_every_clone": bool(clones) and all(c.get("hidden") is not None for c in clones),
        "scans_and_session_audits_clean": all(f.get("scan_hits") == 0 and not f.get("incident") for _, _, _, _, f in found),
        "bound_model_and_effort_on_every_call": all(bound_argv(r, m, e) for _, r, m, e, _ in found),
        "calls_within_reserved": all(units.physical_calls(r) <= reserved.get(unit_of(r), 0) for _, r, _, _, _ in found),
        "no_provider_errors": all(units.provider_incident(r) is None for _, r, _, _, _ in found),
    }
    figures = {name: {"calls": units.physical_calls(r), "tokens": tokens(r), "wall_clock_sec_per_call":
                      _per_call(f, r)} for name, r, _, _, f in found}
    passed = all(checks.values()) and len(found) == len(PLANNED["smoke"]) + 2
    return spend.record(study.ledger, "smoke", passed=passed, checks=checks, figures=figures)


def unit_of(records):
    """The ledger unit of a run's or a judge's records directory."""
    records = Path(records)
    return f"{records.parents[2]}#{records.name}" if records.parent.name == "judges" else str(records)


def _per_call(facts, records):
    wall = facts.get("wall_clock_sec")
    if wall is None and (Path(records) / "record.json").is_file():
        wall = load(Path(records) / "record.json").get("wall_clock_sec")
    made = units.physical_calls(records)
    return wall / made if wall is not None and made else None

