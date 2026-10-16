from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp import compiler as workflow_lisp_compiler
from orchestrator.workflow_lisp import expressions, repl_expr, syntax
from orchestrator.workflow_lisp.compiler import (
    compile_stage3_entrypoint,
    linked_module_type_environment,
)
from orchestrator.workflow_lisp.compiler_session import CompilerSession
from orchestrator.workflow_lisp.effects import UsesProviderEffect
from orchestrator.workflow_lisp.reader import SourceReadTrace, read_sexpr_text
from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef, RecordTypeRef
from orchestrator.workflow_lisp.typecheck_dispatch import typecheck_expression
from orchestrator.workflow_lisp.workflows import PromptExtern, ProviderExtern


def _fixture_sources(target: str) -> dict[str, dict[tuple[str, str], str]]:
    types = {
        ("defenum", "Status"): "(defenum Status READY BLOCKED)",
        ("defrecord", "Plan"): "(defrecord Plan (title String) (status Status))",
        ("defun", "hidden-fn"): "(defun hidden-fn ((plan Plan)) -> String plan.title)",
        ("defproc", "hidden-proc"): (
            "(defproc hidden-proc ((plan Plan)) -> Plan :effects () :lowering inline plan)"
        ),
        ("defworkflow", "unused-flow"): "(defworkflow unused-flow ((plan Plan)) -> Plan plan)",
        ("defprompt", "typed-prompt"): (
            '(defprompt typed-prompt (:fills (subject :text)) -> Plan "{subject}")'
        ),
    }
    entry = {
        ("defrecord", "LocalPlan"): "(defrecord LocalPlan (count Int))",
        ("defenum", "LocalStatus"): "(defenum LocalStatus NEW DONE)",
        ("defrecord", "Collision"): "(defrecord Collision (value String))",
        ("defun", "Collision"): "(defun Collision ((value String)) -> String value)",
        ("defworkflow", "run"): (
            "(defworkflow run ((plan Plan)) -> Plan\n"
            "  (provider-result providers.review :prompt prompts.external :inputs () :returns Plan))"
        ),
        ("defproc", "effectful-proc"): (
            "(defproc effectful-proc ((plan Plan)) -> Plan "
            ":effects ((uses-provider providers.review)) :lowering inline "
            "(provider-result providers.review :prompt prompts.external :inputs () :returns Plan))"
        ),
    }
    return {"proof/types": types, "proof/entry": entry}


def _module_text(
    module_name: str,
    target: str,
    forms: dict[tuple[str, str], str],
) -> str:
    header = [
        "(workflow-lisp",
        '  (:language "0.1")',
        f'  (:target-dsl "{target}")',
        f"  (defmodule {module_name})",
    ]
    if module_name == "proof/entry":
        header.extend(("  (import proof/types :as types :only (Plan))", "  (export run)"))
    else:
        header.append(
            "  (export Status Plan hidden-fn hidden-proc unused-flow typed-prompt)"
        )
    return "\n".join((*header, "  ; fixture source café", *(f"  {form}" for form in forms.values()), ")", ""))


def _form_for(source, head: str, name: str):
    return next(
        form
        for form in source.syntax_module.forms
        if form.form_path[-2:] == (head, name)
    )


def _normalize_newlines(source: str) -> str:
    return source.replace("\r\n", "\n").replace("\r", "\n")


