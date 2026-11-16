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
    args = dict(competition="tiny-tabular", private=PRIVATE, grader=GRADER, leaderboard=LEADERBOARD, public=PUBLIC,
                image_ref=REF) | inputs
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
    assert (sorted(result), sorted(result["findings"]), sorted(result["caps"]), result["limits"]) == (
        ["caps", "check_sha256", "competition", "exempted", "exemptions_sha256", "exemptions_unused", "files_checked",
         "findings", "image", "inputs", "limits", "verdict"],
        ["benchmark", "export_incomplete", "grader_hash", "leaderboard_hash", "links_outside", "not_inspected",
         "private_hash", "private_lines", "unreadable", "withheld_file"],
        ["archive_bytes", "archive_depth", "line_bytes"], list(wc.LIMITS))


def _tree_digest(root):
    import hashlib
    text = "".join(f"{p.relative_to(root).as_posix()}\0{hashlib.sha256(p.read_bytes()).hexdigest()}\n"
                   for p in sorted(root.rglob("*")) if p.is_file())
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def test_the_result_binds_the_competition_every_input_and_the_checks_own_code(wc, tmp_path):
    import hashlib
    withheld = tmp_path / "raw"
    _put(withheld / "train.csv", b"raw,rows\n")
    result = _run(wc, _export(tmp_path / "x"), withheld=[withheld])
    sha = lambda p: "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    assert (result["competition"], result["inputs"], result["check_sha256"]) == ("tiny-tabular", {
        "private": _tree_digest(PRIVATE), "grader": _tree_digest(GRADER), "public": _tree_digest(PUBLIC),
        "leaderboard": sha(LEADERBOARD), "withheld": [_tree_digest(withheld)]}, sha(Path(wc.__file__)))


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


# --- (b) private-only lines ----------------------------------------------------------------------------------------

def test_a_file_holding_a_share_of_the_answers_lines_is_found_with_its_count(wc, tmp_path):
    text = b"user,guess\n" + b"some note\n" + _rows(ANSWERS, 7, start=5) + b"more\n"
    result = _run(wc, _export(tmp_path / "x", {"root/work/mine.csv": text}))
    assert result["findings"]["private_lines"] == [{"path": "root/work/mine.csv", "lines": {"answers.csv": 7}}]


def test_one_answers_line_is_a_hit(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"tmp/one.txt": b"x\n" + _rows(ANSWERS, 1, start=3)}))
    assert (result["verdict"], _paths(result, "private_lines")) == ("fail", ["tmp/one.txt"])


def test_the_answers_header_and_blank_lines_are_not_counted(wc, tmp_path):
    """The public directory is empty here, so neither the header nor a blank line occurs in a public file: only the
    rule keeps them out."""
    inputs = {"private": tmp_path / "private", "public": tmp_path / "public", "grader": tmp_path / "grader",
              "leaderboard": tmp_path / "grader" / "leaderboard.csv"}
    _put(inputs["private"] / "answers.csv", b"id,secret_target\n1,a\n\n   \n2,b\n")
    inputs["public"].mkdir()
    _put(inputs["leaderboard"], b"team,score\nt,1\n")
    _put(inputs["grader"] / "grade.py", b"def grade(s, a):\n    return 0.0\n")
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


