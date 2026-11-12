"""Where the seed-set study keeps things, and the plan's fixed per-tranche facts (plan Step 2).

`Study` names the frozen runtime, the work root (agents' trees and run records), the pools root, the results
directory, the task list, the judge-calibration criterion (the freeze's `criterion.json` lies beside it) and the
state directory holding the spend ledger (`~/.local/state/seed-set` for the command line; tests pass their own).
"""

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from experiments.compare.repos import load
from experiments.seed_set import gates, spend

PROGRAMS = Path("experiments/seed_set/programs")  # in the runtime checkout
EFFORT = "medium"
# runs per task and arm, per tranche: the smoke runs every program once on the last reserve task
PLANNED = {"smoke": dict.fromkeys(("direct", "direct_sonnet", "retry_until_check", "implement_check_repair",
                                   "implement_review_revise"), 1),
           "calibration": {"direct": 4, "direct_sonnet": 1}, "redraw": {"direct": 4, "direct_sonnet": 1}}
RETESTS = {"smoke": 0, "calibration": 10, "redraw": 5}  # the first tasks of the tranche, in seed order
REDRAW_TASKS = 10  # coordinator ruling 2026-11-11: no scaled-down redraw
MIN_FREE = 20 * 10**9
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


def task_rows(study):
    return [json.loads(line) for line in study.tasks_file.read_text().splitlines()]


def task_dir(study, task):
    return study.tasks_file.parent / "tasks" / task


def tranche_tasks(rows, tranche):
    """The tasks a tranche may run, in seed order: the last reserve task for the smoke, the other reserve tasks
    for the redraw, the drawn tasks for the calibration."""
    reserve = [row["id"] for row in rows if row["set"] == "reserve"]
    return {"smoke": reserve[-1:], "redraw": reserve[:-1]}.get(
        tranche, [row["id"] for row in rows if row["set"] == "drawn"])


def require_tasks(study, tranche, tasks, kind="first"):
    """{task: fix commit}; refuse tasks outside the tranche (or outside its retest tasks)."""
    allowed = tranche_tasks(task_rows(study), tranche)
    if kind == "retest":
        allowed = allowed[:RETESTS[tranche]]
    if not tasks or set(tasks) - set(allowed):
        raise SystemExit(f"{tranche} {kind} takes tasks among {allowed}, not {sorted(set(tasks) - set(allowed))}")
    return {row["id"]: row["commit"] for row in task_rows(study)}


def load_arms(study):
    """arms.json with every model one of the two exact IDs, effort medium and at most three calls."""
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


def require_free(study, path):
    path.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(path).free
    if free < study.min_free:
        raise SystemExit(f"stop: {free / 1e9:.1f} GB free under {path}, below {study.min_free / 1e9:.0f} GB")


def study_runs(study):
    """study.json of every candidate run the study prepared, in records order."""
    return sorted(study.work.glob("records/*/run-*/study.json"))


def judge_units(study):
    """(task, kind, pool, judge) of every judge unit with a records directory under the pools root."""
    return [(pool.parent.name, pool.name, pool, judge.name)
            for pool in sorted(study.pools.glob("*/*")) for judge in sorted((pool / "records" / "judges").glob("*"))]
