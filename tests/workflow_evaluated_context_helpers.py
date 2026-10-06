"""Public context fixtures using the existing compile, run and recovery seams."""

import json
import sys
from unittest.mock import patch

from orchestrator.cli.commands.run import run_workflow
from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow_lisp.closed.program import ClosedProgram
from tests.test_workflow_evaluated_providers import _orchestrate_snapshot
from tests.test_workflow_evaluated_resume import _resume_cli
from tests.workflow_evaluated_totality_helpers import (
    checked_run, compile_public,
)
from tests.workflow_lisp_closed_program_helpers import install
from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv
from tests.test_workflow_evaluated_cli import _run_cli


def pure_files(root, source, inputs):
    source_path = install(root, source)
    files = {"workspace": root, "source": source_path, "source_root": root}
    for field in ("providers", "prompts", "commands"):
        path = root / (field + ".json")
        path.write_text("{}")
        files[field] = path
    input_file = root / "inputs.json"
    input_file.write_text(json.dumps(inputs))
    return files, input_file


def assert_pure_public(files, input_file, expected, monkeypatch):
    root = files["workspace"]
    compile_public(files)
    monkeypatch.chdir(root)
    run = public_context_run(files, input_file)
    assert run.exit_code == 0
    authority, snapshot = checked_run(root)
    assert snapshot.terminal.data["value"] == expected
    assert not snapshot.latest_starts
    assert_completed_resumes(root, run.run_id)
    for source in root.rglob("*.orc"):
        source.unlink()
    program = ClosedProgram.from_artifact(authority.program_path.read_text())
    result = evaluate_closed_program(program, authority.header["bound_inputs"], run_id=run.run_id)
    assert result.json_value() == expected
    assert not result.dependencies
    return program, result


def public_context_run(files, input_file=None, state_dir=None):
    args = _run_args(files, input_file=input_file)
    args.emit_debug_yaml = False
    args.command_boundaries_file = str(files["commands"])
    args.state_dir = state_dir
    argv = [value for value in _run_argv(files) if value != "--emit-debug-yaml"]
    argv += ["--command-boundaries-file", str(files["commands"])]
    if input_file is not None:
        argv += ["--input-file", str(input_file)]
    if state_dir is not None:
        argv += ["--state-dir", state_dir]
    if "imports" in files:
        args.imported_workflow_bundles_file = str(files["imports"])
        argv += ["--imported-workflow-bundles-file", str(files["imports"])]
    with patch.object(sys, "argv", argv):
        return run_workflow(args)


def public_entry_cli(files, input_file):
    compile_public(files)
    root = files["workspace"]
    run = _run_cli(root, str(files["source"]), "--source-root", str(files["source_root"]),
                   "--entry-workflow", "entry", "--input-file", str(input_file),
                   "--command-boundaries-file", str(files["commands"]))
    (root / "run.stdout").write_text(run.stdout)
    (root / "run.stderr").write_text(run.stderr)
    (root / "run.argv.json").write_text(json.dumps(run.args))
    assert run.returncode == 0, run.stderr
    authority, snapshot = checked_run(root)
    assert_completed_resumes(root, authority.header["run_id"])
    return authority, snapshot


def assert_completed_resumes(root, run_id):
    before = _orchestrate_snapshot(root)
    for _ in range(2):
        resumed = _resume_cli(root, run_id)
        assert resumed.returncode == 0, resumed.stderr
        assert _orchestrate_snapshot(root) == before


def pause_context(files, monkeypatch, input_file=None):
    from tests import workflow_evaluated_totality_helpers as totality

    with monkeypatch.context() as adapted:
        adapted.setattr(totality, "public_run", public_context_run)
        return totality.pause_public(files, adapted, input_file)


def legacy_carried_context(root, source, inputs, run_id):
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor
    from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
    from orchestrator.workflow.signatures import bind_workflow_inputs
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from tests.workflow_bundle_helpers import bundle_context_dict

    path = install(root, source.replace('"2.35"', '"2.34"'))
    bundle = compile_stage3_entrypoint(path, entry_workflow="entry", source_roots=(root,),
        validate_shared=True, workspace_root=root).validated_bundles_by_name["context_probe::entry"]
    contracts = {name: contract for name, contract in workflow_runtime_input_contracts(bundle).items()
                 if not name.startswith("__write_root__")}
    state = StateManager(workspace=root, run_id=run_id)
    state.initialize(str(path), context=bundle_context_dict(bundle),
                     bound_inputs=bind_workflow_inputs(contracts, inputs, root))
    outcome = WorkflowExecutor(bundle, root, state, retry_delay_ms=0).execute(on_error="stop")
    assert outcome["status"] == "completed"
    return {name: outcome["workflow_outputs"]["return__" + name] for name in (
        "run-id", "run-state", "run-artifacts", "phase", "state", "artifacts", "payload")}


