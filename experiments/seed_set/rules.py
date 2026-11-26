"""Order and stop rules of the seed-set study, the physical audit of its ledger, and the smoke check (plan Step 2,
Stop rules, Ledger).

Order: no start before a `freeze` event whose identity still matches (`frozen_identity`); no probe
(the redraw cap) or calibration start before a passing `smoke` event; no calibration start before a `probe_readout`
event whose chosen list still matches `results/calibration-tasks.json`; no calibration judge outside the early judge
look's three first pools before a passed `early_look` event, and none after a failed one. Stops (a `stop` event, after which `spend.reserve` refuses
everything): a forbidden-model answer in a run or a judge, three tasks with a contaminated run or judgment, more
than 10% of a tranche's planned runs ending as incidents, and a `stop:` decision of the readout. A run cut by a usage
limit is not an incident (coordinator ruling R1); its `pause` event closes starts until `resume-after-limit` (R2),
which is no stop. The audit refuses when a unit made calls the ledger does not hold (a missing or foreign ledger) or
more calls than it reserved.

The freeze (coordinator ruling on review2 M6, 2026-11-12) binds what decides the verdicts and what the agents see:
the runtime commit, the git tree of the study's and the harness's code (`experiments/seed_set`,
`experiments/compare`), each task package's tree, the task list's and the five programs' sha256, and the sha256 of
`criterion.json` and `judge-calibration.json`. It refuses, at the freeze and before every start, when a loaded
module of either package is not the runtime's file (run with the runtime as the working directory and PYTHONPATH),
when the task list lies outside the runtime, when the code or the packages hold an untracked file (the criterion
files and the results directory, written after the commit, excepted), and when
`criterion.json` does not name, under "sha256", the current sha256 of the task list, every program, the rubric
`score_functional.orc`, the price table `orchestrator/providers/price_table.json` (coordinator ruling R4) and
`judge-calibration.json` (plan Step 1f; keys are runtime-relative paths, the judge criterion by its file name), and
when a package the study can draw, probe or smoke on has no stable entry at its
current hash and the scoring path of the runtime's files in `anchor_stability.json` (`anchors.py`; coordinator
rulings, 2026-11-12 and 2026-11-15). A second freeze after a start needs a reason, which the ledger keeps.
"""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from experiments.compare.repos import git, load, runtime_commit, sha256_file
from experiments.compare.scan import model_policy
from experiments.seed_set import anchors, gates, layout, ladder, spend, units
from experiments.seed_set.layout import CHOSEN, PLANNED, WIDTH, study_runs, tranche_tasks
from orchestrator.providers.pricing import FIELDS, load_price_table

JUDGE_EFFORT = "high"  # score_functional.orc's fixed judge effort


CODE = ("experiments/seed_set", "experiments/compare")
RUBRIC_FILE = Path("experiments/compare") / layout.RUBRIC["workflow"]
PRICE_TABLE = Path("orchestrator/providers/price_table.json")  # the runtime's; its sha256 is frozen (ruling R4)


def frozen_identity(study):
    """The freeze's identity of the study as it is now; refuses what the freeze does not bind (module docstring)."""
    for path in (study.frozen, study.criterion):
        if not path.is_file():
            raise SystemExit(f"{path} is missing: freeze the criterion first (plan Step 1f)")
    runtime = study.runtime.resolve()
    if not study.tasks_file.resolve().is_relative_to(runtime):
        raise SystemExit(f"the task list {study.tasks_file} lies outside the runtime {runtime}")
    if outside := loaded_elsewhere(runtime):
        raise SystemExit(f"study or harness modules loaded from outside the runtime {runtime}: {outside[:3]}; run "
                         "with the runtime as working directory and PYTHONPATH")
    packages = study.tasks_file.resolve().parent.relative_to(runtime) / "tasks"
    require_tracked(study, runtime, packages)
    require_named_hashes(study)
    stability = require_stable_anchors(study)
    return {"criterion_sha256": sha256_file(study.frozen), "judge_criterion_sha256": sha256_file(study.criterion),
            "runtime_commit": runtime_commit(runtime), "code_tree": tree(runtime, *CODE),
            "packages": tree(runtime, f"{packages}/"),
            "tasks_sha256": sha256_file(study.tasks_file), "anchor_stability_sha256": sha256_file(stability),
            "price_table_sha256": sha256_file(runtime / PRICE_TABLE),
            "programs": {path.name: sha256_file(path) for path in sorted(study.programs.glob("*.orc"))}}


