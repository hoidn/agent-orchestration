"""The programs of the drafting guide's section on program shapes, run through the public entry.

Guide: docs/lisp_workflow_drafting_guide.md, section "2A. Program Shapes: What Runs Today".
Plan: docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md, Task 5.

Every program is a file of `tests/fixtures/workflow_lisp/guide_shapes/`. Each case runs one
program at one target and asserts how it ends, as the guide states it:

- `Runs`: exit 0, the workflow's value and the ordered command log;
- `Refused`: exit 2 before any command ran, with the first diagnostic's code and location,
  and for the size bound the node count and the limit that the diagnostic prints;
- `FailsAtRunTime`: exit 1, the error code recorded in `state.json`, and the command log.

A program is written at target 2.33; a case at another target rewrites that one header line.
Commands are `probe.py`, which appends `<command> <n>` to `.orchestrate/guide-probe.log`.
The guide quotes the programs; `test_every_quoted_program_is_part_of_its_fixture` checks
that each quoted block is lines of its fixture, so the quotes and the programs cannot drift.
"""

from __future__ import annotations

import json
import logging
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.test_workflow_lisp_generic_unions_runtime import _public_run

REPO = Path(__file__).resolve().parents[1]
SHAPES = Path("tests/fixtures/workflow_lisp/guide_shapes")
GUIDE = REPO / "docs" / "lisp_workflow_drafting_guide.md"
HEADER = '(:target-dsl "2.33")'

_DIAGNOSTIC = re.compile(r"\.orc:(\d+):(\d+): \[([a-z0-9_]+)\]")
_SIZE = re.compile(r"node_count=(\d+), max_nodes=(\d+)")


@dataclass(frozen=True)
class Runs:
    value: dict
    log: tuple[str, ...] = ()


@dataclass(frozen=True)
class Refused:
    code: str
    line: int
    column: int
    size: tuple[int, int] | None = None  # (node count, limit) printed by `pure_expr_payload_too_large`


@dataclass(frozen=True)
class FailsAtRunTime:
    code: str
    log: tuple[str, ...]


def _both(outcome):
    return {"2.33": outcome, "2.34": outcome}


BUMPS_TO_3 = ("bump 0", "bump 1", "bump 2")
MANY_FIELDS = {
    "return__turn": 3, "return__best": 5, "return__worst": 0, "return__sum": 8, "return__tries": 3,
    "return__wins": 3, "return__losses": 0, "return__streak": 3, "return__last": 5, "return__spread": 5,
    "return__gain": 3, "return__improved": True,
}
BRANCH_HISTORY = [{"parents": [{"n": 2}], "n": 2}, {"parents": [{"n": 2}], "n": 2}]
SEARCH_INPUTS = {"total": 3.5, "visits": 2, "all-visits": 10}

