from __future__ import annotations

import importlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.loaded_bundle import workflow_context, workflow_public_input_contracts
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "cli"
WORKFLOW_LISP_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp"
CHARACTERIZATION_FIXTURES = WORKFLOW_LISP_FIXTURES / "characterization" / "sources"


def _write_module(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def _build_module():
    return importlib.import_module("orchestrator.workflow_lisp.build")


def _bind_nested_match_inputs(bundle, workspace: Path) -> dict[str, object]:
    return bind_workflow_inputs(
        workflow_public_input_contracts(bundle),
        {"report": "artifacts/work/input_report.md"},
        workspace,
    )


def test_design_delta_migration_nested_library_import_layout_compiles(tmp_path: Path) -> None:
    package_dir = tmp_path / "lisp_frontend_design_delta"
    _write_module(
        package_dir / "types.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta/types)",
                "  (export WorkReport SelectionResult)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord SelectionResult",
                "    (status String)",
                "    (report WorkReport)))",
            ]
        )
        + "\n",
    )
    _write_module(
        package_dir / "selector.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta/selector)",
                "  (import lisp_frontend_design_delta/types :only (WorkReport SelectionResult))",
                "  (export select-next-work)",
                "  (defworkflow select-next-work",
                "    ((report WorkReport))",
                "    -> SelectionResult",
                "    (provider-result providers.selector",
                "      :prompt prompts.selector",
                "      :inputs (report)",
                "      :returns SelectionResult)))",
            ]
        )
        + "\n",
    )
    entry = _write_module(
        package_dir / "entry.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta/entry)",
                "  (import lisp_frontend_design_delta/types :only (WorkReport SelectionResult))",
                "  (import lisp_frontend_design_delta/selector :as selector :only (select-next-work))",
                "  (export drain)",
                "  (defworkflow drain",
                "    ((report WorkReport))",
                "    -> SelectionResult",
                "    (call selector.select-next-work",
                "      :report report)))",
            ]
        )
        + "\n",
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        provider_externs={"providers.selector": "fake-selector"},
        prompt_externs={"prompts.selector": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert set(result.compiled_results_by_name) == {
        "lisp_frontend_design_delta/types",
        "lisp_frontend_design_delta/selector",
        "lisp_frontend_design_delta/entry",
    }
    assert {
        workflow.typed_workflow.definition.name
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    } == {
        "lisp_frontend_design_delta/entry::drain",
        "lisp_frontend_design_delta/selector::select-next-work",
    }


def test_design_delta_migration_yaml_call_interop_is_manifest_bundle_not_source_import(
    tmp_path: Path,
) -> None:
    build = _build_module()
    build_frontend_bundle = getattr(build, "build_frontend_bundle")
    request_cls = getattr(build, "FrontendBuildRequest")

    result = build_frontend_bundle(
        request_cls(
            source_path=(
                WORKFLOW_LISP_FIXTURES
                / "modules"
                / "valid"
                / "imported_bundle_mix"
                / "neurips"
                / "entry.orc"
            ),
            source_roots=(WORKFLOW_LISP_FIXTURES / "modules" / "valid" / "imported_bundle_mix",),
            entry_workflow="orchestrate",
            provider_externs_path=CLI_FIXTURES / "providers.json",
            prompt_externs_path=CLI_FIXTURES / "prompts.json",
            imported_workflow_bundles_path=CLI_FIXTURES / "imported_workflow_bundles.json",
            command_boundaries_path=CLI_FIXTURES / "commands.json",
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )

    assert result.imported_workflow_bundles[0].bundle_kind == "yaml"
    assert result.imported_workflow_bundles[0].workflow_name == "selector-run"
    assert result.validated_bundle.surface.name == "neurips/entry::orchestrate"


def test_design_delta_migration_stdlib_review_revise_loop_fixture_compiles(
    tmp_path: Path,
) -> None:
    fixture = WORKFLOW_LISP_FIXTURES / "valid" / "phase_stdlib_review_loop.orc"
    module_path = tmp_path / "phase_stdlib_review_loop.orc"
    module_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    result = compile_stage3_module(
        module_path,
        provider_externs={
            "providers.review": "fake-review",
            "providers.fix": "fake-fix",
        },
        prompt_externs={
            "prompts.implementation.review": "prompts/implementation/review.md",
            "prompts.implementation.fix": "prompts/implementation/fix.md",
        },
        command_boundaries={
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=("python", "-m", "orchestrator.workflow_lisp.adapters.validate_review_findings_v1"),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert {
        workflow.typed_workflow.definition.name
        for workflow in result.lowered_workflows
    } == {"phase_stdlib_review_loop::review-revise-loop-demo"}


def test_design_delta_migration_union_match_projection_compiles(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path / "union_match_probe.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule union_match_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt)))",
                "      (match attempt",
                "        ((COMPLETED completed)",
                "         (record ImplementationSummary",
                "           :report completed.execution_report))",
                "        ((BLOCKED blocked)",
                "         (record ImplementationSummary",
                "           :report blocked.progress_report))))))",
            ]
        )
        + "\n",
    )

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.lowered_workflows[0].typed_workflow.definition.name == "summarize"


def test_design_delta_migration_wcc_m3_nested_match_fixture_compiles(tmp_path: Path) -> None:
    result = compile_stage3_module(
        CHARACTERIZATION_FIXTURES / "wcc_m3_nested_non_tail_match.orc",
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={
            "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        },
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m3",
    )

    assert result.lowered_workflows[0].typed_workflow.definition.name == "summarize"


def test_design_delta_migration_wcc_m3_nested_match_smoke_executes_completed_path(tmp_path: Path) -> None:
    fixture = CHARACTERIZATION_FIXTURES / "wcc_m3_nested_non_tail_match.orc"
    module_path = tmp_path / "nested_match_probe.orc"
    module_path.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "prompts" / "implementation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts" / "implementation" / "execute.md").write_text(
        "Return a structured implementation result.\n",
        encoding="utf-8",
    )
    (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "work" / "input_report.md").write_text("# input\n", encoding="utf-8")

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m3",
    )
    bundle = result.validated_bundles["summarize"]
    bound_inputs = _bind_nested_match_inputs(bundle, tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="nested-match-smoke")
    state_manager.initialize(str(module_path), workflow_context(bundle), bound_inputs)
    provider_counts: dict[str, int] = {}

    def _prepare_invocation(_self, provider_name=None, prompt_content=None, **_kwargs):
        return type(
            "ProviderInvocationStub",
            (),
            {
                "input_mode": "stdin",
                "prompt": prompt_content or "",
                "provider_name": provider_name,
            },
        )(), None

    def _execute(_self, invocation, **_kwargs):
        payloads = [
            {
                "variant": "COMPLETED",
                "execution_report": "artifacts/work/attempt_report.md",
            },
            {
                "variant": "APPROVED",
                "execution_report": "artifacts/work/review_report.md",
            },
        ]
        provider_name = getattr(invocation, "provider_name", None)
        index = provider_counts.get(provider_name, 0)
        provider_counts[provider_name] = index + 1
        payload = payloads[index] if index < len(payloads) else payloads[-1]
        bundle_path = next(
            Path(line.split("path:", 1)[1].strip())
            for line in getattr(invocation, "prompt", "").splitlines()
            if "path:" in line
        )
        if not bundle_path.is_absolute():
            bundle_path = tmp_path / bundle_path
        for relpath in ("artifacts/work/attempt_report.md", "artifacts/work/review_report.md"):
            target = tmp_path / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {target.stem}\n", encoding="utf-8")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload), encoding="utf-8")
        return type(
            "ProviderExecutionStub",
            (),
            {
                "exit_code": 0,
                "stdout": b"ok",
                "stderr": b"",
                "duration_ms": 1,
                "error": None,
                "missing_placeholders": None,
                "invalid_prompt_placeholder": False,
                "raw_stdout": None,
                "normalized_stdout": None,
                "provider_session": None,
            },
        )()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"return__report": "artifacts/work/review_report.md"}
    assert provider_counts == {"fake-execute": 2}
    assert state["steps"]["summarize__summary__match_attempt"]["status"] == "completed"
    assert state["steps"]["summarize__summary__match_attempt__completed__match_review"]["status"] == "completed"


