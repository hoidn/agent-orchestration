"""Deterministic descriptor-bound mount plans for ``bubblewrap.v1``."""

from __future__ import annotations

from collections.abc import Mapping
import ctypes
from dataclasses import dataclass
import errno
import fcntl
import json
import os
from pathlib import PurePosixPath
import selectors
import signal
import stat
import time

from orchestrator.providers.isolation_backend import (
    BACKEND_CONTRACT_ID,
    BACKEND_EXECUTABLE_PATH,
    ProviderInvocationIsolationPlan,
    ProviderIsolationBackendIdentity,
    ProviderIsolationInvalidPlan,
    ProviderIsolationMount,
    ProviderIsolationRequest,
    PinnedProviderInvocationAuthorities,
    PinnedProviderIsolationBackend,
    CgroupV2ContainmentRoot,
    CgroupV2ContainmentSlot,
    DurableLaunchReleaseGate,
    WorkflowProviderIsolationRequest,
)
from orchestrator.providers.isolation_network_preflight import (
    PinnedProviderIsolationNetworkAuthority,
    ProviderIsolationNetworkPreflightError,
)
from orchestrator.providers.provider_launch_shim import (
    _fixed_environment,
    _pin_rootless_child,
    _validate_pinned_rootless_child_boundary,
    _wait_for_boundary_ready,
    _wait_for_bwrap_child_pid,
    encode_credential_frame,
)


_WORKSPACE_COMPONENTS = frozenset({"home", "workspace", "tmp"})
_SEALED_TOP_LEVEL = frozenset(
    {
        "bin",
        "sbin",
        "usr",
        "lib",
        "lib32",
        "lib64",
        "etc",
        "opt",
        "proc",
        "dev",
        "run",
        "var",
    }
)
_PR_SET_PDEATHSIG = 1


@dataclass(slots=True)
class _OuterChildWaitState:
    """Tracks whether the direct child PID has already been reaped."""

    reaped: bool = False


def build_bubblewrap_plan(
    *,
    request: ProviderIsolationRequest,
    backend_identity_digest: str,
    network_preflight_digest: str,
    rootfs_fd: int,
    candidate_fd: int,
    scratch_fd: int | None,
    readiness_fd: int,
    status_fd: int,
    credential_fd: int,
    provider_prefix: str,
    synthetic_home: str,
    expected_primary_group_count: int,
    expected_overflow_group_count: int,
    declared_credential_names: tuple[str, ...] = (),
) -> ProviderInvocationIsolationPlan:
    """Build the immutable positive authority set before rendering argv."""

    candidate = PurePosixPath(request.candidate_path)
    if (
        not candidate.is_absolute()
        or len(candidate.parts) < 3
        or candidate.parts[1] not in _WORKSPACE_COMPONENTS
        or candidate.parts[1] in _SEALED_TOP_LEVEL
    ):
        raise ProviderIsolationInvalidPlan(
            "candidate must be below one admitted workspace component"
        )
    if any(part in {"", ".", ".."} for part in candidate.parts[1:]):
        raise ProviderIsolationInvalidPlan(
            "candidate path contains an invalid component"
        )
    if provider_prefix == request.candidate_path or provider_prefix.startswith(
        request.candidate_path + "/"
    ):
        raise ProviderIsolationInvalidPlan(
            "candidate authority overlaps the sealed provider prefix"
        )
    if synthetic_home != "/run/provider-home":
        raise ProviderIsolationInvalidPlan(
            "synthetic home does not match the fixed provider environment"
        )
    mounts: list[ProviderIsolationMount] = [
        ProviderIsolationMount(
            role="sealed_rootfs",
            source_fd=rootfs_fd,
            destination="/",
            access="ro",
        ),
        ProviderIsolationMount(
            role="candidate",
            source_fd=candidate_fd,
            destination=request.candidate_path,
            access="rw",
        ),
    ]
    output_bundle: str | None = None
    if isinstance(request, WorkflowProviderIsolationRequest):
        if scratch_fd is None:
            raise ProviderIsolationInvalidPlan(
                "workflow provider result scratch descriptor is missing"
            )
        scratch_destination = os.fspath(
            PurePosixPath(request.result_logical_path).parent
        )
        runtime_root = f"{request.candidate_path}/.orchestrate"
        if not (
            scratch_destination == runtime_root
            or scratch_destination.startswith(runtime_root + "/")
        ):
            raise ProviderIsolationInvalidPlan(
                "active result parent must be below masked candidate runtime"
            )
        mounts.append(
            ProviderIsolationMount(
                role="active_result_scratch",
                source_fd=scratch_fd,
                destination=scratch_destination,
                access="rw",
            )
        )
        output_bundle = request.result_logical_path
    elif scratch_fd is not None:
        raise ProviderIsolationInvalidPlan(
            "controller attempt forbids a result scratch descriptor"
        )
    environment = tuple(
        _fixed_environment(
            {},
            provider_prefix=provider_prefix,
            output_bundle=output_bundle,
        ).items()
    )
    return ProviderInvocationIsolationPlan(
        backend=BACKEND_CONTRACT_ID,
        backend_identity_digest=backend_identity_digest,
        network_preflight_digest=network_preflight_digest,
        request=request,
        mounts=tuple(mounts),
        provider_prefix=provider_prefix,
        synthetic_home=synthetic_home,
        readiness_fd=readiness_fd,
        status_fd=status_fd,
        credential_fd=credential_fd,
        expected_primary_group_count=expected_primary_group_count,
        expected_overflow_group_count=expected_overflow_group_count,
        environment=environment,
        declared_credential_names=declared_credential_names,
    )


