"""The MLE-bench screen readout (plan docs/plans/2026-11-15-mle-bench-family-plan.md, M1, M7 to M9 and Task 6).

From one resource class's launcher exports, its stage one and, if it ran, its stage two (M9), and each attempt's
result file, to the screen's classes of M1 per competition; at the placement, the ladder's pooled label with the
count and the exact 90 and 95 percent intervals; and the line's metered usage per calendar day beside each tranche's
settled total. It makes no claim beyond those classes and counts.

Reused from the reviewed ladder kit, loaded by path and unchanged (`experiments/long_horizon_tasks/`):
  slot_record.load     reads and checks an export; decides each start's class and whether it is counted (an
                       observation, not excluded, no contamination hit) and its success (reward 1: here a medal)
  readout._criterion   refuses a final readout while a readout field is pending; a rehearsal takes stand-ins
  readout._listed      every start that enters no count with its reason, flags, cuts, refused connections
  readout._contaminated, readout._recorded, readout.pooled_label, readout.interval (exact Clopper-Pearson,
                       standard library, bisection on the binomial tail)
  readout.compute      the whole placement readout of ladder D6; this module takes its pooled label and counts
  readout.bound        a final readout reads the criterion its label names; on this module's private load its
                       KIT_PATH is the experiments directory, so one manifest binds this family's files and the
                       ladder's (the wrapper's pattern of replaced data names, plan M4)

Inputs per stage: (criterion: the tranche's ladder.json as a dict, export: the path of the launcher's export,
state: the tranche's state root). The state root holds `slots/<start:03d>-<slot>/` per attempt (the launcher's
attempt id) with the trial's `jobs/<job>/<trial>/result.json` and each regrade's
`regrade/<attempt>-regrade-<n>/result.json`, and `passthrough/requests.jsonl`, the passthrough's request log. Only
the export's current label enters a count, as in the ladder (D7.6).

The stages are identified, not assumed: stage one's criterion says `stage.stage` 1, stage two's 2 with the same
`stage.class`, and stage two's `stage.derived_from` names stage one's export label and the SHA-256 of its file;
each stage has its own state root. Stage two is offered to every competition with no medal among stage one's
observations, whatever their number (M9 rule 1).

Classes (screen_class; the coordinator's rulings on fix rounds 1 and 2): computed from observations only, over
both stages together, as soon as no outcome of the open slots could change them; "pending" while a slot that could
change it is open, "incomplete" with the number missing when none is and the count is short, "not screened" when
both stages ended with no observation at all. The readout never reclassifies what the launcher exported: an
observation whose reward no result file gives stays an observation, is listed, and a class that would differ
without such observations is marked. A stop withholds every class the stopped stage would decide; a placement
prints its label only once no outcome of its open slots could change it, and a stopped placement places nothing.

The day (M9): a request counts on the calendar day, in the zone given, on which the passthrough received it (its
request-log row's time); the figure is the passthrough's meter, printed beside the launcher's settled total.
Standard library only, so it runs under `python -I` like the ladder's kit.
"""

import argparse
import datetime
import hashlib
import importlib.util
import itertools
import json
import math
import sys
from collections import Counter
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

EXPERIMENTS = Path(__file__).resolve().parents[1]
LADDER_KIT = EXPERIMENTS / "long_horizon_tasks"
STAGE_SLOTS = 3  # attempts per competition in each stage of the screen (M1)
SCREEN_SLOTS = 2 * STAGE_SLOTS
ABOVE, SURVIVES, UNDECIDED, LOW = "above the band", "survives", "undecided", "excluded low"
NOT_SCREENED, NOT_FUNDED = "not screened", "not screened: the second stage was not funded"
INCOMPLETE, PENDING, WITHHELD = "incomplete", "pending", "withheld: the stage ended in a stop"
IN_THE_BAND, IN_PROGRESS, DECIDED, STOPPED = "observed in the band", "in progress", "decided", "stopped"
REQUIRED = ("reward", "medal", "valid_submission", "above_median")  # the reward file's fields that are always there
OUTCOMES = ("medal", "valid", "above_median", "score", "percentile", "grader_exception")
THRESHOLDS = ("bronze", "silver", "gold", "median")  # the reward file's <name>_threshold fields
GRADER_EXCEPTION_NOTE = ("the benchmark's grader caught an error inside the competition's grade function: the "
                         "verifier's reward stands and is counted as written; a person rules on it")
DAY_RULE = ("metered usage, from the passthrough's request logs: a request counts on the calendar day, in the given "
            "time zone, on which the passthrough received it (its request-log row's time)")