def require_tracked(study, runtime, packages):
    """Refuse an untracked file in the runtime's code or task packages (the criterion files and the results,
    written after the commit, excepted)."""
    written = [f":(exclude){path.resolve().relative_to(runtime)}" for path in (study.frozen, study.criterion,
               study.results) if path.resolve().is_relative_to(runtime)]  # written after the commit (Step 1f)
    if untracked := git(runtime, "--no-optional-locks", "status", "--porcelain", "--untracked-files=all", "--",
                        *CODE, str(packages), *written):
        raise SystemExit(f"untracked files in the runtime's code or task packages:\n{untracked}")


def require_named_hashes(study):
    """Refuse a criterion.json that does not name the current sha256 of every file it must (`required_hashes`)."""
    named, required = load(study.frozen).get("sha256", {}), required_hashes(study)
    if wrong := sorted(key for key, digest in required.items() if named.get(key) != digest):
        raise SystemExit(f"{study.frozen} does not name the current sha256 of {wrong} (plan Step 1f)")


def require_stable_anchors(study):
    """The anchor stability file; refuses when a package the study can use has no stable entry at its hash and
    the scoring path of the runtime's files."""
    stability = study.tasks_file.parent / anchors.FILE
    if lost := anchors.unstable(layout.task_rows(study), load(stability) if stability.is_file() else {},
                                study.tasks_file.parent / "tasks", study.runtime.resolve()):
        moved = ("; another scoring path is expected after a commit to a kit module (or a Python or pytest update) "
                 "since the freeze, and the remedy is then a new freeze (the anchors run on the new runtime commit, "
                 "then `record-freeze`), not the anchors run alone"
                 if any(why.endswith("(other scoring path)") for why in lost) else "")
        raise SystemExit(f"no stable anchors under study conditions ({stability}) for {lost[:5]} "
                         f"({len(lost)} packages): run `python -m experiments.seed_set.anchors --work W` and reject "
                         f"what fails{moved}")
    return stability


def tree(runtime, *paths):
    """{path: git object id} of HEAD's entries at `paths`: the identity of their tracked content."""
    return {line.split("\t")[1]: line.split()[2] for line in git(runtime, "ls-tree", "HEAD", "--", *paths).splitlines()}


def loaded_elsewhere(runtime):
    """Files of loaded `experiments.seed_set` and `experiments.compare` modules that are not under `runtime`."""
    files = [getattr(module, "__file__", None) for name, module in list(sys.modules.items())
             if name.startswith(tuple(code.replace("/", ".") for code in CODE))]
    return sorted(f for f in files if f and not Path(f).resolve().is_relative_to(runtime))


def required_hashes(study):
    """{key: sha256} that criterion.json must name: the task list, every program, the rubric, the price table, the
    judge criterion."""
    runtime = study.runtime.resolve()
    paths = [study.tasks_file.resolve(), *sorted(study.programs.resolve().glob("*.orc")), runtime / RUBRIC_FILE,
             runtime / PRICE_TABLE]
    return {str(path.relative_to(runtime)): sha256_file(path) for path in paths} | {
        study.criterion.name: sha256_file(study.criterion)}


