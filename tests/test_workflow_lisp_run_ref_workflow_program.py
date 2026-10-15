"""F1 feasibility: a non-exported named workflow builds as a private child entry.

The child-entry seam is the ordinary closed-program builder applied to a typed
program whose entry is the named workflow (no `:program (:workflow ...)`
surface syntax yet; that arrives with the syntax task).
"""

from __future__ import annotations

import json
import sys

from copy import deepcopy
from dataclasses import replace
from importlib import import_module
from pathlib import Path

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import evaluate_closed_program, site_classes
from orchestrator.workflow.evaluated.values import EvaluatedValueError
from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import RunsRefEffect, UsesCommandEffect, UsesProviderEffect
from orchestrator.workflow_lisp.workflows import PromptExtern
from tests.test_workflow_lisp_trial import _trial_source
from tests.workflow_lisp_closed_program_helpers import BOUNDARIES, PROMPTS, install

HELPER = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule helper) (export bump fetch Box)
  (defrecord Box (n Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch)) :lowering inline
    (command-result fetch :argv ("python" "probe.py" "fetch" n) :returns Box))
  (defun bump ((n Int)) -> Int (+ n 1)))'''

PARENT = '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
  (defmodule controller) (import helper :only (bump fetch Box)) (export run)
  (defrecord Verdict (ok Bool))
  (defworkflow candidate-body ((seed Int) (task String)) -> Int
    (let* ((verdict (provider-result providers.review :prompt prompts.base
                      :inputs (task) :returns Verdict)))
      (if verdict.ok
        (loop/recur :max 5
          :state (loop-state (i Int seed))
          :on-exhausted -1
          (fn (state)
            (let* ((box (fetch (bump state.i))))
              (if (>= box.n 3) (done box.n)
                (continue (loop-state :like state :i box.n))))))
        0)))
  (defworkflow run ((seed Int)) -> Int PARENT_BODY))'''

CHILD = "controller::candidate-body"


def _typed(root: Path, parent_body: str = "(+ seed 1)"):
    install(root, {"helper.orc": HELPER,
                   "controller.orc": PARENT.replace("PARENT_BODY", parent_body)})
    return compile_typed_program(
        root / "controller.orc", entry_workflow="controller::run", source_roots=(root,),
        command_boundaries=BOUNDARIES, provider_externs={"providers.review": "probe-provider"},
        prompt_externs={"prompts.base": PROMPTS["prompt"]}, workspace_root=root)


def _child_entry(typed, name: str = CHILD) -> ClosedProgram:
    child = replace(typed, entry=typed.workflows[name])
    return build_closed_program(child, builder=Builder(child))


def _perform(effects):
    values = import_module("orchestrator.workflow.evaluated.values")

    def perform(node, operands, identity, _owner, _reader):
        arguments = tuple(operand.value for operand in operands)
        kind = _site_kind(node)
        effects.append((kind, arguments[-1]))
        value = {"ok": True} if kind == "provider" else {"n": arguments[-1]}
        return values.coerce_evaluated_value(value, node["result"], dependencies={identity})

    return perform


def _site_kind(node) -> str:
    return "command" if "boundary" in node else "provider"


def test_private_child_entry_evaluates_declared_inputs_with_imported_helper(tmp_path):
    program = ClosedProgram.from_artifact(_child_entry(_typed(tmp_path)).artifact())
    effects: list[tuple[str, object]] = []

    result = evaluate_closed_program(program, {"seed": 0, "task": "t"},
                                     effect_handler=_perform(effects))

    assert (result.value, effects) == (
        3, [("provider", "t"), ("command", 1), ("command", 2), ("command", 3)])


def test_private_child_entry_has_own_signature_sites_and_summary(tmp_path):
    typed = _typed(tmp_path)
    program = _child_entry(typed)

    assert (
        program.tree["entry"],
        [name for name, _ in program.tree["params"]],
        sorted(site_classes(program).values()),
        typed.workflows[CHILD].effect_summary.transitive_effects,
    ) == (
        f"workflow:{CHILD}",
        ["seed", "task"],
        ["command", "provider"],
        frozenset({UsesCommandEffect(subject=("fetch",)),
                   UsesProviderEffect(subject=("providers", "review"))}),
    )


def test_private_child_entry_keeps_canonical_owners_and_owner_bindings(tmp_path):
    program = _child_entry(_typed(tmp_path))
    owners = {definition["key"][0] for definition in program.tree["definitions"].values()}
    configuration = program.tree["configuration"]

    assert (owners, configuration["providers"], configuration["commands"]["fetch"]["stable_command"]) == (
        {"helper"}, {"providers.review": {"provider_id": "probe-provider"}}, ["python", "probe.py"])


def test_private_child_cannot_resolve_parent_runtime_binding(tmp_path):
    install(tmp_path, {"helper.orc": HELPER, "controller.orc": PARENT.replace(
        "(>= box.n 3)", "(>= box.n limit)").replace(
        "PARENT_BODY", "(let* ((limit 3)) (+ seed limit))")})

    with pytest.raises(LispFrontendCompileError) as refused:
        compile_typed_program(
            tmp_path / "controller.orc", entry_workflow="controller::run",
            source_roots=(tmp_path,), command_boundaries=BOUNDARIES,
            provider_externs={"providers.review": "probe-provider"},
            prompt_externs={"prompts.base": PROMPTS["prompt"]}, workspace_root=tmp_path)

    assert [row.code for row in refused.value.diagnostics] == ["name_unknown"]


def test_private_child_entry_refuses_parent_inputs_at_evaluation(tmp_path):
    program = _child_entry(_typed(tmp_path))

    with pytest.raises(EvaluatedValueError) as refused:
        evaluate_closed_program(program, {"seed": 0, "task": "t", "limit": 3},
                                effect_handler=_perform([]))

    assert refused.value.code == "closed_input_names"


