"""PRR command gates and study-local workflow source contracts."""

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap
import uuid

import pytest

from experiments.compare import prepare, sandbox
from experiments.compare.prepare import ArmSpec
from experiments.compare.studies.prr_direct_orc import sources, trusted_check
from orchestrator.workflow_lisp.reader import read_sexpr_text
from orchestrator.workflow_lisp.sexpr import ListExpr


ROOT = Path(__file__).resolve().parents[2]
STUDY = ROOT / "experiments/compare/studies/prr_direct_orc"
SEED = ROOT / "experiments/orc_structural_search/seeds/capped"
RUNTIME = Path(os.environ.get("PRR_RUNTIME", ROOT)).resolve()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_context(path, context):
    path.write_text(json.dumps(context, sort_keys=True) + "\n")
    return path


@pytest.fixture
def pilot_context(tmp_path):
    repo = tmp_path / "candidate"
    (repo / "tests").mkdir(parents=True)
    (repo / "tests/test_public.py").write_text("public fixture\n")
    (repo / "pytest.ini").write_text("[pytest]\n")
    marker = "from pathlib import Path; Path('helper-started').write_text('started'); raise SystemExit(3)"
    (repo / "dev-check.json").write_text(json.dumps({
        "argv": [sys.executable, "-c", marker], "timeout_sec": 1800,
    }))
    helper = tmp_path / "frozen-dev-check.py"
    shutil.copyfile(SEED / "dev_check.py", helper)
    records = tmp_path / "records"
    for ordinal in (1, 2):
        call = records / "calls" / str(ordinal)
        call.mkdir(parents=True)
        (call / "patch-cand-1.diff").write_bytes(b"same original snapshot")
    context = {
        "repo": str(repo), "records": str(records), "diagnostics": str(tmp_path / "diagnostics"),
        "helper": {"path": str(helper), "sha256": digest(helper)},
        "protected": {
            name: digest(repo / name)
            for name in ("dev-check.json", "tests/test_public.py", "pytest.ini")
        } | {"conftest.py": None},
    }
    context_path = _write_context(tmp_path / "context.json", context)
    return context, context_path