def check_cli(declaration, pin, cli="claude"):
    """{"path", "version"} of the unit's `cli` ("claude" or "codex", `spend.CLI` of its model) when the unit
    declaration names the pinned absolute path for it and it answers `--version` with the pinned version
    (coordinator ruling R5; an installed CLI updates itself); else refuse the start. The version runs from the
    study's process with an empty home: no credential, no sandbox. PATH is /usr/bin:/bin for Claude, and the
    declaration's own `path` for Codex, whose launcher is a Node script."""
    data = load(declaration)
    path = data.get(cli)
    if path != pin["path"]:
        raise SystemExit(f"the unit's {cli} CLI {path} is not the pinned {pin['path']}: nothing starts")
    search = "/usr/bin:/bin" if cli == "claude" else os.pathsep.join(data["path"])
    with tempfile.TemporaryDirectory() as home:
        done = subprocess.run([path, "--version"], env={"HOME": home, "PATH": search, "DISABLE_AUTOUPDATER": "1"},
                              capture_output=True, text=True, timeout=120)
    if done.returncode or done.stdout.strip() != pin["version"]:
        raise SystemExit(f"{path} --version answered {done.stdout.strip()!r} (exit {done.returncode}), not the "
                         f"pinned {pin['version']!r}: nothing starts")
    return {"path": path, "version": pin["version"]}


def tier_ratio(study, model):
    """The frozen table's highest tier over its ordinary rates for `model`, 1 without a tier: the runtime's
    `--max-cost-usd` counts every call at the highest tier (`pricing.cap_cost`), the ledger at the ordinary rates."""
    rates = load_price_table(study.runtime / PRICE_TABLE)["models"][model]
    tier = rates.get("long_context")
    if tier and any(tier[key] and not rates[key] for key in FIELDS):
        raise SystemExit(f"{model}: a long-context rate over an ordinary rate of 0 has no bounded ratio")
    return max(tier[key] / rates[key] for key in FIELDS if rates[key]) if tier else 1


def bounded(study):
    """(tranches, models) whose spend terms a freeze checks: the study's own tranches (`layout.STUDY_TRANCHES`), which
    every criterion prices, and each other tranche whose priced ceiling `criterion.json` names (so a criterion
    without the Luna smoke's terms freezes, and a Luna smoke start then refuses at `layout.spend_terms`); and the
    models those tranches have calls for."""
    ceilings = (load(study.frozen).get("spend") or {}).get("ceiling_usd") or {}
    tranches = [tranche for tranche in spend.CAPS if tranche in layout.STUDY_TRANCHES or tranche in ceilings]
    models = [model for model in spend.MODELS
              if any(spend.CAPS[tranche][kind].get(model) for tranche in tranches for kind in spend.KINDS)]
    return tranches, models


def require_spend_bounds(study):
    """Refuse spend terms the runtime or two units in flight would breach (review3 X3): a model's per-call worst case
    below its tier ratio times the largest ordinary-rate call `criterion.json` names for it (`largest_call_usd`; a
    call billed at the highest tier stays inside it), or a tranche's ceiling below WIDTH times the worst case of its
    largest unit (a program at its maximum calls, a judge at one batch: the study's pools are one batch). Only the
    tranches and models `bounded` names need terms."""
    largest, arms = (load(study.frozen).get("spend") or {}).get("largest_call_usd") or {}, layout.load_arms(study)
    tranches, models = bounded(study)
    for model in models:
        per_call = layout.spend_terms(study, "smoke", model)[1]
        if not layout.positive(largest.get(model)):
            raise SystemExit(f"{study.frozen} names no largest ordinary-rate call for {model} under spend")
        if per_call < round(tier_ratio(study, model) * largest[model], 6):
            raise SystemExit(f"{model}: the per-call worst case USD {per_call:g} is below {tier_ratio(study, model):g} "
                             f"x the largest ordinary-rate call USD {largest[model]:g}")
    for tranche in tranches:
        units_ = [(arms[arm]["max_calls"], arms[arm]["model"]) for arm in PLANNED[tranche]]
        units_ += [(1, judge) for judge in layout.tranche_judges(tranche)]
        worst = max(calls * layout.spend_terms(study, tranche, model)[1] for calls, model in units_)
        if (ceiling := layout.spend_terms(study, tranche, spend.HAIKU)[0]) < round(WIDTH * worst, 6):
            raise SystemExit(f"{tranche}: the ceiling USD {ceiling:g} is below {WIDTH} units in flight at the largest "
                             f"unit's worst case USD {worst:g}")


