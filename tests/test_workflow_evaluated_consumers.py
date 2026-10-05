"""Maintained consumers at 2.35 against their accepted old route, with deterministic stand-ins.

`std/improve` with its stand-in launcher, the reviewed change and serial best-of-N of
the single-call comparison, and the generic run watchdog. Every scenario runs on both
routes; values, ordered requests and counts agree apart from R1–R12, and the 2.35 run
is stopped after a relevant commit, resumed through the CLI and resumed again once
completed without dispatching anything again.
"""

from __future__ import annotations

from itertools import chain
import json
from pathlib import Path
import re

import pytest

from orchestrator.workflow.run_ref.contracts import canonical_sha256
from tests.test_workflow_evaluated_cli import _run_cli
from tests.test_workflow_lisp_improve_example_e2e import APPROVED_LAUNCH, EXHAUSTED_LAUNCH, QUESTION, _params
from tests.workflow_evaluated_consumer_sources import (
    BUGGY, CANDIDATES, PROGRAMS, SITE, assert_request_lineage, checked_run, compile_current, executions, flat_outputs,
    git, install, install_shims, jsonl, lineage, missing_edges, old_route, request_view, requests,
    resume_to_completion, routes, sha256, stop_after,
)


def _owners(route) -> list[tuple[str, str]]:
    """Effect class and owning definition of each commit, in journal order."""
    return [(data["effect_class"], re.findall(r"(?:workflow|procedure):([^\s\[]+)", data["identity"])[-1])
            for data in route.commits]


def _chain(count: int) -> list[list[int]]:
    """C9 when each commit's resolved input reads a result of every earlier commit."""
    return [list(range(index)) for index in range(count)]


def _predecessors(count: int) -> list[set[int]]:
    """Required C9 edges when each effect's resolved input reads its predecessor's result."""
    return [set(), *({index - 1} for index in range(1, count))]


def _files(root: Path, *bases: str) -> dict[str, bytes]:
    """Bytes of each file under `bases`, outside any `.git` directory."""
    return {path.relative_to(root).as_posix(): path.read_bytes()
            for base in bases for path in sorted((root / base).rglob("*"))
            if path.is_file() and ".git" not in path.relative_to(root).parts}


# std/improve ----------------------------------------------------------------------

REVIEW = "decision=procedure:improve_experiment_proposal::review-proposal"
REVISION = "next=procedure:improve_experiment_proposal::revise-proposal"
VERDICTS = {
    "APPROVE": lambda hypothesis: {"variant": "APPROVE", "evidence": {"notes": f"methods:ok:{hypothesis}"}},
    "BLOCKED": lambda hypothesis: {"variant": "BLOCKED", "reason": {"issue": f"methods:blocked:{hypothesis}"}},
}


def _proposal(revisions: int) -> dict:
    notes = [f"methods:add-{index}" for index in range(1, revisions + 1)]
    return {"hypothesis": QUESTION + "+r" * revisions, "parameters": _params(*notes)}


def _improve_plan(*verdicts: str) -> dict:
    """The reviewer's verdict per round; each REVISE is answered by the reviser's next proposal."""
    answers = []
    for revisions, verdict in enumerate(verdicts):
        if verdict == "REVISE":
            feedback = {"variant": "REVISE", "feedback": {"notes": f"methods:add-{revisions + 1}"}}
            answers += [{"result": feedback}, {"result": _proposal(revisions + 1)}]
        else:
            answers.append({"result": VERDICTS[verdict](_proposal(revisions)["hypothesis"])})
    return {"codex": answers}


def _improve_required(route) -> list[set[int]]:
    """Each effect reads its predecessor's result; the launch also reads the last revision's proposal."""
    required = _predecessors(len(route.commits))
    required[-1].add(max(index for index, data in enumerate(route.commits) if "revise-proposal" in data["identity"]))
    return required


BLOCKED_LAUNCH = {**APPROVED_LAUNCH, "outcome": "blocked", "note": "methods:blocked:warmup+r"}
IMPROVE = [
    pytest.param(("REVISE", "APPROVE"), REVIEW, 1, "launched", APPROVED_LAUNCH, id="approved-after-committed-review"),
    pytest.param(("REVISE", "APPROVE"), REVISION, 2, "launched", APPROVED_LAUNCH,
                 id="approved-after-committed-revision"),
    pytest.param(("REVISE", "BLOCKED"), REVISION, 2, "held", BLOCKED_LAUNCH, id="blocked-after-committed-revision"),
    pytest.param(("REVISE",) * 3, "loop:state[3] / REVISE", 6, "held", EXHAUSTED_LAUNCH,
                 id="exhausted-after-final-continue"),
]


