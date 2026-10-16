"""Target 2.39 inferred effects and definition-owned optional restrictions."""

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.effects import CallsWorkflowEffect, UsesCommandEffect
from tests.workflow_lisp_closed_program_helpers import install


def _compile(root, declarations, body="(helper)", *, target="2.39", sources=None, imports=""):
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
      (defmodule el1/entry) {imports} (export run)
      {declarations}
      (defworkflow run () -> Int {body}))'''
    graph = dict(sources or {})
    graph["el1/entry.orc"] = source
    path = install(root, graph, entry_path="el1/entry.orc")
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding

    return compile_typed_program(path, entry_workflow="run", source_roots=(root,),
        workspace_root=root, command_boundaries={
            "probe": ExternalToolBinding(name="probe", stable_command=("python", "probe.py"), closure=()),
        }, provider_externs={"providers.allowed": "allowed", "providers.other": "other"},
        prompt_externs={"prompts.ask": "prompt.md"})


@pytest.mark.parametrize("clause", ["", ":effects ()", ":effects ((uses-command unused-label))"])
def test_new_target_omission_empty_and_unused_domain_ceiling_are_distinct(tmp_path, clause):
    typed = _compile(tmp_path, f"(defproc helper () -> Int {clause} 7)")
    helper = typed.procedures["el1/entry::helper"]
    assert (helper.signature.declared_effects is None) == (clause == "")
    assert not helper.transitive_effect_summary.transitive_effects
    assert build_closed_program(typed)


def test_omitted_wrapper_infers_command_across_calls(tmp_path):
    typed = _compile(tmp_path, '''
      (defproc leaf () -> Int (command-result probe :argv ("python" "probe.py") :returns Int))
      (defproc helper () -> Int (leaf))''')
    assert typed.procedures["el1/entry::helper"].transitive_effect_summary.transitive_effects == {
        UsesCommandEffect(subject=("probe",))}


@pytest.mark.parametrize("clause", [":effects ()", ":effects ((uses-command another))"])
def test_explicit_ceiling_rejects_uncovered_effect_at_definition(tmp_path, clause):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, f'''(defproc helper () -> Int {clause}
          (command-result probe :argv ("python" "probe.py") :returns Int))''')
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "procedure_effect_ceiling_exceeded"
    assert "uses-command(probe)" in diagnostic.message
    assert "helper" in diagnostic.message
    assert Path(diagnostic.span.start.path).name == "entry.orc"


@pytest.mark.parametrize("clause", ["((uses-provider missing))", "((uses-provider prompts.ask))",
    "((calls-workflow missing))", "((calls-workflow providers.allowed))"])
def test_unused_unknown_or_wrong_kind_symbol_is_rejected(tmp_path, clause):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, f"(defproc helper () -> Int :effects {clause} 7)")
    assert caught.value.diagnostics[0].code == "procedure_effect_invalid"


@pytest.mark.parametrize("effectful", [False, True])
def test_explicit_empty_is_checked_on_materialized_proc_ref(tmp_path, effectful):
    leaf = '(command-result probe :argv ("python" "probe.py") :returns Int)' if effectful else "7"
    declarations = f'''(defproc leaf () -> Int {leaf})
      (defproc forward ((hook ProcRef[() -> Int])) -> Int :effects () (hook))'''
    if effectful:
        with pytest.raises(LispFrontendCompileError) as caught:
            _compile(tmp_path, declarations, "(forward (proc-ref leaf))")
        assert caught.value.diagnostics[0].code == "procedure_effect_ceiling_exceeded"
    else:
        assert build_closed_program(_compile(tmp_path, declarations, "(forward (proc-ref leaf))"))


def test_generated_local_helper_has_omitted_effect_contract(tmp_path):
    typed = _compile(tmp_path, "(defproc apply ((hook ProcRef[() -> Int])) -> Int (hook))",
        "(let-proc (local () -> Int :captures () 7) (apply (proc-ref local)))")
    generated = [p for p in typed.procedures.values() if p.definition.generated_local_procedure]
    assert generated and all(p.signature.declared_effects is None for p in generated)
    assert all(p.signature.requested_lowering_mode.value == "inline" for p in generated)
    assert all(p.resolved_lowering_mode.value == "inline" for p in generated)


def test_target_239_rejects_authored_lowering_with_expansion_location(tmp_path):
    declarations = '''(defmacro define-helper ()
        (defproc helper () -> Int
          :lowering inline
          7))
      (define-helper)'''
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, declarations)

    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "proc_lowering_annotation_invalid"
    assert Path(diagnostic.span.start.path).name == "entry.orc"
    assert diagnostic.span.start.line == 5
    assert diagnostic.form_path == ("workflow-lisp", "defproc", "helper")
    assert diagnostic.expansion_stack
    assert diagnostic.expansion_stack[0].macro_name == "define-helper"
    assert diagnostic.expansion_stack[0].call_span.start.line == 7


def test_target_239_inline_effectful_procedure_skips_legacy_lowering_analysis(
    tmp_path, monkeypatch
):
    from orchestrator.workflow_lisp import procedure_specialization
    from orchestrator.workflow_lisp.procedures import ProcedureLoweringMode

    def unexpected_analysis(*args, **kwargs):
        pytest.fail("target-2.39 procedures must bypass AUTO/private-workflow analysis")

    monkeypatch.setattr(
        procedure_specialization, "_procedure_private_boundary_valid", unexpected_analysis
    )
    monkeypatch.setattr(
        procedure_specialization, "_procedure_private_body_valid", unexpected_analysis
    )
    monkeypatch.setattr(
        procedure_specialization,
        "_procedure_private_call_site_analysis",
        unexpected_analysis,
    )
    typed = _compile(
        tmp_path,
        '''(defproc leaf () -> Int
             (command-result probe :argv ("python" "probe.py") :returns Int))
           (defproc apply ((hook ProcRef[() -> Int])) -> Int (hook))''',
        "(+ (apply (proc-ref leaf)) (apply (proc-ref leaf)))",
    )

    helpers = [
        procedure
        for procedure in typed.procedures.values()
        if procedure.definition.name == "el1/entry::apply"
        or procedure.specialization is not None
    ]
    assert helpers
    assert all(procedure.signature.declared_effects is None for procedure in helpers)
    assert all(
        procedure.signature.requested_lowering_mode is ProcedureLoweringMode.INLINE
        for procedure in helpers
    )
    assert all(
        procedure.resolved_lowering_mode is ProcedureLoweringMode.INLINE
        and procedure.generated_workflow_name is None
        for procedure in helpers
    )
    assert any(procedure.transitive_effect_summary.transitive_effects for procedure in helpers)


@pytest.mark.parametrize("target", ["2.35", "2.36", "2.37", "2.38", "2.39"])
def test_loop_call_private_override_respects_definition_origin(tmp_path, monkeypatch, target):
    from orchestrator.workflow_lisp import procedure_specialization

    checks = []
    original_boundary = procedure_specialization._procedure_private_boundary_valid
    original_body = procedure_specialization._procedure_private_body_valid

    def counted_boundary(*args, **kwargs):
        checks.append("boundary")
        return original_boundary(*args, **kwargs)

    def counted_body(*args, **kwargs):
        checks.append("body")
        return original_body(*args, **kwargs)

    if target == "2.39":
        def unexpected_analysis(*args, **kwargs):
            pytest.fail("target-2.39 loop calls must bypass legacy private eligibility")

        monkeypatch.setattr(
            procedure_specialization, "_procedure_private_boundary_valid", unexpected_analysis
        )
        monkeypatch.setattr(
            procedure_specialization, "_procedure_private_body_valid", unexpected_analysis
        )
    else:
        monkeypatch.setattr(
            procedure_specialization, "_procedure_private_boundary_valid", counted_boundary
        )
        monkeypatch.setattr(
            procedure_specialization, "_procedure_private_body_valid", counted_body
        )
    effect_clauses = (
        "" if target == "2.39" else ":effects ((uses-command probe)) :lowering inline"
    )
    typed = _compile(
        tmp_path,
        f'''(defproc next-value () -> Int
              {effect_clauses}
              (command-result probe :argv ("python" "probe.py") :returns Int))''',
        '''(loop/recur :max 1
             :state (loop-state (current Int 0))
             :on-exhausted state.current
             (fn (state)
               (let* ((updated (next-value)))
                 (if (< updated 1)
                   (continue (loop-state :like state :current updated))
                   (done updated)))))''',
        target=target,
    )

    checks.clear()
    build_closed_program(typed)

    if target != "2.39":
        assert checks


@pytest.mark.parametrize("origin", ["2.35", "2.36", "2.37", "2.38"])
def test_new_caller_preserves_imported_old_auto_and_private_identities(tmp_path, origin):
    library = f'''(workflow-lisp (:language "0.1") (:target-dsl "{origin}")
      (defmodule el1/lib) (export ChecksResult private-helper auto-helper)
      (defrecord ChecksResult (value Int))
      (defproc private-helper () -> ChecksResult
        :effects ((uses-command probe)) :lowering private-workflow
        (command-result probe :argv ("python" "probe.py") :returns ChecksResult))
      (defproc auto-helper () -> ChecksResult
        :effects ((uses-command probe)) :lowering auto
        (command-result probe :argv ("python" "probe.py") :returns ChecksResult)))'''
    sources = {"el1/lib.orc": library}
    imports = "(import el1/lib :only (ChecksResult private-helper auto-helper))"
    body = '''(let* ((private-result (private-helper))
                     (automatic-first (auto-helper))
                     (automatic-second (auto-helper)))
                automatic-first.value)'''
    old = _compile(
        tmp_path / f"old-{origin}",
        "",
        body,
        target=origin,
        sources=sources,
        imports=imports,
    )
    new = _compile(
        tmp_path / f"new-{origin}",
        "",
        body,
        sources=sources,
        imports=imports,
    )

    for name, strategy in (("private-helper", "private-workflow"), ("auto-helper", "auto")):
        old_proc = old.procedures[f"el1/lib::{name}"]
        new_proc = new.procedures[f"el1/lib::{name}"]
        assert old_proc.definition.effect_contract_target == origin
        assert new_proc.definition.effect_contract_target == origin
        assert old_proc.signature.requested_lowering_mode.value == strategy
        assert (
            new_proc.signature.requested_lowering_mode
            == old_proc.signature.requested_lowering_mode
        )
        assert new_proc.resolved_lowering_mode == old_proc.resolved_lowering_mode
        assert new_proc.generated_workflow_name == old_proc.generated_workflow_name


def test_old_definition_origin_survives_new_caller_specialization(tmp_path):
    lib = '''(workflow-lisp (:language "0.1") (:target-dsl "2.38")
      (defmodule el1/lib) (export forward)
      (defproc forward ((hook ProcRef[() -> Int])) -> Int :effects () :lowering inline (hook)))'''
    typed = _compile(tmp_path, '''(defproc helper () -> Int (command-result probe :argv ("python" "probe.py") :returns Int))''',
        "(forward (proc-ref helper))", sources={"el1/lib.orc": lib}, imports="(import el1/lib :only (forward))")
    specialized = [p for p in typed.procedures.values() if p.specialization
        and p.specialization.base_name == "el1/lib::forward"]
    assert specialized and all(p.definition.effect_contract_target == "2.38" for p in specialized)


@pytest.mark.parametrize("target", ["2.37", "2.38"])
def test_old_caller_refuses_new_definition_before_import_shortcuts(tmp_path, target):
    lib = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule el1/lib) (export helper) (defproc helper () -> Int 7))'''
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, "", target=target, imports="(import el1/lib :only (helper))",
            sources={"el1/lib.orc": lib})
    assert caught.value.diagnostics[0].code == "evaluated_execution_target_direction_invalid"


