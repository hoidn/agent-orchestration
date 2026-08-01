from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil
from types import MappingProxyType
from unittest.mock import patch

import pytest

from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow.run_ref import bundle_transport


_COMPILER_IDENTITY = "sha256:" + "c" * 64


def _write_imported_call_sources(root: Path) -> tuple[Path, Path, Path]:
    source_root = root / "src"
    module_root = source_root / "capsule_stage"
    module_root.mkdir(parents=True)
    child_path = module_root / "child.orc"
    child_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_stage/child)
  (export child)
  (defworkflow child () -> String
    "child-ready"))
""",
        encoding="utf-8",
    )
    entry_path = module_root / "entry.orc"
    entry_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_stage/entry)
  (import capsule_stage/child :only (child))
  (export entry)
  (defworkflow entry () -> String
    (call child)))
""",
        encoding="utf-8",
    )
    asset_path = root / "assets" / "instructions.md"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_bytes(b"exact staged asset\r\n")
    return source_root, entry_path, asset_path


def _decoded_imported_capsule(root: Path) -> bundle_transport.DecodedBundleCapsule:
    from orchestrator.workflow_lisp.build import (
        FrontendBuildRequest,
        build_frontend_bundle,
    )
    from orchestrator.workflow_lisp.compiler import LoweringRoute

    source_root, entry_path, asset_path = _write_imported_call_sources(root)
    with patch(
        "orchestrator.workflow_lisp.build.assemble_bundle_capsule",
        return_value=None,
    ):
        built = build_frontend_bundle(
            FrontendBuildRequest(
                source_path=entry_path,
                source_roots=(source_root,),
                entry_workflow="entry",
                workspace_root=root,
                lowering_route=LoweringRoute.WCC_M4,
            )
        )
    [(child_alias, raw_child)] = built.validated_bundle.imports.items()
    child = replace(raw_child, imports=MappingProxyType({}))
    entry = replace(
        built.validated_bundle,
        imports=MappingProxyType({child_alias: child}),
    )
    catalog = {
        entry.surface.name: entry,
        child.surface.name: child,
    }
    workflow_paths = {
        name: bundle.provenance.workflow_path.relative_to(source_root).as_posix()
        for name, bundle in catalog.items()
    }
    source_paths = {
        bundle.provenance.workflow_path.resolve()
        for bundle in catalog.values()
    }
    closure = tuple(
        [
            bundle_transport.BundleCapsuleClosureBlob(
                path=path.relative_to(source_root).as_posix(),
                roles=("orc",),
                payload=path.read_bytes(),
            )
            for path in sorted(source_paths)
        ]
        + [
            bundle_transport.BundleCapsuleClosureBlob(
                path="assets/instructions.md",
                roles=("prompt_asset",),
                payload=asset_path.read_bytes(),
            )
        ]
    )
    encoded = bundle_transport.encode_bundle_capsule(
        catalog,
        target_workflow_names=(built.selected_workflow_name,),
        closure=closure,
        workflow_closure_paths=workflow_paths,
        compiler_runtime_identity_digest=_COMPILER_IDENTITY,
        lowering_schema_version=2,
    )
    return bundle_transport.decode_bundle_capsule(
        manifest_bytes=encoded.manifest_bytes,
        pickle_bytes=encoded.pickle_bytes,
        closure=encoded.closure,
        expected_capsule_digest=encoded.capsule_digest,
        expected_compiler_runtime_identity_digest=_COMPILER_IDENTITY,
    )


def _decoded_single_source_catalog(
    root: Path,
) -> bundle_transport.DecodedBundleCapsule:
    from orchestrator.workflow_lisp.build import (
        FrontendBuildRequest,
        build_frontend_bundle,
    )
    from orchestrator.workflow_lisp.compiler import LoweringRoute

    source_path = root / "capsule_stage_catalog.orc"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_stage_catalog)
  (export first second shared)
  (defworkflow first () -> String "first")
  (defworkflow second () -> String "second")
  (defworkflow shared () -> String "shared"))
