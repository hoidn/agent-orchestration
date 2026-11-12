"""Phase 3b T2: the `declaration` input part carries no source position, and runs recorded under the earlier rule resume.

Every test drives the public command line with local stand-ins on a closed PATH; no model is called. Journals written by
the earlier rule are the recorded run roots of `tests/fixtures/declaration_pre_change/` (never regenerated). A recorded
`declaration` is accepted only when it equals one of the two rules applied to the node being compared, so the
"still refuses" cases rewrite a journal's `declaration` to the digest of a node that differs by one edit.
"""
from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

from orchestrator.contracts.closed_program.program import strip_node_provenance, strip_provenance
from orchestrator.contracts.closed_program.sites import _ast_nodes
from orchestrator.workflow.evaluated.agent_turns import provider_view
from orchestrator.workflow.evaluated.declaration import (
    declaration_digest, declaration_for_replay, legacy_declaration_digest,
)
from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.agent_session_shims import FAKE_CLAUDE, FAKE_CODEX, closed_path
from tests.test_workflow_evaluated_agent_turns import PLAN
from tests.test_workflow_evaluated_edit_resume_baseline import (
    RECORDED, _cli, _new_rows, _pending_agent_turn_is_recovered, _recorded, _recorded_workspace, _rows, _shim,
)

PROVIDER_RUN = ("prov.orc", "--source-root", ".", "--provider-externs-file", "providers.json",
                "--prompt-externs-file", "prompts.json", "--command-boundaries-file", "commands.json")
AGENT_RUN = ("main.orc", "--source-root", ".", "--provider-externs-file", "providers.json", "--input", "task=t")
P = "workflow:prov::run / p"


# ---- helpers ---------------------------------------------------------------------------------------------------

def _workspace(case: str, root: Path, source: str | None = None) -> dict[str, str]:
    """A recorded case's sources (no run) in `root`, optionally with an edited main source, and its stand-ins."""
    shutil.copytree(RECORDED / case, root, ignore=shutil.ignore_patterns("runs", "README.md"), dirs_exist_ok=True)
    env = {"PATH": closed_path(root / "bin")}
    if case == "provider_committed":
        _shim(root / "bin" / "codex", (root / "codex_shim.py").read_text(encoding="utf-8"))
        env["PROVIDER_SHIM_RESULT"] = '{"ok": true}'
    else:
        _shim(root / "bin" / "codex", FAKE_CODEX)
        _shim(root / "bin" / "claude", FAKE_CLAUDE)
        env.update(CODEX_HOME=str(root / "codex"), CLAUDE_CONFIG_DIR=str(root / "claude"), AGENT_SHIM_PLAN=json.dumps(PLAN))
    if source is not None:
        (root / ("prov.orc" if case == "provider_committed" else "main.orc")).write_text(source, encoding="utf-8")
    return env


def _fresh_run(case: str, root: Path, source: str | None = None) -> tuple[Path, dict[str, str]]:
    env = _workspace(case, root, source)
    ran = _cli(root, env, "run", *(PROVIDER_RUN if case == "provider_committed" else AGENT_RUN))
    assert ran.returncode == 0, ran.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    (root / "requests.jsonl").unlink()          # the run's own calls; later checks count only a resume's
    return run_root, env


def _source(case: str) -> str:
    return (RECORDED / case / ("prov.orc" if case == "provider_committed" else "main.orc")).read_text(encoding="utf-8")


def _starts(run_root: Path) -> dict[str, str]:
    """identity -> `declaration` of each provider-class `started` row."""
    return {row["identity"]: row["input_parts"]["declaration"] for row in _rows(run_root)
            if row["record"] == "started" and "declaration" in row["input_parts"]}


def _node(run_root: Path, site: str) -> dict:
    """The stored program's perform node at `site`, with its source positions."""
    tree = json.loads((run_root / "closed_program.json").read_text(encoding="utf-8"))
    bodies = [tree["body"], *(definition["body"] for definition in tree["definitions"].values())]
    (node,) = [node for body in bodies for node in _ast_nodes(body) if node.get("k") == "perform" and node["site"] == site]
    return node


