from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orchestrator.workflow.pure_expr import canonical_json_for_pure_value
from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from orchestrator.workflow_lisp.workflows import ExternalToolBinding
from orchestrator.workflow_lisp.closed.names import (
    Renamer,
    _normalize_closed_value,
    canonical_callee_name,
    canonical_definition_key,
    canonical_type_descriptor,
    canonical_type_identity,
    key_type_descriptor,
)


TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION


def _typed_nominal_program(root: Path):
    root.mkdir(parents=True)
    for module in ("a", "b"):
        (root / f"{module}.orc").write_text(
            f'''(workflow-lisp
              (:language "0.1") (:target-dsl "{TARGET}")
              (defmodule {module}) (export Outer PublicFlag)
              (defenum Flag yes no)
              (defenum PublicFlag yes no)
              (defpath Report :kind relpath :under "reports" :must-exist true)
              (defrecord Note (flag Flag) (path Report))
              (defrecord Outer (notes List[Note])))''',
            encoding="utf-8",
        )
    entry = root / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
          (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule entry)
          (import a :as left) (import b :as right)
          (export run)
          (defworkflow run ((first left.Outer) (second right.Outer)
                           (flag left.PublicFlag)) -> Int 1))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        entry, entry_workflow="run", source_roots=(root,), command_boundaries={}
    )
    for name in ("entry", "a", "b"):
        (root / f"{name}.orc").unlink()
    return typed


def test_canonical_nominal_descriptors_keep_private_owners_after_import_and_relocation(
    tmp_path: Path,
) -> None:
    here = _typed_nominal_program(tmp_path / "here")
    elsewhere = _typed_nominal_program(tmp_path / "elsewhere" / "deeper")

    def descriptors(typed):
        params = dict(typed.entry.signature.params)
        result = {}
        with patch.object(Path, "read_text", side_effect=AssertionError("source read")), patch.object(
            Path, "read_bytes", side_effect=AssertionError("source read")
        ):
            for param, module in (("first", "a"), ("second", "b")):
                ref = params[param]
                assert canonical_type_identity(ref, typed=typed) == f"{module}::Outer"
                desc = canonical_type_descriptor(ref, typed=typed)
                note = desc["fields"][0]["type"]["item"]
                assert note["name"] == f"{module}::Note"
                assert note["fields"][0]["type"]["name"] == f"{module}::Flag"
                assert note["fields"][1]["type"]["name"] == f"{module}::Report"
                assert note["fields"][1]["type"]["under"] == "reports"
                result[param] = desc
            flag = params["flag"]
            assert canonical_type_identity(flag, typed=typed) == "a::PublicFlag"
            result["flag"] = canonical_type_descriptor(flag, typed=typed)
        return result

    first = descriptors(here)
    second = descriptors(elsewhere)
    assert first == second
    assert first["first"] != first["second"]


