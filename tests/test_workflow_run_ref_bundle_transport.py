from __future__ import annotations

import copyreg
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import pickle
from types import MappingProxyType

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
from orchestrator.workflow.run_ref.config import RunRefBundleCapsuleBinding
from orchestrator.workflow.executable_ir import (
    RunRefStepConfig,
    workflow_executable_ir_to_json,
)
from orchestrator.workflow.loaded_bundle import LoadedWorkflowBundle
from orchestrator.workflow_lisp.build import (
    FrontendBuildResult,
    FrontendBuildRequest,
    build_frontend_bundle,
)
from orchestrator.workflow_lisp.compiler import LoweringRoute
from orchestrator.workflow.run_ref import bundle_transport


def _compiled_bundle(tmp_path: Path) -> LoadedWorkflowBundle:
    source_path = tmp_path / "capsule_catalog.orc"
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_catalog)
  (export child sibling)
  (defworkflow child () -> String
    "ready")
  (defworkflow sibling () -> String
    "also-ready"))
""",
        encoding="utf-8",
    )
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="child",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    ).validated_bundle


def _compiled_controller_result(tmp_path: Path) -> FrontendBuildResult:
    source_path = tmp_path / "capsule_controller.orc"
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_controller)
  (export entry child)
  (defworkflow child () -> String
    "ready")
  (defworkflow entry () -> String
    (let* ((trial
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:bundle child)
               :inputs ()
               :policy (:setup ()))))
      trial.value)))
""",
        encoding="utf-8",
    )
    return build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )


def _compiled_controller_bundle(tmp_path: Path) -> LoadedWorkflowBundle:
    result = _compiled_controller_result(tmp_path)
    return result.compile_result.entry_result.validated_bundles[
        "capsule_controller::entry"
    ]


def _compiled_mixed_controller_bundle(tmp_path: Path) -> LoadedWorkflowBundle:
    source_path = tmp_path / "capsule_mixed.orc"
    source_path.write_text(
        """\
(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.24")
  (defmodule capsule_mixed)
  (export entry child)
  (defworkflow child () -> String
    "ready")
  (defworkflow entry () -> String
    (let* ((bundled
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:bundle child)
               :inputs ()
               :policy (:setup ())))
           (compiled
             (run-ref
               :source (:repo "file:///workspace"
                        :commit "0123456789abcdef0123456789abcdef01234567")
               :program (:path "candidate.orc" :entry candidate)
               :inputs ()
               :returns String
               :policy (:environment :deterministic-effect-free :setup ()))))
      bundled.value)))
""",
        encoding="utf-8",
    )
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=source_path,
            source_roots=(tmp_path,),
            entry_workflow="entry",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )
    return result.compile_result.entry_result.validated_bundles[
        "capsule_mixed::entry"
    ]


def _closure(source_path: Path) -> tuple[bundle_transport.BundleCapsuleClosureBlob, ...]:
    return (
        bundle_transport.BundleCapsuleClosureBlob(
            path=source_path.name,
            roles=("orc",),
            payload=source_path.read_bytes(),
        ),
    )


def _workflow_closure_paths(
    bundles: dict[str, LoadedWorkflowBundle],
) -> dict[str, str]:
    return {
        name: bundle.provenance.workflow_path.name
        for name, bundle in bundles.items()
    }


def _encoded_capsule(tmp_path: Path) -> bundle_transport.EncodedBundleCapsule:
    bundle = _compiled_bundle(tmp_path)
    bundles = {bundle.surface.name: bundle}
    return bundle_transport.encode_bundle_capsule(
        bundles,
        target_workflow_names=(bundle.surface.name,),
        closure=_closure(bundle.provenance.workflow_path),
        workflow_closure_paths=_workflow_closure_paths(bundles),
        compiler_runtime_identity_digest="sha256:" + "c" * 64,
        lowering_schema_version=2,
    )