def test_workflow_ceiling_resolves_alias_and_unused_workflow(tmp_path):
    lib = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule el1/lib) (export target unused)
      (defworkflow target () -> Int 7) (defworkflow unused () -> Int 8))'''
    typed = _compile(tmp_path, '''(defproc helper () -> Int
        :effects ((calls-workflow h.target h.unused)) (call h.target))''',
        imports="(import el1/lib :as h :only (target unused))", sources={"el1/lib.orc": lib})
    from orchestrator.workflow_lisp.effects import CallsWorkflowEffect

    assert typed.procedures["el1/entry::helper"].transitive_effect_summary.transitive_effects == {
        CallsWorkflowEffect(subject=("el1/lib::target",))}


def test_imported_restriction_keeps_definition_scope_under_shadowing(tmp_path):
    lib = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule el1/lib) (export invoke)
      (defworkflow target () -> Int 7)
      (defproc invoke () -> Int :effects ((calls-workflow target)) (call target)))'''
    typed = _compile(tmp_path, '''(defworkflow target () -> Int 8)
      (defproc helper () -> Int :effects ((calls-workflow el1/lib::target)) (invoke))''',
        imports="(import el1/lib :only (invoke))", sources={"el1/lib.orc": lib})
    assert build_closed_program(typed)


