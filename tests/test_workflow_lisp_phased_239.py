from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.check import CheckedFormError, validate
from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.contracts.closed_program.sites import _ast_nodes, assign_sites
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def _source(target: str, sections: str = ":delivery :phased :timeout-sec 60") -> str:
    return f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule phased239) (export run)
      (defrecord Review (approved Bool))
      (defprompt review (:fills (subject :text)) -> Review "Review {{subject}}")
      (defworkflow run ((subject String)) -> Review
        (provider-result providers.review :prompt (review :subject subject)
          :model "bound-model" :effort "bound-effort" {sections})))'''


def _compile(path: Path, source: str, *, prompt_externs=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="phased239::run",
        source_roots=(path.parent,),
        command_boundaries={},
        provider_externs={"providers.review": "test-provider"},
        prompt_externs=prompt_externs or {},
        workspace_root=path.parent,
    )
    return build_closed_program(typed)


def _compile_modules(tmp_path: Path, sources: dict[str, str], entry_workflow: str):
    for relative, source in sources.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
    entry_path = tmp_path / "main.orc"
    typed = compile_typed_program(
        entry_path,
        entry_workflow=entry_workflow,
        source_roots=(tmp_path,),
        command_boundaries={},
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        workspace_root=tmp_path,
    )
    return build_closed_program(typed)


def _provider_effect(program):
    effects = [
        node
        for body in (program.tree["body"], *(row["body"] for row in program.tree["definitions"].values()))
        for node in _ast_nodes(body)
        if node.get("k") == "perform" and node.get("class", "").startswith("provider")
    ]
    assert len(effects) == 1
    return effects[0]


def test_target_239_phased_provider_is_a_closed_provider_coordinator(tmp_path: Path) -> None:
    program = _compile(tmp_path / "phased239.orc", _source("2.39"))
    effect = _provider_effect(program)

    assert effect["class"] == "provider_phased"
    assert effect["repeat"] == "rerun"
    assert effect["policy"]["delivery"]["v"] == "phased"
    assert effect["policy"]["delivery"]["type"] == {"kind": "primitive", "name": "String"}
    assert effect["policy"]["materialization_attempts"]["v"] == 2
    assert effect["policy"]["materialization_attempts"]["type"] == {"kind": "primitive", "name": "Int"}
    assert effect["policy"]["model"]["v"] == "bound-model"
    assert effect["policy"]["effort"]["v"] == "bound-effort"
    assert set(effect["prompt"]) == {"template", "fills"}
    artifact = program.artifact()
    (tmp_path / "phased239.orc").unlink()
    restored = ClosedProgram.from_artifact(artifact)
    assert restored.tree == program.tree
    assert restored.sites == program.sites
    assert restored.digest == program.digest


def test_target_239_phased_provider_rejects_empty_generated_record_contract(tmp_path: Path) -> None:
    source = _source("2.39").replace(
        "(defrecord Review (approved Bool))",
        "(defrecord Empty) (defrecord Review (empty Empty))",
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", source)
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_phased_delivery_policy_invalid"
    assert diagnostic.phased_delivery_diagnostic.reason == "contract_suffix_required"


def test_target_239_phased_provider_allows_discriminant_only_union_contract(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule phased239) (export run)
      (defunion Review (approved) (rejected))
      (defprompt review (:fills (subject :text)) -> Review "Review {subject}")
      (defworkflow run ((subject String)) -> Review
        (provider-result providers.review :prompt (review :subject subject)
          :delivery :phased :timeout-sec 60)))'''
    program = _compile(tmp_path / "phased239.orc", source)
    contract = _provider_effect(program)["contract"]
    assert contract["kind"] == "variant_output"
    assert contract["payload"]["discriminant"]["allowed"] == ["approved", "rejected"]
    assert all(not row["fields"] for row in contract["payload"]["variants"].values())


def test_target_239_composed_provider_keeps_the_ordinary_closed_shape(tmp_path: Path) -> None:
    program = _compile(
        tmp_path / "phased239.orc", _source("2.39", ":delivery :composed")
    )
    effect = _provider_effect(program)

    assert effect["class"] == "provider"
    assert effect["policy"]["delivery"]["v"] == "composed"
    assert "materialization_attempts" not in effect["policy"]
    phased = _compile(tmp_path / "other" / "phased239.orc", _source("2.39"))
    assert phased.digest != program.digest