@pytest.mark.parametrize("target", ["2.35", "2.36"])
def test_existing_introspection_substrate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
) -> None:
    source_root = tmp_path / "src"
    type_forms = _fixture_sources(target)["proof/types"]
    entry_forms = _fixture_sources(target)["proof/entry"]
    expected_forms = {"proof/types": type_forms, "proof/entry": entry_forms}
    authored_text = {
        "proof/types": _module_text("proof/types", target, type_forms),
        "proof/entry": _module_text("proof/entry", target, entry_forms),
    }
    source_paths = {
        module: source_root.joinpath(*module.split("/")).with_suffix(".orc")
        for module in authored_text
    }
    payloads = {}
    for module, text in authored_text.items():
        source_paths[module].parent.mkdir(parents=True, exist_ok=True)
        newline = "\r\n" if module == "proof/types" else "\r"
        payloads[module] = text.replace("\n", newline).encode("utf-8")
        source_paths[module].write_bytes(payloads[module])

    def unexpected_boundary(*_args, **_kwargs):
        pytest.fail("ordinary effect typechecking crossed a lowering/evaluation boundary")

    monkeypatch.setattr(repl_expr, "evaluate_closed_value", unexpected_boundary)
    trace = SourceReadTrace()
    compiled = compile_stage3_entrypoint(
        source_paths["proof/entry"],
        source_roots=(source_root,),
        provider_externs={"providers.review": "fixture-review"},
        prompt_externs={"prompts.external": PromptExtern(name="prompts.external", asset_file="unused.md")},
        validation_profile="frontend_only",

        workspace_root=tmp_path,
        source_read_trace=trace,
    )

    assert compiled.graph.topological_order == ("proof/types", "proof/entry")
    assert set(compiled.graph.modules_by_name) == set(authored_text)
    assert not (tmp_path / ".orchestrate").exists()
    assert set(trace.raw_bytes_by_path) == {path.resolve() for path in source_paths.values()}
    assert {path for path, _revision in trace.revision_vector} == set(trace.raw_bytes_by_path)

    for module, forms in expected_forms.items():
        source = compiled.graph.modules_by_name[module]
        snapshot = _normalize_newlines(trace.raw_bytes_by_path[source.path.resolve()].decode("utf-8"))
        for (head, name), expected_form in forms.items():
            form = _form_for(source, head, name)
            assert form.span.start.path == str(source.path)
            assert snapshot[form.span.start.offset:form.span.end.offset] == expected_form

    entry_result = compiled.entry_result
    context = entry_result.expression_context
    assert context is not None
    import_span = _form_for(compiled.graph.modules_by_name["proof/entry"], "defworkflow", "run").span
    form_path = ("workflow-lisp", "repl-introspection")
    assert context.function_name_resolver("types.hidden-fn", import_span, form_path) == "proof/types::hidden-fn"
    assert "proof/types::hidden-fn" in context.function_catalog.signatures_by_name
    assert "proof/types::hidden-proc" in entry_result.procedure_catalog.signatures_by_name
    assert "proof/types::unused-flow" in entry_result.workflow_catalog.signatures_by_name
    prompt = entry_result.prompt_catalog.resolve("types.typed-prompt")
    assert prompt is not None
    assert prompt.qualified_name == "proof/types::typed-prompt"
    assert tuple(slot.declaration.name for slot in prompt.slots) == ("subject",)
    assert isinstance(entry_result.extern_environment.bindings_by_name["providers.review"], ProviderExtern)
    assert isinstance(entry_result.extern_environment.bindings_by_name["prompts.external"], PromptExtern)

    type_env = linked_module_type_environment(compiled, "proof/entry")
    local_span = _form_for(compiled.graph.modules_by_name["proof/entry"], "defrecord", "LocalPlan").span
    local_path = ("workflow-lisp", "defrecord", "LocalPlan")
    imported_plan = type_env.resolve_type("Plan", span=local_span, form_path=local_path)
    imported_status = type_env.resolve_type("types.Status", span=local_span, form_path=local_path)
    local_plan = type_env.resolve_type("LocalPlan", span=local_span, form_path=local_path)
    local_status = type_env.resolve_type("LocalStatus", span=local_span, form_path=local_path)
    assert isinstance(imported_plan, RecordTypeRef)
    assert imported_plan.name == "proof/types::Plan"
    assert imported_plan.field_types["title"].name == "String"
    assert imported_status.name == "proof/types::Status"
    assert imported_status.allowed_values == ("READY", "BLOCKED")
    assert type_env.declaring_module(imported_status) == "proof/types"
    assert isinstance(local_plan, RecordTypeRef)
    assert local_plan.field_types["count"].name == "Int"
    assert local_status.allowed_values == ("NEW", "DONE")
    assert type_env.declaring_module(local_status) == "proof/entry"

    collision_span = _form_for(compiled.graph.modules_by_name["proof/entry"], "defrecord", "Collision").span
    collision_type = type_env.resolve_type(
        "Collision", span=collision_span, form_path=("workflow-lisp", "defrecord", "Collision")
    )
    assert isinstance(collision_type, RecordTypeRef)
    assert "proof/entry::Collision" in context.function_catalog.signatures_by_name

    parsed = read_sexpr_text(
        "(provider-result providers.review :prompt prompts.external :inputs () :returns Plan)",
        source_path="<effectful-typecheck>",
    )
    datum = parsed.items[0]
    node = syntax.SyntaxNode(datum, datum.span, "<effectful-typecheck>", form_path)
    session = CompilerSession()
    extern_names = frozenset(entry_result.extern_environment.bindings_by_name)
    expression = expressions.elaborate_expression(
        node,
        bound_names=frozenset(),
        extern_names=extern_names,
        procedure_names=frozenset(entry_result.procedure_catalog.signatures_by_name),
        function_names=frozenset(context.function_catalog.signatures_by_name),
        function_name_resolver=context.function_name_resolver,
        procedure_name_resolver=context.procedure_name_resolver,
        workflow_name_resolver=context.workflow_name_resolver,
        target_dsl_version=target,
        prompt_catalog=entry_result.prompt_catalog,
        session_state=session.elaboration,
    )
    typed = typecheck_expression(
        expression,
        type_env=type_env,
        value_env={
            name: PrimitiveTypeRef("Provider" if isinstance(binding, ProviderExtern) else "Prompt")
            for name, binding in entry_result.extern_environment.bindings_by_name.items()
        },
        workflow_catalog=entry_result.workflow_catalog,
        procedure_catalog=entry_result.procedure_catalog,
        function_catalog=context.function_catalog,
        extern_environment=entry_result.extern_environment,
        command_boundary_environment=entry_result.command_boundary_environment,
        prompt_catalog=entry_result.prompt_catalog,
        compiler_session=session,
    )
    assert typed.type_ref.name == "proof/types::Plan"
    assert typed.effect_summary.transitive_effects == frozenset(
        {UsesProviderEffect(subject=("providers", "review"))}
    )