def test_closed_imported_private_nesting_survives_generic_specialization_keys(
    tmp_path: Path,
) -> None:
    root = tmp_path / "private-owners"
    root.mkdir()
    for module in ("a", "b"):
        (root / f"{module}.orc").write_text(
            f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
              (defmodule {module}) (export Outer keep)
              (defenum Flag yes no)
              (defpath Report :kind relpath :under "reports" :must-exist true)
              (defrecord Note (flag Flag) (path Report))
              (defrecord Outer (notes List[Note]))
              (defproc identity :forall (T) ((value T)) -> T
                :effects () :lowering private-workflow value)
              (defworkflow keep ((value Outer)) -> Outer (identity value)))''',
            encoding="utf-8",
        )
    entry = root / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule entry) (import a :as left) (import b :as right) (export run)
          (defworkflow run ((first left.Outer) (second right.Outer)) -> left.Outer
            (let* ((first-result (call left.keep :value first))
                   (second-result (call right.keep :value second)))
              first-result)))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )
    for module in ("entry", "a", "b"):
        (root / f"{module}.orc").unlink()

    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    definitions = restored.tree["definitions"]
    for module in ("a", "b"):
        workflow = next(
            row
            for row in definitions.values()
            if row["key"][:3] == [module, "workflow", "keep"]
        )
        specialized = next(
            row
            for row in definitions.values()
            if row["key"][:3] == [module, "procedure", "identity"]
        )
        descriptor = workflow["params"][0][1]
        assert descriptor == workflow["result"]
        assert descriptor == specialized["params"][0][1] == specialized["result"]
        assert descriptor["name"] == f"{module}::Outer"
        note = descriptor["fields"][0]["type"]["item"]
        assert note["name"] == f"{module}::Note"
        assert note["fields"][0]["type"] == {
            "kind": "enum",
            "name": f"{module}::Flag",
            "allowed": ["yes", "no"],
        }
        path = note["fields"][1]["type"]
        assert path == {
            "kind": "path",
            "name": f"{module}::Report",
            "under": "reports",
            "must_exist_target": True,
        }
        assert specialized["key"][3] == [["T", descriptor]]

    params = restored.tree["params"]
    assert [name for name, _descriptor in params] == ["first", "second"]
    assert params[0][1]["name"] == "a::Outer"
    assert params[1][1]["name"] == "b::Outer"
    assert params[0][1] != params[1][1]


def test_renamer_preserves_authored_names_and_reserves_later_names() -> None:
    renamer = Renamer(reserved_names={"x", "%1", "__authored"})
    outer = {}
    assert renamer.bind("x", authored_label="x", env=outer) == "x"
    inner = dict(outer)
    assert renamer.bind("x_hygiene_digest", authored_label="x", env=inner) == "%2"
    assert renamer.ref("x_hygiene_digest", env=inner) == "%2"
    assert renamer.ref("x", env=outer) == "x"
    assert renamer.bind("__authored", authored_label="__authored", env=outer) == "__authored"
    assert renamer.bind("temporary", authored_label=None, env=inner) == "%3"


def test_renamer_uses_copied_lexical_scopes_and_parent_initializers() -> None:
    renamer = Renamer(reserved_names={"%1", "x", "later"})
    parent = {}
    assert renamer.bind("x", authored_label="x", env=parent) == "x"
    # The initializer reads the old binding before the shadowing binder exists.
    assert renamer.ref("x", env=parent) == "x"
    shadow = dict(parent)
    assert renamer.bind("x", authored_label="renamed_x", env=shadow) == "%2"
    assert renamer.ref("x", env=shadow) == "%2"
    assert renamer.ref("x", env=parent) == "x"

    first_sibling = dict(parent)
    assert renamer.bind("first", authored_label=None, env=first_sibling) == "%3"
    second_sibling = dict(parent)
    assert renamer.bind("second", authored_label=None, env=second_sibling) == "%4"
    assert "first" not in parent and "second" not in parent

    sequential_prefix = dict(parent)
    first_value = renamer.ref("x", env=sequential_prefix)
    assert first_value == "x"
    assert renamer.bind("prefix", authored_label=None, env=sequential_prefix) == "%5"
    second_value = renamer.ref("prefix", env=sequential_prefix)
    assert second_value == "%5"
    assert renamer.bind("prefix2", authored_label=None, env=sequential_prefix) == "%6"
    else_arm = dict(parent)
    assert renamer.bind("else_prefix", authored_label=None, env=else_arm) == "%7"
    assert "prefix" not in else_arm and "else_prefix" not in parent
    assert renamer.bind("later", authored_label="later", env=parent) == "later"


def test_closed_value_key_alpha_normalizes_nested_binders_and_omits_labels() -> None:
    int_type = {"kind": "primitive", "name": "Int"}
    list_type = {"kind": "list", "item": int_type}

    def expression(prefix_name: str, item_name: str, local_name: str, labels: tuple[str, str]):
        return {
            "k": "select",
            "cond": {"k": "lit", "v": True, "type": {"kind": "primitive", "name": "Bool"}},
            "then": {
                "prefix": [{"name": prefix_name, "label": labels[0], "value": {"k": "lit", "v": 1, "type": int_type}}],
                "value": {
                    "k": "list_map",
                    "binder": item_name,
                    "source": {"k": "list", "items": [{"k": "name", "n": prefix_name}], "type": list_type},
                    "body": {
                        "k": "block",
                        "body": {
                            "k": "let",
                            "name": local_name,
                            "label": labels[1],
                            "value": {"k": "name", "n": item_name},
                            "body": {
                                "k": "case",
                                "subject": {"k": "name", "n": local_name},
                                "arms": [
                                    {
                                        "variant": "Ready",
                                        "bind": "payload",
                                        "body": {"k": "done", "value": {"k": "name", "n": "payload"}},
                                    }
                                ],
                            },
                        },
                    },
                    "type": list_type,
                },
            },
            "else": {
                "prefix": [{"name": prefix_name + "2", "value": {"k": "lit", "v": 1, "type": int_type}}],
                "value": {"k": "name", "n": prefix_name + "2"},
            },
        }

    first = _normalize_closed_value(expression("left", "item", "result", ("first-label", "inner-label")))
    second = _normalize_closed_value(expression("renamed", "element", "answer", ("other-label", "other-inner")))
    assert first == second
    assert '"label"' not in json.dumps(first)
    assert first["then"]["prefix"][0]["name"] != "left"
    assert first["then"]["value"]["body"]["body"]["name"] != "result"


def test_loop_carriers_keep_expanded_declaration_family_in_canonical_identity(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/carriers) (export run)
      (defworkflow run () -> Int
        (let* ((left (loop-state (n Int 0)))
               (right (loop-state (n Int 1))))
          (+ left.n right.n))))'''

    def identities(root: Path, body: str):
        path = root / "cp/carriers.orc"
        path.parent.mkdir(parents=True)
        path.write_text(body, encoding="utf-8")
        typed = compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            command_boundaries={},
        )
        from orchestrator.workflow_lisp.expression_traversal import walk_expr
        from orchestrator.workflow_lisp.expressions import LoopStateSeedExpr
        from orchestrator.workflow_lisp.loop_state import carrier_metadata_for_expr

        env = typed.workflow_type_env(typed.entry.definition.name)
        result = []
        for node in walk_expr(typed.entry.typed_body.expr):
            if isinstance(node, LoopStateSeedExpr):
                metadata = carrier_metadata_for_expr(node, session_state=env.session_state)
                if metadata is not None:
                    from orchestrator.workflow_lisp.build_manifest_io import _json_data

                    assert "family=" not in repr(metadata)
                    assert "family" not in _json_data(metadata)
                    assert "loop_carrier_families_by_expr_key" not in repr(env.session_state)
                    assert "loop_carrier_families_by_expr_key" not in _json_data(env.session_state)
                    result.append(canonical_type_identity(metadata.type_ref, typed=typed))
        return result

    first = identities(tmp_path / "first", source)
    edited = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/carriers) (export run)
      (defworkflow run () -> Int
        (let* ((unused 0) (left (loop-state (n Int 0)))
               (right (loop-state (n Int 1))))
          (+ left.n right.n))))'''
    second = identities(tmp_path / "elsewhere" / "deeper", edited)
    assert len(first) == len(second) == 2
    assert first == second
    assert first[0] != first[1]


def test_generic_loop_carriers_keep_same_spelled_private_field_owners(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.build_manifest_io import _json_data
    from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor

    def identities(root: Path, *, relocate: bool) -> dict[str, tuple[str, dict]]:
        root.mkdir(parents=True)
        for module in ("a", "b"):
            (root / f"{module}.orc").write_text(
                f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
                  (defmodule {module}) (export get)
                  (defrecord Note (n Int))
                  (defproc get () -> Note :effects () :lowering inline
                    (record Note :n 1)))''',
                encoding="utf-8",
            )
        entry = root / "main.orc"
        prefix = "\n\n" if relocate else ""
        entry.write_text(
            prefix
            + f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
              (defmodule main) (import a :as a) (import b :as b) (export run)
              (defproc carry :forall (T) ((value T)) -> Int
                :effects () :lowering inline
                (let* ((state (loop-state (payload T value)))) 0))
              (defworkflow run () -> Int
                (+ (carry (a.get)) (carry (b.get)))))''',
            encoding="utf-8",
        )
        typed = compile_typed_program(
            entry,
            entry_workflow="run",
            source_roots=(root,),
            command_boundaries={},
        )
        for source in root.rglob("*.orc"):
            source.unlink()

        env = typed.type_env
        metadata_rows = [
            metadata
            for metadata in env.session_state.loop_carrier_metadata_by_name.values()
            if metadata.field_names == ("payload",)
            and metadata.field_types[0][1].name == "Note"
        ]
        assert len(metadata_rows) == 2
        assert len({metadata.generated_type_name for metadata in metadata_rows}) == 2
        projected = {}
        with patch.object(Path, "read_text", side_effect=AssertionError("source read")), patch.object(
            Path, "read_bytes", side_effect=AssertionError("source read")
        ):
            for metadata in metadata_rows:
                field_type = metadata.field_types[0][1]
                field_identity = canonical_type_identity(field_type, typed=typed)
                descriptor = canonical_type_descriptor(metadata.type_ref, typed=typed)
                assert descriptor["fields"][0]["type"]["name"] == field_identity
                projected[field_identity] = (
                    canonical_type_identity(metadata.type_ref, typed=typed),
                    descriptor,
                )
                assert "family=" not in repr(metadata)
                assert "family" not in _json_data(metadata)
        assert set(projected) == {"a::Note", "b::Note"}
        assert (
            projected["a::Note"][1]["name"].split("[", 1)[0]
            != projected["b::Note"][1]["name"].split("[", 1)[0]
        )
        return projected

    first = identities(tmp_path / "first", relocate=False)
    moved = identities(tmp_path / "elsewhere" / "deeper", relocate=True)
    assert first == moved
    assert first["a::Note"][0] != first["b::Note"][0]


def test_specialized_loop_carriers_project_same_run_ref_signature_and_keep_origins(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.closed.names import _run_ref_signatures
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import LoopStateSeedExpr
    from orchestrator.workflow_lisp.loop_state import carrier_metadata_for_expr
    from orchestrator.workflow_lisp.type_env import ListTypeRef, RecordTypeRef, UnionTypeRef

    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/carrier_refs) (export run)
      (defunion Wrapper :forall (T) (WRAP (value Int)))
      (defproc wrap :forall (T) ((value T)) -> Wrapper[T]
        :effects () :lowering inline (variant Wrapper[T] WRAP :value 0))
      (defproc carry :forall (T) ((value T)) -> Int
        :effects ((runs-ref child)) :lowering inline
        (let* ((state (loop-state (payload T value)))
               (check (run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                 :program (:path "child.orc" :entry child) :inputs (:n 0) :returns Int
                 :policy (:environment :deterministic-effect-free :setup ())))) 0))
      (defworkflow run () -> Int
        (let* ((first (run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                       :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
                       :policy (:environment :deterministic-effect-free :setup ())))
                   (second (run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                            :program (:path "child.orc" :entry child) :inputs (:n 1) :returns Int
                        :policy (:environment :deterministic-effect-free :setup ())))
               (a (carry first)) (b (carry second))
               (c (carry (list first))) (d (carry (list second)))
               (e (carry (wrap first))) (f (carry (wrap second)))) 0)))'''

    def identities(root: Path, text: str):
        path = root / "cp" / "carrier_refs.orc"
        path.parent.mkdir(parents=True)
        path.write_text(text, encoding="utf-8")
        typed = compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
        )
        path.unlink()
        rows = []
        for procedure in typed.procedures.values():
            if getattr(procedure.specialization, "base_name", None) != "cp/carrier_refs::carry":
                continue
            env = typed.procedure_type_env(procedure)
            (seed,) = [
                node
                for node in walk_expr(procedure.typed_body.expr)
                if isinstance(node, LoopStateSeedExpr)
            ]
            field_type = procedure.signature.params[0][1]
            metadata = carrier_metadata_for_expr(
                seed,
                session_state=env.session_state,
                field_types=(("payload", field_type),),
            )
            assert metadata is not None
            rows.append(
                (
                    field_type,
                    metadata,
                    canonical_type_identity(metadata.type_ref, typed=typed),
                )
            )
        assert len(rows) == 6
        return typed, rows

    first_typed, first = identities(tmp_path / "first", source)
    edited_typed, edited = identities(
        tmp_path / "elsewhere" / "deeper",
        "\n\n" + source.replace("(let* ((first", "(let* ((unused 0) (first"),
    )

    def grouped(typed, rows):
        run_refs = _run_ref_signatures(typed)
        groups = {"record": [], "list": [], "phantom": []}
        for field_type, metadata, identity in rows:
            if isinstance(field_type, RecordTypeRef):
                category = "record"
            elif isinstance(field_type, ListTypeRef):
                category = "list"
            elif isinstance(field_type, UnionTypeRef):
                category = "phantom"
                assert field_type.type_args
            else:
                raise AssertionError(type(field_type).__name__)
            projected = run_refs.key_type(metadata.field_types[0][1])
            whole = run_refs.key_type(metadata.type_ref)
            assert whole["fields"][0]["type"] == projected
            groups[category].append((identity, projected, whole))
        return groups

    first_groups = grouped(first_typed, first)
    edited_groups = grouped(edited_typed, edited)
    for category in first_groups:
        first_pair = first_groups[category]
        edited_pair = edited_groups[category]
        assert len(first_pair) == len(edited_pair) == 2
        assert first_pair[0][1] == first_pair[1][1]
        assert edited_pair[0][1] == edited_pair[1][1]
        assert first_pair[0][0].split("[", 1)[0] == first_pair[1][0].split("[", 1)[0]
        assert edited_pair[0][0].split("[", 1)[0] == edited_pair[1][0].split("[", 1)[0]
        assert first_pair[0][0].split("[", 1)[0] == edited_pair[0][0].split("[", 1)[0]
        assert first_pair[0][0] != first_pair[1][0]
        assert edited_pair[0][0] != edited_pair[1][0]
    assert len({first_groups[name][0][0].split("[", 1)[0] for name in first_groups}) == 3
    assert all(
        first_groups[name][0][1] == edited_groups[name][0][1]
        for name in first_groups
    )