def test_workflow_ref_restriction_substitutes_selected_identity(tmp_path):
    from orchestrator.workflow_lisp.effects import CallsWorkflowEffect

    typed = _compile(tmp_path, '''(defrecord Box (n Int))
      (defworkflow target ((n Int)) -> Box (record Box :n n))
      (defproc invoke ((runner WorkflowRef[Int -> Box])) -> Box
        :effects ((calls-workflow runner)) (call runner :n 7))
      (defproc helper () -> Int
        (let* ((box (invoke (workflow-ref target)))) box.n))''')
    assert build_closed_program(typed)
    selected = [row for row in typed.procedures.values()
        if getattr(row.specialization, "workflow_ref_bindings", {})]
    assert selected
    assert all(row.transitive_effect_summary.transitive_effects == {
        CallsWorkflowEffect(subject=("el1/entry::target",))} for row in selected)


def test_named_wrapper_ceiling_uses_selected_callee_workflow(tmp_path):
    typed = _compile(tmp_path, '''(defrecord Box (n Int))
      (defworkflow target ((n Int)) -> Box (record Box :n n))
      (defproc invoke ((runner WorkflowRef[Int -> Box])) -> Box
        :effects ((calls-workflow runner)) (call runner :n 7))
      (defproc helper () -> Int :effects ((calls-workflow target))
        (let* ((box (invoke (workflow-ref target)))) box.n))''')
    assert build_closed_program(typed)


