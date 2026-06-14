"""Managed provider invocation wrapping and runtime paths."""

from __future__ import annotations

import os
import sys
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

from orchestrator.providers.types import ProviderInvocation

if TYPE_CHECKING:
    from orchestrator.workflow.executable_ir import ManagedJobsConfig


class ManagedProviderRuntime:
    """Prepare managed provider guard invocations for one run."""

    def __init__(self, *, run_root: Path, workspace: Path) -> None:
        self.run_root = run_root
        self.workspace = workspace

    def wrap_invocation(
        self,
        invocation: ProviderInvocation,
        *,
        step_name: str,
        visit_count: int,
        config: "ManagedJobsConfig",
    ) -> ProviderInvocation:
        """Wrap a selected provider invocation with the managed-job guard."""

        step_root = self.run_root / "managed_jobs" / step_name / str(visit_count)
        audit_path = step_root / "managed_job_events.jsonl"
        pending_policy_path = step_root / "pending_policy.jsonl"
        shim_dir = step_root / "shims"
        state_root = step_root / "state"
        for path in (audit_path.parent, shim_dir, state_root):
            path.mkdir(parents=True, exist_ok=True)

        command = [
            sys.executable,
            "-m",
            "orchestrator.managed_jobs.provider_guard",
            "--policy",
            str((self.workspace / config.policy).resolve()),
            "--audit-path",
            str(audit_path),
            "--state-root",
            str(state_root),
            "--pending-policy",
            str(pending_policy_path),
            "--backend",
            config.backend,
            "--shim-dir",
            str(shim_dir),
        ]
        for watch_root in config.watch_roots:
            command.extend(["--watch-root", watch_root])
        command.extend(["--", *invocation.command])

        env = dict(invocation.env)
        repo_root = str(Path(__file__).resolve().parents[2])
        existing_pythonpath = env.get("PYTHONPATH") or os.environ.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            repo_root
            if not existing_pythonpath
            else os.pathsep.join((repo_root, existing_pythonpath))
        )
        env.update(
            {
                "MANAGED_JOB_AUDIT_PATH": str(audit_path),
                "MANAGED_JOB_PENDING_POLICY": str(pending_policy_path),
                "MANAGED_JOB_SHIM_DIR": str(shim_dir),
                "MANAGED_JOB_STATE_ROOT": str(state_root),
            }
        )

        metadata = dict(invocation.metadata)
        metadata["managed_jobs"] = {
            "audit_path": str(audit_path),
            "pending_policy_path": str(pending_policy_path),
            "state_root": str(state_root),
            "shim_dir": str(shim_dir),
        }
        return replace(
            invocation,
            command=command,
            env=env,
            terminate_process_tree=True,
            metadata=metadata,
        )
