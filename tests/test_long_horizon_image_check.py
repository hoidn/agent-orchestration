"""The pure parts of the long-horizon image check (`experiments/long_horizon_tasks/image_check.py`)."""

import hashlib
import importlib.util
import io
import os
import tarfile
import zipfile
import zlib
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks"
_spec = importlib.util.spec_from_file_location("lh_image_check", KIT / "image_check.py")
image_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(image_check)

GUID = b"00000000-1111-2222-3333-444444444444"  # a made-up identifier, not the benchmark's
ENV_MAIN = b"main\nfrom __future__ import annotations\n"
SOLVED = b"    return compute_the_answer(records, strict=True)"  # a distinctive line (>= 25 characters)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _store(*layers):
    return [{"id": d[7:], "diff-digest": d, "compressed-size": c, "diff-size": u} for d, c, u in layers]


def _index():
    return image_check.package_index([
        ("solution/solve.sh", b"answer"),
        ("solution/fix.py", b"import os\n" + SOLVED + b"\n"),
        ("tests/test_outputs.py", b"check"),
        ("tests/data/input.csv", b"shared"),
        ("tests/__init__.py", b""),
        ("environment/data/input.csv", b"shared"),
        ("environment/app/main.py", ENV_MAIN),
    ], GUID)


def _file(path, raw):
    return image_check._entry(path, raw, GUID)


def _other(path, kind, link=None):
    return image_check.Entry(path, kind, 0, None, False, None, link)


# ---- sizes and disk ---------------------------------------------------------------------------


def test_layer_sizes_are_read_from_the_store_in_image_order():
    store = _store(("sha256:b", 20, 50), ("sha256:a", 10, 30))
    assert image_check.layer_sizes(["sha256:a", "sha256:b"], store) == [
        {"diff_digest": "sha256:a", "compressed": 10, "unpacked": 30},
        {"diff_digest": "sha256:b", "compressed": 20, "unpacked": 50}]


def test_a_layer_missing_from_the_store_is_an_error():
    with pytest.raises(ValueError, match="sha256:z"):
        image_check.layer_sizes(["sha256:z"], _store(("sha256:a", 1, 2)))


def test_shared_layers_are_those_of_images_measured_before():
    earlier = [{"layers": [{"diff_digest": "sha256:a", "compressed": 10, "unpacked": 30}]}]
    layers = [{"diff_digest": "sha256:a", "compressed": 10, "unpacked": 30},
              {"diff_digest": "sha256:b", "compressed": 20, "unpacked": 50}]
    assert image_check.shared_with(layers, earlier) == {"count": 1, "compressed": 10, "unpacked": 30}


def _line(task, role, *digests):
    return {"task": task, "role": role, "layers": [
        {"diff_digest": d, "compressed": 1, "unpacked": {"base": 100, "a1": 10, "v1": 20, "a2": 40, "v2": 5,
                                                         "a3": 70}[d]}
        for d in digests]}


def test_totals_count_each_distinct_layer_once_and_take_the_worst_choice_of_blocks():
    lines = [_line("t1", "agent", "base", "a1"), _line("t1", "verifier", "base", "v1"),
             _line("t2", "agent", "base", "a2"), _line("t2", "verifier", "v2"),
             _line("t3", "agent", "a3"), {"task": "t4", "role": "agent", "pull": {"ok": False}}]
    got = image_check.totals(lines)
    worst = got["worst_blocks"]
    assert (got["measured"], got["all"]["unpacked"], got["agent_only"]["unpacked"],
            worst[1]["tasks"], worst[1]["unpacked"], worst[2]["tasks"], worst[2]["unpacked"], worst[3]["unpacked"],
            worst[4]) == (5, 245, 220, ["t2"], 145, ["t2", "t3"], 215, 245, None)


def test_a_pull_needs_room_for_the_download_and_the_unpacked_layers():
    assert (image_check.pull_need(10, 30), image_check.pull_need(10)) == (40, 10 + image_check.UNPACK_RATIO * 10)