def _filler(size):
    """Public-looking rows (never an answers line) of about `size` bytes."""
    row = b"%07d,0.12345,0.67890,1\n"
    return b"".join(row % i for i in range(size // len(row % 0)))


def test_a_private_line_near_the_end_of_a_file_far_over_the_cap_is_found(wc, tmp_path):
    """Read as a stream, whatever the size: the line sits across a read-chunk boundary, 3 MiB into a 4 MiB file."""
    line, start = _rows(ANSWERS, 1, start=9), 3 * wc.CHUNK - 3
    head = _filler(3 * wc.CHUNK)
    head = head[:head.rindex(b"\n", 0, start - 1) + 1]
    data = head + b"z" * (start - len(head) - 1) + b"\n" + line + _filler(wc.CHUNK)
    assert data.index(line) == start
    result = _run(wc, _export(tmp_path / "x", {"root/big.csv": data}), cap=wc.CHUNK // 4)
    assert result["findings"]["private_lines"] == [{"path": "root/big.csv", "lines": {"answers.csv": 1}}]


def test_a_large_clean_table_passes(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"root/big.csv": _filler(3 * wc.CHUNK)}), cap=wc.CHUNK // 4)
    assert result["verdict"] == "pass"


def test_a_line_over_the_line_cap_is_not_compared_and_the_next_line_is(wc, tmp_path):
    first, second = _rows(ANSWERS, 1, start=2), _rows(ANSWERS, 1, start=4)
    data = b"x" * (wc.LINE_CAP + wc.CHUNK) + first + second
    result = _run(wc, _export(tmp_path / "x", {"root/long.txt": data}))
    assert result["findings"]["private_lines"] == [{"path": "root/long.txt", "lines": {"answers.csv": 1}}]


NUL = b"\x00\x01binary\x00"


@pytest.mark.parametrize("name, before, found", [
    ("x.log", NUL, True),  # a table or text type: every line, NUL bytes notwithstanding
    ("x.csv", NUL, True),
    ("x.yaml", NUL, True),
    ("notes", b"text\n" * 2000 + NUL, True),  # no suffix and no NUL in its first block
    ("notes", NUL, False),  # no suffix, a NUL in its first block: the lines before it only
    ("libx.so", b"", True),  # another type: the lines before its first NUL
    ("libx.so", NUL, False),
], ids=["log", "csv", "yaml", "no-suffix-text", "no-suffix-binary", "so-before-nul", "so-after-nul"])
def test_which_lines_of_a_file_with_a_nul_byte_are_compared(wc, tmp_path, name, before, found):
    data = before + b"\n" + _rows(ANSWERS, 3) + (b"" if before else NUL)
    result = _run(wc, _export(tmp_path / "x", {f"opt/{name}": data}))
    assert _paths(result, "private_lines") == ([f"opt/{name}"] if found else [])


def test_a_binary_file_of_another_type_is_hashed_only(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"usr/lib/libbig.so": b"\x00" * (SMALL * 3)}))
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


@pytest.mark.parametrize("name, data", [
    ("var/lib/dpkg/alternatives/builtins.7.gz", b"auto\n/usr/share/man/man7/builtins.7.gz\n\nbash-builtins\n"),
    ("opt/joblib/data.pkl.gz", b"x^" + bytes(range(1, 200))),  # a zlib stream, not gzip
    ("opt/odd.zip", b"not a zip\n"),
    ("opt/odd.tar", b"plain text named .tar\n"),
])
def test_a_file_with_an_archive_suffix_but_not_its_format_is_an_ordinary_file(wc, tmp_path, name, data):
    assert _run(wc, _export(tmp_path / "x", {name: data}))["verdict"] == "pass"


def test_a_file_with_an_archive_suffix_but_not_its_format_is_still_line_checked(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"opt/rows.gz": b"x\n" + _rows(ANSWERS, 2)}))
    assert _paths(result, "private_lines") == ["opt/rows.gz"]


def test_a_truncated_gzip_fails_with_its_path(wc, tmp_path):
    data = gzip.compress(os.urandom(5000))[:-20]
    result = _run(wc, _export(tmp_path / "x", {"opt/cut.gz": data}))
    assert (result["verdict"], _paths(result, "unreadable")) == ("fail", ["opt/cut.gz"])


@pytest.mark.parametrize("name, data", [
    ("opt/a.gz", lambda: gzip.compress(_tar({"a.dat": ANSWERS.read_bytes()}))),  # a gzip holding a tar
    ("opt/a.zip.gz", lambda: gzip.compress(_zip({"a.dat": ANSWERS.read_bytes()}))),
    ("opt/a.tar", lambda: _tar({"inner.bin": gzip.compress(ANSWERS.read_bytes())})),  # named for no archive
])
def test_an_archive_inside_an_archive_is_nested_whatever_its_name(wc, tmp_path, name, data):
    result = _run(wc, _export(tmp_path / "x", {name: data()}))
    assert (result["verdict"], [p.split("!")[0] for p in _paths(result, "not_inspected")]) == ("fail", [name])


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


