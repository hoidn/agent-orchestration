from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from tests.workflow_lisp_closed_program_helpers import TARGET, install


def test_bound_proc_reference_executes_merged_specialization_after_readback(
    tmp_path: Path,
) -> None:
    source_path = install(
        tmp_path,
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule cp/bound) (export run)
          (defproc helper ((fixed Int) (x Int)) -> Int
            :effects () :lowering inline (+ fixed x))
          (defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int
            :effects () :lowering inline (runner x))
          (defworkflow run ((x Int)) -> Int
            (invoke (bind-proc (proc-ref helper) :fixed 3) x)))''',
    )
    typed = compile_typed_program(
        source_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    source_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())

    result = evaluate_closed_program(program, {"x": 4})

    assert result.json_value() == 7


@pytest.mark.parametrize("nested", (False, True))
def test_runtime_proc_reference_captures_execute_after_source_free_readback(
    tmp_path: Path,
    nested: bool,
) -> None:
    from tests.test_workflow_lisp_closed_program_names import (
        _typed_runtime_capture_program,
    )

    typed, _definition, _int_type = _typed_runtime_capture_program(
        tmp_path,
        nested=nested,
        shifted=False,
    )
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())

    result = evaluate_closed_program(program, {"x": 4})

    assert result.json_value() == 8


@pytest.mark.parametrize("choice", (False, True))
def test_same_named_local_capture_branches_execute_after_source_free_readback(
    tmp_path: Path,
    choice: bool,
) -> None:
    from tests.test_workflow_lisp_closed_program_frontend import _install

    source_path = _install(tmp_path, "local_proc_specializations")
    typed = compile_typed_program(
        source_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    source_path.unlink()
    program = ClosedProgram.from_artifact(build_closed_program(typed).artifact())

    result = evaluate_closed_program(program, {"choice": choice, "input": 4})

    assert result.json_value() == 11
