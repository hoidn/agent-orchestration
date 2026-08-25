#!/usr/bin/python3
"""Fake interactive OMP binary for Task 10 foreground fork/resume tests.

Implements the exact X8 interactive surface exercised by ``prompt resume``:

* ``--version`` (sole argument): prints ``omp/17.3.4`` and exits 0 with empty
  stderr. No marker file is attempted so the version-probe output contract is
  exact under the Landlock helper.
* Interactive: parses ``--fork <session-id>`` / ``--resume <session-id>``,
  ``--session-dir <dir>``, ``--cwd <dir>``, ``--add-dir <dir>``, ``--model``,
  and ignores the fixed X8 cosmetic flags. It reads one control line from stdin, applies the
  optional ``{"fake": 1, ...}`` control line, and writes the resulting session
  journal(s). Stderr carries ``FAKE_*`` reports (env NAMES only, never
  broker values) plus confinement probe outcomes.

Journal behavior
----------------
``--fork``: finds the source primary by header id in the session dir, writes
exactly one new primary JSONL with a new header id and ``parentSession`` equal
to the source id, reusing the source entry lines. The source journal is never
modified.

``--resume``: appends exactly one complete user-message record to the source
primary, optionally rewriting the pinned 256-byte title slot first.

Control directives (first stdin line, JSON object with ``"fake": 1``)
---------------------------------------------------------------------
``id``: new session id for a fork (default ``22222222-2222-7222-8222-222222222222``)
``ts``: RFC3339 timestamp for new headers/entries (default now)
``agent``: bool - write an agent-shaped fork result (session_init with agent)
``title``: null (keep slot) | ``"changed"`` (valid new slot) | ``"malformed"``
``truncate``: bool - resume: drop the last record (valid truncation)
``rewrite``: bool - resume: swap the last two records (body replacement)
``no_append``: bool - resume: exit without touching the journal
``extra_file``: str - fork: also create this extra file in the session dir
``remove_source``: bool - fork: delete the source primary
``swap``: bool - fork: replace the source primary with a symlink to the result
``probe``: bool - run confinement probes (denied: $HOME/.omp and fresh conf
  copies; allowed: XDG roots, session dir, --add-dir workspace, TMPDIR)
``exit``: int - child exit code (default 0)

The fixture uses only the standard library and writes no locale/TZ files so it
runs under the Landlock write-confinement helper.
"""
import base64
import datetime
import hashlib
import json
import os
import sys

VERSION = "17.3.4"
DEFAULT_ID = "22222222-2222-7222-8222-222222222222"
CONF_RUNTIME_BASE = ".omp-i1-runtime"


def _now_iso() -> str:
    return (
        datetime.datetime.now(datetime.timezone.utc)
        .strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
        + "Z"
    )


def _report(label: str, value: str) -> None:
    sys.stderr.write("FAKE_%s %s\n" % (label, value))
    sys.stderr.flush()


def _slot(title: str = "") -> str:
    obj = {"type": "title", "v": 1, "title": title, "updatedAt": _now_iso(), "pad": ""}
    base = json.dumps(obj, separators=(",", ":")) + "\n"
    obj["pad"] = " " * (256 - len(base.encode("utf-8")))
    text = json.dumps(obj, separators=(",", ":")) + "\n"
    assert len(text.encode("utf-8")) == 256
    return text


def _malformed_slot() -> str:
    obj = {"type": "title", "v": 1, "title": "", "updatedAt": _now_iso(), "pad": ""}
    base = json.dumps(obj, separators=(",", ":")) + "\n"
    obj["pad"] = "x" * (256 - len(base.encode("utf-8")))
    text = json.dumps(obj, separators=(",", ":")) + "\n"
    assert len(text.encode("utf-8")) == 256
    return text


def _flags() -> dict:
    argv = sys.argv[1:]
    flags = {"fork": None, "resume": None, "session_dir": None, "cwd": None,
             "add_dir": None, "model": None}
    index = 0
    while index < len(argv):
        token = argv[index]
        if token == "--fork" and index + 1 < len(argv):
            flags["fork"] = argv[index + 1]
            index += 2
        elif token == "--resume" and index + 1 < len(argv):
            flags["resume"] = argv[index + 1]
            index += 2
        elif token in ("--session-dir", "--cwd", "--add-dir", "--model") and index + 1 < len(argv):
            flags[token[2:].replace("-", "_")] = argv[index + 1]
            index += 2
        else:
            index += 1
    return flags