def test_target_239_default_composed_provider_omits_new_policy_fields(tmp_path: Path) -> None:
    program = _compile(
        tmp_path / "phased239.orc",
        _source("2.39", ""),
    )
    effect = _provider_effect(program)
    assert effect["class"] == "provider"
    assert "delivery" not in effect["policy"]
    assert "materialization_attempts" not in effect["policy"]


@pytest.mark.parametrize("attempts", [1, 3])
def test_target_239_phased_provider_keeps_explicit_literal_attempts(tmp_path: Path, attempts: int) -> None:
    program = _compile(
        tmp_path / "phased239.orc",
        _source(
            "2.39",
            f":delivery :phased :timeout-sec 60 :materialization-attempts {attempts}",
        ),
    )
    assert _provider_effect(program)["policy"]["materialization_attempts"]["v"] == attempts


def test_target_239_phased_provider_requires_explicit_timeout(tmp_path: Path) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", _source("2.39", ":delivery :phased"))
    assert excinfo.value.diagnostics[0].code == "provider_phased_timeout_required"


def test_imported_target_239_phased_provider_requires_its_own_timeout(tmp_path: Path) -> None:
    helper = _source("2.39", ":delivery :phased").replace("phased239", "helper").replace(
        "(export run)", "(export Review run)"
    )
    main = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule main) (import helper :as helper :only (Review run)) (export run)
      (defworkflow run ((subject String)) -> helper.Review
        (call helper.run :subject subject)))'''
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_modules(tmp_path, {"main.orc": main, "helper.orc": helper}, "main::run")
    assert excinfo.value.diagnostics[0].code == "provider_phased_timeout_required"


@pytest.mark.parametrize(
    ("timeout", "code"),
    [
        ("subject", "provider_result_timeout_literal_required"),
        ("true", "provider_result_timeout_type_invalid"),
        ("0", "provider_result_timeout_nonpositive"),
        ("-1", "provider_result_timeout_nonpositive"),
    ],
)
def test_target_239_phased_provider_preserves_timeout_value_validation(
    tmp_path: Path, timeout: str, code: str
) -> None:
    source = _source("2.39", f":delivery :phased :timeout-sec {timeout}")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", source)
    assert excinfo.value.diagnostics[0].code == code


@pytest.mark.parametrize("target", ["2.35", "2.36", "2.37", "2.38"])
def test_phased_provider_is_refused_before_239_definition_target(tmp_path: Path, target: str) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", _source(target))
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_phased_delivery_policy_invalid"
    assert diagnostic.phased_delivery_diagnostic.reason == "target_below_2_39"
    assert diagnostic.phased_delivery_diagnostic.rejected_value.canonical_value == target


def test_target_239_phased_delivery_rejects_agent_valued_provider(tmp_path: Path) -> None:
    source = _source("2.39").replace(
        '(provider-result providers.review :prompt (review :subject subject)\n'
        '          :model "bound-model" :effort "bound-effort" :delivery :phased :timeout-sec 60)',
        '(let* ((reviewer (agent providers.review)))\n'
        '          (provider-result reviewer :prompt (review :subject subject)\n'
        '            :delivery :phased :timeout-sec 60))',
    )
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", source)
    assert excinfo.value.diagnostics[0].code == "agent_turn_option_unsupported"


def test_target_239_phased_delivery_rejects_extern_prompt(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule phased239) (export run)
      (defrecord Review (approved Bool))
      (defworkflow run ((subject String)) -> Review
        (provider-result providers.review :prompt prompts.review
          :returns Review :delivery :phased :timeout-sec 60)))'''
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(
            tmp_path / "phased239.orc",
            source,
            prompt_externs={"prompts.review": "review.md"},
        )
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_phased_delivery_policy_invalid"
    assert diagnostic.phased_delivery_diagnostic.reason == "fragment_application_required"


