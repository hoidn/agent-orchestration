"""Spike of evaluated execution, iteration 3, item E: the second decisive experiment.

Throwaway. One program, `decisive.orc`, holds what review 2 asked for together:

- a command whose declared program is a wrapper (`wrapper.py`) that runs a second script
  (`payload.py`), built under `strict` (the default) with the closure `["payload.py"]`;
- a called workflow (`review`) holding a provider;
- a run reference compiled from the source (path mode), whose input is the provider's
  score and whose value feeds the last command.

The stand-ins answer from what they are sent: the provider from the typed prompt inputs
and a case's multiplier; the child run from its resolved input (three times the seed). The
run-ref runtime runs unchanged with the runtime tests' materializer and a launcher that
logs each child run.

1. Both routes run the program in process. Their provider and command requests are compared
   as sent, each differing field checked against item F's rule; the run-ref child launches
   are compared field by field, each differing field named with each route's value.
2. The spike runs in a child process killed by SIGKILL at every window of the command and
   provider effects and at the run reference's two gaps (after its pending commit; after
   the memo's commit), then resumed; every resume gives the uninterrupted value, and the
   child runs are counted.
3. After the wrapper's second script changes, a resume is refused before any launch.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

REPO = Path(__file__).resolve().parents[2]
COMMIT = "0123456789abcdef0123456789abcdef01234567"
WINDOWS = ("resolved", "during", "finished", "committed")
CASES = {"low": ("warmup", 2, 4), "high": ("a longer topic", 5, 7)}  # topic, the provider's multiplier, seed
SOURCE = """(workflow-lisp
  (:language "0.1")
  (:target-dsl "2.33")
  (defmodule spk/decisive)
  (export run)
  (defrecord Box (n Int))
  (defrecord Review (score Int) (notes String))
  (defrecord Outcome (fetched Int) (score Int) (child Int) (launched Int))
  (defproc fetch ((n Int)) -> Box
    :effects ((uses-command fetch))
    :lowering inline
    (command-result fetch :argv ("python" "wrapper.py" "fetch" n) :returns Box))
  (defworkflow review ((topic String) (seed Int)) -> Review
    (provider-result providers.review :prompt prompts.review :inputs (topic seed) :returns Review))
  (defworkflow run ((topic String) (seed Int)) -> Outcome
    (let* ((a (fetch 1))
           (r (call review :topic topic :seed a.n))
           (child (run-ref
                    :source (:repo "REPO" :commit "COMMIT")
                    :program (:path "candidate.orc" :entry run)
                    :inputs (:seed CHILD_SEED)
                    :returns Int
                    :policy (:environment :deterministic-effect-free :setup ())))
           (b (fetch LAST)))
      (record Outcome :fetched a.n :score r.score :child child.value :launched b.n))))
"""
WRAPPER = 'import runpy\nrunpy.run_path("payload.py", run_name="__main__")\n'
PAYLOAD = """import json, os, sys, time
from pathlib import Path
n = int(sys.argv[-1])
with open("commands.log", "a", encoding="utf-8") as log:
    log.write(f"fetch {n}\\n")
if Path("hold").exists():
    Path("marker").write_text("during", encoding="utf-8")
    while True:
        time.sleep(0.05)
Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"]).write_text(json.dumps({"n": n}), encoding="utf-8")
"""


# The program as review 2 asks for it: the run reference reads the provider's score and the last command reads
# both. The flat route refuses both forms (`run_ref_input_binding_invalid`, `workflow_return_not_exportable`); it
# accepts the program with the workflow input `seed` in both places, the largest part it runs.
FULL = {"CHILD_SEED": "r.score", "LAST": "(+ r.score child.value)"}
ACCEPTED = {"CHILD_SEED": "seed", "LAST": "seed"}


def source(form: dict, repo: Path) -> str:
    text = SOURCE.replace("REPO", str(repo)).replace("COMMIT", COMMIT)
    for key, value in form.items():
        text = text.replace(key, value)
    return text


def expected_value(case: str, form: dict = FULL) -> dict:
    topic, multiplier, seed = CASES[case]
    score = multiplier + len(topic)  # the provider sees the seed 1 (the first command's value)
    child = 3 * (score if form is FULL else seed)
    return {"fetched": 1, "score": score, "child": child, "launched": score + child if form is FULL else seed}


def inputs(case: str) -> dict:
    return {"topic": CASES[case][0], "seed": CASES[case][2]}


def answer(case: str, prompt: str) -> dict:
    """The stand-in reviewer: a score from the typed prompt inputs and the case's multiplier."""

    topic = json.loads(re.search(r"## Typed Prompt Input: topic\n(.*)", prompt).group(1))
    seed = int(re.search(r"## Typed Prompt Input: seed\n(.*)", prompt).group(1))
    return {"score": seed * CASES[case][1] + len(topic), "notes": f"{case} {topic}"}


