from __future__ import annotations

import importlib
from dataclasses import fields, replace
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.definitions import EnumDef, RecordDef
from orchestrator.workflow_lisp.procedures import GeneratedLocalProcedure
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import SyntaxIdentifier, SyntaxList
from orchestrator.workflow_lisp.type_env import render_type_ref


FIXTURE_ROOT = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
    / "modules"
    / "valid"
    / "lsp_l1_symbols"
)
ENTRYPOINT = FIXTURE_ROOT / "lsp_l1_symbols" / "entry.orc"


@pytest.fixture(scope="module")
def compiled_fixture():
    linked = compile_stage3_entrypoint(
        ENTRYPOINT,
        source_roots=(FIXTURE_ROOT,),
        validate_shared=False,
        workspace_root=FIXTURE_ROOT,
        lowering_route="legacy",
    )
    source = linked.graph.modules_by_name[linked.graph.entry_module_name]
    return ENTRYPOINT.read_text(encoding="utf-8"), source, linked.entry_result


def _projection_module():
    return importlib.import_module("orchestrator.workflow_lisp.authored_symbols")


def _project(source, compiled_result):
    return _projection_module().project_authored_symbols(source, compiled_result)


def _replace_name_span(source, replacement_span: SourceSpan):
    first_form = source.syntax_module.forms[0]
    datum = first_form.datum
    assert isinstance(datum, SyntaxList)
    name = datum.items[1]
    assert isinstance(name, SyntaxIdentifier)
    changed_name = replace(name, span=replacement_span)
    changed_form = replace(
        first_form,
        datum=replace(
            datum,
            items=(datum.items[0], changed_name, *datum.items[2:]),
        ),
    )
    syntax_module = replace(
        source.syntax_module,
        forms=(changed_form, *source.syntax_module.forms[1:]),
    )
    return replace(source, syntax_module=syntax_module)


def test_projection_emits_all_ten_direct_kinds_with_exact_name_spans(
    compiled_fixture,
) -> None:
    text, source, compiled_result = compiled_fixture

    rows = _project(source, compiled_result)

    assert [row.kind for row in rows] == [
        "module",
        "enum",
        "path",
        "schema",
        "record",
        "union",
        "resource",
        "transition",
        "procedure",
        "procedure",
        "procedure",
        "workflow",
        "workflow",
        "workflow",
    ]
    assert [row.source_ordinal for row in rows] == list(range(14))
    assert {field.name for field in fields(rows[0])} == {
        "kind",
        "name",
        "definition_span",
        "selection_span",
        "source_ordinal",
    }
    expected_definition_spans = (
        source.syntax_module.module_directive.span,
        *(form.span for form in source.syntax_module.forms),
    )
    expected_selection_spans = (
        source.syntax_module.module_directive.name_span,
        *(
            form.datum.items[1].span
            for form in source.syntax_module.forms
            if isinstance(form.datum, SyntaxList)
            and isinstance(form.datum.items[1], SyntaxIdentifier)
        ),
    )
    expected_definition_text = (
        "(defmodule lsp_l1_symbols/entry)",
        "(defenum ReviewDecision\n"
        "    APPROVE\n"
        "    REVISE)",
        "(defpath ReportPath\n"
        "    :kind relpath\n"
        '    :under "artifacts/work"\n'
        "    :must-exist false)",
        "(defschema CommonFields\n"
        "    (status String))",
        "(defrecord ReviewState\n"
        "    (status String))",
        "(defunion ReviewOutcome\n"
        "    (DONE\n"
        "      (status String)))",
        "(defresource review-state\n"
        "    :state-type ReviewState\n"
        "    :backing state-layout)",
        "(deftransition record-review\n"
        "    :resource review-state\n"
        "    :request-type ReviewState\n"
        "    :result-type ReviewState\n"
        '    :preconditions ((!= request.status ""))\n'
        "    :updates ((set-field status request.status))\n"
        "    :write-set (status)\n"
        "    :idempotency-fields (status)\n"
        "    :result (record ReviewState\n"
        "      :status request.status)\n"
        "    :audit (record ReviewState\n"
        "      :status request.status)\n"
        "    :conflict-policy fail_closed\n"
        "    :backend runtime_native)",
        "(defproc default-status\n"
        "    ()\n"
        "    -> String\n"
        "    :effects ()\n"
        "    :lowering inline\n"
        '    "ready")',
        "(defproc normalize-status\n"
        "    ((status String))\n"
        "    -> String\n"
        "    :effects ()\n"
        "    :lowering inline\n"
        "    status)",
        "(defproc render-and-preserve\n"
        "    ((reports List[Optional[Map[String, ReportPath]]])\n"
        "     (status String)\n"
        "     (target ReportPath))\n"
        "    -> List[Optional[Map[String, ReportPath]]]\n"
        "    :effects ((writes status-view))\n"
        "    :lowering inline\n"
        "    (let* ((rendered\n"
        "             (materialize-view status-view\n"
        "               :value (record ReviewState\n"
        "                        :status status)\n"
        "               :renderer canonical-json\n"
        "               :renderer-version 1\n"
        "               :target target\n"
        "               :returns ReportPath)))\n"
        "      reports))",
        "(defworkflow default-review\n"
        "    ()\n"
        "    -> ReviewState\n"
        "    (loop/recur\n"
        "      :max 1\n"
        "      :state (record ReviewState\n"
        '               :status "ready")\n'
        "      (fn (state)\n"
        "        (done state))))",
        "(defworkflow review\n"
        "    ((status String))\n"
        "    -> String\n"
        "    (normalize-status status))",
        "(defworkflow review-many\n"
        "    ((primary String)\n"
        "     (secondary String)\n"
        "     (fallback String))\n"
        "    -> String\n"
        "    (normalize-status primary))",
    )
    for row, definition_span, selection_span, definition_text in zip(
        rows,
        expected_definition_spans,
        expected_selection_spans,
        expected_definition_text,
        strict=True,
    ):
        assert row.definition_span == definition_span
        assert row.selection_span == selection_span
        assert text[
            row.definition_span.start.offset : row.definition_span.end.offset
        ] == definition_text
        assert (
            text[row.selection_span.start.offset : row.selection_span.end.offset]
            == row.name
        )


