from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import yaml

from orchestrator.loader import WorkflowLoader
from orchestrator.providers.executor import ProviderExecutor
from orchestrator.state import StateManager
from orchestrator.workflow.executor import WorkflowExecutor
from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _build_runtime_union(tmp_path: Path):
    source_lines = [
        "(workflow-lisp",
        '  (:language "0.1")',
        '  (:target-dsl "2.14")',
        "  (defmodule runtime_union_lineage)",
        "  (export decide)",
        "  (defunion Decision",
        "    (ACCEPTED",
        "      (report String))",
        "    (REJECTED",
        "      (report String)",
        "      (rejected_only String)))",
        "  (defworkflow decide",
        "    ((request String))",
        "    -> Decision",
        "    (provider-result providers.decide",
        "      :prompt prompts.decide",
        "      :inputs (request)",
        "      :returns Decision))",
        ")",
    ]
    source_path = tmp_path / "runtime_union_lineage.orc"
    source_path.write_text("\n".join(source_lines) + "\n", encoding="utf-8")
    prompt_path = tmp_path / "prompts" / "decide.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
    prompt_path.write_text("Choose a decision.\n", encoding="utf-8")
    providers_path = _write_json(
        tmp_path / "providers.json",
        {"providers.decide": "fake-decision-provider"},
    )
    prompts_path = _write_json(
        tmp_path / "prompts.json",
        {"prompts.decide": "prompts/decide.md"},
    )
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="decide",
            provider_externs_path=providers_path,
            prompt_externs_path=prompts_path,
            imported_workflow_bundles_path=None,
            command_boundaries_path=None,
            emit_debug_yaml=False,
            workspace_root=tmp_path,
        )
    )
    return (
        result.validated_bundle,
        source_path,
        source_lines.index("      (report String))") + 1,
        source_lines.index("      (report String)") + 1,
    )


def _execute_runtime_union(
    tmp_path: Path,
    *,
    output_payload: object,
    run_id: str,
    corrupt_source_map: bool = False,
):
    bundle, source_path, accepted_report_line, rejected_report_line = (
        _build_runtime_union(tmp_path)
    )
    if corrupt_source_map:
        source_trace_path = bundle.provenance.frontend_source_trace_path
        assert source_trace_path is not None
        source_trace_path.write_text("{malformed\n", encoding="utf-8")
    state_manager = StateManager(workspace=tmp_path, run_id=run_id)
    state_manager.initialize(
        str(source_path),
        bound_inputs={"request": "decide"},
    )

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
        bundle_path = tmp_path / invocation.env["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        bundle_path.write_text(
            json.dumps(output_payload) + "\n",
            encoding="utf-8",
        )
        return SimpleNamespace(
            exit_code=0,
            stdout=b"ok",
            stderr=b"",
            duration_ms=1,
            error=None,
            missing_placeholders=None,
            invalid_prompt_placeholder=False,
            raw_stdout=None,
            normalized_stdout=None,
            provider_session=None,
        )

    with patch.object(
        ProviderExecutor, "prepare_invocation", _prepare_invocation
    ), patch.object(ProviderExecutor, "execute", _execute):
        state = WorkflowExecutor(bundle, tmp_path, state_manager).execute(
            on_error="continue"
        )

    failed_steps = [
        step_state
        for step_state in state["steps"].values()
        if step_state.get("error", {}).get("type") == "contract_violation"
    ]
    assert len(failed_steps) == 1
    return failed_steps[0], accepted_report_line, rejected_report_line


def test_runtime_union_field_violation_resolves_exact_authored_field_origin(
    tmp_path: Path,
) -> None:
    step_state, accepted_report_line, rejected_report_line = _execute_runtime_union(
        tmp_path,
        output_payload={"variant": "ACCEPTED"},
        run_id="runtime-union-field-lineage",
    )

    assert step_state["status"] == "failed"
    assert step_state["exit_code"] == 2
    violation = step_state["error"]["context"]["violations"][0]
    assert violation["type"] == "variant_required_field_missing"
    assert violation["context"]["variant"] == "ACCEPTED"
    assert violation["context"]["name"] == "report"
    assert violation["subject_refs"][0]["subject_kind"] == "variant_output_field"
    assert len(violation["source_origins"]) == 1
    origin = violation["source_origins"][0]
    assert origin["entity_kind"] == "variant_output_field"
    assert origin["line"] == accepted_report_line
    assert origin["line"] != rejected_report_line


def test_source_free_contract_violation_uses_generated_step_origin(
    tmp_path: Path,
) -> None:
    step_state, _, _ = _execute_runtime_union(
        tmp_path,
        output_payload={},
        run_id="runtime-union-step-fallback",
    )

    violation = step_state["error"]["context"]["violations"][0]
    assert "subject_refs" not in violation
    assert len(violation["source_origins"]) == 1
    assert violation["source_origins"][0]["entity_kind"] == "step_id"


def test_yaml_contract_violation_does_not_invent_source_origin(tmp_path: Path) -> None:
    workflow_path = tmp_path / "workflow.yaml"
    workflow_path.write_text(
        yaml.safe_dump(
            {
                "version": "2.10",
                "name": "yaml-contract-without-provenance",
                "steps": [
                    {
                        "name": "ProduceReport",
                        "command": ["bash", "-lc", "true"],
                        "expected_outputs": [
                            {
                                "name": "report",
                                "path": "state/report.txt",
                                "type": "string",
                            }
                        ],
                    }
                ],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    loaded = WorkflowLoader(tmp_path).load(workflow_path)
    state_manager = StateManager(workspace=tmp_path, run_id="yaml-no-provenance")
    state_manager.initialize(str(workflow_path))

    state = WorkflowExecutor(loaded, tmp_path, state_manager).execute(
        on_error="continue"
    )

    violation = state["steps"]["ProduceReport"]["error"]["context"]["violations"][0]
    assert violation["type"] == "missing_output_file"
    assert set(violation) == {"type", "message", "context"}


def test_malformed_optional_source_map_preserves_contract_failure(
    tmp_path: Path,
) -> None:
    step_state, _, _ = _execute_runtime_union(
        tmp_path,
        output_payload={"variant": "ACCEPTED"},
        run_id="runtime-union-malformed-source-map",
        corrupt_source_map=True,
    )

    assert step_state["status"] == "failed"
    assert step_state["exit_code"] == 2
    violation = step_state["error"]["context"]["violations"][0]
    assert violation["type"] == "variant_required_field_missing"
    assert violation["subject_refs"][0]["subject_kind"] == "variant_output_field"
    assert "source_origins" not in violation


def test_runtime_union_field_violations_receive_independent_origins(
    tmp_path: Path,
) -> None:
    step_state, accepted_report_line, rejected_report_line = _execute_runtime_union(
        tmp_path,
        output_payload={"variant": "ACCEPTED", "rejected_only": "inactive"},
        run_id="runtime-union-independent-origins",
    )

    violations = step_state["error"]["context"]["violations"]
    by_type = {violation["type"]: violation for violation in violations}
    missing = by_type["variant_required_field_missing"]
    forbidden = by_type["variant_forbidden_field_present"]
    assert len(missing["source_origins"]) == 1
    assert len(forbidden["source_origins"]) == 1
    assert missing["source_origins"] is not forbidden["source_origins"]
    assert missing["source_origins"][0]["line"] == accepted_report_line
    assert forbidden["source_origins"][0]["line"] != accepted_report_line
    assert forbidden["source_origins"][0]["line"] != rejected_report_line
    assert missing["source_origins"][0]["origin_key"] != (
        forbidden["source_origins"][0]["origin_key"]
    )
