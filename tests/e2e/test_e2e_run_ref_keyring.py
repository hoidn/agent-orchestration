"""F3b-keyring witnesses (design row F3b-2, Task 5b) on the throwaway holder.

The test process joins its own anonymous session keyring and adds a canary
key, so no host keyring is touched. In the profile launch (launcher joins a
fresh session keyring, `--seccomp` key-syscall filter, `/proc/keys` and
`/proc/key-users` masked) a leaf's key syscalls return EPERM, both files are
unreadable and an `add_key` loop adds no key. Diagnostic launches without the
filter, and without both the filter and the join (positive control), show
what the profile removes. Fixtures: `tests/e2e/run_ref_fixtures.py`.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.providers import provider_launch_shim as shim
from tests.e2e.run_ref_fixtures import launch, sealed_rootfs  # noqa: F401 (fixtures)
from tests.e2e.run_ref_holder import Holder, key_syscall_filter

pytestmark = pytest.mark.e2e

KEY_PROBE = r"""
import ctypes, errno, json, mmap, os, signal, sys
libc = ctypes.CDLL(None, use_errno=True)
L, P = ctypes.c_long, ctypes.c_char_p
def call(number, *args):
    result = libc.syscall(L(number), *args)
    return result if result >= 0 else errno.errorcode[ctypes.get_errno()]
def keyctl(op, *args):
    return call(250, L(op), *(L(a) for a in args))
def opened(path):
    try:
        with open(path, "rb") as handle:
            return "read %d bytes" % len(handle.read())
    except OSError as exc:
        return errno.errorcode[exc.errno]
def i386_getpid():
    # int 0x80 enters the kernel with AUDIT_ARCH_I386, which the filter kills.
    page = mmap.mmap(-1, 4096, prot=mmap.PROT_READ | mmap.PROT_WRITE | mmap.PROT_EXEC)
    page.write(bytes([0xB8, 20, 0, 0, 0, 0xCD, 0x80, 0xC3]))
    function = ctypes.CFUNCTYPE(ctypes.c_int)(ctypes.addressof(ctypes.c_char.from_buffer(page)))
    child = os.fork()
    if child == 0:
        os._exit(0 if function() > 0 else 1)
    status = os.waitpid(child, 0)[1]
    return signal.Signals(os.WTERMSIG(status)).name if os.WIFSIGNALED(status) else "exit %d" % os.WEXITSTATUS(status)
mode = sys.argv[1]
report = {}
if mode == "control":  # keyring reads first: the syscall branch below adds a key in the control
    session = keyctl(0, -3, 0)  # KEYCTL_GET_KEYRING_ID of the session keyring
    canary = int(sys.argv[2])
    report = {"session": session, "session_read_bytes": keyctl(11, session, 0, 0),  # KEYCTL_READ: 4 bytes per key
              "canary_read": keyctl(11, canary, 0, 0), "canary_link": keyctl(8, canary, -3)}  # KEYCTL_LINK
if mode in ("syscalls", "keyring", "control"):
    for name, number in (("add_key", 248), ("request_key", 249), ("keyctl", 250)):
        for abi, bit in (("native", 0), ("x32", 0x40000000)):
            args = {"add_key": (P(b"user"), P(b"runref-probe"), P(b"x"), L(1), L(-3)),
                    "request_key": (P(b"user"), P(b"runref-absent"), P(None), L(0)),
                    "keyctl": (L(0), L(-3), L(0))}[name]
            result = call(bit | number, *args)
            report[f"{name}:{abi}"] = result if isinstance(result, str) else "ok"
    report["getpid"] = "ok" if call(39) == os.getpid() else "wrong"
    report["i386_int80"] = i386_getpid()
if mode == "keyring":
    report["/proc/keys"], report["/proc/key-users"] = opened("/proc/keys"), opened("/proc/key-users")
if mode == "quota":
    report["add_key_ok"] = sum(not isinstance(call(248, P(b"user"), P(b"q%d" % i), P(b"x"), L(1), L(-3)), str)
                               for i in range(50))
print(json.dumps(report))
"""

KEYCTL = 250
KEY_SPEC_SESSION_KEYRING = -3


def _keyctl(*args: int) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    result = libc.syscall(ctypes.c_long(KEYCTL), *(ctypes.c_long(a) for a in args))
    if result < 0:
        raise OSError(ctypes.get_errno(), f"keyctl{args}")
    return result


@pytest.fixture(scope="module")
def canary_keyring(sealed_rootfs):
    """The test process's own anonymous session keyring with a canary key; no host keyring is touched."""
    if os.uname().machine != "x86_64":
        pytest.skip("the key-syscall filter is x86_64-only")
    shim._join_fresh_session_keyring()
    libc = ctypes.CDLL(None, use_errno=True)
    canary = libc.syscall(ctypes.c_long(248), b"user", b"runref-canary", b"canary-payload",
                          ctypes.c_size_t(14), ctypes.c_long(KEY_SPEC_SESSION_KEYRING))
    assert canary > 0, ctypes.get_errno()
    return {"session": _keyctl(0, KEY_SPEC_SESSION_KEYRING, 0), "canary": canary}


