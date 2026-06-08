"""Unit tests for shared artifact publish/consume dataflow helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from orchestrator.workflow.dataflow import DataflowManager


def _contract_violation(message: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "failed",
        "exit_code": 2,
        "error": {
            "type": "contract_violation",
            "message": message,
            "context": context,
        },
    }


def test_enforce_consumes_contract_accepts_collection_artifacts(tmp_path: Path) -> None:
    """Frontend-lowered collection artifacts can be consumed by provider steps."""
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "state-layout.md").write_text("# state layout\n", encoding="utf-8")

    manager = DataflowManager(
        workspace=tmp_path,
        artifact_registry={
            "context_docs": {
                "kind": "collection",
                "type": "list",
                "items": {
                    "type": "relpath",
                    "under": "docs/design",
                    "must_exist_target": True,
                },
            },
        },
        workflow_version="2.14",
        uses_qualified_identities=lambda: True,
        workflow_version_at_least=lambda version: version <= "2.14",
        step_id_resolver=lambda step: str(step.get("id") or step.get("name")),
        contract_violation_result=_contract_violation,
        persist_state=lambda state: None,
        substitute_path_template=lambda path, *_args, **_kwargs: (path, None),
        resolve_workspace_path=lambda path: tmp_path / path,
        current_step_index=lambda: 0,
    )
    state = {
        "artifact_versions": {
            "context_docs": [{
                "version": 1,
                "value": ["state-layout.md"],
                "producer": "seed_context",
                "producer_name": "SeedContext",
                "step_index": 0,
            }],
        },
    }
    step = {
        "name": "Review",
        "id": "review",
        "consumes": [{
            "artifact": "context_docs",
            "policy": "latest_successful",
            "freshness": "any",
        }],
    }

    error = manager.enforce_consumes_contract(step, "Review", state, runtime_step_id="root.review")

    assert error is None
    assert state["_resolved_consumes"]["root.review"]["context_docs"] == [
        "docs/design/state-layout.md",
    ]