def _subject(run_root: Path, row: dict) -> dict:
    """The row's declaration subject: the site node, or for an agent turn that node seen as a provider node."""
    node = _node(run_root, row["identity"].rsplit(" / ", 1)[1])
    if node["class"] != "agent_turn":
        return node
    (allocation,) = [r for r in _rows(run_root) if r["record"] == "committed" and r["effect_class"] == "agent"
                     and r["identity"].endswith(" / " + node["agent"]["n"])]
    return provider_view(node, SimpleNamespace(provider=allocation["value"]["provider"]))


def _write_rows(run_root: Path, rows: list[dict]) -> None:
    """Rewrite the journal file between commands (never a reduced row in place), in the journal's own encoding."""
    (run_root / "memo.jsonl").write_bytes(b"".join(
        json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode() + b"\n" for row in rows))


def _rewrite_declaration(run_root: Path, identity: str, digest: str) -> None:
    """Set the `declaration` part of the identity's `started` and `committed` rows and recompute `input_digest`."""
    rows = _rows(run_root)
    for row in rows:
        if row.get("identity") == identity and row["record"] in {"started", "committed"}:
            row["input_parts"] = {**row["input_parts"], "declaration": digest}
            row["input_digest"] = canonical_sha256(row["input_parts"])
    _write_rows(run_root, rows)


def _changed(stderr: str) -> list[str]:
    """The input parts the divergence on the first line names."""
    return ast.literal_eval(re.search(r"input parts changed: (\[[^]]*\])", stderr.splitlines()[0]).group(1))


def _has_position(value) -> bool:
    if isinstance(value, dict):
        return "@" in value or any(_has_position(item) for item in value.values())
    return isinstance(value, list) and any(_has_position(item) for item in value)


def _no_dispatch(root: Path) -> bool:
    return not (root / "requests.jsonl").exists() and not list((root / "bin").glob(".*.calls"))


# ---- the rule ----------------------------------------------------------------------------------------------------

def test_comment_and_blank_lines_give_the_same_provider_declaration(tmp_path: Path) -> None:
    edited = _source("provider_committed").replace(
        "  (defworkflow run", "  ; a comment line\n\n\n  (defworkflow run").replace(
        ':model "chosen-model" :effort "low"', ':effort "low" :model "chosen-model"')
    first, _ = _fresh_run("provider_committed", tmp_path / "a")
    second, _ = _fresh_run("provider_committed", tmp_path / "b", edited)

    assert _starts(first)[P] == _starts(second)[P]


@pytest.mark.parametrize(("old", "new"), [
    ('"chosen-model"', '"other-model"'),
    (':effort "low"', ':effort "high"'),
    (":inputs (s1)", ":inputs ((+ s1 0))"),
    ("s1", "t1"),
], ids=["model", "literal", "operand_shape", "binder_name"])
def test_model_literal_operand_shape_and_binder_name_change_the_declaration(tmp_path: Path, old: str, new: str) -> None:
    """The edited run is recorded in the same workspace path as the base, so only the edit can move the digest."""
    base, _ = _fresh_run("provider_committed", tmp_path / "w")
    declared = _starts(base)[P]
    shutil.rmtree(tmp_path / "w")
    assert old in _source("provider_committed")
    edited, _ = _fresh_run("provider_committed", tmp_path / "w", _source("provider_committed").replace(old, new))

    assert _starts(edited)[P] != declared


def test_agent_turn_declaration_ignores_positions(tmp_path: Path) -> None:
    edited = _source("agent_turns_committed").replace("  (defworkflow run", "  ; a comment line\n\n  (defworkflow run")
    first, _ = _fresh_run("agent_turns_committed", tmp_path / "a")
    second, _ = _fresh_run("agent_turns_committed", tmp_path / "b", edited)

    assert len(_starts(first)) == 4 and _starts(first) == _starts(second)


