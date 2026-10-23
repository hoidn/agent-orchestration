"""Durable Python builds retain ordinary source recipes, never author globals."""
from __future__ import annotations

from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap

import pytest

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.py.diagnostics import PythonFrontendError
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError


def authored(root, text, name="example"):
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{name}.py"
    path.write_text("from __future__ import annotations\nfrom orchestrator.py import *\n" + textwrap.dedent(text))
    return path


def value(built, inputs=None):
    program = ClosedProgram.from_artifact(built.artifact_path.read_text())
    return evaluate_closed_program(program, inputs or {}).value


def test_build_reloads_exact_bytes_despite_mtime_and_cache(tmp_path, monkeypatch):
    from orchestrator.py.build import build
    helper = authored(tmp_path, "COUNT = 1\n", name="build_helper")
    source = authored(tmp_path, '''
    import build_helper
    @workflow
    def run() -> int:
        return build_helper.COUNT
    ''')
    monkeypatch.syspath_prepend(str(tmp_path))
    spec = importlib.util.spec_from_file_location("build_helper", helper)
    cached = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "build_helper", cached)
    spec.loader.exec_module(cached)
    first = build(source, workspace_root=tmp_path)
    assert value(first) == 1
    stamp = helper.stat()
    helper.write_bytes(helper.read_bytes().replace(b"COUNT = 1", b"COUNT = 2"))
    os.utime(helper, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    cached.COUNT = 99
    second = build(source, workspace_root=tmp_path)
    assert value(second) == 2
    assert first.snapshot_path != second.snapshot_path
    assert build(source, workspace_root=tmp_path).snapshot_path == second.snapshot_path
    assert not (tmp_path / ".orchestrate/runs").exists()


def test_worker_stdout_is_not_build_protocol(tmp_path):
    from orchestrator.py.build import build
    source = authored(tmp_path, '''
    print('{"source_path": "bogus", "error": "author output"}')
    @workflow
    def run() -> int:
        print("trace output")
        return 7
    ''')
    assert value(build(source, workspace_root=tmp_path)) == 7


def test_snapshot_rebuilds_project_imports_and_assets(tmp_path):
    from orchestrator.py.build import build
    project = tmp_path / "project"
    source = authored(project, '''
    library = import_orc("library/review", source_root="libs")
    external = Prompt.extern("prompts.python", returns=str)
    agent = Provider("review")
    @workflow
    def run(text: str) -> str:
        agent(external(text))
        return library.review(text)
    ''')
    library = project / "libs/library/review.orc"
    library.parent.mkdir(parents=True)
    library.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule library/review) (export review)
      (defworkflow review ((text String)) -> String
        (provider-result providers.review :prompt prompts.library
          :inputs (text) :returns String)))''')
    (library.parent / "review.md").write_bytes(b"Library source asset\r\n")
    (project / "python.md").write_bytes(b"Python source asset\r\n")
    library_asset = (library.parent / "review.md").read_bytes()
    python_asset = (project / "python.md").read_bytes()
    providers = project / "providers.json"
    providers.write_text(json.dumps({"providers.review": "codex"}))
    prompts = project / "prompts.json"
    prompts.write_text(json.dumps({"prompts.python": {"asset_file": "python.md"},
                                  "prompts.library": {"asset_file": "review.md"}}))
    built = build(source, workspace_root=tmp_path, provider_externs_file=providers,
                  prompt_externs_file=prompts)
    assert built.source_path.with_name("python.md").read_bytes() == python_asset
    retained = next(root / "library/review.orc" for root in built.source_roots
                    if (root / "library/review.orc").exists())
    assert retained.with_name("review.md").read_bytes() == library_asset
    shutil.rmtree(project)
    rebuilt = build_closed_program_bundle(built.request)
    assert (rebuilt.build_key, rebuilt.program.digest) == (built.build_key, built.program_digest)
    assert all(project not in root.parents and root != project for root in built.source_roots)


@pytest.mark.parametrize("changed", ["python", "helper", "prompt", "orc", "manifest"])
def test_frozen_captures_all_authoring_inputs(tmp_path, changed):
    from orchestrator.py.build import build, check
    helper = authored(tmp_path, "COUNT = 1\n", name="frozen_helper")
    source = authored(tmp_path, '''
    import frozen_helper
    library = import_orc("library/count", source_root="libs")
    template = Prompt(file="template.md", fills={"text": Text}, returns=str)
    agent = Provider("review")
    @workflow
    def run(text: str) -> int:
        agent(template(text=text))
        return library.count(frozen_helper.COUNT)
    ''')
    prompt = tmp_path / "template.md"
    prompt.write_text("Read {text}")
    orc = tmp_path / "libs/library/count.orc"
    orc.parent.mkdir(parents=True)
    orc.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule library/count) (export count)
      (defproc count ((value Int)) -> Int value))''')
    manifest = tmp_path / "providers.json"
    manifest.write_text('{"providers.review": "codex"}')
    options = dict(workspace_root=tmp_path, provider_externs_file=manifest)
    built = build(source, **options)
    pin = built.pin_path.read_bytes()
    assert build(source, frozen=True, **options).snapshot_path == built.snapshot_path
    path = {"python": source, "helper": helper, "prompt": prompt,
            "orc": orc, "manifest": manifest}[changed]
    path.write_bytes(path.read_bytes() + b"\n")
    with pytest.raises(PythonFrontendError, match="python_frozen_changed"):
        build(source, frozen=True, **options)
    assert built.pin_path.read_bytes() == pin
    check(source, **options)
    assert built.pin_path.read_bytes() == pin