@pytest.fixture(params=["2.35", "2.36"])
def loaded_catalog(tmp_path, request):
    import json
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
    forms = _fixture_sources(request.param)
    forms["proof/types"][("defrecord", "PrivateType")] = "(defrecord PrivateType (value String))"
    forms["proof/types"][("defprompt", "private-prompt")] = '(defprompt private-prompt (:fills (subject :text)) -> Bool "{subject}")'
    forms["proof/types"][("defprompt", "typed-prompt")] = '(defprompt typed-prompt (:fills (subject :text)) -> Plan "café {subject}\\n")'
    forms["proof/types"][("defun", "private-fn")] = "(defun private-fn ((value String)) -> String value)"
    forms["proof/entry"][("defunion", "Outcome")] = "(defunion Outcome :forall (T E) (OK (value T)) (ERR (error E)))"
    forms["proof/entry"][("defpath", "ReportPath")] = '(defpath ReportPath :kind relpath :under "reports" :must-exist false)'
    forms["proof/entry"][("defprompt", "contract-prompt")] = ('(defprompt contract-prompt (:fills (message :text) (score :value Int) (report :path :out ReportPath)) -> Bool "{message} {score} {report}")')
    paths = {}
    for name, definitions in forms.items():
        path = tmp_path.joinpath("src", *name.split("/")).with_suffix(".orc")
        path.parent.mkdir(parents=True, exist_ok=True)
        text = _module_text(name, request.param, definitions)
        if name == "proof/entry":
            text = text.replace(forms[name][("defrecord", "LocalPlan")] + "\n  ", forms[name][("defrecord", "LocalPlan")] + " ")
        path.write_bytes(text.replace("\n", "\r\n" if name == "proof/types" else "\r").encode())
        paths[name] = path
    providers, prompts = tmp_path / "providers.json", tmp_path / "prompts.json"
    providers.write_text(json.dumps({"providers.review": "fixture-secret-provider"}))
    prompts.write_text(json.dumps({"prompts.external": {"asset_file": "secret-not-read.md"}}))
    trace = SourceReadTrace()
    build = prepare_closed_program_bundle(FrontendBuildRequest(
        source_path=paths["proof/entry"], source_roots=(tmp_path / "src",),
        provider_externs_path=providers, prompt_externs_path=prompts,
        workspace_root=tmp_path,
    ), source_read_trace=trace)
    return repl_expr.LoadedModule(
        build, paths["proof/entry"], source_snapshots=trace.raw_bytes_by_path,
        source_revisions=trace.revision_vector,
    ), forms, paths


