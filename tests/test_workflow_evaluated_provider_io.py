"""Physical readers travel with requests, independently of semantic interning."""
from dataclasses import replace
from copy import deepcopy
import json
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed.build import Builder, _build_with_builder
from orchestrator.workflow_lisp.closed.frontend import (
    _select_and_finalize_typed_program,
    compile_typed_program,
)
from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.reader import SourceReadTrace


CONFIG = {"provider_externs": {"provider": "provider-id"},
          "prompt_externs": {"prompt": {"asset_file": "prompt.md"}},
          "command_boundaries": {}}
PRODUCER = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
  (defmodule cp/producer) (export run Box) (defrecord Box (n Int))
  (defworkflow run ((input Box)) -> Box
    (provider-result provider :prompt prompt :inputs (input.n) :returns Box)))'''
WREF = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule main) (export run) (defrecord Box (n Int))
  (defproc foo ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box
    :effects ((uses-provider provider) (calls-workflow runner)) :lowering inline
    (let* ((own (provider-result provider :prompt prompt :inputs (input.n) :returns Box)))
      (call runner :input own)))
  (defworkflow run ((input Box)) -> Box
    (let* ((a (foo (workflow-ref left) input))
           (b (foo (workflow-ref right) a))) b)))'''


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _stages(tmp_path, sources=None, entry="cp/producer.orc", name="cp/producer::run"):
    root = tmp_path / "original"
    sources = sources or {entry: PRODUCER, "cp/prompt.md": "TARGET LEFT\n"}
    source_paths = [_write(root / relative, text) for relative, text in sources.items()]
    source_read_trace = SourceReadTrace()
    result = compile_stage3_entrypoint(root / entry, entry_workflow="run", source_roots=(root,),
        workspace_root=root, validate_shared=True, source_read_trace=source_read_trace,
        **CONFIG)
    snapshot = _select_and_finalize_typed_program(
        result.entry_result,
        entry_path=root / entry,
        entry_workflow=name,
        export_surface=result.graph.export_surfaces_by_name[
            result.graph.entry_module_name
        ],
        diagnostics=result.diagnostics,
    )
    expected_reads = {path.resolve() for path in source_paths if path.suffix == ".orc"}
    actual_reads = {
        path for path, _ in source_read_trace.revision_vector
        if path.suffix == ".orc"
    }
    assert actual_reads == expected_reads
    assert set(snapshot._io_source_paths.values()) == expected_reads
    assert set(snapshot.source_file_digests) == set(snapshot._io_source_paths)
    assert snapshot.configuration_bindings["provider_externs"] == CONFIG["provider_externs"]
    assert snapshot.configuration_bindings["prompt_externs"] == CONFIG["prompt_externs"]
    for side in ("left", "right"):
        clone = tmp_path / side
        for relative, text in sources.items():
            if Path(relative).suffix != ".orc":
                _write(clone / relative, text)
        assert not tuple(clone.rglob("*.orc"))
    for path in source_paths:
        if path.suffix == ".orc":
            path.unlink()
    imports = {
        side: replace(snapshot, _io_source_paths={
            module: tmp_path / side / path.relative_to(root)
            for module, path in snapshot._io_source_paths.items()
        })
        for side in ("left", "right")
    }
    return snapshot, imports


def _reader_path(program, module=None):
    return program._io_source_paths[module or program.entry_module]


def _typed(tmp_path, source, imports):
    root = tmp_path / "consumer"
    path = _write(root / "main.orc", source)
    _write(root / "prompt.md", "PARENT INLINE\n")
    typed = compile_typed_program(path, entry_workflow="run", source_roots=(root,),
        workspace_root=root, imported_programs=imports, **CONFIG)
    path.unlink()
    return typed


def _checked(typed):
    builder = Builder(typed)
    closed = _build_with_builder(typed, builder)
    checked = ClosedProgram.from_artifact(closed.artifact())
    return checked, builder.provider_io.bind(checked)


def _calls(body):
    return [row for row in _ast_nodes(body) if row["k"] == "call"]