def test_run_ref_signatures_use_exact_imported_type_origins(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.closed.names import _run_ref_signatures
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import RunRefExpr

    root = tmp_path / "sources"
    (root / "cp").mkdir(parents=True)
    for module in ("a", "b"):
        (root / "cp" / f"{module}.orc").write_text(
            f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
              (defmodule cp/{module}) (export get)
              (defrecord Box (n Int))
              (defproc get () -> Int :effects ((runs-ref child)) :lowering inline
                (let* ((r (run-ref :source (:repo "file:///workspace" :commit "0123456789abcdef0123456789abcdef01234567")
                           :program (:path "child.orc" :entry child)
                           :inputs (:x (record Box :n 0)) :returns Int
                           :policy (:environment :deterministic-effect-free :setup ()))))
                  r.value)))''',
            encoding="utf-8",
        )
    main = root / "cp" / "main.orc"
    main.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule cp/main) (import cp/a :as a) (import cp/b :as b)
          (export run) (defworkflow run () -> Int (+ (a.get) (b.get))))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        main,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )
    for path in root.rglob("*.orc"):
        path.unlink()

    rows = []
    for procedure in typed.procedures.values():
        for expr in walk_expr(procedure.typed_body.expr):
            if isinstance(expr, RunRefExpr):
                rows.append((typed.procedure_type_env(procedure), expr.run_ref_metadata))
    assert len(rows) == 2
    assert rows[0][1].generated_type_name == rows[1][1].generated_type_name
    assert [env.module_name for env, _ in rows] == ["cp/a", "cp/b"]
    assert [
        canonical_type_identity(metadata.input_types[0][1], typed=typed)
        for _, metadata in rows
    ] == ["cp/a::Box", "cp/b::Box"]

    projection = _run_ref_signatures(typed)
    keys = [projection.key_type(metadata.type_ref) for _, metadata in rows]
    assert keys[0] != keys[1]
    encoded = canonical_json_for_pure_value(keys)
    assert "RunRefResult$000000000000000" not in encoded

    from dataclasses import fields, is_dataclass

    from orchestrator.workflow_lisp.wcc.elaborate import elaborate_typed_workflow_body
    from orchestrator.workflow_lisp.wcc.model import (
        WCC_M4_ROUTE_SCHEMA_VERSION,
        WccPerform,
    )

    procedure_returns = {
        name: procedure.signature.return_type_ref
        for name, procedure in typed.procedures.items()
    }
    workflow_returns = {
        name: workflow.signature.return_type_ref
        for name, workflow in typed.workflows.items()
    }
    for procedure in typed.procedures.values():
        env = typed.procedure_type_env(procedure)
        (source_expr,) = [
            expr
            for expr in walk_expr(procedure.typed_body.expr)
            if isinstance(expr, RunRefExpr)
        ]
        source_token = source_expr.run_ref_metadata.type_ref.run_ref_origin[0]
        body = elaborate_typed_workflow_body(
            procedure.typed_body,
            owner_name=procedure.definition.name,
            type_env=env,
            value_env=dict(procedure.signature.params),
            workflow_return_types=workflow_returns,
            procedure_return_types=procedure_returns,
            resolved_procedures_by_name=typed.procedures,
            procedure_type_envs=typed.procedure_type_envs,
            route_schema_version=WCC_M4_ROUTE_SCHEMA_VERSION,
            closed_program=True,
        )
        performs: list[WccPerform] = []
        seen: set[int] = set()

        def visit(value: object) -> None:
            if id(value) in seen or value is None or isinstance(value, (str, int, float, bool)):
                return
            seen.add(id(value))
            if isinstance(value, WccPerform):
                if value.perform_kind == "run_ref":
                    performs.append(value)
                for field in fields(value):
                    if field.name != "metadata":
                        visit(getattr(value, field.name))
            elif isinstance(value, dict):
                for child in value.values():
                    visit(child)
            elif isinstance(value, (tuple, list)):
                for child in value:
                    visit(child)
            elif is_dataclass(value) and not isinstance(value, type):
                for field in fields(value):
                    if field.name not in {"metadata", "type_ref", "definition"}:
                        visit(getattr(value, field.name))

        visit(body)
        assert len(performs) == 1
        assert performs[0].metadata.type_ref.run_ref_origin[0] == source_token

    from orchestrator.workflow_lisp.build_manifest_io import _json_data

    for _, metadata in rows:
        rendered = repr(metadata.type_ref)
        assert "run_ref_origin" not in rendered
        assert "run_ref_origin" not in _json_data(metadata.type_ref)


def test_specialized_callee_key_retains_all_types_and_procedure_references(
    tmp_path: Path,
) -> None:
    source = (
        Path(__file__).parent
        / "fixtures"
        / "workflow_lisp"
        / "closed_program"
        / "if_in_hook.orc"
    ).read_text(encoding="utf-8")
    root = tmp_path / "cp"
    root.mkdir()
    entry = root / "if_in_hook.orc"
    entry.write_text(source.replace("TARGET", TARGET), encoding="utf-8")
    (tmp_path / "probe.py").write_text(
        "raise RuntimeError('Task10 compile-only command; runtime is not tested')\n",
        encoding="utf-8",
    )
    typed = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={
            "fetch": ExternalToolBinding(
                name="fetch",
                stable_command=("python", "probe.py"),
                closure=("probe.py",),
            )
        },
    )
    (spec,) = (
        procedure
        for procedure in typed.procedures.values()
        if procedure.specialization is not None
        and procedure.specialization.base_name == "std/improve::improve"
    )

    key = canonical_definition_key(
        spec,
        typed=typed,
        binding_facts={},
        capture_parameters=[],
        residual_signature=None,
    )

    assert key[0:3] == ["std/improve", "procedure", "improve"]
    assert [row[0] for row in key[3]] == ["B", "F", "I", "S"]
    assert [row[0] for row in key[4]] == ["review", "revise"]
    assert {row[1]["target"][2] for row in key[4]} == {"review", "revise"}
    assert key[5:8] == [[], [], []]
    assert [row[1]["name"] for row in key[3]] == [
        "cp/if_in_hook::Note",
        "cp/if_in_hook::Note",
        "cp/if_in_hook::Brief",
        "cp/if_in_hook::Candidate",
    ]
    assert key[8]["result"]["name"] == {
        "head": "std/improve::Improvement",
        "args": [
            "cp/if_in_hook::Candidate",
            "cp/if_in_hook::Note",
            "cp/if_in_hook::Note",
        ],
    }
    closed = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(closed.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        closed.tree,
        closed.sites,
        closed.digest,
    )
    (persisted,) = [
        row["key"]
        for row in restored.tree["definitions"].values()
        if row["key"][:3] == ["std/improve", "procedure", "improve"]
    ]
    assert persisted[:9] == key
    decisions = persisted[9]['command_decisions']
    assert {decision[0] for decision in decisions} == {'call'}
    procedure_refs = {name: value for name, value in persisted[4]}
    assert {tuple(decision[1]) for decision in decisions} == {
        tuple(reference['target'][:3]) for reference in procedure_refs.values()}
    from orchestrator.workflow_lisp.closed.sites import _ast_nodes
    (definition,) = [row for row in restored.tree['definitions'].values() if row['key'] == persisted]
    calls = [node for node in _ast_nodes(definition['body']) if node['k'] == 'call']
    assert len(decisions) == len(calls)
    for decision in decisions:
        assert type(decision[2]) is int and decision[2] >= 0
        assert len(decision[3]) == 64 and len(bytes.fromhex(decision[3])) == 32
    review_target = procedure_refs["review"]["target"]
    revise_target = procedure_refs["revise"]["target"]
    assert review_target[2] == "review" and revise_target[2] == "revise"
    assert review_target[8]["result"]["name"] == {
        "head": "std/improve::Decision",
        "args": ["cp/if_in_hook::Note", "cp/if_in_hook::Note"],
    }
    assert [row["name"] for row in revise_target[8]["params"]] == [
        "cp/if_in_hook::Candidate",
        "cp/if_in_hook::Brief",
        "cp/if_in_hook::Note",
    ]
    assert revise_target[8]["result"]["name"] == "cp/if_in_hook::Candidate"
    name = canonical_callee_name(spec, key=key)
    assert name == (
        "procedure:std/improve::improve["
        + sha256(canonical_json_for_pure_value(key).encode("utf-8")).hexdigest()
        + "]"
    )
    assert str(tmp_path) not in json.dumps(key, sort_keys=True)


@pytest.mark.parametrize("value", [3, 4])
def test_bound_procedure_reference_key_uses_merged_target_specialization(
    tmp_path: Path, value: int
) -> None:
    int_type = {"kind": "primitive", "name": "Int"}
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/bound) (export run)
      (defproc helper ((fixed Int) (x Int)) -> Int :effects () :lowering inline (+ fixed x))
      (defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int :effects () :lowering inline (runner x))
      (defworkflow run ((x Int)) -> Int
        (invoke (bind-proc (proc-ref helper) :fixed {value}) x)))'''
    path = tmp_path / "cp" / "bound.orc"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    path.unlink()
    (invoke,) = [
        procedure
        for procedure in typed.procedures.values()
        if procedure.specialization is not None
        and procedure.specialization.base_name == "cp/bound::invoke"
    ]
    facts = {
        "procedure_references": {
            "runner": {
                "bound": {
                    "fixed": {
                        "value": {
                            "k": "lit",
                            "v": value,
                            "type": int_type,
                        }
                    }
                }
            }
        }
    }

    key = canonical_definition_key(
        invoke,
        typed=typed,
        binding_facts=facts,
        capture_parameters=[],
        residual_signature=None,
    )
    procedure_reference = key[4][0][1]
    literal = {"k": "lit", "v": value, "type": int_type}
    assert procedure_reference["target"][6] == [["fixed", int_type, literal]]
    assert procedure_reference["bound"] == [
        ["fixed", int_type, {"value": literal}]
    ]
    assert procedure_reference["residual"] == procedure_reference["target"][8]
    assert procedure_reference["residual"] == {"params": [int_type], "result": int_type}


def _typed_runtime_capture_program(root: Path, *, nested: bool, shifted: bool):
    call = (
        '''(invoke-three
          (bind-proc (proc-ref helper) :fixed x)
          (bind-proc (proc-ref helper) :fixed x)
          (bind-proc (proc-ref apply-one) :callback
            (bind-proc (proc-ref helper) :fixed x)) x)'''
        if nested
        else '(invoke (bind-proc (proc-ref helper) :fixed x) x)'
    )
    if shifted:
        call = f"(let* ((x (+ x 1))) {call})"
    path = root / "cp" / "captures.orc"
    path.parent.mkdir(parents=True)
    path.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule cp/captures) (export run)
          (defproc helper ((fixed Int) (x Int)) -> Int :effects () :lowering inline (+ fixed x))
          (defproc apply-one ((callback ProcRef[Int -> Int]) (x Int)) -> Int :effects () :lowering inline (callback x))
          (defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int :effects () :lowering inline (runner x))
          (defproc invoke-three ((a ProcRef[Int -> Int]) (b ProcRef[Int -> Int])
                                 (runner ProcRef[Int -> Int]) (x Int)) -> Int
            :effects () :lowering inline (runner x))
          (defworkflow run ((x Int)) -> Int {call}))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(root,),
        workspace_root=root,
        command_boundaries={},
    )
    path.unlink()
    base_name = "cp/captures::invoke-three" if nested else "cp/captures::invoke"
    (definition,) = [
        proc
        for proc in typed.procedures.values()
        if getattr(proc.specialization, "base_name", None) == base_name
    ]
    return typed, definition, definition.signature.params[-1][1]


