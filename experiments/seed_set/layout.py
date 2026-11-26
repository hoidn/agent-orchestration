"""Where the seed-set study keeps things, and the plan's fixed per-tranche facts (plan Step 2).

`Study` names the frozen runtime, the work root (agents' trees and run records), the pools root, the results
directory, the task list, the judge-calibration criterion (the freeze's `criterion.json` lies beside it) and the
state directory holding the spend ledger (`~/.local/state/seed-set` for the command line; tests pass their own).

Tranches: the smoke runs on the manifest's `set: "smoke"` task (coordinator ruling 1, 2026-11-12: the leaking
T3 task left the drawn set, the reserve took its place and the smoke moved to the first T2 task that is not a
probe task); the redraw cap serves the ladder probe only (plan, "Ladder probe": the probe is the plan's one
redraw), on the ladder's packages (`ladder.packages`: both forms, without rejected rows and the smoke's commit);
the calibration runs on the tasks `probe-readout` wrote to `results/calibration-tasks.json` (`CHOSEN`), whose hash
the ledger holds. The Luna smoke (`LUNA_SMOKE`, ruling L-R8 of the Luna plan) runs on the smoke task too: its two
Luna arms once each, then one pool of its own kind (`LUNA_POOL`, beside the smoke's `first`) with its runs alone,
judged by the tranche's judges (`tranche_judges`: Haiku) under the judge criterion naming those judges only
(`pool_criterion`). `STUDY_TRANCHES` are the calibration study's own: every freeze carries their spend terms, and
the readout lists their programs; the Luna smoke gates none of them.
"""

import json
import math
from dataclasses import dataclass
from pathlib import Path

from experiments.compare.repos import dump, load
from experiments.seed_set import gates, ladder, spend

PROGRAMS = Path("experiments/seed_set/programs")  # in the runtime checkout
EFFORT = "medium"
# runs per task and arm, per tranche: the smoke runs every program once on the smoke task
LUNA_SMOKE, LUNA_POOL = "luna_smoke", "luna"  # the Luna smoke's tranche and its pool's kind
PLANNED = {"smoke": dict.fromkeys(("direct", "direct_sonnet", "retry_until_check", "implement_check_repair",
                                   "implement_review_revise"), 1),
           "calibration": {"direct": 4, "direct_sonnet": 1}, "redraw": {"direct": 1},  # redraw: one per probe step
           LUNA_SMOKE: {"direct_luna": 1, "retry_until_check_luna": 1}}
RETESTS = {"smoke": 0, "calibration": 10, "redraw": 0, LUNA_SMOKE: 0}  # the first tasks of the tranche, in its order
STUDY_TRANCHES = ("smoke", "calibration", "redraw")
SMOKES = ("smoke", LUNA_SMOKE)  # on the smoke task; a slot a usage limit cut never runs again
CHOSEN = "calibration-tasks.json"  # under the results directory
MIN_FREE = 20 * 10**9
WIDTH = 2  # units in flight at a time (coordinator ruling R3): a usage limit cuts at most two
RUBRIC = {"workflow": "score_functional.orc", "entry": "score_functional::score", "criteria": ["quality"],
          "reference": None}


@dataclass(frozen=True)
class Study:
    runtime: Path
    work: Path
    pools: Path
    results: Path
    tasks_file: Path
    criterion: Path
    state: Path
    min_free: int = MIN_FREE

    @property
    def ledger(self):
        return self.state / spend.LEDGER.name

    @property
    def programs(self):
        return self.runtime / PROGRAMS

    @property
    def frozen(self):
        return self.criterion.parent / "criterion.json"

    @property
    def host_temp(self):
        """The record of the host-side checks' temporary directories (`host.temporary`, `host.sweep`)."""
        return self.state / "host-temp.jsonl"


def task_rows(study):
    return [json.loads(line) for line in study.tasks_file.read_text().splitlines()]


def task_dir(study, task):
    return study.tasks_file.parent / "tasks" / task


def chosen(study):
    """The calibration's chosen tasks [{"id", "rung"}] as probe-readout wrote them, or [] before it did."""
    path = study.results / CHOSEN
    return load(path)["tasks"] if path.is_file() else []


def tranche_tasks(study, tranche):
    """The tasks a tranche may run, in order: the smoke task for either smoke, every ladder package for the probe,
    the chosen tasks for the calibration."""
    rows = task_rows(study)
    if tranche in SMOKES:
        return [row["id"] for row in rows if row.get("set") == "smoke"]
    if tranche == "redraw":
        return [package["id"] for package in ladder.packages(rows)]
    return [task["id"] for task in chosen(study)]


def require_tasks(study, tranche, tasks, kind="first"):
    """{package: fix commit}; refuse tasks outside the tranche (or outside its retest tasks)."""
    allowed = tranche_tasks(study, tranche)
    if kind == "retest":
        allowed = allowed[:RETESTS[tranche]]
    if not tasks or set(tasks) - set(allowed):
        raise SystemExit(f"{tranche} {kind} takes tasks among {allowed}, not {sorted(set(tasks) - set(allowed))}")
    return ladder.fix_commits(task_rows(study))


def require_pool_kind(tranche, kind):
    """Refuse a pool kind the tranche does not build: the Luna smoke's is `LUNA_POOL` alone, every other tranche's
    `first` or `retest`."""
    if (tranche == LUNA_SMOKE) != (kind == LUNA_POOL):
        raise SystemExit(f"{tranche} builds {'the ' + LUNA_POOL if tranche == LUNA_SMOKE else 'first or retest'} "
                         f"pools, not {kind}")