def test_original_wref_requests_keep_left_right_and_parent_reader(tmp_path):
    snapshot, imports = _stages(tmp_path)
    _reader_path(imports["right"]).with_name("prompt.md").write_text("TARGET RIGHT\n")
    before = snapshot.entry_dir, dict(snapshot.source_file_digests), dict(snapshot._io_source_paths)
    typed = _typed(tmp_path, WREF, imports)
    checked, io = _checked(typed)
    a, b = _calls(checked.tree["body"])
    assert a["callee"] == b["callee"]
    owner = a["callee"]
    own_site = next(site for site_owner, site in checked.sites if site_owner == owner)
    inner, = _calls(checked.tree["definitions"][owner]["body"])
    for call, side in ((a, "left"), (b, "right")):
        foo = io.call(checked.tree["entry"], call["frame"], io.entry)
        assert io.effect(owner, own_site, foo).workflow_path.parent == tmp_path / "consumer"
        target = io.call(owner, inner["frame"], foo)
        assert target.reader.workflow_path == _reader_path(imports[side])
    assert (snapshot.entry_dir, dict(snapshot.source_file_digests),
        dict(snapshot._io_source_paths)) == before
    assert imports["left"].entry is imports["right"].entry is snapshot.entry
    assert imports["left"].source_file_digests == imports["right"].source_file_digests
    assert imports["left"].configuration_bindings == imports["right"].configuration_bindings