def record_freeze(study, reason=None):
    """Record the freeze's identity in the ledger: the first spend needs it, and spend terms the runtime or two
    units in flight would breach refuse it (`require_spend_bounds`). Once a start exists, a new freeze needs a reason
    (an apparatus fix the plan's ledger records), which the event keeps."""
    layout.load_criterion(study)
    if spend.starts(spend.rows(study.ledger)) and not reason:
        raise SystemExit("starts exist: a new freeze needs --reason (the apparatus fix it records)")
    identity = frozen_identity(study)
    require_spend_bounds(study)
    return spend.record(study.ledger, "freeze", **identity, **({"reason": reason} if reason else {}))


def require_order(study, tranche):
    entries = spend.rows(study.ledger)
    freeze = spend.latest(entries, "freeze")
    if freeze is None:
        raise SystemExit("no freeze in the ledger: record-freeze after the criterion is frozen (plan Step 1f)")
    current = frozen_identity(study)
    if any(freeze[key] != value for key, value in current.items()):
        raise SystemExit(f"the criterion or runtime changed since the freeze: {current} against {freeze}")
    smoke, readout = spend.latest(entries, "smoke"), spend.latest(entries, "probe_readout")
    if tranche in ("redraw", "calibration") and not (smoke and smoke["passed"]):
        raise SystemExit("no passed smoke in the ledger: run the smoke and smoke-check first")
    if tranche == "calibration":
        path = study.results / CHOSEN
        if not (readout and readout.get("chosen_sha256")) or not path.is_file() or sha256_file(path) != readout[
                "chosen_sha256"]:
            raise SystemExit(f"no chosen calibration tasks: probe-readout writes {path} and its hash in the ledger "
                             "(plan, Ladder probe)")


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
    """The runs the tranche plans: the smoke's five, the calibration's five per chosen task, and the probe's units
    (a task in one phase; a relaunch is the same unit), at least the flat probe's 20 (review2 minor 4: the
    extension's probe units count)."""
    if tranche == "redraw":
        units = {(row.get("task"), row.get("step")) for row in spend.starts(spend.rows(study.ledger))
                 if row["tranche"] == "redraw"}
        return max(len(ladder.FLAT) * ladder.PROBE_TASKS, len(units))
    return sum(PLANNED[tranche].values()) * len(tranche_tasks(study, tranche))


EARLY_TASKS, EARLY_MARGIN = 3, 4  # plan, Early judge look


def require_early_look(study, tranche, kind, tasks):
    """Calibration judges: only the first pools of the first three chosen tasks before the early judge look has
    passed, and none after it failed."""
    if tranche != "calibration":
        return
    look = spend.latest(spend.rows(study.ledger), "early_look")
    if look and not look["passed"]:
        raise SystemExit(f"the early judge look failed ({look['tasks_below']}): no further judge call; report to "
                         "the owner (plan, Early judge look)")
    first = tranche_tasks(study, "calibration")[:EARLY_TASKS]
    if not look and (kind != "first" or set(tasks) - set(first)):
        raise SystemExit(f"before the early judge look only the first pools of {first} are judged; then early-look")


def early_look(study):
    """Reference minus base per judge on the first three chosen tasks' first pools (an incident pool counts as
    below the margin); failed when, for both judges, it is under 4 points on two of the three. Recorded."""
    first = tranche_tasks(study, "calibration")[:EARLY_TASKS]
    below = {judge: [] for judge in gates.JUDGES}
    for task in first:
        path = study.results / "pools" / f"{task}-first" / "results.json"
        if not path.is_file() and not path.with_name("incident.json").is_file():
            raise SystemExit(f"{task}: its first pool is not summarized yet; judge and summarize the first three")
        anchors = {c["labels"][0].removeprefix(f"{task}-"): c.get("ratings", {})
                   for c in (load(path)["clones"].values() if path.is_file() else []) if c["arm"] == "anchor"}
        for judge in gates.JUDGES:
            try:
                gap = anchors["upstream"][judge]["quality"] - anchors["base"][judge]["quality"]
            except (KeyError, TypeError):
                gap = None
            if gap is None or gap < EARLY_MARGIN:
                below[judge].append(task)
    passed = not all(len(tasks) >= 2 for tasks in below.values())
    return spend.record(study.ledger, "early_look", passed=passed, tasks=first, tasks_below=below)