# id -> (program, inputs, {target: outcome})
CASES = {
    "loop_in_branch": ("loop_in_branch", {"go": True}, _both(Refused("workflow_boundary_type_invalid", 15, 23))),
    "loop_in_called_workflow": (
        "loop_in_called_workflow", {"go": True}, _both(Runs({"return__n": 3}, BUMPS_TO_3)),
    ),
    "loop_in_loop": ("loop_in_loop", {}, _both(Refused("compiler_defect", 12, 5))),
    "loop_in_loop_called": (
        "loop_in_loop_called", {}, _both(Runs({"return__n": 4}, ("bump 0", "bump 1", "bump 0", "bump 1"))),
    ),
    "many_field_update": (
        "many_field_update", {},
        {
            "2.29": Refused("pure_expr_payload_too_large", 23, 22, (647, 256)),
            **_both(Runs(MANY_FIELDS, BUMPS_TO_3)),
        },
    ),
    "shared_binding": (
        "shared_binding", {"a": 3, "b": 1},
        {"2.29": Refused("pure_expr_payload_too_large", 9, 7, (701, 256)), **_both(Runs({"__result__": 800}))},
    ),
    "payload_too_large": (
        "payload_too_large", {"a": 1}, _both(Refused("pure_expr_payload_too_large", 8, 5, (301, 256))),
    ),
    "payload_split": ("payload_split", {"a": 1}, _both(Runs({"__result__": 300}))),
    "record_command_input": (
        "record_command_input", {}, _both(Refused("workflow_return_not_exportable", 9, 106)),
    ),
    "record_fields_command_input": (
        "record_fields_command_input", {}, _both(Runs({"return__n": 4}, ("fetch 4",))),
    ),
    "record_adapter_input": (
        "record_adapter_input", {}, _both(Refused("command_adapter_input_not_projectable", 9, 72)),
    ),
    "record_fields_adapter_input": (
        "record_fields_adapter_input", {}, _both(Runs({"return__n": 4}, ("fetch-fields 4",))),
    ),
    "decimal_arithmetic": (
        "decimal_arithmetic", SEARCH_INPUTS,
        {
            "2.33": Refused("pure_expr_operator_unsupported", 7, 9),
            "2.34": Runs({"__result__": 3.3594745197170104}),
        },
    ),
    "decimal_arithmetic_zero_visits": (
        "decimal_arithmetic", {**SEARCH_INPUTS, "visits": 0},
        {"2.34": FailsAtRunTime("pure_expr_division_by_zero", ())},
    ),
    "decimal_literal": (
        "decimal_literal", {"score": 0.25},
        {"2.33": Refused("frontend_parse_error", 7, 23), "2.34": Runs({"__result__": True})},
    ),
    "decimal_default": ("decimal_default", {"score": 0.25}, _both(Runs({"__result__": True}))),
    "commands_in_sequence": (
        "commands_in_sequence", {"items": [3, 1, 2]},
        _both(Runs({"__result__": [{"n": 3}, {"n": 1}, {"n": 2}]}, ("fetch 3", "fetch 1", "fetch 2"))),
    ),
    "map_effect_procedure_body": (
        "map_effect_procedure_body", {"items": [3, 1, 2]},
        _both(Refused("list_map_effect_body_unsupported", 12, 5)),
    ),
    "map_effect_workflow_body": (
        "map_effect_workflow_body", {"items": [3, 1, 2]},
        _both(Runs({"__result__": [{"n": 3}, {"n": 1}, {"n": 2}]}, ("fetch 3", "fetch 1", "fetch 2"))),
    ),
    "helper_bound_in_loop": (
        "helper_bound_in_loop", {}, _both(Refused("compiler_defect_loop_control_value", 20, 22)),
    ),
    "helper_literal_argument": (
        "helper_literal_argument", {}, _both(Refused("workflow_signature_mismatch", 21, 36)),
    ),
    "helper_holds_the_branch": (
        "helper_holds_the_branch", {},
        _both(Runs({"return__a": 6, "return__b": 4, "return__turn": 4}, (*BUMPS_TO_3, "bump 3"))),
    ),
    "if_over_lists": ("if_over_lists", {"branch": "B"}, _both(Refused("workflow_return_not_exportable", 17, 21))),
    "list_in_state_update": (
        "list_in_state_update", {"branch": "B"},
        _both(Runs(
            {"return__pair__a__n": 1, "return__pair__b__n": 2, "return__history": BRANCH_HISTORY, "return__turn": 2},
            ("fetch 2", "fetch 2"),
        )),
    ),
    "if_over_records": (
        "if_over_records", {"branch": "B"}, _both(FailsAtRunTime("pure_expr_payload_invalid", ("fetch 2",))),
    ),
    "if_over_scalars": (
        "if_over_scalars", {"branch": "B"}, _both(FailsAtRunTime("pure_expr_payload_invalid", ("fetch 2",))),
    ),
    "if_through_defun": ("if_through_defun", {"branch": "B"}, _both(Runs({"return__n": 4}, ("fetch 2",)))),
    "effect_argument": ("effect_argument", {}, _both(Refused("compiler_defect", 16, 12))),
    "effect_argument_bound": (
        "effect_argument_bound", {}, _both(Runs({"return__n": 27}, ("bump 26", "fetch 27"))),
    ),
    "on_exhausted_helper": (
        "on_exhausted_helper", {},
        _both(Runs({"return__n": 2, "return__status": "exhausted"}, ("bump 0", "bump 1"))),
    ),
    "on_exhausted_helper_in_branch": (
        "on_exhausted_helper_in_branch", {"go": True},
        _both(Refused("workflow_boundary_type_invalid", 18, 23)),
    ),
    "on_exhausted_pure_proc": (
        "on_exhausted_pure_proc", {}, _both(Refused("loop_recur_contract_invalid", 19, 21)),
    ),
    "shadowed_name": ("shadowed_name", {}, _both(Runs({"__result__": 15}, ("bump 1", "bump 10")))),
    # The value of a known defect: lexical scope gives 7; a later binder captures `b`.
    "bind_proc_capture": ("bind_proc_capture", {}, _both(Runs({"__result__": 13}))),
}


