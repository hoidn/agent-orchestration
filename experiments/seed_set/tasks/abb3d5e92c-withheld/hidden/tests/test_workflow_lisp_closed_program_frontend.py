from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import fields, replace
from pathlib import Path

import pytest

from orchestrator.workflow_lisp import syntax
from orchestrator.workflow_lisp import compiler as compiler_module
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle,
    load_imported_workflow_bundle_manifest,
)
from orchestrator.workflow_lisp.build_manifest_io import ConfigurationReadTrace
from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint, compile_stage3_module
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow_lisp.command_boundaries import CertifiedAdapterBinding
from orchestrator.workflow_lisp.workflows import ExternalToolBinding, PromptExtern
from orchestrator.workflow.loaded_bundle import workflow_boundary_projection
from orchestrator.workflow_lisp.closed.frontend import TypedProgram, compile_typed_program
from orchestrator.workflow_lisp.closed.build import build_closed_program
from orchestrator.workflow_lisp.closed.artifact import _load_closed_imports
from orchestrator.workflow_lisp.closed.program import (
    ClosedProgram,
    ClosedProgramInvalid,
    _sites_from_nodes,
)
from orchestrator.workflow_lisp.closed.sites import _ast_nodes
from orchestrator.workflow_lisp.expression_traversal import walk_expr
from orchestrator.workflow_lisp.expressions import EnumMemberExpr, GeneratedRelpathSeedExpr
from orchestrator.workflow_lisp.type_env import PathTypeRef, PrimitiveTypeRef
from orchestrator.workflow.run_ref import bundle_transport
from orchestrator.workflow.surface_ast import SurfaceContract


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "closed_program"
TARGET = syntax.EVALUATED_EXECUTION_MIN_TARGET_DSL_VERSION
BOUNDARIES = {
    "fetch": ExternalToolBinding(name="fetch", stable_command=("python", "probe.py"))
}


def _fixture(name: str, *, target: str = TARGET) -> str:
    return (FIXTURES / f"{name}.orc").read_text(encoding="utf-8").replace("TARGET", target)


def _install(tmp_path: Path, name: str, *, target: str = TARGET) -> Path:
    path = tmp_path / "cp" / f"{name}.orc"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_fixture(name, target=target), encoding="utf-8")
    return path


def _error(path: Path, operation) -> tuple[str, Path, int, int]:
    with pytest.raises(LispFrontendCompileError) as excinfo:
        operation()
    diagnostic = excinfo.value.diagnostics[0]
    return (
        diagnostic.code,
        Path(diagnostic.span.start.path),
        diagnostic.span.start.line,
        diagnostic.span.start.column,
    )


def test_source_free_imports_keep_typed_and_restored_producer_scopes(
    tmp_path: Path,
) -> None:
    """Typed and capsule-restored producers retain their own bodies/configs."""
    identity = "sha256:" + "c" * 64

    def install(root: Path, module: str, text: str) -> Path:
        path = root / f"{module}.orc"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def compile_source(path: Path, **configuration) -> TypedProgram:
        return compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(path.parent,),
            workspace_root=path.parent,
            command_boundaries={},
            **configuration,
        )

    def decoded_snapshot(bundle, source: Path):
        encoded = bundle_transport.encode_bundle_capsule(
            {bundle.surface.name: bundle},
            target_workflow_names=(bundle.surface.name,),
            closure=(
                bundle_transport.BundleCapsuleClosureBlob(
                    path=source.name,
                    roles=("orc",),
                    payload=source.read_bytes(),
                ),
            ),
            workflow_closure_paths={bundle.surface.name: source.name},
            compiler_runtime_identity_digest=identity,
            lowering_schema_version=2,
        )
        decoded = bundle_transport.decode_bundle_capsule(
            manifest_bytes=encoded.manifest_bytes,
            pickle_bytes=encoded.pickle_bytes,
            closure=encoded.closure,
            expected_capsule_digest=encoded.capsule_digest,
            expected_compiler_runtime_identity_digest=identity,
        ).bundles_by_name[bundle.surface.name]
        assert decoded.typed_program is None
        return decoded

    def definition(tree, module: str, kind: str, name: str):
        matches = [
            (key, row)
            for key, row in tree["definitions"].items()
            if row["key"][:3] == [module, kind, name]
        ]
        assert len(matches) == 1
        return matches[0]

    for target in ("2.35", "2.34"):
        root = tmp_path / target
        root.mkdir()
        native_by_module = {}
        imports = {}
        producer_paths = []
        for module in ("alpha", "beta"):
            producer = install(
                root,
                module,
                f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
                  (defmodule {module}) (export run)
                  (defworkflow run ((n Int)) -> Int
                    (provider-result provider :prompt prompt :inputs (n) :returns Int)))''',
            )
            producer_paths.append(producer)
            producer_config = {
                "provider_externs": {"provider": f"{module}-provider"},
                "prompt_externs": {"prompt": {"input_file": f"{module}.txt"}},
            }
            if target == "2.35":
                native = compile_source(producer, **producer_config)
                imports[module] = native
            else:
                flat = compile_stage3_entrypoint(
                    producer,
                    source_roots=(root,),
                    workspace_root=root,
                    command_boundaries={},
                    **producer_config,
                )
                bundle = flat.validated_bundles_by_name[f"{module}::run"]
                native = bundle.typed_program
                assert native is not None
                decoded = decoded_snapshot(bundle, producer)
                imports[module] = replace(decoded, typed_program=native)
            native_by_module[module] = native

        consumer = install(
            root,
            "consumer",
            '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
              (defmodule consumer) (export run)
              (defworkflow run ((n Int)) -> Int
                (let* ((first (call alpha :n n))
                       (second (call beta :n first)))
                  (provider-result provider :prompt prompt :inputs (second) :returns Int))))''',
        )
        consumer_config = {
            "provider_externs": {"provider": "consumer-provider"},
            "prompt_externs": {"prompt": {"input_file": "consumer.txt"}},
        }
        if target == "2.34":
            flat_beta = compile_stage3_entrypoint(
                producer_paths[-1],
                source_roots=(root,),
                workspace_root=root,
                command_boundaries={},
                provider_externs={"provider": "beta-provider"},
                prompt_externs={"prompt": {"input_file": "beta.txt"}},
            )
            missing_snapshot = decoded_snapshot(
                flat_beta.validated_bundles_by_name["beta::run"], producer_paths[-1]
            )
            with pytest.raises(LispFrontendCompileError) as excinfo:
                compile_source(
                    consumer,
                    imported_workflow_bundles={**imports, "beta": missing_snapshot},
                    **consumer_config,
                )
            assert excinfo.value.diagnostics[0].code == "compiled_workflow_source_required"

        typed = compile_source(
            consumer,
            **(
                {"imported_programs": imports}
                if target == "2.35"
                else {"imported_workflow_bundles": imports}
            ),
            **consumer_config,
        )
        assert all(
            typed.imported_programs[module] is native
            for module, native in native_by_module.items()
        )
        signatures = {
            module: tuple(native.entry.signature.params)
            for module, native in native_by_module.items()
        }
        for path in (*producer_paths, consumer):
            path.unlink()

        built = build_closed_program(typed)
        restored = ClosedProgram.from_artifact(built.artifact())
        assert (restored.tree, restored.sites, restored.digest) == (
            built.tree,
            built.sites,
            built.digest,
        )
        calls = [node for node in _ast_nodes(restored.tree["body"]) if node["k"] == "call"]
        assert len(calls) == 2
        for module, call in zip(("alpha", "beta"), calls, strict=True):
            owner, body = definition(restored.tree, module, "workflow", "run")
            assert call["callee"] == owner
            (effect,) = [
                node for node in _ast_nodes(body["body"]) if node["k"] == "perform"
            ]
            assert effect["provider"] == f"{module}-provider"
            assert effect["prompt"]["path"] == f"{module}.txt"

        (own_effect,) = [
            node for node in _ast_nodes(restored.tree["body"])
            if node["k"] == "perform"
        ]
        assert own_effect["provider"] == "consumer-provider"
        assert own_effect["prompt"]["path"] == "consumer.txt"
        assert restored.tree["configuration"]["providers"]["provider"] == {
            "provider_id": "consumer-provider"
        }
        import_scopes = tuple(restored.tree["configuration"]["imports"].values())
        assert {
            (scope["providers"]["provider"]["provider_id"],
             scope["prompts"]["prompt"]["path"])
            for scope in import_scopes
        } == {
            ("alpha-provider", "alpha.txt"),
            ("beta-provider", "beta.txt"),
        }
        assert signatures == {
            module: tuple(native.entry.signature.params)
            for module, native in native_by_module.items()
        }


