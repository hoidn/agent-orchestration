"""Fake `codex` and `claude` CLIs that keep a native store and speak each provider's stdout protocol.

Modes (per plan step): success, interrupted, nonzero, nonzero-before-append, timeout, complete-then-hang, linger
(forks a grandchild after completing), orphan (forks a grandchild at startup with stdio on /dev/null and its pid in
`<bin>/.<tool>.orphan`, completes the turn, writes `<bin>/.<tool>.done`, then waits for its parent to die so a test
driver can kill the orchestrator mid-call), overlap, lose-locator, invalid-result. A call beyond the plan exits 97
with `shim plan exhausted: <tool> call #N` on stderr.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

COMMON = r'''import fcntl, hashlib, json, os, sys, time, uuid
from pathlib import Path
prompt = sys.stdin.buffer.read().decode("utf-8")
tool = Path(sys.argv[0]).name
argv = sys.argv[1:]
log = Path("requests.jsonl")
plan = json.loads(os.environ["AGENT_SHIM_PLAN"])
# Steps are consumed per call, including calls that exit before logging a request; the counter lives
# beside the shim so it never touches the workspace or the native homes.
with (Path(sys.argv[0]).parent / f".{tool}.calls").open("a+", encoding="utf-8") as counter:
    fcntl.flock(counter, fcntl.LOCK_EX)
    counter.seek(0); index = len(counter.read()); counter.write("."); counter.flush()
if index >= len(plan.get(tool, [])):
    sys.stderr.write(f"shim plan exhausted: {tool} call #{index + 1}\n"); sys.exit(97)
step = plan[tool][index]
mode = step.get("mode", "success")
here = Path(sys.argv[0]).parent
if mode == "orphan" and os.fork() == 0:     # same process group, detached stdio: survives a dead orchestrator
    null = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2):
        os.dup2(null, fd)
    (here / f".{tool}.orphan").write_text(str(os.getpid()))
    time.sleep(120); os._exit(0)
def log_request(session):
    with log.open("a", encoding="utf-8") as out:
        out.write(json.dumps({"tool": tool, "argv": argv, "session": session, "mode": mode, "cwd": os.getcwd(),
                              "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest()}) + "\n")
def write_result():
    for name, text in step.get("files", {}).items():
        Path(name).parent.mkdir(parents=True, exist_ok=True); Path(name).write_text(text, encoding="utf-8")
    target = Path(os.environ["ORCHESTRATOR_OUTPUT_BUNDLE_PATH"])
    payload = {"ok": "not-bool"} if mode == "invalid-result" else step["result"]
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload), encoding="utf-8")
def emit(event):
    sys.stdout.write(json.dumps(event) + "\n"); sys.stdout.flush()
def finish():
    if mode == "complete-then-hang":
        time.sleep(30)
    if mode == "linger" and os.fork() == 0:
        time.sleep(30); os._exit(0)
    if mode == "orphan":
        parent = os.getppid()
        (here / f".{tool}.done").write_text("")
        deadline = time.monotonic() + 120
        while os.getppid() == parent and time.monotonic() < deadline:
            time.sleep(0.05)
if mode == "timeout":
    time.sleep(30)                      # before any store write: the adapter can prove no advance
if mode == "nonzero-before-append":
    sys.exit(9)                         # before any store write
'''

FAKE_CODEX = COMMON + r'''
resume = "resume" in argv
session = argv[argv.index("resume") + 1] if resume else str(uuid.uuid4())
store = Path(os.environ["CODEX_HOME"]) / "sessions"
files = [p for p in store.rglob("rollout-*.jsonl") if session in p.name] if store.exists() else []
if resume and (mode == "lose-locator" or not files):
    log_request(session)
    sys.stderr.write(f"no rollout found for thread id {session}\n"); sys.exit(1)
path = files[0] if resume else store / "2026" / f"rollout-{session}.jsonl"
path.parent.mkdir(parents=True, exist_ok=True)
rows = [] if not resume else [json.loads(l) for l in path.read_text().splitlines()]
if not resume:
    rows.append({"type": "session_meta", "payload": {"id": session}})
def turn(turn_id, text, complete, result_text="{}"):
    rows.append({"type": "event_msg", "payload": {"type": "task_started", "turn_id": turn_id}})
    rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": session,
                 "item": {"id": "u-" + turn_id, "type": "UserMessage", "content": [{"text_elements": [text]}]}}})
    if complete:
        rows.append({"type": "event_msg", "payload": {"type": "item_completed", "turn_id": turn_id, "thread_id": session,
                     "item": {"id": "a-" + turn_id, "type": "AgentMessage", "phase": "final_answer", "content": [{"type": "Text", "text": result_text}]}}})
        rows.append({"type": "event_msg", "payload": {"type": "task_complete", "turn_id": turn_id, "last_agent_message": result_text}})
if mode == "overlap":
    turn("foreign-" + str(uuid.uuid4())[:8], "external operator turn", True)
turn_id = str(uuid.uuid4())
turn(turn_id, prompt, mode not in {"interrupted", "nonzero"})
path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
log_request(session)
emit({"type": "thread.started", "thread_id": session})
emit({"type": "turn.started"})
if mode == "interrupted":
    os._exit(137)
if mode == "nonzero":
    sys.exit(9)
write_result()
emit({"type": "item.completed", "item": {"type": "agent_message", "text": "done"}})
emit({"type": "turn.completed"})
finish()
'''

FAKE_CLAUDE = COMMON + r'''
resume = "--resume" in argv
session = argv[argv.index("--resume") + 1] if resume else str(uuid.uuid4())
store = Path(os.environ["CLAUDE_CONFIG_DIR"]) / "projects" / "ws"
path = store / f"{session}.jsonl"
if resume and (mode == "lose-locator" or not path.exists()):
    log_request(session)
    sys.stderr.write(f"No conversation found with session ID: {session}\n"); sys.exit(1)
store.mkdir(parents=True, exist_ok=True)
rows = [json.loads(l) for l in path.read_text().splitlines()] if resume else []
parent = next((r["uuid"] for r in reversed(rows) if r["type"] == "assistant"), None)
def turn(prompt_id, text, complete):
    global parent
    user_id = str(uuid.uuid4())
    rows.append({"type": "user", "uuid": user_id, "parentUuid": parent, "sessionId": session, "promptId": prompt_id,
                 "isSidechain": False, "message": {"role": "user", "content": text}})
    if complete:
        # The real CLI (2.1.300) writes one row per content block of a message, same message.id, each the parent
        # of the next; the file's first turn mirrors that split (thinking + text), later turns are one text row.
        message_id, final_id = "msg_" + uuid.uuid4().hex, user_id
        blocks = ([{"type": "thinking", "thinking": ""}] if parent is None else []) + [{"type": "text", "text": "ok"}]
        for block in blocks:
            row_parent, final_id = final_id, str(uuid.uuid4())
            rows.append({"type": "assistant", "uuid": final_id, "parentUuid": row_parent, "sessionId": session, "promptId": prompt_id,
                         "isSidechain": False, "message": {"id": message_id, "role": "assistant", "stop_reason": "end_turn", "content": [block]}})
        parent = final_id
if mode == "overlap":
    turn(str(uuid.uuid4()), "external operator turn", True)
prompt_id = str(uuid.uuid4())
turn(prompt_id, prompt, mode not in {"interrupted", "nonzero"})
path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
log_request(session)
emit({"type": "system", "subtype": "init", "session_id": session, "model": "fake"})
if mode == "interrupted":
    os._exit(137)
if mode == "nonzero":
    sys.exit(9)
write_result()
emit({"type": "assistant", "session_id": session, "message": {"role": "assistant", "content": [{"type": "text", "text": "ok"}]}})
emit({"type": "result", "subtype": "success", "is_error": False, "session_id": session, "result": "ok"})
finish()
'''


def install_agent_shims(bin_dir: Path, monkeypatch, *, codex_home: Path, claude_home: Path, plan: dict) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    for tool, body in (("codex", FAKE_CODEX), ("claude", FAKE_CLAUDE)):
        for marker in (".calls", ".orphan", ".done"):      # a reinstall starts the plan over
            (bin_dir / f".{tool}{marker}").unlink(missing_ok=True)
        (bin_dir / tool).write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
        (bin_dir / tool).chmod(0o700)
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ["PATH"])
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude_home))
    monkeypatch.setenv("AGENT_SHIM_PLAN", json.dumps(plan))


def shim_requests(root: Path) -> list[dict]:
    path = root / "requests.jsonl"
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []
