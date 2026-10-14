"""Characterization for the shared mapping-to-bundle validation boundary."""

import ast
import builtins
import importlib
from pathlib import Path
from types import MappingProxyType, ModuleType

import pytest


def _canonical_expression_symbol(
    node: ast.AST,
    bindings: dict[str, str],
) -> str | None:
    if isinstance(node, ast.Name):
        return bindings.get(node.id, node.id)
    if isinstance(node, ast.Attribute):
        owner = _canonical_expression_symbol(node.value, bindings)
        return f"{owner}.{node.attr}" if owner else node.attr
    return None


def _patch_callable_aliases_by_identity(
    monkeypatch: pytest.MonkeyPatch,
    *,
    modules: tuple[ModuleType, ...],
    forbidden_objects: tuple[object, ...],
    replacement: object,
) -> set[str]:
    forbidden_ids = {id(value) for value in forbidden_objects}
    patched: set[str] = set()
    for module in modules:
        for name, value in tuple(vars(module).items()):
            if id(value) not in forbidden_ids:
                continue
            monkeypatch.setattr(module, name, replacement)
            patched.add(f"{module.__name__}.{name}")
    return patched


def test_persisted_dashboard_typed_surface_does_not_use_fresh_frontends_or_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from orchestrator.dashboard.projection import RunProjector
    from orchestrator.workflow.persisted_surface import PersistedWorkflowSurfaceGraph
    from tests.test_dashboard_compiled_workflow import (
        _scan_one,
        _write_real_imported_bundle_mix_run,
    )

    result, source_path, _state = _write_real_imported_bundle_mix_run(tmp_path)
    run = _scan_one(tmp_path)
    source_path = source_path.resolve(strict=False)
    manifest_path = result.manifest_path.resolve(strict=False)
    artifact_path = result.artifact_paths["persisted_workflow_surface"].resolve(
        strict=False
    )
    authoritative_paths = {manifest_path, artifact_path}
    required_reads: set[Path] = set()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("fresh workflow frontend or validation path was entered")

    definition_targets = (
        "orchestrator.workflow_lisp.build.build_frontend_bundle_in_memory",
        "orchestrator.workflow_lisp.compiler.compile_stage3_entrypoint",
        "orchestrator.workflow_lisp.compiler.compile_stage3_module",
        "orchestrator.workflow_lisp.reader.read_sexpr_file",
        "orchestrator.workflow_lisp.syntax.build_syntax_module",
        "orchestrator.workflow.executable_ir.validate_executable_workflow",
    )

    def resolve_dotted_target(target: str) -> object:
        parts = target.split(".")
        for split_at in range(len(parts), 0, -1):
            try:
                value: object = importlib.import_module(".".join(parts[:split_at]))
            except ModuleNotFoundError:
                continue
            for attribute in parts[split_at:]:
                value = getattr(value, attribute)
            return value
        raise AssertionError(f"cannot resolve forbidden target {target}")

    forbidden_objects = tuple(resolve_dotted_target(target) for target in definition_targets)
    dashboard_consumers = tuple(
        importlib.import_module(module_name)
        for module_name in (
            "orchestrator.dashboard.compiled_workflow",
            "orchestrator.dashboard.models",
            "orchestrator.dashboard.projection",
            "orchestrator.dashboard.server",
            "orchestrator.cli.commands.dashboard",
        )
    )
    _patch_callable_aliases_by_identity(
        monkeypatch,
        modules=dashboard_consumers,
        forbidden_objects=forbidden_objects,
        replacement=forbidden,
    )
    for target in definition_targets:
        monkeypatch.setattr(target, forbidden)

    real_open = builtins.open
    real_read_text = Path.read_text
    real_read_bytes = Path.read_bytes

    def resolved_path(value) -> Path | None:
        try:
            return Path(value).resolve(strict=False)
        except (TypeError, ValueError, OSError, RuntimeError):
            return None

    def record_authorized_read(value) -> None:
        resolved = resolved_path(value)
        if resolved == source_path:
            raise AssertionError("bound Workflow Lisp source was read")
        if resolved in authoritative_paths:
            required_reads.add(resolved)

    def guarded_open(file, *args, **kwargs):
        record_authorized_read(file)
        return real_open(file, *args, **kwargs)

    def guarded_read_text(path: Path, *args, **kwargs):
        record_authorized_read(path)
        return real_read_text(path, *args, **kwargs)

    def guarded_read_bytes(path: Path, *args, **kwargs):
        record_authorized_read(path)
        return real_read_bytes(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)
    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)

    detail = RunProjector().project_detail(run)

    structure = detail.workflow_structure
    assert isinstance(structure, PersistedWorkflowSurfaceGraph)
    assert structure.entry_workflow == "neurips/entry::orchestrate"
    assert set(structure.nodes) == {
        "neurips/entry::orchestrate",
        "neurips/helper::provider-attempt",
        "imported_selector::selector-run",
    }
    assert isinstance(structure.nodes, MappingProxyType)
    with pytest.raises(TypeError):
        structure.nodes["other"] = structure.entry_node  # type: ignore[index]
    assert required_reads == authoritative_paths


# ---------------------------------------------------------------------------
# Task 5 (OMP-I1): authored OMP metadata-mode admission and reservations.
# ---------------------------------------------------------------------------