def test_mixed_schema_capsule_pairs_each_original_snapshot_after_relocation(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "cp" / "child.orc"
    child_path.parent.mkdir()
    child_path.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule cp/child) (export run)
          (defworkflow run ((n Int)) -> Int
            (provider-result provider :prompt prompt :inputs (n) :returns Int)))''',
        encoding="utf-8",
    )
    child_providers = tmp_path / "child-providers.json"
    child_providers.write_text('{"provider":"child-provider"}', encoding="utf-8")
    child_prompts = tmp_path / "child-prompts.json"
    child_prompts.write_text(
        '{"prompt":{"input_file":"child.txt"}}', encoding="utf-8"
    )
    child_build = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=child_path,
            source_roots=(tmp_path,),
            provider_externs_path=child_providers,
            prompt_externs_path=child_prompts,
            workspace_root=tmp_path,
            lowering_route="legacy",
        )
    )
    child_bundle = child_build.validated_bundle
    child_snapshot = child_bundle.typed_program
    assert child_snapshot.producer_lowering_schema == 1
    assert child_build.manifest.lowering_schema_version == 1

    parent_path = tmp_path / "cp" / "parent.orc"
    parent_path.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule cp/parent) (export run)
          (defworkflow run ((n Int)) -> Int
            (let* ((child-result (call dep :n n)))
              (provider-result provider :prompt prompt
                :inputs (child-result) :returns Int))))''',
        encoding="utf-8",
    )
    parent_result = compile_stage3_entrypoint(
        parent_path,
        source_roots=(tmp_path,),
        provider_externs={"provider": "parent-provider"},
        prompt_externs={"prompt": {"input_file": "parent.txt"}},
        imported_workflow_bundles={"dep": child_bundle},
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="wcc_m4",
    )
    parent_bundle = parent_result.validated_bundles_by_name["cp/parent::run"]
    parent_snapshot = parent_bundle.typed_program
    assert parent_snapshot.producer_lowering_schema == 2
    assert parent_snapshot.imported_programs["dep"] is child_snapshot
    assert child_bundle.provenance.frontend_build_root == child_build.build_root

    identity = "sha256:" + "c" * 64
    bundles = {
        child_bundle.surface.name: child_bundle,
        parent_bundle.surface.name: parent_bundle,
    }
    encoded = bundle_transport.encode_bundle_capsule(
        bundles,
        target_workflow_names=(parent_bundle.surface.name,),
        closure=(
            bundle_transport.BundleCapsuleClosureBlob(
                path=child_path.relative_to(tmp_path).as_posix(),
                roles=("orc",),
                payload=child_path.read_bytes(),
            ),
            bundle_transport.BundleCapsuleClosureBlob(
                path=parent_path.relative_to(tmp_path).as_posix(),
                roles=("orc",),
                payload=parent_path.read_bytes(),
            ),
        ),
        workflow_closure_paths={
            child_bundle.surface.name: child_path.relative_to(tmp_path).as_posix(),
            parent_bundle.surface.name: parent_path.relative_to(tmp_path).as_posix(),
        },
        compiler_runtime_identity_digest=identity,
        lowering_schema_version=2,
    )

    moved = tmp_path / "relocated-capsule"
    moved.mkdir()
    manifest_bytes = moved / "manifest.json"
    pickle_bytes = moved / "catalog.pickle"
    manifest_bytes.write_bytes(encoded.manifest_bytes)
    pickle_bytes.write_bytes(encoded.pickle_bytes)
    moved_closure = []
    for blob in encoded.closure:
        moved_blob = moved / blob.path
        moved_blob.parent.mkdir(parents=True, exist_ok=True)
        moved_blob.write_bytes(blob.payload)
        moved_closure.append(
            replace(blob, payload=moved_blob.read_bytes())
        )

    shutil.rmtree(child_build.build_root)
    child_path.unlink()
    parent_path.unlink()
    assert not child_build.build_root.exists()
    decoded = bundle_transport.decode_bundle_capsule(
        manifest_bytes=manifest_bytes.read_bytes(),
        pickle_bytes=pickle_bytes.read_bytes(),
        closure=tuple(moved_closure),
        expected_capsule_digest=encoded.capsule_digest,
        expected_compiler_runtime_identity_digest=identity,
    )
    assert decoded.bundles_by_name[child_bundle.surface.name].typed_program is None
    assert decoded.bundles_by_name[parent_bundle.surface.name].typed_program is None
    restored_child = replace(
        decoded.bundles_by_name[child_bundle.surface.name],
        typed_program=child_snapshot,
    )
    restored_parent = replace(
        decoded.bundles_by_name[parent_bundle.surface.name],
        typed_program=parent_snapshot,
    )

    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "{TARGET}")
          (defmodule cp/consumer) (export run)
          (defworkflow run ((n Int)) -> Int (call parent :n n)))''',
        encoding="utf-8",
    )
    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_workflow_bundles={
            "parent": restored_parent,
            "child": restored_child,
        },
    )
    assert consumer.imported_programs["parent"].producer_lowering_schema == 2
    assert consumer.imported_programs["parent"].imported_programs[
        "dep"
    ].producer_lowering_schema == 1
    assert consumer.imported_programs["child"] is child_snapshot
    consumer_path.unlink()
    assert not consumer_path.exists()

    built = build_closed_program(consumer)
    restored = ClosedProgram.from_artifact(built.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        built.tree,
        built.sites,
        built.digest,
    )

    def owner_definition(module: str) -> Mapping[str, object]:
        matches = [
            row
            for row in restored.tree["definitions"].values()
            if row["key"][:3] == [module, "workflow", "run"]
        ]
        assert len(matches) == 1
        return matches[0]

    for module, provider, prompt in (
        ("cp/child", "child-provider", "child.txt"),
        ("cp/parent", "parent-provider", "parent.txt"),
    ):
        (effect,) = [
            node
            for node in _ast_nodes(owner_definition(module)["body"])
            if node["k"] == "perform"
        ]
        assert effect["provider"] == provider
        assert effect["prompt"]["path"] == prompt


def test_a_program_the_flat_route_refuses_typechecks_into_a_typed_program(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch")

    typed = compile_typed_program(
        entry,
        entry_workflow="cp/loop_in_branch::run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
    )

    assert isinstance(typed, TypedProgram)
    assert (typed.entry.definition.name, typed.target, sorted(typed.procedures)) == (
        "cp/loop_in_branch::run",
        TARGET,
        ["cp/loop_in_branch::fetch"],
    )


def test_evaluated_graph_result_has_no_lowered_workflows(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch")

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )

    assert (result.entry_result.lowered_workflows, result.entry_result.typed_program is not None) == (
        (),
        True,
    )


def test_typed_program_retains_procedure_specializations_and_owner_environments(
    tmp_path: Path,
) -> None:
    entry = _install(tmp_path, "if_in_hook")

    typed = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
    )

    specializations = tuple(
        procedure
        for procedure in typed.procedures.values()
        if procedure.specialization is not None
    )
    assert len(specializations) == 1
    owner_module = specializations[0].specialization.base_name.split("::", 1)[0]
    assert owner_module in typed.module_type_envs
    assert (
        typed.procedure_type_env(specializations[0]).target_dsl_version
        == typed.module_type_envs[owner_module].target_dsl_version
    )


def test_evaluated_entry_skips_flat_lowering_for_its_whole_source_graph(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_helper = _install(tmp_path, "loop_in_branch", target="2.34")
    old_source = old_helper.read_text(encoding="utf-8").replace("(export run)", "(export Box run)")
    old_helper.write_text(old_source, encoding="utf-8")
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/loop_in_branch :as old :only (Box run))
  (export start)
  (defworkflow start ((go Bool)) -> Box
    (call old.run :go go)))
''',
        encoding="utf-8",
    )

    def refuse_lowering(**_kwargs):
        raise AssertionError("evaluated-entry graph reached flat lowering")

    monkeypatch.setattr("orchestrator.workflow_lisp.compiler._lower_workflows_for_route", refuse_lowering)
    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=None,
    )

    assert all(not item.lowered_workflows and not item.validated_bundles for item in result.compiled_results_by_name.values())
    helper = result.compiled_results_by_name["cp/loop_in_branch"]
    assert helper.typed_workflows[0].definition.name == "cp/loop_in_branch::run"
    assert helper.typed_workflows[0].typed_body is not None
    assert helper.typed_workflows[0].effect_summary
    assert "cp/loop_in_branch::fetch" in helper.procedure_catalog.signatures_by_name
    typed = result.entry_result.typed_program
    private_callee = typed.procedures["cp/loop_in_branch::fetch"]
    assert typed.procedure_type_env(private_callee).target_dsl_version == (
        typed.module_type_envs["cp/loop_in_branch"].target_dsl_version
    )


def test_typed_program_keeps_each_module_externs_and_unused_bindings(
    tmp_path: Path,
) -> None:
    old_helper = _install(tmp_path, "loop_in_branch", target="2.34")
    old_source = old_helper.read_text(encoding="utf-8").replace(
        "(export run)", "(export Box run)"
    )
    old_helper.write_text(old_source, encoding="utf-8")
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/loop_in_branch :as old :only (Box run))
  (export start)
  (defworkflow start ((go Bool)) -> Box (call old.run :go go)))
''',
        encoding="utf-8",
    )
    unused_boundary = ExternalToolBinding(
        name="unused",
        stable_command=("python", "unused.py"),
    )

    typed = compile_typed_program(
        entry,
        entry_workflow="start",
        source_roots=(tmp_path,),
        command_boundaries={**BOUNDARIES, "unused": unused_boundary},
        provider_externs={
            "providers.review": "review-provider",
            "providers.unused": "unused-provider",
        },
    )

    helper_externs = typed.module_externs["cp/loop_in_branch"]
    entry_externs = typed.module_externs["cp/entry"]
    assert helper_externs is not entry_externs
    assert helper_externs["providers.review"].provider_id == "review-provider"
    assert entry_externs["providers.review"].provider_id == "review-provider"
    assert typed.externs["providers.unused"].provider_id == "unused-provider"
    assert typed.configuration_bindings["provider_externs"]["providers.unused"] == (
        "unused-provider"
    )
    assert typed.configuration_bindings["command_boundaries"]["unused"] == unused_boundary
    assert "unused" in typed.command_boundaries


def test_old_entry_keeps_its_flat_route_refusal(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch", target="2.34")

    code, path, line, column = _error(
        entry,
        lambda: compile_stage3_entrypoint(
            entry,
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
            validate_shared=True,
            workspace_root=tmp_path,
            lowering_route=None,
        ),
    )

    assert (code, path, line, column) == (
        "workflow_signature_mismatch",
        entry,
        17,
        28,
    )


def test_old_entry_cannot_import_an_evaluated_module(tmp_path: Path) -> None:
    entry = tmp_path / "cp" / "old_entry.orc"
    callee = tmp_path / "cp" / "new_callee.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/old_entry)
  (import cp/new_callee :only (run))
  (export start)
  (defworkflow start () -> Int (call run)))
''',
        encoding="utf-8",
    )
    callee.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/new_callee)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, line, _column = _error(
        entry,
        lambda: compile_stage3_entrypoint(entry, source_roots=(tmp_path,), validate_shared=True),
    )

    assert (code, path, line) == ("evaluated_execution_target_direction_invalid", entry, 5)


def test_old_helper_cannot_call_back_into_the_evaluated_graph(tmp_path: Path) -> None:
    entry = tmp_path / "cp" / "entry.orc"
    helper = tmp_path / "cp" / "helper.orc"
    callee = tmp_path / "cp" / "callee.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/helper :only (relay))
  (export start)
  (defworkflow start () -> Int (call relay)))