def render_bubblewrap_argv(
    plan: ProviderInvocationIsolationPlan,
) -> list[str]:
    """Render only the reviewed namespace and descriptor-bound mount grammar."""

    if plan.backend != BACKEND_CONTRACT_ID:
        raise ProviderIsolationInvalidPlan("backend contract is unsupported")
    rootfs, candidate, *remaining = plan.mounts
    if (
        rootfs.role != "sealed_rootfs"
        or rootfs.access != "ro"
        or rootfs.destination != "/"
        or candidate.role != "candidate"
        or candidate.access != "rw"
    ):
        raise ProviderIsolationInvalidPlan("positive mount plan is malformed")

    candidate_path = PurePosixPath(candidate.destination)
    candidate_overlay = f"/{candidate_path.parts[1]}"
    candidate_ancestors = _directory_ancestors(candidate_path)
    runtime_root = f"{candidate.destination}/.orchestrate"

    argv = [
        os.fspath(BACKEND_EXECUTABLE_PATH),
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-cgroup",
        "--disable-userns",
        "--assert-userns-disabled",
        "--uid",
        "0",
        "--gid",
        "0",
        "--cap-drop",
        "ALL",
        "--hostname",
        plan.hostname,
        "--die-with-parent",
        "--new-session",
        "--as-pid-1",
        "--json-status-fd",
        str(plan.status_fd),
        "--ro-bind-fd",
        str(rootfs.source_fd),
        "/",
        "--tmpfs",
        candidate_overlay,
    ]
    for ancestor in candidate_ancestors:
        argv.extend(("--dir", ancestor))
    argv.extend(
        (
            "--bind-fd",
            str(candidate.source_fd),
            candidate.destination,
            "--tmpfs",
            runtime_root,
        )
    )

    if remaining:
        if len(remaining) != 1 or remaining[0].role != "active_result_scratch":
            raise ProviderIsolationInvalidPlan(
                "result scratch mount set is malformed"
            )
        scratch = remaining[0]
        for ancestor in _relative_directory_ancestors(
            PurePosixPath(scratch.destination),
            PurePosixPath(runtime_root),
        ):
            argv.extend(("--dir", ancestor))
        argv.extend(
            (
                "--bind-fd",
                str(scratch.source_fd),
                scratch.destination,
            )
        )

    if candidate_overlay != "/tmp":
        argv.extend(("--tmpfs", "/tmp"))
    argv.extend(
        (
            "--tmpfs",
            "/run",
        )
    )
    environment = dict(plan.environment)
    synthetic_directories = (
        environment["HOME"],
        environment["XDG_CONFIG_HOME"],
        environment["XDG_CACHE_HOME"],
        environment["XDG_DATA_HOME"],
    )
    created_directories: set[str] = set()
    for directory in synthetic_directories:
        for ancestor in _directory_ancestors(PurePosixPath(directory)):
            if ancestor != "/run" and ancestor not in created_directories:
                argv.extend(("--dir", ancestor))
                created_directories.add(ancestor)
    argv.extend(
        (
            "--proc",
            "/proc",
            "--dev",
            "/dev",
            "--clearenv",
        )
    )
    for name, value in plan.environment:
        argv.extend(("--setenv", name, value))
    argv.extend(
        (
            "--chdir",
            plan.request.candidate_path,
            "--",
            f"{plan.provider_prefix}/bin/python",
            "-I",
            "-S",
            f"{plan.provider_prefix}/libexec/provider-launch-shim-v1.py",
            "--provider-prefix",
            plan.provider_prefix,
        )
    )
    for name in plan.declared_credential_names:
        argv.extend(("--credential-name", name))
    if isinstance(plan.request, WorkflowProviderIsolationRequest):
        argv.extend(("--output-bundle", plan.request.result_logical_path))
    argv.extend(
        (
            "--expected-primary-group-count",
            str(plan.expected_primary_group_count),
            "--expected-overflow-group-count",
            str(plan.expected_overflow_group_count),
            "--boundary-ready-fd",
            str(plan.readiness_fd),
            "--",
            *plan.request.target,
        )
    )
    _audit_rendered_argv(argv, plan)
    return argv