def test_new_wrapper_uses_selected_workflow_of_a_235_definition(tmp_path):
    from orchestrator.workflow_lisp.effects import CallsWorkflowEffect

    library = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule el1/lib) (export Box invoke)
      (defrecord Box (n Int))
      (defproc invoke ((runner WorkflowRef[Int -> Box])) -> Box
        :effects ((calls-workflow runner)) :lowering inline (call runner :n 7)))'''
    typed = _compile(tmp_path, '''(defworkflow target ((n Int)) -> Box (record Box :n n))
      (defproc helper () -> Int :effects ((calls-workflow target))
        (let* ((box (invoke (workflow-ref target)))) box.n))''',
        sources={"el1/lib.orc": library}, imports="(import el1/lib :only (Box invoke))")
    assert build_closed_program(typed)
    selected = [row for row in typed.procedures.values()
        if getattr(row.specialization, "base_name", None) == "el1/lib::invoke"]
    assert selected and all(row.definition.effect_contract_target == "2.35" for row in selected)
    assert typed.procedures["el1/entry::helper"].transitive_effect_summary.transitive_effects == {
        CallsWorkflowEffect(subject=("el1/entry::target",))}


@pytest.mark.parametrize("permitted", ["allowed", "other"])
@pytest.mark.parametrize("shadow", [False, True])
def test_nested_workflow_formals_keep_their_callers_lexical_actuals(tmp_path, permitted, shadow):
    from orchestrator.workflow_lisp.effects import CallsWorkflowEffect
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.workflow_evaluated_totality_helpers import checked_run

    nested_call = "(let* ((runner other)) (inner runner))" if shadow else "(inner other)"
    declarations = f'''(defrecord Box (n Int))
      (defworkflow allowed ((n Int)) -> Box (record Box :n 1))
      (defworkflow other ((n Int)) -> Box (record Box :n 9))
      (defproc inner ((runner WorkflowRef[Int -> Box])) -> Box (call runner :n 7))
      (defproc outer ((runner WorkflowRef[Int -> Box]) (other WorkflowRef[Int -> Box])) -> Box
        :effects ((calls-workflow {permitted})) {nested_call})
      (defproc helper () -> Int
        (let* ((box (outer (workflow-ref allowed) (workflow-ref other)))) box.n))'''
    if permitted == "allowed":
        with pytest.raises(LispFrontendCompileError) as caught:
            _compile(tmp_path, declarations)
        assert caught.value.diagnostics[0].code == "procedure_effect_ceiling_exceeded"
        assert "el1/entry::other" in caught.value.diagnostics[0].message
    else:
        typed = _compile(tmp_path, declarations)
        assert typed.procedures["el1/entry::helper"].transitive_effect_summary.transitive_effects == {
            CallsWorkflowEffect(subject=("el1/entry::other",))}
        assert build_closed_program(typed)
        result = _run_cli(tmp_path, str(tmp_path / "el1/entry.orc"))
        assert result.returncode == 0, result.stderr
        _, snapshot = checked_run(tmp_path)
        assert snapshot.terminal.data["value"] == 9


def test_workflow_callee_command_effect_survives_selected_edge_propagation(tmp_path):
    from orchestrator.workflow_lisp.effects import CallsWorkflowEffect

    typed = _compile(tmp_path, '''(defworkflow target () -> Int
        (command-result probe :argv ("python" "probe.py") :returns Int))
      (defproc helper () -> Int (call target))''')
    assert typed.procedures["el1/entry::helper"].transitive_effect_summary.transitive_effects == {
        CallsWorkflowEffect(subject=("el1/entry::target",)), UsesCommandEffect(subject=("probe",))}


def test_procedure_cycle_through_workflow_keeps_its_existing_refusal(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, '''(defworkflow target () -> Int (helper))
          (defproc helper () -> Int (call target))''')
    assert caught.value.diagnostics[0].code == "proc_lowering_cycle"


@pytest.mark.parametrize("alias", [False, True])
def test_workflow_ref_lexical_binding_precedes_visible_workflow_name(tmp_path, alias):
    from orchestrator.workflow_lisp.effects import CallsWorkflowEffect
    from orchestrator.workflow_lisp.procedures import procedure_effect_inspection

    formal = "selected" if alias else "runner"
    body = "(let* ((runner selected)) (call runner :n 7))" if alias else "(call runner :n 7)"
    typed = _compile(tmp_path, f'''(defrecord Box (n Int))
      (defworkflow runner ((n Int)) -> Box (record Box :n 1))
      (defworkflow other ((n Int)) -> Box (record Box :n 9))
      (defproc invoke (({formal} WorkflowRef[Int -> Box])) -> Box
        :effects ((calls-workflow other)) {body})
      (defproc helper () -> Int
        (let* ((box (invoke (workflow-ref other)))) box.n))''')
    assert build_closed_program(typed)
    assert typed.procedures["el1/entry::helper"].transitive_effect_summary.transitive_effects == {
        CallsWorkflowEffect(subject=("el1/entry::other",))}
    assert any("incomplete" in line for line in procedure_effect_inspection(
        typed.procedures["el1/entry::invoke"], typed.procedures))


def test_empty_ceiling_rejects_a_generic_callees_known_workflow_boundary(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, '''(defrecord Box (n Int))
          (defworkflow target ((n Int)) -> Box (record Box :n n))
          (defproc inner ((runner WorkflowRef[Int -> Box])) -> Box (call runner :n 7))
          (defproc outer ((other WorkflowRef[Int -> Box])) -> Box :effects () (inner other))
          (defproc helper () -> Int
            (let* ((box (outer (workflow-ref target)))) box.n))''')
    assert caught.value.diagnostics[0].code == "procedure_effect_ceiling_exceeded"


def test_unused_workflow_ref_forwarding_keeps_a_proven_empty_ceiling(tmp_path):
    from orchestrator.workflow_lisp.procedures import procedure_effect_inspection

    typed = _compile(tmp_path, '''(defrecord Box (n Int))
      (defworkflow target ((n Int)) -> Box (record Box :n n))
      (defproc ignore ((unused WorkflowRef[Int -> Box])) -> Int 7)
      (defproc outer ((other WorkflowRef[Int -> Box])) -> Int :effects () (ignore other))
      (defproc helper () -> Int (outer (workflow-ref target)))''')
    assert build_closed_program(typed)
    for name in ("ignore", "outer", "helper"):
        procedure = typed.procedures[f"el1/entry::{name}"]
        assert not procedure.transitive_effect_summary.transitive_effects
        assert "effect status: complete" in procedure_effect_inspection(procedure, typed.procedures)


def test_pending_workflow_identity_does_not_hide_known_command_effect(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, '''(defrecord Box (n Int))
          (defworkflow target ((n Int)) -> Box (record Box :n n))
          (defproc inner ((runner WorkflowRef[Int -> Box])) -> Box
            (let* ((n (command-result probe :argv ("python" "probe.py") :returns Int)))
              (call runner :n n)))
          (defproc outer ((other WorkflowRef[Int -> Box])) -> Box
            :effects ((calls-workflow target)) (inner other))
          (defproc helper () -> Int
            (let* ((box (outer (workflow-ref target)))) box.n))''')
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == "procedure_effect_ceiling_exceeded"
    assert "uses-command(probe)" in diagnostic.message


def test_absent_clause_does_not_make_effectful_function_pure(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, '''(defproc leaf () -> Int
            (command-result probe :argv ("python" "probe.py") :returns Int))
          (defun pure () -> Int (leaf))
          (defproc helper () -> Int (pure))''')
    assert caught.value.diagnostics[0].code == "pure_function_has_effect"


@pytest.mark.parametrize("kind", ["run-ref", "trial"])
@pytest.mark.parametrize("specialized", [False, True])
def test_omitted_child_work_wrapper_cannot_enter_pure_function(tmp_path, kind, specialized):
    from tests.test_workflow_lisp_run_ref_workflow_program import PATH_RUN_REF
    from tests.test_workflow_lisp_trial import _trial_source

    effect = (PATH_RUN_REF if kind == "run-ref" else _trial_source()
        .replace('"scorer"', '"providers.allowed"').replace('"rubrics/trial.md"', '"prompt.md"'))
    dispatch = "(forward (proc-ref leaf))" if specialized else "(leaf)"
    declarations = f'''(defworkflow first () -> String "a")
      (defworkflow second () -> String "b")
      (defproc leaf () -> Int (let* ((result {effect})) 7))
      (defproc forward ((hook ProcRef[() -> Int])) -> Int (hook))
      (defun pure () -> Int {dispatch})
      (defproc helper () -> Int (pure))'''
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, declarations)
    diagnostic = caught.value.diagnostics[0]
    assert diagnostic.code == ("run_ref_placement_invalid" if kind == "run-ref"
        else "trial_nested_unsupported")
    assert "pure function" in diagnostic.message


@pytest.mark.parametrize("provider, allowed", [("providers.allowed", True), ("providers.other", False)])
def test_provider_ceiling_checks_the_named_extern_key(tmp_path, provider, allowed):
    source = f'''(defproc helper () -> Int :effects ((uses-provider providers.allowed))
      (provider-result {provider} :prompt prompts.ask :inputs () :returns Int))'''
    if allowed:
        assert _compile(tmp_path, source)
    else:
        with pytest.raises(LispFrontendCompileError) as caught:
            _compile(tmp_path, source)
        assert caught.value.diagnostics[0].code == "procedure_effect_ceiling_exceeded"


def test_new_inspection_uses_inferred_facts_and_marks_generic_calls_incomplete(tmp_path, capsys):
    from orchestrator.cli.commands.repl import ReplSession, _dispatch
    from orchestrator.lsp.navigation import build_navigation_index
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from orchestrator.workflow_lisp.repl_expr import LoadedModule

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule el1/inspect) (export run)
      (defrecord Box (n Int))
      (defworkflow boxed ((n Int)) -> Box (record Box :n n))
      (defworkflow target () -> Int 7)
      (defproc helper () -> Int (call target))
      (defproc forward ((hook ProcRef[() -> Int])) -> Int (hook))
      (defproc seven ((unused ProcRef[() -> Int]) (runner WorkflowRef[Int -> Box])) -> Int 7)
      (defproc invoke ((runner WorkflowRef[Int -> Box])) -> Box (call runner :n 7))
      (defproc ignored ((unused WorkflowRef[Int -> Box])) -> Int (call target))
      (defproc concrete-alias ((unused WorkflowRef[Int -> Box])) -> Box
        (let* ((unused (workflow-ref boxed))) (call unused :n 7)))
      (defproc pending-alias ((runner WorkflowRef[Int -> Box])) -> Box
        (let* ((selected runner)) (call selected :n 7)))
      (defworkflow run () -> Int (helper)))'''
    path = install(tmp_path, source)
    built = prepare_closed_program_bundle(FrontendBuildRequest(
        source_path=path, source_roots=(tmp_path,), workspace_root=tmp_path, entry_workflow="run"))
    session = ReplSession(tmp_path, None, module=LoadedModule(built, path))
    _dispatch(session, ":info helper")
    info = capsys.readouterr().out
    assert "restriction: omitted" in info
    assert "inferred effects: (calls-workflow(el1/inspect::target))" in info
    _dispatch(session, ":info forward")
    assert "effect status: incomplete (hook)" in capsys.readouterr().out
    _dispatch(session, ":info seven")
    assert "effect status: complete" in capsys.readouterr().out
    for name in ("ignored", "concrete-alias"):
        _dispatch(session, f":info {name}")
        assert "effect status: complete" in capsys.readouterr().out
    _dispatch(session, ":info pending-alias")
    assert "effect status: incomplete (selected)" in capsys.readouterr().out
    _dispatch(session, ":type (ignored (workflow-ref boxed))")
    ignored = capsys.readouterr().out
    assert "effects: (calls-workflow(el1/inspect::target))" in ignored
    assert "incomplete" not in ignored
    _dispatch(session, ":type (helper)")
    assert "effects: (calls-workflow(el1/inspect::target))" in capsys.readouterr().out
    _dispatch(session, ":type (forward (proc-ref helper))")
    assert "effects: incomplete" in capsys.readouterr().out
    _dispatch(session, ":type (invoke (workflow-ref boxed))")
    unmaterialized = capsys.readouterr().out
    assert "effects: incomplete (runner)" in unmaterialized
    assert "effects: ()" not in unmaterialized

    result = compile_stage3_entrypoint(path, entry_workflow="run", source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries={})
    index = build_navigation_index(result, frozen_form_completions=())
    completions = {item.label: item.detail for _, rows in index.completions_by_path for item in rows}
    assert "restriction: omitted" in completions["helper"]
    assert "inferred effects: (calls-workflow(el1/inspect::target))" in completions["helper"]
    assert "effect status: incomplete (hook)" in completions["forward"]
    assert "effect status: complete" in completions["seven"]
    assert "effect status: complete" in completions["ignored"]
    assert "effect status: complete" in completions["concrete-alias"]
    assert "effect status: incomplete (selected)" in completions["pending-alias"]