''',
        encoding="utf-8",
    )
    helper.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/helper)
  (import cp/callee :only (run))
  (export relay)
  (defworkflow relay () -> Int (call run)))
''',
        encoding="utf-8",
    )
    callee.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/callee)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, line, _column = _error(
        entry,
        lambda: compile_stage3_entrypoint(entry, source_roots=(tmp_path,), validate_shared=True),
    )

    assert (code, path, line) == ("evaluated_execution_target_direction_invalid", helper, 5)


def test_explicit_new_snapshot_is_refused_only_when_an_old_procedure_calls_it(
    tmp_path: Path,
) -> None:
    producer = tmp_path / "producer.orc"
    producer.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer)
  (export get)
  (defrecord Box (n Int))
  (defworkflow get ((input Box)) -> Box input))
''',
        encoding="utf-8",
    )
    typed_producer = compile_typed_program(
        producer,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    helper = tmp_path / "old.orc"
    helper.write_text(
        '''
(workflow-lisp (:language "0.1") (:target-dsl "2.34") (defmodule old)
  (export Box invoke) (defrecord Box (n Int))
  (defproc invoke ((runner WorkflowRef[Box -> Box]) (input Box)) -> Box
    :effects ((calls-workflow runner)) :lowering inline (call runner :input input)))
''',
        encoding="utf-8",
    )
    main = tmp_path / "main.orc"
    main.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule main)
  (import old :only (Box invoke))
  (export run)
  (defworkflow run ((input Box)) -> Box input))
''',
        encoding="utf-8",
    )

    unused_alias = compile_typed_program(
        main,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"dep": typed_producer},
    )
    assert unused_alias.entry.definition.name == "main::run"

    main.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule main)
  (import old :only (Box invoke))
  (export run)
  (defworkflow run ((input Box)) -> Box
    (invoke (workflow-ref dep) input)))
''',
        encoding="utf-8",
    )
    code, path, line, _column = _error(
        main,
        lambda: compile_typed_program(
            main,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": typed_producer},
        ),
    )

    assert (code, path, line) == (
        "evaluated_execution_target_direction_invalid",
        helper,
        5,
    )


def test_typechecker_diagnostic_is_unchanged_at_the_new_target(tmp_path: Path) -> None:
    entry = tmp_path / "cp" / "bad.orc"
    entry.parent.mkdir(parents=True)

    def compile_at(target: str):
        entry.write_text(
            f'''(workflow-lisp
      (:language "0.1")
      (:target-dsl "{target}")
      (defmodule cp/bad)
      (export run)
      (defrecord Broken (value Missing))
      (defworkflow run ((input Broken)) -> Broken input))
''',
            encoding="utf-8",
        )
        return _error(
            entry,
            lambda: compile_stage3_entrypoint(entry, source_roots=(tmp_path,), validate_shared=True),
        )

    old = compile_at("2.34")
    new = compile_at(TARGET)

    assert old[0] == new[0] == "type_unknown"
    assert (old[2], old[3]) == (new[2], new[3])


def test_typed_entry_refuses_a_pre_evaluated_target_at_its_header(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch", target="2.34")

    code, path, line, _column = _error(
        entry,
        lambda: compile_typed_program(
            entry,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
        ),
    )

    assert (code, path, line) == ("evaluated_execution_target_required", entry, 3)


def test_typed_entry_accepts_short_and_canonical_names_and_a_fixed_standalone_namespace(
    tmp_path: Path,
) -> None:
    entry = _install(tmp_path / "moduled", "loop_in_branch")
    short = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(tmp_path / "moduled",),
        command_boundaries=BOUNDARIES,
    )
    canonical = compile_typed_program(
        entry,
        entry_workflow="cp/loop_in_branch::run",
        source_roots=(tmp_path / "moduled",),
        command_boundaries=BOUNDARIES,
    )

    standalone = tmp_path / "standalone.orc"
    standalone.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )
    standalone_typed = compile_typed_program(
        standalone,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )

    assert short.entry.definition.name == canonical.entry.definition.name == "cp/loop_in_branch::run"
    assert standalone_typed.entry.definition.name == "entry::run"


def test_typed_entry_rejects_an_unknown_name_at_the_entry_source(tmp_path: Path) -> None:
    entry = _install(tmp_path, "loop_in_branch")

    code, path, line, column = _error(
        entry,
        lambda: compile_typed_program(
            entry,
            entry_workflow="missing",
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
        ),
    )

    assert (code, path, line, column) == ("entry_workflow_unknown", entry, 1, 1)


def test_typed_entry_selection_stays_within_the_entry_module(tmp_path: Path) -> None:
    helper = tmp_path / "cp" / "helper.orc"
    helper.parent.mkdir(parents=True, exist_ok=True)
    helper.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/helper)
  (export helper)
  (defworkflow helper () -> Int 1))
''',
        encoding="utf-8",
    )
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/helper :as h :only (helper))
  (export start)
  (defworkflow private () -> Int 2)
  (defworkflow start () -> Int 3))
''',
        encoding="utf-8",
    )

    private = compile_typed_program(
        entry,
        entry_workflow="cp/entry::private",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    assert private.entry.definition.name == "cp/entry::private"

    code, path, line, column = _error(
        entry,
        lambda: compile_typed_program(
            entry,
            entry_workflow="cp/helper::helper",
            source_roots=(tmp_path,),
            command_boundaries={},
        ),
    )

    assert (code, path, line, column) == ("entry_workflow_unknown", entry, 1, 1)


def test_imported_snapshots_with_conflicting_context_are_refused(tmp_path: Path) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/producer)
  (export get)
  (defworkflow get ((value Int)) -> Int value))
''',
        encoding="utf-8",
    )
    first = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    second = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={
            "unused": ExternalToolBinding(
                name="unused",
                stable_command=("python", "changed.py"),
            )
        },
    )
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"first": first, "second": second},
        ),
    )

    assert code == "compiled_workflow_snapshot_conflict"
    assert path == producer_path


def test_imported_snapshots_can_select_different_exports_from_one_context(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/producer)
  (export get other)
  (defworkflow get ((value Int)) -> Int value)
  (defworkflow other ((flag Bool)) -> Bool flag))
''',
        encoding="utf-8",
    )
    get = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    other = compile_typed_program(
        producer_path,
        entry_workflow="other",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"number": get, "flag": other},
    )

    assert consumer.imported_programs == {"number": get, "flag": other}


def test_old_entry_keeps_compiling_when_imported_snapshots_conflict(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "producer.orc"
    bundles = []
    for value in (1, 2):
        producer_path.write_text(
            f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (export get)
  (defworkflow get () -> Int {value}))
''',
            encoding="utf-8",
        )
        result = compile_stage3_entrypoint(
            producer_path,
            source_roots=(tmp_path,),
            validate_shared=True,
            workspace_root=tmp_path,
        )
        bundles.append(result.validated_bundles_by_name["producer::get"])

    parent_path = tmp_path / "parent.orc"
    parent_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule parent)
  (export run)
  (defworkflow run () -> Int (call one)))
''',
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        parent_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
        imported_workflow_bundles={"one": bundles[0], "two": bundles[1]},
    )

    assert "parent::run" in result.validated_bundles_by_name
    assert result.entry_result.typed_program is None


@pytest.mark.parametrize(
    "partial_workflow", ["missing_body", "missing_definition", "missing_env"]
)
def test_partial_non_entry_workflow_prevents_snapshot_admission(
    tmp_path: Path, partial_workflow: str,
) -> None:
    producer_path = tmp_path / "child.orc"
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule child)
  (export run)
  (defworkflow helper ((value Int)) -> Int value)
  (defworkflow run ((value Int)) -> Int (call helper :value value)))
''',
        encoding="utf-8",
    )
    producer = compile_typed_program(
        producer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    workflows = dict(producer.workflows)
    if partial_workflow == "missing_body":
        workflows["child::helper"] = replace(
            workflows["child::helper"],
            typed_body=None,
        )
    elif partial_workflow == "missing_definition":
        del workflows["child::helper"]
    else:
        workflow_type_envs = dict(producer.workflow_type_envs)
        del workflow_type_envs["child::helper"]
        partial = replace(
            producer,
            workflows=workflows,
            workflow_type_envs=workflow_type_envs,
        )
    if partial_workflow != "missing_env":
        partial = replace(producer, workflows=workflows)

    consumer_path = tmp_path / "parent.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule parent)
  (export run)
  (defworkflow run ((value Int)) -> Int (call dep :value value)))
''',
        encoding="utf-8",
    )
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": partial},
        ),
    )

    assert code == "compiled_workflow_source_required"
    assert path == producer_path


@pytest.mark.parametrize("depth", (1, 2, 3))
def test_incomplete_transitive_program_snapshot_is_locally_refused(
    tmp_path: Path,
    depth: int,
) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule producer)
  (export get)
  (defworkflow get () -> Int 1))
''',
        encoding="utf-8",
    )
    producer = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    incomplete = replace(producer, imported_programs={"missing": None})
    for _ in range(depth - 1):
        incomplete = replace(producer, imported_programs={"nested": incomplete})
    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": incomplete},
        ),
    )

    assert code == "compiled_workflow_source_required"
    assert path == producer_path


@pytest.mark.parametrize("edit_source", [False, True])
def test_imported_snapshot_must_match_an_overlapping_source_graph(
    tmp_path: Path, edit_source: bool,
) -> None:
    producer_path = tmp_path / "cp" / "shared.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/shared)
  (export get)
  (defworkflow get ((value Int)) -> Int value))
''',
        encoding="utf-8",
    )
    snapshot = compile_typed_program(
        producer_path,
        entry_workflow="get",
        source_roots=(tmp_path,),
        command_boundaries={},
    )
    if edit_source:
        producer_path.write_bytes(producer_path.read_bytes() + b"\n; changed source revision\n")
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (import cp/shared :as source :only (get))
  (export run)
  (defworkflow run () -> Int (call dep :value 1)))
''',
        encoding="utf-8",
    )

    if not edit_source:
        compiled = compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": snapshot},
        )
        assert compiled.entry.definition.name == "cp/consumer::run"
        return

    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_programs={"dep": snapshot},
        ),
    )

    assert (code, path) == ("compiled_workflow_snapshot_conflict", producer_path)


