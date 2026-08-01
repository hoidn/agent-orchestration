from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.workflow_lisp.reader import SourceReadTrace
from orchestrator.workflow.persisted_surface import (
    canonical_persisted_surface_bytes,
    decode_persisted_workflow_surface_graph,
    serialize_persisted_workflow_surface_graph,
)
from orchestrator.workflow.surface_ast import (
    SurfaceStep,
    SurfaceStepCommonConfig,
    SurfaceStepKind,
)
from tests.test_workflow_lisp_build_artifacts import (
    _build_module,
    _build_request,
    _persisted_fragment_contracts,
    _synthetic_surface_bundle,
)


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "valid" / "entry_publication_runtime.orc"
COMMAND_SOURCE = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "valid"
    / "native_bool_command_branch.orc"
)
IMPORTED_SOURCE_ROOT = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "workflow_lisp"
    / "modules"
    / "valid"
    / "imported_bundle_mix"
)
IMPORTED_ENTRY = IMPORTED_SOURCE_ROOT / "neurips" / "entry.orc"
CLI_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "workflow_lisp" / "cli"
STDLIB_ROOT = REPO_ROOT / "orchestrator" / "workflow_lisp" / "stdlib_modules"
LIBRARY_ONLY_SOURCE = STDLIB_ROOT / "std" / "context.orc"
PRODUCTION_REQUEST_CAPTURE_FIELDS = (
    "source_path",
    "workspace_root",
    "source_roots",
    "entry_workflow",
    "validation_profile",
    "boundary_admission_profile",
    "lint_profile",
    "lowering_route",
    "provider_externs",
    "prompt_externs",
    "command_boundaries",
    "imported_workflow_bundles",
)


def test_in_memory_q2_persisted_surface_payload_round_trips_v2(
    tmp_path: Path,
) -> None:
    template = _build_module().build_frontend_bundle(
        _build_request(tmp_path)
    ).validated_bundle
    _, contract, expected_outputs = _persisted_fragment_contracts()
    root = _synthetic_surface_bundle(
        template,
        "synthetic::in-memory-q2",
        steps=(
            SurfaceStep(
                name="Q2",
                step_id="q2",
                kind=SurfaceStepKind.PROVIDER,
                provider="test-provider",
                common=SurfaceStepCommonConfig(
                    expected_outputs=expected_outputs
                ),
                compiler_prompt_fragment_contract=contract,
                compiled_prompt_fragment_identity=(
                    contract.compiled_prompt_fragment_identity
                ),
            ),
        ),
    )
    root = replace(
        root,
        surface=replace(root.surface, version="2.21"),
    )

    payload = serialize_persisted_workflow_surface_graph(root)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    assert payload["schema_version"] == "persisted_workflow_surface_graph.v2"
    assert decoded.entry_node.steps[0].compiler_prompt_fragment_contract == (
        contract
    )


def test_in_memory_q3_persisted_surface_payload_round_trips_exact_pair(
    tmp_path: Path,
) -> None:
    from tests.test_workflow_lisp_prompt_identity_carriage import (
        _compile as _compile_prompt_identity,
        _provider_carriers,
    )

    result = _compile_prompt_identity(
        tmp_path,
        target_dsl="2.22",
        lowering_route="legacy",
        with_output=True,
    )
    _, surface, _, _, _, _, bundle = _provider_carriers(result)

    payload = serialize_persisted_workflow_surface_graph(bundle)
    decoded = decode_persisted_workflow_surface_graph(
        canonical_persisted_surface_bytes(payload)
    )
    decoded_step = decoded.entry_node.steps[0]

    assert payload["schema_version"] == (
        "persisted_workflow_surface_graph.v3"
    )
    assert decoded_step.prompt_attempt_identity_version == (
        surface.prompt_attempt_identity_version
    )
    assert decoded_step.compiler_prompt_attempt_binding_plan == (
        surface.compiler_prompt_attempt_binding_plan
    )
    assert decoded_step.compiler_prompt_fragment_contract == (
        surface.compiler_prompt_fragment_contract
    )


def _tree_snapshot(root: Path) -> tuple[tuple[str, str, bytes | str], ...]:
    entries: list[tuple[str, str, bytes | str]] = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            entries.append((relative, "symlink", path.readlink().as_posix()))
        elif path.is_dir():
            entries.append((relative, "directory", ""))
        else:
            entries.append((relative, "file", path.read_bytes()))
    return tuple(entries)


