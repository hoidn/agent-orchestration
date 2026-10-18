"""Structural search edit validation: frozen surfaces and the one-site transaction."""

import hashlib
from pathlib import Path

import pytest

from experiments.orc_structural_search.candidates import (
    Receipt,
    compile_candidate,
    validate_frozen_surfaces,
    validate_one_site,
)
from experiments.orc_structural_search.config import ExperimentConfig

REPO = Path(__file__).resolve().parents[2]
FILE = "plan_review_execute.orc"
SOURCE = (REPO / "workflows/examples/plan_review_execute.orc").read_text().replace(
    '(:target-dsl "2.35")', '(:target-dsl "2.39")')
PROVIDERS = (REPO / "workflows/examples/inputs/plan_review_execute/providers.json").read_text()
REVIEW_SITE = "(provider-result providers.codex\n                       :prompt (review-plan"
REVIEW_CALL = REVIEW_SITE + " :task task :steps draft.steps))"
REVIEW_REPLACEMENT = "(provider-result providers.claude :prompt (review-plan :task task :steps draft.steps))"
DRAFT_BODY = '"Plan this task as ordered steps, naming the files each step touches. Change no files.\\n\\nTask: {task}"'
HELPER = "(defworkflow fresh-helper ((task String)) -> Execution\n  (provider-result providers.codex :prompt (execute-plan :task task :steps (list task))))"


def config(condition="topology-only", mutable_definitions=("run",)) -> ExperimentConfig:
    return ExperimentConfig(
        mutable_files=(FILE,), mutable_definitions=mutable_definitions, condition=condition, interface="I2",
        entry_workflow="plan_review_execute::run", source_root=".", providers_file="providers.json",
        command_boundaries_file=None, episode_wall_clock_sec=600, criterion_sha256=None)


def candidate(root: Path, source: str | bytes) -> Path:
    root.mkdir(parents=True)
    data = source if isinstance(source, bytes) else source.encode()
    (root / FILE).write_bytes(data)
    (root / "providers.json").write_text(PROVIDERS)
    return root


def pair(tmp_path: Path, parent_source, child_source) -> tuple[Path, Path]:
    return candidate(tmp_path / "parent", parent_source), candidate(tmp_path / "child", child_source)


def edit(old: str, new: str, source: str = SOURCE) -> str:
    assert source.count(old) == 1, old
    return source.replace(old, new)


def site_of(text: str, needle: str) -> str:
    index = text.index(needle)
    line = text.count("\n", 0, index) + 1
    column = index - text.rfind("\n", 0, index)
    return f"workflow:plan_review_execute::run@{FILE}:{line}:{column}"


def receipt(parent: Path, site_id: str, replacement: str, helpers=(), digest=None) -> Receipt:
    digest = digest or "sha256:" + hashlib.sha256((parent / FILE).read_bytes()).hexdigest()
    return Receipt(parent_candidate_id="sha256:parent", site_id=site_id, expected_file_digest=digest,
                   replacement_expression=replacement, supporting_declarations=tuple(helpers),
                   condition="topology-only", hypothesis="Review with the other provider.")


def test_whitespace_only_child_passes_validation_and_keeps_program_digest(tmp_path):
    child_source = edit("  (defworkflow run", "\n  ;; reflowed\n  (defworkflow   run").replace("\n", "\n  ")
    parent, child = pair(tmp_path, SOURCE, child_source)
    digests = {compile_candidate(root, config()).program_digest for root in (parent, child)}
    assert (validate_frozen_surfaces(parent, child, config()).accepted, len(digests), None in digests) == (
        True, 1, False)


def test_unrelated_definition_edit_is_refused_with_scope_exceeded(tmp_path):
    other = "(defworkflow other ((task String)) -> String task)\n)"
    parent_source = SOURCE.rstrip().removesuffix(")") + other
    child_source = edit("(defworkflow other ((task String)) -> String task)",
                        "(defworkflow other ((task String)) -> String \"x\")", parent_source)
    parent, child = pair(tmp_path, parent_source, child_source)
    assert validate_frozen_surfaces(parent, child, config()).code == "scope_exceeded"


def test_import_change_is_refused_with_frozen_surface_changed(tmp_path):
    parent_source = edit("(export run)", "(export run)\n  (import std/improve :only (Decision))")
    child_source = edit("(import std/improve :only (Decision))", "(import std/improve :only (Decision improve))",
                        parent_source)
    parent, child = pair(tmp_path, parent_source, child_source)
    assert validate_frozen_surfaces(parent, child, config()).code == "frozen_surface_changed"