def test_the_benchmarks_package_inside_a_zip_is_found(wc, tmp_path):
    result = _run(wc, _export(tmp_path / "x", {"srv/env.zip": _zip({"lib/mlebench/__init__.py": b"x = 1\n"})}))
    assert _paths(result, "benchmark") == ["srv/env.zip!lib/mlebench"]


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


@pytest.mark.parametrize("target, leaves", [("../../x", False), ("../../../x", True)])
def test_a_link_two_levels_down_may_climb_two_levels_and_no_more(wc, tmp_path, target, leaves):
    export = _export(tmp_path / "x", {"a/b/f": b"1\n"})
    (export / "a" / "b" / "l").symlink_to(target)
    assert _paths(_run(wc, export), "links_outside") == (["a/b/l"] if leaves else [])


@pytest.mark.parametrize("form", ["directory", "tar"])
@pytest.mark.parametrize("target, leaves", [
    ("/etc/alternatives/python3", False),  # absolute: resolved against the export's root, even if absent there
    ("../lib/python3/dist-packages/x", False),
    ("../../../../opt/x", True),  # climbs above the root
    ("/usr/../../x", True),
])
def test_a_link_leaves_the_export_only_when_it_climbs_above_its_root(wc, tmp_path, form, target, leaves):
    export = _export(tmp_path / "x")
    (export / "usr" / "bin" / "python3").symlink_to(target)
    result = _run(wc, export if form == "directory" else _as_tar(export, tmp_path / "x.tar"))
    assert _paths(result, "links_outside") == (["usr/bin/python3"] if leaves else [])


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


def test_a_hard_link_is_reported_the_same_way_in_both_forms(wc, tmp_path):
    zipped = _zip({"m.dat": ANSWERS.read_bytes()})
    export = _export(tmp_path / "x", {"var/a.bin": ANSWERS.read_bytes(), "var/a.zip": zipped})
    os.link(export / "var" / "a.bin", export / "var" / "b.bin")
    os.link(export / "var" / "a.zip", export / "var" / "b.zip")
    from_dir, from_tar = _run(wc, export), _run(wc, _as_tar(export, tmp_path / "x.tar"))
    assert (_paths(from_tar, "private_hash"), from_tar["findings"], from_tar["files_checked"]) == (
        ["var/a.bin", "var/a.zip!m.dat", "var/b.bin", "var/b.zip!m.dat"], from_dir["findings"], from_dir["files_checked"])


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


TWO = {"etc/os-release": b"NAME=x\n", "opt/a.dat": ANSWERS.read_bytes()}  # headers at 0 and 1024