def _run_helper(context_path, mode, bundle, *, cwd=None):
    return subprocess.run(
        [sys.executable, str(STUDY / "trusted_check.py"), mode, str(context_path)],
        env={**os.environ, "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(bundle)},
        cwd=cwd, capture_output=True, text=True,
    )


def _bundle(context, name):
    path = Path(context["repo"]) / ".orchestrate" / "prr-tests" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _diagnostic(context, stage):
    rows = [json.loads(path.read_text()) for path in Path(context["diagnostics"]).glob("*.json")]
    assert len(rows) == 1
    assert rows[0]["stage"] == stage
    assert rows[0]["paid_continuation_allowed"] is False
    return rows[0]


def test_public_check_failure_is_a_report_and_allows_the_workflow_branch(pilot_context, tmp_path):
    context, context_path = pilot_context
    bundle = _bundle(context, "check-result.json")
    done = _run_helper(context_path, "check", bundle)
    report = json.loads(bundle.read_text())
    assert done.returncode == 0, done.stderr
    assert report["passed"] is False and report["failing"]
    assert (Path(context["repo"]) / "helper-started").read_text() == "started"
    assert not Path(context["diagnostics"]).exists()


def test_public_check_resolves_relative_bundle_from_command_workspace(pilot_context):
    context, context_path = pilot_context
    repo = Path(context["repo"])
    command_workspace = repo / ".orchestrate/runs/command-smoke"
    command_workspace.mkdir(parents=True)
    relative_bundle = Path("effects/check/attempt-1/result.json")
    (command_workspace / relative_bundle).parent.mkdir(parents=True)
    done = _run_helper(context_path, "check", relative_bundle, cwd=command_workspace)
    assert done.returncode == 0, done.stderr
    report = json.loads((command_workspace / relative_bundle).read_text())
    assert report["passed"] is False and report["failing"]


def test_output_bundle_cannot_escape_candidate(pilot_context, tmp_path):
    context, context_path = pilot_context
    outside_bundle = tmp_path / "outside-result.json"
    done = _run_helper(context_path, "check", outside_bundle)
    assert done.returncode == 70
    assert not outside_bundle.exists()
    assert "inside the candidate" in _diagnostic(context, "before-tests")["reason"]


@pytest.mark.parametrize("changed", ["dev-check.json", "tests/test_public.py", "pytest.ini", "conftest.py", "helper"])
def test_integrity_change_stops_before_public_check(pilot_context, tmp_path, changed):
    context, context_path = pilot_context
    target = Path(context["helper"]["path"]) if changed == "helper" else Path(context["repo"]) / changed
    target.write_text("changed before check\n")
    bundle = _bundle(context, "integrity-result.json")
    done = _run_helper(context_path, "check", bundle)
    assert done.returncode == 70
    assert not bundle.exists() and not (Path(context["repo"]) / "helper-started").exists()
    _diagnostic(context, "before-tests")


def test_missing_helper_hash_is_an_integrity_failure(pilot_context, tmp_path):
    context, context_path = pilot_context
    del context["helper"]["sha256"]
    _write_context(context_path, context)
    done = _run_helper(context_path, "check", _bundle(context, "missing-hash.json"))
    assert done.returncode == 70
    assert not (Path(context["repo"]) / "helper-started").exists()
    _diagnostic(context, "context")


def test_malformed_protected_hash_is_an_integrity_failure(pilot_context, tmp_path):
    context, context_path = pilot_context
    context["protected"]["pytest.ini"] = "not-a-sha256"
    _write_context(context_path, context)
    done = _run_helper(context_path, "check", _bundle(context, "malformed-hash.json"))
    assert done.returncode == 70
    assert not (Path(context["repo"]) / "helper-started").exists()
    assert "invalid SHA256" in _diagnostic(context, "context")["reason"]


def test_protected_symlink_cannot_escape_candidate(pilot_context, tmp_path):
    context, context_path = pilot_context
    outside = tmp_path / "outside.py"
    outside.write_text("public fixture\n")
    target = Path(context["repo"]) / "tests/test_public.py"
    target.unlink()
    target.symlink_to(outside)
    done = _run_helper(context_path, "check", _bundle(context, "symlink.json"))
    assert done.returncode == 70
    assert not (Path(context["repo"]) / "helper-started").exists()
    _diagnostic(context, "before-tests")


def test_protected_parent_symlink_cannot_escape_candidate(pilot_context, tmp_path):
    context, context_path = pilot_context
    repo = Path(context["repo"])
    external = tmp_path / "external-tests"
    external.mkdir()
    (external / "test_public.py").write_text("public fixture\n")
    (repo / "tests").rename(repo / "tests.original")
    (repo / "tests").symlink_to(external, target_is_directory=True)
    done = _run_helper(context_path, "check", _bundle(context, "parent-symlink.json"))
    assert done.returncode == 70
    assert not (repo / "helper-started").exists()
    assert "symlink" in _diagnostic(context, "before-tests")["reason"].lower()


def test_context_file_must_be_outside_candidate(pilot_context, tmp_path):
    context, _ = pilot_context
    context_path = _write_context(Path(context["repo"]) / "context.json", context)
    done = _run_helper(context_path, "check", _bundle(context, "inside-context.json"))
    assert done.returncode == 70
    assert not (Path(context["repo"]) / "helper-started").exists()
    assert "context" in _diagnostic(context, "context")["reason"].lower()


def test_check_rejects_a_protected_file_changed_during_public_tests(pilot_context, tmp_path):
    context, context_path = pilot_context
    repo = Path(context["repo"])
    config = repo / "dev-check.json"
    config.write_text(json.dumps({
        "argv": [sys.executable, "-c", "from pathlib import Path; Path('pytest.ini').write_text('tampered')"],
        "timeout_sec": 1800,
    }))
    context["protected"]["dev-check.json"] = digest(config)
    _write_context(context_path, context)
    done = _run_helper(context_path, "check", _bundle(context, "mutated-result.json"))
    assert done.returncode == 70
    assert json.loads(next(Path(context["diagnostics"]).glob("*.json")).read_text())["stage"] == "after-tests"


def test_diagnosis_audit_admits_only_the_unchanged_snapshot(pilot_context, tmp_path):
    context, context_path = pilot_context
    bundle = _bundle(context, "audit-result.json")
    done = _run_helper(context_path, "audit-diagnosis", bundle)
    assert done.returncode == 0, done.stderr
    assert json.loads(bundle.read_text()) is True

    second = Path(context["records"]) / "calls/2/patch-cand-1.diff"
    second.write_bytes(b"diagnosis edited implementation")
    refused = _run_helper(context_path, "audit-diagnosis", _bundle(context, "mutated-audit.json"))
    assert refused.returncode == 70
    assert not (tmp_path / "mutated-audit.json").exists()
    _diagnostic(context, "after-diagnosis")


def test_diagnosis_audit_refuses_if_repair_call_exists_early(pilot_context, tmp_path):
    context, context_path = pilot_context
    (Path(context["records"]) / "calls/3").mkdir()
    done = _run_helper(context_path, "audit-diagnosis", _bundle(context, "early-repair.json"))
    assert done.returncode == 70
    assert not (tmp_path / "early-repair.json").exists()
    _diagnostic(context, "after-diagnosis")


def test_final_capture_can_recheck_the_protected_manifest(pilot_context):
    context, _ = pilot_context
    trusted_check.verify(context, "final-capture")
    (Path(context["repo"]) / "tests/test_public.py").unlink()
    with pytest.raises(trusted_check.IntegrityError):
        trusted_check.verify(context, "final-capture")
    _diagnostic(context, "final-capture")


def _forms(path):
    return read_sexpr_text(path.read_text(), source_path=str(path)).items[0].items


def _render(expr):
    if isinstance(expr, ListExpr):
        return "(" + " ".join(_render(item) for item in expr.items) + ")"
    return str(expr.value)


def _walk(expr):
    if isinstance(expr, ListExpr):
        yield expr
        for item in expr.items:
            yield from _walk(item)


def _form(forms, name):
    return next(form for form in forms if isinstance(form, ListExpr) and _render(form.items[0]) == name)


def _keyword_args(form, start=2):
    return {_render(form.items[index]): form.items[index + 1]
            for index in range(start, len(form.items), 2)}


def _first_implementation_call(path):
    forms = _forms(path)
    prompt = _form(forms, "defprompt")
    assert _render(prompt.items[1]) == "implement-prompt"
    fills = _render(prompt.items[2])
    assert fills == "(:fills (task :text) (repo :text))"
    assert _render(prompt.items[4]) == "Change"
    run = _form(forms, "defworkflow")
    assert _render(run.items[1]) == "run"
    calls = [node for node in _walk(run) if _render(node.items[0]) == "provider-result"]
    first = calls[0]
    args = _keyword_args(first)
    prompt_call = args[":prompt"]
    prompt_args = _keyword_args(prompt_call, start=1)
    return (
        _render(first.items[1]), _render(prompt_call.items[0]),
        tuple(sorted((key, _render(value)) for key, value in prompt_args.items())),
        _render(args[":model"]), _render(args[":effort"]), _render(args[":timeout-sec"]),
    )


def test_rendered_sources_preserve_seed_shapes_and_compile_current_runtime(tmp_path):
    snapshot = tmp_path / "frozen source snapshot"
    snapshot.mkdir()
    source_names = (
        "sources.py", "common.orc", "direct.orc", "implement_check_diagnose_repair.orc",
        "providers.json", "commands.json", "trusted_check.py", "dev_check.py",
    )
    for name in source_names:
        shutil.copyfile(STUDY / name, snapshot / name)
    snapshot_hashes = {name: digest(snapshot / name) for name in source_names}
    loader = importlib.util.spec_from_file_location("prr_frozen_sources", snapshot / "sources.py")
    frozen_sources = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(frozen_sources)

    with pytest.raises(ValueError, match="differ from the frozen source snapshot"):
        frozen_sources.render_sources(snapshot, sys.executable, snapshot / "trusted_check.py")
    assert {name: digest(snapshot / name) for name in source_names} == snapshot_hashes

    destination = tmp_path / "rendered study sources"
    rendered = frozen_sources.render_sources(destination, sys.executable, snapshot / "trusted_check.py")
    assert {name: digest(snapshot / name) for name in source_names} == snapshot_hashes
    assert rendered == {
        "source_root": destination.resolve(), "direct": destination / "direct.orc",
        "orc": destination / "implement_check_diagnose_repair.orc",
        "providers": destination / "providers.json", "commands": destination / "commands.json",
    }
    assert (destination / "common.orc").read_bytes() == (SEED / "common.orc").read_bytes()
    assert (snapshot / "dev_check.py").read_bytes() == (SEED / "dev_check.py").read_bytes()
    assert not (destination / "trusted_check.py").exists()
    assert not (destination / "dev_check.py").exists()

    providers = json.loads(rendered["providers"].read_text())
    assert providers == {
        "providers.coder": "codex_unrestricted_workspace",
        "providers.reviewer": "codex_unrestricted_workspace",
    }
    commands = json.loads(rendered["commands"].read_text())
    trusted = str((snapshot / "trusted_check.py").resolve())
    helper = str((snapshot / "dev_check.py").resolve())
    for name, mode in (("dev-check", "check"), ("audit-diagnosis", "audit-diagnosis")):
        assert commands[name]["stable_command"] == [str(Path(sys.executable).resolve()), trusted, mode]
        assert commands[name]["closure"] == sorted([trusted, helper])

    # Compare the current typed prompt and its input dataflow across the two arms;
    # the study may clarify public evaluation inputs without freezing seed prose.
    assert _render(_form(_forms(rendered["direct"]), "defprompt")) == _render(
        _form(_forms(rendered["orc"]), "defprompt"))
    direct = _first_implementation_call(rendered["direct"])
    orc = _first_implementation_call(rendered["orc"])
    assert direct == orc == (
        "providers.coder", "implement-prompt", ((":repo", "repo"), (":task", "task")),
        "gpt-5.6-luna", "high", "14400",
    )

    for source, module in ((rendered["direct"], "direct"),
                           (rendered["orc"], "implement_check_diagnose_repair")):
        done = subprocess.run(
            [sys.executable, "-P", "-m", "orchestrator", "compile", str(source),
             "--entry-workflow", f"{module}::run", "--source-root", str(rendered["source_root"]),
             "--provider-externs-file", str(rendered["providers"]), "--command-boundaries-file",
             str(rendered["commands"]), "--diagnostics-json"],
             cwd=RUNTIME, env={**os.environ, "PYTHONPATH": str(RUNTIME)}, capture_output=True, text=True,
        )
        assert done.returncode == 0, done.stdout + done.stderr
        assert json.loads(done.stdout)["status"] == "accepted"


def _open_tree(path):
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        return
    path.chmod(0o755)
    for child in path.iterdir():
        _open_tree(child)


def _smoke_task(task, runtime, mode):
    template = ROOT / "experiments/compare/tasks/pure-result-replay-command-recovery"
    task.mkdir(parents=True)
    for name in ("task.txt", "intent.txt"):
        shutil.copyfile(template / name, task / name)
    seed = task / "seed"
    (seed / "tests").mkdir(parents=True)
    (seed / "tests/test_prr_smoke.py").write_text("def test_public_smoke():\n    assert True\n")
    if mode in {"fail", "diagnosis-mutation"}:
        argv = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                "tests/test_missing_prr_smoke.py"]
    else:
        argv = [sys.executable, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider",
                "tests/test_prr_smoke.py"]
    (seed / "dev-check.json").write_text(json.dumps({"argv": argv, "timeout_sec": 1800}) + "\n")
    base = subprocess.run(["git", "-C", str(runtime), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    (task / "base_commit").write_text(base + "\n")


def _fake_codex(path):
    path.write_text(textwrap.dedent("""\
        #!/usr/bin/env python3
        import json
        import os
        from pathlib import Path
        import sys

        marker = Path.cwd() / ".orchestrate" / "prr-smoke-call-count"
        marker.parent.mkdir(parents=True, exist_ok=True)
        count = int(marker.read_text()) + 1 if marker.exists() else 1
        marker.write_text(str(count))
        case = os.environ["PRR_FAKE_CASE"]
        repo = Path.cwd()
        prompt = sys.stdin.read()
        if count == 1:
            if case == "integrity":
                (repo / "dev-check.json").write_text('{"argv": ["false"], "timeout_sec": 1800}\\n')
            else:
                (repo / "solution.py").write_text("value = 1\\n")
            result = {"summary": "smoke implementation", "account": "synthetic"}
        elif count == 2:
            if case == "diagnosis-mutation":
                (repo / "solution.py").write_text("value = 2\\n")
            result = {"findings": ["synthetic diagnosis"]}
        else:
            (repo / "solution.py").write_text("value = 3\\n")
            result = {"summary": "smoke repair", "account": "synthetic"}
        bundle_line = next((line for line in prompt.splitlines() if line.startswith("- path: ")), None)
        if bundle_line is None:
            raise SystemExit("fake Codex prompt omitted the structured-result path")
        bundle_path = Path(bundle_line.partition(":")[2].strip())
        bundle = bundle_path if bundle_path.is_absolute() else repo / bundle_path
        bundle.parent.mkdir(parents=True, exist_ok=True)
        bundle.write_text(json.dumps(result) + "\\n")
        print(json.dumps({"type": "thread.started", "thread_id": f"smoke-{count}"}))
        print(json.dumps({"type": "turn.started"}))
        print(json.dumps({"type": "item.completed", "item": {
            "type": "agent_message", "id": f"message-{count}", "text": json.dumps(result)}}))
        print(json.dumps({"type": "turn.completed"}))
    """))
    path.chmod(0o755)


def _smoke_environment(root, sources_dir, fake_cli, home, monkeypatch, mode):
    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                 "CLAUDE_CODE_OAUTH_TOKEN_FILE"):
        monkeypatch.delenv(name, raising=False)
    declaration = sandbox.dependencies({"PATH": "", "HOME": str(home)})
    declaration["codex"] = str(fake_cli.resolve())
    declaration["readonly"] = dict(declaration["readonly"])
    declaration["readonly"][str(fake_cli.resolve())] = str(fake_cli.resolve())
    declaration["readonly"][str(sources_dir.resolve())] = str(sources_dir.resolve())
    declaration["path"] = [str(fake_cli.parent.resolve()), *declaration["path"]]
    declaration["environment"] = sorted(set(declaration["environment"]) | {"PRR_FAKE_CASE"})
    config = root / "sandbox-dependencies.json"
    config.write_text(json.dumps(declaration, indent=2) + "\n")
    return {
        "COMPARE_SANDBOX": str(config), "COMPARE_MAX_CALLS": "3",
        "COMPARE_CODEX_MODELS": "gpt-5.6-luna", "HOME": str(home),
        "CODEX_HOME": str(home / ".codex"), "PRR_FAKE_CASE": mode,
    }


def _run_inert_smoke(root, runtime, monkeypatch, mode, arm):
    run_root = root / "work"
    run_root.mkdir()
    sources_dir = root / "sources"
    sources_dir.mkdir()
    rendered = sources.render_sources(sources_dir, sys.executable, STUDY / "trusted_check.py")
    fake_dir = root / "fakebin"
    fake_dir.mkdir()
    fake_cli = fake_dir / "codex"
    _fake_codex(fake_cli)
    home = root / "empty-home"
    home.mkdir()
    environment = _smoke_environment(root, sources_dir, fake_cli, home, monkeypatch, mode)
    task = root / "task"
    _smoke_task(task, runtime, mode)
    source = rendered["direct"] if arm == "direct" else rendered["orc"]
    module = "direct" if arm == "direct" else "implement_check_diagnose_repair"
    spec = ArmSpec(
        source=source, entry=f"{module}::run", source_root=rendered["source_root"],
        providers=rendered["providers"], inputs=("task", "intent", "repo", "context"),
        command_boundaries=rendered["commands"],
    )
    context_path = sources_dir / "context.json"
    records = prepare.run_arm(
        task, f"prr_{mode}", run_root, runtime, sets=(f"context={context_path}",),
        spec=spec, environment=environment,
    )
    record = json.loads((records / "record.json").read_text())
    candidate = Path(record["candidates"][0])
    protected_names = {"dev-check.json", "tests/test_prr_smoke.py"}
    tracked = subprocess.run(["git", "-C", str(candidate), "ls-files", "--cached"],
                             check=True, capture_output=True, text=True).stdout.splitlines()
    protected_names.update(
        name for name in tracked
        if Path(name).name in {"conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"}
    )
    protected_names.update(("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"))
    protected = {}
    for relative in protected_names:
        path = candidate / relative
        protected[relative] = digest(path) if path.is_file() else None
    helper = STUDY / "dev_check.py"
    context = {
        "repo": str(candidate), "records": str(records), "diagnostics": str(root / "diagnostics" / mode),
        "helper": {"path": str(helper), "sha256": digest(helper)}, "protected": protected,
    }
    _write_context(context_path, context)
    command = subprocess.run(
        ["bash", str(records / "command.sh")], cwd=ROOT,
        env={**os.environ, **environment},
        capture_output=True, text=True, timeout=90,
    )
    if mode in {"integrity", "diagnosis-mutation"}:
        assert command.returncode != 0, f"expected integrity halt; smoke artifacts: {root}"
    else:
        assert command.returncode == 0, f"{command.stdout}{command.stderr}smoke artifacts: {root}"
    collected = prepare.collect(records)
    calls = sorted((records / "calls").iterdir(), key=lambda path: int(path.name))
    return records, record, collected, calls


@pytest.mark.skipif(not os.environ.get("PRR_RUNTIME"), reason="set PRR_RUNTIME to the approved derived runtime")
@pytest.mark.parametrize(
    "mode,arm,calls_expected,outcome",
    [("direct", "direct", 1, "completed"), ("pass", "orc", 1, "completed"),
     ("fail", "orc", 3, "completed"), ("integrity", "orc", 1, "failed"),
     ("diagnosis-mutation", "orc", 2, "failed")],
)
def test_approved_runtime_inert_orchestrator_smoke(
    monkeypatch, mode, arm, calls_expected, outcome,
):
    probe = ["bwrap", "--dev-bind", "/", "/", "--tmpfs", "/dev/shm", "--tmpfs", "/var/tmp",
             "--unshare-pid", "--proc", "/proc", "true"]
    if shutil.which("bwrap") is None or subprocess.run(probe, capture_output=True).returncode:
        pytest.skip("the compare CLI shim requires working bubblewrap support")
    outside = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "compare-harness-tests"
    outside.mkdir(parents=True, exist_ok=True)
    root = Path(tempfile.mkdtemp(prefix=f"prr-{mode}-", dir=outside))
    passed = False
    try:
        records, record, collected, calls = _run_inert_smoke(root, RUNTIME, monkeypatch, mode, arm)
        assert len(calls) == calls_expected
        assert collected["outcome"] == outcome
        if mode in {"integrity", "diagnosis-mutation"}:
            memo = next(Path(record["state_root"]).glob("*/memo.jsonl"))
            rows = [json.loads(line) for line in memo.read_text().splitlines()]
            failed = next(row for row in rows if row["record"] == "failed")
            assert failed["exit_info"]["exit_code"] == 70
        if mode == "integrity":
            diagnostics = list((root / "diagnostics" / mode).glob("*.json"))
            assert len(diagnostics) == 1
            assert json.loads(diagnostics[0].read_text())["paid_continuation_allowed"] is False
        if mode == "diagnosis-mutation":
            assert not (records / "calls/3").exists()
            diagnostics = list((root / "diagnostics" / mode).glob("*.json"))
            assert len(diagnostics) == 1
            assert "diagnosis changed" in json.loads(diagnostics[0].read_text())["reason"]
        if mode == "pass":
            assert (records / "calls/1/prompt.txt").is_file()
        if mode == "fail":
            assert (records / "calls/3").is_dir()
        passed = True
    finally:
        if passed:
            _open_tree(root)
            shutil.rmtree(root)
