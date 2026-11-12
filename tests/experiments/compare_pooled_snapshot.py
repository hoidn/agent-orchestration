"""Build the comparison harness `world` and `pooled` fixtures once per worker and restore them per test.

`pooled` costs about seven seconds (five stand-in agent runs through the real shims, a pool of
twelve clones) and every state it holds carries absolute paths, so it cannot be relocated. Instead the
template is built at fixed paths once per module, snapshotted, and each test starts by replacing those
paths with a fresh copy of the snapshot: the tree a test sees is byte-for-byte what a rebuild gives,
except that the random draw of the reviewed_change stages is made once per worker.
"""

import copy
import shutil
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.experiments import compare_harness_support as support

_KEYS = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
         "CLAUDE_CODE_OAUTH_TOKEN_FILE")


def _snapshot(world, destination):
    """Copy world.tmp and world.outside; directories that are not listable are copied open and their
    modes are kept to be put back by `_restore`."""
    hidden = {}

    def open_hidden(directory, root):
        mode = stat.S_IMODE(directory.stat().st_mode)
        if not mode & 0o400:
            hidden[(root, directory.relative_to(root))] = mode
            directory.chmod(0o755)
        for child in directory.iterdir():
            if child.is_dir() and not child.is_symlink():
                open_hidden(child, root)

    copies = {}
    for name, root in (("tmp", world.tmp), ("outside", world.outside)):
        open_hidden(root, root)
        copies[name] = destination / name
        shutil.copytree(root, copies[name], symlinks=True)
    modes = [(name, rel, mode) for (root, rel), mode in hidden.items()
             for name, base in (("tmp", world.tmp), ("outside", world.outside)) if base == root]
    return SimpleNamespace(copies=copies, modes=modes)


def _restore(snapshot, world):
    roots = {"tmp": world.tmp, "outside": world.outside}
    for name, root in roots.items():
        if root.exists():
            support.open_up(root)
            shutil.rmtree(root)
        shutil.copytree(snapshot.copies[name], root, symlinks=True)
    for name, rel, mode in snapshot.modes:
        (roots[name] / rel).chmod(mode)


@pytest.fixture(scope="module")
def _template(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    generator = support.world._get_wrapped_function()(tmp_path_factory.mktemp("template"), patch)
    live = next(generator)
    plain = _snapshot(live, tmp_path_factory.mktemp("plain"))
    pooled = support.pooled._get_wrapped_function()(live)
    full = _snapshot(live, tmp_path_factory.mktemp("full"))
    patch.undo()
    yield SimpleNamespace(live=live, plain=plain, full=full, pooled=pooled)
    next(generator, None)


@pytest.fixture
def world(request, _template, monkeypatch):
    live = _template.live
    _restore(_template.full if "pooled" in request.fixturenames else _template.plain, live)
    monkeypatch.setenv("COMPARE_SANDBOX", str(live.sandbox_config))
    monkeypatch.setenv("HOME", str(live.empty_home))
    monkeypatch.setenv("CODEX_HOME", str(live.empty_home / ".codex"))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(live.empty_home / ".claude"))
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    return SimpleNamespace(**vars(live))


@pytest.fixture
def pooled(world, _template):
    built = _template.pooled
    return SimpleNamespace(out=built.out, mapping=copy.deepcopy(built.mapping), failed=built.failed)