def test_catalog_retains_production_context_and_visible_names(loaded_catalog):
    from orchestrator.workflow_lisp import repl_inspect
    module, _forms, paths = loaded_catalog
    context = module.stage3.expression_context
    assert context.linked_module_graph.entry_module_name == "proof/entry"
    assert context.module_import_scope.alias_to_module == {"types": "proof/types"}
    rows = repl_inspect.visible_declarations(module)
    plan = [row for row in rows if row.canonical_name == "proof/types::Plan"]
    assert len(plan) == 1
    assert set(plan[0].names) == {"Plan", "types.Plan", "proof/types/Plan", "proof/types::Plan"}
    assert {row.kind for row in rows} >= {"record", "enum", "union", "path", "builtin", "function", "procedure", "workflow", "prompt", "extern"}
    assert not any("private-fn" in name for row in rows for name in row.names)
    assert rows == tuple(sorted(rows, key=lambda row: (row.kind, row.names)))
    for row in rows:
        for name in row.names:
            assert name in repl_inspect.inspect_name(module, name)
    assert "title: String" in repl_inspect.inspect_name(module, "Plan")
    assert "READY" in repl_inspect.inspect_name(module, "types.Status")
    assert "OK" in repl_inspect.inspect_name(module, "Outcome")
    assert "under: reports" in repl_inspect.inspect_name(module, "ReportPath")
    collision = repl_inspect.inspect_name(module, "Collision")
    assert "record" in collision and "function" in collision
    prompt = repl_inspect.inspect_name(module, "types.typed-prompt")
    assert "subject" in prompt and "text" in prompt and "Plan" in prompt
    extern = repl_inspect.inspect_name(module, "providers.review")
    assert "Provider" in extern and "fixture-secret-provider" not in extern
    assert "secret-not-read" not in repl_inspect.inspect_name(module, "prompts.external")
    assert "proof/entry" in repl_inspect.browse_module(module)
    assert not paths["proof/entry"].parents[2].joinpath(".orchestrate").exists()
    for name in ("private-fn", "types.PrivateType", "types.private-prompt", "proof/types::PrivateType", "proof/unloaded/Plan"):
        with pytest.raises(repl_expr.ReplRefusal) as error:
            repl_inspect.inspect_name(module, name)
        assert error.value.code == "repl_name_unknown"


def test_source_snapshot_preserves_authored_forms_after_delete(loaded_catalog, monkeypatch):
    from orchestrator.workflow_lisp import repl_inspect
    module, forms, paths = loaded_catalog
    for path in paths.values():
        path.unlink()
    def unexpected_io(*args, **kwargs):
        pytest.fail("inspection attempted filesystem IO")
    with monkeypatch.context() as guard:
        guard.setattr(Path, "resolve", unexpected_io)
        guard.setattr(Path, "stat", unexpected_io)
        guard.setattr(Path, "read_bytes", unexpected_io)
        for name in ("Plan", "types.Status", "types.hidden-fn", "types.hidden-proc", "types.unused-flow", "types.typed-prompt", "LocalPlan", "LocalStatus", "Collision", "Outcome", "ReportPath"):
            text = repl_inspect.source_name(module, name)
            assert "loaded snapshot" in text and "sha256:" in text
            matching = [form for declarations in forms.values() for (head, member), form in declarations.items() if member == name.rsplit(".", 1)[-1]]
            assert matching
            for form in matching:
                assert form in text
        for name in ("String", "providers.review", "prompts.external"):
            with pytest.raises(repl_expr.ReplRefusal) as error:
                repl_inspect.source_name(module, name)
            assert error.value.code == "repl_source_unavailable"
        module.source_origin = "reconstructed"
        assert "reconstructed module source" in repl_inspect.source_name(module, "Plan")


def test_source_snapshot_refuses_missing_or_corrupt_facts(loaded_catalog):
    from dataclasses import replace
    from orchestrator.workflow_lisp import repl_inspect
    module, _forms, paths = loaded_catalog
    for snapshots in ({}, {path: b"corrupt" for path in module.source_snapshots}):
        module.source_snapshots = snapshots
        with pytest.raises(repl_expr.ReplRefusal) as error:
            repl_inspect.source_name(module, "Collision")
        assert error.value.code == "repl_source_unavailable"
        assert "function" in str(error.value) and "record" in str(error.value)
    module.stage3 = replace(module.stage3, expression_context=None)
    with pytest.raises(repl_expr.ReplRefusal) as error:
        repl_inspect.browse_module(module)
    assert error.value.code == "repl_module_context_missing"


