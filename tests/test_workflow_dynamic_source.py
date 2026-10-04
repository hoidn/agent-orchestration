"""Production dynamic source, real module linking, and persisted provenance."""
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import SourceReadTrace


def write_source(root: Path, module: str, body: str, *, budget=1000, target="3.0") -> Path:
    path = root / (module + ".orc")
    path.parent.mkdir(parents=True, exist_ok=True)
    budget_header = f"(:budget {budget})" if budget is not None else ""
    path.write_text(f'(workflow-lisp (:language "0.1") (:target-dsl "{target}") {budget_header} (defmodule {module}) {body})')
    return path


def compile_source(path, root, **kwargs):
    from orchestrator.workflow_lisp.dynamic.source import compile_source
    return compile_source(path, source_roots=(root,), **kwargs).program


def test_public_workflow_and_ordinary_captures_evaluate_after_source_deletion(tmp_path):
    from orchestrator.workflow.dynamic.evaluator import evaluate as evaluate_dynamic_program
    path = write_source(tmp_path, "demo/main", """
      (export main)
      (define (apply f x) (f x))
      (defworkflow main ((n Int :default 3)) -> Int
        (let* ((delta 2)) (apply (fn (x) (+ x delta)) n)))
    """)
    trace = SourceReadTrace()
    program = compile_source(path, tmp_path, source_read_trace=trace)
    assert len(trace.module_graph_read_attempts) == 1
    path.unlink()
    assert evaluate_dynamic_program(program, {"n": 3}).json_value() == 5
    boundary = program.definitions[program.entry]["boundary"]
    assert boundary["defaults"]["n"] == 3
    assert program.definitions["demo/main::apply"]["boundary"] is None
    assert any(row["captures"] == ("delta",) for row in program.definitions.values())
    assert all(row["span"]["start"]["path"] == "demo/main.orc" for row in program.source_map["entries"].values())


def test_imported_dynamic_workflow_and_declaration_only_old_source(tmp_path):
    from orchestrator.workflow.dynamic.evaluator import evaluate as evaluate_dynamic_program
    write_source(tmp_path, "old/types", "(export Box) (defrecord Box (n Int)) (defmacro unused () absent)", budget=None, target="2.35")
    write_source(tmp_path, "demo/lib", "(import old/types :only (Box)) (export box) (defworkflow box ((n Int)) -> Box (record (n n)))", budget=None)
    path = write_source(tmp_path, "demo/main", "(import demo/lib :only (box)) (export main) (defworkflow main () -> Int (field (box 4) \"n\"))")
    program = compile_source(path, tmp_path)
    assert evaluate_dynamic_program(program, {}).json_value() == 4
    assert program.definitions["demo/lib::box"]["owner"]["asset_base"] == "demo"
    assert "old/types::Box" in program.schemas


@pytest.mark.parametrize("body,budget", [
    ("(defworkflow main () -> Int 1)", None),
    ("(defworkflow main () -> Int 1)", 0),
    ("(defworkflow main () 1)", 100),
    ("(define (bad x x) x) (defworkflow main () -> Int 1)", 100),
    ("(define (bad) unknown) (defworkflow main () -> Int 1)", 100),
    ("(define (bad) (run-ref foo)) (defworkflow main () -> Int 1)", 100),
    ("(defworkflow main () -> Int 1) (defworkflow main () -> Int 2)", 100),
])
def test_all_source_bodies_and_headers_are_checked(tmp_path, body, budget):
    path = write_source(tmp_path, "demo/main", body, budget=budget)
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_source(path, tmp_path)
    assert caught.value.diagnostics[0].span.start.path == str(path)


def test_build_publishes_checked_artifact_and_refuses_compiled_imports(tmp_path):
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.dynamic.build import build_dynamic_program_bundle
    from orchestrator.workflow_lisp.dynamic.program import DynamicProgram
    path = write_source(tmp_path, "demo/main", "(export main) (defworkflow main () -> Int 1)")
    request = FrontendBuildRequest(source_path=path, source_roots=(tmp_path,), workspace_root=tmp_path)
    built = build_dynamic_program_bundle(request)
    assert DynamicProgram.from_artifact(built.artifact_path.read_bytes()).digest == built.program.digest
    assert built.manifest_path.is_file()
    from dataclasses import replace
    manifest = tmp_path / "imports.json"
    manifest.write_text("{}")
    with pytest.raises(LispFrontendCompileError) as caught:
        build_dynamic_program_bundle(replace(request, imported_workflow_bundles_path=manifest))
    assert caught.value.diagnostics[0].code == "dynamic_import_incompatible"


