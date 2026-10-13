"""Finite public W3/native comparison; each pinned runtime runs in its own process."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import traceback
from unittest.mock import patch

import pytest


ROOT = Path(__file__).resolve().parents[2]
NATIVE_PIN = "b0b05d504d4b1be7b1cbaebfadf47ffdc3e66012"
TYPED_PIN = "47e85a9c7e452bfd367275a15d5e97b928efa5ca"
EVIDENCE = Path("/tmp/orc-w3-dynamic-reevaluation-20261012")
W3_IMPROVE = ROOT / "tests/fixtures/workflow_lisp/w3_dynamic_reevaluation/improve.orc"


def _git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args])


def _provenance(root, pin, typed):
    assert root.is_dir(), f"Required runtime checkout is missing: {root}"
    head = _git(root, "rev-parse", "HEAD").decode().strip()
    if typed:
        assert head == pin, "W3 runtime HEAD differs from comparison pin"
        assert not _git(root, "status", "--porcelain"), "W3 comparator must be clean"
    else:
        _git(root, "merge-base", "--is-ancestor", pin, head)
    owners = ["orchestrator", "experiments/mlevolve_pair", "tests"]
    rows = _git(root, "ls-tree", "-r", "-z", pin, "--", *owners).split(b"\0")
    hashes = {}
    for row in rows:
        if not row:
            continue
        metadata, relative = row.split(b"\t")
        name = relative.decode()
        expected = metadata.split()[2].decode()
        path = root / name
        assert path.is_file(), f"Pinned runtime source missing: {path}"
        raw = path.read_bytes()
        actual = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert actual == expected, f"Pinned source modified: {path}"
        hashes[name] = hashlib.sha256(raw).hexdigest()
    allowed = {"tests/fixtures/workflow_lisp/w3_dynamic_reevaluation/improve.orc"} if not typed else set()
    current = set(_git(root, "ls-files", "--", *owners).decode().splitlines())
    untracked = set(_git(root, "ls-files", "--others", "--exclude-standard", "--", *owners).decode().splitlines())
    assert not (current | untracked) - set(hashes) - allowed, "Unapproved runtime/helper source addition"
    return {"root": str(root), "pin": pin, "packet_head": head, "sha256": hashes}


@pytest.fixture(scope="module")
def runtimes():
    supplied = os.environ.get("ORC_W3_REEVALUATION_TYPED_ROOT")
    assert supplied, "Set ORC_W3_REEVALUATION_TYPED_ROOT to the explicitly prepared clean pinned W3 checkout"
    typed = Path(supplied).resolve()
    for root, pin, is_typed in ((ROOT, NATIVE_PIN, False), (typed, TYPED_PIN, True)):
        _provenance(root, pin, is_typed)
    return {"native": ROOT, "w3": typed}


def _pair(runtimes, tmp_path, case, *, native_options=None, w3_options=None, **options):
    results = {}
    for runtime, package_root in runtimes.items():
        workspace = tmp_path / runtime
        workspace.mkdir(parents=True)
        assert not workspace.is_relative_to(package_root)
        selected = {**options, **((w3_options if runtime == "w3" else native_options) or {})}
        if case == "improve":
            from tests.test_workflow_dynamic_improve import _write_probes
            _write_probes(workspace, **{key: selected[key] for key in ("review_script", "revise_script") if key in selected})
        request = {"runtime": runtime, "package_root": str(package_root), "workspace": str(workspace),
                   "case": case, "options": selected, "w3_improve": W3_IMPROVE.read_text()}
        request_path = workspace / "request.json"
        request_path.write_text(json.dumps(request))
        env = {**os.environ, "PYTHONPATH": str(package_root), "PYTHONDONTWRITEBYTECODE": "1"}
        argv = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", str(request_path)]
        completed = subprocess.run(argv, cwd=package_root, env=env, capture_output=True, text=True, timeout=120)
        (workspace / "worker.stdout").write_text(completed.stdout)
        (workspace / "worker.stderr").write_text(completed.stderr)
        (workspace / "worker-command.json").write_text(json.dumps({"argv": argv, "cwd": str(package_root),
                                                                   "exit": completed.returncode}))
        assert completed.returncode == 0, f"{runtime}: {completed.stderr}\nEvidence: {workspace}"
        results[runtime] = json.loads((workspace / "observation.json").read_text())
    return results


def _save_compile(workspace, completed, *, typed=False):
    (workspace / "compile.stdout").write_text(completed.stdout)
    (workspace / "compile.stderr").write_text(completed.stderr)
    (workspace / "compile-command.json").write_text(json.dumps({"argv": completed.args, "cwd": str(workspace),
                                                                "exit": completed.returncode}))
    sources = {str(path.relative_to(workspace)): {"text": path.read_text(),
               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
               for path in workspace.rglob("*.orc") if ".orchestrate" not in path.parts}
    (workspace / "sources-before.json").write_text(json.dumps(sources, indent=2))
    if completed.returncode:
        diagnostics = re.findall(r"^(.+\.orc):(\d+):(\d+):.*?\[([^]]+)\]", completed.stderr, re.MULTILINE)
        assert diagnostics, completed.stderr
        return {"refused": True, "exit": completed.returncode,
                "diagnostics": [{"path": path, "line": int(line), "column": int(column), "code": code}
                                for path, line, column, code in diagnostics]}
    summary = json.loads(completed.stdout)
    key = "closed_program" if typed else "dynamic_program"
    assert set(summary["artifact_paths"]) == {key}
    raw = Path(summary["artifact_paths"][key]).read_bytes()
    artifact = json.loads(raw)
    assert artifact["target"] == ("2.36" if typed else "3.0")
    if typed:
        from orchestrator.workflow_lisp.closed.program import ClosedProgram
        digest = ClosedProgram.from_artifact(raw.decode()).digest
    else:
        from orchestrator.workflow_lisp.dynamic.program import DynamicProgram
        digest = DynamicProgram.from_artifact(raw).digest
    assert summary["program_digest"] == digest
    summary["observed_artifact"] = {"target": artifact["target"], "schema": artifact["schema"],
        "program_digest": digest, "sha256": hashlib.sha256(raw).hexdigest()}
    return summary


def _run_receipt(workspace, compiled, typed):
    header = max(workspace.glob(".orchestrate/runs/*/run.json"), key=lambda path: path.stat().st_mtime_ns)
    observed = json.loads(header.read_text())
    assert observed["program_digest"] == compiled["program_digest"]
    assert observed["result_persistence_profile"] == ("evaluated_execution.v1" if typed else "dynamic_execution.v1")
    return {key: observed[key] for key in ("program_digest", "result_persistence_profile")}


class _CompileRefused(Exception):
    pass


class _Prepared(Exception):
    pass


def _refusal(compiled):
    return {"value": None, "requests": [], "exit": compiled["exit"], "run_root": None,
            "compile": [compiled], "state": None, "phase": "compile", "diagnostics": compiled["diagnostics"]}


def _w3_variant(source, workspace, options):
    if options.get("inline"):
        import orchestrator
        builtin = Path(orchestrator.__file__).parent / "workflow_lisp/stdlib_modules/w3/std/improve.orc"
        body = builtin.read_text().split("  (defproc improve", 1)[1].rstrip()[:-1]
        source = source.replace("(Decision Improvement improve)", "(Decision Improvement)")
        source = source.replace("  (defworkflow run", "  (defproc inline-improve" + body + "\n  (defworkflow run", 1)
        source = source.replace("(improve initial", "(inline-improve initial", 1)
    if options.get("wrapped"):
        declarations = '\n'.join(line for line in source.splitlines() if "(defrecord" in line)
        (workspace / "grt/types.orc").write_text('(workflow-lisp (:language "0.1") (:target-dsl "2.36")\n'
            '(defmodule grt/types) (export Draft Feedback Blocker)\n' + declarations + ')')
        source = '\n'.join(line for line in source.splitlines() if "(defrecord" not in line)
        source = source.replace("  (export run)", "  (import grt/types :only (Draft Feedback Blocker))\n"
            "  (import grt/review :only (assess))\n  (export run)")
        review = '''(command-result probe_review
            :argv ("python" "probe_review.py" draft.title goal rubric)
            :returns Decision[Feedback Blocker])'''
        assert source.count(review) == 1
        source = source.replace(review, "(assess draft goal rubric)", 1)
        (workspace / "grt/review.orc").write_text('''(workflow-lisp (:language "0.1") (:target-dsl "2.36")
          (defmodule grt/review) (import grt/types :only (Draft Feedback Blocker))
          (import std/improve :only (Decision)) (export assess)
          (defproc assess ((draft Draft) (goal String) (rubric String)) -> Decision[Feedback Blocker]
            :effects ((uses-command probe_review)) :lowering inline
            ''' + review + '))')
    return source


def _internal_counter(source, typed):
    if typed:
        source = source.replace("(history List[Trial]) (evaluations Int)",
                                "(history List[Trial]) (evaluations Int) (history_size Int)", 1)
        source = source.replace("(history_size state.evaluations)", "(history_size state.history_size)")
        source = source.replace(":evaluations (+ state.evaluations 1)",
            ":evaluations (+ state.evaluations 1) :history_size (+ state.history_size 1)")
        source = source.replace(":history (list seed-a-trial seed-b-trial) :evaluations 2",
            ":history (list seed-a-trial seed-b-trial) :evaluations 2 :history_size 2", 1)
    else:
        source = source.replace('(evaluations 2)', '(evaluations 2) (history_size 2)', 1)
        source = source.replace('(evaluations (+ (field state "evaluations") 1))',
            '(evaluations (+ (field state "evaluations") 1)) (history_size (+ (field state "history_size") 1))')
        source = source.replace('(propose operation branch base other (field state "evaluations"))',
            '(propose operation branch base other (field state "history_size"))', 1)
        source = source.replace('(field state "b") (field state "evaluations"))',
            '(field state "b") (field state "history_size"))', 1)
    return source


def _public_native(workspace, kind, options):
    from tests import test_workflow_dynamic_improve as improve
    from tests import test_workflow_dynamic_search as search
    helper = improve if kind == "improve" else search
    from orchestrator.workflow.dynamic import runtime
    real_run = helper.run_workflow
    real_perform = runtime.perform_command
    compiled = []
    options = dict(options)
    internal_counter = options.pop("internal_counter", False)
    prepare_only = options.pop("prepare_only", False)
    prepared_argv = []

    def compile_then_run(args):
        if internal_counter:
            path = Path(args.workflow)
            path.write_text(_internal_counter(path.read_text(), False))
        argv = [sys.executable, "-B", "-m", "orchestrator", "compile", args.workflow,
                "--command-boundaries-file", args.command_boundaries_file]
        completed = subprocess.run(argv, cwd=workspace, capture_output=True, text=True)
        compiled.append(_save_compile(workspace, completed))
        if compiled[-1].get("refused"):
            raise _CompileRefused()
        if prepare_only:
            prepared_argv.extend(["run", args.workflow, "--command-boundaries-file", args.command_boundaries_file,
                                  *[value for item in args.input for value in ("--input", item)]])
            raise _Prepared()
        return real_run(args)

    def checked_perform(*args, **kwargs):
        _run_receipt(workspace, compiled[0], False)
        return real_perform(*args, **kwargs)

    with patch.object(helper, "run_workflow", compile_then_run), patch.object(runtime, "perform_command", checked_perform):
        try:
            actual = helper._dynamic_run(workspace, **options)
        except _CompileRefused:
            return _refusal(compiled[0])
        except _Prepared:
            return {"value": None, "requests": [], "exit": 0, "run_root": None, "compile": compiled,
                    "state": None, "phase": "prepared", "prepared_argv": prepared_argv}
    result = actual["result"]
    state = json.loads((result.run_root / "state.json").read_text()) if result.run_root else None
    return {"value": state["workflow_outputs"] if state else None,
            "requests": actual["events" if kind == "improve" else "calls"],
            "exit": result.exit_code, "run_root": str(result.run_root) if result.run_root else None,
            "compile": compiled, "state": state, "phase": "run",
            "run_header": _run_receipt(workspace, compiled[0], False) if result.run_root else None}


def _public_w3(workspace, kind, options, source):
    from contextlib import chdir
    from orchestrator.cli.commands.run import run_workflow
    from orchestrator.cli.main import create_parser
    from tests.test_workflow_lisp_closed_program_compile_cli import _compile
    from tests.workflow_evaluated_totality_helpers import checked_run
    from tests import workflow_evaluated_program_sources as search

    if kind == "search":
        text = (search.PAIR / "search_compact.orc").read_text().replace('(:target-dsl "2.33")', '(:target-dsl "2.36")')
        assert text != (search.PAIR / "search_compact.orc").read_text()
        if options.get("controller_limit", 16) != 16:
            text = text.replace(":max 16", f':max {options["controller_limit"]}')
        if options.get("internal_counter"):
            text = _internal_counter(text, True)
        files = search.install(workspace, text, options.get("scenario") if options.get("scripted", True) else None)
        if "answers" in options:
            (files["source"].parent / "answers.json").write_text(json.dumps(options["answers"]))
    else:
        probes = {name: workspace / f"{name}.py" for name in ("probe_review", "probe_revise")}
        entry = workspace / "grt/entry.orc"
        entry.parent.mkdir()
        entry.write_text(_w3_variant(options.get("source_text") or source, workspace, options))
        files = {"workspace": workspace, "source": entry, "source_root": workspace,
                 "providers": workspace / "providers.json", "prompts": workspace / "prompts.json",
                 "commands": workspace / "commands.json"}
        files["providers"].write_text("{}")
        files["prompts"].write_text("{}")
        files["commands"].write_text(json.dumps({name: {"kind": "external_tool",
            "stable_command": ["python", probe.name], "closure": [probe.name]} for name, probe in probes.items()}))
    compiled = _save_compile(workspace, _compile(files), typed=True)
    if compiled.get("refused"):
        return _refusal(compiled)
    if options.get("prepare_only"):
        argv = ["run", str(files["source"]), "--source-root", str(files["source_root"]),
                "--provider-externs-file", str(files["providers"]), "--prompt-externs-file", str(files["prompts"]),
                "--command-boundaries-file", str(files["commands"])]
        for name in ("seed", "limit", "goal", "rubric"):
            if name in options:
                argv += ["--input", f"{name}={options[name]}"]
        return {"value": None, "requests": [], "exit": 0, "run_root": None, "compile": [compiled],
                "state": None, "phase": "prepared", "prepared_argv": argv}
    from orchestrator.workflow.evaluated import runtime
    real_perform = runtime.perform_command

    def checked_perform(*args, **kwargs):
        _run_receipt(workspace, compiled, True)
        return real_perform(*args, **kwargs)

    monkeypatch = pytest.MonkeyPatch()
    with chdir(workspace), monkeypatch.context() as patched:
        patched.setattr(runtime, "perform_command", checked_perform)
        if kind == "search":
            requests = search.observe_requests(patched)
            if "inputs" in options:
                input_file = workspace / "inputs.json"
                input_file.write_text(json.dumps(options["inputs"]))
                args = create_parser().parse_args(["run", str(files["source"]),
                    "--source-root", str(files["source_root"]), "--command-boundaries-file", str(files["commands"]),
                    "--input-file", str(input_file)])
                result = run_workflow(args)
            else:
                result = search.public_run(files, options.get("budget", 12))
        else:
            argv = ["run", str(files["source"]), "--source-root", str(workspace),
                    "--command-boundaries-file", str(files["commands"])]
            for name in ("seed", "limit", "goal", "rubric"):
                if name in options:
                    argv += ["--input", f"{name}={options[name]}"]
            args = create_parser().parse_args(argv)
            patched.setenv("DYNAMIC_IMPROVE_EVENT_LOG", str(workspace / "hook-events.jsonl"))
            result = run_workflow(args)
            log = workspace / "hook-events.jsonl"
            requests = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    authority, snapshot = checked_run(workspace) if result.run_root else (None, None)
    terminal = snapshot.terminal.data if snapshot else None
    return {"value": terminal.get("value") if terminal else None, "requests": requests, "exit": result.exit_code,
            "run_root": str(authority.run_root) if authority else None, "compile": [compiled], "state": terminal,
            "phase": "run", "run_header": _run_receipt(workspace, compiled, True) if authority else None}


def _worker(request_path):
    request = json.loads(request_path.read_text())
    package_root, workspace = Path(request["package_root"]), Path(request["workspace"])
    sys.path.insert(0, str(package_root))
    typed = request["runtime"] == "w3"
    provenance = _provenance(package_root, TYPED_PIN if typed else NATIVE_PIN, typed)
    import orchestrator
    assert Path(orchestrator.__file__).resolve().is_relative_to(package_root)
    provenance.update(import_file=orchestrator.__file__, interpreter=sys.executable)
    (workspace / "provenance-before.json").write_text(json.dumps(provenance, indent=2))
    kind = request["case"]
    options = dict(request["options"])
    restart_budget = options.pop("restart_budget", False)
    if restart_budget and not typed:
        failed = _public_native(workspace, kind, {**options, "budget": 60})
        old_root = Path(failed["run_root"])
        before_old = _tree_digests(old_root)
        for filename in ("compile.stdout", "compile.stderr", "compile-command.json", "sources-before.json"):
            (workspace / ("failed-" + filename)).write_bytes((workspace / filename).read_bytes())
        actual = _public_native(workspace, kind, {**options, "budget": 1000})
        assert actual["run_root"] != failed["run_root"]
        assert _tree_digests(old_root) == before_old
        actual.update(failed=failed, old_run_unchanged=before_old)
    else:
        actual = (_public_w3(workspace, kind, options, request["w3_improve"]) if typed else
                  _public_native(workspace, kind, options))
    compiled = actual["compile"][0]
    if not compiled.get("refused"):
        actual["target"] = compiled["observed_artifact"]["target"]
    before = json.loads((workspace / "sources-before.json").read_text())
    after_sources = {name: {"text": (workspace / name).read_text(),
                           "sha256": hashlib.sha256((workspace / name).read_bytes()).hexdigest()}
                     for name in before}
    assert before == after_sources
    (workspace / "sources-after.json").write_text(json.dumps(after_sources, indent=2))
    (workspace / "observation.json").write_text(json.dumps(actual, indent=2))
    after = _provenance(package_root, TYPED_PIN if typed else NATIVE_PIN, typed)
    assert provenance["sha256"] == after["sha256"]
    (workspace / "provenance-after.json").write_text(json.dumps(after, indent=2))


@pytest.fixture
def evidence_path(request):
    directory = EVIDENCE / "observations" / request.node.name.replace("/", "_")
    directory.mkdir(parents=True, exist_ok=True)
    # Each invocation owns fresh raw evidence, including a failed worker's workspace.
    import tempfile
    return Path(tempfile.mkdtemp(prefix="attempt-", dir=directory))


def test_RW_I01_initial_approval_public_pair(runtimes, evidence_path):
    pair = _pair(runtimes, evidence_path, "improve", seed="approve", limit=3)
    expected = {"variant": "APPROVED", "value": {"title": "approve", "score": 0},
                "evidence": {"note": "ok:approve:tidy"}}
    for result in pair.values():
        assert result["exit"] == 0
        assert result["value"] == expected
        assert result["requests"] == [{"hook": "review", "argv": ["approve", "tidy", "clear"]}]


def test_RW_S02_real_local_search_public_pair(runtimes, evidence_path):
    from tests.workflow_evaluated_program_sources import reference
    expected, requests = reference(None, 12)
    pair = _pair(runtimes, evidence_path, "search", scripted=False, budget=12)
    assert expected["evaluations"] == 10
    for result in pair.values():
        assert result["exit"] == 0
        assert result["value"] == expected
        assert result["requests"] == requests


@pytest.mark.parametrize("case,seed,limit,expected", [
    ("RW-I02", "block", 3, {"variant": "BLOCKED", "value": {"title": "block+r", "score": 1}, "reason": {"why": "refused:block+r"}}),
    ("RW-I03", "draft", 3, {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}),
    ("RW-I04", "malformed", 3, None),
    ("RW-I05", "fail", 2, None),
    ("RW-I06", "draft", 2, {"variant": "EXHAUSTED", "value": {"title": "draft+r+r", "score": 2}}),
    ("RW-I07", "approve", 3, {"variant": "APPROVED", "value": {"title": "approve", "score": 0}, "evidence": {"note": "ok:approve:tidy"}}),
    ("RW-I08", "block", 3, {"variant": "BLOCKED", "value": {"title": "block+r", "score": 1}, "reason": {"why": "refused:block+r"}}),
    ("RW-I09", "draft", 3, {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}),
    ("RW-I10", "approve", 0, None),
    ("RW-I11", "block", 3, {"variant": "BLOCKED", "value": {"title": "block+r", "score": 1}, "reason": {"why": "refused:block+r"}}),
], ids=lambda value: value if isinstance(value, str) and value.startswith("RW-") else None)
def test_improve_policy(runtimes, evidence_path, case, seed, limit, expected):
    from tests.test_workflow_dynamic_improve import _expected_events
    variants = (False, True) if case in ("RW-I07", "RW-I08", "RW-I09") else (False,)
    for inline in variants:
        pair = _pair(runtimes, evidence_path / ("inline" if inline else "imported"), "improve",
                     seed=seed, limit=limit, inline=inline, wrapped=case == "RW-I06")
        for result in pair.values():
            assert result["value"] == expected
            assert result["requests"] == (_expected_events(seed, limit) if limit else [])
            assert (result["exit"] == 0) == (expected is not None)
            if expected is None:
                assert result["state"] is None or result["state"].get("status", result["state"].get("outcome")) == "failed"


from tests.experiments.test_mlevolve_pair_fixture import BUDGETS, SCENARIOS


@pytest.mark.parametrize("scenario,budget", [(s, b) for b in BUDGETS for s in SCENARIOS],
    ids=[f"RW-S01/{s['name']}/budget-{b}" for b in BUDGETS for s in SCENARIOS])
def test_search_matrix(runtimes, evidence_path, scenario, budget):
    from tests.experiments.test_mlevolve_pair_fixture import _reference
    expected, requests = _reference(scenario, budget)
    pair = _pair(runtimes, evidence_path, "search", scenario=scenario, budget=budget)
    for result in pair.values():
        assert result["exit"] == 0
        assert result["value"] == expected
        assert result["requests"] == requests


def test_RW_S03_budget_and_strict_input_refusal(runtimes, evidence_path):
    from tests.experiments.test_mlevolve_pair_fixture import _reference
    expected, requests = _reference(SCENARIOS[0], 17)
    invalid = _pair(runtimes, evidence_path / "budget", "search", scenario=SCENARIOS[0], budget=17)
    for result in invalid.values():
        assert result["value"] == expected and result["requests"] == requests == []
    malformed = _pair(runtimes, evidence_path / "bool", "search", scenario=SCENARIOS[0],
                      inputs={"max_evaluations": True, "target_score": 0.0})
    for result in malformed.values():
        assert result["exit"] == 2 and result["value"] is None
        assert result["requests"] == [] and result["run_root"] is None


@pytest.mark.parametrize("case", ["RW-S04", "RW-S05"], ids=["RW-S04", "RW-S05"])
def test_search_failed_boundaries(runtimes, evidence_path, case):
    from tests.experiments.test_mlevolve_pair_fixture import _reference, _scenario_answers
    scenario = SCENARIOS[6] if case == "RW-S04" else SCENARIOS[0]
    answers = _scenario_answers(scenario)
    prefix = 3 if case == "RW-S04" else 1
    if case == "RW-S04":
        answers["proposals"]["improve/A/2"].update(a=True)
    else:
        answers["evaluations"]["1,0"] = {"valid": "false", "score": 0.0, "error": "invalid-seed"}
    _, requests = _reference(scenario, 12)
    pair = _pair(runtimes, evidence_path / "failed", "search", scenario=scenario, answers=answers)
    if case == "RW-S05":
        expected, repaired_requests = _reference(SCENARIOS[6], 5)
        repaired = _pair(runtimes, evidence_path / "domain-invalid", "search", scenario=SCENARIOS[6], budget=5)
        for result in repaired.values():
            assert result["value"] == expected and result["requests"] == repaired_requests
        assert [row["action"] for row in expected["trace"]] == ["seed", "seed", "improve", "repair", "improve"]
    for result in pair.values():
        assert result["exit"] == 1 and result["value"] is None
        assert result["requests"] == requests[:prefix]


def test_RW_S06_lowered_controller_bound(runtimes, evidence_path):
    pair = _pair(runtimes, evidence_path, "search", scripted=False, controller_limit=1)
    assert pair["native"]["value"] == pair["w3"]["value"]
    assert pair["native"]["requests"] == pair["w3"]["requests"]
    for result in pair.values():
        assert result["exit"] == 0
        assert result["value"]["status"] == "loop_bound_exhausted"


def _bases():
    from tests.test_workflow_dynamic_edits import _base_source
    return _base_source(), W3_IMPROVE.read_text().replace("draft.title goal rubric)", "draft.title goal)", 1)


def _tree_digests(root):
    return {str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*") if path.is_file()}


def _edit_receipt(root, case, sources, sites, **observations):
    from tests.test_workflow_dynamic_edits import _save_receipt
    import difflib
    changes = {}
    saved = dict(sources)
    for runtime in ("native", "w3"):
        before, after = sources[f"{runtime}.before.orc"], sources[f"{runtime}.after.orc"]
        search = "(defmodule dynamic_consumer/search)" in after or "(defmodule mlevolve_pair/search_compact)" in after
        entry = ("dynamic_consumer/search.orc" if search else "dynamic_consumer/improve.orc") if runtime == "native" else (
            "experiments/mlevolve_pair/search_compact.orc" if search else "grt/entry.orc")
        for site in sites[runtime]:
            site["file"] = ("dynamic_consumer/types.orc" if site["role"] == "boundary-schema" and runtime == "native" else
                            site.get("file") or ("probe_review.py" if site["role"] == "producer" else entry))
            matches = [path for path in root.rglob(Path(site["file"]).name)
                       if path.as_posix().endswith(f'/{runtime}/{site["file"]}')]
            assert matches, f"Counted site has no staged source: {site}"
            saved[f'{runtime}.sites/{site["file"]}'] = max(matches, key=lambda path: path.stat().st_mtime_ns).read_text()
            assert saved[f'{runtime}.sites/{site["file"]}']
        changes[runtime] = {"diff": ''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True))),
                            "loc_scope": "main authored ORC only; schema and shared probe edits are separate",
                            "nonblank_before": sum(bool(line.strip()) for line in before.splitlines()),
                            "nonblank_after": sum(bool(line.strip()) for line in after.splitlines()),
                            "semantic_sites": sites[runtime],
                            "boundary_schema_sites": sum(site["role"] == "boundary-schema" for site in sites[runtime]),
                            "internal_sites": sum(site["role"] not in ("boundary-schema", "producer") for site in sites[runtime]),
                            "apparatus_sites": sum(site["role"] == "producer" for site in sites[runtime])}
    _save_receipt(root, case, {"changes": changes, **observations, "timing": "unmeasured"}, saved)


def _site(symbol, role, file=None):
    return {"symbol": symbol, "role": role, **({"file": file} if file else {})}


def _one_revision(pair, requests, *, origin=False):
    value = {"title": "draft+r", "score": 1, **({"origin": "seed"} if origin else {})}
    for result in pair.values():
        assert result["exit"] == 0
        assert result["value"] == {"variant": "EXHAUSTED", "value": value}
        assert result["requests"] == requests


def _late_failure(result, code, completed):
    assert result["exit"] == 1 and result["value"] is None
    error = result["state"]["error"]
    assert error["code"] == code
    start = error["metadata"]["span"]["start"]
    assert start["path"].endswith(".orc") and start["line"] > 0
    assert error["metadata"]["call_stack"]
    assert [row["status"] for row in result["state"]["effects"]] == ["completed"] * completed


def test_RW_E01_external_origin_and_private_search_state(runtimes, evidence_path):
    from tests.test_workflow_dynamic_edits import _origin_revise_probe
    from tests.workflow_lisp_improve_stdlib_sources import REVISE_PROBE
    from tests.test_workflow_dynamic_improve import FIXTURES
    native, w3 = _bases()
    types = (FIXTURES / "consumer_types.orc").read_text()
    changed_types = types.replace('(defrecord Draft (title String) (score Int))',
                                  '(defrecord Draft (title String) (score Int) (origin String))', 1)
    native_red = native.replace('(field current "title") goal)', '(field current "title") goal (field current "origin"))', 1)
    native_red = native_red.replace('(field feedback "note"))', '(field feedback "note") (field current "origin"))', 1)
    w3_red = w3.replace('(defrecord Draft (title String) (score Int))',
                        '(defrecord Draft (title String) (score Int) (origin String))', 1)
    w3_red = w3_red.replace('draft.title goal)', 'draft.title goal draft.origin)', 1)
    w3_red = w3_red.replace('draft.title goal feedback.note)', 'draft.title goal feedback.note draft.origin)', 1)
    red = _pair(runtimes, evidence_path / "red", "improve", seed="draft", limit=1, revise_script=_origin_revise_probe(),
        native_options={"source_text": native_red, "types_text": changed_types}, w3_options={"source_text": w3_red})
    for result in red.values():
        assert result["exit"] != 0 and result["requests"] == []
    native_after = native_red.replace('(record (title seed) (score 0))', '(record (title seed) (score 0) (origin "seed"))', 1)
    w3_after = w3_red.replace('(record Draft :title seed :score 0)', '(record Draft :title seed :score 0 :origin "seed")', 1)
    repaired = _pair(runtimes, evidence_path / "repaired", "improve", seed="draft", limit=1, revise_script=_origin_revise_probe(),
        native_options={"source_text": native_after, "types_text": changed_types}, w3_options={"source_text": w3_after})
    _one_revision(repaired, [{"hook": "review", "argv": ["draft", "tidy", "seed"]},
        {"hook": "revise", "argv": ["draft", "tidy", "fb0", "seed"]}], origin=True)
    sites = {runtime: [_site("Draft.origin", "boundary-schema"), _site("run.initial.origin", "construction"),
        _site("review.origin", "command-input"), _site("revise.origin", "command-input"),
        _site("revise.payload.origin", "producer", "probe_revise.py")]
        for runtime in runtimes}
    _edit_receipt(evidence_path, "RW-E01-boundary", {"native.before.orc": native, "native.after.orc": native_after,
        "w3.before.orc": w3, "w3.after.orc": w3_after, "types.before.orc": types, "types.after.orc": changed_types,
        "native.red.orc": native_red, "w3.red.orc": w3_red,
        "shared.probe_revise.before.py": REVISE_PROBE, "shared.probe_revise.after.py": _origin_revise_probe()},
        sites, failed=red, repaired=repaired, shared_apparatus_edits=["revision producer adds origin result field"])
    from tests.workflow_evaluated_program_sources import reference
    expected, requests = reference(None, 12)
    private = _pair(runtimes, evidence_path / "private-state", "search", scripted=False, internal_counter=True)
    assert any(row["action"] == "fuse" for row in expected["trace"])
    for result in private.values():
        assert result["value"] == expected and result["requests"] == requests
    native_search = (FIXTURES / "search.orc").read_text()
    w3_search = (runtimes["w3"] / "experiments/mlevolve_pair/search_compact.orc").read_text().replace('"2.33"', '"2.36"', 1)
    sites = {runtime: [_site("initial.history_size", "construction"), _site("branch-step.history_size", "update"),
        _site("fusion-step.history_size", "update"), _site("branch-step.proposal.history_size", "read"),
        _site("fusion-step.proposal.history_size", "read")] for runtime in runtimes}
    sites["w3"].insert(0, _site("SearchState.history_size", "private-declaration"))
    _edit_receipt(evidence_path, "RW-E01-internal", {"native.before.orc": native_search,
        "native.after.orc": _internal_counter(native_search, False), "w3.before.orc": w3_search,
        "w3.after.orc": _internal_counter(w3_search, True)}, sites, results=private, external_schema_changes=0)


def test_RW_E02_feedback_rename_preserves_evidence_and_revision(runtimes, evidence_path):
    from tests.test_workflow_dynamic_edits import _message_review_probe
    from tests.workflow_lisp_improve_stdlib_sources import REVIEW_PROBE
    from tests.test_workflow_dynamic_improve import FIXTURES
    native, w3 = _bases()
    types_before = (FIXTURES / "consumer_types.orc").read_text()
    types = types_before.replace('(defrecord Feedback (note String))', '(defrecord Feedback (message String))')
    w3_schema = w3.replace('(defrecord Feedback (note String))', '(defrecord Feedback (message String))')
    stale_producer = _pair(runtimes, evidence_path / "producer", "improve", seed="approve", limit=1,
        native_options={"source_text": native, "types_text": types},
        w3_options={"source_text": w3_schema.replace("feedback.note", "feedback.message")})
    for result in stale_producer.values():
        assert result["exit"] == 1 and result["value"] is None
        assert len(result["requests"]) == 1 and result["requests"][0]["hook"] == "review"
    stale_consumer = _pair(runtimes, evidence_path / "consumer", "improve", seed="draft", limit=1, review_script=_message_review_probe(),
        native_options={"source_text": native, "types_text": types}, w3_options={"source_text": w3_schema})
    assert len(stale_consumer["native"]["requests"]) == 1
    assert stale_consumer["w3"]["phase"] == "compile" and stale_consumer["w3"]["requests"] == []
    native_after = native.replace('(field feedback "note")', '(field feedback "message")', 1)
    w3_after = w3_schema.replace("feedback.note", "feedback.message", 1)
    outcomes = []
    for seed in ("approve", "draft"):
        pair = _pair(runtimes, evidence_path / seed, "improve", seed=seed, limit=1, review_script=_message_review_probe(),
            native_options={"source_text": native_after, "types_text": types}, w3_options={"source_text": w3_after})
        if seed == "draft":
            _one_revision(pair, [{"hook": "review", "argv": ["draft", "tidy"]}, {"hook": "revise", "argv": ["draft", "tidy", "fb0"]}])
        else:
            for result in pair.values():
                assert result["value"] == {"variant": "APPROVED", "value": {"title": "approve", "score": 0}, "evidence": {"message": "ok:approve:tidy"}}
        outcomes.append(pair)
    sites = {runtime: [_site("Feedback.message", "boundary-schema"), _site("review.payload.message", "producer"),
                       _site("revise.feedback.message", "read")] for runtime in runtimes}
    _edit_receipt(evidence_path, "RW-E02", {"native.before.orc": native, "native.after.orc": native_after,
        "w3.before.orc": w3, "w3.after.orc": w3_after,
        "native.types.before.orc": types_before, "native.types.after.orc": types,
        "shared.probe_review.before.py": REVIEW_PROBE, "shared.probe_review.after.py": _message_review_probe()}, sites,
        stale_producer=stale_producer, stale_consumer=stale_consumer, outcomes=outcomes,
        shared_apparatus_edits=["APPROVE evidence.note and REVISE feedback.note producers rename to message"])


def test_RW_E03_review_only_rubric_captures_tie(runtimes, evidence_path):
    from tests.test_workflow_dynamic_edits import _rubric_review_probe
    from tests.workflow_lisp_improve_stdlib_sources import REVIEW_PROBE
    native, w3 = _bases()
    native_after = native.replace('(field current "title") goal)', '(field current "title") goal rubric)', 1)
    w3_after = w3.replace('draft.title goal)', 'draft.title goal rubric)', 1)
    pair = _pair(runtimes, evidence_path, "improve", seed="draft", limit=1, rubric="clarity", review_script=_rubric_review_probe(),
                 native_options={"source_text": native_after}, w3_options={"source_text": w3_after})
    _one_revision(pair, [{"hook": "review", "argv": ["draft", "tidy", "clarity"]},
                       {"hook": "revise", "argv": ["draft", "tidy", "fb0:clarity"]}])
    sites = {runtime: [_site("review.argv.rubric", "captured-read")] for runtime in runtimes}
    _edit_receipt(evidence_path, "RW-E03", {"native.before.orc": native, "native.after.orc": native_after,
        "w3.before.orc": w3, "w3.after.orc": w3_after,
        "shared.probe_review.before.py": REVIEW_PROBE, "shared.probe_review.after.py": _rubric_review_probe()},
        sites, results=pair, new_declarations=0, context_forwarding=0,
        shared_apparatus_edits=["review reads rubric argv", "approval evidence uses rubric", "revision feedback uses rubric"])


def test_RW_E04_pure_feedback_helper(runtimes, evidence_path):
    native, w3 = _bases()
    native_after = native.replace('(field feedback "note")', '(feedback-to-revision-input feedback)', 1)
    native_after = native_after.replace('  (export run)', '  (export run)\n'
        '  (define (feedback-to-revision-input feedback) (field feedback "note"))', 1)
    helper = '''  (defun feedback-to-revision-input ((feedback Feedback)) -> String
    feedback.note)
'''
    w3_after = w3.replace('  (defworkflow run', helper + '  (defworkflow run', 1)
    w3_after = w3_after.replace('draft.title goal feedback.note)',
        'draft.title goal (feedback-to-revision-input feedback))', 1)
    pair = _pair(runtimes, evidence_path, "improve", seed="draft", limit=1,
        native_options={"source_text": native_after},
        w3_options={"source_text": w3_after})
    _one_revision(pair, [{"hook": "review", "argv": ["draft", "tidy"]}, {"hook": "revise", "argv": ["draft", "tidy", "fb0"]}])
    program = json.loads(Path(pair["native"]["compile"][0]["artifact_paths"]["dynamic_program"]).read_text())
    helper_name = "dynamic_consumer/improve::feedback-to-revision-input"
    assert program["definitions"][helper_name]["body"]["k"] == "field"
    revision = program["definitions"]["dynamic_consumer/improve::revise-for$fn/body"]["body"]
    assert any(node.get("k") == "call" and node["callee"].get("code") == helper_name
               for _, node in revision["bindings"])
    sites = {runtime: [_site("feedback-to-revision-input", "helper"), _site("revise.feedback-to-revision-input", "call")]
             for runtime in runtimes}
    sites["w3"].append(_site("Feedback -> String", "signature"))
    _edit_receipt(evidence_path, "RW-E04", {"native.before.orc": native, "native.after.orc": native_after,
        "w3.before.orc": w3, "w3.after.orc": w3_after}, sites, results=pair)


def test_RW_D01_unbound_lexical_name_located_before_effects(runtimes, evidence_path):
    native, w3 = _bases()
    native_bad = native.replace('(field current "title") goal)', '(field current "title") missing_goal)', 1)
    w3_bad = w3.replace('draft.title goal)', 'draft.title missing_goal)', 1)
    pair = _pair(runtimes, evidence_path / "bad", "improve", seed="draft", limit=1,
                 native_options={"source_text": native_bad}, w3_options={"source_text": w3_bad})
    for result in pair.values():
        assert result["phase"] == "compile" and result["requests"] == []
        assert result["diagnostics"][0]["line"] > 0 and result["diagnostics"][0]["column"] > 0
    repaired = _pair(runtimes, evidence_path / "fixed", "improve", seed="draft", limit=1,
                     native_options={"source_text": native}, w3_options={"source_text": w3})
    _one_revision(repaired, [{"hook": "review", "argv": ["draft", "tidy"]}, {"hook": "revise", "argv": ["draft", "tidy", "fb0"]}])
    _edit_receipt(evidence_path, "RW-D01", {"native.before.orc": native_bad, "native.after.orc": native,
        "w3.before.orc": w3_bad, "w3.after.orc": w3}, {runtime: [_site("review.goal", "repair")] for runtime in runtimes},
        failed=pair, repaired=repaired)


def test_RW_D02_arity_before_effect_and_after_review(runtimes, evidence_path):
    native, w3 = _bases()
    native = native.replace('  (export run)', '  (export run)\n  (define (identity value) value)', 1)
    w3 = w3.replace('  (defworkflow run', '  (defproc identity ((value String)) -> String :effects () :lowering inline value)\n  (defworkflow run', 1)
    failed = {}
    for site in ("before-effect", "after-review"):
        native_bad = (native.replace('(field current "title") goal)', '(field current "title") (identity goal "extra"))', 1)
                      if site == "before-effect" else native.replace('(field feedback "note")', '(identity (field feedback "note") "extra")', 1))
        w3_bad = (w3.replace('draft.title goal)', 'draft.title (identity goal "extra"))', 1)
                  if site == "before-effect" else w3.replace('feedback.note)', '(identity feedback.note "extra"))', 1))
        pair = _pair(runtimes, evidence_path / site, "improve", seed="draft", limit=1,
                     native_options={"source_text": native_bad}, w3_options={"source_text": w3_bad})
        _late_failure(pair["native"], "dynamic_call_arity", 0 if site == "before-effect" else 1)
        assert len(pair["native"]["requests"]) == (0 if site == "before-effect" else 1)
        assert pair["w3"]["phase"] == "compile" and pair["w3"]["requests"] == []
        failed[site] = pair
    repaired = _pair(runtimes, evidence_path / "fixed", "improve", seed="draft", limit=1,
                     native_options={"source_text": native}, w3_options={"source_text": w3})
    _one_revision(repaired, [{"hook": "review", "argv": ["draft", "tidy"]}, {"hook": "revise", "argv": ["draft", "tidy", "fb0"]}])
    _edit_receipt(evidence_path, "RW-D02", {"native.before.orc": native_bad, "native.after.orc": native,
        "w3.before.orc": w3_bad, "w3.after.orc": w3}, {runtime: [_site("identity.call", "repair")] for runtime in runtimes},
        failed=failed, repaired=repaired, completed_effects_before_failure=[0, 1])


def test_RW_D03_missing_field_after_review(runtimes, evidence_path):
    native, w3 = _bases()
    native_bad = native.replace('(field feedback "note")', '(field feedback "missing")', 1)
    w3_bad = w3.replace('feedback.note', 'feedback.missing', 1)
    pair = _pair(runtimes, evidence_path / "bad", "improve", seed="draft", limit=1,
                 native_options={"source_text": native_bad}, w3_options={"source_text": w3_bad})
    _late_failure(pair["native"], "dynamic_field_missing", 1)
    assert pair["native"]["requests"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert pair["w3"]["phase"] == "compile" and pair["w3"]["requests"] == []
    repaired = _pair(runtimes, evidence_path / "fixed", "improve", seed="draft", limit=1,
                     native_options={"source_text": native}, w3_options={"source_text": w3})
    _one_revision(repaired, [{"hook": "review", "argv": ["draft", "tidy"]}, {"hook": "revise", "argv": ["draft", "tidy", "fb0"]}])
    _edit_receipt(evidence_path, "RW-D03", {"native.before.orc": native_bad, "native.after.orc": native,
        "w3.before.orc": w3_bad, "w3.after.orc": w3}, {runtime: [_site("revise.feedback.note", "repair")] for runtime in runtimes},
        failed=pair, repaired=repaired)


def test_RW_D04_operation_budget_fresh_restart_repeats_review(runtimes, evidence_path):
    native, w3 = _bases()
    pair = _pair(runtimes, evidence_path, "improve", seed="draft", limit=1, restart_budget=True,
                 native_options={"source_text": native}, w3_options={"source_text": w3})
    failed = pair["native"]["failed"]
    _late_failure(failed, "dynamic_budget_exhausted", 1)
    assert failed["requests"] == [{"hook": "review", "argv": ["draft", "tidy"]}]
    assert pair["native"]["old_run_unchanged"]
    expected = [{"hook": "review", "argv": ["draft", "tidy"]}, {"hook": "revise", "argv": ["draft", "tidy", "fb0"]}]
    assert pair["native"]["requests"] == failed["requests"] + expected
    assert pair["w3"]["requests"] == expected
    assert pair["native"]["value"] == pair["w3"]["value"] == {"variant": "EXHAUSTED", "value": {"title": "draft+r", "score": 1}}
    from tests.test_workflow_dynamic_edits import _save_receipt
    _save_receipt(evidence_path, "RW-D04", {"results": pair,
        "asymmetry": "W3 has no dynamic operation-budget promise; no equal-budget performance comparison"},
        {"native.low-budget.orc": native.replace('(:budget 1000)', '(:budget 60)'), "native.fresh.orc": native, "w3.orc": w3})


@pytest.mark.parametrize("goal", ["tidy", "steady"], ids=["RW-D05", "RW-D06"])
def test_public_committed_pair_interruption_and_recovery(runtimes, evidence_path, goal):
    import signal
    from tests.test_workflow_dynamic_improve_interruptions import _CLI_GATE, _instrument_probe, _request_shape
    from tests.test_workflow_dynamic_interruptions import _kill_known_processes, _wait_file
    prepared = _pair(runtimes, evidence_path, "improve", seed="draft", limit=3, goal=goal, prepare_only=True)
    typed_gate = '''else:
    from orchestrator.workflow.evaluated import runtime
    original_append = runtime.append_record
    committed = 0
    def gated_append(path, record, **kwargs):
        global committed
        result = original_append(path, record, **kwargs)
        if record.get("record") == "committed":
            committed += 1
            if committed == 2:
                pause("w3_pair_committed")
        return result
    runtime.append_record = gated_append
'''
    beginning = _CLI_GATE.index("else:\n    from orchestrator.workflow.executor")
    ending = _CLI_GATE.index("\nfrom orchestrator.cli import main", beginning)
    gate = _CLI_GATE[:beginning] + typed_gate + _CLI_GATE[ending:]
    preflight = '''
import orchestrator
assert Path(orchestrator.__file__).resolve().is_relative_to(Path(os.environ["COMPARISON_IMPORT_ROOT"]))
if mode == "dynamic":
    from orchestrator.workflow.dynamic import runtime as effect_runtime
else:
    from orchestrator.workflow.evaluated import runtime as effect_runtime
original_perform = effect_runtime.perform_command
def checked_perform(*args, **kwargs):
    header = max(Path.cwd().glob(".orchestrate/runs/*/run.json"), key=lambda p: p.stat().st_mtime_ns)
    observed = json.loads(header.read_text())
    assert observed["program_digest"] == os.environ["COMPARISON_PROGRAM_DIGEST"]
    assert observed["result_persistence_profile"] == os.environ["COMPARISON_PROFILE"]
    (control / "public-route-before-effect.json").write_text(json.dumps({
        "import_file": orchestrator.__file__, "program_digest": observed["program_digest"],
        "profile": observed["result_persistence_profile"]}))
    return original_perform(*args, **kwargs)
effect_runtime.perform_command = checked_perform
'''
    gate = gate.replace("\nfrom orchestrator.cli import main", preflight + "\nfrom orchestrator.cli import main", 1)
    expected = []
    for iteration in range(3):
        title = "draft" + "+r" * iteration
        expected += [{"hook": "review", "argv": [title, goal, "clear"]},
                     {"hook": "revise", "argv": [title, goal, f"fb{iteration}"]}]
    results = {}
    for runtime, package_root in runtimes.items():
        workspace = evidence_path / runtime
        control = workspace / "interrupt-control"
        control.mkdir()
        launcher = control / "public_cli_gate.py"
        launcher.write_text(gate)
        for hook in ("review", "revise"):
            _instrument_probe(workspace / f"probe_{hook}.py", hook)
        env = {**os.environ, "PYTHONPATH": str(package_root), "PYTHONDONTWRITEBYTECODE": "1",
            "IMPROVE_INTERRUPT_CONTROL": str(control), "IMPROVE_INTERRUPT_MODE": "dynamic" if runtime == "native" else "w3",
            "DYNAMIC_IMPROVE_EVENT_LOG": str(workspace / "hook-events.jsonl"),
            "COMPARISON_IMPORT_ROOT": str(package_root), "COMPARISON_PROGRAM_DIGEST": prepared[runtime]["compile"][0]["program_digest"],
            "COMPARISON_PROFILE": "dynamic_execution.v1" if runtime == "native" else "evaluated_execution.v1"}
        _provenance(package_root, NATIVE_PIN if runtime == "native" else TYPED_PIN, runtime == "w3")
        argv = [sys.executable, "-B", str(launcher), *prepared[runtime]["prepared_argv"]]
        process = subprocess.Popen(argv, cwd=workspace, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            marker = _wait_file(process, control / "gate.json")
            assert marker["barrier"] == ("dynamic_effect_2_settled" if runtime == "native" else "w3_pair_committed")
            assert marker["pid"] == marker["pgid"] == process.pid
            _kill_known_processes(process, control)
            assert process.returncode == -signal.SIGKILL
        finally:
            _kill_known_processes(process, control)
            stdout, stderr = process.communicate(timeout=8)
            (control / "interrupted.stdout").write_text(stdout)
            (control / "interrupted.stderr").write_text(stderr)
            (control / "interrupted-command.json").write_text(json.dumps({"argv": argv, "cwd": str(workspace), "exit": process.returncode}))
        log = control / "calls.jsonl"
        events = [json.loads(line) for line in log.read_text().splitlines()]
        assert _request_shape(events) == expected[:2]
        assert all(event["pgid"] == process.pid and event["pid"] != process.pid for event in events)
        old_root, = workspace.glob(".orchestrate/runs/*")
        old_header = json.loads((old_root / "run.json").read_text())
        assert old_header["program_digest"] == prepared[runtime]["compile"][0]["program_digest"]
        assert old_header["result_persistence_profile"] == ("dynamic_execution.v1" if runtime == "native" else "evaluated_execution.v1")
        assert old_header["bound_inputs"]["goal"] == goal
        old = _tree_digests(old_root)
        committed_results = {name: digest for name, digest in old.items() if name.endswith("/result.json")}
        assert len(committed_results) == 2
        before = json.loads((old_root / "state.json").read_text())
        assert before["status"] != "completed" and before["workflow_outputs"] is None
        command = (["resume", old_root.name] if runtime == "w3" else prepared[runtime]["prepared_argv"])
        argv = [sys.executable, "-B", "-m", "orchestrator", *command]
        completed = subprocess.run(argv, cwd=workspace, env=env, capture_output=True, text=True, timeout=60)
        (control / "recovery.stdout").write_text(completed.stdout)
        (control / "recovery.stderr").write_text(completed.stderr)
        (control / "recovery-command.json").write_text(json.dumps({"argv": argv, "cwd": str(workspace), "exit": completed.returncode}))
        assert completed.returncode == 0, completed.stderr
        roots = list(workspace.glob(".orchestrate/runs/*"))
        final_root = old_root if runtime == "w3" else next(root for root in roots if root != old_root)
        final = json.loads((final_root / "state.json").read_text())
        after_events = [json.loads(line) for line in log.read_text().splitlines()]
        assert _request_shape(after_events) == (expected if runtime == "w3" else expected[:2] + expected)
        assert final["status"] == "completed"
        assert final["workflow_outputs"] == {"variant": "EXHAUSTED", "value": {"title": "draft+r+r+r", "score": 3}}
        if runtime == "native":
            assert _tree_digests(old_root) == old
            assert len(roots) == 2
        else:
            assert len(roots) == 1
            after = _tree_digests(old_root)
            assert all(after[name] == digest for name, digest in committed_results.items())
        results[runtime] = {"prefix": events, "all_requests": after_events, "total_calls": len(after_events),
            "before_state": before, "final_state": final, "old_run": str(old_root), "final_run": str(final_root),
            "old_file_hashes": old, "committed_result_hashes": committed_results,
            "run_header": old_header, "gate": marker}
        (workspace / "recovery-observation.json").write_text(json.dumps(results[runtime], indent=2))
        _provenance(package_root, NATIVE_PIN if runtime == "native" else TYPED_PIN, runtime == "w3")
    assert results["w3"]["total_calls"] == 6 and results["native"]["total_calls"] == 8


def test_RW_C01_returned_hook_factories_and_local_w3_hooks(runtimes, evidence_path):
    pair = _pair(runtimes, evidence_path, "improve", seed="draft", limit=1, goal="ship", rubric="precise")
    _one_revision(pair, [{"hook": "review", "argv": ["draft", "ship", "precise"]},
                        {"hook": "revise", "argv": ["draft", "ship", "fb0"]}])
    from tests.test_workflow_dynamic_improve import FIXTURES
    native, w3 = (FIXTURES / "improve.orc").read_text(), W3_IMPROVE.read_text()
    _edit_receipt(evidence_path, "RW-C01", {"native.before.orc": native, "native.after.orc": native,
        "w3.before.orc": w3, "w3.after.orc": w3}, {
            "native": [_site("review-for", "returned-hook-factory"), _site("revise-for", "returned-hook-factory")],
            "w3": [_site("review", "local-hook"), _site("revise", "local-hook")]}, results=pair,
            w3_explicit_hook_signatures=0, w3_forwarded_contexts=0, consumer_behavior_equivalent=True)


def test_RW_C02_runtime_function_selection_and_w3_branch_alternative(runtimes, evidence_path):
    native = '''(workflow-lisp (:language "0.1") (:target-dsl "3.0") (:budget 1000)
      (defmodule dynamic_consumer/improve) (export run)
      (define (make-left offset) (fn (n) (+ n offset)))
      (define (make-right offset) (fn (n) (- n offset)))
      (defworkflow run ((seed String :default "left") (limit Int :default 5)
                       (goal String :default "tidy") (rubric String :default "clear")) -> Int
        (let* ((left (make-left limit)) (right (make-right limit))
               (chosen (if (= seed "left") left right)))
          (chosen 40))))'''
    w3 = '''(workflow-lisp (:language "0.1") (:target-dsl "2.36")
      (defmodule grt/entry) (export run)
      (defproc apply-int ((hook ProcRef[Int -> Int]) (n Int)) -> Int
        :effects () :lowering inline (hook n))
      (defworkflow run ((seed String :default "left") (limit Int :default 5)
                       (goal String :default "tidy") (rubric String :default "clear")) -> Int
        (let-proc
          ((left ((n Int)) -> Int :captures (limit) (+ n limit))
           (right ((n Int)) -> Int :captures (limit) (- n limit)))
          (let* ((chosen (if (= seed "left") (proc-ref left) (proc-ref right))))
            (apply-int chosen 40)))))'''
    alternative = w3.replace('(let* ((chosen (if (= seed "left") (proc-ref left) (proc-ref right))))\n            (apply-int chosen 40))',
                             '(if (= seed "left") (apply-int (proc-ref left) 40) (apply-int (proc-ref right) 40))', 1)
    outcomes = {}
    for choice, expected in (("left", 45), ("right", 35)):
        attempted = _pair(runtimes, evidence_path / choice / "chosen", "improve", seed=choice, limit=5,
                          native_options={"source_text": native}, w3_options={"source_text": w3})
        assert attempted["native"]["value"] == expected and attempted["native"]["requests"] == []
        if attempted["w3"]["phase"] == "compile":
            assert attempted["w3"]["diagnostics"] and attempted["w3"]["requests"] == []
        else:
            assert attempted["w3"]["value"] == expected and attempted["w3"]["requests"] == []
        branched = _pair(runtimes, evidence_path / choice / "branch", "improve", seed=choice, limit=5,
                         native_options={"source_text": native}, w3_options={"source_text": alternative})
        for result in branched.values():
            assert result["value"] == expected and result["requests"] == [] and result["exit"] == 0
        outcomes[choice] = {"chosen": attempted, "branch": branched}
    from tests.test_workflow_dynamic_edits import _save_receipt
    _save_receipt(evidence_path, "RW-C02", {"outcomes": outcomes,
        "native_runtime_function_choice": True, "w3_call_sites_branch": 2, "native_chosen_call_sites": 1,
        "effect_counts": 0, "timing": "unmeasured"}, {"native.orc": native, "w3.proc-ref.orc": w3, "w3.branch.orc": alternative})


def test_packet_commit_accepts_new_test_but_rejects_changed_runtime_and_helpers(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "comparison@example.invalid")
    _git(tmp_path, "config", "user.name", "Comparison test")
    for name in ("orchestrator/runtime.py", "tests/reused_helper.py"):
        path = tmp_path / name
        path.parent.mkdir(exist_ok=True)
        path.write_text("pinned bytes\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "runtime pin")
    pin = _git(tmp_path, "rev-parse", "HEAD").decode().strip()
    (tmp_path / "experiments/dynamic_core_evaluation").mkdir(parents=True)
    (tmp_path / "experiments/dynamic_core_evaluation/test_w3_dynamic_reevaluation.py").write_text("new packet test\n")
    (tmp_path / "README.md").write_text("new packet documentation\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-qm", "docs and comparison packet")
    receipt = _provenance(tmp_path, pin, False)
    assert receipt["packet_head"] != receipt["pin"]
    for name in ("orchestrator/runtime.py", "tests/reused_helper.py"):
        path = tmp_path / name
        path.write_text("modified control\n")
        with pytest.raises(AssertionError, match="Pinned source modified"):
            _provenance(tmp_path, pin, False)
        path.write_text("pinned bytes\n")


if __name__ == "__main__":
    try:
        assert sys.argv[1] == "--worker"
        _worker(Path(sys.argv[2]))
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
