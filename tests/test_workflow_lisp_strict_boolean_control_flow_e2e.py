"""End-to-end acceptance for target-2.26 strict Boolean condition normalization.

Compiles real `.orc` conditions with effectful operands, runs them through the
executor, and proves left-to-right exactly-once execution, dynamic
short-circuit skipping (durable ``status: skipped`` rows with no visit,
attempt, checkpoint, or execution-value payload), and that a forced failure
after the condition settles is resumed without repeating the settled effect.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from tests.workflow_bundle_helpers import bundle_context_dict


def _command(workspace: Path, name: str, value: str) -> ExternalToolBinding:
    """A command script that emits a JSON value and records an invocation marker."""

    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / f"{name}.py").write_text(
        "import os, pathlib\n"
        "bundle = pathlib.Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        f"bundle.write_text({value!r}, encoding='utf-8')\n"
        f"(bundle.parent / '{name}.ran').write_text('1', encoding='utf-8')\n",
        encoding="utf-8",
    )
    return ExternalToolBinding(name=name, stable_command=("python", f"scripts/{name}.py"))


def _failing_command(workspace: Path, name: str) -> ExternalToolBinding:
    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / f"{name}.py").write_text(
        "import sys\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    return ExternalToolBinding(name=name, stable_command=("python", f"scripts/{name}.py"))


def _marking_failing_command(workspace: Path, name: str) -> ExternalToolBinding:
    """A command that records a marker then exits nonzero (forced downstream failure)."""

    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / f"{name}.py").write_text(
        "import os, pathlib, sys\n"
        "bundle = pathlib.Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        f"(bundle.parent / '{name}.ran').write_text('1', encoding='utf-8')\n"
        "sys.exit(3)\n",
        encoding="utf-8",
    )
    return ExternalToolBinding(name=name, stable_command=("python", f"scripts/{name}.py"))


def _marker_files(workspace: Path, name: str) -> list[Path]:
    return list(workspace.rglob(f"{name}.ran"))


def _provider_patches(workspace: Path, document: str, counter: list):
    def _prepare_invocation(_self, *args, **kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def _execute(_self, invocation, **_kwargs):
        bundle_path = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        counter.append(str(bundle_path))
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(document + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    return (
        patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation),
        patch.object(ProviderExecutor, "execute", _execute),
    )


def _compile_and_bind(
    workspace: Path,
    module_path: Path,
    *,
    run_id: str,
    command_boundaries: dict[str, ExternalToolBinding],
    provider_externs: dict[str, str] | None = None,
    prompt_externs: dict[str, dict[str, str]] | None = None,
    inputs: dict | None = None,
):
    result = compile_stage3_entrypoint(
        module_path,
        source_roots=(workspace,),
        provider_externs=provider_externs or {},
        prompt_externs=prompt_externs or {},
        command_boundaries=command_boundaries,
        validate_shared=True,
        workspace_root=workspace,
    )
    bundle = next(iter(result.validated_bundles_by_name.values()))
    runtime_inputs = dict(workflow_runtime_input_contracts(bundle))
    binding_inputs = {
        name: contract
        for name, contract in runtime_inputs.items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(binding_inputs, inputs or {}, workspace)
    state_manager = StateManager(workspace=workspace, run_id=run_id)
    state_manager.initialize(
        module_path.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    return bundle, state_manager


def _step_by_suffix(steps: dict, suffix: str) -> dict:
    return next(step for name, step in steps.items() if name.endswith(suffix))


def _skipped_effect_step(steps: dict) -> dict:
    """Return the skipped compiler-owned condition-effect step, if any."""

    return next(
        step
        for name, step in steps.items()
        if step["status"] == "skipped" and "__cond_effect_" in name
    )


def _assert_durable_skipped(step: dict) -> None:
    assert step["status"] == "skipped"
    assert step["skipped"] is True
    assert "visit_count" not in step
    assert "artifacts" not in step
    assert "output" not in step
    assert "result" not in step
    assert "checkpoint" not in step


def _resume_manager(workspace: Path, run_id: str) -> StateManager:
    manager = StateManager(workspace=workspace, run_id=run_id)
    manager.load()
    return manager


def test_linear_extraction_routes_and_resumes(tmp_path: Path) -> None:
    """An inline enum comparison hoists its provider effect and resumes cleanly."""

    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review.\n", encoding="utf-8")
    module_path = tmp_path / "linear.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule linear)",
                "  (export decide)",
                "  (defenum ReviewDecision",
                "    APPROVE",
                "    REVISE)",
                "  (defworkflow decide",
                "    ()",
                "    -> Bool",
                "    (if (= (provider-result providers.review",
                "             :prompt prompts.review",
                "             :inputs ()",
                "             :returns ReviewDecision)",
                "           ReviewDecision.APPROVE)",
                "        (command-result accept",
                '          :argv ("python" "scripts/accept.py")',
                "          :returns Bool)",
                "        (command-result revise",
                '          :argv ("python" "scripts/revise.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    counter: list = []
    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="linear",
        command_boundaries={
            "accept": _command(tmp_path, "accept", "true"),
            "revise": _command(tmp_path, "revise", "false"),
        },
        provider_externs={"providers.review": "fake-review"},
        prompt_externs={"prompts.review": {"input_file": "prompts/review.md"}},
    )
    p1, p2 = _provider_patches(tmp_path, '"APPROVE"', counter)
    with p1, p2:
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first["status"] == "completed"
    assert first["workflow_outputs"] == {"__result__": True}
    assert len(counter) == 1
    assert len(_marker_files(tmp_path, "accept")) == 1
    assert _marker_files(tmp_path, "revise") == []
    _assert_durable_skipped(_step_by_suffix(first["steps"], "__revise"))

    with p1, p2:
        resumed = WorkflowExecutor(
            bundle, tmp_path, _resume_manager(tmp_path, "linear"), retry_delay_ms=0
        ).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}


def test_short_circuit_and_skips_unreached_command(tmp_path: Path) -> None:
    """A false first `and` operand dynamically skips the later command operand."""

    module_path = tmp_path / "short_and.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule short_and)",
                "  (export gate)",
                "  (defworkflow gate",
                "    ()",
                "    -> Bool",
                "    (if (and (command-result stop_after_false",
                '              :argv ("python" "scripts/stop_after_false.py")',
                "              :returns Bool)",
                "             (command-result must_not_run",
                '              :argv ("python" "scripts/must_not_run.py")',
                "              :returns Bool))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="short_and",
        command_boundaries={
            "stop_after_false": _command(tmp_path, "stop_after_false", "false"),
            "must_not_run": _command(tmp_path, "must_not_run", "true"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert first["status"] == "completed"
    assert first["workflow_outputs"] == {"__result__": False}
    assert len(_marker_files(tmp_path, "stop_after_false")) == 1
    assert _marker_files(tmp_path, "must_not_run") == []
    assert _step_by_suffix(first["steps"], "__stop_after_false")["visit_count"] == 1
    _assert_durable_skipped(_step_by_suffix(first["steps"], "__must_not_run"))

    resumed = WorkflowExecutor(
        bundle, tmp_path, _resume_manager(tmp_path, "short_and"), retry_delay_ms=0
    ).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": False}
    assert _marker_files(tmp_path, "must_not_run") == []
    _assert_durable_skipped(_step_by_suffix(resumed["steps"], "__must_not_run"))


def test_short_circuit_or_skips_unreached_provider(tmp_path: Path) -> None:
    """A true first `or` operand dynamically skips the later provider operand."""

    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "stop.md").write_text("Stop.\n", encoding="utf-8")
    (tmp_path / "prompts" / "later.md").write_text("Later.\n", encoding="utf-8")
    module_path = tmp_path / "short_or.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule short_or)",
                "  (export gate)",
                "  (defworkflow gate",
                "    ()",
                "    -> Bool",
                "    (if (or (provider-result providers.stop_after_true",
                "             :prompt prompts.stop",
                "             :inputs ()",
                "             :returns Bool)",
                "            (provider-result providers.must_not_run",
                "             :prompt prompts.later",
                "             :inputs ()",
                "             :returns Bool))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    counter: list = []
    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="short_or",
        command_boundaries={
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
        provider_externs={
            "providers.stop_after_true": "fake-stop",
            "providers.must_not_run": "fake-later",
        },
        prompt_externs={
            "prompts.stop": {"input_file": "prompts/stop.md"},
            "prompts.later": {"input_file": "prompts/later.md"},
        },
    )
    p1, p2 = _provider_patches(tmp_path, "true", counter)
    with p1, p2:
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first["status"] == "completed"
    assert first["workflow_outputs"] == {"__result__": True}
    assert len(counter) == 1
    _assert_durable_skipped(_skipped_effect_step(first["steps"]))

    with p1, p2:
        resumed = WorkflowExecutor(
            bundle, tmp_path, _resume_manager(tmp_path, "short_or"), retry_delay_ms=0
        ).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}
    _assert_durable_skipped(_skipped_effect_step(resumed["steps"]))


def test_nested_control_value_routes_and_resumes(tmp_path: Path) -> None:
    """A nested effectful `if` value selects one branch before the outer route."""

    module_path = tmp_path / "nested.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule nested)",
                "  (export route)",
                "  (defworkflow route",
                "    ()",
                "    -> Bool",
                "    (if (= (if (command-result choose",
                '                :argv ("python" "scripts/choose.py")',
                "                :returns Bool)",
                "             (command-result left",
                '               :argv ("python" "scripts/left.py")',
                "               :returns Int)",
                "             (command-result right",
                '               :argv ("python" "scripts/right.py")',
                "               :returns Int))",
                "           1)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="nested",
        command_boundaries={
            "choose": _command(tmp_path, "choose", "true"),
            "left": _command(tmp_path, "left", "1"),
            "right": _command(tmp_path, "right", "0"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert first["status"] == "completed"
    assert first["workflow_outputs"] == {"__result__": True}
    assert len(_marker_files(tmp_path, "choose")) == 1
    assert len(_marker_files(tmp_path, "left")) == 1
    assert _marker_files(tmp_path, "right") == []
    _assert_durable_skipped(_step_by_suffix(first["steps"], "__right"))

    resumed = WorkflowExecutor(
        bundle, tmp_path, _resume_manager(tmp_path, "nested"), retry_delay_ms=0
    ).execute(resume=True)

    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == {"__result__": True}
    assert len(_marker_files(tmp_path, "choose")) == 1
    assert len(_marker_files(tmp_path, "left")) == 1
    assert _marker_files(tmp_path, "right") == []


def test_linear_extraction_forced_failure_resumes_without_repeating(tmp_path: Path) -> None:
    """A forced branch failure after the condition settles is not re-run on resume."""

    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "review.md").write_text("Review.\n", encoding="utf-8")
    module_path = tmp_path / "linear_fail.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule linear_fail)",
                "  (export decide)",
                "  (defenum ReviewDecision",
                "    APPROVE",
                "    REVISE)",
                "  (defworkflow decide",
                "    ()",
                "    -> Bool",
                "    (if (= (provider-result providers.review",
                "             :prompt prompts.review",
                "             :inputs ()",
                "             :returns ReviewDecision)",
                "           ReviewDecision.APPROVE)",
                "        (command-result accept",
                '          :argv ("python" "scripts/accept.py")',
                "          :returns Bool)",
                "        (command-result revise",
                '          :argv ("python" "scripts/revise.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    counter: list = []
    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="linear_fail",
        command_boundaries={
            "accept": _failing_command(tmp_path, "accept"),
            "revise": _command(tmp_path, "revise", "false"),
        },
        provider_externs={"providers.review": "fake-review"},
        prompt_externs={"prompts.review": {"input_file": "prompts/review.md"}},
    )
    p1, p2 = _provider_patches(tmp_path, '"APPROVE"', counter)
    with p1, p2:
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first["status"] == "failed"
    assert len(counter) == 1
    assert _marker_files(tmp_path, "revise") == []

    with p1, p2:
        resumed = WorkflowExecutor(
            bundle, tmp_path, _resume_manager(tmp_path, "linear_fail"), retry_delay_ms=0
        ).execute(resume=True)

    assert resumed["status"] == "failed"
    assert len(counter) == 1


def test_direct_provider_bool_condition_routes(tmp_path: Path) -> None:
    """A direct provider ``Bool`` condition admits, routes, and runs once."""

    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "gate.md").write_text("Gate.\n", encoding="utf-8")
    module_path = tmp_path / "direct_provider.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule direct_provider)",
                "  (export gate)",
                "  (defworkflow gate",
                "    ()",
                "    -> Bool",
                "    (if (provider-result providers.gate",
                "          :prompt prompts.gate",
                "          :inputs ()",
                "          :returns Bool)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    counter: list = []
    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="direct_provider",
        command_boundaries={
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
        provider_externs={"providers.gate": "fake-gate"},
        prompt_externs={"prompts.gate": {"input_file": "prompts/gate.md"}},
    )
    p1, p2 = _provider_patches(tmp_path, "true", counter)
    with p1, p2:
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first["status"] == "completed"
    assert first["workflow_outputs"] == {"__result__": True}
    assert len(counter) == 1


def test_failure_before_routing_never_selects_branch(tmp_path: Path) -> None:
    """A failing condition effect aborts before either branch executes."""

    module_path = tmp_path / "failure.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule failure)",
                "  (export gate)",
                "  (defworkflow gate",
                "    ()",
                "    -> Bool",
                "    (if (command-result failing_check",
                '          :argv ("python" "scripts/failing_check.py")',
                "          :returns Bool)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="failure",
        command_boundaries={
            "failing_check": _failing_command(tmp_path, "failing_check"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert first["status"] == "failed"
    assert _marker_files(tmp_path, "yes") == []
    assert _marker_files(tmp_path, "no") == []


def test_invalid_contract_condition_effect_fails_before_routing(tmp_path: Path) -> None:
    """A condition effect returning an invalid Bool contract fails before routing."""

    module_path = tmp_path / "invalid_contract.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule invalid_contract)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (command-result bad_check",
                '          :argv ("python" "scripts/bad_check.py")',
                "          :returns Bool)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="invalid_contract",
        command_boundaries={
            # Exits 0 but writes a JSON string, not a Bool: contract failure.
            "bad_check": _command(tmp_path, "bad_check", '"not-a-bool"'),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert first["status"] == "failed"
    assert _marker_files(tmp_path, "yes") == []
    assert _marker_files(tmp_path, "no") == []


def test_nested_let_shadowing_routes(tmp_path: Path) -> None:
    """A nested ``let*`` shadow routes on the inner binding, not the outer one."""

    module_path = tmp_path / "shadow.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule shadow)",
                "  (export decide)",
                "  (defworkflow decide () -> Bool",
                "    (if (let* ((outer (command-result first",
                '                        :argv ("python" "scripts/first.py")',
                "                        :returns Bool)))",
                "          (let* ((outer (command-result second",
                '                          :argv ("python" "scripts/second.py")',
                "                          :returns Bool)))",
                "            outer))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="shadow",
        command_boundaries={
            "first": _command(tmp_path, "first", "true"),
            "second": _command(tmp_path, "second", "false"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    result = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert result["status"] == "completed"
    # The inner `outer` (second = false) shadows the outer (first = true).
    assert result["workflow_outputs"] == {"__result__": False}
    assert _marker_files(tmp_path, "first")
    assert _marker_files(tmp_path, "second")
    assert _marker_files(tmp_path, "no")
    assert _marker_files(tmp_path, "yes") == []


def test_effectful_not_inverts_and_runs_once(tmp_path: Path) -> None:
    """``not`` over a false effect inverts and invokes the effect once."""

    module_path = tmp_path / "not_invert.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule not_invert)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (not (command-result probe",
                '               :argv ("python" "scripts/probe.py")',
                "               :returns Bool))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="not_invert",
        command_boundaries={
            "probe": _command(tmp_path, "probe", "false"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    result = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert result["status"] == "completed"
    assert result["workflow_outputs"] == {"__result__": True}
    assert len(_marker_files(tmp_path, "probe")) == 1
    assert _marker_files(tmp_path, "yes")
    assert _marker_files(tmp_path, "no") == []


def test_effectful_not_forced_failure_resumes_without_repeating(tmp_path: Path) -> None:
    """A forced branch failure after an inverted condition is not re-run on resume."""

    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "gate.md").write_text("Gate.\n", encoding="utf-8")
    module_path = tmp_path / "not_fail.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule not_fail)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (not (provider-result providers.gate",
                "               :prompt prompts.gate",
                "               :inputs ()",
                "               :returns Bool))",
                "        (command-result accept",
                '          :argv ("python" "scripts/accept.py")',
                "          :returns Bool)",
                "        (command-result revise",
                '          :argv ("python" "scripts/revise.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    counter: list = []
    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="not_fail",
        command_boundaries={
            "accept": _failing_command(tmp_path, "accept"),
            "revise": _command(tmp_path, "revise", "false"),
        },
        provider_externs={"providers.gate": "fake-gate"},
        prompt_externs={"prompts.gate": {"input_file": "prompts/gate.md"}},
    )
    p1, p2 = _provider_patches(tmp_path, "false", counter)
    with p1, p2:
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first["status"] == "failed"
    assert len(counter) == 1
    assert _marker_files(tmp_path, "revise") == []

    with p1, p2:
        resumed = WorkflowExecutor(
            bundle, tmp_path, _resume_manager(tmp_path, "not_fail"), retry_delay_ms=0
        ).execute(resume=True)

    assert resumed["status"] == "failed"
    assert len(counter) == 1


def _counting_command(workspace: Path, name: str) -> ExternalToolBinding:
    """A command that emits ``true`` and appends one marker per invocation."""

    scripts = workspace / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / f"{name}.py").write_text(
        "import os, pathlib\n"
        "bundle = pathlib.Path(os.environ['ORCHESTRATOR_OUTPUT_BUNDLE_PATH'])\n"
        "bundle.parent.mkdir(parents=True, exist_ok=True)\n"
        "bundle.write_text('true', encoding='utf-8')\n"
        f"with open(bundle.parent / '{name}.count', 'a') as f: f.write('x')\n",
        encoding="utf-8",
    )
    return ExternalToolBinding(name=name, stable_command=("python", f"scripts/{name}.py"))


def test_list_map_effect_cardinality_preserved_in_condition(tmp_path: Path) -> None:
    """A list-map-effect body inside a condition runs once per source item."""

    module_path = tmp_path / "list_card.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule list_card)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (let* ((flags (list/map-effect",
                "                        ((x (list 1 2 3))) :max 10",
                "                        (command-result probe",
                '                          :argv ("python" "scripts/probe.py")',
                "                          :returns Bool)))",
                "               (ok (command-result final",
                '                     :argv ("python" "scripts/final.py")',
                "                     :returns Bool)))",
                "          ok)",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="list_card",
        command_boundaries={
            "probe": _counting_command(tmp_path, "probe"),
            "final": _command(tmp_path, "final", "true"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    result = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert result["status"] == "completed"
    assert result["workflow_outputs"] == {"__result__": True}
    count_files = list(tmp_path.rglob("probe.count"))
    assert len(count_files) == 1
    assert count_files[0].read_text(encoding="utf-8") == "xxx"
    assert _marker_files(tmp_path, "yes")
    assert _marker_files(tmp_path, "no") == []


def test_loop_untaken_done_branch_effect_stays_unexecuted(tmp_path: Path) -> None:
    """An untaken loop `done` branch never runs its effect; the reached branch
    runs at most once."""

    module_path = tmp_path / "loop_done_effect.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule loop_done_effect)",
                "  (export gate)",
                "  (defworkflow gate () -> Bool",
                "    (if (loop/recur",
                "          :max 1",
                "          :state (loop-state (count Int 0))",
                "          :on-exhausted false",
                "          (fn (state)",
                "            (if (= state.count 0)",
                "                (continue",
                "                  (let* ((marker (command-result reached",
                '                          :argv ("python" "scripts/reached.py")',
                "                          :returns Bool)))",
                "                    (loop-state :like state :count 1)))",
                "                (done (command-result untaken",
                '                        :argv ("python" "scripts/untaken.py")',
                "                        :returns Bool)))))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="loop_done_effect",
        command_boundaries={
            "reached": _command(tmp_path, "reached", "true"),
            "untaken": _command(tmp_path, "untaken", "true"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    result = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert result["status"] == "completed"
    # The reached `continue` branch runs its marker effect exactly once; the
    # untaken `done` branch effect is never invoked.
    assert len(_marker_files(tmp_path, "reached")) == 1
    assert _marker_files(tmp_path, "untaken") == []


def test_loop_match_selected_arm_consumes_binding(tmp_path: Path) -> None:
    """The selected match arm consumes its bound value; the sibling arm stays
    unexecuted."""

    module_path = tmp_path / "loop_match_arm.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule loop_match_arm)",
                "  (export gate)",
                "  (defunion Subject (A (flag Bool)) (B (flag Bool)))",
                "  (defworkflow gate () -> Bool",
                "    (if (loop/recur",
                "          :max 1",
                "          :state (loop-state (count Int 0))",
                "          :on-exhausted false",
                "          (fn (state)",
                "            (match (command-result subject",
                '                     :argv ("python" "scripts/subject.py")',
                "                     :returns Subject)",
                "              ((A a)",
                "               (done a.flag))",
                "              ((B b)",
                "               (continue",
                "                 (let* ((marker (command-result must_not_run",
                '                         :argv ("python" "scripts/must_not_run.py")',
                "                         :returns Bool)))",
                "                   (loop-state :like state :count 1)))))))",
                "        (command-result yes",
                '          :argv ("python" "scripts/yes.py")',
                "          :returns Bool)",
                "        (command-result no",
                '          :argv ("python" "scripts/no.py")',
                "          :returns Bool))))",
            ]
        ),
        encoding="utf-8",
    )

    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="loop_match_arm",
        command_boundaries={
            "subject": _command(
                tmp_path, "subject", '{"variant": "A", "flag": true}'
            ),
            "must_not_run": _command(tmp_path, "must_not_run", "true"),
            "yes": _command(tmp_path, "yes", "true"),
            "no": _command(tmp_path, "no", "false"),
        },
    )
    result = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
        on_error="stop"
    )

    assert result["status"] == "completed"
    assert result["workflow_outputs"] == {"__result__": True}
    # The selected `A` arm consumed `a.flag` as its `done` result; the untaken
    # `B` arm's effect never runs.
    assert len(_marker_files(tmp_path, "subject")) == 1
    assert _marker_files(tmp_path, "must_not_run") == []
    assert len(_marker_files(tmp_path, "yes")) == 1
    assert _marker_files(tmp_path, "no") == []


def _variant_proof_module(module_name: str) -> str:
    """The shared provider-produced union narrowing workflow source."""

    return "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.26")',
            f"  (defmodule {module_name})",
            "  (export gate)",
            "  (defpath WorkReport",
            "    :kind relpath",
            '    :under "artifacts/work"',
            "    :must-exist true)",
            "  (defunion ImplementationState",
            "    (COMPLETED (execution_report WorkReport))",
            "    (BLOCKED (progress_report WorkReport)))",
            "  (defworkflow gate () -> Bool",
            "    (let* ((attempt",
            "             (provider-result providers.execute",
            "               :prompt prompts.execute",
            "               :inputs ()",
            "               :returns ImplementationState)))",
            "      (if (= attempt.variant COMPLETED)",
            "          (command-result send",
            '            :argv ("python" "scripts/send.py" attempt.execution_report)',
            "            :returns Bool)",
            "          (command-result skip",
            '            :argv ("python" "scripts/skip.py")',
            "            :returns Bool)))))",
        ]
    )


def _variant_proof_workspace(tmp_path: Path, module_name: str) -> Path:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "execute.md").write_text("Produce.\n", encoding="utf-8")
    (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "work" / "execution_report.md").write_text(
        "# report\n", encoding="utf-8"
    )
    module_path = tmp_path / f"{module_name}.orc"
    module_path.write_text(_variant_proof_module(module_name), encoding="utf-8")
    return module_path


def _variant_proof_compile_and_bind(
    workspace: Path,
    module_path: Path,
    *,
    run_id: str,
    send_binding: ExternalToolBinding,
):
    return _compile_and_bind(
        workspace,
        module_path,
        run_id=run_id,
        command_boundaries={
            "send": send_binding,
            "skip": _command(workspace, "skip", "false"),
        },
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={"prompts.execute": {"input_file": "prompts/execute.md"}},
    )


def test_proof_guard_consuming_leaf_carries_requires_variant(tmp_path: Path) -> None:
    """A provider union narrowed by `=` attaches ``requires_variant`` to its
    first consuming leaf."""

    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    module_path = _variant_proof_workspace(tmp_path, "proof_guard")
    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake"},
        prompt_externs={"prompts.execute": "prompts/execute.md"},
        command_boundaries={
            "send": ExternalToolBinding(
                name="send", stable_command=("python", "scripts/send.py")
            ),
            "skip": ExternalToolBinding(
                name="skip", stable_command=("python", "scripts/skip.py")
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    steps = result.lowered_workflows[0].authored_mapping["steps"]
    if_step = next(step for step in steps if "if" in step)
    send_step = next(
        step for step in if_step["then"]["steps"] if step.get("name", "").endswith("__send")
    )
    assert send_step["requires_variant"] == {"step": "gate__attempt", "value": "COMPLETED"}
    assert "when" not in send_step


def _predicate_proof_descriptors(bundle, state_manager, tmp_path: Path) -> list[dict]:
    from tests.test_workflow_lisp_lexical_checkpoint_restore import (
        _checkpoint_point_by_step_suffix,
        _latest_checkpoint_record,
    )

    send_point = _checkpoint_point_by_step_suffix(bundle, "__then__send")
    record = _latest_checkpoint_record(
        tmp_path=tmp_path, state_manager=state_manager, point=send_point
    )
    return [
        proof
        for proof in record["restore_payload"]["active_variant_proofs"]
        if proof.get("proof_kind") == "predicate"
    ]


def test_contradiction_mutated_discriminant_fails_closed(tmp_path: Path) -> None:
    """Mutating the persisted producer discriminant fails the guard closed."""

    module_path = _variant_proof_workspace(tmp_path, "contradiction")
    counter: list = []
    bundle, state_manager = _variant_proof_compile_and_bind(
        tmp_path,
        module_path,
        run_id="contradiction",
        send_binding=_failing_command(tmp_path, "send"),
    )
    document = '{"variant": "COMPLETED", "execution_report": "artifacts/work/execution_report.md"}'
    p1, p2 = _provider_patches(tmp_path, document, counter)

    original_run = WorkflowExecutor._run_top_level_step

    def _mutate_discriminant_then_run(
        self,
        step,
        state,
        *,
        step_name,
        resume_current_step=False,
    ):
        requires_variant = step.get("requires_variant") if hasattr(step, "get") else None
        if isinstance(requires_variant, dict):
            producer = requires_variant.get("step")
            producer_result = state.get("steps", {}).get(producer)
            if isinstance(producer_result, dict):
                artifacts = producer_result.setdefault("artifacts", {})
                artifacts["variant"] = "BLOCKED"
                artifacts["return__variant"] = "BLOCKED"
        return original_run(
            self,
            step,
            state,
            step_name=step_name,
            resume_current_step=resume_current_step,
        )

    with p1, p2, patch.object(
        WorkflowExecutor, "_run_top_level_step", _mutate_discriminant_then_run
    ):
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first["status"] == "failed"
    state = state_manager.load().to_dict()
    send_result = next(
        result
        for name, result in state["steps"].items()
        if name.endswith("__then__send")
    )
    assert send_result["error"]["type"] == "variant_unavailable"


def test_proof_resume_restores_variant_proof_descriptor(tmp_path: Path) -> None:
    """Resume inside the branch restores a proof descriptor binding producer
    and variant."""

    module_path = _variant_proof_workspace(tmp_path, "proof_resume")
    counter: list = []
    bundle, state_manager = _variant_proof_compile_and_bind(
        tmp_path,
        module_path,
        run_id="proof_resume",
        send_binding=_failing_command(tmp_path, "send"),
    )
    document = '{"variant": "COMPLETED", "execution_report": "artifacts/work/execution_report.md"}'
    p1, p2 = _provider_patches(tmp_path, document, counter)
    with p1, p2:
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    assert first["status"] == "failed"
    assert len(counter) == 1
    proofs = _predicate_proof_descriptors(bundle, state_manager, tmp_path)
    assert [proof["variant"] for proof in proofs] == ["COMPLETED"]
    assert all(proof["producer_step_name"].endswith("__attempt") for proof in proofs)

    with p1, p2:
        resumed = WorkflowExecutor(
            bundle, tmp_path, _resume_manager(tmp_path, "proof_resume"), retry_delay_ms=0
        ).execute(resume=True)

    assert resumed["status"] == "failed"
    assert len(counter) == 1


def _cond_exhaustive_module() -> str:
    """The fifth accepted fixture: exhaustive no-`else` cond with an observable
    provider before a proof-forced terminal test."""

    return "\n".join(
        [
            "(workflow-lisp",
            '  (:language "0.1")',
            '  (:target-dsl "2.26")',
            "  (defmodule cond_exhaustive)",
            "  (export decide)",
            '  (defpath WorkReport :kind relpath :under "artifacts/work" :must-exist true)',
            "  (defunion ImplementationState",
            "    (COMPLETED (execution_report WorkReport))",
            "    (BLOCKED (blocker_reason WorkReport)))",
            "  (defworkflow decide () -> Bool",
            "    (let* ((attempt",
            "             (provider-result providers.execute",
            "               :prompt prompts.execute",
            "               :inputs ()",
            "               :returns ImplementationState)))",
            "      (cond",
            "        ((= attempt.variant COMPLETED)",
            "         (command-result consume-completed",
            '           :argv ("python" "scripts/consume_completed.py" attempt.execution_report)',
            "           :returns Bool))",
            "        ((or (provider-result providers.last-check",
            "              :prompt prompts.last-check",
            "              :inputs ()",
            "              :returns Bool)",
            "             (= attempt.variant BLOCKED))",
            "         (command-result consume-blocked",
            '           :argv ("python" "scripts/consume_blocked.py" attempt.blocker_reason)',
            "           :returns Bool))))))",
        ]
    )


def _cond_exhaustive_workspace(tmp_path: Path) -> Path:
    (tmp_path / "prompts").mkdir(exist_ok=True)
    (tmp_path / "prompts" / "execute.md").write_text("EXECUTE_PROVIDER\n", encoding="utf-8")
    (tmp_path / "prompts" / "last-check.md").write_text("LAST_CHECK_PROVIDER\n", encoding="utf-8")
    (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "work" / "blocker_reason.md").write_text(
        "# blocker\n", encoding="utf-8"
    )
    module_path = tmp_path / "cond_exhaustive.orc"
    module_path.write_text(_cond_exhaustive_module(), encoding="utf-8")
    return module_path


def _union_bool_provider_patches(
    workspace: Path,
    union_document: str,
    bool_document: str,
    union_counter: list,
    bool_counter: list,
):
    def _prepare_invocation(_self, *args, **kwargs):
        return (
            SimpleNamespace(
                input_mode="stdin",
                prompt=kwargs.get("prompt_content", ""),
                env=kwargs.get("env") or {},
            ),
            None,
        )

    def _execute(_self, invocation, **_kwargs):
        bundle_path = workspace / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        if "EXECUTE_PROVIDER" in (invocation.prompt or ""):
            document = union_document
            union_counter.append(str(bundle_path))
        else:
            document = bool_document
            bool_counter.append(str(bundle_path))
        bundle_path.write_text(document + "\n", encoding="utf-8")
        return SimpleNamespace(
            exit_code=0,
            stdout=b"",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    return (
        patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation),
        patch.object(ProviderExecutor, "execute", _execute),
    )


def test_cond_exhaustive_terminal_carries_requires_variant_guards(
    tmp_path: Path,
) -> None:
    """Each clause's field-consuming command carries its variant guard."""

    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    module_path = _cond_exhaustive_workspace(tmp_path)
    result = compile_stage3_module(
        module_path,
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.last-check": "fake-last-check",
        },
        prompt_externs={
            "prompts.execute": "prompts/execute.md",
            "prompts.last-check": "prompts/last-check.md",
        },
        command_boundaries={
            "consume-completed": ExternalToolBinding(
                name="consume-completed",
                stable_command=("python", "scripts/consume_completed.py"),
            ),
            "consume-blocked": ExternalToolBinding(
                name="consume-blocked",
                stable_command=("python", "scripts/consume_blocked.py"),
            ),
        },
        validate_shared=False,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    steps = result.lowered_workflows[0].authored_mapping["steps"]
    if_step = next(step for step in steps if "if" in step)
    completed_cmd = next(
        step
        for step in if_step["then"]["steps"]
        if step.get("name", "").endswith("consume-completed")
    )
    blocked_cmd = next(
        step
        for step in if_step["else"]["steps"]
        if step.get("name", "").endswith("consume-blocked")
    )
    assert completed_cmd["requires_variant"] == {
        "step": "decide__attempt",
        "value": "COMPLETED",
    }
    assert blocked_cmd["requires_variant"] == {
        "step": "decide__attempt",
        "value": "BLOCKED",
    }
    # The forced terminal equality is erased: the short-circuit projection's
    # inner test is a literal, never a runtime discriminant comparison.
    short_circuit = next(
        step
        for step in if_step["else"]["steps"]
        if "pure_projection" in step
    )
    inner_expr = short_circuit["pure_projection"]["payload"]["expr"]["else"]
    assert inner_expr["condition"]["kind"] == "literal"
    assert inner_expr["condition"]["value"] is True


