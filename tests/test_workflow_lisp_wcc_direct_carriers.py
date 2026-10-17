from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed import command_templates
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.wcc.model import WccOpaqueFrontendValue, WccPerform
from tests.test_workflow_lisp_closed_command_requests import _prepared_entry
from tests.test_workflow_lisp_closed_command_transport import _walk_wcc
from tests.workflow_lisp_closed_program_helpers import build, install


@pytest.mark.parametrize("operand", ["(let* () input)", "(let* ((inside (+ input 1))) inside)"])
def test_direct_expansion_blocks_translate_without_opaque_bridge(tmp_path: Path, monkeypatch, operand):
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/direct_block) (export run)
      (defun keep ((value Int)) -> Int value)
      (defworkflow run ((input Int)) -> Int (keep {operand})))'''

    def forbidden(*args, **kwargs):
        pytest.fail("a prepared expansion block used the opaque translator")

    monkeypatch.setattr(command_templates, "prepare_frontend_value", forbidden)
    program = build(tmp_path, source, boundaries={}, providers={}, prompts={})
    from orchestrator.contracts.closed_program.program import ClosedProgram
    assert ClosedProgram.from_artifact(program.artifact()).tree == program.tree


def test_prepared_prompt_payload_has_only_resolved_rows(tmp_path: Path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/prepared_prompt) (export run)
      (defrecord Answer (accepted Bool))
      (defprompt review (:fills (message :text) (score :value Int)) -> Answer
        "{message} {score} {message}")
      (defworkflow run ((message String) (score Int)) -> Answer
        (provider-result provider :prompt (review :score score :message message))))'''
    path = install(tmp_path, source)
    typed = compile_typed_program(path, entry_workflow="cp/prepared_prompt::run",
        source_roots=(tmp_path,), command_boundaries={}, provider_externs={"provider": "probe-provider"}, workspace_root=tmp_path)
    body, _, _ = _prepared_entry(typed)
    assert not any(isinstance(node, WccOpaqueFrontendValue) for node in _walk_wcc(body))
    (perform,) = [node for node in _walk_wcc(body) if isinstance(node, WccPerform)]
    application = perform.operation_payload["prompt_application"]
    assert isinstance(application, Mapping)
    assert [row["name"] for row in application["fills"]] == ["message", "score"]
    assert [row["placeholder_ordinals"] for row in application["fills"]] == [(0, 2), (1,)]
    assert [row["renderer_id"] for row in application["fills"]] == ["raw-utf8-string", "canonical-json"]
    assert [row["type_ref"].name for row in application["fills"]] == ["String", "Int"]
    closed = build_closed_program(typed)
    from orchestrator.contracts.closed_program.sites import _ast_nodes
    (effect,) = [node for node in _ast_nodes(closed.tree["body"]) if node["k"] == "perform"]
    assert effect["prompt"]["fills"][1]["value"]["k"] == "name"


@pytest.mark.parametrize("generic", [False, True])
def test_direct_variant_literal_keeps_its_discriminant_owner(tmp_path: Path, generic):
    from orchestrator.workflow_lisp.effects import EMPTY_EFFECT_SUMMARY
    from orchestrator.workflow_lisp.expressions import UnionVariantTagExpr
    from orchestrator.workflow_lisp.type_env import DiscriminantTypeRef
    from orchestrator.workflow_lisp.wcc.elaborate import _elaborate_expr_to_value
    from orchestrator.workflow_lisp.wcc.model import WccIdentityFactory, WccLiteralAtom

    declaration = "(defunion Choice :forall (T) (YES (value T)) (NO))" if generic else "(defunion Choice (YES (value Int)) (NO))"
    applied = "Choice[Int]" if generic else "Choice"
    path = install(tmp_path, f'''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/direct_tag) (export run) {declaration}
      (defworkflow run ((choice {applied}) (other {applied})) -> Bool (= choice.variant other.variant)))''')
    program = compile_typed_program(path, entry_workflow="cp/direct_tag::run", source_roots=(tmp_path,),
        command_boundaries={}, workspace_root=tmp_path)
    types = program.workflow_type_env(program.entry.definition.name)
    owner = dict(program.entry.signature.params)["choice"]
    original = program.entry.typed_body.expr
    expr = UnionVariantTagExpr(union_name=owner.name, variant_name="YES", variant_names=("YES", "NO"),
        span=original.span, form_path=original.form_path, discriminant_owner=owner)
    prefix, value = _elaborate_expr_to_value(expr,
        scope=WccIdentityFactory(owner_name="tag", ), type_env=types,
        value_env={}, workflow_return_types={}, procedure_return_types={},
        effect_summary=EMPTY_EFFECT_SUMMARY, procedure_edges_by_site={}, compile_time_bindings={})
    assert prefix == () and isinstance(value, WccLiteralAtom)
    assert value.value == "YES" and isinstance(value.metadata.type_ref, DiscriminantTypeRef)
    assert value.metadata.type_ref.owner_union is owner
    assert value.metadata.type_ref.variant_names == ("YES", "NO")
    assert value.metadata.type_ref.applied_union == (owner if generic else None)


