from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from orchestrator.workflow.core_ast import _statement_to_json
from orchestrator.workflow.executable_ir import (
    ProviderStepConfig,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.persisted_surface import (
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.runtime_step import RuntimeStep
from orchestrator.workflow.semantic_ir import workflow_semantic_ir_to_json
from orchestrator.workflow_lisp.build import _json_data
from orchestrator.workflow_lisp.compiler import compile_stage3_module
from orchestrator.workflow_lisp.expressions import ProviderResultExpr
from orchestrator.workflow_lisp.source_map import build_source_map_document
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan


REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURE_ROOT = REPO_ROOT / "tests/fixtures/workflow_lisp/provider_call_policy"
KEYWORD_FREE_FIXTURE = FIXTURE_ROOT / "keyword_free.orc"
KEYWORD_FREE_BASELINE = (
    REPO_ROOT / "tests/baselines/workflow_lisp/provider_call_policy_keyword_free.json"
)
WORKFLOW_NAME = "keyword-free"
NODE_ID = "root.keyword_free__result"
RUNTIME_NAME = "KeywordFreeProvider"
RUNTIME_STEP_ID = "keyword_free_provider"
CONSTANT_SPAN = SourceSpan(
    start=SourcePosition(path="<provider-call-policy-fixture>", line=1, column=1, offset=0),
    end=SourcePosition(path="<provider-call-policy-fixture>", line=1, column=2, offset=1),
)


def _load_manifest(name: str) -> dict[str, str]:
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


def _compile_keyword_free():
    return compile_stage3_module(
        KEYWORD_FREE_FIXTURE.relative_to(REPO_ROOT),
        entry_workflow=WORKFLOW_NAME,
        provider_externs=_load_manifest("providers.json"),
        prompt_externs=_load_manifest("prompts.json"),
        validate_shared=True,
        workspace_root=REPO_ROOT,
        lowering_route="wcc_m4",
    )


def _keyword_free_representation_payload() -> dict[str, Any]:
    result = _compile_keyword_free()
    typed_expr = result.typed_workflows[0].typed_body.expr
    assert isinstance(typed_expr, ProviderResultExpr)
    typed_expr = replace(
        typed_expr,
        provider=replace(typed_expr.provider, span=CONSTANT_SPAN),
        prompt=replace(typed_expr.prompt, span=CONSTANT_SPAN),
        span=CONSTANT_SPAN,
    )

    bundle = result.validated_bundles[WORKFLOW_NAME]
    assert len(bundle.core_workflow_ast.body) == 1
    assert tuple(bundle.ir.nodes) == (NODE_ID,)
    node = bundle.ir.nodes[NODE_ID]
    assert isinstance(node.execution_config, ProviderStepConfig)

    executable_node = workflow_executable_ir_to_json(bundle.ir)["nodes"][NODE_ID]
    return {
        "typed_provider_result": _json_data(typed_expr),
        "core_provider_statement": _statement_to_json(bundle.core_workflow_ast.body[0]),
        "executable_provider_config": executable_node["execution_config"],
        "runtime_step": dict(
            RuntimeStep(node=node, name=RUNTIME_NAME, step_id=RUNTIME_STEP_ID)
        ),
    }


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _contains_key(value: Any, key: str) -> bool:
    if isinstance(value, dict):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_key(item, key) for item in value)
    return False


def test_keyword_free_provider_result_matches_pre_feature_golden_bytes() -> None:
    actual = _canonical_bytes(_keyword_free_representation_payload())

    assert actual == KEYWORD_FREE_BASELINE.read_bytes()


def test_provider_call_policy_projection_exclusions_remain_policy_neutral() -> None:
    result = _compile_keyword_free()
    bundle = result.validated_bundles[WORKFLOW_NAME]
    runtime_plan = _json_data(bundle.runtime_plan)
    semantic_ir = workflow_semantic_ir_to_json(bundle.semantic_ir)
    persisted_graph = serialize_persisted_workflow_surface_graph(bundle)
    source_map = _json_data(
        build_source_map_document(
            SimpleNamespace(
                compiled_results_by_name={"__main__": result},
                validated_bundles_by_name=result.validated_bundles,
            ),
            selected_name=WORKFLOW_NAME,
            display_name_resolver=lambda workflow_name: workflow_name,
        )
    )

    assert runtime_plan["nodes"][NODE_ID]["kind"] == "provider"
    assert any(effect["effect_kind"] == "provider_call" for effect in semantic_ir["effects"].values())
    persisted_steps = persisted_graph["nodes"][WORKFLOW_NAME]["steps"]
    assert [step["kind"] for step in persisted_steps] == ["provider"]
    source_workflow = source_map["workflows"][WORKFLOW_NAME]
    assert [node["step_kind"] for node in source_workflow["core_nodes"]] == ["provider"]
    assert [node["kind"] for node in source_workflow["executable_nodes"]] == ["provider"]

    for projection in (runtime_plan, semantic_ir, persisted_graph, source_map):
        assert not _contains_key(projection, "provider_call_policy")