def test_source_digests_use_consumed_import_bytes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    helper = _install(tmp_path, "loop_in_branch", target="2.34")
    helper_source = helper.read_bytes()
    helper_source_text = helper_source.decode("utf-8").replace("(export run)", "(export Box run)")
    helper.write_text(helper_source_text, encoding="utf-8")
    entry = tmp_path / "cp" / "entry.orc"
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/entry)
  (import cp/loop_in_branch :as old :only (Box run))
  (export start)
  (defworkflow start ((go Bool)) -> Box
    (call old.run :go go)))
''',
        encoding="utf-8",
    )
    trace = SourceReadTrace()
    original = compile_stage3_entrypoint
    changed = False

    def compile_then_edit(*args, **kwargs):
        nonlocal changed
        result = original(*args, **kwargs)
        if not changed:
            helper.write_bytes(helper.read_bytes() + b"\n; changed after compile\n")
            changed = True
        return result

    monkeypatch.setattr("orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint", compile_then_edit)
    typed = compile_typed_program(
        entry,
        entry_workflow="start",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        source_read_trace=trace,
    )
    monkeypatch.setattr("orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint", original)
    fresh = compile_typed_program(
        entry,
        entry_workflow="start",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
    )

    assert typed.source_file_digests["cp/loop_in_branch"] == hashlib.sha256(helper_source_text.encode()).hexdigest()
    assert fresh.source_file_digests["cp/loop_in_branch"] == hashlib.sha256(helper.read_bytes()).hexdigest()
    assert typed.source_file_digests["cp/loop_in_branch"] != fresh.source_file_digests["cp/loop_in_branch"]


def test_local_definition_keys_ignore_paths_positions_and_pure_bindings(tmp_path: Path) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/local)
  (export run)
  (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int :effects () :lowering inline (hook value))
  (defworkflow run ((choice Bool) (input Int)) -> Int
    (if choice
      (let-proc (increment ((value Int)) -> Int :captures () (+ value 1))
        (apply-int (proc-ref increment) input))
      (let-proc (increment ((value Int)) -> Int :captures () (+ value 2))
        (apply-int (proc-ref increment) input)))))
'''
    changed = source.replace(
        "  (defworkflow run ((choice Bool) (input Int)) -> Int\n",
        "  (defworkflow run ((choice Bool) (input Int)) -> Int\n    (let* ((unused 0))\n",
    )
    changed = changed.replace(
        "        (apply-int (proc-ref increment) input)))))\n",
        "        (apply-int (proc-ref increment) input))))))\n",
    )
    first = tmp_path / "first" / "cp" / "local.orc"
    second = tmp_path / "elsewhere" / "cp" / "local.orc"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text(source, encoding="utf-8")
    second.write_text(changed, encoding="utf-8")

    first_typed = compile_typed_program(
        first,
        entry_workflow="run",
        source_roots=(first.parent.parent,),
        command_boundaries={},
    )
    second_typed = compile_typed_program(
        second,
        entry_workflow="run",
        source_roots=(second.parent.parent,),
        command_boundaries={},
    )

    first_keys = tuple(sorted(first_typed.local_definition_keys.values()))
    second_keys = tuple(sorted(second_typed.local_definition_keys.values()))
    assert len(first_keys) == 2
    assert first_keys == second_keys
    assert {key[0] for key in first_keys} == {"cp/local::run"}
    assert {key[2] for key in first_keys} == {0, 1}


def test_local_definition_specializations_keep_base_capture_and_declaration_identity(
    tmp_path: Path,
) -> None:
    entry = _install(tmp_path, "local_proc_specializations")
    typed = compile_typed_program(
        entry,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
    )

    local_procedures = tuple(
        procedure
        for procedure in typed.procedures.values()
        if procedure.definition.generated_local_procedure is not None
    )
    bases = {
        procedure.definition.name: procedure
        for procedure in local_procedures
        if procedure.specialization is None
    }
    specializations = tuple(
        procedure for procedure in local_procedures if procedure.specialization is not None
    )

    assert len(bases) == len(specializations) == 2
    assert {
        key[2]
        for name, key in typed.local_definition_keys.items()
        if name in bases
    } == {0, 1}
    for specialization in specializations:
        base_name = specialization.specialization.base_name
        base = bases[base_name]
        assert base.definition.generated_local_procedure.capture_names == ("v",)
        assert typed.local_definition_keys[specialization.definition.name] == (
            typed.local_definition_keys[base_name]
        )
        assert typed.local_definition_keys[base_name][3] == (("v", "Int"),)


def test_macro_expansion_local_identity_is_scoped_to_its_callable(tmp_path: Path) -> None:
    source = f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule sample)
  (export run)
  (defproc apply-int ((hook ProcRef[Int -> Int]) (value Int)) -> Int :effects () :lowering inline (hook value))
  (defmacro invoke (value)
    (let-proc (increment ((arg Int)) -> Int :captures () (+ arg 1))
      (apply-int (proc-ref increment) value)))
  (defworkflow run ((input Int)) -> Int (invoke input)))
'''
    with_other = source.rstrip()[:-1] + '''
  (defworkflow other ((input Int)) -> Int
    (if true (invoke input) (invoke input))))
'''
    path = tmp_path / "sample.orc"
    path.write_text(source, encoding="utf-8")

    def compile_current():
        return compile_typed_program(
            path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
        )

    first = compile_current()
    path.write_text(with_other, encoding="utf-8")
    second = compile_current()

    first_run_keys = tuple(
        key for key in first.local_definition_keys.values() if key[0] == "sample::run"
    )
    second_run_keys = tuple(
        key for key in second.local_definition_keys.values() if key[0] == "sample::run"
    )
    assert first_run_keys
    assert first_run_keys == second_run_keys


def test_old_source_producer_retains_typed_snapshot_on_result_and_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    entry = tmp_path / "cp" / "producer.orc"
    entry.parent.mkdir(parents=True)
    source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
    '''
    entry.write_text(source, encoding="utf-8")
    caller_boundaries = {
        "original": ExternalToolBinding(
            name="original",
            stable_command=("python", "original.py"),
        )
    }
    lower_calls = []
    shared_calls = []
    executable_calls = []
    original_lower = compiler_module._lower_workflows_for_route
    original_validate = compiler_module.validate_lowered_workflows
    original_revalidate = compiler_module._revalidate_stage3_executable_bundles
    original_attach = compiler_module._attach_typed_programs_to_source_bundles
    pre_attachment_catalog = {}

    def lower_spy(*args, **kwargs):
        lower_calls.append(kwargs.get("target_dsl_version"))
        return original_lower(*args, **kwargs)

    def validation_spy(*args, **kwargs):
        shared_calls.append(kwargs.get("validation_profile"))
        return original_validate(*args, **kwargs)

    def executable_spy(*args, **kwargs):
        executable_calls.append(True)
        return original_revalidate(*args, **kwargs)

    def attach_spy(bundles_by_name, typed_program):
        pre_attachment_catalog.update(bundles_by_name)
        return original_attach(bundles_by_name, typed_program)

    monkeypatch.setattr(compiler_module, "_lower_workflows_for_route", lower_spy)
    monkeypatch.setattr(compiler_module, "validate_lowered_workflows", validation_spy)
    monkeypatch.setattr(
        compiler_module,
        "_revalidate_stage3_executable_bundles",
        executable_spy,
    )
    monkeypatch.setattr(
        compiler_module,
        "_attach_typed_programs_to_source_bundles",
        attach_spy,
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries=caller_boundaries,
        validate_shared=True,
        workspace_root=tmp_path,
    )

    snapshot = result.entry_result.typed_program
    assert isinstance(snapshot, TypedProgram)
    assert snapshot.entry is None
    assert snapshot.producer_lowering_schema == 2
    assert "cp/producer::private-inc" in snapshot.procedures
    caller_boundaries["later"] = ExternalToolBinding(
        name="later",
        stable_command=("python", "later.py"),
    )
    retained_boundaries = snapshot.configuration_bindings["command_boundaries"]
    assert tuple(retained_boundaries) == ("original",)
    with pytest.raises(TypeError):
        retained_boundaries["mutate"] = caller_boundaries["original"]
    bundle = result.validated_bundles_by_name["cp/producer::get"]
    assert result.entry_result.validated_bundles["cp/producer::get"] is bundle
    assert bundle.typed_program.producer_lowering_schema == 2
    assert result.entry_result.validation_profile is not None
    assert lower_calls == ["2.34"]
    assert shared_calls
    assert executable_calls
    assert result.compiled_results_by_name["cp/producer"].validated_bundles[
        "cp/producer::get"
    ] is bundle
    assert bundle.typed_program.entry.definition.name == "cp/producer::get"
    assert bundle.typed_program.procedures["cp/producer::private-inc"].typed_body is not None
    assert bundle.typed_program.source_file_digests["cp/producer"] == hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()
    kwargs = {
        "target_workflow_names": (bundle.surface.name,),
        "closure": (
            bundle_transport.BundleCapsuleClosureBlob(
                path=entry.name,
                roles=("orc",),
                payload=source.encode("utf-8"),
            ),
        ),
        "workflow_closure_paths": {bundle.surface.name: entry.name},
        "compiler_runtime_identity_digest": "sha256:" + "c" * 64,
        "lowering_schema_version": 2,
    }
    encoded_before_attachment = bundle_transport.encode_bundle_capsule(
        pre_attachment_catalog, **kwargs
    )
    encoded_after_attachment = bundle_transport.encode_bundle_capsule(
        result.validated_bundles_by_name, **kwargs
    )
    assert encoded_before_attachment == encoded_after_attachment