def stop_reasons(study):
    reasons = []
    if len(contaminated := contaminated_tasks(study)) >= 3:
        reasons.append(f"three or more contaminated tasks: {contaminated}")
    facts = [load(path) for path in study_runs(study)]
    for tranche in PLANNED:
        incidents = sum(f["tranche"] == tranche and "incident" in f for f in facts)
        if incidents * 10 > planned_runs(study, tranche):  # over 10%, exactly
            reasons.append(f"{incidents} incidents in the {tranche} tranche, over 10% of its planned runs")
    return reasons


def written_filesystems(study, path):
    """Where a start writes: `path` (its trees or pools), the results, the ledger, the host checks' temporary
    clones and `/`."""
    return [path, study.results, study.state, Path(tempfile.gettempdir()), Path("/")]


def require_free(study, path):
    """Plan, Stop rules: under the floor (20 GB) free on any filesystem a start writes to, stop (review2 minor 5)."""
    path.mkdir(parents=True, exist_ok=True)
    for where in written_filesystems(study, path):
        existing = next(p for p in (where, *where.parents) if p.exists())
        if (free := shutil.disk_usage(existing).free) < study.min_free:
            reason = f"{free / 1e9:.1f} GB free under {existing}, below {study.min_free / 1e9:.0f} GB"
            stop(study, reason)
            raise SystemExit(f"stop: {reason}")


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
    spend.refuse_closed(spend.rows(study.ledger))


def bound_argv(records, model, effort):
    """Every recorded call passes `--model <model>` and its CLI's effort flag: `--effort <effort>` for Claude, and
    `--config model_reasoning_effort=<effort>` for a call the shim recorded as Codex (`provider.txt`), as the metered
    templates bind them."""
    for call in units.calls(records):
        args = (call / "argv.nul").read_bytes().split(b"\0") if (call / "argv.nul").is_file() else []
        pairs = {(a, b) for a, b in zip(args, args[1:])}
        codex = (call / "provider.txt").is_file() and (call / "provider.txt").read_text().strip() == units.CODEX
        bound = (b"--config", b"model_reasoning_effort=" + effort.encode()) if codex else (b"--effort", effort.encode())
        if not {(b"--model", model.encode()), bound} <= pairs:
            return False
    return True


def tokens(records, model):
    """The metered tokens of a unit's calls by the CLI that runs `model` (`spend.CLI`), from its metering.json."""
    receipt = Path(records) / "metering.json"
    consumption = load(receipt).get("consumption") if receipt.is_file() else None
    return (consumption.get(spend.CLI[model]) or {}).get("tokens") if isinstance(consumption, dict) else "unavailable"


def scan_record(records):
    """The scan of a unit's records directory: a run's `scan` in its record.json, or a judge's scan.json; or None."""
    run, judge = Path(records) / "record.json", Path(records) / "scan.json"
    if run.is_file():
        return load(run).get("scan")
    return load(judge) if judge.is_file() else None


def scan_clean(records):
    """Scanned, and every hit adjudicated `cleared` (coordinator ruling, 2026-11-23); contaminated or no verdict is
    not clean."""
    found = scan_record(records)
    return found is not None and (not found["hits"] or (found["verdict"] or {}).get("verdict") == "cleared")


def adjudication_command(records):
    """The `prepare.py scan` command of a run or judge whose scan holds hits and no verdict, or None. Model-policy hits
    need no verdict: that run or judge is excluded anyway."""
    found, records = scan_record(records), Path(records)
    if not (found and found.get("hits") and found.get("verdict") is None and not model_policy(found["hits"])):
        return None
    if (records / "record.json").is_file():
        return f"prepare.py scan --run {records}"
    return f"prepare.py scan --pool {records.parents[2]} --judge {records.name}"