@pytest.mark.parametrize(("present", "users", "action"), [
    ({"img"}, set(), "keep"), ({"img"}, {"c1"}, "keep"), (set(), {"c1"}, "refuse"), ({"other"}, set(), "remove")])
def test_an_image_is_removed_only_when_this_run_brought_it_and_no_container_uses_it(present, users, action):
    assert image_check.removal("img", present, users)[0] == action


def test_the_scratch_directory_is_created_private(tmp_path):
    made = image_check.scratch_dir(tmp_path / "scratch")
    assert made.stat().st_mode & 0o777 == 0o700


def test_a_scratch_directory_others_can_enter_is_refused(tmp_path):
    os.chmod(tmp_path, 0o755)
    with pytest.raises(image_check.Stop):
        image_check.scratch_dir(tmp_path)


# ---- the package ------------------------------------------------------------------------------


def test_distinctive_lines_are_long_answer_lines_absent_from_the_environment_and_not_the_canary():
    answers = [SOLVED + b"\nfrom __future__ import annotations\nshort\n# harbor-canary GUID " + GUID]
    env = [b"from __future__ import annotations\n"]
    assert image_check.distinctive_lines(answers, env, GUID) == {SOLVED.strip(): _sha(SOLVED.strip())}


def test_the_canary_identifier_is_read_from_the_package_texts():
    texts = [b"# no marker", b"# harbor-canary GUID " + GUID + b"\n", b"<!-- harbor-canary GUID " + GUID + b" -->"]
    assert image_check.canary_id(texts) == GUID


def test_two_canary_identifiers_in_one_package_are_an_error():
    with pytest.raises(ValueError):
        image_check.canary_id([b"canary GUID " + GUID, b"canary GUID " + GUID.replace(b"0", b"9")])


# ---- the search -------------------------------------------------------------------------------


def test_a_clean_listing_is_withheld():
    found = image_check.classify([_file("usr/bin/python3", b"py"), _file("app/main.py", ENV_MAIN)], _index())
    assert (found["withheld"], found["path_hits"], found["digest_hits"], found["near_copy"]) == (True, [], [], "clean")


def test_a_root_tests_directory_is_a_path_hit():
    found = image_check.classify([_other("tests", "dir")], _index())
    assert (found["withheld"], found["path_hits"]) == (False, [{"path": "tests", "kind": "dir", "matches": "tests/"}])


@pytest.mark.parametrize(("entry", "matches"), [
    (_other("opt/task/solution/solve.sh", "hardlink", "usr/bin/x"), "solution/solve.sh"),
    (_other("opt/run", "symlink", "/solution/solve.sh"), "solution/solve.sh")])
def test_links_are_path_tested_by_their_name_and_their_target(entry, matches):
    assert image_check.classify([entry], _index())["path_hits"][0]["matches"] == matches


def test_a_copy_of_a_test_file_under_any_name_is_a_digest_hit():
    found = image_check.classify([_file("srv/x.py", b"check")], _index())
    assert (found["withheld"], found["digest_hits"]) == (False, [{"path": "srv/x.py", "matches": ["tests/test_outputs.py"]}])


def test_files_the_environment_also_ships_and_empty_files_are_not_digest_hits():
    found = image_check.classify([_file("app/data/input.csv", b"shared"), _file("app/pkg/__init__.py", b"")], _index())
    assert found["digest_hits"] == []


def test_canary_files_are_split_into_environment_copies_name_only_matches_and_others():
    marked = b"# harbor-canary GUID " + GUID
    env_copy = image_check.Entry("srv/main.py", "file", len(ENV_MAIN), _sha(ENV_MAIN), True, None, None)
    found = image_check.classify([env_copy, _file("app/main.py", marked), _file("opt/notes.txt", marked)], _index())
    assert (found["canary_env_sha"], found["canary_name_only"], found["canary_other"], found["canary_counts"]) == (
        ["srv/main.py"], [{"path": "app/main.py", "env": "environment/app/main.py"}], ["opt/notes.txt"],
        {"env_sha": 1, "name_only": 1, "other": 1})


