"""Structural search candidates: identity, snapshot and compile through the ordinary CLI."""

import json
from pathlib import Path

import pytest

from experiments.orc_structural_search.candidates import candidate_id, compile_candidate, snapshot
from experiments.orc_structural_search.config import ExperimentConfig, load_config

REPO = Path(__file__).resolve().parents[2]
SOURCE = (REPO / "workflows/examples/plan_review_execute.orc").read_text().replace(
    '(:target-dsl "2.35")', '(:target-dsl "2.39")')
PROVIDERS = (REPO / "workflows/examples/inputs/plan_review_execute/providers.json").read_text()
CONFIG = {
    "mutable_files": ["plan_review_execute.orc"],
    "mutable_definitions": ["run"],
    "condition": "topology-only",
    "interface": "I1",
    "entry_workflow": "plan_review_execute::run",
    "source_root": ".",
    "providers_file": "providers.json",
    "command_boundaries_file": None,
    "episode_wall_clock_sec": 600,
    "criterion_sha256": None,
}


def make_candidate(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True)
    for name, text in files.items():
        (root / name).write_text(text)
    return root


def make_config(tmp_path: Path, **overrides) -> ExperimentConfig:
    path = tmp_path / "config.json"
    path.write_text(json.dumps({**CONFIG, **overrides}))
    return load_config(path)


def test_candidate_id_ignores_nothing_but_covers_every_byte(tmp_path):
    a = make_candidate(tmp_path / "a", {"m.orc": SOURCE})
    b = make_candidate(tmp_path / "b", {"m.orc": SOURCE})
    assert candidate_id(a, orchestrator_commit="abc") == candidate_id(b, orchestrator_commit="abc")
    c = make_candidate(tmp_path / "c", {"m.orc": SOURCE + "\n"})
    assert candidate_id(c, orchestrator_commit="abc") != candidate_id(a, orchestrator_commit="abc")
    assert candidate_id(a, orchestrator_commit="def") != candidate_id(a, orchestrator_commit="abc")


def test_candidate_id_distinguishes_file_names(tmp_path):
    a = make_candidate(tmp_path / "a", {"m.orc": SOURCE})
    b = make_candidate(tmp_path / "b", {"n.orc": SOURCE})
    assert candidate_id(a, orchestrator_commit="abc") != candidate_id(b, orchestrator_commit="abc")


def test_candidate_id_excludes_build_cache(tmp_path):
    a = make_candidate(tmp_path / "a", {"m.orc": SOURCE})
    before = candidate_id(a, orchestrator_commit="abc")
    (a / ".orchestrate/build").mkdir(parents=True)
    (a / ".orchestrate/build/manifest.json").write_text("{}")
    assert candidate_id(a, orchestrator_commit="abc") == before


def test_snapshot_never_writes_parent_and_refuses_existing_dest(tmp_path):
    parent = make_candidate(tmp_path / "parent", {"m.orc": SOURCE, "providers.json": PROVIDERS})
    before = candidate_id(parent, orchestrator_commit="abc")
    child = snapshot(parent, {"m.orc": b"edited"}, tmp_path / "child")
    assert ((child / "m.orc").read_bytes(), (child / "providers.json").read_text(),
            candidate_id(parent, orchestrator_commit="abc")) == (b"edited", PROVIDERS, before)
    with pytest.raises(FileExistsError):
        snapshot(parent, {}, child)


def test_compile_candidate_reports_accepted_build_key_and_digest(tmp_path):
    root = make_candidate(tmp_path / "c", {"plan_review_execute.orc": SOURCE, "providers.json": PROVIDERS})
    outcome = compile_candidate(root, make_config(tmp_path))
    assert (outcome.status, bool(outcome.build_key), outcome.program_digest.startswith("sha256:"),
            outcome.diagnostics) == ("accepted", True, True, ())


def test_compile_candidate_reports_rejected_diagnostics(tmp_path):
    broken = SOURCE.replace(":prompt (execute-plan :task task :steps revised.steps)",
                            ":prompt (execute-plan :task task :steps task)")
    assert broken != SOURCE
    root = make_candidate(tmp_path / "c", {"plan_review_execute.orc": broken, "providers.json": PROVIDERS})
    outcome = compile_candidate(root, make_config(tmp_path))
    assert (outcome.status, outcome.build_key, outcome.program_digest, len(outcome.diagnostics) > 0) == (
        "rejected", None, None, True)


def test_load_config_rejects_unknown_condition(tmp_path):
    with pytest.raises(ValueError, match="condition"):
        make_config(tmp_path, condition="everything")


def test_load_config_rejects_unknown_interface(tmp_path):
    with pytest.raises(ValueError, match="interface"):
        make_config(tmp_path, interface="I4")


def test_load_config_reads_lists_as_tuples(tmp_path):
    assert make_config(tmp_path).mutable_files == ("plan_review_execute.orc",)
