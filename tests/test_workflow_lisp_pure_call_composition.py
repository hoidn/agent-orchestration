"""Legacy-characterization and target-2.30 regression coverage for EC-1."""

from __future__ import annotations

import hashlib
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.run import run_workflow
from orchestrator.workflow import pure_expr as runtime_pure_expr
from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.steps import pure_projection as runtime_pure_projection_step
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    compile_stage3_module,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import ProcedureCallExpr
from orchestrator.workflow_lisp.syntax import HelperExpansionFrame, ProcedureExpansionFrame
from tests.test_workflow_lisp_lexical_checkpoint_restore import (
    TRANSITION_RESUME_FIXTURE_SOURCE,
)


PREPARATION = Path(__file__).parent / "fixtures" / "workflow_lisp" / "pure_call_composition_preparation"


def _fixture_at_current_target(fixture_name: str, *, workspace: Path) -> Path:
    source = (PREPARATION / f"{fixture_name}.orc").read_text(encoding="utf-8")
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / f"{fixture_name}_target_229.orc"
    path.write_text(source.replace('(:target-dsl "2.27")', '(:target-dsl "2.29")'), encoding="utf-8")
    return path


def _fixture_at_target_230(fixture_name: str, *, workspace: Path) -> Path:
    source = (PREPARATION / f"{fixture_name}.orc").read_text(encoding="utf-8")
    workspace.mkdir(parents=True, exist_ok=True)
    path = workspace / f"{fixture_name}_target_230.orc"
    path.write_text(
        source.replace('(:target-dsl "2.27")', '(:target-dsl "2.30")'),
        encoding="utf-8",
    )
    return path


def _compile(path: Path, *, workspace: Path):
    return compile_stage3_module(
        path,
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=workspace,
    )


def _run(path: Path, *, workspace: Path, inputs: dict[str, object]) -> dict[str, object]:
    bundle = _compile(path, workspace=workspace).validated_bundles["orchestrate"]
    state_manager = StateManager(workspace=workspace, run_id=path.stem)
    state_manager.initialize(path.as_posix(), bound_inputs=inputs)
    return WorkflowExecutor(bundle, workspace, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )


@pytest.mark.parametrize(
    ("fixture_name", "diagnostic_code"),
    (
        ("early_defun_rejection", "pure_function_has_effect"),
        ("uncalled_generic_function_specialization", "pure_function_has_effect"),
        ("aggregate_map_rejection", "effect_not_permitted"),
        ("once_only_hygienic_arguments", "effect_not_permitted"),
        ("map_short_circuit_and_proc_rejection", "list_map_body_effect_forbidden"),
        ("map_short_circuit_or_proc_rejection", "list_map_body_effect_forbidden"),
    ),
)
def test_task5_current_target_red_probes_name_the_pre_normalization_blocker(
    tmp_path: Path,
    fixture_name: str,
    diagnostic_code: str,
) -> None:
    """These rejections are Task-5 evidence, not expected Task-6 behavior."""

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            _fixture_at_current_target(fixture_name, workspace=tmp_path),
            workspace=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == diagnostic_code


def test_task5_legacy_defun_probes_are_diagnostic_not_semantic_controls(tmp_path: Path) -> None:
    values = _run(
        _fixture_at_current_target("defun_argument_control", workspace=tmp_path),
        workspace=tmp_path,
        inputs={"x": 9},
    )
    ignored_argument = _run(
        _fixture_at_current_target("eager_ignored_argument_control", workspace=tmp_path),
        workspace=tmp_path,
        inputs={"child": "../escape"},
    )

    assert values["workflow_outputs"] == {
        "return__duplicated": 18,
        "return__ignored": 9,
        "return__captured": 2,
    }
    assert ignored_argument["workflow_outputs"] == {"__result__": "../escape"}


@pytest.mark.parametrize(
    ("fixture_name", "expected"),
    (
        ("map_short_circuit_skip_control", [False]),
        ("map_short_circuit_or_control", [True]),
    ),
)
def test_task5_authored_condition_controls_skip_fallible_map_work(
    tmp_path: Path,
    fixture_name: str,
    expected: list[bool],
) -> None:
    nonempty = _run(
        _fixture_at_current_target(fixture_name, workspace=tmp_path),
        workspace=tmp_path,
        inputs={"children": ["../escape"]},
    )
    empty = _run(
        _fixture_at_current_target(fixture_name, workspace=tmp_path / "empty"),
        workspace=tmp_path / "empty",
        inputs={"children": []},
    )

    assert nonempty["workflow_outputs"] == {"__result__": expected}
    assert empty["workflow_outputs"] == {"__result__": []}