def test_original_direct_requests_share_body_with_distinct_physical_readers(tmp_path):
    _, imports = _stages(tmp_path)
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord Box (n Int))
      (defworkflow run ((input Box)) -> Box
        (let* ((a (call left :input input)) (b (call right :input a))) b)))'''
    checked, io = _checked(_typed(tmp_path, source, imports))
    a, b = _calls(checked.tree["body"])
    assert a["callee"] == b["callee"]
    for call, side in ((a, "left"), (b, "right")):
        child = io.call(checked.tree["entry"], call["frame"], io.entry)
        assert child.reader.workflow_path == _reader_path(imports[side])


@pytest.mark.parametrize("wrapper", ("alias", "forward", "bound", "nested-bound"))
def test_reference_forwarding_preserves_creation_selection(tmp_path, wrapper):
    _, imports = _stages(tmp_path)
    source = WREF
    if wrapper in {"alias", "forward"}:
        argument = "runner" if wrapper == "forward" else "alias"
        body = f"(foo {argument} input)"
        if wrapper == "alias":
            body = f"(let* ((alias runner)) {body})"
        declaration = f'''(defproc outer ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box
          :effects ((uses-provider provider) (calls-workflow runner)) :lowering inline {body})'''
        source = source.replace("(defworkflow run", declaration + "\n  (defworkflow run")
        source = source.replace("(foo (workflow-ref", "(outer (workflow-ref")
    else:
        declaration = '''(defproc invoke ((hook ProcRef[Box -> Box]) (input Box)) -> Box
          :effects ()
          :lowering inline (hook input))'''
        source = source.replace("(defworkflow run", declaration + "\n  (defworkflow run")
        for side in ("left", "right"):
            bound = f"(bind-proc (proc-ref foo) :runner (workflow-ref {side}))"
            if wrapper == "nested-bound":
                bound = f"(bind-proc (proc-ref invoke) :hook {bound})"
            source = source.replace(f"(foo (workflow-ref {side})", f"(invoke {bound}")
    checked, io = _checked(_typed(tmp_path, source, imports))
    root_owner = checked.tree["entry"]
    for outer, side in zip(_calls(checked.tree["body"]), ("left", "right"), strict=True):
        activation = io.call(root_owner, outer["frame"], io.entry)
        while True:
            inner, = _calls(checked.tree["definitions"][activation.owner]["body"])
            activation = io.call(activation.owner, inner["frame"], activation)
            if activation.reader.workflow_path == _reader_path(imports[side]):
                break
        assert activation.reader.workflow_path == _reader_path(imports[side])


def test_carrier_rebind_rejects_missing_or_wrong_checked_coordinates(tmp_path):
    _, imports = _stages(tmp_path)
    checked, io = _checked(_typed(tmp_path, WREF, imports))
    coordinate = next(iter(io.calls))
    with pytest.raises(ValueError, match="carrier does not match"):
        replace(io, calls={}).bind(checked)
    calls = dict(io.calls)
    calls[coordinate] = replace(calls[coordinate], callee=checked.tree["entry"])
    with pytest.raises(ValueError, match="carrier does not match"):
        replace(io, calls=calls).bind(checked)
    with pytest.raises(ValueError, match="owner/site"):
        io.effect("unknown", "unknown", io.entry)
    outer, _ = _calls(checked.tree["body"])
    coordinate = checked.tree["entry"], outer["frame"]
    calls = dict(io.calls)
    calls[coordinate] = replace(calls[coordinate], references={})
    with pytest.raises(ValueError, match="reference slots"):
        replace(io, calls=calls).bind(checked)
    calls = dict(io.calls)
    calls[coordinate] = replace(calls[coordinate], reader=("slot", ("runner",)))
    with pytest.raises(ValueError, match="route"):
        replace(io, calls=calls).bind(checked)


def test_relocation_changes_only_physical_carrier(tmp_path):
    snapshot, imports = _stages(tmp_path)
    original_paths = dict(snapshot._io_source_paths)
    first, first_io = _checked(_typed(tmp_path / "a", WREF, imports))
    moved = {
        side: replace(program, _io_source_paths={
            module: tmp_path / "moved" / side / path.relative_to(tmp_path / side)
            for module, path in program._io_source_paths.items()
        })
        for side, program in imports.items()
    }
    second, second_io = _checked(_typed(tmp_path / "b", WREF, moved))
    assert first.digest == second.digest
    assert first.sites == second.sites
    assert first.tree["definitions"].keys() == second.tree["definitions"].keys()
    assert dict(snapshot._io_source_paths) == original_paths
    for checked, io, selected in ((first, first_io, imports), (second, second_io, moved)):
        outer, _ = _calls(checked.tree["body"])
        foo = io.call(checked.tree["entry"], outer["frame"], io.entry)
        inner, = _calls(checked.tree["definitions"][foo.owner]["body"])
        assert io.call(foo.owner, inner["frame"], foo).reader.workflow_path == _reader_path(selected["left"])


@pytest.mark.parametrize("mode", ("inline", "private-workflow"))
def test_original_procedure_snapshot_preserves_reader_decision(tmp_path, mode):
    sources = {
        "lib/helper.orc": f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule lib/helper) (export R ask) (defrecord R (n Int))
          (defproc ask () -> R :effects ((uses-provider provider)) :lowering {mode}
            (provider-result provider :prompt prompt :inputs () :returns R)))''',
        "app/parent.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule app/parent) (import lib/helper :as helper) (export run)
          (defworkflow run () -> helper.R (helper.ask)))''',
        "lib/prompt.md": "PRIVATE HELPER\n", "app/prompt.md": "PARENT\n"}
    _, imports = _stages(tmp_path, sources, "app/parent.orc", "app/parent::run")
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord R (n Int))
      (defworkflow run () -> R (call parent)))'''
    checked, io = _checked(_typed(tmp_path, source, {"parent": imports["left"]}))
    outer, = _calls(checked.tree["body"])
    parent = io.call(checked.tree["entry"], outer["frame"], io.entry)
    inner, = _calls(checked.tree["definitions"][outer["callee"]]["body"])
    helper = io.call(outer["callee"], inner["frame"], parent)
    expected = parent.reader.workflow_path if mode == "inline" else _reader_path(
        imports["left"], "lib/helper")
    assert helper.reader.workflow_path == expected


