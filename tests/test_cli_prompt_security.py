"""Retained descriptor filesystem and native scaffold safety boundaries."""

from contextlib import closing

import os
import stat
import threading

import pytest

from orchestrator.prompt_scaffold import ScaffoldVerificationError, verify_scaffold
from orchestrator.prompt_session import PromptSessionError
from orchestrator.prompt_session_scaffold import verify_private_scaffold
from orchestrator.providers.omp_launch_fs import LaunchFsError, open_dir_no_follow
from orchestrator.workflow.workspace_files import WorkspaceFiles
from tests.test_prompt_scaffold import _historical_scaffold
from tests.test_prompt_session import _real_private_resolved


def test_workspace_exclusive_result_create_rejects_symlink_leaf(tmp_path):
    target = tmp_path / "planted-target.json"
    target.write_bytes(b'"planted-target"')
    leaf = tmp_path / "result.json"
    leaf.symlink_to(target)
    with closing(WorkspaceFiles(tmp_path)) as files:
        with pytest.raises(OSError):
            files.create("result.json", b'"fresh-value"', exclusive=True)
    assert target.read_bytes() == b'"planted-target"'
    assert leaf.is_symlink()
    assert leaf.readlink() == target


def test_workspace_exclusive_result_create_rejects_existing_leaf(tmp_path):
    leaf = tmp_path / "result.json"
    leaf.write_bytes(b'"planted-leaf"')
    with closing(WorkspaceFiles(tmp_path)) as files:
        with pytest.raises(OSError):
            files.create("result.json", b'"fresh-value"', exclusive=True)
    assert leaf.read_bytes() == b'"planted-leaf"'


def test_workspace_exclusive_result_create_rejects_special_leaf_without_blocking(tmp_path):
    leaf = tmp_path / "result.json"
    os.mkfifo(leaf)
    errors = []

    def create():
        with closing(WorkspaceFiles(tmp_path)) as files:
            try:
                files.create("result.json", b'"fresh-value"', exclusive=True)
            except OSError as error:
                errors.append(error)

    thread = threading.Thread(target=create, daemon=True)
    thread.start()
    thread.join(2)
    assert not thread.is_alive(), "result creation blocked on the special leaf"
    assert len(errors) == 1
    assert stat.S_ISFIFO(leaf.stat().st_mode)


def test_workspace_exclusive_result_create_rejects_symlink_parent(tmp_path):
    moved = tmp_path / "result-moved"
    moved.mkdir()
    parent = tmp_path / "result"
    parent.symlink_to(moved.name, target_is_directory=True)
    with closing(WorkspaceFiles(tmp_path)) as files:
        with pytest.raises(OSError):
            files.create("result/bundle.json", b'"fresh-value"', exclusive=True)
    assert not (moved / "bundle.json").exists()
    assert list(moved.iterdir()) == []


def test_workspace_exclusive_result_create_write_failure_removes_owned_partial(tmp_path, monkeypatch):
    from orchestrator.workflow import workspace_files

    def fail_after_partial(descriptor, payload):
        os.write(descriptor, payload[:3])
        raise OSError("simulated partial write failure")

    monkeypatch.setattr(workspace_files, "_write_bytes", fail_after_partial)
    with closing(WorkspaceFiles(tmp_path)) as files:
        with pytest.raises(OSError, match="partial write failure"):
            files.create("result.json", b'"fresh-value"', exclusive=True)
    assert not (tmp_path / "result.json").exists()
    assert list(tmp_path.iterdir()) == []


def test_native_private_prompt_file_rejects_symlink(tmp_path):
    resolved, private = _real_private_resolved(tmp_path)
    target = tmp_path / "real-prompt.md"
    original = (private / "prompt.md").read_bytes()
    target.write_bytes(original)
    (private / "prompt.md").unlink()
    (private / "prompt.md").symlink_to(target)
    descriptor = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            verify_private_scaffold(descriptor, resolved.link)
    finally:
        os.close(descriptor)
    assert target.read_bytes() == original
    assert (private / "prompt.md").is_symlink()


def test_native_private_prompt_file_rejects_special_leaf_without_blocking(tmp_path):
    resolved, private = _real_private_resolved(tmp_path)
    (private / "prompt.md").unlink()
    os.mkfifo(private / "prompt.md")
    errors = []

    def verify():
        descriptor = os.open(private, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            verify_private_scaffold(descriptor, resolved.link)
        except PromptSessionError as error:
            errors.append(error)
        finally:
            os.close(descriptor)

    thread = threading.Thread(target=verify, daemon=True)
    thread.start()
    thread.join(2)
    assert not thread.is_alive(), "private prompt capture blocked on the special leaf"
    assert len(errors) == 1
    assert errors[0].code == "session_link_invalid"
    assert stat.S_ISFIFO((private / "prompt.md").stat().st_mode)


def test_omp_conf_directory_admission_rejects_symlink_ancestors(tmp_path):
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "config.yml").write_bytes(b"configuration witness")
    link_dir = tmp_path / "conf-link-dir"
    link_dir.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(LaunchFsError):
        open_dir_no_follow(str(link_dir / "conf"))
    alias = tmp_path / "conf-alias"
    alias.symlink_to(conf, target_is_directory=True)
    with pytest.raises(LaunchFsError):
        open_dir_no_follow(str(alias))
    assert (conf / "config.yml").read_bytes() == b"configuration witness"


def test_historical_scaffold_verification_rejects_symlinked_scaffold_path(tmp_path):
    result, inputs = _historical_scaffold(tmp_path, b"p")
    alias = result.path.parent / "scaffold-alias"
    alias.symlink_to(result.path, target_is_directory=True)
    with pytest.raises(OSError):
        verify_scaffold(generated_root=result.path.parent, inputs=inputs, name=alias.name)
    assert alias.is_symlink()


def test_historical_scaffold_verification_rejects_symlink_parent(tmp_path):
    result, inputs = _historical_scaffold(tmp_path, b"p")
    link_dir = tmp_path / "generated-alias"
    link_dir.symlink_to(result.path.parent, target_is_directory=True)
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=link_dir, inputs=inputs, name=result.path.name)
    assert link_dir.is_symlink()
