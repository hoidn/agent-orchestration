"""Tests for dashboard file-reference safety."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.dashboard.files import FileReferenceResolver, UnsafePathError


def test_resolver_accepts_workspace_relative_and_run_relative_paths(tmp_path: Path):
    workspace = tmp_path / "workspace"
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    (run_root / "logs").mkdir(parents=True)
    (workspace / "artifacts").mkdir()
    (workspace / "artifacts" / "result.txt").write_text("ok", encoding="utf-8")
    (run_root / "logs" / "Step.stdout").write_text("stdout", encoding="utf-8")

    resolver = FileReferenceResolver(workspace, run_root)
    workspace_ref = resolver.workspace_ref("artifacts/result.txt")
    run_ref = resolver.run_ref("logs/Step.stdout")

    assert workspace_ref.scope == "workspace"
    assert workspace_ref.route_path == "artifacts/result.txt"
    assert workspace_ref.absolute_path == (workspace / "artifacts" / "result.txt").resolve()
    assert run_ref.scope == "run"
    assert run_ref.route_path == "logs/Step.stdout"
    assert run_ref.exists


def test_resolver_accepts_absolute_path_inside_allowed_roots(tmp_path: Path):
    workspace = tmp_path / "workspace"
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    artifact = workspace / "artifacts" / "result.txt"
    artifact.parent.mkdir(parents=True)
    run_root.mkdir(parents=True)
    artifact.write_text("ok", encoding="utf-8")

    ref = FileReferenceResolver(workspace, run_root).from_any(str(artifact))

    assert ref.scope == "workspace"
    assert ref.route_path == "artifacts/result.txt"


def test_resolver_rejects_absolute_path_outside_allowed_roots(tmp_path: Path):
    workspace = tmp_path / "workspace"
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    outside = tmp_path / "outside.txt"
    run_root.mkdir(parents=True)
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(UnsafePathError):
        FileReferenceResolver(workspace, run_root).from_any(str(outside))


def test_resolver_rejects_dotdot_before_resolution(tmp_path: Path):
    workspace = tmp_path / "workspace"
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    run_root.mkdir(parents=True)

    with pytest.raises(UnsafePathError):
        FileReferenceResolver(workspace, run_root).workspace_ref("../outside.txt")


def test_resolver_rejects_symlink_escape(tmp_path: Path):
    workspace = tmp_path / "workspace"
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    outside = tmp_path / "outside"
    outside.mkdir()
    run_root.mkdir(parents=True)
    (workspace / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        FileReferenceResolver(workspace, run_root).workspace_ref("link/secret.txt")


def test_resolver_reports_missing_and_broken_symlink_as_display_states(tmp_path: Path):
    workspace = tmp_path / "workspace"
    run_root = workspace / ".orchestrate" / "runs" / "run1"
    run_root.mkdir(parents=True)
    (workspace / "broken").symlink_to(workspace / "missing-target")

    resolver = FileReferenceResolver(workspace, run_root)
    missing = resolver.workspace_ref("missing.txt")
    broken = resolver.workspace_ref("broken")

    assert missing.status == "missing"
    assert broken.status == "broken_symlink"
