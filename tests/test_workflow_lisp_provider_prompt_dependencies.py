from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from orchestrator.workflow.executable_ir import workflow_executable_ir_to_json
from orchestrator.workflow.persisted_surface import serialize_persisted_workflow_surface_graph
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.build import _json_data
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.source_map import build_source_map_document


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workflow_lisp/provider_prompt_dependencies"
BASELINE = REPO_ROOT / "tests/baselines/workflow_lisp/provider_prompt_dependencies_keyword_free.json"


def _manifest(name: str) -> dict[str, str]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _artifact(value: Any) -> dict[str, str]:
    data = _canonical(value)
    return {"canonical_bytes": data.decode("ascii"), "sha256": f"sha256:{hashlib.sha256(data).hexdigest()}"}


def _route_artifacts(route: str) -> dict[str, dict[str, str]]:
    result = compile_stage3_module(
        (FIXTURE_ROOT / "keyword_free.orc").relative_to(REPO_ROOT),
        entry_workflow="keyword-free",
        provider_externs=_manifest("providers.json"),
        prompt_externs=_manifest("prompts.json"),
        validate_shared=True,
        workspace_root=REPO_ROOT,
        lowering_route=route,
    )
    lowered = result.lowered_workflows[0]
    bundle = result.validated_bundles["keyword-free"]
    source_map = _json_data(
        build_source_map_document(
            SimpleNamespace(
                compiled_results_by_name={"__main__": result},
                validated_bundles_by_name=result.validated_bundles,
            ),
            selected_name="keyword-free",
            display_name_resolver=lambda name: name,
        )
    )
    return {
        "frontend_ast": _artifact(_json_data(result.module)),
        "lowered_mapping": _artifact(lowered.authored_mapping),
        "core_ast": _artifact(_json_data(bundle.core_workflow_ast)),
        "executable_ir": _artifact(workflow_executable_ir_to_json(bundle.ir)),
        "semantic_ir": _artifact(workflow_semantic_ir_to_json(bundle.semantic_ir)),
        "persisted_surface": _artifact(serialize_persisted_workflow_surface_graph(bundle)),
        "runtime_plan": _artifact(_json_data(bundle.runtime_plan)),
        "source_map": _artifact(source_map),
    }


def test_keyword_free_provider_result_matches_preimplementation_dual_route_baseline() -> None:
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert expected["schema"] == "provider_prompt_dependencies_keyword_free_baseline.v1"
    assert expected["implementation_base_commit"] == "451765a2ebd374111d2cbeab0969cec4830717fb"
    assert expected["routes"] == {
        "classic_direct": _route_artifacts("legacy"),
        "wcc_schema_2": _route_artifacts("wcc_m4"),
    }
