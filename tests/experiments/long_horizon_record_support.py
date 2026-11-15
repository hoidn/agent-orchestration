"""Constructed long-horizon exports (the layout of `experiments/long_horizon_tasks/slot_record.py`) for the tests of
the slot record and of the readout. Nothing here runs an agent, a container or a provider call."""

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
KIT = ROOT / "experiments" / "long_horizon_tasks"


def load_kit(name):
    spec = importlib.util.spec_from_file_location(f"lh_{name}_tested", KIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LADDER = json.loads((KIT / "ladder.json").read_text())
EFFORTS = tuple(LADDER["attempt"]["efforts"])
TASKS = [task["name"] for task in LADDER["tasks"]["list"]]
TOKEN_KINDS = ("input", "output", "cache_read", "cache_write_5m", "cache_write_1h")
LABEL, OLD = "a" * 64, "b" * 64
TERM = "<a frozen term>"
TERM_SHA256 = hashlib.sha256(TERM.encode()).hexdigest()
STAND_IN_VALUES = {"readout.contamination_scan.terms": [TERM],
                   "readout.contamination_scan.canary_sha256": "c" * 64,
                   "readout.graded_outcome.verifiers": {TASKS[0]: "passed and total sub-tests"},
                   "readout.fall_bound.seed": 20261114}
STANDINS = {p["field"]: STAND_IN_VALUES[p["field"]] for p in LADDER["pending"] if p["field"].startswith("readout.")}
CEILING = {"by": "ceiling", "cause": None}


def with_values(ladder, values):
    """A copy of the criterion with each dotted field set to its value."""
    out = copy.deepcopy(ladder)
    for field, value in values.items():
        *path, key = field.split(".")
        target = out
        for part in path:
            target = target[part]
        target[key] = value
    return out


def filled(ladder=LADDER):
    """The criterion as the freeze leaves it: every pending readout field filled with its stand-in."""
    out = with_values(ladder, STANDINS)
    out["pending"] = [p for p in out["pending"] if p["field"] not in STANDINS]
    return out


def start(slot, number, label, reward):
    return {"slot": slot, "start": number, "label": label, "row": 5, "reward": reward, "excluded": None,
            "contamination": [], "usd": 1.0, "minutes": 30.0, "tokens": {kind: 10 for kind in TOKEN_KINDS},
            "graded": None, "egress_refused": {}}


def _outcomes(outcome):
    if outcome == "-":
        return []
    return [{"reward": o} if isinstance(o, int) else o for o in (outcome if isinstance(outcome, list) else [outcome])]


def export(table, *, label=LABEL, end=CEILING, earlier=(), allowance=None, pilot=()):
    """table: {task: {effort: [outcome of round 1, 2, ...]}}. An outcome is 0 or 1 (an observation ending normally),
    "-" (a slot not started), a dict of start fields, or a list of such dicts (one slot's starts, in order)."""
    slots, starts = [], []
    for task, by_effort in table.items():
        for effort, outcomes in by_effort.items():
            for number, outcome in enumerate(outcomes, 1):
                slot = f"r{number}-{task}-{effort}"
                slots.append({"slot": slot, "task": task, "effort": effort, "round": number,
                              "pilot": (task, effort, number) in pilot})
                for fields in _outcomes(outcome):
                    starts.append(start(slot, len(starts) + 1, label, None) | fields)
    return {"label": label, "earlier_labels": [{"label": old, "ended_by": f"ledger row ending {old[:8]}"}
                                               for old in earlier],
            "end": end, "slots": slots, "starts": starts, "allowance": allowance}


def same(rewards):
    return {effort: list(rewards) for effort in EFFORTS}