def test_halt_block_keeps_the_expansion_owner_provenance(tmp_path: Path):
    from orchestrator.workflow_lisp.wcc.model import WccBlock, WccHalt

    path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule cp/halt_provenance) (export run)
      (defun keep ((value Int)) -> Int value)
      (defworkflow run ((input Int)) -> Int (keep (let* () input))))''')
    typed = compile_typed_program(path, entry_workflow="cp/halt_provenance::run",
        source_roots=(tmp_path,), command_boundaries={}, workspace_root=tmp_path)
    body, _, builder = _prepared_entry(typed)
    (block,) = [node for node in _walk_wcc(body) if isinstance(node, WccBlock)]
    assert isinstance(block.body, WccHalt)
    assert builder.provenance(block.metadata) != builder.provenance(block.body.result.metadata)
    owner = typed.entry.definition.name
    context = builder.definition_context(canonical=owner, owner=owner, source_program=typed,
        type_env=typed.workflow_type_env(owner), node=typed.entry.typed_body,
        params=typed.entry.definition.params, callable_def=typed.entry)
    translated = builder.value(block, context.with_names({"input": "input"}), dict(typed.entry.signature.params))
    assert translated["k"] == "name"
    assert translated["@"] == builder.provenance(block.metadata)["@"]


@pytest.mark.parametrize("kind", ["command_result", "provider_result", "agent_turn"])
def test_payload_walks_runtime_values_and_preserves_static_guidance(kind):
    from dataclasses import replace
    from orchestrator.workflow_lisp.closed.command_templates import _wcc_call_nodes
    from orchestrator.workflow_lisp.expressions import NameExpr
    from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.wcc.elaborate import _substitute_wcc_binding_value
    from orchestrator.workflow_lisp.wcc.hygiene import _free_names, _renamed
    from orchestrator.workflow_lisp.wcc.model import (
        WccBlock, WccCall, WccHalt, WccIdentityFactory, WccLet, WccNameAtom,
    )

    position = SourcePosition(path="payload.orc", line=1, column=1, offset=0)
    span = SourceSpan(start=position, end=position)
    metadata = WccIdentityFactory(owner_name="payload").value_metadata(
        role="operand", type_ref=PrimitiveTypeRef(name="Int"), source_span=span, form_path=())
    argument = WccNameAtom(metadata=metadata, name="input")
    call = WccCall(metadata=metadata, callee_name="keep", specialized_callee_name="keep", args=(argument,))
    local = WccNameAtom(metadata=metadata, name="local")
    block = WccBlock(metadata=metadata, body=WccLet(metadata=metadata, bound_name="local",
        bound_type_ref=metadata.type_ref, bound_value=call, body=WccHalt(metadata=metadata, result=local)))
    guidance = NameExpr(name="static", span=span, form_path=())
    payload = ({"adapter_inputs": (("input", block),), "return_spec": guidance,
        "argv_transport": [{"kind": "template", "parts": [{"kind": "slot", "value": argument}]}]}
        if kind == "command_result" else {"return_spec": guidance, "model": argument,
            "prompt_application": {"template": "", "fills": ({"value": block},)},
            **({"materialization_attempts": argument} if kind == "provider_result" else {})})
    perform = WccPerform(metadata=metadata, perform_kind=kind, target_name="target", prompt_name=None,
        positional_args=(), keyword_args=(), returns_type_name="Int", operation_payload=payload)
    assert [node for node, _ in _wcc_call_nodes(perform)] == [call]
    assert _free_names(perform) == {"input"}
    renamed = _renamed(perform, {"input": "outer", "static": "wrong"})
    assert _free_names(renamed) == {"outer"}
    assert renamed.operation_payload["return_spec"] is guidance
    substituted = _substitute_wcc_binding_value(perform, {"input": replace(argument, name="outer")})
    assert _free_names(substituted) == {"outer"}
    assert substituted.operation_payload["return_spec"] is guidance


def test_historical_resume_payload_keeps_its_lexical_references(tmp_path):
    from orchestrator.workflow_lisp.type_env import FrontendTypeEnvironment
    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.hygiene import _free_names, _renamed
    from tests.test_workflow_lisp_phase_stdlib import _compile, VALID_RESUME_FIXTURE

    result = _compile(VALID_RESUME_FIXTURE, tmp_path=tmp_path)
    workflow = next(row for row in result.typed_workflows if row.definition.name.endswith("resume-record-phase"))
    body = elaborate_typed_workflow_body(workflow.typed_body,
                                    owner_name=workflow.definition.name,
                                    value_env=dict(workflow.signature.params),
        type_env=FrontendTypeEnvironment.from_module(result.module),
        workflow_return_types={row.definition.name: row.signature.return_type_ref for row in result.typed_workflows},
        procedure_return_types={row.definition.name: row.signature.return_type_ref for row in result.typed_procedures})
    perform = next(node for node in _walk_wcc(body)
        if isinstance(node, WccPerform) and node.perform_kind == "resume_or_start")
    assert _free_names(perform) == _free_names(perform.operation_payload) == {"inputs", "phase-ctx"}
    renamed = _renamed(perform, {"phase-ctx": "renamed-ctx"})
    assert renamed.operation_payload.ctx_expr.name == "renamed-ctx"