def test_a_name_only_match_is_paired_with_the_environment_file_whose_path_ends_alike():
    rels = ["environment/a/__init__.py", "environment/pkg/sub/__init__.py", "environment/pkg/__init__.py"]
    assert image_check.closest_env("app/pkg/sub/__init__.py", rels) == "environment/pkg/sub/__init__.py"


def test_a_name_only_match_that_shares_only_the_canary_line_says_so():
    marker = b"# harbor-canary GUID " + GUID
    got = image_check.compare_texts(marker + b"\nnew body\n", marker + b"\nold body\nmore\n", GUID)
    assert (got["identical"], got["shared_lines"], got["canary_only_shared"], got["image_only_lines"],
            got["env_only_lines"], got["image_size"]) == (False, 1, True, 1, 2, len(marker) + 10)


def test_a_name_only_match_that_shares_other_lines_counts_them():
    marker = b"# harbor-canary GUID " + GUID
    got = image_check.compare_texts(marker + b"\nimport os\nx = 1\n", marker + b"\nimport os\nx = 2\n", GUID)
    assert (got["shared_non_canary_lines"], got["canary_only_shared"]) == (1, False)


@pytest.mark.parametrize(("sha", "name_only", "other", "verdict"), [
    (0, 0, 0, "not found"), (2, 0, 0, "environment copies only"), (2, 1, 0, "needs a look"),
    (2, 1, 1, "found outside environment files")])
def test_the_canary_verdict_never_calls_a_name_only_match_clean(sha, name_only, other, verdict):
    found = {"canary_env_sha": ["x"] * sha, "canary_name_only": [{}] * name_only, "canary_other": ["y"] * other}
    assert image_check.canary_verdict(found, GUID) == verdict


def test_an_edited_copy_outside_system_paths_is_a_near_copy_that_needs_a_look():
    found = image_check.classify([_file("opt/work/fix_v2.py", b"import sys\n" + SOLVED + b"  \n")], _index())
    assert (found["digest_hits"], found["near_copy"], found["near_copy_look"],
            found["near_copies"][0]["lines"]) == ([], "needs a look", ["opt/work/fix_v2.py"], [_sha(SOLVED.strip())])


@pytest.mark.parametrize(("path", "count", "verdict"), [
    ("usr/lib/python3/inspect.py", 1, "noise"), ("usr/lib/python3/inspect.py", image_check.NOISE_N, "needs a look"),
    ("srv/venv/lib/python3.12/site-packages/x.py", 1, "noise"), ("app/x.py", 1, "needs a look"),
    ("lib64/x", 1, "noise"), ("library/x", 1, "needs a look"),
    ("root/.local/share/uv/python/cpython-3.11/lib/python3.11/code.py", 1, "noise"), ("opt/venv/bin/tool", 1, "needs a look")])
# (without a pyvenv.cfg beside it, opt/venv/bin is not a virtual environment)
def test_a_near_copy_in_a_system_path_is_noise_only_below_the_threshold(path, count, verdict):
    assert image_check.near_verdict(path, count) == verdict


def test_every_directory_holding_a_pyvenv_cfg_is_a_virtual_environment():
    paths = ["opt/venv/pyvenv.cfg", "opt/venv/bin/tool", "srv/app/.venv/pyvenv.cfg", "opt/notvenv/cfg"]
    assert image_check.venv_roots(paths) == {"opt/venv", "srv/app/.venv"}


@pytest.mark.parametrize(("path", "verdict"), [
    ("opt/venv/bin/tool", "noise"), ("opt/venv/lib/x.py", "noise"), ("opt/venv2/bin/tool", "needs a look")])
def test_a_near_copy_inside_a_virtual_environment_is_judged_as_in_a_language_directory(path, verdict):
    assert image_check.near_verdict(path, 1, {"opt/venv"}) == verdict