""",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(root,),
            entry_workflow="first",
            workspace_root=root,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    catalog = {built.selected_workflow_name: built.validated_bundle}
    encoded = bundle_transport.encode_bundle_capsule(
        catalog,
        target_workflow_names=(built.selected_workflow_name,),
        closure=(
            bundle_transport.BundleCapsuleClosureBlob(
                path=source_path.name,
                roles=("orc",),
                payload=source_path.read_bytes(),
            ),
        ),
        workflow_closure_paths={name: source_path.name for name in catalog},
        compiler_runtime_identity_digest=_COMPILER_IDENTITY,
        lowering_schema_version=2,
    )
    return bundle_transport.decode_bundle_capsule(
        manifest_bytes=encoded.manifest_bytes,
        pickle_bytes=encoded.pickle_bytes,
        closure=encoded.closure,
        expected_capsule_digest=encoded.capsule_digest,
        expected_compiler_runtime_identity_digest=_COMPILER_IDENTITY,
    )


def _decoded_three_workflow_catalog(
    root: Path,
) -> bundle_transport.DecodedBundleCapsule:
    from orchestrator.workflow_lisp.build import (
        FrontendBuildRequest,
        build_frontend_bundle,
    )
    from orchestrator.workflow_lisp.compiler import LoweringRoute

    source_path = root / "capsule_stage_catalog.orc"
    source_path.parent.mkdir(parents=True)
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_stage_catalog)
  (export first second shared)
  (defworkflow first () -> String "first")
  (defworkflow second () -> String "second")
  (defworkflow shared () -> String "shared"))
""",
        encoding="utf-8",
    )
    built = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(root,),
            entry_workflow="first",
            workspace_root=root,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    catalog = dict(built.compile_result.validated_bundles_by_name)
    catalog[built.selected_workflow_name] = built.validated_bundle
    return bundle_transport.DecodedBundleCapsule(
        capsule_digest="sha256:" + "a" * 64,
        target_workflow_names=(built.selected_workflow_name,),
        bundles_by_name=MappingProxyType(catalog),
        closure=(
            bundle_transport.BundleCapsuleClosureBlob(
                path=source_path.name,
                roles=("orc",),
                payload=source_path.read_bytes(),
            ),
        ),
        workflow_closure_paths=MappingProxyType(
            {name: source_path.name for name in catalog}
        ),
    )


def test_stage_bundle_capsule_writes_exact_closure_and_relocates_graph_without_compile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.run_ref import capsule_stage
    from orchestrator.workflow_lisp import compiler, reader

    controller_root = tmp_path / "controller"
    clone_root = tmp_path / "clone"
    clone_root.mkdir()
    decoded = _decoded_imported_capsule(controller_root)
    original_paths = {
        bundle.provenance.workflow_path
        for bundle in decoded.bundles_by_name.values()
    }
    shutil.rmtree(controller_root)
    assert all(not path.exists() for path in original_paths)

    def reject_recompile(*_args, **_kwargs):
        pytest.fail("capsule staging may not invoke the Workflow Lisp compiler")

    def reject_source_read(*_args, **_kwargs):
        pytest.fail("capsule staging may not invoke the Workflow Lisp reader")

    monkeypatch.setattr(compiler, "compile_stage3_entrypoint", reject_recompile)
    monkeypatch.setattr(reader, "read_sexpr_file", reject_source_read)

    staged = capsule_stage.stage_bundle_capsule(decoded, clone_root=clone_root)

    expected_root = (
        clone_root.resolve() / ".orchestrate" / "run-ref-capsule"
    )
    assert staged.staged_root == expected_root
    assert staged.target_workflow_names == decoded.target_workflow_names
    assert type(staged.bundles_by_name).__name__ == "mappingproxy"
    assert type(staged.workflow_paths_by_name).__name__ == "mappingproxy"
    for blob in decoded.closure:
        assert (expected_root / "closure" / blob.path).read_bytes() == blob.payload

    for name, bundle in staged.bundles_by_name.items():
        expected_path = expected_root / "closure" / decoded.workflow_closure_paths[name]
        assert staged.workflow_paths_by_name[name] == expected_path
        assert bundle.provenance.workflow_path == expected_path
        assert bundle.provenance.source_root == expected_root / "closure"
        assert bundle.surface.provenance is bundle.provenance
        assert bundle.core_workflow_ast.provenance is bundle.provenance
        assert bundle.core_workflow_ast._surface_workflow is bundle.surface
        assert bundle.ir.provenance is bundle.provenance
        assert bundle.provenance.frontend_source_trace_path is None
        assert bundle.provenance.frontend_persisted_surface_path is None

    entry = staged.bundles_by_name[staged.target_workflow_names[0]]
    [(alias, child)] = entry.imports.items()
    assert child is staged.bundles_by_name[child.surface.name]
    assert entry.surface.imports[alias].workflow_path == child.provenance.workflow_path
    assert entry.surface.imports[alias].source_root == child.provenance.source_root
    assert entry.core_workflow_ast.imports[alias].workflow_path == child.provenance.workflow_path
    assert entry.core_workflow_ast.imports[alias].source_root == child.provenance.source_root
    with pytest.raises(TypeError):
        staged.bundles_by_name["other"] = child  # type: ignore[index]
    with pytest.raises(TypeError):
        entry.imports["other"] = child  # type: ignore[index]


