"""`agent` types as the opaque `Agent` primitive at 2.38 and carries provider origins."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle_in_memory
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import UsesProviderEffect

MODULE = '''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
  (defmodule main) (export run)
  (defrecord Note (text String))
  (defworkflow run ((task String) (planner String)) -> Note
    (let* ((designer (agent providers.claude :model planner :effort "high"))
           (same designer))
      (provider-result providers.codex :prompt prompts.base :inputs (task) :returns Note))))'''

TEAM = MODULE.replace(
    "(defrecord Note (text String))",
    "(defrecord Note (text String)) (defrecord Team (lead Agent) (label String))",
).replace("(same designer))", '(same designer) (team (record Team :lead {lead} :label "d")))')


def _build(root: Path, source: str):
    (root / "main.orc").write_text(source, encoding="utf-8")
    (root / "prompt.md").write_text("ASSET\n", encoding="utf-8")
    (root / "providers.json").write_text(
        json.dumps({"providers.claude": "claude_unrestricted_workspace", "providers.codex": "codex"}),
        encoding="utf-8",
    )
    (root / "prompts.json").write_text(json.dumps({"prompts.base": {"asset_file": "prompt.md"}}), encoding="utf-8")
    built = build_frontend_bundle_in_memory(FrontendBuildRequest(
        source_path=root / "main.orc",
        source_roots=(root,),
        workspace_root=root,
        provider_externs_path=root / "providers.json",
        prompt_externs_path=root / "prompts.json",
    ))
    return built.compile_result.entry_result.typed_program


def _first_code(root: Path, source: str) -> str:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _build(root, source)
    return excinfo.value.diagnostics[0].code


def test_agent_binding_types_as_opaque_agent_and_uses_its_provider(tmp_path: Path) -> None:
    workflow = _build(tmp_path, MODULE.format(target="2.38")).workflows["main::run"]
    subjects = {e.subject for e in workflow.effect_summary.direct_effects if isinstance(e, UsesProviderEffect)}
    assert subjects == {("providers", "claude"), ("providers", "codex")}


def test_alias_is_accepted_where_agent_is_expected(tmp_path: Path) -> None:
    assert _build(tmp_path, TEAM.format(target="2.38", lead="same")).workflows["main::run"]


def test_string_is_not_an_agent(tmp_path: Path) -> None:
    """A `String` in an `Agent` field fails with the ordinary field-type mismatch code (control: Int field)."""
    agent_as_string = _first_code(tmp_path, TEAM.format(target="2.38", lead="task"))
    control = _first_code(tmp_path, TEAM.format(target="2.38", lead="task").replace("(lead Agent)", "(lead Int)"))
    assert agent_as_string == control


@pytest.mark.parametrize("target", ["2.36", "2.37"])
def test_agent_below_238_refuses_with_target_diagnostic(tmp_path: Path, target: str) -> None:
    assert _first_code(tmp_path, MODULE.format(target=target)) == "agent_target_dsl_unsupported"


@pytest.mark.parametrize("operand", ["task", "prompts.base"])
def test_agent_requires_a_provider_extern(tmp_path: Path, operand: str) -> None:
    source = MODULE.format(target="2.38").replace("(agent providers.claude", f"(agent {operand}")
    assert _first_code(tmp_path, source) == "agent_provider_invalid"


def test_agent_rejects_timeout_and_unknown_keywords(tmp_path: Path) -> None:
    source = MODULE.format(target="2.38").replace(':effort "high"', ':effort "high" :timeout-sec 60')
    assert _first_code(tmp_path, source) == "agent_keyword_invalid"


@pytest.mark.parametrize("keyword, code", [(":model", "agent_model_type_invalid"), (":effort", "agent_effort_type_invalid")])
def test_agent_policy_must_be_a_string(tmp_path: Path, keyword: str, code: str) -> None:
    source = MODULE.format(target="2.38").replace("(agent providers.claude", f"(agent providers.claude {keyword} 3")
    source = source.replace(f'{keyword} planner', "").replace(f'{keyword} "high"', "")
    assert _first_code(tmp_path, source) == code


def test_agent_policy_must_be_inline_lowerable(tmp_path: Path) -> None:
    source = MODULE.format(target="2.38").replace(':model planner', ':model (if true planner "m")')
    assert _first_code(tmp_path, source) == "agent_policy_operand_not_inline_lowerable"


def test_agent_type_name_is_absent_below_238(tmp_path: Path) -> None:
    source = MODULE.format(target="2.37").replace('(agent providers.claude :model planner :effort "high")', '"x"') \
        .replace("(defrecord Note (text String))", "(defrecord Note (text String) (who Agent))")
    assert _first_code(tmp_path, source) == "type_unknown"


@pytest.mark.parametrize("target, accepted", [("2.37", True), ("2.38", False)])
def test_user_type_named_agent_is_reserved_only_from_238(tmp_path: Path, target: str, accepted: bool) -> None:
    source = MODULE.format(target=target).replace('(agent providers.claude :model planner :effort "high")', '"x"') \
        .replace("(defrecord Note (text String))", "(defrecord Note (text String)) (defrecord Agent (n String))")
    if accepted:
        assert _build(tmp_path, source).workflows["main::run"]
    else:
        assert _first_code(tmp_path, source) == "prelude_type_name_reserved"


def test_agent_inside_a_pure_definition_is_refused_like_any_effect(tmp_path: Path) -> None:
    pure = MODULE.format(target="2.38").replace(
        "(defworkflow run", "(defun helper () -> Agent (agent providers.claude))\n  (defworkflow run")
    control = pure.replace("(agent providers.claude)", "(provider-result providers.claude :prompt prompts.base :inputs () :returns Note)") \
        .replace("-> Agent", "-> Note")
    assert _first_code(tmp_path, pure) == _first_code(tmp_path, control)


def test_agent_factory_procedure_returns_an_agent(tmp_path: Path) -> None:
    source = MODULE.format(target="2.38").replace(
        "(defworkflow run", "(defproc make () -> Agent :effects ((uses-provider providers.claude)) (agent providers.claude))\n  (defworkflow run") \
        .replace("(same designer))", "(same designer) (made (make)))")
    assert _build(tmp_path, source).workflows["main::run"]


def test_origins_are_exact_through_let_aliases_and_conservative_otherwise() -> None:
    from types import SimpleNamespace

    from orchestrator.workflow_lisp.compiler_session import TypecheckSessionState
    from orchestrator.workflow_lisp.expressions import AgentExpr, NameExpr
    from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.typecheck_agents import agent_origins, record_agent_origin
    from orchestrator.workflow_lisp.typecheck_proofs import BindingIdentity
    from orchestrator.workflow_lisp.workflows import ExternEnvironment, ProviderExtern

    position = SourcePosition(path="main.orc", line=1, column=1, offset=0)
    span = SourceSpan(start=position, end=position)

    def name(text: str) -> NameExpr:
        return NameExpr(name=text, span=span, form_path=())

    def let(text: str) -> BindingIdentity:
        return BindingIdentity(path=(), kind="let", name=text, ordinal=0)

    agent_type = PrimitiveTypeRef(name="Agent")
    context = SimpleNamespace(
        session_state=TypecheckSessionState(),
        extern_environment=ExternEnvironment(bindings_by_name={
            "providers.claude": ProviderExtern(name="providers.claude", provider_id="claude"),
            "providers.codex": ProviderExtern(name="providers.codex", provider_id="codex"),
        }),
        binding_env={},
    )
    designer, same = let("designer"), let("same")
    record_agent_origin(context, designer, AgentExpr(provider=name("providers.claude"), span=span, form_path=()),
                        agent_type, {})
    record_agent_origin(context, same, name("designer"), agent_type, {"designer": designer})
    shadowed = let("designer")   # equal fields, different binder: must not inherit origins
    context.binding_env = {"designer": shadowed, "same": same}
    assert (agent_origins(name("same"), context), agent_origins(name("designer"), context),
            agent_origins(name("unbound"), context)) == (
        frozenset({"providers.claude"}),
        frozenset({"providers.claude", "providers.codex"}),
        frozenset({"providers.claude", "providers.codex"}),
    )
