from pathlib import Path

import pytest

from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.command_boundaries import ExternalToolBinding
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from tests.workflow_lisp_closed_program_helpers import install


INT_SOURCE = '''(workflow-lisp
  (:language "0.1") (:target-dsl "2.35")
  (defmodule probe/shared_int) (export run)
  (defrecord Output (n Int))
  (defunion Choice (YES (n Int)) (NO (n Int)))
  (defproc extract :forall (T) ((value T))
    :where ((T has-shared-union-field n Int)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (command-result probe :argv ("python" "probe.py" value.n) :returns Output))
  (defworkflow run () -> Output
    (extract (variant Choice YES :n 7))))'''

PATH_SOURCE = '''(workflow-lisp
  (:language "0.1") (:target-dsl "2.35")
  (defmodule probe/shared_path) (export run)
  (defpath ReportPath :kind relpath :under "state" :must-exist true)
  (defpath ArtifactPath :kind relpath :under "state" :must-exist true)
  (defrecord Output (status String))
  (defunion Choice (REPORT (artifact ReportPath)) (ARTIFACT (artifact ArtifactPath)))
  (defproc project :forall (T) ((choice T))
    :where ((T has-shared-union-field artifact Path.state-root)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (command-result probe :argv ("python" "probe.py" choice.artifact) :returns Output))
  (defworkflow run ((path ReportPath)) -> Output
    (project (variant Choice REPORT :artifact path))))'''

NESTED_SOURCE = '''(workflow-lisp
  (:language "0.1") (:target-dsl "2.35")
  (defmodule probe/shared_nested) (export run)
  (defrecord Payload (item-id String))
  (defrecord Output (status String))
  (defunion Selection (SELECTED (selection Payload)) (ALTERNATE (selection Payload)))
  (defproc choose :forall (SelectionT) ((choice SelectionT))
    :where ((SelectionT is-union)
            (SelectionT has-shared-union-field selection Payload)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (command-result probe
      :argv ("python" "probe.py" choice.selection.item-id) :returns Output))
  (defworkflow run () -> Output
    (choose (variant Selection SELECTED :selection (record Payload :item-id "seed")))))'''


@pytest.mark.parametrize("source,field_name,field_type", [
    pytest.param(INT_SOURCE, "n", "Int", id="int"),
    pytest.param(PATH_SOURCE, "artifact", "Path.state-root", id="directional-path"),
    pytest.param(NESTED_SOURCE, "selection", "Payload", id="nested-record"),
])
def test_closed_shared_union_projection_preserves_resolved_proof(
    tmp_path: Path, source: str, field_name: str, field_type: str,
) -> None:
    path = install(tmp_path, source)
    typed = compile_typed_program(
        path, entry_workflow=None, source_roots=(tmp_path,), workspace_root=tmp_path,
        command_boundaries={"probe": ExternalToolBinding(
            name="probe", stable_command=("python", "probe.py"), closure=("probe.py",),
        )},
    )
    capabilities = [
        capability
        for procedure in typed.procedures.values() if procedure.specialization is not None
        for capability in procedure.specialization.shared_union_field_capabilities
    ]
    assert any(cap.field_name == field_name and cap.field_type_ref.name == field_type
               for cap in capabilities)
    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert restored.digest == closed.digest


HELPER_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
  (defmodule helper) (export project Output Payload)
  (defrecord Payload (item-id String))
  (defrecord Output (status String))
  (defproc project :forall (T) ((choice T))
    :where ((T has-shared-union-field selection helper::Payload)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (command-result probe
      :argv ("python" "probe.py" choice.selection.item-id) :returns Output)))'''

ENTRY_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule entry) (import helper :as h) (export run)
  (defrecord Payload (item-id FIELD_TYPE))
  (defunion Choice (A (selection Payload)) (B (selection Payload)))
  (defworkflow run () -> h.Output
    (h.project (variant Choice A :selection (record Payload :item-id FIELD_VALUE)))))'''