def _manifest_digest(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _rewrite_manifest(
    encoded: bundle_transport.EncodedBundleCapsule,
    mutate,
) -> tuple[bytes, str]:
    manifest = json.loads(encoded.manifest_bytes)
    mutate(manifest)
    manifest_bytes = canonical_json_bytes(manifest)
    return manifest_bytes, _manifest_digest(manifest_bytes)


def test_bundle_capsule_protocol_five_round_trip_is_deterministic_and_frozen(
    tmp_path: Path,
) -> None:
    bundle = _compiled_bundle(tmp_path)
    kwargs = dict(
        target_workflow_names=(bundle.surface.name,),
        closure=_closure(bundle.provenance.workflow_path),
        workflow_closure_paths={
            bundle.surface.name: bundle.provenance.workflow_path.name,
        },
        compiler_runtime_identity_digest="sha256:" + "c" * 64,
        lowering_schema_version=2,
    )

    first = bundle_transport.encode_bundle_capsule(
        {bundle.surface.name: bundle},
        **kwargs,
    )
    second = bundle_transport.encode_bundle_capsule(
        {bundle.surface.name: bundle},
        **kwargs,
    )

    assert first == second
    assert first.pickle_bytes.startswith(b"\x80\x05")
    assert first.capsule_digest == _manifest_digest(first.manifest_bytes)

    decoded = bundle_transport.decode_bundle_capsule(
        manifest_bytes=first.manifest_bytes,
        pickle_bytes=first.pickle_bytes,
        closure=first.closure,
        expected_capsule_digest=first.capsule_digest,
        expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
    )

    assert type(decoded) is bundle_transport.DecodedBundleCapsule
    assert type(decoded.bundles_by_name).__name__ == "mappingproxy"
    assert decoded.target_workflow_names == (bundle.surface.name,)
    assert tuple(decoded.bundles_by_name) == (bundle.surface.name,)
    assert decoded.workflow_closure_paths == {
        bundle.surface.name: bundle.provenance.workflow_path.name,
    }
    decoded_bundle = decoded.bundles_by_name[bundle.surface.name]
    assert type(decoded_bundle) is LoadedWorkflowBundle
    assert type(decoded_bundle.imports).__name__ == "mappingproxy"
    assert type(decoded_bundle.ir.nodes).__name__ == "mappingproxy"
    assert decoded_bundle.surface.name == bundle.surface.name


def test_bundle_capsule_directory_round_trip_preserves_exact_bytes(
    tmp_path: Path,
) -> None:
    encoded = _encoded_capsule(tmp_path)
    capsule_root = tmp_path / "artifact" / "run_ref_bundle_capsule.v1"

    bundle_transport.write_bundle_capsule_directory(capsule_root, encoded)
    loaded = bundle_transport.read_bundle_capsule_directory(
        capsule_root,
        expected_capsule_digest=encoded.capsule_digest,
    )

    assert loaded == encoded
    assert (capsule_root / "manifest.json").read_bytes() == encoded.manifest_bytes
    assert (capsule_root / "bundles.pkl").read_bytes() == encoded.pickle_bytes
    for blob in encoded.closure:
        assert (capsule_root / "closure" / blob.path).read_bytes() == blob.payload


def test_bundle_capsule_directory_rejects_unmanifested_file(
    tmp_path: Path,
) -> None:
    encoded = _encoded_capsule(tmp_path)
    capsule_root = tmp_path / "artifact" / "run_ref_bundle_capsule.v1"
    bundle_transport.write_bundle_capsule_directory(capsule_root, encoded)
    (capsule_root / "closure" / "extra.orc").write_bytes(b"unexpected")

    with pytest.raises(
        ValueError,
        match="run_ref_bundle_directory_invalid",
    ):
        bundle_transport.read_bundle_capsule_directory(
            capsule_root,
            expected_capsule_digest=encoded.capsule_digest,
        )


def test_frontend_build_emits_reachable_mode_one_capsule_and_binds_controller(
    tmp_path: Path,
) -> None:
    result = _compiled_controller_result(tmp_path)

    assert result.run_ref_bundle_capsule is not None
    encoded = result.run_ref_bundle_capsule
    capsule_root = result.build_root / "run_ref_bundle_capsule.v1"
    persisted = bundle_transport.read_bundle_capsule_directory(
        capsule_root,
        expected_capsule_digest=encoded.capsule_digest,
    )
    assert persisted == encoded
    decoded = bundle_transport.decode_bundle_capsule(
        manifest_bytes=encoded.manifest_bytes,
        pickle_bytes=encoded.pickle_bytes,
        closure=encoded.closure,
        expected_capsule_digest=encoded.capsule_digest,
        expected_compiler_runtime_identity_digest=(
            next(
                config.run_ref.compiler_runtime_identity_digest
                for node in result.validated_bundle.ir.nodes.values()
                if isinstance(
                    (config := node.execution_config),
                    RunRefStepConfig,
                )
            )
        ),
    )
    assert decoded.target_workflow_names == ("capsule_controller::child",)
    assert tuple(decoded.bundles_by_name) == ("capsule_controller::child",)
    [controller_config] = [
        node.execution_config
        for node in result.validated_bundle.ir.nodes.values()
        if isinstance(node.execution_config, RunRefStepConfig)
    ]
    assert controller_config.capsule_binding == RunRefBundleCapsuleBinding(
        encoded.capsule_digest
    )
    assert result.artifact_paths["run_ref_bundle_capsule_manifest"] == (
        capsule_root / "manifest.json"
    )
    assert result.artifact_paths["run_ref_bundle_capsule_pickle"] == (
        capsule_root / "bundles.pkl"
    )


def test_frontend_build_without_mode_one_omits_capsule_artifacts(
    tmp_path: Path,
) -> None:
    bundle = _compiled_bundle(tmp_path)
    result = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=bundle.provenance.workflow_path,
            source_roots=(tmp_path,),
            entry_workflow="child",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    )

    assert result.run_ref_bundle_capsule is None
    assert not (result.build_root / "run_ref_bundle_capsule.v1").exists()
    assert all(
        not name.startswith("run_ref_bundle_capsule")
        for name in result.artifact_paths
    )


