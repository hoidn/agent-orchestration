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


def test_record_published_artifacts_routes_private_collection_publication_to_private_artifact_versions(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "state-layout.md").write_text("# state layout\n", encoding="utf-8")

    manager = DataflowManager(
        workspace=tmp_path,
        artifact_registry={},
        private_artifact_registry={
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
        current_step_index=lambda: 2,
    )
    state = {
        "artifact_versions": {
            "public_report": [{
                "version": 1,
                "value": "artifacts/work/report.md",
                "producer": "root.seed",
                "producer_name": "Seed",
                "step_index": 0,
            }],
        },
        "private_artifact_versions": {},
    }
    step = {
        "name": "CollectContext",
        "id": "collect_context",
        "publishes": [{"artifact": "context_docs", "from": "context_docs"}],
    }
    result = {
        "exit_code": 0,
        "artifacts": {
            "context_docs": ["state-layout.md"],
        },
        "step_id": "root.collect_context",
    }

    error = manager.record_published_artifacts(step, "CollectContext", result, state)

    assert error is None
    assert state["artifact_versions"] == {
        "public_report": [{
            "version": 1,
            "value": "artifacts/work/report.md",
            "producer": "root.seed",
            "producer_name": "Seed",
            "step_index": 0,
        }],
    }
    assert state["private_artifact_versions"]["context_docs"] == [{
        "version": 1,
        "value": ["docs/design/state-layout.md"],
        "producer": "root.collect_context",
        "producer_name": "CollectContext",
        "step_index": 2,
        "catalog_ref": "context_docs",
    }]


def test_enforce_consumes_contract_resolves_private_collection_artifacts_from_private_lane(
    tmp_path: Path,
) -> None:
    (tmp_path / "docs" / "design").mkdir(parents=True)
    (tmp_path / "docs" / "design" / "state-layout.md").write_text("# state layout\n", encoding="utf-8")

    manager = DataflowManager(
        workspace=tmp_path,
        artifact_registry={},
        private_artifact_registry={
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
        "artifact_versions": {},
        "private_artifact_versions": {
            "context_docs": [{
                "version": 3,
                "value": ["state-layout.md"],
                "producer": "root.collect_context",
                "producer_name": "CollectContext",
                "step_index": 1,
                "catalog_ref": "context_docs",
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
    assert state["_pending_private_artifact_consumes"]["root.review"] == {"context_docs": 3}


def test_finalize_consumes_commits_private_collection_freshness_to_private_artifact_consumes(
    tmp_path: Path,
) -> None:
    manager = DataflowManager(
        workspace=tmp_path,
        artifact_registry={},
        private_artifact_registry={
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
        "artifact_consumes": {},
        "private_artifact_consumes": {},
        "_pending_private_artifact_consumes": {"root.review": {"context_docs": 4}},
        "_resolved_consumes": {"root.review": {"context_docs": ["docs/design/state-layout.md"]}},
    }
    step = {
        "name": "Review",
        "id": "review",
        "consumes": [{
            "artifact": "context_docs",
            "policy": "latest_successful",
            "freshness": "since_last_consume",
        }],
    }

    manager.finalize_consumes(step, "Review", state, runtime_step_id="root.review", succeeded=True)

    assert state["artifact_consumes"] == {}
    assert state["private_artifact_consumes"]["root.review"] == {"context_docs": 4}
    assert state["private_artifact_consumes"]["__global__"] == {"context_docs": 4}
