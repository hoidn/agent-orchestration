"""Prepare-selected ledger history publication states (docs/design/verified_iteration_drain.md)."""

import errno
import hashlib
import importlib.util
import json
import os
import signal
import sys
import tempfile
from pathlib import Path

import pytest

from tests.test_verified_iteration_drain import (
    INPUTS,
    PREPARE,
    ROOT,
    STATE_ROOT,
    WORK_ROOT,
    _init_workspace,
    _prepare,
    _prepare_args,
    _run_script,
)
from tests.test_workflow_evaluated_invalidate import _tree_bytes

LEDGER = "# Ledger ü\r\niter 0 | ACCEPTED | a..b | note  \r\nno final newline".encode("utf-8")
ABRUPT = """import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("prepare_abrupt", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
os.link = lambda source, destination: os._exit(75)
sys.argv = sys.argv[1:]
module.main()
"""


def _seed_ledger(workspace: Path, raw: bytes = LEDGER) -> Path:
    ledger = workspace / WORK_ROOT / "ledger.md"
    (ledger.parent / "blocked").mkdir(parents=True)
    (workspace / STATE_ROOT / "iterations/0").mkdir(parents=True)
    ledger.write_bytes(raw)
    final = workspace / INPUTS / f"{hashlib.sha256(raw).hexdigest()}.md"
    final.parent.mkdir()
    return final


