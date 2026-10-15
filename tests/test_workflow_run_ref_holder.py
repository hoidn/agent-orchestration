"""Units of the run-ref holder runtime (Task 6a): profile builders, launcher, broker, F3b-1.

Real-sandbox evidence lives in tests/e2e/test_e2e_run_ref_holder_runtime.py; these
units run real processes and files on the host where that is possible.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
import resource
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from orchestrator.providers import isolation_backend as backend
from orchestrator.workflow.run_ref import holder_spawner as profile
from orchestrator.workflow.run_ref.holder import Holder
from orchestrator.workflow.run_ref.holder_broker import (
    MAX_RESULT_DEPTH, MAX_RESULT_ENTRIES, MAX_WIPE_DEPTH, GuestRefusal, read_leaf_results, wipe_mount,
)
from orchestrator.workflow.run_ref.image_store import SealedImage
from orchestrator.workflow.run_ref.leaf import LeafRequest
from orchestrator.workflow.run_ref.runtime import RunRefRuntimeError

LIMITS = {"wall-seconds": 600, "memory-mib": 2048, "cpus": 2, "pids": 128, "workspace-mib": 512, "output-mib": 8}
REVIEWED_FILTER_SHA256 = "fa6c19ff4ce45a4b4e0dc7ecf298c7b758b53f4afcc71a41e42f94e22cbaba4f"


def _request(**changes) -> LeafRequest:
    fields = {"leaf_id": "leaf-1", "argv": ("/usr/bin/python3", "-c", "print(1)"), "env": {"A": "b c"},
              "cwd": "/workspace", "timeout_sec": 5.0, "stdout_limit": 100, "stderr_limit": 100,
              "input_files": {"inputs.json": b"{}"}, "network": "none"}
    return LeafRequest(**(fields | changes))


def _after(argv: list[str], flag: str) -> list[list[str]]:
    return [argv[i + 1:i + 3] for i, value in enumerate(argv) if value == flag]


# -- argv, unit and filter -----------------------------------------------------------------------------
def test_holder_argv_is_the_sibling_profile_shape():
    argv = profile.holder_argv(workspace_mib=512, runref_dir="/ctl/runref-x", git=True)
    sizes = {argv[i + 3]: int(argv[i + 1]) >> 20 for i, value in enumerate(argv) if value == "--size"}

    assert {
        "namespaces": [a for a in argv if a.startswith("--unshare-")],
        "hardening": [a for a in argv if a in ("--disable-userns", "--die-with-parent", "--new-session",
                                               "--clearenv")] + _after(argv, "--cap-drop")[0][:1],
        "by_descriptor": _after(argv, "--ro-bind-fd"),
        "sized_tmpfs": sizes,
        "path_binds": _after(argv, "--ro-bind"),
        "masks": [argv[i - 2:i + 3] for i, value in enumerate(argv) if value == "--ro-bind-data"],
        "remount_ro": [a[0] for a in _after(argv, "--remount-ro")],
        "seccomp_and_info": (_after(argv, "--seccomp")[0][0], _after(argv, "--info-fd")[0][0]),
        "no_sys": [a for a in argv if a.startswith("/sys")],
        "command": argv[argv.index("--") + 1:argv.index("--") + 3],
        "masks_after_proc": argv.index("--perms") > argv.index("--proc"),
        "git_inside_workspace_tmpfs": argv.index("/workspace/.git") > argv.index("/workspace"),
    } == {
        "namespaces": ["--unshare-user", "--unshare-ipc", "--unshare-pid", "--unshare-net", "--unshare-uts",
                       "--unshare-cgroup"],
        "hardening": ["--disable-userns", "--die-with-parent", "--new-session", "--clearenv", "ALL"],
        "by_descriptor": [["6", "/"], ["10", "/workspace/.git"]],
        "sized_tmpfs": {"/dev/shm": 64, "/workspace": 512, "/tmp": 256, "/result": 128},
        "path_binds": [["/ctl/runref-x", "/run/runref"]],
        "masks": [["--perms", "0000", "--ro-bind-data", "7", "/proc/keys"],
                  ["--perms", "0000", "--ro-bind-data", "8", "/proc/key-users"]],
        "remount_ro": ["/dev", "/run"],
        "seccomp_and_info": ("9", "5"),
        "no_sys": [],
        "command": ["/bin/sh", "-c"],
        "masks_after_proc": True,
        "git_inside_workspace_tmpfs": True,
    }


def test_holder_argv_without_git_binds_no_workspace_git():
    argv = profile.holder_argv(workspace_mib=64, runref_dir="/ctl/r", git=False)

    assert _after(argv, "--ro-bind-fd") == [["6", "/"]]


def test_mounts_are_remounted_read_only_after_their_binds():
    argv = profile.holder_argv(workspace_mib=64, runref_dir="/ctl/r", git=False)
    remounts = [i for i, value in enumerate(argv) if value == "--remount-ro"]

    assert (remounts[0] > argv.index("/dev/shm"), remounts[1] > argv.index("/run/runref")) == (True, True)


def test_scope_unit_is_named_from_the_token_and_carries_the_policy_limits():
    assert (profile.unit_name("ab" * 32), profile.scope_properties(LIMITS)) == (
        "run-ref-abababababababab.scope",
        [f"MemoryMax={2048 << 20}", "MemorySwapMax=0", "TasksMax=128", "CPUQuota=200%", "OOMPolicy=continue",
         "Delegate=yes"])


def test_read_back_expectation_follows_the_policy():
    unit, files = profile.expected_readback(LIMITS, "/app.slice/run-ref-x.scope")

    assert (unit["CPUQuotaPerSecUSec"], unit["OOMPolicy"], files["cpu.max"], files["pids.max"]) == (
        "2s", "continue", "200000 100000", "128")


CAPTURE_SHIM_PROGRAM = r"""
import ctypes, hashlib, sys
from orchestrator.providers import provider_launch_shim as shim
installed = []
class Recording:
    @staticmethod
    def prctl(option, *args):
        if option == shim._PR_SET_SECCOMP:
            program = args[1]._obj  # the byref(sock_fprog) argument
            installed.append(ctypes.string_at(program.filter, program.len * ctypes.sizeof(shim._SockFilter)))
        return 0