class ChildRuns:
    """The runtime tests' materializer, and a child launcher that logs each launch and answers three times
    its seed. `launches` keeps what each launch was sent."""

    def __init__(self, log: Path) -> None:
        from tests.test_workflow_run_ref_runtime import _RuntimeHarness

        self.harness, self.log, self.launches = _RuntimeHarness(), log, []

    def launch(self, launch):
        from orchestrator.workflow.run_ref.contracts import canonical_json_bytes
        from orchestrator.workflow.run_ref.runtime import RunRefChildProcessResult

        self.launches.append(launch)
        with open(self.log, "a", encoding="utf-8") as log:
            log.write(launch.child_run_id + "\n")
        outputs = {"__result__": 3 * launch.request_document["inputs"]["seed"]}
        state_dir = launch.workspace / ".orchestrate" / "runs" / launch.child_run_id
        state_dir.mkdir(parents=True)
        state = {"run_id": launch.child_run_id, "status": "completed", "workflow_outputs": outputs}
        (state_dir / "state.json").write_bytes(canonical_json_bytes(state) + b"\n")
        result = {"schema_version": "run_ref_path_child_result.v1", "status": "completed",
                  "step_config_digest": launch.request_document["expected_step_config_digest"],
                  "target_workflow_name": "run", "child_run_id": launch.child_run_id, "workflow_outputs": outputs,
                  "path_compile": {"diagnostics": {}, "program_identity": {}, "signature": {}, "effect_facts": {},
                                   "evidence": {}}}
        return RunRefChildProcessResult(returncode=0, stdout=canonical_json_bytes(result) + b"\n", stderr=b"",
                                        duration_ms=4)

    def dependencies(self):
        from orchestrator.workflow.run_ref.runtime import RunRefRuntimeDependencies

        return RunRefRuntimeDependencies(materialize_source=self.harness.materialize, launch_child=self.launch)


def install(workspace: Path, repo: Path, form: dict = FULL) -> Path:
    """The program, its wrapper and second script, its prompt and manifests; the entry's path."""

    workspace.mkdir(parents=True, exist_ok=True)
    repo.mkdir(parents=True, exist_ok=True)
    entry = workspace / "spk" / "decisive.orc"
    entry.parent.mkdir(parents=True, exist_ok=True)
    entry.write_text(source(form, repo), encoding="utf-8")
    (entry.parent / "review.md").write_text("Review the topic.\n", encoding="utf-8")
    (workspace / "wrapper.py").write_text(WRAPPER, encoding="utf-8")
    (workspace / "payload.py").write_text(PAYLOAD, encoding="utf-8")
    manifests = {"providers.json": {"providers.review": "codex"}, "prompts.json": {"prompts.review": "review.md"},
                 "commands.json": {"fetch": {"kind": "external_tool", "stable_command": ["python", "wrapper.py"]}}}
    for name, payload in manifests.items():
        (workspace / name).write_text(json.dumps(payload), encoding="utf-8")
    return entry


def build(workspace: Path, repo: Path, form: dict = FULL):
    from experiments.evaluated_execution_spike.closed import build_closed_program
    from experiments.evaluated_execution_spike.frontend import typecheck_program
    from orchestrator.workflow_lisp.workflows import ExternalToolBinding

    entry = install(workspace, repo, form)
    typed = typecheck_program(entry, entry_workflow="spk/decisive::run", source_roots=(workspace,),
                              command_boundaries={"fetch": ExternalToolBinding(name="fetch",
                                                                               stable_command=("python", "wrapper.py"))},
                              provider_externs={"providers.review": "codex"}, prompt_externs={"prompts.review": "review.md"})
    return build_closed_program(typed, closures={"fetch": ["payload.py"]})