def test_private_child_entry_identity_survives_snapshot_and_rebuild(tmp_path):
    first = _child_entry(_typed(tmp_path / "a"))
    snapshot = ClosedProgram.from_artifact(first.artifact())
    rebuilt = _child_entry(_typed(tmp_path / "b", parent_body="(+ seed 2)"))

    assert {snapshot.digest, rebuilt.digest} == {first.digest}


# Task 3: `run-ref :program (:workflow <name>)` syntax and typing at target 2.38.

DIGEST = "0123456789abcdef" * 4
POLICY = (f'(:environment :confined :image "registry.example/project@sha256:{DIGEST}" '
          ':network :model-only :limits (:wall-seconds 900 :memory-mib 4096 :cpus 2 '
          ':pids 256 :workspace-mib 2048 :output-mib 64))')
RUN_REF = ('(run-ref :source (:repo "file:///srv/project.git" :commit revision) '
           ':program (:workflow candidate-body) :inputs (:seed seed :task "t") '
           f':policy {POLICY})')
PATH_RUN_REF = ('(run-ref :source (:repo "file:///srv/x.git" :commit "' + "a" * 40 + '") '
                ':program (:path "c.orc" :entry run) :inputs (:payload "p") :returns String '
                ':policy (:environment :deterministic-effect-free :setup ()))')
