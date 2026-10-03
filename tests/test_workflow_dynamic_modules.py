"""Selective old-source declaration linking for dynamic workflow preparation."""

from __future__ import annotations

from pathlib import Path

import pytest

import orchestrator.workflow_lisp.compiler as compiler
import orchestrator.workflow_lisp.macros as macros
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.modules import resolve_module_graph
from orchestrator.workflow_lisp.prompts import elaborate_prompt_definitions
from orchestrator.workflow_lisp.syntax import syntax_head_name, syntax_node_datum


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "workflow_lisp"
MODULE_FIXTURES = FIXTURE_ROOT / "dynamic" / "modules"
STDLIB_ROOT = Path(__file__).parents[1] / "orchestrator" / "workflow_lisp" / "stdlib_modules"


def test_selected_imports_filter_before_macro_and_type_elaboration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry_path = MODULE_FIXTURES / "entry.orc"
    selected_path = MODULE_FIXTURES / "selected.orc"

    with pytest.raises(LispFrontendCompileError) as baseline:
        compiler.compile_stage1_entrypoint(
            entry_path,
            source_roots=(FIXTURE_ROOT, STDLIB_ROOT),
        )
    assert any(
        diagnostic.code == "type_unknown"
        for diagnostic in baseline.value.diagnostics
    )

    def reject_unselected_macro(form, datum):
        if (
            form.module_path == str(selected_path)
            and syntax_head_name(datum) == "defmacro"
        ):
            raise AssertionError("unselected macro reached macro collection")
        return original_macro_elaborator(form, datum)

    original_macro_elaborator = macros._elaborate_macro_definition
    monkeypatch.setattr(macros, "_elaborate_macro_definition", reject_unselected_macro)
    monkeypatch.setattr(
        compiler,
        "elaborate_procedure_definitions",
        lambda *args, **kwargs: pytest.fail("executable definitions were elaborated"),
    )
    trace = SourceReadTrace()
    select = getattr(compiler, "_compile_stage1_selected_declarations_entrypoint", None)
    assert callable(select), "selective declaration compiler seam is missing"

    result = select(
        entry_path,
        source_roots=(FIXTURE_ROOT, STDLIB_ROOT),
        source_read_trace=trace,
    )

    assert tuple(
        definition.name
        for definition in result.compiled_modules_by_name["std/improve"].definitions
    ) == ("Decision", "Improvement")
    assert tuple(
        definition.name
        for definition in result.compiled_modules_by_name[
            "dynamic/modules/selected"
        ].definitions
    ) == ("Feedback", "Blocker", "Selected")
    selected_heads = tuple(
        syntax_head_name(syntax_node_datum(form))
        for form in result.graph.modules_by_name[
            "dynamic/modules/selected"
        ].syntax_module.forms
    )
    assert selected_heads == ("defrecord", "defrecord", "defrecord")
    assert result.graph.modules_by_name["std/improve"].path == (
        STDLIB_ROOT / "std" / "improve.orc"
    )
    assert result.graph.modules_by_name["std/improve"].syntax_module.module_name == (
        "std/improve"
    )
    assert result.compiled_modules_by_name["std/improve"].definitions
    assert result.compiled_modules_by_name["std/improve"].definitions[0].span.start.path == str(
        STDLIB_ROOT / "std" / "improve.orc"
    )
    compiler.linked_module_type_environment(result, "dynamic/modules/selected")
    assert trace.raw_bytes_by_path[selected_path.resolve()] == selected_path.read_bytes()
    assert not trace.revision_conflict_paths


@pytest.mark.parametrize(
    "entry_name",
    ("entry_proc.orc", "entry_workflow.orc", "entry_macro.orc", "entry_proc_ref.orc"),
)
def test_selected_executable_or_procedure_reference_is_refused(entry_name: str) -> None:
    entry_path = MODULE_FIXTURES / entry_name
    select = getattr(compiler, "_compile_stage1_selected_declarations_entrypoint", None)
    assert callable(select), "selective declaration compiler seam is missing"

    with pytest.raises(LispFrontendCompileError) as exc_info:
        select(entry_path, source_roots=(FIXTURE_ROOT, STDLIB_ROOT))

    assert exc_info.value.diagnostics[0].code == "dynamic_import_incompatible"
    assert exc_info.value.diagnostics[0].span.start.path == str(
        STDLIB_ROOT / "std" / "improve.orc"
        if entry_name == "entry_proc.orc"
        else MODULE_FIXTURES / "selected.orc"
    )