# 1. Both routes in process ----------------------------------------------------------------------------


def flat_route(root: Path, case: str, monkeypatch: pytest.MonkeyPatch, form: dict = ACCEPTED):
    """The flat route through the public run entry: (exit code, value, provider and command requests, launches)."""

    from orchestrator.cli.commands.run import run_workflow
    from orchestrator.workflow.executor import WorkflowExecutor
    from tests.experiments.test_evaluated_execution_spike_requests import Recorder, is_generated_helper
    from tests.test_workflow_lisp_rich_loop_values_e2e import _run_args, _run_argv

    workspace = root / "flat"
    entry = install(workspace, root.parent / "repo", form)
    children = ChildRuns(root / "flat-children.log")
    monkeypatch.setattr(WorkflowExecutor, "_run_ref_runtime_dependencies", children.dependencies(), raising=False)
    recorder = Recorder({}, lambda invocation: answer(case, invocation.prompt)).install(monkeypatch)
    files = {"source": entry, "source_root": workspace, "providers": workspace / "providers.json",
             "prompts": workspace / "prompts.json", "commands": workspace / "commands.json"}
    (workspace / "inputs.json").write_text(json.dumps(inputs(case)), encoding="utf-8")
    args = _run_args(files, input_file=workspace / "inputs.json")
    args.command_boundaries_file, args.run_ref_root = str(files["commands"]), str((root / "flat-run-ref").resolve())
    args.emit_debug_yaml = False  # with a run reference, the debug YAML fails: its static configuration holds bytes
    argv = [a for a in _run_argv(files) if a != "--emit-debug-yaml"] + ["--command-boundaries-file", str(files["commands"])]
    monkeypatch.chdir(workspace)
    with patch.object(sys, "argv", argv):
        result = run_workflow(args)
    requests = [r for r in recorder.requests if not is_generated_helper(r)]
    return result.exit_code, dict(result.workflow_outputs), requests, children.launches


def spike_route(root: Path, case: str, program, monkeypatch: pytest.MonkeyPatch, form: dict = ACCEPTED):
    """The spike in process: (value, provider and command requests, child launches, where each request was)."""

    from experiments.evaluated_execution_spike.evaluator import evaluate
    from experiments.evaluated_execution_spike.memo import read_records
    from experiments.evaluated_execution_spike.run_ref import RunRefCoordinator
    from tests.experiments.test_evaluated_execution_spike import outputs
    from tests.experiments.test_evaluated_execution_spike_requests import Recorder, Where

    workspace = (root / "spike").resolve()
    install(workspace, root.parent / "repo", form)
    children = ChildRuns(root / "spike-children.log")
    recorder = Recorder({}, lambda invocation: answer(case, invocation.prompt)).install(monkeypatch)
    monkeypatch.chdir(workspace)
    run_root = workspace / "run"
    coordinator = RunRefCoordinator(workspace, run_root, (root / "spike-run-ref").resolve(), children.dependencies())
    result = evaluate(program, inputs=inputs(case), workspace=workspace, run_root=run_root,
                      coordinators={"run_ref": coordinator})
    classes = site_classes(program)
    where = [Where(r["identity"], os.path.relpath(run_root / r["result_path"], workspace), workspace, "")
             for r in read_records(run_root) if r["record"] == "started"
             and classes[re.sub(r"\[\d+\]", "[*]", r["identity"])] != "run_ref"]
    return outputs(result.value), recorder.requests, children.launches, where


def site_classes(program) -> dict[str, str]:
    return {node["site"]: node["class"] for node in perform_nodes(program)}


def launch_fields(launch) -> dict:
    """A child launch as sent, the static configuration decoded."""

    from orchestrator.workflow.run_ref.config import decode_run_ref_static_config

    document = dict(launch.request_document)
    config = decode_run_ref_static_config(base64.b64decode(document.pop("run_ref_static_config_base64"))).record
    return {"mode": launch.mode, "child_run_id": launch.child_run_id, "workspace": str(launch.workspace),
            **{f"request.{k}": v for k, v in document.items()}, **{f"config.{k}": v for k, v in config.items()}}


