"""Numeric surface N6 and N7: a `Float` that enters a run at target 2.34 is finite.

Contract: docs/design/workflow_lisp_numeric_surface.md, rules N6 and N7 and
section 6; Task 4 of docs/plans/2026-09-29-workflow-lisp-evaluated-execution-plan.md.

Programs run through the public entry (`run_workflow`). A command result comes
from a probe that copies `answer.json` verbatim into its result bundle, so each
test controls the exact JSON text; a provider result comes from a stand-in
provider executor that does the same. Target 2.33 is the control: it accepts
non-finite values as it does today (a known defect that stays), and the controls
pin what it writes to `state.json`.

The expected output file boundary is tested at its validator: Workflow Lisp
lowers an expected output file only as a `String` (a prompt output position), so
no `.orc` program declares a `Float` one.
"""

from __future__ import annotations

import json
import logging
import math
import re
import struct
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.contracts.output_contract import OutputContractError, validate_expected_outputs
from tests.test_workflow_lisp_generic_unions_runtime import (
    _log,
    _public_run,
    _public_run_files,
    _write_probe,
    _write_sources,
)
from tests.test_workflow_lisp_improve_example_e2e import _Agents
from tests.workflow_lisp_improve_stdlib_sources import _PROBE_PRELUDE

PROBE = _PROBE_PRELUDE + """bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
bundle.parent.mkdir(parents=True, exist_ok=True)
bundle.write_text(Path(__file__).with_name("answer.json").read_text(encoding="utf-8"), encoding="utf-8")
"""

HEADER = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "TARGET")
  (defmodule grt/entry)
  (export run)
  (defrecord Score (value Float) (label String))
  (defproc measure ((label String) (x Float)) -> Score
    :effects ((uses-command probe))
    :lowering inline
    (command-result probe :argv ("python" "PROBE" label x) :returns Score))
"""

# The input `x` reaches the command's argv; the second command runs only after the first result is accepted.
BY_COMMAND = """  (defworkflow run ((x Float)) -> Score
    (let* ((first (measure "first" x))
           (second (measure first.label x)))
      second)))
"""

# The provider result is the workflow's result; the command after it runs only if the result is accepted.
BY_PROVIDER = """  (defproc ask ((label String)) -> Score
    :effects ((uses-provider providers.ask))
    :lowering inline
    (provider-result providers.ask :prompt prompts.ask :inputs (label) :returns Score))
  (defworkflow run ((x Float)) -> Score
    (let* ((first (ask "first"))
           (second (measure first.label x)))
      first)))
"""

# A Float field in a record inside a union variant inside a list. A list of records
# inside a union variant is refused by the compiler (`collection_element_type_unsupported`).
NESTED = """  (defrecord Item (value Float) (label String))
  (defunion Outcome (FOUND (item Item)) (NONE (why String)))
  (defrecord Report (outcomes List[Outcome]))
  (defproc report ((label String)) -> Report
    :effects ((uses-command probe))
    :lowering inline
    (command-result probe :argv ("python" "PROBE" label) :returns Report))
  (defworkflow run () -> Report
    (report "r")))
"""

# A Float field of a union variant: a union result has a variant bundle contract.
UNION = """  (defunion Measured (OK (value Float) (label String)) (NONE (why String)))
  (defproc classify ((label String)) -> Measured
    :effects ((uses-command probe))
    :lowering inline
    (command-result probe :argv ("python" "PROBE" label) :returns Measured))
  (defworkflow run () -> Measured
    (classify "u")))
"""

# An opaque `Value` field: at 2.34 a non-finite number anywhere inside it is refused like a Float.
OPAQUE = """  (defrecord Blob (payload Value))
  (defproc fetch ((label String)) -> Blob
    :effects ((uses-command probe))
    :lowering inline
    (command-result probe :argv ("python" "PROBE" label) :returns Blob))
  (defworkflow run () -> Blob
    (fetch "v")))
