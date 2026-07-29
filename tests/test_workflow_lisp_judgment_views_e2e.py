"""Deterministic runtime acceptance for the Q4 judgment-panel consumer."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import patch

import pytest

from orchestrator.providers.executor import (
    ProviderExecutionResult,
    ProviderExecutor,
)
from orchestrator.providers.types import (
    InputMode,
    PreparedProviderPolicy,
    ProviderInvocation,
)
from orchestrator.runtime_observability import (
    record_compiled_frontend_provenance,
)
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow.judgment_views import project_judgment_views
from orchestrator.workflow.loaded_bundle import (
    workflow_runtime_input_contracts,
)
from orchestrator.workflow.prompt_attempt_result_binding import (
    PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY,
)
from orchestrator.workflow.signatures import bind_workflow_inputs
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from tests.workflow_bundle_helpers import bundle_context_dict


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / "workflows" / "examples"
PANEL = WORKFLOWS / "review_revise_design_docs_judgment_panel.orc"
PANEL_INPUTS = (
    WORKFLOWS
    / "inputs"
    / "review_revise_design_docs_judgment_panel"
)
FIXTURE = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "judgment_views"
    / "review_revise_design_docs_judgment_panel_case.json"
)
ENTRY = (
    "review_revise_design_docs_judgment_panel"
    "::review-revise-design-docs-judgment-panel"
)
SYNTHESIS_PROMPT = Path(
    "prompts/workflows/review_revise_design_docs/synthesize.md"
)
REPO_SYNTHESIS_PROMPT = (
    REPO_ROOT
    / "prompts"
    / "workflows"
    / "review_revise_design_docs"
    / "synthesize.md"
)
FIX_PROMPT = "prompts/workflows/review_revise_design_docs/fix.md"
SYNTHESIS_PATH = "artifacts/review/q4-panel/synthesis.md"
_TYPED_INPUT_HEADING = re.compile(
    r"^## Typed Prompt Input: (?P<name>[A-Za-z_][A-Za-z0-9_]*)$",
    re.MULTILINE,
)


def _compile_panel(workspace: Path):
    panel_source = workspace / PANEL.name
    panel_source.parent.mkdir(parents=True, exist_ok=True)
    panel_source.write_bytes(PANEL.read_bytes())
    synthesis_prompt = workspace / SYNTHESIS_PROMPT
    synthesis_prompt.parent.mkdir(parents=True, exist_ok=True)
    synthesis_prompt.write_bytes(REPO_SYNTHESIS_PROMPT.read_bytes())
    providers_path = workspace / "providers.json"
    providers_path.write_bytes(
        (PANEL_INPUTS / "providers.json").read_bytes()
    )
    prompts_path = workspace / "prompts.json"
    prompts_path.write_text(
        json.dumps(
            {
                "prompts.design-docs.fix": FIX_PROMPT,
                "prompts.design-docs.synthesize": (
                    SYNTHESIS_PROMPT.as_posix()
                ),
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=panel_source,
            source_roots=(workspace, WORKFLOWS),
            entry_workflow=(
                "review-revise-design-docs-judgment-panel"
            ),
            provider_externs_path=providers_path,
            prompt_externs_path=prompts_path,
            workspace_root=workspace,
            lowering_route="wcc_m4",
        )
    )
    assert result.validated_bundle.surface.name == ENTRY
    return result, result.validated_bundle, panel_source


def _fixture_payload() -> dict[str, Any]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["schema_version"] == (
        "workflow_lisp_judgment_panel_fixture.v1"
    )
    return payload


def _write_required_inputs(
    workspace: Path,
    inputs: dict[str, Any],
) -> None:
    required_files = {
        str(inputs["target_doc"]): "panel target\n",
        str(inputs["checks_report"]): "checks passed\n",
        **{
            str(path): f"context: {path}\n"
            for path in inputs["context_docs"]
        },
    }
    for relpath, content in required_files.items():
        path = workspace / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _typed_prompt_input(prompt: str, name: str) -> Any:
    marker = f"## Typed Prompt Input: {name}\n"
    assert prompt.count(marker) == 1
    rendered = prompt.split(marker, 1)[1].splitlines()[0]
    return json.loads(rendered)


def _typed_path_input(prompt: str, name: str) -> str:
    marker = f"## Typed Prompt Input: {name}\n"
    assert prompt.count(marker) == 1
    return prompt.split(marker, 1)[1].splitlines()[0]


def _typed_prompt_input_names(prompt: str) -> tuple[str, ...]:
    return tuple(
        match.group("name")
        for match in _TYPED_INPUT_HEADING.finditer(prompt)
    )


def _output_bundle_path(
    workspace: Path,
    invocation: ProviderInvocation,
) -> Path:
    path = Path(invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    return path if path.is_absolute() else workspace / path


def _deterministic_provider_hooks(
    workspace: Path,
    *,
    lens_ids: list[str],
    events: list[dict[str, Any]],
):
    prepared_prompts: list[str] = []

    def prepare(
        _self: ProviderExecutor,
        provider_name: str,
        *_args: Any,
        **kwargs: Any,
    ):
        prompt = str(kwargs.get("prompt_content") or "")
        policy = kwargs.get("provider_call_policy") or {}
        prepared_prompts.append(prompt)
        return (
            ProviderInvocation(
                command=["deterministic-panel-provider"],
                input_mode=InputMode.STDIN,
                prompt=prompt,
                env=dict(kwargs.get("env") or {}),
                timeout_sec=kwargs.get("timeout_sec"),
                prepared_prompt=prompt,
                prepared_provider_policy=PreparedProviderPolicy(
                    provider_name=provider_name,
                    model=policy.get("model"),
                    effort=policy.get("effort"),
                    timeout_sec=kwargs.get("timeout_sec"),
                    input_mode="stdin",
                ),
            ),
            None,
        )

    def execute(
        _self: ProviderExecutor,
        invocation: ProviderInvocation,
        **_kwargs: Any,
    ) -> ProviderExecutionResult:
        ordinal = len(events)
        output_path = _output_bundle_path(workspace, invocation)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if ordinal < len(lens_ids):
            lens = lens_ids[ordinal]
            report_path = f"artifacts/review/{lens}"
            findings_path = (
                f"artifacts/work/q4-panel/findings-{ordinal + 1}.json"
            )
            report = workspace / report_path
            report.parent.mkdir(parents=True, exist_ok=True)
            report.write_text(
                f"review-{ordinal + 1}:{lens}\n",
                encoding="utf-8",
            )
            findings = workspace / findings_path
            findings.parent.mkdir(parents=True, exist_ok=True)
            findings.write_text('{"items":[]}\n', encoding="utf-8")
            variant = ("APPROVE", "REVISE", "BLOCKED")[ordinal % 3]
            payload: dict[str, Any] = {
                "variant": variant,
                "review_report": report_path,
                "findings": {
                    "schema_version": "ReviewFindings.v1",
                    "items_path": findings_path,
                },
            }
            if variant == "BLOCKED":
                payload["blocker_class"] = "user_decision_required"
            event = {
                "kind": "review",
                "lens": lens,
                "report": report_path,
                "typed_input_names": _typed_prompt_input_names(
                    invocation.prompt or ""
                ),
            }
        else:
            assert ordinal == len(lens_ids)
            prompt = invocation.prompt or ""
            reports = _typed_prompt_input(prompt, "reports")
            target_doc = _typed_path_input(prompt, "target_doc")
            assert reports == [
                f"artifacts/review/{lens}" for lens in lens_ids
            ]
            synthesis = workspace / SYNTHESIS_PATH
            synthesis.parent.mkdir(parents=True, exist_ok=True)
            synthesis.write_text(
                "\n".join(str(path) for path in reports) + "\n",
                encoding="utf-8",
            )
            payload = SYNTHESIS_PATH
            event = {
                "kind": "synthesis",
                "reports": reports,
                "target_doc": target_doc,
                "typed_input_names": _typed_prompt_input_names(prompt),
            }

        output_path.write_text(
            json.dumps(payload, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        events.append(event)
        return ProviderExecutionResult(0, b"", b"", 1)

    return prepare, execute, prepared_prompts


def _run_panel(
    workspace: Path,
    *,
    lens_ids: list[str],
    run_id: str,
):
    result, bundle, panel_source = _compile_panel(workspace)
    fixture = _fixture_payload()
    inputs = dict(fixture["inputs"])
    inputs["lens_ids"] = list(lens_ids)
    _write_required_inputs(workspace, inputs)
    contracts = {
        name: contract
        for name, contract in workflow_runtime_input_contracts(bundle).items()
        if not name.startswith("__write_root__")
    }
    bound_inputs = bind_workflow_inputs(contracts, inputs, workspace)
    manager = StateManager(workspace, run_id=run_id)
    manager.initialize(
        panel_source.as_posix(),
        context=bundle_context_dict(bundle),
        bound_inputs=bound_inputs,
    )
    events: list[dict[str, Any]] = []
    prepare, execute, prepared_prompts = _deterministic_provider_hooks(
        workspace,
        lens_ids=lens_ids,
        events=events,
    )
    with (
        patch.object(ProviderExecutor, "prepare_invocation", prepare),
        patch.object(ProviderExecutor, "execute", execute),
    ):
        state = WorkflowExecutor(
            bundle,
            workspace,
            manager,
            max_retries=0,
            retry_delay_ms=0,
        ).execute(on_error="stop")
    return result, bundle, manager, state, events, prepared_prompts


def test_panel_executes_ordered_reviews_then_one_ineligible_synthesis(
    tmp_path: Path,
) -> None:
    fixture = _fixture_payload()
    lens_ids = list(fixture["inputs"]["lens_ids"])
    _, bundle, manager, state, events, prepared_prompts = _run_panel(
        tmp_path,
        lens_ids=lens_ids,
        run_id="q4-panel-clean",
    )
    reports = [f"artifacts/review/{lens}" for lens in lens_ids]

    assert state["status"] == "completed", state.get("error")
    assert state["workflow_outputs"] == {
        "return__reports": reports,
        "return__synthesis": SYNTHESIS_PATH,
    }
    assert [event["kind"] for event in events] == [
        "review",
        "review",
        "review",
        "synthesis",
    ]
    assert [event["report"] for event in events[:3]] == reports
    assert events[3] == {
        "kind": "synthesis",
        "reports": reports,
        "target_doc": fixture["inputs"]["target_doc"],
        "typed_input_names": ("target_doc", "reports"),
    }
    assert len(prepared_prompts) == 4
    review_results = [
        frame["state"]["steps"][
            "review_revise_design_docs_judgment_panel::review-one__decision"
        ]
        for frame in state["call_frames"].values()
    ]
    assert len(review_results) == 3
    assert all(
        PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY
        in result["debug"]
        for result in review_results
    )
    synthesis_result = state["steps"][f"{ENTRY}__synthesis"]
    assert (
        PROMPT_ATTEMPT_RESULT_BINDING_DEBUG_KEY
        not in synthesis_result.get("debug", {})
    )

    record_compiled_frontend_provenance(state, bundle.provenance)
    projection = project_judgment_views(
        state,
        manager.run_root,
        workspace_root=tmp_path,
    )
    assert len(projection["judgments"]) == 3
    assert all(
        judgment["status"] == "available"
        for judgment in projection["judgments"]
    )
    assert len(projection["matrices"]) == 1
    assert len(projection["matrices"][0]["members"]) == 3
    assert len(projection["iteration_series"]) == 3
    assert all(
        judgment.get("result", {}).get("value") != SYNTHESIS_PATH
        for judgment in projection["judgments"]
    )


@pytest.mark.parametrize(
    ("lens", "diagnostic"),
    (
        ("", "path_join_under_child_invalid"),
        ("../escape.md", "path_join_under_escape"),
    ),
)
def test_panel_rejects_unsafe_lens_before_provider_launch(
    tmp_path: Path,
    lens: str,
    diagnostic: str,
) -> None:
    _, _, _, state, events, prepared_prompts = _run_panel(
        tmp_path,
        lens_ids=[lens],
        run_id=f"q4-panel-unsafe-{diagnostic}",
    )

    assert state["status"] == "failed"
    assert diagnostic in json.dumps(state, sort_keys=True)
    assert events == []
    assert prepared_prompts == []


def test_panel_duplicate_hits_write_root_guard_without_uniqueness_claim(
    tmp_path: Path,
) -> None:
    duplicate = "q4-panel/duplicate.md"
    _, _, _, state, events, prepared_prompts = _run_panel(
        tmp_path,
        lens_ids=[duplicate, duplicate],
        run_id="q4-panel-duplicate-destination",
    )
    duplicate_report = f"artifacts/review/{duplicate}"

    assert state["status"] == "failed"
    assert "colliding_write_root_binding" in json.dumps(
        state,
        sort_keys=True,
    )
    assert state["workflow_outputs"] == {}
    assert events == [
        {
            "kind": "review",
            "lens": duplicate,
            "report": duplicate_report,
            "typed_input_names": (),
        }
    ]
    assert len(prepared_prompts) == 1
    assert (tmp_path / duplicate_report).read_text(
        encoding="utf-8"
    ) == f"review-1:{duplicate}\n"
