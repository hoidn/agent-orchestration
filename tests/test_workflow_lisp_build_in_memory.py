from __future__ import annotations

import hashlib
import importlib
import inspect
import json
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from orchestrator.workflow_lisp.reader import SourceReadTrace


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
