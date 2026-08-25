"""Task 8 adversarial filesystem trust-boundary REDs: the OMP bundle fallback
never follows a planted link/special/pre-existing leaf nor writes through a
symlinked parent; user sources (--prompt-file/--conf/--scaffold/
workflows/generated/reserved run root) are admitted component-wise no-follow
with identity checks; rerun reserves before capture (X7). Also hosts the
reservation-ordering regressions moved from Step 8.2.
"""


from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

from orchestrator.state import StateManager

from tests.test_cli_prompt import (  # noqa: F401  (shared harness)
    INFERENCE_PROVIDER,
    OUTPUT_REQUEST,
    TASK_TEXT,
    _exit,
    _generated_scaffold,
    _run_roots,
    fake_runtime,
)

_BUNDLE_NAME = "__write_root__run_run__result__result_bundle.json"

def _bundles(tmp_path: Path) -> list[Path]:
    runs = tmp_path / ".orchestrate"
    return sorted(runs.rglob(_BUNDLE_NAME)) if runs.exists() else []

def _run_cli_in_thread(
    argv: list[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: float = 15.0
) -> int | None:
    result: dict[str, int | None] = {"code": None}

    def runner() -> None:
        result["code"] = _exit(argv, tmp_path, monkeypatch)

    thread = threading.Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        return None
    return result["code"]


# ---------------------------------------------------------------------------
# Change 1: OMP output-bundle fallback never follows planted paths
# ---------------------------------------------------------------------------

def test_bundle_fallback_rejects_symlink_leaf(
    tmp_path, monkeypatch, fake_runtime
):
    """A child-planted symlink at the bundle leaf must fail the run; the linked target is never created/consumed as workflow output."""
    target = tmp_path / "planted-target.json"
    target.write_bytes(b'"planted-target"')
    fake_runtime.skip_bundle_write = True
    fake_runtime.plant = "symlink-leaf"
    fake_runtime.plant_target = target
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code != 0
    assert target.read_bytes() == b'"planted-target"'  # untouched
    # The planted symlink leaf is left in place (only an O_EXCL-created
    # owned leaf would ever be removed), and nothing was written through it.
    leaves = _bundles(tmp_path)
    assert len(leaves) == 1
    assert leaves[0].is_symlink()
    assert leaves[0].readlink() == target

def test_bundle_fallback_rejects_existing_leaf(
    tmp_path, monkeypatch, fake_runtime
):
    """A pre-existing regular leaf is provider-planted (OMP JSON transport children never receive the bundle path); its content must not be validated as workflow output."""
    fake_runtime.skip_bundle_write = True
    fake_runtime.plant = "existing-leaf"
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code != 0
    # The pre-existing planted regular leaf is never consumed, overwritten,
    # or removed by the failing materialization.
    leaves = _bundles(tmp_path)
    assert len(leaves) == 1
    assert leaves[0].read_bytes() == b'"planted-leaf"'

def test_bundle_fallback_rejects_special_leaf(
    tmp_path, monkeypatch, fake_runtime
):
    fake_runtime.skip_bundle_write = True
    fake_runtime.plant = "special-leaf"
    code = _run_cli_in_thread(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code is not None, "bundle validation blocked on the special leaf"
    assert code != 0
    # The planted FIFO leaf remains (and is never opened for reading).
    leaves = _bundles(tmp_path)
    assert len(leaves) == 1
    import stat as stat_module
    assert stat_module.S_ISFIFO(leaves[0].stat().st_mode)

def test_bundle_fallback_rejects_symlink_parent(
    tmp_path, monkeypatch, fake_runtime
):
    fake_runtime.skip_bundle_write = True
    fake_runtime.plant = "symlink-parent"
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code != 0
    moved = sorted(
        path for path in (tmp_path / ".orchestrate").rglob("*-moved")
    )
    assert all(not (path / _BUNDLE_NAME).exists() for path in moved)
    assert _bundles(tmp_path) == []

def test_bundle_fallback_write_failure_removes_owned_partial(
    tmp_path, monkeypatch, fake_runtime
):
    """A mid-write failure removes only the owned partial leaf (created with O_EXCL by this process), never leaves debris or a planted entry."""
    import orchestrator.workflow.executor as executor_module

    fake_runtime.skip_bundle_write = True

    def fail_after_partial(descriptor, payload):
        os.write(descriptor, payload[:3])
        raise OSError("simulated partial write failure")

    monkeypatch.setattr(executor_module, "_write_bundle_fd", fail_after_partial)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert _bundles(tmp_path) == []


# ---------------------------------------------------------------------------
# Change 2: prompt sources are admitted through no-follow component walks
# ---------------------------------------------------------------------------

def test_prompt_file_rejects_symlink(tmp_path, monkeypatch, fake_runtime):
    real = tmp_path / "real-prompt.md"
    real.write_bytes(TASK_TEXT.encode("utf-8"))
    link = tmp_path / "linked-prompt.md"
    link.symlink_to(real)
    code = _exit(
        ["prompt", "run", "--prompt-file", str(link),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (tmp_path / "workflows" / "generated").exists()
    assert not (tmp_path / ".orchestrate").exists()

def test_prompt_file_rejects_special_leaf(tmp_path, monkeypatch, fake_runtime):
    fifo = tmp_path / "fifo-prompt.md"
    os.mkfifo(fifo)
    code = _run_cli_in_thread(
        ["prompt", "run", "--prompt-file", str(fifo),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code is not None, "prompt-file capture blocked on the special leaf"
    assert code == 1
    assert fake_runtime.executed == []

def test_conf_root_rejects_symlink_ancestor(tmp_path, monkeypatch, fake_runtime):
    conf = tmp_path / "conf"
    conf.mkdir()
    (conf / "config.yml").write_text(
        "advisor:\n  enabled: false\nmemory:\n  backend: off\ntask:\n"
        "  maxConcurrency: 4\n  maxRecursionDepth: 1\n  disabledAgents:\n",
        encoding="utf-8",
    )
    link_dir = tmp_path / "conf-link-dir"
    link_dir.symlink_to(tmp_path, target_is_directory=True)
    alias = link_dir / "conf-target"
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_conf",
         "--conf", str(alias)],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (tmp_path / "workflows" / "generated").exists()
    alias = tmp_path / "conf-alias"
    alias.symlink_to(conf, target_is_directory=True)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_conf",
         "--conf", str(alias)],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (tmp_path / "workflows" / "generated").exists()

def test_generated_root_symlink_ancestor_fails_without_redirected_creation(
    tmp_path, monkeypatch, fake_runtime
):
    target = tmp_path / "redirected-workflows"
    target.mkdir()
    (tmp_path / "workflows").symlink_to(target, target_is_directory=True)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert not (target / "generated").exists()
    assert fake_runtime.executed == []

def test_rerun_rejects_symlinked_scaffold_path(tmp_path, monkeypatch, fake_runtime):
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    alias = tmp_path / "scaffold-alias"
    alias.symlink_to(scaffold, target_is_directory=True)
    fake_runtime.executed.clear()
    code = _exit(
        ["prompt", "run", "--scaffold", str(alias)],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []

def test_rerun_reserves_run_root_before_capture(tmp_path, monkeypatch, fake_runtime):
    import orchestrator.cli.commands.prompt as prompt_module

    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)

    reserved = "20260821T000000Z-abc999"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_capture = prompt_module._capture_rerun
    reserved_seen: list[bool] = []

    def tracked_capture(scaffold_path):
        reserved_seen.append(
            (tmp_path / ".orchestrate" / "runs" / reserved).is_dir()
        )
        return original_capture(scaffold_path)

    monkeypatch.setattr(prompt_module, "_capture_rerun", tracked_capture)
    fake_runtime.executed.clear()
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert reserved_seen == [True]

    # A pre-existing selected root fails before capture runs at all.
    fresh = tmp_path / "rerun-conflict"
    fresh.mkdir()
    (fresh / ".orchestrate" / "runs" / reserved).mkdir(parents=True)
    capture_calls: list[bool] = []

    def spying_capture(scaffold_path):
        capture_calls.append(True)
        return original_capture(scaffold_path)

    monkeypatch.setattr(prompt_module, "_capture_rerun", spying_capture)
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        fresh,
        monkeypatch,
    )
    assert code == 1
    assert capture_calls == []

def test_prompt_inputs_creation_rejects_run_root_ancestor_swap(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.prompt_scaffold as scaffold_service

    reserved = "20260821T000000Z-abc456"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_generate = scaffold_service.generate_scaffold

    def generate_and_swap(**kwargs):
        result = original_generate(**kwargs)
        # Barrier: swap the runs root for another ordinary directory tree
        # holding the same run-id component.
        runs = tmp_path / ".orchestrate" / "runs"
        swapped = tmp_path / ".orchestrate-swapped"
        os.replace(runs, swapped)
        (tmp_path / ".orchestrate").mkdir(exist_ok=True)
        (tmp_path / ".orchestrate" / "runs").mkdir()
        (tmp_path / ".orchestrate" / "runs" / reserved).mkdir()
        return result

    monkeypatch.setattr(scaffold_service, "generate_scaffold", generate_and_swap)
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (tmp_path / ".orchestrate" / "runs" / reserved / "prompt-inputs").exists()
    assert not (tmp_path / ".orchestrate-swapped" / reserved / "prompt-inputs").exists()
def test_run_id_reserved_before_verification_and_pre_existing_root_fails(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.prompt_scaffold as scaffold_service

    reserved = "20260821T000000Z-abc123"

    def tracked_generate(**kwargs):
        # The run id/root must already be reserved when verification begins.
        assert (tmp_path / ".orchestrate" / "runs" / reserved).is_dir()
        return original_generate(**kwargs)

    original_generate = scaffold_service.generate_scaffold
    monkeypatch.setattr(scaffold_service, "generate_scaffold", tracked_generate)
    monkeypatch.setattr(
        StateManager, "new_run_id", lambda: reserved
    )
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == ["omp_no_tools"]
    assert (tmp_path / ".orchestrate" / "runs" / reserved).is_dir()

    # A pre-existing run root fails before execution.
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    monkeypatch.chdir(fresh)
    (fresh / ".orchestrate" / "runs" / reserved).mkdir(parents=True)
    fake_runtime.executed.clear()
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        fresh,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []


def test_rerun_reserves_run_root_before_scaffold_verification(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.prompt_scaffold as scaffold_service

    # Generate once so a verified scaffold exists to rerun.
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    fake_runtime.executed.clear()

    reserved = "20260821T000000Z-xyz789"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_verify = scaffold_service.verify_scaffold

    def tracked_verify(**kwargs):
        # The run id/root must already be reserved when verification begins.
        assert (tmp_path / ".orchestrate" / "runs" / reserved).is_dir()
        return original_verify(**kwargs)

    monkeypatch.setattr(scaffold_service, "verify_scaffold", tracked_verify)
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    assert fake_runtime.provider_names() == ["omp_no_tools"]

    # A pre-existing run root fails the rerun before scaffold verification.
    fresh = tmp_path / "rerun-fresh"
    fresh.mkdir()
    (fresh / ".orchestrate" / "runs" / reserved).mkdir(parents=True)
    verify_calls = []

    def spying_verify(**kwargs):
        verify_calls.append(kwargs)
        return original_verify(**kwargs)

    monkeypatch.setattr(scaffold_service, "verify_scaffold", spying_verify)
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        fresh,
        monkeypatch,
    )
    assert code == 1
    assert verify_calls == []


def test_rerun_rejects_scaffold_from_another_workspace_before_child(
    tmp_path, monkeypatch, fake_runtime
):
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 0
    scaffold = _generated_scaffold(tmp_path)
    assert fake_runtime.provider_names() == ["omp_no_tools"]
    fake_runtime.executed.clear()

    rerun_workspace = tmp_path / "rerun-workspace"
    rerun_workspace.mkdir()
    code = _exit(
        ["prompt", "run", "--scaffold", str(scaffold)],
        rerun_workspace,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (rerun_workspace / ".orchestrate").exists()



def test_prompt_file_rejects_symlink_parent(tmp_path, monkeypatch, fake_runtime):
    real_dir = tmp_path / "real-prompts"
    real_dir.mkdir()
    real = real_dir / "prompt.md"
    real.write_bytes(TASK_TEXT.encode("utf-8"))
    link_dir = tmp_path / "prompts-link"
    link_dir.symlink_to(real_dir, target_is_directory=True)
    code = _exit(
        ["prompt", "run", "--prompt-file", str(link_dir / "prompt.md"),
         "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
    assert not (tmp_path / "workflows" / "generated").exists()
    assert not (tmp_path / ".orchestrate").exists()

def test_prompt_inputs_creation_oserror_fails_closed(
    tmp_path, monkeypatch, fake_runtime
):
    import orchestrator.cli.commands.prompt_io as prompt_io_module
    import orchestrator.prompt_scaffold as scaffold_service

    reserved = "20260821T000000Z-abc777"
    monkeypatch.setattr(StateManager, "new_run_id", lambda: reserved)
    original_generate = scaffold_service.generate_scaffold

    def generate_then_readonly_root(**kwargs):
        result = original_generate(**kwargs)
        root = tmp_path / ".orchestrate" / "runs" / reserved
        os.chmod(root, 0o555)
        return result

    monkeypatch.setattr(
        scaffold_service, "generate_scaffold", generate_then_readonly_root
    )
    code = _exit(
        ["prompt", "run", "--prompt", TASK_TEXT, "--provider", "omp_no_tools"],
        tmp_path,
        monkeypatch,
    )
    assert code == 1
    assert fake_runtime.executed == []
