from __future__ import annotations

from copy import deepcopy

import pytest

from orchestrator.workflow_lisp.closed.program import ClosedProgram, canonical_digest
from orchestrator.workflow_lisp.closed.program import ClosedProgramInvalid
from tests.test_workflow_lisp_closed_command_transport import _commands
from tests.test_workflow_lisp_closed_program_check import _command_result_tree, _document_command_tree, _lit
from tests.test_workflow_lisp_closed_program_compile_cli import _build_state, _write_workspace


def _public_document(tmp_path, inputs):
    files = _write_workspace(tmp_path)
    files["source"].write_text(f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule grt/entry) (export run)
      (defworkflow run ((n Int)) -> Int
        (command-result probe_revise :argv ("python" "probe_revise.py" "${{inputs.n}}")
          {inputs} :returns Int)))''')
    return files, _build_state(files)


@pytest.mark.parametrize("inputs,present", [("", False), (":inputs ()", True), (":inputs ((payload n))", True)])
def test_closed_external_document_checks_both_operand_lanes(tmp_path, inputs, present):
    files, (_, program, artifact) = _public_document(tmp_path, inputs)
    (command,) = _commands(program.tree)
    assert ("document" in command) is present
    assert len(command["argv"]) == 1
    slot = command["argv_transport"][0]["parts"][0]
    assert slot["kind"] == "slot"
    assert slot["value"]["n"] == program.tree["params"][0][0]
    for source in files["source_root"].rglob("*.orc"):
        source.unlink()
    restored = ClosedProgram.from_artifact(artifact.decode())
    assert restored.digest == program.digest
    assert _commands(restored.tree) == [command]


def _read_resealed(tree):
    # Serialize malformed operands without visiting the trusted AST walker;
    # the reader validates the tree and derives its checked digest independently.
    altered = ClosedProgram(tree=tree, sites=tuple(tuple(row) for row in tree["sites"]), digest=canonical_digest(tree))
    return ClosedProgram.from_artifact(altered.artifact())


@pytest.mark.parametrize("keys", [["payload", "payload"], [""], [1], None, [["payload"]]])
def test_resealed_external_document_rejects_invalid_keys_and_rows(keys):
    tree, command = _command_result_tree()
    command["document"] = None if keys is None else [[key, _lit(1)] for key in keys]
    if keys == [["payload"]]:
        command["document"] = [["payload"]]
    with pytest.raises(ClosedProgramInvalid, match="effect_shape"):
        _read_resealed(tree)


def test_resealed_external_document_does_not_hide_unbound_argv():
    tree, command = _command_result_tree()
    command["document"] = [["payload", _lit(1)]]
    command["argv"] = [{"k": "name", "n": "unbound"}]
    with pytest.raises(ClosedProgramInvalid, match="unbound_name"):
        _read_resealed(tree)


def test_resealed_certified_document_preserves_raw_signature_without_reconstruction():
    tree, command = _document_command_tree(["token_id", "token_detail", "target"])
    command["document"] = [[key, _lit("valid", {"kind": "primitive", "name": "String"})]
                           for key, _ in command["document"]]
    _read_resealed(tree)
    signature = deepcopy(tree["configuration"]["commands"]["adapter-fetch"]["input_signature"])
    command["document"][1][1] = _lit(2)
    restored = _read_resealed(tree)
    assert restored.tree["configuration"]["commands"]["adapter-fetch"]["input_signature"] == signature
    command["document"][1][1] = _lit("inconsistent")
    with pytest.raises(ClosedProgramInvalid, match="type_mismatch"):
        _read_resealed(tree)


def test_certified_imported_alias_is_preserved_in_source_free_readback(tmp_path):
    from dataclasses import replace
    from tests.test_workflow_lisp_command_input_documents import _adapter_commands
    from tests.workflow_lisp_closed_program_helpers import build

    bindings = {name: replace(binding, closure=()) for name, binding in _adapter_commands(tmp_path, "shared.Box").items()}
    program = build(tmp_path, {
        "models.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
          (defmodule models) (export Box) (defrecord Box (value Int)))''',
        "entry.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
          (defmodule entry) (import models :as shared :only (Box)) (export run)
          (defworkflow run ((box shared.Box)) -> String
            (command-result emit :adapter emit :inputs ((payload box)) :returns String)))''',
    }, entry_path="entry.orc", boundaries=bindings)
    assert program.tree["configuration"]["commands"]["emit"]["input_signature"][0]["type_name"] == "shared.Box"
    for source in tmp_path.rglob("*.orc"):
        source.unlink()
    restored = ClosedProgram.from_artifact(program.artifact())
    assert restored.tree == program.tree


@pytest.mark.parametrize("reference", [
    {"kind": "primitive", "name": "Provider"},
    {"kind": "list", "item": {"kind": "primitive", "name": "Provider"}},
    {"kind": "optional", "item": {"kind": "primitive", "name": "Prompt"}},
    {"kind": "map", "key": {"kind": "primitive", "name": "String"},
     "value": {"kind": "primitive", "name": "Provider"}},
])
def test_resealed_external_document_rejects_checked_nontransportable_value(reference):
    tree, command = _command_result_tree()
    tree["params"] = [["callback", reference]]
    command["document"] = [["payload", {"k": "name", "n": "callback"}]]
    with pytest.raises(ClosedProgramInvalid, match="type_mismatch"):
        _read_resealed(tree)


def test_external_translation_keeps_stable_token_value_error():
    from types import SimpleNamespace
    from orchestrator.workflow_lisp.closed.effects import _set_external_command_inputs

    effect = {"boundary": "fetch"}
    binding = SimpleNamespace(stable_command=("python", "probe.py"))
    perform = SimpleNamespace(positional_args=())
    with pytest.raises(ValueError, match="changed its stable command tokens"):
        _set_external_command_inputs(effect, binding, {}, perform, None, None, None)


@pytest.mark.parametrize("type_name", ["String", "List[Int]", "Optional[Int]", "Map[String,Int]", "List[Choice]", "Optional[List[Choice]]", "Map[String,List[Choice]]", "Candidate", "Asset"])
@pytest.mark.parametrize("certified", [False, True])
def test_source_free_document_keeps_recursive_nominal_descriptors(tmp_path, type_name, certified):
    from dataclasses import replace
    from tests.test_workflow_lisp_command_input_documents import _adapter_commands, _commands as bindings_for, _source
    from tests.workflow_lisp_closed_program_helpers import build

    declarations = '''(defpath Asset :kind relpath :under "assets" :must-exist false)
      (defunion Choice (YES (asset Asset)) (NO))
      (defrecord Candidate (choices List[Choice]) (note Optional[String]))'''
    commands = _adapter_commands(tmp_path, type_name) if certified else bindings_for(tmp_path)
    commands = {name: replace(binding, closure=()) for name, binding in commands.items()}
    mode = ':adapter emit' if certified else ':argv ("python" "emit.py")'
    program = build(tmp_path, _source(f'(command-result emit {mode} :inputs ((payload value)) :returns String)',
        params=f'(value {type_name})', declarations=declarations), boundaries=commands)
    command, = _commands(program.tree)
    assert command["argv"] == []
    assert command["document"][0][0] == ("body" if certified else "payload")
    assert command["document"][0][1]["n"] == program.tree["params"][0][0]
    for source in tmp_path.rglob("*.orc"):
        source.unlink()
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (program.tree, program.sites, program.digest)


def test_document_catalog_check_rejects_coherent_forged_nominal_descriptor():
    tree, command = _command_result_tree()
    descriptor = {"kind": "record", "name": "sample::Payload", "fields": [
        {"name": "value", "type": {"kind": "primitive", "name": "Int"}}]}
    tree["types"] = {descriptor["name"]: deepcopy(descriptor)}
    value = {"k": "record", "type": descriptor, "fields": [["value", _lit(1)]]}
    command["document"] = [["payload", value]]
    _read_resealed(tree)
    descriptor["fields"][0]["type"] = {"kind": "primitive", "name": "String"}
    value["fields"][0][1] = _lit("coherent", {"kind": "primitive", "name": "String"})
    with pytest.raises(ClosedProgramInvalid, match="nominal_definition"):
        _read_resealed(tree)


def test_imported_document_keeps_exact_command_owner_when_label_conflicts(tmp_path):
    from dataclasses import replace
    from tests.test_workflow_lisp_command_input_documents import _adapter_commands, _commands as bindings_for
    from tests.workflow_lisp_closed_program_helpers import install
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.closed.build import build_closed_program

    certified = {name: replace(binding, closure=(), stable_command=("python", "emit.py"))
                 for name, binding in _adapter_commands(tmp_path, "Int").items()}
    external = {name: replace(binding, closure=()) for name, binding in bindings_for(tmp_path).items()}
    producer_path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule producer) (export run)
      (defworkflow run ((n Int)) -> String
        (command-result emit :adapter emit :inputs ((payload n)) :returns String)))''')
    producer = compile_typed_program(producer_path, entry_workflow="run", source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=certified)
    consumer_path = install(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule consumer) (export run)
      (defworkflow run ((n Int)) -> String
        (command-result emit :argv ("python" "emit.py" n)
          :inputs ((payload (call producer :n n))) :returns String)))''')
    consumer = compile_typed_program(consumer_path, entry_workflow="run", source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=external, imported_programs={"producer": producer})
    producer_path.unlink()
    consumer_path.unlink()
    program = build_closed_program(consumer)
    root = program.tree["configuration"]["commands"]["emit"]
    definition, = [row for row in program.tree["definitions"].values()
                   if row["key"][:3] == ["producer", "workflow", "run"]]
    own = program.tree["configuration"]["imports"][definition["configuration"]]["commands"]["emit"]
    assert (root["kind"], own["kind"]) == ("external_tool", "certified_adapter")
    assert root["stable_command"] == own["stable_command"]
    commands = _commands(program.tree)
    assert {tuple(row[0] for row in command["document"]) for command in commands} == {("payload",), ("body",)}
    assert sorted(len(command["argv"]) for command in commands) == [0, 1]
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (program.tree, program.sites, program.digest)
    definition["configuration"] = "sha256:" + "0" * 64
    with pytest.raises(ClosedProgramInvalid, match="configuration_scope"):
        _read_resealed(program.tree)


@pytest.mark.parametrize("certified", [False, True])
def test_document_only_imported_effect_call_retains_sites_and_owner(tmp_path, certified):
    from dataclasses import replace
    from tests.test_workflow_lisp_command_input_documents import _adapter_commands, _commands as bindings_for
    from tests.workflow_lisp_closed_program_helpers import build

    commands = bindings_for(tmp_path, ("emit", "inc"))
    if certified:
        commands["emit"] = _adapter_commands(tmp_path, "Int")["emit"]
    commands = {name: replace(binding, closure=()) for name, binding in commands.items()}
    mode = ':adapter emit' if certified else ':argv ("python" "emit.py")'
    program = build(tmp_path, {
        "helper.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
          (defmodule helper) (export produce)
          (defproc produce ((x Int)) -> Int :effects ((uses-command inc)) :lowering private-workflow
            (command-result inc :argv ("python" "inc.py" x) :returns Int)))''',
        "entry.orc": f'''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
          (defmodule entry) (import helper :as h :only (produce)) (export run)
          (defworkflow run ((n Int)) -> String
            (command-result emit {mode} :inputs ((payload (h.produce n))) :returns String)))''',
    }, entry_path="entry.orc", boundaries=commands)
    _assert_imported_effect_sites(program)
    for source in tmp_path.rglob("*.orc"):
        source.unlink()
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (program.tree, program.sites, program.digest)