def test_design_delta_migration_wcc_m3_nested_match_keeps_branch_local_effects_inside_selected_arm(
    tmp_path: Path,
) -> None:
    module_path = _write_module(
        tmp_path / "nested_branch_effect_probe.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule nested_branch_effect_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ReviewDecision",
                "    (APPROVED",
                "      (execution_report WorkReport))",
                "    (REVISE",
                "      (progress_report WorkReport)))",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt))",
                "           (summary",
                "             (match attempt",
                "               ((COMPLETED completed)",
                "                (let* ((review",
                "                         (provider-result providers.execute",
                "                           :prompt prompts.implementation.execute",
                "                           :inputs (completed.execution_report)",
                "                           :returns ReviewDecision)))",
                "                  (match review",
                "                    ((APPROVED approved)",
                "                     (record ImplementationSummary",
                "                       :report approved.execution_report))",
                "                    ((REVISE revise)",
                "                     (record ImplementationSummary",
                "                       :report revise.progress_report)))))",
                "               ((BLOCKED blocked)",
                "                (record ImplementationSummary",
                "                  :report blocked.progress_report)))))",
                "      (record ImplementationSummary",
                "        :report summary.report))))",
            ]
        )
        + "\n",
    )
    (tmp_path / "prompts" / "implementation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts" / "implementation" / "execute.md").write_text(
        "Return a structured implementation result.\n",
        encoding="utf-8",
    )
    (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "work" / "input_report.md").write_text("# input\n", encoding="utf-8")

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m3",
    )
    bundle = result.validated_bundles["summarize"]
    bound_inputs = bind_workflow_inputs(
        workflow_public_input_contracts(bundle),
        {"report": "artifacts/work/input_report.md"},
        tmp_path,
    )
    state_manager = StateManager(workspace=tmp_path, run_id="nested-branch-effect")
    state_manager.initialize(str(module_path), workflow_context(bundle), bound_inputs)
    provider_counts: dict[str, int] = {}

    def _prepare_invocation(_self, provider_name=None, prompt_content=None, **_kwargs):
        return type(
            "ProviderInvocationStub",
            (),
            {
                "input_mode": "stdin",
                "prompt": prompt_content or "",
                "provider_name": provider_name,
            },
        )(), None

    def _execute(_self, invocation, **_kwargs):
        payloads = [
            {
                "variant": "BLOCKED",
                "progress_report": "artifacts/work/blocked_report.md",
            },
            {
                "variant": "APPROVED",
                "execution_report": "artifacts/work/review_report.md",
            },
        ]
        provider_name = getattr(invocation, "provider_name", None)
        index = provider_counts.get(provider_name, 0)
        provider_counts[provider_name] = index + 1
        payload = payloads[index] if index < len(payloads) else payloads[-1]
        bundle_path = next(
            Path(line.split("path:", 1)[1].strip())
            for line in getattr(invocation, "prompt", "").splitlines()
            if "path:" in line
        )
        if not bundle_path.is_absolute():
            bundle_path = tmp_path / bundle_path
        for relpath in ("artifacts/work/blocked_report.md", "artifacts/work/review_report.md"):
            target = tmp_path / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {target.stem}\n", encoding="utf-8")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload), encoding="utf-8")
        return type(
            "ProviderExecutionStub",
            (),
            {
                "exit_code": 0,
                "stdout": b"ok",
                "stderr": b"",
                "duration_ms": 1,
                "error": None,
                "missing_placeholders": None,
                "invalid_prompt_placeholder": False,
                "raw_stdout": None,
                "normalized_stdout": None,
                "provider_session": None,
            },
        )()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"return__report": "artifacts/work/blocked_report.md"}
    assert provider_counts == {"fake-execute": 1}
    assert state["steps"]["summarize__summary__match_attempt__completed__review"]["status"] == "skipped"
    assert state["steps"]["summarize__summary__match_attempt__completed__match_review"]["status"] == "skipped"