def _command_request(build, tmp_path: Path):
    command_boundaries_path = tmp_path / "commands.json"
    command_boundaries_path.write_text(
        json.dumps(
            {
                name: {
                    "kind": "external_tool",
                    "stable_command": ["python", f"scripts/{name}.py"],
                }
                for name in ("probe_ready", "record_blocked", "record_ready")
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return build.FrontendBuildRequest(
        source_path=COMMAND_SOURCE,
        source_roots=(COMMAND_SOURCE.parent,),
        entry_workflow="gate",
        command_boundaries_path=command_boundaries_path,
        workspace_root=tmp_path,
    )


def _imported_request(build, tmp_path: Path):
    return build.FrontendBuildRequest(
        source_path=IMPORTED_ENTRY,
        source_roots=(IMPORTED_SOURCE_ROOT,),
        entry_workflow="orchestrate",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        imported_workflow_bundles_path=CLI_FIXTURES
        / "imported_workflow_bundles.json",
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        workspace_root=tmp_path,
    )


def _write_imported_catalog_fixture(tmp_path: Path) -> tuple[Path, Path]:
    source_root = tmp_path / "src"
    module_root = source_root / "catalog"
    module_root.mkdir(parents=True)
    (module_root / "shared.orc").write_text(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule catalog/shared)
  (export Result shared)
  (defrecord Result
    (value String))
  (defworkflow shared
    ((value String))
    -> Result
    (record Result
      :value value)))
""",
        encoding="utf-8",
    )
    (module_root / "entry.orc").write_text(
        """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.18")
  (defmodule catalog/entry)
  (import catalog/shared :only (Result shared))
  (export selected sibling)
  (defworkflow selected
    ((value String))
    -> Result
    (call shared
      :value value))
  (defworkflow sibling
    ((value String))
    -> Result
    (call shared
      :value value)))
""",
        encoding="utf-8",
    )
    manifest_path = source_root / "imports.json"
    manifest_path.write_text(
        json.dumps(
            {
                "selected": {
                    "kind": "compiled",
                    "path": "catalog/entry.orc",
                    "entry_workflow": "selected",
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return source_root, manifest_path


def _assert_exact_production_request_capture(
    capture: object,
    *,
    request: object,
    configuration: object,
    validation_profile: object,
    boundary_admission_profile: object,
) -> None:
    assert tuple(field.name for field in fields(capture)) == (
        PRODUCTION_REQUEST_CAPTURE_FIELDS
    )
    assert tuple(
        getattr(capture, field_name)
        for field_name in PRODUCTION_REQUEST_CAPTURE_FIELDS
    ) == (
        request.source_path.resolve(),
        request.workspace_root.resolve(),
        tuple(path.resolve() for path in request.source_roots),
        request.entry_workflow,
        validation_profile,
        boundary_admission_profile,
        request.lint_profile,
        configuration.lowering_route,
        configuration.provider_externs,
        configuration.prompt_externs,
        configuration.command_boundaries,
        {
            binding.canonical_key: binding.bundle
            for binding in configuration.imported_workflow_bundles
        },
    )
    with pytest.raises(FrozenInstanceError):
        capture.entry_workflow = "mutated"
    with pytest.raises(TypeError):
        capture.provider_externs["unexpected"] = "mutated"
    with pytest.raises(TypeError):
        capture.prompt_externs["unexpected"] = {"mutated": True}
    with pytest.raises(TypeError):
        capture.command_boundaries["unexpected"] = object()
    with pytest.raises(TypeError):
        capture.imported_workflow_bundles["unexpected"] = object()


def test_in_memory_build_public_signature_exposes_only_source_trace() -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")

    signature = inspect.signature(build.build_frontend_bundle_in_memory)

    assert tuple(signature.parameters) == ("request", "source_read_trace")
    assert signature.parameters["request"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    source_trace = signature.parameters["source_read_trace"]
    assert source_trace.kind is inspect.Parameter.KEYWORD_ONLY
    assert source_trace.default is None
    annotations = inspect.get_annotations(
        build.build_frontend_bundle_in_memory,
        eval_str=True,
    )
    assert annotations == {
        "request": build.FrontendBuildRequest,
        "source_read_trace": SourceReadTrace | None,
        "return": build.FrontendInMemoryBuildResult,
    }


def test_production_request_capture_is_exact_ordered_and_immutable_after_loaders(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    request = _imported_request(build, tmp_path)
    configuration = build.load_frontend_initialization_configuration(
        workspace_root=request.workspace_root,
        source_roots=request.source_roots,
        provider_externs_path=request.provider_externs_path,
        prompt_externs_path=request.prompt_externs_path,
        command_boundaries_path=request.command_boundaries_path,
        imported_workflow_bundles_path=request.imported_workflow_bundles_path,
        lowering_route=request.lowering_route,
    )

    result = build.build_frontend_bundle_in_memory(request)

    _assert_exact_production_request_capture(
        result.compile_request_capture,
        request=request,
        configuration=configuration,
        validation_profile=compiler.Stage3ValidationProfile.SHARED_CALLABLE,
        boundary_admission_profile=(
            compiler.WorkflowBoundaryAdmissionProfile.SHARED_CALLABLE
        ),
    )


def test_same_production_request_capture_is_retained_on_success_and_language_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    request = build.FrontendBuildRequest(
        source_path=SOURCE,
        source_roots=(SOURCE.parent,),
        entry_workflow="entry-publication-runtime",
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        command_boundaries_path=CLI_FIXTURES / "commands.json",
        workspace_root=tmp_path,
    )
    configuration = build.load_frontend_initialization_configuration(
        workspace_root=request.workspace_root,
        source_roots=request.source_roots,
        provider_externs_path=request.provider_externs_path,
        prompt_externs_path=request.prompt_externs_path,
        command_boundaries_path=request.command_boundaries_path,
        imported_workflow_bundles_path=None,
        lowering_route=request.lowering_route,
    )
    success = build.build_frontend_bundle_in_memory(request)
    expected_capture = success.compile_request_capture
    expected_error = build.LispFrontendCompileError(())

    def fail_at_compile_seam(
        compile_request_capture: object,
        *,
        source_read_trace: SourceReadTrace,
    ) -> object:
        assert compile_request_capture == expected_capture
        assert (
            compile_request_capture.provider_externs
            == configuration.provider_externs
        )
        assert (
            compile_request_capture.prompt_externs
            == configuration.prompt_externs
        )
        assert compile_request_capture.imported_workflow_bundles == {}
        assert (
            compile_request_capture.command_boundaries
            == configuration.command_boundaries
        )
        assert isinstance(source_read_trace, SourceReadTrace)
        raise expected_error

    monkeypatch.setattr(build, "_compile_entry", fail_at_compile_seam)

    with pytest.raises(build.LispFrontendCompileError) as caught:
        build.build_frontend_bundle_in_memory(request)

    assert caught.value is expected_error
    assert caught.value.compile_request_capture == expected_capture
    _assert_exact_production_request_capture(
        caught.value.compile_request_capture,
        request=request,
        configuration=configuration,
        validation_profile=compiler.Stage3ValidationProfile.SHARED_CALLABLE,
        boundary_admission_profile=(
            compiler.WorkflowBoundaryAdmissionProfile.SHARED_CALLABLE
        ),
    )


def test_read_only_build_matches_persistent_prefix_without_mutating_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    in_memory_builder = getattr(build, "build_frontend_bundle_in_memory")
    result_type = getattr(build, "FrontendInMemoryBuildResult")
    request = build.FrontendBuildRequest(
        source_path=SOURCE,
        source_roots=(SOURCE.parent,),
        entry_workflow="entry-publication-runtime",
        workspace_root=tmp_path,
    )
    before = _tree_snapshot(tmp_path)
    source_reads: list[Path] = []
    read_bytes = Path.read_bytes

    def traced_read_bytes(path: Path) -> bytes:
        if path.suffix == ".orc":
            source_reads.append(path.resolve())
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", traced_read_bytes)

    in_memory = in_memory_builder(request)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    assert isinstance(in_memory, result_type)
    with pytest.raises(FrozenInstanceError):
        in_memory.fingerprint = "mutated"
    assert in_memory.source_read_trace.records
    assert tuple(record.canonical_path for record in in_memory.source_read_trace.records) == tuple(
        source_reads
    )
    assert in_memory.configuration_trace.records == ()
    assert in_memory.configuration_trace.revision_vector == ()
    assert _tree_snapshot(tmp_path) == before
    assert not (tmp_path / ".orchestrate").exists()

    supplied_trace = SourceReadTrace()
    traced = in_memory_builder(request, source_read_trace=supplied_trace)
    assert traced.source_read_trace is not supplied_trace
    assert traced.source_read_trace.records == supplied_trace.records
    assert traced.source_read_trace.revision_vector == supplied_trace.revision_vector
    immutable_records = traced.source_read_trace.records
    with pytest.raises(FrozenInstanceError):
        traced.source_read_trace.records = ()
    supplied_trace._record(
        canonical_path=tmp_path / "later.orc",
        revision="missing",
    )
    assert traced.source_read_trace.records == immutable_records
    assert supplied_trace.records
    assert _tree_snapshot(tmp_path) == before

    persistent = build.build_frontend_bundle(request)

    assert persistent.entry_selection == in_memory.entry_selection
    assert persistent.validated_bundle == in_memory.validated_bundle
    assert persistent.imported_workflow_bundles == in_memory.imported_workflow_bundles == ()
    assert persistent.compile_result == in_memory.compile_result
    assert persistent.manifest.fingerprint == in_memory.fingerprint
    assert persistent.build_root == in_memory.build_root
    assert persistent.manifest_path == in_memory.manifest_path
    assert in_memory.manifest_path == in_memory.build_root / "manifest.json"
    assert json.loads(persistent.artifact_paths["source_map"].read_text()) == in_memory.source_map_payload
    assert (
        json.loads(persistent.artifact_paths["workflow_boundary_projection"].read_text())
        == in_memory.workflow_boundary_projection_payload
    )
    assert (
        json.loads(persistent.artifact_paths["persisted_workflow_surface"].read_text())
        == in_memory.persisted_surface_payload
    )
    assert json.loads(persistent.artifact_paths["semantic_ir"].read_text()) == in_memory.semantic_ir_payload
    assert (
        json.loads(persistent.artifact_paths["core_workflow_ast"].read_text())
        == in_memory.core_workflow_ast_payload
    )
    assert (
        json.loads(persistent.artifact_paths["executable_ir"].read_text())
        == in_memory.executable_ir_payload
    )
    assert (
        json.loads(persistent.artifact_paths["runtime_plan"].read_text())
        == in_memory.runtime_plan_payload
    )
    assert (tmp_path / ".orchestrate" / "build").is_dir()


def test_read_only_build_retains_immutable_exact_source_bytes_after_mutation(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    source_path = tmp_path / "entry_publication_runtime.orc"
    original = SOURCE.read_bytes().replace(b"\n", b"\r\n")
    source_path.write_bytes(original)
    request = build.FrontendBuildRequest(
        source_path=source_path,
        source_roots=(tmp_path,),
        entry_workflow="entry-publication-runtime",
        workspace_root=tmp_path,
    )

    result = build.build_frontend_bundle_in_memory(request)
    source_path.write_bytes(b"changed after build\n")

    assert result.source_read_trace.raw_bytes_by_path[source_path.resolve()] == original
    with pytest.raises(TypeError):
        result.source_read_trace.raw_bytes_by_path[source_path.resolve()] = b"mutated"  # type: ignore[index]


@pytest.mark.parametrize("tamper", ("missing", "non_sha", "mismatch"))
def test_read_only_build_rejects_invalid_source_revision_vectors(
    tmp_path: Path,
    tamper: str,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    in_memory_builder = getattr(build, "build_frontend_bundle_in_memory")

    class TamperedSourceReadTrace(SourceReadTrace):
        @property
        def revision_vector(self) -> tuple[tuple[Path, str], ...]:
            actual = super().revision_vector
            if tamper == "missing":
                return ()
            path, revision = actual[0]
            if tamper == "non_sha":
                replacement = "missing"
            else:
                replacement = "sha256:" + ("0" * 64)
                assert replacement != revision
            return ((path, replacement), *actual[1:])

    request = build.FrontendBuildRequest(
        source_path=SOURCE,
        source_roots=(SOURCE.parent,),
        entry_workflow="entry-publication-runtime",
        workspace_root=tmp_path,
    )

    with pytest.raises(ValueError, match="source read trace"):
        in_memory_builder(request, source_read_trace=TamperedSourceReadTrace())

    assert not (tmp_path / ".orchestrate").exists()


def test_in_memory_build_uses_authoritative_source_map_when_path_conflicts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    request = _command_request(build, tmp_path)
    first = build.build_frontend_bundle_in_memory(request)
    source_map_path = first.build_root / "source_map.json"
    source_map_path.parent.mkdir(parents=True)
    source_map_path.write_text(
        json.dumps(
            {
                "workflows": {
                    first.entry_selection.canonical_name: {
                        "command_boundaries": [
                            {
                                "step_id": "probe_ready",
                                "boundary_kind": "certified_adapter",
                                "adapter_name": "conflicting-adapter",
                            }
                        ]
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    before = _tree_snapshot(tmp_path)
    read_text = Path.read_text

    def reject_conflicting_source_map_read(path: Path, *args, **kwargs) -> str:
        if path == source_map_path:
            raise AssertionError("supplied source-map payload must be authoritative")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_conflicting_source_map_read)

    result = build.build_frontend_bundle_in_memory(request)

    assert _tree_snapshot(tmp_path) == before
    assert {
        boundary["boundary_name"]
        for boundary in result.runtime_plan_payload["observability"]["command_boundaries"]
    } == {"probe_ready"}
    semantic_boundary_names = {
        boundary["boundary_name"]
        for boundary in result.semantic_ir_payload["command_boundaries"].values()
    }
    assert "probe_ready" in semantic_boundary_names
    assert "conflicting-adapter" not in semantic_boundary_names
    assert any(
        bridge["bridge_kind"] == "validation_subject"
        for bridge in result.semantic_ir_payload["source_map"].values()
    )


def test_source_map_empty_payload_is_authoritative_and_none_is_legacy_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    core_ast = importlib.import_module("orchestrator.workflow.core_ast")
    lowering = importlib.import_module("orchestrator.workflow.lowering")
    semantic_ir = importlib.import_module("orchestrator.workflow.semantic_ir")
    request = _command_request(build, tmp_path)
    compiled = build.build_frontend_bundle_in_memory(request)
    bundle = compiled.validated_bundle
    source_map_path = compiled.build_root / "source_map.json"
    source_map_path.parent.mkdir(parents=True)
    conflicting_payload = json.loads(json.dumps(compiled.source_map_payload))
    workflow_payload = conflicting_payload["workflows"][
        compiled.entry_selection.canonical_name
    ]
    for boundary in workflow_payload["command_boundaries"]:
        boundary["boundary_kind"] = "certified_adapter"
        boundary["adapter_name"] = "conflicting-adapter"
    source_map_path.write_text(
        json.dumps(conflicting_payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    read_text = Path.read_text

    def reject_source_map_read(path: Path, *args, **kwargs) -> str:
        if path == source_map_path:
            raise AssertionError("an explicit empty source-map payload may not read provenance")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", reject_source_map_read)

    empty_core = core_ast.build_core_workflow_ast(
        bundle.surface,
        bundle.imports,
        bundle.provenance,
        source_map_payload={},
    )
    empty_bundle = lowering.build_loaded_workflow_bundle(
        bundle.surface,
        imports=bundle.imports,
        source_map_payload={},
    )
    empty_semantic_ir = semantic_ir.derive_workflow_semantic_ir(
        core_workflow_ast=empty_core,
        surface=empty_bundle.surface,
        ir=empty_bundle.ir,
        projection=empty_bundle.projection,
        runtime_plan=empty_bundle.runtime_plan,
        imports=empty_bundle.imports,
        provenance=empty_bundle.provenance,
        source_map_payload={},
    )

    assert "conflicting-adapter" not in json.dumps(
        core_ast.workflow_core_ast_to_json(empty_core)
    )
    assert "conflicting-adapter" not in json.dumps(
        build._public_runtime_plan_payload(empty_bundle.runtime_plan)
    )
    assert "conflicting-adapter" not in json.dumps(
        semantic_ir.workflow_semantic_ir_to_json(empty_semantic_ir)
    )

    monkeypatch.setattr(Path, "read_text", read_text)

    fallback_core = core_ast.build_core_workflow_ast(
        bundle.surface,
        bundle.imports,
        bundle.provenance,
        source_map_payload=None,
    )
    fallback_bundle = lowering.build_loaded_workflow_bundle(
        bundle.surface,
        imports=bundle.imports,
        source_map_payload=None,
    )
    fallback_semantic_ir = semantic_ir.derive_workflow_semantic_ir(
        core_workflow_ast=fallback_core,
        surface=fallback_bundle.surface,
        ir=fallback_bundle.ir,
        projection=fallback_bundle.projection,
        runtime_plan=fallback_bundle.runtime_plan,
        imports=fallback_bundle.imports,
        provenance=fallback_bundle.provenance,
        source_map_payload=None,
    )

    assert "conflicting-adapter" in json.dumps(
        core_ast.workflow_core_ast_to_json(fallback_core)
    )
    assert "conflicting-adapter" in json.dumps(
        build._public_runtime_plan_payload(fallback_bundle.runtime_plan)
    )
    assert "conflicting-adapter" in json.dumps(
        semantic_ir.workflow_semantic_ir_to_json(fallback_semantic_ir)
    )


def test_recursive_imported_builds_share_trace_and_never_emit_child_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    request = _imported_request(build, tmp_path)
    before = _tree_snapshot(tmp_path)
    source_reads: list[Path] = []
    read_bytes = Path.read_bytes

    def traced_read_bytes(path: Path) -> bytes:
        if path.suffix == ".orc":
            source_reads.append(path.resolve())
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", traced_read_bytes)

    in_memory = build.build_frontend_bundle_in_memory(request)
    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    assert _tree_snapshot(tmp_path) == before
    assert not (tmp_path / ".orchestrate").exists()
    assert tuple(
        record.canonical_path for record in in_memory.source_read_trace.records
    ) == tuple(source_reads)
    assert len(in_memory.imported_workflow_bundles) == 1
    imported = in_memory.imported_workflow_bundles[0]
    assert imported.workflow_name == "imported_selector::selector-run"
    assert imported.bundle_fingerprint
    assert imported.bundle == in_memory.validated_bundle.imports["selector-run"]

    persistent = build.build_frontend_bundle(request)

    assert persistent.imported_workflow_bundles == in_memory.imported_workflow_bundles
    emitted_build_roots = tuple(
        path
        for path in (tmp_path / ".orchestrate" / "build").iterdir()
        if path.is_dir()
    )
    assert emitted_build_roots == (persistent.build_root,)
    assert imported.bundle_fingerprint != persistent.manifest.fingerprint


def test_imported_binding_retains_frozen_complete_canonical_bundle_catalog(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    source_root, manifest_path = _write_imported_catalog_fixture(tmp_path)
    before = _tree_snapshot(tmp_path)

    configuration = build.load_frontend_initialization_configuration(
        workspace_root=tmp_path,
        source_roots=(source_root,),
        imported_workflow_bundles_path=manifest_path,
    )

    assert _tree_snapshot(tmp_path) == before
    assert not (tmp_path / ".orchestrate").exists()
    binding = configuration.imported_workflow_bundles[0]
    catalog = binding.bundle_catalog
    assert tuple(catalog) == (
        "catalog/entry::selected",
        "catalog/entry::sibling",
        "catalog/shared::shared",
    )
    assert binding.workflow_name == "catalog/entry::selected"
    assert binding.bundle is catalog[binding.workflow_name]
    shared = catalog["catalog/shared::shared"]
    for catalog_bundle in catalog.values():
        for imported_bundle in catalog_bundle.imports.values():
            assert imported_bundle is catalog[imported_bundle.surface.name]
    for workflow_name in (
        "catalog/entry::selected",
        "catalog/entry::sibling",
    ):
        imported = tuple(catalog[workflow_name].imports.values())
        assert imported == (shared,)
        with pytest.raises(TypeError):
            catalog[workflow_name].imports["other"] = shared  # type: ignore[index]
    with pytest.raises(TypeError):
        catalog["other"] = shared  # type: ignore[index]

    coverage = binding.bundle.provenance.frontend_source_map_coverage
    assert coverage is binding.bundle.surface.provenance.frontend_source_map_coverage
    assert coverage is binding.bundle.ir.provenance.frontend_source_map_coverage
    with pytest.raises(TypeError):
        coverage["frontend_ast"] = "mutated"


def test_imported_catalog_flattening_rejects_canonical_name_conflicts() -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    compile_result = SimpleNamespace(
        compiled_results_by_name={
            "first": SimpleNamespace(validated_bundles={"duplicate": object()}),
            "second": SimpleNamespace(validated_bundles={"duplicate": object()}),
        }
    )

    with pytest.raises(RuntimeError, match="canonical-name conflict.*duplicate"):
        build._flatten_compiled_bundle_catalog(compile_result)


def test_library_only_in_memory_result_is_explicit_and_non_runnable(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    request = build.FrontendBuildRequest(
        source_path=LIBRARY_ONLY_SOURCE,
        source_roots=(STDLIB_ROOT,),
        entry_workflow=None,
        workspace_root=tmp_path,
    )
    before = _tree_snapshot(tmp_path)

    result = build.build_frontend_bundle_in_memory(request)

    assert result.compile_result.graph.entry_module_name == "std/context"
    assert result.compile_result.graph.export_surfaces_by_name["std/context"].types_by_name
    assert result.entry_selection is None
    assert result.selected_workflow_name is None
    assert result.validated_bundle is None
    assert result.fingerprint is None
    assert result.build_root is None
    assert result.manifest_path is None
    assert result.source_map_payload is None
    assert result.workflow_boundary_projection_payload is None
    assert result.persisted_surface_payload is None
    assert result.semantic_ir_payload is None
    assert result.core_workflow_ast_payload is None
    assert result.executable_ir_payload is None
    assert result.runtime_plan_payload is None
    assert result.source_read_trace.records
    assert _tree_snapshot(tmp_path) == before

    with pytest.raises(build.LispFrontendCompileError) as persistent_error:
        build.build_frontend_bundle(request)
    assert persistent_error.value.diagnostics[0].code == "entry_workflow_required"
    assert _tree_snapshot(tmp_path) == before

    manifest_path = tmp_path / "library-only-imports.json"
    manifest_path.write_text(
        json.dumps(
            {
                "context": {
                    "kind": "compiled",
                    "path": str(LIBRARY_ONLY_SOURCE),
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before_import = _tree_snapshot(tmp_path)

    with pytest.raises(build.LispFrontendCompileError) as imported_error:
        build.load_imported_workflow_bundle_manifest(
            manifest_path,
            workspace_root=tmp_path,
            source_roots=(STDLIB_ROOT,),
        )

    assert imported_error.value.diagnostics[0].code == "entry_workflow_required"
    assert _tree_snapshot(tmp_path) == before_import


def test_recursive_library_only_import_error_retains_child_capture_without_writes(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    child_source = tmp_path / "child.orc"
    child_source.write_text(
        "\n".join(
            (
                "(workflow-lisp",
                '  (:language "0.1")',
                '  (:target-dsl "2.14")',
                "  (defmodule child))",
                "",
            )
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "imports.json"
    manifest_path.write_text(
        json.dumps(
            {
                "child": {
                    "kind": "compiled",
                    "path": child_source.name,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )
    child_request = build.FrontendBuildRequest(
        source_path=child_source,
        source_roots=(tmp_path,),
        entry_workflow=None,
        workspace_root=tmp_path,
    )

    with pytest.raises(build.LispFrontendCompileError) as direct_error:
        build.build_frontend_bundle(child_request)
    expected_diagnostics = direct_error.value.diagnostics
    before_recursive_attempt = _tree_snapshot(tmp_path)

    with pytest.raises(build.LispFrontendCompileError) as recursive_error:
        build.load_imported_workflow_bundle_manifest(
            manifest_path,
            workspace_root=tmp_path,
            source_roots=(tmp_path,),
        )

    error = recursive_error.value
    assert error.diagnostics == expected_diagnostics
    assert tuple(diagnostic.code for diagnostic in error.diagnostics) == (
        "entry_workflow_required",
    )
    assert error.compile_request_capture.source_path == child_source.resolve()
    assert error.compile_request_capture.entry_workflow is None
    assert _tree_snapshot(tmp_path) == before_recursive_attempt
    assert not (tmp_path / ".orchestrate").exists()


def test_configuration_trace_hashes_the_one_json_read_and_returns_a_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    request = _command_request(build, tmp_path)
    command_path = request.command_boundaries_path.resolve()
    command_bytes = command_path.read_bytes()
    reads: list[Path] = []
    read_bytes = Path.read_bytes

    def traced_read_bytes(path: Path) -> bytes:
        if path.resolve() == command_path:
            reads.append(path.resolve())
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", traced_read_bytes)

    result = build.build_frontend_bundle_in_memory(request)

    assert reads == [command_path]
    assert tuple(
        record.canonical_path for record in result.configuration_trace.records
    ) == (command_path,)
    assert tuple(record.ordinal for record in result.configuration_trace.records) == (0,)
    assert result.configuration_trace.revision_vector == (
        (
            command_path,
            f"sha256:{hashlib.sha256(command_bytes).hexdigest()}",
        ),
    )
    immutable_records = result.configuration_trace.records
    with pytest.raises(FrozenInstanceError):
        result.configuration_trace.records = ()
    with pytest.raises(FrozenInstanceError):
        result.configuration_trace.records[0].revision = "missing"
    assert result.configuration_trace.records == immutable_records


def test_recursive_build_configuration_trace_matches_every_physical_json_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    request = _imported_request(build, tmp_path)
    configured_paths = {
        request.provider_externs_path.resolve(),
        request.prompt_externs_path.resolve(),
        request.imported_workflow_bundles_path.resolve(),
        request.command_boundaries_path.resolve(),
    }
    reads: list[Path] = []
    read_bytes = Path.read_bytes

    def traced_read_bytes(path: Path) -> bytes:
        canonical_path = path.resolve()
        if canonical_path in configured_paths:
            reads.append(canonical_path)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", traced_read_bytes)

    result = build.build_frontend_bundle_in_memory(request)

    assert tuple(
        record.canonical_path for record in result.configuration_trace.records
    ) == tuple(reads)
    assert {path for path, _ in result.configuration_trace.revision_vector} == (
        configured_paths
    )
    assert reads == [
        request.provider_externs_path.resolve(),
        request.prompt_externs_path.resolve(),
        request.command_boundaries_path.resolve(),
        request.imported_workflow_bundles_path.resolve(),
        request.provider_externs_path.resolve(),
        request.prompt_externs_path.resolve(),
        request.command_boundaries_path.resolve(),
    ]
    assert not (tmp_path / ".orchestrate").exists()


def test_configuration_trace_records_missing_unreadable_and_strict_decode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest_io = importlib.import_module(
        "orchestrator.workflow_lisp.build_manifest_io"
    )
    trace = manifest_io.ConfigurationReadTrace()
    missing = tmp_path / "missing.json"

    with pytest.raises(manifest_io.LispFrontendCompileError):
        manifest_io._load_json_file(
            missing,
            label="missing manifest",
            configuration_read_trace=trace,
        )

    unreadable = tmp_path / "unreadable.json"
    unreadable.write_text("{}\n", encoding="utf-8")
    invalid_utf8 = tmp_path / "invalid-utf8.json"
    invalid_utf8.write_bytes(b'{"value":"\xff"}')
    read_bytes = Path.read_bytes

    def reject_unreadable(path: Path) -> bytes:
        if path == unreadable:
            raise PermissionError("unreadable")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_unreadable)

    with pytest.raises(PermissionError, match="unreadable"):
        manifest_io._load_json_file(
            unreadable,
            label="unreadable manifest",
            configuration_read_trace=trace,
        )
    with pytest.raises(UnicodeDecodeError):
        manifest_io._load_json_file(
            invalid_utf8,
            label="invalid UTF-8 manifest",
            configuration_read_trace=trace,
        )

    assert tuple(record.revision for record in trace.records) == (
        "missing",
        "unreadable",
        f"sha256:{hashlib.sha256(invalid_utf8.read_bytes()).hexdigest()}",
    )


@pytest.mark.parametrize("newline", ("\n", "\r\n", "\r"))
def test_configuration_loader_preserves_legacy_newline_diagnostics_and_raw_revision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    newline: str,
) -> None:
    manifest_io = importlib.import_module(
        "orchestrator.workflow_lisp.build_manifest_io"
    )
    lines = ("{", '  "valid": true,', "  invalid", "}")
    raw_variants = tuple(
        separator.join(lines).encode("utf-8")
        for separator in ("\n", "\r\n", "\r")
    )
    assert len({hashlib.sha256(raw).hexdigest() for raw in raw_variants}) == 3
    raw_bytes = newline.join(lines).encode("utf-8")
    normalized_text = (
        raw_bytes.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")
    )
    with pytest.raises(json.JSONDecodeError) as legacy_error:
        json.loads(normalized_text)

    manifest_path = tmp_path / "invalid.json"
    manifest_path.write_bytes(raw_bytes)
    canonical_path = manifest_path.resolve()
    reads: list[Path] = []
    read_bytes = Path.read_bytes

    def traced_read_bytes(path: Path) -> bytes:
        reads.append(path.resolve())
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", traced_read_bytes)
    trace = manifest_io.ConfigurationReadTrace()

    with pytest.raises(manifest_io.LispFrontendCompileError) as error:
        manifest_io._load_json_file(
            manifest_path,
            label="invalid manifest",
            configuration_read_trace=trace,
        )

    diagnostic = error.value.diagnostics[0]
    expected = legacy_error.value
    assert reads == [canonical_path]
    assert diagnostic.code == "workflow_lisp_manifest_invalid_json"
    assert (
        diagnostic.span.start.line,
        diagnostic.span.start.column,
        diagnostic.span.start.offset,
        diagnostic.notes,
    ) == (expected.lineno, expected.colno, expected.pos, (expected.msg,))
    assert trace.records[0].revision == (
        f"sha256:{hashlib.sha256(raw_bytes).hexdigest()}"
    )


def test_recursive_configuration_revision_mismatch_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    request = _imported_request(build, tmp_path)
    provider_path = request.provider_externs_path.resolve()
    provider_bytes = provider_path.read_bytes()
    provider_reads = 0
    read_bytes = Path.read_bytes

    def changing_read_bytes(path: Path) -> bytes:
        nonlocal provider_reads
        if path.resolve() == provider_path:
            provider_reads += 1
            if provider_reads > 1:
                return provider_bytes + b"\n"
            return provider_bytes
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", changing_read_bytes)

    with pytest.raises(
        RuntimeError,
        match="changed during one configuration read trace",
    ):
        build.build_frontend_bundle_in_memory(request)

    assert provider_reads == 2
    assert not (tmp_path / ".orchestrate").exists()


def test_initialization_configuration_without_optional_paths_is_frozen_and_read_free(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    first_root = (tmp_path / "src").resolve()
    second_root = (tmp_path / "lib").resolve()
    workspace_root = tmp_path.resolve()
    before = _tree_snapshot(tmp_path)

    configuration = build.load_frontend_initialization_configuration(
        workspace_root=workspace_root,
        source_roots=(first_root, first_root, second_root),
    )

    assert isinstance(configuration, build.FrontendInitializationConfiguration)
    assert configuration.workspace_root == workspace_root
    assert configuration.source_roots == (first_root, first_root, second_root)
    assert configuration.provider_externs_path is None
    assert configuration.prompt_externs_path is None
    assert configuration.command_boundaries_path is None
    assert configuration.imported_workflow_bundles_path is None
    assert configuration.lowering_route is build.LoweringRoute.WCC_M4
    assert configuration.provider_externs == {}
    assert configuration.prompt_externs == {}
    assert configuration.command_boundary_manifest == {}
    assert configuration.command_boundaries == {}
    assert configuration.imported_workflow_bundles == ()
    assert configuration.source_read_trace.records == ()
    assert configuration.source_read_trace.revision_vector == ()
    assert configuration.source_read_trace.raw_bytes_by_path == {}
    assert configuration.configuration_trace.records == ()
    assert configuration.configuration_trace.revision_vector == ()
    assert _tree_snapshot(tmp_path) == before

    with pytest.raises(FrozenInstanceError):
        configuration.workspace_root = tmp_path / "other"  # type: ignore[misc]
    with pytest.raises(TypeError):
        configuration.provider_externs["providers.execute"] = "other"  # type: ignore[index]

    signature = inspect.signature(build.load_frontend_initialization_configuration)
    assert "source_path" not in signature.parameters
    assert tuple(signature.parameters) == (
        "workspace_root",
        "source_roots",
        "provider_externs_path",
        "prompt_externs_path",
        "command_boundaries_path",
        "imported_workflow_bundles_path",
        "lowering_route",
    )


def test_initialization_configuration_uses_production_loaders_and_shared_recursive_traces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    provider_path = (CLI_FIXTURES / "providers.json").resolve()
    prompt_path = (CLI_FIXTURES / "prompts.json").resolve()
    command_path = (CLI_FIXTURES / "commands.json").resolve()
    imported_manifest_path = (
        CLI_FIXTURES / "imported_workflow_bundles.json"
    ).resolve()
    imported_source_path = (CLI_FIXTURES / "imported_selector.orc").resolve()
    configured_paths = {
        provider_path,
        prompt_path,
        command_path,
        imported_manifest_path,
    }
    configuration_reads: list[Path] = []
    source_reads: list[Path] = []
    read_bytes = Path.read_bytes

    def traced_read_bytes(path: Path) -> bytes:
        canonical_path = path.resolve()
        if canonical_path in configured_paths:
            configuration_reads.append(canonical_path)
        if canonical_path.suffix == ".orc":
            source_reads.append(canonical_path)
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", traced_read_bytes)
    before = _tree_snapshot(tmp_path)

    configuration = build.load_frontend_initialization_configuration(
        workspace_root=tmp_path.resolve(),
        source_roots=(CLI_FIXTURES.resolve(),),
        provider_externs_path=provider_path,
        prompt_externs_path=prompt_path,
        command_boundaries_path=command_path,
        imported_workflow_bundles_path=imported_manifest_path,
    )

    assert configuration.provider_externs == {
        "providers.execute": "test-provider"
    }
    assert configuration.prompt_externs == {
        "prompts.implementation.execute": (
            "tests/fixtures/workflow_lisp/valid/prompts/implementation/execute.md"
        )
    }
    assert configuration.command_boundary_manifest == {
        "run_checks": {
            "kind": "external_tool",
            "stable_command": ("python", "scripts/run_checks.py"),
        }
    }
    assert tuple(configuration.command_boundaries) == ("run_checks",)
    assert configuration.command_boundaries["run_checks"].stable_command == (
        "python",
        "scripts/run_checks.py",
    )
    assert len(configuration.imported_workflow_bundles) == 1
    imported = configuration.imported_workflow_bundles[0]
    assert imported.canonical_key == "selector-run"
    assert imported.resolved_bundle_path == imported_source_path
    assert imported.load_status == "compiled"
    assert tuple(
        record.canonical_path
        for record in configuration.configuration_trace.records
    ) == tuple(configuration_reads)
    assert configuration_reads == [
        provider_path,
        prompt_path,
        command_path,
        imported_manifest_path,
        provider_path,
        prompt_path,
        command_path,
    ]
    assert tuple(
        record.canonical_path for record in configuration.source_read_trace.records
    ) == tuple(source_reads)
    assert source_reads
    assert set(source_reads) == {imported_source_path}
    assert configuration.source_read_trace.raw_bytes_by_path == {
        imported_source_path: read_bytes(imported_source_path),
    }
    assert _tree_snapshot(tmp_path) == before
    assert not (tmp_path / ".orchestrate").exists()

    with pytest.raises(TypeError):
        configuration.command_boundary_manifest["run_checks"]["kind"] = "other"  # type: ignore[index]


@pytest.mark.parametrize(
    "configured_field",
    (
        "provider_externs_path",
        "prompt_externs_path",
        "command_boundaries_path",
        "imported_workflow_bundles_path",
    ),
)
def test_initialization_configuration_preserves_configured_missing_failure(
    tmp_path: Path,
    configured_field: str,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    options = {configured_field: tmp_path / f"missing-{configured_field}.json"}

    with pytest.raises(build.LispFrontendCompileError) as error:
        build.load_frontend_initialization_configuration(
            workspace_root=tmp_path,
            **options,
        )

    assert error.value.diagnostics[0].code == "workflow_lisp_manifest_missing"
    assert not (tmp_path / ".orchestrate").exists()


def test_initialization_configuration_preserves_unreadable_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    provider_path = (tmp_path / "providers.json").resolve()
    provider_path.write_text("{}\n", encoding="utf-8")
    read_bytes = Path.read_bytes

    def reject_provider_read(path: Path) -> bytes:
        if path.resolve() == provider_path:
            raise PermissionError("unreadable configuration")
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_provider_read)

    with pytest.raises(PermissionError):
        build.load_frontend_initialization_configuration(
            workspace_root=tmp_path,
            provider_externs_path=provider_path,
        )

    assert not (tmp_path / ".orchestrate").exists()


@pytest.mark.parametrize(
    ("configured_field", "payload", "diagnostic_code"),
    (
        ("provider_externs_path", [], "workflow_lisp_manifest_invalid"),
        (
            "prompt_externs_path",
            {"prompt": {"input_file": "one", "asset_file": "two"}},
            "workflow_lisp_manifest_invalid",
        ),
        (
            "command_boundaries_path",
            {"run": {"stable_command": [1]}},
            "command_boundary_manifest_invalid",
        ),
        (
            "imported_workflow_bundles_path",
            {},
            "imported_workflow_bundle_manifest_empty",
        ),
    ),
)
def test_initialization_configuration_preserves_production_schema_failures(
    tmp_path: Path,
    configured_field: str,
    payload: object,
    diagnostic_code: str,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    manifest_path = tmp_path / f"{configured_field}.json"
    manifest_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(build.LispFrontendCompileError) as error:
        build.load_frontend_initialization_configuration(
            workspace_root=tmp_path,
            **{configured_field: manifest_path},
        )

    assert error.value.diagnostics[0].code == diagnostic_code
    assert not (tmp_path / ".orchestrate").exists()


def test_public_build_language_error_carries_same_attempt_configuration_vector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    diagnostics = importlib.import_module(
        "orchestrator.workflow_lisp.diagnostics"
    )
    invalid_source = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "workflow_lisp"
        / "invalid"
        / "unknown_type.orc"
    )
    provider_path = (tmp_path / "providers.json").resolve()
    provider_path.write_bytes(b'{"provider":"revision-a"}\n')
    revision_b = b'{"provider":"revision-b"}\n'
    read_bytes = Path.read_bytes
    mutated = False

    def mutate_to_b_during_build(path: Path) -> bytes:
        nonlocal mutated
        if path.resolve() == provider_path and not mutated:
            mutated = True
            path.write_bytes(revision_b)
            return revision_b
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", mutate_to_b_during_build)
    request = build.FrontendBuildRequest(
        source_path=invalid_source,
        source_roots=(invalid_source.parent,),
        provider_externs_path=provider_path,
        workspace_root=tmp_path,
    )

    with pytest.raises(build.LispFrontendCompileError) as error:
        build.build_frontend_bundle_in_memory(request)

    assert mutated is True
    assert error.value.configuration_revision_vector == (
        (
            provider_path,
            f"sha256:{hashlib.sha256(revision_b).hexdigest()}",
        ),
    )
    assert str(error.value) == diagnostics.render_diagnostics(
        error.value.diagnostics
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_public_build_success_binds_configuration_revision_read_during_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    provider_path = (tmp_path / "providers.json").resolve()
    provider_path.write_bytes(b'{"provider":"revision-a"}\n')
    revision_b = b'{"provider":"revision-b"}\n'
    read_bytes = Path.read_bytes
    mutated = False

    def mutate_to_b_during_build(path: Path) -> bytes:
        nonlocal mutated
        if path.resolve() == provider_path and not mutated:
            mutated = True
            path.write_bytes(revision_b)
            return revision_b
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", mutate_to_b_during_build)
    request = build.FrontendBuildRequest(
        source_path=SOURCE,
        source_roots=(SOURCE.parent,),
        entry_workflow="entry-publication-runtime",
        provider_externs_path=provider_path,
        workspace_root=tmp_path,
    )

    result = build.build_frontend_bundle_in_memory(request)

    assert mutated is True
    assert result.configuration_trace.revision_vector == (
        (
            provider_path,
            f"sha256:{hashlib.sha256(revision_b).hexdigest()}",
        ),
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_public_build_loader_and_recursive_errors_carry_attempt_configuration(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    invalid_json_path = (tmp_path / "invalid-providers.json").resolve()
    invalid_json_bytes = b"{invalid-json\n"
    invalid_json_path.write_bytes(invalid_json_bytes)
    loader_request = build.FrontendBuildRequest(
        source_path=SOURCE,
        source_roots=(SOURCE.parent,),
        entry_workflow="entry-publication-runtime",
        provider_externs_path=invalid_json_path,
        workspace_root=tmp_path,
    )

    with pytest.raises(build.LispFrontendCompileError) as loader_error:
        build.build_frontend_bundle_in_memory(loader_request)

    assert loader_error.value.configuration_revision_vector == (
        (
            invalid_json_path,
            f"sha256:{hashlib.sha256(invalid_json_bytes).hexdigest()}",
        ),
    )

    invalid_import = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "workflow_lisp"
        / "invalid"
        / "unknown_type.orc"
    )
    imported_manifest_path = (tmp_path / "imports.json").resolve()
    imported_manifest_path.write_text(
        json.dumps(
            {
                "broken": {
                    "kind": "compiled",
                    "path": str(invalid_import),
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    imported_manifest_bytes = imported_manifest_path.read_bytes()
    recursive_request = build.FrontendBuildRequest(
        source_path=SOURCE,
        source_roots=(invalid_import.parent, SOURCE.parent),
        entry_workflow="entry-publication-runtime",
        imported_workflow_bundles_path=imported_manifest_path,
        workspace_root=tmp_path,
    )

    with pytest.raises(build.LispFrontendCompileError) as recursive_error:
        build.build_frontend_bundle_in_memory(recursive_request)

    assert recursive_error.value.configuration_revision_vector == (
        (
            imported_manifest_path,
            f"sha256:{hashlib.sha256(imported_manifest_bytes).hexdigest()}",
        ),
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_public_build_no_configuration_error_binds_empty_vector_but_direct_compile_does_not(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    compiler = importlib.import_module("orchestrator.workflow_lisp.compiler")
    invalid_source = (
        REPO_ROOT
        / "tests"
        / "fixtures"
        / "workflow_lisp"
        / "invalid"
        / "unknown_type.orc"
    )
    request = build.FrontendBuildRequest(
        source_path=invalid_source,
        source_roots=(invalid_source.parent,),
        workspace_root=tmp_path,
    )

    with pytest.raises(build.LispFrontendCompileError) as build_error:
        build.build_frontend_bundle_in_memory(request)
    with pytest.raises(build.LispFrontendCompileError) as direct_error:
        compiler.compile_stage3_entrypoint(
            invalid_source,
            source_roots=(invalid_source.parent,),
            workspace_root=tmp_path,
        )

    assert build_error.value.configuration_revision_vector == ()
    assert build_error.value.configuration_revision_conflict_paths == ()
    assert direct_error.value.configuration_revision_vector is None
    assert direct_error.value.configuration_revision_conflict_paths is None
    assert build_error.value.diagnostics == direct_error.value.diagnostics
    assert str(build_error.value) == str(direct_error.value)
    assert not (tmp_path / ".orchestrate").exists()


@pytest.mark.parametrize("error_kind", ("lisp", "generic"))
def test_public_build_preserves_more_complete_compatible_error_configuration_vector(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error_kind: str,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    first_path = (tmp_path / "first.json").resolve()
    second_path = (tmp_path / "second.json").resolve()
    first_revision = "sha256:" + ("1" * 64)
    complete_vector = (
        (first_path, first_revision),
        (second_path, "sha256:" + ("2" * 64)),
    )
    if error_kind == "lisp":
        existing_error = build.LispFrontendCompileError(
            (),
            configuration_revision_vector=complete_vector,
            configuration_revision_conflict_paths=(second_path,),
        )
        expected_type = build.LispFrontendCompileError
    else:
        existing_error = RuntimeError("generic failure with shared evidence")
        existing_error.configuration_revision_vector = complete_vector
        existing_error.configuration_revision_conflict_paths = (second_path,)
        expected_type = RuntimeError

    def fail_with_shared_trace(
        request: build.FrontendBuildRequest,
        *,
        source_read_trace: SourceReadTrace | None,
        configuration_read_trace: object,
    ) -> object:
        configuration_read_trace._record(  # type: ignore[attr-defined]
            canonical_path=first_path,
            revision=first_revision,
        )
        raise existing_error

    monkeypatch.setattr(
        build,
        "_build_frontend_bundle_in_memory",
        fail_with_shared_trace,
    )
    request = build.FrontendBuildRequest(
        source_path=SOURCE,
        workspace_root=tmp_path,
    )

    with pytest.raises(expected_type) as caught:
        build.build_frontend_bundle_in_memory(request)

    assert caught.value is existing_error
    assert caught.value.configuration_revision_vector == complete_vector
    assert caught.value.configuration_revision_conflict_paths == (second_path,)
    assert not (tmp_path / ".orchestrate").exists()


def test_public_build_generic_recursive_configuration_conflict_survives_aba_reversion(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    manifest_io = importlib.import_module(
        "orchestrator.workflow_lisp.build_manifest_io"
    )
    provider_path = (tmp_path / "providers.json").resolve()
    revision_a_bytes = b'{"providers.execute":"provider-a"}\n'
    revision_b_bytes = b'{"providers.execute":"provider-b"}\n'
    provider_path.write_bytes(revision_a_bytes)
    request = replace(
        _imported_request(build, tmp_path),
        provider_externs_path=provider_path,
    )
    configured_paths = (
        provider_path,
        request.prompt_externs_path.resolve(),
        request.command_boundaries_path.resolve(),
        request.imported_workflow_bundles_path.resolve(),
    )
    expected_vector = tuple(
        sorted(
            (
                (
                    path,
                    f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
                )
                for path in configured_paths
            ),
            key=lambda item: item[0].as_posix(),
        )
    )
    read_bytes = Path.read_bytes
    provider_reads = 0
    raised_by_trace: list[RuntimeError] = []
    record = manifest_io.ConfigurationReadTrace._record

    def aba_read(path: Path) -> bytes:
        nonlocal provider_reads
        if path.resolve() != provider_path:
            return read_bytes(path)
        provider_reads += 1
        if provider_reads == 1:
            return revision_a_bytes
        provider_path.write_bytes(revision_b_bytes)
        try:
            return revision_b_bytes
        finally:
            provider_path.write_bytes(revision_a_bytes)

    def capture_trace_error(
        trace: object,
        *,
        canonical_path: Path,
        revision: str,
    ) -> object:
        try:
            return record(
                trace,
                canonical_path=canonical_path,
                revision=revision,
            )
        except RuntimeError as error:
            raised_by_trace.append(error)
            raise

    monkeypatch.setattr(Path, "read_bytes", aba_read)
    monkeypatch.setattr(
        manifest_io.ConfigurationReadTrace,
        "_record",
        capture_trace_error,
    )

    with pytest.raises(RuntimeError) as caught:
        build.build_frontend_bundle_in_memory(request)

    assert provider_reads == 2
    assert read_bytes(provider_path) == revision_a_bytes
    assert raised_by_trace == [caught.value]
    assert caught.value.configuration_revision_vector == expected_vector
    assert caught.value.configuration_revision_conflict_paths == (
        provider_path,
    )
    assert not (tmp_path / ".orchestrate").exists()


def test_public_build_unchanged_generic_error_carries_nonconflicting_configuration(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    provider_path = (tmp_path / "providers.json").resolve()
    provider_bytes = b'{"provider":"unchanged"}\n'
    provider_path.write_bytes(provider_bytes)
    expected_error = PermissionError("source is unreadable")
    read_bytes = Path.read_bytes

    def fail_source_read(path: Path) -> bytes:
        if path.resolve() == SOURCE.resolve():
            raise expected_error
        return read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", fail_source_read)
    request = build.FrontendBuildRequest(
        source_path=SOURCE,
        source_roots=(SOURCE.parent,),
        entry_workflow="entry-publication-runtime",
        provider_externs_path=provider_path,
        workspace_root=tmp_path,
    )

    with pytest.raises(PermissionError) as caught:
        build.build_frontend_bundle_in_memory(request)

    assert caught.value is expected_error
    assert caught.value.configuration_revision_vector == (
        (
            provider_path,
            f"sha256:{hashlib.sha256(provider_bytes).hexdigest()}",
        ),
    )
    assert caught.value.configuration_revision_conflict_paths == ()
    assert not (tmp_path / ".orchestrate").exists()


def test_initialization_configuration_copies_and_deep_freezes_retained_payloads(
    tmp_path: Path,
) -> None:
    build = importlib.import_module("orchestrator.workflow_lisp.build")
    command_path = (tmp_path / "certified-adapter.json").resolve()
    command_path.write_text(
        json.dumps(
            {
                "normalize": {
                    "kind": "certified_adapter",
                    "stable_command": ["python", "scripts/normalize.py"],
                    "input_contract": {
                        "type": "object",
                        "properties": {
                            "payload": {
                                "type": "array",
                                "items": {"type": "string"},
                            }
                        },
                    },
                    "output_type_name": "Normalized",
                    "effects": ["structured_result"],
                    "path_safety": {
                        "kind": "workspace_relpath",
                        "rules": [
                            {
                                "root": "workspace",
                                "modes": ["read"],
                            }
                        ],
                    },
                    "source_map_behavior": "step",
                    "fixture_ids": ["normalize_ok"],
                    "negative_fixture_ids": ["normalize_bad"],
                }
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    configuration = build.load_frontend_initialization_configuration(
        workspace_root=tmp_path.resolve(),
        source_roots=(CLI_FIXTURES.resolve(),),
        provider_externs_path=CLI_FIXTURES / "providers.json",
        prompt_externs_path=CLI_FIXTURES / "prompts.json",
        command_boundaries_path=command_path,
        imported_workflow_bundles_path=CLI_FIXTURES
        / "imported_workflow_bundles.json",
    )

    adapter = configuration.command_boundaries["normalize"]
    manifest_adapter = configuration.command_boundary_manifest["normalize"]
    assert adapter.input_contract is not manifest_adapter["input_contract"]
    assert adapter.path_safety is not manifest_adapter["path_safety"]
    assert adapter.input_contract["properties"]["payload"]["items"] == {
        "type": "string"
    }
    assert adapter.path_safety["rules"][0]["modes"] == ("read",)
    with pytest.raises(TypeError):
        adapter.input_contract["properties"]["payload"]["items"]["type"] = "integer"
    with pytest.raises(TypeError):
        adapter.path_safety["rules"][0]["root"] = "other"

    imported = configuration.imported_workflow_bundles[0]
    coverage = imported.bundle.provenance.frontend_source_map_coverage
    assert coverage is imported.bundle.surface.provenance.frontend_source_map_coverage
    assert coverage is imported.bundle.core_workflow_ast.provenance.frontend_source_map_coverage
    assert coverage is imported.bundle.ir.provenance.frontend_source_map_coverage
    assert (
        coverage
        is imported.bundle.core_workflow_ast._surface_workflow.provenance.frontend_source_map_coverage
    )
    with pytest.raises(TypeError):
        coverage["frontend_ast"] = "mutated"
    with pytest.raises(TypeError):
        imported.bundle.imports["other"] = imported.bundle
    assert not (tmp_path / ".orchestrate").exists()
