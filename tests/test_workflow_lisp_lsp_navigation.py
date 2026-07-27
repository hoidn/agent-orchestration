"""Closed-matrix navigation tests for the Workflow Lisp language server."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from importlib import import_module
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest

from lsprotocol import types

from orchestrator.lsp import compile_driver as lsp_compile_driver
from orchestrator.lsp import state as lsp_state
from orchestrator.lsp.coordinates import source_span_to_lsp_range
from orchestrator.lsp.server import WorkflowLispLanguageServer
from orchestrator.workflow_lisp.compiler import (
    LinkedStage3CompileResult,
    Stage3ValidationProfile,
    compile_stage3_entrypoint,
)
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.effects import WriteEffect, effect_summary
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    LetStarExpr,
    ProcedureCallExpr,
    ProcRefLiteralExpr,
    ProviderResultExpr,
)
from orchestrator.workflow_lisp.prompts import (
    PromptApplicationExpr,
    PromptCatalog,
)
from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
from orchestrator.workflow_lisp.syntax import (
    SyntaxIdentifier,
    SyntaxList,
)
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURES = (
    Path(__file__).parent
    / "fixtures"
    / "workflow_lisp"
)
CALLABLE_ROOT = FIXTURES / "modules" / "valid" / "callables"
CALLABLE_ENTRY = CALLABLE_ROOT / "neurips" / "entry.orc"
CALLABLE_HELPER = CALLABLE_ROOT / "neurips" / "helper.orc"
CALLABLE_PROCEDURES = CALLABLE_ROOT / "neurips" / "procedures.orc"
CALLABLE_TYPES = CALLABLE_ROOT / "neurips" / "types.orc"
L1_SYMBOLS_ROOT = (
    FIXTURES / "modules" / "valid" / "lsp_l1_symbols"
)
L1_SYMBOLS_ENTRY = (
    L1_SYMBOLS_ROOT / "lsp_l1_symbols" / "entry.orc"
)
L5_AUTHORED_REFS_ROOT = (
    FIXTURES / "modules" / "valid" / "lsp_l5_authored_refs"
)
L5_AUTHORED_REFS_ENTRY = (
    L5_AUTHORED_REFS_ROOT / "lsp_l5" / "entry.orc"
)
L5_AUTHORED_REFS_DEFINITIONS = (
    L5_AUTHORED_REFS_ROOT / "lsp_l5" / "definitions.orc"
)
L5_PRIVATE_ROOT = (
    FIXTURES / "modules" / "invalid" / "lsp_l5_private"
)
L5_AMBIGUOUS_ROOT = (
    FIXTURES / "modules" / "invalid" / "ambiguous"
)
REVIEW_REVISE_DESIGN_DOCS = (
    Path(__file__).resolve().parents[1]
    / "workflows"
    / "examples"
    / "review_revise_design_docs.orc"
)
STDLIB_CALLER = FIXTURES / "valid" / "minimal_caller_finalize_selected_item.orc"


def _navigation_surface() -> object:
    try:
        return import_module("orchestrator.lsp.navigation")
    except ModuleNotFoundError:
        pytest.fail("orchestrator.lsp.navigation is not implemented")


def _build_index(
    result: LinkedStage3CompileResult,
    *,
    form_heads: tuple[str, ...] | None = None,
) -> object:
    navigation = _navigation_surface()
    build_index = getattr(navigation, "build_navigation_index", None)
    project = getattr(navigation, "project_form_completion_rows", None)
    assert callable(build_index), "build_navigation_index is missing"
    assert callable(project), "project_form_completion_rows is missing"
    if form_heads is None:
        registry = import_module("orchestrator.workflow_lisp.form_registry")
        registered_form_heads = getattr(
            registry,
            "registered_form_heads",
            None,
        )
        assert callable(
            registered_form_heads
        ), "registered_form_heads is missing"
        form_heads = tuple(
            registered_form_heads(target_dsl_version=None)
        )
    return build_index(
        result,
        frozen_form_completions=project(form_heads),
    )


def test_project_form_completion_rows_accepts_only_exact_frozen_heads() -> None:
    navigation = _navigation_surface()
    project = getattr(navigation, "project_form_completion_rows", None)
    assert callable(project), "project_form_completion_rows is missing"

    rows = project(("defproc", "workflow-lisp"))

    assert isinstance(rows, tuple)
    assert tuple(
        (row.label, row.kind, row.canonical_target, row.detail)
        for row in rows
    ) == (
        ("defproc", "form", "defproc", "form"),
        ("workflow-lisp", "form", "workflow-lisp", "form"),
    )
    with pytest.raises(FrozenInstanceError):
        rows[0].label = "changed"


@pytest.mark.parametrize(
    "heads",
    (
        ["defproc"],
        ("defproc", "defproc"),
        ("workflow-lisp", "defproc"),
        ("",),
        (1,),
    ),
)
def test_project_form_completion_rows_rejects_malformed_catalog(
    heads: object,
) -> None:
    navigation = _navigation_surface()
    project = getattr(navigation, "project_form_completion_rows", None)
    assert callable(project), "project_form_completion_rows is missing"

    with pytest.raises((TypeError, ValueError)):
        project(heads)


def test_build_navigation_index_requires_explicit_frozen_form_rows(
    callable_result: LinkedStage3CompileResult,
) -> None:
    build_index = getattr(_navigation_surface(), "build_navigation_index", None)
    assert callable(build_index), "build_navigation_index is missing"

    with pytest.raises(TypeError):
        build_index(callable_result)


def test_build_navigation_index_reuses_explicit_form_rows_for_every_module(
    callable_result: LinkedStage3CompileResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigation = _navigation_surface()
    project = getattr(navigation, "project_form_completion_rows", None)
    build_index = getattr(navigation, "build_navigation_index", None)
    assert callable(project), "project_form_completion_rows is missing"
    assert callable(build_index), "build_navigation_index is missing"
    frozen_rows = project(("only-frozen-form",))

    def unexpected_registry_read(*args: object, **kwargs: object) -> object:
        pytest.fail("navigation index construction reread the form registry")

    monkeypatch.setattr(
        navigation,
        "registered_form_heads",
        unexpected_registry_read,
        raising=False,
    )

    index = build_index(
        callable_result,
        frozen_form_completions=frozen_rows,
    )

    assert index.completions_by_path
    assert all(
        frozen_rows[0] in completions
        for _path, completions in index.completions_by_path
    )


def _definition_at(
    index: object,
    *,
    source_path: Path,
    line: int,
    character: int,
    accepted_text_by_path: dict[Path, str],
) -> SourceSpan | None:
    lookup = getattr(
        _navigation_surface(),
        "definition_at_lsp_position",
        None,
    )
    assert callable(lookup), "definition_at_lsp_position is missing"
    return lookup(
        index,
        source_path=source_path,
        line=line,
        character=character,
        accepted_text_by_path=accepted_text_by_path,
    )


def _symbols(index: object, source_path: Path) -> tuple[object, ...]:
    lookup = getattr(_navigation_surface(), "symbols_for_document", None)
    assert callable(lookup), "symbols_for_document is missing"
    return tuple(lookup(index, source_path=source_path))


def _completions(index: object, source_path: Path) -> tuple[object, ...]:
    lookup = getattr(_navigation_surface(), "completion_for_document", None)
    assert callable(lookup), "completion_for_document is missing"
    return tuple(lookup(index, source_path=source_path))


@pytest.fixture(scope="module")
def callable_result() -> LinkedStage3CompileResult:
    return compile_stage3_entrypoint(
        CALLABLE_ENTRY.resolve(),
        source_roots=(CALLABLE_ROOT.resolve(),),
        provider_externs={"providers.execute": "test-provider"},
        prompt_externs={
            "prompts.implementation.execute": "prompts/implementation/execute.md"
        },
        command_boundaries={
            "run_checks": ExternalToolBinding(
                name="run_checks",
                stable_command=("python", "scripts/run_checks.py"),
            )
        },
        validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
        workspace_root=Path.cwd().resolve(),
        lowering_route="legacy",
    )


@pytest.fixture(scope="module")
def stdlib_result() -> LinkedStage3CompileResult:
    return compile_stage3_entrypoint(
        STDLIB_CALLER.resolve(),
        source_roots=(STDLIB_CALLER.parent.resolve(),),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
        workspace_root=Path.cwd().resolve(),
    )


@pytest.fixture(scope="module")
def l1_symbols_result() -> LinkedStage3CompileResult:
    return compile_stage3_entrypoint(
        L1_SYMBOLS_ENTRY.resolve(),
        source_roots=(L1_SYMBOLS_ROOT.resolve(),),
        validate_shared=False,
        workspace_root=L1_SYMBOLS_ROOT.resolve(),
        lowering_route="legacy",
    )


@pytest.fixture(scope="module")
def l5_authored_refs_result() -> LinkedStage3CompileResult:
    return compile_stage3_entrypoint(
        L5_AUTHORED_REFS_ENTRY.resolve(),
        source_roots=(L5_AUTHORED_REFS_ROOT.resolve(),),
        provider_externs={"providers.review": "test-provider"},
        prompt_externs={},
        command_boundaries={},
        validate_shared=False,
        workspace_root=L5_AUTHORED_REFS_ROOT.resolve(),
        lowering_route="legacy",
    )


def _accepted_texts(
    result: LinkedStage3CompileResult,
) -> dict[Path, str]:
    return {
        source.path.resolve(): source.path.read_text(encoding="utf-8")
        for source in result.graph.modules_by_name.values()
    }


def _definition_span(
    result: LinkedStage3CompileResult,
    *,
    callable_name: str,
    kind: str,
) -> SourceSpan:
    for compiled in result.compiled_results_by_name.values():
        catalog = (
            compiled.procedure_catalog
            if kind == "procedure"
            else compiled.workflow_catalog
        )
        definition = catalog.definitions_by_name.get(callable_name)
        if definition is not None:
            return definition.span
    raise AssertionError(f"missing {kind} definition {callable_name}")


def _l5_prompt_applications(
    result: LinkedStage3CompileResult,
) -> tuple[PromptApplicationExpr, ...]:
    return tuple(
        node.prompt
        for compiled in result.compiled_results_by_name.values()
        for owner in (*compiled.typed_procedures, *compiled.typed_workflows)
        for node in walk_expr(owner.typed_body.expr)
        if type(node) is ProviderResultExpr
        and type(node.prompt) is PromptApplicationExpr
    )


def _l5_original_syntax_lists(
    result: LinkedStage3CompileResult,
) -> tuple[SyntaxList, ...]:
    navigation = _navigation_surface()
    project = getattr(navigation, "_original_syntax_lists", None)
    assert callable(project), "_original_syntax_lists is missing"
    return tuple(
        syntax_list
        for module_name in result.graph.topological_order
        for syntax_list in project(
            result.graph.modules_by_name[module_name].syntax_module
        )
    )


def _l5_prompt_links(index: object) -> tuple[object, ...]:
    return tuple(
        link
        for link in index.definition_links
        if link.reference_kind == "prompt-application"
    )


def _l5_proc_ref_occurrences(
    result: LinkedStage3CompileResult,
) -> tuple[ProcRefLiteralExpr, ...]:
    return tuple(
        node
        for compiled in result.compiled_results_by_name.values()
        for owner in (*compiled.typed_procedures, *compiled.typed_workflows)
        for node in walk_expr(owner.typed_body.expr)
        if type(node) is ProcRefLiteralExpr
    )


def _l5_proc_ref_links(index: object) -> tuple[object, ...]:
    return tuple(
        link
        for link in index.definition_links
        if link.reference_kind == "proc-ref"
    )


def _l5_procedure_definitions(
    result: LinkedStage3CompileResult,
) -> dict[str, object]:
    return {
        name: definition
        for compiled in result.compiled_results_by_name.values()
        for name, definition in (
            compiled.procedure_catalog.definitions_by_name.items()
        )
    }


def _replace_l5_entry_result(
    result: LinkedStage3CompileResult,
    entry_result: object,
) -> LinkedStage3CompileResult:
    module_name = result.graph.entry_module_name
    return replace(
        result,
        entry_result=entry_result,
        compiled_results_by_name={
            **result.compiled_results_by_name,
            module_name: entry_result,
        },
    )


def _span_start_position(
    span: SourceSpan,
    accepted_text: str,
) -> tuple[int, int]:
    start = source_span_to_lsp_range(span, accepted_text)["start"]
    return start["line"], start["character"]


def test_prompt_application_heads_project_exact_semantic_rows(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    index = _build_index(result)
    applications = _l5_prompt_applications(result)
    links = _l5_prompt_links(index)
    syntax_lists = _l5_original_syntax_lists(result)
    expected = {
        (
            "prompt-application",
            syntax_list.items[0].span,
            application.prompt.qualified_name,
            "prompt",
            application.prompt.declaration.span,
        )
        for application in applications
        for syntax_list in syntax_lists
        if syntax_list.span == application.span
        and not syntax_list.expansion_stack
        and syntax_list.items
        and type(syntax_list.items[0]) is SyntaxIdentifier
    }

    assert len(applications) == 4
    assert len(expected) == 4
    assert {
        (
            link.reference_kind,
            link.reference_span,
            link.canonical_target,
            link.target_kind,
            link.definition_span,
        )
        for link in links
    } == expected
    assert {
        link.canonical_target for link in links
    } == {
        "lsp_l5/entry::local-review",
        "lsp_l5/definitions::shared",
    }
    assert {
        Path(link.definition_span.start.path).resolve()
        for link in links
    } == {
        L5_AUTHORED_REFS_ENTRY.resolve(),
        L5_AUTHORED_REFS_DEFINITIONS.resolve(),
    }
    assert all(
        link.definition_span
        in {
            result.compiled_results_by_name[
                "lsp_l5/entry"
            ].prompt_catalog.resolve(
                "local-review"
            ).declaration.span,
            result.compiled_results_by_name[
                "lsp_l5/definitions"
            ].prompt_catalog.resolve(
                "shared"
            ).declaration.span,
        }
        for link in links
    )


def test_prompt_application_navigation_supports_local_alias_canonical_and_only_spellings(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    index = _build_index(result)
    accepted_texts = _accepted_texts(result)
    entry_path = L5_AUTHORED_REFS_ENTRY.resolve()
    entry_text = accepted_texts[entry_path]
    expected_targets = {
        "local-review": "lsp_l5/entry::local-review",
        "shared": "lsp_l5/definitions::shared",
        "defs.shared": "lsp_l5/definitions::shared",
        "lsp_l5/definitions/shared": "lsp_l5/definitions::shared",
    }
    links_by_text = {
        entry_text[
            link.reference_span.start.offset : link.reference_span.end.offset
        ]: link
        for link in _l5_prompt_links(index)
    }

    assert set(links_by_text) == set(expected_targets)
    for spelling, canonical_target in expected_targets.items():
        link = links_by_text[spelling]
        line, character = _span_start_position(
            link.reference_span,
            entry_text,
        )
        assert link.canonical_target == canonical_target
        assert _definition_at(
            index,
            source_path=entry_path,
            line=line,
            character=character,
            accepted_text_by_path=accepted_texts,
        ) == link.definition_span
    direct_controls = tuple(
        link
        for link in index.definition_links
        if (
            link.canonical_target == "lsp_l5/entry::local-review"
            and link.reference_kind
            in {"procedure-call", "workflow-call"}
        )
    )
    assert {
        (link.reference_kind, link.target_kind)
        for link in direct_controls
    } == {
        ("procedure-call", "procedure"),
        ("workflow-call", "workflow"),
    }
    assert all(link not in direct_controls for link in links_by_text.values())


def test_prompt_application_navigation_is_exactly_head_token_bounded(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    index = _build_index(result)
    accepted_texts = _accepted_texts(result)
    entry_path = L5_AUTHORED_REFS_ENTRY.resolve()
    entry_text = accepted_texts[entry_path]
    link = next(
        row
        for row in _l5_prompt_links(index)
        if row.canonical_target == "lsp_l5/entry::local-review"
    )
    application = next(
        row
        for row in _l5_prompt_applications(result)
        if row.prompt.qualified_name == "lsp_l5/entry::local-review"
    )
    reference_range = source_span_to_lsp_range(
        link.reference_span,
        entry_text,
    )

    def lookup_offset(offset: int) -> SourceSpan | None:
        prefix = entry_text[:offset]
        line = prefix.count("\n")
        character = len(
            prefix.rsplit("\n", maxsplit=1)[-1].encode("utf-16-le")
        ) // 2
        return _definition_at(
            index,
            source_path=entry_path,
            line=line,
            character=character,
            accepted_text_by_path=accepted_texts,
        )

    assert lookup_offset(link.reference_span.start.offset) == link.definition_span
    assert lookup_offset(link.reference_span.end.offset - 1) == link.definition_span
    assert lookup_offset(link.reference_span.start.offset - 1) is None
    assert _definition_at(
        index,
        source_path=entry_path,
        line=reference_range["end"]["line"],
        character=reference_range["end"]["character"],
        accepted_text_by_path=accepted_texts,
    ) is None
    assert lookup_offset(link.reference_span.end.offset) is None
    assert lookup_offset(
        entry_text.index(":message", application.span.start.offset)
    ) is None
    assert lookup_offset(
        entry_text.index(
            "message",
            entry_text.index(":message", application.span.start.offset)
            + len(":message"),
        )
    ) is None
    assert lookup_offset(application.span.end.offset - 1) is None


@pytest.mark.parametrize(
    "drift",
    (
        "missing-syntax-match",
        "duplicate-syntax-match",
        "wrong-syntax-kind",
        "whole-span-mismatch",
        "canonical-identity-mismatch",
        "absent-prompt-catalog-target",
        "differing-definition-span",
        "expanded-occurrence",
        "generated-expanded-definition",
    ),
)
def test_prompt_application_projection_fails_closed_on_join_drift(
    l5_authored_refs_result: LinkedStage3CompileResult,
    drift: str,
) -> None:
    result = l5_authored_refs_result
    navigation = _navigation_surface()
    project = getattr(
        navigation,
        "_project_prompt_application_link",
        None,
    )
    assert callable(project), "_project_prompt_application_link is missing"
    application = next(
        row
        for row in _l5_prompt_applications(result)
        if row.prompt.qualified_name == "lsp_l5/entry::local-review"
    )
    matching_syntax = next(
        row
        for row in _l5_original_syntax_lists(result)
        if row.span == application.span
    )
    compiled = result.compiled_results_by_name["lsp_l5/entry"]
    prompt_catalog = compiled.prompt_catalog
    assert isinstance(prompt_catalog, PromptCatalog)
    definition_spans = {
        ("prompt", application.prompt.qualified_name): (
            application.prompt.declaration.span
        )
    }
    syntax_lists = (matching_syntax,)

    if drift == "missing-syntax-match":
        syntax_lists = ()
    elif drift == "duplicate-syntax-match":
        syntax_lists = (matching_syntax, matching_syntax)
    elif drift == "wrong-syntax-kind":
        syntax_lists = (
            replace(
                matching_syntax,
                items=(matching_syntax.items[1], *matching_syntax.items[1:]),
            ),
        )
    elif drift == "whole-span-mismatch":
        syntax_lists = (
            replace(
                matching_syntax,
                span=replace(
                    matching_syntax.span,
                    end=replace(
                        matching_syntax.span.end,
                        offset=matching_syntax.span.end.offset - 1,
                        column=matching_syntax.span.end.column - 1,
                    ),
                ),
            ),
        )
    elif drift == "canonical-identity-mismatch":
        application = replace(
            application,
            prompt=replace(
                application.prompt,
                qualified_name="lsp_l5/entry::other",
            ),
        )
    elif drift == "absent-prompt-catalog-target":
        prompt_catalog = PromptCatalog(definitions_by_name={})
    elif drift == "differing-definition-span":
        definition_spans[
            ("prompt", application.prompt.qualified_name)
        ] = _l5_test_span(
            L5_AUTHORED_REFS_ENTRY.resolve(),
            1,
            2,
        )
    elif drift == "expanded-occurrence":
        application = replace(application, expansion_stack=(object(),))
    else:
        expanded_definition = replace(
            application.prompt.declaration,
            expansion_stack=(object(),),
        )
        expanded_prompt = replace(
            application.prompt,
            declaration=expanded_definition,
        )
        application = replace(application, prompt=expanded_prompt)
        prompt_catalog = PromptCatalog(
            definitions_by_name={
                "local-review": expanded_prompt,
                expanded_prompt.qualified_name: expanded_prompt,
            }
        )

    with pytest.raises(ValueError):
        project(
            application,
            syntax_lists=syntax_lists,
            prompt_catalog=prompt_catalog,
            definition_spans=definition_spans,
        )


@pytest.mark.parametrize(
    "invalidity",
    ("zero-width", "cross-path"),
)
def test_prompt_application_projection_rejects_invalid_target_definition_spans(
    l5_authored_refs_result: LinkedStage3CompileResult,
    invalidity: str,
) -> None:
    result = l5_authored_refs_result
    navigation = _navigation_surface()
    project = getattr(
        navigation,
        "_project_prompt_application_link",
        None,
    )
    assert callable(project), "_project_prompt_application_link is missing"
    application = next(
        row
        for row in _l5_prompt_applications(result)
        if row.prompt.qualified_name == "lsp_l5/entry::local-review"
    )
    matching_syntax = next(
        row
        for row in _l5_original_syntax_lists(result)
        if row.span == application.span
    )
    target_span = application.prompt.declaration.span
    if invalidity == "zero-width":
        target_span = replace(
            target_span,
            end=target_span.start,
        )
    else:
        target_span = replace(
            target_span,
            end=replace(
                target_span.end,
                path=str(L5_AUTHORED_REFS_DEFINITIONS.resolve()),
            ),
        )
    tampered_prompt = replace(
        application.prompt,
        declaration=replace(
            application.prompt.declaration,
            span=target_span,
        ),
    )
    tampered_application = replace(
        application,
        prompt=tampered_prompt,
    )
    prompt_catalog = PromptCatalog(
        definitions_by_name={
            "local-review": tampered_prompt,
            tampered_prompt.qualified_name: tampered_prompt,
        }
    )

    with pytest.raises(ValueError):
        project(
            tampered_application,
            syntax_lists=(matching_syntax,),
            prompt_catalog=prompt_catalog,
            definition_spans={
                ("prompt", tampered_prompt.qualified_name): target_span,
            },
        )


def test_original_prompt_syntax_without_final_application_is_not_discovered(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    navigation = _navigation_surface()
    project = getattr(
        navigation,
        "_reference_links_for_authored_owner",
        None,
    )
    assert callable(project), "_reference_links_for_authored_owner is missing"
    compiled = result.compiled_results_by_name["lsp_l5/entry"]
    prompt_catalog = compiled.prompt_catalog
    assert isinstance(prompt_catalog, PromptCatalog)
    direct_call_owner = next(
        workflow
        for workflow in compiled.typed_workflows
        if workflow.definition.name.endswith("::procedure-control")
    )
    syntax_lists = _l5_original_syntax_lists(result)
    assert any(
        row.items
        and type(row.items[0]) is SyntaxIdentifier
        and row.items[0].resolved_name == "local-review"
        for row in syntax_lists
    )

    links = project(
        direct_call_owner.typed_body.expr,
        definition_spans={
            ("procedure", "lsp_l5/entry::local-review"): (
                _definition_span(
                    result,
                    callable_name="lsp_l5/entry::local-review",
                    kind="procedure",
                )
            ),
            ("prompt", "lsp_l5/entry::local-review"): (
                prompt_catalog.resolve(
                    "local-review"
                ).declaration.span
            ),
        },
        syntax_lists=syntax_lists,
        prompt_catalog=prompt_catalog,
        procedure_definitions=_l5_procedure_definitions(result),
    )

    assert all(link.reference_kind != "prompt-application" for link in links)


def test_retained_proc_ref_names_project_exact_semantic_rows(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    occurrences = _l5_proc_ref_occurrences(result)
    syntax_lists = _l5_original_syntax_lists(result)
    definitions = _l5_procedure_definitions(result)
    links = _l5_proc_ref_links(_build_index(result))
    expected = {
        (
            "proc-ref",
            syntax_list.items[1].span,
            occurrence.target_name,
            "procedure",
            definitions[occurrence.target_name].span,
        )
        for occurrence in occurrences
        for syntax_list in syntax_lists
        if syntax_list.span == occurrence.span
        and not syntax_list.expansion_stack
        and len(syntax_list.items) == 2
        and type(syntax_list.items[0]) is SyntaxIdentifier
        and syntax_list.items[0].resolved_name == "proc-ref"
        and type(syntax_list.items[1]) is SyntaxIdentifier
    }

    assert len(occurrences) == 4
    assert len(expected) == 4
    assert {
        (
            link.reference_kind,
            link.reference_span,
            link.canonical_target,
            link.target_kind,
            link.definition_span,
        )
        for link in links
    } == expected
    assert {
        link.canonical_target for link in links
    } == {
        "lsp_l5/entry::local-review",
        "lsp_l5/definitions::shared",
    }
    assert {
        Path(link.definition_span.start.path).resolve()
        for link in links
    } == {
        L5_AUTHORED_REFS_ENTRY.resolve(),
        L5_AUTHORED_REFS_DEFINITIONS.resolve(),
    }


def test_retained_proc_ref_navigation_supports_local_alias_canonical_and_only_spellings(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    index = _build_index(result)
    accepted_texts = _accepted_texts(result)
    entry_path = L5_AUTHORED_REFS_ENTRY.resolve()
    entry_text = accepted_texts[entry_path]
    expected_targets = {
        "local-review": "lsp_l5/entry::local-review",
        "shared": "lsp_l5/definitions::shared",
        "defs.shared": "lsp_l5/definitions::shared",
        "lsp_l5/definitions/shared": "lsp_l5/definitions::shared",
    }
    links_by_text = {
        entry_text[
            link.reference_span.start.offset : link.reference_span.end.offset
        ]: link
        for link in _l5_proc_ref_links(index)
    }

    assert set(links_by_text) == set(expected_targets)
    for spelling, canonical_target in expected_targets.items():
        link = links_by_text[spelling]
        line, character = _span_start_position(
            link.reference_span,
            entry_text,
        )
        assert link.canonical_target == canonical_target
        assert _definition_at(
            index,
            source_path=entry_path,
            line=line,
            character=character,
            accepted_text_by_path=accepted_texts,
        ) == link.definition_span


def test_retained_proc_ref_navigation_is_exactly_name_token_bounded(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    index = _build_index(result)
    accepted_texts = _accepted_texts(result)
    entry_path = L5_AUTHORED_REFS_ENTRY.resolve()
    entry_text = accepted_texts[entry_path]
    link = next(
        row
        for row in _l5_proc_ref_links(index)
        if row.canonical_target == "lsp_l5/entry::local-review"
    )
    occurrence = next(
        row
        for row in _l5_proc_ref_occurrences(result)
        if row.target_name == "lsp_l5/entry::local-review"
    )
    matching_syntax = next(
        row
        for row in _l5_original_syntax_lists(result)
        if row.span == occurrence.span
    )

    def lookup_offset(offset: int) -> SourceSpan | None:
        prefix = entry_text[:offset]
        line = prefix.count("\n")
        character = len(
            prefix.rsplit("\n", maxsplit=1)[-1].encode("utf-16-le")
        ) // 2
        return _definition_at(
            index,
            source_path=entry_path,
            line=line,
            character=character,
            accepted_text_by_path=accepted_texts,
        )

    assert lookup_offset(link.reference_span.start.offset) == link.definition_span
    assert lookup_offset(link.reference_span.end.offset - 1) == link.definition_span
    assert lookup_offset(occurrence.span.start.offset) is None
    assert lookup_offset(matching_syntax.items[0].span.start.offset) is None
    assert lookup_offset(link.reference_span.start.offset - 1) is None
    assert lookup_offset(link.reference_span.end.offset) is None
    assert lookup_offset(occurrence.span.end.offset - 1) is None


@pytest.mark.parametrize(
    "drift",
    (
        "missing-original-list",
        "duplicate-original-list",
        "non-proc-ref-head",
        "missing-name",
        "non-identifier-name",
        "extra-item",
        "authored-name-mismatch",
        "canonical-target-mismatch",
        "missing-procedure-definition",
        "differing-definition-span",
        "invalid-token-containment",
    ),
)
def test_proc_ref_projection_rejects_missing_multiple_kind_identity_and_span_mismatch(
    l5_authored_refs_result: LinkedStage3CompileResult,
    drift: str,
) -> None:
    result = l5_authored_refs_result
    project = getattr(
        _navigation_surface(),
        "_project_proc_ref_link",
        None,
    )
    assert callable(project), "_project_proc_ref_link is missing"
    occurrence = next(
        row
        for row in _l5_proc_ref_occurrences(result)
        if row.target_name == "lsp_l5/entry::local-review"
    )
    matching_syntax = next(
        row
        for row in _l5_original_syntax_lists(result)
        if row.span == occurrence.span
    )
    definitions = _l5_procedure_definitions(result)
    definition_spans = {
        ("procedure", name): definition.span
        for name, definition in definitions.items()
    }
    syntax_lists = (matching_syntax,)

    if drift == "missing-original-list":
        syntax_lists = ()
    elif drift == "duplicate-original-list":
        syntax_lists = (matching_syntax, matching_syntax)
    elif drift == "non-proc-ref-head":
        syntax_lists = (
            replace(
                matching_syntax,
                items=(
                    replace(
                        matching_syntax.items[0],
                        resolved_name="call",
                    ),
                    matching_syntax.items[1],
                ),
            ),
        )
    elif drift == "missing-name":
        syntax_lists = (
            replace(
                matching_syntax,
                items=(matching_syntax.items[0],),
            ),
        )
    elif drift == "non-identifier-name":
        syntax_lists = (
            replace(
                matching_syntax,
                items=(matching_syntax.items[0], matching_syntax),
            ),
        )
    elif drift == "extra-item":
        syntax_lists = (
            replace(
                matching_syntax,
                items=(*matching_syntax.items, matching_syntax.items[1]),
            ),
        )
    elif drift == "authored-name-mismatch":
        occurrence = replace(occurrence, authored_name="other")
    elif drift == "canonical-target-mismatch":
        definitions[occurrence.target_name] = replace(
            definitions[occurrence.target_name],
            name="lsp_l5/entry::other",
        )
    elif drift == "missing-procedure-definition":
        definitions.pop(occurrence.target_name)
    elif drift == "differing-definition-span":
        definition_spans[
            ("procedure", occurrence.target_name)
        ] = _l5_test_span(L5_AUTHORED_REFS_ENTRY.resolve(), 1, 2)
    else:
        invalid_name = replace(
            matching_syntax.items[1],
            span=replace(
                matching_syntax.items[1].span,
                end=matching_syntax.span.end,
            ),
        )
        syntax_lists = (
            replace(
                matching_syntax,
                items=(matching_syntax.items[0], invalid_name),
            ),
        )

    with pytest.raises(ValueError):
        project(
            occurrence,
            syntax_lists=syntax_lists,
            procedure_definitions=definitions,
            definition_spans=definition_spans,
        )


def test_proc_ref_projection_rejects_expanded_matching_original_syntax(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    project = getattr(
        _navigation_surface(),
        "_project_proc_ref_link",
        None,
    )
    assert callable(project), "_project_proc_ref_link is missing"
    occurrence = next(
        row
        for row in _l5_proc_ref_occurrences(result)
        if row.target_name == "lsp_l5/entry::local-review"
    )
    matching_syntax = next(
        row
        for row in _l5_original_syntax_lists(result)
        if row.span == occurrence.span
    )
    definitions = _l5_procedure_definitions(result)

    with pytest.raises(ValueError):
        project(
            occurrence,
            syntax_lists=(
                replace(matching_syntax, expansion_stack=(object(),)),
            ),
            procedure_definitions=definitions,
            definition_spans={
                ("procedure", name): definition.span
                for name, definition in definitions.items()
            },
        )


@pytest.mark.parametrize(
    "target_provenance",
    ("generated", "expanded"),
)
def test_proc_ref_projection_rejects_generated_or_expanded_catalog_definition(
    l5_authored_refs_result: LinkedStage3CompileResult,
    target_provenance: str,
) -> None:
    result = l5_authored_refs_result
    project = getattr(
        _navigation_surface(),
        "_project_proc_ref_link",
        None,
    )
    assert callable(project), "_project_proc_ref_link is missing"
    occurrence = next(
        row
        for row in _l5_proc_ref_occurrences(result)
        if row.target_name == "lsp_l5/entry::local-review"
    )
    matching_syntax = next(
        row
        for row in _l5_original_syntax_lists(result)
        if row.span == occurrence.span
    )
    definitions = _l5_procedure_definitions(result)
    definition = definitions[occurrence.target_name]
    definitions[occurrence.target_name] = replace(
        definition,
        **(
            {"generated_local_procedure": object()}
            if target_provenance == "generated"
            else {"expansion_stack": (object(),)}
        ),
    )

    with pytest.raises(ValueError):
        project(
            occurrence,
            syntax_lists=(matching_syntax,),
            procedure_definitions=definitions,
            definition_spans={
                ("procedure", name): row.span
                for name, row in definitions.items()
            },
        )


@pytest.mark.parametrize(
    "excluded_shape",
    (
        "erased-final-occurrence",
        "expanded-occurrence",
        "generated-procedure-owner",
        "expanded-owner",
        "specialized-procedure-owner",
        "specialized-workflow-owner",
    ),
)
def test_proc_ref_projection_excludes_erased_expanded_generated_and_specialized_occurrences(
    l5_authored_refs_result: LinkedStage3CompileResult,
    excluded_shape: str,
) -> None:
    result = l5_authored_refs_result
    compiled = result.entry_result
    workflow = next(
        row
        for row in compiled.typed_workflows
        if row.definition.name.endswith("::exercise-prompts")
    )
    body = workflow.typed_body
    assert isinstance(body.expr, LetStarExpr)
    proc_ref_bindings = body.expr.bindings[:4]
    assert all(
        type(value) is ProcRefLiteralExpr
        for _name, value in proc_ref_bindings
    )
    syntax_lists = _l5_original_syntax_lists(result)
    excluded_spans = tuple(
        next(
            syntax_list.items[1].span
            for syntax_list in syntax_lists
            if syntax_list.span == value.span
        )
        for _name, value in proc_ref_bindings
    )

    if excluded_shape == "erased-final-occurrence":
        changed_workflow = replace(
            workflow,
            typed_body=replace(
                body,
                expr=replace(
                    body.expr,
                    bindings=body.expr.bindings[4:],
                ),
            ),
        )
        changed_entry = replace(
            compiled,
            typed_workflows=(changed_workflow,),
        )
    elif excluded_shape == "expanded-occurrence":
        name, occurrence = proc_ref_bindings[0]
        changed_workflow = replace(
            workflow,
            typed_body=replace(
                body,
                expr=replace(
                    body.expr,
                    bindings=(
                        (name, replace(occurrence, expansion_stack=(object(),))),
                        *body.expr.bindings[1:],
                    ),
                ),
            ),
        )
        changed_entry = replace(
            compiled,
            typed_workflows=(changed_workflow,),
        )
        excluded_spans = (
            next(
                syntax_list.items[1].span
                for syntax_list in syntax_lists
                if syntax_list.span == occurrence.span
            ),
        )
    elif excluded_shape in {
        "generated-procedure-owner",
        "specialized-procedure-owner",
    }:
        procedure = next(
            row
            for row in compiled.typed_procedures
            if row.definition.name.endswith("::local-review")
        )
        changed_procedure = replace(
            procedure,
            typed_body=body,
            definition=replace(
                procedure.definition,
                generated_local_procedure=(
                    object()
                    if excluded_shape == "generated-procedure-owner"
                    else None
                ),
            ),
            specialization=(
                object()
                if excluded_shape == "specialized-procedure-owner"
                else None
            ),
        )
        changed_entry = replace(
            compiled,
            typed_procedures=(changed_procedure,),
            typed_workflows=(),
        )
    else:
        changed_workflow = replace(
            workflow,
            definition=replace(
                workflow.definition,
                expansion_stack=(
                    (object(),)
                    if excluded_shape == "expanded-owner"
                    else ()
                ),
            ),
            specialization=(
                object()
                if excluded_shape == "specialized-workflow-owner"
                else None
            ),
        )
        changed_entry = replace(
            compiled,
            typed_workflows=(changed_workflow,),
        )

    changed_result = _replace_l5_entry_result(result, changed_entry)
    links = _l5_proc_ref_links(_build_index(changed_result))

    assert all(
        link.reference_span not in excluded_spans
        for link in links
    )


def test_macro_consumed_proc_refs_and_macro_heads_have_no_l5_rows() -> None:
    source_path = REVIEW_REVISE_DESIGN_DOCS.resolve()
    result = compile_stage3_entrypoint(
        source_path,
        source_roots=(source_path.parent,),
        provider_externs={
            "providers.design-docs.review": "codex",
            "providers.design-docs.fix": "codex",
        },
        prompt_externs={
            "prompts.design-docs.fix": (
                "prompts/workflows/review_revise_design_docs/fix.md"
            ),
        },
        command_boundaries={},
        validate_shared=False,
        workspace_root=Path.cwd().resolve(),
        lowering_route="legacy",
    )
    source = source_path.read_text(encoding="utf-8")
    index = _build_index(result)
    excluded_offsets = {
        source.index("review-revise-loop", source.index("(review-revise-loop")),
        source.index(
            "review-design-docs",
            source.index("(proc-ref review-design-docs"),
        ),
        source.index(
            "fix-design-doc",
            source.index("(proc-ref fix-design-doc"),
        ),
    }

    assert not _l5_proc_ref_occurrences(result)
    assert all(
        link.reference_span.start.offset not in excluded_offsets
        for link in index.definition_links
    )
    direct_call = next(
        link
        for link in index.definition_links
        if (
            link.reference_kind == "workflow-call"
            and link.canonical_target
            == "review_revise_design_docs::build-review-runtime-owned"
        )
    )
    assert source[
        direct_call.reference_span.start.offset :
        direct_call.reference_span.end.offset
    ] == "build-review-runtime-owned"


def _l5_test_span(
    path: Path,
    start: int,
    end: int,
) -> SourceSpan:
    return SourceSpan(
        start=SourcePosition(
            path=str(path),
            line=1,
            column=start + 1,
            offset=start,
        ),
        end=SourcePosition(
            path=str(path),
            line=1,
            column=end + 1,
            offset=end,
        ),
    )


def test_definition_links_are_frozen_five_field_semantic_rows(
    callable_result: LinkedStage3CompileResult,
) -> None:
    index = _build_index(callable_result)
    links = tuple(
        link
        for link in index.definition_links
        if link.reference_kind in {"procedure-call", "workflow-call"}
    )

    assert links
    assert tuple(field.name for field in fields(type(links[0]))) == (
        "reference_kind",
        "reference_span",
        "canonical_target",
        "target_kind",
        "definition_span",
    )
    assert {
        (
            link.reference_kind,
            link.reference_span,
            link.canonical_target,
            link.target_kind,
            link.definition_span,
        )
        for link in links
    } == {
        (
            (
                "workflow-call"
                if type(node) is CallExpr
                else "procedure-call"
            ),
            node.authored_callee_span,
            node.callee_name,
            "workflow" if type(node) is CallExpr else "procedure",
            _definition_span(
                callable_result,
                callable_name=node.callee_name,
                kind=(
                    "workflow"
                    if type(node) is CallExpr
                    else "procedure"
                ),
            ),
        )
        for compiled in callable_result.compiled_results_by_name.values()
        for owner in (*compiled.typed_procedures, *compiled.typed_workflows)
        if owner.specialization is None
        and not owner.definition.expansion_stack
        and (
            not hasattr(owner.definition, "generated_local_procedure")
            or owner.definition.generated_local_procedure is None
        )
        for node in walk_expr(owner.typed_body.expr)
        if type(node) in {CallExpr, ProcedureCallExpr}
        and node.authored_callee_span is not None
    }
    with pytest.raises(FrozenInstanceError):
        links[0].canonical_target = "changed"


@pytest.mark.parametrize(
    ("reference_kind", "target_kind"),
    (
        ("unknown-reference", "procedure"),
        ("procedure-call", "unknown-target"),
    ),
)
def test_definition_link_rejects_unknown_reference_and_target_kinds(
    tmp_path: Path,
    reference_kind: str,
    target_kind: str,
) -> None:
    link_type = getattr(_navigation_surface(), "DefinitionLink")
    reference_span = _l5_test_span(tmp_path / "source.orc", 1, 7)
    definition_span = _l5_test_span(tmp_path / "target.orc", 10, 20)

    with pytest.raises(ValueError):
        link_type(
            reference_kind=reference_kind,
            reference_span=reference_span,
            canonical_target="demo::shared",
            target_kind=target_kind,
            definition_span=definition_span,
        )


def test_reference_projection_collapses_only_identical_duplicate_facts(
    tmp_path: Path,
) -> None:
    navigation = _navigation_surface()
    link_type = getattr(navigation, "DefinitionLink")
    insert_target = getattr(
        navigation,
        "_insert_unique_definition_target",
        None,
    )
    insert_link = getattr(
        navigation,
        "_insert_unique_reference_link",
        None,
    )
    assert callable(insert_target)
    assert callable(insert_link)
    definition_span = _l5_test_span(tmp_path / "target.orc", 10, 20)
    link = link_type(
        reference_kind="procedure-call",
        reference_span=_l5_test_span(tmp_path / "source.orc", 1, 7),
        canonical_target="demo::shared",
        target_kind="procedure",
        definition_span=definition_span,
    )
    targets: dict[tuple[str, str], SourceSpan] = {}
    occurrences: dict[tuple[str, str, int, int], object] = {}
    kinds_by_span: dict[tuple[str, int, int], str] = {}

    insert_target(
        targets,
        target_kind="procedure",
        canonical_target="demo::shared",
        definition_span=definition_span,
    )
    insert_target(
        targets,
        target_kind="procedure",
        canonical_target="demo::shared",
        definition_span=definition_span,
    )
    insert_link(occurrences, kinds_by_span, link)
    insert_link(occurrences, kinds_by_span, link)

    assert targets == {("procedure", "demo::shared"): definition_span}
    assert tuple(occurrences.values()) == (link,)


@pytest.mark.parametrize(
    "collision",
    ("definition-span", "target-kind", "canonical-target"),
)
def test_reference_projection_rejects_target_and_occurrence_collisions(
    tmp_path: Path,
    collision: str,
) -> None:
    navigation = _navigation_surface()
    link_type = getattr(navigation, "DefinitionLink")
    insert_target = getattr(
        navigation,
        "_insert_unique_definition_target",
        None,
    )
    insert_link = getattr(
        navigation,
        "_insert_unique_reference_link",
        None,
    )
    assert callable(insert_target)
    assert callable(insert_link)
    reference_span = _l5_test_span(tmp_path / "source.orc", 1, 7)
    definition_span = _l5_test_span(tmp_path / "target.orc", 10, 20)
    other_definition_span = _l5_test_span(
        tmp_path / "other-target.orc",
        30,
        40,
    )
    base = link_type(
        reference_kind="procedure-call",
        reference_span=reference_span,
        canonical_target="demo::shared",
        target_kind="procedure",
        definition_span=definition_span,
    )
    targets: dict[tuple[str, str], SourceSpan] = {}
    occurrences: dict[tuple[str, str, int, int], object] = {}
    kinds_by_span: dict[tuple[str, int, int], str] = {}
    insert_target(
        targets,
        target_kind=base.target_kind,
        canonical_target=base.canonical_target,
        definition_span=base.definition_span,
    )
    insert_link(occurrences, kinds_by_span, base)

    if collision == "definition-span":
        with pytest.raises(ValueError):
            insert_target(
                targets,
                target_kind=base.target_kind,
                canonical_target=base.canonical_target,
                definition_span=other_definition_span,
            )
        conflicting = replace(
            base,
            definition_span=other_definition_span,
        )
    elif collision == "target-kind":
        conflicting = replace(
            base,
            target_kind="workflow",
        )
    else:
        conflicting = replace(
            base,
            canonical_target="other::shared",
        )

    with pytest.raises(ValueError):
        insert_link(occurrences, kinds_by_span, conflicting)


def test_reference_projection_rejects_cross_kind_assertions_at_one_span(
    tmp_path: Path,
) -> None:
    navigation = _navigation_surface()
    link_type = getattr(navigation, "DefinitionLink")
    insert_link = getattr(
        navigation,
        "_insert_unique_reference_link",
        None,
    )
    assert callable(insert_link)
    reference_span = _l5_test_span(tmp_path / "source.orc", 1, 7)
    definition_span = _l5_test_span(tmp_path / "target.orc", 10, 20)
    occurrences: dict[tuple[str, str, int, int], object] = {}
    kinds_by_span: dict[tuple[str, int, int], str] = {}
    insert_link(
        occurrences,
        kinds_by_span,
        link_type(
            reference_kind="procedure-call",
            reference_span=reference_span,
            canonical_target="demo::shared",
            target_kind="procedure",
            definition_span=definition_span,
        ),
    )

    with pytest.raises(ValueError):
        insert_link(
            occurrences,
            kinds_by_span,
            link_type(
                reference_kind="workflow-call",
                reference_span=reference_span,
                canonical_target="demo::shared",
                target_kind="workflow",
                definition_span=definition_span,
            ),
        )


def test_reference_projection_preserves_same_spelling_across_namespaces_at_distinct_spans(
    tmp_path: Path,
) -> None:
    navigation = _navigation_surface()
    link_type = getattr(navigation, "DefinitionLink")
    insert_target = getattr(
        navigation,
        "_insert_unique_definition_target",
        None,
    )
    insert_link = getattr(
        navigation,
        "_insert_unique_reference_link",
        None,
    )
    assert callable(insert_target)
    assert callable(insert_link)
    targets: dict[tuple[str, str], SourceSpan] = {}
    occurrences: dict[tuple[str, str, int, int], object] = {}
    kinds_by_span: dict[tuple[str, int, int], str] = {}
    rows = tuple(
        link_type(
            reference_kind=reference_kind,
            reference_span=_l5_test_span(
                tmp_path / "source.orc",
                ordinal * 10,
                ordinal * 10 + 6,
            ),
            canonical_target="demo::shared",
            target_kind=target_kind,
            definition_span=_l5_test_span(
                tmp_path / f"{target_kind}.orc",
                10,
                20,
            ),
        )
        for ordinal, (reference_kind, target_kind) in enumerate(
            (
                ("prompt-application", "prompt"),
                ("procedure-call", "procedure"),
                ("workflow-call", "workflow"),
            ),
            start=1,
        )
    )

    for row in rows:
        insert_target(
            targets,
            target_kind=row.target_kind,
            canonical_target=row.canonical_target,
            definition_span=row.definition_span,
        )
        insert_link(occurrences, kinds_by_span, row)

    assert set(targets) == {
        ("prompt", "demo::shared"),
        ("procedure", "demo::shared"),
        ("workflow", "demo::shared"),
    }
    assert set(occurrences.values()) == set(rows)


@pytest.mark.parametrize(
    ("source_path", "line", "character", "callee_name", "kind"),
    (
        (
            CALLABLE_ENTRY,
            12,
            14,
            "neurips/procedures::build-checks",
            "procedure",
        ),
        (
            CALLABLE_ENTRY,
            13,
            12,
            "neurips/helper::provider-attempt",
            "workflow",
        ),
        (
            CALLABLE_HELPER,
            18,
            10,
            "neurips/helper::provider-attempt",
            "workflow",
        ),
    ),
)
def test_definition_resolves_only_exact_direct_authored_call_heads(
    callable_result: LinkedStage3CompileResult,
    source_path: Path,
    line: int,
    character: int,
    callee_name: str,
    kind: str,
) -> None:
    index = _build_index(callable_result)

    assert _definition_at(
        index,
        source_path=source_path.resolve(),
        line=line,
        character=character,
        accepted_text_by_path=_accepted_texts(callable_result),
    ) == _definition_span(
        callable_result,
        callable_name=callee_name,
        kind=kind,
    )


def test_definition_reaches_imported_stdlib_defproc_authored_span(
    stdlib_result: LinkedStage3CompileResult,
) -> None:
    index = _build_index(stdlib_result)
    stdlib_span = _definition_span(
        stdlib_result,
        callable_name="std/resource::finalize-selected-item-proc",
        kind="procedure",
    )

    assert _definition_at(
        index,
        source_path=STDLIB_CALLER.resolve(),
        line=41,
        character=7,
        accepted_text_by_path=_accepted_texts(stdlib_result),
    ) == stdlib_span
    assert Path(stdlib_span.start.path).resolve().is_relative_to(
        (
            Path.cwd()
            / "orchestrator"
            / "workflow_lisp"
            / "stdlib_modules"
        ).resolve()
    )


def test_definition_resolves_a_direct_local_procedure_call(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "local.orc"
    source_path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule local)",
                "  (export run)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (report WorkReport))",
                "  (defproc identity ((report_path WorkReport)) -> ChecksResult",
                "    :effects ()",
                "    :lowering inline",
                "    (record ChecksResult",
                "      :report report_path))",
                "  (defworkflow run ((report_path WorkReport)) -> ChecksResult",
                "    (identity report_path)))",
                "",
            )
        ),
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        source_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )

    assert _definition_at(
        _build_index(result),
        source_path=source_path,
        line=17,
        character=5,
        accepted_text_by_path=_accepted_texts(result),
    ) == _definition_span(
        result,
        callable_name="local::identity",
        kind="procedure",
    )


def test_same_raw_callable_names_resolve_by_canonical_compiler_identity(
    tmp_path: Path,
) -> None:
    package = tmp_path / "demo"
    package.mkdir()
    (package / "types.orc").write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/types)",
                "  (export WorkReport ChecksResult)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (report WorkReport)))",
                "",
            )
        ),
        encoding="utf-8",
    )
    for module_name in ("a", "b"):
        (package / f"{module_name}.orc").write_text(
            "\n".join(
                (
                    "(workflow-lisp",
                    '  (:language "0.1")',
                    '  (:target-dsl "2.14")',
                    f"  (defmodule demo/{module_name})",
                    "  (import demo/types :only (WorkReport ChecksResult))",
                    "  (export same)",
                    "  (defproc same ((report_path WorkReport)) -> ChecksResult",
                    "    :effects ()",
                    "    :lowering inline",
                    "    (record ChecksResult",
                    "      :report report_path)))",
                    "",
                )
            ),
            encoding="utf-8",
        )
    entry_path = package / "entry.orc"
    entry_path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule demo/entry)",
                "  (import demo/types :only (WorkReport ChecksResult))",
                "  (import demo/a :as a)",
                "  (import demo/b :as b)",
                "  (export run)",
                "  (defworkflow run ((report_path WorkReport)) -> ChecksResult",
                "    (a.same report_path)))",
                "",
            )
        ),
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )

    assert _definition_at(
        _build_index(result),
        source_path=entry_path,
        line=9,
        character=5,
        accepted_text_by_path=_accepted_texts(result),
    ) == _definition_span(
        result,
        callable_name="demo/a::same",
        kind="procedure",
    )
    assert _definition_span(
        result,
        callable_name="demo/a::same",
        kind="procedure",
    ) != _definition_span(
        result,
        callable_name="demo/b::same",
        kind="procedure",
    )


def test_same_canonical_name_resolves_in_distinct_callable_namespaces(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "same-name.orc"
    source_path.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule same-name)",
                "  (defpath WorkReport",
                "    :kind relpath",
                '    :under "artifacts/work"',
                "    :must-exist true)",
                "  (defrecord ChecksResult",
                "    (report WorkReport))",
                "  (defproc shared ((report_path WorkReport)) -> ChecksResult",
                "    :effects ()",
                "    :lowering inline",
                "    (record ChecksResult :report report_path))",
                "  (defworkflow shared ((report_path WorkReport)) -> ChecksResult",
                "    (record ChecksResult :report report_path))",
                "  (defworkflow procedure-caller",
                "    ((report_path WorkReport)) -> ChecksResult",
                "    (shared report_path))",
                "  (defworkflow workflow-caller",
                "    ((report_path WorkReport)) -> ChecksResult",
                "    (call shared :report_path report_path)))",
                "",
            )
        ),
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        source_path,
        source_roots=(tmp_path,),
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )
    compiled = result.compiled_results_by_name["same-name"]
    calls = {
        type(node): node
        for workflow in compiled.typed_workflows
        if workflow.definition.name.endswith("-caller")
        for node in walk_expr(workflow.typed_body.expr)
        if type(node) in {CallExpr, ProcedureCallExpr}
    }
    accepted_texts = _accepted_texts(result)
    index = _build_index(result)

    for call_type, target_kind in (
        (ProcedureCallExpr, "procedure"),
        (CallExpr, "workflow"),
    ):
        call = calls[call_type]
        assert call.authored_callee_span is not None
        position = source_span_to_lsp_range(
            call.authored_callee_span,
            accepted_texts[source_path.resolve()],
        )["start"]
        assert _definition_at(
            index,
            source_path=source_path,
            line=position["line"],
            character=position["character"],
            accepted_text_by_path=accepted_texts,
        ) == _definition_span(
            result,
            callable_name="same-name::shared",
            kind=target_kind,
        )


@pytest.mark.parametrize(
    ("source_path", "line", "character"),
    (
        (CALLABLE_ENTRY, 12, 13),  # opening parenthesis before procedure head
        (CALLABLE_ENTRY, 12, 31),  # exact end of procedure callee span
        (CALLABLE_ENTRY, 12, 32),  # procedure argument
        (CALLABLE_ENTRY, 3, 3),  # defmodule definition
        (CALLABLE_ENTRY, 4, 10),  # imported type
        (CALLABLE_ENTRY, 8, 15),  # workflow definition/signature
        (CALLABLE_ENTRY, 14, 16),  # workflow call argument
        (CALLABLE_HELPER, 10, 22),  # provider extern
        (CALLABLE_HELPER, 11, 16),  # prompt extern
    ),
)
def test_definition_has_no_whole_form_or_other_identifier_fallback(
    callable_result: LinkedStage3CompileResult,
    source_path: Path,
    line: int,
    character: int,
) -> None:
    assert (
        _definition_at(
            _build_index(callable_result),
            source_path=source_path.resolve(),
            line=line,
            character=character,
            accepted_text_by_path=_accepted_texts(callable_result),
        )
        is None
    )


def test_null_or_generated_call_provenance_is_never_indexed(
    callable_result: LinkedStage3CompileResult,
) -> None:
    entry_result = callable_result.compiled_results_by_name["neurips/entry"]
    typed_workflow = entry_result.typed_workflows[0]
    typed_body = typed_workflow.typed_body
    assert isinstance(typed_body.expr, LetStarExpr)
    procedure_call = typed_body.expr.bindings[0][1]
    assert isinstance(procedure_call, ProcedureCallExpr)
    without_provenance = replace(
        procedure_call,
        authored_callee_span=None,
    )
    replaced_body = replace(
        typed_body.expr,
        bindings=(("checks", without_provenance),),
    )
    replaced_workflow = replace(
        typed_workflow,
        typed_body=replace(typed_body, expr=replaced_body),
    )
    replaced_entry_result = replace(
        entry_result,
        typed_workflows=(replaced_workflow,),
    )
    replaced_result = replace(
        callable_result,
        entry_result=replaced_entry_result,
        compiled_results_by_name={
            **callable_result.compiled_results_by_name,
            "neurips/entry": replaced_entry_result,
        },
    )

    assert (
        _definition_at(
            _build_index(replaced_result),
            source_path=CALLABLE_ENTRY.resolve(),
            line=12,
            character=14,
            accepted_text_by_path=_accepted_texts(replaced_result),
        )
        is None
    )


def test_document_symbols_are_all_ten_compiler_proven_kinds_in_source_order(
    l1_symbols_result: LinkedStage3CompileResult,
) -> None:
    symbols = _symbols(
        _build_index(l1_symbols_result),
        L1_SYMBOLS_ENTRY.resolve(),
    )
    text = L1_SYMBOLS_ENTRY.read_text(encoding="utf-8")

    assert tuple((symbol.name, symbol.kind) for symbol in symbols) == (
        ("lsp_l1_symbols/entry", "module"),
        ("ReviewDecision", "enum"),
        ("ReportPath", "path"),
        ("CommonFields", "schema"),
        ("ReviewState", "record"),
        ("ReviewOutcome", "union"),
        ("review-state", "resource"),
        ("record-review", "transition"),
        ("default-status", "procedure"),
        ("normalize-status", "procedure"),
        ("render-and-preserve", "procedure"),
        ("default-review", "workflow"),
        ("review", "workflow"),
        ("review-many", "workflow"),
    )
    assert tuple(symbol.source_ordinal for symbol in symbols) == tuple(
        range(14)
    )
    assert tuple(
        symbol.definition_span.start.offset for symbol in symbols
    ) == tuple(
        sorted(symbol.definition_span.start.offset for symbol in symbols)
    )
    for symbol in symbols:
        assert symbol.definition_span != symbol.selection_span
        assert text[
            symbol.selection_span.start.offset :
            symbol.selection_span.end.offset
        ] == symbol.name
        assert text[
            symbol.definition_span.start.offset :
            symbol.definition_span.end.offset
        ].startswith("(def")


def test_document_symbol_index_uses_projection_without_reading_or_parsing(
    callable_result: LinkedStage3CompileResult,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    navigation = _navigation_surface()
    reader = import_module("orchestrator.workflow_lisp.reader")
    project = getattr(navigation, "project_authored_symbols", None)
    assert callable(project), "compiler-owned symbol projection is not wired"
    projected_modules: list[str] = []

    def recording_projection(
        resolved_source: object,
        compiled_result: object,
    ) -> tuple[object, ...]:
        projected_modules.append(resolved_source.module_name)
        return project(resolved_source, compiled_result)

    def unexpected_read_or_parse(*args: object, **kwargs: object) -> object:
        pytest.fail("navigation index construction read or parsed source text")

    monkeypatch.setattr(
        navigation,
        "project_authored_symbols",
        recording_projection,
    )
    monkeypatch.setattr("builtins.open", unexpected_read_or_parse)
    monkeypatch.setattr(Path, "read_text", unexpected_read_or_parse)
    monkeypatch.setattr(reader, "read_sexpr_text", unexpected_read_or_parse)
    monkeypatch.setattr(reader, "read_sexpr_file", unexpected_read_or_parse)

    symbols = _symbols(
        _build_index(callable_result),
        CALLABLE_ENTRY.resolve(),
    )

    assert len(symbols) == 2
    assert projected_modules == list(
        callable_result.graph.topological_order
    )


def test_completion_preserves_exact_import_scope_spellings_and_namespaces(
    callable_result: LinkedStage3CompileResult,
) -> None:
    registry = import_module("orchestrator.workflow_lisp.form_registry")
    registered_form_heads = getattr(registry, "registered_form_heads", None)
    assert callable(registered_form_heads), "registered_form_heads is missing"
    expected_callables = {
        "orchestrate": (
            "workflow",
            "neurips/entry::orchestrate",
        ),
        "proc.build-checks": (
            "procedure",
            "neurips/procedures::build-checks",
        ),
        "neurips/procedures/build-checks": (
            "procedure",
            "neurips/procedures::build-checks",
        ),
        "build-checks": (
            "procedure",
            "neurips/procedures::build-checks",
        ),
        "helper.provider-attempt": (
            "workflow",
            "neurips/helper::provider-attempt",
        ),
        "neurips/helper/provider-attempt": (
            "workflow",
            "neurips/helper::provider-attempt",
        ),
        "provider-attempt": (
            "workflow",
            "neurips/helper::provider-attempt",
        ),
        "helper.secondary": (
            "workflow",
            "neurips/helper::secondary",
        ),
        "neurips/helper/secondary": (
            "workflow",
            "neurips/helper::secondary",
        ),
        "secondary": (
            "workflow",
            "neurips/helper::secondary",
        ),
    }

    completions = _completions(
        _build_index(callable_result),
        CALLABLE_ENTRY.resolve(),
    )
    kind_rank = {"procedure": 0, "workflow": 1, "form": 2}
    expected_order = tuple(
        sorted(
            (
                *(
                    (label, kind, canonical_target)
                    for label, (kind, canonical_target) in expected_callables.items()
                ),
                *(
                    (head, "form", head)
                    for head in registered_form_heads()
                ),
            ),
            key=lambda row: (row[0], kind_rank[row[1]], row[2]),
        )
    )
    assert tuple(
        (item.label, item.kind, item.canonical_target)
        for item in completions
    ) == expected_order

    callable_rows = {
        item.label: (item.kind, item.canonical_target)
        for item in completions
        if item.kind in {"procedure", "workflow"}
    }

    assert callable_rows == expected_callables
    assert {
        item.label
        for item in completions
        if item.kind == "form"
    } == set(registered_form_heads())
    assert "neurips/procedures::build-checks" not in callable_rows
    assert "procedures.build-checks" not in callable_rows


def test_completion_preserves_same_label_procedure_workflow_and_form_rows(
    tmp_path: Path,
) -> None:
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    entry_path = root / "lsp_l1_symbols" / "entry.orc"
    entry_path.write_text(
        entry_path.read_text(encoding="utf-8").replace(
            "normalize-status",
            "review",
        ),
        encoding="utf-8",
    )
    result = compile_stage3_entrypoint(
        entry_path,
        source_roots=(root,),
        validate_shared=False,
        workspace_root=root,
        lowering_route="legacy",
    )
    rows = tuple(
        item
        for item in _completions(
            _build_index(result, form_heads=("review",)),
            entry_path,
        )
        if item.label == "review"
    )

    assert tuple(
        (item.label, item.kind, item.canonical_target, item.detail)
        for item in rows
    ) == (
        (
            "review",
            "procedure",
            "lsp_l1_symbols/entry::review",
            "procedure (status: String) -> String effects ()",
        ),
        (
            "review",
            "workflow",
            "lsp_l1_symbols/entry::review",
            "workflow (status: String) -> String",
        ),
        ("review", "form", "review", "form"),
    )


def test_completion_details_use_resolved_signatures_and_declared_effects_only(
    l1_symbols_result: LinkedStage3CompileResult,
) -> None:
    rows = {
        (item.kind, item.label): item.detail
        for item in _completions(
            _build_index(l1_symbols_result),
            L1_SYMBOLS_ENTRY.resolve(),
        )
    }
    typed_render = next(
        procedure
        for procedure in l1_symbols_result.entry_result.typed_procedures
        if procedure.definition.name.endswith("::render-and-preserve")
    )
    typed_review_workflow = next(
        workflow
        for workflow in l1_symbols_result.entry_result.typed_workflows
        if workflow.definition.name.endswith("::review")
    )
    inferred_only_summary = effect_summary(
        direct_effects=(WriteEffect(subject=("inferred-only",)),),
    )
    changed_procedure = replace(
        typed_render,
        direct_effect_summary=inferred_only_summary,
        transitive_effect_summary=inferred_only_summary,
    )
    changed_workflow = replace(
        typed_review_workflow,
        effect_summary=inferred_only_summary,
    )
    changed_entry_result = replace(
        l1_symbols_result.entry_result,
        typed_procedures=tuple(
            changed_procedure
            if procedure is typed_render
            else procedure
            for procedure in l1_symbols_result.entry_result.typed_procedures
        ),
        typed_workflows=tuple(
            changed_workflow
            if workflow is typed_review_workflow
            else workflow
            for workflow in l1_symbols_result.entry_result.typed_workflows
        ),
    )
    changed_result = replace(
        l1_symbols_result,
        entry_result=changed_entry_result,
        compiled_results_by_name={
            **l1_symbols_result.compiled_results_by_name,
            l1_symbols_result.graph.entry_module_name: changed_entry_result,
        },
    )
    changed_rows = {
        (item.kind, item.label): item.detail
        for item in _completions(
            _build_index(changed_result),
            L1_SYMBOLS_ENTRY.resolve(),
        )
    }

    assert changed_procedure.direct_effect_summary.direct_effects
    assert (
        changed_procedure.direct_effect_summary.direct_effects
        != changed_procedure.signature.declared_effects
    )
    assert changed_workflow.effect_summary.transitive_effects
    assert rows[("procedure", "default-status")] == (
        "procedure () -> String effects ()"
    )
    assert rows[("procedure", "normalize-status")] == (
        "procedure (status: String) -> String effects ()"
    )
    assert rows[("procedure", "render-and-preserve")] == (
        "procedure "
        "(reports: List[Optional[Map[String, ReportPath]]], "
        "status: String, target: ReportPath) "
        "-> List[Optional[Map[String, ReportPath]]] "
        "effects (writes(status-view))"
    )
    assert changed_rows[("procedure", "render-and-preserve")] == (
        "procedure "
        "(reports: List[Optional[Map[String, ReportPath]]], "
        "status: String, target: ReportPath) "
        "-> List[Optional[Map[String, ReportPath]]] "
        "effects (writes(status-view))"
    )
    assert rows[("workflow", "default-review")] == (
        "workflow () -> ReviewState"
    )
    assert rows[("workflow", "review")] == (
        "workflow (status: String) -> String"
    )
    assert changed_rows[("workflow", "review")] == (
        "workflow (status: String) -> String"
    )
    assert rows[("workflow", "review-many")] == (
        "workflow "
        "(primary: String, secondary: String, fallback: String) -> String"
    )


def test_server_maps_completion_namespaces_details_and_protocol_kinds(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    entry_path = root / "lsp_l1_symbols" / "entry.orc"
    entry_path.write_text(
        entry_path.read_text(encoding="utf-8").replace(
            "normalize-status",
            "review",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        lsp_compile_driver,
        "registered_form_heads",
        lambda *, target_dsl_version=None: ("review",),
    )
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    server = WorkflowLispLanguageServer()
    server.driver = driver

    completion = server.completion(_completion_params(entry_path))

    assert completion.is_incomplete is False
    assert tuple(
        (item.label, item.kind, item.detail)
        for item in completion.items
        if item.label == "review"
    ) == (
        (
            "review",
            types.CompletionItemKind.Function,
            "procedure (status: String) -> String effects ()",
        ),
        (
            "review",
            types.CompletionItemKind.Function,
            "workflow (status: String) -> String",
        ),
        (
            "review",
            types.CompletionItemKind.Keyword,
            "form",
        ),
    )


def test_completion_has_no_nominal_or_server_inferred_type_filter(
    callable_result: LinkedStage3CompileResult,
) -> None:
    completion_for_document = getattr(
        _navigation_surface(),
        "completion_for_document",
    )
    # The closed v1 surface takes only compiler visibility for a document.
    # It has no cursor/type/taxonomy/filter input on which to invent filtering.
    labels = {
        item.label
        for item in completion_for_document(
            _build_index(callable_result),
            source_path=CALLABLE_ENTRY.resolve(),
        )
    }

    assert {
        "orchestrate",
        "build-checks",
        "provider-attempt",
        "secondary",
    }.issubset(labels)


def test_registered_form_heads_accessor_is_sorted_and_exact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = import_module("orchestrator.workflow_lisp.form_registry")
    registered_form_heads = getattr(registry, "registered_form_heads", None)
    assert callable(registered_form_heads), "registered_form_heads is missing"
    fake_spec = registry.get_form_spec("defproc")
    assert fake_spec is not None
    monkeypatch.setattr(
        registry,
        "_FORM_REGISTRY",
        {"z-form": fake_spec, "a-form": fake_spec},
    )

    assert registered_form_heads() == ("a-form", "z-form")


def test_utf16_cursor_membership_uses_exact_accepted_text() -> None:
    navigation = _navigation_surface()
    contains = getattr(navigation, "lsp_position_in_source_span", None)
    assert callable(contains), "lsp_position_in_source_span is missing"
    from orchestrator.workflow_lisp.spans import SourcePosition

    span = SourceSpan(
        start=SourcePosition(
            path="/workspace/unicode.orc",
            line=1,
            column=3,
            offset=2,
        ),
        end=SourcePosition(
            path="/workspace/unicode.orc",
            line=1,
            column=5,
            offset=4,
        ),
    )

    assert contains(span, line=0, character=3, accepted_text="a😀bc") is True
    assert contains(span, line=0, character=5, accepted_text="a😀bc") is False


def test_definition_fails_closed_without_exact_accepted_source_text(
    callable_result: LinkedStage3CompileResult,
) -> None:
    assert (
        _definition_at(
            _build_index(callable_result),
            source_path=CALLABLE_ENTRY.resolve(),
            line=12,
            character=14,
            accepted_text_by_path={},
        )
        is None
    )


def _compile_driver_for_callable_root(
    root: Path,
) -> tuple[lsp_compile_driver.LspCompileDriver, Path, list[int]]:
    entry_path = root / "neurips" / "entry.orc"
    build_calls: list[int] = []

    def build(
        _request: object,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        build_calls.append(len(build_calls) + 1)
        compile_result = compile_stage3_entrypoint(
            entry_path,
            source_roots=(root,),
            provider_externs={"providers.execute": "test-provider"},
            prompt_externs={
                "prompts.implementation.execute": (
                    "prompts/implementation/execute.md"
                )
            },
            command_boundaries={
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
            validation_profile=Stage3ValidationProfile.SHARED_CALLABLE,
            workspace_root=root,
            lowering_route="legacy",
            source_read_trace=source_read_trace,
        )
        return SimpleNamespace(
            compile_result=compile_result,
            diagnostics=compile_result.diagnostics,
            configuration_trace=SimpleNamespace(revision_vector=()),
        )

    driver = lsp_compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=root.as_uri(),
            initialization_options={"source_roots": (str(root),)},
        ),
        build_in_memory=build,
    )
    text = entry_path.read_text(encoding="utf-8")
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=lsp_compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    return driver, entry_path, build_calls


def _compile_driver_for_l1_symbols_root(
    root: Path,
) -> tuple[lsp_compile_driver.LspCompileDriver, Path]:
    entry_path = root / "lsp_l1_symbols" / "entry.orc"

    def build(
        _request: object,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        compile_result = compile_stage3_entrypoint(
            entry_path,
            source_roots=(root,),
            validate_shared=False,
            workspace_root=root,
            lowering_route="legacy",
            source_read_trace=source_read_trace,
        )
        return SimpleNamespace(
            compile_result=compile_result,
            diagnostics=compile_result.diagnostics,
            configuration_trace=SimpleNamespace(revision_vector=()),
        )

    driver = lsp_compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=root.as_uri(),
            initialization_options={"source_roots": (str(root),)},
        ),
        build_in_memory=build,
    )
    text = entry_path.read_text(encoding="utf-8")
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=lsp_compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    return driver, entry_path


def _compile_driver_for_l5_root(
    root: Path,
    *,
    entry_relative: Path = Path("lsp_l5/entry.orc"),
) -> tuple[lsp_compile_driver.LspCompileDriver, Path]:
    entry_path = root / entry_relative

    def build(
        _request: object,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        try:
            compile_result = compile_stage3_entrypoint(
                entry_path,
                source_roots=(root,),
                provider_externs={"providers.review": "test-provider"},
                prompt_externs={},
                command_boundaries={},
                validate_shared=False,
                workspace_root=root,
                lowering_route="legacy",
                source_read_trace=source_read_trace,
            )
        except LispFrontendCompileError as error:
            vector = driver.state.configuration_vector
            assert vector is not None
            error.configuration_revision_vector = (
                vector.configuration_revisions
            )
            error.configuration_revision_conflict_paths = ()
            raise
        return SimpleNamespace(
            compile_result=compile_result,
            diagnostics=compile_result.diagnostics,
            configuration_trace=SimpleNamespace(revision_vector=()),
        )

    driver = lsp_compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=root.as_uri(),
            initialization_options={"source_roots": (str(root),)},
        ),
        build_in_memory=build,
    )
    text = entry_path.read_text(encoding="utf-8")
    driver.apply_transition(
        lsp_state.open_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            editor_text=text,
            disk_snapshot=lsp_compile_driver.probe_disk_source(entry_path),
        )
    )
    driver.drain()
    return driver, entry_path


def _definition_params(
    path: Path,
    *,
    line: int = 12,
    character: int = 14,
) -> types.DefinitionParams:
    return types.DefinitionParams(
        text_document=types.TextDocumentIdentifier(uri=path.as_uri()),
        position=types.Position(line=line, character=character),
    )


def _document_symbol_params(path: Path) -> types.DocumentSymbolParams:
    return types.DocumentSymbolParams(
        text_document=types.TextDocumentIdentifier(uri=path.as_uri())
    )


def _completion_params(path: Path) -> types.CompletionParams:
    return types.CompletionParams(
        text_document=types.TextDocumentIdentifier(uri=path.as_uri()),
        position=types.Position(line=0, character=0),
    )


def _replace_driver_entry(
    driver: lsp_compile_driver.LspCompileDriver,
    entry: lsp_state.CompileEntryState,
) -> None:
    driver.state = replace(driver.state, entries=(entry,))


def _static_completion_shape(
    driver: lsp_compile_driver.LspCompileDriver,
) -> tuple[tuple[str, types.CompletionItemKind, str, str], ...]:
    return tuple(
        (
            row.label,
            types.CompletionItemKind.Keyword,
            "form",
            row.label,
        )
        for row in driver.frozen_form_completions
    )


def _l5_definition_params_for_kind(
    driver: lsp_compile_driver.LspCompileDriver,
    entry_path: Path,
    reference_kind: str,
) -> types.DefinitionParams:
    entry = driver.state.entries[0]
    snapshot = entry.accepted_snapshot
    assert snapshot is not None
    compile_result = snapshot.build_value.compile_result
    index = _build_index(compile_result)
    link = next(
        row
        for row in index.definition_links
        if (
            row.reference_kind == reference_kind
            and row.canonical_target == "lsp_l5/entry::local-review"
        )
    )
    accepted_text = dict(snapshot.accepted_text_by_path)[entry_path.resolve()]
    position = source_span_to_lsp_range(
        link.reference_span,
        accepted_text,
    )["start"]
    return _definition_params(
        entry_path,
        line=position["line"],
        character=position["character"],
    )


def test_l5_same_visible_label_never_cross_substitutes_prompt_procedure_or_workflow(
    l5_authored_refs_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    links = tuple(
        row
        for row in _build_index(result).definition_links
        if row.canonical_target == "lsp_l5/entry::local-review"
    )
    prompt_span = result.entry_result.prompt_catalog.resolve(
        "local-review"
    ).declaration.span
    procedure_span = _definition_span(
        result,
        callable_name="lsp_l5/entry::local-review",
        kind="procedure",
    )
    workflow_span = _definition_span(
        result,
        callable_name="lsp_l5/entry::local-review",
        kind="workflow",
    )

    assert {
        (row.reference_kind, row.target_kind)
        for row in links
    } == {
        ("prompt-application", "prompt"),
        ("proc-ref", "procedure"),
        ("procedure-call", "procedure"),
        ("workflow-call", "workflow"),
    }
    assert {
        row.reference_kind: row.definition_span
        for row in links
    } == {
        "prompt-application": prompt_span,
        "proc-ref": procedure_span,
        "procedure-call": procedure_span,
        "workflow-call": workflow_span,
    }
    assert prompt_span != procedure_span
    assert procedure_span != workflow_span
    assert prompt_span != workflow_span


@pytest.mark.parametrize(
    ("fixture_root", "entry_relative", "diagnostic_code"),
    (
        (
            L5_PRIVATE_ROOT,
            Path("lsp_l5/entry.orc"),
            "proc_ref_private_import_invalid",
        ),
        (
            L5_AMBIGUOUS_ROOT,
            Path("ambiguous/entry.orc"),
            "module_import_ambiguous",
        ),
    ),
)
def test_l5_private_and_ambiguous_imports_fail_through_compiler_authority(
    tmp_path: Path,
    fixture_root: Path,
    entry_relative: Path,
    diagnostic_code: str,
) -> None:
    root = tmp_path / fixture_root.name
    shutil.copytree(fixture_root, root)
    entry_path = root / entry_relative

    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_stage3_entrypoint(
            entry_path,
            source_roots=(root,),
            provider_externs={"providers.review": "test-provider"},
            prompt_externs={},
            command_boundaries={},
            validate_shared=False,
            workspace_root=root,
            lowering_route="legacy",
        )
    assert diagnostic_code in {
        diagnostic.code for diagnostic in excinfo.value.diagnostics
    }

    driver, entry_path = _compile_driver_for_l5_root(
        root,
        entry_relative=entry_relative,
    )
    entry = driver.state.entries[0]
    server = WorkflowLispLanguageServer()
    server.driver = driver

    assert entry.compile_status == "language_error"
    assert entry.accepted_snapshot is None
    assert diagnostic_code in {
        contribution.code
        for contribution in entry.diagnostic_contributions
    }
    assert lsp_state.current_navigation_snapshot(
        driver.state,
        document_uri=entry_path.as_uri(),
    ) is None
    assert server.definition(
        _definition_params(entry_path, line=0, character=1)
    ) is None


_L5_DEFINITION_PREFLIGHT_STATES = (
    "unavailable",
    "unreadable",
    "dirty",
    "compile_pending",
    "dependency_invalidated",
    "language_failed",
    "server_failed",
    "superseded",
    "closed",
    "unassociated",
    "configuration_stale",
    "source_stale",
    "source_configuration_stale",
    "clean_idle",
    "malformed",
    "navigation_index_failed",
)


@pytest.mark.parametrize("preflight_state", _L5_DEFINITION_PREFLIGHT_STATES)
def test_l5_definition_rows_share_the_complete_current_snapshot_preflight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    preflight_state: str,
) -> None:
    import orchestrator.lsp.server as server_module

    root = tmp_path / "lsp_l5_authored_refs"
    shutil.copytree(L5_AUTHORED_REFS_ROOT, root)
    driver, entry_path = _compile_driver_for_l5_root(root)
    params_by_kind = {
        reference_kind: _l5_definition_params_for_kind(
            driver,
            entry_path,
            reference_kind,
        )
        for reference_kind in (
            "prompt-application",
            "proc-ref",
            "procedure-call",
        )
    }
    server = WorkflowLispLanguageServer()
    server.driver = driver
    server._defer_compiles = True
    monkeypatch.setattr(
        server,
        "_schedule_compile_pump",
        lambda: None,
    )
    assert all(
        server.definition(params) is not None
        for params in params_by_kind.values()
    )
    entry = driver.state.entries[0]
    dependency_path = root / "lsp_l5" / "definitions.orc"

    if preflight_state == "unavailable":
        dependency_path.unlink()
    elif preflight_state == "unreadable":
        original_probe = lsp_compile_driver.probe_disk_source

        def unreadable_probe(path: str | Path) -> object:
            snapshot = original_probe(path)
            if snapshot.canonical_path == dependency_path.resolve():
                return replace(
                    snapshot,
                    revision="unreadable",
                    raw_decoded_text=None,
                )
            return snapshot

        monkeypatch.setattr(
            lsp_compile_driver,
            "probe_disk_source",
            unreadable_probe,
        )
    elif preflight_state == "dirty":
        driver.apply_transition(
            lsp_state.change_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
                editor_text=(entry.editor_text or "") + "\n",
            )
        )
    elif preflight_state == "compile_pending":
        assert entry.disk_snapshot is not None
        driver.apply_transition(
            lsp_state.save_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
                disk_snapshot=entry.disk_snapshot,
            )
        )
    elif preflight_state == "dependency_invalidated":
        dependency_path.write_text(
            dependency_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        driver.apply_transition(driver.observe_disk_path(dependency_path))
    elif preflight_state in {"language_failed", "server_failed"}:
        _replace_driver_entry(
            driver,
            replace(
                entry,
                pending_generation=None,
                compile_status=(
                    "language_error"
                    if preflight_state == "language_failed"
                    else "server_error"
                ),
                accepted_snapshot=None,
                dependency_closure=None,
                dependency_revision_vector=None,
                diagnostic_contributions=(),
            ),
        )
    elif preflight_state == "superseded":
        _replace_driver_entry(
            driver,
            replace(
                entry,
                generation=entry.generation + 1,
                pending_generation=entry.generation,
                compile_status="pending",
            ),
        )
    elif preflight_state == "closed":
        driver.apply_transition(
            lsp_state.close_entry(
                driver.state,
                document_uri=entry_path.as_uri(),
            )
        )
    elif preflight_state == "unassociated":
        params_by_kind = {
            reference_kind: types.DefinitionParams(
                text_document=types.TextDocumentIdentifier(
                    uri=(root / "not-open.orc").as_uri()
                ),
                position=params.position,
            )
            for reference_kind, params in params_by_kind.items()
        }
    elif preflight_state == "configuration_stale":
        driver.apply_transition(
            lsp_state.latch_configuration_stale(driver.state)
        )
    elif preflight_state in {
        "source_stale",
        "source_configuration_stale",
    }:
        dependency_path.write_text(
            dependency_path.read_text(encoding="utf-8") + "\n",
            encoding="utf-8",
        )
        if preflight_state == "source_configuration_stale":
            driver.apply_transition(
                lsp_state.latch_configuration_stale(driver.state)
            )
    elif preflight_state == "clean_idle":
        _replace_driver_entry(
            driver,
            replace(
                entry,
                pending_generation=None,
                compile_status="idle",
                accepted_snapshot=None,
                dependency_closure=None,
                dependency_revision_vector=None,
                diagnostic_contributions=(),
            ),
        )
    elif preflight_state == "malformed":
        driver.state = replace(driver.state, configuration_vector=None)
    else:
        assert preflight_state == "navigation_index_failed"

        def fail_index(*_args: object, **_kwargs: object) -> object:
            raise ValueError("definition occurrence collision")

        monkeypatch.setattr(
            server_module,
            "build_navigation_index",
            fail_index,
        )

    assert {
        reference_kind: server.definition(params)
        for reference_kind, params in params_by_kind.items()
    } == {
        "prompt-application": None,
        "proc-ref": None,
        "procedure-call": None,
    }


@pytest.mark.parametrize(
    "reference_kind",
    ("procedure-call", "prompt-application", "proc-ref"),
)
def test_l5_navigation_index_failure_is_logged_once_and_all_definition_shapes_are_null(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reference_kind: str,
) -> None:
    import orchestrator.lsp.server as server_module

    root = tmp_path / "lsp_l5_authored_refs"
    shutil.copytree(L5_AUTHORED_REFS_ROOT, root)
    driver, entry_path = _compile_driver_for_l5_root(root)
    params = _l5_definition_params_for_kind(
        driver,
        entry_path,
        reference_kind,
    )
    server = WorkflowLispLanguageServer()
    server.driver = driver
    logged: list[types.LogMessageParams] = []
    published: list[types.PublishDiagnosticsParams] = []
    monkeypatch.setattr(server, "window_log_message", logged.append)
    monkeypatch.setattr(
        server,
        "text_document_publish_diagnostics",
        published.append,
    )
    state_before = driver.state
    workspace_before = tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )

    def fail_index(*_args: object, **_kwargs: object) -> object:
        raise ValueError("definition occurrence collision")

    monkeypatch.setattr(
        server_module,
        "build_navigation_index",
        fail_index,
    )

    assert server.definition(params) is None
    assert len(logged) == 1
    assert logged[0].type == types.MessageType.Error
    assert "definition occurrence collision" in logged[0].message
    assert published == []
    assert driver.state is state_before
    assert tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ) == workspace_before


def test_l5_unsupported_generated_and_outside_token_requests_are_null(
    l5_authored_refs_result: LinkedStage3CompileResult,
    callable_result: LinkedStage3CompileResult,
) -> None:
    result = l5_authored_refs_result
    index = _build_index(result)
    accepted_texts = _accepted_texts(result)
    entry_path = L5_AUTHORED_REFS_ENTRY.resolve()
    entry_text = accepted_texts[entry_path]
    exact_links = tuple(
        row
        for row in index.definition_links
        if (
            row.canonical_target == "lsp_l5/entry::local-review"
            and row.reference_kind
            in {"prompt-application", "proc-ref", "procedure-call"}
        )
    )

    for link in exact_links:
        for offset in (
            link.reference_span.start.offset - 1,
            link.reference_span.end.offset,
        ):
            prefix = entry_text[:offset]
            line = prefix.count("\n")
            character = len(
                prefix.rsplit("\n", maxsplit=1)[-1].encode("utf-16-le")
            ) // 2
            assert _definition_at(
                index,
                source_path=entry_path,
                line=line,
                character=character,
                accepted_text_by_path=accepted_texts,
            ) is None

    unsupported_offset = entry_text.index("provider-result")
    unsupported_prefix = entry_text[:unsupported_offset]
    unsupported_line = unsupported_prefix.count("\n")
    unsupported_character = len(
        unsupported_prefix.rsplit("\n", maxsplit=1)[-1].encode("utf-16-le")
    ) // 2
    assert _definition_at(
        index,
        source_path=entry_path,
        line=unsupported_line,
        character=unsupported_character,
        accepted_text_by_path=accepted_texts,
    ) is None

    entry_result = callable_result.compiled_results_by_name["neurips/entry"]
    typed_workflow = entry_result.typed_workflows[0]
    typed_body = typed_workflow.typed_body
    assert isinstance(typed_body.expr, LetStarExpr)
    procedure_call = typed_body.expr.bindings[0][1]
    assert isinstance(procedure_call, ProcedureCallExpr)
    assert procedure_call.authored_callee_span is not None
    generated_entry = replace(
        entry_result,
        typed_workflows=(
            replace(
                typed_workflow,
                typed_body=replace(
                    typed_body,
                    expr=replace(
                        typed_body.expr,
                        bindings=(
                            (
                                "checks",
                                replace(
                                    procedure_call,
                                    authored_callee_span=None,
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    )
    generated_result = replace(
        callable_result,
        entry_result=generated_entry,
        compiled_results_by_name={
            **callable_result.compiled_results_by_name,
            "neurips/entry": generated_entry,
        },
    )
    call_position = source_span_to_lsp_range(
        procedure_call.authored_callee_span,
        _accepted_texts(callable_result)[CALLABLE_ENTRY.resolve()],
    )["start"]
    assert _definition_at(
        _build_index(generated_result),
        source_path=CALLABLE_ENTRY.resolve(),
        line=call_position["line"],
        character=call_position["character"],
        accepted_text_by_path=_accepted_texts(generated_result),
    ) is None


def test_success_snapshot_freezes_postflight_text_for_every_trace_path(
    tmp_path: Path,
) -> None:
    root = tmp_path / "callables"
    shutil.copytree(CALLABLE_ROOT, root)

    driver, _entry_path, _calls = _compile_driver_for_callable_root(root)

    snapshot = driver.state.entries[0].accepted_snapshot
    assert snapshot is not None
    assert snapshot.accepted_text_by_path == tuple(
        (
            path,
            path.read_text(encoding="utf-8"),
        )
        for path, _revision in snapshot.source_revision_vector
    )


def test_server_navigation_translates_only_from_current_frozen_snapshot(
    tmp_path: Path,
) -> None:
    root = tmp_path / "callables"
    shutil.copytree(CALLABLE_ROOT, root)
    driver, entry_path, _calls = _compile_driver_for_callable_root(root)
    server = WorkflowLispLanguageServer()
    server.driver = driver
    expected_proc_span = _definition_span(
        driver.state.entries[0].accepted_snapshot.build_value.compile_result,
        callable_name="neurips/procedures::build-checks",
        kind="procedure",
    )

    location = server.definition(_definition_params(entry_path))
    symbols = server.document_symbols(_document_symbol_params(entry_path))
    completions = server.completion(_completion_params(entry_path))

    assert location == types.Location(
        uri=Path(expected_proc_span.start.path).resolve().as_uri(),
        range=types.Range(
            start=types.Position(
                **source_span_to_lsp_range(
                    expected_proc_span,
                    Path(expected_proc_span.start.path).read_text(
                        encoding="utf-8"
                    ),
                )["start"]
            ),
            end=types.Position(
                **source_span_to_lsp_range(
                    expected_proc_span,
                    Path(expected_proc_span.start.path).read_text(
                        encoding="utf-8"
                    ),
                )["end"]
            ),
        ),
    )
    assert tuple(symbol.name for symbol in symbols or ()) == (
        "neurips/entry",
        "orchestrate",
    )
    assert completions is not None
    assert completions.is_incomplete is False
    assert "build-checks" in {
        item.label for item in completions.items
    }


@pytest.mark.parametrize(
    "recovery_status",
    (
        "dirty-idle",
        "current-pending",
        "language-error",
        "server-error",
    ),
)
def test_server_completion_returns_only_frozen_forms_for_valid_recovery(
    tmp_path: Path,
    recovery_status: str,
) -> None:
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    current_entry = driver.state.entries[0]
    disk_snapshot = current_entry.disk_snapshot
    assert disk_snapshot is not None
    assert disk_snapshot.raw_decoded_text is not None
    common = {
        "accepted_snapshot": None,
        "dependency_closure": None,
        "dependency_revision_vector": None,
        "diagnostic_contributions": (),
    }
    if recovery_status == "dirty-idle":
        recovery_entry = replace(
            current_entry,
            editor_text=disk_snapshot.raw_decoded_text + "\n",
            generation=current_entry.generation + 1,
            pending_generation=None,
            buffer_status="dirty",
            compile_status="idle",
            **common,
        )
    elif recovery_status == "current-pending":
        pending = lsp_state.save_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
            disk_snapshot=disk_snapshot,
        )
        driver.apply_transition(pending)
        recovery_entry = None
    else:
        recovery_entry = replace(
            current_entry,
            pending_generation=None,
            buffer_status="clean",
            compile_status=(
                "language_error"
                if recovery_status == "language-error"
                else "server_error"
            ),
            **common,
        )
    if recovery_entry is not None:
        _replace_driver_entry(driver, recovery_entry)
    server = WorkflowLispLanguageServer()
    server.driver = driver

    completion = server.completion(_completion_params(entry_path))

    assert completion.is_incomplete is True
    assert tuple(
        (item.label, item.kind, item.detail, item.sort_text)
        for item in completion.items
    ) == _static_completion_shape(driver)
    assert all(item.data is None for item in completion.items)
    assert all(item.insert_text is None for item in completion.items)
    assert all(item.text_edit is None for item in completion.items)
    assert all("procedure" not in item.detail for item in completion.items)
    assert all("workflow" not in item.detail for item in completion.items)
    assert "review" not in {
        item.label
        for item in completion.items
        if item.detail != "form"
    }
    if recovery_status == "current-pending":
        assert driver.state.entries[0].compile_status == "success"


@pytest.mark.parametrize(
    "closed_status",
    (
        "configuration-stale",
        "unavailable",
        "unassociated",
        "closed",
        "clean-idle",
        "malformed",
    ),
)
def test_server_completion_returns_exact_empty_for_closed_l2_states(
    tmp_path: Path,
    closed_status: str,
) -> None:
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    entry = driver.state.entries[0]
    disk_snapshot = entry.disk_snapshot
    assert disk_snapshot is not None
    assert disk_snapshot.raw_decoded_text is not None
    requested_path = entry_path
    if closed_status == "configuration-stale":
        driver.state = replace(driver.state, configuration_stale=True)
    elif closed_status == "unavailable":
        _replace_driver_entry(
            driver,
            replace(
                entry,
                disk_snapshot=replace(
                    disk_snapshot,
                    revision="missing",
                    raw_decoded_text=None,
                ),
                accepted_snapshot=None,
                pending_generation=None,
                buffer_status="unavailable",
                compile_status="idle",
                dependency_closure=None,
                dependency_revision_vector=None,
                diagnostic_contributions=(),
            ),
        )
    elif closed_status == "unassociated":
        requested_path = root / "not-open.orc"
    elif closed_status == "closed":
        driver.state = lsp_state.close_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
        ).state
    elif closed_status == "clean-idle":
        _replace_driver_entry(
            driver,
            replace(
                entry,
                accepted_snapshot=None,
                pending_generation=None,
                compile_status="idle",
                dependency_closure=None,
                dependency_revision_vector=None,
                diagnostic_contributions=(),
            ),
        )
    else:
        _replace_driver_entry(
            driver,
            replace(
                entry,
                editor_text=disk_snapshot.raw_decoded_text,
                accepted_snapshot=None,
                pending_generation=None,
                buffer_status="dirty",
                compile_status="idle",
                dependency_closure=None,
                dependency_revision_vector=None,
                diagnostic_contributions=(),
            ),
        )
    server = WorkflowLispLanguageServer()
    server.driver = driver

    completion = server.completion(_completion_params(requested_path))

    assert completion.is_incomplete is False
    assert tuple(completion.items) == ()


def test_current_success_index_failure_never_falls_back_to_static_completion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import orchestrator.lsp.server as server_module

    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    server = WorkflowLispLanguageServer()
    server.driver = driver
    logged: list[types.LogMessageParams] = []
    monkeypatch.setattr(server, "window_log_message", logged.append)

    def fail_index(*_args: object, **_kwargs: object) -> object:
        raise ValueError("candidate index is invalid")

    monkeypatch.setattr(
        server_module,
        "build_navigation_index",
        fail_index,
    )

    def unexpected_static_fallback(*_args: object, **_kwargs: object) -> str:
        pytest.fail("current-success index failure selected static completion")

    monkeypatch.setattr(
        server_module,
        "classify_completion_recovery",
        unexpected_static_fallback,
        raising=False,
    )

    completion = server.completion(_completion_params(entry_path))

    assert completion.is_incomplete is False
    assert tuple(completion.items) == ()
    assert len(logged) == 1
    assert "candidate index is invalid" in logged[0].message


def test_completion_preflight_failure_is_logged_once_and_returns_exact_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    entry = driver.state.entries[0]
    disk_snapshot = entry.disk_snapshot
    assert disk_snapshot is not None
    assert disk_snapshot.raw_decoded_text is not None
    _replace_driver_entry(
        driver,
        replace(
            entry,
            editor_text=disk_snapshot.raw_decoded_text + "\n",
            generation=entry.generation + 1,
            pending_generation=None,
            buffer_status="dirty",
            compile_status="idle",
            accepted_snapshot=None,
            dependency_closure=None,
            dependency_revision_vector=None,
            diagnostic_contributions=(),
        ),
    )
    driver.state = replace(driver.state, configuration_vector=None)
    server = WorkflowLispLanguageServer()
    server.driver = driver
    logged: list[types.LogMessageParams] = []
    monkeypatch.setattr(server, "window_log_message", logged.append)
    driver._log_server_error = server.log_internal_error

    completion = server.completion(_completion_params(entry_path))

    assert completion.is_incomplete is False
    assert tuple(completion.items) == ()
    assert len(logged) == 1
    assert logged[0].type == types.MessageType.Error
    assert logged[0].message == (
        "RuntimeError: compile driver state has no configuration vector"
    )


def test_full_and_recovery_completion_ignore_post_init_registry_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = import_module("orchestrator.workflow_lisp.form_registry")
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    frozen_labels = tuple(row.label for row in driver.frozen_form_completions)
    form_spec = registry.get_form_spec("defproc")
    assert form_spec is not None
    monkeypatch.setitem(registry._FORM_REGISTRY, "zz-late-form", form_spec)
    server = WorkflowLispLanguageServer()
    server.driver = driver

    full = server.completion(_completion_params(entry_path))
    entry = driver.state.entries[0]
    disk_snapshot = entry.disk_snapshot
    assert disk_snapshot is not None
    assert disk_snapshot.raw_decoded_text is not None
    _replace_driver_entry(
        driver,
        replace(
            entry,
            editor_text=disk_snapshot.raw_decoded_text + "\n",
            generation=entry.generation + 1,
            pending_generation=None,
            buffer_status="dirty",
            compile_status="idle",
            accepted_snapshot=None,
            dependency_closure=None,
            dependency_revision_vector=None,
            diagnostic_contributions=(),
        ),
    )
    recovery = server.completion(_completion_params(entry_path))

    assert tuple(
        item.label
        for item in full.items
        if item.kind == types.CompletionItemKind.Keyword
    ) == frozen_labels
    assert recovery.is_incomplete is True
    assert tuple(item.label for item in recovery.items) == frozen_labels
    assert "zz-late-form" not in {
        item.label for item in (*full.items, *recovery.items)
    }


def test_server_presents_ten_symbol_kinds_and_exact_selection_ranges(
    tmp_path: Path,
) -> None:
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    server = WorkflowLispLanguageServer()
    server.driver = driver
    snapshot = driver.state.entries[0].accepted_snapshot
    assert snapshot is not None
    compile_result = snapshot.build_value.compile_result
    resolved_source = compile_result.graph.modules_by_name[
        compile_result.graph.entry_module_name
    ]
    projection = import_module(
        "orchestrator.workflow_lisp.authored_symbols"
    ).project_authored_symbols(
        resolved_source,
        compile_result.entry_result,
    )
    accepted_text = dict(snapshot.accepted_text_by_path)[entry_path.resolve()]

    symbols = server.document_symbols(_document_symbol_params(entry_path))

    assert symbols is not None
    assert tuple(symbol.kind for symbol in symbols) == (
        types.SymbolKind.Module,
        types.SymbolKind.Enum,
        types.SymbolKind.Class,
        types.SymbolKind.Interface,
        types.SymbolKind.Struct,
        types.SymbolKind.Enum,
        types.SymbolKind.Object,
        types.SymbolKind.Event,
        types.SymbolKind.Function,
        types.SymbolKind.Function,
        types.SymbolKind.Function,
        types.SymbolKind.Function,
        types.SymbolKind.Function,
        types.SymbolKind.Function,
    )
    assert tuple(symbol.name for symbol in symbols) == tuple(
        row.name for row in projection
    )
    for symbol, row in zip(symbols, projection, strict=True):
        assert symbol.range == types.Range(
            **{
                endpoint: types.Position(**position)
                for endpoint, position in source_span_to_lsp_range(
                    row.definition_span,
                    accepted_text,
                ).items()
            }
        )
        assert symbol.selection_range == types.Range(
            **{
                endpoint: types.Position(**position)
                for endpoint, position in source_span_to_lsp_range(
                    row.selection_span,
                    accepted_text,
                ).items()
            }
        )
        assert symbol.range != symbol.selection_range


@pytest.mark.parametrize("invalid_range", ("definition", "selection"))
def test_server_returns_null_if_either_symbol_range_cannot_be_translated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_range: str,
) -> None:
    import orchestrator.lsp.server as server_module

    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    server = WorkflowLispLanguageServer()
    server.driver = driver
    snapshot = driver.state.entries[0].accepted_snapshot
    assert snapshot is not None
    index = _build_index(snapshot.build_value.compile_result)
    symbol = _symbols(index, entry_path.resolve())[0]
    span_name = f"{invalid_range}_span"
    span = getattr(symbol, span_name)
    invalid_span = replace(
        span,
        end=replace(span.end, offset=len(entry_path.read_text()) + 1),
    )
    invalid_symbol = replace(symbol, **{span_name: invalid_span})
    monkeypatch.setattr(
        server_module,
        "symbols_for_document",
        lambda *_args, **_kwargs: (invalid_symbol,),
    )

    assert server.document_symbols(
        _document_symbol_params(entry_path)
    ) is None


@pytest.mark.parametrize(
    "request_kind",
    ("definition", "document_symbols", "completion"),
)
def test_projection_crosscheck_failure_is_one_internal_error_and_null_or_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    request_kind: str,
) -> None:
    navigation = _navigation_surface()
    projection_module = import_module(
        "orchestrator.workflow_lisp.authored_symbols"
    )
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    server = WorkflowLispLanguageServer()
    server.driver = driver
    logged: list[types.LogMessageParams] = []
    published: list[types.PublishDiagnosticsParams] = []
    monkeypatch.setattr(server, "window_log_message", logged.append)
    monkeypatch.setattr(
        server,
        "text_document_publish_diagnostics",
        published.append,
    )
    state_before = driver.state
    workspace_before = tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    )

    def fail_projection(*args: object, **kwargs: object) -> object:
        raise projection_module.AuthoredSymbolProjectionError(
            "test crosscheck mismatch"
        )

    monkeypatch.setattr(
        navigation,
        "project_authored_symbols",
        fail_projection,
        raising=False,
    )

    if request_kind == "definition":
        assert server.definition(_definition_params(entry_path)) is None
    elif request_kind == "document_symbols":
        assert server.document_symbols(
            _document_symbol_params(entry_path)
        ) is None
    else:
        completion = server.completion(_completion_params(entry_path))
        assert completion.is_incomplete is False
        assert tuple(completion.items) == ()
    assert len(logged) == 1
    assert logged[0].type == types.MessageType.Error
    assert "AuthoredSymbolProjectionError" in logged[0].message
    assert published == []
    assert driver.state is state_before
    assert tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ) == workspace_before


@pytest.mark.parametrize(
    "status",
    (
        "dirty",
        "pending",
        "dependency_invalidated",
        "language_failed",
        "server_failed",
        "superseded",
        "closed",
        "configuration_stale",
        "source_stale",
        "source_configuration_stale",
        "unassociated",
    ),
)
def test_server_navigation_never_serves_a_non_current_snapshot(
    tmp_path: Path,
    status: str,
) -> None:
    root = tmp_path / "lsp_l1_symbols"
    shutil.copytree(L1_SYMBOLS_ROOT, root)
    driver, entry_path = _compile_driver_for_l1_symbols_root(root)
    entry = driver.state.entries[0]
    retained_snapshot = entry.accepted_snapshot
    assert retained_snapshot is not None
    server = WorkflowLispLanguageServer()
    server.driver = driver

    current_definition = server.definition(
        _definition_params(entry_path, line=75, character=5)
    )
    current_symbols = server.document_symbols(
        _document_symbol_params(entry_path)
    )
    current_completion = server.completion(_completion_params(entry_path))
    current_index = _build_index(
        retained_snapshot.build_value.compile_result
    )

    assert current_definition is not None
    assert tuple(symbol.name for symbol in current_symbols or ()) == (
        "lsp_l1_symbols/entry",
        "ReviewDecision",
        "ReportPath",
        "CommonFields",
        "ReviewState",
        "ReviewOutcome",
        "review-state",
        "record-review",
        "default-status",
        "normalize-status",
        "render-and-preserve",
        "default-review",
        "review",
        "review-many",
    )
    assert current_completion.is_incomplete is False
    assert tuple(
        (item.label, item.kind, item.detail)
        for item in current_completion.items
    ) == tuple(
        (
            item.label,
            (
                types.CompletionItemKind.Function
                if item.kind in {"procedure", "workflow"}
                else types.CompletionItemKind.Keyword
            ),
            item.detail,
        )
        for item in _completions(current_index, entry_path)
    )

    requested_path = entry_path
    if status == "dirty":
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    buffer_status="dirty",
                    compile_status="idle",
                ),
            ),
        )
    elif status in {"pending", "dependency_invalidated", "superseded"}:
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    generation=entry.generation + 1,
                    pending_generation=entry.generation + 1,
                    compile_status="pending",
                ),
            ),
        )
    elif status == "language_failed":
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    compile_status="language_error",
                ),
            ),
        )
    elif status == "server_failed":
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    compile_status="server_error",
                ),
            ),
        )
    elif status == "closed":
        driver.state = lsp_state.close_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
        ).state
    elif status == "configuration_stale":
        driver.state = replace(driver.state, configuration_stale=True)
    elif status in {"source_stale", "source_configuration_stale"}:
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    buffer_status="unavailable",
                    compile_status="idle",
                ),
            ),
            configuration_stale=status == "source_configuration_stale",
        )
    elif status == "unassociated":
        requested_path = root / "not-open.orc"

    assert server.definition(
        _definition_params(requested_path, line=75, character=5)
    ) is None
    assert server.document_symbols(
        _document_symbol_params(requested_path)
    ) is None
    completion = server.completion(_completion_params(requested_path))
    assert completion is not None
    assert completion.is_incomplete is False
    assert tuple(completion.items) == ()


def test_notification_free_source_drift_returns_null_and_recompiles(
    tmp_path: Path,
) -> None:
    root = tmp_path / "callables"
    shutil.copytree(CALLABLE_ROOT, root)
    driver, entry_path, build_calls = _compile_driver_for_callable_root(root)
    helper_path = root / "neurips" / "helper.orc"
    helper_path.write_text(
        helper_path.read_text(encoding="utf-8") + "\n",
        encoding="utf-8",
    )
    server = WorkflowLispLanguageServer()
    server.driver = driver

    response = server.definition(_definition_params(entry_path))

    assert response is None
    assert build_calls == [1, 2]
    assert driver.state.entries[0].compile_status == "success"
    assert driver.queued_generations == ()


def test_notification_free_configuration_drift_emits_one_restart_notice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    entry_path = root / "entry.orc"
    text = (
        "(workflow-lisp\n"
        '  (:language "0.1")\n'
        '  (:target-dsl "2.14"))\n'
    )
    entry_path.write_text(text, encoding="utf-8")
    provider_path = root / "providers.json"
    provider_path.write_text("{}\n", encoding="utf-8")
    driver = lsp_compile_driver.initialize_compile_driver(
        lsp_state.initialize_lsp_state(
            root_uri=root.as_uri(),
            initialization_options={
                "provider_externs_path": str(provider_path),
            },
        )
    )
    provider_path.write_text("{ }\n", encoding="utf-8")
    server = WorkflowLispLanguageServer()
    server.driver = driver
    shown: list[object] = []
    logged: list[object] = []
    monkeypatch.setattr(server, "window_show_message", shown.append)
    monkeypatch.setattr(server, "window_log_message", logged.append)

    first = server.completion(_completion_params(entry_path))
    second = server.completion(_completion_params(entry_path))

    assert first is not None and tuple(first.items) == ()
    assert second is not None and tuple(second.items) == ()
    assert len(shown) == 1
    assert len(logged) == 1
    assert driver.state.configuration_stale is True