def test_a_launcher_script_in_a_virtual_environment_is_noise_in_the_search():
    index = _index() | {"venvs": {"opt/venv"}}
    found = image_check.classify([_file("opt/venv/bin/tool", SOLVED + b"\n")], index)
    assert (found["near_copies"][0]["verdict"], found["near_copy"]) == ("noise", "clean")


def _zip(members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, raw in members.items():
            z.writestr(name, raw)
    return buf.getvalue()


def test_an_archive_outside_system_paths_is_opened_and_its_members_searched():
    found = image_check.classify([_file("opt/backup.zip", _zip({"x/solve.sh": b"answer", "y.py": SOLVED}))], _index())
    assert (found["archives_opened"], [h["path"] for h in found["digest_hits"]], found["near_copy_look"]) == (
        [{"path": "opt/backup.zip", "members": 2}], ["opt/backup.zip!x/solve.sh"], ["opt/backup.zip!y.py"])


def test_a_loose_git_object_is_opened_as_a_blob():
    raw = zlib.compress(b"blob 6\0answer")
    found = image_check.classify([_file("srv/repo/.git/objects/ab/" + "c" * 38, raw)], _index())
    assert [h["path"] for h in found["digest_hits"]] == ["srv/repo/.git/objects/ab/" + "c" * 38 + "!blob"]


def test_archives_too_large_unreadable_or_nested_are_reported_not_opened():
    big = image_check.Entry("opt/big.tar", "file", 10**9, _sha(b"x"), False, None, None)
    nested = _file("opt/outer.zip", _zip({"inner.whl": b"PK"}))
    pack = _file("srv/repo/.git/objects/pack/pack-1.pack", b"PACK")
    found = image_check.classify([big, _file("opt/bad.tar.gz", b"not gzip"), nested, pack], _index())
    assert ([n["why"] for n in found["not_opened"]], found["near_copy"]) == (
        ["larger than MAX_READ", "ReadError", "archive inside an archive", "git pack"], "needs a look")


def test_a_git_directory_outside_system_paths_needs_a_look():
    found = image_check.classify([_other("srv/repo/.git", "dir")], _index())
    assert (found["git_dirs"], found["near_copy"]) == (["srv/repo/.git"], "needs a look")


def test_the_exported_tar_is_read_member_by_member(tmp_path):
    path = tmp_path / "x.tar"
    with tarfile.open(path, "w") as tar:
        info = tarfile.TarInfo("./app/main.py")
        info.size = 4
        tar.addfile(info, io.BytesIO(b"main"))
        for name, kind, link in (("./tests", tarfile.DIRTYPE, ""), ("./app/link", tarfile.LNKTYPE, "app/main.py"),
                                 ("./run", tarfile.SYMTYPE, "/solution/solve.sh")):
            info = tarfile.TarInfo(name)
            info.type, info.linkname = kind, link
            tar.addfile(info)
    got = [(e.path, e.kind, e.sha, e.link) for e in image_check.tar_entries(path, GUID)]
    assert got == [("app/main.py", "file", _sha(b"main"), None), ("tests", "dir", None, None),
                   ("app/link", "hardlink", None, "app/main.py"), ("run", "symlink", None, "/solution/solve.sh")]


def test_the_layer_walk_finds_a_deleted_answer_and_counts_the_whiteout():
    entries = [image_check.Entry("layer0/opt/solve.sh", "file", 6, _sha(b"answer"), False, None, None),
               image_check.Entry("layer1/opt/solve.sh", "whiteout", 0, None, False, None, None)]
    got = image_check.layer_verdict(entries, _index())
    assert (got["withheld"], got["whiteouts"], got["digest_hits"][0]["path"]) == (False, 1, "opt/solve.sh")


def test_the_needle_is_found_across_a_chunk_boundary(monkeypatch):
    monkeypatch.setattr(image_check, "CHUNK", 8)
    data = b"x" * 13 + GUID + b"y" * 5
    assert image_check.holds(io.BytesIO(data), GUID) == (_sha(data), True)


def test_no_needle_means_no_hit():
    assert image_check.holds(io.BytesIO(b"abc"), None) == (_sha(b"abc"), False)