def launch_expectations(root: Path, case: str, program, flat_run_id: str) -> dict[str, tuple]:
    """Each field in which the routes' child launches differ, with each route's value; a field not listed must be
    equal. Rule: the runtime derives the child's run id and workspace from the visit key, whose parent run id and
    step id are the flat route's run id and step, and the spike's run root name and a digest of the identity."""

    from experiments.evaluated_execution_spike.memo import read_records
    from experiments.evaluated_execution_spike.run_ref import RunRefCoordinator
    from orchestrator.workflow.run_ref.ledger import RunRefVisitKey
    from orchestrator.workflow.run_ref.runtime import _child_run_id, _workspace_for_ordinal

    workspace = (root / "spike").resolve()
    classes = site_classes(program)
    (identity,) = [r["identity"] for r in read_records(workspace / "run") if r["record"] == "started"
                   and classes[re.sub(r"\[\d+\]", "[*]", r["identity"])] == "run_ref"]
    node = next(n for n in perform_nodes(program) if n["class"] == "run_ref")
    coordinator = RunRefCoordinator(workspace, workspace / "run", (root / "spike-run-ref").resolve())
    spike = coordinator.request(node, {"inputs": {"seed": CASES[case][2]}}, identity)
    flat = replace(spike, run_ref_root=(root / "flat-run-ref").resolve(), visit=RunRefVisitKey(
        parent_run_id=flat_run_id, execution_frame_id="root", call_frame_id=None, step_id="root.spk_decisive_run__child",
        visit_count=1))
    ids = (_child_run_id(flat, 1), _child_run_id(spike, 1))
    workspaces = (str(_workspace_for_ordinal(flat, 1)), str(_workspace_for_ordinal(spike, 1)))
    return {"child_run_id": ids, "request.child_run_id": ids, "workspace": workspaces, "request.clone_root": workspaces,
            "request.child_state_dir": tuple(f"{w}/.orchestrate/runs" for w in workspaces),
            # The materializer's record: its paths are under each route's run-ref root, the child's workspace among
            # them, and its own digest covers them; nothing else differs in it.
            "request.materialized_source": ((workspaces[0], str(flat.run_ref_root)),
                                            (workspaces[1], str(spike.run_ref_root)))}


def perform_nodes(program) -> list[dict]:
    found = []

    def walk(node):
        if isinstance(node, dict):
            found.extend([node] if node.get("k") == "perform" else [])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(program.tree)
    return found


def assert_launch_differences(flat: dict, spike: dict, expected: dict[str, tuple]) -> None:
    differing = {k for k in {*flat, *spike} if flat.get(k) != spike.get(k)}
    assert differing == set(expected), sorted(differing ^ set(expected))
    for field in differing - {"request.materialized_source"}:
        assert (flat[field], spike[field]) == expected[field], field
    def placed(record: dict, workspace: str, run_ref_root: str) -> str:
        text = json.dumps({k: v for k, v in record.items() if k != "digest"})
        return text.replace(workspace, "<workspace>").replace(run_ref_root, "<run-ref root>")

    (flat_places, spike_places) = expected["request.materialized_source"]
    assert placed(flat["request.materialized_source"], *flat_places) == placed(spike["request.materialized_source"],
                                                                                *spike_places)