def _directory_ancestors(path: PurePosixPath) -> tuple[str, ...]:
    current = PurePosixPath("/")
    values: list[str] = []
    for part in path.parts[1:]:
        current /= part
        values.append(os.fspath(current))
    return tuple(values)


def _relative_directory_ancestors(
    path: PurePosixPath,
    root: PurePosixPath,
) -> tuple[str, ...]:
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise ProviderIsolationInvalidPlan(
            "scratch destination escaped masked runtime"
        ) from exc
    current = root
    values: list[str] = []
    for part in relative.parts:
        current /= part
        values.append(os.fspath(current))
    return tuple(values)


def _audit_rendered_argv(
    argv: list[str],
    plan: ProviderInvocationIsolationPlan,
) -> None:
    if not argv or argv[0] != os.fspath(BACKEND_EXECUTABLE_PATH):
        raise ProviderIsolationInvalidPlan(
            "rendered backend executable is not the fixed authority"
        )
    if "--ro-bind" in argv or "--bind" in argv:
        raise ProviderIsolationInvalidPlan(
            "rendered plan contains a pathname-backed host mount"
        )
    if any(item in {"sudo", "pkexec", "setpriv"} for item in argv):
        raise ProviderIsolationInvalidPlan(
            "rendered plan contains a privileged launcher"
        )
    output_bundle = (
        plan.request.result_logical_path
        if isinstance(plan.request, WorkflowProviderIsolationRequest)
        else None
    )
    expected_environment = tuple(
        _fixed_environment(
            {},
            provider_prefix=plan.provider_prefix,
            output_bundle=output_bundle,
        ).items()
    )
    if (
        plan.synthetic_home != "/run/provider-home"
        or plan.environment != expected_environment
    ):
        raise ProviderIsolationInvalidPlan(
            "rendered plan environment is not the fixed provider environment"
        )
    permitted_fds = {
        plan.credential_fd,
        plan.readiness_fd,
        plan.status_fd,
        *(mount.source_fd for mount in plan.mounts),
    }
    for index, item in enumerate(argv):
        if item not in {"--ro-bind-fd", "--bind-fd"}:
            continue
        try:
            source_fd = int(argv[index + 1], 10)
        except (IndexError, ValueError) as exc:
            raise ProviderIsolationInvalidPlan(
                "rendered descriptor mount is malformed"
            ) from exc
        if source_fd not in permitted_fds:
            raise ProviderIsolationInvalidPlan(
                "rendered mount references an undeclared descriptor"
            )


class ProviderIsolationLaunchError(RuntimeError):
    """The trusted launch apparatus failed before a quiescent result."""

    code = "provider_isolation_launch_failed"

    def __init__(self, message: str):
        super().__init__(f"{self.code}: {message}")