def test_node_stripping_equals_the_node_taken_from_the_stripped_program() -> None:
    """`strip_node_provenance` is the program digest's stripping, applied to one perform node (every recorded case)."""
    programs = [json.loads(path.read_text(encoding="utf-8")) for path in sorted(RECORDED.glob("*/runs/*/closed_program.json"))]
    pairs = []
    for tree in programs:
        stripped = strip_provenance(tree)
        for raw_body, clean_body in zip([tree["body"], *(d["body"] for d in tree["definitions"].values())],
                                        [stripped["body"], *(d["body"] for d in stripped["definitions"].values())]):
            raw = [node for node in _ast_nodes(raw_body) if node.get("k") == "perform"]
            clean = [node for node in _ast_nodes(clean_body) if node.get("k") == "perform"]
            pairs.extend(zip(raw, clean, strict=True))

    assert len(pairs) >= 10 and all(strip_node_provenance(raw) == clean for raw, clean in pairs)
    assert not any(_has_position(clean) for _raw, clean in pairs)


def test_old_digest_is_used_only_when_both_rules_agree_on_the_written_subject() -> None:
    """Design §2: the recorded old-rule value stands for the current one only when the subject in the writing program
    has the current subject's new-rule digest. Under one program both are the same node; a later program differs."""
    node = _node(next(RECORDED.glob("provider_committed/runs/*")), "p")
    other = copy.deepcopy(node)
    other["policy"]["model"]["v"] = "other-model"

    assert declaration_for_replay(legacy_declaration_digest(node), node, node) == legacy_declaration_digest(node)
    assert declaration_for_replay(legacy_declaration_digest(other), node, other) == declaration_digest(node)
    assert declaration_for_replay(legacy_declaration_digest(other), node, node) == declaration_digest(node)


# ---- runs recorded under the earlier rule ------------------------------------------------------------------------