def test_bundle_capsule_encoding_canonicalizes_catalog_order_without_global_reducer(
    tmp_path: Path,
) -> None:
    child = _compiled_bundle(tmp_path)
    sibling = build_frontend_bundle(
        FrontendBuildRequest(
            source_path=child.provenance.workflow_path,
            source_roots=(tmp_path,),
            entry_workflow="sibling",
            workspace_root=tmp_path,
            lowering_route=LoweringRoute.WCC_M4,
        )
    ).validated_bundle
    kwargs = dict(
        target_workflow_names=(sibling.surface.name, child.surface.name),
        closure=_closure(child.provenance.workflow_path),
        workflow_closure_paths={
            child.surface.name: child.provenance.workflow_path.name,
            sibling.surface.name: sibling.provenance.workflow_path.name,
        },
        compiler_runtime_identity_digest="sha256:" + "c" * 64,
        lowering_schema_version=2,
    )
    dispatch_before = dict(copyreg.dispatch_table)

    forward = bundle_transport.encode_bundle_capsule(
        {child.surface.name: child, sibling.surface.name: sibling},
        **kwargs,
    )
    reverse = bundle_transport.encode_bundle_capsule(
        {sibling.surface.name: sibling, child.surface.name: child},
        **kwargs,
    )

    assert forward == reverse
    assert copyreg.dispatch_table == dispatch_before


def test_bundle_capsule_encoding_canonicalizes_nested_mapping_order(
    tmp_path: Path,
) -> None:
    bundle = _compiled_bundle(tmp_path)
    forward = replace(
        bundle,
        surface=replace(
            bundle.surface,
            context=MappingProxyType({"alpha": 1, "beta": 2}),
        ),
    )
    reverse = replace(
        bundle,
        surface=replace(
            bundle.surface,
            context=MappingProxyType({"beta": 2, "alpha": 1}),
        ),
    )
    kwargs = dict(
        target_workflow_names=(bundle.surface.name,),
        closure=_closure(bundle.provenance.workflow_path),
        workflow_closure_paths={
            bundle.surface.name: bundle.provenance.workflow_path.name,
        },
        compiler_runtime_identity_digest="sha256:" + "c" * 64,
        lowering_schema_version=2,
    )

    first = bundle_transport.encode_bundle_capsule(
        {bundle.surface.name: forward},
        **kwargs,
    )
    second = bundle_transport.encode_bundle_capsule(
        {bundle.surface.name: reverse},
        **kwargs,
    )

    assert first == second