@dataclass(frozen=True, slots=True)
class BubblewrapLaunchResult:
    """Bounded process result plus the exact immutable launch authority."""

    plan: ProviderInvocationIsolationPlan
    network_preflight_digest: str
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    child_pid: int
    child_starttime: int
    host_boundary: Mapping[str, object]
    containment_identity: str
    containment_empty: bool


def _validate_cgroup_launch_authorities(
    *,
    pinned_backend: PinnedProviderIsolationBackend,
    release_gate: DurableLaunchReleaseGate,
    containment_slot: CgroupV2ContainmentSlot,
) -> None:
    """Cross-bind the exact backend, durable gate, root, and launch leaf."""

    if (
        type(pinned_backend) is not PinnedProviderIsolationBackend
        or type(pinned_backend.identity) is not ProviderIsolationBackendIdentity
        or type(release_gate) is not DurableLaunchReleaseGate
        or type(containment_slot) is not CgroupV2ContainmentSlot
        or type(containment_slot.root) is not CgroupV2ContainmentRoot
    ):
        raise ProviderIsolationInvalidPlan(
            "containment launch authorities require exact types"
        )
    if (
        pinned_backend.identity.containment_root_identity
        != containment_slot.root.identity_digest
    ):
        raise ProviderIsolationInvalidPlan(
            "backend containment root does not match the launch slot"
        )
    if (
        release_gate.containment_identity != containment_slot.identity_digest
        or release_gate.events != ("launch_intent",)
        or release_gate.release_consumed
        or release_gate.release_permit is not None
        or release_gate.poisoned
    ):
        raise ProviderIsolationInvalidPlan(
            "launch release and containment authorities are inconsistent"
        )