def test_design_delta_migration_wcc_m3_triple_nested_match_keeps_outer_branch_guards(
    tmp_path: Path,
) -> None:
    module_path = _write_module(
        tmp_path / "triple_nested_branch_effect_probe.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule triple_nested_branch_effect_probe)",
                "  (export summarize)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defunion ReviewDecision",
                "    (APPROVED",
                "      (execution_report WorkReport))",
                "    (REVISE",
                "      (progress_report WorkReport)))",
                "  (defunion FinalDecision",
                "    (FINAL",
                "      (execution_report WorkReport))",
                "    (RETRY",
                "      (progress_report WorkReport)))",
                "  (defunion ImplementationAttempt",
                "    (COMPLETED",
                "      (execution_report WorkReport))",
                "    (BLOCKED",
                "      (progress_report WorkReport)))",
                "  (defrecord ImplementationSummary",
                "    (report WorkReport))",
                "  (defworkflow summarize",
                "    ((report WorkReport))",
                "    -> ImplementationSummary",
                "    (let* ((attempt",
                "             (provider-result providers.execute",
                "               :prompt prompts.implementation.execute",
                "               :inputs (report)",
                "               :returns ImplementationAttempt))",
                "           (summary",
                "             (match attempt",
                "               ((COMPLETED completed)",
                "                (let* ((review",
                "                         (provider-result providers.execute",
                "                           :prompt prompts.implementation.execute",
                "                           :inputs (completed.execution_report)",
                "                           :returns ReviewDecision)))",
                "                  (match review",
                "                    ((APPROVED approved)",
                "                     (let* ((final",
                "                              (provider-result providers.execute",
                "                                :prompt prompts.implementation.execute",
                "                                :inputs (approved.execution_report)",
                "                                :returns FinalDecision)))",
                "                       (match final",
                "                         ((FINAL final_decision)",
                "                          (record ImplementationSummary",
                "                            :report final_decision.execution_report))",
                "                         ((RETRY retry)",
                "                          (record ImplementationSummary",
                "                            :report retry.progress_report)))))",
                "                    ((REVISE revise)",
                "                     (record ImplementationSummary",
                "                       :report revise.progress_report)))))",
                "               ((BLOCKED blocked)",
                "                (record ImplementationSummary",
                "                  :report blocked.progress_report)))))",
                "      (record ImplementationSummary",
                "        :report summary.report))))",
            ]
        )
        + "\n",
    )
    (tmp_path / "prompts" / "implementation").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompts" / "implementation" / "execute.md").write_text(
        "Return a structured implementation result.\n",
        encoding="utf-8",
    )
    (tmp_path / "artifacts" / "work").mkdir(parents=True, exist_ok=True)
    (tmp_path / "artifacts" / "work" / "input_report.md").write_text("# input\n", encoding="utf-8")

    result = compile_stage3_module(
        module_path,
        provider_externs={"providers.execute": "fake-execute"},
        prompt_externs={"prompts.implementation.execute": "prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m3",
    )
    bundle = result.validated_bundles["summarize"]
    bound_inputs = _bind_nested_match_inputs(bundle, tmp_path)
    state_manager = StateManager(workspace=tmp_path, run_id="triple-nested-branch-effect")
    state_manager.initialize(str(module_path), workflow_context(bundle), bound_inputs)
    provider_counts: dict[str, int] = {}

    def _prepare_invocation(_self, provider_name=None, prompt_content=None, **_kwargs):
        return type(
            "ProviderInvocationStub",
            (),
            {
                "input_mode": "stdin",
                "prompt": prompt_content or "",
                "provider_name": provider_name,
            },
        )(), None

    def _execute(_self, invocation, **_kwargs):
        payloads = [
            {
                "variant": "BLOCKED",
                "progress_report": "artifacts/work/blocked_report.md",
            },
            {
                "variant": "APPROVED",
                "execution_report": "artifacts/work/review_report.md",
            },
            {
                "variant": "FINAL",
                "execution_report": "artifacts/work/final_report.md",
            },
        ]
        provider_name = getattr(invocation, "provider_name", None)
        index = provider_counts.get(provider_name, 0)
        provider_counts[provider_name] = index + 1
        payload = payloads[index] if index < len(payloads) else payloads[-1]
        bundle_path = next(
            Path(line.split("path:", 1)[1].strip())
            for line in getattr(invocation, "prompt", "").splitlines()
            if "path:" in line
        )
        if not bundle_path.is_absolute():
            bundle_path = tmp_path / bundle_path
        for relpath in (
            "artifacts/work/blocked_report.md",
            "artifacts/work/review_report.md",
            "artifacts/work/final_report.md",
        ):
            target = tmp_path / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(f"# {target.stem}\n", encoding="utf-8")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(json.dumps(payload), encoding="utf-8")
        return type(
            "ProviderExecutionStub",
            (),
            {
                "exit_code": 0,
                "stdout": b"ok",
                "stderr": b"",
                "duration_ms": 1,
                "error": None,
                "missing_placeholders": None,
                "invalid_prompt_placeholder": False,
                "raw_stdout": None,
                "normalized_stdout": None,
                "provider_session": None,
            },
        )()

    with patch.object(ProviderExecutor, "prepare_invocation", _prepare_invocation), patch.object(
        ProviderExecutor, "execute", _execute
    ):
        state = WorkflowExecutor(bundle, tmp_path, state_manager, retry_delay_ms=0).execute(on_error="continue")

    assert state["status"] == "completed"
    assert state["workflow_outputs"] == {"return__report": "artifacts/work/blocked_report.md"}
    assert provider_counts == {"fake-execute": 1}
    assert state["steps"]["summarize__summary__match_attempt__completed__review"]["status"] == "skipped"
    assert state["steps"]["summarize__summary__match_attempt__completed__match_review"]["status"] == "skipped"
    assert state["steps"]["summarize__summary__match_attempt__completed__match_review__approved__final"]["status"] == "skipped"
    assert state["steps"]["summarize__summary__match_attempt__completed__match_review__approved__match_final"]["status"] == "skipped"


def test_design_delta_migration_wcc_m3_branch_local_leak_fixture_fails_as_lexical_escape(
    tmp_path: Path,
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_module(
            CHARACTERIZATION_FIXTURES / "wcc_m3_branch_local_ref_leak.orc",
            provider_externs={"providers.execute": "fake-execute"},
            prompt_externs={
                "prompts.implementation.execute": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
            },
            validate_shared=False,
            workspace_root=tmp_path,
            lowering_route="wcc_m3",
        )

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "name_unknown"
    assert "completed" in diagnostic.message


def test_design_delta_domain_types_import_from_two_candidate_modules(tmp_path: Path) -> None:
    package_dir = tmp_path / "lisp_frontend_design_delta_probe"
    selector = _write_module(
        package_dir / "selector.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta_probe/selector)",
                "  (import lisp_frontend_design_delta/types :only (RunStatePath SelectionResult))",
                "  (export select-next-work)",
                "  (defworkflow select-next-work",
                "    ((run-state RunStatePath))",
                "    -> SelectionResult",
                "    (provider-result providers.selector",
                "      :prompt prompts.selector",
                "      :inputs (run-state)",
                "      :returns SelectionResult)))",
            ]
        )
        + "\n",
    )
    work_item = _write_module(
        package_dir / "work_item.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule lisp_frontend_design_delta_probe/work_item)",
                "  (import lisp_frontend_design_delta/types :only (DesignRevisionResult WorkReport))",
                "  (export run-work-item)",
                "  (defworkflow run-work-item",
                "    ((report WorkReport))",
                "    -> DesignRevisionResult",
                "    (provider-result providers.work-item",
                "      :prompt prompts.work-item",
                "      :inputs (report)",
                "      :returns DesignRevisionResult)))",
            ]
        )
        + "\n",
    )

    selector_result = compile_stage3_entrypoint(
        selector,
        source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
        provider_externs={"providers.selector": "fake-selector"},
        prompt_externs={"prompts.selector": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )
    work_item_result = compile_stage3_entrypoint(
        work_item,
        source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
        provider_externs={"providers.work-item": "fake-work-item"},
        prompt_externs={"prompts.work-item": "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "lisp_frontend_design_delta/types" in selector_result.compiled_results_by_name
    assert "lisp_frontend_design_delta/types" in work_item_result.compiled_results_by_name
    assert selector_result.entry_result.validated_bundles
    assert work_item_result.entry_result.validated_bundles


def test_design_delta_domain_types_reject_invalid_drain_result_variant(tmp_path: Path) -> None:
    module_path = _write_module(
        tmp_path / "invalid_drain_result_variant.orc",
        "\n".join(
            [
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule invalid_drain_result_variant)",
                "  (import lisp_frontend_design_delta/types :only (DrainResult RunStatePath))",
                "  (export invalid-drain)",
                "  (defworkflow invalid-drain",
                "    ((run-state RunStatePath))",
                "    -> DrainResult",
                "    (variant DrainResult FINISHED",
                "      :run-state run-state)))",
            ]
        )
        + "\n",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            module_path,
            source_roots=(REPO_ROOT / "workflows" / "library", tmp_path),
            validate_shared=True,
            workspace_root=tmp_path,
        )

    assert any(
        diagnostic.code == "union_variant_unknown" or "FINISHED" in diagnostic.message
        for diagnostic in excinfo.value.diagnostics
    )


def test_design_delta_plan_phase_candidate_compiles_with_stdlib_review_loop(tmp_path: Path) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "plan_phase.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={
            "providers.plan.draft": "codex",
            "providers.plan.review": "codex",
            "providers.plan.fix": "codex",
        },
        prompt_externs={
            "prompts.plan.draft": (
                "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/draft_plan.md"
            ),
            "prompts.plan.review": (
                "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/review_plan.md"
            ),
            "prompts.plan.fix": (
                "workflows/library/prompts/lisp_frontend_design_delta_plan_phase/revise_plan.md"
            ),
        },
        command_boundaries={
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                ),
            )
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "lisp_frontend_design_delta/types" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles
    lowered_workflows = [
        workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    ]
    assert all(lowered["version"] == "2.14" for lowered in lowered_workflows)

    def _walk_steps(steps):
        for step in steps:
            yield step
            if "repeat_until" in step:
                yield from _walk_steps(step["repeat_until"].get("steps", []))
            if "match" in step:
                for case in step["match"].get("cases", {}).values():
                    yield from _walk_steps(case.get("steps", []))

    all_steps = [
        step
        for lowered in lowered_workflows
        for step in _walk_steps(lowered["steps"])
    ]
    assert any(step.get("provider") == "codex" for step in all_steps)
    assert any("repeat_until" in step for step in all_steps)
    assert any("return__variant" in lowered["outputs"] for lowered in lowered_workflows)


