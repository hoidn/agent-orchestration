"""Closed-matrix navigation tests for the Workflow Lisp language server."""

from __future__ import annotations

from dataclasses import replace
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
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import (
    CallExpr,
    LetStarExpr,
    ProcedureCallExpr,
)
from orchestrator.workflow_lisp.spans import SourceSpan
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
STDLIB_CALLER = FIXTURES / "valid" / "minimal_caller_finalize_selected_item.orc"


def _navigation_surface() -> object:
    try:
        return import_module("orchestrator.lsp.navigation")
    except ModuleNotFoundError:
        pytest.fail("orchestrator.lsp.navigation is not implemented")


def _build_index(result: LinkedStage3CompileResult) -> object:
    build_index = getattr(_navigation_surface(), "build_navigation_index", None)
    assert callable(build_index), "build_navigation_index is missing"
    return build_index(result)


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


def test_completion_is_exact_visible_callable_and_registered_form_union(
    callable_result: LinkedStage3CompileResult,
) -> None:
    registry = import_module("orchestrator.workflow_lisp.form_registry")
    registered_form_heads = getattr(registry, "registered_form_heads", None)
    assert callable(registered_form_heads), "registered_form_heads is missing"
    expected_callables = {
        "orchestrate",
        "proc.build-checks",
        "neurips/procedures/build-checks",
        "build-checks",
        "helper.provider-attempt",
        "neurips/helper/provider-attempt",
        "provider-attempt",
        "helper.secondary",
        "neurips/helper/secondary",
        "secondary",
    }

    completions = _completions(
        _build_index(callable_result),
        CALLABLE_ENTRY.resolve(),
    )

    assert tuple(item.label for item in completions) == tuple(
        sorted(expected_callables | set(registered_form_heads()))
    )
    assert {
        item.label
        for item in completions
        if item.kind == "callable"
    } == expected_callables
    assert {
        item.label
        for item in completions
        if item.kind == "form"
    } == set(registered_form_heads()) - expected_callables


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


def test_projection_crosscheck_failure_is_one_internal_error_and_null(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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

    assert server.document_symbols(
        _document_symbol_params(entry_path)
    ) is None
    assert len(logged) == 1
    assert logged[0].type == types.MessageType.Error
    assert "AuthoredSymbolProjectionError" in logged[0].message
    assert published == []
    assert driver.state is state_before


@pytest.mark.parametrize(
    "status",
    (
        "dirty",
        "pending",
        "invalidated",
        "configuration_stale",
        "language_failed",
        "server_failed",
        "superseded",
        "closed",
        "unassociated",
    ),
)
def test_server_navigation_never_serves_a_non_current_snapshot(
    tmp_path: Path,
    status: str,
) -> None:
    root = tmp_path / "callables"
    shutil.copytree(CALLABLE_ROOT, root)
    driver, entry_path, _calls = _compile_driver_for_callable_root(root)
    entry = driver.state.entries[0]
    requested_path = entry_path
    if status == "dirty":
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    buffer_status="dirty",
                    compile_status="idle",
                    accepted_snapshot=None,
                ),
            ),
        )
    elif status in {"pending", "invalidated", "superseded"}:
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    generation=entry.generation + 1,
                    pending_generation=entry.generation + 1,
                    compile_status="pending",
                    accepted_snapshot=None,
                ),
            ),
        )
    elif status == "configuration_stale":
        driver.state = lsp_state.latch_configuration_stale(driver.state).state
    elif status == "language_failed":
        driver.state = replace(
            driver.state,
            entries=(
                replace(
                    entry,
                    compile_status="language_error",
                    accepted_snapshot=None,
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
                    accepted_snapshot=None,
                ),
            ),
        )
    elif status == "closed":
        driver.state = lsp_state.close_entry(
            driver.state,
            document_uri=entry_path.as_uri(),
        ).state
    elif status == "unassociated":
        requested_path = root / "not-open.orc"

    server = WorkflowLispLanguageServer()
    server.driver = driver

    assert server.definition(_definition_params(requested_path)) is None
    assert server.document_symbols(
        _document_symbol_params(requested_path)
    ) is None
    completion = server.completion(_completion_params(requested_path))
    assert completion is not None
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