def test_prompt_body_edit_refused_under_topology_only(tmp_path):
    parent, child = pair(tmp_path, SOURCE, edit(DRAFT_BODY, '"Plan {task} as ordered steps."'))
    cfg = config("topology-only", ("run", "draft-plan"))
    assert validate_frozen_surfaces(parent, child, cfg).code == "frozen_surface_changed"


def test_prompt_body_edit_accepted_under_prompt_only(tmp_path):
    parent, child = pair(tmp_path, SOURCE, edit(DRAFT_BODY, '"Plan {task} as ordered steps."'))
    assert validate_frozen_surfaces(parent, child, config("prompt-only", ("run", "draft-plan"))).accepted


def test_one_site_transaction_accepts_single_subtree_replacement(tmp_path):
    parent, child = pair(tmp_path, SOURCE, edit(REVIEW_CALL, REVIEW_REPLACEMENT))
    verdict = validate_one_site(parent, child, receipt(parent, site_of(SOURCE, REVIEW_SITE), REVIEW_REPLACEMENT),
                                config())
    assert (verdict.accepted, verdict.code) == (True, None)


def test_one_site_transaction_accepts_declared_fresh_helper(tmp_path):
    child_source = edit("  (defworkflow run", f"  {HELPER}\n\n  (defworkflow run", edit(REVIEW_CALL, REVIEW_REPLACEMENT))
    parent, child = pair(tmp_path, SOURCE, child_source)
    verdict = validate_one_site(
        parent, child, receipt(parent, site_of(SOURCE, REVIEW_SITE), REVIEW_REPLACEMENT, [HELPER]), config())
    assert (verdict.accepted, verdict.code) == (True, None)


def test_one_site_transaction_refuses_second_changed_subtree(tmp_path):
    child_source = edit("(provider-result providers.codex\n        :prompt (execute-plan",
                        "(provider-result providers.claude\n        :prompt (execute-plan",
                        edit(REVIEW_CALL, REVIEW_REPLACEMENT))
    parent, child = pair(tmp_path, SOURCE, child_source)
    verdict = validate_one_site(parent, child, receipt(parent, site_of(SOURCE, REVIEW_SITE), REVIEW_REPLACEMENT),
                                config())
    assert verdict.code == "scope_exceeded"


def test_one_site_transaction_refuses_stale_digest(tmp_path):
    parent, child = pair(tmp_path, SOURCE, edit(REVIEW_CALL, REVIEW_REPLACEMENT))
    stale = receipt(parent, site_of(SOURCE, REVIEW_SITE), REVIEW_REPLACEMENT, digest="sha256:" + "0" * 64)
    assert validate_one_site(parent, child, stale, config()).code == "digest_mismatch"


def test_one_site_transaction_refuses_site_with_no_form_start(tmp_path):
    parent, child = pair(tmp_path, SOURCE, edit(REVIEW_CALL, REVIEW_REPLACEMENT))
    shifted = site_of(SOURCE, REVIEW_SITE[2:])  # inside the `provider-result` symbol
    assert validate_one_site(parent, child, receipt(parent, shifted, REVIEW_REPLACEMENT), config()).code == (
        "site_unlocatable")


@pytest.mark.parametrize("name", ["draft-plan", "Plan", "run", "imp", "Decision"])
def test_helper_colliding_with_existing_name_is_refused(tmp_path, name):
    parent_source = edit("(export run)", "(export run)\n  (import std/improve :as imp :only (Decision))")
    helper = HELPER.replace("fresh-helper", name)
    child_source = edit("  (defworkflow run", f"  {helper}\n\n  (defworkflow run",
                        edit(REVIEW_CALL, REVIEW_REPLACEMENT, parent_source))
    parent, child = pair(tmp_path, parent_source, child_source)
    verdict = validate_one_site(
        parent, child, receipt(parent, site_of(parent_source, REVIEW_SITE), REVIEW_REPLACEMENT, [helper]), config())
    assert verdict.code == "declaration_collision"


def test_transaction_locates_site_in_crlf_and_utf8_source(tmp_path):
    parent_text = edit("  (defworkflow run", "  ;; señal: niño\n  (defworkflow run")
    child_text = edit(REVIEW_CALL, REVIEW_REPLACEMENT, parent_text)
    parent, child = pair(tmp_path, parent_text.replace("\n", "\r\n").encode(),
                         child_text.replace("\n", "\r\n").encode())
    verdict = validate_one_site(
        parent, child, receipt(parent, site_of(parent_text, REVIEW_SITE), REVIEW_REPLACEMENT), config())
    assert (verdict.accepted, verdict.code) == (True, None)
