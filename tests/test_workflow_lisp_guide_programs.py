"""Guide-shape semantics on evaluated execution, with historical typed refusals.

The original 2.29/2.33/2.34 outcomes remain as fixture provenance. Executable
cases use 2.35 and native values; old lowering defects and payload limits are
not current admission rules. Older language/type refusals still use typed
analysis without dispatch or a flat backend.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

from tests.workflow_evaluated_totality_helpers import public_run
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.build_manifest_io import _parse_command_boundaries_manifest

REPO = Path(__file__).resolve().parents[1]
SHAPES = Path("tests/fixtures/workflow_lisp/guide_shapes")
HEADER = '(:target-dsl "2.33")'

@dataclass(frozen=True)
class Runs:
    value: object
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
    "bind_proc_capture": ("bind_proc_capture", {}, _both(Runs({"__result__": 7}))),
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
    boundaries = json.loads(files["commands"].read_text())
    for row in boundaries.values():
        row["closure"] = [(SHAPES / "probe.py").as_posix()]
    files["commands"].write_text(json.dumps(boundaries))
    return files


def _log(root: Path) -> tuple[str, ...]:
    log = root / ".orchestrate" / "guide-probe.log"
    return tuple(log.read_text(encoding="utf-8").splitlines()) if log.exists() else ()



def _native(outcome: Runs) -> Runs:
    fields = outcome.value
    value = fields["__result__"] if "__result__" in fields else {
        key.removeprefix("return__"): value for key, value in fields.items()
    }
    return Runs(value, outcome.log)


EVALUATED = {
    case: _native(by_target["2.34"])
    for case, (_, _, by_target) in CASES.items()
    if isinstance(by_target.get("2.34"), Runs)
}
EVALUATED.update({
    "loop_in_branch": Runs({"n": 3}, BUMPS_TO_3),
    "loop_in_loop": Runs({"n": 4}, ("bump 0", "bump 1", "bump 0", "bump 1")),
    "payload_too_large": Runs(300),
    "map_effect_procedure_body": Runs([{"n": 3}, {"n": 1}, {"n": 2}], ("fetch 3", "fetch 1", "fetch 2")),
    "helper_bound_in_loop": Runs({"a": 6, "b": 4, "turn": 4}, (*BUMPS_TO_3, "bump 3")),
    "helper_literal_argument": Runs({"a": 6, "b": 4, "turn": 4}, (*BUMPS_TO_3, "bump 3")),
    "if_over_lists": Runs({"n": 2, "parents": [{"n": 2}]}, ("fetch 2",)),
    "if_over_records": Runs({"n": 4}, ("fetch 2",)),
    "if_over_scalars": Runs({"n": 4}, ("fetch 2",)),
    "effect_argument": Runs({"n": 27}, ("bump 26", "fetch 27")),
    "on_exhausted_helper_in_branch": Runs({"n": 2, "status": "exhausted"}, ("bump 0", "bump 1")),
    "on_exhausted_operator": Runs(6),
    "on_exhausted_float_operator": Runs(2.5),
    "on_exhausted_float_defun": Runs(2.5),
    "decimal_arithmetic_zero_visits": FailsAtRunTime("pure_expr_division_by_zero", ()),
})
TYPED_REFUSALS = [
    (case, target, outcome)
    for case, (_, _, by_target) in CASES.items()
    for target, outcome in by_target.items()
    if isinstance(outcome, Refused) and outcome.stage in {"reader", "typecheck"}
]


@pytest.mark.parametrize("case", EVALUATED)
def test_evaluated_program_outcomes(tmp_path, monkeypatch, case):
    program, inputs, _history = CASES[case]
    expected = EVALUATED[case]
    files = _install(tmp_path, program, "2.35")
    input_file = tmp_path / "inputs.json"
    input_file.write_text(json.dumps(inputs))
    monkeypatch.chdir(tmp_path)
    result = public_run(files, input_file)
    assert _log(tmp_path) == expected.log
    (memo,) = (tmp_path / ".orchestrate" / "runs").glob("*/memo.jsonl")
    terminal = json.loads(memo.read_text().splitlines()[-1])
    if isinstance(expected, Runs):
        assert result.exit_code == 0
        assert terminal["outcome"] == "completed"
        assert terminal["value"] == expected.value
    else:
        assert result.exit_code == 1
        assert terminal["outcome"] == "failed"
        assert terminal["code"] == expected.code


@pytest.mark.parametrize(("case", "target", "expected"), TYPED_REFUSALS,
                         ids=[f"{case}@{target}" for case, target, _ in TYPED_REFUSALS])
def test_historical_language_refusal_still_has_authored_location(tmp_path, case, target, expected):
    files = _install(tmp_path, CASES[case][0], target)
    boundaries = _parse_command_boundaries_manifest(
        json.loads(files["commands"].read_text()), manifest_path=files["commands"],
    )
    with pytest.raises(LispFrontendCompileError) as refused:
        compile_stage3_entrypoint(
            files["source"], source_roots=(files["source_root"],),
            command_boundaries=boundaries, workspace_root=tmp_path,
            validate_shared=False,
        )
    diagnostic = refused.value.diagnostics[0]
    assert (diagnostic.code, diagnostic.span.start.line, diagnostic.span.start.column) == (
        expected.code, expected.line, expected.column,
    )
    assert _log(tmp_path) == ()
    assert not (tmp_path / ".orchestrate" / "runs").exists()


def test_every_fixture_program_has_a_case() -> None:
    programs = {path.stem for path in (REPO / SHAPES).glob("*.orc")}
    assert programs == {program for program, _, _ in CASES.values()}
    # argv record projection is retired; current structured command inputs have
    # their public coverage in test_workflow_evaluated_input_documents.py.
    covered = set(EVALUATED) | {case for case, _, _ in TYPED_REFUSALS}
    assert set(CASES) - covered == {"record_command_input"}