def test_direct_command_and_imported_prompt_ownership(tmp_path):
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
    write_source(tmp_path, "old/prompts", '(export review) (defrecord Review (ok Bool)) (defprompt review (:fills (draft :text)) -> Review "Review {draft}")', target="2.35", budget=None)
    path = write_source(tmp_path, "demo/main", '''
      (import old/prompts :only (review))
      (export main)
      (define (run-tool) (command-result tool :argv ("python" "tool.py" true) :returns Int))
      (defworkflow main ((draft String)) -> Value
        (provider-result providers.review :effort draft :prompt (review :draft draft) :model draft))
    ''')
    program = compile_source(path, tmp_path, command_boundaries={"tool": ExternalToolBinding("tool", ("python", "tool.py"), closure=())}, provider_externs={"providers.review": "local"})
    command = program.definitions["demo/main::run-tool"]["body"]
    assert command["k"] == "let"
    assert command["bindings"][0][1] == {"k": "lit", "v": "True"}
    provider = program.definitions[program.entry]["body"]["body"]
    assert provider["prompt_owner"]["module"] == "old/prompts"
    assert provider["inputs"] == ()
    from orchestrator.workflow_lisp.dynamic.program import _pointer
    pointer = _pointer(_pointer("/definitions", program.entry), "body") + "/body"
    entries = program.source_map["entries"]
    assert entries[pointer + "/prompt"]["source"] == "old/prompts"
    assert entries[pointer + "/result"]["source"] == "old/prompts"
    assert entries[pointer + "/prompt/fills/0/value"]["source"] == "demo/main"


@pytest.mark.parametrize("call", [
    '(command-result tool :argv ("python") :inputs () :returns Int)',
    '(command-result tool :argv ("python") :input-type Empty :returns Int)',
    '(provider-result providers.review :prompt prompts.base :inputs (1) :returns Int)',
    '(provider-result providers.review :prompt prompts.base :timeout-sec (+ 1 2) :returns Int)',
    '(provider-result providers.review :prompt prompts.base :delivery "phased" :returns Int)',
])
def test_unsupported_effect_boundaries_are_checked_when_unreachable(tmp_path, call):
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
    path = write_source(tmp_path, "demo/main", f'(export main) (defrecord Empty) (define (bad) {call}) (defworkflow main () -> Int 1)')
    with pytest.raises(LispFrontendCompileError):
        compile_source(path, tmp_path, command_boundaries={"tool": ExternalToolBinding("tool", ("python",), closure=())}, provider_externs={"providers.review": "local"}, prompt_externs={"prompts.base": "prompt.md"})


@pytest.mark.parametrize("entry", [None, "main", "demo/main::main"])
def test_existing_entry_selection_and_source_free_error_locations(tmp_path, entry):
    from orchestrator.workflow.dynamic.evaluator import evaluate
    path = write_source(tmp_path, "demo/main", '(export main) (define (read x) (field x "missing")) (defworkflow main () -> Int (read 1))')
    program = compile_source(path, tmp_path, entry_workflow=entry)
    path.unlink()
    with pytest.raises(ValueError) as caught:
        evaluate(program, {})
    assert caught.value.code == "dynamic_operand_type"
    assert caught.value.metadata["module"] == "demo/main"
    assert caught.value.metadata["span"]["start"]["path"] == "demo/main.orc"
    assert "read" in caught.value.metadata["artifact_pointer"]


def test_lexical_code_ids_and_semantics_are_independent_of_whitespace(tmp_path):
    path = write_source(tmp_path, "demo/main", '(export main) (define (make n) (fn (x) (+ x n))) (defworkflow main () -> Int ((make 1) 2))')
    before = compile_source(path, tmp_path)
    path.write_text("; heading\n\n" + path.read_text())
    after = compile_source(path, tmp_path)
    assert before.semantic_digest == after.semantic_digest
    assert before.provenance_digest != after.provenance_digest
    closure_code = next(name for name in before.definitions if "$fn/" in name)
    assert closure_code == "demo/main::make$fn/body"
    assert before.definitions[closure_code]["captures"] == ("n",)


def test_document_order_is_preserved_before_schema_ordering_and_empty_document_admits(tmp_path):
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
    path = write_source(tmp_path, "demo/main", '''(export main)
      (defrecord Input (a Int) (b Int)) (defrecord Empty)
      (define (empty) (command-result tool :argv ("python") :inputs () :input-type Empty :returns Int))
      (defworkflow main () -> Int (command-result tool :inputs ((b 2) (a 1)) :argv ("python" false) :input-type Input :returns Int))''')
    program = compile_source(path, tmp_path, command_boundaries={"tool": ExternalToolBinding("tool", ("python",), closure=())})
    body = program.definitions[program.entry]["body"]
    assert [row[1]["v"] for row in body["bindings"]] == [2, 1, "False"]
    assert [row[0] for row in body["body"]["document"]] == ["a", "b"]
    assert program.definitions["demo/main::empty"]["body"]["document"] == ()