@pytest.mark.parametrize(
    "mismatch",
    ["missing", "duplicate", "kind", "name", "full_span"],
)
def test_projection_fails_closed_on_compiled_crosscheck_mismatch(
    compiled_fixture,
    mismatch: str,
) -> None:
    _, source, compiled_result = compiled_fixture
    module = compiled_result.module
    procedure_catalog = compiled_result.procedure_catalog

    if mismatch == "missing":
        module = replace(
            module,
            definitions=tuple(
                definition
                for definition in module.definitions
                if definition.name != "ReviewOutcome"
            ),
        )
    elif mismatch == "duplicate":
        procedure = next(iter(procedure_catalog.definitions_by_name.values()))
        procedure_catalog = replace(
            procedure_catalog,
            definitions_by_name={
                **procedure_catalog.definitions_by_name,
                "duplicate-key": procedure,
            },
        )
    elif mismatch == "kind":
        enum = next(
            definition
            for definition in module.definitions
            if isinstance(definition, EnumDef)
        )
        wrong_kind = RecordDef(name=enum.name, fields=(), span=enum.span)
        module = replace(
            module,
            definitions=tuple(
                wrong_kind if definition is enum else definition
                for definition in module.definitions
            ),
        )
    elif mismatch == "name":
        enum = next(
            definition
            for definition in module.definitions
            if isinstance(definition, EnumDef)
        )
        module = replace(
            module,
            definitions=tuple(
                replace(enum, name="DifferentDecision")
                if definition is enum
                else definition
                for definition in module.definitions
            ),
        )
    else:
        path = next(
            definition
            for definition in module.definitions
            if definition.name == "ReportPath"
        )
        shifted = replace(
            path.span,
            end=replace(path.span.end, offset=path.span.end.offset - 1),
        )
        module = replace(
            module,
            definitions=tuple(
                replace(path, span=shifted) if definition is path else definition
                for definition in module.definitions
            ),
        )

    with pytest.raises(_projection_module().AuthoredSymbolProjectionError):
        _project(
            source,
            replace(
                compiled_result,
                module=module,
                procedure_catalog=procedure_catalog,
            ),
        )


def test_projection_fails_closed_on_module_identity_mismatch(compiled_fixture) -> None:
    _, source, compiled_result = compiled_fixture
    compiled_result = replace(
        compiled_result,
        module=replace(compiled_result.module, module_name="different/module"),
    )

    with pytest.raises(_projection_module().AuthoredSymbolProjectionError):
        _project(source, compiled_result)


@pytest.mark.parametrize("kind", ["procedure", "workflow"])
def test_projection_rejects_wrong_module_canonical_callable(
    compiled_fixture,
    kind: str,
) -> None:
    _, source, compiled_result = compiled_fixture
    catalog = (
        compiled_result.procedure_catalog
        if kind == "procedure"
        else compiled_result.workflow_catalog
    )
    definition = next(iter(catalog.definitions_by_name.values()))
    local_name = definition.name.rsplit("::", 1)[-1]
    wrong_module_definition = replace(
        definition,
        name=f"wrong/module::{local_name}",
    )
    changed_catalog = replace(
        catalog,
        definitions_by_name={
            key: (
                wrong_module_definition
                if candidate is definition
                else candidate
            )
            for key, candidate in catalog.definitions_by_name.items()
        },
    )
    changed_result = replace(
        compiled_result,
        procedure_catalog=(
            changed_catalog
            if kind == "procedure"
            else compiled_result.procedure_catalog
        ),
        workflow_catalog=(
            changed_catalog
            if kind == "workflow"
            else compiled_result.workflow_catalog
        ),
    )

    with pytest.raises(_projection_module().AuthoredSymbolProjectionError):
        _project(source, changed_result)