def test_design_delta_implementation_phase_candidate_compiles_with_variant_and_review_loop(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "implementation_phase.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={
            "providers.implementation.execute": "codex",
            "providers.implementation.review": "codex",
            "providers.implementation.fix": "codex",
        },
        prompt_externs={
            "prompts.implementation.execute": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/"
                "implement_plan.md"
            ),
            "prompts.implementation.review": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/"
                "review_implementation.md"
            ),
            "prompts.implementation.fix": (
                "workflows/library/prompts/lisp_frontend_design_delta_implementation_phase/"
                "fix_implementation.md"
            ),
        },
        command_boundaries={
            "run_neurips_backlog_checks": ExternalToolBinding(
                name="run_neurips_backlog_checks",
                stable_command=(
                    "python",
                    "workflows/library/scripts/run_neurips_backlog_checks.py",
                ),
            ),
            "validate_review_findings_v1": ExternalToolBinding(
                name="validate_review_findings_v1",
                stable_command=(
                    "python",
                    "-m",
                    "orchestrator.workflow_lisp.adapters.validate_review_findings_v1",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "lisp_frontend_design_delta/types" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles
    lowered_workflows = [
        workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    ]
    assert all(lowered["version"] == "2.14" for lowered in lowered_workflows)

    def _walk_steps(steps):
        for step in steps:
            yield step
            if "repeat_until" in step:
                yield from _walk_steps(step["repeat_until"].get("steps", []))
            if "match" in step:
                for case in step["match"].get("cases", {}).values():
                    yield from _walk_steps(case.get("steps", []))

    all_steps = [
        step
        for lowered in lowered_workflows
        for step in _walk_steps(lowered["steps"])
    ]
    assert any(step.get("provider") == "codex" for step in all_steps)
    assert any("variant_output" in step for step in all_steps)
    assert any("repeat_until" in step for step in all_steps)
    assert any("command" in step for step in all_steps)
    assert any("return__variant" in lowered["outputs"] for lowered in lowered_workflows)


def test_design_delta_selector_candidate_compiles_as_provider_decision(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "selector.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={"providers.selector": "codex"},
        prompt_externs={
            "prompts.selector.select-next-work": (
                "workflows/library/prompts/lisp_frontend_selector/select_next_design_delta_work.md"
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert "lisp_frontend_design_delta/types" in result.compiled_results_by_name
    assert result.entry_result.validated_bundles
    lowered = result.entry_result.lowered_workflows[0].authored_mapping
    assert lowered["version"] == "2.14"
    assert any(step.get("provider") == "codex" for step in lowered["steps"])
    assert "return__selection_status" in lowered["outputs"]


def test_design_delta_architect_candidate_compiles_draft_and_validation_leaves(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT
        / "workflows"
        / "library"
        / "lisp_frontend_design_delta"
        / "design_gap_architect.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={"providers.architect.draft": "codex"},
        prompt_externs={
            "prompts.architect.draft": (
                "workflows/library/prompts/lisp_frontend_design_delta_design_gap_architect/"
                "draft_implementation_architecture.md"
            ),
        },
        command_boundaries={
            "validate_lisp_frontend_design_gap_architecture": ExternalToolBinding(
                name="validate_lisp_frontend_design_gap_architecture",
                stable_command=(
                    "python",
                    "workflows/library/scripts/validate_lisp_frontend_design_gap_architecture.py",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered_workflows = [
        workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    ]
    assert all(lowered["version"] == "2.14" for lowered in lowered_workflows)
    assert any(
        step.get("provider") == "codex"
        for lowered in lowered_workflows
        for step in lowered["steps"]
    )
    assert any(
        "command" in step
        for lowered in lowered_workflows
        for step in lowered["steps"]
    )
    assert any("return__draft_status" in lowered["outputs"] for lowered in lowered_workflows)
    assert any(
        "return__architecture_validation_status" in lowered["outputs"]
        for lowered in lowered_workflows
    )


def test_design_delta_work_item_candidate_compiles_terminal_and_recovery_leaves(
    tmp_path: Path,
) -> None:
    result = compile_stage3_entrypoint(
        REPO_ROOT / "workflows" / "library" / "lisp_frontend_design_delta" / "work_item.orc",
        source_roots=(REPO_ROOT / "workflows" / "library",),
        provider_externs={"providers.work-item.recovery-classifier": "codex"},
        prompt_externs={
            "prompts.work-item.classify-blocked-recovery": (
                "workflows/library/prompts/lisp_frontend_design_delta_work_item/"
                "classify_blocked_implementation_recovery.md"
            ),
        },
        command_boundaries={
            "classify_lisp_frontend_work_item_terminal": ExternalToolBinding(
                name="classify_lisp_frontend_work_item_terminal",
                stable_command=(
                    "python",
                    "workflows/library/scripts/classify_lisp_frontend_work_item_terminal.py",
                ),
            ),
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    lowered_workflows = [
        workflow.authored_mapping
        for compiled in result.compiled_results_by_name.values()
        for workflow in compiled.lowered_workflows
    ]
    assert all(lowered["version"] == "2.14" for lowered in lowered_workflows)
    assert any(
        "command" in step
        for lowered in lowered_workflows
        for step in lowered["steps"]
    )
    assert any(
        step.get("provider") == "codex"
        for lowered in lowered_workflows
        for step in lowered["steps"]
    )
    assert any("return__terminal_route" in lowered["outputs"] for lowered in lowered_workflows)
    assert any(
        "return__blocked_recovery_route" in lowered["outputs"]
        for lowered in lowered_workflows
    )