@pytest.mark.parametrize("document", [False, True])
def test_certified_raw_argv_and_promoted_document_use_actual_binding_types(tmp_path, document):
    from orchestrator.workflow_lisp.command_boundaries import CertifiedAdapterBinding, CertifiedAdapterInputField
    from tests.test_workflow_lisp_closed_program_check import _certified_command_row
    row = _certified_command_row(signature=[{"name": "payload", "type_name": "Int", "required": True, "transport_key": "data"}])
    row.pop("kind")
    row["input_signature"] = tuple(CertifiedAdapterInputField(**field) for field in row["input_signature"])
    binding = CertifiedAdapterBinding(**row)
    clause = ':adapter adapter-fetch :inputs ((payload 4))' if document else ':argv ("python" "adapter.py" 4)'
    step = "invoke" if document else "adapter-fetch"
    path = write_source(tmp_path, "demo/main", f'(export main) (defworkflow main () -> Int (command-result {step} {clause} :returns Int))')
    program = compile_source(path, tmp_path, command_boundaries={"adapter-fetch": binding})
    effect = program.definitions[program.entry]["body"]["body"]
    assert ("document" in effect) is document
    assert program.bindings["demo/main"]["types"] == {"Int": "Int"}
    assert "input_type" not in effect


def test_prompt_path_refinement_dependencies_and_guidance_retain_native_owners(tmp_path):
    path = write_source(tmp_path, "demo/main", '''(export main)
      (defpath NotePath :kind relpath :under "notes" :must-exist true)
      (defprompt review (:fills (note :doc NotePath) (value :value)) -> (result Int :description "score") "Review {value}")
      (defworkflow main ((note NotePath)) -> Int
        (provider-result providers.review :prompt (review :value 1 :note note)
          :prompt-dependencies (:optional (note) :position append :instruction "read")))''')
    program = compile_source(path, tmp_path, provider_externs={"providers.review": "local"})
    effect = program.definitions[program.entry]["body"]["body"]
    assert effect["prompt"]["fills"][0]["type"]["kind"] == "path"
    assert effect["prompt"]["fills"][1]["type"] == {"kind": "primitive", "name": "Value"}
    assert effect["dependencies"]["position"] == "append"
    assert "description" in effect["contract"]["payload"]["fields"][0]


def test_build_refuses_symlinked_publication_and_retains_frozen_trace(tmp_path):
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.dynamic.build import prepare_dynamic_program_bundle, build_dynamic_program_bundle
    path = write_source(tmp_path, "demo/main", "(export main) (defworkflow main () -> Int 1)")
    request = FrontendBuildRequest(source_path=path, workspace_root=tmp_path)
    trace = SourceReadTrace()
    built = prepare_dynamic_program_bundle(request, source_read_trace=trace)
    before = built.source_read_trace.records
    assert before
    with pytest.raises(TypeError):
        built.source_paths["extra"] = path
    other = tmp_path / "other"
    other.mkdir()
    (tmp_path / ".orchestrate").symlink_to(other, target_is_directory=True)
    with pytest.raises(OSError):
        build_dynamic_program_bundle(request)
    assert list(other.iterdir()) == []
    assert built.source_read_trace.records == before


@pytest.mark.parametrize("name", ["if", "fn", "+", "command-result"])
def test_workflow_names_use_the_same_reserved_binder_rule(tmp_path, name):
    path = write_source(tmp_path, "demo/main", f"(export {name}) (defworkflow {name} () -> Int 1)")
    with pytest.raises(LispFrontendCompileError) as caught:
        compile_source(path, tmp_path)
    assert caught.value.diagnostics[0].code == "dynamic_source_invalid"


@pytest.mark.parametrize("certified", [False, True])
@pytest.mark.parametrize("number,admitted", [(-(2**63), True), (2**63 - 1, True), (-(2**63)-1, False), (2**63, False)])
def test_raw_argv_literal_numeric_formation_precedes_rendering(tmp_path, certified, number, admitted):
    from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding, CertifiedAdapterBinding, CertifiedAdapterInputField
    if certified:
        from tests.test_workflow_lisp_closed_program_check import _certified_command_row
        row = _certified_command_row(signature=[{"name": "payload", "type_name": "Int", "required": True, "transport_key": "data"}])
        row.pop("kind")
        row["input_signature"] = tuple(CertifiedAdapterInputField(**field) for field in row["input_signature"])
        binding = CertifiedAdapterBinding(**row)
        name, stable = "adapter-fetch", '"python" "adapter.py"'
    else:
        name, stable = "tool", '"python"'
        binding = ExternalToolBinding("tool", ("python",), closure=())
    path = write_source(tmp_path, "demo/main", f'(export main) (define (unused) (command-result {name} :argv ({stable} {number}) :returns Int)) (defworkflow main () -> Int 1)')
    if admitted:
        program = compile_source(path, tmp_path, command_boundaries={name: binding})
        assert program.definitions["demo/main::unused"]["body"]["bindings"][0][1]["v"] == str(number)
    else:
        with pytest.raises(LispFrontendCompileError) as caught:
            compile_source(path, tmp_path, command_boundaries={name: binding})
        assert caught.value.diagnostics[0].span.start.path == str(path)