@pytest.mark.parametrize(
    ("option", "code"),
    [
        (":capture-context :portable", "provider_context_phased_delivery_invalid"),
        (":session-artifact saved", "session_artifact_phased_delivery_invalid"),
    ],
)
def test_target_239_phased_delivery_rejects_context_and_session_pairings(
    tmp_path: Path, option: str, code: str
) -> None:
    source = _source("2.39", f":delivery :phased :timeout-sec 60 {option}")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", source)
    assert excinfo.value.diagnostics[0].code == code


def test_imported_phased_definition_uses_its_older_owner_target(tmp_path: Path) -> None:
    older = _source("2.38").replace("phased239", "older").replace("run", "review")
    main = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule main) (import older :as older :only (Review review)) (export run)
      (defworkflow run ((subject String)) -> older.Review
        (call older.review :subject subject)))'''
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_modules(tmp_path, {"main.orc": main, "older.orc": older}, "main::run")
    assert excinfo.value.diagnostics[0].phased_delivery_diagnostic.reason == "target_below_2_39"


def test_source_free_typed_import_keeps_older_phased_definition_owner_target(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.expressions import LiteralExpr

    older_path = tmp_path / "older.orc"
    older_path.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
          (defmodule older) (export run)
          (defprompt review (:fills (subject :text)) -> String "Review {subject}")
          (defworkflow run () -> String
            (provider-result providers.review :prompt (review :subject "x")
              :delivery :composed)))''',
        encoding="utf-8",
    )
    older = compile_typed_program(
        older_path,
        entry_workflow="older::run",
        source_roots=(tmp_path,),
        command_boundaries={},
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        workspace_root=tmp_path,
    )
    older_path.unlink()

    caller_path = tmp_path / "caller.orc"
    caller_path.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
          (defmodule caller) (export run)
          (defworkflow run () -> String (call older)))''',
        encoding="utf-8",
    )
    caller = compile_typed_program(
        caller_path,
        entry_workflow="caller::run",
        source_roots=(tmp_path,),
        command_boundaries={},
        provider_externs={},
        prompt_externs={},
        workspace_root=tmp_path,
        imported_programs={"older": older},
    )

    workflow = older.workflows["older::run"]
    effect = workflow.typed_body.expr
    assert effect.delivery.value == "composed"
    phased_effect = replace(
        effect,
        delivery=replace(effect.delivery, value="phased"),
        materialization_attempts=LiteralExpr(
            2,
            "int",
            effect.delivery.span,
            effect.delivery.form_path,
            effect.delivery.expansion_stack,
        ),
    )
    phased_workflow = replace(
        workflow,
        typed_body=replace(workflow.typed_body, expr=phased_effect),
    )
    older_workflows = dict(older.workflows)
    older_workflows["older::run"] = phased_workflow
    older_capsule = replace(older, workflows=older_workflows, entry=phased_workflow)
    caller_imports = dict(caller.imported_programs)
    caller_imports["older"] = older_capsule
    caller_workflows = dict(caller.workflows)
    caller_workflows["older::run"] = phased_workflow
    caller_capsule = replace(
        caller,
        imported_programs=caller_imports,
        workflows=caller_workflows,
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        build_closed_program(caller_capsule)
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "closed_program_gap"
    assert "defining source to target DSL 2.39" in diagnostic.message


def test_closed_checker_rejects_phased_provider_reached_by_parallel_worker(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule phased239) (export run)
      (defrecord Review (approved Bool))
      (defprompt review (:fills (subject :text)) -> Review "Review {subject}")
      (defworkflow worker ((subject String)) -> Review
        (provider-result providers.review :prompt (review :subject subject)
          :delivery :phased :timeout-sec 60))
      (defworkflow run ((subjects List[String])) -> List[Review]
        (list/map-effect ((subject subjects)) :max 4 :parallel 2 :workspace "."
          (call worker :subject subject))))'''
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", source)
    assert excinfo.value.diagnostics[0].code == "parallel_provider_boundary"