def test_stage_bundle_capsule_preserves_valid_shared_and_cyclic_object_identity(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.run_ref import capsule_stage

    decoded = _decoded_three_workflow_catalog(tmp_path / "controller")
    originals = dict(decoded.bundles_by_name)
    names = sorted(originals)
    first_name, second_name, shared_name = names
    import_storage = {name: {} for name in names}
    cyclic: dict[str, LoadedWorkflowBundle] = {
        name: replace(
            originals[name],
            imports=MappingProxyType(import_storage[name]),
        )
        for name in names
    }
    import_storage[first_name].update(
        {"peer": cyclic[second_name], "shared": cyclic[shared_name]}
    )
    import_storage[second_name].update(
        {"peer": cyclic[first_name], "shared": cyclic[shared_name]}
    )
    decoded = replace(
        decoded,
        bundles_by_name=MappingProxyType(cyclic),
    )
    clone_root = tmp_path / "clone"
    clone_root.mkdir()

    staged = capsule_stage.stage_bundle_capsule(decoded, clone_root=clone_root)

    first = staged.bundles_by_name[first_name]
    second = staged.bundles_by_name[second_name]
    shared = staged.bundles_by_name[shared_name]
    assert first.imports["peer"] is second
    assert second.imports["peer"] is first
    assert first.imports["shared"] is shared
    assert second.imports["shared"] is shared


def test_stage_bundle_capsule_retains_explicitly_carried_frontend_artifact(
    tmp_path: Path,
) -> None:
    from orchestrator.workflow.run_ref import capsule_stage

    decoded = _decoded_single_source_catalog(tmp_path / "controller")
    [bundle] = decoded.bundles_by_name.values()
    persisted_path = bundle.provenance.frontend_persisted_surface_path
    assert persisted_path is not None
    carried = bundle_transport.BundleCapsuleClosureBlob(
        path=persisted_path.as_posix(),
        roles=("workflow_asset",),
        payload=b"explicit carried frontend artifact\n",
    )
    decoded = replace(
        decoded,
        closure=tuple(sorted((*decoded.closure, carried), key=lambda blob: blob.path)),
    )
    clone_root = tmp_path / "clone"
    clone_root.mkdir()

    staged = capsule_stage.stage_bundle_capsule(decoded, clone_root=clone_root)

    [relocated] = staged.bundles_by_name.values()
    expected = staged.staged_root / "closure" / persisted_path
    assert relocated.provenance.frontend_persisted_surface_path == expected
    assert expected.read_bytes() == carried.payload
    assert relocated.provenance.frontend_source_trace_path is None


@pytest.mark.parametrize("defect", ("escape", "duplicate", "existing_mismatch"))
def test_stage_bundle_capsule_rejects_path_defects_before_staging(
    tmp_path: Path,
    defect: str,
) -> None:
    from orchestrator.workflow.run_ref import capsule_stage

    decoded = _decoded_single_source_catalog(tmp_path / "controller")
    [blob] = decoded.closure
    clone_root = tmp_path / "clone"
    clone_root.mkdir()
    if defect == "escape":
        escaped = replace(blob, path="../escaped.orc")
        decoded = replace(
            decoded,
            closure=(escaped,),
            workflow_closure_paths=MappingProxyType(
                {name: escaped.path for name in decoded.bundles_by_name}
            ),
        )
    elif defect == "duplicate":
        decoded = replace(decoded, closure=(blob, blob))
    else:
        destination = (
            clone_root
            / ".orchestrate"
            / "run-ref-capsule"
            / "closure"
            / blob.path
        )
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"different existing bytes")

    with pytest.raises(
        bundle_transport.BundleCapsuleValidationError,
        match="run_ref_capsule_invalid",
    ):
        capsule_stage.stage_bundle_capsule(decoded, clone_root=clone_root)

    assert not (tmp_path / "escaped.orc").exists()
    if defect == "existing_mismatch":
        assert destination.read_bytes() == b"different existing bytes"


def test_stage_bundle_capsule_rehashes_bytes_after_durable_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.workflow.run_ref import capsule_stage

    decoded = _decoded_single_source_catalog(tmp_path / "controller")
    clone_root = tmp_path / "clone"
    clone_root.mkdir()
    writes: list[Path] = []

    def tampering_write(path: Path, _payload: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"tampered after write")
        writes.append(path)

    monkeypatch.setattr(capsule_stage, "durable_atomic_write", tampering_write)

    with pytest.raises(
        bundle_transport.BundleCapsuleValidationError,
        match="run_ref_capsule_invalid",
    ):
        capsule_stage.stage_bundle_capsule(decoded, clone_root=clone_root)

    assert writes
