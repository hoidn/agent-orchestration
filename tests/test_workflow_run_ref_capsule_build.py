from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from orchestrator.workflow.executable_ir import CallBoundaryNode, RunRefStepConfig
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.run_ref.capsule_build import (
    CapsuleBuildError,
    assemble_bundle_capsule,
)
from orchestrator.workflow.run_ref.config import (
    BundleProgram,
    PathProgram,
    RunRefBundleCapsuleBinding,
    decode_run_ref_static_config,
)
from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.validation import (
    WorkflowBoundaryValidationPolicy,
    WorkflowMappingBuildRequest,
    WorkflowMappingValidationOptions,
    validate_workflow_mapping,
)
from orchestrator.workflow_lisp.build import (
    FrontendBuildRequest,
    build_frontend_bundle_in_memory,
)
from orchestrator.workflow_lisp.compiler import LoweringRoute


_COMMIT = "0123456789abcdef0123456789abcdef01234567"


def _source() -> str:
    return f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_build)
  (export entry child sibling helper grandchild unused)
  (defworkflow helper () -> String "helper")
  (defworkflow grandchild () -> String "grandchild")
  (defworkflow child () -> String
    (let* ((nested
             (run-ref
               :source (:repo "file:///workspace" :commit "{_COMMIT}")
               :program (:bundle grandchild)
               :inputs ()
               :policy (:setup ())))
           (ordinary (call helper)))
      (string/concat ordinary nested.value)))
  (defworkflow sibling () -> String
    (call helper))
  (defworkflow unused () -> String "unused")
  (defworkflow entry () -> String
    (let* ((first
             (run-ref
               :source (:repo "file:///workspace" :commit "{_COMMIT}")
               :program (:bundle child)
               :inputs ()
               :policy (:setup ())))
           (second
             (run-ref
               :source (:repo "file:///workspace" :commit "{_COMMIT}")
               :program (:bundle sibling)
               :inputs ()
               :policy (:setup ())))
           (compiled
             (run-ref
               :source (:repo "file:///workspace" :commit "{_COMMIT}")
               :program (:path "candidate.orc" :entry candidate)
               :inputs ()
               :returns String
               :policy (:environment :deterministic-effect-free :setup ()))))
      (string/concat first.value second.value compiled.value))))'''


def _compiled(tmp_path: Path):
    source_path = tmp_path / "capsule_build.orc"
    source_path.write_text(_source(), encoding="utf-8")
    return build_frontend_bundle_in_memory(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )


def _raw_selected(result) -> LoadedWorkflowBundle:
    return result.compile_result.entry_result.validated_bundles[
        "capsule_build::entry"
    ]


def _manifest(assembled) -> dict[str, object]:
    return json.loads(assembled.encoded.manifest_bytes)


def _run_ref_configs(bundle: LoadedWorkflowBundle) -> list[RunRefStepConfig]:
    return [
        node.execution_config
        for node in bundle.ir.nodes.values()
        if isinstance(node.execution_config, RunRefStepConfig)
    ]


def test_assemble_bundle_capsule_closes_recursive_targets_imports_and_shared_edges(
    tmp_path: Path,
) -> None:
    result = _compiled(tmp_path)

    assembled = assemble_bundle_capsule(
        _raw_selected(result),
        local_catalog=result.compile_result,
        raw_bytes_by_path=result.source_read_trace,
        lowering_schema_version=2,
    )

    assert assembled is not None
    manifest = _manifest(assembled)
    assert manifest["target_workflow_names"] == [
        "capsule_build::child",
        "capsule_build::grandchild",
        "capsule_build::sibling",
    ]
    assert manifest["bundle_names"] == [
        "capsule_build::child",
        "capsule_build::grandchild",
        "capsule_build::helper",
        "capsule_build::sibling",
    ]
    assert "capsule_build::entry" not in manifest["bundle_names"]
    assert "capsule_build::unused" not in manifest["bundle_names"]
    assert manifest["workflow_closure_paths"] == {
        name: "source/capsule_build.orc"
        for name in manifest["bundle_names"]
    }
    assert [blob.path for blob in assembled.encoded.closure] == [
        "source/capsule_build.orc"
    ]

    configs = _run_ref_configs(assembled.bound_controller)
    by_mode = {type(config.run_ref.program): config for config in configs}
    binding = RunRefBundleCapsuleBinding(assembled.encoded.capsule_digest)
    assert by_mode[BundleProgram].capsule_binding == binding
    assert by_mode[PathProgram].capsule_binding is None


def test_assemble_bundle_capsule_accepts_imported_binding_catalog_and_reads_assets_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = _compiled(tmp_path)
    local = dict(result.compile_result.entry_result.validated_bundles)
    local.pop("capsule_build::grandchild")

    target_path = tmp_path / "asset_target.orc"
    target_path.write_bytes(b"compiled asset target source\n")
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    shared = asset_dir / "shared.md"
    shared.write_bytes(b"shared prompt bytes\n")
    context = asset_dir / "context.json"
    context.write_bytes(b'{"context":true}\n')
    validation = validate_workflow_mapping(
        WorkflowMappingBuildRequest(
            authored_mapping={
                "version": "2.24",
                "name": "capsule_build::grandchild",
                "steps": [
                    {
                        "name": "Provider",
                        "provider": "test-provider",
                        "asset_file": "assets/shared.md",
                        "asset_depends_on": [
                            "assets/shared.md",
                            "assets/context.json",
                        ],
                    }
                ],
            },
            workflow_path=target_path,
            frontend_kind="workflow_lisp",
        ),
        options=WorkflowMappingValidationOptions(
            workspace_root=tmp_path,
            boundary_validation_policy=(
                WorkflowBoundaryValidationPolicy.PUBLIC_CALLABLE
            ),
        ),
    )
    assert validation.errors == ()
    assert validation.bundle is not None
    imported = SimpleNamespace(
        bundle_catalog=MappingProxyType(
            {"capsule_build::grandchild": validation.bundle}
        )
    )
    raw = dict(result.source_read_trace.raw_bytes_by_path)
    raw[target_path.resolve()] = target_path.read_bytes()
    read_count = 0
    original_read_bytes = Path.read_bytes

    def counted_read_bytes(path: Path) -> bytes:
        nonlocal read_count
        if path.resolve() == shared.resolve():
            read_count += 1
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", counted_read_bytes)

    assembled = assemble_bundle_capsule(
        _raw_selected(result),
        local_catalog=local,
        imported_catalogs=(imported,),
        raw_bytes_by_path=raw,
        lowering_schema_version=2,
    )

    assert assembled is not None
    assert read_count == 1
    closure = {blob.path: blob for blob in assembled.encoded.closure}
    assert closure["source/asset_target.orc"].roles == ("orc",)
    assert closure["source/assets/shared.md"].roles == (
        "prompt_asset",
        "workflow_asset",
    )
    assert closure["source/assets/context.json"].roles == (
        "workflow_asset",
    )


def test_assemble_bundle_capsule_includes_nested_supervision_and_peer_assets(
    tmp_path: Path,
) -> None:
    controller_root = tmp_path / "controller"
    controller_root.mkdir()
    controller_path = controller_root / "capsule_nested.orc"
    controller_path.write_text(
        f'''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_nested)
  (export entry child sibling)
  (defworkflow child () -> String "placeholder")
  (defworkflow sibling () -> String "placeholder")
  (defworkflow entry () -> String
    (let* ((child-result
             (run-ref
               :source (:repo "file:///workspace" :commit "{_COMMIT}")
               :program (:bundle child)
               :inputs ()
               :policy (:setup ())))
           (sibling-result
             (run-ref
               :source (:repo "file:///workspace" :commit "{_COMMIT}")
               :program (:bundle sibling)
               :inputs ()
               :policy (:setup ()))))
      (string/concat child-result.value sibling-result.value))))''',
        encoding="utf-8",
    )
    controller = build_frontend_bundle_in_memory(
        FrontendBuildRequest(
            source_path=controller_path,
            source_roots=(controller_root,),
            entry_workflow="entry",
            workspace_root=controller_root,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )

    target_root = tmp_path / "target"
    target_root.mkdir()
    assets = target_root / "assets"
    assets.mkdir()
    member_names = ("worker", "supervisor", "planner", "reviewer")
    for member_name in member_names:
        (assets / f"{member_name}.md").write_text(
            f"{member_name} prompt\n",
            encoding="utf-8",
        )
    provider_path = target_root / "providers.json"
    provider_path.write_text(
        json.dumps(
            {
                f"providers.{member_name}": "codex"
                for member_name in member_names
            }
        ),
        encoding="utf-8",
    )
    prompt_path = target_root / "prompts.json"
    prompt_path.write_text(
        json.dumps(
            {
                f"prompts.{member_name}": f"assets/{member_name}.md"
                for member_name in member_names
            }
        ),
        encoding="utf-8",
    )
    target_path = target_root / "capsule_nested.orc"
    target_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_nested)
  (export child sibling)
  (defworkflow child () -> String
    (with-live-providers
      ((worker
         (provider-result providers.worker
           :prompt prompts.worker :inputs () :timeout-sec 30
           :returns String))
       (supervisor
         (provider-result providers.supervisor
           :prompt prompts.supervisor :inputs () :timeout-sec 30
           :returns ProviderSteeringDirective)
         :observes worker))
      worker))
  (defworkflow sibling () -> String
    (with-live-provider-peers
      ((planner
         (provider-result providers.planner
           :prompt prompts.planner :inputs () :timeout-sec 10
           :returns String))
       (reviewer
         (provider-result providers.reviewer
           :prompt prompts.reviewer :inputs () :timeout-sec 10
           :returns String)))
      planner)))''',
        encoding="utf-8",
    )
    target = build_frontend_bundle_in_memory(
        FrontendBuildRequest(
            source_path=target_path,
            source_roots=(target_root,),
            entry_workflow="child",
            workspace_root=target_root,
            provider_externs_path=provider_path,
            prompt_externs_path=prompt_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    local = dict(controller.compile_result.entry_result.validated_bundles)
    local.pop("capsule_nested::child")
    local.pop("capsule_nested::sibling")
    imported = SimpleNamespace(
        bundle_catalog=target.compile_result.entry_result.validated_bundles
    )
    raw = dict(controller.source_read_trace.raw_bytes_by_path)
    raw.update(target.source_read_trace.raw_bytes_by_path)

    assembled = assemble_bundle_capsule(
        controller.compile_result.entry_result.validated_bundles[
            "capsule_nested::entry"
        ],
        local_catalog=local,
        imported_catalogs=(imported,),
        raw_bytes_by_path=raw,
        lowering_schema_version=2,
    )

    assert assembled is not None
    closure = {blob.path: blob for blob in assembled.encoded.closure}
    assert {
        f"source/assets/{member_name}.md"
        for member_name in member_names
    }.issubset(closure)
    for member_name in member_names:
        assert closure[f"source/assets/{member_name}.md"].roles == (
            "prompt_asset",
        )


def test_assemble_bundle_capsule_terminates_on_reached_import_cycle(
    tmp_path: Path,
) -> None:
    result = _compiled(tmp_path)
    catalog = dict(result.compile_result.entry_result.validated_bundles)
    original = catalog["capsule_build::grandchild"]
    import_storage: dict[str, LoadedWorkflowBundle] = {}
    cyclic = replace(original, imports=MappingProxyType(import_storage))
    import_storage["self"] = cyclic
    catalog["capsule_build::grandchild"] = cyclic

    assembled = assemble_bundle_capsule(
        _raw_selected(result),
        local_catalog=catalog,
        raw_bytes_by_path=result.source_read_trace,
        lowering_schema_version=2,
    )

    assert assembled is not None
    assert "capsule_build::grandchild" in _manifest(assembled)["bundle_names"]


def test_assemble_bundle_capsule_rejects_root_independent_path_collision(
    tmp_path: Path,
) -> None:
    result = _compiled(tmp_path)
    catalog = dict(result.compile_result.entry_result.validated_bundles)
    sibling = catalog["capsule_build::sibling"]
    other_root = tmp_path / "other-root"
    other_root.mkdir()
    other_source = other_root / "capsule_build.orc"
    other_source.write_bytes(b"different source bytes\n")
    catalog["capsule_build::sibling"] = replace(
        sibling,
        provenance=replace(
            sibling.provenance,
            workflow_path=other_source,
            source_root=other_root,
        ),
    )
    raw = dict(result.source_read_trace.raw_bytes_by_path)
    raw[other_source.resolve()] = other_source.read_bytes()

    with pytest.raises(CapsuleBuildError) as raised:
        assemble_bundle_capsule(
            _raw_selected(result),
            local_catalog=catalog,
            raw_bytes_by_path=raw,
            lowering_schema_version=2,
        )

    assert raised.value.code == "run_ref_capsule_closure_collision"


def test_assemble_bundle_capsule_returns_none_without_mode_one(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "plain.orc"
    source_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule plain)
  (export entry)
  (defworkflow entry () -> String "ready"))''',
        encoding="utf-8",
    )
    result = build_frontend_bundle_in_memory(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    selected = result.compile_result.entry_result.validated_bundles[
        "plain::entry"
    ]

    assert assemble_bundle_capsule(
        selected,
        local_catalog={},
        raw_bytes_by_path={},
        lowering_schema_version=2,
    ) is None


def test_assemble_bundle_capsule_ignores_unused_same_name_import_wrapper(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "plain_wrapper.orc"
    source_path.write_text(
        '''(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule plain_wrapper)
  (export entry)
  (defworkflow entry () -> String "ready"))''',
        encoding="utf-8",
    )
    result = build_frontend_bundle_in_memory(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    selected = result.compile_result.entry_result.validated_bundles[
        "plain_wrapper::entry"
    ]
    ghost = replace(selected, imports=MappingProxyType({}))
    wrapper = replace(
        selected,
        imports=MappingProxyType({"unused-self": ghost}),
    )

    assert assemble_bundle_capsule(
        wrapper,
        local_catalog={},
        raw_bytes_by_path={},
        lowering_schema_version=2,
    ) is None


def test_assemble_bundle_capsule_rejects_used_same_name_payload_conflict(
    tmp_path: Path,
) -> None:
    result = _compiled(tmp_path)
    catalog = dict(result.compile_result.entry_result.validated_bundles)
    child = catalog["capsule_build::child"]
    call_alias = next(
        node.call_alias
        for node in child.ir.nodes.values()
        if isinstance(node, CallBoundaryNode)
    )
    helper = child.imports[call_alias]
    changed_helper = replace(
        helper,
        surface=replace(
            helper.surface,
            context=MappingProxyType({"semantic_drift": True}),
        ),
    )
    catalog["capsule_build::child"] = replace(
        child,
        imports=MappingProxyType(
            {**child.imports, call_alias: changed_helper}
        ),
    )

    with pytest.raises(CapsuleBuildError) as raised:
        assemble_bundle_capsule(
            _raw_selected(result),
            local_catalog=catalog,
            raw_bytes_by_path=result.source_read_trace,
            lowering_schema_version=2,
        )

    assert raised.value.code == "run_ref_capsule_catalog_conflict"


@pytest.mark.parametrize(
    ("defect", "expected_code"),
    (
        ("missing_target", "run_ref_capsule_workflow_missing"),
        ("missing_source", "run_ref_capsule_source_missing"),
        ("source_digest", "run_ref_capsule_source_digest_mismatch"),
        ("catalog_conflict", "run_ref_capsule_catalog_conflict"),
    ),
)
def test_assemble_bundle_capsule_fails_closed_on_missing_conflict_and_digest(
    tmp_path: Path,
    defect: str,
    expected_code: str,
) -> None:
    result = _compiled(tmp_path)
    catalog = dict(result.compile_result.entry_result.validated_bundles)
    source_input: object = result.source_read_trace
    imported_catalogs: tuple[object, ...] = ()
    if defect == "missing_target":
        catalog.pop("capsule_build::child")
    elif defect == "missing_source":
        source_input = {}
    elif defect == "source_digest":
        source_input = SimpleNamespace(
            raw_bytes_by_path={
                result.resolved_request.source_path.resolve(): b"tampered\n"
            },
            revision_vector=result.source_read_trace.revision_vector,
        )
    elif defect == "catalog_conflict":
        imported_catalogs = (
            {"capsule_build::child": catalog["capsule_build::child"]},
        )

    with pytest.raises(CapsuleBuildError) as raised:
        assemble_bundle_capsule(
            _raw_selected(result),
            local_catalog=catalog,
            imported_catalogs=imported_catalogs,
            raw_bytes_by_path=source_input,
            lowering_schema_version=2,
        )

    assert raised.value.code == expected_code


def test_assemble_bundle_capsule_rejects_reached_compiler_identity_disagreement(
    tmp_path: Path,
) -> None:
    result = _compiled(tmp_path)
    selected = _raw_selected(result)
    nodes = dict(selected.ir.nodes)
    mode_one_node_id, mode_one_node = next(
        (node_id, node)
        for node_id, node in nodes.items()
        if isinstance(node.execution_config, RunRefStepConfig)
        and isinstance(node.execution_config.run_ref.program, BundleProgram)
    )
    record = mode_one_node.execution_config.run_ref.record
    record["compiler_runtime_identity_digest"] = "sha256:" + "f" * 64
    changed = decode_run_ref_static_config(canonical_json_bytes(record))
    nodes[mode_one_node_id] = replace(
        mode_one_node,
        execution_config=replace(
            mode_one_node.execution_config,
            run_ref=changed,
        ),
    )
    selected = replace(
        selected,
        ir=replace(selected.ir, nodes=MappingProxyType(nodes)),
    )

    with pytest.raises(CapsuleBuildError) as raised:
        assemble_bundle_capsule(
            selected,
            local_catalog=result.compile_result,
            raw_bytes_by_path=result.source_read_trace,
            lowering_schema_version=2,
        )

    assert raised.value.code == "run_ref_capsule_compiler_identity_conflict"
