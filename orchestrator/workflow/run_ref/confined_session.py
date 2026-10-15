"""One confined child attempt's holder session: leaves, seeding, checkpoints and wall budget.

`ConfinedChildSession` is the `confined` object the evaluated child runtime receives
(`execute_pure_run(confined=...)`) and the `LeafRunner` its command attempts dispatch
through. Per child attempt (design R3, N4, N5, N9, P5, P29):

* one `Holder` per controller incarnation, launched lazily before its first leaf (a pure child never launches
  one; a provider site is refused before any launch). Before the launch the clone
  must equal its last `committed` checkpoint header (an `intent` header is repaired
  by re-freezing); after it, the tmpfs `/workspace` is seeded from the clone by a
  host helper in the holder's `host` slot.
* after every leaf that quiesced by exiting, the tmpfs is checkpointed onto the
  clone by the same helper under the two-phase header, before the memo commit;
  never after a timeout, wall exhaustion, a lingering leaf or a holder death.
* a checkpoint failure under the live controller stops the scope, re-freezes the
  partial clone and publishes `committed`, ending the child like a holder death, keeping
  `run_ref_environment_escape_rejected` when the copier refused.
* one fixed Linux BOOTTIME clock starts before admission and ends after holder stop:
  admission/provisioning, snapshot copies, pure evaluation, launch/rehash, seeding,
  leaves/result import, checkpoints and shutdown all consume the same allowance;
  each helper/leaf timeout is clamped to the visit budget that remains, including
  downtime/suspension; acknowledged ledger closures preserve charge across recovery. Witness validation and
  parent settlement remain outside the child execution accounting.
  Exhaustion fails the attempt with `run_ref_budget_exhausted`.

A failure ends the session: later leaves are refused with the same code. A launch
refused before release (`run_ref_environment_unavailable`) is kept apart in
`prerelease_error` so the lifecycle aborts the parent effect instead of settling
`FAILED`. Dependencies: an admitted `ConfinedAdmission` (image, limits), a
provisioned child (clone, control root), `holder.Holder`, `checkpoint.py`.
`PR_SET_PDEATHSIG` of the host helper is tied to the thread that forks it, so the
session must be driven from the thread that runs the child (the evaluated runtime's).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import time
from typing import Any

from orchestrator._common.io_atomic import durable_atomic_write

from .confined_budget import boottime_ns
from .checkpoint import RunRefCheckpointError, preflight_checkpoint, publish_initial_header
from .confinement import CHECKPOINT_HEADER
from .contracts import canonical_json_bytes
from .holder import Holder
from .leaf import LeafOutcome, LeafRequest
from .runtime import RunRefRuntimeError

HOLDER_DIRNAME = "holder"
BUDGET_FILENAME = "budget.json"
BUDGET_SCHEMA = "run_ref_confined_budget.v1"
# Installation-policy evidence allowance for attempt snapshots (D8), separate from :output-mib.
EVIDENCE_ALLOWANCE_BYTES = 64 << 20
BUDGET_EXHAUSTED = "run_ref_budget_exhausted"
LOST = "run_ref_environment_lost"
UNAVAILABLE = "run_ref_environment_unavailable"
_DIRECTORY = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_CONTROLLER_ROOT = Path(__file__).resolve().parents[3]

# Runs in the holder's `host` slot (N4): the copier between the retained descriptors it inherits.
HELPER = r'''
import json, sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from orchestrator.workflow.run_ref import checkpoint
operation, tmpfs, disk = sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
try:
    if operation == "seed":
        copied = checkpoint.seed_workspace(disk, tmpfs, max_bytes=int(sys.argv[5]))
        print(json.dumps({"digest": copied.manifest.digest}))
    else:
        header = checkpoint.checkpoint_workspace(tmpfs, disk, Path(sys.argv[5]), effect_identity=sys.argv[6],
                                                 ordinal=int(sys.argv[7]), max_bytes=int(sys.argv[8]))
        print(json.dumps({"digest": header.manifest_digest}))
except checkpoint.RunRefCheckpointError as exc:
    print(json.dumps({"code": exc.code, "detail": exc.detail}))
    sys.exit(3)
'''


def _performer_error(code: str, detail: str) -> Exception:
    from orchestrator.workflow.evaluated.commands import CommandPerformerError
    return CommandPerformerError(code, detail)


def ensure_checkpoint_header(child_root: Path, baseline_digest: str) -> Path:
    """The initial `committed` header (effect `none`, ordinal 0) once, after provisioning."""
    header = Path(child_root) / CHECKPOINT_HEADER
    if not header.exists():
        publish_initial_header(header, baseline_digest)
    return header


class ConfinedChildSession:
    """The holder, budget and attempt snapshots of one confined child attempt (`LeafRunner`)."""

    def __init__(self, admission: Any, provisioned: Any, *, holder_factory: Callable[..., Any] | None = None,
                 clock: Callable[[], float] | None = None, started_at: float | None = None,
                 budget_context=None, failure_callback=None, evidence_ledger=None, evidence_visit=None) -> None:
        from orchestrator.workflow.workspace_files import WorkspaceFiles
        from .evaluated_child import SNAPSHOTS_DIRNAME

        self.image = admission.image
        self.evidence_ledger, self.evidence_visit = evidence_ledger, evidence_visit
        self.limits = dict(admission.config.policy.limits)
        self.budget = float(self.limits["wall-seconds"])
        self.layout = provisioned.layout
        self.header_path = self.layout.child_root / CHECKPOINT_HEADER
        (self.layout.child_root / SNAPSHOTS_DIRNAME).mkdir(mode=0o700, exist_ok=True)
        self.snapshots = WorkspaceFiles(self.layout.child_root / SNAPSHOTS_DIRNAME)
        self.clone_files = WorkspaceFiles(self.layout.workspace)
        self._holder_factory = holder_factory or Holder
        self._clock = clock or (lambda: boottime_ns() / 1_000_000_000)
        self.budget_context, self.failure_callback = budget_context, failure_callback
        self.failed_proof = None
        self.resume_error = None
        from .confined_recovery import _released
        self.released = _released(self.layout)
        self._split_known = budget_context is None or budget_context.state["charged_ns"] == 0
        self.holder: Any = None
        self.host_seconds = 0.0
        self.guest_seconds = 0.0
        self._wall_started = self._clock() if started_at is None else started_at
        self._finished_at: float | None = None
        self._stop_record: dict[str, Any] | None = None
        self._stop_error: RunRefRuntimeError | None = None
        self.failure: tuple[str, str] | None = None
        self.prerelease_error: RunRefRuntimeError | None = None
        self._clone_fd: int | None = None

    # -- budget (R3) -------------------------------------------------------------------------------
    @property
    def charged_seconds(self) -> float:
        if self.budget_context is not None:
            return self.budget_context.charged_ns / 1_000_000_000
        end = self._clock() if self._finished_at is None else self._finished_at
        return end - self._wall_started

    @property
    def remaining(self) -> float:
        return self.budget - self.charged_seconds

    def _require_wall_budget(self) -> None:
        if self.remaining > 0:
            return
        code, detail = BUDGET_EXHAUSTED, "child wall budget is exhausted"
        if not self.released:
            self.prerelease_error = RunRefRuntimeError(code, detail)
        else:
            self._fail(code, detail)
        raise _performer_error(code, detail)

    def _stop_holder(self) -> None:
        if self._stop_error is not None:
            raise self._stop_error
        if self.holder is None:
            return
        try:
            self.holder.stop()
        except Exception as exc:
            detail = exc.detail if isinstance(exc, RunRefRuntimeError) else f"{type(exc).__name__}: {exc}"
            if self.failure is not None:
                code, cause = self.failure
                self.failure = (code, f"{cause}; holder stop failed: {detail}")
                self._stop_error = RunRefRuntimeError(*self.failure)
            else:
                self._stop_error = RunRefRuntimeError(getattr(exc, "code", LOST), detail)
            raise self._stop_error from exc

    def _fail(self, code: str, detail: str) -> tuple[str, str]:
        """End the session; a failed scope stop aborts before any clone repair or settlement."""
        if self.failure is None:
            self.failure = (code, detail)
        self._stop_holder()
        return self.failure

    # -- evaluated child runtime interface ---------------------------------------------------------
    def clone_input_parts(self, node: Mapping[str, Any], launch_cwd: Path | None, operands=()) -> dict[str, str]:
        """Bind and store the clone files the command names (D5); charged to the wall budget."""
        from orchestrator.workflow.evaluated.confined_dispatch import (
            GUEST_WORKSPACE, bind_clone_inputs, command_clone_rows, document_clone_rows, guest_cwd, store_attempt_snapshot,
        )

        self._require_wall_budget()
        cwd = guest_cwd(self.layout.workspace, launch_cwd).removeprefix(GUEST_WORKSPACE).lstrip("/") or "."
        allowance = EVIDENCE_ALLOWANCE_BYTES - self.check_evidence()
        document_rows = document_clone_rows(node, operands, self.clone_files)
        rows = [*command_clone_rows(node, cwd), *document_rows]
        binding = bind_clone_inputs(rows, self.clone_files, max_bytes=allowance, directory_rows=document_rows)
        store_attempt_snapshot(self.snapshots, binding.blobs, allowance_bytes=allowance)
        return binding.parts

    def check_evidence(self, *, extra_bytes=0):
        from .confined_evidence import evidence_usage, IMAGE_INVENTORY
        from .image_store import validate_inventory
        from orchestrator.workflow.evaluated.authority import load_run_authority
        from orchestrator.workflow.evaluated.machine import site_classes
        from orchestrator.workflow.evaluated.memo import read_memo
        from orchestrator.workflow.evaluated.confined_dispatch import verify_attempt_snapshot
        used = evidence_usage(self.layout, ledger_path=self.evidence_ledger,
                              visit=self.evidence_visit, extra_bytes=extra_bytes)
        from orchestrator.workflow.workspace_files import WorkspaceFiles
        files = WorkspaceFiles(self.layout.child_root)
        try:
            validate_inventory(files.read(IMAGE_INVENTORY, max_bytes=EVIDENCE_ALLOWANCE_BYTES), self.image.record)
            authority = load_run_authority(self.layout.child_root, run_files=files)
            snapshot = read_memo(authority.memo_path, site_classes(authority.program), run_files=files)
            for entry in snapshot.entries:
                if entry.data['record'] == 'started':
                    verify_attempt_snapshot(self.snapshots, entry.data['input_parts'])
        finally:
            files.close()
        return used

    def verified_parts(self, input_parts: Mapping[str, str]) -> dict[str, str]:
        """A committed effect's clone inputs, from its verified snapshot, never the clone (P1)."""
        from orchestrator.workflow.evaluated.confined_dispatch import verify_attempt_snapshot
        return verify_attempt_snapshot(self.snapshots, input_parts)

    def leaf_context(self) -> Any:
        """The attempt's dispatch context, built after the holder and snapshot work it waits for."""
        from orchestrator.workflow.evaluated.confined_dispatch import ConfinedLeafContext

        self._ensure_started()
        return ConfinedLeafContext(runner=self, image=self.image, network="none",
                                   remaining_wall_seconds=self.remaining)

    # -- holder ------------------------------------------------------------------------------------
    def _ensure_started(self) -> None:
        if self.failure is not None:
            raise RunRefRuntimeError(*self.failure)
        if self.holder is not None:
            return
        self._require_wall_budget()
        self._clone_fd = os.open(self.layout.workspace, _DIRECTORY)
        try:
            preflight_checkpoint(self.header_path, self._clone_fd)
        except RunRefCheckpointError as exc:
            self.prerelease_error = RunRefRuntimeError(exc.code, f"clone_checkpoint_refused:{exc.detail}")
            raise self.prerelease_error from exc
        self._require_wall_budget()
        control = self.layout.child_root / HOLDER_DIRNAME
        control.mkdir(mode=0o700, exist_ok=True)
        git_fd = os.open(self.layout.workspace / ".git", _DIRECTORY)
        try:
            holder = self._holder_factory(self.image, self.limits, control_dir=control, git_dir_fd=git_fd)
            holder.launch()
        except RunRefRuntimeError as exc:
            if exc.code == UNAVAILABLE:
                self.prerelease_error = exc
            else:
                self.failure = (exc.code, exc.detail)
            raise
        finally:
            os.close(git_fd)
        self.holder = holder
        self.released = True
        seeded = self._helper("seed", str(self.limits["workspace-mib"] << 20))
        if seeded is not None:
            raise RunRefRuntimeError(*self._fail(*seeded))

    def _helper(self, operation: str, *arguments: str) -> tuple[str, str] | None:
        """Run the copier in the `host` slot; return `(code, detail)` when it failed."""
        if self.remaining <= 0:
            return BUDGET_EXHAUSTED, f"no wall budget left for the {operation}"
        tmpfs, disk = self.holder.root_fd("workspace"), self._clone_fd
        argv = [sys.executable, "-I", "-c", HELPER, str(_CONTROLLER_ROOT), operation, str(tmpfs), str(disk),
                *arguments]
        try:
            completed = self.holder.run_host_helper(argv, pass_fds=(tmpfs, disk), timeout_sec=self.remaining)
        except RunRefRuntimeError as exc:
            if self.remaining <= 0:
                return BUDGET_EXHAUSTED, f"the {operation} ran out of the wall budget"
            return exc.code, exc.detail
        if completed.returncode == 0:
            return None
        if completed.returncode == 3:
            refused = json.loads(completed.stdout)
            return refused["code"], f"{operation} refused: {refused['detail']}"
        return LOST, f"{operation} helper exited {completed.returncode}: {completed.stderr[-500:]!r}"

    def run_leaf(self, request: LeafRequest) -> LeafOutcome:
        if self.failure is not None:
            raise _performer_error(*self.failure)
        if self.remaining <= 0:
            raise _performer_error(*self._fail(BUDGET_EXHAUSTED, "child wall budget is exhausted before dispatch"))
        started = self._clock()
        outcome = self.holder.run_leaf(replace(request, timeout_sec=min(request.timeout_sec, self.remaining)))
        spent = self._clock() - started
        guest = min(spent, outcome.duration_ms / 1000)
        self.guest_seconds += guest
        if outcome.holder_death is not None:
            self._fail(outcome.holder_death.code, outcome.holder_death.detail)
            return outcome
        if not outcome.quiesced_by_exit:  # timeout, wall clamp or lingering descendants: no checkpoint (N9)
            return outcome
        if self.remaining <= 0:
            raise _performer_error(*self._fail(BUDGET_EXHAUSTED, "leaf exhausted the child wall budget"))
        self._checkpoint(request.leaf_id)
        if self.remaining <= 0:
            raise _performer_error(*self._fail(BUDGET_EXHAUSTED, "checkpoint exhausted the child wall budget"))
        return outcome

    def _checkpoint(self, leaf_id: str) -> None:
        effect, _, ordinal = leaf_id.rpartition("-attempt-")
        failed = self._helper("checkpoint", str(self.header_path), effect, ordinal,
                              str(self.limits["workspace-mib"] << 20))
        if failed is None:
            return
        failed = self._fail(*failed)  # N5: stop the scope before reading the partial clone
        try:  # P5: retain the copier's refusal while publishing the repaired checkpoint
            preflight_checkpoint(self.header_path, self._clone_fd)
        except (RunRefCheckpointError, OSError) as exc:
            self.failure = (failed[0], f"{failed[1]}; re-freeze failed: {exc}")
        raise _performer_error(*self.failure)

    def record_failure(self, authority, exc):
        """Close accounting and await the parent's failed-row ack before any memo failure."""
        if self.failed_proof is not None:
            return self.failed_proof
        if self.prerelease_error is not None:
            raise self.prerelease_error
        if self.failure_callback is None:
            return None
        self.stop()
        self.failed_proof = self.failure_callback(authority, exc)
        return self.failed_proof

    def finish(self) -> None:
        """Quiesce before the completed memo terminal, including shutdown in the wall limit."""
        self.stop()
        self._require_wall_budget()

    def stop(self) -> dict[str, Any]:
        """Stop once and freeze the wall/guest split; all remaining elapsed time is host work."""
        if self._stop_record is not None:
            return self._stop_record
        try:
            self._stop_holder()
        finally:
            if self._clone_fd is not None:
                os.close(self._clone_fd)
                self._clone_fd = None
            self.snapshots.close()
            self.clone_files.close()
        self._finished_at = self._clock()
        if self.budget_context is not None:
            self.budget_context.close()
        self.host_seconds = max(0.0, self.charged_seconds - self.guest_seconds)
        record = {"schema_version": BUDGET_SCHEMA, "budget_ms": int(self.budget * 1000),
                  "guest_ms": int(self.guest_seconds * 1000), "host_ms": int(self.host_seconds * 1000),
                  "charged_ms": int(self.charged_seconds * 1000)}
        if not self._split_known:
            record["host_ms"] = record["guest_ms"] = "UNKNOWN"
        durable_atomic_write(self.layout.child_root / BUDGET_FILENAME, canonical_json_bytes(record))
        self._stop_record = record
        return record


__all__ = ["CHECKPOINT_HEADER", "ConfinedChildSession", "EVIDENCE_ALLOWANCE_BYTES", "ensure_checkpoint_header"]