def execute_bubblewrap_invocation(
    *,
    invocation_authorities: PinnedProviderInvocationAuthorities,
    pinned_backend: PinnedProviderIsolationBackend,
    credentials: Mapping[str, bytes],
    declared_credential_names: tuple[str, ...],
    release_gate: DurableLaunchReleaseGate,
    containment_slot: CgroupV2ContainmentSlot,
    network_authority: PinnedProviderIsolationNetworkAuthority,
    timeout_seconds: float = 30,
) -> BubblewrapLaunchResult:
    """Execute one rootless, gated, descriptor-projected provider attempt."""

    if os.geteuid() == 0:
        raise ProviderIsolationLaunchError(
            "rootless Bubblewrap launch requires an unprivileged controller"
        )
    if type(invocation_authorities) is not PinnedProviderInvocationAuthorities:
        raise ProviderIsolationInvalidPlan(
            "pinned invocation authorities have an invalid exact type"
        )
    invocation_authorities.revalidate()
    request = invocation_authorities.request
    if type(network_authority) is not PinnedProviderIsolationNetworkAuthority:
        raise ProviderIsolationInvalidPlan(
            "pinned network authority has an invalid exact type"
        )
    _validate_cgroup_launch_authorities(
        pinned_backend=pinned_backend,
        release_gate=release_gate,
        containment_slot=containment_slot,
    )
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or timeout_seconds <= 0
        or timeout_seconds > 300
    ):
        raise ProviderIsolationInvalidPlan("launch timeout is invalid")
    if set(credentials) - set(declared_credential_names):
        raise ProviderIsolationInvalidPlan(
            "credential map contains an undeclared name"
        )
    frame = bytearray(
        encode_credential_frame(
            dict(credentials),
            declared_names=declared_credential_names,
        )
    )
    controller_groups = tuple(os.getgroups())
    primary_count = controller_groups.count(os.getegid())
    overflow_count = len(controller_groups) - primary_count
    deadline = time.monotonic() + float(timeout_seconds)

    reservations: list[int] = []
    owned_fds: list[int] = []
    parent_fds: list[int] = []
    outer_pid = -1
    wait_state = _OuterChildWaitState()
    child_pid = -1
    child_pidfd = -1
    child_proc_fd = -1
    child_starttime = -1
    slot_removed = False
    try:
        pinned_backend.revalidate()
        containment_slot.revalidate()
        if containment_slot.populated:
            raise ProviderIsolationInvalidPlan(
                "containment slot must be empty before launch"
            )
        invocation_authorities.revalidate()
        network_authority.revalidate()
        (
            root_source,
            candidate_source,
            scratch_source,
        ) = invocation_authorities._duplicate_setup_fds()
        owned_fds.extend((root_source, candidate_source))
        _require_mount_authority_fd(root_source, role="sealed_rootfs")
        _require_mount_authority_fd(candidate_source, role="candidate")
        if scratch_source is not None:
            _require_mount_authority_fd(
                scratch_source,
                role="active_result_scratch",
            )
            owned_fds.append(scratch_source)
        reservations = _reserve_fixed_fds(
            {
                0,
                1,
                2,
                3,
                4,
                5,
                7,
                8,
                *({6} if scratch_source is not None else set()),
            }
        )
        backend_exec_fd = _duplicate_setup_fd(
            pinned_backend.executable_fd,
            minimum=64,
        )
        owned_fds.append(backend_exec_fd)

        credential_read, credential_write = os.pipe2(os.O_CLOEXEC)
        readiness_read, readiness_write = os.pipe2(os.O_CLOEXEC)
        status_read, status_write = os.pipe2(os.O_CLOEXEC)
        stdout_read, stdout_write = os.pipe2(os.O_CLOEXEC)
        stderr_read, stderr_write = os.pipe2(os.O_CLOEXEC)
        devnull = os.open(os.devnull, os.O_RDONLY | os.O_CLOEXEC)
        owned_fds.extend(
            (
                credential_read,
                readiness_write,
                status_write,
                stdout_write,
                stderr_write,
                devnull,
            )
        )
        parent_fds.extend(
            (
                credential_write,
                readiness_read,
                status_read,
                stdout_read,
                stderr_read,
            )
        )
        fixed_scratch = 6 if scratch_source is not None else None
        plan = build_bubblewrap_plan(
            request=request,
            backend_identity_digest=pinned_backend.identity.digest,
            network_preflight_digest=network_authority.capability.digest,
            rootfs_fd=4,
            candidate_fd=5,
            scratch_fd=fixed_scratch,
            readiness_fd=7,
            status_fd=8,
            credential_fd=3,
            provider_prefix=invocation_authorities.provider_prefix,
            synthetic_home="/run/provider-home",
            expected_primary_group_count=primary_count,
            expected_overflow_group_count=overflow_count,
            declared_credential_names=declared_credential_names,
        )
        argv = render_bubblewrap_argv(plan)
        roles = {
            0: devnull,
            1: stdout_write,
            2: stderr_write,
            3: credential_read,
            4: root_source,
            5: candidate_source,
            7: readiness_write,
            8: status_write,
        }
        if scratch_source is not None:
            roles[6] = scratch_source

        controller_pid = os.getpid()
        start_gate_read, start_gate_write = os.pipe2(os.O_CLOEXEC)
        owned_fds.append(start_gate_read)
        parent_fds.append(start_gate_write)
        outer_pid = os.fork()
        if outer_pid == 0:
            _child_exec_pinned_backend(
                executable_fd=backend_exec_fd,
                argv=argv,
                roles=roles,
                start_gate_read_fd=start_gate_read,
                start_gate_write_fd=start_gate_write,
                expected_parent_pid=controller_pid,
            )
        for fd in owned_fds:
            _safe_close(fd)
        owned_fds.clear()
        for fd in reservations:
            _safe_close(fd)
        reservations.clear()
        parent_fds.remove(start_gate_write)
        _enroll_outer_child_and_release(
            outer_pid=outer_pid,
            containment_slot=containment_slot,
            gate_write_fd=start_gate_write,
        )

        child_pid = _wait_for_bwrap_child_pid(
            status_read,
            selector_factory=selectors.DefaultSelector,
            json_loads=json.loads,
            monotonic=time.monotonic,
            timeout_seconds=_remaining(deadline),
        )
        child_pidfd, child_proc_fd, child_starttime = _pin_rootless_child(
            child_pid,
            selector_factory=selectors.DefaultSelector,
        )
        _wait_for_boundary_ready(
            readiness_read,
            selector_factory=selectors.DefaultSelector,
            monotonic=time.monotonic,
            timeout_seconds=_remaining(deadline),
        )
        _safe_close(readiness_read)
        parent_fds.remove(readiness_read)
        invocation_authorities.revalidate()
        pinned_backend.revalidate()
        containment_slot.revalidate()
        containment_members = containment_slot.members()
        if child_pid not in containment_members:
            raise ProviderIsolationLaunchError(
                "pinned provider child escaped containment"
            )
        if outer_pid not in containment_members:
            raise ProviderIsolationLaunchError(
                "pinned outer child escaped containment"
            )
        if containment_members != tuple(sorted((outer_pid, child_pid))):
            raise ProviderIsolationLaunchError(
                "provider containment membership is not exact"
            )
        host_boundary = _validate_pinned_rootless_child_boundary(
            child_pid=child_pid,
            pidfd=child_pidfd,
            proc_dir_fd=child_proc_fd,
            starttime=child_starttime,
            controller_euid=os.geteuid(),
            controller_egid=os.getegid(),
            controller_groups=controller_groups,
            expected_primary_count=primary_count,
            expected_overflow_count=overflow_count,
            selector_factory=selectors.DefaultSelector,
        )
        network_authority.revalidate()
        permit = release_gate.record_commit()
        release_gate.consume_release(permit)
        _write_all_fd(credential_write, frame)
        _safe_close(credential_write)
        parent_fds.remove(credential_write)

        returncode, stdout, stderr = _drain_and_wait(
            pid=outer_pid,
            stdout_fd=stdout_read,
            stderr_fd=stderr_read,
            status_fd=status_read,
            deadline=deadline,
            wait_state=wait_state,
        )
        for fd in (stdout_read, stderr_read, status_read):
            if fd in parent_fds:
                parent_fds.remove(fd)
        containment_slot.wait_empty(timeout_seconds=_remaining(deadline))
        invocation_authorities.revalidate()
        containment_identity = containment_slot.identity_digest
        containment_slot.remove()
        slot_removed = True
        return BubblewrapLaunchResult(
            plan=plan,
            network_preflight_digest=plan.network_preflight_digest,
            argv=tuple(argv),
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            child_pid=child_pid,
            child_starttime=child_starttime,
            host_boundary=host_boundary,
            containment_identity=containment_identity,
            containment_empty=True,
        )
    except (
        ProviderIsolationInvalidPlan,
        ProviderIsolationLaunchError,
        ProviderIsolationNetworkPreflightError,
    ):
        raise
    except BaseException as exc:
        raise ProviderIsolationLaunchError(
            "rootless Bubblewrap invocation failed"
        ) from exc
    finally:
        _zero(frame)
        for fd in (*owned_fds, *parent_fds, *reservations, child_pidfd, child_proc_fd):
            _safe_close(fd)
        if not slot_removed:
            _teardown_bubblewrap_containment(
                containment_slot=containment_slot,
                outer_pid=outer_pid,
                outer_reaped=wait_state.reaped,
            )


