"""Structural search I2 sites: the runtime's manifest helper, site selection, the site brief, receipt derivation."""

import hashlib
import random
import re
import shutil
from pathlib import Path

import pytest

from experiments.orc_structural_search.candidates import (
    _child_forms, _owner_form, _site_path, _subform, canonical_form, validate_one_site)
from experiments.orc_structural_search.config import ExperimentConfig
from experiments.orc_structural_search.sites import (
    derive_receipt, eligible_sites, replacement_start, select_site, site_brief, site_manifest, slot_type)
from tests.experiments.orc_structural_search_support import SEEDS, world  # noqa: F401 (fixture)

FILE = "plan_then_implement.orc"
OWNER = "workflow:plan_then_implement::run"
DRAFT_SITE = f"{OWNER}@{FILE}:29:19"
CONFIG = ExperimentConfig(
    mutable_files=(FILE,), mutable_definitions=("run",), condition="topology-only", interface="I2",
    entry_workflow="plan_then_implement::run", source_root=".", providers_file="providers.json",
    command_boundaries_file="commands.json", episode_wall_clock_sec=600, criterion_sha256=None)
DRAFT_CALL = """(provider-result providers.planner
                    :prompt (draft-plan :task task :repo repo)
                    :model "claude-opus-5-5" :effort "high" :timeout-sec 5400)"""
HELPER = "(defproc fresh-steps ((task String)) -> Plan\n    :effects ()\n    (record Plan :steps (list task)))"
SEED_TEXT = (SEEDS / FILE).read_text()


def root_with(path: Path, source: str) -> Path:
    path.mkdir(parents=True)
    for name in ("common.orc", "providers.json", "commands.json"):
        shutil.copy(SEEDS / name, path / name)
    (path / FILE).write_text(source)
    return path


def edit(old: str, new: str, source: str = SEED_TEXT) -> str:
    assert source.count(old) == 1, old
    return source.replace(old, new)


def helper_child(tmp_path: Path) -> tuple[Path, Path]:
    """Parent: the seed. Child: the draft call replaced by a call of a fresh top-level helper."""
    parent = root_with(tmp_path / "parent", SEED_TEXT)
    child_text = edit("  (defworkflow run", f"  {HELPER}\n\n  (defworkflow run", edit(DRAFT_CALL, "(fresh-steps task)"))
    return parent, root_with(tmp_path / "child", child_text)


def test_site_manifest_runs_the_runtime_helper_and_lists_the_seeds_sites(world):
    manifest = site_manifest(world.candidate, CONFIG, runtime=world.runtime)
    kinds = [record["kind"] for record in manifest["sites"].values() if record["owner"]["name"] == OWNER]
    assert (sorted(kinds), DRAFT_SITE in manifest["sites"], list(manifest["file_digests"])) == (
        ["let*", "provider-call", "provider-call", "provider-call", "provider-call"], True, [FILE])


def record(site_id: str, *, eligibility: str = "eligible") -> dict:
    owner, _, location = site_id.rpartition("@")
    return {"site_id": site_id, "owner": {"name": owner}, "eligibility": eligibility,
            "span": {"start": {"path": location.split(":")[0]}}}


def test_eligible_sites_keep_only_mutable_definitions_in_mutable_files():
    ids = [f"{OWNER}@{FILE}:9:1", f"{OWNER}@{FILE}:3:1", f"{OWNER}@other.orc:1:1",
           f"workflow:plan_then_implement::helper@{FILE}:5:1"]
    sites = {site_id: record(site_id) for site_id in ids} | {
        f"{OWNER}@{FILE}:7:1": record(f"{OWNER}@{FILE}:7:1", eligibility="excluded")}
    assert [site["site_id"] for site in eligible_sites({"sites": sites}, CONFIG)] == ids[1::-1]


def test_select_site_is_reproducible_for_a_seed():
    sites = [record(f"{OWNER}@{FILE}:{line}:1") for line in range(1, 20)]
    assert select_site(sites, random.Random(7)) == select_site(sites, random.Random(7))


def test_derive_receipt_reads_the_replacement_and_fresh_helpers_from_the_child(tmp_path):
    parent, child = helper_child(tmp_path)
    receipt = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    parent_owner = _owner_form(_child_forms(parent / FILE), "run")
    child_site = _subform(_owner_form(_child_forms(child / FILE), "run"), _site_path(parent_owner, 29, 19))
    replacement = _child_forms(_write(tmp_path / "r.orc", receipt.replacement_expression))[0]
    digest = "sha256:" + hashlib.sha256((parent / FILE).read_bytes()).hexdigest()
    assert (canonical_form(replacement), receipt.supporting_declarations, receipt.expected_file_digest) == (
        canonical_form(child_site), (HELPER,), digest)