CONFINED = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule controller) (import helper :only (bump fetch Box nested peek)) (export run)
  (defrecord Verdict (ok Bool))
  (defpath Loose :kind relpath :under "artifacts" :must-exist false)
  (defrecord LooseOut (file Loose))
  (defpath Bundle :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defworkflow candidate-body ((seed Int) (task String)) -> Int
    (let* ((verdict (provider-result providers.review :prompt prompts.base
                      :inputs (task) :returns Verdict)))
      (if verdict.ok (let* ((n (bump seed)) (box (fetch n))) box.n) 0)))
  (defworkflow leaf ((value String)) -> String value)
  EXTRA
  (defworkflow run ((seed Int) (revision String)) -> Int
    (let* ((child RUN_REF))
      (match child
        ((COMPLETED c) c.result.value)
        ((FAILED f) f.accounting.attempt_ordinal)))))'''
NESTED_HELPER = HELPER.replace("(export bump fetch Box)", "(export bump fetch Box nested peek)").replace(
    "(defun bump", f'''(defproc nested ((n Int)) -> Int :effects ((runs-ref run)) :lowering inline
    (let* ((c {PATH_RUN_REF})) n))
  (defrecord Seen (ok Bool))
  (defpath Located :kind relpath :under ".orchestrate/runs" :must-exist false)
  (defproc peek ((n Int)) -> Int :effects ((uses-provider providers.review)) :lowering inline
    (let* ((v (provider-result providers.review :prompt prompts.base :inputs (n) :returns Seen))
           (b (provider-bundle-path v :as Located))) n))
  (defun bump''')


TRIAL_RUBRIC = PromptExtern(name="trial-rubric", asset_file="rubrics/trial.md")


def _confined(root: Path, *edits: tuple[str, str], extra: str = ""):
    source = CONFINED.replace("EXTRA", extra).replace("RUN_REF", RUN_REF)
    for old, new in edits:
        assert old in source, old
        source = source.replace(old, new)
    install(root, {"helper.orc": NESTED_HELPER, "controller.orc": source})
    return compile_typed_program(
        root / "controller.orc", entry_workflow="controller::run", source_roots=(root,),
        command_boundaries=BOUNDARIES, provider_externs={"providers.review": "probe-provider", "scorer": "probe-provider"},
        prompt_externs={"prompts.base": PROMPTS["prompt"], "trial-rubric": TRIAL_RUBRIC}, workspace_root=root)


def _refusal(root: Path, *edits: tuple[str, str], extra: str = "") -> str:
    with pytest.raises(LispFrontendCompileError) as refused:
        _confined(root, *edits, extra=extra)
    return refused.value.diagnostics[0].code


def _site(typed):
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import RunRefExpr

    body = typed.workflows["controller::run"].typed_body.expr
    [site] = [node for node in walk_expr(body) if isinstance(node, RunRefExpr)]
    return site


def test_workflow_program_site_resolves_static_child_and_literal_policy(tmp_path):
    site = _site(_confined(tmp_path))

    assert (site.program.workflow_name, site.source.repo, site.program.policy.image,
            site.program.policy.network, dict(site.program.policy.limits),
            [name for name, _ in site.inputs]) == (
        "controller::candidate-body", "file:///srv/project.git",
        f"registry.example/project@sha256:{DIGEST}", "model-only",
        {"wall-seconds": 900, "memory-mib": 4096, "cpus": 2, "pids": 256,
         "workspace-mib": 2048, "output-mib": 64},
        ["seed", "task"])


def test_workflow_program_site_is_completed_failed_union(tmp_path):
    outcome = _site(_confined(tmp_path)).run_ref_metadata.outcome_type_ref
    completed = outcome.variant_field_types["COMPLETED"]
    failed = outcome.variant_field_types["FAILED"]

    assert (
        sorted(outcome.variant_field_types),
        list(completed),
        list(completed["result"].field_types),
        completed["result"].field_types["value"].name,
        {name: type_ref.name for name, type_ref in failed.items()},
    ) == (
        ["COMPLETED", "FAILED"],
        ["result"],
        ["value", "workspace_delta", "accounting"],
        "Int",
        {"code": "String", "detail": "String", "accounting": "RunRefAccounting"},
    )


def test_workflow_program_site_refuses_bare_value_access(tmp_path):
    assert _refusal(tmp_path, ("((COMPLETED c) c.result.value)", "((COMPLETED c) child.value)")) == (
        "record_field_unknown")


def test_workflow_program_site_match_must_handle_failed(tmp_path):
    assert _refusal(tmp_path, ("\n        ((FAILED f) f.accounting.attempt_ordinal)", "")) == (
        "union_match_non_exhaustive")


def test_workflow_program_commit_literal_is_admitted(tmp_path):
    site = _site(_confined(tmp_path, (":commit revision", ':commit "' + "b" * 40 + '"')))

    assert site.source.commit.value == "b" * 40


def test_workflow_program_child_without_provider_admits_network_none(tmp_path):
    typed = _confined(tmp_path, (":program (:workflow candidate-body) :inputs (:seed seed :task \"t\")",
                                 ":program (:workflow leaf) :inputs (:value \"v\")"),
                      (":network :model-only", ":network :none"),
                      ("((COMPLETED c) c.result.value)", "((COMPLETED c) 1)"))

    assert _site(typed).program.policy.network == "none"


SHAPE_REFUSALS = {
    "older-target": (('(:target-dsl "2.38")', '(:target-dsl "2.37")'),
                     "run_ref_child_target_unavailable"),
    "mixed-program": (("(:workflow candidate-body)", '(:workflow candidate-body :path "c.orc" :entry run)'),
                      "run_ref_program_mode_invalid"),
    "string-name": (("(:workflow candidate-body)", '(:workflow "candidate-body")'), "run_ref_literal_required"),
    "unknown-workflow": (("(:workflow candidate-body)", "(:workflow missing-body)"), "workflow_call_unknown"),
    "returns": ((":policy (:environment", ":returns Int :policy (:environment"), "run_ref_program_mode_invalid"),
    "setup": ((":environment :confined", ":setup () :environment :confined"), "run_ref_program_mode_invalid"),
    "path-environment": ((":environment :confined", ":environment :deterministic-effect-free"),
                         "run_ref_program_mode_invalid"),
    "unknown-policy-key": ((":network :model-only", ":network :model-only :gpu 1"), "run_ref_shape_invalid"),
    "missing-image": ((f':image "registry.example/project@sha256:{DIGEST}" ', ""), "run_ref_shape_invalid"),
    "tagged-image": (("project@sha256", "project:latest@sha256"), "run_ref_literal_required"),
    "undigested-image": ((f"@sha256:{DIGEST}", ""), "run_ref_literal_required"),
    "dynamic-image": ((f':image "registry.example/project@sha256:{DIGEST}"', ":image revision"),
                      "run_ref_literal_required"),
    "open-network": ((":network :model-only", ":network :internet"), "run_ref_literal_required"),
    "missing-limit": ((" :output-mib 64", ""), "run_ref_shape_invalid"),
    "unknown-limit": ((":output-mib 64", ":output-mib 64 :gpus 1"), "run_ref_shape_invalid"),
    "zero-limit": ((":cpus 2", ":cpus 0"), "run_ref_literal_required"),
    "dynamic-limit": ((":cpus 2", ":cpus seed"), "run_ref_literal_required"),
    "headroom": ((":memory-mib 4096", ":memory-mib 3007"), "run_ref_environment_effect_unsupported"),
    "dynamic-repo": (('(:repo "file:///srv/project.git"', "(:repo revision"), "run_ref_literal_required"),
    "bad-commit-literal": ((":commit revision", ':commit "abc"'), "run_ref_literal_required"),
    "int-commit": ((":commit revision", ":commit seed"), "type_mismatch"),
    "missing-input": ((':inputs (:seed seed :task "t")', ":inputs (:seed seed)"), "workflow_signature_mismatch"),
    "unknown-input": ((':task "t")', ':task "t" :extra 1)'), "workflow_signature_mismatch"),
    "input-type": ((':task "t")', ":task seed)"), "type_mismatch"),
}


@pytest.mark.parametrize("case", sorted(SHAPE_REFUSALS))
def test_workflow_program_refuses_invalid_site(tmp_path, case):
    edit, code = SHAPE_REFUSALS[case]

    assert _refusal(tmp_path, edit) == code


def test_workflow_program_headroom_boundary_is_admitted(tmp_path):
    site = _site(_confined(tmp_path, (":memory-mib 4096", ":memory-mib 3008")))

    assert dict(site.program.policy.limits)["memory-mib"] == 3008


def _child(name: str, body: str, *, params: str = "((seed Int))", result: str = "Int") -> str:
    return f"(defworkflow {name} {params} -> {result} {body})"


EFFECT_REFUSALS = {
    "nested-run-ref": (_child("bad", f"(let* ((c {PATH_RUN_REF})) seed)"),
                       "run_ref_environment_effect_unsupported"),
    "nested-run-ref-imported-helper": (_child("bad", "(nested seed)"),
                                       "run_ref_environment_effect_unsupported"),
    "human-input-through-call": (
        _child("asker", '(let* ((r (request-input "q"))) seed)') + _child("bad", "(call asker :seed seed)"),
        "run_ref_environment_effect_unsupported"),
    "parallel-map": (_child("bad", '(let* ((xs (list/map-effect ((repo (list "a"))) :max 1 :parallel 1 '
                                   ':workspace repo (call leaf :value repo)))) seed)'),
                     "run_ref_environment_effect_unsupported"),
    "provider-bundle-path-imported-helper": (_child("bad", "(peek seed)"), "run_ref_child_transport_unsupported"),
    "provider-bundle-path-through-procedure": (
        "(defproc look ((n Int)) -> Int :effects ((uses-provider providers.review)) :lowering inline "
        "(let* ((v (provider-result providers.review :prompt prompts.base :inputs (n) :returns Verdict)) "
        "(b (provider-bundle-path v :as Bundle))) n))" + _child("bad", "(look seed)"),
        "run_ref_child_transport_unsupported"),
    "session-context-capture": (
        _child("bad", "(let* ((c (provider-result providers.review :prompt prompts.base :inputs (seed) "
                      ":capture-context :portable :returns Verdict))) seed)"),
        "run_ref_environment_effect_unsupported"),
    "trial": ('(defworkflow first () -> String "a") (defworkflow second () -> String "b")'
              + _child("bad", f"(let* ((t {_trial_source()})) seed)"),
              "run_ref_environment_effect_unsupported"),
    "parallel-map-through-call": (
        _child("fan", '(let* ((xs (list/map-effect ((repo (list "a"))) :max 1 :parallel 1 '
                      ':workspace repo (call leaf :value repo)))) seed)') + _child("bad", "(call fan :seed seed)"),
        "run_ref_environment_effect_unsupported"),
    "must-exist-false-result": (_child("bad", '(command-result fetch :argv ("python" "probe.py") :returns LooseOut)',
                                       result="LooseOut"),
                                "run_ref_child_transport_unsupported"),
    # A bare `Provider` parameter is already refused at the workflow boundary;
    # a record field carrying one crosses it and must stop at the child site.
    "authority-input": ("(defrecord Holder (p Provider))"
                        + _child("bad", "seed", params="((seed Int) (role Holder))"),
                        "run_ref_child_transport_unsupported"),
}


@pytest.mark.parametrize("case", sorted(EFFECT_REFUSALS))
def test_workflow_program_refuses_unsupported_child(tmp_path, case):
    extra, code = EFFECT_REFUSALS[case]
    inputs = ":inputs (:seed seed :role (record Holder :p providers.review))" if case == "authority-input" else ":inputs (:seed seed)"

    assert _refusal(tmp_path, ('(:workflow candidate-body) :inputs (:seed seed :task "t")',
                               f"(:workflow bad) {inputs}"),
                    ("((COMPLETED c) c.result.value)", "((COMPLETED c) 1)"), extra=extra) == code


def test_workflow_program_network_none_refuses_provider_child(tmp_path):
    assert _refusal(tmp_path, (":network :model-only", ":network :none")) == (
        "run_ref_environment_effect_unsupported")


def test_workflow_program_child_effects_stay_out_of_parent_summary(tmp_path):
    typed = _confined(tmp_path)

    assert typed.workflows["controller::run"].effect_summary.transitive_effects == frozenset(
        {RunsRefEffect(subject=(CHILD,))})


def test_path_mode_run_ref_is_unchanged_at_target_238(tmp_path):
    source = CONFINED.replace("EXTRA", "").replace("RUN_REF", PATH_RUN_REF).replace(
        "(match child\n        ((COMPLETED c) c.result.value)\n        ((FAILED f) f.accounting.attempt_ordinal))",
        "(if (= child.value \"p\") 1 0)")
    install(tmp_path, {"helper.orc": NESTED_HELPER, "controller.orc": source})
    typed = compile_typed_program(
        tmp_path / "controller.orc", entry_workflow="controller::run", source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES, provider_externs={"providers.review": "probe-provider"},
        prompt_externs={"prompts.base": PROMPTS["prompt"]}, workspace_root=tmp_path)

    from base64 import b64decode
    from orchestrator.workflow.evaluated.machine import site_nodes
    from orchestrator.workflow.run_ref.config import decode_run_ref_static_config

    [node] = [node for node in site_nodes(build_closed_program(typed, builder=Builder(typed))).values()
              if node["class"] == "run_ref"]
    config = decode_run_ref_static_config(b64decode(node["config"]))

    assert (_site(typed).run_ref_metadata.outcome_type_ref, config.program.record["mode"],
            config.target_dsl_version) == (None, "path", "2.35")


def _wcc_body(typed):
    from orchestrator.workflow_lisp.wcc import elaborate_typed_workflow_body

    run = typed.workflows["controller::run"]
    return elaborate_typed_workflow_body(
        run.typed_body, owner_name="controller::run", type_env=typed.workflow_type_envs["controller::run"],
        value_env=dict(run.signature.params), route_schema_version="wcc_m4")


def _wcc_perform(typed):
    from orchestrator.workflow_lisp.wcc import WccLet, WccPerform

    body = _wcc_body(typed)
    pending, performs = [body], []
    while pending:
        node = pending.pop()
        if isinstance(node, WccLet):
            pending.extend((node.bound_value, node.body))
        if isinstance(node, WccPerform) and node.perform_kind == "run_ref":
            performs.append(node)
    [perform] = performs
    return perform


def test_workflow_program_wcc_payload_carries_child_policy_inputs_and_commit(tmp_path):
    from orchestrator.workflow_lisp.wcc import WccNameAtom

    perform = _wcc_perform(_confined(tmp_path))
    payload = perform.operation_payload

    assert (
        perform.target_name,
        payload.workflow_name,
        payload.repo,
        payload.policy.network,
        [name for name, _ in payload.input_type_descriptors],
        [name for name, _ in perform.keyword_args],
        [type(value).__name__ for value in perform.positional_args],
        perform.positional_args[0].name if isinstance(perform.positional_args[0], WccNameAtom) else None,
        payload.result_descriptor["envelope"]["fields"][0]["type"],
        perform.returns_type_name,
    ) == (
        CHILD,
        CHILD,
        "file:///srv/project.git",
        "model-only",
        ["seed", "task"],
        ["seed", "task"],
        ["WccNameAtom"],
        "revision",
        {"kind": "primitive", "name": "Int"},
        payload.generated_outcome_type,
    )


def test_trial_arm_cannot_run_a_confined_workflow_child():
    from orchestrator.workflow_lisp.expressions import parse_trial_expression
    from tests.test_workflow_lisp_trial import _expression, _trial_source

    arm = RUN_REF.replace(":commit revision", ':commit "' + "c" * 40 + '"')
    with pytest.raises(LispFrontendCompileError) as refused:
        parse_trial_expression(_expression(_trial_source(arm_a=arm)), target_dsl_version="2.38")

    assert refused.value.diagnostics[0].code == "run_ref_child_target_unavailable"


def test_resource_form_in_child_is_an_unsupported_environment_effect():
    from orchestrator.workflow_lisp.expressions import elaborate_expression
    from orchestrator.workflow_lisp.typecheck_run_ref import _child_form_refusal
    from tests.test_workflow_lisp_resource_stdlib import _expression_syntax

    form = elaborate_expression(_expression_syntax(
        "(resource-transition :transition write-drain-status :resource drain-run-state "
        ':request (record DrainStatusRequest :status "BLOCKED"))'), bound_names=frozenset())

    assert _child_form_refusal(form, network_none=False)[0] == "run_ref_environment_effect_unsupported"


def test_in_memory_frontend_build_reports_child_refusal(tmp_path):
    """The LSP and `_compile_entry` path compiles without the typed-program selector."""
    from orchestrator.workflow_lisp.build import FrontendBuildRequest, build_frontend_bundle_in_memory

    source = CONFINED.replace("EXTRA", _child("bad", '(let* ((r (request-input "q"))) seed)')).replace(
        "RUN_REF", RUN_REF).replace('(:workflow candidate-body) :inputs (:seed seed :task "t")',
                                    "(:workflow bad) :inputs (:seed seed)")
    install(tmp_path, {"helper.orc": NESTED_HELPER, "controller.orc": source})
    boundaries = tmp_path / "boundaries.json"
    boundaries.write_text(json.dumps({"fetch": {"kind": "external_tool", "stable_command": ["python", "probe.py"],
                                                "closure": ["probe.py"]}}))
    (tmp_path / "providers.json").write_text(json.dumps({"providers.review": "probe-provider"}))
    (tmp_path / "prompts.json").write_text(json.dumps({"prompts.base": "inputs/prompt.md"}))

    with pytest.raises(LispFrontendCompileError) as refused:
        build_frontend_bundle_in_memory(FrontendBuildRequest(
            source_path=tmp_path / "controller.orc", source_roots=(tmp_path,), entry_workflow="controller::run",
            provider_externs_path=tmp_path / "providers.json", prompt_externs_path=tmp_path / "prompts.json",
            command_boundaries_path=boundaries, workspace_root=tmp_path))

    assert [row.code for row in refused.value.diagnostics] == ["run_ref_environment_effect_unsupported"]


def test_workflow_payload_refuses_a_malformed_policy(tmp_path):
    from dataclasses import fields as dataclass_fields
    from orchestrator.workflow_lisp.wcc import WccRunRefWorkflowPayload

    payload = _wcc_perform(_confined(tmp_path)).operation_payload
    arguments = {field.name: getattr(payload, field.name) for field in dataclass_fields(payload)
                 if not field.name.startswith("_")}
    arguments.update(result_descriptor=payload.result_descriptor,
                     input_type_descriptors=tuple(payload.input_type_descriptors),
                     policy=replace(payload.policy, network="internet"))

    with pytest.raises(ValueError):
        WccRunRefWorkflowPayload(**arguments)


def test_retained_outcome_must_match_its_site(tmp_path):
    from orchestrator.workflow_lisp.typecheck_context import TypecheckSessionStateCollisionError
    from orchestrator.workflow_lisp.typecheck_run_ref import resolve_unique_run_ref_site_metadata

    typed = _confined(tmp_path)
    site = _site(typed)
    metadata = site.run_ref_metadata
    forged = replace(metadata, outcome_type_ref=replace(metadata.outcome_type_ref, name="RunRefOutcome$" + "0" * 16))
    session = typed.workflow_type_envs["controller::run"].session_state

    assert resolve_unique_run_ref_site_metadata(site, session_state=session, prefer_retained=True) is metadata
    with pytest.raises(TypecheckSessionStateCollisionError):
        resolve_unique_run_ref_site_metadata(replace(site, run_ref_metadata=forged), session_state=session,
                                             prefer_retained=True)


# Task 4: the confined site compiles into a checked private child entry carried
# by `run_ref_static_config.v2`.

def _built(typed) -> ClosedProgram:
    return ClosedProgram.from_artifact(build_closed_program(typed, builder=Builder(typed)).artifact())


def _confined_site(program):
    from base64 import b64decode
    from orchestrator.workflow.evaluated.machine import site_nodes
    from orchestrator.workflow.run_ref.confined_config import decode_run_ref_confined_static_config

    [node] = [node for node in site_nodes(program).values() if node["class"] == "run_ref"]
    return node, decode_run_ref_confined_static_config(b64decode(node["config"]))


def _child_program(program) -> ClosedProgram:
    [child] = program.tree["children"].values()
    return ClosedProgram.from_artifact(json.dumps(child))


def test_confined_site_carries_a_checked_child_entry(tmp_path):
    program = _built(_confined(tmp_path))
    _node, config = _confined_site(program)
    child = _child_program(program)

    assert (list(program.tree["children"]), child.tree["entry"], [name for name, _ in child.tree["params"]],
            sorted(site_classes(child).values())) == (
        [config.program.child_program_digest], f"workflow:{CHILD}", ["seed", "task"], ["command", "provider"])


def test_child_entry_is_the_ordinary_compile_of_the_named_workflow(tmp_path):
    typed = _confined(tmp_path)

    assert _child_program(_built(typed)).digest == _child_entry(typed).digest


def test_parent_keeps_one_run_ref_site_and_child_sites_are_its_own(tmp_path):
    program = _built(_confined(tmp_path))

    child_owners = {owner for owner, _site in _child_program(program).sites}

    assert (program.sites, f"workflow:{CHILD}" in child_owners, "workflow:controller::run" in child_owners) == (
        (("workflow:controller::run", "child"),), True, False)


def test_confined_config_binds_child_owner_configuration_policy_and_inputs(tmp_path):
    from orchestrator.contracts.closed_program.program import canonical_digest

    program = _built(_confined(tmp_path))
    _node, config = _confined_site(program)
    child = _child_program(program)

    assert (config.target_dsl_version, config.repo, config.program.workflow_name,
            config.program.owner_configuration_digest, config.policy.image, config.policy.network,
            dict(config.policy.limits)["memory-mib"], [row.name for row in config.inputs],
            child.tree["configuration"]["providers"]) == (
        "2.38", "file:///srv/project.git", CHILD, canonical_digest(child.tree["configuration"]),
        f"registry.example/project@sha256:{DIGEST}", "model-only", 4096, ["seed", "task"],
        {"providers.review": {"provider_id": "probe-provider"}, "scorer": {"provider_id": "probe-provider"}})


def test_site_type_is_the_outcome_union_of_the_generated_envelope(tmp_path):
    program = _built(_confined(tmp_path))
    node, config = _confined_site(program)

    assert (node["result"], program.tree["types"][config.generated_outcome_type]) == (
        config.outcome_descriptor, config.outcome_descriptor)


class _Stop(Exception):
    pass


def test_commit_projection_is_evaluated_in_the_parent_as_the_first_operand(tmp_path):
    typed = _confined(tmp_path, (":commit revision", ":commit sha"),
                      ("(let* ((child", "(let* ((rev (record Rev :sha revision)) (sha rev.sha) (child"),
                      extra="(defrecord Rev (sha String))")
    seen = []

    def perform(node, operands, _identity, _owner, _reader):
        seen.append([operand.json_value() for operand in operands])
        raise _Stop

    with pytest.raises(_Stop):
        evaluate_closed_program(_built(typed), {"seed": 1, "revision": "c" * 40}, effect_handler=perform)

    assert seen == [["c" * 40, 1, "t"]]


def test_one_child_entry_serves_every_site_naming_it(tmp_path):
    typed = _confined(tmp_path, ("(let* ((child ", f"(let* ((other {RUN_REF}) (child "))

    program = _built(typed)

    assert (len(program.sites), len(program.tree["children"])) == (2, 1)


def test_installation_maxima_are_not_consulted_at_compile_time(tmp_path):
    huge = (":wall-seconds 900 :memory-mib 4096 :cpus 2 :pids 256 :workspace-mib 2048",
            ":wall-seconds 31536000 :memory-mib 1048576 :cpus 4096 :pids 4194304 :workspace-mib 1047616")

    _node, config = _confined_site(_built(_confined(tmp_path, huge)))

    assert dict(config.policy.limits)["memory-mib"] == 1048576


def test_source_relocation_keeps_parent_and_child_identity(tmp_path):
    first = _built(_confined(tmp_path / "a"))
    moved = _built(_confined(tmp_path / "b", ("  (defworkflow leaf", "\n\n\n  (defworkflow leaf"),
                             ("(defrecord Verdict", "\n\n  (defrecord Verdict")))

    assert (moved.digest, list(moved.tree["children"])) == (first.digest, list(first.tree["children"]))


def test_stored_program_keeps_its_captured_child_after_dependency_changes(tmp_path, monkeypatch):
    built = _built(_confined(tmp_path))
    stored = built.artifact()
    monkeypatch.setattr(sys.modules[__name__], "NESTED_HELPER", NESTED_HELPER.replace("(+ n 1)", "(+ n 2)"))
    rebuilt = _built(_confined(tmp_path))
    reloaded = ClosedProgram.from_artifact(stored)

    # The stored program keeps the captured child; a fresh compile of the
    # changed import is a different child and parent identity (the resume
    # program-digest comparison refuses it).
    assert (_child_program(reloaded).digest, _confined_site(reloaded)[1].program.child_program_digest,
            rebuilt.digest != built.digest, list(rebuilt.tree["children"]) != list(built.tree["children"])) == (
        _child_program(built).digest, _child_program(built).digest, True, True)


def _tampered(program, edit) -> str:
    tree = json.loads(program.artifact())
    edit(tree)
    return json.dumps(tree)


def _swap_child(tree, replacement):
    [digest] = tree["children"]
    tree["children"][digest] = replacement


CHILD_TAMPERING = {
    "owner-configuration": lambda tree, _other: next(iter(tree["children"].values()))["configuration"]["providers"][
        "providers.review"].update(provider_id="other-provider"),
    "child-from-changed-source": lambda tree, other: _swap_child(tree, next(iter(other.tree["children"].values()))),
    "rekeyed-child-from-changed-source": lambda tree, other: tree.update(children=dict(other.tree["children"])),
    "dropped-child": lambda tree, _other: tree.pop("children"),
    "nested-child": lambda tree, _other: next(iter(tree["children"].values())).update(
        children=deepcopy(tree["children"])),
}


@pytest.mark.parametrize("case", sorted(CHILD_TAMPERING))
def test_substituted_child_entry_or_owner_configuration_is_refused(tmp_path, case):
    from orchestrator.contracts.closed_program.program import ClosedProgramInvalid

    program = _built(_confined(tmp_path / "a"))
    other = _built(_confined(tmp_path / "b", ("(bump seed)", "(bump (+ seed 1))")))

    with pytest.raises(ClosedProgramInvalid):
        ClosedProgram.from_artifact(_tampered(program, lambda tree: CHILD_TAMPERING[case](tree, other)))


LEAF_CHILD = ((":program (:workflow candidate-body) :inputs (:seed seed :task \"t\")",
               ":program (:workflow leaf) :inputs (:value \"v\")"),
              ("((COMPLETED c) c.result.value)", "((COMPLETED c) 1)"))


def test_preparation_comparison_distinguishes_confined_policies(tmp_path):
    from orchestrator.workflow_lisp.closed.preparation_check import _Comparison

    payload = _wcc_perform(_confined(tmp_path / "a", *LEAF_CHILD)).operation_payload
    other = _wcc_perform(_confined(tmp_path / "b", *LEAF_CHILD,
                                   (":network :model-only", ":network :none"))).operation_payload
    comparison = object.__new__(_Comparison)

    comparison.run_ref_header(payload, payload, "payload")
    with pytest.raises(ValueError):
        comparison.run_ref_header(payload, other, "payload")


def test_generated_outcome_name_resolves_to_the_site_union(tmp_path):
    typed = _confined(tmp_path)
    outcome = _site(typed).run_ref_metadata.outcome_type_ref
    env = typed.workflow_type_envs["controller::run"]

    resolved = env.resolve_type(outcome.name, span=_site(typed).span, form_path=("probe",),
                                session_state=env.session_state)

    assert resolved is outcome


def _run(tmp_path, source: str, *inputs: str):
    import os
    import subprocess
    import sys

    install(tmp_path, {"helper.orc": NESTED_HELPER, "controller.orc": source})
    (tmp_path / "providers.json").write_text(json.dumps({"providers.review": "probe-provider"}))
    (tmp_path / "prompts.json").write_text(json.dumps({"prompts.base": "inputs/prompt.md"}))
    (tmp_path / "boundaries.json").write_text(json.dumps({"fetch": {
        "kind": "external_tool", "stable_command": ["python", "probe.py"], "closure": ["probe.py"]}}))
    (tmp_path / "state").mkdir()
    argv = [sys.executable, "-m", "orchestrator", "run", "controller.orc", "--entry-workflow", "controller::run",
            "--provider-externs-file", "providers.json", "--prompt-externs-file", "prompts.json",
            "--command-boundaries-file", "boundaries.json", "--state-dir", "state"]
    for item in inputs:
        argv += ["--input", item]
    repo = Path(__file__).resolve().parents[1]
    return subprocess.run(argv, cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(repo)},
                          capture_output=True, text=True, timeout=180)


def test_running_a_confined_site_is_refused_before_any_run_state(tmp_path):
    source = CONFINED.replace("EXTRA", "").replace("RUN_REF", RUN_REF)

    completed = _run(tmp_path, source, "seed=1", "revision=" + "c" * 40)

    assert (completed.returncode, "run_ref_provider_transport_unavailable" in completed.stderr,
            list((tmp_path / "state").iterdir())) == (2, True, [])


PLAIN_238 = CONFINED.replace("EXTRA", "").split("    (let* ((child")[0] + "    (+ seed 1)))"


def test_target_238_program_without_a_confined_site_runs(tmp_path):
    completed = _run(tmp_path, PLAIN_238, "seed=1", "revision=x")

    assert completed.returncode == 0, completed.stderr


def test_resuming_into_a_confined_site_is_refused_before_loading_the_run(tmp_path):
    import os
    import subprocess
    import sys

    assert _run(tmp_path, PLAIN_238, "seed=1", "revision=" + "c" * 40).returncode == 0
    [run_root] = list((tmp_path / "state").iterdir())
    (tmp_path / "controller.orc").write_text(CONFINED.replace("EXTRA", "").replace("RUN_REF", RUN_REF))

    completed = subprocess.run(
        [sys.executable, "-m", "orchestrator", "resume", run_root.name, "--state-dir", "state"],
        cwd=tmp_path, env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        capture_output=True, text=True, timeout=180)

    assert (completed.returncode, "run_ref_provider_transport_unavailable" in completed.stderr) == (2, True)


def test_commit_operand_is_demanded_by_the_run_ref_like_its_inputs(tmp_path):
    from orchestrator.workflow_lisp.closed.command_templates import _wcc_continuation_binding_demands

    body = _wcc_body(_confined(tmp_path))
    run_ref_demand = _wcc_continuation_binding_demands(body)[id(body)][0]

    assert {"revision", "seed"} <= run_ref_demand


@pytest.mark.parametrize("children", [{}, "foreign"])
def test_program_without_confined_sites_refuses_child_entries(tmp_path, children):
    from orchestrator.contracts.closed_program.program import ClosedProgramInvalid

    plain = _child_entry(_typed(tmp_path / "plain"))
    foreign = _built(_confined(tmp_path / "confined")).tree["children"]
    tree = json.loads(plain.artifact())
    tree["children"] = foreign if children == "foreign" else children

    with pytest.raises(ClosedProgramInvalid):
        ClosedProgram.from_artifact(json.dumps(tree))


def test_forged_confined_memory_below_profile_reserve_is_refused_on_read_back(tmp_path):
    from base64 import b64decode, b64encode
    from orchestrator.contracts.closed_program.program import ClosedProgramInvalid

    program = _built(_confined(tmp_path))
    node, _config = _confined_site(program)

    def forge(tree):
        from orchestrator.workflow.evaluated.machine import site_nodes

        record = json.loads(b64decode(node["config"]))
        record["environment"]["limits"][1][1] = 1
        forged = b64encode(json.dumps(record, sort_keys=True, separators=(",", ":")).encode()).decode()
        [target] = [row for row in site_nodes(ClosedProgram(tree, (), "")).values() if row["class"] == "run_ref"]
        target["config"] = forged

    with pytest.raises(ClosedProgramInvalid):
        ClosedProgram.from_artifact(_tampered(program, forge))


def test_confined_translation_refuses_inputs_that_disagree_with_the_typed_origin(tmp_path):
    from orchestrator.workflow_lisp.closed.effects import _translate_run_ref_workflow

    perform = _wcc_perform(_confined(tmp_path))
    reordered = replace(perform, keyword_args=tuple(reversed(perform.keyword_args)))

    with pytest.raises(ValueError, match="retained result origin"):
        _translate_run_ref_workflow(None, reordered, None, {})


# Ruling P12: a confined site is refused in any `list/map-effect` frame,
# serial or parallel, directly or through calls.

MAP_CALLEES = (
    f"(defworkflow one ((seed Int) (revision String)) -> Int (let* ((child {RUN_REF})) "
    "(match child ((COMPLETED c) c.result.value) ((FAILED f) 0))))"
    "(defworkflow two ((seed Int) (revision String)) -> Int (call one :seed seed :revision revision))"
    f"(defworkflow onep ((seed Int) (revision String)) -> Int (let* ((child {PATH_RUN_REF})) 1))"
)
MAP_RUN_BODY = "(let* ((child RUN_REF))\n      (match child\n        ((COMPLETED c) c.result.value)\n        ((FAILED f) f.accounting.attempt_ordinal)))"
MAP_PLACEMENTS = {
    "serial-direct": "(let* ((xs (list/map-effect ((x (list 1 2))) :max 2 "
                     + RUN_REF.replace(":seed seed", ":seed x") + "))) 1)",
    "serial-through-call": "(let* ((xs (list/map-effect ((x (list 1 2))) :max 2 "
                           "(call one :seed x :revision revision)))) 1)",
    "serial-through-nested-call": "(let* ((xs (list/map-effect ((x (list 1 2))) :max 2 "
                                  "(call two :seed x :revision revision)))) 1)",
    "parallel-through-call": '(let* ((xs (list/map-effect ((repo (list "a"))) :max 1 :parallel 1 '
                             ":workspace repo (call one :seed 1 :revision revision)))) 1)",
}


def _map_program(tmp_path, body):
    source = CONFINED.replace("EXTRA", MAP_CALLEES).replace(MAP_RUN_BODY, body)
    install(tmp_path, {"helper.orc": NESTED_HELPER, "controller.orc": source})
    return compile_typed_program(
        tmp_path / "controller.orc", entry_workflow="controller::run", source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES, provider_externs={"providers.review": "probe-provider"},
        prompt_externs={"prompts.base": PROMPTS["prompt"]}, workspace_root=tmp_path)


@pytest.mark.parametrize("case", sorted(MAP_PLACEMENTS))
def test_confined_site_in_a_list_map_effect_frame_is_refused(tmp_path, case):
    assert MAP_RUN_BODY in CONFINED
    with pytest.raises(LispFrontendCompileError) as refused:
        _map_program(tmp_path, MAP_PLACEMENTS[case])

    assert [row.code for row in refused.value.diagnostics] == ["run_ref_placement_invalid"]


def test_path_site_through_a_serial_list_map_effect_call_is_still_admitted(tmp_path):
    typed = _map_program(tmp_path, "(let* ((xs (list/map-effect ((x (list 1 2))) :max 2 "
                                   "(call onep :seed x :revision revision)))) 1)")

    assert len(_built(typed).sites) == 1


# Fix round 2: the map placement walk runs only for programs with confined
# sites, follows imported programs, and skips callees resolved elsewhere.

PRODUCER_238 = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
  (defmodule producer) (export get)
  (defworkflow leaf ((n Int)) -> Int (+ n 1))
  (defworkflow get ((n Int)) -> Int
    (let* ((child (run-ref :source (:repo "file:///srv/p.git" :commit "{"a" * 40}")
                    :program (:workflow leaf) :inputs (:n n) :policy {POLICY.replace(":model-only", ":none")})))
      (match child ((COMPLETED c) c.result.value) ((FAILED f) 0)))))'''
PLAIN_PRODUCER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
  (defmodule producer) (export get)
  (defworkflow get ((n Int)) -> Int (+ n 1)))'''
MAP_DEP = "(let* ((xs (list/map-effect ((x (list 1 2))) :max 2 (call dep :n x)))) 1)"


def _bundle_build(tmp_path, producer: str, body: str):
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle

    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "producer.orc").write_text(producer)
    (tmp_path / "imports.json").write_text(json.dumps({"dep": {"kind": "compiled", "path": "producer.orc"}}))
    (tmp_path / "consumer.orc").write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
      (defmodule consumer) (export run)
      (defworkflow run () -> Int BODY))'''.replace("BODY", body))
    return build_closed_program_bundle(FrontendBuildRequest(
        source_path=tmp_path / "consumer.orc", entry_workflow="run", workspace_root=tmp_path,
        source_roots=(tmp_path,), imported_workflow_bundles_path=tmp_path / "imports.json"))


