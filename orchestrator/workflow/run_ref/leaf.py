"""Leaf-launch interface between the run-ref dispatch side and the holder runtime.

Types only. The dispatch side builds :class:`LeafRequest` values and adapts
:class:`LeafOutcome` values; the holder runtime (``holder.py``) implements
:class:`LeafRunner` by running each leaf inside the confined holder. Holder
deaths and attribute drift are reported in ``LeafOutcome.holder_death``;
nothing here writes ledgers or memos.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, Protocol


@dataclass(frozen=True)
class LeafRequest:
    leaf_id: str                       # attempt-relative leaf name; the holder creates /result/<leaf_id> exclusively
    argv: tuple[str, ...]              # argv[0] is an image-pinned absolute guest path
    env: Mapping[str, str]             # the complete guest environment; nothing is inherited from the host
    cwd: str                           # guest path under /workspace
    timeout_sec: float                 # already clamped to the child's remaining wall budget by the caller
    stdout_limit: int                  # bytes kept; excess is dropped and flagged
    stderr_limit: int
    input_files: Mapping[str, bytes]   # regular files written into /result/<leaf_id>/ before release
    network: Literal["none", "model-only"]  # "model-only" refuses with run_ref_provider_transport_unavailable until Task 10


@dataclass(frozen=True)
class HolderDeath:
    code: str                          # run_ref_environment_lost or run_ref_environment_escape_rejected
    detail: str                        # names the cause (attribute drift names the attribute)


@dataclass(frozen=True)
class LeafOutcome:
    exit_code: int | None              # None when killed (timeout, wall exhaustion, holder death)
    timed_out: bool
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    result_files: Mapping[str, bytes]  # regular files read from /result/<leaf_id> under the broker rules
    duration_ms: int                   # leaf wall time (host-side work is accounted by the caller)
    quiesced_by_exit: bool             # True only when the leaf exited on its own (checkpoint allowed, N9)
    holder_death: HolderDeath | None   # set when the holder died or drifted; the attempt fails with this code


class LeafRunner(Protocol):
    def run_leaf(self, request: LeafRequest) -> LeafOutcome: ...