def _key_users_count() -> int:
    """The host user's key count (`qnkeys`) from the host's /proc/key-users."""
    [row] = [line for line in Path("/proc/key-users").read_text().splitlines()
             if line.split(":")[0].strip() == str(os.getuid())]
    return int(row.split()[3].split("/")[0])


def _probe(holder: Holder, name: str, *args: str) -> dict:
    result = holder.run(name, f"exec python3 /run/runref/{name}/probe.py {' '.join(args)}\n",
                        files={"probe.py": KEY_PROBE})
    assert result["outcome"] == "exited", result
    return json.loads(result["stdout"])


LOAD_SHIM = ("import ctypes, importlib.util, sys\n"
             "spec = importlib.util.spec_from_file_location('provider_launch_shim', sys.argv[1])\n"
             "shim = importlib.util.module_from_spec(spec)\nspec.loader.exec_module(shim)\n")


def _host_probe(install: str) -> dict:
    """Run KEY_PROBE in a fresh host interpreter after `install` (the shim is loaded by path, as the launcher does)."""
    script = LOAD_SHIM + install + "\nsys.argv = ['probe', 'syscalls']\n" + KEY_PROBE
    done = subprocess.run([sys.executable, "-I", "-c", script, shim.__file__], capture_output=True, text=True,
                          timeout=30)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


EXPECTED_FILTER = {"add_key:native": "EPERM", "add_key:x32": "EPERM", "request_key:native": "EPERM",
                   "request_key:x32": "EPERM", "keyctl:native": "EPERM", "keyctl:x32": "EPERM",
                   "getpid": "ok", "i386_int80": "SIGSYS"}


def test_harness_key_filter_has_the_shim_filter_semantics(canary_keyring):
    shim_installed = _host_probe("shim._install_key_syscall_filter()")
    harness_installed = _host_probe(
        f"raw = bytes.fromhex('{key_syscall_filter().hex()}')\n"
        "array = (shim._SockFilter * (len(raw) // 8)).from_buffer_copy(raw)\n"
        "program = shim._SockFprog(len=len(array), filter=array)\n"
        "libc = ctypes.CDLL(None, use_errno=True)\n"
        "assert libc.prctl(shim._PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) == 0\n"
        "assert libc.prctl(shim._PR_SET_SECCOMP, shim._SECCOMP_MODE_FILTER, ctypes.byref(program), 0, 0) == 0")
    unfiltered = _host_probe("")

    assert {"shim": shim_installed, "harness": harness_installed,
            "unfiltered_differs": {k: v for k, v in unfiltered.items() if v != EXPECTED_FILTER[k]} != {}} == {
        "shim": EXPECTED_FILTER, "harness": EXPECTED_FILTER, "unfiltered_differs": True}, unfiltered


def test_holder_keyring_is_fresh_and_key_syscalls_are_refused(launch, canary_keyring):
    holder = launch()
    leaf = _probe(holder, "keyring", "keyring")
    before = _key_users_count()
    quota = _probe(holder, "quota", "quota")
    after = _key_users_count()
    control = launch(key_filter=False)  # diagnostic launch, identical except for --seccomp
    control_leaf = _probe(control, "control", "control", str(canary_keyring["canary"]))
    # Positive control (no join, no filter): the probe does see the canary when it is reachable.
    reachable = _probe(launch(key_filter=False, join_keyring=False), "reachable", "control",
                       str(canary_keyring["canary"]))

    assert {
        "leaf": leaf,
        "quota": (quota["add_key_ok"], after - before < 50),  # other same-uid processes may add keys meanwhile
        "control_session_is_not_the_test_process": control_leaf["session"] != canary_keyring["session"],
        "control_session_holds_no_key": control_leaf["session_read_bytes"],
        "control_canary": (control_leaf["canary_read"], control_leaf["canary_link"]),
        "control_key_syscalls": (control_leaf["add_key:native"], control_leaf["keyctl:native"]),
        "positive_control": (reachable["session"] == canary_keyring["session"], reachable["canary_read"]),
    } == {
        "leaf": EXPECTED_FILTER | {"/proc/keys": "EACCES", "/proc/key-users": "EACCES"},
        "quota": (0, True),
        "control_session_is_not_the_test_process": True,
        "control_session_holds_no_key": 0,
        "control_canary": ("EACCES", "EACCES"),
        "control_key_syscalls": ("ok", "ok"),  # so the filter is what refuses them in the profile
        "positive_control": (True, len(b"canary-payload")),
    }, (control_leaf, reachable, canary_keyring)