def refuse_unadjudicated(commands, step):
    """Stop `step` before it writes anything while a scan awaits its verdict, so a forgotten adjudication leaves no
    permanent record (an incident, a smoke result): the operator adjudicates and runs `step` again."""
    if commands := [command for command in commands if command]:
        raise SystemExit(f"scan hits and no verdict; adjudicate each, then run {step} again:\n" + "\n".join(
            f"  {command} --verdict contaminated|cleared --reason TEXT" for command in commands))


SMOKE_POOLS = {"smoke": "first", layout.LUNA_SMOKE: layout.LUNA_POOL}  # each smoke's pool kind on the smoke task


def smoke_units(study, task, tranche="smoke"):
    """(name, records, model, effort, facts) of every unit of the smoke `tranche`: the runs and its pool's judges."""
    found = [(f"{facts['arm']}", path.parent, facts["model"], facts["effort"], facts)
             for path in study_runs(study) if (facts := load(path))["tranche"] == tranche]
    for _, _, pool, judge in [u for u in layout.judge_units(study) if u[:2] == (task, SMOKE_POOLS[tranche])]:
        facts_path = pool / "records" / f"study-{judge}.json"
        found.append((f"judge {judge}", pool / "records" / "judges" / judge, judge, JUDGE_EFFORT,
                      load(facts_path) if facts_path.is_file() else {}))
    return found


def smoke_check(study, tranche="smoke"):
    """The mechanical part of the checklist of the smoke `tranche` (the Claude smoke, or the Luna smoke with its one
    judge and `luna_checks`); records pass or fail in the ledger as an event named after the tranche (the Claude
    smoke's is the `smoke` event the probe and the calibration require; the Luna smoke's gates none of them) and
    returns it. A unit cut by a usage limit, a planned program without its run and a reserved unit not yet settled
    each fail it. A failed smoke is a stop for the owner; a repeat the owner approves runs from a new freeze and a
    fresh ledger (the kit's README, "Running a tranche again after a stop or a failed smoke")."""
    (task,) = tranche_tasks(study, tranche)
    found, judges = smoke_units(study, task, tranche), layout.tranche_judges(tranche)
    refuse_unadjudicated([adjudication_command(r) for _, r, _, _, _ in found], "smoke-check")
    runs = [f for name, _, _, _, f in found if not name.startswith("judge")]
    results_path = study.results / "pools" / f"{task}-{SMOKE_POOLS[tranche]}" / "results.json"
    results = load(results_path) if results_path.is_file() else {"clones": {}, "excluded_judges": {"pool": "missing"}}
    reserved = {row["unit"]: row["calls"] for row in spend.starts(spend.rows(study.ledger))
                if row["tranche"] == tranche}
    checks = (unit_checks(found, runs, reserved, tranche) | pool_checks(results_path, results, runs, judges)
              | call_checks(found, reserved))
    extra = luna_checks(study, reserved, runs) if tranche == layout.LUNA_SMOKE else {"checks": {}}
    checks |= extra.pop("checks")
    passed = all(checks.values()) and len(found) == len(PLANNED[tranche]) + len(judges)
    direct = [(f, r) for name, r, _, _, f in found if name == "direct" and "cut" not in f]  # a cut call says nothing
    return spend.record(study.ledger, tranche, passed=passed, checks=checks, figures=smoke_figures(found),
                        **bisect_from_start(direct), **extra)


def smoke_figures(found):
    """Per smoke unit: its physical calls, metered tokens and wall-clock seconds per call."""
    return {name: {"calls": units.physical_calls(r), "tokens": tokens(r, m), "wall_clock_sec_per_call":
                   _per_call(f, r)} for name, r, m, _, f in found}