@pytest.mark.parametrize("verdicts,marker,paused,status,launch", IMPROVE)
def test_public_improve_launcher_consumes_the_returned_proposal(tmp_path, monkeypatch, verdicts, marker, paused,
                                                                status, launch):
    old, new = routes(tmp_path, monkeypatch, "improve", _improve_plan(*verdicts), {"question": QUESTION}, marker)

    (command,) = [data for data in new.commits if data["effect_class"] == "command"]
    (old_argv,), (new_argv,) = (jsonl(route.root / "scripts/launch_experiment.py.argv.jsonl") for route in (old, new))
    interpreter = json.loads((new.authority.run_root / "run.json").read_text(encoding="utf-8"))["interpreters"]
    assert {"value": new.value, "providers": len(new.requests), "paused": len(new.paused),
            "launches": [jsonl(route.root / "scripts/launch_experiment.log") for route in (old, new)],
            "argv": [old_argv["argv"], new_argv["argv"][0]], "argv_digest": command["input_parts"]["argv"],
            "command_env": [new_argv["bundle"], new_argv["PYTHONDONTWRITEBYTECODE"]],
            "owners": _owners(new)[-1], "first": lineage(new)[0],
            "missing": missing_edges(new, _improve_required(new))} == {
        "value": {"status": status}, "providers": 2 * len(verdicts) - (verdicts[-1] != "REVISE"), "paused": paused,
        "launches": [[launch], [launch]], "argv": [["python", *new_argv["argv"][1:]], interpreter["python"]["path"]],
        "argv_digest": canonical_sha256(["python", *new_argv["argv"][1:]]),
        "command_env": [new.result(command), "1"],
        "owners": ("command", "improve_experiment_proposal::execute"), "first": [], "missing": [[]] * len(new.commits)}


# Reviewed change -------------------------------------------------------------------

FIXED = "def add(a, b):\n    return a + b\n"
CHANGE = {"result": {"summary": "Fix add.", "account": "add subtracted; it now adds."},
          "files": {"repo/calc.py": FIXED}}
REVISED = {"result": {"summary": "Add a test.", "account": "add adds; a test covers it.", "replies": "none"},
           "files": {"repo/test_calc.py": "from calc import add\nassert add(2, 3) == 5\n"}}
REDO = {"result": {"summary": "Redo the fix.", "account": "add is rewritten."}, "files": {"repo/calc.py": FIXED}}
QUESTION_FOR_HUMAN = "Should add also accept strings?"
NEEDS_HUMAN = {"result": {"variant": "NEEDS_HUMAN", "question": QUESTION_FOR_HUMAN}}


def _review(variant: str, round_: int, **fields) -> dict:
    report = f"artifacts/review/round-{round_}.md"
    return {"result": {"variant": variant, "report": report, **fields}, "files": {report: f"# Round {round_}\n"}}


def _changes(round_: int) -> dict:
    return _review("REQUEST_CHANGES", round_, summary=f"round {round_}: no test", findings=["add a regression test"])


APPROVE_2 = _review("APPROVE", 2, notes=["fine"])
READY = {"variant": "READY", "report": "artifacts/review/round-2.md", "rounds": 2}
REVIEWED = [
    pytest.param({"claude": [CHANGE, REVISED], "codex": [_changes(1), APPROVE_2]}, "REQUEST_CHANGES / else / revision",
                 3, READY, id="request-changes-then-approve"),
    pytest.param({"claude": [CHANGE, REDO], "codex": [_review("WRONG_APPROACH", 1, reason="patch the caller"),
                                                       APPROVE_2]}, "loop:state[1] / review", 2, READY,
                 id="wrong-approach-then-approve"),
    pytest.param({"claude": [CHANGE], "codex": [NEEDS_HUMAN]},
                 " / change", 1, {"variant": "ESCALATED", "question": QUESTION_FOR_HUMAN}, id="needs-human-escalated"),
    pytest.param({"claude": [CHANGE, REVISED, REVISED], "codex": [_changes(1), _changes(2), _changes(3)]},
                 "loop:state[2] / REQUEST_CHANGES / else / revision", 5,
                 {"variant": "UNRESOLVED", "reason": "round 3: no test", "rounds": 3},
                 id="unresolved-after-three-rounds"),
]