def test_catalog_prompt_contracts_preserve_order_and_refinements(loaded_catalog):
    from orchestrator.workflow_lisp import repl_inspect
    module, _, _ = loaded_catalog
    text = repl_inspect.inspect_name(module, "contract-prompt")
    assert text.index("message: text") < text.index("score: value") < text.index("report: path")
    assert "refinement: Int" in text
    assert "refinement: ReportPath" in text
    assert "output-role: required_string_file" in text
    assert "returns: Bool" in text
    assert "effects: ()" in repl_inspect.inspect_name(module, "types.hidden-fn")
    assert "returns: proof/types::Plan" in repl_inspect.inspect_name(module, "types.hidden-proc")
    assert "type parameters: T, E" in repl_inspect.inspect_name(module, "Outcome")
    assert "value: T" in repl_inspect.inspect_name(module, "Outcome")
    assert "must-exist: false" in repl_inspect.inspect_name(module, "ReportPath")


def test_source_snapshot_refuses_shifted_enum_span(loaded_catalog):
    from dataclasses import replace
    from orchestrator.workflow_lisp import repl_inspect
    module, _, _ = loaded_catalog
    context = module.stage3.expression_context
    graph = context.linked_module_graph
    source = graph.modules_by_name["proof/entry"]
    form = _form_for(source, "defenum", "LocalStatus")
    shifted = replace(form, span=replace(form.span, start=replace(form.span.start, offset=form.span.start.offset + 1)))
    syntax_module = replace(source.syntax_module, forms=tuple(shifted if node is form else node for node in source.syntax_module.forms))
    modules = {**graph.modules_by_name, "proof/entry": replace(source, syntax_module=syntax_module)}
    module.stage3 = replace(module.stage3, expression_context=replace(context, linked_module_graph=replace(graph, modules_by_name=modules)))
    with pytest.raises(repl_expr.ReplRefusal) as error:
        repl_inspect.source_name(module, "LocalStatus")
    assert error.value.code == "repl_source_unavailable"


def test_catalog_omits_generated_specializations(loaded_catalog):
    from dataclasses import replace
    from orchestrator.workflow_lisp import repl_inspect
    module, _, _ = loaded_catalog
    procs = dict(module.typed_program.procedures)
    key = "proof/types::hidden-proc"
    procs[key] = replace(procs[key], specialization=object())
    module.typed_program = replace(module.typed_program, procedures=procs)
    procedures = {
        row.canonical_name
        for row in repl_inspect.visible_declarations(module)
        if row.kind == "procedure"
    }
    assert key not in procedures
    assert "proof/entry::effectful-proc" in procedures


def test_source_snapshot_copies_input_snapshot_mapping(loaded_catalog):
    from orchestrator.workflow_lisp import repl_inspect
    module, _, _ = loaded_catalog
    snapshots = dict(module.source_snapshots)
    copied = repl_expr.LoadedModule(module.build, module.source_path, source_snapshots=snapshots, source_revisions=module.source_revisions)
    snapshots.clear()
    assert "(defrecord Plan" in repl_inspect.source_name(copied, "Plan")


def test_source_snapshot_is_all_or_nothing_across_namespaces(loaded_catalog):
    from dataclasses import replace
    from orchestrator.workflow_lisp import repl_inspect
    module, _, _ = loaded_catalog
    context = module.stage3.expression_context
    graph = context.linked_module_graph
    source = graph.modules_by_name["proof/entry"]
    form = _form_for(source, "defun", "Collision")
    syntax_module = replace(source.syntax_module, forms=tuple(node for node in source.syntax_module.forms if node is not form))
    modules = {**graph.modules_by_name, "proof/entry": replace(source, syntax_module=syntax_module)}
    module.stage3 = replace(module.stage3, expression_context=replace(context, linked_module_graph=replace(graph, modules_by_name=modules)))
    with pytest.raises(repl_expr.ReplRefusal) as error:
        repl_inspect.source_name(module, "Collision")
    assert error.value.code == "repl_source_unavailable"
    assert "function" in str(error.value)
    assert "(defrecord" not in str(error.value)