def _install(root: Path, program: str, target: str) -> dict[str, Path]:
    shapes = root / SHAPES
    shapes.mkdir(parents=True)
    for name in ("probe.py", "commands.json"):
        shutil.copy2(REPO / SHAPES / name, shapes / name)
    text = (REPO / SHAPES / f"{program}.orc").read_text(encoding="utf-8")
    assert text.count(HEADER) == 1, program
    (shapes / f"{program}.orc").write_text(text.replace(HEADER, f'(:target-dsl "{target}")'), encoding="utf-8")
    files = {
        "source": shapes / f"{program}.orc",
        "source_root": root / SHAPES.parent,
        "providers": root / "providers.json",
        "prompts": root / "prompts.json",
        "commands": shapes / "commands.json",
    }
    files["providers"].write_text("{}", encoding="utf-8")
    files["prompts"].write_text("{}", encoding="utf-8")
    return files


def _log(root: Path) -> tuple[str, ...]:
    log = root / ".orchestrate" / "guide-probe.log"
    return tuple(log.read_text(encoding="utf-8").splitlines()) if log.exists() else ()


def _error_types(node: object) -> set[str]:
    """Every `type` of an error mapping (one with a `message`) anywhere in `node`."""

    if isinstance(node, dict):
        found = {node["type"]} if isinstance(node.get("type"), str) and "message" in node else set()
        return found.union(*(_error_types(value) for value in node.values()))
    if isinstance(node, list):
        return set().union(*(_error_types(item) for item in node))
    return set()


def _observe(root: Path, monkeypatch, caplog, program: str, inputs: dict, target: str, outcome):
    files = _install(root, program, target)
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs), encoding="utf-8")
    monkeypatch.chdir(root)
    with caplog.at_level(logging.ERROR):
        result = _public_run(files, input_file=input_file)
    if isinstance(outcome, Runs):
        value = json.loads(json.dumps(dict(result.workflow_outputs), default=dict))  # read-only mappings
        return Runs(value, _log(root)), result.exit_code
    if isinstance(outcome, FailsAtRunTime):
        (state,) = (root / ".orchestrate" / "runs").glob("*/state.json")
        types = _error_types(json.loads(state.read_text(encoding="utf-8")).get("steps"))
        code = outcome.code if outcome.code in types else sorted(types)
        return FailsAtRunTime(code, _log(root)), result.exit_code
    line, column, code = next(iter(_DIAGNOSTIC.findall(caplog.text)), ("0", "0", None))
    size = next(iter(_SIZE.findall(caplog.text)), None)
    refused = Refused(code, int(line), int(column), tuple(map(int, size)) if outcome.size and size else None)
    return (refused, _log(root)), result.exit_code


EXIT_CODES = {Runs: 0, Refused: 2, FailsAtRunTime: 1}


@pytest.mark.parametrize(
    ("case", "target"),
    [pytest.param(case, target, id=f"{case}@{target}") for case, (_, _, by_target) in CASES.items() for target in by_target],
)
def test_guide_program_ends_as_the_guide_says(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, case: str, target: str
) -> None:
    program, inputs, by_target = CASES[case]
    outcome = by_target[target]

    observed, exit_code = _observe(tmp_path, monkeypatch, caplog, program, inputs, target, outcome)

    expected = (outcome, ()) if isinstance(outcome, Refused) else outcome
    assert (exit_code, observed) == (EXIT_CODES[type(outcome)], expected), caplog.text[-3000:]


def test_every_fixture_program_has_a_case() -> None:
    programs = {path.stem for path in (REPO / SHAPES).glob("*.orc")}

    assert programs == {program for program, _, _ in CASES.values()}


_QUOTE = re.compile(r"```lisp\n;; (tests/fixtures/workflow_lisp/guide_shapes/[a-z_]+\.orc)\n(.*?)```", re.DOTALL)


def _is_part_of(quote: str, program: str) -> bool:
    """Each run of quoted lines between `...` lines is consecutive lines of the program, in order."""

    lines = [line.strip() for line in program.splitlines()]
    start = 0
    for run in re.split(r"^\s*\.\.\.\s*$", quote, flags=re.MULTILINE):
        wanted = [line.strip() for line in run.strip("\n").splitlines()]
        if not wanted:
            continue
        found = next((i for i in range(start, len(lines) - len(wanted) + 1) if lines[i : i + len(wanted)] == wanted), None)
        if found is None:
            return False
        start = found + len(wanted)
    return True


def test_every_quoted_program_is_part_of_its_fixture() -> None:
    quotes = _QUOTE.findall(GUIDE.read_text(encoding="utf-8"))

    assert quotes, "the guide quotes no program of the fixture directory"
    assert [path for path, quote in quotes if not _is_part_of(quote, (REPO / path).read_text(encoding="utf-8"))] == []
