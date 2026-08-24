#!/usr/bin/python3
"""Fake OMP binary for pinned-launch adapter tests (Task 5, OMP-I1).

Behavior
--------
* ``--version`` (sole argument): prints ``omp/17.3.4`` and exits 0 with empty
  stderr. It also attempts to write ``$HOME/.omp/version-probe-marker`` so
  tests can observe whether the probe ran confined (the write is denied when
  the helper protects ``$HOME/.omp``). The marker attempt never affects the
  probe output contract.
* Full run: reads stdin to EOF. When the first line is a JSON object with
  ``"fake": 1`` it applies control directives; otherwise the entire stdin is
  the prompt. It emits an omp_session-compatible stdout stream and, when
  ``--session-dir`` is present, writes the primary journal into that
  directory. Stderr carries ``FAKE_*`` reports for argv/env/cwd/fd-table/
  stdin/agents and filesystem probe results.

Control directives (first stdin line, JSON object with ``"fake": 1``)
----------------------------------------------------------------------
``mode``: ``"settled"`` (default) | ``"unsettled"`` | ``"spoof"`` |
``"primary-mismatch"``
``id`` / ``ts``: session id and RFC3339 timestamp (deterministic tests)
``reply``: assistant text (default "OK")
``journal_id``: journal id override (primary-mismatch)
``probe``: bool - run filesystem probes and report results on stderr
``sleep``: float - pause before the terminal agent_end (close-time races)
``exit``: int - child exit code (default 0)
``spoof_line``: JSON string emitted before the protocol (mode "spoof")

The fake uses only the standard library and avoids locale/TZ files so it runs
under the Landlock write confinement helper.
"""
import base64
import datetime
import hashlib
import json
import os
import sys
import time

VERSION = "17.3.4"

_TS_MS = 1787524395000


def _now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        + "Z"
    )


def _report(label: str, value: str) -> None:
    sys.stderr.write("FAKE_%s %s\n" % (label, value))
    sys.stderr.flush()


def _slot() -> str:
    obj = {"type": "title", "v": 1, "title": "", "updatedAt": _now_iso(), "pad": ""}
    base = json.dumps(obj, separators=(",", ":")) + "\n"
    obj["pad"] = " " * (256 - len(base.encode("utf-8")))
    text = json.dumps(obj, separators=(",", ":")) + "\n"
    assert len(text.encode("utf-8")) == 256
    return text


def _usage() -> dict:
    return {
        "input": 0,
        "output": 0,
        "cacheRead": 0,
        "cacheWrite": 0,
        "totalTokens": 0,
        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "total": 0},
    }


def _assistant_message(reply: str, stop: str, ts_ms: int) -> dict:
    return {
        "role": "assistant",
        "content": [{"type": "text", "text": reply}],
        "api": "openai-codex-responses",
        "provider": "openai-codex",
        "model": "openai-codex/gpt-5.6-sol",
        "usage": _usage(),
        "stopReason": stop,
        "timestamp": ts_ms,
    }


def _user_message(prompt: str, ts_ms: int) -> dict:
    return {
        "role": "user",
        "content": [{"type": "text", "text": prompt}],
        "attribution": "user",
        "timestamp": ts_ms,
    }


def _session_id(prompt: bytes, control: dict) -> str:
    explicit = control.get("id")
    if isinstance(explicit, str) and explicit:
        return explicit
    digest = hashlib.sha256(prompt).hexdigest()[:12]
    return "fake-%s" % digest


def _journal_path(session_dir: str, ts: str, session_id: str, journal_id: str) -> str:
    stem = ts.replace(":", "-").replace(".", "-")
    return os.path.join(session_dir, "%s_%s.jsonl" % (stem, journal_id))


def _version_probe() -> int:
    sys.stdout.write("omp/%s\n" % VERSION)
    sys.stdout.flush()
    home = os.environ.get("HOME", "/")
    marker = os.path.join(home, ".omp", "version-probe-marker")
    try:
        with open(marker, "w") as handle:
            handle.write("probe-unconfined")
    except OSError:
        pass
    return 0


def _argv_flags() -> dict:
    argv = sys.argv[1:]
    flags = {"session_dir": None, "add_dir": None}
    index = 0
    while index < len(argv):
        if argv[index] == "--session-dir" and index + 1 < len(argv):
            flags["session_dir"] = argv[index + 1]
            index += 2
        elif argv[index] == "--add-dir" and index + 1 < len(argv):
            flags["add_dir"] = argv[index + 1]
            index += 2
        else:
            index += 1
    return flags