def test_task5_explicit_bindings_preserve_dynamic_capture_and_force_fallible_values(
    tmp_path: Path,
) -> None:
    source = tmp_path / "explicit_bindings.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.29")',
                "  (defrecord Result (duplicated Int) (ignored Int) (captured Int))",
                "  (defrecord EagerResult (checked Path.state-root) (value String))",
                "  (defworkflow values ((x Int)) -> Result",
                "    (let* ((duplicate-argument (+ x 1))",
                "           (ignored-argument (+ x 2))",
                "           (captured-y x))",
                "      (record Result",
                "        :duplicated (+ duplicate-argument duplicate-argument)",
                "        :ignored captured-y",
                "        :captured captured-y)))",
                "  (defworkflow eager ((child String)) -> EagerResult",
                "    (let* ((checked (path/join-under Path.state-root child))",
                "           (value child))",
                "      (record EagerResult :checked checked :value value))))",
            )
        ),
        encoding="utf-8",
    )
    result = _compile(source, workspace=tmp_path)

    values_bundle = result.validated_bundles["values"]
    values_state = StateManager(workspace=tmp_path, run_id="explicit-values")
    values_state.initialize(source.as_posix(), bound_inputs={"x": 9})
    values = WorkflowExecutor(
        values_bundle, tmp_path, values_state, retry_delay_ms=0
    ).execute(on_error="stop")

    eager_bundle = result.validated_bundles["eager"]
    eager_state = StateManager(workspace=tmp_path, run_id="explicit-eager")
    eager_state.initialize(source.as_posix(), bound_inputs={"child": "../escape"})
    eager = WorkflowExecutor(
        eager_bundle, tmp_path, eager_state, retry_delay_ms=0
    ).execute(on_error="stop")

    assert values["workflow_outputs"] == {
        "return__duplicated": 20,
        "return__ignored": 9,
        "return__captured": 9,
    }
    assert eager["status"] == "failed"


def test_task5_imported_nested_call_is_currently_rejected_before_normalization(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "pure_helpers.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.29")',
                "  (defmodule pure_helpers)",
                "  (export increment)",
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1)))",
            )
        ),
        encoding="utf-8",
    )
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.29")',
                "  (defmodule entry)",
                "  (import pure_helpers :only (increment))",
                "  (export orchestrate)",
                "  (defun twice ((value Int)) -> Int (increment (increment value)))",
                "  (defworkflow orchestrate ((value Int)) -> Int (twice value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_target_230_is_admitted_before_pure_call_composition_is_checked(
    tmp_path: Path,
) -> None:
    source = tmp_path / "target_230_gate.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defworkflow orchestrate () -> Int 1))",
            )
        ),
        encoding="utf-8",
    )

    assert _compile(source, workspace=tmp_path).validated_bundles["orchestrate"]


def test_target_230_expands_nested_inline_procedure_calls_in_a_function(
    tmp_path: Path,
) -> None:
    path = _fixture_at_target_230("early_defun_rejection", workspace=tmp_path)

    result = _run(path, workspace=tmp_path, inputs={"value": 9})

    assert result["workflow_outputs"] == {"__result__": 11}


def test_target_230_compiles_ordered_bindings_for_repeated_and_unused_arguments(
    tmp_path: Path,
) -> None:
    source = tmp_path / "compiled_ordered_arguments.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc twice ((value Int)) -> Int",
                "    :effects () :lowering inline (+ value value))",
                "  (defproc ignore-check ((checked Path.state-root) (value String)) -> String",
                "    :effects () :lowering inline value)",
                "  (defun repeat-call ((value Int)) -> Int (twice (+ value 1)))",
                "  (defun eager-call ((child String)) -> String",
                "    (ignore-check (path/join-under Path.state-root child) child))",
                "  (defworkflow repeated ((value Int)) -> Int (repeat-call value))",
                "  (defworkflow eager ((child String)) -> String (eager-call child)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = _compile(source, workspace=tmp_path)
    repeated_state = StateManager(workspace=tmp_path, run_id="compiled-repeated")
    repeated_state.initialize(source.as_posix(), bound_inputs={"value": 9})
    repeated = WorkflowExecutor(
        compiled.validated_bundles["repeated"], tmp_path, repeated_state, retry_delay_ms=0
    ).execute(on_error="stop")
    eager_state = StateManager(workspace=tmp_path, run_id="compiled-eager")
    eager_state.initialize(source.as_posix(), bound_inputs={"child": "../escape"})
    eager = WorkflowExecutor(
        compiled.validated_bundles["eager"], tmp_path, eager_state, retry_delay_ms=0
    ).execute(on_error="stop")

    assert repeated["workflow_outputs"] == {"__result__": 20}
    assert eager["status"] == "failed"


@pytest.mark.parametrize(
    ("definition", "callable_kind", "record_definitions", "box_fields", "box_values"),
    (
        (
            "  (defun ignore-box ((box Box)) -> Int 7)",
            "function",
            (),
            "(value Int)",
            ":value (+ n 1)",
        ),
        (
            "  (defproc ignore-box ((box Box)) -> Int\n"
            "    :effects () :lowering inline 7)",
            "procedure",
            (),
            "(value Int)",
            ":value (+ n 1)",
        ),
        (
            "  (defun ignore-box ((box Box)) -> Int 7)",
            "function",
            ("  (defrecord Inner (x Int))",),
            "(value Int) (raw Int) (inner Inner)",
            ":value (+ n 1) :raw n :inner (record Inner :x 1)",
        ),
        (
            "  (defproc ignore-box ((box Box)) -> Int\n"
            "    :effects () :lowering inline 7)",
            "procedure",
            ("  (defrecord Inner (x Int))",),
            "(value Int) (raw Int) (inner Inner)",
            ":value (+ n 1) :raw n :inner (record Inner :x 1)",
        ),
    ),
)
def test_target_230_projects_deferred_structured_actual_before_inline_call(
    tmp_path: Path,
    definition: str,
    callable_kind: str,
    record_definitions: tuple[str, ...],
    box_fields: str,
    box_values: str,
) -> None:
    """Deferred, reference, and nested record fields stay eager and typed."""

    source = tmp_path / f"deferred_box_{callable_kind}.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                *record_definitions,
                f"  (defrecord Box {box_fields})",
                definition,
                "  (defworkflow orchestrate ((n Int)) -> Int",
                f"    (let* ((box (record Box {box_values})))",
                "      (ignore-box box))))",
            )
        ),
        encoding="utf-8",
    )

    assert _run(source, workspace=tmp_path, inputs={"n": 4})["workflow_outputs"] == {
        "__result__": 7
    }


