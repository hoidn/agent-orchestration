"""The pure parts of the long-horizon image check (`experiments/long_horizon_tasks/image_check.py`)."""

import hashlib
import importlib.util
import io
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks"
_spec = importlib.util.spec_from_file_location("lh_image_check", KIT / "image_check.py")
image_check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(image_check)

GUID = b"00000000-1111-2222-3333-444444444444"  # a made-up identifier, not the benchmark's


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _store(*layers):
    return [{"id": d[7:], "diff-digest": d, "compressed-size": c, "diff-size": u} for d, c, u in layers]


def _index():
    return image_check.package_index([
        ("solution/solve.sh", _sha(b"answer")),
        ("tests/test_outputs.py", _sha(b"check")),
        ("tests/data/input.csv", _sha(b"shared")),
        ("tests/__init__.py", _sha(b"")),
        ("environment/data/input.csv", _sha(b"shared")),
        ("environment/app/main.py", _sha(b"main")),
    ])


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
        {"diff_digest": d, "compressed": 1, "unpacked": {"base": 100, "a1": 10, "v1": 20, "a2": 40, "v2": 5}[d]}
        for d in digests]}


def test_totals_count_each_distinct_layer_once_per_strategy():
    lines = [_line("t1", "agent", "base", "a1"), _line("t1", "verifier", "base", "v1"),
             _line("t2", "agent", "base", "a2"), _line("t2", "verifier", "v2"),
             {"task": "t3", "role": "agent", "pull": {"ok": False}}]
    got = image_check.totals(lines, ["t1", "t2", "t3"])
    assert (got["measured"], got["all"]["unpacked"], got["agent_only"]["unpacked"],
            got["largest_block"]["task"], got["largest_block"]["unpacked"],
            got["largest_block_and_next"]["unpacked"]) == (4, 175, 150, "t2", 145, 175)


def test_a_clean_listing_is_withheld():
    members = [("usr/bin/python3", _sha(b"py"), False), ("app/main.py", _sha(b"main"), False)]
    found = image_check.classify(members, _index())
    assert (found["withheld"], found["path_hits"], found["digest_hits"]) == (True, [], [])


def test_a_root_tests_directory_is_a_path_hit():
    found = image_check.classify([("tests/anything.txt", _sha(b"x"), False)], _index())
    assert (found["withheld"], found["path_hits"]) == (False, [{"path": "tests/anything.txt", "matches": "tests/"}])


def test_a_solution_file_under_another_directory_is_a_path_hit():
    found = image_check.classify([("opt/task/solution/solve.sh", _sha(b"other"), False)], _index())
    assert found["path_hits"] == [{"path": "opt/task/solution/solve.sh", "matches": "solution/solve.sh"}]


def test_a_copy_of_a_test_file_under_any_name_is_a_digest_hit():
    found = image_check.classify([("srv/x.py", _sha(b"check"), False)], _index())
    assert (found["withheld"], found["digest_hits"]) == (
        False, [{"path": "srv/x.py", "matches": ["tests/test_outputs.py"]}])


def test_files_the_environment_also_ships_and_empty_files_are_not_digest_hits():
    members = [("app/data/input.csv", _sha(b"shared"), False), ("app/pkg/__init__.py", _sha(b""), False)]
    assert image_check.classify(members, _index())["digest_hits"] == []


def test_canary_files_are_split_into_environment_copies_name_only_matches_and_others():
    members = [("srv/main.py", _sha(b"main"), True), ("app/main.py", _sha(b"edited"), True),
               ("opt/notes.txt", _sha(b"n"), True)]
    found = image_check.classify(members, _index())
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


def test_the_canary_identifier_is_read_from_the_package_texts():
    texts = [b"# no marker", b"# harbor-canary GUID " + GUID + b"\n", b"<!-- harbor-canary GUID " + GUID + b" -->"]
    assert image_check.canary_id(texts) == GUID


def test_two_canary_identifiers_in_one_package_are_an_error():
    with pytest.raises(ValueError):
        image_check.canary_id([b"canary GUID " + GUID, b"canary GUID " + GUID.replace(b"0", b"9")])


def test_the_needle_is_found_across_a_chunk_boundary(monkeypatch):
    monkeypatch.setattr(image_check, "CHUNK", 8)
    data = b"x" * 13 + GUID + b"y" * 5
    assert image_check.holds(io.BytesIO(data), GUID) == (_sha(data), True)


def test_no_needle_means_no_hit():
    assert image_check.holds(io.BytesIO(b"abc"), None) == (_sha(b"abc"), False)
