"""Python module ownership and imports use the ordinary compiler graph."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import json
import textwrap

import pytest

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.py.diagnostics import PythonFrontendError
from tests.test_workflow_python_declarations import module_source


def orc(root, name, body, *, target="2.39"):
    path = root / (name + ".orc")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'(workflow-lisp (:language "0.1") (:target-dsl "{target}") '
                    f'(defmodule {name})\n' + textwrap.dedent(body) + ')\n')
    return path


def test_imports_concrete_proc_workflow_type_and_prompt(tmp_path):
    orc(tmp_path / "libs", "library/review", '''
      (export Note revise echo draft)
      (defrecord Note (text String))
      (defproc revise ((text String)) -> Note (record Note :text text))
      (defworkflow echo ((note Note)) -> Note note)
      (defprompt draft (:fills (task :text)) -> Note "Draft {task}")
    ''')
    module = module_source(tmp_path, '''
    library = import_orc("library/review", source_root="libs")
    author = Provider("codex")

    @workflow
    def run(text: str) -> library.Note:
        note = library.revise(text)
        return library.echo(library.Note(text=note.text))

    @workflow
    def draft(text: str) -> library.Note:
        return author(library.draft(task=text))
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated",
                           provider_externs={"providers.codex": "codex"})
    linked = compile_stage3_entrypoint(graph.source_path, source_roots=graph.source_roots,
                                      provider_externs={"providers.codex": "codex"})
    providers = tmp_path / "providers.json"
    providers.write_text(json.dumps({"providers.codex": "codex"}))
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=graph.source_path, source_roots=graph.source_roots,
        entry_workflow="run", workspace_root=tmp_path, provider_externs_path=providers,
    ))
    assert evaluate_closed_program(built.program, {"text": "hello"}).value == {"text": "hello"}
    assert linked.graph.export_surfaces_by_name["library/review"].prompts_by_name["draft"]
    assert graph.generated_to_python[graph.source_path] == Path(module.__file__)
    assert graph.source_reads[tmp_path / "libs/library/review.orc"]


def test_imported_generic_type_application_uses_compiler(tmp_path):
    module = module_source(tmp_path, '''
    library = import_orc("std/improve")
    @record
    class Notes:
        text: str
    @record
    class Blocker:
        reason: str
    Decision = library.Decision[Notes, Blocker]
    @workflow
    def run(value: Decision) -> str:
        return match(value, APPROVE=lambda approved: approved.evidence.text,
                     REVISE=lambda revise: revise.feedback.text,
                     BLOCKED=lambda blocked: blocked.reason.reason)
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(
        source_path=graph.source_path, source_roots=graph.source_roots, entry_workflow="run"))
    assert evaluate_closed_program(built.program, {
        "value": {"variant": "APPROVE", "evidence": {"text": "good"}},
    }).value == "good"
    assert "std/improve" in compile_stage3_entrypoint(graph.source_path, source_roots=graph.source_roots).compiled_results_by_name


def test_modules_relocate_without_identity_change(tmp_path):
    from orchestrator.py.emit import generate_graph
    results = []
    for location in (tmp_path / "first", tmp_path / "relocated"):
        module_source(location, '''
        @record
        class Note:
            text: str
        author = Provider("codex")
        task = Prompt(text="Make {text}", fills={"text": Text}, returns=Note)
        @workflow
        def draft(text: str) -> Note:
            return author(task(text=text))
        ''', name="left")
        module_source(location, '''
        @record
        class Note:
            count: int
        @pure
        def describe(note: Note) -> int:
            return note.count
        ''', name="right")
        facade = module_source(location, '''
        from left import Note, draft as selected
        __all__ = ["selected", "Note"]
        ''', name="facade")
        module = module_source(location, '''
        from facade import selected, Note as LeftNote
        from right import Note as RightNote, describe
        @workflow
        def run(text: str, other: RightNote) -> LeftNote:
            describe(other)
            return selected(text)
        ''')
        providers = location / "providers.json"
        providers.write_text(json.dumps({"providers.codex": "codex"}))
        graph = generate_graph(module, location / "generated",
                               provider_externs={"providers.codex": "codex"})
        built = build_closed_program_bundle(FrontendBuildRequest(
            source_path=graph.source_path, source_roots=graph.source_roots,
            entry_workflow="run", provider_externs_path=providers))
        facade_graph = generate_graph(facade, location / "facade-generated",
                                     provider_externs={"providers.codex": "codex"})
        assert facade_graph.entry_aliases == {"selected": ("py/left", "draft")}
        assert "py/facade" not in {path.relative_to(graph.source_root).with_suffix("").as_posix()
                                  for path in graph.source_paths}
        assert set(graph.generated_to_python.values()) >= {location / "left.py", location / "right.py"}
        results.append(built)
    assert results[0].program.digest == results[1].program.digest
    assert results[0].program.sites == results[1].program.sites


@pytest.mark.parametrize("member", ["missing", "_private"])
def test_private_missing_and_old_imports_refuse(tmp_path, member):
    path = orc(tmp_path / "libs", "library/check", '''
      (export public)
      (defproc public ((value Int)) -> Int value)
      (defproc _private ((value Int)) -> Int value)
    ''')
    module = module_source(tmp_path, f'''
    library = import_orc("library/check", source_root="libs")
    @workflow
    def run(value: int) -> int:
        return library.{member}(value)
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(PythonFrontendError, match="python_import_member_missing") as error:
        generate_graph(module, tmp_path / "generated")
    assert error.value.site.path == module.__file__
    assert error.value.site.line == 7
    orc(tmp_path / "libs", "old", '(export value) (defrecord value (count Int))', target="2.34")
    path.write_text(path.read_text().replace('(export public)', '(import old) (export public)'))
    with pytest.raises(LispFrontendCompileError) as error:
        generate_graph(module, tmp_path / "generated-old")
    assert any(diagnostic.span.start.path.endswith("old.orc") for diagnostic in error.value.diagnostics)


def test_stdlib_import_has_one_source_owner(tmp_path):
    from orchestrator.py.emit import generate_graph
    module = module_source(tmp_path, '''
    library = import_orc("std/improve")
    @workflow
    def run(value: int) -> int:
        return value
    ''')
    graph = generate_graph(module, tmp_path / "generated")
    sources = [path for path in graph.source_reads if path.name == "improve.orc"]
    assert len(sources) == 1
    assert "stdlib_modules" in sources[0].parts
    assert not (graph.source_root / "std/improve.orc").exists()


def test_imported_types_in_containers_and_optionals(tmp_path):
    orc(tmp_path / "libs", "library/data", '(export Note) (defrecord Note (text String))')
    module = module_source(tmp_path, '''
    library = import_orc("library/data", source_root="libs")
    @workflow
    def run(values: list[library.Note]) -> list[library.Note]:
        return values
    @workflow
    def maybe(value: library.Note | None) -> library.Note | None:
        return value
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=graph.source_path,
            source_roots=graph.source_roots, entry_workflow="run"))
    assert [dict(item) for item in evaluate_closed_program(built.program, {"values": [{"text": "ok"}]}).value] == [{"text": "ok"}]


def test_imported_invalid_source_preserves_original_location(tmp_path):
    path = orc(tmp_path / "libs", "library/broken", '(export broken) (defproc broken () -> Int "wrong")')
    module = module_source(tmp_path, '''
    library = import_orc("library/broken", source_root="libs")
    @workflow
    def run() -> int:
        return library.broken()
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(LispFrontendCompileError) as error:
        generate_graph(module, tmp_path / "generated")
    assert any(diagnostic.span.start.path == str(path) for diagnostic in error.value.diagnostics)


def test_imported_record_construction_is_lazy_and_compiler_checked(tmp_path):
    orc(tmp_path / "libs", "library/data", '(export Note) (defrecord Note (text String))')
    module = module_source(tmp_path, '''
    library = import_orc("library/data", source_root="libs")
    initial = library.Note(text="before configuration")
    @workflow
    def run() -> library.Note:
        return initial
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=graph.source_path,
            source_roots=graph.source_roots, entry_workflow="run"))
    assert evaluate_closed_program(built.program, {}).value == {"text": "before configuration"}


def test_duplicate_roots_and_python_union_owners_refuse(tmp_path):
    from orchestrator.py.emit import generate_graph
    module = module_source(tmp_path, '''
    @variant
    class Yes: pass
    @variant
    class No: pass
    First = Yes | No
    Competing = Yes | No
    @workflow
    def run(value: int) -> int:
        return value
    ''')
    with pytest.raises(PythonFrontendError, match="python_union_owner_ambiguous"):
        generate_graph(module, tmp_path / "generated")
    module = module_source(tmp_path, '@workflow\ndef run(value: int) -> int:\n    return value')
    with pytest.raises(PythonFrontendError, match="python_source_root_duplicate"):
        generate_graph(module, tmp_path / "generated", source_roots=(tmp_path, tmp_path / "."))


def test_python_prompt_extern_assets_preserve_original_owner(tmp_path):
    from orchestrator.py.emit import generate_graph
    prompt = tmp_path / "prompts/task.md"
    prompt.parent.mkdir()
    prompt.write_bytes(b"Produce a result.\n")
    module = module_source(tmp_path, '''
    task = Prompt.extern("prompts.task", returns=str)
    author = Provider("codex")
    @workflow
    def run() -> str:
        return author(task())
    ''')
    graph = generate_graph(module, tmp_path / "generated",
              provider_externs={"providers.codex": "codex"},
              prompt_externs={"prompts.task": {"asset_file": "prompts/task.md"}})
    assert graph.prompt_assets[prompt] == prompt.read_bytes()
    assert (graph.source_path.parent / "prompts/task.md").read_bytes() == prompt.read_bytes()
    assert graph.asset_bindings == ({"owner": str(module.__file__),
                "generated_owner": str(graph.source_path), "relative_path": "prompts/task.md",
                "source_path": str(prompt)},)


def test_imported_member_and_enum_tokens_do_not_collide_with_metadata(tmp_path):
    orc(tmp_path / "libs", "library/names", '''
      (export name Mode)
      (defenum Mode name kind site fields)
      (defproc name ((value Mode)) -> Mode value)
    ''')
    module = module_source(tmp_path, '''
    library = import_orc("library/names", source_root="libs")
    initial = library.Mode.name
    @workflow
    def run() -> library.Mode:
        return library.name(initial)
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=graph.source_path,
            source_roots=graph.source_roots, entry_workflow="run"))
    assert evaluate_closed_program(built.program, {}).value == "name"


def test_python_union_import_without_case_bindings_preserves_owner(tmp_path):
    owner = module_source(tmp_path, '''
    @variant
    class Accepted:
        text: str
    @variant
    class Blocked:
        reason: str
    Outcome = Accepted | Blocked
    ''', name="union_owner")
    module = module_source(tmp_path, '''
    from union_owner import Outcome
    @workflow
    def run(value: Outcome) -> str:
        return match(value, Accepted=lambda accepted: accepted.text,
                     Blocked=lambda blocked: blocked.reason)
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    linked = compile_stage3_entrypoint(graph.source_path, source_roots=graph.source_roots)
    assert "py/union_owner" in linked.compiled_results_by_name
    assert owner.__file__ in graph.source_map.source_hashes
    assert not any(type(definition).__name__ == "UnionDef" for definition in linked.entry_result.module.definitions)


def test_private_python_cross_module_call_refuses_before_tracing_owner(tmp_path):
    owner = module_source(tmp_path, '''
    calls = []
    @pure
    def visible(value: int) -> int:
        calls.append("visible")
        return value
    @pure
    def _private(value: int) -> int:
        calls.append("private")
        return value
    ''', name="private_owner")
    module_source(tmp_path, '''
    from private_owner import _private
    @pure
    def indirect(value: int) -> int:
        return _private(value)
    ''', name="private_consumer")
    module = module_source(tmp_path, '''
    from private_owner import visible
    from private_consumer import indirect
    @workflow
    def run(value: int) -> int:
        visible(value)
        return indirect(value)
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(PythonFrontendError, match="python_import_member_missing"):
        generate_graph(module, tmp_path / "generated")
    assert owner.calls == ["visible"]


def test_imported_prompt_asset_evidence_is_source_owned(tmp_path):
    from orchestrator.py.emit import generate_graph
    source = orc(tmp_path / "libs", "library/provider", '''
      (export draft)
      (defworkflow draft () -> String
        (provider-result providers.codex :prompt prompts.task :inputs () :returns String))
    ''')
    asset = source.parent / "prompts/task.md"
    asset.parent.mkdir()
    asset.write_bytes(b"Return a string.\n")
    module = module_source(tmp_path, '''
    library = import_orc("library/provider", source_root="libs")
    @workflow
    def run() -> str:
        return library.draft()
    ''')
    graph = generate_graph(module, tmp_path / "generated",
              provider_externs={"providers.codex": "codex"},
              prompt_externs={"prompts.task": {"asset_file": "prompts/task.md"}})
    assert graph.prompt_assets[asset] == asset.read_bytes()
    assert any(row["owner"] == str(source) and row["relative_path"] == "prompts/task.md"
               for row in graph.asset_bindings)


def test_cross_python_prompt_and_constructor_imports_precede_source_ranges(tmp_path):
    module_source(tmp_path, '''
    @record
    class Note:
        text: str
    template = Prompt(text="Answer {task}", fills={"task": Text}, returns=str)
    ''', name="prompt_owner")
    module = module_source(tmp_path, '''
    from prompt_owner import template, Note
    author = Provider("codex")
    @workflow
    def run(value: str) -> str:
        note = Note(text=value)
        return author(template(task=note.text))
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated",
                           provider_externs={"providers.codex": "codex"})
    linked = compile_stage3_entrypoint(graph.source_path, source_roots=graph.source_roots,
                                       provider_externs={"providers.codex": "codex"})
    assert "py/prompt_owner" in linked.compiled_results_by_name
    lines = graph.source_path.read_text().splitlines()
    entries = [entry for entry in graph.source_map.entries
               if entry.generated.path == str(graph.source_path) and entry.kind == "definition"]
    assert entries and "defworkflow run" in lines[entries[0].generated.line - 1]


def test_duplicate_logical_python_modules_refuse(tmp_path):
    module_source(tmp_path, '@record\nclass First:\n    value: int', name="duplicate_left")
    module_source(tmp_path, '@record\nclass Second:\n    value: int', name="duplicate_right")
    module = module_source(tmp_path, '''
    from duplicate_left import First
    from duplicate_right import Second
    @workflow
    def run(value: First) -> First:
        return value
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(PythonFrontendError, match="python_module_duplicate"):
        generate_graph(module, tmp_path / "generated", module_names={
            "duplicate_left": "duplicate", "duplicate_right": "duplicate"})


def test_explicit_python_capture_is_exact_and_complete(tmp_path):
    module = module_source(tmp_path, '@workflow\ndef run(value: int) -> int:\n    return value')
    path = Path(module.__file__)
    captured = path.read_bytes()
    path.write_bytes(captured.replace(b"return value", b"return value + 1"))
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated", python_sources={path: captured})
    assert graph.python_sources[path] == captured
    import hashlib
    assert graph.source_map.source_hashes[str(path)] == "sha256:" + hashlib.sha256(captured).hexdigest()
    with pytest.raises(PythonFrontendError, match="python_source_not_captured"):
        generate_graph(module, tmp_path / "incomplete", python_sources={})


def test_import_resolution_uses_explicit_roots_without_cwd(tmp_path, monkeypatch):
    incidental = tmp_path / "incidental"
    orc(incidental, "library/data", '(export echo) (defproc echo ((value Int)) -> Int value)')
    module = module_source(tmp_path, '''
    library = import_orc("library/data")
    @workflow
    def run(value: int) -> int:
        return library.echo(value)
    ''')
    monkeypatch.chdir(incidental)
    from orchestrator.py.emit import generate_graph
    with pytest.raises(LispFrontendCompileError):
        generate_graph(module, tmp_path / "missing")
    graph = generate_graph(module, tmp_path / "generated", source_roots=(incidental,))
    assert graph.source_roots == (graph.source_root, incidental)
    assert incidental / "library/data.orc" in graph.source_reads


def test_imported_workflow_omits_compiler_owned_defaults(tmp_path):
    orc(tmp_path / "libs", "library/defaults", '''
      (export echo)
      (defworkflow echo ((value Int :default 4) (required Int)) -> Int (+ value required))
    ''')
    module = module_source(tmp_path, '''
    library = import_orc("library/defaults", source_root="libs")
    @workflow
    def run() -> int:
        return library.echo(required=3)
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=graph.source_path,
            source_roots=graph.source_roots, entry_workflow="run"))
    assert evaluate_closed_program(built.program, {}).value == 7


def test_enum_only_python_module_import_keeps_nominal_owner(tmp_path):
    module_source(tmp_path, '''
    from enum import Enum
    class Mode(Enum):
        READY = "ready"
    ''', name="enum_owner")
    module = module_source(tmp_path, '''
    import enum_owner
    @workflow
    def run(value: enum_owner.Mode) -> enum_owner.Mode:
        return value
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=graph.source_path,
            source_roots=graph.source_roots, entry_workflow="run"))
    assert evaluate_closed_program(built.program, {"value": "ready"}).value == "ready"


@pytest.mark.parametrize("declaration,expression", [
    ('(defrecord Item (_kind String))', 'value._kind'),
    ('(defunion Item (Bad (_kind String)) (Good (text String)))',
     'match(value, Bad=lambda bad: bad._kind, Good=lambda good: good.text)'),
    ('(defrecord Nested (_kind String)) (defrecord Item (child Nested))', 'value.child._kind'),
])
def test_imported_reserved_record_and_match_fields_refuse(tmp_path, declaration, expression):
    orc(tmp_path / "libs", "library/reserved", '(export Item) ' + declaration)
    module = module_source(tmp_path, f'''
    library = import_orc("library/reserved", source_root="libs")
    @workflow
    def run(value: library.Item) -> str:
        return {expression}
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(PythonFrontendError, match="python_record_field_reserved") as error:
        generate_graph(module, tmp_path / "generated")
    assert error.value.site.path == module.__file__


def test_only_reachable_python_bodies_trace_once_across_modules(tmp_path):
    owner = module_source(tmp_path, '''
    calls = []
    @pure
    def used(value: int) -> int:
        calls.append("used")
        return value + 1
    @pure
    def unused(value: int) -> int:
        calls.append("unused")
        return value if value else 0
    ''', name="reachable_owner")
    middle = module_source(tmp_path, '''
    import reachable_owner
    calls = []
    @pure
    def indirect(value: int) -> int:
        calls.append("indirect")
        return reachable_owner.used(value)
    ''', name="reachable_middle")
    module = module_source(tmp_path, '''
    import reachable_owner
    import reachable_middle
    @workflow
    def run(value: int) -> int:
        return reachable_middle.indirect(value)
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=graph.source_path,
            source_roots=graph.source_roots, entry_workflow="run"))
    assert evaluate_closed_program(built.program, {"value": 2}).value == 3
    assert owner.calls == ["used"]
    assert middle.calls == ["indirect"]
    assert Path(owner.__file__) in graph.python_sources


def test_python_imported_variant_construction_keeps_unique_union_owner(tmp_path):
    module_source(tmp_path, '''
    @variant
    class A: pass
    @variant
    class B: pass
    Outcome = A | B
    ''', name="variant_owner")
    module = module_source(tmp_path, '''
    from variant_owner import A, B, Outcome
    @workflow
    def run(flag: bool) -> int:
        when(flag, then=lambda: A(), else_=lambda: B())
        return 1
    ''')
    from orchestrator.py.emit import generate_graph
    graph = generate_graph(module, tmp_path / "generated")
    built = build_closed_program_bundle(FrontendBuildRequest(source_path=graph.source_path,
            source_roots=graph.source_roots, entry_workflow="run"))
    assert evaluate_closed_program(built.program, {"flag": False}).value == 1


@pytest.mark.parametrize("token", ["_name", "__name__", "__module__"])
def test_non_type_subscripts_and_private_enum_metadata_tokens_refuse(tmp_path, token):
    path = orc(tmp_path / "libs", "library/subscript", '''
      (export echo)
      (defproc echo ((value String)) -> String value)
    ''')
    module = module_source(tmp_path, '''
    library = import_orc("library/subscript", source_root="libs")
    @workflow
    def run() -> str:
        return library.echo[int]("value")
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(PythonFrontendError, match="python_import_generic_callable_unsupported"):
        generate_graph(module, tmp_path / "generated")
    path.write_text(path.read_text().replace('(export echo)', f'(export echo Mode) (defenum Mode {token} ready)'))
    module = module_source(tmp_path, f'''
    library = import_orc("library/subscript", source_root="libs")
    initial = library.Mode.{token}
    @workflow
    def run() -> str:
        return initial
    ''')
    with pytest.raises(PythonFrontendError, match="python_import_member_reserved"):
        generate_graph(module, tmp_path / "reserved")


def test_metadata_compile_errors_map_to_python_and_keep_generated_notes(tmp_path):
    module = module_source(tmp_path, '''
    library = import_orc("missing/library")
    @workflow
    def run() -> int:
        return 1
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(LispFrontendCompileError) as error:
        generate_graph(module, tmp_path / "generated")
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.span.start.path == module.__file__
    assert diagnostic.span.start.line == 4
    assert diagnostic.code
    assert any("Generated source: <module:missing/library>" in note for note in diagnostic.notes)

    module = module_source(tmp_path, '''
    class Report(RelPath, under=123): pass
    @workflow
    def run(value: Report) -> Report:
        return value
    ''')
    with pytest.raises(LispFrontendCompileError) as error:
        generate_graph(module, tmp_path / "invalid-type")
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.span.start.path == module.__file__
    assert any("Generated source:" in note and "workflow-python-types-" in note for note in diagnostic.notes)


def test_generic_application_errors_point_to_python_use(tmp_path):
    module = module_source(tmp_path, '''
    library = import_orc("std/improve")
    @workflow
    def run(value: library.Decision[int]) -> int:
        return 1
    ''')
    from orchestrator.py.emit import generate_graph
    with pytest.raises(LispFrontendCompileError) as error:
        generate_graph(module, tmp_path / "generated")
    assert error.value.diagnostics[0].span.start.path == module.__file__


def test_prompt_capture_rejects_changed_bytes_between_reads(tmp_path, monkeypatch):
    path = tmp_path / "task.md"
    path.write_bytes(b"First version")
    module = module_source(tmp_path, '''
    first = Prompt(file="task.md", fills={}, returns=str)
    second = Prompt(file="task.md", fills={}, returns=str)
    @workflow
    def run(value: int) -> int:
        return value
    ''')
    original = Path.read_bytes
    versions = iter((b"First version", b"Later version"))
    def read_bytes(current):
        return next(versions) if current == path else original(current)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    from orchestrator.py.emit import generate_graph
    with pytest.raises(PythonFrontendError, match="python_source_changed"):
        generate_graph(module, tmp_path / "generated")