def _require_mount_authority_fd(fd: int, *, role: str) -> None:
    if isinstance(fd, bool) or not isinstance(fd, int) or fd < 0:
        raise ProviderIsolationInvalidPlan(f"{role} descriptor is invalid")
    try:
        value = os.fstat(fd)
    except OSError as exc:
        raise ProviderIsolationInvalidPlan(
            f"{role} descriptor is unavailable"
        ) from exc
    if not stat.S_ISDIR(value.st_mode):
        raise ProviderIsolationInvalidPlan(
            f"{role} authority must be a directory"
        )
    if role in {"candidate", "active_result_scratch"} and (
        value.st_uid != os.geteuid() or stat.S_IMODE(value.st_mode) & 0o077
    ):
        raise ProviderIsolationInvalidPlan(
            f"{role} authority must be private and controller-owned"
        )
    if role == "sealed_rootfs" and stat.S_IMODE(value.st_mode) & 0o022:
        raise ProviderIsolationInvalidPlan(
            "sealed rootfs authority is writable by group or other"
        )


def _reserve_fixed_fds(targets: set[int]) -> list[int]:
    if (
        not targets
        or any(
            isinstance(target, bool)
            or not isinstance(target, int)
            or target < 0
            or target > 8
            for target in targets
        )
    ):
        raise ProviderIsolationLaunchError(
            "fixed descriptor reservation set is invalid"
        )
    reservations: list[int] = []
    base_fd = -1
    duplicate_source_fd = -1
    try:
        base_fd = os.open(os.devnull, os.O_RDWR | os.O_CLOEXEC)
        duplicate_source_fd = fcntl.fcntl(
            base_fd,
            fcntl.F_DUPFD_CLOEXEC,
            16,
        )
        if base_fd in targets:
            reservations.append(base_fd)
            base_fd = -1
        for target in sorted(targets):
            try:
                os.fstat(target)
            except OSError as exc:
                if exc.errno != errno.EBADF:
                    raise
                reserved = fcntl.fcntl(
                    duplicate_source_fd,
                    fcntl.F_DUPFD_CLOEXEC,
                    target,
                )
                if reserved != target:
                    os.close(reserved)
                    raise ProviderIsolationLaunchError(
                        "fixed descriptor reservation raced"
                    )
                reservations.append(reserved)
        return reservations
    except BaseException:
        for fd in reservations:
            _safe_close(fd)
        raise
    finally:
        _safe_close(base_fd)
        _safe_close(duplicate_source_fd)


