"""Task 10: standalone foreground TTY fork/resume of linked OMP sessions.

Grammar: ``prompt resume ID [--in-place]``. fds 0/1/2 must be TTYs before any
lookup/lock/write/child. The exact Task 9 active-primary lookup runs first; a
descriptor-relative nonblocking flock on ``<visit>.continuations.lock`` is
held across preflight, child, postconditions, and the one no-replace
continuation publication. Fork = full-id ``--fork``; in-place = full-id
``--resume`` (exact X8 argv/env/cwd per lane). Profile lanes spawn through
the Task 5 Landlock exec helper with a fresh verified frozen-conf copy and a
new empty cwd; ambient lanes spawn directly with null confinement in the
workspace. Once the child has STARTED, every outcome — normal exit, wait
failure, KeyboardInterrupt, or postcondition failure — commits exactly one
next closed continuation record at a single publication boundary, and a
publication failure surfaces as its own stable bridge error. Broker values
are consumed into the child environment but never printed or recorded.
"""

from __future__ import annotations

import errno
import fcntl
import hashlib
import os
import subprocess
import sys
from argparse import Namespace
from pathlib import Path
from typing import Callable, Mapping

from orchestrator._common.safe_tree import read_regular_file
from orchestrator.cli.commands.prompt_io import PromptCliError
from orchestrator.providers.omp_launch_fs import (
    LaunchFsError,
    open_dir_no_follow,
    session_inventory_fd,
)
from orchestrator.providers.omp_launch import PRODUCTION_BINARY_PATH
from orchestrator.providers.omp_launch_contract import POSITIVE_ENV_NAMES
from orchestrator.providers.omp_pin import OMP_BINARY_PIN
from orchestrator.providers.omp_session import (
    OmpSessionError,
    build_session_manifest,
)
from orchestrator.providers.omp_write_confinement import (
    SCHEMA_VERSION,
    landlock_abi,
)
from orchestrator.prompt_resume_postconditions import (
    ResumePostconditionError,
    post_live_manifest,
    validate_fork_result,
    validate_in_place_result,
)
from orchestrator.prompt_resume_preflight import (
    PreflightError,
    now_iso,
    open_relative,
    prepare_launch,
)
from orchestrator.prompt_resume_record import (
    ContinuationRecordError,
    build_record,
    publish_continuation,
)
from orchestrator.prompt_session import PromptSessionError, validate_continuation_chain
from orchestrator.prompt_session_chain import read_continuations, read_manifest_bound
from orchestrator.prompt_session_lookup import resolve_prompt_session

_DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
_PASS_THROUGH_ENV = frozenset(POSITIVE_ENV_NAMES) - {
    "PI_CODING_AGENT_DIR", "OMP_BROKER_URL", "OMP_BROKER_TOKEN",
}
# Aliased so failure-injection tests can patch the spawn seam narrowly.
_Popen = subprocess.Popen


