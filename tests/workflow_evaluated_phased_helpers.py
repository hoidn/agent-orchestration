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


# Public integration helpers retain the real CLI, built-in capability and tmux backend.
def public_case(root, *, mode="success", attempts=2):
    import os
    import shutil
    import sys
    from pathlib import Path
    assert shutil.which("tmux"), "tmux is required for public phased acceptance"
    repo = Path(__file__).resolve().parents[1]
    directory = root / "tests/fixtures/phased_239"
    directory.mkdir(parents=True)
    for source in (repo / "tests/fixtures/phased_239").iterdir():
        if source.is_file():
            shutil.copyfile(source, directory / source.name)
    source = directory / "main.orc"
    source.write_text(source.read_text().replace(":materialization-attempts 2", f":materialization-attempts {attempts}"))
    binary = root / "bin/codex"
    binary.parent.mkdir()
    binary.write_text(f"#!{sys.executable}\n" + (repo / "tests/fixtures/providers/fake_phased_interactive.py").read_text())
    binary.chmod(0o700)
    (root / "outputs").mkdir()
    env = {**os.environ, "PYTHONPATH": str(repo), "PYTHONDONTWRITEBYTECODE": "1",
        "PATH": str(binary.parent) + os.pathsep + os.environ["PATH"], "ORC_FAKE_PHASED_MODE": mode}
    assert shutil.which("codex", path=env["PATH"]) == str(binary)
    args = ["run", str(source), "--entry-workflow", "main::run", "--source-root", str(directory),
        "--provider-externs-file", str(directory / "providers.json"),
        "--command-boundaries-file", str(directory / "commands.json"),
        "--input", "subject=deterministic ñ", "--input", "report=outputs/report.md"]
    return args, env, root


def public_cli(case, args, *, env=None):
    import subprocess
    import sys
    return subprocess.run([sys.executable, "-m", "orchestrator", *args], cwd=case[2],
        env=env or case[1], capture_output=True, text=True, timeout=90, check=False)


def public_events(root):
    import json
    path = root / "phased-events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def public_run_root(root):
    (run_root,) = (root / ".orchestrate/runs").iterdir()
    return run_root


def public_snapshot(run_root):
    from orchestrator.workflow.evaluated.authority import load_run_authority
    from orchestrator.workflow.evaluated.machine import site_classes
    from orchestrator.workflow.evaluated.memo import read_memo
    authority = load_run_authority(run_root)
    return read_memo(authority.memo_path, site_classes(authority.program))


def public_tree(root):
    return {str(path.relative_to(root)): path.read_bytes() for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()}


def assert_public_completed(case, run_root, *, ordinal, processes, turns=None):
    import json
    from orchestrator.workflow.run_ref.contracts import canonical_sha256
    snapshot = public_snapshot(run_root)
    rows = [entry.data for entry in snapshot.entries]
    commits = [row for row in rows if row["record"] == "committed"]
    assert [row["effect_class"] for row in commits] == ["provider_phased", "command"]
    phased, downstream = commits
    assert phased["attempt"] == ordinal and downstream["depends_on"] == [phased["identity"]]
    assert phased["value"] == {"approved": True}
    assert phased["result_digest"] == canonical_sha256(phased["value"])
    assert phased["proof"]["natural_shutdown"] == {"disposition": "natural_exit", "return_code": 0,
        "pane_absent": True, "server_absent": True, "proof_complete": True}
    settled = [row for row in rows if row["record"] == "settled"]
    assert len(settled) == 1 and settled[0]["identity"] == phased["identity"]
    downstream_start = next(row for row in rows if row["record"] == "started" and row["identity"] == downstream["identity"])
    assert rows.index(phased) < rows.index(settled[0]) < rows.index(downstream_start)
    assert snapshot.terminal.data["outcome"] == "completed" and snapshot.terminal.data["value"] == 9
    receipt = json.loads((run_root / phased["result_path"]).with_name("phased-attempt.json").read_text())
    assert receipt == {"schema_version": "evaluated_phased_provider_attempt.v1", "state": "settled", "proof": phased["proof"]}
    events = public_events(case[2])
    starts = [row for row in events if row["event"] == "start"]
    tasks = [row for row in events if row["event"] == "task"]
    assert len(starts) == len(tasks) == processes
    assert len({row["pid"] for row in starts}) == processes
    assert [row["pid"] for row in starts] == [row["pid"] for row in tasks]
    assert starts[-1]["bundle"] == str(run_root / phased["result_path"])
    assert starts[-1]["argv"][:4] == ["--model", "bound-model", "--config", "model_reasoning_effort=low"]
    assert [row for row in events if row["event"] == "natural_exit"][-1]["pid"] == starts[-1]["pid"]
    if turns is not None:
        assert len([row for row in events if row["event"] == "submit"]) == turns
    assert (case[2] / "outputs/report.md").read_bytes() == "salida ñ\r\n".encode()
    assert (case[2] / "continuations.jsonl").read_text().splitlines() == ['{"approved": true}']
    before = public_tree(run_root), public_events(case[2])
    for _ in range(2):
        resumed = public_cli(case, ["resume", run_root.name])
        assert resumed.returncode == 0, resumed.stdout + resumed.stderr
        assert (public_tree(run_root), public_events(case[2])) == before


