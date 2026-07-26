import hashlib
import json
from pathlib import Path

from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.wcc.route import LoweringRoute


def test_frontend_build_preserves_value_boundary_and_digest_binds_surface(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "value_build_contract.orc"
    source_path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.19")',
                "  (defmodule value_build_contract)",
                "  (export entry)",
                "  (defproc pass-value",
                "    ((payload Value))",
                "    -> Value",
                "    :effects ()",
                "    :lowering inline",
                "    payload)",
                "  (defworkflow entry ((payload Value)) -> Value",
                "    (pass-value payload)))",
                "",
            )
        ),
        encoding="utf-8",
    )

    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )

    surface_path = result.artifact_paths["persisted_workflow_surface"]
    surface_bytes = surface_path.read_bytes()
    persisted_surface = json.loads(surface_bytes)
    canonical_name = "value_build_contract::entry"

    assert persisted_surface["entry_workflow"] == canonical_name
    assert persisted_surface["nodes"][canonical_name]["workflow_name"] == canonical_name

    boundary_projection = json.loads(
        result.artifact_paths["workflow_boundary_projection"].read_bytes()
    )
    [selected_boundary] = [
        workflow
        for workflow in boundary_projection["workflows"]
        if workflow["workflow_name"] == canonical_name
    ]
    assert selected_boundary["flattened_inputs"] == [
        {
            "contract_definition": {"kind": "value", "type": "value"},
            "generated_name": "payload",
            "source_path": ["payload"],
        }
    ]
    assert selected_boundary["flattened_outputs"] == [
        {
            "contract_definition": {"kind": "value", "type": "value"},
            "generated_name": "__result__",
            "source_path": ["return"],
        }
    ]

    expected_surface_sha = "sha256:" + hashlib.sha256(surface_bytes).hexdigest()
    assert result.manifest.persisted_workflow_surface["sha256"] == expected_surface_sha
    assert (
        result.validated_bundle.provenance.frontend_persisted_surface_sha256
        == expected_surface_sha
    )