def prepare_public_producers(root):
    from tests.test_workflow_evaluated_public_context import _provider_files

    source = '''(workflow-lisp (:language "0.1") (:target-dsl "2.35")
      (defmodule main) (export run) (defrecord Result (left Int) (right Int))
      (defworkflow run () -> Result
        (let* ((a (call left :n 5)) (b (call right :n 7)))
          (record Result :left a :right b))))'''
    files, inputs = _provider_files(root, source)
    inputs.write_text("{}")
    imports = {}
    for side, increment, effort in (("left", 1, "low"), ("right", 2, "high")):
        producer = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.34")
          (defmodule {side}/entry) (export get)
          (defworkflow get ((n Int)) -> Int
            (let* ((command-value (command-result shared
                     :argv ("python" "{side}.py" n) :returns Int))
                   (provider-value (provider-result provider :prompt prompt :inputs (command-value)
                     :model "{side}-model" :effort "{effort}" :returns Int)))
              (+ command-value provider-value))))'''
        path = install(root, producer)
        path.with_name("prompt.md").write_text(json.dumps({"owner": side, "increment": increment}))
        (root / (side + ".py")).write_text(f'''import json, os, sys
from pathlib import Path
n = int(sys.argv[1])
with open("commands.log", "a") as log:
    log.write(json.dumps(["{side}", n]) + "\\n")
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps(n + {increment}))
''')
        imports[side] = {"kind": "compiled", "path": path.relative_to(root).as_posix()}
    files["imports"] = root / "imports.json"
    files["imports"].write_text(json.dumps(imports))
    files["providers"].write_text(json.dumps({"provider": "codex"}))
    files["prompts"].write_text(json.dumps({"prompt": {"asset_file": "prompt.md"}}))
    files["commands"].write_text(json.dumps({"shared": {"kind": "external_tool",
        "stable_command": ["python"], "closure": ["left.py", "right.py"]}}))
    return files, inputs


def assert_public_producer_commits(root, authority, snapshot):
    import hashlib
    from tests.workflow_evaluated_totality_helpers import assert_commit_bytes

    rows = [entry.data for entry in snapshot.active_commits.values()]
    assert [row["effect_class"] for row in rows] == ["command", "provider", "command", "provider"]
    assert [row["value"] for row in rows] == [6, 11, 9, 13]
    assert [row["depends_on"] for row in rows] == [[], [rows[0]["identity"]], [], [rows[2]["identity"]]]
    assert (root / "commands.log").read_bytes() == b'["left", 5]\n["right", 7]\n'
    for side, row in zip(("left", "right"), (rows[1], rows[3]), strict=True):
        digest = "sha256:" + hashlib.sha256((root / side / "prompt.md").read_bytes()).hexdigest()
        assert row["input_parts"]["source:asset_file:prompt.md"] == digest
    for entry in snapshot.active_commits.values():
        assert_commit_bytes(authority, entry)


def assert_public_producer_requests(root, authority, snapshot):
    from tests.test_workflow_evaluated_providers import _requests

    requests = _requests(root)
    assert len(requests) == 2
    providers = [entry for entry in snapshot.active_commits.values() if entry.data["effect_class"] == "provider"]
    expected = (("left", 1, 6, "low"), ("right", 2, 9, "high"))
    for entry, request, (side, increment, operand, effort) in zip(providers, requests, expected, strict=True):
        argv = ["exec", "--model", side + "-model", "--config", "model_reasoning_effort=" + effort,
                "--dangerously-bypass-approvals-and-sandbox"]
        assert_selected_request(root, authority, entry, request,
                                {"owner": side, "increment": increment}, operand, argv)


def assert_selected_request(root, authority, entry, request, source_payload, operand, argv):
    import hashlib
    import os
    from tests.test_workflow_evaluated_providers import _assert_attempt_evidence, workspace_relative

    row = entry.data
    bundle = request["env"]["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]
    assert request["argv"] == argv
    assert request["cwd"] == str(root)
    assert os.path.isabs(bundle)
    assert {**request["env"], "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": workspace_relative(bundle, root)} == {
        "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": (authority.run_root / row["result_path"]).relative_to(root).as_posix(),
        "ORCHESTRATOR_PROVIDER_ATTEMPT_SITE_KEY": "sha256:" + hashlib.sha256(row["identity"].encode()).hexdigest()}
    blocks = request["prompt"].split("\n\n")
    assert json.loads(blocks[0]) == source_payload
    assert json.loads(blocks[1].splitlines()[-1]) == operand
    assert row["input_parts"]["prompt"] == "sha256:" + hashlib.sha256(request["prompt"].encode()).hexdigest()
    _assert_attempt_evidence(authority.run_root, row, request)


def prepare_library_producers(root):
    """Independent in-memory maps; these have no reconstructing CLI manifest."""
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from orchestrator.workflow_lisp.closed.frontend import compile_typed_program
    from orchestrator.workflow_lisp.closed.build import Builder, build_closed_program
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding, PromptExtern

    files, _ = prepare_public_producers(root)
    imports = {}
    for side, provider in (("left", "codex"), ("right", "codex_unrestricted_workspace")):
        path = root / side / "entry.orc"
        compiled = compile_stage3_entrypoint(path, entry_workflow="get", source_roots=(root,),
            validate_shared=True, workspace_root=root,
            command_boundaries={"shared": ExternalToolBinding(name="shared",
                stable_command=("python", side + ".py"), closure=(side + ".py",))},
            provider_externs={"provider": provider},
            prompt_externs={"prompt": PromptExtern(name="prompt", asset_file="prompt.md")})
        imports[side] = compiled.validated_bundles_by_name[side + "/entry::get"]
    (root / "consumer.py").write_text('from pathlib import Path\nPath("consumer-dispatched").touch()\nraise RuntimeError("unused consumer")\n')
    sentinel = root / "bin" / "claude"
    sentinel.write_text('#!' + sys.executable + '\nfrom pathlib import Path\nPath("consumer-provider-dispatched").touch()\nraise RuntimeError("unused consumer provider")\n')
    sentinel.chmod(0o700)
    typed = compile_typed_program(files["source"], entry_workflow="run", source_roots=(root,),
        workspace_root=root, imported_workflow_bundles=imports,
        command_boundaries={"shared": ExternalToolBinding(name="shared",
            stable_command=("python", "consumer.py"), closure=("consumer.py",))},
        provider_externs={"provider": "claude"},
        prompt_externs={"prompt": PromptExtern(name="prompt", asset_file="prompt.md")})
    builder = Builder(typed)
    closed = build_closed_program(typed, builder=builder)
    program = ClosedProgram.from_artifact(closed.artifact())
    for field in ("providers", "prompts", "commands", "imports"):
        files[field].unlink()
    return files["source"], program, builder.provider_io.bind(program)


def assert_library_configuration(program):
    configurations = program.tree["configuration"]
    expected = {"left/entry": "codex", "right/entry": "codex_unrestricted_workspace"}
    for definition in program.tree["definitions"].values():
        owner = definition["key"][0]
        configuration = configurations["imports"][definition["configuration"]]
        side = owner.split("/")[0]
        assert configuration["commands"]["shared"]["stable_command"] == ["python", side + ".py"]
        assert configuration["commands"]["shared"]["closure"] == [{"base": "workspace", "path": side + ".py"}]
        assert configuration["providers"]["provider"]["provider_id"] == expected[owner]
    assert configurations["providers"]["provider"]["provider_id"] == "claude"
    assert configurations["commands"]["shared"]["stable_command"] == ["python", "consumer.py"]


def pause_library_fourth(root, authority, io, monkeypatch):
    import pytest
    from orchestrator.workflow.evaluated import runtime
    from tests.test_workflow_evaluated_command_lifecycle import _InterruptedRun

    original = runtime.append_record
    commits = []

    def after_commit(path, record, **kwargs):
        entry = original(path, record, **kwargs)
        if record["record"] == "committed":
            commits.append(entry)
            if len(commits) == 4:
                raise _InterruptedRun()
        return entry

    with monkeypatch.context() as patched:
        patched.setattr(runtime, "append_record", after_commit)
        with pytest.raises(_InterruptedRun):
            runtime.execute_pure_run(authority, {}, run_id=authority.header["run_id"],
                                     workspace=root, provider_io=io)
    return commits


def assert_library_requests(root, authority, snapshot):
    from tests.test_workflow_evaluated_providers import _requests

    requests = _requests(root)
    assert len(requests) == 2
    providers = [entry for entry in snapshot.active_commits.values() if entry.data["effect_class"] == "provider"]
    assert_selected_request(root, authority, providers[0], requests[0], {"owner": "left", "increment": 1}, 6,
        ["exec", "--model", "left-model", "--config", "model_reasoning_effort=low", "--dangerously-bypass-approvals-and-sandbox"])
    assert_selected_request(root, authority, providers[1], requests[1], {"owner": "right", "increment": 2}, 9,
        ["exec", "--dangerously-bypass-approvals-and-sandbox", "--skip-git-repo-check",
         "--model", "right-model", "--config", "model_reasoning_effort=high"])


def assert_library_command_inventory(root, snapshot):
    from hashlib import sha256
    from orchestrator.workflow.run_ref.contracts import canonical_sha256

    commands = [entry.data for entry in snapshot.active_commits.values() if entry.data["effect_class"] == "command"]
    for side, row in zip(("left", "right"), commands, strict=True):
        filename = side + ".py"
        fact = {"kind": "file", "digest": "sha256:" + sha256((root / filename).read_bytes()).hexdigest()}
        expected = {json.dumps(["workspace", filename, ordinal], separators=(",", ":")): fact for ordinal in (1, None)}
        assert row["implementation_files"] == expected
        assert row["input_parts"]["implementation_files"] == canonical_sha256(expected)


def assert_library_replays(root, authority, io, prefix):
    from orchestrator.workflow.evaluated import runtime
    from orchestrator.workflow.evaluated.views import load_evaluated_view

    requests = (root / "requests.jsonl").read_bytes()
    command_log = (root / "commands.log").read_bytes()
    expected = {"left": 17, "right": 22}
    assert runtime.execute_pure_resume(authority, {}, run_id=authority.header["run_id"], workspace=root,
                                       provider_io=io) == (0, expected)
    assert authority.memo_path.read_bytes().startswith(prefix)
    assert load_evaluated_view(authority.run_root)["workflow_outputs"] == expected
    before = _orchestrate_snapshot(root)
    assert runtime.execute_pure_resume(authority, {}, run_id=authority.header["run_id"], workspace=root,
                                       provider_io=io) == (0, expected)
    assert _orchestrate_snapshot(root) == before
    assert (root / "requests.jsonl").read_bytes() == requests
    assert (root / "commands.log").read_bytes() == command_log
    assert not (root / "consumer-dispatched").exists()
    assert not (root / "consumer-provider-dispatched").exists()


def prepare_phase_provider(root, source, inputs):
    from tests.test_workflow_evaluated_public_context import _provider_files

    files, input_file = _provider_files(root, source)
    files["providers"].write_text(json.dumps({"providers.execute": "codex"}))
    files["prompts"].write_text(json.dumps({"prompts.implementation.execute": {"asset_file": "prompt.md"}}))
    (root / "prompt.md").write_text(json.dumps({"phase": "implementation"}))
    input_file.write_text(json.dumps(inputs))
    for relative in ("docs/design/design.md", "docs/plans/plan.md", "artifacts/work/runtime-execution-report.md"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("evidence\n")
    return files, input_file


def legacy_phase_provider(files, inputs):
    from orchestrator.state import StateManager
    from orchestrator.workflow.executor import WorkflowExecutor
    from orchestrator.workflow.loaded_bundle import workflow_runtime_input_contracts
    from orchestrator.workflow.signatures import bind_workflow_inputs
    from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
    from tests.workflow_bundle_helpers import bundle_context_dict

    root = files["workspace"]
    bundle = compile_stage3_entrypoint(files["source"], entry_workflow="run", source_roots=(root,),
        provider_externs={"providers.execute": "codex"},
        prompt_externs={"prompts.implementation.execute": "prompt.md"},
        validate_shared=True, workspace_root=root).validated_bundles_by_name["main::run"]
    contracts = {name: contract for name, contract in workflow_runtime_input_contracts(bundle).items()
                 if not name.startswith("__write_root__")}
    flattened = {outer + "__" + name: value for outer, record in inputs.items() for name, value in record.items()}
    state = StateManager(workspace=root, run_id="old-named-x3")
    state.initialize(str(files["source"]), context=bundle_context_dict(bundle),
                     bound_inputs=bind_workflow_inputs(contracts, flattened, root))
    outcome = WorkflowExecutor(bundle, root, state, retry_delay_ms=0).execute(on_error="stop")
    assert outcome["status"] == "completed"
    return {name: outcome["workflow_outputs"]["return__" + name] for name in (
        "implementation_state", "implementation_state_bundle_path")}


def assert_generic_hook_run(root, authority, snapshot, owner):
    from tests.workflow_evaluated_totality_helpers import assert_commit_bytes

    commits = list(snapshot.active_commits.values())
    assert [entry.data["value"] for entry in commits] == [11, "typed"]
    assert [entry.data["depends_on"] for entry in commits] == [[], []]
    assert snapshot.terminal.data["value"] == "typed"
    for entry in commits:
        assert_commit_bytes(authority, entry)
    assert_completed_resumes(root, authority.header["run_id"])
    assert (root / "hooks.log").read_bytes() == b"integer\ntext\n"
    for path in root.rglob("*.orc"):
        path.unlink()
    program = ClosedProgram.from_artifact(authority.program_path.read_text())
    assert_generic_hook_owner(program, owner)


def assert_generic_hook_owner(program, owner):
    rows = [row for row in program.tree["definitions"].values() if row["key"][:3] == [owner, "procedure", "apply"]]
    assert {row["result"]["name"] for row in rows} == {"Int", "String"}