def _assert_imported_effect_sites(program):
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    assert {row["boundary"] for row in _commands(program.tree)} == {"inc", "emit"}
    calls = [node for node in _ast_nodes(program.tree["body"]) if node.get("k") == "call"]
    assert len(calls) == 1
    definition = program.tree["definitions"][calls[0]["callee"]]
    assert definition["key"][:3] == ["helper", "procedure", "produce"]
    assert len(program.sites) == 2


def test_document_only_local_capture_keeps_original_wire_after_shadowing(tmp_path):
    from dataclasses import replace
    from tests.test_workflow_lisp_command_input_documents import _commands as bindings_for
    from tests.workflow_lisp_closed_program_helpers import build
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    commands = {name: replace(binding, closure=()) for name, binding in bindings_for(tmp_path, ("emit", "inc")).items()}
    program = build(tmp_path, '''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule captured) (export run)
      (defproc invoke ((hook ProcRef[Int -> Int]) (x Int)) -> Int :effects () :lowering inline (hook x))
      (defworkflow run ((n Int)) -> String
        (let-proc (saved ((x Int)) -> Int :captures (n)
          (command-result inc :argv ("python" "inc.py" n x) :returns Int))
          (let* ((n 100))
            (command-result emit :argv ("python" "emit.py")
              :inputs ((payload (invoke (proc-ref saved) 1))) :returns String)))))''', boundaries=commands)
    calls = [node for node in _ast_nodes(program.tree["body"]) if node.get("k") == "call"]
    call, = calls
    assert _capture_origin_wire(call, program.tree["body"]) == program.tree["params"][0][0]
    producer = next(command for command in _commands(program.tree) if command["boundary"] == "inc")
    assert producer["argv"][1]["v"] == 1
    assert len(program.sites) == 2
    for source in tmp_path.rglob("*.orc"):
        source.unlink()
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (program.tree, program.sites, program.digest)