class PromptResumeError(Exception):
    """A stable, non-secret Task 10 bridge failure."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        super().__init__(f"{code}: {detail}" if detail else code)


def build_bridge_env(caller_env: Mapping[str, str]) -> dict[str, str]:
    """Reconstruct the exact 12-name positive environment for the child.

    Nine names pass through from the ambient caller environment (required),
    ``PI_CODING_AGENT_DIR`` derives from ``HOME``, and the CURRENT broker pair
    is required from the ambient environment — never re-derived. Broker values
    are consumed here and never printed or recorded.
    """
    missing = sorted(name for name in _PASS_THROUGH_ENV if not caller_env.get(name))
    if missing:
        raise PromptResumeError(
            "prompt_resume_env_invalid", f"missing {', '.join(missing)}"
        )
    url = caller_env.get("OMP_BROKER_URL")
    token = caller_env.get("OMP_BROKER_TOKEN")
    if not url or not token:
        raise PromptResumeError(
            "prompt_resume_broker_missing", "current broker pair is required"
        )
    return {
        **{name: caller_env[name] for name in sorted(_PASS_THROUGH_ENV)},
        "PI_CODING_AGENT_DIR": os.path.join(caller_env["HOME"], ".omp", "agent"),
        "OMP_BROKER_URL": url,
        "OMP_BROKER_TOKEN": token,
    }


def validate_record_confinement(
    record_confinement: object, actual_policy: object, *, profile: bool
) -> None:
    """Writer-side truthfulness: the record must carry the executed policy."""
    if not profile:
        if record_confinement is not None or actual_policy is not None:
            raise PromptResumeError(
                "prompt_resume_postcondition_failed",
                "ambient continuation must keep null confinement",
            )
        return
    if (
        not isinstance(actual_policy, dict)
        or not isinstance(record_confinement, dict)
        or record_confinement != actual_policy
    ):
        raise PromptResumeError(
            "prompt_resume_postcondition_failed",
            "continuation confinement is not the executed policy",
        )


def _terminate_child(proc) -> None:
    """Deterministically stop an interrupted child; never raises."""
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except BaseException:
        try:
            proc.kill()
            proc.wait(timeout=10)
        except BaseException:
            pass


def resume_prompt_session(
    *,
    runs_root: Path,
    identifier: str,
    in_place: bool,
    pin,
    binary_resolver: Callable[[], str],
    env: Mapping[str, str],
    stdin_fd: int,
    stdout_fd: int,
    stderr_fd: int,
    cwd: str,
    runtime_root: str | None = None,
    now: Callable[[], str] | None = None,
) -> int:
    """Run one foreground fork/resume; returns 0 or raises ``PromptResumeError``."""
    if not (os.isatty(stdin_fd) and os.isatty(stdout_fd) and os.isatty(stderr_fd)):
        raise PromptResumeError(
            "prompt_resume_tty_required", "stdin, stdout, and stderr must be TTYs"
        )
    resolved = resolve_prompt_session(Path(runs_root), identifier)
    mode = "in_place" if in_place else "fork"
    bridge_env = build_bridge_env(env)
    link = resolved.link.document
    lane = link["provider"]["lane"]
    profile = lane in ("no-tools", "conf")
    workspace = link["workflow_workspace"]
    runtime_base = (
        runtime_root if runtime_root is not None else os.path.join(env["HOME"], ".omp-i1-runtime")
    )
    timestamp = now if now is not None else now_iso
    run_fd = sessions_fd = live_fd = lock_fd = -1
    empty_cwd: str | None = None
    try:
        run_fd = open_dir_no_follow(os.fspath(resolved.run_root))
        run_stat = os.fstat(run_fd)
        if (run_stat.st_dev, run_stat.st_ino) != resolved.run_identity:
            raise PromptResumeError("prompt_resume_invalid", "source run directory identity changed")
        sessions_fd = os.open("provider_sessions", _DIR_FLAGS, dir_fd=run_fd)
        sessions_stat = os.fstat(sessions_fd)
        sessions_identity = (sessions_stat.st_dev, sessions_stat.st_ino)
        live_fd = open_relative(run_fd, link["paths"]["live"])
        lock_fd = os.open(
            f"{resolved.visit_key}.continuations.lock",
            os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=sessions_fd,
        )
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
                raise PromptResumeError(
                    "prompt_resume_locked", "another resume holds the per-session lock"
                ) from exc
            raise PromptResumeError("prompt_resume_invalid", f"per-session lock failed: {exc}") from exc

        # Re-read and re-validate the chain under the lock; it must equal the
        # primary that the pre-lock lookup resolved.
        link_raw = read_regular_file(sessions_fd, f"{resolved.visit_key}.session-link.json")
        records, _names, _identity = read_continuations(sessions_fd, resolved.visit_key)
        active = validate_continuation_chain(
            link_raw,
            records,
            initial_journal_sha256=hashlib.sha256(resolved.journal_bytes).hexdigest(),
            run_root=resolved.run_root,
        )
        live_manifest = build_session_manifest(live_fd)
        if live_manifest.manifest_sha256 != active.live_manifest_sha256:
            raise PromptResumeError("prompt_resume_invalid", "live manifest drifted since lookup")
        pre_journal = read_manifest_bound(live_fd, live_manifest, active.primary_basename)
        if hashlib.sha256(pre_journal).hexdigest() != active.journal_sha256:
            raise PromptResumeError("prompt_resume_invalid", "active journal drifted since lookup")
        pre_inventory = session_inventory_fd(live_fd)
        if (active.session_id, active.primary_basename) != (
            resolved.session_id, resolved.primary_basename
        ):
            raise PromptResumeError("prompt_resume_invalid", "continuation chain changed during lookup")

        plan = prepare_launch(
            run_fd=run_fd,
            resolved=resolved,
            active=active,
            mode=mode,
            pin=pin,
            binary_resolver=binary_resolver,
            bridge_env=bridge_env,
            workspace=workspace,
            runtime_base=runtime_base,
            stderr_fd=stderr_fd,
        )
        empty_cwd = plan.empty_cwd

        started_at = timestamp()
        try:
            child_argv = (
                [*plan.helper_prefix, "--", plan.private, *plan.interactive_argv]
                if plan.helper_prefix is not None
                else [plan.private, *plan.interactive_argv]
            )
            proc = _Popen(
                child_argv,
                stdin=stdin_fd,
                stdout=stdout_fd,
                stderr=stderr_fd,
                cwd=plan.child_cwd,
                env=bridge_env,
                close_fds=True,
            )
        except OSError as exc:
            # The child never started: no outcome to record (preflight parity).
            raise PromptResumeError("prompt_resume_child_failed", f"child could not start: {exc}") from exc

        # --- mandatory post-start outcome path: one outcome, one record -------
        interrupt: BaseException | None = None
        try:
            child_exit = proc.wait()
        except KeyboardInterrupt as exc:
            interrupt = exc
            _terminate_child(proc)
            child_exit = 130
        except OSError:
            child_exit = -1
        ended_at = timestamp()
        post_manifest = post_live_manifest(live_fd)

        result: dict[str, str | None] | None = None
        failure: str | None = None
        if interrupt is not None:
            failure = "prompt_resume_interrupted"
        elif child_exit != 0:
            failure = "prompt_resume_child_failed"
        else:
            try:
                if mode == "fork":
                    new_name, new_id, new_sha = validate_fork_result(
                        live_fd=live_fd,
                        pre_inventory=pre_inventory,
                        pre_manifest_sha256=active.live_manifest_sha256,
                        source_primary=active.primary_basename,
                        source_sha256=active.journal_sha256,
                        source_session_id=active.session_id,
                    )
                    result = {
                        "session_id": new_id,
                        "primary_basename": new_name,
                        "journal_sha256": new_sha,
                    }
                else:
                    new_sha = validate_in_place_result(
                        live_fd=live_fd,
                        pre_inventory=pre_inventory,
                        pre_manifest_sha256=active.live_manifest_sha256,
                        pre_bytes=pre_journal,
                        source_primary=active.primary_basename,
                        source_session_id=active.session_id,
                    )
                    result = {
                        "session_id": active.session_id,
                        "primary_basename": active.primary_basename,
                        "journal_sha256": new_sha,
                    }
            except ResumePostconditionError:
                failure = "prompt_resume_postcondition_failed"
        if failure is None:
            try:
                validate_record_confinement(
                    plan.actual_confinement, plan.actual_confinement, profile=profile
                )
            except PromptResumeError:
                failure = "prompt_resume_postcondition_failed"
                result = None

        record = build_record(
            link_raw=link_raw,
            records=records,
            active=active,
            mode=mode,
            child_exit_code=child_exit,
            failure=failure,
            result=(
                result
                if failure is None
                else {"session_id": None, "primary_basename": None, "journal_sha256": None}
            ),
            started_at=started_at,
            ended_at=ended_at,
            pin=pin,
            interactive_argv=plan.interactive_argv,
            confinement=plan.actual_confinement,
            conf_manifest=plan.conf_manifest,
            post_manifest=post_manifest,
        )
        label = "success" if failure is None else "failed"
        try:
            publish_continuation(
                run_fd=run_fd,
                sessions_fd=sessions_fd,
                sessions_identity=sessions_identity,
                visit_key=resolved.visit_key,
                records=records,
                payload=record,
            )
        except ContinuationRecordError as exc:
            raise PromptResumeError(
                "prompt_resume_record_failed",
                f"could not publish the {label} continuation record: {exc}",
            ) from exc
        if interrupt is not None:
            raise interrupt
        if failure is not None:
            raise PromptResumeError(
                failure, "resume outcome did not satisfy the bridge postconditions"
            )
        return 0
    except PreflightError as exc:
        raise PromptResumeError(exc.code, exc.detail) from exc
    except (OSError, LaunchFsError, OmpSessionError, TypeError, ValueError) as exc:
        raise PromptResumeError("prompt_resume_invalid", str(exc)) from exc
    finally:
        for fd in (lock_fd, live_fd, sessions_fd, run_fd):
            if fd >= 0:
                try:
                    os.close(fd)
                except OSError:
                    pass
        # The profile empty cwd is intentionally retained: the recorded
        # confinement binds its (dev, ino) identity, and each run uses a fresh
        # nonce path, so leaving it does not affect later resumes.


def prompt_resume_workflow(args: Namespace) -> int:
    """Dispatch ``prompt resume ID [--in-place]``; returns the process exit code."""
    try:
        repeats = getattr(args, "in_place", 0)
        if repeats not in (0, 1):
            raise PromptCliError("--in-place must be given at most once")
        return resume_prompt_session(
            runs_root=Path.cwd() / ".orchestrate" / "runs",
            identifier=args.session_id,
            in_place=bool(repeats),
            pin=OMP_BINARY_PIN,
            binary_resolver=lambda: PRODUCTION_BINARY_PATH,
            env=os.environ,
            stdin_fd=0,
            stdout_fd=1,
            stderr_fd=2,
            cwd=os.getcwd(),
        )
    except PromptCliError as exc:
        print(f"prompt resume: {exc}", file=sys.stderr)
        return 2
    except (PromptResumeError, PromptSessionError) as exc:
        print(f"prompt resume: {exc}", file=sys.stderr)
        return 1
