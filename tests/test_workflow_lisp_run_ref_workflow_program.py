"""F1 feasibility: a non-exported named workflow builds as a private child entry.

The child-entry seam is the ordinary closed-program builder applied to a typed
program whose entry is the named workflow (no `:program (:workflow ...)`
surface syntax yet; that arrives with the syntax task).
"""

from __future__ import annotations

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
      (if verdict.ok (let* ((box (fetch (bump seed)))) box.n) 0)))
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


def _confined(root: Path, *edits: tuple[str, str], extra: str = ""):
    source = CONFINED.replace("EXTRA", extra).replace("RUN_REF", RUN_REF)
    for old, new in edits:
        assert old in source, old
        source = source.replace(old, new)
    install(root, {"helper.orc": NESTED_HELPER, "controller.orc": source})
    return compile_typed_program(
        root / "controller.orc", entry_workflow="controller::run", source_roots=(root,),
        command_boundaries=BOUNDARIES, provider_externs={"providers.review": "probe-provider"},
        prompt_externs={"prompts.base": PROMPTS["prompt"]}, workspace_root=root)


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
    "headroom": ((":memory-mib 4096", ":memory-mib 2943"), "run_ref_literal_required"),
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
    site = _site(_confined(tmp_path, (":memory-mib 4096", ":memory-mib 2944")))

    assert dict(site.program.policy.limits)["memory-mib"] == 2944


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


def _wcc_perform(typed):
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.wcc import WccLet, WccPerform, elaborate_typed_workflow_body

    run = typed.workflows["controller::run"]
    body = elaborate_typed_workflow_body(
        run.typed_body, owner_name="controller::run", type_env=typed.workflow_type_envs["controller::run"],
        value_env=dict(run.signature.params), route_schema_version="wcc_m4")
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


def test_workflow_program_closed_build_refuses_until_child_entry_compiles(tmp_path):
    typed = _confined(tmp_path)

    with pytest.raises(LispFrontendCompileError) as refused:
        build_closed_program(typed, builder=Builder(typed))

    assert [row.code for row in refused.value.diagnostics] == ["run_ref_child_target_unavailable"]


def test_trial_arm_cannot_run_a_confined_workflow_child():
    from orchestrator.workflow_lisp.expressions import parse_trial_expression
    from tests.test_workflow_lisp_trial import _expression, _trial_source

    arm = RUN_REF.replace(":commit revision", ':commit "' + "c" * 40 + '"')
    with pytest.raises(LispFrontendCompileError) as refused:
        parse_trial_expression(_expression(_trial_source(arm_a=arm)), target_dsl_version="2.38")

    assert refused.value.diagnostics[0].code == "run_ref_child_target_unavailable"