def test_parallel_worker_refusal_follows_imported_helper_calls(tmp_path: Path) -> None:
    helper = _source("2.39").replace("phased239", "helper").replace(
        "(export run)", "(export Review run)"
    )
    main = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule main) (import helper :as helper :only (Review run)) (export run)
      (defworkflow run ((subjects List[String])) -> List[helper.Review]
        (list/map-effect ((subject subjects)) :max 4 :parallel 2 :workspace "."
          (call helper.run :subject subject))))'''
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_modules(tmp_path, {"main.orc": main, "helper.orc": helper}, "main::run")
    assert excinfo.value.diagnostics[0].code == "parallel_provider_boundary"


def test_parallel_worker_refusal_follows_specialized_procedure_calls(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule phased239) (export run)
      (defrecord Review (approved Bool))
      (defprompt review (:fills (subject :text)) -> Review "Review {subject}")
      (defproc worker :forall (T) ((subject String) (tag T)) -> Review
        :effects ((uses-provider providers.review))
        (provider-result providers.review :prompt (review :subject subject)
          :delivery :phased :timeout-sec 60))
      (defworkflow run ((subjects List[String])) -> List[Review]
        (list/map-effect ((subject subjects)) :max 4 :parallel 2 :workspace "."
          (worker subject false))))'''
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", source)
    assert excinfo.value.diagnostics[0].code == "parallel_provider_boundary"


def test_source_free_checker_rejects_direct_phased_provider_map_forgery(tmp_path: Path) -> None:
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule phased239) (export run)
      (defrecord Review (approved Bool))
      (defprompt review (:fills (subject :text)) -> Review "Review {subject}")
      (defworkflow worker ((subject String)) -> Review
        (record Review :approved true))
      (defworkflow run ((base String) (subjects List[String])) -> List[Review]
        (let* ((sequential (provider-result providers.review
                  :prompt (review :subject base) :delivery :phased :timeout-sec 60)))
          (list/map-effect ((subject subjects)) :max 4 :parallel 2 :workspace "."
            (call worker :subject subject)))))'''
    tree = deepcopy(_compile(tmp_path / "phased239.orc", source).tree)
    effect = next(
        node for node in _ast_nodes(tree["body"])
        if node.get("k") == "perform" and node.get("class") == "provider_phased"
    )
    parallel = next(
        node for node in _ast_nodes(tree["body"]) if node.get("k") == "par-map"
    )
    parallel["body"] = {
        "k": "let",
        "name": "phased-result",
        "value": deepcopy(effect),
        "body": {"k": "halt", "value": {"k": "name", "n": "phased-result"}},
    }
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    with pytest.raises(CheckedFormError) as excinfo:
        validate(tree)
    assert excinfo.value.rule == "parallel_provider_boundary"


def test_runtime_phased_without_interactive_capability_has_no_ordinary_fallback(tmp_path: Path) -> None:
    from tests.test_workflow_evaluated_providers import _cli, _fixture, _requests

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule main) (export run)
      (defrecord Result (ok Bool))
      (defprompt review (:fills (message :text)) -> Result "{message}")
      (defworkflow run ((message String)) -> Result
        (provider-result providers.review :prompt (review :message message)
          :delivery :phased :timeout-sec 60)))'''
    fixture = _fixture(tmp_path, source)
    fixture[1].write_text('{"providers.review":"codex_gpt55"}')
    result = _cli(tmp_path, fixture)

    assert result.returncode == 1
    assert not _requests(tmp_path)
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    memo = run_root / "memo.jsonl"
    import json
    rows = [json.loads(line) for line in memo.read_bytes().splitlines()]
    assert any(row["record"] == "started" for row in rows)
    assert not any(row["record"] == "committed" for row in rows)
    assert any(row.get("code") == "provider_phased_preparation_failed" for row in rows)


def test_confined_run_ref_provider_walker_recognizes_phased_class(tmp_path: Path) -> None:
    from types import SimpleNamespace

    from orchestrator.workflow_lisp.closed.artifact import (
        ConfinedRunRefUnavailable,
        refuse_confined_run_ref_sites,
    )

    effect = _provider_effect(_compile(tmp_path / "phased239.orc", _source("2.39")))
    program = SimpleNamespace(tree={"children": {
        "child": {"entry": "workflow:child::run", "body": effect},
    }})
    with pytest.raises(ConfinedRunRefUnavailable) as excinfo:
        refuse_confined_run_ref_sites(program)
    assert excinfo.value.code == "run_ref_provider_transport_unavailable"