def test_private_procedure_reference_uses_selected_typed_program_source(tmp_path):
    sources = {
        "lib/helper.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule lib/helper) (export R ask) (defrecord R (n Int))
          (defproc ask () -> R :effects ((uses-provider provider)) :lowering private-workflow
            (provider-result provider :prompt prompt :inputs () :returns R)))''',
        "app/parent.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule app/parent) (import lib/helper :as helper) (export run)
          (defproc invoke ((hook ProcRef[ -> helper.R])) -> helper.R
            :effects () :lowering inline (hook))
          (defworkflow run () -> helper.R (invoke (proc-ref helper.ask))))''',
        "lib/prompt.md": "PRIVATE HELPER\n"}
    _, imports = _stages(tmp_path, sources, "app/parent.orc", "app/parent::run")
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord R (n Int))
      (defworkflow run () -> R (call parent)))'''
    checked, io = _checked(_typed(tmp_path, source, {"parent": imports["left"]}))
    activation = io.entry
    for _ in range(3):
        body = checked.tree["body"] if activation.owner == checked.tree["entry"] else checked.tree["definitions"][activation.owner]["body"]
        call, = _calls(body)
        activation = io.call(activation.owner, call["frame"], activation)
    assert activation.reader.workflow_path.name == "helper.orc"
    assert activation.reader.workflow_path == _reader_path(imports["left"], "lib/helper")
    assert activation.reader.workflow_path != _reader_path(imports["left"])


def test_build_result_delivers_carrier_bound_to_returned_readback(tmp_path):
    from orchestrator.workflow_lisp.build import FrontendBuildRequest
    from orchestrator.workflow_lisp.closed.artifact import build_closed_program_bundle

    source = _write(tmp_path / "source.orc", '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defworkflow run () -> Bool (provider-result provider :prompt prompt :inputs () :returns Bool)))''')
    providers = _write(tmp_path / "providers.json", json.dumps(CONFIG["provider_externs"]))
    prompts = _write(tmp_path / "prompts.json", json.dumps(CONFIG["prompt_externs"]))
    result = build_closed_program_bundle(FrontendBuildRequest(source_path=source, workspace_root=tmp_path, entry_workflow="run",
        provider_externs_path=providers, prompt_externs_path=prompts))
    carrier = result.provider_io.bind(result.program)
    owner, site = result.program.sites[0]
    assert carrier.effect(owner, site, carrier.entry).workflow_path == source
    assert "provider_io" not in result.program.artifact()


def test_local_procedure_reference_preserves_reader_after_source_deletion(tmp_path):
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord Box (n Int))
      (defproc invoke ((hook ProcRef[Box -> Box]) (input Box)) -> Box
        :effects () :lowering inline (hook input))
      (defworkflow run ((input Box)) -> Box
        (let-proc (local ((value Box)) -> Box :captures ()
          (provider-result provider :prompt prompt :inputs (value.n) :returns Box))
          (invoke (proc-ref local) input))))'''
    checked, io = _checked(_typed(tmp_path, source, {}))
    activation = io.entry
    for _ in range(2):
        body = checked.tree["body"] if activation.owner == checked.tree["entry"] else checked.tree["definitions"][activation.owner]["body"]
        call, = _calls(body)
        activation = io.call(activation.owner, call["frame"], activation)
    owner, site = next(row for row in checked.sites if row[0] == activation.owner)
    assert io.effect(owner, site, activation).workflow_path.parent == tmp_path / "consumer"


def test_direct_typed_import_retains_selected_source_reader(tmp_path):
    root = tmp_path / "producer"
    path = _write(root / "cp/producer.orc", PRODUCER.replace("2.34", "2.35"))
    producer = compile_typed_program(path, entry_workflow="run", source_roots=(root,), **CONFIG)
    source = _write(tmp_path / "main.orc", '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord Box (n Int))
      (defworkflow run ((input Box)) -> Box (call child :input input)))''')
    typed = compile_typed_program(source, entry_workflow="run", source_roots=(tmp_path,),
        imported_programs={"child": producer}, **CONFIG)
    path.unlink()
    source.unlink()
    checked, io = _checked(typed)
    call, = _calls(checked.tree["body"])
    assert io.call(checked.tree["entry"], call["frame"], io.entry).reader.workflow_path == path