"""

FINITE_ANSWER = '{"value": 1.5, "label": "a"}'

# Each row of N6, as the JSON text of the value, and the value as the refusal prints it.
ROWS = {
    "NaN": "nan",
    "Infinity": "inf",
    "-Infinity": "-inf",
    '"nan"': "nan",
    '"inf"': "inf",
    '"-inf"': "-inf",
    '"Infinity"': "inf",
    "1e400": "inf",
}
TOKEN_OF = {"nan": "NaN", "inf": "Infinity", "-inf": "-Infinity"}

# 17 significant digits, the smallest subnormal, and a negative zero.
FINITE = ["0.30000000000000004", "5e-324", "-0.0"]


class _StandInProvider(_Agents):
    """The provider executor stand-in: its result bundle is the given JSON text, verbatim."""

    def execute(self, invocation, **_kwargs):
        self.calls.append(invocation.provider_name)
        Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(self.answers, encoding="utf-8")
        return SimpleNamespace(
            exit_code=0, stdout=b"", stderr=b"", duration_ms=1, error=None, missing_placeholders=None,
            invalid_prompt_placeholder=False, raw_stdout=None, normalized_stdout=None, provider_session=None,
        )  # fmt: skip


def _run(root: Path, target: str, body: str, *, answer: str, x: str | None = "1.0", provider: str | None = None):
    probe = _write_probe(root, "probe", PROBE)
    (root / "answer.json").write_text(answer, encoding="utf-8")
    source = (HEADER + body).replace("TARGET", target).replace("PROBE", probe.as_posix())
    _write_sources(root, {"grt/entry.orc": source})
    files = _public_run_files(root, {"probe": probe})
    input_file = None
    if x is not None:
        input_file = root / "inputs.json"
        input_file.write_text('{"x": %s}' % x, encoding="utf-8")
    stand_in = _StandInProvider(provider or FINITE_ANSWER)
    if "providers.ask" in body:
        files["providers"].write_text('{"providers.ask": "stand-in"}', encoding="utf-8")
        files["prompts"].write_text('{"prompts.ask": "prompts/ask.md"}', encoding="utf-8")
        (root / "grt" / "prompts").mkdir(exist_ok=True)
        (root / "grt" / "prompts" / "ask.md").write_text("Answer.\n", encoding="utf-8")
    with ExitStack() as stack:
        stand_in.installed(stack)
        result = _public_run(files, input_file=input_file)
    return result, _log(probe), stand_in.calls


def _state(result) -> tuple[dict, str]:
    text = (result.run_root / "state.json").read_text(encoding="utf-8")
    return json.loads(text), text


def _refusal(state: dict) -> tuple[str, str, dict]:
    (step,) = [step for step in state["steps"].values() if step.get("status") == "failed"]
    (violation,) = step["error"]["context"]["violations"]
    return state["status"], violation["type"], violation["context"]


def _orchestrator_files_with_non_finite_tokens(root: Path) -> list[str]:
    """Files the orchestrator serialises under the runs directory: state, checkpoints, records.

    `logs/` is left out: it holds what a command printed, verbatim.
    """

    runs = root / ".orchestrate" / "runs"
    return sorted(
        path.relative_to(runs).as_posix()
        for path in runs.rglob("*")
        if path.is_file()
        and "logs" not in path.relative_to(runs).parts[1:2]
        and re.search(rb"NaN|Infinity", path.read_bytes())
    )


def _result_files(root: Path) -> list[str]:
    """The result files commands and providers wrote. A refused one stays, as evidence."""

    results = sorted((root / ".orchestrate" / "workflow_lisp").rglob("*result_bundle.json"))
    return [path.read_text(encoding="utf-8") for path in results]


def _bits(value: float) -> bytes:
    return struct.pack(">d", value)


def _same(value: float, printed: str) -> bool:
    expected = float(printed)
    return math.isnan(value) if math.isnan(expected) else _bits(value) == _bits(expected)


def _command_answer(value: str) -> str:
    return '{"value": %s, "label": "a"}' % value


def _union_answer(value: str) -> str:
    return '{"variant": "OK", "value": %s, "label": "a"}' % value


def _nested_answer(value: str) -> str:
    return '{"outcomes": [{"variant": "NONE", "why": "w"}, {"variant": "FOUND", "item": {"value": %s, "label": "a"}}]}' % value


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    return tmp_path


# Target 2.34: each row of N6 is refused where it enters, naming the field.


@pytest.mark.parametrize("row", ROWS)
def test_234_refuses_a_non_finite_workflow_input(root: Path, row: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        result, commands, _ = _run(root, "2.34", BY_COMMAND, answer=FINITE_ANSWER, x=row)

    errors = [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR]
    # The refusal comes before the run exists: no run directory, no command.
    assert (result.exit_code, (root / ".orchestrate" / "runs").exists(), commands) == (2, False, [])
    assert any("float_not_finite" in message and "'x'" in message for message in errors), errors


@pytest.mark.parametrize("row", ROWS)
def test_234_refuses_a_non_finite_command_result_field(root: Path, row: str) -> None:
    result, commands, _ = _run(root, "2.34", BY_COMMAND, answer=_command_answer(row))

    state, _ = _state(result)
    status, code, context = _refusal(state)
    assert (result.exit_code, status, code, context["json_pointer"], context["value"]) == (
        1, "failed", "float_not_finite", "/value", ROWS[row]
    )  # fmt: skip
    assert (commands, _orchestrator_files_with_non_finite_tokens(root)) == (["first 1.0"], [])
    assert _result_files(root) == [_command_answer(row)]


@pytest.mark.parametrize("row", ROWS)
def test_234_refuses_a_non_finite_provider_result_field(root: Path, row: str) -> None:
    result, commands, asked = _run(root, "2.34", BY_PROVIDER, answer=FINITE_ANSWER, provider=_command_answer(row))

    state, _ = _state(result)
    status, code, context = _refusal(state)
    assert (result.exit_code, status, code, context["json_pointer"], context["value"]) == (
        1, "failed", "float_not_finite", "/value", ROWS[row]
    )  # fmt: skip
    assert (asked, commands, _orchestrator_files_with_non_finite_tokens(root)) == (["stand-in"], [], [])
    assert _result_files(root) == [_command_answer(row)]


@pytest.mark.parametrize("row", ["NaN", "Infinity", "-Infinity", "1e400"])
def test_234_refuses_a_non_finite_float_in_a_nested_position(root: Path, row: str) -> None:
    result, commands, _ = _run(root, "2.34", NESTED, answer=_nested_answer(row), x=None)

    state, _ = _state(result)
    status, code, context = _refusal(state)
    assert (status, code, context["json_pointer"], context["value_path"], context["value"]) == (
        "failed", "float_not_finite", "/outcomes", "/1/item/value", ROWS[row]
    )  # fmt: skip
    assert (commands, _orchestrator_files_with_non_finite_tokens(root)) == (["r"], [])
    assert _result_files(root) == [_nested_answer(row)]


@pytest.mark.parametrize("row", ROWS)
def test_234_refuses_a_non_finite_union_variant_field(root: Path, row: str) -> None:
    result, commands, _ = _run(root, "2.34", UNION, answer=_union_answer(row), x=None)

    status, code, context = _refusal(_state(result)[0])
    assert (status, code, context["json_pointer"], context["value"]) == ("failed", "float_not_finite", "/value", ROWS[row])
    assert (commands, _orchestrator_files_with_non_finite_tokens(root)) == (["u"], [])
    assert _result_files(root) == [_union_answer(row)]


@pytest.mark.parametrize(
    ("target", "row", "code", "value_path"),
    [
        ("2.34", "NaN", "float_not_finite", "/scores/1"),
        ("2.34", "1e400", "float_not_finite", "/scores/1"),
        ("2.33", "NaN", "invalid_json_document", None),
        ("2.33", "1e400", "invalid_transportable_value", "/scores/1"),
    ],
)
def test_a_non_finite_number_inside_a_value_field_is_refused(
    root: Path, target: str, row: str, code: str, value_path: str | None
) -> None:
    result, _, _ = _run(root, target, OPAQUE, answer='{"payload": {"scores": [1, %s]}}' % row, x=None)

    _, refused, context = _refusal(_state(result)[0])
    assert (refused, context.get("value_path")) == (code, value_path)


@pytest.mark.parametrize("row", ['"nan"', '"inf"'])
def test_a_string_is_never_a_nested_float_at_either_target(root: Path, row: str) -> None:
    """A nested `Float` accepts only a JSON number, so a string there is a type error, as at 2.33."""

    for target in ("2.33", "2.34"):
        result, _, _ = _run(root, target, NESTED, answer=_nested_answer(row), x=None)
        _, code, context = _refusal(_state(result)[0])
        assert (code, context["error"]) == ("invalid_transportable_value", "$/1/item/value is not a finite Float")


# A JSON integer too large for a double: 2.33 fails with an uncaught `OverflowError`
# (a known defect that stays); 2.34 refuses it as the infinity it would read as.
HUGE_INTEGER = "1" + "0" * 400
HUGE = {
    "input": {"body": BY_COMMAND, "answer": FINITE_ANSWER, "x": HUGE_INTEGER},
    "command": {"body": BY_COMMAND, "answer": _command_answer(HUGE_INTEGER)},
    "provider": {"body": BY_PROVIDER, "answer": FINITE_ANSWER, "provider": _command_answer(HUGE_INTEGER)},
}


@pytest.mark.parametrize("boundary", ["command", "provider"])
def test_234_refuses_an_integer_result_field_too_large_for_a_double(root: Path, boundary: str) -> None:
    result, commands, _ = _run(root, "2.34", **HUGE[boundary])

    _, code, context = _refusal(_state(result)[0])
    assert (result.exit_code, code, context["json_pointer"], context["value"]) == (1, "float_not_finite", "/value", "inf")
    assert commands == (["first 1.0"] if boundary == "command" else [])


def test_234_refuses_an_integer_input_too_large_for_a_double(root: Path, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.ERROR):
        result, commands, _ = _run(root, "2.34", **HUGE["input"])

    assert (result.exit_code, commands) == (2, [])
    assert "float_not_finite: input 'x' is inf" in caplog.text


@pytest.mark.parametrize("boundary", ["input", "command", "provider"])
def test_233_fails_on_an_integer_too_large_for_a_double_as_today(
    root: Path, boundary: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR):
        result, _, _ = _run(root, "2.33", **HUGE[boundary])

    assert (result.exit_code, "Unexpected error: int too large to convert to float" in caplog.text) == (1, True)
    if boundary != "input":
        state, _ = _state(result)
        assert (state["status"], state["error"]["exception_type"]) == ("failed", "OverflowError")


# Target 2.34: a finite Float passes each boundary and arrives as the same double.


@pytest.mark.parametrize("value", FINITE)
def test_234_passes_a_finite_workflow_input_unchanged(root: Path, value: str) -> None:
    result, commands, _ = _run(root, "2.34", BY_COMMAND, answer=FINITE_ANSWER, x=value)

    state, _ = _state(result)
    received = [float(line.split()[1]) for line in commands]
    assert (result.exit_code, len(received)) == (0, 2)
    assert all(_same(number, value) for number in [state["bound_inputs"]["x"], *received])


@pytest.mark.parametrize("value", FINITE)
def test_234_passes_a_finite_command_result_field_unchanged(root: Path, value: str) -> None:
    result, _, _ = _run(root, "2.34", BY_COMMAND, answer=_command_answer(value))

    assert result.exit_code == 0
    assert _same(result.workflow_outputs["return__value"], value)


@pytest.mark.parametrize("value", FINITE)
def test_234_passes_a_finite_provider_result_field_unchanged(root: Path, value: str) -> None:
    result, commands, _ = _run(root, "2.34", BY_PROVIDER, answer=FINITE_ANSWER, provider=_command_answer(value))

    assert (result.exit_code, commands) == (0, ["a 1.0"])
    assert _same(result.workflow_outputs["return__value"], value)


@pytest.mark.parametrize("value", FINITE)
def test_234_passes_a_finite_union_variant_field_unchanged(root: Path, value: str) -> None:
    result, _, _ = _run(root, "2.34", UNION, answer=_union_answer(value), x=None)

    assert result.exit_code == 0
    assert _same(result.workflow_outputs["return__value"], value)


@pytest.mark.parametrize("value", FINITE)
def test_234_passes_a_finite_float_in_a_nested_position_unchanged(root: Path, value: str) -> None:
    result, _, _ = _run(root, "2.34", NESTED, answer=_nested_answer(value), x=None)

    assert result.exit_code == 0
    assert _same(result.workflow_outputs["return__outcomes"][1]["item"]["value"], value)


# Target 2.33, the control: non-finite values are accepted as today and reach state.json.


@pytest.mark.parametrize("row", ROWS)
def test_233_accepts_a_non_finite_workflow_input_as_today(root: Path, row: str) -> None:
    result, commands, _ = _run(root, "2.33", BY_COMMAND, answer=FINITE_ANSWER, x=row)

    state, text = _state(result)
    printed = ROWS[row]
    assert (result.exit_code, state["status"], commands) == (0, "completed", [f"first {printed}", f"a {printed}"])
    assert _same(state["bound_inputs"]["x"], printed)
    assert f'"x": {TOKEN_OF[printed]}' in text


@pytest.mark.parametrize("row", ROWS)
def test_233_accepts_a_non_finite_command_result_field_as_today(root: Path, row: str) -> None:
    result, commands, _ = _run(root, "2.33", BY_COMMAND, answer=_command_answer(row))

    state, text = _state(result)
    printed = ROWS[row]
    assert (result.exit_code, state["status"], commands) == (0, "completed", ["first 1.0", "a 1.0"])
    assert _same(result.workflow_outputs["return__value"], printed)
    assert f'"return__value": {TOKEN_OF[printed]}' in text


@pytest.mark.parametrize("row", ROWS)
def test_233_accepts_a_non_finite_provider_result_field_as_today(root: Path, row: str) -> None:
    result, commands, _ = _run(root, "2.33", BY_PROVIDER, answer=FINITE_ANSWER, provider=_command_answer(row))

    state, text = _state(result)
    printed = ROWS[row]
    assert (result.exit_code, state["status"], commands) == (0, "completed", ["a 1.0"])
    assert _same(result.workflow_outputs["return__value"], printed)
    assert f'"return__value": {TOKEN_OF[printed]}' in text


@pytest.mark.parametrize("row", ROWS)
def test_233_accepts_a_non_finite_union_variant_field_as_today(root: Path, row: str) -> None:
    result, commands, _ = _run(root, "2.33", UNION, answer=_union_answer(row), x=None)

    state, text = _state(result)
    printed = ROWS[row]
    assert (result.exit_code, state["status"], commands) == (0, "completed", ["u"])
    assert _same(result.workflow_outputs["return__value"], printed)
    assert f'"return__value": {TOKEN_OF[printed]}' in text


@pytest.mark.parametrize(
    ("row", "code"),
    [
        ("NaN", "invalid_json_document"),
        ("Infinity", "invalid_json_document"),
        ("-Infinity", "invalid_json_document"),
        ("1e400", "invalid_transportable_value"),
    ],
)
def test_233_refuses_a_non_finite_nested_float_as_today(root: Path, row: str, code: str) -> None:
    result, commands, _ = _run(root, "2.33", NESTED, answer=_nested_answer(row), x=None)

    status, refused, _ = _refusal(_state(result)[0])
    assert (result.exit_code, status, refused, commands) == (1, "failed", code, ["r"])


# The expected output file boundary, at its validator.

FILE_ROWS = {"NaN": "nan", "Infinity": "inf", "-Infinity": "-inf", "nan": "nan", "inf": "inf", "-inf": "-inf", "1e400": "inf"}


def _expected_output(root: Path, text: str, **kwargs) -> float:
    (root / "score.txt").write_text(text, encoding="utf-8")
    contract = [{"name": "score", "path": "score.txt", "type": "float"}]
    return validate_expected_outputs(contract, workspace=root, **kwargs)["score"]


@pytest.mark.parametrize("row", FILE_ROWS)
def test_finite_floats_refuse_a_non_finite_expected_output_file(tmp_path: Path, row: str) -> None:
    with pytest.raises(OutputContractError) as excinfo:
        _expected_output(tmp_path, row, finite_floats=True)

    (violation,) = excinfo.value.violations
    assert (violation["type"], violation["context"]) == (
        "float_not_finite", {"value": FILE_ROWS[row], "path": "score.txt"}
    )  # fmt: skip


@pytest.mark.parametrize("value", FINITE)
def test_finite_floats_pass_a_finite_expected_output_file_unchanged(tmp_path: Path, value: str) -> None:
    assert _same(_expected_output(tmp_path, value, finite_floats=True), value)


@pytest.mark.parametrize("row", FILE_ROWS)
def test_an_expected_output_file_keeps_todays_non_finite_values_by_default(tmp_path: Path, row: str) -> None:
    assert _same(_expected_output(tmp_path, row), FILE_ROWS[row])