def _probe_paths(flags: dict) -> tuple[list[str], list[str]]:
    denied = []
    home = os.environ.get("HOME", "/")
    denied.append(os.path.join(home, ".omp"))
    allowed = []
    for name in (
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
        "XDG_CACHE_HOME",
        "TMPDIR",
    ):
        value = os.environ.get(name)
        if value:
            allowed.append(value)
    if flags["session_dir"]:
        allowed.append(flags["session_dir"])
    if flags["add_dir"]:
        allowed.append(flags["add_dir"])
    return denied, allowed


def _run_probes(flags: dict, label: str) -> None:
    denied, allowed = _probe_paths(flags)
    ops = ("create", "write", "truncate", "replace", "rename", "restore")
    for root in denied:
        try:
            os.makedirs(root, exist_ok=True)
        except OSError:
            pass
        for op in ops:
            outcome = _attempt_op(root, "denied-file", op)
            _report(label, "%s %s=%s" % (root, op, outcome))
    for root in allowed:
        try:
            os.makedirs(root, exist_ok=True)
        except OSError:
            pass
        for op in ("create", "write"):
            outcome = _attempt_op(root, "allowed-file", op)
            _report(label, "%s %s=%s" % (root, op, outcome))


def _attempt_op(root: str, name: str, op: str) -> str:
    path = os.path.join(root, name)
    moved = path + ".mv"
    try:
        if op == "create":
            try:
                os.unlink(path)
            except OSError:
                pass
            with open(path, "x"):
                pass
        elif op == "write":
            with open(path, "w") as handle:
                handle.write("x")
        elif op == "truncate":
            with open(path, "r+") as handle:
                handle.truncate(0)
        elif op == "replace":
            with open(path + ".new", "w") as handle:
                handle.write("x")
            os.replace(path + ".new", path)
        elif op == "rename":
            os.rename(path, moved)
        elif op == "restore":
            os.rename(moved, path)
        return "ok"
    except OSError:
        return "denied"


def _emit_stream(prompt: bytes, control: dict, session_id: str, ts: str) -> str:
    reply = control.get("reply")
    if not isinstance(reply, str):
        reply = "OK"
    stop = "stop"
    mode = control.get("mode")
    if mode == "unsettled":
        stop = "canceled"
    ts_ms = _TS_MS
    user = _user_message(prompt.decode("utf-8", errors="replace"), ts_ms)
    assistant = _assistant_message(reply, stop, ts_ms + 100)
    lines = []
    header = {
        "type": "session",
        "version": 3,
        "id": session_id,
        "timestamp": ts,
        "cwd": os.getcwd(),
    }
    lines.append(json.dumps(header, separators=(",", ":")))
    lines.append('{"type":"agent_start"}')
    lines.append('{"type":"turn_start"}')
    lines.append(
        json.dumps(
            {"type": "message_start", "message": user},
            separators=(",", ":"),
        )
    )
    lines.append(
        json.dumps(
            {"type": "message_end", "message": user},
            separators=(",", ":"),
        )
    )
    lines.append(
        json.dumps(
            {"type": "message_start", "message": assistant},
            separators=(",", ":"),
        )
    )
    for update in (
        {"type": "text_start", "contentIndex": 0},
        {"type": "text_delta", "contentIndex": 0, "delta": reply},
        {"type": "text_end", "contentIndex": 0, "content": reply},
    ):
        lines.append(
            json.dumps(
                {"type": "message_update", "assistantMessageEvent": update},
                separators=(",", ":"),
            )
        )
    lines.append(
        json.dumps(
            {"type": "message_end", "message": assistant},
            separators=(",", ":"),
        )
    )
    lines.append(
        json.dumps(
            {"type": "turn_end", "message": assistant, "toolResults": []},
            separators=(",", ":"),
        )
    )
    if mode != "unsettled":
        lines.append(
            json.dumps(
                {
                    "type": "agent_end",
                    "messages": [user, assistant],
                    "isTerminal": True,
                    "telemetry": {"agentId": "fake"},
                    "coverage": {"inputs": [], "outputs": []},
                },
                separators=(",", ":"),
            )
        )
    return "\n".join(lines) + "\n"