NO_RESULT_REASON = {0: "no result file gives this reward: the launcher records 0 for an observation whose two "
                       "regrades both ended in a verifier timeout (ladder.py `regraded`, regrade case 1)"}
NO_RULE = "no result file gives this reward, and the launcher has no rule that records it without one"
METER_TOLERANCE_USD_PER_START = 0.01  # the ladder's smoke check: the settlement's figures agree within USD 0.01
REHEARSAL_LINE = ("REHEARSAL: stand-in values for the pending readout fields and no label check; nothing here is a "
                  "result")
WARNING = "WARNING"
COLUMNS = ("competition", "stage one", "stage two", "open", "missing", "valid", "valid not scored", "above median",
           "usd", "cuts", "grader exceptions", "rewards without a verifier result", "class", "marks")
RESTS = "the class rests on rewards without a verifier result"
# What Task 6 names and the inputs do not carry (coordinator's note 8): where each would have to come from.
NOT_IN_THE_INPUTS = {
    "installed packages": "dropped from Task 6 (coordinator's ruling on fix round 1): neither the export nor the "
                          "result file lists them; they would be parsed from each attempt's transcript",
    "processes holding the GPU": "the wrapper's once-a-minute record (plan M4, item 7) is Task 5's; its file and form "
                                 "are not yet written",
}


