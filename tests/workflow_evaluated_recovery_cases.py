"""Scenario and case tables of the public recovery campaign.

Every scenario is one the integrated consumer harness (`test_workflow_evaluated_consumers`)
keeps: the three core programs (std/improve REVISE→revision→APPROVE→launch, the reviewed
change implement→REQUEST_CHANGES→revision→APPROVE, serial best-of-N) and each further
branch it runs. Variants that differ there only by where a run is paused (improve approved
after the review or after the revision, best-of-N after either candidate) are the core plan
itself; the window product already kills each of their effects. Each scenario lists the
activation identities an uninterrupted public run reaches, in journal order, as the census
verifies them, and the stand-in answer of each provider effect in the same order.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from tests.test_workflow_evaluated_consumers import (
    APPROVE_2, BEST_OF_N, CHANGE, NEEDS_HUMAN, QUESTION_FOR_HUMAN, READY, REDO, REPAIR, REPAIR_OUTPUT, REVISED,
    SELECTION, WATCH_CASES, _changes, _improve_plan, _review, _watch_inputs,
)
from tests.test_workflow_lisp_improve_example_e2e import QUESTION
from tests.workflow_evaluated_consumer_sources import CANDIDATES, sha256
from tests.workflow_evaluated_recovery_helpers import WINDOWS, current_source, digest


IMPROVE = "workflow:improve_experiment_proposal::run-experiment"
STD = (IMPROVE + " / result=procedure:std/improve::improve"
       "[7eaa3bc62fe4dc0150d1ba45bf073096c79f3f6259b001f8769d1fccefa68ed5] / loop:state")
REVIEW = "decision=procedure:improve_experiment_proposal::review-proposal / #1"
REVISE = "REVISE / next=procedure:improve_experiment_proposal::revise-proposal / #1"
REVIEWED = "workflow:reviewed_change::reviewed-change"
BEST = "workflow:best_of_n::best-of-n"
CODER = " / else / #1=workflow:best_of_n::implement-one / change"
WATCHDOG = "workflow:generic_run_watchdog/watchdog::watchdog"
PUBLISH = (" / published=procedure:generic_run_watchdog/watchdog::publish-repair-outcome"
           "[44eb081577915604e4a20f467003c4a3bfbaf024b58e07f90e0308de6f467f73]")
REPAIRING = " / outcome / body / then / repair-result=workflow:generic_run_watchdog/watchdog::invoke-repair / result / body"
CHANGE_INPUTS = {"task": "Fix add in repo/calc.py so that it returns the sum.", "intent": "add returns a + b",
                 "repo": "repo"}


@dataclass(frozen=True)
class Scenario:
    program: str  # `PROGRAMS` key
    inputs: dict
    effects: tuple[tuple[str, str], ...]  # (activation identity, effect class) in journal order
    answers: tuple[dict, ...]  # the stand-in answer of each provider effect, in journal order
    value: dict
    watch: str | None = None  # `WATCH_CASES` key: inputs name a per-worker target workspace


def _improve(rounds: int, *tail: tuple[str, str]) -> tuple[tuple[str, str], ...]:
    """Review then revision per REVISE round, the final review, then `tail`."""
    effects = [(f"{STD}[{index}] / {REVIEW}", "provider") for index in range(1, rounds + 1)]
    revisions = [(f"{STD}[{index}] / {REVISE}", "provider") for index in range(1, rounds + 1)]
    ordered = [effect for pair in zip(effects, revisions) for effect in pair]
    return (*ordered, *tail)


def _launch(branch: str, execute: str) -> tuple[str, str]:
    """The launcher command under `branch`, inside the `execute` activation of that branch."""
    return f"{IMPROVE} / {branch} / #1=procedure:improve_experiment_proposal::execute[{execute}] / #1", "command"


def _reviewed(*steps: str) -> tuple[tuple[str, str], ...]:
    return tuple((f"{REVIEWED} / {step}", "provider") for step in steps)


def _watchdog(branch: str | None) -> tuple[tuple[str, str], ...]:
    """Watch, the repair provider on the codex (`then`) or claude (`else`) branch, then publish."""
    repair = ((f"{WATCHDOG}{REPAIRING} / {branch} / #1", "provider"),) if branch else ()
    outcome = "REPAIR" if branch else "NO_ACTION"
    return ((f"{WATCHDOG} / watch", "command"), *repair, (f"{WATCHDOG}{PUBLISH} / {outcome} / #1", "command"))


CORE = {
    "improve": Scenario(
        "improve", {"question": QUESTION},
        _improve(1, (f"{STD}[2] / {REVIEW}", "provider"),
                 _launch("APPROVED", "dacbeb4ede643446acfe00218cbed1ed687a166e5b333d05e86e7c302ef96c7b")),
        tuple(_improve_plan("REVISE", "APPROVE")["codex"]), {"status": "launched"}),
    "reviewed_change": Scenario(
        "reviewed_change", CHANGE_INPUTS,
        _reviewed("change", "loop:state[1] / review", "loop:state[1] / REQUEST_CHANGES / else / revision",
                  "loop:state[2] / review"),
        (CHANGE, _changes(1), REVISED, APPROVE_2), READY),
    "best_of_n": Scenario(
        "best_of_n", {"task": "Fix add in calc.py so that it returns the sum.", "intent": "add returns a + b",
                      "repos": list(CANDIDATES)},
        ((f"{BEST} / accounts / body / loop:#1[1]{CODER}", "provider"),
         (f"{BEST} / accounts / body / loop:#1[2]{CODER}", "provider"), (f"{BEST} / selection", "provider")),
        (*BEST_OF_N["claude"], *BEST_OF_N["codex"]), SELECTION),
}
BRANCHES = {
    "improve-blocked": Scenario(
        "improve", {"question": QUESTION},
        _improve(1, (f"{STD}[2] / {REVIEW}", "provider"),
                 _launch("BLOCKED", "8dc20ff144c9d0c1bd3fe7c460a4ecdf532af78df29fec80d13e4baef9122a30")),
        tuple(_improve_plan("REVISE", "BLOCKED")["codex"]), {"status": "held"}),
    "improve-exhausted": Scenario(
        "improve", {"question": QUESTION},
        _improve(3, _launch("EXHAUSTED", "60c14eca61031b22ef442066622361a11d0ed72962f52e3e5742d77cec491a8d")),
        tuple(_improve_plan("REVISE", "REVISE", "REVISE")["codex"]), {"status": "held"}),
    "reviewed_change-wrong-approach": Scenario(
        "reviewed_change", CHANGE_INPUTS,
        _reviewed("change", "loop:state[1] / review", "loop:state[1] / WRONG_APPROACH / else / redo",
                  "loop:state[2] / review"),
        (CHANGE, _review("WRONG_APPROACH", 1, reason="patch the caller"), REDO, APPROVE_2),
        READY),
    "reviewed_change-needs-human": Scenario(
        "reviewed_change", CHANGE_INPUTS, _reviewed("change", "loop:state[1] / review"), (CHANGE, NEEDS_HUMAN),
        {"variant": "ESCALATED", "question": QUESTION_FOR_HUMAN}),
    "reviewed_change-unresolved": Scenario(
        "reviewed_change", CHANGE_INPUTS,
        _reviewed("change", *(f"loop:state[{index}] / {step}" for index in (1, 2)
                              for step in ("review", "REQUEST_CHANGES / else / revision")), "loop:state[3] / review"),
        (CHANGE, _changes(1), REVISED, _changes(2), REVISED, _changes(3)),
        {"variant": "UNRESOLVED", "reason": "round 3: no test", "rounds": 3}),
    "watchdog-no-action": Scenario(
        "watchdog", {}, _watchdog(None), (),
        {"watch_status": "RUNNING_OK", "repair_status": "NO_ACTION", "recovery_action": "NONE",
         "watchdog_result_path": "state/watchdog/watchdog-result.json"}, watch="no-action"),
    "watchdog-codex-repair": Scenario("watchdog", {}, _watchdog("then"), (REPAIR,), REPAIR_OUTPUT, watch="codex-repair"),
    "watchdog-claude-repair": Scenario("watchdog", {}, _watchdog("else"), (REPAIR,), REPAIR_OUTPUT,
                                       watch="claude-repair"),
}
SCENARIOS = {**CORE, **BRANCHES}
_WATCH_INPUTS: dict[str, dict] = {}


def scenario_inputs(factory, name: str) -> dict:
    """The scenario's inputs; a watchdog's target workspace is made once per worker, so its
    absolute path (an argv operand and a recorded value) is the same in baseline and cells."""
    scenario = SCENARIOS[name]
    if scenario.watch is None:
        return scenario.inputs
    if name not in _WATCH_INPUTS:
        status, provider = WATCH_CASES[scenario.watch][:2]
        _WATCH_INPUTS[name] = _watch_inputs(Path(factory.getbasetemp()) / f"target-{name}", status, provider)
    return _WATCH_INPUTS[name]


def answers(name: str) -> dict[str, dict]:
    """Site key (`sha256:` of the identity) to stand-in answer, for this scenario's providers."""
    scenario = SCENARIOS[name]
    providers = [identity for identity, kind in scenario.effects if kind == "provider"]
    return {sha256(identity): answer for identity, answer in zip(providers, scenario.answers, strict=True)}