def test_failed_build_preserves_pin_and_existing_snapshot(tmp_path):
    from orchestrator.py.build import build, check
    source = authored(tmp_path, "@workflow\ndef run() -> int:\n    return 1\n")
    with pytest.raises(PythonFrontendError, match="python_frozen_pin_missing"):
        build(source, workspace_root=tmp_path, frozen=True)
    checked = check(source, workspace_root=tmp_path)
    assert not checked.pin_path.exists()
    built = build(source, workspace_root=tmp_path)
    pin = built.pin_path.read_bytes()
    retained = {p.relative_to(built.snapshot_path): p.read_bytes()
                for p in built.snapshot_path.rglob("*") if p.is_file()}
    source.write_text("from orchestrator.py import workflow\n@workflow\ndef run( -> int:\n    return 2\n")
    with pytest.raises(PythonFrontendError, match="python_syntax_error") as error:
        build(source, workspace_root=tmp_path)
    assert error.value.site.path == str(source)
    assert "SyntaxError" in error.value.traceback
    assert built.pin_path.read_bytes() == pin
    assert retained == {p.relative_to(built.snapshot_path): p.read_bytes()
                        for p in built.snapshot_path.rglob("*") if p.is_file()}


def test_snapshot_paths_refuse_symlink_escape(tmp_path):
    from orchestrator.py.build import build
    workspace = tmp_path / "workspace"
    source = authored(workspace, "@workflow\ndef run() -> int:\n    return 1\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (workspace / ".orchestrate").symlink_to(outside, target_is_directory=True)
    with pytest.raises((PythonFrontendError, LispFrontendCompileError), match="path|symlink|workspace"):
        build(source, workspace_root=workspace)
    assert not list(outside.iterdir())


def test_diagnostics_preserve_python_and_orc_locations(tmp_path):
    from orchestrator.py.build import build
    source = authored(tmp_path, '''
    @workflow
    def run() -> int:
        return "wrong"
    ''')
    with pytest.raises(LispFrontendCompileError) as error:
        build(source, workspace_root=tmp_path)
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.span.start.path == str(source)
    assert diagnostic.code and any(".orc:" in note for note in diagnostic.notes)
    source = authored(tmp_path, '''
    library = import_orc("library/broken", source_root="libs")
    @workflow
    def run() -> int:
        return library.broken()
    ''')
    library = tmp_path / "libs/library/broken.orc"
    library.parent.mkdir(parents=True)
    library.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule library/broken) (export broken)
      (defproc broken () -> Int "wrong"))''')
    with pytest.raises(LispFrontendCompileError) as error:
        build(source, workspace_root=tmp_path)
    assert any(d.span.start.path == str(library) for d in error.value.diagnostics)


@pytest.mark.parametrize("absolute", [False, True])
def test_retained_bundle_locators_keep_ordinary_identity(tmp_path, absolute):
    from orchestrator.py.build import build
    project = tmp_path / "project"
    source = authored(project, '''
    library = import_orc("library/consumer", source_root="libs")
    @workflow
    def run() -> int:
        return library.consume()
    ''')
    producer = project / "producers/producer.orc"
    producer.parent.mkdir()
    producer.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule producer) (export produce) (defworkflow produce () -> Int 9))''')
    consumer = project / "libs/library/consumer.orc"
    consumer.parent.mkdir(parents=True)
    consumer.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule library/consumer) (export consume)
      (defworkflow consume () -> Int (call dep)))''')
    manifest = project / "imports.json"
    manifest.write_text(json.dumps({"dep": {"kind": "compiled", "path":
        str(producer) if absolute else "producers/producer.orc"}}))
    original = manifest.read_bytes()
    built = build(source, workspace_root=tmp_path, source_roots=(producer.parent,),
                  imported_workflow_bundles_file=manifest)
    assert value(built) == 9
    assert original in [path.read_bytes() for path in built.snapshot_path.rglob("imports.json")]
    recipe_manifest = json.loads(built.imported_workflow_bundles_path.read_text())
    assert (built.imported_workflow_bundles_path.parent / recipe_manifest["dep"]["path"]).resolve().is_relative_to(built.snapshot_path)
    shutil.rmtree(project)
    rebuilt = build_closed_program_bundle(built.request)
    assert (rebuilt.build_key, rebuilt.program.digest) == (built.build_key, built.program_digest)


def test_existing_snapshot_symlinks_and_changed_bytes_are_refused(tmp_path):
    from orchestrator.py.build import build
    source = authored(tmp_path, "@workflow\ndef run() -> int:\n    return 1\n")
    built = build(source, workspace_root=tmp_path)
    pin = built.pin_path.read_bytes()
    outside = tmp_path / "untouched.orc"
    outside.write_text("outside")
    retained_source = built.source_path.read_bytes()
    built.source_path.unlink()
    built.source_path.symlink_to(outside)
    with pytest.raises(PythonFrontendError, match="python_build_path_error"):
        build(source, workspace_root=tmp_path)
    assert outside.read_text() == "outside" and built.pin_path.read_bytes() == pin
    built.source_path.unlink()
    built.source_path.write_bytes(retained_source + b"\n")
    with pytest.raises(PythonFrontendError, match="python_snapshot_changed"):
        build(source, workspace_root=tmp_path)
    assert built.pin_path.read_bytes() == pin


def test_runtime_prompt_input_remains_workspace_relative_and_unfrozen(tmp_path):
    from orchestrator.py.build import build
    source = authored(tmp_path / "project", '''
    external = Prompt.extern("prompts.runtime", returns=str)
    agent = Provider("review")
    @workflow
    def run() -> str:
        return agent(external())
    ''')
    providers = tmp_path / "providers.json"
    providers.write_text('{"providers.review":"codex"}')
    prompts = tmp_path / "prompts.json"
    prompts.write_text('{"prompts.runtime":{"input_file":"runtime/task.md"}}')
    runtime = tmp_path / "runtime/task.md"
    runtime.parent.mkdir()
    runtime.write_text("First")
    kwargs = dict(workspace_root=tmp_path, provider_externs_file=providers, prompt_externs_file=prompts)
    built = build(source, **kwargs)
    assert built.prompt_externs_path.read_bytes() == prompts.read_bytes()
    assert str(runtime) not in json.loads((built.snapshot_path / "manifest.json").read_text())["authoring_inputs"]
    runtime.write_text("Second")
    assert build(source, frozen=True, **kwargs).snapshot_path == built.snapshot_path


def test_explicit_python_root_keeps_namespace_package_identity(tmp_path):
    from orchestrator.py.build import build
    project = tmp_path / "project"
    helper = authored(project / "pkg", "@pure\ndef count() -> int:\n    return 4\n", name="helper")
    source = authored(project / "pkg", '''
    from .helper import count
    @workflow
    def run() -> int:
        return count()
    ''', name="main")
    built = build(source, source_roots=(project,), workspace_root=tmp_path)
    assert built.entry_workflow == "py/pkg/main::run"
    assert value(built) == 4
    manifest = json.loads((built.snapshot_path / "manifest.json").read_text())
    assert str(helper) in manifest["authoring_inputs"]


@pytest.mark.parametrize("body", ["return missing_name", "return broken()"])
def test_worker_trace_errors_keep_authored_site_and_debug_traceback(tmp_path, body):
    from orchestrator.py.build import build
    source = authored(tmp_path, f'''
    from pathlib import Path
    def broken():
        return Path(__file__).with_name("missing.txt").read_text()
    @workflow
    def run() -> int:
        {body}
    ''')
    with pytest.raises(PythonFrontendError) as error:
        build(source, workspace_root=tmp_path)
    assert error.value.code == "python_import_or_trace_error"
    assert error.value.site.path == str(source)
    assert "Traceback" in error.value.traceback


def test_nonzero_worker_exit_cannot_publish_success(tmp_path):
    from orchestrator.py.build import build
    source = authored(tmp_path, '''
    import atexit, os
    atexit.register(lambda: os._exit(17))
    @workflow
    def run() -> int:
        return 1
    ''')
    with pytest.raises(PythonFrontendError, match="python_worker_failed"):
        build(source, workspace_root=tmp_path)
    assert not list((tmp_path / ".orchestrate/python").glob("pin-*.json"))


def test_final_build_identity_is_checked_before_pin(tmp_path, monkeypatch):
    import importlib
    module = importlib.import_module("orchestrator.py.build")
    source = authored(tmp_path, "@workflow\ndef run() -> int:\n    return 1\n")
    first = module.build(source, workspace_root=tmp_path)
    pin = first.pin_path.read_bytes()
    original_builder = module.build_closed_program_bundle
    def changed_identity(*args, **kwargs):
        return replace(original_builder(*args, **kwargs), build_key="unexpected-identity")
    monkeypatch.setattr(module, "build_closed_program_bundle", changed_identity)
    with pytest.raises(PythonFrontendError, match="python_snapshot_identity_changed"):
        module.build(source, workspace_root=tmp_path)
    assert first.pin_path.read_bytes() == pin


def test_python_facade_entry_selection_preserves_defining_owner(tmp_path):
    from orchestrator.py.build import build
    owner = authored(tmp_path, '''
    TARGET = "2.38"
    @workflow
    def original() -> int:
        return 3
    ''', name="owner")
    source = authored(tmp_path, '''
    TARGET = "2.39"
    from owner import original as selected
    __all__ = ["selected"]
    ''', name="facade")
    built = build(source, workspace_root=tmp_path)
    assert built.entry_workflow == "py/owner::original" and value(built) == 3
    assert ClosedProgram.from_artifact(built.artifact_path.read_text()).tree["target"] == "2.38"
    for selected in ("selected", "py/facade::selected", "py/owner::original"):
        explicit = build(source, entry_workflow=selected, frozen=True, workspace_root=tmp_path)
        assert explicit.snapshot_path == built.snapshot_path
        assert explicit.pin_path == built.pin_path
    assert str(owner) in json.loads((built.snapshot_path / "manifest.json").read_text())["authoring_inputs"]


def test_package_reexport_imports_and_traces_selected_source_once(tmp_path):
    from orchestrator.py.build import build
    source = authored(tmp_path / "pkg", '''
    from pathlib import Path
    marker = Path(__file__).with_name("observed.txt")
    with marker.open("a") as output:
        output.write("import\\n")
    @workflow
    def run() -> int:
        with marker.open("a") as output:
            output.write("trace\\n")
        return 5
    ''', name="main")
    (source.parent / "__init__.py").write_text("from .main import run\n")
    built = build(source, workspace_root=tmp_path)
    assert value(built) == 5
    assert source.with_name("observed.txt").read_text().splitlines() == ["import", "trace"]


def test_successful_compiler_warning_keeps_python_and_retained_generated_site(tmp_path):
    from orchestrator.py.build import build
    source = authored(tmp_path, '''
    @variant
    class A: pass
    @variant
    class B: pass
    Outcome = A | B
    agent = Provider("review")
    task = Prompt(text="Return one outcome", fills={}, returns=Outcome)
    @workflow
    def run() -> Outcome:
        return agent(task())
    ''')
    providers = tmp_path / "providers.json"
    providers.write_text('{"providers.review":"codex"}')
    built = build(source, workspace_root=tmp_path, provider_externs_file=providers)
    diagnostic = next(d for d in built.compile_diagnostics
                      if d.code == "variant_output_without_variant_specific_fields")
    assert diagnostic.span.start.path == str(source)
    assert any(str(built.source_path) in note for note in diagnostic.notes)


def test_retained_recipe_runs_through_public_orchestrator_without_python(tmp_path):
    from orchestrator.py import build
    from orchestrator.workflow.evaluated.memo import read_memo
    source = authored(tmp_path / "project", '''
    @workflow
    def run(count: int) -> int:
        return count + 1
    ''')
    built = build(source, workspace_root=tmp_path)
    shutil.rmtree(source.parent)
    process = subprocess.run([sys.executable, "-m", "orchestrator", "run", str(built.source_path),
        "--entry-workflow", built.entry_workflow, "--input", "count=4",
        *(part for root in built.source_roots for part in ("--source-root", str(root)))],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).parents[1]), "PYTHONDONTWRITEBYTECODE": "1"})
    assert process.returncode == 0, process.stderr
    (run_root,) = (tmp_path / ".orchestrate/runs").iterdir()
    snapshot = read_memo(run_root / "memo.jsonl", {})
    assert snapshot.terminal.data == {"record": "terminal", "outcome": "completed", "value": 5}


def test_worker_diagnostics_retain_native_macro_expansion_context(tmp_path):
    from orchestrator.py import build
    from orchestrator.workflow_lisp.diagnostics import render_diagnostic
    from orchestrator.workflow_lisp.syntax import ExpansionFrame
    source = authored(tmp_path, '''
    library = import_orc("library/broken", source_root="libs")
    @workflow
    def run() -> int:
        return library.broken()
    ''')
    library = tmp_path / "libs/library/broken.orc"
    library.parent.mkdir(parents=True)
    library.write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule library/broken) (export broken)
      (defmacro emit-bad (name) (defproc name () -> Int "wrong"))
      (emit-bad broken))''')
    with pytest.raises(LispFrontendCompileError) as error:
        build(source, workspace_root=tmp_path)
    diagnostic = error.value.diagnostics[0]
    assert diagnostic.code == "procedure_return_type_invalid"
    assert diagnostic.span.start.path == str(library)
    assert isinstance(diagnostic.expansion_stack[0], ExpansionFrame)
    rendered = render_diagnostic(diagnostic)
    assert "expanded from macro `emit-bad` call at" in rendered
    assert "macro definition at" in rendered