def _imported_typed(root, *, field_type="String", field_value='"seed"', whitespace=""):
    path = install(root, {"helper.orc": whitespace + HELPER_SOURCE,
                         "entry.orc": whitespace + ENTRY_SOURCE.replace("FIELD_TYPE", field_type)
                         .replace("FIELD_VALUE", field_value)}, entry_path="entry.orc")
    return compile_typed_program(
        path, entry_workflow=None, source_roots=(root,), workspace_root=root,
        command_boundaries={"probe": ExternalToolBinding(
            name="probe", stable_command=("python", "probe.py"), closure=("probe.py",),
        )},
    )


def test_imported_homonymous_shared_record_retains_both_owners(tmp_path):
    typed = _imported_typed(tmp_path)
    closed = build_closed_program(typed)
    assert closed.tree["types"]["helper::Payload"] != closed.tree["types"]["entry::Payload"]
    assert ClosedProgram.from_artifact(closed.artifact()).digest == closed.digest


def test_imported_incompatible_shared_record_still_fails_typecheck(tmp_path):
    with pytest.raises(LispFrontendCompileError) as error:
        _imported_typed(tmp_path, field_type="Int", field_value="7")
    assert error.value.diagnostics[0].code == "parametric_constraint_unsatisfied"


def _nodes(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _nodes(value)
    elif isinstance(node, (list, tuple)):
        for child in node:
            yield from _nodes(child)


def test_imported_proof_survives_deleted_sources_and_relocation(tmp_path):
    import shutil
    first_root, second_root = tmp_path / "first", tmp_path / "second"
    typed = _imported_typed(first_root)
    shutil.rmtree(first_root)
    first = build_closed_program(typed)
    typed_again = _imported_typed(second_root, whitespace="\n\n\n")
    second = build_closed_program(typed_again)
    assert first.digest == second.digest
    assert first.sites == second.sites
    proofs = [node["shared"] for node in _nodes(first.tree) if node.get("k") == "field" and "shared" in node]
    assert any(rows[0]["name"] == "helper::Payload" and rows[1] is None for rows in proofs)
    assert ClosedProgram.from_artifact(first.artifact()).digest == first.digest


MATCH_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule probe/shared_match) (export run)
  (defrecord Output (status String))
  (defunion Inner (A (a String)) (B (b String)))
  (defunion Outer (LEFT (selection Inner)) (RIGHT (selection Inner)))
  (defproc extract :forall (T) ((choice T))
    :where ((T has-shared-union-field selection Inner)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (match choice.selection
      ((A proven) (command-result probe :argv ("python" "probe.py" proven.a) :returns Output))
      ((B proven) (command-result probe :argv ("python" "probe.py" proven.b) :returns Output))))
  (defworkflow run ((flag Bool)) -> Output
    (let* ((inner (if flag (variant Inner A :a "left") (variant Inner B :b "right")))
           (choice (if flag (variant Outer LEFT :selection inner) (variant Outer RIGHT :selection inner)))
           (selected (extract choice))) selected)))'''


def test_shared_full_union_followed_by_real_match_keeps_variant_proof(tmp_path):
    from tests.workflow_lisp_closed_program_helpers import build
    closed = build(tmp_path, MATCH_SOURCE, boundaries={"probe": ExternalToolBinding(
        name="probe", stable_command=("python", "probe.py"), closure=("probe.py",))})
    fields = [node for node in _nodes(closed.tree) if node.get("k") == "field"]
    assert any(node.get("shared", [None])[0] == closed.tree["types"]["probe/shared_match::Inner"] for node in fields)
    assert any(node["path"] == ["a"] and "shared" not in node for node in fields)
    restored = ClosedProgram.from_artifact(closed.artifact())
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value
    def command(node, args, site, _owner, _reader):
        return coerce_evaluated_value({"status": args[-1].value}, node["result"])
    assert evaluate_closed_program(restored, {"flag": True}, effect_handler=command).value == {"status": "left"}
    assert evaluate_closed_program(restored, {"flag": False}, effect_handler=command).value == {"status": "right"}


PREFIX_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule probe/shared_prefix) (export run)
  (defrecord Payload (item-id String))
  (defrecord Output (status String))
  (defunion Choice (A (selection Payload)) (B (selection Payload)))
  (defrecord Envelope (choice Choice))
  (defproc project :forall (T) ((choice T))
    :where ((T has-shared-union-field selection Payload)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (command-result probe
      :argv ("python" "probe.py" choice.selection.item-id) :returns Output))
  (defworkflow run ((choice Choice)) -> Output
    (let* ((envelope (record Envelope :choice choice))) (project envelope.choice))))'''