def test_iteration_override_uses_actual_private_reader(tmp_path):
    sources = {
        "lib/helper.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule lib/helper) (export R ask) (defrecord R (n Int))
          (defproc ask ((input R)) -> R :effects ((uses-provider provider)) :lowering inline
            (provider-result provider :prompt prompt :inputs (input.n) :returns R)))''',
        "app/parent.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule app/parent) (import lib/helper :as helper) (export run)
          (defworkflow run ((input helper.R)) -> helper.R
            (loop/recur :max 1 :state input
              (fn (state) (let* ((asked (helper.ask state))) (done asked))))))''',
        "lib/prompt.md": "PRIVATE HELPER\n"}
    _, imports = _stages(tmp_path, sources, "app/parent.orc", "app/parent::run")
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord R (n Int))
      (defworkflow run ((input R)) -> R (call parent :input input)))'''
    checked, io = _checked(_typed(tmp_path, source, {"parent": imports["left"]}))
    outer, = _calls(checked.tree["body"])
    parent = io.call(checked.tree["entry"], outer["frame"], io.entry)
    inner, = _calls(checked.tree["definitions"][parent.owner]["body"])
    helper = io.call(parent.owner, inner["frame"], parent)
    expected = _reader_path(imports["left"], "lib/helper")
    assert helper.reader.workflow_path == expected
    assert helper.reader.workflow_path != parent.reader.workflow_path


def _bound_typed(tmp_path):
    _, imports = _stages(tmp_path)
    declaration = '''(defproc invoke ((hook ProcRef[Box -> Box]) (input Box)) -> Box
        :effects () :lowering inline (hook input))'''
    source = WREF.replace("(defworkflow run", declaration + "\n(defworkflow run")
    for side in ("left", "right"):
        source = source.replace(f"(foo (workflow-ref {side})",
            f"(invoke (bind-proc (proc-ref foo) :runner (workflow-ref {side}))")
    return _typed(tmp_path, source, imports)


def test_bound_workflow_formal_requires_validated_caller_signature(tmp_path, monkeypatch):
    from orchestrator.workflow_lisp.closed import names
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef

    typed = _bound_typed(tmp_path)
    original = names._procedure_reference_key
    def mismatched(resolved, **kwargs):
        args = tuple(replace(arg, type_ref=PrimitiveTypeRef("Int"))
            if arg.name == "runner" else arg for arg in resolved.bound_args)
        return original(replace(resolved, bound_args=args), **kwargs)
    monkeypatch.setattr(names, "_procedure_reference_key", mismatched)
    with pytest.raises(ValueError, match="bound formal type disagrees"):
        _checked(typed)


@pytest.mark.parametrize("part", ("params", "result"))
def test_bound_workflow_resolved_signature_requires_catalog_match(tmp_path, monkeypatch, part):
    from orchestrator.workflow_lisp.closed import names
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef

    typed = _bound_typed(tmp_path)
    original = names._workflow_reference_key
    def mismatched(resolved, **kwargs):
        wrong = PrimitiveTypeRef("Bool")
        updated = (replace(resolved, return_type_ref=wrong) if part == "result"
            else replace(resolved, signature_params=(("input", wrong),)))
        return original(updated, **kwargs)
    monkeypatch.setattr(names, "_workflow_reference_key", mismatched)
    with pytest.raises(ValueError, match="workflow signature does not match"):
        _checked(typed)


def test_bound_workflow_wire_requires_native_signature(tmp_path):
    from orchestrator.contracts.closed_program.check import CheckedFormError, validate

    checked, _ = _checked(_bound_typed(tmp_path))
    tree = deepcopy(checked.tree)
    row = next(row for row in tree["definitions"].values() if row["key"][4])
    bound = row["key"][4][0][1]["bound"][0]
    assert bound[1]["signature"]["result"]["name"].startswith("cp/producer")
    for ref in (*bound[1]["signature"]["params"], bound[1]["signature"]["result"]):
        ref["name"] = ref["name"].replace("cp/producer", "main")
    with pytest.raises(CheckedFormError):
        validate(tree)


def test_capture_remap_preserves_nominal_objects_and_original_facts(tmp_path):
    from orchestrator.workflow_lisp.closed.names import _remap_capture_fact_scope

    typed = _bound_typed(tmp_path)
    reference = next(proc.specialization.workflow_ref_bindings["runner"]
        for proc in typed.procedures.values() if proc.specialization is not None
        and "runner" in proc.specialization.workflow_ref_bindings)
    facts = {"bound": {"capture": {"capture": 2},
        "runner": {"workflow": {"resolved": reference, "facts": {"target": {}}}}}}
    result = _remap_capture_fact_scope(facts, {2: 7})
    assert result["bound"]["capture"] == {"capture": 7}
    assert facts["bound"]["capture"] == {"capture": 2}
    assert result["bound"]["runner"]["workflow"]["resolved"] is reference
    with pytest.raises(ValueError, match="no target-scope route"):
        _remap_capture_fact_scope(facts, {})


def test_transitive_workflow_uses_current_typed_import(tmp_path):
    sources = {
        "lib/helper.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule lib/helper) (export R ask) (defrecord R (n Int))
          (defworkflow ask ((input R)) -> R
            (provider-result provider :prompt prompt :inputs (input.n) :returns R)))''',
        "app/parent.orc": '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule app/parent) (import lib/helper :as helper) (export run)
          (defworkflow run ((input helper.R)) -> helper.R
            (call helper.ask :input input)))''',
        "lib/prompt.md": "HELPER\n"}
    snapshot, imports = _stages(tmp_path, sources, "app/parent.orc", "app/parent::run")
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord R (n Int))
      (defworkflow run ((input R)) -> R
        (let* ((a (call left :input input)) (b (call right :input a))) b)))'''
    checked, io = _checked(_typed(tmp_path, source, imports))
    left, right = _calls(checked.tree["body"])
    assert left["callee"] == right["callee"]
    for call, side in ((left, "left"), (right, "right")):
        parent = io.call(checked.tree["entry"], call["frame"], io.entry)
        child, = _calls(checked.tree["definitions"][parent.owner]["body"])
        selected = io.call(parent.owner, child["frame"], parent)
        assert selected.reader.workflow_path == _reader_path(imports[side], "lib/helper")
    assert imports["left"].entry is imports["right"].entry is snapshot.entry