@pytest.mark.parametrize(
    ("sections", "reason"),
    [
        (":delivery :phased :timeout-sec 60 :materialization-attempts true", "attempts_type_invalid"),
        (":delivery :phased :timeout-sec 60 :materialization-attempts 0", "attempts_out_of_range"),
        (":delivery :phased :timeout-sec 60 :materialization-attempts 4", "attempts_out_of_range"),
        (":delivery :phased :timeout-sec 60 :materialization-attempts subject", "attempts_literal_required"),
        (":delivery :composed :materialization-attempts 2", "attempts_pairing_invalid"),
        (":materialization-attempts 2", "attempts_pairing_invalid"),
    ],
)
def test_target_239_policy_admission_rejects_forged_attempt_shapes(
    tmp_path: Path, sections: str, reason: str
) -> None:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile(tmp_path / "phased239.orc", _source("2.39", sections))
    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "provider_phased_delivery_policy_invalid"
    assert diagnostic.phased_delivery_diagnostic.reason == reason


@pytest.mark.parametrize(
    ("mutation", "rule"),
    [
        ("repeat", "effect_repeat"),
        ("bad_contract", "effect_contract"),
        ("missing_contract_payload", "effect_contract"),
        ("empty_contract_payload", "effect_result"),
        ("empty_record_contract", "effect_contract"),
        ("missing_timeout", "effect_shape"),
        ("prompt_source", "effect_shape"),
        ("extra_prompt_field", "effect_shape"),
        ("missing_delivery", "effect_shape"),
        ("wrong_delivery", "effect_shape"),
        ("missing_attempts", "effect_shape"),
        ("attempts_bool", "effect_shape"),
        ("attempts_low", "effect_shape"),
        ("attempts_high", "effect_shape"),
        ("attempts_dynamic", "effect_shape"),
        ("ordinary_with_phased_fields", "effect_shape"),
        ("wrong_target", "effect_class"),
        ("extra_field", "node_shape"),
    ],
)
def test_source_free_checker_rejects_phased_class_and_policy_forgery(
    tmp_path: Path, mutation: str, rule: str
) -> None:
    tree = deepcopy(_compile(tmp_path / "phased239.orc", _source("2.39")).tree)
    effect = next(
        node for node in _ast_nodes(tree["body"])
        if node.get("k") == "perform" and node.get("class") == "provider_phased"
    )
    policy = effect["policy"]
    if mutation == "repeat":
        effect["repeat"] = "never"
    elif mutation == "bad_contract":
        effect["contract"] = None
    elif mutation == "missing_contract_payload":
        del effect["contract"]["payload"]
    elif mutation == "empty_contract_payload":
        effect["contract"]["payload"] = {}
    elif mutation == "empty_record_contract":
        empty = deepcopy(effect["result"])
        empty["fields"] = []
        tree["result"] = deepcopy(empty)
        tree["types"][empty["name"]] = deepcopy(empty)
        effect["result"] = deepcopy(empty)
        effect["contract"] = {
            "kind": "output_bundle",
            "payload": {"fields": []},
        }
    elif mutation == "prompt_source":
        effect["prompt"] = {"source_kind": "input_file", "path": "prompt.md"}
    elif mutation == "extra_prompt_field":
        effect["prompt"]["unexpected"] = "x"
    elif mutation == "missing_delivery":
        del policy["delivery"]
    elif mutation == "wrong_delivery":
        policy["delivery"]["v"] = "composed"
    elif mutation == "missing_attempts":
        del policy["materialization_attempts"]
    elif mutation == "missing_timeout":
        del policy["timeout_sec"]
    elif mutation == "attempts_bool":
        policy["materialization_attempts"]["v"] = True
    elif mutation == "attempts_low":
        policy["materialization_attempts"]["v"] = 0
    elif mutation == "attempts_high":
        policy["materialization_attempts"]["v"] = 4
    elif mutation == "attempts_dynamic":
        policy["materialization_attempts"] = {
                "k": "name", "n": "attempts"
        }
    elif mutation == "ordinary_with_phased_fields":
        effect["class"] = "provider"
    elif mutation == "wrong_target":
        tree["target"] = "2.38"
    elif mutation == "extra_field":
        effect["unused"] = None
    tree["sites"] = [list(row) for row in assign_sites(tree)]

    with pytest.raises(CheckedFormError) as excinfo:
        validate(tree)
    assert excinfo.value.rule == rule