def _ladder(name):
    """A private load of one module of the reviewed ladder kit, by its path (the kit runs under `python -I`)."""
    spec = importlib.util.spec_from_file_location(f"mle_lh_{name}", LADDER_KIT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ladder = _ladder("readout")
ladder.KIT_PATH = "experiments"  # bound() keys each file as f"{KIT_PATH}/{name}": here, from the experiments directory
slot_record = ladder.slot_record  # the one loaded by the ladder's readout, so that its RecordError is one class
interval = ladder.interval


class ReadoutError(ValueError):
    """A rule or an input the readout refuses: `code` names the rule, `where` the file or row when there is one."""

    def __init__(self, code, message, where=None):
        super().__init__(f"{code}: {message}" + (f" ({where})" if where else ""))
        self.code, self.where = code, where


# ---- the result file that gave an attempt's reward ----------------------------------------------------------------

def outcomes(rewards):
    """The graded outcomes of the reward file the verifier writes (Task 2): the one place that knows its fields.
    score and percentile are absent when the grader gave no finite score, a valid submission included;
    grader_exception, absent from files written before it was added, reads as 0; a threshold the grader gave none
    for is absent and is not recorded (None)."""
    missing = [name for name in REQUIRED if name not in rewards]
    if missing:
        raise ReadoutError("reward-field", f"the reward file lacks {missing}")
    if rewards["reward"] != int(rewards["medal"] > 0):
        raise ReadoutError("reward-medal", f"reward {rewards['reward']} with medal {rewards['medal']}: the reward is 1 "
                                           "for any medal and 0 for none")
    return {"medal": int(rewards["medal"]), "valid": int(rewards["valid_submission"]),
            "above_median": int(rewards["above_median"]), "score": rewards.get("score"),
            "percentile": rewards.get("percentile"), "grader_exception": int(rewards.get("grader_exception", 0)),
            "thresholds": {name: rewards.get(f"{name}_threshold") for name in THRESHOLDS}}


def _no_outcomes(start):
    """An observation that no result file backs: nothing graded, and the reason the reward stands as exported."""
    return dict.fromkeys(OUTCOMES) | {"thresholds": dict.fromkeys(THRESHOLDS),
                                      "reason": NO_RESULT_REASON.get(start["reward"], NO_RULE)}


def _rewards(path):
    """The reward file's fields as the harness put them in a result.json, or None."""
    if not path.is_file():
        return None
    return ((slot_record.read(path).get("verifier_result") or {}).get("rewards")) or None


def reward_source(state, start):
    """(rewards, source) of the result that gave the start's reward: the first regrade that gave one (the launcher
    stops at it), else the trial's own; (None, None) when none gave one."""
    attempt = state / "slots" / f"{start['start']:03d}-{start['slot']}"
    if not attempt.is_dir():
        raise ReadoutError("no-attempt-directory", f"start {start['start']}: no directory {attempt.name}", state)
    for n in (1, 2):
        rewards = _rewards(attempt / "regrade" / f"{attempt.name}-regrade-{n}" / "result.json")
        if rewards and rewards.get("reward") is not None:
            return rewards, f"regrade {n}"
    trials = sorted(p for p in (attempt / "jobs").glob("*/*") if p.is_dir())
    rewards = _rewards(trials[0] / "result.json") if trials else None
    return (rewards, "trial") if rewards and rewards.get("reward") is not None else (None, None)


def _attempt(start, state):
    """One observation with its graded outcomes; refused when the result file's reward is not the exported one."""
    rewards, source = reward_source(state, start)
    graded = outcomes(rewards) if rewards else _no_outcomes(start)
    if rewards is not None and rewards["reward"] != start["reward"]:
        raise ReadoutError("reward-mismatch", f"start {start['start']}: the {source}'s result gives reward "
                                              f"{rewards['reward']}, the export {start['reward']}")
    return {"start": start["start"], "slot": start["slot"], "reward": start["reward"], "source": source,
            "ending": start["ending"], "flagged": start["flagged"], "usd": start["usd"],
            "minutes": start["minutes"]} | graded


# ---- one stage --------------------------------------------------------------------------------------------------

def _refused(starts):
    """{address: count} of the refused connections over the starts given."""
    counts = {}
    for start in starts:
        for address, n in start["egress_refused"].items():
            counts[address] = counts.get(address, 0) + n
    return dict(sorted(counts.items()))


def _graded(attempts):
    """The counts of the graded outcomes over a stage's observations; an outcome not recorded counts in none."""
    return {"valid": sum(a["valid"] == 1 for a in attempts), "invalid": sum(a["valid"] == 0 for a in attempts),
            "valid_not_scored": sum(a["valid"] == 1 and a["score"] is None for a in attempts),
            "above_median": sum(a["above_median"] == 1 for a in attempts),
            "grader_exception": sum(a["grader_exception"] == 1 for a in attempts),
            "grader_exceptions": [a | {"note": GRADER_EXCEPTION_NOTE} for a in attempts if a["grader_exception"] == 1]}


def _unbacked(attempts):
    """The observations whose reward no result file gives: listed, with the launcher's reason, for a ruling."""
    listed = [a for a in attempts if a["source"] is None]
    return {"reward_without_result": len(listed), "rewards_without_result": listed,
            "medals_without_result": sum(a["reward"] == 1 for a in listed)}


def _spent(own, observed, classes):
    """Cost of every start that counts as one (cuts and failures included), minutes over observations, cuts."""
    minutes, left = ladder._recorded([s["minutes"] for s in observed])
    return {"usd": sum(s["usd"] for s in own if classes[s["class"]]["starts"]), "mean_minutes": minutes,
            "minutes_not_recorded": left, "cuts": sum(s["class"] == "cut" for s in own)}


def _competition(name, current, listed, state, classes):
    """A competition's figures in one stage: its observations, medals and graded outcomes, cost, minutes, cuts,
    flags and refused connections, and every start that entered no count with its reason."""
    own = [s for s in current if s["task"] == name]
    observed = [s for s in own if s["counted"]]
    attempts = [_attempt(s, state) for s in observed]
    return {"observations": len(observed), "medals": sum(s["success"] for s in observed), "attempts": attempts,
            "flagged": sum(s["flagged"] for s in observed), "egress_refused": _refused(own),
            "not_counted": [e for e in listed["exclusions"] if e["task"] == name]} | _graded(attempts) | _spent(
                own, observed, classes) | _unbacked(attempts)


def open_slots(export, starts):
    """The schedule's slots whose outcome is still to come: no start of the slot is final (a cut and a pre-session
    failure are run again, D5; a slot is lost after its third pre-session failure), and the tranche is still running
    or an attempt of the slot is still open. {slot id: (task, effort)}."""
    by_slot = {}
    for start in starts:
        by_slot.setdefault(start["slot"], []).append(start["class"])
    in_flight, running = {entry["slot"] for entry in export["open"]}, export["end"] is None

    def final(slot):
        classes = by_slot.get(slot, [])
        return any(c not in slot_record.AGAIN_AFTER for c in classes) or classes.count("pre_session_failure") >= 3

    return {s["slot"]: (s["task"], s["effort"]) for s in export["slots"]
            if not final(s["slot"]) and (running or s["slot"] in in_flight)}


def _inputs(given, standins):
    """A stage's criterion (pending fields refused or stood in for), export, its file's SHA-256 and state root."""
    criterion, path, state = given
    criterion, rehearsal = ladder._criterion(criterion, standins)
    efforts = criterion["attempt"]["efforts"]
    if len(efforts) != 1:
        raise ReadoutError("effort", f"a stage of the screen runs at one effort; this criterion has {efforts}")
    if criterion["schedule"]["rounds"] != STAGE_SLOTS:
        raise ReadoutError("rounds", f"a stage of the screen has {STAGE_SLOTS} rounds; this criterion has "
                                     f"{criterion['schedule']['rounds']}")
    raw = Path(path).read_bytes()
    export = slot_record.read(Path(path))
    if not export["slots"]:
        raise ReadoutError("empty-stage", "the export schedules no competition", path)
    return {"criterion": criterion, "rehearsal": rehearsal, "export": export, "sha256": hashlib.sha256(raw).hexdigest(),
            "state": Path(state)}


def stage(inputs):
    """One stage's readout: per competition of its schedule, its figures (_competition) and its open slots."""
    criterion, export = inputs["criterion"], inputs["export"]
    starts = slot_record.load(export, criterion)
    current = [s for s in starts if s["label"] == export["label"]]
    listed = ladder._listed(current, criterion["attempt"]["efforts"], criterion) | {
        "contaminated": ladder._contaminated(starts, criterion)}
    scheduled = {slot["task"] for slot in export["slots"]}
    names = [task["name"] for task in criterion["tasks"]["list"] if task["name"] in scheduled]
    classes, waiting = criterion["classification"]["classes"], Counter(t for t, _ in open_slots(export, starts).values())
    return {"rehearsal": inputs["rehearsal"], "label": export["label"], "end": export["end"],
            "open": len(export["open"]), "earlier_label_starts": len(starts) - len(current), "listed": listed,
            "settled_usd": sum(s["usd"] for s in starts), "starts": len(starts),
            "competitions": {n: _competition(n, current, listed, inputs["state"], classes) | {"open": waiting[n]}
                             for n in names}}


def _stopped(result):
    """Whether a stage's tranche ended in a stop."""
    return result["end"] is not None and result["end"]["by"] == "stop"


# ---- the stages are identified, not assumed (coordinator's ruling 2 on fix round 2) --------------------------------

def _stage_number(inputs):
    return (inputs["criterion"].get("stage") or {}).get("stage")


def identify(one, two):
    """Refused unless stage one's criterion is a stage one, and stage two's a stage two of the same class derived
    from stage one's export (its label and its file's SHA-256), in a state root of its own."""
    if _stage_number(one) != 1:
        raise ReadoutError("stage-number", f"the first stage's criterion says stage {_stage_number(one)}, not 1")
    if two is None:
        return
    if _stage_number(two) != 2:
        raise ReadoutError("stage-number", f"the second stage's criterion says stage {_stage_number(two)}, not 2")
    if two["criterion"]["stage"]["class"] != one["criterion"]["stage"]["class"]:
        raise ReadoutError("stage-class", "the two stages' criteria name different resource classes")
    derived = two["criterion"]["stage"].get("derived_from") or {}
    if (derived.get("export_label"), derived.get("export_sha256")) != (one["export"]["label"], one["sha256"]):
        raise ReadoutError("derived-from", "stage two's criterion is not derived from this stage one's export")
    if one["state"].resolve() == two["state"].resolve():
        raise ReadoutError("same-state", "the two stages are given one state root")


def _settled(stage_inputs):
    """Whether a stage's tranche has ended, not in a stop, with no attempt open: what stage two is derived from."""
    export = stage_inputs["export"]
    return export["end"] is not None and export["end"]["by"] != "stop" and not export["open"]


def _check_stage_two(one, two):
    """Stage two follows stage one's settled end and holds only competitions of stage one with no medal (M9 rule 1)."""
    for name in two["competitions"]:
        figures = one["competitions"].get(name)
        if figures is None:
            raise ReadoutError("stage-two-unknown", f"stage two holds {name}, which stage one did not schedule")
        if figures["medals"]:
            raise ReadoutError("stage-two-medal", f"stage two holds {name}, which has a medal in stage one: it "
                                                  "should never have been funded")


# ---- the screen's classes (M1; the coordinator's rulings on fix rounds 1 and 2) ----------------------------------

def _by_stage_one(medals, observations, waiting):
    """The class of a competition with a medal in stage one, which stage two never holds."""
    if medals < observations:
        return SURVIVES, 0
    if observations == STAGE_SLOTS:
        return ABOVE, 0
    return (PENDING, None) if waiting else (INCOMPLETE, STAGE_SLOTS - observations)


def screen_class(one, two, funded):
    """(class, missing) of M1 over both stages. one and two are (medals, observations, open slots) of a stage; two is
    None when stage two holds no slot of the competition; funded is False when stage two did not fund it, None while
    that is not yet known. A class as soon as no outcome of the open slots could change it: in stage one, a medal
    beside a non-medal survives and three of three is above the band; a stage one with no medal goes to stage two;
    there, any medal survives at once and no medal in six observations is excluded low. Otherwise "pending" while a
    slot is open, else "incomplete" with the number missing ("not screened" with no observation at all)."""
    medals, observed, waiting = one
    if medals:
        return _by_stage_one(medals, observed, waiting)
    if waiting:
        return PENDING, None
    if two is None:
        return (NOT_FUNDED, SCREEN_SLOTS - observed) if funded is False else (UNDECIDED, None)
    medals_two, observed_two, waiting_two = two
    total = observed + observed_two
    if medals_two:
        return SURVIVES, 0
    if total >= SCREEN_SLOTS:
        return LOW, 0
    if waiting_two:
        return PENDING, None
    return (NOT_SCREENED if total == 0 else INCOMPLETE), SCREEN_SLOTS - total


def _counts(stage_result, name, backed=False):
    """(medals, observations, open slots) of a competition in a stage; backed leaves out the observations no result
    file backs."""
    figures = stage_result["competitions"][name]
    less = (figures["medals_without_result"], figures["reward_without_result"]) if backed else (0, 0)
    return figures["medals"] - less[0], figures["observations"] - less[1], figures["open"]


def _class_of(one, two, name, funded, backed):
    """The competition's (class, missing), withheld when a stage that decides it ended in a stop."""
    if _stopped(one) or (two is not None and _stopped(two)):
        return WITHHELD, None
    return screen_class(_counts(one, name, backed), _counts(two, name, backed) if two else None, funded)


def _screen(one, two, no_stage_two):
    """Per competition of stage one: its class, its counts over both stages, what is missing and what is open."""
    screened = {}
    for name in one["competitions"]:
        in_two = two is not None and name in two["competitions"]
        funded = in_two if two is not None else (False if no_stage_two else None)
        held = two if in_two else None
        cls, missing = _class_of(one, held, name, funded, False)
        backed, _ = _class_of(one, held, name, funded, True)
        stages = [one] + ([two] if in_two else [])
        screened[name] = {"class": cls, "missing": missing, "rests_on_rewards_without_result": backed != cls,
                          **{key: sum(s["competitions"][name][key] for s in stages)
                             for key in ("observations", "medals", "open")}}
    return screened


# ---- the placement (ladder D6) ----------------------------------------------------------------------------------

def _kind(label):
    """A pooled label with its counts left out, so that two outcomes compare by their class."""
    return NOT_SCREENED if label.startswith(NOT_SCREENED) else label


def decided(cells, waiting, rule):
    """Whether no outcome of the open slots could change the pooled label: cells {effort: (k, n)}, waiting {effort:
    open slots}; each open slot may end as a success, a failure or no observation at all."""
    options = [[(k + s, n + a) for a in range(waiting.get(e, 0) + 1) for s in range(a + 1)]
               for e, (k, n) in cells.items()]
    labels = {_kind(ladder.pooled_label(dict(zip(cells, combo)), rule)) for combo in itertools.product(*options)}
    return len(labels) == 1


def _placed(task, waiting, rule, stop):
    """One placed competition's label and status: none after a stop, the ladder's once decided, else in progress."""
    cells = {e: (c["k"], c["n"]) for e, c in task["cells"].items()}
    if stop:
        return {"status": STOPPED, "label": None}
    if not decided(cells, waiting, rule):
        return {"status": IN_PROGRESS, "label": None}
    return {"status": DECIDED, "label": task["pooled"]["label"]}


def place(given, screened, standins=None):
    """The ladder's placement readout of the fresh attempts alone; the screen's counts printed beside, never pooled
    (M1). A label only once no outcome of the open slots could change it; a stopped placement places nothing."""
    criterion, path, _ = given
    export = slot_record.read(Path(path))
    result = ladder.compute(criterion, export, standins)
    starts = slot_record.load(export, ladder._criterion(criterion, standins)[0])
    waiting = Counter(open_slots(export, starts).values())
    placed = {}
    for name, task in result["tasks"].items():
        if screened.get(name, {}).get("class") != SURVIVES:
            raise ReadoutError("not-survivor", f"{name} is in the placement but did not survive the screen")
        pooled, own = task["pooled"], {e: waiting[(name, e)] for e in task["cells"]}
        status = _placed(task, own, criterion["readout"]["pooled"], result["stop"])
        placed[name] = {"K": pooled["K"], "n": pooled["n"], "open": sum(own.values()), **status,
                        "reported_as": IN_THE_BAND if status["label"] == "screened in" else status["label"],
                        "interval_90": interval(pooled["K"], pooled["n"], 0.90),
                        "interval_95": interval(pooled["K"], pooled["n"], 0.95),
                        "cells": {e: {"k": c["k"], "n": c["n"]} for e, c in task["cells"].items()},
                        "screen": {key: screened[name][key] for key in ("observations", "medals")}}
    return {"rehearsal": result["rehearsal"], "label": result["label"], "end": result["end"], "open": result["open"],
            "settled_usd": sum(s["usd"] for s in starts), "starts": len(starts), "competitions": placed}


# ---- metered usage per calendar day (M9, "The day") -------------------------------------------------------------

def _finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _row(line, where):
    """(time, usd or None) of one request-log row; a refusal (no usd) has no price. Refused when it is not a JSON
    object with a finite time and, if priced, a finite usd at or above 0."""
    try:
        row = json.loads(line, object_pairs_hook=slot_record._unique, parse_constant=slot_record._no_constant)
    except ValueError as error:
        raise ReadoutError("request-log", f"not a JSON row: {error}", where) from None
    if not isinstance(row, dict) or not _finite(row.get("time")):
        raise ReadoutError("request-log", "a row is an object with a finite time", where)
    usd = row.get("usd")
    if usd is not None and not (_finite(usd) and usd >= 0):
        raise ReadoutError("request-log", f"usd {usd!r} is not a finite number at or above 0", where)
    return row["time"], usd


def _priced(state):
    """[(time, usd)] of every priced request in a stage's request log."""
    log = Path(state) / "passthrough" / "requests.jsonl"
    if not log.is_file():
        raise ReadoutError("request-log", "no request log: the day's usage cannot be read", log)
    rows = [_row(line, f"{log}:{n}") for n, line in enumerate(log.read_text().splitlines(), 1) if line.strip()]
    return [(time, usd) for time, usd in rows if usd is not None]


def per_day(states, zone):
    """{date: metered USD} over every priced request of the stages' logs, each on the calendar day in the given zone
    on which the passthrough received it."""
    days = {}
    for time, usd in (row for state in states for row in _priced(state)):
        day = datetime.datetime.fromtimestamp(time, zone).date().isoformat()
        days[day] = days.get(day, 0.0) + usd
    return {day: round(usd, 6) for day, usd in sorted(days.items())}


def meter(state, settled_usd, starts):
    """A tranche's metered total beside the launcher's settled total; a difference above the tolerance (USD 0.01 a
    start, the ladder's smoke check) is a warning, not a refusal: the settlement takes the largest of its figures,
    or a start's whole reservation when one cannot be read (ladder D4)."""
    metered = round(sum(usd for _, usd in _priced(state)), 6)
    difference, tolerance = round(metered - settled_usd, 6), round(METER_TOLERANCE_USD_PER_START * starts, 6)
    return {"metered_usd": metered, "settled_usd": round(settled_usd, 6), "difference_usd": difference,
            "tolerance_usd": tolerance, "warning": abs(difference) > tolerance}


# ---- the readout ------------------------------------------------------------------------------------------------

def _stop(one, two, placed):
    """The first stage, in order, that ended in a stop, with its cause; None when none did."""
    for name, result in (("one", one), ("two", two), ("placement", placed)):
        if result is not None and _stopped(result):
            return {"stage": name, "cause": result["end"]["cause"]}
    return None


def _check_order(one_inputs, two_inputs, no_stage_two):
    """Stage two, or the word that there is none, only after stage one has settled."""
    if two_inputs is not None and no_stage_two:
        raise ReadoutError("both-stage-two", "a stage-two export and 'no stage two' exclude each other")
    if two_inputs is not None and not _settled(one_inputs):
        raise ReadoutError("stage-two-early", "stage two is read only after stage one has ended, not in a stop, with "
                                              "no attempt open")
    if no_stage_two and not _settled(one_inputs):
        raise ReadoutError("no-stage-two-early", "'no stage two' is said only after stage one has settled")


def compute(stage_one, stage_two=None, *, no_stage_two=False, placement=None, time_zone, standins=None):
    """The readout of one resource class. Each stage is (criterion, export path, state root); no_stage_two says
    stage two was not funded at all (M9: k is zero). time_zone is the machine's zone, in which a request's day is
    read."""
    one_inputs = _inputs(stage_one, standins)
    two_inputs = _inputs(stage_two, standins) if stage_two is not None else None
    identify(one_inputs, two_inputs)
    _check_order(one_inputs, two_inputs, no_stage_two)
    one = stage(one_inputs)
    two = stage(two_inputs) if two_inputs is not None else None
    if two is not None:
        _check_stage_two(one, two)
    screened = _screen(one, two, no_stage_two)
    placed = None if placement is None else place(placement, screened, standins)
    given = {"one": (stage_one, one), "two": (stage_two, two), "placement": (placement, placed)}
    return {"rehearsal": any(r["rehearsal"] for r in (one, two, placed) if r), "stop": _stop(one, two, placed),
            "stages": {"one": _summary(one), "two": _summary(two)}, "no_stage_two": no_stage_two,
            "competitions": _joined(screened, one, two), "placement": placed,
            "per_day_usd": per_day([g[2] for g, _ in given.values() if g], time_zone), "time_zone": str(time_zone),
            "meter": {k: meter(g[2], r["settled_usd"], r["starts"]) for k, (g, r) in given.items() if g},
            "day_rule": DAY_RULE, "not_in_the_inputs": NOT_IN_THE_INPUTS}


def _summary(result):
    """A stage's own fields for the document, or None."""
    return result and {key: result[key] for key in ("label", "end", "open", "earlier_label_starts", "listed")}


def _joined(screened, one, two):
    """Per competition: its screen class and counts, beside each stage's own figures."""
    second = two["competitions"] if two else {}
    return {name: {"screen": screened[name], "stage_one": one["competitions"][name], "stage_two": second.get(name)}
            for name in screened}


# ---- the table --------------------------------------------------------------------------------------------------

def _cell(figures):
    """A stage's medals of its observations, or "-" when the stage holds no slot of the competition."""
    return "-" if figures is None else f"{figures['medals']} of {figures['observations']}"


def _row_cells(name, c):
    """A competition's row, one cell per column of COLUMNS."""
    stages = [s for s in (c["stage_one"], c["stage_two"]) if s]
    total = {key: sum(s[key] for s in stages) for key in ("valid", "valid_not_scored", "above_median", "usd", "cuts",
                                                           "grader_exception", "reward_without_result")}
    screen = c["screen"]
    return [f"{name:<12}", _cell(c["stage_one"]), _cell(c["stage_two"]), str(screen["open"]),
            "-" if screen["missing"] is None else str(screen["missing"]), str(total["valid"]),
            str(total["valid_not_scored"]), str(total["above_median"]), f"{total['usd']:.2f}", str(total["cuts"]),
            str(total["grader_exception"]), str(total["reward_without_result"]), screen["class"],
            RESTS if screen["rests_on_rewards_without_result"] else ""]


def _figure(value):
    """A recorded number, or "not recorded"."""
    return "not recorded" if value is None else f"{value:g}"


def _scores(name, c):
    """One line per observation: its score against the thresholds the reward file gives. Start numbers repeat from
    tranche to tranche, so each line names its stage."""
    attempts = [(stage, a) for stage in ("one", "two") if c[f"stage_{stage}"] for a in c[f"stage_{stage}"]["attempts"]]
    return [" | ".join([f"  stage {stage} start {a['start']}", name,
                        f"score {'none' if a['score'] is None else _figure(a['score'])}",
                        *(f"{key} {_figure(value)}" for key, value in a["thresholds"].items())])
            for stage, a in attempts]


def _placement_line(name, p):
    """A placed competition: its count, both intervals, its status and, once decided, its label as reported."""
    low, high = (f"{100 * x:.1f}" for x in p["interval_90"])
    low95, high95 = (f"{100 * x:.1f}" for x in p["interval_95"])
    return (f"placement {name} | {p['K']} of {p['n']} | 90% {low}-{high} | 95% {low95}-{high95} | {p['status']} | "
            f"{p['reported_as'] or '-'} | open {p['open']}")


def _money_lines(result):
    """The per-day metered figures, each tranche's metered and settled totals, and a warning line per difference."""
    lines = [f"day {day} | metered USD {usd:.2f} | {result['time_zone']}" for day, usd in result["per_day_usd"].items()]
    for name, m in result["meter"].items():
        lines.append(f"meter {name} | metered {m['metered_usd']:.2f} | settled {m['settled_usd']:.2f} | difference "
                     f"{m['difference_usd']:.2f} | tolerance {m['tolerance_usd']:.2f}")
        lines += [f"{WARNING} | meter {name} | the metered figure differs from the settled total by "
                  f"{m['difference_usd']:.2f}, above the tolerance"] * m["warning"]
    return lines


def table(result):
    """The short plain-text table, from compute's result alone; a rehearsal's first and last lines say so."""
    lines = [" | ".join(COLUMNS)]
    for name, c in result["competitions"].items():
        lines += [" | ".join(_row_cells(name, c)).rstrip(" |"), *_scores(name, c)]
    lines += [_placement_line(n, p) for n, p in ((result["placement"] or {}).get("competitions") or {}).items()]
    lines += _money_lines(result)
    stop = result["stop"]
    lines += [f"stopped in stage {stop['stage']}: {stop['cause']}"] if stop else []
    banner = [REHEARSAL_LINE] if result["rehearsal"] else []
    return "\n".join(banner + lines + banner) + "\n"


def document(result):
    """The JSON document: sorted keys, so the same inputs give the same bytes."""
    return json.dumps(result, indent=1, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n"


# ---- the command ------------------------------------------------------------------------------------------------

def bound(criterion_path, manifest_path, label, root=EXPERIMENTS.parent):
    """A final readout reads the criterion its label names: the ladder's own bound() (the manifest frozen, its
    SHA-256 the label, each file the readout reads recorded in it as it is) over the tranche's criterion, this module
    and the two ladder modules it loads, keyed by their paths from the repository root (Task 4's manifests follow the
    ladder's format). None, or a ReadoutError "label-binding" naming what does not hold."""
    try:
        criterion = Path(criterion_path).resolve().relative_to((Path(root) / "experiments").resolve())
        files = {criterion.as_posix(): Path(criterion_path).read_bytes(),
                 "mle_bench_tasks/screen_readout.py": Path(__file__).read_bytes()} | {
            f"long_horizon_tasks/{name}": (LADDER_KIT / name).read_bytes() for name in ("readout.py", "slot_record.py")}
        ladder.bound(files, Path(manifest_path).read_bytes(), label)
    except (ValueError, ladder.ReadoutError) as error:
        raise ReadoutError("label-binding", str(error), criterion_path) from None


def _given(paths, final):
    """A stage's (criterion, export path, state root) from its four paths; in a final readout, bound to its label."""
    if paths is None:
        return None
    export, state, criterion, manifest = (Path(p) for p in paths)
    if final:
        bound(criterion, manifest, slot_record.read(export)["label"])
    return slot_record.read(criterion), export, state


def _zone(name):
    """The IANA zone of that name, or a ReadoutError."""
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as error:
        raise ReadoutError("time-zone", f"no IANA time zone {name!r}: {error}") from None


def main(argv):
    """The command: prints the table; with --json, writes the document; exit 2 with the reason on a refusal."""
    parser = argparse.ArgumentParser(description="The MLE-bench screen readout (plan M1, Task 6): prints a short "
                                     "table; with --json, writes the readout as one JSON document.")
    stage_args = {"nargs": 4, "metavar": ("EXPORT", "STATE", "CRITERION", "MANIFEST")}
    parser.add_argument("--stage-one", required=True, **stage_args,
                        help="stage one's export, state root, ladder.json and manifests/<tranche>.json")
    two = parser.add_mutually_exclusive_group()
    two.add_argument("--stage-two", **stage_args, help="stage two's four paths, as for --stage-one")
    two.add_argument("--no-stage-two", action="store_true", help="stage two was not funded (M9: k is zero)")
    parser.add_argument("--placement", **stage_args, help="the placement's four paths, as for --stage-one")
    parser.add_argument("--time-zone", required=True, help="this machine's IANA time zone, e.g. America/Los_Angeles")
    parser.add_argument("--rehearsal", metavar="STAND_INS", help="stand-ins for the pending readout fields")
    parser.add_argument("--json", metavar="PATH", help="where to write the JSON document")
    args = parser.parse_args(argv)
    try:
        final = args.rehearsal is None  # a rehearsal reads unfrozen criteria, as the ladder's does
        result = compute(_given(args.stage_one, final), _given(args.stage_two, final), no_stage_two=args.no_stage_two,
                         placement=_given(args.placement, final), time_zone=_zone(args.time_zone),
                         standins=slot_record.read(Path(args.rehearsal)) if args.rehearsal else None)
    except (ReadoutError, ladder.ReadoutError, slot_record.RecordError, OSError) as error:
        print(f"screen_readout.py: {error}", file=sys.stderr)
        return 2
    print(table(result), end="")
    if args.json:
        Path(args.json).write_text(document(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
