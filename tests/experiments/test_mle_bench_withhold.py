"""MLE-bench family plan, Task 3: the withholding check on an exported agent image
(experiments/mle_bench_tasks/withhold_check.py). Directory trees and small tar files stand in for an export."""

import gzip
import importlib.util
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TINY = ROOT / "tests" / "experiments" / "fixtures" / "mle_bench" / "tiny-tabular"
PUBLIC, PRIVATE, GRADER = TINY / "prepared" / "public", TINY / "prepared" / "private", TINY / "competition"
LEADERBOARD = GRADER / "leaderboard.csv"
ANSWERS = PRIVATE / "answers.csv"
REF = "localhost/mle-tiny-agent@sha256:" + "a" * 64
SMALL = 4096  # a read cap below the size of some planted files, for the cap tests


@pytest.fixture(scope="module")
def wc():
    spec = importlib.util.spec_from_file_location("mle_bench_withhold", ROOT / "experiments" / "mle_bench_tasks" / "withhold_check.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _export(root, files=None):
    """An export stand-in: the agent image's public data at home/data/, a few system files, and `files`."""
    for p in PUBLIC.iterdir():
        _put(root / "home" / "data" / p.name, p.read_bytes())
    _put(root / "etc" / "os-release", b"NAME=Stand-in\n")
    _put(root / "usr" / "bin" / "tool", b"\x7fELF\x00\x01binary")
    for rel, data in (files or {}).items():
        _put(root / rel, data)
    return root


def _put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _run(wc, export, cap=None, **inputs):
    args = dict(private=PRIVATE, grader=GRADER, leaderboard=LEADERBOARD, public=PUBLIC, image_ref=REF) | inputs
    return wc.check(export, **args) if cap is None else wc.check(export, cap=cap, **args)


def _paths(result, kind):
    return sorted(f["path"] for f in result["findings"][kind])


def _rows(path, n=None, start=0):
    lines = path.read_bytes().splitlines(keepends=True)[1:]
    return b"".join(lines[start:] if n is None else lines[start:start + n])


# --- a clean image -------------------------------------------------------------------------------------------------

def test_an_export_holding_only_public_data_and_system_files_passes(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x"))
    assert (result["verdict"], result["image"], all(not v for v in result["findings"].values())) == ("pass", REF, True)


def test_the_result_names_every_kind_of_finding_and_the_caps(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x"))
    assert (sorted(result), sorted(result["findings"]), sorted(result["caps"])) == (
        ["caps", "files_checked", "findings", "image", "verdict"],
        ["benchmark", "grader_hash", "leaderboard_hash", "links_outside", "not_inspected", "private_hash",
         "private_lines", "unreadable"],
        ["archive_depth", "read_bytes", "text_probe_bytes"])


def test_an_export_with_no_file_fails(wc, tmp_path):
    (tmp_path / "x").mkdir()
    assert _run(wc, tmp_path / "x")["verdict"] == "fail"


def test_a_grader_file_identical_to_a_public_file_is_not_a_hit(wc, tmp_path):
    """The competition's description.md is byte for byte the public one, which the agent is given."""
    result = _run(wc, _export(tmp_path / "x", {"srv/description.md": (GRADER / "description.md").read_bytes()}))
    assert result["verdict"] == "pass"


# --- (a) by SHA-256, under any name and at any depth -----------------------------------------------------------------

@pytest.mark.parametrize("source, kind", [(ANSWERS, "private_hash"), (GRADER / "grade.py", "grader_hash"),
                                          (GRADER / "prepare.py", "grader_hash"), (LEADERBOARD, "leaderboard_hash")])
def test_a_withheld_file_is_found_by_hash_under_another_name_at_depth(wc, tmp_path, source, kind):
    result = _run(wc, _export(tmp_path / "x", {"var/cache/a/b/c/notes.bin": source.read_bytes()}))
    assert (result["verdict"], _paths(result, kind)) == ("fail", ["var/cache/a/b/c/notes.bin"])


def test_a_file_larger_than_the_read_cap_is_still_found_by_hash(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"opt/blob.dat": ANSWERS.read_bytes()}), cap=64)
    assert _paths(result, "private_hash") == ["opt/blob.dat"]


# --- (b) private-only lines ----------------------------------------------------------------------------------------

def test_a_file_holding_a_share_of_the_answers_lines_is_found_with_its_count(wc, tmp_path):
    text = b"user,guess\n" + b"some note\n" + _rows(ANSWERS, 7, start=5) + b"more\n"
    result = _run(wc, _export(tmp_path / "x", {"root/work/mine.csv": text}))
    assert result["findings"]["private_lines"] == [{"path": "root/work/mine.csv", "lines": {"answers.csv": 7}}]


def test_one_answers_line_is_a_hit(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"tmp/one.txt": b"x\n" + _rows(ANSWERS, 1, start=3)}))
    assert (result["verdict"], _paths(result, "private_lines")) == ("fail", ["tmp/one.txt"])