@pytest.mark.parametrize("nested", [False, True])
def test_runtime_procedure_reference_captures_are_scoped_and_value_independent(
    tmp_path: Path, nested: bool
) -> None:
    from orchestrator.workflow_lisp.closed.names import canonical_definition_key

    int_key = {"kind": "primitive", "name": "Int"}

    def build(root: Path, *, shifted: bool):
        typed, definition, int_ref = _typed_runtime_capture_program(
            root, nested=nested, shifted=shifted
        )
        paths = [["a"], ["b"], ["runner", "callback"]] if nested else [["runner"]]
        captures = [
            {
                "type": int_ref,
                "routes": [["reference", path, ["parameter", "fixed"]]],
            }
            for path in paths
        ]
        refs = (
            {
                "a": {"bound": {"fixed": {"capture": 0}}},
                "b": {"bound": {"fixed": {"capture": 1}}},
                "runner": {
                    "bound": {
                        "callback": {"procedure": {"bound": {"fixed": {"capture": 2}}}}
                    }
                },
            }
            if nested
            else {"runner": {"bound": {"fixed": {"capture": 0}}}}
        )
        key = canonical_definition_key(
            definition,
            typed=typed,
            binding_facts={"procedure_references": refs},
            capture_parameters=captures,
            residual_signature=None,
        )
        return key

    original = build(tmp_path / "original", shifted=False)
    renamed_runtime_value = build(tmp_path / "shifted" / "deeper", shifted=True)
    assert original == renamed_runtime_value
    assert original[8] == {"params": [int_key], "result": int_key}
    refs = dict(original[4])
    if nested:
        runner = refs["runner"]
        assert runner["target"][7] == [
            {
                "type": int_key,
                "routes": [["reference", ["callback"], ["parameter", "fixed"]]],
            }
        ]
        nested_target = dict(runner["target"][4])["callback"]
        lifted_binding = runner["bound"][0][2]["procedure"]
        assert nested_target["bound"] == [["fixed", int_key, {"capture": 0}]]
        assert lifted_binding["bound"] == [["fixed", int_key, {"capture": 2}]]
        assert nested_target["target"] == lifted_binding["target"]
        assert refs["a"]["bound"] == [["fixed", int_key, {"capture": 0}]]
        assert refs["b"]["bound"] == [["fixed", int_key, {"capture": 1}]]
    else:
        runner = refs["runner"]
        assert runner["target"][6] == []
        assert runner["target"][7] == [
            {"type": int_key, "routes": [["parameter", "fixed"]]}
        ]
        assert runner["bound"] == [["fixed", int_key, {"capture": 0}]]