def luna_checks(study, reserved, runs):
    """The Luna smoke's own: {"checks": no pause of the Codex starts (a credit balance, ruling L-R7) that one of its
    units recorded or that is open now, and every run's metering completeness recorded; "metering_complete": each
    run's recorded value, which does not decide the check}."""
    entries = spend.rows(study.ledger)
    open_now = {row["seq"] for row in spend.open_pauses(entries)}
    credit = [row for row in entries if row["kind"] == "event" and row["event"] == "pause"
              and row.get("closes") == units.CODEX and (row.get("unit") in reserved or row["seq"] in open_now)]
    return {"checks": {"no_credit_pause": not credit,
                       "metering_completeness_recorded": bool(runs) and all("metering_complete" in f for f in runs)},
            "metering_complete": {f["arm"]: f.get("metering_complete") for f in runs}}


def unit_checks(found, runs, reserved, tranche="smoke"):
    """Every planned program ran without incident, no unit was cut by a usage limit, every reserved unit settled."""
    settled = {unit_of(r) for _, r, _, _, f in found if "calls" in f}
    return {"every_program_ran_without_incident": sorted(f["arm"] for f in runs) == sorted(PLANNED[tranche])
            and not any("incident" in f for f in runs),
            "no_unit_cut_by_a_usage_limit": not any("cut" in f for _, _, _, _, f in found),  # review3 X1
            "every_reserved_unit_settled": set(reserved) <= settled}


def pool_checks(results_path, results, runs, judges=(spend.HAIKU, spend.SONNET)):
    """The smoke pool holds every completed run and both anchors, rated by every one of the smoke's `judges` (named
    "both" for two), with hidden results, and its ratings bound to the judged patches."""
    clones = results["clones"].values()
    return {"clone_count": len(results["clones"]) == sum(f.get("outcome") == "completed" for f in runs) + 2,
            f"{'both_judges' if len(judges) == 2 else 'the_judge'}_rated_every_clone": not results["excluded_judges"]
            and all(set(c.get("ratings", {})) == set(judges) for c in clones) and bool(clones),
            "hidden_result_on_every_clone": bool(clones) and all(c.get("hidden") is not None for c in clones),
            "ratings_bound_to_judged_patches": ratings_bound(results_path.parent, results)}


def call_checks(found, reserved):
    """Clean scans and session audits, the bound model and effort on every call, calls within the reservation, no
    provider error."""
    return {"scans_and_session_audits_clean": all(scan_clean(r) and not f.get("incident") for _, r, _, _, f in found),
            "bound_model_and_effort_on_every_call": all(bound_argv(r, m, e) for _, r, m, e, _ in found),
            "calls_within_reserved": all(units.physical_calls(r) <= reserved.get(unit_of(r), 0)
                                         for _, r, _, _, _ in found),
            "no_provider_errors": all(units.provider_incident(r) is None for _, r, _, _, _ in found)}


def ratings_bound(directory, results):
    """Every rating in a summarized pool was given on the pooled patch (its judge's recorded digest matches)."""
    judged = {path.stem.removeprefix("study-"): load(path).get("judged_patches", {})
              for path in Path(directory).glob("study-*.json")}
    return bool(results["clones"]) and all(
        judged.get(judge, {}).get(cid) == sha256_file(Path(directory) / "patches" / f"{cid}.diff")
        for cid, clone in results["clones"].items() for judge in clone.get("ratings", {}))


def bisect_from_start(direct):
    """The median wall time and CLI-reported cost of the smoke's Haiku `direct` runs [(facts, records)], and
    whether either is above the plan's line for bisecting the ladder from the start (15 minutes, USD 0.50)."""
    walls = sorted(w for f, r in direct if (w := _per_call(f, r)) is not None)
    costs = sorted(c for _, r in direct if (c := units.cli_cost(load(Path(r) / "record.json")["sandbox"]["home"]))
                   is not None)
    wall = walls[len(walls) // 2] if walls else None
    cost = costs[len(costs) // 2] if costs else None
    return {"direct_median_wall_sec": wall, "direct_median_cli_cost_usd": cost if cost is not None else "unavailable",
            "bisect": (wall or 0) > ladder.BISECT_WALL_SEC or (cost or 0) > ladder.BISECT_COST_USD}


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