def test_run_ref_step_config_digest_binds_optional_capsule_authority(
    tmp_path: Path,
) -> None:
    bundle = _compiled_controller_bundle(tmp_path)
    [config] = [
        node.execution_config
        for node in bundle.ir.nodes.values()
        if isinstance(node.execution_config, RunRefStepConfig)
    ]
    assert config.capsule_binding is None
    unbound_digest = config.step_config_digest
    binding = RunRefBundleCapsuleBinding("sha256:" + "a" * 64)
    bound = replace(config, capsule_binding=binding)

    assert bound.run_ref is config.run_ref
    assert bound.step_config_digest != unbound_digest
    assert bound.step_config_digest == replace(
        config,
        capsule_binding=RunRefBundleCapsuleBinding("sha256:" + "a" * 64),
    ).step_config_digest

    payload = workflow_executable_ir_to_json(
        replace(
            bundle.ir,
            nodes=MappingProxyType(
                {
                    node_id: (
                        replace(node, execution_config=bound)
                        if node.execution_config is config
                        else node
                    )
                    for node_id, node in bundle.ir.nodes.items()
                }
            ),
        )
    )
    [node_payload] = [
        node
        for node in payload["nodes"].values()
        if node["kind"] == "run_ref"
    ]
    assert node_payload["execution_config"]["capsule_binding"] == binding.record


def test_bundle_capsule_encode_rejects_prebound_mode_one_config(
    tmp_path: Path,
) -> None:
    bundle = _compiled_controller_bundle(tmp_path)
    binding = RunRefBundleCapsuleBinding("sha256:" + "a" * 64)
    bound_nodes = MappingProxyType(
        {
            node_id: (
                replace(
                    node,
                    execution_config=replace(
                        node.execution_config,
                        capsule_binding=binding,
                    ),
                )
                if isinstance(node.execution_config, RunRefStepConfig)
                else node
            )
            for node_id, node in bundle.ir.nodes.items()
        }
    )
    bound = replace(bundle, ir=replace(bundle.ir, nodes=bound_nodes))

    with pytest.raises(
        ValueError,
        match="run_ref_bundle_prebound_config",
    ):
        bundle_transport.encode_bundle_capsule(
            {bound.surface.name: bound},
            target_workflow_names=(bound.surface.name,),
            closure=_closure(bound.provenance.workflow_path),
            workflow_closure_paths={
                bound.surface.name: bound.provenance.workflow_path.name,
            },
            compiler_runtime_identity_digest="sha256:" + "c" * 64,
            lowering_schema_version=2,
        )


def test_bundle_capsule_decode_injects_verified_binding_and_rechecks_digests(
    tmp_path: Path,
) -> None:
    bundle = _compiled_controller_bundle(tmp_path)
    [unbound] = [
        node.execution_config
        for node in bundle.ir.nodes.values()
        if isinstance(node.execution_config, RunRefStepConfig)
    ]
    encoded = bundle_transport.encode_bundle_capsule(
        {bundle.surface.name: bundle},
        target_workflow_names=(bundle.surface.name,),
        closure=_closure(bundle.provenance.workflow_path),
        workflow_closure_paths={
            bundle.surface.name: bundle.provenance.workflow_path.name,
        },
        compiler_runtime_identity_digest="sha256:" + "c" * 64,
        lowering_schema_version=2,
    )

    decoded = bundle_transport.decode_bundle_capsule(
        manifest_bytes=encoded.manifest_bytes,
        pickle_bytes=encoded.pickle_bytes,
        closure=encoded.closure,
        expected_capsule_digest=encoded.capsule_digest,
        expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
    )

    [bound] = [
        node.execution_config
        for node in decoded.bundles_by_name[bundle.surface.name].ir.nodes.values()
        if isinstance(node.execution_config, RunRefStepConfig)
    ]
    assert bound.capsule_binding == RunRefBundleCapsuleBinding(
        encoded.capsule_digest
    )
    assert bound.step_config_digest != unbound.step_config_digest


