from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from orchestrator.cli.commands.resume import resume_workflow
from orchestrator.cli.commands.invalidate import invalidate_run
from orchestrator.cli.run_ref_root import resolve_run_ref_root
from orchestrator.workflow.evaluated.authority import RunAuthorityError, load_run_header
from tests.test_workflow_evaluated_cli import _build, _run_cli
from tests.test_workflow_evaluated_invalidate import _tree_bytes


def test_new_header_fixes_default_without_creating_root(tmp_path, monkeypatch):
    home_at_run = tmp_path / "home-at-run"
    home_at_resume = tmp_path / "home-at-resume"
    home_at_run.mkdir()
    home_at_resume.mkdir()
    monkeypatch.setenv("HOME", str(home_at_run))
    source, _program = _build(tmp_path)
    expected_root = resolve_run_ref_root(None)

    result = _run_cli(tmp_path, str(source), "--input", "score=0.75")

    assert result.returncode == 0, result.stderr
    (run_root,) = (tmp_path / ".orchestrate" / "runs").iterdir()
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    assert header["run_ref_root"] == expected_root.as_posix()
    assert not expected_root.exists()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(home_at_resume))
    before = header_path.read_bytes()
    assert resume_workflow(run_root.name) == 0

    assert header_path.read_bytes() == before
    assert not expected_root.exists()
    assert not resolve_run_ref_root(None).exists()