shim.ctypes.CDLL = lambda *a, **k: Recording()
shim._install_key_syscall_filter()
sys.stdout.write(installed[0].hex())
"""


def test_seccomp_program_is_byte_equal_to_what_the_shim_installs():
    captured = subprocess.run([sys.executable, "-c", CAPTURE_SHIM_PROGRAM], capture_output=True, text=True,
                              check=True, env={**os.environ, "PYTHONPATH": os.getcwd()}).stdout
    program = profile.key_syscall_filter_program()

    assert (program.hex() == captured, hashlib.sha256(program).hexdigest()) == (True, REVIEWED_FILTER_SHA256)


def test_profile_refuses_hosts_other_than_x86_64():
    with pytest.raises(RunRefRuntimeError, match="run_ref_environment_unavailable"):
        profile.require_x86_64("aarch64")


# -- launcher -------------------------------------------------------------------------------------------
REPORT_DESCRIPTORS = ("import json, os; names = os.listdir('/proc/self/fd'); "
                      "os.write(3, json.dumps({n: os.readlink('/proc/self/fd/' + n) for n in names "
                      "if os.path.lexists('/proc/self/fd/' + n)}).encode())")


def _launcher(release: bytes | None, token: str = "the-token") -> tuple[int, dict]:
    launch_host, launch_guest = socket.socketpair()
    report_read, report_write = os.pipe()
    stray_read, stray_write = os.pipe()  # an inherited descriptor that must not survive
    digest = hashlib.sha256(token.encode()).hexdigest()
    process = subprocess.Popen(
        [sys.executable, "-I", "-S", "-c", profile.launcher_source(), str(launch_guest.fileno()), digest,
         str(report_write), sys.executable, "-I", "-c", REPORT_DESCRIPTORS],
        pass_fds=(launch_guest.fileno(), report_write, stray_read), stdout=subprocess.PIPE)
    for fd in (launch_guest.detach(), report_write, stray_read, stray_write):
        os.close(fd)
    reported = int(launch_host.recv(64))
    if release is not None:
        launch_host.sendall(release)
    launch_host.close()
    code = process.wait(timeout=30)
    with os.fdopen(report_read, "rb") as handle:
        report = handle.read()
    assert reported == process.pid
    return code, json.loads(report) if report else {}


def test_launcher_without_the_exact_token_never_executes():
    assert (_launcher(None)[0], _launcher(b"not-the-token\n")[0]) == (97, 98)


def test_released_launcher_keeps_only_dev_null_and_the_kept_descriptors():
    code, descriptors = _launcher(b"the-token\n")
    listing = {fd: target for fd, target in descriptors.items() if not target.startswith("/proc/")}

    assert (code, {fd: t for fd, t in listing.items() if fd in "012"}, sorted(listing)) == (
        0, {"0": "/dev/null", "1": "/dev/null", "2": "/dev/null"}, ["0", "1", "2", "3"])


# -- leaf requests ----------------------------------------------------------------------------------------
def test_leaf_script_execs_argv_under_exactly_the_request_environment():
    script = profile.leaf_script(_request(argv=("/usr/bin/python3", "-c", "print('a b')"), cwd="/workspace/s p"))
    cd_line, exec_line = script.splitlines()

    assert (shlex.split(cd_line), shlex.split(exec_line)) == (
        ["cd", "--", "/workspace/s p", "||", "exit", "126"],
        ["exec", "/usr/bin/env", "-i", "--", "A=b c", "/usr/bin/python3", "-c", "print('a b')"])


@pytest.mark.parametrize("changes", [
    {"leaf_id": "../x"}, {"leaf_id": "a/b"}, {"argv": ()}, {"argv": ("python3",)}, {"argv": ("/a=b",)},
    {"argv": ("/bin/sh", "a\0b")}, {"env": {"A=B": "x"}}, {"cwd": "/tmp"}, {"cwd": "/workspace/../etc"},
    {"timeout_sec": 0}, {"timeout_sec": float("inf")}, {"input_files": {"stdout": b""}},
    {"input_files": {"a/b": b""}}, {"network": "host"}, {"stdout_limit": 1.5}, {"stderr_limit": True},
    {"stdout_limit": -1},
])
def test_malformed_leaf_requests_are_refused(changes):
    with pytest.raises(ValueError):
        profile.validate_leaf_request(_request(**changes))


def test_model_only_leaf_refuses_until_the_relay_exists(tmp_path):
    holder = Holder(SealedImage(-1, {}), LIMITS, control_dir=tmp_path)

    with pytest.raises(RunRefRuntimeError) as refused:
        holder.run_leaf(_request(network="model-only"))
    assert refused.value.code == "run_ref_provider_transport_unavailable"


def test_launch_failure_from_a_broken_image_descriptor_is_coded_unavailable(tmp_path):
    holder = Holder(SealedImage(-1, {"tree_digest": "sha256:" + "0" * 64}), LIMITS, control_dir=tmp_path)

    with pytest.raises(RunRefRuntimeError) as refused:
        holder.launch()
    assert (refused.value.code, holder.scope) == ("run_ref_environment_unavailable", None)


def test_a_spawner_silent_until_the_ready_deadline_is_unavailable(tmp_path, monkeypatch):
    """No guest code has run before ready: silence is a launch refusal like EOF, not a holder death."""
    from orchestrator.workflow.run_ref import holder_scope

    monkeypatch.setattr(holder_scope, "LAUNCH_SECONDS", 0.2)
    scope = holder_scope.HolderScope(SealedImage(-1, {}), LIMITS, control_dir=tmp_path)
    scope.process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    scope.ctrl, silent = socket.socketpair()
    info_read, info_write = os.pipe()
    os.write(info_write, b'{"child-pid": 1}')
    os.close(info_write)
    try:
        with pytest.raises(RunRefRuntimeError) as refused:
            scope._await_ready(info_read)
    finally:
        scope.process.kill()
        scope.process.wait()
        silent.close()
        scope.ctrl.close()

    assert (refused.value.code, refused.value.detail.split(":")[0]) == (
        "run_ref_environment_unavailable", "spawner_not_ready")


def test_holder_info_pipe_silent_until_deadline_is_unavailable(tmp_path, monkeypatch):
    from orchestrator.workflow.run_ref import holder_scope

    monkeypatch.setattr(holder_scope, "LAUNCH_SECONDS", 0.02)
    scope = holder_scope.HolderScope(SealedImage(-1, {}), LIMITS, control_dir=tmp_path)
    scope.process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    scope._released = True
    info_read, info_write = os.pipe()
    try:
        with pytest.raises(RunRefRuntimeError) as refused:
            scope._await_ready(info_read)
    finally:
        os.close(info_write)
        scope.process.kill()
        scope.process.wait()

    assert (refused.value.code, refused.value.detail.split(":")[0]) == (
        "run_ref_environment_unavailable", "holder_info_pipe_not_ready")


def test_host_helper_needs_an_absolute_executable(tmp_path):
    holder = Holder(SealedImage(-1, {}), LIMITS, control_dir=tmp_path)

    with pytest.raises(ValueError):
        holder.run_host_helper(["python3", "-c", "pass"], timeout_sec=1)


# -- result broker and wipe ---------------------------------------------------------------------------------
@pytest.fixture
def result_root(tmp_path):
    (tmp_path / "leaf").mkdir()
    (tmp_path / "leaf" / "stdout").write_bytes(b"x" * 50)
    (tmp_path / "leaf" / "stderr").write_bytes(b"err")
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    yield tmp_path, fd
    os.close(fd)


def test_broker_reads_bounded_output_and_nested_regular_result_files(result_root):
    root, fd = result_root
    (root / "leaf" / "out" / "deep").mkdir(parents=True)
    (root / "leaf" / "out" / "deep" / "value.json").write_bytes(b"[1]")

    reads = read_leaf_results(fd, "leaf", stdout_limit=10, stderr_limit=10, max_bytes=1 << 20)

    assert (reads.stdout, reads.stdout_truncated, reads.stderr, reads.stderr_truncated, reads.files) == (
        b"x" * 10, True, b"err", False, {"out/deep/value.json": b"[1]"})


@pytest.mark.parametrize("plant", ["fifo", "symlink", "missing", "nested_fifo", "unreadable"])
def test_broker_refuses_guest_planted_entries_promptly(result_root, plant):
    root, fd = result_root
    leaf = root / "leaf"
    if plant == "fifo":
        (leaf / "stdout").unlink()
        os.mkfifo(leaf / "stdout")
    elif plant == "symlink":
        (leaf / "stderr").unlink()
        (leaf / "stderr").symlink_to("/etc/hostname")
    elif plant == "missing":
        (leaf / "stdout").unlink()
    elif plant == "nested_fifo":
        (leaf / "dir").mkdir()
        os.mkfifo(leaf / "dir" / "pipe")
    else:
        (leaf / "stdout").chmod(0)
    started = time.monotonic()

    with pytest.raises(GuestRefusal):
        read_leaf_results(fd, "leaf", stdout_limit=10, stderr_limit=10, max_bytes=1 << 20)
    assert time.monotonic() - started < 1


def test_broker_propagates_host_descriptor_exhaustion(result_root):
    _root, fd = result_root
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    filler: list[int] = []
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, hard))
    try:
        while True:
            try:
                filler.append(os.dup(0))
            except OSError:
                break
        with pytest.raises(OSError) as raised:
            read_leaf_results(fd, "leaf", stdout_limit=10, stderr_limit=10, max_bytes=1 << 20)
    finally:
        for descriptor in filler:
            os.close(descriptor)
        resource.setrlimit(resource.RLIMIT_NOFILE, (soft, hard))
    assert (type(raised.value) is OSError, raised.value.errno) == (True, errno.EMFILE)


def _refused(fd: int) -> str:
    started = time.monotonic()
    with pytest.raises(GuestRefusal) as refused:
        read_leaf_results(fd, "leaf", stdout_limit=10, stderr_limit=10, max_bytes=1 << 20)
    assert time.monotonic() - started < 5
    return str(refused.value)


def test_broker_refuses_an_unreadable_result_directory_as_guest_caused(result_root):
    root, fd = result_root
    (root / "leaf" / "sub").mkdir()
    (root / "leaf" / "sub" / "file").write_text("x")
    (root / "leaf" / "sub").chmod(0o400)
    try:
        assert "sub" in _refused(fd)
    finally:
        (root / "leaf" / "sub").chmod(0o700)


def test_broker_refuses_a_result_name_that_is_not_utf8(result_root):
    root, fd = result_root
    (root / "leaf" / os.fsdecode(b"\xff")).write_text("x")

    assert "UTF-8" in _refused(fd)


@pytest.mark.parametrize("shape", ["files", "directories", "nested"])
def test_broker_bounds_the_result_tree_before_accumulating(result_root, shape):
    root, fd = result_root
    if shape == "nested":
        os.makedirs(root / "leaf" / "/".join(["d"] * (MAX_RESULT_DEPTH + 2)))
    for index in range(MAX_RESULT_ENTRIES + 1 if shape != "nested" else 0):
        target = root / "leaf" / f"e{index}"
        target.mkdir() if shape == "directories" else target.write_bytes(b"")

    assert any(word in _refused(fd) for word in ("entries", "deeply"))


def test_wipe_refuses_a_tree_deeper_than_its_descriptor_bound(tmp_path):
    previous = os.getcwd()
    os.chdir(tmp_path)
    try:
        for _ in range(MAX_WIPE_DEPTH + 10):
            os.mkdir("d")
            os.chdir("d")
    finally:
        os.chdir(previous)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    open_before = len(os.listdir("/proc/self/fd"))
    try:
        assert (wipe_mount(fd), len(os.listdir("/proc/self/fd")) == open_before) == (False, True)
    finally:
        os.close(fd)
        _remove_deep(tmp_path)


def _remove_deep(root: Path) -> None:
    """pytest's own cleanup handles the depth, but keep tmp_path tidy for reruns."""
    subprocess.run(["rm", "-rf", "--", str(root / "d")], check=True)