def test_the_answers_header_and_blank_lines_are_not_counted(wc, tmp_path):
    """Neither the header nor a blank line occurs in a public file here, so only the rule keeps them out."""
    inputs = {"private": tmp_path / "private", "public": tmp_path / "public", "grader": tmp_path / "grader",
              "leaderboard": tmp_path / "grader" / "leaderboard.csv"}
    _put(inputs["private"] / "answers.csv", b"id,secret_target\n1,a\n\n   \n2,b\n")
    _put(inputs["public"] / "test.csv", b"id\n1\n2\n")
    _put(inputs["leaderboard"], b"team,score\nt,1\n")
    _put(tmp_path / "x" / "tmp" / "h.csv", b"id,secret_target\n\n   \nnote\n")
    assert _run(wc, tmp_path / "x", **inputs)["verdict"] == "pass"


def test_a_private_line_that_also_occurs_in_a_public_file_is_never_a_hit(wc, tmp_path):
    private, public = tmp_path / "private", tmp_path / "public"
    shutil.copytree(PUBLIC, public)
    _put(private / "answers.csv", b"id,y\n1,shared\n2,secret\n")
    _put(public / "extra.csv", b"id,y\n1,shared\n")
    inputs = dict(private=private, public=public)
    shared = _run(wc, _export(tmp_path / "a", {"tmp/f.csv": b"1,shared\n"}), **inputs)
    secret = _run(wc, _export(tmp_path / "b", {"tmp/f.csv": b"2,secret\r\n"}), **inputs)
    assert (shared["verdict"], _paths(secret, "private_lines")) == ("pass", ["tmp/f.csv"])


def test_a_public_file_sharing_most_lines_with_the_training_data_is_not_a_hit(wc, tmp_path):
    """An agent's working copy of train.csv, re-ordered and with a few new rows, holds no answer."""
    rows = (PUBLIC / "train.csv").read_bytes().splitlines(keepends=True)
    text = rows[0] + b"".join(reversed(rows[1:50])) + b"9999,0.1,0.2,1\n8888,0.3,0.4,0\n"
    result = _run(wc, _export(tmp_path / "x", {"root/work/train_copy.csv": text,
                                               "root/work/test_copy.csv": (PUBLIC / "test.csv").read_bytes()}))
    assert result["verdict"] == "pass"


def test_a_large_file_of_an_answers_type_is_not_inspected_and_fails(wc, tmp_path):
    big = b"id,value\n" + b"".join(b"%d,0.5\n" % i for i in range(2000))
    result = _run(wc, _export(tmp_path / "x", {"data/big.csv": big}), cap=SMALL)
    assert (result["verdict"], _paths(result, "not_inspected")) == ("fail", ["data/big.csv"])


def test_a_large_file_of_another_type_is_hashed_only(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"usr/lib/libbig.so": b"\x00" * (SMALL * 3)}), cap=SMALL)
    assert result["verdict"] == "pass"


# --- archives, one level deep --------------------------------------------------------------------------------------

def _tar(members, mode="w"):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode=mode) as tf:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


ARCHIVES = {
    "backup.gz": lambda m: gzip.compress(next(iter(m.values()))),
    "backup.zip": _zip,
    "backup.tar": _tar,
    "backup.tgz": lambda m: _tar(m, "w:gz"),
    "backup.tar.gz": lambda m: _tar(m, "w:gz"),
}


@pytest.mark.parametrize("name", list(ARCHIVES))
def test_the_answers_inside_an_archive_are_found_by_hash(wc, tmp_path, name):
    data = ARCHIVES[name]({"inner/renamed.dat": ANSWERS.read_bytes()})
    result = _run(wc, _export(tmp_path / "x", {f"srv/{name}": data}))
    assert [p.split("!")[0] for p in _paths(result, "private_hash")] == [f"srv/{name}"]


def test_answers_lines_inside_a_zip_member_are_found(wc, tmp_path):
    data = _zip({"notes.txt": b"hello\n" + _rows(ANSWERS, 3)})
    result = _run(wc, _export(tmp_path / "x", {"srv/n.zip": data}))
    assert _paths(result, "private_lines") == ["srv/n.zip!notes.txt"]