def test_bundle_capsule_decode_binds_mode_one_and_leaves_mode_two_unbound(
    tmp_path: Path,
) -> None:
    bundle = _compiled_mixed_controller_bundle(tmp_path)
    encoded = bundle_transport.encode_bundle_capsule(
        {bundle.surface.name: bundle},
        target_workflow_names=(bundle.surface.name,),
        closure=_closure(bundle.provenance.workflow_path),
        workflow_closure_paths={
            bundle.surface.name: bundle.provenance.workflow_path.name,
        },
        compiler_runtime_identity_digest="sha256:" + "c" * 64,
        lowering_schema_version=2,
    )

    decoded = bundle_transport.decode_bundle_capsule(
        manifest_bytes=encoded.manifest_bytes,
        pickle_bytes=encoded.pickle_bytes,
        closure=encoded.closure,
        expected_capsule_digest=encoded.capsule_digest,
        expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
    )

    configs = [
        node.execution_config
        for node in decoded.bundles_by_name[bundle.surface.name].ir.nodes.values()
        if isinstance(node.execution_config, RunRefStepConfig)
    ]
    assert len(configs) == 2
    by_mode = {config.run_ref.program.record["mode"]: config for config in configs}
    assert by_mode["bundle"].capsule_binding == RunRefBundleCapsuleBinding(
        encoded.capsule_digest
    )
    assert by_mode["path"].capsule_binding is None


def test_bundle_capsule_binding_rewrites_cyclic_catalog_without_losing_identity(
    tmp_path: Path,
) -> None:
    bundle = _compiled_controller_bundle(tmp_path)
    import_storage: dict[str, LoadedWorkflowBundle] = {}
    cyclic = replace(bundle, imports=MappingProxyType(import_storage))
    import_storage["self"] = cyclic
    binding = RunRefBundleCapsuleBinding("sha256:" + "a" * 64)

    rewritten = bundle_transport.bind_bundle_catalog_capsule(
        {cyclic.surface.name: cyclic},
        binding=binding,
    )

    rebound = rewritten[cyclic.surface.name]
    assert rebound.imports["self"] is rebound
    [config] = [
        node.execution_config
        for node in rebound.ir.nodes.values()
        if isinstance(node.execution_config, RunRefStepConfig)
    ]
    assert config.capsule_binding == binding


@pytest.mark.parametrize(
    "defect",
    ("digest", "oversize", "protocol"),
)
def test_bundle_capsule_rejects_envelope_defects_before_unpickle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
) -> None:
    encoded = _encoded_capsule(tmp_path)
    pickle_bytes = encoded.pickle_bytes
    manifest_bytes = encoded.manifest_bytes
    expected_capsule_digest = encoded.capsule_digest
    if defect == "digest":
        expected_capsule_digest = "sha256:" + "0" * 64
    elif defect == "oversize":
        monkeypatch.setattr(
            bundle_transport,
            "MAX_BUNDLE_PICKLE_BYTES",
            len(pickle_bytes) - 1,
        )
    else:
        pickle_bytes = b"\x80\x04" + pickle_bytes[2:]
        manifest = json.loads(manifest_bytes)
        manifest["encoding"] = "python-pickle-protocol-4.v1"
        manifest["pickle"]["protocol"] = 4
        manifest["pickle"]["size_bytes"] = len(pickle_bytes)
        manifest["pickle"]["sha256"] = (
            f"sha256:{hashlib.sha256(pickle_bytes).hexdigest()}"
        )
        manifest_bytes = canonical_json_bytes(manifest)
        expected_capsule_digest = _manifest_digest(manifest_bytes)

    monkeypatch.setattr(
        bundle_transport.pickle,
        "loads",
        lambda _payload: pytest.fail("unpickle ran before envelope validation"),
    )

    with pytest.raises(
        ValueError,
        match=(
            "run_ref_bundle_pickle_digest_mismatch"
            if defect == "digest"
            else "run_ref_bundle_pickle_oversize"
            if defect == "oversize"
            else "run_ref_bundle_encoding_invalid"
        ),
    ):
        bundle_transport.decode_bundle_capsule(
            manifest_bytes=manifest_bytes,
            pickle_bytes=pickle_bytes,
            closure=encoded.closure,
            expected_capsule_digest=expected_capsule_digest,
            expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
        )


