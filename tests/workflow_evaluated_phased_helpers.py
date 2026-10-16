"""Checked phased requests and local provider fixtures, without paid providers."""

from orchestrator.workflow.evaluated.machine import evaluate_closed_program
from orchestrator.workflow.evaluated.values import coerce_evaluated_value
from tests.test_workflow_lisp_phased_239 import _compile


def local_executor(workspace, *, command=("local-provider", "${PROMPT}")):
    from orchestrator.providers import ProviderRegistry, ProviderTemplate, InteractiveSessionSupport, InputMode
    from orchestrator.providers.executor import ProviderExecutor
    registry = ProviderRegistry()
    registry.register(ProviderTemplate(name="test-provider", command=list(command), input_mode=InputMode.ARGV,
        interactive_session_support=InteractiveSessionSupport(
            schema_version="interactive_terminal_turn_queue.v1", turn_boundary_messages=True,
            command=command, message_submit_keys=("ENTER",), graceful_close_text="/exit",
            graceful_close_submit_keys=("ENTER",))))
    return ProviderExecutor(workspace, registry)


def external_attempt(tmp_path, *, attempts=2, timeout=60, policy="", typed_artifact=False):
    from types import SimpleNamespace
    from orchestrator.workflow.evaluated.providers import resolve_provider_input
    from orchestrator.workflow.workspace_files import WorkspaceFiles
    node, operands, identity, reader = checked_request(tmp_path, attempts=attempts, timeout=timeout,
        policy=policy, typed_artifact=typed_artifact)
    workspace_files = WorkspaceFiles(tmp_path)
    attempt_files = workspace_files.mkdir_exclusive(".orchestrate/run/attempt-000001")
    result_path = "attempt-000001/result.json"
    resolved = resolve_provider_input(node, operands, workspace=tmp_path, reader=reader,
        result_path=str(attempt_files.workspace / "result.json"), delivery_name="file/1")
    return SimpleNamespace(node=node, identity=identity, ordinal=1, result_path=result_path,
        input_digest="sha256:" + "a" * 64, resolved=resolved, workspace=tmp_path,
        workspace_files=workspace_files, attempt_files=attempt_files, launch_cwd=None,
        provider_executor=local_executor(tmp_path),
        authority=SimpleNamespace(run_root=tmp_path / ".orchestrate/run",
            header={"run_id": "evaluated-local-run", "workflow_file": "main.orc"}))


def local_terminal_provider(tmp_path, *, reject_first=False, always_invalid=False, early_exit=False, typed_artifact=False):
    import sys
    from pathlib import Path
    script = tmp_path / "local-terminal.py"
    script.write_text('''import json, os, sys
from pathlib import Path
sys.path.insert(0, REPO)
from orchestrator.workflow.provider_phased_delivery.protocol import submit_materialization
with Path("task-starts").open("a") as stream:
    stream.write(str(os.getpid()) + "\\n")
if EARLY:
    raise SystemExit(0)
ordinal = 0
for line in sys.stdin:
    if line.strip() == "/exit":
        break
    try:
        frame = json.loads(line)
    except (ValueError, TypeError):
        continue
    if not isinstance(frame, dict) or frame.get("phase") not in {"initial_materialization", "retry_materialization"}:
        continue
    ordinal += 1
    output = Path("outputs/report.md")
    bundle = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    if output.exists() or bundle.exists():
        raise RuntimeError("candidate set was not reset")
    invalid = ALWAYS or (REJECT and ordinal == 1)
    if not invalid:
        output.write_bytes("salida ñ\\r\\n".encode())
    value = {"approved": True, **({"document": "docs/note.md"} if DOCUMENT else {})}
    bundle.write_bytes(b"invalid" if invalid else json.dumps(value).encode() + b"\\n")
    receipt = submit_materialization(request_id="local-" + str(ordinal))
    with Path("receipts.jsonl").open("a") as stream:
        stream.write(json.dumps({"status": receipt.status, "pid": os.getpid()}) + "\\n")
    if receipt.status == "failed":
        raise SystemExit(1)
'''.replace("REPO", repr(str(Path(__file__).resolve().parents[1])))
        .replace("REJECT", repr(reject_first)).replace("ALWAYS", repr(always_invalid))
        .replace("EARLY", repr(early_exit)).replace("DOCUMENT", repr(typed_artifact)))
    return local_executor(tmp_path, command=(sys.executable, "-u", str(script), "${PROMPT}"))


def checked_request(tmp_path, *, task="Tarea ñ\n", attempts=2, timeout=60, policy="", typed_artifact=False):
    source = f'''(workflow-lisp (:language "0.1") (:target-dsl "2.39")
      (defmodule phased239) (export run)
      (defpath Note :kind relpath :under "docs" :must-exist true)
      (defpath Report :kind relpath :under "outputs" :must-exist false)
      (defrecord Review (approved Bool) {"(document Note)" if typed_artifact else ""})
      (defprompt review (:fills (subject :text) (note :doc) (report :path :out Report))
        -> Review "{{subject}} {{report}}")
      (defworkflow run ((subject String) (note Note) (report Report)) -> Review
        (provider-result providers.review :prompt (review :subject subject :note note :report report)
          :delivery :phased :materialization-attempts {attempts} :timeout-sec {timeout} {policy})))'''
    (tmp_path / "docs").mkdir(exist_ok=True)
    (tmp_path / "docs/note.md").write_bytes("capturada ñ\r\n".encode())
    program = _compile(tmp_path / "phased239.orc", source)
    captured = []

    def handle(node, operands, identity, owner, reader):
        captured.append((node, operands, identity, reader))
        return coerce_evaluated_value({"approved": True,
            **({"document": "docs/note.md"} if typed_artifact else {})}, node["result"])

    evaluate_closed_program(program, {"subject": task, "note": "docs/note.md",
        "report": "outputs/report.md"}, effect_handler=handle)
    return captured[0]