def test_public_run_records_explicit_root_without_creating_it(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    source, program = _build(tmp_path)
    selected_root = (tmp_path / "runtime" / "refs").resolve(strict=False)
    default_root = resolve_run_ref_root(None)

    default_result = _run_cli(tmp_path, str(source), "--input", "score=0.75")
    assert default_result.returncode == 0, default_result.stderr
    runs_root = tmp_path / ".orchestrate" / "runs"
    (default_run_root,) = runs_root.iterdir()
    explicit_result = _run_cli(
        tmp_path,
        str(source),
        "--input",
        "score=0.75",
        "--run-ref-root",
        selected_root.as_posix(),
    )
    assert explicit_result.returncode == 0, explicit_result.stderr
    explicit_run_root = (set(runs_root.iterdir()) - {default_run_root}).pop()

    default_header = json.loads((default_run_root / "run.json").read_text(encoding="utf-8"))
    explicit_header = json.loads((explicit_run_root / "run.json").read_text(encoding="utf-8"))
    assert explicit_header["run_ref_root"] == selected_root.as_posix()
    assert default_header["program_digest"] == explicit_header["program_digest"] == program.digest
    assert default_header["input_digest"] == explicit_header["input_digest"]
    assert default_header["resume_request"] == explicit_header["resume_request"]
    assert "run_ref_root" not in explicit_header["resume_request"]
    assert selected_root.is_relative_to(tmp_path)
    assert not default_root.exists()
    assert not selected_root.exists()


def _completed_run(root: Path, *arguments: str) -> Path:
    source, _program = _build(root)
    result = _run_cli(root, str(source), "--input", "score=0.75", *arguments)
    assert result.returncode == 0, result.stderr
    (run_root,) = (root / ".orchestrate" / "runs").iterdir()
    return run_root


def test_resume_root_option_mismatch_is_readonly(tmp_path, monkeypatch, caplog):
    run_root = _completed_run(tmp_path)
    changed_root = (tmp_path / "different-run-ref").resolve(strict=False)
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("memo was read before run-reference root preflight finished")

    monkeypatch.setattr("orchestrator.workflow.evaluated.runtime.read_memo", forbidden)
    before = _tree_bytes(run_root)
    assert resume_workflow(run_root.name, run_ref_root=changed_root.as_posix()) == 2

    assert "resume_run_ref_root_changed" in caplog.text
    assert _tree_bytes(run_root) == before
    assert not changed_root.exists()


def test_resume_accepts_equivalent_explicit_root_readonly(tmp_path, monkeypatch):
    selected_root = (tmp_path / "selected-run-ref").resolve(strict=False)
    run_root = _completed_run(tmp_path, "--run-ref-root", selected_root.as_posix())
    monkeypatch.chdir(tmp_path)
    before = _tree_bytes(run_root)

    assert resume_workflow(run_root.name, run_ref_root=selected_root.as_posix()) == 0

    assert _tree_bytes(run_root) == before
    assert not selected_root.exists()


def test_missing_recipe_precedes_explicit_root_mismatch(tmp_path, monkeypatch, caplog):
    recorded_root = (tmp_path / "recorded-run-ref").resolve(strict=False)
    changed_root = (tmp_path / "different-run-ref").resolve(strict=False)
    run_root = _completed_run(tmp_path, "--run-ref-root", recorded_root.as_posix())
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.pop("resume_request")
    header_path.write_text(json.dumps(header), encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    def forbidden(*args, **kwargs):
        pytest.fail("memo was read before recipe preflight finished")

    monkeypatch.setattr("orchestrator.workflow.evaluated.runtime.read_memo", forbidden)
    before = _tree_bytes(run_root)
    assert resume_workflow(run_root.name, run_ref_root=changed_root.as_posix()) == 2

    assert "resume_request_missing" in caplog.text
    assert "resume_run_ref_root_changed" not in caplog.text
    assert _tree_bytes(run_root) == before


def test_historical_missing_root_is_not_backfilled_from_resume_flag(tmp_path, monkeypatch):
    run_root = _completed_run(tmp_path)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    header.pop("run_ref_root")
    header_path.write_text(json.dumps(header), encoding="utf-8")
    selected_root = (tmp_path / "new-run-ref").resolve(strict=False)
    monkeypatch.chdir(tmp_path)
    before = _tree_bytes(run_root)

    assert resume_workflow(run_root.name, run_ref_root=selected_root.as_posix()) == 0

    assert _tree_bytes(run_root) == before
    assert not selected_root.exists()


def test_header_reader_accepts_all_historical_recipe_root_combinations(tmp_path):
    run_root = _completed_run(tmp_path)
    header_path = run_root / "run.json"
    current = json.loads(header_path.read_text(encoding="utf-8"))
    recipe = current.pop("resume_request")
    root = current.pop("run_ref_root")

    for has_recipe in (False, True):
        for has_root in (False, True):
            header = dict(current)
            if has_recipe:
                header["resume_request"] = recipe
            if has_root:
                header["run_ref_root"] = root
            header_path.write_text(json.dumps(header), encoding="utf-8")
            loaded = load_run_header(run_root)
            assert ("resume_request" in loaded) is has_recipe
            assert ("run_ref_root" in loaded) is has_root


def _remove_recorded_root(authority):
    header = json.loads(authority.header_path.read_text())
    header.pop("run_ref_root")
    authority.header_path.write_text(json.dumps(header))


def _historical_empty_run(monkeypatch, parent, source, refs, *extra):
    from tests.test_workflow_evaluated_run_ref import _authority
    from tests.test_workflow_evaluated_run_ref_settlement import _service_run

    with monkeypatch.context() as context:
        context.setattr("orchestrator.cli.commands.evaluated.execute_pure_run", lambda *a, **kw: (1, None))
        assert _service_run(context, parent, source, refs, *extra).exit_code == 1
    authority, memo = _authority(parent)
    assert not memo.entries
    _remove_recorded_root(authority)
    return authority


def test_missing_root_at_first_reached_run_ref_is_readonly(tmp_path, monkeypatch):
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    from tests.test_workflow_evaluated_resume import _resume_cli

    parent, source, refs = _public_fixture(tmp_path)
    authority = _historical_empty_run(monkeypatch, parent, source, refs)
    before = _tree_bytes(parent)
    resumed = _resume_cli(parent, authority.run_root.name)
    assert resumed.returncode == 2, resumed.stderr
    assert "resume_run_ref_root_missing" in resumed.stderr
    assert _tree_bytes(parent) == before and not refs.exists()


def _root_frontier_fixture(tmp_path, monkeypatch, kind, selected):
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    from tests.test_workflow_evaluated_providers import _fixture

    child = lambda call: f"(let* ((child {call})) child.value)"
    if kind == "provider":
        decision = '(provider-result providers.review :prompt prompts.base :inputs () :returns Result)'
        body = lambda call: f'(let* ((decision {decision})) (if decision.ok {child(call)} false))'
        definitions = '(defrecord Result (ok Bool))'
    else:
        decision = '(command-result choose :argv ("python" "choose.py") :returns Bool)'
        body = (lambda call: f'(let* ((decision {decision})) {child(call)})') if kind == "command-sequential" else (
            lambda call: f'(if {decision} {child(call)} false)')
        definitions = ""
    parent, source, refs = _public_fixture(tmp_path, body=body, definitions=definitions)
    if kind == "provider":
        _path, providers, prompts, _request = _fixture(parent)
        monkeypatch.setenv("PATH", str(parent / "bin") + os.pathsep + os.environ["PATH"])
        monkeypatch.setenv("PROVIDER_SHIM_RESULT", json.dumps({"ok": selected}))
        extra = ("--provider-externs-file", str(providers), "--prompt-externs-file", str(prompts))
    else:
        (parent / "choose.py").write_text('import os\nfrom pathlib import Path\n'
            'Path("dispatches").open("a").write("choose\\n")\n'
            f'Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text("{str(selected).lower()}")\n')
        boundaries = parent / "commands.json"
        boundaries.write_text(json.dumps({"choose": {"stable_command": ["python", "choose.py"], "closure": ["choose.py"]}}))
        extra = ("--command-boundaries-file", str(boundaries))
    return parent, source, refs, extra


@pytest.mark.parametrize("kind", ["command-conditional", "command-sequential", "provider"])
@pytest.mark.parametrize("selected", [True, False])
def test_missing_root_after_new_effect_preserves_local_frontier(tmp_path, monkeypatch, kind, selected):
    from tests.test_workflow_evaluated_run_ref import _authority
    from tests.test_workflow_evaluated_resume import _resume_cli

    parent, source, refs, extra = _root_frontier_fixture(tmp_path, monkeypatch, kind, selected)
    authority = _historical_empty_run(monkeypatch, parent, source, refs, *extra)
    reached = selected or kind == "command-sequential"
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == (1 if reached else 0), result.stderr
    _, memo = _authority(parent)
    assert len(memo.active_commits) == 1 and not memo.pending_starts
    assert not refs.exists() and not (authority.run_root / "run-ref-attempts.jsonl").exists()
    assert all(row.data.get("effect_class") != "run_ref" for row in memo.entries)
    if reached:
        assert "resume_run_ref_root_missing" in result.stderr
        assert memo.terminal.data["outcome"] == "failed"
    before = _tree_bytes(parent)
    second = _resume_cli(parent, authority.run_root.name)
    assert second.returncode == (2 if reached else 0), second.stderr
    assert _tree_bytes(parent) == before


def test_missing_root_at_committed_run_ref_precedes_reconcile(tmp_path, monkeypatch):
    from tests.test_workflow_evaluated_run_ref import _public_fixture
    from tests.test_workflow_evaluated_run_ref_settlement import _commit_gap
    from tests.test_workflow_evaluated_resume import _resume_cli

    parent, source, refs = _public_fixture(tmp_path)
    authority, _memo = _commit_gap(monkeypatch, parent, source, refs)
    _remove_recorded_root(authority)
    before = _tree_bytes(parent), _tree_bytes(refs)
    result = _resume_cli(parent, authority.run_root.name)
    assert result.returncode == 2 and "resume_run_ref_root_missing" in result.stderr
    assert (_tree_bytes(parent), _tree_bytes(refs)) == before


def test_malformed_present_root_refuses_readonly_and_invalidation_without_path_io(
    tmp_path, monkeypatch, caplog
):
    run_root = _completed_run(tmp_path)
    header_path = run_root / "run.json"
    header = json.loads(header_path.read_text(encoding="utf-8"))
    malformed_roots = (
        "",
        "relative/run-ref",
        "/tmp/run-ref/../other",
        "//tmp/run-ref",
        "/tmp//run-ref",
        "/dev/fd",
        "/dev/fd/17",
        "/proc/self/fd/17",
        "\x00",
        None,
        17,
    )
    path_spellings = {value for value in malformed_roots if isinstance(value, str)}
    original_resolve = Path.resolve
    original_open = os.open
    original_stat = os.stat
    original_lstat = os.lstat

    def forbidden_root_io(path, *args, **kwargs):
        spelling = os.fsdecode(os.fspath(path))
        if spelling in path_spellings:
            pytest.fail(f"malformed run-reference root was accessed: {spelling!r}")

    def guarded_resolve(path, *args, **kwargs):
        if os.fspath(path) in path_spellings:
            pytest.fail(f"malformed run-reference root was resolved: {path}")
        return original_resolve(path, *args, **kwargs)

    def guarded_open(path, *args, **kwargs):
        forbidden_root_io(path)
        return original_open(path, *args, **kwargs)

    def guarded_stat(path, *args, **kwargs):
        forbidden_root_io(path)
        return original_stat(path, *args, **kwargs)

    def guarded_lstat(path, *args, **kwargs):
        forbidden_root_io(path)
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", guarded_resolve)
    monkeypatch.setattr(os, "open", guarded_open)
    monkeypatch.setattr(os, "stat", guarded_stat)
    monkeypatch.setattr(os, "lstat", guarded_lstat)

    def forbidden_memo_read(*args, **kwargs):
        pytest.fail("memo was read before malformed header preflight finished")

    monkeypatch.setattr("orchestrator.workflow.evaluated.runtime.read_memo", forbidden_memo_read)
    monkeypatch.setattr("orchestrator.workflow.evaluated.memo.read_memo", forbidden_memo_read)
    monkeypatch.chdir(tmp_path)

    for malformed_root in malformed_roots:
        header["run_ref_root"] = malformed_root
        header_path.write_text(json.dumps(header), encoding="utf-8")
        before = _tree_bytes(run_root)
        with pytest.raises(RunAuthorityError) as loaded_error:
            load_run_header(run_root)
        assert loaded_error.value.code == "memo_inconsistent"
        assert resume_workflow(run_root.name) == 2
        with pytest.raises(RunAuthorityError) as invalidation_error:
            invalidate_run(run_root.name, "unused")
        assert invalidation_error.value.code == "memo_inconsistent"
        assert _tree_bytes(run_root) == before

    assert "memo_inconsistent" in caplog.text