def test_ordinary_prefix_shared_segment_and_suffix_stay_aligned(tmp_path):
    from tests.workflow_lisp_closed_program_helpers import build
    closed = build(tmp_path, PREFIX_SOURCE, boundaries={"probe": ExternalToolBinding(
        name="probe", stable_command=("python", "probe.py"), closure=("probe.py",))})
    fields = [node for node in _nodes(closed.tree) if node.get("k") == "field"]
    projection = next(node for node in fields if node.get("path") == ["selection", "item-id"])
    assert projection["shared"] == [closed.tree["types"]["probe/shared_prefix::Payload"], None]
    assert any(node["path"] == ["choice"] and "shared" not in node for node in fields)
    assert ClosedProgram.from_artifact(closed.artifact()).digest == closed.digest


def test_shared_adapter_inputs_retain_checked_expressions_in_authored_order(tmp_path):
    from orchestrator.workflow_lisp.build import _parse_command_boundaries_manifest
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import CommandResultExpr
    source = INT_SOURCE.replace(':argv ("python" "probe.py" value.n)',
        ':adapter probe :inputs ((second value.n) (first value.n))')
    boundary = _parse_command_boundaries_manifest({"probe": {
        "kind": "certified_adapter", "stable_command": ["python", "probe.py"], "closure": [],
        "input_contract": {"type": "object"}, "output_type_name": "Output",
        "effects": ["structured_result"], "path_safety": {"kind": "workspace_relpath"},
        "source_map_behavior": "step", "fixture_ids": ["ok"], "negative_fixture_ids": ["bad"],
        "behavior_class": "structured_result", "owner_module": "probe/shared_int",
        "artifact_contracts": [], "state_writes": [], "error_codes": [], "replacement_path": None,
        "invocation_protocol": "json_object_positional_arg",
        "input_signature": [{"name": name, "type_name": "Int", "required": True,
                             "transport_key": name} for name in ("first", "second")],
    }}, manifest_path=None)
    path = install(tmp_path, source)
    typed = compile_typed_program(path, entry_workflow=None, source_roots=(tmp_path,),
        workspace_root=tmp_path, command_boundaries=boundary)
    procedure = next(p for p in typed.procedures.values() if p.specialization is not None)
    command = next(n for n in walk_expr(procedure.typed_body.expr) if isinstance(n, CommandResultExpr))
    assert [name for name, _ in command.adapter_inputs] == ["second", "first"]
    assert all(value.shared_field_types[0].name == "Int" for _, value in command.adapter_inputs)
    closed = build_closed_program(typed)
    assert ClosedProgram.from_artifact(closed.artifact()).digest == closed.digest


def test_shared_fact_concatenation_aligns_ordinary_prefix_and_suffix(tmp_path):
    from dataclasses import replace
    from orchestrator.workflow_lisp.expression_traversal import map_expr, walk_expr
    from orchestrator.workflow_lisp.expressions import FieldAccessExpr, NameExpr
    typed = _imported_typed(tmp_path)
    procedure = next(p for p in typed.procedures.values() if p.specialization is not None)
    field = next(n for n in walk_expr(procedure.typed_body.expr) if isinstance(n, FieldAccessExpr))
    prefix = replace(field, base=replace(field.base, name="envelope"), fields=("choice",), shared_field_types=())
    combined = map_expr(field, lambda n: prefix if isinstance(n, NameExpr) and n.name == field.base.name else n)
    assert combined.fields == ("choice", "selection", "item-id")
    assert combined.shared_field_types == (None, field.shared_field_types[0], None)
    assert replace(field, shared_field_types=()) == field
    assert hash(replace(field, shared_field_types=())) == hash(field)