def test_a_nested_archive_is_not_inspected_and_fails(wc, tmp_path):
    data = _zip({"inner.zip": _zip({"a.dat": ANSWERS.read_bytes()})})
    result = _run(wc, _export(tmp_path / "x", {"srv/outer.zip": data}))
    assert (result["verdict"], _paths(result, "not_inspected")) == ("fail", ["srv/outer.zip!inner.zip"])


def test_an_archive_over_the_cap_is_not_inspected_and_fails(wc, tmp_path):
    data = _tar({"pad.bin": os.urandom(SMALL * 2)})
    result = _run(wc, _export(tmp_path / "x", {"srv/large.tar": data}), cap=SMALL)
    assert (result["verdict"], _paths(result, "not_inspected")) == ("fail", ["srv/large.tar"])


def test_a_corrupt_archive_fails_with_its_path(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"srv/broken.zip": b"PK\x03\x04 not a zip"}))
    assert (result["verdict"], _paths(result, "unreadable")) == ("fail", ["srv/broken.zip"])


def test_a_public_archive_copied_unchanged_is_not_opened(wc, tmp_path):
    """A public file is given to the agent, so a byte-identical copy is fine, whatever it holds."""
    public = tmp_path / "public"
    shutil.copytree(PUBLIC, public)
    _put(public / "extra.zip", _zip({"x.csv": b"1,2\n"}))
    result = _run(wc, _export(tmp_path / "x", {"home/data/extra.zip": (public / "extra.zip").read_bytes()}),
                  cap=16, public=public)
    assert result["verdict"] == "pass"


# --- (c) the benchmark's package or its competition directory ------------------------------------------------------

@pytest.mark.parametrize("rel, found", [
    ("usr/lib/python3/site-packages/mlebench/__init__.py", "usr/lib/python3/site-packages/mlebench"),
    ("usr/lib/python3/site-packages/mlebench-0.1.dist-info/METADATA", "usr/lib/python3/site-packages/mlebench-0.1.dist-info"),
    ("opt/src/tiny-tabular/readme.txt", "opt/src/tiny-tabular"),
    ("opt/tiny-tabular.tar.gz", "opt/tiny-tabular.tar.gz"),
])
def test_the_benchmarks_package_or_the_competition_by_name_is_found(wc, tmp_path, rel, found):
    data = _tar({"x": b"y"}, "w:gz") if rel.endswith(".gz") else b"pass\n"
    result = _run(wc, _export(tmp_path / "x", {rel: data}))
    assert (result["verdict"], _paths(result, "benchmark")) == ("fail", [found])


# --- fail closed ---------------------------------------------------------------------------------------------------

def test_an_unreadable_file_fails_with_its_path(wc, tmp_path):
    export = _export(tmp_path / "x", {"root/secret": b"x"})
    (export / "root" / "secret").chmod(0)
    try:
        result = _run(wc, export)
    finally:
        (export / "root" / "secret").chmod(0o600)
    assert (result["verdict"], _paths(result, "unreadable")) == ("fail", ["root/secret"])


def test_an_unreadable_directory_fails_with_its_path(wc, tmp_path):
    export = _export(tmp_path / "x", {"root/locked/f": b"x"})
    (export / "root" / "locked").chmod(0)
    try:
        result = _run(wc, export)
    finally:
        (export / "root" / "locked").chmod(0o700)
    assert (result["verdict"], _paths(result, "unreadable")) == ("fail", ["root/locked"])


def test_a_special_file_fails_with_its_path(wc, tmp_path):
    export = _export(tmp_path / "x")
    os.mkfifo(export / "pipe")
    assert _paths(_run(wc, export), "unreadable") == ["pipe"]


def test_a_symbolic_link_is_not_followed_and_one_leaving_the_export_fails(wc, tmp_path):
    export = _export(tmp_path / "x")
    (export / "etc" / "answers").symlink_to(ANSWERS)  # absolute: read inside the image, it does not leave it
    (export / "etc" / "up").symlink_to("../../../outside")
    result = _run(wc, export)
    assert (_paths(result, "private_hash"), _paths(result, "links_outside")) == ([], ["etc/up"])


def test_a_link_inside_the_export_passes(wc, tmp_path):
    export = _export(tmp_path / "x")
    (export / "etc" / "rel").symlink_to("../home/data/train.csv")
    (export / "etc" / "abs").symlink_to("/usr/bin/tool")
    assert _run(wc, export)["verdict"] == "pass"