def test_public_same_named_procedure_workflow_and_local_callables_keep_kind_owners(
    tmp_path: Path,
) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/local_kinds) (export run)
      (defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int :effects () :lowering inline (runner x))
      (defproc same ((x Int)) -> Int :effects () :lowering inline
        (let-proc (leaf ((y Int)) -> Int :captures ()
          (let* ((state (loop-state (n Int y)))) state.n)) (invoke (proc-ref leaf) x)))
      (defworkflow same ((x Int)) -> Int
        (let-proc (leaf ((y Int)) -> Int :captures ()
          (let* ((state (loop-state (n Int y)))) state.n)) (invoke (proc-ref leaf) x)))
      (defworkflow run ((x Int)) -> Int (let* ((first (same x))) (call same :x first))))'''
    path = tmp_path / "cp" / "local_kinds.orc"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={},
    )
    path.unlink()
    locals_ = [
        procedure
        for procedure in typed.procedures.values()
        if procedure.definition.generated_local_procedure is not None
        and procedure.specialization is None
    ]
    assert len(locals_) == 2
    keys = [
        canonical_definition_key(
            procedure,
            typed=typed,
            binding_facts={},
            capture_parameters=[],
            residual_signature=None,
        )
        for procedure in locals_
    ]
    assert {key[2]["owner"][1] for key in keys} == {"procedure", "workflow"}
    assert all(
        key[2]["owner"][0] == "cp/local_kinds"
        and key[2]["owner"][2] == "same"
        and key[2]["name"] == "leaf"
        and key[2]["ordinal"] == 0
        for key in keys
    )
    names = {
        canonical_callee_name(procedure, key=key)
        for procedure, key in zip(locals_, keys)
    }
    assert len(names) == 2

    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import LoopStateSeedExpr
    from orchestrator.workflow_lisp.loop_state import carrier_metadata_for_expr

    carrier_identities = []
    for procedure in locals_:
        env = typed.procedure_type_env(procedure)
        (seed,) = [
            expr
            for expr in walk_expr(procedure.typed_body.expr)
            if isinstance(expr, LoopStateSeedExpr)
        ]
        metadata = carrier_metadata_for_expr(
            seed,
            session_state=env.session_state,
        )
        assert metadata is not None
        carrier_identities.append(
            canonical_type_identity(metadata.type_ref, typed=typed)
        )
        family_owner = metadata.family[0]
        assert family_owner[0] == "cp/local_kinds"
        assert family_owner[1] == "procedure"
    assert len(set(carrier_identities)) == 2


def test_variant_case_descriptor_names_its_applied_union(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.closed.names import canonical_type_descriptor

    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/variant_owner) (export run)
      (defunion Box :forall (T) (SOME (value T)) (NONE))
      (defworkflow run ((box Box[Int])) -> Int
        (match box ((SOME item) item.value) ((NONE item) 0))))'''
    path = tmp_path / "cp" / "variant_owner.orc"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    union_ref = dict(typed.entry.signature.params)["box"]
    payload_ref = typed.type_env.union_variant(
        union_ref,
        "SOME",
        span=union_ref.definition.span,
        form_path=(),
    )
    path.unlink()

    union_descriptor = canonical_type_descriptor(union_ref, typed=typed)
    payload_descriptor = canonical_type_descriptor(payload_ref, typed=typed)
    assert union_descriptor["name"] == "cp/variant_owner::Box[Int]"
    assert payload_descriptor["union_name"] == union_descriptor["name"]
    assert canonical_type_identity(payload_ref, typed=typed) == (
        "cp/variant_owner::Box[Int].variant"
    )


