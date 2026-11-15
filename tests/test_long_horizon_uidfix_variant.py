"""The pure parts of the labelled variant's build (`experiments/long_horizon_tasks/uidfix_variant.py`)."""

import importlib.util
import io
import tarfile
from pathlib import Path

KIT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks"
_spec = importlib.util.spec_from_file_location("lh_uidfix_variant", KIT / "uidfix_variant.py")
variant = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(variant)

BOUND = b"uid = 10000 + secrets.randbelow(1000000000)\n"


def _tar(files, mtime=0):
    """A tar stream of (name, bytes, mode) regular files, as `podman export` writes one."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tar:
        for name, data, mode in files:
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), mode, mtime
            tar.addfile(info, io.BytesIO(data))
    raw.seek(0)
    return raw


def test_the_tree_keeps_each_files_kind_mode_owner_and_sha256_and_the_watched_files_text():
    tree, text = variant.tree(_tar([("tests/app_worker.py", BOUND, 0o644), ("etc/x", b"x", 0o600)]))
    assert (sorted(tree), tree["etc/x"][1], text) == (["etc/x", "tests/app_worker.py"], 0o600, BOUND.decode())


def test_only_the_changed_file_differs_when_two_trees_differ_in_its_content_and_in_modification_times():
    before = variant.tree(_tar([("tests/app_worker.py", BOUND, 0o644), ("etc/x", b"x", 0o600)]))[0]
    after = _tar([("tests/app_worker.py", BOUND.replace(b"1000000000", b"55000"), 0o644), ("etc/x", b"x", 0o600)],
                 mtime=1700000000)
    assert variant.differing(before, variant.tree(after)[0]) == ["tests/app_worker.py"]


def test_a_mode_change_or_a_new_file_also_differs():
    before = variant.tree(_tar([("etc/x", b"x", 0o600)]))[0]
    after = variant.tree(_tar([("etc/x", b"x", 0o644), ("etc/y", b"", 0o644)]))[0]
    assert variant.differing(before, after) == ["etc/x", "etc/y"]


def test_the_recipe_builds_from_the_pinned_digest_and_refuses_unless_one_line_holds_the_bound():
    recipe = variant.recipe("harborframework/terminal-bench:v-verifier-1@sha256:ab")
    assert (recipe.splitlines()[0], "grep -cF 'secrets.randbelow(1000000000)' /tests/app_worker.py" in recipe) == (
        "FROM docker.io/harborframework/terminal-bench:v-verifier-1@sha256:ab", True)


def test_the_diff_shows_the_one_changed_line():
    assert variant.diff_text(BOUND.decode(), BOUND.decode().replace("1000000000", "55000")).splitlines()[2:] == [
        "@@ -1 +1 @@", "-uid = 10000 + secrets.randbelow(1000000000)", "+uid = 10000 + secrets.randbelow(55000)"]
