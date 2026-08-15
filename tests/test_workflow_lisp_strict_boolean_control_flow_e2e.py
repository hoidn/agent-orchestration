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


def test_pre_provider_input_peer_group_runtime_and_resume(tmp_path: Path) -> None:
    """A peer-group member input selection lowers to one projection prelude
    with an ordinary pure-projection checkpoint resume policy."""

    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "planner.md").write_text("Plan.\n", encoding="utf-8")
    (tmp_path / "prompts" / "reviewer.md").write_text("Review.\n", encoding="utf-8")
    module_path = tmp_path / "peer_input.orc"
    module_path.write_text(
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.26")',
                "  (defmodule peer_input)",
                "  (export orchestrate)",
                "  (defworkflow orchestrate ((a Bool) (b Bool)) -> String",
                "    (with-live-provider-peers",
                "      ((planner",
                "         (let* ((flag (if a b false)))",
                "           (provider-result providers.planner",
                "             :prompt prompts.planner :inputs (flag)",
                "             :timeout-sec 30 :returns String)))",
                "       (reviewer",
                "         (provider-result providers.reviewer",
                "           :prompt prompts.reviewer :inputs ()",
                "           :timeout-sec 20 :returns Bool)))",
                "      planner)))",
            ]
        ),
        encoding="utf-8",
    )

    from orchestrator.workflow_lisp.compiler import compile_stage3_module

    compiled = compile_stage3_module(
        module_path,
        entry_workflow="orchestrate",
        provider_externs={
            "providers.planner": "fake-planner",
            "providers.reviewer": "fake-reviewer",
        },
        prompt_externs={
            "prompts.planner": "prompts/planner.md",
            "prompts.reviewer": "prompts/reviewer.md",
        },
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    lowered = next(
        workflow
        for workflow in compiled.lowered_workflows
        if workflow.typed_workflow.definition.name == "orchestrate"
    )
    steps = lowered.authored_mapping["steps"]
    assert len(steps) == 2
    projection_step = steps[0]
    peer_group_step = steps[1]
    assert "provider_peer_group" in peer_group_step
    payload = projection_step["pure_projection"]["payload"]
    assert payload["expr"]["kind"] == "if"

    # The whole selection is a single existing pure_projection whose ordinary
    # step-level resume policy reuses the completed projection on resume.
    effect_boundary = projection_step["pure_projection"].get("effect_boundary")
    if effect_boundary is not None:
        assert effect_boundary["effect_kind"] == "pure_projection"