def assert_public_readers(case, run_root, status):
    import json
    from orchestrator.monitor.config import load_monitor_config
    from orchestrator.monitor.scanner import scan_monitor_runs
    directory = case[2] / ".public-control"
    directory.mkdir(exist_ok=True)
    config = directory / "monitor.json"
    config.write_text(json.dumps({"workspaces": [{"name": "public-phased", "path": str(case[2])}],
        "email": {"backend": "smtp", "from": "test@example.invalid", "to": ["test@example.invalid"],
            "smtp_host": "localhost"}}))
    before = public_tree(run_root), public_events(case[2])
    report = public_cli(case, ["report", "--run-id", run_root.name, "--format", "json"])
    assert report.returncode == 0, report.stdout + report.stderr
    assert json.loads(report.stdout)["run"]["status"] == status
    (monitor_run,) = scan_monitor_runs(load_monitor_config(config))
    assert monitor_run.read_error is None and monitor_run.state["status"] == status
    ledger = directory / "monitor-ledger.json"
    monitor = public_cli(case, ["monitor", "--config", str(config), "--once", "--dry-run", "--ledger", str(ledger)])
    assert monitor.returncode == 0, monitor.stdout + monitor.stderr
    assert not ledger.exists()
    assert (public_tree(run_root), public_events(case[2])) == before