# --- a tar export, read as a stream --------------------------------------------------------------------------------

def _as_tar(root, out, prefix="./"):
    with tarfile.open(out, "w") as tf:
        for path in sorted(root.rglob("*")):
            tf.add(path, arcname=prefix + path.relative_to(root).as_posix(), recursive=False)
    return out


def test_a_tar_export_gives_the_same_findings_as_its_directory(wc, tmp_path):
    export = _export(tmp_path / "x", {"var/a.bin": ANSWERS.read_bytes(), "tmp/b.csv": _rows(ANSWERS, 2),
                                      "usr/lib/mlebench/x.py": b"1\n"})
    (export / "etc" / "up").symlink_to("../../outside")
    from_dir, from_tar = _run(wc, export), _run(wc, _as_tar(export, tmp_path / "x.tar"))
    assert (from_tar["findings"], from_tar["files_checked"]) == (from_dir["findings"], from_dir["files_checked"])


def test_a_clean_tar_export_passes(wc, tmp_path):
    assert _run(wc, _as_tar(_export(tmp_path / "x"), tmp_path / "x.tar"))["verdict"] == "pass"


def test_a_hard_link_in_a_tar_export_is_checked_through_its_target(wc, tmp_path):
    export = _export(tmp_path / "x", {"var/a.bin": ANSWERS.read_bytes()})
    os.link(export / "var" / "a.bin", export / "var" / "b.bin")
    assert _paths(_run(wc, _as_tar(export, tmp_path / "x.tar")), "private_hash") == ["var/a.bin"]


def test_a_hard_link_to_a_member_not_in_the_tar_fails(wc, tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w") as tf:
        info = tarfile.TarInfo("etc/hosts")
        info.type, info.linkname = tarfile.LNKTYPE, "etc/missing"
        tf.addfile(info)
    _put(tmp_path / "x.tar", buf.getvalue())
    assert _paths(_run(wc, tmp_path / "x.tar"), "unreadable") == ["etc/hosts"]


def test_a_tar_member_cut_short_fails_with_its_path(wc, tmp_path):
    _put(tmp_path / "cut.tar", _tar({"etc/a": b"x", "var/pad.bin": os.urandom(20000)})[:12000])
    assert _paths(_run(wc, tmp_path / "cut.tar"), "unreadable") == ["var/pad.bin"]


def test_an_export_that_is_not_a_tar_fails_with_its_path(wc, tmp_path):
    _put(tmp_path / "x.tar", b"\x01" * 2048)
    assert _paths(_run(wc, tmp_path / "x.tar"), "unreadable") == [str(tmp_path / "x.tar")]


# --- the image reference and the command line ----------------------------------------------------------------------

@pytest.mark.parametrize("ref", ["localhost/mle-tiny-agent:latest", "localhost/x@sha256:" + "a" * 63,
                                 "localhost/x@sha256:" + "A" * 64, "localhost/x@sha256:" + "a" * 65, ""])
def test_an_image_reference_not_pinned_by_digest_is_refused(wc, tmp_path, ref):
    with pytest.raises(wc.Refused):
        _run(wc, _export(tmp_path / "x"), image_ref=ref)


def _cli(export, out, ref=REF):
    cmd = [sys.executable, "-m", "experiments.mle_bench_tasks.withhold_check", "--image-ref", ref,
           "--export", str(export), "--private", str(PRIVATE), "--grader", str(GRADER), "--leaderboard",
           str(LEADERBOARD), "--public", str(PUBLIC), "--out", str(out)]
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True).returncode


def test_the_command_line_exits_0_on_a_pass_and_1_on_a_fail_and_writes_the_result(tmp_path):
    clean, dirty = _export(tmp_path / "a"), _export(tmp_path / "b", {"x/y": ANSWERS.read_bytes()})
    codes = _cli(clean, tmp_path / "a.json"), _cli(dirty, tmp_path / "b.json")
    verdicts = [json.loads((tmp_path / f).read_text())["verdict"] for f in ("a.json", "b.json")]
    assert (codes, verdicts) == ((0, 1), ["pass", "fail"])


def test_the_command_line_refuses_an_unpinned_reference_and_writes_nothing(tmp_path):
    code = _cli(_export(tmp_path / "a"), tmp_path / "a.json", ref="localhost/x:latest")
    assert (code, (tmp_path / "a.json").exists()) == (2, False)