def test_private_discriminants_keep_their_exact_union_owner(tmp_path: Path) -> None:
    from orchestrator.workflow_lisp.typecheck_proofs import resolve_field_access

    for module in ("a", "b"):
        path = tmp_path / f"{module}.orc"
        path.write_text(
            f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
              (defmodule {module}) (export Outer)
              (defunion Choice (YES) (NO))
              (defrecord Outer (choice Choice)))''',
            encoding="utf-8",
        )
    path = tmp_path / "entry.orc"
    path.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule entry) (import a :as left) (import b :as right) (export run)
          (defworkflow run ((first left.Outer) (second right.Outer)) -> Int 1))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    identities = []
    for formal, outer_type in typed.entry.signature.params:
        union_type = outer_type.field_types["choice"]
        discriminant = resolve_field_access(
            union_type,
            base_name=formal,
            binding_identity=None,
            field_name="variant",
            span=union_type.definition.span,
            form_path=(),
            type_env=typed.type_env,
            proof_scope=None,
        )
        identities.append(canonical_type_identity(discriminant, typed=typed))
    for source_path in tmp_path.glob("*.orc"):
        source_path.unlink()
    assert identities == ["a::Choice.variant", "b::Choice.variant"]


@pytest.mark.parametrize("producer_mode", ("named", "standalone"))
def test_legacy_snapshot_keeps_carrier_family_for_later_closed_import(
    tmp_path: Path,
    producer_mode: str,
) -> None:
    from orchestrator.workflow_lisp.compiler import (
        compile_stage3_entrypoint,
        compile_stage3_module,
    )
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import LoopStateSeedExpr
    from orchestrator.workflow_lisp.loop_state import carrier_metadata_for_expr
    from orchestrator.workflow_lisp.build_manifest_io import _json_data

    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    module_header = "(defmodule cp/producer)" if producer_mode == "named" else ""
    export_header = "(export get)" if producer_mode == "named" else ""
    producer_path.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          {module_header} {export_header}
          (defproc carry ((value Int)) -> Int :effects () :lowering inline
            (let* ((state (loop-state (n Int value)))) state.n))
          (defworkflow get ((n Int)) -> Int (carry n)))''',
        encoding="utf-8",
    )
    if producer_mode == "named":
        producer_result = compile_stage3_entrypoint(
            producer_path,
            source_roots=(tmp_path,),
            command_boundaries={},
            validate_shared=True,
            workspace_root=tmp_path,
        )
        producer_bundle = producer_result.validated_bundles_by_name[
            "cp/producer::get"
        ]
    else:
        producer_result = compile_stage3_module(
            producer_path,
            validate_shared=True,
            workspace_root=tmp_path,
        )
        producer_bundle = producer_result.validated_bundles["get"]
    producer_snapshot = producer_bundle.typed_program
    carrier_rows = []
    for procedure in producer_snapshot.procedures.values():
        if getattr(procedure.specialization, "base_name", None) not in {
            "cp/producer::carry",
            None,
        }:
            continue
        env = producer_snapshot.procedure_type_env(procedure)
        for seed in (
            node
            for node in walk_expr(procedure.typed_body.expr)
            if isinstance(node, LoopStateSeedExpr)
        ):
            metadata = carrier_metadata_for_expr(
                seed,
                session_state=env.session_state,
                field_types=(("n", dict(procedure.signature.params)["value"]),),
            )
            if metadata is not None:
                carrier_rows.append(metadata)
    assert carrier_rows
    assert all(metadata.family is not None for metadata in carrier_rows)
    legacy_name = carrier_rows[0].generated_type_name
    assert "carrier$" not in legacy_name
    assert "family=" not in repr(carrier_rows[0])
    assert "family" not in _json_data(carrier_rows[0])

    producer_path.unlink()
    identities = {
        canonical_type_identity(metadata.type_ref, typed=producer_snapshot)
        for metadata in carrier_rows
    }
    assert identities

    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule cp/consumer) (export run)
          (defworkflow run ((n Int)) -> Int (call dep :n n)))''',
        encoding="utf-8",
    )
    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"dep": producer_snapshot},
    )
    assert consumer.imported_programs["dep"] is producer_snapshot
    assert not producer_path.exists()
    imported_envs = tuple(consumer.module_type_envs.values())
    imported_identities = {
        canonical_type_identity(metadata.type_ref, typed=consumer)
        for metadata in carrier_rows
        if any(
            env.session_state.loop_carrier_metadata_by_name.get(
                metadata.generated_type_name
            )
            is not None
            for env in imported_envs
        )
    }
    assert imported_identities == identities


def test_list_map_effect_seed_gets_its_expanded_declaration_family(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow_lisp.expression_traversal import walk_expr
    from orchestrator.workflow_lisp.expressions import LoopStateSeedExpr
    from orchestrator.workflow_lisp.loop_state import carrier_metadata_for_expr

    path = tmp_path / "cp" / "map_carrier.orc"
    path.parent.mkdir(parents=True)
    path.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule cp/map_carrier) (export run)
          (defworkflow child ((value Int)) -> Int
            (command-result tick :argv ("python" "tick.py" value) :returns Int))
          (defworkflow run ((values List[Int])) -> List[Int]
            (list/map-effect ((item values)) :max 3 (call child :value item))))''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={
            "tick": ExternalToolBinding(
                name="tick",
                stable_command=("python", "tick.py"),
            )
        },
    )
    path.unlink()
    env = typed.workflow_type_env(typed.entry.definition.name)
    (seed,) = [
        node
        for node in walk_expr(typed.entry.typed_body.expr)
        if isinstance(node, LoopStateSeedExpr)
    ]
    metadata = carrier_metadata_for_expr(seed, session_state=env.session_state)
    assert metadata is not None
    assert metadata.source_kind == "seed"
    assert metadata.family == (["cp/map_carrier", "workflow", "run"], 0)
    assert canonical_type_identity(metadata.type_ref, typed=typed).startswith(
        "workflow_lisp/private::loop-state-carrier$"
    )


def test_sibling_local_names_use_owner_ordinals_and_ignore_relocation_edits(
    tmp_path: Path,
) -> None:
    base = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/local_scopes) (export run)
      (defproc invoke ((runner ProcRef[Int -> Int]) (x Int)) -> Int :effects () :lowering inline (runner x))
      (defworkflow run ((x Int)) -> Int
        BODY))'''

    def keys_at(root: Path, body: str):
        path = root / "cp" / "local_scopes.orc"
        path.parent.mkdir(parents=True)
        path.write_text(base.replace("BODY", body), encoding="utf-8")
        typed = compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(root,),
            workspace_root=root,
            command_boundaries={},
        )
        path.unlink()
        locals_ = [
            procedure
            for procedure in typed.procedures.values()
            if procedure.definition.generated_local_procedure is not None
            and procedure.specialization is None
        ]
        keys = [
            canonical_definition_key(
                procedure,
                typed=typed,
                binding_facts={},
                capture_parameters=[],
                residual_signature=None,
            )
            for procedure in locals_
        ]
        return sorted(keys, key=lambda key: key[2]["ordinal"])

    first = keys_at(
        tmp_path / "first",
        """(let* ((a (let-proc (leaf ((y Int)) -> Int :captures () (+ y 1))
                         (invoke (proc-ref leaf) x)))
                      (b (let-proc (leaf ((y Int)) -> Int :captures () (+ y 2))
                         (invoke (proc-ref leaf) x)))) (+ a b))""",
    )
    relocated = keys_at(
        tmp_path / "elsewhere" / "deeper",
        """(let* ((padding 1)
                      (left (let-proc (leaf ((z Int)) -> Int :captures () (+ z 1))
                         (invoke (proc-ref leaf) x)))
                      (right (let-proc (leaf ((z Int)) -> Int :captures () (+ z 2))
                         (invoke (proc-ref leaf) x)))) (+ left right))""",
    )
    assert [key[2]["ordinal"] for key in first] == [0, 1]
    assert [key[2]["ordinal"] for key in relocated] == [0, 1]
    assert first == relocated