@dataclass(frozen=True)
class Cell:
    """One case-table row: (source hash, scenario, identity, effect ordinal, window)."""

    source_hash: str
    scenario: str
    identity: str
    ordinal: int
    window: str

    @property
    def id(self) -> str:
        return f"{self.scenario}-effect{self.ordinal:02d}-{self.window}"

    @property
    def effect_class(self) -> str:
        return SCENARIOS[self.scenario].effects[self.ordinal - 1][1]

    def gate(self) -> dict:
        return {"window": self.window, "identity": self.identity, "attempt": 1, "digest": digest(self.identity)}


def cells(names) -> list[Cell]:
    return [Cell(sha256(current_source(SCENARIOS[name].program)), name, identity, ordinal, window)
            for name in names
            for ordinal, (identity, _kind) in enumerate(SCENARIOS[name].effects, start=1) for window in WINDOWS]


CELLS = cells(CORE)
BRANCH_CELLS = cells(BRANCHES)
LAUNCH = [cell for cell in CELLS if cell.effect_class == "command"]
assert (len(CELLS), len(set(CELLS)), len(LAUNCH)) == (110, 110, 10)
assert len(set(BRANCH_CELLS)) == len(BRANCH_CELLS) and not {cell.id for cell in CELLS} & {
    cell.id for cell in BRANCH_CELLS}