@pytest.mark.parametrize("last_check_document", ['"true"', '"false"'])
def test_cond_exhaustive_terminal_routes_and_resumes(
    tmp_path: Path,
    last_check_document: str,
) -> None:
    """The exhaustive terminal runs its provider once and its body in both
    valid paths, resuming without repeating the provider."""

    module_path = _cond_exhaustive_workspace(tmp_path)
    union_counter: list = []
    bool_counter: list = []
    bundle, state_manager = _compile_and_bind(
        tmp_path,
        module_path,
        run_id="cond_runtime",
        command_boundaries={
            "consume-completed": _command(tmp_path, "consume_completed", "true"),
            "consume-blocked": _marking_failing_command(tmp_path, "consume_blocked"),
        },
        provider_externs={
            "providers.execute": "fake-execute",
            "providers.last-check": "fake-last-check",
        },
        prompt_externs={
            "prompts.execute": {"input_file": "prompts/execute.md"},
            "prompts.last-check": {"input_file": "prompts/last-check.md"},
        },
    )
    union_document = '{"variant": "BLOCKED", "blocker_reason": "artifacts/work/blocker_reason.md"}'
    p1, p2 = _union_bool_provider_patches(
        tmp_path, union_document, last_check_document, union_counter, bool_counter
    )
    with p1, p2:
        first = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(
            on_error="stop"
        )

    # The BLOCKED body is selected and executed (then forced to fail); the
    # COMPLETED body is skipped. Both providers execute exactly once.
    assert first["status"] == "failed"
    assert len(union_counter) == 1
    assert len(bool_counter) == 1
    assert len(_marker_files(tmp_path, "consume_blocked")) == 1
    assert _marker_files(tmp_path, "consume_completed") == []

    with p1, p2:
        resumed = WorkflowExecutor(
            bundle, tmp_path, _resume_manager(tmp_path, "cond_runtime"), retry_delay_ms=0
        ).execute(resume=True)

    assert resumed["status"] == "failed"
    # Resume neither repeats the providers nor changes the selected result.
    assert len(union_counter) == 1
    assert len(bool_counter) == 1
    assert len(_marker_files(tmp_path, "consume_blocked")) == 1
    assert _marker_files(tmp_path, "consume_completed") == []