def test_bundle_capsule_decode_rejects_schema_and_exact_type_drift(
    tmp_path: Path,
) -> None:
    encoded = _encoded_capsule(tmp_path)
    manifest = json.loads(encoded.manifest_bytes)
    manifest["schema_version"] = "run_ref_bundle_capsule.v2"
    manifest_bytes = canonical_json_bytes(manifest)
    invalid_values = (
        (
            manifest_bytes,
            encoded.pickle_bytes,
            "run_ref_bundle_manifest_invalid",
        ),
        (
            encoded.manifest_bytes,
            pickle.dumps({"not": "a catalog"}, protocol=5),
            "run_ref_bundle_catalog_invalid",
        ),
    )

    for invalid_manifest, invalid_pickle, diagnostic in invalid_values:
        if invalid_pickle is not encoded.pickle_bytes:
            manifest = json.loads(invalid_manifest)
            manifest["pickle"]["size_bytes"] = len(invalid_pickle)
            manifest["pickle"]["sha256"] = (
                f"sha256:{hashlib.sha256(invalid_pickle).hexdigest()}"
            )
            invalid_manifest = canonical_json_bytes(manifest)
        with pytest.raises(
            ValueError,
            match=diagnostic,
        ):
            bundle_transport.decode_bundle_capsule(
                manifest_bytes=invalid_manifest,
                pickle_bytes=invalid_pickle,
                closure=encoded.closure,
                expected_capsule_digest=_manifest_digest(invalid_manifest),
                expected_compiler_runtime_identity_digest=(
                    "sha256:" + "c" * 64
                ),
            )


@pytest.mark.parametrize(
    ("mutate", "diagnostic"),
    (
        (
            lambda manifest: manifest.__setitem__(
                "lowering_schema_version", 99
            ),
            "run_ref_bundle_lowering_schema_invalid",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "target_dsl_versions", ["2.23"]
            ),
            "run_ref_bundle_version_invalid",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "target_workflow_names", []
            ),
            "run_ref_bundle_manifest_invalid",
        ),
        (
            lambda manifest: manifest.__setitem__(
                "bundle_names", ["capsule_catalog::child", "extra"]
            ),
            "run_ref_bundle_manifest_invalid",
        ),
    ),
)
def test_bundle_capsule_rejects_version_and_manifest_catalog_skew_before_unpickle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutate,
    diagnostic: str,
) -> None:
    encoded = _encoded_capsule(tmp_path)
    manifest_bytes, capsule_digest = _rewrite_manifest(encoded, mutate)
    monkeypatch.setattr(
        bundle_transport.pickle,
        "loads",
        lambda _payload: pytest.fail("unpickle ran before manifest validation"),
    )

    with pytest.raises(ValueError, match=diagnostic):
        bundle_transport.decode_bundle_capsule(
            manifest_bytes=manifest_bytes,
            pickle_bytes=encoded.pickle_bytes,
            closure=encoded.closure,
            expected_capsule_digest=capsule_digest,
            expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
        )


def test_bundle_capsule_rejects_noncanonical_manifest_and_closure_before_unpickle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = _encoded_capsule(tmp_path)
    monkeypatch.setattr(
        bundle_transport.pickle,
        "loads",
        lambda _payload: pytest.fail("unpickle ran before envelope validation"),
    )

    noncanonical = encoded.manifest_bytes + b"\n"
    with pytest.raises(ValueError, match="run_ref_bundle_manifest_invalid"):
        bundle_transport.decode_bundle_capsule(
            manifest_bytes=noncanonical,
            pickle_bytes=encoded.pickle_bytes,
            closure=encoded.closure,
            expected_capsule_digest=_manifest_digest(noncanonical),
            expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
        )

    changed_closure = (
        bundle_transport.BundleCapsuleClosureBlob(
            path=encoded.closure[0].path,
            roles=encoded.closure[0].roles,
            payload=encoded.closure[0].payload + b"\n",
        ),
    )
    with pytest.raises(ValueError, match="run_ref_bundle_closure_mismatch"):
        bundle_transport.decode_bundle_capsule(
            manifest_bytes=encoded.manifest_bytes,
            pickle_bytes=encoded.pickle_bytes,
            closure=changed_closure,
            expected_capsule_digest=encoded.capsule_digest,
            expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
        )