def _write_journal(session_dir: str, ts: str, session_id: str, journal_id: str, stream: str) -> None:
    os.makedirs(session_dir, exist_ok=True)
    lines = stream.rstrip("\n").split("\n")
    header = json.loads(lines[0])
    entries = []
    for line in lines[1:]:
        event = json.loads(line)
        if event.get("type") == "message_end":
            message = event.get("message") or {}
            role = message.get("role")
            if role == "user":
                entries.append(
                    {
                        "type": "message",
                        "id": "u1",
                        "parentId": None,
                        "timestamp": message.get("timestamp"),
                        "message": message,
                    }
                )
            elif role == "assistant":
                entries.append(
                    {
                        "type": "message",
                        "id": "a1",
                        "parentId": "u1",
                        "timestamp": message.get("timestamp"),
                        "message": message,
                    }
                )
    journal_lines = [json.dumps(header, separators=(",", ":"))]
    journal_lines += [
        json.dumps(entry, separators=(",", ":")) for entry in entries
    ]
    payload = _slot() + "\n".join(journal_lines) + "\n"
    path = _journal_path(session_dir, ts, session_id, journal_id)
    with open(path, "x") as handle:
        handle.write(payload)


def _main() -> int:
    argv = sys.argv[1:]
    if argv == ["--version"]:
        return _version_probe()

    prompt = sys.stdin.buffer.read()
    control: dict = {}
    try:
        first = json.loads(prompt.split(b"\n", 1)[0])
        if isinstance(first, dict) and first.get("fake") == 1:
            control = first
    except (ValueError, IndexError):
        pass

    session_id = _session_id(prompt, control)
    ts = control.get("ts")
    if not isinstance(ts, str) or not ts:
        ts = _now_iso()

    flags = _argv_flags()
    _report("ARGS", json.dumps(argv))
    _report("ENV", json.dumps(sorted(os.environ)))
    _report("CWD", os.getcwd())
    try:
        _report("FDS", json.dumps(sorted(os.listdir("/proc/self/fd"))))
    except OSError:
        pass
    _report("STDIN", base64.b64encode(prompt).decode("ascii"))
    _report(
        "BROKER",
        json.dumps(
            {
                "url": os.environ.get("OMP_BROKER_URL"),
                "token": os.environ.get("OMP_BROKER_TOKEN"),
                "agent_dir": os.environ.get("PI_CODING_AGENT_DIR"),
            }
        ),
    )
    if control.get("leak_token") is True:
        sys.stderr.write("TOKEN_LEAK %s\n" % os.environ.get("OMP_BROKER_TOKEN", ""))
    token_file = control.get("token_file")
    if token_file:
        with open(token_file, "w", encoding="utf-8") as handle:
            handle.write(os.environ.get("OMP_BROKER_TOKEN", ""))
        sys.stderr.flush()
    agents_dir = os.environ.get("PI_CODING_AGENT_DIR")
    if isinstance(agents_dir, str) and os.path.isdir(agents_dir):
        try:
            _report("AGENTS", json.dumps(sorted(os.listdir(os.path.join(agents_dir, "agents")))))
        except OSError:
            pass

    mode = control.get("mode")
    if mode == "spoof":
        spoof = control.get("spoof_line")
        if isinstance(spoof, str):
            sys.stdout.write(spoof + "\n")

    stream = _emit_stream(prompt, control, session_id, ts)
    sys.stdout.write(stream)
    sys.stdout.flush()

    journal_id = control.get("journal_id")
    if not isinstance(journal_id, str) or not journal_id:
        journal_id = session_id
    if flags["session_dir"] and mode != "primary-mismatch":
        _write_journal(flags["session_dir"], ts, session_id, session_id, stream)
    elif flags["session_dir"] and mode == "primary-mismatch":
        _write_journal(flags["session_dir"], ts, session_id, journal_id, stream)

    if control.get("probe") is True:
        _run_probes(flags, "PROBE")
        try:
            child = os.fork()
        except OSError:
            child = -1
        if child == 0:
            _run_probes(flags, "SPAWNED_PROBE")
            os._exit(0)

    sleep = control.get("sleep")
    if isinstance(sleep, (int, float)) and sleep > 0:
        time.sleep(sleep)

    exit_code = control.get("exit")
    if not isinstance(exit_code, int):
        exit_code = 0
    return exit_code


if __name__ == "__main__":
    sys.exit(_main())