def _duplicate_setup_fd(fd: int, *, minimum: int = 16) -> int:
    try:
        return fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, minimum)
    except OSError as exc:
        raise ProviderIsolationLaunchError(
            "setup authority descriptor could not be duplicated"
        ) from exc


def _enroll_outer_child_and_release(
    *,
    outer_pid: int,
    containment_slot: CgroupV2ContainmentSlot,
    gate_write_fd: int,
) -> None:
    try:
        containment_slot.add_pid(outer_pid)
        if containment_slot.members() != (outer_pid,):
            raise ProviderIsolationLaunchError(
                "outer child containment membership could not be verified"
            )
        _write_all_fd(gate_write_fd, b"\x01")
    finally:
        _safe_close(gate_write_fd)


def _teardown_bubblewrap_containment(
    *,
    containment_slot: CgroupV2ContainmentSlot,
    outer_pid: int,
    outer_reaped: bool,
) -> None:
    """Terminate, prove empty, and remove one failed launch leaf."""

    failures: list[BaseException] = []
    termination_expected = False
    try:
        containment_slot.kill()
        termination_expected = True
    except BaseException as exc:
        failures.append(exc)

    if outer_pid > 0 and not outer_reaped:
        try:
            os.kill(outer_pid, signal.SIGKILL)
            termination_expected = True
        except ProcessLookupError:
            termination_expected = True
        except BaseException as exc:
            failures.append(exc)
        try:
            waited_pid, _wait_status = os.waitpid(
                outer_pid,
                0 if termination_expected else os.WNOHANG,
            )
            if waited_pid not in {0, outer_pid} or (
                waited_pid == 0 and not termination_expected
            ):
                failures.append(
                    ProviderIsolationLaunchError(
                        "direct outer child could not be reaped"
                    )
                )
        except ChildProcessError:
            pass
        except BaseException as exc:
            failures.append(exc)

    empty_proven = False
    try:
        containment_slot.wait_empty(timeout_seconds=5.0)
        empty_proven = True
    except BaseException as exc:
        failures.append(exc)

    if empty_proven:
        try:
            containment_slot.remove()
            if containment_slot.path.exists():
                raise ProviderIsolationLaunchError(
                    "empty containment slot remains after removal"
                )
        except BaseException as exc:
            failures.append(exc)

    if failures:
        raise ProviderIsolationLaunchError(
            "containment teardown could not be proven"
        ) from failures[0]


def _arm_parent_death_signal(expected_parent_pid: int) -> None:
    if (
        isinstance(expected_parent_pid, bool)
        or not isinstance(expected_parent_pid, int)
        or expected_parent_pid <= 1
    ):
        raise ProviderIsolationLaunchError(
            "outer child parent identity is invalid"
        )
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0) != 0:
        error = ctypes.get_errno()
        raise OSError(error, "PR_SET_PDEATHSIG failed")
    if os.getppid() != expected_parent_pid:
        raise ProviderIsolationLaunchError(
            "outer child controller disappeared before launch"
        )