def test_public_local_procedure_reference_uses_original_capture_selector(
    tmp_path: Path,
) -> None:
    source = (
        Path(__file__).parent
        / "fixtures"
        / "workflow_lisp"
        / "closed_program"
        / "local_proc_specializations.orc"
    ).read_text(encoding="utf-8").replace("TARGET", TARGET)
    path = tmp_path / "cp" / "local_proc_specializations.orc"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={},
    )
    path.unlink()
    definitions = [
        procedure
        for procedure in typed.procedures.values()
        if procedure.specialization is not None
        and procedure.specialization.base_name == "cp/local_proc_specializations::apply-int"
    ]
    assert len(definitions) == 2
    facts = {
        "procedure_references": {
            "hook": {"bound": {"v": {"value": {"k": "lit", "v": 7, "type": {"kind": "primitive", "name": "Int"}}}}}
        }
    }
    keys = [
        canonical_definition_key(
            definition,
            typed=typed,
            binding_facts=facts,
            capture_parameters=[],
            residual_signature=None,
        )
        for definition in definitions
    ]
    assert {key[4][0][1]["target"][2]["ordinal"] for key in keys} == {0, 1}
    assert all(
        key[4][0][1]["bound"]
        == [[ ["local", 0], {"kind": "primitive", "name": "Int"}, {"value": {"k": "lit", "v": 7, "type": {"kind": "primitive", "name": "Int"}}} ]]
        for key in keys
    )