def test_selected_prompt_keeps_its_path_and_type_dependencies() -> None:
    entry_path = MODULE_FIXTURES / "entry_prompt.orc"
    selected_path = MODULE_FIXTURES / "selected.orc"
    select = getattr(compiler, "_compile_stage1_selected_declarations_entrypoint", None)
    assert callable(select), "selective declaration compiler seam is missing"

    result = select(
        entry_path,
        source_roots=(FIXTURE_ROOT, STDLIB_ROOT),
        source_read_trace=SourceReadTrace(),
    )

    selected_source = result.graph.modules_by_name[
        "dynamic/modules/selected"
    ].syntax_module
    assert tuple(syntax_head_name(syntax_node_datum(form)) for form in selected_source.forms) == (
        "defrecord",
        "defpath",
        "defprompt",
    )
    assert tuple(
        definition.name
        for definition in result.compiled_modules_by_name[
            "dynamic/modules/selected"
        ].definitions
    ) == ("Feedback", "PromptPath")
    assert "PromptWithTypes" in result.graph.export_surfaces_by_name[
        "dynamic/modules/selected"
    ].prompts_by_name
    assert all(form.module_path == str(selected_path) for form in selected_source.forms)

    original = resolve_module_graph(entry_path, source_roots=(FIXTURE_ROOT, STDLIB_ROOT))
    owner = result.graph.modules_by_name["dynamic/modules/selected"]
    original_owner = original.modules_by_name[owner.module_name]
    assert (owner.path, owner.source_root) == (original_owner.path, original_owner.source_root)
    assert owner.path.parent == selected_path.parent
    for form in selected_source.forms:
        original_form = next(item for item in original_owner.syntax_module.forms if item.form_path == form.form_path)
        assert form == original_form  # Full spans and nested prompt/path locations survive filtering.
    assert elaborate_prompt_definitions(selected_source) == elaborate_prompt_definitions(original_owner.syntax_module)
    path_definition = next(item for item in result.compiled_modules_by_name[owner.module_name].definitions if item.name == "PromptPath")
    path_form = next(item for item in selected_source.forms if syntax_head_name(syntax_node_datum(item)) == "defpath")
    assert path_definition.span == path_form.span
    assert path_definition.under == "artifacts/prompt"


def _write_module(root: Path, name: str, body: str) -> Path:
    path = root / f"{name}.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'(workflow-lisp (:language "0.1") (:target-dsl "2.35") (defmodule {name}) {body})', encoding="utf-8")
    return path


def test_selected_transitive_schema_closure_keeps_self_qualified_private_type(tmp_path: Path) -> None:
    entry = _write_module(tmp_path, "review/entry", "(import review/helper :as helper :only (Public))")
    _write_module(tmp_path, "review/helper", """
      (import review/middle :as middle :only (Extended))
      (export Public)
      (defrecord Private (x Int))
      (defrecord Public (:include middle.Extended) (payload review/helper/Private))
    """)
    _write_module(tmp_path, "review/middle", """
      (import review/base :only (Fields))
      (export Extended)
      (defschema Extended (:include Fields) (status Bool))
    """)
    _write_module(tmp_path, "review/base", "(export Fields) (defschema Fields (message String))")
    baseline = compiler.compile_stage1_entrypoint(entry, source_roots=(tmp_path,))
    compiler.linked_module_type_environment(baseline, "review/helper")

    result = compiler._compile_stage1_selected_declarations_entrypoint(entry, source_roots=(tmp_path,))

    assert result.compiled_modules_by_name["review/helper"].definitions == baseline.compiled_modules_by_name["review/helper"].definitions
    assert result.compiled_modules_by_name["review/middle"].schemas == baseline.compiled_modules_by_name["review/middle"].schemas
    assert result.compiled_modules_by_name["review/base"].schemas == baseline.compiled_modules_by_name["review/base"].schemas
    compiler.linked_module_type_environment(result, "review/helper")


def test_selected_indirect_proc_ref_dependency_reports_import_chain(tmp_path: Path) -> None:
    entry = _write_module(tmp_path, "review/entry", "(import review/helper :only (Public))")
    _write_module(tmp_path, "review/helper", """
      (import review/base :only (Callback))
      (export Public)
      (defrecord Public (payload Callback))
    """)
    owner = _write_module(tmp_path, "review/base", "(export Callback) (defrecord Callback (function ProcRef[(Int) -> Int]))")

    with pytest.raises(LispFrontendCompileError) as error:
        compiler._compile_stage1_selected_declarations_entrypoint(entry, source_roots=(tmp_path,))

    diagnostic = error.value.diagnostics[0]
    assert diagnostic.code == "dynamic_import_incompatible"
    assert diagnostic.span.start.path == diagnostic.span.end.path == str(owner)
    assert "review/entry -> review/helper::Public -> review/base::Callback" in diagnostic.message