BOUND_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule probe/shared_bound) (export run)
  (defrecord Output (n Int))
  (defunion Choice (YES (n Int)) (NO (n Int)))
  (defproc deliver ((fixed Int)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (command-result probe :argv ("python" "probe.py" fixed) :returns Output))
  (defproc forward :forall (T) ((value T))
    :where ((T has-shared-union-field n Int)) -> Output
    :effects ((uses-command probe)) :lowering inline
    (let* ((runner (bind-proc (proc-ref deliver) :fixed value.n))) (runner)))
  (defworkflow run ((flag Bool)) -> Output
    (forward (if flag (variant Choice YES :n 7) (variant Choice NO :n 9)))))'''


def test_shared_projection_survives_forwarding_and_bound_reference(tmp_path):
    from tests.workflow_lisp_closed_program_helpers import build
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value
    closed = build(tmp_path, BOUND_SOURCE, boundaries={"probe": ExternalToolBinding(
        name="probe", stable_command=("python", "probe.py"), closure=("probe.py",))})
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert any(n.get("k") == "field" and n.get("shared") for n in _nodes(closed.tree))
    deliver = next(d for d in closed.tree["definitions"].values() if d["key"][2] == "deliver")
    assert deliver["key"][7] == [{"type": {"kind": "primitive", "name": "Int"},
                                  "routes": [["parameter", "fixed"]]}]
    def command(node, args, site, _owner, _reader):
        return coerce_evaluated_value({"n": args[-1].value}, node["result"])
    assert evaluate_closed_program(restored, {"flag": True}, effect_handler=command).value == {"n": 7}
    assert evaluate_closed_program(restored, {"flag": False}, effect_handler=command).value == {"n": 9}


def test_older_helper_nested_enum_union_and_containers_preserve_source_owners(tmp_path):
    from tests.workflow_lisp_closed_program_helpers import build
    declarations = '''(defenum Status A B)
      (defunion Nested (ON (status Status)) (OFF (status Status)))
      (defrecord Leaf (status Status))'''
    fields = '(item-id String) (status Status) (nested Nested) (leaves List[Leaf])'
    helper = HELPER_SOURCE.replace('(defrecord Payload (item-id String))',
        declarations + '\n  (defrecord Payload ' + fields + ')')
    entry = ENTRY_SOURCE.replace('(defrecord Payload (item-id FIELD_TYPE))',
        declarations + '\n  (defrecord Payload ' + fields + ')').replace(
        '(record Payload :item-id FIELD_VALUE)',
        '(record Payload :item-id "seed" :status Status.A :nested (variant Nested ON :status Status.A) :leaves (list (record Leaf :status Status.B)))')
    closed = build(tmp_path, {"helper.orc": helper, "entry.orc": entry}, entry_path="entry.orc",
        boundaries={"probe": ExternalToolBinding(name="probe", stable_command=("python", "probe.py"), closure=("probe.py",))})
    restored = ClosedProgram.from_artifact(closed.artifact())
    for basename in ("Payload", "Nested", "Leaf", "Status"):
        assert closed.tree["types"]["entry::" + basename] != closed.tree["types"]["helper::" + basename]
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    from orchestrator.workflow.evaluated.values import coerce_evaluated_value
    def command(node, args, site, _owner, _reader):
        return coerce_evaluated_value({"status": args[-1].value}, node["result"])
    assert evaluate_closed_program(restored, {}, effect_handler=command).value == {"status": "seed"}


def test_wcc_frontend_reconstruction_retains_aligned_segment_facts(tmp_path):
    from dataclasses import replace
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import FieldAccessExpr
    from orchestrator.workflow_lisp.wcc.model import WccNodeMetadata, WccNameAtom, WccFieldAccessAtom
    from orchestrator.workflow_lisp.wcc.lower import _inline_expr_from_wcc_value
    from orchestrator.workflow_lisp.wcc.defunctionalize import _frontend_expr_from_wcc_value, _frontend_expr_from_wcc_value_with_env
    typed = _imported_typed(tmp_path)
    procedure = next(p for p in typed.procedures.values() if p.specialization is not None)
    field = next(n for n in walk_expr(procedure.typed_body.expr) if isinstance(n, FieldAccessExpr))
    metadata = WccNodeMetadata(node_id="field", scope_id="scope", type_ref=procedure.signature.params[0][1],
                               source_span=field.span, form_path=field.form_path)
    base = WccNameAtom(metadata=metadata, name=field.base.name)
    atom = WccFieldAccessAtom(metadata=metadata, base=base, fields=field.fields, shared_field_types=field.shared_field_types)
    for restored in (_inline_expr_from_wcc_value(atom, {}), _frontend_expr_from_wcc_value(atom),
                     _frontend_expr_from_wcc_value_with_env(atom, {})):
        assert restored.shared_field_types == field.shared_field_types
    prefix = replace(field, base=replace(field.base, name="envelope"), fields=("choice",), shared_field_types=())
    combined = _frontend_expr_from_wcc_value_with_env(atom, {field.base.name: prefix})
    assert combined.fields == ("choice", "selection", "item-id")
    assert combined.shared_field_types == (None, field.shared_field_types[0], None)


@pytest.mark.parametrize("flag,expected", [(True, 7), (False, 9)])
def test_pure_shared_int_survives_inline_retyping(tmp_path, flag, expected):
    from tests.workflow_lisp_closed_program_helpers import build
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    source = BOUND_SOURCE.replace('''-> Output
    :effects ((uses-command probe)) :lowering inline
    (let* ((runner (bind-proc (proc-ref deliver) :fixed value.n))) (runner))''',
        '''-> Int :effects () :lowering inline value.n''').replace('(defworkflow run ((flag Bool)) -> Output', '(defworkflow run ((flag Bool)) -> Int')
    closed = build(tmp_path, source, boundaries={"probe": ExternalToolBinding(
        name="probe", stable_command=("python", "probe.py"), closure=("probe.py",))})
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert evaluate_closed_program(restored, {"flag": flag}).value == expected


@pytest.mark.parametrize("flag,expected", [(True, "left"), (False, "right")])
def test_pure_shared_full_union_then_match_survives_inline_retyping(tmp_path, flag, expected):
    from tests.workflow_lisp_closed_program_helpers import build
    from orchestrator.workflow.evaluated.machine import evaluate_closed_program
    source = MATCH_SOURCE.replace('''-> Output
    :effects ((uses-command probe)) :lowering inline
    (match choice.selection
      ((A proven) (command-result probe :argv ("python" "probe.py" proven.a) :returns Output))
      ((B proven) (command-result probe :argv ("python" "probe.py" proven.b) :returns Output)))''',
        '''-> Inner :effects () :lowering inline choice.selection''').replace('(defworkflow run ((flag Bool)) -> Output', '(defworkflow run ((flag Bool)) -> String').replace('''(selected (extract choice))) selected''', '''(selected (extract choice))) (match selected ((A proven) proven.a) ((B proven) proven.b))''')
    closed = build(tmp_path, source, boundaries={})
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert evaluate_closed_program(restored, {"flag": flag}).value == expected


@pytest.mark.parametrize("mutation", ["absent", "incompatible", "missing-variant", "scalar", "unresolved"])
def test_inline_retyping_revalidates_retained_targets_and_keeps_original_refusal(tmp_path, mutation):
    from dataclasses import replace
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import FieldAccessExpr
    from orchestrator.workflow_lisp.typecheck import typecheck_expression
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef, TypeParamRef
    typed = _imported_typed(tmp_path)
    procedure = next(p for p in typed.procedures.values() if p.specialization is not None)
    field = next(n for n in walk_expr(procedure.typed_body.expr) if isinstance(n, FieldAccessExpr))
    actual = procedure.signature.params[0][1]
    if mutation == "absent":
        field = replace(field, shared_field_types=())
    elif mutation in {"incompatible", "unresolved"}:
        target = PrimitiveTypeRef(name="Int") if mutation == "incompatible" else TypeParamRef(name="Unresolved")
        field = replace(field, shared_field_types=(target, None))
    elif mutation == "missing-variant":
        variants = dict(actual.variant_field_types)
        variants[next(iter(variants))] = {}
        actual = replace(actual, variant_field_types=variants)
    else:
        actual = PrimitiveTypeRef(name="Int")
    with pytest.raises(LispFrontendCompileError) as error:
        typecheck_expression(field, type_env=typed.type_env, value_env={field.base.name: actual})
    assert error.value.diagnostics[0].code in {"variant_ref_unproved", "record_field_unknown"}


def test_inline_retyping_context_capability_replaces_prior_target(tmp_path):
    from dataclasses import replace
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import FieldAccessExpr
    from orchestrator.workflow_lisp.typecheck import typecheck_expression
    from orchestrator.workflow_lisp.type_env import PrimitiveTypeRef
    from orchestrator.workflow_lisp.parametric_constraints import SharedUnionFieldCapability
    typed = _imported_typed(tmp_path)
    procedure = next(p for p in typed.procedures.values() if p.specialization is not None)
    field = next(n for n in walk_expr(procedure.typed_body.expr) if isinstance(n, FieldAccessExpr))
    target = field.shared_field_types[0]
    actual = procedure.signature.params[0][1]
    wrong = replace(field, shared_field_types=(PrimitiveTypeRef(name="Int"), None))
    checked = typecheck_expression(wrong, type_env=typed.type_env, value_env={field.base.name: actual},
        shared_union_field_capabilities=(SharedUnionFieldCapability(actual.name, "selection", target),))
    assert checked.expr.shared_field_types == (target, None)


@pytest.mark.parametrize("shared", [True, False], ids=["certified", "ordinary"])
def test_union_leaf_projection_preserves_shared_suffix_alignment(tmp_path, shared):
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import UnionVariantExpr
    from orchestrator.workflow_lisp.lowering.values import _union_variant_expr_value_at_path
    from orchestrator.workflow_lisp.typecheck import typecheck_expression
    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule probe/concat) (export run)
      (defrecord Payload (item-id String))
      (defrecord Envelope (selection Payload))
      (defunion Choice (A (selection Payload)) (B (selection Payload)))
      (defunion Wrap (DONE (payload Payload)))
      (defproc wrap :forall (T) ((choice T))
        :where ((T has-shared-union-field selection Payload)) -> Wrap
        :effects () :lowering inline (variant Wrap DONE :payload choice.selection))
      (defworkflow run ((choice Choice)) -> Wrap (wrap choice)))'''
    if not shared:
        source = source.replace(':forall (T) ((choice T))', '((choice Envelope))').replace(
            ':where ((T has-shared-union-field selection Payload)) ', '').replace(
            '(defworkflow run ((choice Choice))', '(defworkflow run ((choice Envelope))')
    path = install(tmp_path, source)
    typed = compile_typed_program(path, entry_workflow=None, source_roots=(tmp_path,),
                                  workspace_root=tmp_path, command_boundaries={})
    procedure = next(p for p in typed.procedures.values()
                     if (p.specialization is not None) == shared)
    variant = next(n for n in walk_expr(procedure.typed_body.expr) if isinstance(n, UnionVariantExpr))
    original = variant.fields[0][1]
    projected = _union_variant_expr_value_at_path(variant, ("payload", "item-id"), bound_record_fields=True)
    closed = build_closed_program(typed)
    assert ClosedProgram.from_artifact(closed.artifact()).digest == closed.digest
    assert projected.fields == ("selection", "item-id")
    assert projected.shared_field_types == ((*original.shared_field_types, None) if shared else ())
    retyped = typecheck_expression(projected, type_env=typed.type_env,
                                  value_env=dict(procedure.signature.params))
    assert retyped.type_ref.name == "String"
    assert retyped.expr.shared_field_types == projected.shared_field_types