def test_fixture_covers_callable_signature_diversity(compiled_fixture) -> None:
    _, _, compiled_result = compiled_fixture
    procedure_signatures = tuple(
        procedure.signature for procedure in compiled_result.typed_procedures
    )
    workflow_signatures = tuple(
        workflow.signature for workflow in compiled_result.typed_workflows
    )

    assert sorted(len(signature.params) for signature in procedure_signatures) == [
        0,
        1,
        3,
    ]
    assert sorted(len(signature.params) for signature in workflow_signatures) == [
        0,
        1,
        3,
    ]
    rendered_callable_types = {
        render_type_ref(type_ref)
        for signature in (*procedure_signatures, *workflow_signatures)
        for _, type_ref in signature.params
    } | {
        render_type_ref(signature.return_type_ref)
        for signature in (*procedure_signatures, *workflow_signatures)
    }
    assert "List[Optional[Map[String, ReportPath]]]" in rendered_callable_types
    assert {
        bool(signature.declared_effects)
        for signature in procedure_signatures
    } == {False, True}


@pytest.mark.parametrize(
    "invalid_span",
    ["wrong_path", "zero", "negative", "reversed", "outside"],
)
def test_projection_fails_closed_on_invalid_selection_span(
    compiled_fixture,
    invalid_span: str,
) -> None:
    _, source, compiled_result = compiled_fixture
    definition_span = source.syntax_module.forms[0].span
    datum = source.syntax_module.forms[0].datum
    assert isinstance(datum, SyntaxList)
    name = datum.items[1]
    assert isinstance(name, SyntaxIdentifier)
    span = name.span

    if invalid_span == "wrong_path":
        replacement = replace(
            span,
            start=replace(span.start, path="different.orc"),
            end=replace(span.end, path="different.orc"),
        )
    elif invalid_span == "zero":
        replacement = replace(span, end=span.start)
    elif invalid_span == "negative":
        replacement = SourceSpan(
            start=SourcePosition(
                path=span.start.path,
                line=0,
                column=0,
                offset=-1,
            ),
            end=span.end,
        )
    elif invalid_span == "reversed":
        replacement = SourceSpan(start=span.end, end=span.start)
    else:
        replacement = SourceSpan(
            start=definition_span.end,
            end=replace(
                definition_span.end,
                column=definition_span.end.column + 1,
                offset=definition_span.end.offset + 1,
            ),
        )

    with pytest.raises(_projection_module().AuthoredSymbolProjectionError):
        _project(_replace_name_span(source, replacement), compiled_result)


def test_projection_ignores_compiled_only_generated_and_specialized_shapes(
    compiled_fixture,
) -> None:
    _, source, compiled_result = compiled_fixture
    baseline = _project(source, compiled_result)
    enum = next(
        definition
        for definition in compiled_result.module.definitions
        if isinstance(definition, EnumDef)
    )
    procedure = next(
        iter(compiled_result.procedure_catalog.definitions_by_name.values())
    )
    workflow = next(
        iter(compiled_result.workflow_catalog.definitions_by_name.values())
    )
    generated_local = GeneratedLocalProcedure(
        authored_local_name="hidden",
        generated_name="%hidden",
        owner_callable_name=procedure.name,
        residual_params=(),
        return_type_name="String",
        capture_names=(),
        origin_span=procedure.span,
    )
    expanded_enum = replace(enum, name="ExpansionOnly")
    specialized_procedure = replace(procedure)
    generated_procedure = replace(
        procedure,
        generated_local_procedure=generated_local,
    )
    specialized_workflow = replace(workflow)
    typed_procedure = next(
        row
        for row in compiled_result.typed_procedures
        if row.definition is procedure
    )
    typed_workflow = next(
        row
        for row in compiled_result.typed_workflows
        if row.definition is workflow
    )
    specialized_typed_procedure = replace(
        typed_procedure,
        definition=specialized_procedure,
        specialization=object(),
    )
    specialized_typed_workflow = replace(
        typed_workflow,
        definition=specialized_workflow,
        specialization=object(),
    )
    compiled_result = replace(
        compiled_result,
        module=replace(
            compiled_result.module,
            definitions=(*compiled_result.module.definitions, expanded_enum),
        ),
        procedure_catalog=replace(
            compiled_result.procedure_catalog,
            definitions_by_name={
                **compiled_result.procedure_catalog.definitions_by_name,
                "specialized-alias": specialized_procedure,
                "generated-local-alias": generated_procedure,
            },
        ),
        workflow_catalog=replace(
            compiled_result.workflow_catalog,
            definitions_by_name={
                **compiled_result.workflow_catalog.definitions_by_name,
                "specialized-alias": specialized_workflow,
            },
        ),
        typed_procedures=(
            *compiled_result.typed_procedures,
            specialized_typed_procedure,
        ),
        typed_workflows=(
            *compiled_result.typed_workflows,
            specialized_typed_workflow,
        ),
    )

    assert _project(source, compiled_result) == baseline