def _find_primary(session_dir: str, session_id: str) -> tuple[str, bytes]:
    for name in sorted(os.listdir(session_dir)):
        if not name.endswith(".jsonl"):
            continue
        path = os.path.join(session_dir, name)
        with open(path, "rb") as handle:
            data = handle.read()
        try:
            header = json.loads(data.split(b"\n", 2)[1].decode("utf-8"))
        except (ValueError, IndexError, UnicodeDecodeError):
            continue
        if header.get("type") == "session" and header.get("id") == session_id:
            return name, data
    raise SystemExit("fake-omp-interactive: no primary matches %s" % session_id)


def _entry_lines(data: bytes) -> list[str]:
    return data.decode("utf-8").rstrip("\n").split("\n")[2:]


def _probe_paths(flags: dict) -> tuple[list[str], list[str]]:
    denied = [os.path.join(os.environ.get("HOME", "/"), ".omp")]
    base = os.path.join(os.environ.get("HOME", "/"), CONF_RUNTIME_BASE)
    try:
        for nonce in sorted(os.listdir(base)):
            candidate = os.path.join(base, nonce, "conf")
            if os.path.isdir(candidate):
                denied.append(candidate)
    except OSError:
        pass
    allowed = []
    for name in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "TMPDIR"):
        value = os.environ.get(name)
        if value:
            allowed.append(value)
    if flags["session_dir"]:
        allowed.append(flags["session_dir"])
    if flags["add_dir"]:
        allowed.append(flags["add_dir"])
    return denied, allowed


def _attempt_op(root: str, name: str, op: str) -> str:
    path = os.path.join(root, name)
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
            os.rename(path, path + ".mv")
        elif op == "restore":
            os.rename(path + ".mv", path)
        return "ok"
    except OSError:
        return "denied"


def _run_probes(flags: dict, label: str) -> None:
    denied, allowed = _probe_paths(flags)
    for root in denied:
        try:
            os.makedirs(root, exist_ok=True)
        except OSError:
            pass
        for op in ("create", "write", "truncate", "replace", "rename", "restore"):
            _report(label, "%s %s=%s" % (root, op, _attempt_op(root, "denied-file", op)))
    for root in allowed:
        try:
            os.makedirs(root, exist_ok=True)
        except OSError:
            pass
        for op in ("create", "write"):
            _report(label, "%s %s=%s" % (root, op, _attempt_op(root, "allowed-file", op)))
        try:
            os.unlink(os.path.join(root, "allowed-file"))
        except OSError:
            pass


def _fork(flags: dict, control: dict) -> int:
    source_name, source = _find_primary(flags["session_dir"], flags["fork"])
    new_id = control.get("id")
    if not isinstance(new_id, str) or not new_id:
        new_id = DEFAULT_ID
    ts = control.get("ts")
    if not isinstance(ts, str) or not ts:
        ts = _now_iso()
    cwd = os.environ.get("PWD") or os.getcwd()
    header = {"type": "session", "version": 3, "id": new_id, "timestamp": ts,
              "cwd": cwd, "parentSession": flags["fork"]}
    if control.get("agent") is True:
        entries = [
            json.dumps({"type": "session_init", "id": "i1", "parentId": None,
                        "timestamp": ts, "systemPrompt": "s", "task": "t",
                        "tools": [], "agent": "child"}, separators=(",", ":")),
            json.dumps({"type": "message", "id": "u1", "parentId": "i1",
                        "timestamp": ts, "message": {"role": "user",
                        "content": "child prompt", "timestamp": 1}},
                       separators=(",", ":")),
        ]
    else:
        entries = _entry_lines(source)
    lines = [json.dumps(header, separators=(",", ":"))] + entries
    payload = _slot() + "\n".join(lines) + "\n"
    stem = ts.replace(":", "-").replace(".", "-")
    result_name = "%s_%s.jsonl" % (stem, new_id)
    result_path = os.path.join(flags["session_dir"], result_name)
    with open(result_path, "x") as handle:
        handle.write(payload)
    if control.get("extra_file") is True:
        extra = os.path.join(flags["session_dir"], "extra.txt")
        with open(extra, "x") as handle:
            handle.write("stray")
    if control.get("extra_primary") is True:
        extra = os.path.join(flags["session_dir"], "%s_%s.jsonl" % (stem, "99999999-9999-7999-8999-999999999999"))
        with open(extra, "x") as handle:
            handle.write(_slot() + json.dumps(
                {"type": "session", "version": 3, "id": "99999999-9999-7999-8999-999999999999",
                 "timestamp": ts, "cwd": cwd, "parentSession": flags["fork"]},
                separators=(",", ":")) + "\n")
    if control.get("remove_source") is True:
        os.unlink(os.path.join(flags["session_dir"], source_name))
    if control.get("swap") is True:
        try:
            os.unlink(os.path.join(flags["session_dir"], source_name))
        except OSError:
            pass
        os.symlink(result_name, os.path.join(flags["session_dir"], source_name))
    return 0


