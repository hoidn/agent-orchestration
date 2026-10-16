"""Native inspection uses retained source and declarations, never evaluation."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.dynamic.build import prepare_dynamic_program_bundle
from orchestrator.workflow_lisp.dynamic.repl_expr import NativeLoadedModule
from orchestrator.workflow_lisp.repl_expr import ReplRefusal
from tests.test_workflow_dynamic_repl import (
    _events, _hashes, _inspection_env, _load, _load_case, _repl, _run,
    _run_cli, _run_root, _write_case,
)
from tests.test_workflow_dynamic_source import write_source


@pytest.fixture
def catalog(tmp_path):
    library = write_source(tmp_path, "lib/native", '''
      (export Plan Status helper selected review)
      (defrecord Plan (steps List[String]))
      (defenum Status READY DONE)
      (define (helper x) x)
      (define (selected x) x)
      (define (private-helper x) x)
      (defrecord Private (secret String))
      (defprompt review (:fills (task :text) (plan :value Plan)) -> Bool
        "retained café {task} {plan}")
    ''', budget=None)
    old = write_source(tmp_path, "lib/old", '''
      (export Legacy old-helper)
      (defrecord Legacy (value Int))
      (defun old-helper ((x Int)) -> Int x)
    ''', budget=None, target="2.35")
    source = write_source(tmp_path, "demo/main", '''
      (import lib/native :as lib :only (Plan selected))
      (import lib/old :as old :only (Legacy))
      (export run)
      (define (helper x) (+ x 1))
      (defworkflow run ((plan Plan)) -> Plan plan)
    ''')
    write_source(tmp_path, "lib/unloaded", '(export ghost) (define (ghost x) x)', budget=None)
    for path, newline in ((library, "\r\n"), (source, "\r")):
        path.write_bytes(path.read_text().replace("\n", newline).encode())
    providers, prompts = tmp_path / "providers.json", tmp_path / "prompts.json"
    providers.write_text(json.dumps({"providers.secret": "not-a-public-provider-id"}))
    prompts.write_text(json.dumps({"prompts.secret": {"asset_file": "private-prompt-content.md"}}))
    built = prepare_dynamic_program_bundle(FrontendBuildRequest(
        source_path=source, workspace_root=tmp_path, source_roots=(tmp_path,),
        provider_externs_path=providers, prompt_externs_path=prompts,
    ))
    return NativeLoadedModule(built, source), (source, library, old)


def test_native_catalog_projects_actual_visibility_and_contracts(catalog, tmp_path):
    from orchestrator.workflow_lisp.dynamic import repl_inspect as inspect
    module, _paths = catalog
    before = module.build.program.artifact()
    rows = inspect.visible_declarations(module)
    names = {name for row in rows for name in row.names}
    assert {"Plan", "lib.Plan", "lib/native/Plan", "lib.helper", "selected", "old.Legacy", "run"} <= names
    assert not {"old-helper", "old.old-helper", "lib.private-helper", "lib.Private", "lib/unloaded/ghost"} & names
    local = inspect.inspect_name(module, "helper")
    imported = inspect.inspect_name(module, "lib.helper")
    assert "module: demo/main" in local and "module: lib/native" in imported
    assert "x: unavailable" in local and "type: Function" in local
    assert "returns: unavailable" in local and "effects: unavailable" in local
    assert "steps: List[String]" in inspect.inspect_name(module, "Plan")
    assert "READY, DONE" in inspect.inspect_name(module, "lib.Status")
    workflow = inspect.inspect_name(module, "run")
    assert "declared boundary schemas" in workflow and "plan: lib/native::Plan" in workflow
    assert "returns: lib/native::Plan" in workflow
    prompt = inspect.inspect_name(module, "lib.review")
    assert "task: text" in prompt and "plan: value" in prompt and "returns: Bool" in prompt
    for name, secret, kind in (("providers.secret", "not-a-public-provider-id", "Provider"),
                               ("prompts.secret", "private-prompt-content.md", "Prompt")):
        info = inspect.inspect_name(module, name)
        assert kind in info and "contract: unavailable" in info and secret not in info
        with pytest.raises(ReplRefusal, match="authored") as error:
            inspect.source_name(module, name)
        assert error.value.code == "repl_source_unavailable"
    assert "retained café" not in inspect.browse_module(module)
    assert module.build.program.artifact() == before
    assert not (tmp_path / ".orchestrate").exists()
    for name in ("private-helper", "lib.private-helper", "lib.Private", "old.old-helper", "lib/unloaded/ghost"):
        with pytest.raises(ReplRefusal) as error:
            inspect.inspect_name(module, name)
        assert error.value.code == "repl_name_unknown"


def test_native_source_uses_retained_normalized_snapshot_after_mutation_and_deletion(catalog, monkeypatch):
    from orchestrator.workflow_lisp.dynamic import repl_inspect as inspect
    module, paths = catalog
    expected = {name: inspect.source_name(module, name) for name in ("helper", "lib.helper", "lib.review", "Plan", "run")}
    assert "(define (helper x) (+ x 1))" in expected["helper"]
    for path in paths:
        path.write_text("invalid replacement")
        path.unlink()

    def no_disk(*_args, **_kwargs):
        pytest.fail("source inspection read the filesystem")

    monkeypatch.setattr(Path, "read_bytes", no_disk)
    monkeypatch.setattr(Path, "read_text", no_disk)
    for name, source in expected.items():
        assert inspect.source_name(module, name) == source
        assert "loaded snapshot: sha256:" in source
        assert "\r" not in source


@pytest.mark.parametrize("corruption", ["missing", "hash", "span", "identity"])
def test_native_source_refuses_missing_or_mismatched_snapshot(catalog, corruption):
    from orchestrator.workflow_lisp.dynamic import repl_inspect as inspect
    module, paths = catalog
    trace = module.build.source_read_trace
    snapshots = dict(trace.raw_bytes_by_path)
    if corruption == "missing":
        snapshots.pop(paths[0])
    elif corruption == "hash":
        snapshots[paths[0]] = b"corrupt"
    else:
        lowerer = module.build.lowerer
        params, body, workflow, form = lowerer.members["demo/main::helper"]
        if corruption == "span":
            form = replace(form, span=replace(form.span, end=replace(form.span.end, offset=form.span.end.offset - 1)))
        else:
            signature = form.items[1]
            wrong = replace(signature.items[0], resolved_name="wrong")
            signature = replace(signature, items=(wrong, *signature.items[1:]))
            form = replace(form, datum=replace(form.datum, items=(form.items[0], signature, *form.items[2:])))
        lowerer.members["demo/main::helper"] = (params, body, workflow, form)
    module.build = replace(module.build, source_read_trace=replace(trace, raw_bytes_by_path=snapshots))
    with pytest.raises(ReplRefusal) as error:
        inspect.source_name(module, "helper")
    assert error.value.code == "repl_source_unavailable"


def test_native_type_query_uses_literals_and_function_metadata_without_evaluation(catalog, monkeypatch):
    from orchestrator.workflow_lisp.dynamic import repl_inspect as inspect
    from orchestrator.workflow_lisp.dynamic import repl_expr
    module, _paths = catalog

    def no_call(*_args, **_kwargs):
        pytest.fail("native type query evaluated or lowered the expression")

    monkeypatch.setattr(repl_expr, "_evaluate_body", no_call)
    monkeypatch.setattr(module.build.lowerer, "lower", no_call)
    for text, kind in (("7", "Int"), ("true", "Bool"), ("1.5", "Float"), ('"two words"', "String"),
                       ("helper", "Function"), ("lib.helper", "Function"), ("selected", "Function")):
        result = inspect.type_query(text, module)
        assert f"type: {kind}" in result
        assert "observed runtime kind" not in result
    for expression in ("(/ 1 0)", "(helper 7)", "(command-result no-such-command :argv () :returns Int)"):
        with pytest.raises(ReplRefusal) as error:
            inspect.type_query(expression, module)
        assert error.value.code == "repl_type_unavailable"
    with pytest.raises(ReplRefusal) as error:
        inspect.type_query("missing", module)
    assert error.value.code == "name_unknown"


def test_public_native_loaded_only_inspection_is_readonly(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (defrecord Answer (value Int))
      (define (identity x) x)
      (define (explode) (/ 1 0))
      (defworkflow run () -> Answer (record (value (identity 7))))
    ''')
    before = _hashes(tmp_path)
    repl = _repl(tmp_path, [_load(source, tmp_path), ":browse", ":info identity", ":source identity",
                            ":info run", ":info Answer", ":type identity", ":type 7", ":type (explode)",
                            ":where", ":quit"])
    assert repl.returncode == 0, repl.stderr
    assert "function: demo/main::identity, identity" in repl.stdout and "value: Int" in repl.stdout
    assert "(define (identity x) x)" in repl.stdout
    assert "type: Function" in repl.stdout and "type: Int" in repl.stdout
    assert "[repl_type_unavailable]" in repl.stderr
    assert "[repl_not_attached]" in repl.stderr and "division_by_zero" not in repl.stderr
    assert _hashes(tmp_path) == before


def test_public_native_captured_closure_type_is_observed_and_where_has_no_provenance(tmp_path):
    source = write_source(tmp_path, "demo/main", '''
      (export run)
      (define (n x) x)
      (defworkflow run ((n Int :default 7)) -> Int
        (let* ((closure (fn (x) (+ n x)))) (closure 0)))
    ''')
    run = _run(tmp_path, source)
    assert run.returncode == 0, run.stderr
    root = _run_root(tmp_path)
    before = _hashes(root)
    repl = _repl(tmp_path, [_load(source, tmp_path), f":attach {root.name}", ":type closure", ":type n",
                            ":info n", ":where closure", ":where", ":where missing", ":type (closure 5)", ":quit"])
    assert repl.returncode == 0, repl.stderr
    assert "type: Function\nbasis: observed runtime kind" in repl.stdout
    assert "type: Int\nbasis: observed runtime kind" in repl.stdout
    assert "function: demo/main::n, n" in repl.stdout
    assert repl.stderr.count("[repl_no_result_file]") == 2
    assert "[name_unknown]" in repl.stderr and "[repl_type_unavailable]" in repl.stderr
    assert _hashes(root) == before


@pytest.mark.parametrize("kind", ["command", "provider"])
def test_public_native_effect_inspection_never_calls_or_changes_run(tmp_path, kind):
    case = _write_case(tmp_path, kind)
    control = tmp_path / "control"
    control.mkdir()
    run = _run_cli(case, control)
    assert run.returncode == 0, run.stderr
    root = _run_root(tmp_path)
    before, calls = _hashes(root), _events(control)
    repl = _repl(tmp_path, [_load_case(case), f":attach {root.name}", ":browse", ":info main", ":source main",
                            ":type 1", ":type main", ":type (main)", ":where", ":quit"],
                 env=_inspection_env(control, kind))
    assert repl.returncode == 0, repl.stderr
    assert "workflow: demo/main::main, main" in repl.stdout and "loaded snapshot: sha256:" in repl.stdout
    assert "[repl_type_unavailable]" in repl.stderr and "[repl_no_result_file]" in repl.stderr
    assert _events(control) == calls
    assert _hashes(root) == before