def test_workflow_reference_keys_use_exact_resolved_extern_rows(tmp_path: Path) -> None:
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
      (defmodule cp/wrefs) (export run)
      (defrecord Box (n Int))
      (defworkflow helper ((input Box)) -> Box
        (provider-result providers.execute :prompt prompts.execute :inputs (input.n) :returns Box))
      (defproc invoke ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box
        :effects ((calls-workflow runner)) :lowering inline (call runner :input input))
      (defworkflow run ((input Box)) -> Box (invoke (workflow-ref helper) input)))'''
    path = tmp_path / "cp" / "wrefs.orc"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")
    typed = compile_typed_program(
        path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={},
        provider_externs={"providers.execute": "provider-a"},
        prompt_externs={
            "prompts.execute": {"asset_file": "prompts/execute.md"}
        },
    )
    path.unlink()
    (definition,) = [
        procedure
        for procedure in typed.procedures.values()
        if getattr(procedure.specialization, "base_name", None) == "cp/wrefs::invoke"
    ]
    asset_rows = {
        "providers": [["providers.execute", {"provider_id": "provider-a"}]],
        "prompts": [[
            "prompts.execute",
            {"source_kind": "asset_file", "path": "prompts/execute.md", "asset_base": "cp"},
        ]],
    }

    def key(externs):
        return canonical_definition_key(
            definition,
            typed=typed,
            binding_facts={
                "workflow_references": {"runner": {"externs": externs}}
            },
            capture_parameters=[],
            residual_signature=None,
        )

    original = key(asset_rows)
    wref = dict(original[5])["runner"]
    assert wref["externs"] == asset_rows
    changed_provider = {
        **asset_rows,
        "providers": [["providers.execute", {"provider_id": "provider-b"}]],
    }
    changed_prompt = {
        **asset_rows,
        "prompts": [[
            "prompts.execute",
            {"source_kind": "input_file", "path": "prompts/execute.md"},
        ]],
    }
    assert key(changed_provider) != original
    assert key(changed_prompt) != original
    for malformed in (
        {**asset_rows, "providers": [["providers.execute", {"provider_id": " "}]]},
        {**asset_rows, "providers": [["providers.wrong", {"provider_id": "provider-a"}]]},
        {**asset_rows, "prompts": [["prompts.execute", {"source_kind": "asset_file", "path": "p"}]]},
        {**asset_rows, "unexpected": []},
    ):
        with pytest.raises(ValueError):
            key(malformed)