def test_only_frozen_requires_valid_pin_and_normal_build_repairs_it(tmp_path):
    from orchestrator.py import build, check
    source = authored(tmp_path, "@workflow\ndef run() -> int:\n    return 1\n")
    built = build(source, workspace_root=tmp_path)
    built.pin_path.write_bytes(b"{broken")
    assert check(source, workspace_root=tmp_path).build_key == built.build_key
    assert built.pin_path.read_bytes() == b"{broken"
    with pytest.raises(PythonFrontendError, match="python_frozen_pin_invalid"):
        build(source, frozen=True, workspace_root=tmp_path)
    repaired = build(source, workspace_root=tmp_path)
    assert json.loads(repaired.pin_path.read_text())["build_key"] == built.build_key


@pytest.mark.parametrize("frame_kind", ["macro", "helper", "procedure"])
def test_diagnostic_worker_protocol_retains_native_metadata(frame_kind):
    from orchestrator.py._worker import _exception_result
    from orchestrator.py.build import _worker_error
    from orchestrator.workflow_lisp.diagnostics import (LispFrontendDiagnostic,
        build_authored_phased_delivery_diagnostic, serialize_diagnostic)
    from orchestrator.workflow_lisp.spans import SourcePosition, SourceSpan
    from orchestrator.workflow_lisp.syntax import ExpansionFrame, HelperExpansionFrame, ProcedureExpansionFrame
    span = SourceSpan(SourcePosition("source.orc", 2, 3, 5), SourcePosition("source.orc", 2, 8, 10))
    frame = {"macro": lambda: ExpansionFrame("macro", "m1", span, span, ("template",)),
             "helper": lambda: HelperExpansionFrame("helper", span, span),
             "procedure": lambda: ProcedureExpansionFrame("procedure", span, span)}[frame_kind]()
    phased = build_authored_phased_delivery_diagnostic("delivery_enum_invalid", canonical_value=None,
        source_spans_by_owner={"delivery_keyword": span, "provider_application": span})
    diagnostic = LispFrontendDiagnostic(code=phased.code, message="Original compiler message", span=span,
        notes=("Original compiler note",), form_path=("workflow-lisp",), expansion_stack=(frame,),
        phased_delivery_diagnostic=phased)
    payload = _exception_result(LispFrontendCompileError((diagnostic,)), "source.orc", {})
    restored = _worker_error(json.loads(json.dumps(payload))).diagnostics[0]
    assert restored == diagnostic
    assert serialize_diagnostic(restored) == serialize_diagnostic(diagnostic)


