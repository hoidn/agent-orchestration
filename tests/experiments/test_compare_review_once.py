"""Comparison harness, review_once arm (experiments/compare): one review of a given patch and its blockers.

The contract tests compile review_once and reviewed_change and compare their review calls. The others run on
temporary git repositories with a stand-in reviewer behind the real shim (see compare_harness_support).
"""

import functools
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from experiments.compare import prepare
from orchestrator.workflow_lisp.build import FrontendBuildRequest
from orchestrator.workflow_lisp.closed.artifact import prepare_closed_program_bundle
from tests.experiments.compare_harness_support import (  # noqa: F401 (world is a fixture)
    REPO, UPSTREAM, call, drive, edit, skip_without_sandbox, start,
)
from tests.experiments.compare_harness_support import world as sandbox_world


@pytest.fixture
def world(sandbox_world):  # only the sandboxed tests need bubblewrap; the contract tests compile only
    skip_without_sandbox()
    return sandbox_world

REPORT = "artifacts/review/r.md"
APPROVE = {"variant": "APPROVE", "report": REPORT, "notes": []}


def strip_spans(node):
    if isinstance(node, dict):
        return {key: strip_spans(value) for key, value in node.items() if key != "@"}
    return [strip_spans(item) for item in node] if isinstance(node, list) else node


def provider_calls(node):
    if isinstance(node, dict):
        if node.get("k") == "perform" and node.get("class") == "provider":
            yield node
        node = list(node.values())
    for child in node if isinstance(node, list) else ():
        yield from provider_calls(child)


@functools.cache
def reviewer(arm):
    """The arm's compiled review call (the one returning `Review`): its prompt template and fill kinds, the
    `Review` descriptor without its module name, and its binding (policy, provider)."""
    source, entry, source_root, providers, _ = prepare.ARMS[arm]
    program = prepare_closed_program_bundle(FrontendBuildRequest(
        source_path=REPO / source, source_roots=(REPO / source_root,), entry_workflow=entry,
        provider_externs_path=REPO / providers, workspace_root=REPO)).program
    (review,) = [c for c in provider_calls(program.tree) if c["result"].get("name", "").endswith("::Review")]
    module = entry.split("::")[0]
    return {"template": review["prompt"]["template"],
            "fills": [strip_spans({k: v for k, v in fill.items() if k != "value"})
                      for fill in review["prompt"]["fills"]],
            "review": json.loads(json.dumps(review["result"]).replace(f'"{module}::', '"')),
            "binding": (strip_spans(review["policy"]), review["provider"])}


def test_review_once_compiles_the_reviewer_of_reviewed_change():
    assert reviewer("review_once") == reviewer("reviewed_change")


def test_the_reviewer_is_bound_as_in_reviewed_change():
    policy, provider = reviewer("reviewed_change")["binding"]
    assert ({name: value["v"] for name, value in policy.items()}, provider) == (
        {"model": "gpt-6-sol", "effort": "high", "timeout_sec": 5400}, "codex_unrestricted_workspace")


def test_inputs_name_the_candidate_the_intent_and_the_fixed_account(world):
    records, record = start(world, "review_once")
    assert (json.loads((records / "inputs.json").read_text()), record["cwd"]) == (
        {"repo": record["candidates"][0], "intent": (world.task / "intent.txt").read_text(),
         "account": prepare.REVIEW_ONCE_ACCOUNT, "replies": prepare.REVIEW_ONCE_REPLIES}, record["candidates"][0])



@pytest.mark.parametrize("field", ["account", "replies"])
def test_run_refuses_overriding_the_frozen_review_inputs(world, field):
    with pytest.raises(SystemExit, match="frozen by the calibration criterion"):
        start(world, "review_once", sets=[f"{field}=other"])


def test_a_failed_review_has_no_blocker_count(world):
    _, collected = drive(world, "review_once", ["true"], None, outcome="failed")
    assert (collected["outcome"], collected["blockers"]) == ("failed", None)

