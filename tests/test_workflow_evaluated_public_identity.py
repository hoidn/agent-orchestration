"""Public effect identities and macro provenance with real bundle producers."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from orchestrator.workflow.evaluated.views import load_evaluated_view
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from tests.test_workflow_evaluated_providers import _orchestrate_snapshot
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.test_workflow_lisp_closed_program_compile_cli import _compile
from tests.workflow_evaluated_context_helpers import pure_files, pause_context
from tests.workflow_evaluated_totality_helpers import checked_run, compile_public, assert_commit_bytes
from tests.test_workflow_evaluated_calls import _walk_nodes


PROBE = '''import json, os, sys
from pathlib import Path
command, raw = sys.argv[1:3]
n = int(raw)
with open("requests.jsonl", "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "cwd": os.getcwd(),
        "bundle": os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]}) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"n": n}))
'''


def _arms_source():
    path = Path(__file__).parent / "experiments/fixtures/evaluated_execution_spike/arms_in_loop.orc"
    return path.read_text().replace('(:target-dsl "2.33")', '(:target-dsl "2.35")')


def _pure_seed(source):
    return source.replace("(defworkflow run () -> Int\n    (loop/recur",
        "(defworkflow run () -> Int\n    (let* ((seed (+ 0 0))) (loop/recur").replace(
        "(i Int 0)", "(i Int seed)").replace("(done (+ state.total got.n))))))))",
        "(done (+ state.total got.n)))))))))")


def _effect_files(root, source):
    files, inputs = pure_files(root, source, {})
    (root / "probe.py").write_text(PROBE)
    files["commands"].write_text(json.dumps({"fetch": {"kind": "external_tool",
        "stable_command": ["python", "probe.py"], "closure": ["probe.py"]}}))
    return files, inputs


def _complete_effects(files, inputs, monkeypatch, *, expected=10):
    root = files["workspace"]
    compile_public(files)
    monkeypatch.chdir(root)
    pause = pause_context(files, monkeypatch, inputs)
    authority, before = checked_run(root)
    assert list(before.active_commits.values()) == [pause]
    prefix = authority.memo_path.read_bytes()
    resumed = _resume_cli(root, authority.header["run_id"])
    assert resumed.returncode == 0, resumed.stderr
    authority, completed = checked_run(root)
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert completed.terminal.data["value"] == expected
    _readonly_resume(root, authority.header["run_id"])
    return authority, completed


def _readonly_resume(root, run_id, *, package=None):
    before = _orchestrate_snapshot(root)
    requests = (root / "requests.jsonl").read_bytes()
    for _ in range(2):
        resumed = _package_cli(root, package, "resume", run_id) if package else _resume_cli(root, run_id)
        assert resumed.returncode == 0, resumed.stderr
        assert _orchestrate_snapshot(root) == before
        assert (root / "requests.jsonl").read_bytes() == requests


def _effect_observation(root, authority, snapshot):
    commits = list(snapshot.active_commits.values())
    requests = [json.loads(line) for line in (root / "requests.jsonl").read_text().splitlines()]
    assert len(commits) == len(snapshot.latest_starts) == len(requests) == 4
    assert [entry.data["value"] for entry in commits] == [{"n": n} for n in range(1, 5)]
    for n, entry, request in zip(range(1, 5), commits, requests, strict=True):
        assert_commit_bytes(authority, entry)
        assert request == {"argv": ["fetch", str(n)], "cwd": str(root),
            "bundle": (authority.run_root / entry.data["result_path"]).relative_to(root).as_posix()}
    fields = ("identity", "attempt", "effect_class", "input_parts", "input_digest",
              "depends_on", "value", "result_path", "result_digest")
    return {"sites": authority.program.tree["sites"],
            "commits": [{field: entry.data[field] for field in fields} for entry in commits],
            "starts": [{field: entry.data[field] for field in ("identity", "attempt", "input_parts", "input_digest")}
                       for entry in snapshot.latest_starts.values()]}


def test_public_effect_sites_survive_formatting_and_pure_seed_refactor(tmp_path, monkeypatch):
    source = _arms_source()
    observations = []
    for name, text in (("base", source), ("formatted", "\n; formatting only\n" + source),
                       ("pure-seed", _pure_seed(source)), ("pure-renamed", _pure_seed(source).replace("seed", "start"))):
        if name.startswith("pure"):
            assert text != source, f"{name} rewrite left the fixture unchanged"
        root = tmp_path / name
        files, inputs = _effect_files(root, text)
        authority, snapshot = _complete_effects(files, inputs, monkeypatch)
        observations.append(_effect_observation(root, authority, snapshot))
    # Compare these lexical effects/requests, never arbitrary full-program digests.
    assert observations[0] == observations[1] == observations[2] == observations[3]


def _package_cli(root, package, *args):
    return subprocess.run([sys.executable, "-m", "orchestrator", *args], cwd=root,
        env={**os.environ, "PYTHONPATH": str(package), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True)


def test_public_effect_replay_survives_workspace_and_package_relocation(tmp_path, monkeypatch):
    root = tmp_path / "original"
    files, inputs = _effect_files(root, _arms_source())
    authority, snapshot = _complete_effects(files, inputs, monkeypatch)
    observation = _effect_observation(root, authority, snapshot)
    run_id = authority.header["run_id"]
    monkeypatch.chdir(tmp_path)
    moved = tmp_path / "moved"
    root.rename(moved)
    _readonly_resume(moved, run_id)
    package = tmp_path / "copied-package"
    shutil.copytree(Path(__file__).parents[1] / "orchestrator", package / "orchestrator")
    origin = subprocess.run([sys.executable, "-c", "import orchestrator; print(orchestrator.__file__)"],
        cwd=moved, env={**os.environ, "PYTHONPATH": str(package), "PYTHONDONTWRITEBYTECODE": "1"},
        capture_output=True, text=True, check=True)
    assert Path(origin.stdout.strip()) == package / "orchestrator" / "__init__.py"
    (moved / "relocated-import-origin.txt").write_text(origin.stdout)
    moved_files = {key: moved / path.relative_to(root) for key, path in files.items()}
    compiled = _compile(moved_files, package_root=package)
    assert compiled.returncode == 0, compiled.stderr
    _readonly_resume(moved, run_id, package=package)
    relocated, after = checked_run(moved)
    assert [{field: entry.data[field] for field in observation["commits"][0]}
            for entry in after.active_commits.values()] == observation["commits"]
    assert load_evaluated_view(relocated.run_root)["workflow_outputs"] == 10


def test_public_semantic_change_refuses_without_repeating_effects(tmp_path, monkeypatch):
    files, inputs = _effect_files(tmp_path, _arms_source())
    authority, _snapshot = _complete_effects(files, inputs, monkeypatch)
    files["source"].write_text(files["source"].read_text().replace(
        "(variant Turn FIRST :n 1)", "(variant Turn FIRST :n 9)", 1))
    before = _orchestrate_snapshot(tmp_path)
    requests = (tmp_path / "requests.jsonl").read_bytes()
    refused = _resume_cli(tmp_path, authority.header["run_id"])
    assert refused.returncode == 2, refused.stderr
    assert "resume_program_changed" in refused.stderr
    assert _orchestrate_snapshot(tmp_path) == before
    assert (tmp_path / "requests.jsonl").read_bytes() == requests


MACRO_SOURCE = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
  (defmodule macro/entry) (export run) (defrecord Box (n Int))
  (defworkflow-alias run ((tmp Int)) Int
    (let* ((got (command-result fetch :argv ("python" "probe.py" "fetch" tmp) :returns Box)))
      got.n))
  (defmacro defworkflow-alias (name params return_type &body body)
    (defworkflow name params -> return_type
      (let* ((tmp 99)) (splice body)))))'''


def _macro_observation(root, authority, snapshot, source):
    (entry,) = snapshot.active_commits.values()
    assert len(snapshot.latest_starts) == 1
    assert entry.data["value"] == {"n": 7}
    assert_commit_bytes(authority, entry)
    (request,) = [json.loads(line) for line in (root / "requests.jsonl").read_text().splitlines()]
    assert request["argv"] == ["fetch", "7"]
    program = ClosedProgram.from_artifact(authority.program_path.read_text())
    (effect,) = [node for node in _walk_nodes(program.tree) if node.get("k") == "perform"]
    annotation = effect["@"]
    line = source[:source.index("command-result")].count("\n") + 1
    assert annotation["span"].startswith(str(root / "macro" / "entry.orc") + ":" + str(line) + ":")
    assert annotation["form"] == ["workflow-lisp", "defworkflow", "run"]
    assert set(annotation) == {"span", "form"}
    return {field: entry.data[field] for field in ("identity", "input_parts", "input_digest", "value", "depends_on")}


def test_public_caller_macro_splice_keeps_hygiene_effect_identity_and_provenance(tmp_path, monkeypatch):
    observations = []
    for name, source in (("base", MACRO_SOURCE), ("formatted", "\n; formatting only\n" + MACRO_SOURCE)):
        root = tmp_path / name
        files, inputs = _effect_files(root, source)
        inputs.write_text('{"tmp":7}')
        authority, snapshot = _complete_effects(files, inputs, monkeypatch, expected=7)
        observations.append(_macro_observation(root, authority, snapshot, source))
    assert observations[0] == observations[1]


def _hidden_macro_files(root, kind):
    fixtures = Path(__file__).parent / "fixtures/workflow_lisp"
    files, _inputs = _effect_files(root, _arms_source())
    files["providers"].write_text(json.dumps({"providers.execute": "codex"}))
    files["prompts"].write_text(json.dumps({"prompts.implementation.execute": {"asset_file": "prompt.md"}}))
    (root / "prompt.md").write_text(json.dumps({"owner": "macro-negative"}))
    if kind == "imported":
        shutil.copytree(fixtures / "modules/valid/import_macro/neurips", root / "neurips")
        files["source"] = root / "neurips/entry.orc"
        files["source"].write_text(files["source"].read_text().replace('"2.14"', '"2.35"'))
        return files, "generated", "neurips/macros.orc"
    if kind == "command":
        source = (fixtures / "invalid/macro_hidden_command_effect.orc").read_text().replace('"2.14"', '"2.35"')
        source = source.replace('(:target-dsl "2.35")', '(:target-dsl "2.35") (defmodule main) (export command_checks)')
        files["commands"].write_text(json.dumps({"run_checks": {"kind": "external_tool",
            "stable_command": ["python", "probe.py"], "closure": ["probe.py"]}}))
        entry = "command_checks"
    else:
        source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
          (defmodule main) (export generated) (defrecord ImplementationSummary (report String))
          (emit-provider-workflow generated)
          (defmacro emit-provider-workflow (name)
            (defworkflow name ((report String)) -> ImplementationSummary
              (provider-result providers.execute :prompt prompts.implementation.execute
                :inputs (report) :returns ImplementationSummary))))'''
        entry = "generated"
    files["source"] = root / "main.orc"
    files["source"].write_text(source)
    return files, entry, "main.orc"


@pytest.mark.parametrize("kind", ("command", "provider", "imported"))
def test_public_hidden_macro_effects_keep_required_source_refusal(tmp_path, kind):
    files, entry, origin = _hidden_macro_files(tmp_path, kind)
    result = _compile(files, extra=("--entry-workflow", entry))
    (tmp_path / "compile.stdout").write_text(result.stdout)
    (tmp_path / "compile.stderr").write_text(result.stderr)
    (tmp_path / "compile.argv.json").write_text(json.dumps(result.args))
    assert result.returncode != 0
    assert "macro_hidden_effect" in result.stderr
    assert origin in result.stderr
    assert "required_lint" in result.stderr
    assert not (tmp_path / "requests.jsonl").exists()
    assert not (tmp_path / ".orchestrate/runs").exists()