def test_bundle_capsule_rejects_workflow_closure_association_before_unpickle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = _encoded_capsule(tmp_path)

    def mutate(manifest) -> None:
        name = manifest["target_workflow_names"][0]
        manifest["workflow_closure_paths"][name] = "missing.orc"

    manifest_bytes, capsule_digest = _rewrite_manifest(encoded, mutate)
    monkeypatch.setattr(
        bundle_transport.pickle,
        "loads",
        lambda _payload: pytest.fail(
            "unpickle ran before workflow closure validation"
        ),
    )

    with pytest.raises(
        ValueError,
        match="run_ref_bundle_workflow_closure_invalid",
    ):
        bundle_transport.decode_bundle_capsule(
            manifest_bytes=manifest_bytes,
            pickle_bytes=encoded.pickle_bytes,
            closure=encoded.closure,
            expected_capsule_digest=capsule_digest,
            expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
        )


@pytest.mark.parametrize(
    "workflow_paths",
    (
        {},
        {"capsule_catalog::child": "missing.orc"},
        {"wrong-name": "capsule_catalog.orc"},
    ),
)
def test_bundle_capsule_encode_requires_exact_workflow_closure_association(
    tmp_path: Path,
    workflow_paths: dict[str, str],
) -> None:
    bundle = _compiled_bundle(tmp_path)

    with pytest.raises(
        ValueError,
        match="run_ref_bundle_workflow_closure_invalid",
    ):
        bundle_transport.encode_bundle_capsule(
            {bundle.surface.name: bundle},
            target_workflow_names=(bundle.surface.name,),
            closure=_closure(bundle.provenance.workflow_path),
            workflow_closure_paths=workflow_paths,
            compiler_runtime_identity_digest="sha256:" + "c" * 64,
            lowering_schema_version=2,
        )

@pytest.mark.parametrize(
    "digest_name",
    ("signature", "core_ast", "executable_ir", "semantic_ir", "runtime_plan"),
)
def test_bundle_capsule_rejects_cross_view_digest_tamper(
    tmp_path: Path,
    digest_name: str,
) -> None:
    encoded = _encoded_capsule(tmp_path)

    def mutate(manifest) -> None:
        name = manifest["target_workflow_names"][0]
        manifest["bundle_digests"][name][digest_name] = "sha256:" + "0" * 64

    manifest_bytes, capsule_digest = _rewrite_manifest(encoded, mutate)
    with pytest.raises(ValueError, match="run_ref_bundle_digest_mismatch"):
        bundle_transport.decode_bundle_capsule(
            manifest_bytes=manifest_bytes,
            pickle_bytes=encoded.pickle_bytes,
            closure=encoded.closure,
            expected_capsule_digest=capsule_digest,
            expected_compiler_runtime_identity_digest="sha256:" + "c" * 64,
        )


def test_bundle_capsule_compiler_identity_is_an_external_decode_guard(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    encoded = _encoded_capsule(tmp_path)
    monkeypatch.setattr(
        bundle_transport.pickle,
        "loads",
        lambda _payload: pytest.fail("unpickle ran before compiler identity guard"),
    )

    with pytest.raises(
        ValueError,
        match="run_ref_bundle_compiler_identity_invalid",
    ):
        bundle_transport.decode_bundle_capsule(
            manifest_bytes=encoded.manifest_bytes,
            pickle_bytes=encoded.pickle_bytes,
            closure=encoded.closure,
            expected_capsule_digest=encoded.capsule_digest,
            expected_compiler_runtime_identity_digest="sha256:" + "d" * 64,
        )


@pytest.mark.parametrize(
    "bundles",
    (
        MappingProxyType({}),
        MappingProxyType({"wrong-name": object()}),
    ),
)
def test_bundle_capsule_encode_rejects_empty_or_non_bundle_catalog(
    bundles,
) -> None:
    with pytest.raises(
        (TypeError, ValueError),
        match="run_ref_bundle_catalog_invalid",
    ):
        bundle_transport.encode_bundle_capsule(
            bundles,
            target_workflow_names=("missing",),
            closure=(),
            workflow_closure_paths={},
            compiler_runtime_identity_digest="sha256:" + "c" * 64,
            lowering_schema_version=2,
        )