def test_wipe_empties_a_mount_whose_entries_the_guest_locked(tmp_path):
    (tmp_path / "locked" / "inner").mkdir(parents=True)
    (tmp_path / "locked" / "inner" / "f").write_text("x")
    os.symlink("/etc", tmp_path / "link")
    (tmp_path / "locked" / "inner").chmod(0)
    (tmp_path / "locked").chmod(0)
    fd = os.open(tmp_path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        assert (wipe_mount(fd), os.path.exists("/etc")) == (True, True)
    finally:
        os.close(fd)


# -- F3b-1 attributes on a real process ------------------------------------------------------------------
@pytest.fixture
def sleeper():
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    yield process.pid
    process.kill()
    process.wait()


CHANGES = {
    "limits": lambda pid: resource.prlimit(pid, resource.RLIMIT_NOFILE, (64, 64)),
    "nice": lambda pid: os.setpriority(os.PRIO_PROCESS, pid, 5),
    "oom_score_adj": lambda pid: Path(f"/proc/{pid}/oom_score_adj").write_text("700"),
    "cpus_allowed": lambda pid: os.sched_setaffinity(pid, {min(os.sched_getaffinity(pid))}),
    "sched_getattr": lambda pid: os.sched_setscheduler(pid, os.SCHED_IDLE, os.sched_param(0)),
    "ioprio": lambda pid: profile._libc.syscall(251, 1, pid, 3 << 13),  # ioprio_set IOPRIO_CLASS_IDLE
    "coredump_filter": lambda pid: Path(f"/proc/{pid}/coredump_filter").write_text("0x0"),
}


@pytest.mark.parametrize("attribute", sorted(CHANGES))
def test_each_spawner_attribute_change_is_named_as_drift(sleeper, attribute):
    if attribute == "cpus_allowed" and len(os.sched_getaffinity(sleeper)) < 2:
        pytest.skip("affinity narrowing needs two CPUs")
    ready = profile.spawner_attributes(sleeper)
    CHANGES[attribute](sleeper)

    assert profile.attribute_drift(ready, profile.spawner_attributes(sleeper), None) == attribute


def test_unchanged_spawner_attributes_are_no_drift(sleeper):
    ready = profile.spawner_attributes(sleeper)

    assert profile.attribute_drift(ready, profile.spawner_attributes(sleeper), None) is None


def test_affinity_is_compared_within_the_scope_effective_cpuset():
    ready = {"cpus_allowed": frozenset({0, 1, 2, 3})}
    narrowed_cpuset = {"cpus_allowed": frozenset({0, 1})}

    assert (profile.attribute_drift(ready, narrowed_cpuset, frozenset({0, 1})),
            profile.attribute_drift(ready, narrowed_cpuset, frozenset({0, 1, 2, 3}))) == (None, "cpus_allowed")


# -- containment root from an explicit scope path ------------------------------------------------------------
@pytest.mark.parametrize("path", ["relative/scope", "/sys/fs/cgroup", "/sys/fs/cgroup/a/../b", "/tmp/scope",
                                  ])
def test_scope_path_constructor_refuses_noncanonical_paths(path):
    with pytest.raises(backend.ProviderIsolationBackendUnavailable, match="noncanonical"):
        backend.CgroupV2ContainmentRoot.from_scope_path(Path(path), slot_prefix="run-ref-")


def test_scope_path_constructor_refuses_an_invalid_slot_prefix():
    with pytest.raises(backend.ProviderIsolationInvalidPlan):
        backend.CgroupV2ContainmentRoot.from_scope_path(Path("/sys/fs/cgroup/x"), slot_prefix="../")


def test_scope_root_slots_carry_the_profile_prefix_only():
    try:
        discovered = backend.CgroupV2ContainmentRoot.discover()
    except backend.ProviderIsolationBackendUnavailable as exc:
        pytest.skip(str(exc))
    root = backend.CgroupV2ContainmentRoot.from_scope_path(discovered.path, slot_prefix="run-ref-")
    slot = root.create_slot("pytest-holder-prefix")
    try:
        with pytest.raises(backend.ProviderIsolationStateError):
            root.load_slot("provider-isolation-" + slot.name[len("run-ref-"):])
        assert (slot.name.startswith("run-ref-"), root.load_slot(slot.name).identity_digest,
                root.path, root.identity_digest) == (
            True, slot.identity_digest, discovered.path, discovered.identity_digest)
    finally:
        slot.remove()


def test_discovered_root_keeps_the_provider_slot_prefix():
    try:
        root = backend.CgroupV2ContainmentRoot.discover()
    except backend.ProviderIsolationBackendUnavailable as exc:
        pytest.skip(str(exc))
    slot = root.create_slot("pytest-provider-prefix")
    slot.remove()

    assert slot.name.startswith("provider-isolation-")


def test_launcher_source_runs_without_the_shim_module():
    source = profile.launcher_source()

    assert ("provider_launch_shim" not in source, "def _join_fresh_session_keyring" in source) == (True, True)