@pytest.mark.parametrize("selected", ["allowed", "other"])
def test_named_workflow_ceiling_waits_for_unknown_formal_then_checks_binding(tmp_path, selected):
    declarations = '''(defrecord Box (n Int))
      (defworkflow allowed ((n Int)) -> Box (record Box :n n))
      (defworkflow other ((n Int)) -> Box (record Box :n n))
      (defproc invoke ((runner WorkflowRef[Int -> Box])) -> Box
        :effects ((calls-workflow allowed)) (call runner :n 7))
      (defproc helper () -> Int
        (let* ((box (invoke (workflow-ref SELECTED)))) box.n))'''.replace("SELECTED", selected)
    if selected == "allowed":
        assert build_closed_program(_compile(tmp_path, declarations))
    else:
        with pytest.raises(LispFrontendCompileError) as caught:
            _compile(tmp_path, declarations)
        assert caught.value.diagnostics[0].code == "procedure_effect_ceiling_exceeded"
        assert "el1/entry::other" in caught.value.diagnostics[0].message


def test_restricted_wrapper_checks_effectful_generated_hook(tmp_path):
    with pytest.raises(LispFrontendCompileError) as caught:
        _compile(tmp_path, '''(defproc apply ((hook ProcRef[() -> Int])) -> Int (hook))
          (defproc helper () -> Int :effects ()
            (let-proc (local () -> Int :captures ()
              (command-result probe :argv ("python" "probe.py") :returns Int))
              (apply (proc-ref local))))''')
    assert caught.value.diagnostics[0].code == "procedure_effect_ceiling_exceeded"


