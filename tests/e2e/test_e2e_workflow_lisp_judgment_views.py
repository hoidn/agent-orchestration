"""Bounded real-provider acceptance for the Q4 judgment panel."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import pytest

from orchestrator.cli.commands import resume as resume_command
from orchestrator.cli.commands.report import _state_only_snapshot
from orchestrator.observability.report import build_status_snapshot
from orchestrator.providers.control import ProviderExecutionControl
from orchestrator.providers.executor import (
    ProviderExecutionResult,
    ProviderExecutor,
)
from orchestrator.providers.observation import ProviderObservationHandle
from orchestrator.providers.types import ProviderInvocation
from orchestrator.runtime_observability import (
    record_compiled_frontend_provenance,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.judgment_views import (
    validate_judgment_views_projection,
)
from orchestrator.workflow.loaded_bundle import (
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.prompt_identity import canonical_json_bytes
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.wcc.route import (
    workflow_lisp_context_with_lowering_schema,
)
from tests.e2e.conftest import skip_if_no_cli, skip_if_no_e2e
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = REPO_ROOT / "workflows" / "examples"
PANEL = WORKFLOWS / "review_revise_design_docs_judgment_panel.orc"
PANEL_INPUTS = (
    WORKFLOWS
    / "inputs"
    / "review_revise_design_docs_judgment_panel"
)
ENTRY = (
    "review_revise_design_docs_judgment_panel"
    "::review-revise-design-docs-judgment-panel"
)


def _git_value(checkout: Path, expression: str) -> str:
    return subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", expression],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _view_digest(view: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(
        canonical_json_bytes(view)
    ).hexdigest()


@pytest.mark.e2e
def test_judgment_views_real_provider_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run the public panel naturally, then prove completed reuse is read-only."""

    skip_if_no_e2e()
    for executable in ("codex", "git"):
        skip_if_no_cli(executable)

    trusted_checkout_value = os.environ.get(
        "ORCHESTRATE_E2E_TRUSTED_CHECKOUT"
    )
    assert trusted_checkout_value
    trusted_checkout = Path(trusted_checkout_value).resolve()
    assert trusted_checkout == REPO_ROOT.resolve()
    assert Path(
        _git_value(trusted_checkout, "--show-toplevel")
    ).resolve() == trusted_checkout

    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=PANEL,
            source_roots=(WORKFLOWS,),
            entry_workflow=(
                "review-revise-design-docs-judgment-panel"
            ),
            provider_externs_path=PANEL_INPUTS / "providers.json",
            prompt_externs_path=PANEL_INPUTS / "prompts.json",
            workspace_root=trusted_checkout,
            lowering_route="wcc_m4",
        )
    )
    bundle = result.validated_bundle
    assert bundle.surface.name == ENTRY

    inputs = json.loads(
        (PANEL_INPUTS / "panel_inputs.json").read_text(
            encoding="utf-8"
        )
    )
    inputs.update(
        {
            "target_doc": (
                "docs/design/workflow_lisp_judgment_views.md"
            ),
            "context_docs": [
                "docs/design/workflow_lisp_prompt_calculus.md"
            ],
            "checks_report": "artifacts/work/q4-task8/checks.md",
            "review_model": "gpt-5.5",
            "review_effort": "high",
            "synthesis_model": "gpt-5.5",
            "synthesis_effort": "high",
        }
    )
    assert inputs["lens_ids"] == [
        "q4-panel/architecture-quality.md",
        "q4-panel/contract-correctness.md",
        "q4-panel/operational-clarity.md",
    ]
    checks_path = trusted_checkout / inputs["checks_report"]
    checks_path.parent.mkdir(parents=True, exist_ok=True)
    checks_path.write_text(
        (
            "Q4 Task 8 bounded real-provider acceptance preflight passed.\n"
            "Leave workflow-adapter execution to the runtime after provider "
            "close. Inside this provider call, do not invoke "
            "`orchestrator.workflow_lisp.adapters` commands or any command "
            "that writes `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` after creating "
            "the required ReviewDecision bundle. Use read-only JSON "
            "inspection for self-checks; the runtime validates referenced "
            "findings after the provider exits.\n"
        ),
        encoding="utf-8",
    )

    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(
            bundle
        ).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(
        contracts,
        inputs,
        trusted_checkout,
    )
    manager = StateManager(trusted_checkout)
    run_context = workflow_lisp_context_with_lowering_schema(
        bundle_context_dict(bundle),
        result.manifest.lowering_schema_version,
    )
    manager.initialize(
        PANEL.as_posix(),
        context=run_context,
        bound_inputs=bound_inputs,
    )
    with manager.state_transaction() as transaction_state:
        record_compiled_frontend_provenance(
            transaction_state,
            bundle.provenance,
        )
    persisted_state = json.loads(
        manager.state_file.read_text(encoding="utf-8")
    )
    assert persisted_state["context"] == run_context
    persisted_surface = persisted_state["runtime_observability"][
        "compiled_frontend"
    ]["persisted_workflow_surface"]
    persisted_surface_path = (
        bundle.provenance.frontend_persisted_surface_path
    )
    assert isinstance(persisted_surface_path, Path)
    assert persisted_surface == {
        "schema_version": (
            bundle.provenance.frontend_persisted_surface_schema_version
        ),
        "path": persisted_surface_path.as_posix(),
        "entry_workflow": (
            bundle.provenance.frontend_persisted_surface_entry_workflow
        ),
        "sha256": (
            bundle.provenance.frontend_persisted_surface_sha256
        ),
    }

    original_execute = ProviderExecutor.execute
    provider_calls: list[dict[str, Any]] = []

    def checked_execute(
        self: ProviderExecutor,
        invocation: ProviderInvocation,
        cwd: Path | None = None,
        stream_output: bool = False,
        session_runtime: dict[str, Any] | None = None,
        control: ProviderExecutionControl | None = None,
        *,
        observation_handle: ProviderObservationHandle | None = None,
    ) -> ProviderExecutionResult:
        resolved_cwd = Path(cwd or self.workspace).resolve()
        assert resolved_cwd == trusted_checkout
        assert invocation.command[:2] == ["codex", "exec"]
        assert (
            invocation.command.count(
                "--dangerously-bypass-approvals-and-sandbox"
            )
            == 1
        )
        assert invocation.timeout_sec == 3600
        provider_calls.append(
            {
                "argv": list(invocation.command),
                "cwd": str(resolved_cwd),
            }
        )
        execution = original_execute(
            self,
            invocation,
            cwd=cwd,
            stream_output=stream_output,
            session_runtime=session_runtime,
            control=control,
            observation_handle=observation_handle,
        )
        assert execution.exit_code == 0
        assert execution.error is None
        return execution

    monkeypatch.setattr(
        ProviderExecutor,
        "execute",
        checked_execute,
    )
    started_at = datetime.now(timezone.utc).isoformat()
    completed = WorkflowExecutor(
        bundle,
        trusted_checkout,
        manager,
        max_retries=0,
        retry_delay_ms=0,
        stream_output=True,
    ).execute(on_error="stop")

    assert completed["status"] == "completed", completed.get("error")
    assert len(provider_calls) == 4
    expected_reports = [
        f"artifacts/review/{lens}"
        for lens in inputs["lens_ids"]
    ]
    assert completed["workflow_outputs"]["return__reports"] == (
        expected_reports
    )
    assert all(
        (trusted_checkout / path).is_file()
        for path in expected_reports
    )
    synthesis = completed["workflow_outputs"][
        "return__synthesis"
    ]
    assert (trusted_checkout / synthesis).is_file()

    loaded_view = validate_judgment_views_projection(
        build_status_snapshot(
            bundle,
            completed,
            manager.run_root,
        )["judgment_views"]
    )
    state_only_view = validate_judgment_views_projection(
        _state_only_snapshot(
            completed,
            manager.run_root,
        )["judgment_views"]
    )
    assert canonical_json_bytes(loaded_view) == canonical_json_bytes(
        state_only_view
    )
    assert len(loaded_view["judgments"]) == 3
    assert all(
        row["status"] == "available"
        for row in loaded_view["judgments"]
    )
    assert len(loaded_view["matrices"]) == 1
    assert len(loaded_view["matrices"][0]["members"]) == 3
    assert all(
        f"__loop#{index}." in member["coordinate"]["call_frame_path"][0]
        for index, member in enumerate(
            loaded_view["matrices"][0]["members"]
        )
    )
    assert len(loaded_view["disagreements"]) == 1
    assert len(loaded_view["iteration_series"]) == 3

    calls_before_resume = len(provider_calls)
    state_bytes_before_resume = manager.state_file.read_bytes()
    monkeypatch.setattr(
        resume_command,
        "_load_resume_workflow_bundle",
        lambda **_kwargs: resume_command.ResumeWorkflowBundle(
            bundle=bundle,
            lowering_schema_version=(
                result.manifest.lowering_schema_version
            ),
        ),
    )
    monkeypatch.chdir(trusted_checkout)
    assert (
        resume_command.resume_workflow(
            run_id=manager.run_id,
            repair=False,
            force_restart=False,
        )
        == 0
    )
    assert manager.state_file.read_bytes() == state_bytes_before_resume
    resume_manager = StateManager(
        trusted_checkout,
        run_id=manager.run_id,
    )
    resumed = resume_manager.load().to_dict()
    assert resumed["status"] == "completed"
    assert resumed["workflow_outputs"] == completed["workflow_outputs"]
    assert len(provider_calls) == calls_before_resume

    resumed_loaded_view = validate_judgment_views_projection(
        build_status_snapshot(
            bundle,
            resumed,
            resume_manager.run_root,
        )["judgment_views"]
    )
    resumed_state_only_view = validate_judgment_views_projection(
        _state_only_snapshot(
            resumed,
            resume_manager.run_root,
        )["judgment_views"]
    )
    assert resumed_loaded_view == loaded_view
    assert resumed_state_only_view == state_only_view

    finished_at = datetime.now(timezone.utc).isoformat()
    loaded_digest = _view_digest(loaded_view)
    state_only_digest = _view_digest(state_only_view)
    assert loaded_digest == state_only_digest
    print(
        "Q4_TASK8_REAL_PROVIDER_SUMMARY "
        + json.dumps(
            {
                "commit": _git_value(trusted_checkout, "HEAD"),
                "tree": _git_value(
                    trusted_checkout,
                    "HEAD^{tree}",
                ),
                "started_at": started_at,
                "finished_at": finished_at,
                "run_id": manager.run_id,
                "run_root": str(manager.run_root),
                "provider_call_count": len(provider_calls),
                "resume_replay_count": (
                    len(provider_calls) - calls_before_resume
                ),
                "loaded_view_sha256": loaded_digest,
                "state_only_view_sha256": state_only_digest,
            },
            sort_keys=True,
            separators=(",", ":"),
        ),
        flush=True,
    )