def test_record_names_the_applied_patch_and_its_hash(world):
    patch = world.task / "anchors" / "upstream.diff"
    _, record = start(world, "review_once", apply=patch)
    assert record["applied"] == {"path": str(patch.resolve()), "sha256": hashlib.sha256(patch.read_bytes()).hexdigest()}


def test_the_collected_patch_is_uncommitted_in_the_candidate_when_the_sandboxed_reviewer_starts(world):
    control, _ = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    _, record = start(world, "review_once", apply=control / "collected" / "final.diff")
    done = call(world, record, "git status --porcelain; git rev-parse HEAD; cat pkg/calc.py; echo p > /tmp/p",
                binary="codex")
    assert (done.stdout.splitlines()[1:], (Path(record["tree"]) / "tmp" / "p").is_file()) == (
        [" M pkg/calc.py", "?? pkg/extra.py", record["compare_base"], "def add(a, b):", "    return a + b"], True)


def test_run_refuses_a_patch_that_does_not_apply_and_leaves_no_run(world):
    patch = world.tmp / "stale.diff"
    patch.write_text(UPSTREAM.replace("return a - b", "return a * b"))
    with pytest.raises(SystemExit, match="does not apply to the seeded candidate"):
        start(world, "review_once", apply=patch)
    assert ([*(world.root / "records" / "review_once").iterdir()], [*(world.root / "agents").iterdir()]) == ([], [])


@pytest.mark.parametrize("arm, sets, apply", [
    ("review_once", (), None),
    ("direct_task", ("model=m", "effort=high"), "anchors/upstream.diff"),
])
def test_run_takes_a_patch_for_review_once_and_for_no_other_arm(world, arm, sets, apply):
    with pytest.raises(SystemExit, match="--apply"):
        prepare.run_arm(world.task, arm, world.root, world.runtime, sets=sets, apply=apply and world.task / apply)


def test_cli_prints_a_command_that_runs_review_once_in_its_candidate(world, capsys):
    prepare.main(["run", "--task", str(world.task), "--arm", "review_once", "--root", str(world.root),
                  "--runtime", str(world.runtime), "--apply", str(world.task / "anchors" / "upstream.diff")])
    command = capsys.readouterr().out
    seen = json.loads(subprocess.run(["bash", "-c", command], capture_output=True, text=True, check=True).stdout)
    record = json.loads(next((world.root / "records" / "review_once").glob("run-*/record.json")).read_text())
    h = world.runtime / "experiments" / "compare"
    assert (seen["cwd"], seen["argv"][:8]) == (record["candidates"][0], [
        "run", str(h / "control/review_once.orc"), "--entry-workflow", "control/review_once::review-once",
        "--source-root", str(h), "--provider-externs-file", str(h / "control/review_once.providers.json")])


@pytest.mark.parametrize("review, blockers, findings", [
    (APPROVE | {"notes": ["a nit"]}, 0, []),
    ({"variant": "REQUEST_CHANGES", "report": REPORT, "summary": "s", "findings": ["x", "y", "z"]}, 3, ["x", "y", "z"]),
    ({"variant": "WRONG_APPROACH", "report": REPORT, "reason": "redesign"}, 1, []),
    ({"variant": "NEEDS_HUMAN", "question": "whose call?"}, 0, []),
], ids=["approve", "request-changes", "wrong-approach", "needs-human"])
def test_collect_counts_the_reviews_blockers(world, review, blockers, findings):
    _, collected = drive(world, "review_once", ["true"], review)
    assert (collected["variant"], collected["blockers"], collected["findings"], collected["review"]) == (
        review["variant"], blockers, findings, review)


@pytest.mark.parametrize("script, changed", [
    (f"mkdir -p artifacts/review && echo report > {REPORT}", False),
    (edit("$PWD", "b + a"), True),
], ids=["report-only", "edited"])
def test_collect_records_whether_the_reviewer_changed_the_candidate(world, script, changed):
    control, _ = drive(world, "direct_task", [edit("$PWD", "a + b")], True)
    _, collected = drive(world, "review_once", [script], APPROVE, apply=control / "collected" / "final.diff")
    assert collected["candidate_changed"] is changed