def test_target_230_preserves_authored_record_field_named_ref(
    tmp_path: Path,
) -> None:
    """A complete record mapping is data even when its only field is `ref`."""

    source = tmp_path / "authored_ref_field.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Box (ref String))",
                "  (defun ignore-box ((box Box)) -> Int 7)",
                "  (defworkflow orchestrate ((text String)) -> Int",
                "    (let* ((box (record Box :ref text))) (ignore-box box))))",
            )
        ),
        encoding="utf-8",
    )

    compiled = _compile(source, workspace=tmp_path)
    payloads = [
        step.pure_projection["payload"]
        for step in compiled.validated_bundles["orchestrate"].surface.steps
        if step.pure_projection is not None
    ]
    assert any(
        payload["expr"].get("kind") == "record"
        and [field["name"] for field in payload["expr"]["fields"]] == ["ref"]
        for payload in payloads
    )

    state = StateManager(workspace=tmp_path, run_id="authored-ref-field")
    state.initialize(source.as_posix(), bound_inputs={"text": "kept-as-data"})
    assert WorkflowExecutor(
        compiled.validated_bundles["orchestrate"], tmp_path, state, retry_delay_ms=0
    ).execute(on_error="stop")[
        "workflow_outputs"
    ] == {"__result__": 7}


def test_target_230_evaluates_compiler_owned_arguments_once_before_nonterminal_continuations(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generated call lets remain eager before control, private, and provider tails."""

    source = tmp_path / "nonterminal_ordered_arguments.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Box (value String))",
                "  (defproc ignore-path ((checked Path.state-root) (value String)) -> String",
                "    :effects () :lowering inline value)",
                "  (defproc private-pass ((value String)) -> Box",
                "    :effects () :lowering private-workflow (record Box :value value))",
                "  (defun ignored ((child String)) -> String",
                "    (ignore-path (path/join-under Path.state-root child) child))",
                "  (defworkflow control ((child String)) -> Int",
                "    (let* ((ignored-value (ignored child))) (if true 1 2)))",
                "  (defworkflow private ((child String)) -> Box",
                "    (let* ((ignored-value (ignored child))) (private-pass child)))",
                "  (defworkflow provider ((child String)) -> String",
                "    (let* ((ignored-value (ignored child)))",
                "      (provider-result providers.execute :prompt prompts.execute",
                "        :inputs () :returns String))))",
            )
        ),
        encoding="utf-8",
    )
    compiled = compile_stage3_module(
        source,
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=tmp_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.execute": "prompt.md"},
    )
    calls: list[str] = []
    original_join = runtime_pure_expr._join_relative_child_under_root
    evaluated: list[str] = []

    def count_join(root, child, *, path_type_name):
        evaluated.append(child)
        return original_join(root, child, path_type_name=path_type_name)

    monkeypatch.setattr(runtime_pure_expr, "_join_relative_child_under_root", count_join)

    def prepare(_self, provider_name, *args, **kwargs):
        return (
            SimpleNamespace(
                provider_name=provider_name,
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def execute(_self, invocation, **_kwargs):
        calls.append(invocation.provider_name)
        return SimpleNamespace(
            exit_code=0,
            stdout=b"provider-result",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=b"",
            normalized_stdout=None,
            provider_session=None,
        )

    for workflow_name in ("control", "private", "provider"):
        state = StateManager(workspace=tmp_path, run_id=f"nonterminal-{workflow_name}")
        state.initialize(source.as_posix(), bound_inputs={"child": "../escape"})
        with (
            patch.object(ProviderExecutor, "prepare_invocation", prepare),
            patch.object(ProviderExecutor, "execute", execute),
        ):
            result = WorkflowExecutor(
                compiled.validated_bundles[workflow_name],
                tmp_path,
                state,
                retry_delay_ms=0,
            ).execute(on_error="stop")
        assert result["status"] == "failed"
    assert calls == []
    assert evaluated == ["../escape", "../escape", "../escape"]


def test_target_230_evaluates_dynamic_actuals_once_when_formals_repeat_or_ignore(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "counted_ordered_arguments.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Pair (first Path.state-root) (second Path.state-root))",
                "  (defproc duplicate-path ((value Path.state-root)) -> Pair",
                "    :effects () :lowering inline",
                "    (record Pair :first value :second value))",
                "  (defproc ignore-path ((value Path.state-root)) -> Int",
                "    :effects () :lowering inline 7)",
                "  (defun repeat-actual ((child String)) -> Pair",
                "    (duplicate-path (path/join-under Path.state-root child)))",
                "  (defun ignore-actual ((child String)) -> Int",
                "    (ignore-path (path/join-under Path.state-root child)))",
                "  (defworkflow repeated ((child String)) -> Pair (repeat-actual child))",
                "  (defworkflow ignored ((child String)) -> Int (ignore-actual child)))",
            )
        ),
        encoding="utf-8",
    )
    compiled = _compile(source, workspace=tmp_path)
    original_join = runtime_pure_expr._join_relative_child_under_root
    evaluated: list[str] = []

    def count_join(root, child, *, path_type_name):
        evaluated.append(child)
        return original_join(root, child, path_type_name=path_type_name)

    monkeypatch.setattr(runtime_pure_expr, "_join_relative_child_under_root", count_join)
    for workflow_name in ("repeated", "ignored"):
        state = StateManager(workspace=tmp_path, run_id=f"counted-{workflow_name}")
        state.initialize(source.as_posix(), bound_inputs={"child": "work"})
        result = WorkflowExecutor(
            compiled.validated_bundles[workflow_name],
            tmp_path,
            state,
            retry_delay_ms=0,
        ).execute(on_error="stop")
        assert result["status"] == "completed"
    assert evaluated == ["work", "work"]


def test_target_230_preserves_nested_let_shadowing_in_compiler_owned_calls(
    tmp_path: Path,
) -> None:
    source = tmp_path / "nested_compiler_let_shadow.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defun expanded-shadow ((n Int)) -> Int",
                "    (let* ((x n) (y (let* ((x (+ x 1))) x))) (+ x y)))",
                "  (defworkflow orchestrate ((value Int)) -> Int",
                "    (expanded-shadow value)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = _compile(source, workspace=tmp_path)
    payloads = [
        step.pure_projection["payload"]
        for step in compiled.validated_bundles["orchestrate"].surface.steps
        if step.pure_projection is not None
    ]
    assert any(
        payload["pure_expr_schema_version"] == 3
        and payload["expr"]["kind"] == "let"
        for payload in payloads
    )
    state = StateManager(workspace=tmp_path, run_id="nested-compiler-let-shadow")
    state.initialize(source.as_posix(), bound_inputs={"value": 3})
    assert WorkflowExecutor(
        compiled.validated_bundles["orchestrate"], tmp_path, state, retry_delay_ms=0
    ).execute(on_error="stop")["workflow_outputs"] == {
        "__result__": 7
    }


def test_target_230_preserves_different_type_nested_shadowing_in_a_defun(
    tmp_path: Path,
) -> None:
    source = tmp_path / "different_type_compiler_let_shadow.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defun expanded-shadow ((n Int)) -> Int",
                "    (let* ((x n) (y (let* ((x \"note\")) 1))) (+ x y)))",
                "  (defworkflow orchestrate ((value Int)) -> Int",
                "    (expanded-shadow value)))",
            )
        ),
        encoding="utf-8",
    )

    assert _run(source, workspace=tmp_path, inputs={"value": 3})["workflow_outputs"] == {
        "__result__": 4
    }


def test_target_230_preserves_defun_only_call_bindings_and_call_origins(
    tmp_path: Path,
) -> None:
    source = tmp_path / "defun_call_origins.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defun increment ((value Int)) -> Int (+ value 1))",
                "  (defun decrement ((value Int)) -> Int (- value 1))",
                "  (defworkflow orchestrate ((value Int)) -> Int",
                "    (+ (increment value) (decrement value))))",
            )
        ),
        encoding="utf-8",
    )
    compiled = _compile(source, workspace=tmp_path)
    projection_step_names = [
        step.name
        for step in compiled.validated_bundles["orchestrate"].surface.steps
        if step.pure_projection is not None
    ]
    origins = tuple(compiled.lowered_workflows[0].origin_map.step_spans.values())

    assert _run(source, workspace=tmp_path, inputs={"value": 8})["workflow_outputs"] == {
        "__result__": 16
    }
    helper_names = {
        frame.function_name
        for origin in origins
        for frame in origin.expansion_stack
        if isinstance(frame, HelperExpansionFrame)
    }
    assert {"increment", "decrement"} <= helper_names
    assert len(projection_step_names) == len(set(projection_step_names))
    assert not any("__pure_function_param" in name for name in projection_step_names)


def test_target_230_retains_selected_pure_callee_provenance(tmp_path: Path) -> None:
    compiled = _compile(
        _fixture_at_target_230("early_defun_rejection", workspace=tmp_path),
        workspace=tmp_path,
    )

    frames = [
        frame
        for workflow in compiled.typed_workflows
        for node in walk_expr(workflow.typed_body.expr)
        for frame in node.expansion_stack
        if isinstance(frame, ProcedureExpansionFrame)
    ]

    assert any(frame.procedure_name == "increment" for frame in frames)


def test_pure_call_builds_are_repeatable_without_changing_pre_230_plans(
    tmp_path: Path,
) -> None:
    composed = tmp_path / "repeatable_composed.orc"
    composed.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc increment ((value Int)) -> Int",
                "    :effects () :lowering inline (+ value 1))",
                "  (defun wrapped ((value Int)) -> Int (increment value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )
    legacy = tmp_path / "repeatable_legacy.orc"
    legacy.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.29")',
                "  (defworkflow orchestrate ((value Int)) -> Int (+ value 1)))",
            )
        ),
        encoding="utf-8",
    )

    first_composed = _compile(composed, workspace=tmp_path)
    second_composed = _compile(composed, workspace=tmp_path)
    first_legacy = _compile(legacy, workspace=tmp_path)
    second_legacy = _compile(legacy, workspace=tmp_path)

    assert first_composed.validated_bundles["orchestrate"] == second_composed.validated_bundles[
        "orchestrate"
    ]
    assert first_legacy.validated_bundles["orchestrate"] == second_legacy.validated_bundles[
        "orchestrate"
    ]
    assert first_legacy.lowered_workflows == second_legacy.lowered_workflows


def test_pre_230_phase_resource_ref_wrapper_matches_clean_baseline_identity(
    tmp_path: Path,
) -> None:
    """Legacy transition request refs keep the base executable IR bytes."""

    control_path = PREPARATION / "early_defun_rejection.orc"
    original_read_bytes = Path.read_bytes

    def read_control(path: Path) -> bytes:
        return (
            TRANSITION_RESUME_FIXTURE_SOURCE.encode()
            if path == control_path
            else original_read_bytes(path)
        )

    with patch.object(Path, "read_bytes", read_control):
        bundle = _compile(control_path, workspace=tmp_path).validated_bundles[
            "orchestrate"
        ]
    executable_ir = workflow_executable_ir_to_json(bundle.ir)
    digest = hashlib.sha256(
        json.dumps(executable_ir, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    # Captured independently from the detached clean base worktree at 5e4e761a.
    assert digest == "33425ece652adec050da4b34ad20f506f2dccb8e87060608c8e1c3045bb39f8a"


def test_target_230_materializes_uncalled_function_procedure_specializations(
    tmp_path: Path,
) -> None:
    result = _compile(
        _fixture_at_target_230(
            "uncalled_generic_function_specialization", workspace=tmp_path
        ),
        workspace=tmp_path,
    )

    assert any(
        procedure.definition.name.startswith("%parametric-call.identity.")
        for procedure in result.typed_procedures
    )


def test_target_230_expands_selected_pure_hook_in_its_specialized_environment(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_pure_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1))",
                "  (defproc apply-hook",
                "    :forall (T)",
                "    ((hook ProcRef[T -> T]) (value T)) -> T",
                "    :effects () :lowering inline",
                "    (hook value))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (apply-hook (proc-ref increment) value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = _compile(source, workspace=tmp_path)
    generic_base = next(
        procedure
        for procedure in compiled.typed_procedures
        if procedure.definition.name == "apply-hook"
    )
    assert isinstance(generic_base.typed_body.expr, ProcedureCallExpr)
    assert generic_base.typed_body.expr.callee_name == "hook"

    bundle = compiled.validated_bundles["orchestrate"]
    state = StateManager(workspace=tmp_path, run_id="selected-pure-hook")
    state.initialize(source.as_posix(), bound_inputs={"value": 8})
    executed = WorkflowExecutor(bundle, tmp_path, state, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert executed["workflow_outputs"] == {"__result__": 9}


def test_target_230_expands_nonparametric_selected_pure_hook_not_its_template(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_nonparametric_pure_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1))",
                "  (defproc apply-hook",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline",
                "    (hook value))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (apply-hook (proc-ref increment) value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    executed = _run(source, workspace=tmp_path, inputs={"value": 8})

    assert executed["workflow_outputs"] == {"__result__": 9}


def test_target_230_selects_all_proc_ref_arguments_as_one_materialized_row(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_two_hooks.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Result (same Int) (mixed Int))",
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1))",
                "  (defproc decrement ((value Int)) -> Int :effects () :lowering inline (- value 1))",
                "  (defproc apply-two",
                "    ((first ProcRef[Int -> Int]) (second ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline (first (second value)))",
                "  (defun paired ((value Int)) -> Result",
                "    (let* ((same (apply-two (proc-ref increment) (proc-ref increment) value))",
                "           (mixed (apply-two (proc-ref increment) (proc-ref decrement) value)))",
                "      (record Result :same same :mixed mixed)))",
                "  (defworkflow orchestrate ((value Int)) -> Result (paired value)))",
            )
        ),
        encoding="utf-8",
    )

    executed = _run(source, workspace=tmp_path, inputs={"value": 8})

    assert executed["workflow_outputs"] == {"return__same": 10, "return__mixed": 8}


def test_target_230_expands_selected_bind_proc_hook_with_runtime_residual(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_bound_pure_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc add-leading ((leading Int) (value Int)) -> Int",
                "    :effects () :lowering inline (+ leading value))",
                "  (defproc apply-hook",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline (hook value))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (let* ((hook (bind-proc (proc-ref add-leading) :leading 2)))",
                "      (apply-hook hook value)))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = _compile(source, workspace=tmp_path)
    selected_apply_hook = next(
        procedure
        for procedure in compiled.typed_procedures
        if getattr(procedure.specialization, "base_name", None) == "apply-hook"
        and "hook" in procedure.specialization.proc_ref_bindings
    )
    selected_bound_hook = next(
        procedure
        for procedure in compiled.typed_procedures
        if getattr(procedure.specialization, "base_name", None) == "add-leading"
        and "leading" in procedure.specialization.value_bindings
    )
    assert (
        selected_apply_hook.specialization.proc_ref_bindings["hook"].call_target_name
        == selected_bound_hook.definition.name
    )
    assert selected_bound_hook.specialization.value_bindings["leading"].value == 2
    projection_step_names = [
        step.name
        for step in compiled.validated_bundles["orchestrate"].surface.steps
        if step.pure_projection is not None
    ]
    selected_frames = [
        frame
        for lowered in compiled.lowered_workflows
        for origin in lowered.origin_map.step_spans.values()
        for frame in origin.expansion_stack
        if isinstance(frame, ProcedureExpansionFrame)
        and frame.procedure_name == selected_bound_hook.definition.name
    ]
    assert selected_frames
    assert all(
        frame.definition_span == selected_bound_hook.definition.span
        for frame in selected_frames
    )
    # Formal aliases are direct references to the materialized actual, not
    # additional projection bundles.  The selected hook still remains visible
    # on the projection origins that do materialize its bound leading value.
    assert not any("__pure_procedure_param" in name for name in projection_step_names)

    bundle = compiled.validated_bundles["orchestrate"]
    state = StateManager(workspace=tmp_path, run_id="selected-bound-pure-hook")
    state.initialize(source.as_posix(), bound_inputs={"value": 8})
    executed = WorkflowExecutor(bundle, tmp_path, state, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert executed["workflow_outputs"] == {"__result__": 10}


def test_target_230_provisionally_admits_nested_procedure_calls_in_function_records(
    tmp_path: Path,
) -> None:
    source = tmp_path / "function_record_procedure_call.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Box (value Int))",
                "  (defproc increment ((value Int)) -> Int",
                "    :effects () :lowering inline (+ value 1))",
                "  (defun boxed ((value Int)) -> Box",
                "    (record Box :value (increment value)))",
                "  (defworkflow orchestrate ((value Int)) -> Box (boxed value)))",
            )
        ),
        encoding="utf-8",
    )

    executed = _run(source, workspace=tmp_path, inputs={"value": 8})

    assert executed["workflow_outputs"] == {"return__value": 9}


def test_target_230_rechecks_uncalled_effectful_functions(tmp_path: Path) -> None:
    source = tmp_path / "uncalled_effectful.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc provider-backed ((value Int)) -> Int",
                "    :effects ((uses-provider providers.execute))",
                "    :lowering inline",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute :inputs (value) :returns Int))",
                "  (defun uncalled ((value Int)) -> Int (provider-backed value))",
                "  (defworkflow orchestrate ((value Int)) -> Int value))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            source,
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_target_230_rechecks_uncalled_effectful_functions_in_linked_modules(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "helper.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defmodule helper)",
                "  (export identity)",
                "  (defproc provider-backed ((value Int)) -> Int",
                "    :effects ((uses-provider providers.execute)) :lowering inline",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute :inputs (value) :returns Int))",
                "  (defun uncalled ((value Int)) -> Int (provider-backed value))",
                "  (defun identity ((value Int)) -> Int value))",
            )
        ),
        encoding="utf-8",
    )
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defmodule entry)",
                "  (import helper :only (identity))",
                "  (export orchestrate)",
                "  (defworkflow orchestrate ((value Int)) -> Int (identity value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_target_230_rechecks_uncalled_private_functions(tmp_path: Path) -> None:
    source = tmp_path / "uncalled_private.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Box (value Int))",
                "  (defproc private ((value Int)) -> Box",
                "    :effects () :lowering private-workflow (record Box :value value))",
                "  (defun uncalled ((value Int)) -> Box (private value))",
                "  (defworkflow orchestrate ((value Int)) -> Int value))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(source, workspace=tmp_path)

    assert excinfo.value.diagnostics[0].code == "pure_call_representation_unsupported"


def test_target_230_keeps_selected_hook_arguments_when_effectful_call_is_not_inlined(
    tmp_path: Path,
) -> None:
    """A non-inline call retains its authored call shape after selection."""

    source = tmp_path / "effectful_selected_hook_arguments.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc increment ((value Int)) -> Int",
                "    :effects () :lowering inline (+ value 1))",
                "  (defproc effectful-apply",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects ((uses-provider providers.execute)) :lowering auto",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute :inputs (value) :returns Int))",
                "  (defworkflow orchestrate ((value Int)) -> Int",
                "    (effectful-apply (proc-ref increment) value)))",
            )
        ),
        encoding="utf-8",
    )

    compiled = compile_stage3_module(
        source,
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=tmp_path,
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={"prompts.implementation.execute": "prompt.md"},
    )

    assert "orchestrate" in compiled.validated_bundles


def test_target_230_leaves_unresolved_generic_hook_template_unexpanded(
    tmp_path: Path,
) -> None:
    """The generic base is checked but does not claim template-hook purity."""

    source = tmp_path / "generic_hook_template.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc apply-hook",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline (hook value))",
                "  (defun outer ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    (apply-hook hook value))",
                "  (defproc increment ((value Int)) -> Int",
                "    :effects () :lowering inline (+ value 1))",
                "  (defworkflow orchestrate ((value Int)) -> Int",
                "    (outer (proc-ref increment) value)))",
            )
        ),
        encoding="utf-8",
    )

    executed = _run(source, workspace=tmp_path, inputs={"value": 8})

    assert executed["workflow_outputs"] == {"__result__": 9}


def test_target_230_reports_unrepresentable_selected_body_without_clone_crash(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unrepresentable_selected_body.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Box (value Int))",
                "  (defworkflow child ((value Int)) -> Box (record Box :value value))",
                "  (defproc helper ((value Int)) -> Int",
                "    :effects () :lowering inline",
                "    (let* ((child-ref (workflow-ref child))) value))",
                "  (defun wrapped ((value Int)) -> Int (helper value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(source, workspace=tmp_path)

    assert excinfo.value.diagnostics[0].code == "pure_call_representation_unsupported"


def test_target_230_rejects_effectful_selected_hook_in_pure_function(
    tmp_path: Path,
) -> None:
    source = tmp_path / "selected_effectful_hook.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defproc effectful ((value Int)) -> Int",
                "    :effects ((uses-provider providers.execute)) :lowering inline",
                "    (provider-result providers.execute",
                "      :prompt prompts.implementation.execute :inputs (value) :returns Int))",
                "  (defproc apply-hook",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline (hook value))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (apply-hook (proc-ref effectful) value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            source,
            lowering_route="wcc_m4",
            validate_shared=True,
            workspace_root=tmp_path,
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={"prompts.implementation.execute": "prompt.md"},
        )

    assert excinfo.value.diagnostics[0].code == "pure_function_has_effect"


def test_target_230_rejects_private_procedure_in_pure_function(
    tmp_path: Path,
) -> None:
    source = tmp_path / "private_pure_call.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defrecord Box (value Int))",
                "  (defproc private ((value Int)) -> Box",
                "    :effects () :lowering private-workflow (record Box :value value))",
                "  (defun wrapped ((value Int)) -> Box (private value))",
                "  (defworkflow orchestrate ((value Int)) -> Box (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(source, workspace=tmp_path)

    assert excinfo.value.diagnostics[0].code == "pure_call_representation_unsupported"


def test_target_230_resolves_imported_inline_procedures_inside_functions(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "pure_helpers.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defmodule pure_helpers)",
                "  (export increment)",
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1)))",
            )
        ),
        encoding="utf-8",
    )
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defmodule entry)",
                "  (import pure_helpers :only (increment))",
                "  (export orchestrate)",
                "  (defun twice ((value Int)) -> Int (increment (increment value)))",
                "  (defworkflow orchestrate ((value Int)) -> Int (twice value)))",
            )
        ),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name["entry::orchestrate"]
    state_manager = StateManager(workspace=tmp_path, run_id="imported-inline")
    state_manager.initialize(entry.as_posix(), bound_inputs={"value": 8})

    executed = WorkflowExecutor(
        bundle, tmp_path, state_manager, retry_delay_ms=0
    ).execute(on_error="stop")

    assert executed["workflow_outputs"] == {"__result__": 10}


def test_target_230_selected_imported_hook_keeps_its_caller_binding(
    tmp_path: Path,
) -> None:
    helper = tmp_path / "helper.orc"
    entry = tmp_path / "entry.orc"
    helper.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defmodule helper)",
                "  (export apply-hook)",
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 1))",
                "  (defproc apply-hook",
                "    ((hook ProcRef[Int -> Int]) (value Int)) -> Int",
                "    :effects () :lowering inline (+ (hook value) (increment 0))))",
            )
        ),
        encoding="utf-8",
    )
    entry.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defmodule entry)",
                "  (import helper :only (apply-hook))",
                "  (export orchestrate)",
                "  (defproc increment ((value Int)) -> Int :effects () :lowering inline (+ value 2))",
                "  (defun wrapped ((value Int)) -> Int",
                "    (apply-hook (proc-ref increment) value))",
                "  (defworkflow orchestrate ((value Int)) -> Int (wrapped value)))",
            )
        ),
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        lowering_route="wcc_m4",
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles_by_name["entry::orchestrate"]
    state = StateManager(workspace=tmp_path, run_id="imported-selected-hook")
    state.initialize(entry.as_posix(), bound_inputs={"value": 8})
    executed = WorkflowExecutor(bundle, tmp_path, state, retry_delay_ms=0).execute(
        on_error="stop"
    )
    resumed_state = StateManager(workspace=tmp_path, run_id="imported-selected-hook")
    resumed_state.load()
    resumed = WorkflowExecutor(
        bundle, tmp_path, resumed_state, retry_delay_ms=0
    ).execute(resume=True, on_error="stop")

    # The selected hook is entry::increment (+2) while the ordinary local
    # reference in helper::apply-hook remains helper::increment (+1).
    assert executed["workflow_outputs"] == {"__result__": 11}
    assert resumed["workflow_outputs"] == {"__result__": 11}


def test_target_230_pure_call_projection_reuses_committed_provider_on_resume(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "entry.orc"
    source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.30")',
                "  (defmodule entry)",
                "  (export orchestrate)",
                "  (defproc increment ((value Int)) -> Int",
                "    :effects () :lowering inline (+ value 1))",
                "  (defun wrapped ((value Int)) -> Int (increment value))",
                "  (defworkflow orchestrate () -> Int",
                "    (let* ((provided (provider-result providers.execute",
                "                       :prompt prompts.implementation.execute",
                "                       :inputs () :returns Int))",
                    "           (prepared (wrapped provided))",
                    "           (consumed (provider-result providers.consume",
                    "                       :prompt prompts.implementation.consume",
                    "                       :inputs (prepared) :returns Int))",
                    "           (finished (provider-result providers.finish",
                    "                       :prompt prompts.implementation.finish",
                    "                       :inputs (consumed) :returns Int)))",
                    "      finished)))",
            )
        ),
        encoding="utf-8",
    )
    for prompt_name in ("execute", "consume", "finish"):
        (tmp_path / f"{prompt_name}.md").write_text(
            "deterministic prompt\n", encoding="utf-8"
        )
    providers = tmp_path / "providers.json"
    providers.write_text(
        '{"providers.execute":"execute","providers.consume":"consume","providers.finish":"finish"}',
        encoding="utf-8",
    )
    prompts = tmp_path / "prompts.json"
    prompts.write_text(
        '{"prompts.implementation.execute":"execute.md","prompts.implementation.consume":"consume.md","prompts.implementation.finish":"finish.md"}',
        encoding="utf-8",
    )

    calls: list[str] = []
    pure_evaluations: list[str] = []
    original_evaluate_pure_expr = runtime_pure_projection_step.evaluate_pure_expr

    def count_pure_evaluation(payload, **kwargs):
        pure_evaluations.append(str(payload["pure_expr_schema_version"]))
        return original_evaluate_pure_expr(payload, **kwargs)

    def prepare(_self, provider_name, *args, **kwargs):
        return (
            SimpleNamespace(
                provider_name=provider_name,
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def execute(_self, invocation, **_kwargs):
        calls.append(invocation.provider_name)
        bundle_path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
        if not bundle_path.is_absolute():
            bundle_path = tmp_path / bundle_path
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        value = {"execute": 8, "consume": 9, "finish": 10}[invocation.provider_name]
        bundle_path.write_text(f"{value}\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"sidecar",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    original_checkpoint_hook = (
        WorkflowExecutor._emit_lexical_checkpoint_shadow_after_step_commit
    )
    interrupted = False

    class _PostCommitInterruption(BaseException):
        pass

    def interrupt_after_provider_checkpoint(self, state, step_name, step, finalized):
        nonlocal interrupted
        original_checkpoint_hook(self, state, step_name, step, finalized)
        if step_name == "entry::orchestrate__consumed" and not interrupted:
            interrupted = True
            raise _PostCommitInterruption

    run_args = Namespace(
        workflow=str(source), context=None, context_file=None, input=[], input_file=None,
        clean_processed=False, archive_processed=None, debug=False, stream_output=False,
        dry_run=False, backup_state=False, state_dir=None, on_error="stop",
        max_retries=0, retry_delay=0, quiet=True, verbose=False, log_level="error",
        step_summaries=False, summary_mode=None, summary_provider="claude_sonnet_summary",
        summary_timeout_sec=120, summary_max_input_chars=12000, summary_profile=None,
        live_agent_notes=False, live_agent_note_provider=None,
        live_agent_note_interval_sec=15.0, live_agent_note_timeout_sec=30,
        live_agent_note_max_tail_chars=6000, entry_workflow="orchestrate",
        source_root=[str(tmp_path)], provider_externs_file=str(providers),
        prompt_externs_file=str(prompts), imported_workflow_bundles_file=None,
        command_boundaries_file=None, emit_debug_yaml=True,
    )

    monkeypatch.chdir(tmp_path)
    with (
        patch.object(ProviderExecutor, "prepare_invocation", prepare),
        patch.object(ProviderExecutor, "execute", execute),
        patch.object(
            runtime_pure_projection_step,
            "evaluate_pure_expr",
            count_pure_evaluation,
        ),
        patch.object(
            WorkflowExecutor,
            "_emit_lexical_checkpoint_shadow_after_step_commit",
            interrupt_after_provider_checkpoint,
        ),
        patch.object(
            sys,
            "argv",
            [
                "orchestrator", "run", str(source), "--source-root", str(tmp_path),
                "--entry-workflow", "orchestrate", "--provider-externs-file", str(providers),
                "--prompt-externs-file", str(prompts), "--emit-debug-yaml",
            ],
        ),
    ):
        with pytest.raises(_PostCommitInterruption):
            run_workflow(
                run_args,
                run_id="pure-call-provider-resume",
            )

    assert calls == ["execute", "consume"]
    state_before_resume = json.loads(
        (tmp_path / ".orchestrate" / "runs" / "pure-call-provider-resume" / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert state_before_resume["steps"]["entry::orchestrate__provided"]["artifacts"] == {
        "__result__": 8
    }
    assert state_before_resume["steps"]["entry::orchestrate__consumed"]["artifacts"] == {
        "__result__": 9
    }
    prepared_keys = [
        name
        for name in state_before_resume["steps"]
        if name.startswith("entry::orchestrate__prepared__scope_")
    ]
    assert len(prepared_keys) == 1
    assert state_before_resume["steps"][prepared_keys[0]]["result_storage"] == (
        "derived_pure_replay.v1"
    )
    with (
        patch.object(ProviderExecutor, "prepare_invocation", prepare),
        patch.object(ProviderExecutor, "execute", execute),
        patch.object(
            runtime_pure_projection_step,
            "evaluate_pure_expr",
            count_pure_evaluation,
        ),
    ):
        assert resume_workflow(run_id="pure-call-provider-resume", retry_delay_ms=0) == 0

    resumed = json.loads(
        (tmp_path / ".orchestrate" / "runs" / "pure-call-provider-resume" / "state.json").read_text(
            encoding="utf-8"
        )
    )
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": 10}
    assert calls == ["execute", "consume", "finish"]
    assert len(pure_evaluations) == 1


@pytest.mark.parametrize(
    ("fixture_name", "inputs", "expected"),
    (
        (
            "aggregate_map_rejection",
            {"seed": 5, "values": [1, 2]},
            {"return__seed": 6, "return__values": [2, 3]},
        ),
        (
            "once_only_hygienic_arguments",
            {"x": 9},
            {"return__duplicated": 20, "return__ignored": 9, "return__captured": 9},
        ),
        (
            "map_short_circuit_and_proc_rejection",
            {"children": ["../escape"]},
            {"__result__": [False]},
        ),
        (
            "map_short_circuit_or_proc_rejection",
            {"children": ["../escape"]},
            {"__result__": [True]},
        ),
    ),
)
def test_target_230_inlines_pure_calls_in_values_and_short_circuit_map_conditions(
    tmp_path: Path,
    fixture_name: str,
    inputs: dict[str, object],
    expected: dict[str, object],
) -> None:
    result = _run(
        _fixture_at_target_230(fixture_name, workspace=tmp_path),
        workspace=tmp_path,
        inputs=inputs,
    )

    assert result["workflow_outputs"] == expected