def tranche_judges(tranche):
    """The judges a tranche's caps give calls (`spend.CAPS`), in `gates.JUDGES` order."""
    return [judge for judge in gates.JUDGES if spend.CAPS[tranche]["judge"].get(judge)]


def pool_criterion(study, kind):
    """The judge criterion a pool of `kind` is built and summarized under: the study's, or for the Luna smoke's pool
    a copy naming only the Luna smoke's judges (summarize.py takes the criterion's judges to be the pool's), written
    to `results/` from the study's on every call, so both steps read the same bytes."""
    if kind != LUNA_POOL:
        return study.criterion
    path = study.results / f"{LUNA_SMOKE}-criterion.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    dump(path, load(study.criterion) | {"judges": tranche_judges(LUNA_SMOKE)})
    return path


def load_arms(study):
    """arms.json with every model one of the study's exact IDs (`spend.MODELS`), effort medium and at most three
    calls."""
    arms = load(study.programs / "arms.json")
    for name, arm in arms.items():
        spend.check_model(arm["model"])
        if arm["effort"] != EFFORT or type(arm["max_calls"]) is not int or not 1 <= arm["max_calls"] <= 3:
            raise SystemExit(f"arms.json {name}: effort must be {EFFORT} and max_calls 1 to 3")
    return arms


def load_criterion(study):
    """The judge-calibration criterion: both judges, the functional rubric, and no calibration purpose or block
    (summarize.py skips hidden tests for purpose "calibration")."""
    value = load(study.criterion)
    if (value.get("purpose") == "calibration" or "calibration" in value or value.get("rubric") != RUBRIC
            or sorted(value.get("judges", [])) != sorted(gates.JUDGES)):
        raise SystemExit(f"{study.criterion}: the judge-calibration criterion names both judges and the functional "
                         "rubric, without a calibration purpose or block")
    return value


def spend_terms(study, tranche, model):
    """(the tranche's priced ceiling, the model's per-call worst case, the pin {"path", "version"} of the CLI that
    runs the model, `spend.CLI`) from criterion.json's "spend" block (coordinator rulings R4 and R5):
    {"ceiling_usd": {tranche: USD}, "per_call_usd": {model: USD}, "cli": pins}. `pins` takes two shapes
    (`cli_pin`): {cli: {"path", "version"}}, a pin per CLI, or one {"path", "version"}, which pins the Claude CLI
    and no other. The coordinator sets them at the freeze; there is no default, and a start without them refuses."""
    terms = load(study.frozen).get("spend") or {}
    ceiling, per_call = (terms.get("ceiling_usd") or {}).get(tranche), (terms.get("per_call_usd") or {}).get(model)
    cli = cli_pin(terms.get("cli"), spend.CLI.get(model))
    if not (positive(ceiling) and positive(per_call) and isinstance(cli, dict) and sorted(cli) == ["path", "version"]
            and all(isinstance(value, str) and value for value in cli.values())):
        raise SystemExit(f"{study.frozen} names no priced ceiling for {tranche}, per-call worst case for {model} or "
                         f"pin (path and version) of the CLI that runs {model} ({spend.CLI.get(model, 'no known CLI')}) "
                         "under \"spend\": the coordinator sets them at the freeze")
    return ceiling, per_call, cli


def cli_pin(pins, name):
    """The pin of CLI `name` in criterion.json's `spend.cli`: `pins[name]`, or `pins` itself when it is one pin (it
    names a "path"), which is the Claude CLI's; None without one."""
    if isinstance(pins, dict) and "path" in pins:
        pins = {"claude": pins}
    return pins.get(name) if isinstance(pins, dict) else None


def positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def study_runs(study):
    """study.json of every candidate run the study prepared, in records order."""
    return sorted(study.work.glob("records/*/run-*/study.json"))


def counted_runs(study):
    """`study_runs` without the probe runs whose form is not the current one: the calibration's slots, pools and
    readout count a probe run only when the programs of the freeze in force at its reservation (the last `freeze`
    before its row) are those of the latest freeze (ruling R17: the programs' text is part of the form)."""
    entries = spend.rows(study.ledger)
    freezes = [row for row in entries if row["kind"] == "event" and row["event"] == "freeze"]
    latest = freezes[-1].get("programs") if freezes else None
    def programs(seq):
        return next((row.get("programs") for row in reversed(freezes) if row["seq"] < seq), None)
    stale = {row["unit"] for row in spend.starts(entries)
             if row["tranche"] == "redraw" and programs(row["seq"]) != latest}
    return [path for path in study_runs(study) if str(path.parent) not in stale]


def judge_units(study):
    """(task, kind, pool, judge) of every judge unit with a records directory under the pools root (a rebuilt
    pool's kind is its pool's)."""
    return [(pool.parent.name, pool.name.removesuffix(REBUILT), pool, judge.name)
            for pool in sorted(study.pools.glob("*/*")) for judge in sorted((pool / "records" / "judges").glob("*"))]


REBUILT = ".2"  # a pool with a judge cut by a usage limit is rebuilt once, from the same records, as <kind>.2


def current_pool(study, task, kind):
    """The pool of (task, kind) that counts: its rebuild when there is one, else the first (built or not)."""
    first = study.pools / task / kind
    rebuilt = first.with_name(kind + REBUILT)
    return rebuilt if rebuilt.exists() else first


def cut_judges(pool):
    """The judges of a pool whose run a usage limit cut."""
    return sorted(path.stem.removeprefix("study-") for path in (Path(pool) / "records").glob("study-*.json")
                  if "cut" in load(path))