def test_selected_trace_rereads_one_canonical_source_and_rejects_changed_bytes(tmp_path: Path) -> None:
    entry = _write_module(tmp_path, "review/entry", "(import review/helper :only (Public)) (import review/middle :only (Other))")
    _write_module(tmp_path, "review/middle", "(import review/helper :as helper :only (Public)) (export Other) (defrecord Other (x helper.Public))")
    helper = _write_module(tmp_path, "review/helper", "(export Public) (defrecord Public (x Int))")
    trace = SourceReadTrace()
    select = compiler._compile_stage1_selected_declarations_entrypoint
    first = select(entry, source_roots=(tmp_path,), source_read_trace=trace)
    second = select(entry, source_roots=(tmp_path,), source_read_trace=trace)

    assert first.entry_module.module_name == second.entry_module.module_name
    assert set(trace.raw_bytes_by_path) == {entry.resolve(), helper.resolve(), (tmp_path / "review/middle.orc").resolve()}
    assert trace.raw_bytes_by_path[helper.resolve()] == helper.read_bytes()
    helper_records = [record for record in trace.records if record.canonical_path == helper.resolve()]
    assert len(helper_records) == 4  # The shared diamond member is physically reread in each graph.
    assert len({record.revision for record in helper_records}) == 1
    assert not trace.revision_conflict_paths
    original_bytes = helper.read_bytes()
    helper.write_bytes(original_bytes + b"\r\n; newer snapshot\r\n")

    with pytest.raises(RuntimeError, match="changed during one compiler read trace"):
        select(entry, source_roots=(tmp_path,), source_read_trace=trace)

    assert trace.revision_conflict_paths == (helper.resolve(),)
    assert trace.raw_bytes_by_path[helper.resolve()] == original_bytes


def test_selected_trace_includes_source_root_inference_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = _write_module(tmp_path, "review/entry", "(defrecord Public (x Int))")
    original_bytes = entry.read_bytes()
    read_bytes = Path.read_bytes
    reads = 0

    def rewrite_after_first_read(path: Path) -> bytes:
        nonlocal reads
        raw = read_bytes(path)
        if path.resolve() == entry.resolve():
            reads += 1
            if reads == 1:
                path.write_bytes(raw + b"\n; newer source after root inference\n")
        return raw

    monkeypatch.setattr(Path, "read_bytes", rewrite_after_first_read)
    trace = SourceReadTrace()

    with pytest.raises(RuntimeError, match="changed during one compiler read trace"):
        compiler._compile_stage1_selected_declarations_entrypoint(entry, source_read_trace=trace)

    assert reads == 2
    assert trace.revision_conflict_paths == (entry.resolve(),)
    assert trace.raw_bytes_by_path[entry.resolve()] == original_bytes


@pytest.mark.parametrize("reference", ["Payload", "helper.Payload", "review/helper/Payload"])
def test_selected_alias_import_preserves_qualified_only_visibility(tmp_path: Path, reference: str) -> None:
    entry = _write_module(tmp_path, "review/entry", f"""
      (import review/helper :as helper)
      (defrecord Public (payload {reference}))
    """)
    _write_module(tmp_path, "review/helper", "(export Payload) (defrecord Payload (x Int))")
    for compile_entrypoint in (
        compiler.compile_stage1_entrypoint,
        compiler._compile_stage1_selected_declarations_entrypoint,
    ):
        if reference == "Payload":
            with pytest.raises(LispFrontendCompileError) as error:
                result = compile_entrypoint(entry, source_roots=(tmp_path,))
                compiler.linked_module_type_environment(result, "review/entry")
            assert error.value.diagnostics[0].code == "type_unknown"
        else:
            result = compile_entrypoint(entry, source_roots=(tmp_path,))
            compiler.linked_module_type_environment(result, "review/entry")
            assert result.entry_module.imports[0].only == ()


@pytest.mark.parametrize(
    "fixture,entry",
    [
        ("alias_only", "neurips/default_alias"),
        ("alias_only", "neurips/only_binding"),
        ("schema_import", "neurips/entry"),
        ("schema_reexport_import", "neurips/entry"),
    ],
)
def test_selected_loader_reuses_existing_valid_module_contracts(fixture: str, entry: str) -> None:
    root = FIXTURE_ROOT / "modules" / "valid" / fixture
    path = root / f"{entry}.orc"
    baseline = compiler.compile_stage1_entrypoint(path, source_roots=(root,))
    result = compiler._compile_stage1_selected_declarations_entrypoint(path, source_roots=(root,))
    assert result.entry_module.module_name == baseline.entry_module.module_name
    for name in result.graph.modules_by_name:
        assert result.compiled_modules_by_name[name].definitions == baseline.compiled_modules_by_name[name].definitions
        assert result.compiled_modules_by_name[name].schemas == baseline.compiled_modules_by_name[name].schemas
        assert tuple(directive.alias for directive in result.compiled_modules_by_name[name].imports) == tuple(directive.alias for directive in baseline.compiled_modules_by_name[name].imports)


@pytest.mark.parametrize(
    "fixture,entry,code",
    [
        ("missing_export", "neurips/entry", "module_export_missing"),
        ("duplicate_alias", "duplicate/alias", "module_alias_duplicate"),
        ("cycle", "cycle/entry", "module_cycle"),
        ("ambiguous", "ambiguous/entry", "module_import_ambiguous"),
        ("schema_only_ambiguous", "neurips/entry", "module_import_ambiguous"),
        ("path_mismatch", "neurips/bad", "module_path_mismatch"),
    ],
)
def test_selected_loader_reuses_existing_invalid_module_contracts(fixture: str, entry: str, code: str) -> None:
    root = FIXTURE_ROOT / "modules" / "invalid" / fixture
    with pytest.raises(LispFrontendCompileError) as error:
        compiler._compile_stage1_selected_declarations_entrypoint(root / f"{entry}.orc", source_roots=(root,))
    assert error.value.diagnostics[0].code == code