def test_typed_snapshot_copies_certified_adapter_configuration(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "cp" / "producer.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defworkflow get ((n Int)) -> Int n))
''',
        encoding="utf-8",
    )
    input_contract = {"required": ["before"]}
    path_safety = {"kind": "workspace_relpath"}
    adapter = CertifiedAdapterBinding(
        name="adapter",
        stable_command=("python", "adapter.py"),
        input_contract=input_contract,
        output_type_name="Int",
        effects=("structured_result",),
        path_safety=path_safety,
        source_map_behavior="step",
        fixture_ids=("adapter_ok",),
        negative_fixture_ids=("adapter_bad",),
    )

    result = compile_stage3_entrypoint(
        entry,
        source_roots=(tmp_path,),
        command_boundaries={"adapter": adapter},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    snapshot = result.entry_result.typed_program
    assert isinstance(snapshot, TypedProgram)
    retained = snapshot.command_boundaries["adapter"]
    retained_config = snapshot.configuration_bindings["command_boundaries"]["adapter"]
    assert retained is not adapter
    assert retained_config is not adapter
    input_contract["required"].append("after")
    path_safety["kind"] = "unrestricted"
    assert retained.input_contract["required"] == ("before",)
    assert retained.path_safety["kind"] == "workspace_relpath"
    assert retained_config.input_contract["required"] == ("before",)
    assert retained_config.path_safety["kind"] == "workspace_relpath"


def test_typed_program_can_import_an_explicit_source_snapshot(tmp_path: Path) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    producer_snapshot = producer.validated_bundles_by_name[
        "cp/producer::get"
    ].typed_program
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run ((n Int)) -> Int (call dep :n n)))
''',
        encoding="utf-8",
    )

    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        imported_programs={"dep": producer_snapshot},
    )

    assert consumer.entry.definition.name == "cp/consumer::run"
    assert consumer.imported_programs["dep"] is producer_snapshot
    assert consumer.module_workflow_signatures["cp/consumer"]["dep"].params[0][0] == "n"
    assert "cp/producer::private-inc" in consumer.procedures


def test_evaluated_consumer_requires_a_matching_bundle_snapshot(tmp_path: Path) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get other)
  (defworkflow get ((n Int)) -> Int n)
  (defworkflow other ((flag Bool)) -> Bool flag))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        command_boundaries=BOUNDARIES,
        validate_shared=True,
        workspace_root=tmp_path,
    )
    get_bundle = producer.validated_bundles_by_name["cp/producer::get"]
    other_bundle = producer.validated_bundles_by_name["cp/producer::other"]
    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run ((n Int)) -> Int (call dep :n n)))
''',
        encoding="utf-8",
    )

    def compile_bundle(bundle):
        return compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries=BOUNDARIES,
            imported_workflow_bundles={"dep": bundle},
        )

    compiled = compile_bundle(get_bundle)
    assert compiled.imported_programs["dep"] is get_bundle.typed_program
    assert "cp/producer::get" in compiled.workflows
    assert "cp/producer" in compiled.module_type_envs
    assert "cp/producer" not in compiled.source_file_digests

    decoded_bundle = replace(get_bundle, typed_program=None)
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_bundle(decoded_bundle),
    )
    assert code == "compiled_workflow_source_required"
    assert path == Path(get_bundle.provenance.workflow_path)

    restored = replace(decoded_bundle, typed_program=get_bundle.typed_program)
    assert compile_bundle(restored).entry.definition.name == "cp/consumer::run"
    producer_path.unlink()
    assert compile_bundle(restored).entry.definition.name == "cp/consumer::run"

    wrong_pair = replace(decoded_bundle, typed_program=other_bundle.typed_program)
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_bundle(wrong_pair),
    )
    assert code == "compiled_workflow_source_required"
    assert path == Path(get_bundle.provenance.workflow_path)


def test_typed_snapshot_keeps_its_schema_across_a_direct_import(tmp_path: Path) -> None:
    producer_path = tmp_path / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        command_boundaries={},
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route="legacy",
    )
    producer_snapshot = producer.validated_bundles_by_name[
        "cp/producer::get"
    ].typed_program

    consumer_path = tmp_path / "cp" / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/consumer)
  (export run)
  (defworkflow run ((n Int)) -> Int (call dep :n n)))
''',
        encoding="utf-8",
    )
    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"dep": producer_snapshot},
    )

    assert producer_snapshot.producer_lowering_schema == 1
    assert consumer.producer_lowering_schema == 2
    assert consumer.imported_programs["dep"] is producer_snapshot
    with pytest.raises(TypeError, match="producer_lowering_schema"):
        TypedProgram(
            **{
                item.name: getattr(producer_snapshot, item.name)
                for item in fields(TypedProgram)
                if item.name != "producer_lowering_schema"
            }
        )
    for schema in (1, 2):
        assert replace(
            producer_snapshot,
            producer_lowering_schema=schema,
        ).producer_lowering_schema == schema
    for invalid in (True, False, 0, 3, "1", 1.0, None):
        with pytest.raises(ValueError, match="producer_lowering_schema"):
            replace(
                producer_snapshot,
                producer_lowering_schema=invalid,
            )


def test_source_manifest_compilation_keeps_the_supplied_legacy_schema(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "src" / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/producer)
  (export get)
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
''',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "imports.json"
    manifest_path.write_text(
        json.dumps(
            {"dep": {"kind": "compiled", "path": "src/cp/producer.orc"}}
        ),
        encoding="utf-8",
    )

    (binding,) = load_imported_workflow_bundle_manifest(
        manifest_path,
        workspace_root=tmp_path,
        source_roots=(tmp_path / "src",),
        lowering_route="legacy",
    )

    assert binding.bundle.typed_program.producer_lowering_schema == 1
    assert binding.bundle.provenance.frontend_build_root is not None


def test_closed_import_manifest_compiles_evaluated_source_with_default_schema(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "src" / "cp" / "producer.orc"
    producer_path.parent.mkdir(parents=True)
    producer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule cp/producer)
  (export get)
  (defworkflow get ((n Int)) -> Int (+ n 1)))
''',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "imports.json"
    manifest_path.write_text(
        json.dumps(
            {"dep": {"kind": "compiled", "path": "src/cp/producer.orc"}}
        ),
        encoding="utf-8",
    )
    request = FrontendBuildRequest(
        source_path=tmp_path / "cp" / "consumer.orc",
        source_roots=(tmp_path / "src",),
        imported_workflow_bundles_path=manifest_path,
        workspace_root=tmp_path,
    )

    bundles, programs = _load_closed_imports(
        request,
        provider_externs={},
        prompt_externs={},
        command_boundaries={},
        configuration_trace=ConfigurationReadTrace(),
    )

    assert not bundles
    assert programs["dep"].producer_lowering_schema == 2


def test_bundle_snapshot_contract_survives_deleted_nested_nominal_sources(
    tmp_path: Path,
) -> None:
    types_path = tmp_path / "types.orc"
    types_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule types)
  (export Outer)
  (defrecord Inner (x Int))
  (defrecord Outer (inner Inner)))
''',
        encoding="utf-8",
    )
    producer_path = tmp_path / "child.orc"
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule child)
  (import types)
  (export get)
  (defworkflow get ((rows List[types/Outer])) -> Int 1))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = producer.validated_bundles_by_name["child::get"]
    assert compiler_module._typed_program_matches_bundle(bundle.typed_program, bundle)
    types_path.unlink()
    producer_path.unlink()

    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )
    code, path, _line, _column = _error(
        consumer_path,
        lambda: compile_typed_program(
            consumer_path,
            entry_workflow="run",
            source_roots=(tmp_path,),
            command_boundaries={},
            imported_workflow_bundles={"dep": bundle},
        ),
    )

    assert (code, path) == ("workflow_call_signature_erased", producer_path)


def test_typed_product_preserves_grouped_inputs_and_defaults(tmp_path: Path) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (export get)
  (defrecord Pair (left Int) (right Int))
  (defworkflow get ((a Pair) (count Int :default 3)) -> Int count))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = producer.validated_bundles_by_name["producer::get"]

    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defrecord Pair (left Int) (right Int))
  (defworkflow run ((pair Pair)) -> Int (call dep :a pair)))
''',
        encoding="utf-8",
    )
    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_workflow_bundles={"dep": bundle},
    )

    imported_signature = consumer.module_workflow_signatures["consumer"]["dep"]
    assert [(name, type_ref.name) for name, type_ref in imported_signature.params] == [
        ("a", "Pair"),
        ("count", "Int"),
    ]
    assert imported_signature.param_defaults["count"].datum == 3
    assert imported_signature.hidden_context_requirements == bundle.typed_program.entry.signature.hidden_context_requirements
    assert imported_signature.private_compatibility_bridge_types == bundle.typed_program.entry.signature.private_compatibility_bridge_types


def test_typed_product_groups_private_context_by_its_source_formal(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (import std/phase :only (with-phase))
  (export entry run-phase)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord Pair (x String) (y String))
  (defrecord Result (label String) (phase_name Symbol))
  (defworkflow entry
    ((pair Pair))
    -> Result
    (call run-phase :a__x pair.x :a__y pair.y))
  (defworkflow run-phase
    ((phase__ctx PhaseCtx)
     (a__x String)
     (a__y String))
    -> Result
    (with-phase phase__ctx plan-gate-wrapper
      (record Result
        :label a__x
        :phase_name phase__ctx.phase-name))))
''',
        encoding="utf-8",
    )
    producer = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = producer.validated_bundles_by_name["producer::run-phase"]
    native_signature = bundle.typed_program.entry.signature
    assert compiler_module._typed_program_matches_bundle(bundle.typed_program, bundle)
    assert set(native_signature.hidden_context_requirements) == {"phase__ctx"}
    private_bindings = workflow_boundary_projection(bundle).private_runtime_context_bindings
    assert len(private_bindings) == 1
    assert private_bindings[0].source_param_name == "phase__ctx"
    changed_provenance = replace(
        private_bindings[0],
        source_provenance={"workflow_name": "other-owner", "path": "/other/source.orc"},
    )
    provenance_bundle = replace(
        bundle,
        provenance=replace(
            bundle.provenance,
            private_exec_context_bindings=(changed_provenance,),
        ),
    )
    assert compiler_module._typed_program_matches_bundle(
        bundle.typed_program,
        provenance_bundle,
    )
    changed_source = replace(private_bindings[0], source_param_name="other-context")
    source_bundle = replace(
        bundle,
        provenance=replace(
            bundle.provenance,
            private_exec_context_bindings=(changed_source,),
        ),
    )
    assert not compiler_module._typed_program_matches_bundle(
        bundle.typed_program,
        source_bundle,
    )

    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
  (defmodule consumer)
  (export run)
  (defrecord RunCtx
    (run-id RunId)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord PhaseCtx
    (run RunCtx)
    (phase-name Symbol)
    (state-root Path.state-root)
    (artifact-root Path.artifact-root))
  (defrecord Pair (x String) (y String))
  (defrecord Result (label String) (phase_name Symbol))
  (defworkflow run
    ((phase__ctx PhaseCtx)
     (pair Pair))
    -> Result
    (call dep :phase__ctx phase__ctx :a pair)))
''',
        encoding="utf-8",
    )
    consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_workflow_bundles={"dep": bundle},
    )

    imported_signature = consumer.module_workflow_signatures["consumer"]["dep"]
    assert [(name, type_ref.name) for name, type_ref in imported_signature.params] == [
        ("a", "Pair"),
        ("phase__ctx", "PhaseCtx"),
    ]
    bundle_requirement = imported_signature.hidden_context_requirements["phase__ctx"]
    assert (bundle_requirement.binding_kind, bundle_requirement.allows_entry_bootstrap) == (
        "derived_private_child_context",
        True,
    )

    typed_consumer = compile_typed_program(
        consumer_path,
        entry_workflow="run",
        source_roots=(tmp_path,),
        command_boundaries={},
        imported_programs={"dep": bundle.typed_program},
    )
    typed_signature = typed_consumer.module_workflow_signatures["consumer"]["dep"]
    assert [(name, type_ref.name) for name, type_ref in typed_signature.params] == [
        ("a", "Pair"),
        ("phase__ctx", "PhaseCtx"),
    ]
    assert typed_signature.hidden_context_requirements == (
        native_signature.hidden_context_requirements
    )