def _capture_origin_wire(call, body):
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes

    aliases = {node["name"]: node["value"] for node in _ast_nodes(body)
               if node.get("k") == "let" and node["value"].get("k") == "name"}
    origin = call["args"][0]["n"]
    while origin in aliases:
        origin = aliases[origin]["n"]
    return origin


@pytest.mark.parametrize("operand,accepted", [("choice", True), ("selected", False)])
def test_external_document_active_union_preserves_narrowed_transport_boundary(tmp_path, operand, accepted):
    from dataclasses import replace
    from tests.test_workflow_lisp_command_input_documents import _commands as bindings_for
    from tests.workflow_lisp_closed_program_helpers import build

    commands = {name: replace(binding, closure=()) for name, binding in bindings_for(tmp_path).items()}
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "TARGET")
      (defmodule narrowed) (export run) (defunion Choice (YES (n Int)) (NO))
      (defworkflow run ((choice Choice)) -> String
        (match choice
          ((YES selected) (command-result emit :argv ("python" "emit.py")
            :inputs ((payload {operand})) :returns String))
          ((NO empty) "none"))))'''
    if not accepted:
        from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
        with pytest.raises(LispFrontendCompileError) as rejected:
            build(tmp_path, source, boundaries=commands)
        assert rejected.value.diagnostics[0].code == "command_result_inputs_invalid"
        return
    program = build(tmp_path, source, boundaries=commands)
    command, = _commands(program.tree)
    assert command["document"][0][1]["k"] == "name"
    assert program.tree["params"][0][1]["kind"] == "union"
    for source in tmp_path.rglob("*.orc"):
        source.unlink()
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (program.tree, program.sites, program.digest)


def test_certified_document_preserves_admitted_duplicate_signature_rows():
    tree, command = _document_command_tree(["same", "same", "target"])
    signature = tree["configuration"]["commands"]["adapter-fetch"]["input_signature"]
    signature[0]["transport_key"] = "same"
    signature[1]["transport_key"] = "same"
    restored = _read_resealed(tree)
    assert restored.tree["configuration"]["commands"]["adapter-fetch"]["input_signature"] == signature
    assert _commands(restored.tree)[0]["document"] == command["document"]


def test_resealed_binding_kind_cannot_grant_certified_nonempty_argv():
    from tests.test_workflow_lisp_closed_program_check import _certified_command_row

    tree, command = _command_result_tree()
    command["argv"] = [_lit(1)]
    command["document"] = [["payload", _lit(1)]]
    _read_resealed(tree)
    row = _certified_command_row()
    row["stable_command"] = command["command"]
    row["closure"] = command["closure"]
    tree["configuration"]["commands"]["fetch"] = row
    with pytest.raises(ClosedProgramInvalid, match="effect_shape"):
        _read_resealed(tree)
