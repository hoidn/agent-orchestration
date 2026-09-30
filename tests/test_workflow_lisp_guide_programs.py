"""The programs of the drafting guide's section on program shapes, run through the public entry.

Guide: docs/lisp_workflow_drafting_guide.md, section "2A. Program Shapes: What Runs Today".
Plan: docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md, Task 5.

Every program is a file of `tests/fixtures/workflow_lisp/guide_shapes/`. Each case runs one
program at one target and asserts how it ends, as the guide states it:

- `Runs`: exit 0, the workflow's value and the ordered command log;
- `Refused`: exit 2 before any command ran, with the first diagnostic's code and location,
  the stage that raised it (`STAGES`; the guide's label follows from it), and for the size
  bound the node count and the limit that the diagnostic prints;
- `FailsAtRunTime`: exit 1, the error code recorded in `state.json`, and the command log.

A program is written at target 2.33; a case at another target rewrites that one header line.
Commands are `probe.py`, which appends `<command> <n>` to `.orchestrate/guide-probe.log`.
The guide quotes the programs; `test_every_quoted_program_is_part_of_its_fixture` finds every
fenced block whose first line is a comment naming a fixture, requires the quote form, and
checks that the block is lines of its fixture, so the quotes and the programs cannot drift.
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
from tests.test_workflow_lisp_totality_matrix import _record_diagnostic_origins

REPO = Path(__file__).resolve().parents[1]
SHAPES = Path("tests/fixtures/workflow_lisp/guide_shapes")
GUIDE = REPO / "docs" / "lisp_workflow_drafting_guide.md"
HEADER = '(:target-dsl "2.33")'

_DIAGNOSTIC = re.compile(r"\.orc:(\d+):(\d+): \[([a-z0-9_]+)\]")
_SIZE = re.compile(r"node_count=(\d+), max_nodes=(\d+)")

# Where a refusal is raised: from the innermost frame outward, the first frame that holds a
# fragment names the stage (the frames are recorded as the totality matrix records them).
STAGES = (
    ("/workflow_lisp/expressions.py:", "reader"),
    ("/workflow_lisp/typecheck", "typecheck"),
    ("/workflow/pure_expr.py:validate_pure_expr_payload", "payload validation"),
    ("/workflow_lisp/wcc/elaborate.py:", "elaboration"),
    ("/workflow_lisp/wcc/defunctionalize.py:", "defunctionalization"),
    ("/workflow_lisp/lowering/origins.py:_remapped_shared_validation_diagnostic", "shared validation"),
    ("/workflow_lisp/lowering/", "lowering"),
)


@dataclass(frozen=True)
class Runs:
    value: dict
    log: tuple[str, ...] = ()


@dataclass(frozen=True)
class Refused:
    code: str
    line: int
    column: int
    stage: str
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
SEARCH_INPUTS = {"total": 3.5, "visits": 2, "all-visits": 10}

# id -> (program, inputs, {target: outcome})
CASES = {
    "loop_in_branch": ("loop_in_branch", {"go": True}, _both(Refused("workflow_boundary_type_invalid", 15, 23, "shared validation"))),
    "loop_in_called_workflow": (
        "loop_in_called_workflow", {"go": True}, _both(Runs({"return__n": 3}, BUMPS_TO_3)),
    ),
    "loop_in_loop": ("loop_in_loop", {}, _both(Refused("compiler_defect", 12, 5, "defunctionalization"))),
    "loop_in_loop_called": (
        "loop_in_loop_called", {}, _both(Runs({"return__n": 4}, ("bump 0", "bump 1", "bump 0", "bump 1"))),
    ),
    "many_field_update": (
        "many_field_update", {},
        {
            "2.29": Refused("pure_expr_payload_too_large", 23, 22, "payload validation", (647, 256)),
            **_both(Runs(MANY_FIELDS, BUMPS_TO_3)),
        },
    ),
    "shared_binding": (
        "shared_binding", {"a": 3, "b": 1},
        {"2.29": Refused("pure_expr_payload_too_large", 9, 7, "payload validation", (701, 256)), **_both(Runs({"__result__": 800}))},
    ),
    "payload_too_large": (
        "payload_too_large", {"a": 1}, _both(Refused("pure_expr_payload_too_large", 8, 5, "payload validation", (301, 256))),
    ),
    "payload_split": ("payload_split", {"a": 1}, _both(Runs({"__result__": 300}))),
    "record_command_input": (
        "record_command_input", {}, _both(Refused("workflow_return_not_exportable", 9, 106, "lowering")),
    ),
    "record_fields_command_input": (
        "record_fields_command_input", {}, _both(Runs({"return__n": 4}, ("fetch 4",))),
    ),
    "record_adapter_input": (
        "record_adapter_input", {}, _both(Refused("command_adapter_input_not_projectable", 9, 72, "typecheck")),
    ),
    "record_fields_adapter_input": (
        "record_fields_adapter_input", {}, _both(Runs({"return__n": 4}, ("fetch-fields 4",))),
    ),
    "decimal_arithmetic": (
        "decimal_arithmetic", SEARCH_INPUTS,
        {
            "2.33": Refused("pure_expr_operator_unsupported", 7, 9, "reader"),
            "2.34": Runs({"__result__": 3.3594745197170104}),
        },
    ),
    "decimal_arithmetic_zero_visits": (
        "decimal_arithmetic", {**SEARCH_INPUTS, "visits": 0},
        {"2.34": FailsAtRunTime("pure_expr_division_by_zero", ())},
    ),
    "decimal_literal": (
        "decimal_literal", {"score": 0.25},
        {"2.33": Refused("frontend_parse_error", 7, 23, "reader"), "2.34": Runs({"__result__": True})},
    ),
    "decimal_default": ("decimal_default", {"score": 0.25}, _both(Runs({"__result__": True}))),
    "commands_in_sequence": (
        "commands_in_sequence", {"items": [3, 1, 2]},
        _both(Runs({"__result__": [{"n": 3}, {"n": 1}, {"n": 2}]}, ("fetch 3", "fetch 1", "fetch 2"))),
    ),
    "map_effect_procedure_body": (
        "map_effect_procedure_body", {"items": [3, 1, 2]},
        _both(Refused("list_map_effect_body_unsupported", 12, 5, "defunctionalization")),
    ),
    "map_effect_workflow_body": (
        "map_effect_workflow_body", {"items": [3, 1, 2]},
        _both(Runs({"__result__": [{"n": 3}, {"n": 1}, {"n": 2}]}, ("fetch 3", "fetch 1", "fetch 2"))),
    ),
    "helper_bound_in_loop": (
        "helper_bound_in_loop", {}, _both(Refused("compiler_defect_loop_control_value", 20, 22, "defunctionalization")),
    ),
    "helper_literal_argument": (
        "helper_literal_argument", {}, _both(Refused("workflow_signature_mismatch", 21, 36, "lowering")),
    ),
    "helper_holds_the_branch": (
        "helper_holds_the_branch", {},
        _both(Runs({"return__a": 6, "return__b": 4, "return__turn": 4}, (*BUMPS_TO_3, "bump 3"))),
    ),
    "if_over_lists": ("if_over_lists", {"branch": "B"}, _both(Refused("workflow_return_not_exportable", 17, 21, "lowering"))),
    # Both arms of both `if`s of the refused source: A reads `pair.a`; C reads `pair.b` twice.
    "list_in_state_update_a": (
        "list_in_state_update", {"branch": "A"},
        _both(Runs({"return__n": 1, "return__parents": [{"n": 1}]}, ("fetch 1",))),
    ),
    "list_in_state_update_c": (
        "list_in_state_update", {"branch": "C"},
        _both(Runs({"return__n": 2, "return__parents": [{"n": 2}]}, ("fetch 2",))),
    ),
    "if_over_records": (
        "if_over_records", {"branch": "B"}, _both(FailsAtRunTime("pure_expr_payload_invalid", ("fetch 2",))),
    ),
    "if_over_scalars": (
        "if_over_scalars", {"branch": "B"}, _both(FailsAtRunTime("pure_expr_payload_invalid", ("fetch 2",))),
    ),
    "if_through_defun": ("if_through_defun", {"branch": "B"}, _both(Runs({"return__n": 4}, ("fetch 2",)))),
    "effect_argument": ("effect_argument", {}, _both(Refused("compiler_defect", 16, 12, "elaboration"))),
    "effect_argument_bound": (
        "effect_argument_bound", {}, _both(Runs({"return__n": 27}, ("bump 26", "fetch 27"))),
    ),
    "on_exhausted_helper": (
        "on_exhausted_helper", {},
        _both(Runs({"return__n": 2, "return__status": "exhausted"}, ("bump 0", "bump 1"))),
    ),
    "on_exhausted_helper_in_branch": (
        "on_exhausted_helper_in_branch", {"go": True},
        _both(Refused("workflow_boundary_type_invalid", 18, 23, "shared validation")),
    ),
    "on_exhausted_operator": (
        "on_exhausted_operator", {"base": 3},
        _both(Refused("workflow_return_not_exportable", 9, 21, "lowering")),
    ),
    "on_exhausted_operator_in_state": ("on_exhausted_operator_in_state", {"base": 3}, _both(Runs({"__result__": 6}))),
    "on_exhausted_float_operator": (
        "on_exhausted_float_operator", {"base": 1.25},
        {
            "2.33": Refused("pure_expr_operand_type_mismatch", 9, 21, "typecheck"),
            "2.34": Refused("workflow_return_not_exportable", 9, 21, "lowering"),
        },
    ),
    "on_exhausted_float_defun": (
        "on_exhausted_float_defun", {"base": 1.25},
        {
            "2.33": Refused("pure_expr_operand_type_mismatch", 7, 5, "typecheck"),
            "2.34": Refused("workflow_return_not_exportable", 11, 21, "lowering"),
        },
    ),
    "on_exhausted_float_in_state": (
        "on_exhausted_float_in_state", {"base": 1.25},
        {"2.33": Refused("pure_expr_operand_type_mismatch", 8, 55, "typecheck"), "2.34": Runs({"__result__": 2.5})},
    ),
    "on_exhausted_pure_proc": (
        "on_exhausted_pure_proc", {}, _both(Refused("loop_recur_contract_invalid", 19, 21, "typecheck")),
    ),
    "shadowed_name": ("shadowed_name", {}, _both(Runs({"__result__": 15}, ("bump 1", "bump 10")))),
    # The value of a known defect: lexical scope gives 7; the later binder of `b` is read.
    "bind_proc_capture": ("bind_proc_capture", {}, _both(Runs({"__result__": 13}))),
    "bind_proc_renamed": ("bind_proc_renamed", {}, _both(Runs({"__result__": 7}))),
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


def _stage(origins: list[tuple[str, list[str]]], code: str | None) -> str | None:
    frames = next((frames for recorded, frames in origins if recorded == code), [])
    return next((stage for frame in frames for fragment, stage in STAGES if fragment in frame), None)


def _observe(root: Path, monkeypatch, caplog, program: str, inputs: dict, target: str, outcome):
    files = _install(root, program, target)
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs), encoding="utf-8")
    monkeypatch.chdir(root)
    origins = _record_diagnostic_origins(monkeypatch)
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
    size = tuple(map(int, size)) if outcome.size and size else None
    refused = Refused(code, int(line), int(column), _stage(origins, code), size)
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


_OPENING = re.compile(r"\s*(```|~~~)")
_NAMES_FIXTURE = re.compile(r"\s*(;+|#+|//+|--+).*guide_shapes/[\w.-]+\.orc")
_QUOTE_HEADER = re.compile(r";; (tests/fixtures/workflow_lisp/guide_shapes/[a-z_]+\.orc)")


def _fences(text: str) -> list[tuple[str, list[str]]]:
    """Every fenced block of a Markdown text: its opening line and its lines."""

    blocks, opening, body = [], None, []
    for line in text.splitlines():
        if opening is None:
            if _OPENING.match(line):
                opening, body = line, []
        elif line.strip() and set(line.strip()) == {opening.strip()[0]} and len(line.strip()) >= 3:
            blocks.append((opening, body))
            opening = None
        else:
            body.append(line)
    return blocks


def _is_part_of(quote: list[str], program: str) -> bool:
    """Each run of quoted lines between `...` lines is consecutive lines of the program, in order."""

    lines = [line.strip() for line in program.splitlines()]
    runs: list[list[str]] = [[]]
    for line in quote:
        if line.strip() == "...":
            runs.append([])
        else:
            runs[-1].append(line.strip())
    start = 0
    for wanted in filter(None, runs):
        found = next((i for i in range(start, len(lines) - len(wanted) + 1) if lines[i : i + len(wanted)] == wanted), None)
        if found is None:
            return False
        start = found + len(wanted)
    return True


def _quote_faults(text: str) -> list[str]:
    """The first line of each fence that names a fixture and is not a quote of its lines, in the quote form."""

    faults = []
    for opening, body in _fences(text):
        if not body or not _NAMES_FIXTURE.match(body[0]):
            continue
        header = _QUOTE_HEADER.fullmatch(body[0])
        fixture = REPO / header.group(1) if header else None
        in_form = opening.strip() == "```lisp" and fixture is not None and fixture.is_file()
        if not (in_form and _is_part_of(body[1:], fixture.read_text(encoding="utf-8"))):
            faults.append(body[0])
    return faults


def test_every_quoted_program_is_part_of_its_fixture() -> None:
    text = GUIDE.read_text(encoding="utf-8")

    assert [body[0] for _, body in _fences(text) if body and _QUOTE_HEADER.fullmatch(body[0])], "no quote found"
    assert _quote_faults(text) == []


@pytest.mark.xfail(strict=True, reason="F43: fixture headers with invalid suffixes are silently skipped")
@pytest.mark.parametrize("suffix", [".orx", ""])
def test_fixture_quote_with_invalid_suffix_is_reported(suffix: str) -> None:
    header = f";; tests/fixtures/workflow_lisp/guide_shapes/decimal_arithmetic{suffix}"
    assert _quote_faults(f"```lisp\n{header}\n(not-a-fixture-line)\n```\n") == [header]