def test_source_snapshot_boundary_capture_rejects_projection_changes(
    tmp_path: Path,
) -> None:
    entry = tmp_path / "cp" / "union.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/union)
  (export run)
  (defunion Outcome (OK (value Int)) (NOPE (reason String)))
  (defworkflow run ((flag Bool)) -> Outcome
    (if flag
      (variant Outcome OK :value 1)
      (variant Outcome NOPE :reason "no"))))
''',
        encoding="utf-8",
    )
    result = compile_stage3_module(
        entry,
        entry_workflow="run",
        validate_shared=True,
        workspace_root=tmp_path,
    )
    bundle = result.validated_bundles["run"]
    retained = bundle.typed_program._compiled_bundle_boundaries["run"]
    assert compiler_module._typed_program_matches_bundle(bundle.typed_program, bundle)
    assert "projection" in retained[1]["return__variant"]
    with pytest.raises(TypeError):
        retained[1]["return__variant"]["projection"]["return_kind"] = "record"

    original = bundle.surface.outputs["return__variant"]
    changed_definition = dict(original.definition)
    changed_projection = dict(changed_definition["projection"])
    changed_projection["active_variants"] = ("NOPE",)
    changed_definition["projection"] = changed_projection
    changed_surface = replace(
        bundle.surface,
        outputs={
            **bundle.surface.outputs,
            "return__variant": SurfaceContract(
                name=original.name,
                kind=original.kind,
                value_type=original.value_type,
                definition=changed_definition,
                from_ref=original.from_ref,
            ),
        },
    )
    changed_bundle = replace(bundle, surface=changed_surface)
    assert not compiler_module._typed_program_matches_bundle(
        bundle.typed_program,
        changed_bundle,
    )


@pytest.mark.parametrize("supply_trace", (True, False))
@pytest.mark.parametrize(
    ("lowering_route", "expected_schema"),
    ((None, 2), ("legacy", 1)),
)
def test_standalone_old_source_producer_retains_snapshot_and_passes_trace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    supply_trace: bool,
    lowering_route: str | None,
    expected_schema: int,
) -> None:
    entry = tmp_path / "producer.orc"
    source = '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defproc private-inc ((n Int)) -> Int :effects () :lowering inline (+ n 1))
  (defworkflow get ((n Int)) -> Int (private-inc n)))
'''
    entry.write_text(source, encoding="utf-8")
    supplied_trace = SourceReadTrace() if supply_trace else None
    seen_traces = []
    original_detector = compiler_module._syntax_module_uses_module_graph
    original_pipeline = compiler_module._run_stage3_validation_pipeline
    lowered_targets = []
    original_lowerer = compiler_module._lower_workflows_for_route

    def trace_detector(path: Path, *, source_read_trace: SourceReadTrace | None = None):
        seen_traces.append(source_read_trace)
        return original_detector(path, source_read_trace=source_read_trace)

    def compile_then_delete(*args, **kwargs):
        result = original_pipeline(*args, **kwargs)
        entry.unlink()
        return result

    def traced_lowerer(*args, **kwargs):
        lowered_targets.append(kwargs["target_dsl_version"])
        return original_lowerer(*args, **kwargs)

    monkeypatch.setattr(
        compiler_module,
        "_syntax_module_uses_module_graph",
        trace_detector,
    )
    monkeypatch.setattr(
        compiler_module,
        "_run_stage3_validation_pipeline",
        compile_then_delete,
    )
    monkeypatch.setattr(
        compiler_module,
        "_lower_workflows_for_route",
        traced_lowerer,
    )
    result = compile_stage3_module(
        entry,
        validate_shared=True,
        workspace_root=tmp_path,
        lowering_route=lowering_route,
        source_read_trace=supplied_trace,
    )

    snapshot = result.typed_program
    assert isinstance(snapshot, TypedProgram)
    assert snapshot.producer_lowering_schema == expected_schema
    assert snapshot.entry is None
    assert result.module.module_name is None
    assert "get" in snapshot.workflows
    assert "private-inc" in snapshot.procedures
    assert len(seen_traces) == 1
    assert isinstance(seen_traces[0], SourceReadTrace)
    if supplied_trace is not None:
        assert seen_traces[0] is supplied_trace
    trace = seen_traces[0]
    assert trace.records
    assert not entry.exists()
    assert snapshot.source_file_digests["producer"] == hashlib.sha256(
        source.encode("utf-8")
    ).hexdigest()
    assert "get" in result.validated_bundles
    assert lowered_targets == ["2.34"]


@pytest.mark.parametrize(
    ("module_name", "expected_module"),
    ((None, "entry"), ("producer", "producer")),
)
def test_standalone_evaluated_source_producer_keeps_canonical_namespace(
    tmp_path: Path,
    module_name: str | None,
    expected_module: str,
) -> None:
    entry = tmp_path / (
        "path_specific_name.orc" if module_name is None else "producer.orc"
    )
    module_declaration = (
        "" if module_name is None else "  (defmodule producer)\n  (export run)\n"
    )
    entry.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "{TARGET}")
{module_declaration}  (defworkflow run () -> Int 1))
''',
        encoding="utf-8",
    )

    result = compile_stage3_module(entry)

    assert result.module.module_name == expected_module
    assert result.typed_program.entry_module == expected_module
    assert tuple(result.typed_program.workflows) == (f"{expected_module}::run",)
    assert result.lowered_workflows == ()


def test_graph_source_producer_passes_one_trace_through_delegation_and_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = tmp_path / "cp" / "entry.orc"
    child = tmp_path / "cp" / "child.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/entry)
  (import cp/child :only (inc))
  (export run)
  (defworkflow run ((n Int)) -> Int (call inc :n n)))
''',
        encoding="utf-8",
    )
    child.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/child)
  (export inc)
  (defworkflow inc ((n Int)) -> Int (+ n 1)))
''',
        encoding="utf-8",
    )
    supplied_trace = SourceReadTrace()
    delegated_traces = []
    recorded_traces = []
    lowered_targets = []
    original_entrypoint = compiler_module.compile_stage3_entrypoint
    original_record = SourceReadTrace._record
    original_lowerer = compiler_module._lower_workflows_for_route

    def delegated_entrypoint(*args, **kwargs):
        delegated_traces.append(kwargs["source_read_trace"])
        return original_entrypoint(*args, **kwargs)

    def observed_record(trace, **kwargs):
        recorded_traces.append(trace)
        return original_record(trace, **kwargs)

    def observed_lowerer(*args, **kwargs):
        lowered_targets.append(kwargs["target_dsl_version"])
        return original_lowerer(*args, **kwargs)

    monkeypatch.setattr(
        compiler_module,
        "compile_stage3_entrypoint",
        delegated_entrypoint,
    )
    monkeypatch.setattr(SourceReadTrace, "_record", observed_record)
    monkeypatch.setattr(
        compiler_module,
        "_lower_workflows_for_route",
        observed_lowerer,
    )
    result = compile_stage3_module(
        entry,
        entry_workflow="run",
        validate_shared=True,
        workspace_root=tmp_path,
        source_read_trace=supplied_trace,
    )

    assert result.typed_program is not None
    assert delegated_traces == [supplied_trace]
    assert recorded_traces
    assert all(trace is supplied_trace for trace in recorded_traces)
    assert len(lowered_targets) == 2
    assert set(lowered_targets) == {"2.34"}


def test_graph_source_producer_rejects_conflicting_repeated_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entry = tmp_path / "cp" / "entry.orc"
    child = tmp_path / "cp" / "child.orc"
    entry.parent.mkdir(parents=True)
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/entry)
  (import cp/child :only (inc))
  (export run)
  (defworkflow run ((n Int)) -> Int (call inc :n n)))
''',
        encoding="utf-8",
    )
    child.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/child)
  (export inc)
  (defworkflow inc ((n Int)) -> Int (+ n 1)))
''',
        encoding="utf-8",
    )
    original_read_bytes = Path.read_bytes
    child_reads = 0

    def change_second_child_read(path: Path) -> bytes:
        nonlocal child_reads
        content = original_read_bytes(path)
        if path.resolve() == child.resolve():
            child_reads += 1
            if child_reads == 2:
                return content + b"\n; source changed during compilation\n"
        return content

    monkeypatch.setattr(Path, "read_bytes", change_second_child_read)
    trace = SourceReadTrace()
    with pytest.raises(RuntimeError):
        compile_stage3_module(
            entry,
            entry_workflow="run",
            validate_shared=True,
            workspace_root=tmp_path,
            source_read_trace=trace,
        )

    assert child_reads == 2
    assert trace.revision_conflict_paths == (child.resolve(),)


def test_old_source_compilation_preserves_opaque_import_without_claiming_full_snapshot(
    tmp_path: Path,
) -> None:
    child_path = tmp_path / "cp" / "child.orc"
    child_path.parent.mkdir(parents=True)
    child_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/child)
  (export inc)
  (defworkflow inc ((n Int)) -> Int (+ n 1)))
''',
        encoding="utf-8",
    )
    child_result = compile_stage3_entrypoint(
        child_path,
        source_roots=(tmp_path,),
        validate_shared=True,
        workspace_root=tmp_path,
    )
    opaque_child = replace(
        child_result.validated_bundles_by_name["cp/child::inc"],
        typed_program=None,
    )
    caller_path = tmp_path / "cp" / "caller.orc"
    caller_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule cp/caller)
  (export run)
  (defworkflow run ((n Int)) -> Int (call dep :n n)))