def _write(path: Path, text: str) -> Path:
    path.write_text(text)
    return path


def test_derived_receipt_passes_validate_one_site_for_a_single_subtree_replacement(tmp_path):
    parent, child = helper_child(tmp_path)
    receipt = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    assert validate_one_site(parent, child, receipt, CONFIG).accepted is True


def test_derived_receipt_carries_the_hypothesis_line_or_unavailable(tmp_path):
    parent, child = helper_child(tmp_path)
    before = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    (child / "HYPOTHESIS.txt").write_text("a pure plan is enough\nsecond line\n")
    after = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    assert (before.hypothesis, after.hypothesis) == ("unavailable", "a pure plan is enough")


def test_derive_receipt_of_a_child_that_moved_the_site_yields_a_scope_exceeded_verdict(tmp_path):
    parent = root_with(tmp_path / "parent", SEED_TEXT)
    body = "(variant Outcome DONE :summary change.summary)))"
    moved = edit("    (let* ((draft", "    (if true (let* ((draft", edit(
        body, '(variant Outcome DONE :summary change.summary)) (variant Outcome DONE :summary "skipped")))'))
    child = root_with(tmp_path / "child", moved)
    receipt = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    assert (receipt.replacement_expression, validate_one_site(parent, child, receipt, CONFIG).code) == (
        "", "scope_exceeded")


def test_site_brief_carries_the_site_record_and_no_runtime_path(world):
    site = site_manifest(world.candidate, CONFIG, runtime=world.runtime)["sites"][DRAFT_SITE]
    brief = site_brief(site)
    assert [needle in brief for needle in (DRAFT_SITE, "Plan", "task: String", str(world.runtime))] == [
        True, True, True, False]


def test_slot_type_reads_the_canonical_identity_at_a_position(world):
    manifest = site_manifest(world.candidate, CONFIG, runtime=world.runtime)
    assert (slot_type(manifest, OWNER, FILE, 29, 19), slot_type(manifest, OWNER, FILE, 29, 20)) == (
        "plan_then_implement::Plan", None)


def test_derived_receipt_replaces_invalid_hypothesis_bytes_and_caps_the_line(tmp_path):
    parent, child = helper_child(tmp_path)
    (child / "HYPOTHESIS.txt").write_bytes(b"bad \xff" + b"x" * 600 + b"\n")
    receipt = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    assert (receipt.hypothesis[:5], len(receipt.hypothesis)) == ("bad �", 500)


def test_derived_receipt_of_a_crlf_child_is_lf_normalized_and_validates(tmp_path):
    parent, child = helper_child(tmp_path)
    (child / FILE).write_bytes((child / FILE).read_bytes().replace(b"\n", b"\r\n"))
    receipt = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    assert (receipt.replacement_expression, receipt.supporting_declarations,
            validate_one_site(parent, child, receipt, CONFIG).accepted) == ("(fresh-steps task)", (HELPER,), True)


def test_derive_receipt_of_an_unreadable_child_file_is_empty(tmp_path):
    parent, child = helper_child(tmp_path)
    (child / FILE).unlink()
    (child / FILE).mkdir()  # reading it raises an OSError other than FileNotFoundError
    receipt = derive_receipt(parent, child, {"site_id": DRAFT_SITE}, CONFIG, parent_candidate_id="sha256:p")
    assert (receipt.replacement_expression, receipt.supporting_declarations) == ("", ())


def test_derive_receipt_names_the_parent_file_when_the_site_does_not_resolve(tmp_path):
    parent, child = helper_child(tmp_path)
    with pytest.raises(ValueError, match=re.escape(str(parent / FILE))):
        derive_receipt(parent, child, {"site_id": f"{OWNER}@{FILE}:29:21"}, CONFIG, parent_candidate_id="sha256:p")


def test_replacement_start_is_where_the_childs_form_at_the_parent_site_begins(tmp_path):
    parent, child = helper_child(tmp_path)
    text = (child / FILE).read_text()
    index = text.index("(fresh-steps task)")
    expected = (FILE, text.count("\n", 0, index) + 1, index - text.rfind("\n", 0, index))
    assert replacement_start(parent, child, {"site_id": DRAFT_SITE}) == expected