def test_the_flat_route_refuses_a_run_reference_or_a_command_fed_by_an_effects_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The program as asked for, and the same with only the run reference's input taken from the workflow input:
    the flat route refuses each before it runs anything. The spike runs the program as asked for."""

    codes = {}
    for name, form in (("full", FULL), ("child-seed-from-input", {**FULL, "CHILD_SEED": "seed"})):
        caplog.clear()
        with monkeypatch.context() as local:
            code, _, requests, launches = flat_route(tmp_path / name, "low", local, form)
        codes[name] = (code, re.findall(r"\[(\w+)\]", caplog.text), len(requests), len(launches))
    with monkeypatch.context() as local:
        spike_value = spike_route(tmp_path / "spike", "low", build(tmp_path / "program", tmp_path / "repo"), local,
                                  FULL)[0]

    assert codes == {"full": (2, ["run_ref_input_binding_invalid"], 0, 0),
                     "child-seed-from-input": (2, ["workflow_return_not_exportable"], 0, 0)}
    assert spike_value == {f"return__{k}": v for k, v in expected_value("low").items()}


def test_both_routes_send_the_same_requests_apart_from_the_named_fields_for_each_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """On the largest part the flat route runs (`ACCEPTED`)."""

    from tests.experiments.test_evaluated_execution_spike_requests import assert_request_differences

    program = build(tmp_path / "program", tmp_path / "repo", ACCEPTED)
    for case in CASES:
        root = tmp_path / case
        with monkeypatch.context() as local:
            flat_code, flat_value, flat_requests, flat_launches = flat_route(root, case, local)
        with monkeypatch.context() as local:
            spike_value, spike_requests, spike_launches, where = spike_route(root, case, program, local)
        flat_run_id = next((root / "flat" / ".orchestrate" / "runs").iterdir()).name
        where = [replace(w, flat_run_id=flat_run_id) for w in where]

        expected = {f"return__{k}": v for k, v in expected_value(case, ACCEPTED).items()}
        assert (flat_code, spike_value, flat_value) == (0, expected, expected), case
        assert_request_differences(flat_requests, spike_requests, where)
        (flat_launch,), (spike_launch,) = [launch_fields(x) for x in flat_launches], [launch_fields(x) for x in spike_launches]
        assert_launch_differences(flat_launch, spike_launch, launch_expectations(root, case, program, flat_run_id))


# 2 and 3. The spike killed from outside, then a changed second script -------------------------------------


class FunctionalProvider:
    """In the child: answers by `answer`, logs each call, blocks on the hold file."""

    def __init__(self, case: str, workspace: Path) -> None:
        self.case, self.workspace = case, workspace

    def prepare_invocation(self, provider_name, *args, **kwargs):
        from tests.test_workflow_lisp_generic_union_provider_results import _Provider

        return _Provider({}).prepare_invocation(provider_name, *args, **kwargs)

    def execute(self, invocation, **kwargs):
        from tests.experiments.test_evaluated_execution_spike import in_cwd
        from tests.test_workflow_lisp_generic_union_provider_results import _Provider

        with open(self.workspace / "providers.log", "a", encoding="utf-8") as log:
            log.write("review\n")
        if (self.workspace / "hold").exists():
            (self.workspace / "marker").write_text("during", encoding="utf-8")
            while True:
                time.sleep(0.05)
        return in_cwd(_Provider(answer(self.case, invocation.prompt)).execute)(invocation, **kwargs)


def child(config_path: str) -> None:
    from experiments.evaluated_execution_spike.evaluator import EvaluationFailed, evaluate
    from experiments.evaluated_execution_spike.run_ref import RunRefCoordinator
    from experiments.evaluated_execution_spike.sites import ClosedProgram
    from orchestrator.providers.executor import ProviderExecutor

    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    workspace = Path(config["workspace"])
    provider = FunctionalProvider(config["case"], workspace)
    ProviderExecutor.prepare_invocation = provider.prepare_invocation
    ProviderExecutor.execute = provider.execute
    program = ClosedProgram.from_artifact(Path(config["program"]).read_text(encoding="utf-8"))
    children = ChildRuns(workspace / "children.log")
    coordinator = RunRefCoordinator(workspace, workspace / "run", Path(config["run_ref_root"]), children.dependencies())
    seen: Counter[str] = Counter()

    def hook(event: str, identity: str) -> None:
        seen[event] += 1
        if seen[event] != config.get("at"):
            return
        if config.get("window") == "during" and event == "started":
            (workspace / "hold").write_text("", encoding="utf-8")
        elif config.get("window") == event:
            (workspace / "marker").write_text(event, encoding="utf-8")
            while True:
                time.sleep(0.05)

    os.chdir(workspace)
    try:
        result = evaluate(program, inputs=inputs(config["case"]), workspace=workspace,
                          run_root=workspace / "run", hook=hook, coordinators={"run_ref": coordinator})
        print(json.dumps({"value": result.value}))
    except EvaluationFailed as failed:
        print(json.dumps({"refused": failed.code, "detail": failed.detail}))


def _spawn(config: dict, root: Path) -> subprocess.Popen:
    path = root / f"config-{time.monotonic_ns()}.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTHONDONTWRITEBYTECODE": "1"}
    return subprocess.Popen([sys.executable, __file__, "child", str(path)], cwd=REPO, env=env, start_new_session=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def run_child(config: dict, root: Path) -> dict:
    out, err = _spawn(config, root).communicate(timeout=120)
    assert out.strip(), err[-2000:]
    return json.loads(out.strip().splitlines()[-1])


def kill_child(config: dict, root: Path) -> None:
    process = _spawn(config, root)
    marker = Path(config["workspace"]) / "marker"
    deadline = time.monotonic() + 60
    while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker.exists(), process.communicate()[1][-2000:]
    os.killpg(process.pid, signal.SIGKILL)
    process.communicate()
    marker.unlink()
    (Path(config["workspace"]) / "hold").unlink(missing_ok=True)


def lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def launched(workspace: Path) -> dict[str, int]:
    """Launches so far: commands, provider calls, child runs."""

    return {name: len(lines(workspace / f"{name}.log")) for name in ("commands", "providers", "children")}


# The effects in order, and the kill points: every window of a command or a provider; the run reference's two gaps.
EFFECTS = ("command", "provider", "run_ref", "command")
KILLS = [(k, window) for k, kind in enumerate(EFFECTS, 1)
         for window in (("finished", "committed") if kind == "run_ref" else WINDOWS)]


def test_every_kill_resumes_to_the_uninterrupted_result_and_a_changed_second_script_is_refused(tmp_path: Path) -> None:
    from experiments.evaluated_execution_spike.memo import read_records
    from experiments.evaluated_execution_spike.sites import ClosedProgram
    from experiments.evaluated_execution_spike.view import derive_state

    template = tmp_path / "template"
    program = build(template, tmp_path / "repo")
    (tmp_path / "program.json").write_text(program.artifact(), encoding="utf-8")
    program = ClosedProgram.from_artifact(program.artifact())

    def workspace(case: str, name: str) -> dict:
        root = tmp_path / case / name
        shutil.copytree(template, root)
        return {"workspace": str(root), "program": str(tmp_path / "program.json"), "case": case,
                "run_ref_root": str((tmp_path / case / f"{name}-run-ref").resolve())}

    for case in CASES:
        (tmp_path / case).mkdir()
        once = workspace(case, "once")
        assert run_child(once, tmp_path) == {"value": expected_value(case)}, case
        assert launched(Path(once["workspace"])) == {"commands": 2, "providers": 1, "children": 1}, case

        for k, window in KILLS:
            where = f"{case}, effect {k} ({EFFECTS[k - 1]}), {window}"
            config = workspace(case, f"{k}-{window}")
            kill_child({**config, "window": window, "at": k}, tmp_path)
            resumed = run_child(config, tmp_path)
            counts, again = launched(Path(config["workspace"])), window in ("during", "finished")
            run_root = Path(config["workspace"]) / "run"
            identity = [r["identity"] for r in read_records(run_root) if r["record"] == "committed"][k - 1]

            assert resumed == {"value": expected_value(case)}, where
            assert counts == {"commands": 2 + (again and EFFECTS[k - 1] == "command"),
                              "providers": 1 + (again and EFFECTS[k - 1] == "provider"),
                              "children": 1 + (again and EFFECTS[k - 1] == "run_ref")}, where
            assert [r["attempt"] for r in read_records(run_root) if r["record"] == "started"
                    and r["identity"] == identity] == ([1, 2] if again else [1]), where
            assert derive_state(program, run_root)["status"] == "completed", where

        before = launched(Path(once["workspace"]))
        payload = Path(once["workspace"]) / "payload.py"
        payload.write_text(payload.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        refused = run_child(once, tmp_path)
        assert (refused["refused"], refused["detail"]["files"]) == ("effect_input_diverged", ["payload.py"]), case
        assert launched(Path(once["workspace"])) == before, case


if __name__ == "__main__" and sys.argv[1:2] == ["child"]:
    child(sys.argv[2])