@pytest.mark.parametrize("cut", [
    lambda t: t[:1024],  # at the second member's header
    lambda t: t[:1124],  # inside it
    lambda t: t[:1536 + 100],  # inside its data
    lambda t: t[:1024] + b"\x01" * 512 + t[1024:],  # a garbage block before it
    lambda t: _tar({"etc/os-release": b"NAME=x\n"}) + _tar({"opt/a.dat": ANSWERS.read_bytes()}),  # a second archive
    lambda t: t[:1536 + 512 * ((len(ANSWERS.read_bytes()) + 511) // 512) + 512],  # one NUL block, not two
    lambda t: b"",
    lambda t: b"\x01" * 2048,  # not a tar
])
def test_a_cut_or_corrupted_tar_export_fails_as_incomplete(wc, tmp_path, cut):
    _put(tmp_path / "x.tar", cut(_tar(TWO)))
    result = _run(wc, tmp_path / "x.tar")
    assert (result["verdict"], _paths(result, "export_incomplete")) == ("fail", [str(tmp_path / "x.tar")])


def test_a_whole_tar_export_is_not_incomplete(wc, tmp_path):
    _put(tmp_path / "x.tar", _tar(TWO))
    assert _run(wc, tmp_path / "x.tar")["findings"]["export_incomplete"] == []


def test_a_cut_tar_inside_an_archive_fails(wc, tmp_path):
    data = _tar(TWO)[:1024]
    result = _run(wc, _export(tmp_path / "x", {"srv/cut.tar": data}))
    assert _paths(result, "unreadable") == ["srv/cut.tar"]


# --- the image reference and the command line ----------------------------------------------------------------------

@pytest.mark.parametrize("ref", ["localhost/mle-tiny-agent:latest", "localhost/x@sha256:" + "a" * 63,
                                 "localhost/x@sha256:" + "A" * 64, "localhost/x@sha256:" + "a" * 65, ""])
def test_an_image_reference_not_pinned_by_digest_is_refused(wc, tmp_path, ref):
    with pytest.raises(wc.Refused):
        _run(wc, _export(tmp_path / "x"), image_ref=ref)


@pytest.mark.parametrize("change", [
    lambda t: {"private": t / "empty"},
    lambda t: {"private": t / "missing"},
    lambda t: {"grader": t / "empty"},  # no grade.py
    lambda t: {"leaderboard": t / "missing.csv"},
    lambda t: {"leaderboard": t / "empty.csv"},
    lambda t: {"public": t / "missing"},
    lambda t: {"withheld": [t / "missing"]},
    lambda t: {"competition": "another-competition"},  # not the id config.yaml names
    lambda t: {"competition": "Not An Id"},
])
def test_missing_empty_or_mismatched_inputs_are_refused(wc, tmp_path, change):
    (tmp_path / "empty").mkdir()
    (tmp_path / "empty.csv").write_bytes(b"")
    with pytest.raises(wc.Refused):
        _run(wc, _export(tmp_path / "x"), **change(tmp_path))


# --- withheld directories and exemptions ---------------------------------------------------------------------------

def test_a_file_of_a_withheld_directory_is_found_by_hash(wc, tmp_path):
    raw = tmp_path / "raw"
    _put(raw / "train.csv", b"id,x1,x2,label,hidden\n1,2,3,4,5\n")
    _put(raw / "description.md", (PUBLIC / "description.md").read_bytes())  # also public: never a hit
    export = _export(tmp_path / "x", {"opt/t.csv": (raw / "train.csv").read_bytes()})
    result = _run(wc, export, withheld=[raw])
    assert result["findings"]["withheld_file"] == [{"path": "opt/t.csv", "source": "raw/train.csv"}]


def _exempt(tmp_path, entries):
    _put(tmp_path / "exempt.json", json.dumps(entries).encode())
    return tmp_path / "exempt.json"


def _sha(data):
    import hashlib
    return hashlib.sha256(data).hexdigest()


def test_an_exempted_nested_archive_passes_and_is_listed(wc, tmp_path):
    inner = _zip({"fixture.txt": b"test data\n"})
    exempt = _exempt(tmp_path, [{"sha256": _sha(inner), "reason": "a package's own test fixture"}])
    result = _run(wc, _export(tmp_path / "x", {"srv/t.zip": _zip({"inner.zip": inner})}), exempt=exempt)
    assert (result["verdict"], result["exempted"], result["exemptions_sha256"]) == (
        "pass", [{"path": "srv/t.zip!inner.zip", "sha256": _sha(inner), "reason": "a package's own test fixture",
                  "finding": "nested archive"}], "sha256:" + _sha(exempt.read_bytes()))


def test_an_exemption_does_not_lift_a_hit_on_the_same_file(wc, tmp_path):
    private = tmp_path / "private"
    shutil.copytree(PRIVATE, private)
    big = _tar({"pad.bin": os.urandom(SMALL * 2)})
    _put(private / "bundle.tar", big)
    exempt = _exempt(tmp_path, [{"sha256": _sha(big), "reason": "over the cap"}])
    result = _run(wc, _export(tmp_path / "x", {"opt/b.tar": big}), private=private, exempt=exempt, cap=SMALL)
    assert (result["verdict"], _paths(result, "private_hash"), len(result["exempted"])) == ("fail", ["opt/b.tar"], 1)


def test_an_exemption_does_not_lift_an_unreadable_archive(wc, tmp_path):
    broken = b"PK\x03\x04 not a zip"
    exempt = _exempt(tmp_path, [{"sha256": _sha(broken), "reason": "x"}])
    result = _run(wc, _export(tmp_path / "x", {"srv/b.zip": broken}), exempt=exempt)
    assert (result["verdict"], result["exemptions_unused"]) == ("fail", [_sha(broken)])


def test_an_exemption_for_a_file_not_present_is_reported_unused(wc, tmp_path):
    exempt = _exempt(tmp_path, [{"sha256": "b" * 64, "reason": "x"}])
    result = _run(wc, _export(tmp_path / "x"), exempt=exempt)
    assert (result["verdict"], result["exemptions_unused"]) == ("pass", ["b" * 64])


@pytest.mark.parametrize("entries", [{"sha256": "b" * 64}, [{"sha256": "b" * 63, "reason": "x"}],
                                     [{"sha256": "b" * 64, "reason": " "}]])
def test_a_malformed_exemption_file_is_refused(wc, tmp_path, entries):
    with pytest.raises(wc.Refused):
        _run(wc, _export(tmp_path / "x"), exempt=_exempt(tmp_path, entries))


def test_a_binary_private_file_is_withheld_by_hash_only(wc, tmp_path):
    """Its bytes are no lines: a PNG's signature, which holds newlines, recurs in every PNG."""
    private = tmp_path / "private"
    shutil.copytree(PRIVATE, private)
    signature = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    _put(private / "images" / "1.png", signature + b"private image")
    result = _run(wc, _export(tmp_path / "x", {"usr/share/a.png": signature + b"another image"}), private=private)
    assert result["verdict"] == "pass"


def test_lines_are_counted_per_private_file(wc, tmp_path):
    private = tmp_path / "private"
    shutil.copytree(PRIVATE, private)
    _put(private / "labels.csv", b"id,label\n1,alpha\n2,beta\n3,gamma\n")
    text = _rows(ANSWERS, 4) + b"2,beta\n3,gamma\n"
    result = _run(wc, _export(tmp_path / "x", {"tmp/mix.csv": text}), private=private)
    assert result["findings"]["private_lines"] == [{"path": "tmp/mix.csv", "lines": {"answers.csv": 4, "labels.csv": 2}}]


def _cli(export, out, ref=REF, private=PRIVATE):
    cmd = [sys.executable, "-m", "experiments.mle_bench_tasks.withhold_check", "--image-ref", ref,
           "--competition", "tiny-tabular", "--export", str(export), "--private", str(private), "--grader",
           str(GRADER), "--leaderboard", str(LEADERBOARD), "--public", str(PUBLIC), "--out", str(out)]
    env = dict(os.environ, PYTHONPATH=str(ROOT))
    return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True).returncode


def test_the_command_line_exits_0_on_a_pass_and_1_on_a_fail_and_writes_the_result(tmp_path):
    clean, dirty = _export(tmp_path / "a"), _export(tmp_path / "b", {"x/y": ANSWERS.read_bytes()})
    codes = _cli(clean, tmp_path / "a.json"), _cli(dirty, tmp_path / "b.json")
    verdicts = [json.loads((tmp_path / f).read_text())["verdict"] for f in ("a.json", "b.json")]
    assert (codes, verdicts) == ((0, 1), ["pass", "fail"])


def test_the_command_line_refuses_an_unpinned_reference_and_removes_an_earlier_result(tmp_path):
    (tmp_path / "a.json").write_text('{"verdict": "pass"}')
    code = _cli(_export(tmp_path / "a"), tmp_path / "a.json", ref="localhost/x:latest")
    assert (code, (tmp_path / "a.json").exists()) == (2, False)


def test_a_crashed_run_leaves_no_result_not_even_an_earlier_one(tmp_path):
    """An unreadable private file makes the check itself fail (a crash, exit 1): no result may remain."""
    private = tmp_path / "private"
    shutil.copytree(PRIVATE, private)
    (private / "locked.csv").write_bytes(b"id\n1\n")
    (private / "locked.csv").chmod(0)
    (tmp_path / "a.json").write_text('{"verdict": "pass"}')
    try:
        code = _cli(_export(tmp_path / "x"), tmp_path / "a.json", private=private)
    finally:
        (private / "locked.csv").chmod(0o600)
    assert (code, sorted(p.name for p in tmp_path.iterdir() if p.suffix == ".json" or ".tmp" in p.name)) == (1, [])