def test_confined_site_in_an_imported_program_under_a_map_body_is_refused(tmp_path):
    with pytest.raises(LispFrontendCompileError) as refused:
        _bundle_build(tmp_path, PRODUCER_238, MAP_DEP)

    assert [row.code for row in refused.value.diagnostics] == ["run_ref_placement_invalid"]


def test_confined_site_in_an_imported_program_called_directly_compiles(tmp_path):
    built = _bundle_build(tmp_path, PRODUCER_238, "(call dep :n 1)")

    assert len(built.program.tree["children"]) == 1


def test_map_body_calling_an_imported_bundle_compiles_as_before(tmp_path):
    built = _bundle_build(tmp_path, PLAIN_PRODUCER, MAP_DEP)

    assert ("children" in built.program.tree, len(built.program.sites)) == (False, 0)


def _with_imports(typed, **imported_programs):
    # As for a workflow-bundle or lookup-alias callee: `dep` is in neither table.
    return replace(typed, imported_programs=imported_programs)


def test_map_walk_never_runs_for_a_program_without_confined_sites(tmp_path):
    from orchestrator.workflow_lisp.typecheck_run_ref import refuse_unsupported_confined_children

    typed = _bundle_build(tmp_path, PLAIN_PRODUCER, MAP_DEP).typed_program

    assert refuse_unsupported_confined_children(_with_imports(typed)) is None


def test_map_walk_skips_callees_resolved_outside_the_program_tables(tmp_path):
    from orchestrator.workflow_lisp.typecheck_run_ref import refuse_unsupported_confined_children

    typed = _bundle_build(tmp_path / "map", PLAIN_PRODUCER, MAP_DEP).typed_program
    confined = _bundle_build(tmp_path / "confined", PRODUCER_238, "(call dep :n 1)").typed_program

    assert refuse_unsupported_confined_children(
        _with_imports(typed, other=confined.imported_programs["dep"])) is None