''',
        encoding="utf-8",
    )

    result = compile_stage3_entrypoint(
        caller_path,
        source_roots=(tmp_path,),
        imported_workflow_bundles={"dep": opaque_child},
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.entry_result.typed_program is None
    assert result.entry_result.lowered_workflows
    assert "cp/caller::run" in result.validated_bundles_by_name


def test_standalone_old_source_compilation_withholds_conflicting_snapshot(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_bundles = []
    for value in (1, 2):
        producer_path.write_text(
            f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule producer)
  (export get)
  (defworkflow get () -> Int {value}))
''',
            encoding="utf-8",
        )
        producer = compile_stage3_entrypoint(
            producer_path,
            source_roots=(tmp_path,),
            validate_shared=True,
            workspace_root=tmp_path,
        )
        producer_bundles.append(
            producer.validated_bundles_by_name["producer::get"]
        )

    caller_path = tmp_path / "caller.orc"
    caller_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.34")
  (defmodule caller)
  (export run)
  (defworkflow run () -> Int (call first)))
''',
        encoding="utf-8",
    )
    result = compile_stage3_module(
        caller_path,
        imported_workflow_bundles={
            "first": producer_bundles[0],
            "second": producer_bundles[1],
        },
        validate_shared=True,
        workspace_root=tmp_path,
    )

    assert result.typed_program is None
    assert result.lowered_workflows
    assert "run" in result.validated_bundles


def test_imported_private_enum_owners_survive_evaluated_retyping(tmp_path: Path) -> None:
    (tmp_path / "cp").mkdir()
    for module, values, member, export_name in (
        ("alpha", "DONE BLOCKED", "DONE", "get-alpha"),
        ("beta", "READY FAILED", "READY", "get-beta"),
    ):
        pure_check = f"{module}-pure-check"
        (tmp_path / "cp" / f"{module}.orc").write_text(
            f'''(workflow-lisp
  (:language "0.1") (:target-dsl "2.25")
  (defmodule cp/{module}) (export {export_name} {pure_check} legacy)
  (defenum Status {values})
  (defrecord Result (status Status))
  (defproc {export_name} () -> Result :effects () :lowering inline
    (record Result :status Status.{member}))
  (defun {pure_check} () -> Bool (= Status.{member} Status.{member}))
  (defworkflow legacy () -> Result ({export_name})))
''',
            encoding="utf-8",
        )
    entry = tmp_path / "cp" / "entry.orc"
    for module in ("alpha", "beta"):
        flat = compile_stage3_entrypoint(
            tmp_path / "cp" / f"{module}.orc",
            entry_workflow=f"cp/{module}::legacy",
            source_roots=(tmp_path,),
            command_boundaries={},
            workspace_root=tmp_path,
            validate_shared=True,
        )
        assert f"cp/{module}::legacy" in flat.validated_bundles_by_name

    old_source = f'''(workflow-lisp
  (:language "0.1") (:target-dsl "2.35") (defmodule cp/entry)
  (import cp/alpha :as alpha :only (get-alpha alpha-pure-check))
  (import cp/beta :as beta :only (get-beta beta-pure-check))
  (export run)
  (defenum Status LOCAL OTHER)
  (defworkflow run () -> Bool
    (let* ((left (alpha.get-alpha)) (right (beta.get-beta)))
      (and (= left.status left.status) (= right.status right.status)
        (alpha.alpha-pure-check) (beta.beta-pure-check)))))
'''
    entry.write_text(old_source, encoding="utf-8")
    evaluated_source = old_source
    typed = compile_typed_program(
        entry,
        entry_workflow="cp/entry::run",
        source_roots=(tmp_path,),
        command_boundaries={},
        workspace_root=tmp_path,
    )
    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )

    def enum_owners(value):
        if isinstance(value, dict):
            if value.get("kind") == "enum" and value.get("allowed"):
                yield value.get("name")
            for child in value.values():
                yield from enum_owners(child)
        elif isinstance(value, list):
            for child in value:
                yield from enum_owners(child)

    owners = set(enum_owners(program.tree))
    assert {"cp/alpha::Status", "cp/beta::Status"} <= owners

    entry.write_text(evaluated_source.replace("(beta.beta-pure-check)", "Status.MISSING"), encoding="utf-8")
    with pytest.raises(LispFrontendCompileError) as excinfo:
        compile_typed_program(
            entry,
            entry_workflow="cp/entry::run",
            source_roots=(tmp_path,),
            command_boundaries={},
            workspace_root=tmp_path,
        )
    assert excinfo.value.diagnostics[0].code == "enum_member_unknown"


def test_old_imported_enum_snapshot_keeps_its_owner_after_source_deletion(
    tmp_path: Path,
) -> None:
    producer_path = tmp_path / "producer.orc"
    producer_path.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule producer) (export get)
          (defenum Status DONE BLOCKED)
          (defrecord Result (status Status))
          (defproc make () -> Result :effects () :lowering inline
            (record Result :status Status.DONE))
          (defworkflow get () -> Bool
            (let* ((result (make))) (= result.status Status.DONE))))''',
        encoding="utf-8",
    )
    producer_result = compile_stage3_entrypoint(
        producer_path,
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        validate_shared=True,
    )
    producer_bundle = producer_result.validated_bundles_by_name["producer::get"]
    assert producer_bundle.typed_program is not None

    consumer_path = tmp_path / "consumer.orc"
    consumer_path.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule consumer) (export run)
          (defenum Status LOCAL OTHER)
          (defworkflow run () -> Bool (call dep)))''',
        encoding="utf-8",
    )
    producer_path.unlink()
    typed = compile_typed_program(
        consumer_path,
        entry_workflow="consumer::run",
        source_roots=(tmp_path,),
        workspace_root=tmp_path,
        command_boundaries={},
        imported_workflow_bundles={"dep": producer_bundle},
    )
    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )

    def enum_owners(value):
        if isinstance(value, dict):
            if value.get("kind") == "enum" and value.get("allowed"):
                yield value.get("name")
            for child in value.values():
                yield from enum_owners(child)
        elif isinstance(value, list):
            for child in value:
                yield from enum_owners(child)

    assert set(enum_owners(program.tree)) == {"producer::Status"}


def test_generic_retyped_argument_keeps_generated_path_seed_type(tmp_path: Path) -> None:
    helper = tmp_path / "helper.orc"
    helper.write_text(
        '''(workflow-lisp
  (:language "0.1") (:target-dsl "2.14") (defmodule helper) (export run)
  (defpath OutputPath :kind relpath :under "artifacts" :must-exist false)
  (defrecord Result (ok Bool))
  (defproc keep :forall (T) ((value T)) -> T :effects () :lowering inline value)
  (defworkflow run () -> Result
    (let* ((path (keep (__generated-relpath-seed__ OutputPath "artifacts/probe.txt" "probe"))))
      (record Result :ok true))))
''',
        encoding="utf-8",
    )
    old_product = compile_stage3_entrypoint(
        helper,
        entry_workflow="helper::run",
        source_roots=(tmp_path,),
        command_boundaries={},
        workspace_root=tmp_path,
        validate_shared=True,
    )
    assert "helper::run" in old_product.validated_bundles_by_name
    entry = tmp_path / "entry.orc"
    entry.write_text(
        '''(workflow-lisp
  (:language "0.1") (:target-dsl "2.35") (defmodule entry)
  (import helper :only (run)) (export start)
  (defworkflow start () -> Bool (let* ((got (call run))) got.ok)))
''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        entry,
        entry_workflow="entry::start",
        source_roots=(tmp_path,),
        command_boundaries={},
        workspace_root=tmp_path,
    )
    seeds = [
        node
        for workflow in typed.workflows.values()
        for node in walk_expr(workflow.typed_body.expr)
        if isinstance(node, GeneratedRelpathSeedExpr)
    ]
    assert seeds and all(isinstance(node.target_type_ref, PathTypeRef) for node in seeds)
    program = build_closed_program(typed)
    assert ClosedProgram.from_artifact(program.artifact()).digest == program.digest


def test_operator_binding_object_order_is_not_argument_order(tmp_path: Path) -> None:
    fields = " ".join(f"(f{index} Int)" for index in range(11))
    updates = " ".join(f":f{index} {index}" for index in range(11))
    source = tmp_path / "entry.orc"
    source.write_text(
        f'''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule entry) (export run)
  (defrecord State {fields})
  (defworkflow run ((state State)) -> State (record-update state {updates})))
''',
        encoding="utf-8",
    )
    typed = compile_typed_program(
        source,
        entry_workflow="entry::run",
        source_roots=(tmp_path,),
        command_boundaries={},
        workspace_root=tmp_path,
    )
    program = build_closed_program(typed)
    operator = next(node for node in _ast_nodes(program.tree["body"]) if node.get("k") == "op")
    assert len(operator["args"]) == 12
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )

    reordered = json.loads(program.artifact())
    reordered_op = next(node for node in _ast_nodes(reordered["body"]) if node.get("k") == "op")
    reordered_op["payload"]["bindings"] = dict(
        reversed(list(reordered_op["payload"]["bindings"].items()))
    )
    assert ClosedProgram.from_artifact(json.dumps(reordered)).digest == program.digest

    for mode in ("missing", "extra", "wrong_type"):
        tampered = deepcopy(program.tree)
        tampered_op = next(node for node in _ast_nodes(tampered["body"]) if node.get("k") == "op")
        bindings = tampered_op["payload"]["bindings"]
        if mode == "missing":
            del bindings["a10"]
        elif mode == "extra":
            bindings["a12"] = deepcopy(bindings["a11"])
        else:
            bindings["a10"]["type"] = {"kind": "primitive", "name": "String"}
        with pytest.raises(ClosedProgramInvalid):
            ClosedProgram.from_artifact(json.dumps(tampered))