_PUBLIC_KILL_LAUNCHER = r'''
import json, os, runpy, shutil, signal, stat, sys, time
from pathlib import Path
from orchestrator.workflow.evaluated import runtime, attempts, memo, phased_providers as phased
from orchestrator.workflow import workspace_files as workspace
from orchestrator.providers import interactive_terminal as terminal

cut = os.environ['ORC_PUBLIC_CUT']
marker = Path(os.environ['ORC_PUBLIC_MARKER'])
reservation = None
publishing = False
receipt_renamed = False
durability = []
marker_replace = os.replace

def pause(name):
    if cut == name and not marker.exists():
        temporary = marker.with_suffix('.tmp')
        temporary.write_text(json.dumps({'cut': name, 'pid': os.getpid(), 'durability': durability,
            'reservation': reservation.to_dict() if reservation else None}))
        marker_replace(temporary, marker)
        signal.pause()

def wait_event(kind):
    limit = time.monotonic() + 15
    while time.monotonic() < limit:
        path = Path('phased-events.jsonl')
        if path.exists() and any(json.loads(line)['event'] == kind for line in path.read_text().splitlines()):
            return
        time.sleep(.01)
    raise AssertionError('fake did not reach ' + kind)

append = memo.append_record
def append_gate(path, record, **kwargs):
    value = append(path, record, **kwargs)
    if record['record'] == 'started': pause('started')
    if record['record'] == 'committed': pause('committed')
    if record['record'] == 'settled': pause('memo-settled')
    return value
runtime.append_record = attempts.append_record = append_gate

allocate = runtime.allocate_attempt
def allocate_gate(*args, **kwargs):
    value = allocate(*args, **kwargs)
    pause('attempt-directory')
    return value
runtime.allocate_attempt = allocate_gate

mkdir = os.mkdir
def mkdir_gate(path, *args, **kwargs):
    value = mkdir(path, *args, **kwargs)
    if str(path) == 'effects': pause('effects-directory')
    parent = kwargs.get('dir_fd')
    if (len(str(path)) == 64 and str(path).isalnum() and parent is not None
            and os.readlink('/proc/self/fd/' + str(parent)).endswith('/effects')):
        pause('identity-directory')
    return value
os.mkdir = mkdir_gate

reserve = terminal.InteractiveTerminalTurnQueueAdapter.reserve_recoverable
def reserve_gate(*args, **kwargs):
    global reservation
    reservation = reserve(*args, **kwargs)
    observed = marker.with_name('_owned-reservation.json')
    temporary = observed.with_suffix('.tmp')
    temporary.write_text(json.dumps({'reservation': reservation.to_dict()}))
    marker_replace(temporary, observed)
    pause('reservation')
    return reservation
terminal.InteractiveTerminalTurnQueueAdapter.reserve_recoverable = staticmethod(reserve_gate)

write_atomic = workspace.WorkspaceFiles.write_atomic
def write_gate(self, path, content, **kwargs):
    global publishing
    initial = str(path) == 'phased-attempt.json' and json.loads(content).get('state') == 'intent'
    if initial:
        publishing = True
        pause('before-receipt')
    value = write_atomic(self, path, content, **kwargs)
    if initial: publishing = False
    return value
workspace.WorkspaceFiles.write_atomic = write_gate

copy = shutil.copyfileobj
def copy_gate(source, destination, *args, **kwargs):
    if publishing and cut == 'receipt-temp':
        destination.write(source.read(12))
        destination.flush()
        pause('receipt-temp')
    return copy(source, destination, *args, **kwargs)
shutil.copyfileobj = copy_gate

replace = os.replace
def replace_gate(source, destination, *args, **kwargs):
    global receipt_renamed
    initial = publishing and str(destination) == 'phased-attempt.json'
    if initial: pause('receipt-before-rename')
    value = replace(source, destination, *args, **kwargs)
    if initial:
        receipt_renamed = True
        durability.append('rename')
        pause('receipt-after-rename')
    return value
os.replace = replace_gate

fsync = os.fsync
def fsync_gate(fd):
    value = fsync(fd)
    if publishing:
        if stat.S_ISREG(os.fstat(fd).st_mode):
            durability.append('file-fsync')
            pause('receipt-file-fsync')
        elif receipt_renamed:
            durability.append('directory-fsync')
            pause('receipt-directory-fsync')
    return value
os.fsync = fsync_gate

start_server = terminal._TmuxInteractiveTerminalBackend.start_server
def server_gate(self, *args, **kwargs):
    assert durability == ['file-fsync', 'rename', 'directory-fsync'], durability
    pause('before-backend')
    value = start_server(self, *args, **kwargs)
    pause('after-server')
    return value
terminal._TmuxInteractiveTerminalBackend.start_server = server_gate

start = terminal.InteractiveTerminalTurnQueueAdapter.start
def start_gate(self, *args, **kwargs):
    value = start(self, *args, **kwargs)
    if cut == 'task': wait_event('task')
    pause('task')
    return value
terminal.InteractiveTerminalTurnQueueAdapter.start = start_gate

offer = terminal.InteractiveTerminalTurnQueueAdapter.offer
def offer_gate(self, *args, **kwargs):
    if cut == 'before-materialization': wait_event('task')
    pause('before-materialization')
    value = offer(self, *args, **kwargs)
    if cut == 'materialization': wait_event('candidates')
    pause('materialization')
    return value
terminal.InteractiveTerminalTurnQueueAdapter.offer = offer_gate

freeze = phased.EvaluatedPhasedBindings.freeze_candidate
def freeze_gate(self, *args, **kwargs):
    pause('before-freeze')
    value = freeze(self, *args, **kwargs)
    pause('frozen')
    return value
phased.EvaluatedPhasedBindings.freeze_candidate = freeze_gate

prepare = phased.prepare_phased_provider_attempt
def prepare_gate(*args, **kwargs):
    value = prepare(*args, **kwargs)
    pause('prepared')
    return value
phased.prepare_phased_provider_attempt = prepare_gate

settle = phased.settle_phased_provider_attempt
def settle_gate(*args, **kwargs):
    value = settle(*args, **kwargs)
    pause('receipt-settled')
    return value
phased.settle_phased_provider_attempt = settle_gate

if cut == 'absence-guard':
    def forbidden(*args, **kwargs):
        raise AssertionError('absent ownership must never reach cleanup')
    phased.recover_phased_provider_attempt = forbidden
    scandir = os.scandir
    def guarded_scan(path):
        if isinstance(path, (str, bytes, os.PathLike)) and os.fsdecode(path) == '/tmp':
            raise AssertionError('absent ownership must never scan transport root')
        return scandir(path)
    os.scandir = guarded_scan

runpy.run_module('orchestrator', run_name='__main__')
'''