def _prepare_in_process(workspace: Path, monkeypatch, *, bundle: str | None = None) -> int:
    monkeypatch.chdir(workspace)
    monkeypatch.setattr(sys, "argv", [PREPARE, *_prepare_args()])
    if bundle is not None:
        monkeypatch.setenv("ORCHESTRATOR_OUTPUT_BUNDLE_PATH", bundle)
    spec = importlib.util.spec_from_file_location("prepare_verified_iteration_under_test", ROOT / PREPARE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.main()


def _is_closed(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return True
    return False


def test_prepare_publishes_one_raw_ledger_read_through_a_closed_private_temporary(tmp_path, monkeypatch):
    workspace = _init_workspace(tmp_path)
    final = _seed_ledger(workspace)
    (final.parent / ".abandoned.tmp").write_bytes(b"partial")
    temporaries, links, reads = [], [], []
    mkstemp, link, read_bytes = tempfile.mkstemp, os.link, Path.read_bytes

    def staged(*args, **kwargs):
        temporaries.append(mkstemp(*args, **kwargs))
        return temporaries[-1]

    def publish(source, destination):
        fd, name = temporaries[-1]
        links.append((_is_closed(fd), Path(source) == Path(name), Path(source).parent == final.parent,
                      Path(source).read_bytes(), os.stat(source).st_mode & 0o777, Path(destination) == final))
        return link(source, destination)

    monkeypatch.setattr(tempfile, "mkstemp", staged)
    monkeypatch.setattr(os, "link", publish)
    monkeypatch.setattr(Path, "read_bytes", lambda path: reads.append(path.name) or read_bytes(path))
    assert _prepare_in_process(workspace, monkeypatch) == 0
    assert links == [(True, True, True, LEDGER, 0o600, True)]
    assert reads.count("ledger.md") == 1
    assert final.read_bytes() == LEDGER == (workspace / WORK_ROOT / "ledger.md").read_bytes()
    assert sorted(path.name for path in final.parent.iterdir()) == [".abandoned.tmp", final.name]
    assert (final.parent / ".abandoned.tmp").read_bytes() == b"partial"
    order = json.loads((workspace / STATE_ROOT / "iterations/0/work-order.json").read_text(encoding="utf-8"))
    assert (order["ledger_path"], order["ledger_input_path"]) == (f"{WORK_ROOT}/ledger.md", final.relative_to(workspace).as_posix())


@pytest.mark.parametrize("arrival", ["before", "during_link"])
def test_prepare_reuses_an_equal_regular_final_without_rewriting_it(tmp_path, monkeypatch, arrival):
    workspace = _init_workspace(tmp_path)
    final = _seed_ledger(workspace)
    link, winners = os.link, []

    def arrive():
        final.write_bytes(LEDGER)
        os.utime(final, ns=(10**9, 10**9))
        winners.append(final.stat())

    def race(source, destination):
        arrive()
        return link(source, destination)

    if arrival == "before":
        arrive()
    else:
        monkeypatch.setattr(os, "link", race)
    assert _prepare_in_process(workspace, monkeypatch) == 0
    (winner,) = winners
    assert (final.stat().st_ino, final.stat().st_mtime_ns, final.stat().st_nlink) == (winner.st_ino, winner.st_mtime_ns, 1)
    assert [path.name for path in final.parent.iterdir()] == [final.name]


def _install_unusable_final(kind: str, final: Path, monkeypatch) -> None:
    link, open_ = os.link, os.open

    def race(source, destination):
        final.write_bytes(b"winner")
        return link(source, destination)

    def denied(path, *args, **kwargs):
        if Path(path) == final:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return open_(path, *args, **kwargs)

    if kind == "different":
        final.write_bytes(b"different")
    elif kind == "extended":
        final.write_bytes(LEDGER + b"\n")
    elif kind == "symlink":
        (final.parent / "equal.md").write_bytes(LEDGER)
        final.symlink_to("equal.md")
    elif kind == "directory":
        final.mkdir()
    elif kind == "fifo":
        os.mkfifo(final)
    elif kind == "unreadable":
        final.write_bytes(LEDGER)
        monkeypatch.setattr(os, "open", denied)
    else:
        monkeypatch.setattr(os, "link", race)


def _refuse_within_ten_seconds(workspace: Path, monkeypatch) -> SystemExit:
    def blocked(*_):
        pytest.fail("Prepare blocked opening the final")

    previous = signal.signal(signal.SIGALRM, blocked)
    signal.alarm(10)
    try:
        with pytest.raises(SystemExit) as refusal:
            _prepare_in_process(workspace, monkeypatch, bundle="state/bundle.json")
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)
    return refusal.value


@pytest.mark.parametrize(
    "kind", ["different", "extended", "symlink", "directory", "fifo", "unreadable", "different_race"]
)
def test_prepare_refuses_an_unusable_final_and_preserves_it(tmp_path, monkeypatch, kind):
    workspace = _init_workspace(tmp_path)
    final = _seed_ledger(workspace)
    _install_unusable_final(kind, final, monkeypatch)
    before = _tree_bytes(workspace)
    assert _refuse_within_ten_seconds(workspace, monkeypatch).code not in (0, None)
    after = _tree_bytes(workspace)
    if kind == "different_race":
        before[f"{INPUTS}/{final.name}"] = ("file", b"winner")
    assert after == before
    assert not (workspace / "state/bundle.json").exists()
    assert not (workspace / STATE_ROOT / "iterations/0/work-order.json").exists()


@pytest.mark.parametrize("seam", ["link", "write"])
def test_prepare_recoverable_failure_before_publication_cleans_only_its_temporary(tmp_path, monkeypatch, seam):
    workspace = _init_workspace(tmp_path)
    final = _seed_ledger(workspace)
    (final.parent / ".abandoned.tmp").write_bytes(b"partial")
    fdopen = os.fdopen

    def unsupported(source, destination):
        raise OSError(errno.EPERM, "Operation not permitted", str(destination))

    def partial(fd, *args, **kwargs):
        handle = fdopen(fd, *args, **kwargs)
        if Path(os.readlink(f"/proc/self/fd/{fd}")).parent == final.parent:
            handle.write(LEDGER[:3])
            handle.close()
            raise OSError(errno.ENOSPC, "No space left on device")
        return handle

    with monkeypatch.context() as patched:
        if seam == "link":
            patched.setattr(os, "link", unsupported)
        else:
            patched.setattr(os, "fdopen", partial)
        with pytest.raises(OSError):
            _prepare_in_process(workspace, monkeypatch)
    assert [path.name for path in final.parent.iterdir()] == [".abandoned.tmp"]
    assert not (workspace / STATE_ROOT / "iterations/0/work-order.json").exists()
    order = _prepare(workspace)
    assert (workspace / order["ledger_input_path"]).read_bytes() == LEDGER
    assert sorted(path.name for path in final.parent.iterdir()) == [".abandoned.tmp", final.name]
    assert (final.parent / ".abandoned.tmp").read_bytes() == b"partial"


def test_prepare_retry_ignores_a_temporary_abandoned_by_an_abrupt_exit(tmp_path):
    workspace = _init_workspace(tmp_path)
    final = _seed_ledger(workspace)
    abrupt = _run_script(workspace, "-c", ABRUPT, str(ROOT / PREPARE), *_prepare_args(), check=False)
    assert abrupt.returncode == 75, abrupt.stderr
    (residue,) = final.parent.iterdir()
    residue_stat = residue.stat()
    assert not (workspace / STATE_ROOT / "iterations/0/work-order.json").exists()
    order = _prepare(workspace)
    assert workspace / order["ledger_input_path"] == final and final.read_bytes() == LEDGER
    assert sorted(final.parent.iterdir()) == sorted([residue, final])
    assert (residue.stat().st_ino, residue.stat().st_mtime_ns) == (residue_stat.st_ino, residue_stat.st_mtime_ns)
    assert residue.stat().st_ino != final.stat().st_ino


def test_prepare_retry_after_publication_reuses_the_copy_and_new_bytes_get_a_new_name(tmp_path, monkeypatch):
    workspace = _init_workspace(tmp_path)
    final = _seed_ledger(workspace)
    bundle = workspace / "state/bundle.json"
    write_text = Path.write_text

    def lost(path, *args, **kwargs):
        if path == bundle:
            raise OSError(errno.EIO, "Input/output error", str(path))
        return write_text(path, *args, **kwargs)

    with monkeypatch.context() as patched:
        patched.setattr(Path, "write_text", lost)
        with pytest.raises(OSError):
            _prepare_in_process(workspace, monkeypatch, bundle="state/bundle.json")
    os.utime(final, ns=(10**9, 10**9))
    published = final.stat()
    assert final.read_bytes() == LEDGER and not bundle.exists()
    env = {"ORCHESTRATOR_OUTPUT_BUNDLE_PATH": "state/bundle.json"}
    assert _prepare(workspace, env=env)["ledger_input_path"] == final.relative_to(workspace).as_posix()
    assert (final.stat().st_ino, final.stat().st_mtime_ns) == (published.st_ino, published.st_mtime_ns)
    appended = LEDGER + b"\niter 1 | DONE\n"
    (workspace / WORK_ROOT / "ledger.md").write_bytes(appended)
    order = _prepare(workspace, env=env)
    renewed = f"{INPUTS}/{hashlib.sha256(appended).hexdigest()}.md"
    assert order["ledger_input_path"] == renewed
    assert json.loads(bundle.read_text(encoding="utf-8"))["ledger_input_path"] == renewed
    assert (workspace / renewed).read_bytes() == appended and final.read_bytes() == LEDGER