@pytest.mark.parametrize(
    "export_name",
    ("project-selected-item-payload", "project-selection-result"),
)
def test_required_drain_context_stays_an_explicit_entry_input(
    tmp_path: Path, export_name: str
) -> None:
    from tests.workflow_lisp_closed_program_corpus import corpus, prepare

    workflow = next(
        row
        for row in corpus()
        if row.source.as_posix().endswith("lisp_frontend_design_delta/stdlib_payloads.orc")
        and row.name == export_name
    )
    prepared = prepare(workflow, tmp_path)
    prepared.entry.write_bytes(workflow.source.read_bytes())
    old = compile_stage3_entrypoint(
        prepared.entry,
        entry_workflow=workflow.canonical_name,
        source_roots=prepared.source_roots,
        command_boundaries=prepared.commands,
        provider_externs=prepared.providers,
        prompt_externs=prepared.prompts,
        workspace_root=prepared.workspace_root,
        validate_shared=True,
    )
    assert workflow.canonical_name in old.validated_bundles_by_name

    from tests.workflow_lisp_closed_program_corpus import _replace_entry_target

    _replace_entry_target(workflow.source, prepared.entry)
    typed = compile_typed_program(
        prepared.entry,
        entry_workflow=workflow.canonical_name,
        source_roots=prepared.source_roots,
        command_boundaries=prepared.commands,
        provider_externs=prepared.providers,
        prompt_externs=prepared.prompts,
        workspace_root=prepared.workspace_root,
    )
    assert "ctx" in dict(typed.entry.signature.params)
    program = build_closed_program(typed)
    restored = ClosedProgram.from_artifact(program.artifact())
    assert (restored.tree, restored.sites, restored.digest) == (
        program.tree,
        program.sites,
        program.digest,
    )
    assert "ctx" in {name for name, _type in program.tree["params"]}
    assert "ctx" not in program.tree["defaults"]


def test_omitted_non_synthesizable_drain_context_is_refused(tmp_path: Path) -> None:
    source = tmp_path / "entry.orc"
    source.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule entry) (export run)
          (defrecord DrainCtx
            (state-root Path.state-root)
            (artifact-root Path.artifact-root)
            (extra String))
          (defworkflow leaf ((ctx DrainCtx)) -> String ctx.extra)
          (defworkflow run () -> String (call leaf)))''',
        encoding="utf-8",
    )

    with pytest.raises(LispFrontendCompileError) as excinfo:
        typed = compile_typed_program(
            source,
            entry_workflow="entry::run",
            source_roots=(tmp_path,),
            workspace_root=tmp_path,
            command_boundaries={},
        )
        build_closed_program(typed)

    diagnostic = excinfo.value.diagnostics[0]
    assert diagnostic.code == "workflow_signature_mismatch"
    assert "ctx" in diagnostic.message


def test_evaluated_provider_bundle_path_root_applies_to_source_and_snapshot_bodies(
    tmp_path: Path,
) -> None:
    def producer_source(target: str, under: str) -> str:
        return f'''(workflow-lisp (:language "0.1") (:target-dsl "{target}")
 (defmodule producer) (export entry Projection)
 (defpath ResultBundle :kind relpath :under "{under}" :must-exist false)
 (defrecord Result (text String)) (defrecord Projection (text String))
 (defworkflow entry () -> Projection
   (let* ((r (provider-result provider :prompt prompt :inputs () :returns Result))
          (bundlepath (provider-bundle-path r :as ResultBundle)))
     (record Projection :text r.text))))'''

    def compile_kwargs(root: Path):
        return {
            "source_roots": (root,),
            "command_boundaries": {},
            "workspace_root": root,
            "provider_externs": {"provider": "codex"},
            "prompt_externs": {
                "prompt": PromptExtern(name="prompt", input_file="inputs/prompt.md")
            },
        }

    def install_producer(root: Path, target: str, under: str) -> Path:
        root.mkdir(parents=True, exist_ok=True)
        source = root / "producer.orc"
        source.write_text(producer_source(target, under), encoding="utf-8")
        prompt = root / "inputs/prompt.md"
        prompt.parent.mkdir(parents=True, exist_ok=True)
        prompt.write_text("Compile-only prompt boundary.\n", encoding="utf-8")
        return source

    def checked(typed):
        program = build_closed_program(typed)
        restored = ClosedProgram.from_artifact(program.artifact())
        assert (restored.tree, restored.sites, restored.digest) == (
            program.tree,
            program.sites,
            program.digest,
        )
        assert program.sites == _sites_from_nodes(program.tree)
        return program

    def assert_code(action, code: str, source: Path | None = None) -> None:
        with pytest.raises(LispFrontendCompileError) as excinfo:
            action()
        diagnostic = excinfo.value.diagnostics[0]
        assert diagnostic.code == code
        if source is not None:
            assert Path(diagnostic.span.start.path) == source

    invalid_root = tmp_path / "invalid"
    invalid_source = install_producer(invalid_root, "2.14", "state")
    old = compile_stage3_entrypoint(
        invalid_source,
        entry_workflow="producer::entry",
        validate_shared=True,
        **compile_kwargs(invalid_root),
    )
    bundle = old.validated_bundles_by_name["producer::entry"]
    assert bundle.typed_program is not None
    snapshot = bundle.typed_program

    invalid_source.write_text(producer_source("2.35", "state"), encoding="utf-8")
    assert_code(
        lambda: compile_typed_program(
            invalid_source,
            entry_workflow="producer::entry",
            **compile_kwargs(invalid_root),
        ),
        "provider_bundle_path_target_invalid",
        invalid_source,
    )

    invalid_source.write_text(producer_source("2.14", "state"), encoding="utf-8")
    source_consumer = invalid_root / "source-consumer.orc"
    source_consumer.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
 (defmodule source-consumer) (import producer :only (Projection entry)) (export run)
 (defworkflow run () -> Projection (call entry)))''',
        encoding="utf-8",
    )
    source_typed = compile_typed_program(
        source_consumer,
        entry_workflow="source-consumer::run",
        **compile_kwargs(invalid_root),
    )
    invalid_source.unlink()
    assert_code(lambda: checked(source_typed), "provider_bundle_path_target_invalid", invalid_source)

    snapshot_consumer = invalid_root / "snapshot-consumer.orc"
    snapshot_consumer.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
 (defmodule snapshot-consumer) (export run)
 (defpath ResultBundle :kind relpath :under "state" :must-exist false)
 (defrecord Projection (text String))
 (defworkflow run () -> Projection (call dep)))''',
        encoding="utf-8",
    )

    def consume(imported):
        return checked(
            compile_typed_program(
                snapshot_consumer,
                entry_workflow="snapshot-consumer::run",
                imported_workflow_bundles={"dep": imported},
                **compile_kwargs(invalid_root),
            )
        )

    uncalled_consumer = invalid_root / "uncalled-consumer.orc"
    uncalled_consumer.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
 (defmodule uncalled-consumer) (export run)
 (defpath ResultBundle :kind relpath :under "state" :must-exist false)
 (defrecord Projection (text String))
 (defworkflow run () -> String "uncalled"))''',
        encoding="utf-8",
    )
    uncalled = checked(
        compile_typed_program(
            uncalled_consumer,
            entry_workflow="uncalled-consumer::run",
            imported_workflow_bundles={"dep": bundle},
            **compile_kwargs(invalid_root),
        )
    )
    assert uncalled.sites == ()
    assert_code(
        lambda: compile_typed_program(
            snapshot_consumer,
            entry_workflow="snapshot-consumer::run",
            imported_workflow_bundles={"dep": replace(bundle, typed_program=None)},
            **compile_kwargs(invalid_root),
        ),
        "compiled_workflow_source_required",
    )
    assert_code(lambda: consume(replace(bundle, typed_program=snapshot)), "provider_bundle_path_target_invalid", invalid_source)

    valid_root = tmp_path / "valid"
    valid_source = install_producer(valid_root, "2.14", ".orchestrate/runs")
    valid_old = compile_stage3_entrypoint(
        valid_source,
        entry_workflow="producer::entry",
        validate_shared=True,
        **compile_kwargs(valid_root),
    )
    valid_bundle = valid_old.validated_bundles_by_name["producer::entry"]
    valid_source.write_text(producer_source("2.35", ".orchestrate/runs"), encoding="utf-8")
    direct = checked(
        compile_typed_program(
            valid_source,
            entry_workflow="producer::entry",
            **compile_kwargs(valid_root),
        )
    )
    assert len(direct.sites) == 1

    valid_source.write_text(producer_source("2.14", ".orchestrate/runs"), encoding="utf-8")
    source_consumer = valid_root / "source-consumer.orc"
    source_consumer.write_text(
        '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
 (defmodule source-consumer) (import producer :only (Projection entry)) (export run)
 (defworkflow run () -> Projection (call entry)))''',
        encoding="utf-8",
    )
    source_typed = compile_typed_program(
        source_consumer,
        entry_workflow="source-consumer::run",
        **compile_kwargs(valid_root),
    )
    valid_source.unlink()
    source_readback = checked(source_typed)

    valid_snapshot_consumer = valid_root / "snapshot-consumer.orc"
    valid_snapshot_consumer.write_text(
        snapshot_consumer.read_text(encoding="utf-8").replace('under "state"', 'under ".orchestrate/runs"'),
        encoding="utf-8",
    )
    valid_bundle_program = checked(
        compile_typed_program(
            valid_snapshot_consumer,
            entry_workflow="snapshot-consumer::run",
            imported_workflow_bundles={"dep": valid_bundle},
            **compile_kwargs(valid_root),
        )
    )
    assert_code(
        lambda: compile_typed_program(
            valid_snapshot_consumer,
            entry_workflow="snapshot-consumer::run",
            imported_workflow_bundles={"dep": replace(valid_bundle, typed_program=None)},
            **compile_kwargs(valid_root),
        ),
        "compiled_workflow_source_required",
    )
    valid_snapshot = valid_bundle.typed_program
    decoded_bundle = replace(valid_bundle, typed_program=None)
    assert valid_snapshot is not None
    restored_bundle = replace(decoded_bundle, typed_program=valid_snapshot)
    assert checked(
        compile_typed_program(
            valid_snapshot_consumer,
            entry_workflow="snapshot-consumer::run",
            imported_workflow_bundles={"dep": restored_bundle},
            **compile_kwargs(valid_root),
        )
    ).digest == valid_bundle_program.digest
    assert source_readback.sites