@pytest.mark.parametrize("plan,marker,paused,value", REVIEWED)
def test_public_reviewed_change_keeps_independent_review_order(tmp_path, monkeypatch, plan, marker, paused, value):
    inputs = {"task": "Fix add in repo/calc.py so that it returns the sum.", "intent": "add returns a + b",
              "repo": "repo"}

    old, new = routes(tmp_path, monkeypatch, "reviewed_change", plan, inputs, marker)

    calls = len(plan["claude"]) + len(plan["codex"])
    assert {"value": new.value, "tools": [request["tool"] for request in new.requests], "paused": len(new.paused),
            "owners": set(_owners(new)), "first": lineage(new)[0], "missing": missing_edges(new, _predecessors(calls)),
            "reports": [_files(route.root, "artifacts") for route in (old, new)],
            "repo": [_files(route.root / "repo", ".") for route in (old, new)]} == {
        "value": value, "tools": ["claude", "codex"] * (calls // 2), "paused": paused,
        "owners": {("provider", "reviewed_change::reviewed-change")}, "first": [], "missing": [[]] * calls,
        "reports": [{name: text.encode() for answer in plan["codex"]
                     for name, text in answer.get("files", {}).items()}] * 2,
        "repo": [{"calc.py": BUGGY.encode(), **{name.removeprefix("repo/"): text.encode() for answer in plan["claude"]
                                                for name, text in answer["files"].items()}}] * 2}
    assert value.get("report") is None or (new.root / value["report"]).is_file()


# Serial best-of-N --------------------------------------------------------------------

FIXED_ALT = "def add(a, b):\n    return sum((a, b))\n"
SELECTION = {"winner": CANDIDATES[1], "ranking": [f"{CANDIDATES[1]}: 2 2 2 2", f"{CANDIDATES[0]}: 1 1 1 1"],
             "report": "artifacts/review/selection.md"}
BEST_OF_N = {
    "repos": list(CANDIDATES),
    "claude": [{"result": {"summary": "Fix add.", "account": "first candidate"}, "files": {"{repo}/calc.py": FIXED}},
               {"result": {"summary": "Fix add.", "account": "second candidate"},
                "files": {"{repo}/calc.py": FIXED_ALT}}],
    "codex": [{"result": SELECTION, "files": {SELECTION["report"]: "# Selection\n"}}],
}


def _candidate(root: Path) -> dict:
    status = {repo: git(root / repo, "status", "--porcelain") for repo in CANDIDATES}
    return {"status": status, "bases": len({git(root / repo, "rev-parse", "HEAD") for repo in CANDIDATES}),
            "calc": [(root / repo / "calc.py").read_text(encoding="utf-8") for repo in CANDIDATES]}


@pytest.mark.parametrize("marker,paused", [("loop:#1[1]", 1), ("loop:#1[2]", 2)],
                         ids=["after-first-candidate", "after-second-candidate"])
def test_public_best_of_n_runs_isolated_candidates_serially_then_the_judge(tmp_path, monkeypatch, marker, paused):
    inputs = {"task": "Fix add in calc.py so that it returns the sum.", "intent": "add returns a + b",
              "repos": list(CANDIDATES)}

    old, new = routes(tmp_path, monkeypatch, "best_of_n", BEST_OF_N, inputs, marker)

    candidates = [_candidate(route.root) for route in (old, new)]
    first, second, judge = lineage(new)
    assert set(second) <= {0}  # C9 requires no edge here; the observed edge to the first candidate is reported
    assert {"value": new.value, "requests": [(request["tool"], request["repos"]) for request in new.requests],
            "paused": len(new.paused), "owners": _owners(new), "lineage": [first, judge],
            "candidates": candidates, "report": (new.root / SELECTION["report"]).is_file()} == {
        "value": SELECTION, "requests": [("claude", [CANDIDATES[0]]), ("claude", [CANDIDATES[1]]),
                                         ("codex", list(CANDIDATES))],
        "paused": paused,
        "owners": [("provider", "best_of_n::implement-one")] * 2 + [("provider", "best_of_n::best-of-n")],
        "lineage": [[], [0, 1]], "candidates": [candidates[0]] * 2, "report": True}
    assert candidates[0]["calc"] == [FIXED, FIXED_ALT] and candidates[0]["bases"] == 1
    assert candidates[0]["status"] == {repo: " M calc.py\n" for repo in CANDIDATES}


# Generic run watchdog ------------------------------------------------------------------

EVIDENCE = "artifacts/work/watchdog"
PROBE = "workflows/library/scripts/probe_orchestrator_run.py"
PUBLISHER = "workflows/library/scripts/publish_run_watchdog_result.py"
PUBLISH_FLAGS = ("--repair-result-path", "--target-run-id", "--watch-status", "--repair-required",
                 "--recommended-recovery", "--evidence-bundle-path", "--repair-status", "--fix-complexity",
                 "--recovery-action", "--repair-report-path", "--plan-path", "--new-run-id", "--output")
REPAIRED = {"repair_status": "FIXED_AND_RESUMED", "fix_complexity": "TRIVIAL", "recovery_action": "RESUME",
            "repair_report_path": f"{EVIDENCE}/repair-report.md", "plan_path": "", "new_run_id": ""}
REPAIR = {"result": REPAIRED, "files": {f"{EVIDENCE}/repair-report.md": "# Fixture repair report\n",
                                         f"{EVIDENCE}/repair-result.json": json.dumps(REPAIRED, indent=2) + "\n"}}
WATCHDOG = "generic_run_watchdog/watchdog::"
PUBLISHED = [("command", WATCHDOG + "watchdog"), ("command", WATCHDOG + "publish-repair-outcome")]
REPAIR_OUTPUT = {"watch_status": "FAILED", "repair_status": "FIXED_AND_RESUMED", "recovery_action": "RESUME",
                 "watchdog_result_path": "state/watchdog/watchdog-result.json"}


def _watch_inputs(root: Path, status: str, provider: str) -> dict:
    """A target run in its own workspace; with no `updated_at` the watch bundle carries no clock reading."""
    state = root / "target" / ".orchestrate/runs/target-run/state.json"
    state.parent.mkdir(parents=True)
    state.write_text(json.dumps({"schema_version": "2.1", "run_id": "target-run", "status": status, "steps": {},
                                 "workflow_file": "workflows/examples/fixture.yaml"}, indent=2) + "\n")
    return {"target_run_id": "target-run", "target_workspace": str(root / "target"), "state_root": "state/watchdog",
            "evidence_root": EVIDENCE, "repair_result_target_path": f"{EVIDENCE}/repair-result.json",
            "repair_provider": provider}


def _command_requests(old, new, target: str, watch: tuple, repair: tuple) -> None:
    """R9/R12: probe and publisher ran once per route with the same argv on both; the 2.35 commits' argv
    digests are of that argv and of the source operands in order, `${inputs.state_root}` rendered."""
    probe = ["python", PROBE, "--run-id", "target-run", "--target-workspace", target, "--output",
             "state/watchdog/watch.json", "--evidence-root", EVIDENCE, "--repair-result-target-path",
             f"{EVIDENCE}/repair-result.json", "--max-stale-minutes", "60"]
    values = (repair[0], "target-run", *watch, f"{EVIDENCE}/target-run-evidence.json", *repair[1:],
              "state/watchdog/watchdog-result.json")
    publish = ["python", PUBLISHER, *chain.from_iterable(zip(PUBLISH_FLAGS, values, strict=True))]
    commands = [data["input_parts"]["argv"] for data in new.commits if data["effect_class"] == "command"]
    executed = [canonical_sha256(["python", *argv]) for argv in executions((old, new), PROBE, PUBLISHER)]
    assert commands == executed == [canonical_sha256(probe), canonical_sha256(publish)]


WATCH_CASES = {
    "no-action": ("running", "codex", " / watch", [], ("RUNNING_OK", "NO", "NONE"),
                  ("", "NO_ACTION", "NOT_APPLICABLE", "NONE", "", "", "")),
    "codex-repair": ("failed", "codex", "invoke-repair", ["codex"], ("FAILED", "YES", "RESUME"),
                     (f"{EVIDENCE}/repair-result.json", *REPAIRED.values())),
    "claude-repair": ("failed", "claude_opus", "invoke-repair", ["claude"], ("FAILED", "YES", "RESUME"),
                      (f"{EVIDENCE}/repair-result.json", *REPAIRED.values())),
}


def _watch_case(root: Path, monkeypatch, case: str) -> dict:
    status, provider, marker, tools, watch, repair = WATCH_CASES[case]
    inputs = _watch_inputs(root, status, provider)
    old, new = routes(root, monkeypatch, "watchdog", {"codex": [REPAIR], "claude": [REPAIR]}, inputs, marker)
    _command_requests(old, new, inputs["target_workspace"], watch, repair)
    lineage_files = [_files(route.root, "state/watchdog", EVIDENCE) for route in (old, new)]
    assert lineage_files[0] == lineage_files[1]
    repairs = [("provider", WATCHDOG + "invoke-repair")] if tools else []
    assert ([request["tool"] for request in new.requests], _owners(new), lineage(new), len(new.paused)) == (
        tools, PUBLISHED[:1] + repairs + PUBLISHED[1:], _chain(len(new.commits)), 0 if case == "no-action" else 1)
    semantic = json.loads(lineage_files[1]["state/watchdog/watchdog-result.json"])
    return {"outputs": new.value, "lineage_paths": sorted(lineage_files[1]), "semantic_result": semantic}


def test_public_watchdog_both_branches_preserve_artifact_lineage(tmp_path, monkeypatch):
    no_action, codex_repair, claude_repair = (_watch_case(tmp_path / case, monkeypatch, case) for case in WATCH_CASES)

    assert no_action["outputs"] == {"watch_status": "RUNNING_OK", "repair_status": "NO_ACTION",
                                    "recovery_action": "NONE",
                                    "watchdog_result_path": "state/watchdog/watchdog-result.json"}
    assert {"state/watchdog/watch.json", "state/watchdog/watchdog-result.json",
            f"{EVIDENCE}/target-run-evidence.json"}.issubset(no_action["lineage_paths"])
    assert {f"{EVIDENCE}/repair-result.json", f"{EVIDENCE}/repair-report.md"}.isdisjoint(no_action["lineage_paths"])
    assert codex_repair["outputs"] == claude_repair["outputs"] == REPAIR_OUTPUT
    assert no_action["semantic_result"]["repair_result_path"] == ""
    assert codex_repair["semantic_result"]["repair_result_path"] == f"{EVIDENCE}/repair-result.json"
    assert codex_repair["lineage_paths"] == claude_repair["lineage_paths"]
    assert {"state/watchdog/watch.json", "state/watchdog/watchdog-result.json", f"{EVIDENCE}/target-run-evidence.json",
            f"{EVIDENCE}/repair-result.json", f"{EVIDENCE}/repair-report.md"}.issubset(codex_repair["lineage_paths"])


def _publications(root: Path) -> int:
    _, snapshot = checked_run(root)
    return sum(1 for entry in snapshot.entries
               if entry.data["record"] == "started" and "publish-repair-outcome" in entry.data["identity"])


def test_public_watchdog_retry_reuses_provider_and_publishes_once(tmp_path, monkeypatch):
    failing = {"exit": 1, "merge": {"state/watchdog/watch.json": {"fixture_dependency_version": "after-first-attempt"}}}
    install_shims(tmp_path / "bin", monkeypatch, {"codex": [failing, REPAIR]})
    inputs, program, root = _watch_inputs(tmp_path, "failed", "codex"), PROGRAMS["watchdog"], tmp_path / "new"
    old = old_route(tmp_path / "old", install(tmp_path / "old", program, inputs, current=False),
                    "--max-retries", "1", "--retry-delay", "0")
    frontend = install(root, program, inputs, current=True)
    compile_current(root, frontend)
    assert _run_cli(root, *frontend, "--input-file", "inputs.json").returncode != 0
    run_id = checked_run(root)[0].run_root.name
    stop_after(root, ["resume", run_id], "invoke-repair")
    before_resume = (len(requests(root)), _publications(root))

    new = resume_to_completion(root)

    executions((old, new), PROBE, PUBLISHER)
    attempts = [entry.data for entry in new.snapshot.entries
                if entry.data["record"] == "started" and "invoke-repair" in entry.data["identity"]]
    prompts = [(new.authority.run_root / Path(row["result_path"]).parent / "prompt.txt").read_bytes()
               for row in attempts]
    (repaired,) = [data for data in new.commits if data["effect_class"] == "provider"]
    result = (new.authority.run_root / repaired["result_path"]).read_bytes()
    assert (old.value, request_view(old)) == (flat_outputs(new.value), request_view(new))
    assert_request_lineage(new)
    assert {"tools": [request["tool"] for request in new.requests], "attempts": [row["attempt"] for row in attempts],
            "sites": len({request["env"][SITE] for request in new.requests}),
            "dependencies": len({row["input_parts"]["dependency:state/watchdog/watch.json"] for row in attempts}),
            "captured": [sha256(request["prompt"]) for request in new.requests],
            "started": [row["input_parts"]["prompt"] for row in attempts],
            "before_resume": before_resume, "after_resume": (len(new.requests), _publications(root)),
            "result": [repaired["result_digest"], repaired["value"], repaired["input_digest"]],
            "semantic": (root / "state/watchdog/watchdog-result.json").read_bytes(), "outputs": new.value} == {
        "tools": ["codex", "codex"], "attempts": [1, 2], "sites": 1, "dependencies": 2,
        "captured": [sha256(raw) for raw in prompts],
        "started": [sha256(raw) for raw in prompts], "before_resume": (2, 0), "after_resume": (2, 1),
        "result": [sha256(result), json.loads(result), canonical_sha256(repaired["input_parts"])],
        "semantic": (old.root / "state/watchdog/watchdog-result.json").read_bytes(), "outputs": REPAIR_OUTPUT}
    assert len(set(prompts)) == 2