def _child_exec_pinned_backend(
    *,
    executable_fd: int,
    argv: list[str],
    roles: Mapping[int, int],
    start_gate_read_fd: int,
    start_gate_write_fd: int,
    expected_parent_pid: int,
) -> None:
    try:
        _safe_close(start_gate_write_fd)
        _arm_parent_death_signal(expected_parent_pid)
        os.setsid()
        try:
            release = os.read(start_gate_read_fd, 1)
        finally:
            _safe_close(start_gate_read_fd)
        if release != b"\x01":
            raise ProviderIsolationLaunchError(
                "outer child launch gate was not released"
            )
        for target, source in sorted(roles.items()):
            os.dup2(source, target, inheritable=True)
        _close_unlisted_fds({*roles, executable_fd})
        os.execve(executable_fd, argv, {})
    except BaseException:
        try:
            os.write(2, b"provider_isolation_launch_child_failed\n")
        except OSError:
            pass
        os._exit(127)


def _close_unlisted_fds(allowed: set[int]) -> None:
    try:
        values = [
            int(name, 10)
            for name in os.listdir("/proc/self/fd")
            if name.isdecimal()
        ]
    except OSError:
        soft_limit = os.sysconf("SC_OPEN_MAX")
        values = list(range(3, min(int(soft_limit), 1_048_576)))
    for fd in values:
        if fd in allowed:
            continue
        _safe_close(fd)


def _drain_and_wait(
    *,
    pid: int,
    stdout_fd: int,
    stderr_fd: int,
    status_fd: int,
    deadline: float,
    wait_state: _OuterChildWaitState,
) -> tuple[int, str, str]:
    streams = {
        stdout_fd: ("stdout", bytearray(), 16 * 1024 * 1024),
        stderr_fd: ("stderr", bytearray(), 16 * 1024 * 1024),
        status_fd: ("status", bytearray(), 1024 * 1024),
    }
    selector = selectors.DefaultSelector()
    wait_status: int | None = None
    try:
        for fd in streams:
            os.set_blocking(fd, False)
            selector.register(fd, selectors.EVENT_READ)
        while selector.get_map() or wait_status is None:
            if wait_status is None:
                observed_pid, status_value = os.waitpid(pid, os.WNOHANG)
                if observed_pid == pid:
                    wait_state.reaped = True
                    wait_status = status_value
            remaining = _remaining(deadline)
            if selector.get_map():
                for key, _events in selector.select(min(remaining, 0.05)):
                    name, value, bound = streams[key.fd]
                    chunk = os.read(key.fd, min(65_536, bound + 1 - len(value)))
                    if chunk:
                        value.extend(chunk)
                        if len(value) > bound:
                            raise ProviderIsolationLaunchError(
                                f"provider {name} exceeded the byte bound"
                            )
                        continue
                    selector.unregister(key.fd)
                    _safe_close(key.fd)
            elif wait_status is None:
                time.sleep(min(remaining, 0.01))
        assert wait_status is not None
        return (
            os.waitstatus_to_exitcode(wait_status),
            bytes(streams[stdout_fd][1]).decode("utf-8", errors="replace"),
            bytes(streams[stderr_fd][1]).decode("utf-8", errors="replace"),
        )
    finally:
        selector.close()
        for _name, value, _bound in streams.values():
            _zero(value)
        for fd in streams:
            _safe_close(fd)


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("isolated provider launch timed out")
    return min(remaining, 60.0)


def _write_all_fd(fd: int, value: bytes | bytearray) -> None:
    view = memoryview(value)
    try:
        offset = 0
        while offset < len(view):
            written = os.write(fd, view[offset:])
            if written <= 0:
                raise OSError(errno.EIO, "short write")
            offset += written
    finally:
        view.release()


def _safe_close(fd: int) -> None:
    if not isinstance(fd, int) or fd < 0:
        return
    try:
        os.close(fd)
    except OSError as exc:
        if exc.errno != errno.EBADF:
            raise


def _zero(value: bytearray) -> None:
    for index in range(len(value)):
        value[index] = 0