def test_pre_change_agent_turns_resume_without_dispatch(tmp_path: Path) -> None:
    run_root, env = _recorded("agent_turns_committed", tmp_path)
    recorded = _rows(run_root)
    turns = [row for row in recorded if row["record"] == "committed" and row["effect_class"] == "agent_turn"]
    assert len(turns) == 4 and all(row["input_parts"]["declaration"] == legacy_declaration_digest(_subject(run_root, row))
                                   != declaration_digest(_subject(run_root, row)) for row in turns)

    resumed = _cli(tmp_path, {**env, "AGENT_SHIM_PLAN": "{}"}, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert _rows(run_root) == recorded and _no_dispatch(tmp_path)


def test_pre_change_pending_agent_turn_is_recovered_at_its_ordinal() -> None:
    """The pending `b1` reaches comparison point 2 after the committed `a1` passed point 1; the turns started after
    the recovery record the new rule, and the journal that mixes both rules then resumes with nothing to do."""
    with _recorded_workspace("agent_turn_pending") as root:
        _pending_agent_turn_is_recovered(root)
        (run_root,) = (root / ".orchestrate" / "runs").iterdir()
        rows = _rows(run_root)
        recorded = {row["identity"] for row in rows[:8] if row["record"] == "started"}
        mixed = {row["identity"]: row["input_parts"]["declaration"] == declaration_digest(_subject(run_root, row))
                 for row in rows if row["record"] == "committed" and row["effect_class"] == "agent_turn"}
        assert mixed == {identity: identity not in recorded for identity in mixed} and len(mixed) == 4
        (root / "requests.jsonl").unlink()

        again = _cli(root, {"PATH": closed_path(root / "bin"), "CODEX_HOME": str(root / "codex"),
                            "CLAUDE_CONFIG_DIR": str(root / "claude"), "AGENT_SHIM_PLAN": "{}"}, "resume", run_root.name)

        assert again.returncode == 0, again.stderr
        assert _rows(run_root) == rows and not (root / "requests.jsonl").exists()


def test_pre_change_phased_commit_resumes_without_dispatch(tmp_path: Path) -> None:
    run_root, env = _recorded("phased_committed", tmp_path)
    recorded = _rows(run_root)
    (phased,) = [row for row in recorded if row["record"] == "committed"]
    assert phased["input_parts"]["declaration"] == legacy_declaration_digest(_subject(run_root, phased))

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert phased["identity"] not in {row["identity"] for row in _new_rows(run_root, recorded, "started")}
    assert not (tmp_path / "phased-events.jsonl").exists()
    rows = _rows(run_root)
    again = _cli(tmp_path, env, "resume", run_root.name)
    assert again.returncode == 0, again.stderr
    assert _rows(run_root) == rows and not (tmp_path / "phased-events.jsonl").exists()


def test_pre_change_pending_phased_attempt_is_recovered(tmp_path: Path) -> None:
    """As on the base (`tests/test_workflow_evaluated_edit_resume_baseline.py`): the prepared attempt's transport
    reservation is gone, so resume refuses before any write. A pending phased attempt is never compared with a fresh
    input outside a plan (its receipt binds the recorded digest, and recovery starts a new attempt), so this pins that
    the new rule adds no refusal ahead of the base's; the planner's kept-pending test (T6) is where it is compared."""
    run_root, env = _recorded("phased_pending", tmp_path)
    (start,) = [row for row in _rows(run_root) if row["record"] == "started"]
    assert start["input_parts"]["declaration"] == legacy_declaration_digest(_subject(run_root, start))
    receipt = json.loads((run_root / start["result_path"]).with_name("phased-attempt.json").read_text())
    if (Path("/tmp") / receipt["transport"]["namespace"]).exists():
        pytest.skip("the recording host still holds this reservation")
    before = {path: path.read_bytes() for path in run_root.rglob("*") if path.is_file() and path.name != "run.lock"}

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 2 and "[provider_phased_cleanup_failed]" in resumed.stderr.splitlines()[0]
    assert {path: path.read_bytes() for path in run_root.rglob("*") if path.is_file() and path.name != "run.lock"} == before


# ---- a recorded value that is no rule of the current node --------------------------------------------------------

def _edited_node(node: dict, edit: str) -> dict:
    """The node with one edit; source positions are left as they are, so only the edit differs."""
    node = copy.deepcopy(node)
    (row,) = node["inputs"]
    if edit == "other_digest":
        return {**node, "site": "an unrelated node"}
    if edit == "model":
        node["policy"]["model"]["v"] = "other-model"
    elif edit == "literal":
        node["policy"]["effort"]["v"] = "high"
    elif edit == "binder_name":
        row[0], row[2]["n"] = "t1", "t1"
    elif edit == "operand_shape":
        zero = {"@": row[2]["@"], "k": "lit", "type": {"kind": "primitive", "name": "Int"}, "v": 0}
        row[2] = {"@": row[2]["@"], "args": [row[2], zero], "k": "op", "op": "+"}
    return node


@pytest.mark.parametrize("journal", ["old_rule", "new_rule"])
@pytest.mark.parametrize("edit", ["other_digest", "model", "literal", "binder_name", "operand_shape"])
def test_recorded_declaration_that_matches_neither_rule_diverges(tmp_path: Path, journal: str, edit: str) -> None:
    """The journal's `declaration` is set to the digest, under the rule that wrote the journal, of the provider node
    with one edit. The current node is unchanged, so neither rule applied to it gives the recorded value."""
    if journal == "old_rule":
        run_root, env = _recorded("provider_committed", tmp_path)
        rule = legacy_declaration_digest
    else:
        run_root, env = _fresh_run("provider_committed", tmp_path)
        rule = declaration_digest
    node = _node(run_root, "p")
    assert _starts(run_root)[P] == rule(node)
    _rewrite_declaration(run_root, P, rule(_edited_node(node, edit)))
    before = (run_root / "memo.jsonl").read_bytes()

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 2 and "[effect_input_diverged]" in resumed.stderr.splitlines()[0]
    assert _changed(resumed.stderr) == ["declaration"]
    assert (run_root / "memo.jsonl").read_bytes() == before and not (tmp_path / "requests.jsonl").exists()


@pytest.mark.parametrize("journal", ["old_rule", "new_rule"])
def test_changed_prompt_file_diverges_on_a_journal_of_either_rule(tmp_path: Path, journal: str) -> None:
    run_root, env = (_recorded("provider_committed", tmp_path) if journal == "old_rule"
                     else _fresh_run("provider_committed", tmp_path))
    (tmp_path / "prompt.md").write_text("Review the step twice.\n", encoding="utf-8")
    before = (run_root / "memo.jsonl").read_bytes()

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 2 and "[effect_input_diverged]" in resumed.stderr.splitlines()[0]
    assert "declaration" not in _changed(resumed.stderr) and "prompt" in _changed(resumed.stderr)
    assert (run_root / "memo.jsonl").read_bytes() == before and not (tmp_path / "requests.jsonl").exists()


# ---- new attempts ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("ending", ["failed", "interrupted"])
def test_a_retry_after_a_failed_provider_records_the_new_rule(tmp_path: Path, ending: str) -> None:
    """The recorded journal cut back to `p`'s old-rule `started` row (a kill before its commit), or closed there with
    the `failed` and `terminal` rows a failing stand-in writes; the next attempt records the new rule."""
    run_root, env = _recorded("provider_committed", tmp_path)
    rows = _rows(run_root)
    prefix = rows[:[row.get("identity") for row in rows].index(P) + 1]
    failure = [{"attempt": 1, "code": "provider_exit_nonzero", "exit_info": {"error": None, "exit_code": 9},
                "identity": P, "record": "failed"},
               {"code": "provider_exit_nonzero", "message": "evaluated provider failed: 9", "outcome": "failed",
                "record": "terminal"}]
    written = prefix + (failure if ending == "failed" else [])
    _write_rows(run_root, written)
    shutil.rmtree(run_root / "effects" / hashlib.sha256(b"workflow:prov::run / s3").hexdigest())

    resumed = _cli(tmp_path, env, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    (retry,) = [row for row in _new_rows(run_root, written, "started") if row["identity"] == P]
    assert retry["attempt"] == 2 and retry["input_parts"]["declaration"] == declaration_digest(_node(run_root, "p"))
    assert prefix[-1]["input_parts"]["declaration"] != retry["input_parts"]["declaration"]


# ---- collisions --------------------------------------------------------------------------------------------------

TWIN = '''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
  (defmodule prov) (export run)
  (defrecord Review (ok Bool))
  (defproc first ((s1 Int)) -> Review
    :effects ((uses-provider providers.review))
    (let* ((r (provider-result providers.review :prompt prompts.base :inputs (s1)
                :model "chosen-model" :effort "low" :returns Review)))
      r))
  (defproc second ((s1 Int)) -> Review
    :effects ((uses-provider providers.review))
    (let* ((r (provider-result providers.review :prompt prompts.base :inputs (s1)
                :model "chosen-model" :effort "low" :returns Review)))
      r))
  (defworkflow run ((n Int :default 0)) -> Bool
    (let* ((a (first n))
           (b (second n)))
      b.ok)))
'''


def test_identical_provider_calls_at_two_sites_commit_and_resume_independently(tmp_path: Path) -> None:
    """Two procedures hold the same provider call: one `declaration` digest, two identities (and two result paths).
    The second fails; resume reuses the first and runs only the second; a later resume dispatches nothing."""
    env = _workspace("provider_committed", tmp_path, TWIN)
    failed = _cli(tmp_path, {**env, "PROVIDER_SHIM_RESULTS": json.dumps(['{"ok": true}', '{"ok": "not-bool"}'])},
                  "run", *PROVIDER_RUN)
    assert failed.returncode == 1, failed.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    starts = [row for row in _rows(run_root) if row["record"] == "started"]
    first, second = (row["identity"] for row in starts)
    assert first != second and len({row["input_parts"]["declaration"] for row in starts}) == 1
    recorded = _rows(run_root)

    resumed = _cli(tmp_path, {**env, "PROVIDER_SHIM_RESULTS": json.dumps(['{"ok": true}'] * 3)}, "resume", run_root.name)

    assert resumed.returncode == 0, resumed.stderr
    assert [(row["identity"], row["attempt"]) for row in _new_rows(run_root, recorded, "started")] == [(second, 2)]
    assert len((tmp_path / "requests.jsonl").read_text().splitlines()) == 3
    rows = _rows(run_root)
    again = _cli(tmp_path, env, "resume", run_root.name)
    assert again.returncode == 0, again.stderr
    assert _rows(run_root) == rows and len((tmp_path / "requests.jsonl").read_text().splitlines()) == 3