def test_local_python_imports_require_source_bytes(tmp_path):
    import py_compile
    from orchestrator.py import build
    helper = authored(tmp_path, "COUNT = 3\n", name="bytecode_helper")
    py_compile.compile(str(helper), cfile=str(helper.with_suffix(".pyc")), doraise=True)
    helper.unlink()
    source = authored(tmp_path, '''
    import bytecode_helper
    @workflow
    def run() -> int:
        return bytecode_helper.COUNT
    ''')
    with pytest.raises(PythonFrontendError, match="python_source_required"):
        build(source, workspace_root=tmp_path)


@pytest.mark.parametrize("installed_kind", ["stdlib", "platstdlib", "purelib", "platlib", "site", "user_site"])
def test_local_loader_leaves_installed_roots_to_normal_imports(tmp_path, monkeypatch, installed_kind):
    import importlib
    import site
    import sysconfig
    from orchestrator.py import _worker
    installed = tmp_path / "environment" / installed_kind
    installed.mkdir(parents=True)
    name = "_workflow_installed_probe"
    dependency = installed / f"{name}.py"
    dependency.write_text("VALUE = 7\n")
    # This is an authored directory whose spelling must not determine its role.
    project = tmp_path / "site-packages" / "project"
    project.mkdir(parents=True)
    local_name = "_workflow_local_probe"
    local = project / f"{local_name}.py"
    local.write_text("VALUE = 9\n")
    paths = {key: str(installed) for key in ("stdlib", "platstdlib", "purelib", "platlib")
             if key == installed_kind}
    monkeypatch.setattr(sysconfig, "get_paths", lambda: paths)
    monkeypatch.setattr(site, "getsitepackages", lambda: [str(installed)] if installed_kind == "site" else [])
    monkeypatch.setattr(site, "getusersitepackages", lambda: str(installed) if installed_kind == "user_site" else "")
    monkeypatch.syspath_prepend(str(installed))
    monkeypatch.syspath_prepend(str(project))
    captures = {}
    finder = _worker._LocalSources((tmp_path,), captures)
    monkeypatch.setattr(sys, "meta_path", [finder, *sys.meta_path])
    monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.delitem(sys.modules, local_name, raising=False)
    try:
        dependency_module = importlib.import_module(name)
        local_module = importlib.import_module(local_name)
        assert dependency_module.VALUE == 7 and local_module.VALUE == 9
        assert not isinstance(dependency_module.__loader__, _worker._ByteLoader)
        assert isinstance(local_module.__loader__, _worker._ByteLoader)
        assert captures == {local: local.read_bytes()}
    finally:
        sys.modules.pop(name, None)
        sys.modules.pop(local_name, None)