def test_public_omitted_generic_wrapper_runs_and_completed_resume_reuses_result(tmp_path):
    import json
    from tests.workflow_evaluated_totality_helpers import checked_run
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_resume import _resume_cli

    source = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule el1/runtime) (export run)
      (defproc leaf () -> Int
        (command-result probe :argv ("python" "probe.py") :returns Int))
      (defproc forward ((hook ProcRef[() -> Int])) -> Int (hook))
      (defworkflow run () -> Int (forward (proc-ref leaf))))''')
    (tmp_path / "probe.py").write_text('''import os
from pathlib import Path
with open("calls.log", "a") as log: log.write("called\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("7")
''', encoding="utf-8")
    commands = tmp_path / "commands.json"
    commands.write_text(json.dumps({"probe": {"kind": "external_tool",
        "stable_command": ["python", "probe.py"], "closure": ["probe.py"]}}))
    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(commands))
    assert result.returncode == 0, result.stderr
    run_root, = (tmp_path / ".orchestrate/runs").iterdir()
    authority, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["value"] == 7
    assert len(snapshot.active_commits) == 1
    before = (run_root / "memo.jsonl").read_bytes()
    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == before
    assert (tmp_path / "calls.log").read_text().splitlines() == ["called"]


def test_public_ordinary_workflow_call_keeps_frame_and_completed_resume_reuses_result(
    tmp_path,
):
    import json

    from tests.workflow_evaluated_totality_helpers import checked_run
    from tests.test_workflow_evaluated_cli import _run_cli
    from tests.test_workflow_evaluated_resume import _resume_cli

    typed = _compile(
        tmp_path,
        '''(defworkflow worker () -> Int
             (command-result probe :argv ("python" "probe.py") :returns Int))
           (defproc wrapper () -> Int (call worker))''',
        "(wrapper)",
    )
    wrapper = typed.procedures["el1/entry::wrapper"]
    assert CallsWorkflowEffect(subject=("el1/entry::worker",)) in (
        wrapper.transitive_effect_summary.transitive_effects
    )
    closed = build_closed_program(typed)

    def closed_nodes(value):
        if isinstance(value, dict):
            yield value
            for child in value.values():
                yield from closed_nodes(child)
        elif isinstance(value, list):
            for child in value:
                yield from closed_nodes(child)

    assert "workflow:el1/entry::worker" in closed.tree["definitions"]
    assert any(
        node.get("k") == "call" and node.get("callee") == "workflow:el1/entry::worker"
        for node in closed_nodes(closed.tree)
    )
    source = tmp_path / "el1" / "entry.orc"
    (tmp_path / "probe.py").write_text(
        '''import os
from pathlib import Path
with open("calls.log", "a") as log: log.write("called\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("7")
''',
        encoding="utf-8",
    )
    commands = tmp_path / "commands.json"
    commands.write_text(
        json.dumps(
            {
                "probe": {
                    "kind": "external_tool",
                    "stable_command": ["python", "probe.py"],
                    "closure": ["probe.py"],
                }
            }
        )
    )
    result = _run_cli(tmp_path, str(source), "--command-boundaries-file", str(commands))
    assert result.returncode == 0, result.stderr
    run_root, = (tmp_path / ".orchestrate/runs").iterdir()
    _, snapshot = checked_run(tmp_path)
    assert snapshot.terminal.data["value"] == 7
    before = (run_root / "memo.jsonl").read_bytes()

    resumed = _resume_cli(tmp_path, run_root.name)
    assert resumed.returncode == 0, resumed.stderr
    assert (run_root / "memo.jsonl").read_bytes() == before
    assert (tmp_path / "calls.log").read_text().splitlines() == ["called"]