def public_launcher(case, cut):
    directory = case[2] / ".public-control"
    directory.mkdir(exist_ok=True)
    launcher = directory / "kill-cli.py"
    launcher.write_text(_PUBLIC_KILL_LAUNCHER)
    marker = directory / (cut + ".json")
    env = {**case[1], "ORC_PUBLIC_CUT": cut, "ORC_PUBLIC_MARKER": str(marker)}
    if cut == "materialization":
        env["ORC_FAKE_HOLD_BEFORE_SUBMIT"] = "1"
    return launcher, marker, env


def public_kill(case, cut):
    import json
    import os
    import signal
    import subprocess
    import sys
    import time
    import pytest
    launcher, marker, env = public_launcher(case, cut)
    log = launcher.with_name(cut + ".log")
    with log.open("w") as stream:
        process = subprocess.Popen([sys.executable, str(launcher), *case[0]], cwd=case[2], env=env,
            stdout=stream, stderr=stream, start_new_session=True)
        try:
            deadline = time.monotonic() + 40
            while process.poll() is None and not marker.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            if not marker.exists():
                pytest.fail(f"public phased kill gate {cut} not reached: {log.read_text()}")
            payload = json.loads(marker.read_text())
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)
            assert process.returncode == -signal.SIGKILL
            return payload
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)


def public_resume_absence_guard(case, run_root):
    import subprocess
    import sys
    launcher, marker, env = public_launcher(case, "absence-guard")
    return subprocess.run([sys.executable, str(launcher), "resume", run_root.name], cwd=case[2], env=env,
        capture_output=True, text=True, timeout=90, check=False)


import pytest


@pytest.fixture(autouse=True)
def public_phased_cleanup(tmp_path):
    """Reap only reservations returned to this test's controller, including failed assertions."""
    yield
    import json
    import time
    from pathlib import Path
    from orchestrator.providers.interactive_terminal import InteractiveTerminalReservation, InteractiveTerminalTurnQueueAdapter
    from orchestrator.workflow.provider_phased_delivery.endpoint import PhasedSubmitEndpoint
    control = tmp_path / ".public-control"
    if not (tmp_path / "tests/fixtures/phased_239/main.orc").exists():
        return
    control.mkdir(exist_ok=True)
    reservations = {}
    markers = list(control.glob("*.json"))
    markers.extend((tmp_path / ".orchestrate/runs").glob("*/effects/*/attempt-*/phased-attempt.json"))
    for marker in markers:
        try:
            record = json.loads(marker.read_text())
        except ValueError:
            continue  # A kill gate's independent observation retains ownership if a test tears the receipt.
        transport = record.get("reservation") or record.get("transport")
        if transport:
            reservation = InteractiveTerminalReservation.from_dict(Path("/tmp"), transport)
            reservations[reservation.adapter_token] = reservation
    for reservation in reservations.values():
        deadline = time.monotonic() + 12
        admission = PhasedSubmitEndpoint.inspect_owned(reservation, deadline=deadline)
        adapter = InteractiveTerminalTurnQueueAdapter(control / "cleanup", socket_root=Path("/tmp"), reservation=reservation)
        proof = adapter.recover_failed(reservation, deadline=deadline)
        assert proof.cleanup_complete, f"test-owned reservation cleanup incomplete: {reservation.path}"
        PhasedSubmitEndpoint.recover_owned(reservation, deadline=deadline, provider_cleanup=proof, admission=admission)