@pytest.mark.parametrize("alias", (False, True))
def test_parametric_forwarding_keeps_reference_created_in_parent_reader(tmp_path, alias):
    body = "(let* ((alias hook)) (apply alias))" if alias else "(apply hook)"
    helper = _write(tmp_path / "consumer" / "lib/helper.orc", f'''
      (workflow-lisp (:language "0.1") (:target-dsl "2.35")
        (defmodule lib/helper) (export outer apply)
        (defproc apply :forall (T) ((hook ProcRef[() -> T])) -> T
          :effects () :lowering inline (hook))
        (defproc outer :forall (U) ((hook ProcRef[() -> U])) -> U
          :effects () :lowering inline {body}))''')
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (import lib/helper :as helper) (export run)
      (defproc ask () -> Bool :effects ((uses-provider provider)) :lowering inline
        (provider-result provider :prompt prompt :inputs () :returns Bool))
      (defworkflow run () -> Bool
        (loop/recur :max 1 :state false
          (fn (state) (let* ((result (helper.outer (proc-ref ask)))) (done result))))))'''
    typed = _typed(tmp_path, source, {})
    helper.unlink()
    checked, io = _checked(typed)
    outer, = _calls(checked.tree["body"])
    consumer = io.call(checked.tree["entry"], outer["frame"], io.entry)
    assert consumer.reader.workflow_path == helper
    assert consumer.references[("hook",)].workflow_path == io.entry.reader.workflow_path
    forwarded, = _calls(checked.tree["definitions"][consumer.owner]["body"])
    target = io.call(consumer.owner, forwarded["frame"], consumer)
    assert target.references[("hook",)].workflow_path == io.entry.reader.workflow_path