def _resume(flags: dict, control: dict) -> int:
    source_name, source = _find_primary(flags["session_dir"], flags["resume"])
    path = os.path.join(flags["session_dir"], source_name)
    slot = source[:256]
    body = source[256:]
    tail = ""
    if control.get("truncate") is True:
        body = body.rstrip(b"\n").rsplit(b"\n", 2)[0] + b"\n"
    elif control.get("rewrite") is True:
        parts = body.rstrip(b"\n").split(b"\n")
        if len(parts) >= 2:
            parts[-1], parts[-2] = parts[-2], parts[-1]
            body = b"\n".join(parts) + b"\n"
    elif control.get("no_append") is not True:
        last_line = body.rstrip(b"\n").rsplit(b"\n", 1)[-1]
        last_id = json.loads(last_line.decode("utf-8"))["id"]
        entry_id = "u-%s" % hashlib.sha256(body).hexdigest()[:8]
        ts = control.get("ts")
        if not isinstance(ts, str) or not ts:
            ts = _now_iso()
        entry = {"type": "message", "id": entry_id, "parentId": last_id,
                 "timestamp": ts, "message": {"role": "user",
                 "content": "resumed", "timestamp": 1}}
        tail = json.dumps(entry, separators=(",", ":")) + "\n"
    title_kind = control.get("title")
    if title_kind == "malformed":
        slot = _malformed_slot().encode("utf-8")
    elif title_kind == "changed":
        slot = _slot("resumed title").encode("utf-8")
    with open(path, "w") as handle:
        handle.write(slot.decode("utf-8") + body.decode("utf-8") + tail)
    return 0


def _version_probe() -> int:
    sys.stdout.write("omp/%s\n" % VERSION)
    sys.stdout.flush()
    return 0


def _main() -> int:
    argv = sys.argv[1:]
    if argv == ["--version"]:
        return _version_probe()

    prompt = sys.stdin.buffer.readline()
    control: dict = {}
    try:
        first = json.loads(prompt.split(b"\n", 1)[0])
        if isinstance(first, dict) and first.get("fake") == 1:
            control = first
    except (ValueError, IndexError):
        pass

    flags = _flags()
    _report("ARGS", json.dumps(argv))
    _report("ENV", json.dumps(sorted(os.environ)))
    _report("CWD", os.getcwd())
    try:
        _report("FDS", json.dumps(sorted(os.listdir("/proc/self/fd"))))
    except OSError:
        pass
    _report("STDIN", base64.b64encode(prompt).decode("ascii"))

    if flags["fork"] is not None:
        _fork(flags, control)
    elif flags["resume"] is not None:
        _resume(flags, control)
    else:
        raise SystemExit("fake-omp-interactive: expected --fork or --resume")

    if control.get("probe") is True:
        _run_probes(flags, "PROBE")
        try:
            child = os.fork()
        except OSError:
            child = -1
        if child == 0:
            _run_probes(flags, "SPAWNED_PROBE")
            os._exit(0)

    _report("DONE", "1")
    exit_code = control.get("exit")
    if not isinstance(exit_code, int):
        exit_code = 0
    return exit_code


if __name__ == "__main__":
    sys.exit(_main())
