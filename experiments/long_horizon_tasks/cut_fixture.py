"""Cut committed fixtures from local recordings; the raw recordings stay in the local cache.

Stream fixture (one recorded trial): the stream's init event and last events, the count of `api_retry`
events, the harness's exception class, the CLI's exit code, the trial's usage figures and the verifier's
result. Model text, tool input and tool output are dropped (task content); CLI-made text (a `<synthetic>`
message, an error result) is kept, and so is the harness's exception message when no stream exists and
the class is `RuntimeError`; home paths become `<home>` (not the container's `/home/claude`), IPv4
addresses `<address>`, a fake slot token `<fake slot token>`.

Request fixture (one recording's `stub.jsonl`): what the CLI sent, as distinct request shapes plus one row
per request `[shape index, status, number of messages, seconds since the first request, stub fault mode,
cache marks]`, where a cache mark is `[message index, block index, cache_control]`; `first_request` keeps
the first request's message blocks by type, length and cache control, and the stub's counts of watched
names; `bearer_matches` lists the stub's check of the fake token per request, when it was asked for.
A shape keeps the method and path, every header name, the values of the headers a rule may match
(`SHOWN_HEADERS`, and the user agent's product token), `model`, effort (`output_config.effort`),
`max_tokens`, `stream`, declared tool names, server-tool types, each tool definition's length and
`cache_control`, the names of the other body fields, and each system block's length and `cache_control`;
`body_keys`, the body's top-level keys (`messages`, `system` and `tools` when not empty: the stub's log does not
tell an empty list from an absent one); and, per declared tool, `tool_keys` and `input_schema_keys`, the sorted
top-level keys of the tool's definition and of its `input_schema`, read from the CLI's own record of the request
shape in the recording's session files (an `api-request-shape` entry) and joined to the sent tool by name and JSON
length (the stub's `tool_chars`); a tool with no single such definition gets None. `message_block_keys` holds, per
block type, the sorted key sets of the sent message blocks whose session transcript block (the same type and JSON
length, the stub's `chars`, less a `cache_control` the stub saw) is the only one; `message_block_keys_unrecorded`
counts the others by type, every text block among them (the stub's `chars` of a text block is its text's length,
which says nothing of its keys). Only key names are read from the session files: never a description, a schema
body, a tool input or any text. It never keeps system or message text, `metadata`, or a
credential: `x-api-key` and `authorization` become `<dummy>` (an authorization keeps its scheme).

Trace fixture (a recording's `strace.*` files, record.sh STRACE=1 or DECOY=1): every path a file call named,
with the calls and their results (`ok`, an errno name, or `unfinished`), and the programs executed. Never a
call's other arguments: no command line, no environment, no file content; a run of 32 or more hex digits
in a path becomes `<hex>`. When the trace holds the CLI's
own `execve` (DECOY=1 traces the host-side `podman exec` from its start), only the CLI's process and its
children from that `execve` on are kept (`cli_started_in_trace`); host-side paths are dropped. With a
`canary.txt` (DECOY=1), `decoy` says where the planted credential's canary went: how many requests carried
the slot's token, how many named the canary in their system, tool or message text (the stub's `--watch`
counts), and which files of the recording hold it.

After-limit fixture (a timed-out trial and its recording's `stub.jsonl`): when the harness ended the agent
phase, how many requests the stub logged after it, the last one's delay, their statuses and bearer
checks; and the distinct `<tool_use_error>` texts of the stream (CLI-made text, as a refused tool call
is answered), never any other tool output.

Live-probe fixtures (plan Task 4: the probe's directory and the passthrough's `requests.jsonl`), into one
directory: per session, `session-<effort>.json`, a stream fixture as above plus `exported_config`, the keys of
the exported configuration (`agent/sessions/.claude.json`) in CONFIG_KEYS and no other; and `passthrough-log.json`,
the passthrough's rows as logged (it never logs the `authorization` header or a header value outside its list),
each row's time as seconds since the first. Across the four files each distinct vendor or account identifier
(VENDOR_IDS: request, message and workspace ids, and every UUID: organization, session, event) becomes one
placeholder of its shape, numbered in order of appearance, so a value shared by two files stays shared.

The index: `harbor-args <trial config.json>` prints the harness arguments a trial ran with, read back from
its configuration (the `harbor_args` field of `recordings.json`).

Usage: python -I cut_fixture.py <trial dir holding result.json and agent/> <source label> <out.json>
       python -I cut_fixture.py requests <stub.jsonl> <source label> <out.json>
       python -I cut_fixture.py trace <recording dir> <source label> <out.json>
       python -I cut_fixture.py after-limit <trial dir> <stub.jsonl> <source label> <out.json>
       python -I cut_fixture.py live-probe <probe dir> <requests.jsonl> <source note> <out dir>
       python -I cut_fixture.py harbor-args <trial config.json>
"""

import collections
import datetime
import json
import re
import sys
from pathlib import Path

TAIL = 4
SHOWN_HEADERS = ("anthropic-beta", "anthropic-version", "content-type", "x-app")
SECRET_HEADERS = ("x-api-key", "authorization")
NAMED_PARAMS = ("model", "metadata", "max_tokens", "stream", "output_config")
SESSION_FILES = "jobs/*/*/agent/sessions/projects/**/*.jsonl"
CACHE_MARK = len(', "cache_control": ')  # what a cache mark adds to a block's JSON, besides its value
CONFIG_KEYS = ("cachedExtraUsageDisabledReason",)  # the exported configuration's word on paid extra usage
VENDOR_IDS = re.compile(r"\b(req|msg|wrkspc)_[0-9A-Za-z]{20,}\b|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _cut_message(message):
    keep = {k: message.get(k) for k in ("model", "stop_reason", "stop_details", "usage") if k in message}
    synthetic = message.get("model") == "<synthetic>"
    keep["content"] = [b if synthetic else {"type": b.get("type"), **({"name": b["name"]} if "name" in b else {})}
                       for b in message.get("content") or [] if isinstance(b, dict)]
    return keep


def _cut_user(event):
    blocks = (event.get("message") or {}).get("content")
    blocks = blocks if isinstance(blocks, list) else []
    flags = [b.get("is_error") for b in blocks if isinstance(b, dict)]
    return {"type": "user", "parent_tool_use_id": event.get("parent_tool_use_id"), "tool_result_is_error": flags}


def cut_event(event):
    kind = event.get("type")
    if kind == "assistant":
        cut = {k: v for k, v in event.items() if k not in ("message", "uuid", "session_id")}
        return {**cut, "message": _cut_message(event.get("message") or {})}
    if kind == "user":
        return _cut_user(event)
    if kind == "result" and not event.get("is_error") and event.get("subtype") == "success":
        return {**event, "result": "<cut: model text>"}
    return event


def _exit_code(message):
    found = re.search(r"Command failed \(exit (\d+)\)", message or "")
    return int(found.group(1)) if found else None


def fixture(trial, source):
    result = json.loads((trial / "result.json").read_text())
    exc = result.get("exception_info") or {}
    stream = trial / "agent" / "claude-code.txt"
    events = [json.loads(line) for line in stream.read_text().splitlines() if line.startswith("{")] \
        if stream.exists() else []
    kept = {"exception_message": exc.get("exception_message")} \
        if not events and exc.get("exception_type") == "RuntimeError" else {}
    return {"source": source,
            "harness_exception": exc.get("exception_type"), **kept,
            "cli_exit_code": _exit_code(exc.get("exception_message")),
            "agent_result": result.get("agent_result"),
            "verifier_result": result.get("verifier_result"),
            "init": next((cut_event(e) for e in events if e.get("subtype") == "init"), None),
            "n_events": len(events),
            "n_api_retry": sum(e.get("subtype") == "api_retry" for e in events),
            "stream_tail": [cut_event(e) for e in events[-TAIL:]]}


def _header(name, value):
    if name in SECRET_HEADERS:
        return value.replace("<redacted>", "<dummy>") if " " in value else "<dummy>"
    if name == "user-agent":
        return value.split(" ", 1)[0]
    return value if name in SHOWN_HEADERS else None


def _body(params):
    return {"effort": (params.get("output_config") or {}).get("effort"), "max_tokens": params.get("max_tokens"),
            "stream": params.get("stream"), "other_params": sorted(k for k in params if k not in NAMED_PARAMS)}


def _body_keys(row):
    lists = {"messages": row.get("n_messages"), "system": row.get("system"), "tools": row.get("tools")}
    return sorted({*(row.get("params") or {}), *(name for name, value in lists.items() if value)})


def _only(found):
    return next(iter(found)) if len(found) == 1 else None


def _tool_keys(row, defined):
    tools = row.get("tools") or []
    known = [_only(defined.get((name, chars), ())) for name, chars in zip(tools, row.get("tool_chars") or
                                                                           [None] * len(tools))]
    return {"tool_keys": [list(k[0]) if k else None for k in known],
            "input_schema_keys": [list(k[1]) if k else None for k in known]}


def _shape(row, defined):
    return {"method": row.get("method", "POST"), "path": row.get("path"), "subagent": row.get("subagent"),
            "headers": {k: _header(k, v) for k, v in sorted((row.get("headers") or {}).items())},
            "model": row.get("model"), **_body(row.get("params") or {}), "body_keys": _body_keys(row),
            "tools": row.get("tools"), "server_tools": [t.get("type") for t in row.get("server_tools") or []],
            "tool_chars": row.get("tool_chars"), "tool_cache": row.get("tool_cache"), **_tool_keys(row, defined),
            "system": [{k: b[k] for k in ("chars", "cache_control") if k in b} for b in row.get("system") or []]}


def _session_entries(recording):
    return [json.loads(line) for path in sorted(Path(recording).glob(SESSION_FILES))
            for line in path.read_text().splitlines() if line.strip()]


def _keys_by_length(entries):
    """The CLI's own records in its session files, by (name or type, JSON length): each tool definition of an
    `api-request-shape` entry (its keys and its schema's keys), and each transcript message block (its keys)."""
    tools, blocks = collections.defaultdict(set), collections.defaultdict(set)
    for entry in entries:
        for tool in (entry.get("shape") or {}).get("tools") or [] if entry.get("type") == "api-request-shape" else []:
            schema = tool.get("input_schema")
            tools[(tool.get("name"), len(json.dumps(tool)))].add(
                (tuple(sorted(tool)), tuple(sorted(schema)) if isinstance(schema, dict) else ()))
        content = (entry.get("message") or {}).get("content") if entry.get("type") in ("user", "assistant") else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict):
                blocks[(block.get("type"), len(json.dumps(block)))].add(tuple(sorted(block)))
    return tools, blocks


def _block_keys(rows, blocks):
    keys, unrecorded = collections.defaultdict(set), collections.Counter()
    for block in (b for row in rows for _, sent in row.get("message_blocks") or [] for b in sent):
        mark = block.get("cache_control")
        chars = block["chars"] - (CACHE_MARK + len(json.dumps(mark)) if mark is not None else 0)
        found = _only(blocks.get((block["type"], chars), ())) if block["type"] != "text" else None
        if found is None:
            unrecorded[block["type"]] += 1
        else:
            keys[block["type"]].add(tuple(sorted({*found, *(["cache_control"] if mark is not None else [])})))
    return {"message_block_keys": {kind: sorted(map(list, found)) for kind, found in sorted(keys.items())},
            "message_block_keys_unrecorded": dict(sorted(unrecorded.items()))}


def _cache_marks(row):
    return [[i, j, b["cache_control"]] for i, (_, blocks) in enumerate(row.get("message_blocks") or [])
            for j, b in enumerate(blocks) if "cache_control" in b]


def _hide_canary(rows, log):
    """A decoy recording's canary is a watched name: its count is kept under `<canary>`, never the value."""
    marker = Path(log).parent / "canary.txt"
    canary = marker.read_text().strip() if marker.exists() else None
    for row in rows:
        if canary in (row.get("mentions") or {}):
            row["mentions"]["<canary>"] = row["mentions"].pop(canary)
    return rows


def requests(log, source):
    rows = _hide_canary([json.loads(line) for line in Path(log).read_text().splitlines() if line.strip()], log)
    defined, blocks = _keys_by_length(_session_entries(Path(log).parent))
    shapes, out = [], []
    start = next((r["time"] for r in rows if "time" in r), None)
    for row in rows:
        shape = _shape(row, defined)
        if shape not in shapes:
            shapes.append(shape)
        since = round(row["time"] - start, 1) if "time" in row else None
        out.append([shapes.index(shape), row.get("status"), row.get("n_messages"), since, row.get("mode"),
                    _cache_marks(row)])
    return {"source": source, "shapes": shapes, "requests": out, **_first_and_bearer(rows),
            **_block_keys(rows, blocks)}


def _first_and_bearer(rows):
    first = next((r for r in rows if "message_blocks" in r), {})
    return {"first_request": {k: first[k] for k in ("message_blocks", "mentions") if k in first},
            "bearer_matches": [r["bearer_matches"] for r in rows if "bearer_matches" in r]}


_CALL = re.compile(r'^(?:\d+\s+)?\S+\s+(\w+)\((?:AT_FDCWD, |\d+, )?"([^"]*)"')
_RESULT = re.compile(r"\) += (-?\d+|\?|0x[0-9a-f]+)(?: (E[A-Z0-9]+))?(?: \(.*\))?$")


_RESUMED = re.compile(r"^(\d+)\s+\S+\s+<\.\.\. (\w+) resumed>")


def _outcome(paths, path, call, line):
    result = _RESULT.search(line) if line else None
    outcome = "unfinished" if result is None else (result.group(2) or "ok")
    paths.setdefault(path, {}).setdefault(call, [])
    if outcome not in paths[path][call]:
        paths[path][call].append(outcome)


def _trace_line(line, paths, execs, pending):
    """One strace line: a call that another process interrupted (`<unfinished ...>`) takes the result of
    its `<... call resumed>` line; one never resumed stays `unfinished`."""
    resumed = _RESUMED.match(line)
    if resumed and (resumed.group(1), resumed.group(2)) in pending:
        _outcome(paths, pending.pop((resumed.group(1), resumed.group(2))), resumed.group(2), line)
        return
    found = _CALL.match(line)
    if not found:
        return
    call, path = found.groups()
    path = re.sub(r"[0-9a-f]{32,}", "<hex>", path)  # a key file's hashed name, for one
    if call.startswith("exec"):
        execs.append(path)
    elif "<unfinished" in line and line[:1].isdigit():
        pending[(line.split(" ", 1)[0], call)] = path
    else:
        _outcome(paths, path, call, None if "<unfinished" in line else line)


_CLI_EXEC = re.compile(r'^(\d+)\s+\S+\s+execve\("[^"]*/claude"')
_CHILD = re.compile(r"^(\d+)\s.*\b(?:clone3?|v?fork)\b.*\) += (\d+)(?: /\* (\d+) in strace's PID NS \*/)?$")


def _cli_tree(lines):
    """The lines of the CLI's process and its children from the CLI's own execve on, or None if the trace
    does not hold that execve (strace attached to the running CLI). A child is known by the result of
    its parent's clone or fork, in strace's own PID namespace (record.sh traces with
    `--pidns-translation`: a container's child pid comes with its host pid)."""
    start = next((i for i, line in enumerate(lines) if _CLI_EXEC.match(line) and "= -1 E" not in line), None)
    if start is None:
        return None
    edges = collections.defaultdict(set)  # a child's own lines can come before its parent's clone result
    for child in filter(None, map(_CHILD.match, lines[start:])):
        edges[child.group(1)].add(child.group(3) or child.group(2))
    tree, todo = set(), [_CLI_EXEC.match(lines[start]).group(1)]
    while todo:
        pid = todo.pop()
        if pid not in tree:
            tree.add(pid)
            todo.extend(edges[pid])
    return [line for line in lines[start:] if line.split(" ", 1)[0] in tree], len(tree)


def _stub_rows(recording):
    log = recording / "stub.jsonl"
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()] if log.exists() else []


def _holding(recording, marker, canary):
    return sorted(str(p.relative_to(recording)) for p in recording.rglob("*")
                  if p.is_file() and p != marker and canary in _unwatched(p, canary))


def _decoy(recording):
    marker = recording / "canary.txt"
    if not marker.exists():
        return None
    canary = marker.read_text().strip()
    checked = [r for r in _stub_rows(recording) if "bearer_matches" in r]
    watched = [r for r in checked if canary in (r.get("mentions") or {})]
    return {"canary": canary, "requests": len(checked),
            "requests_with_the_slot_token": sum(r["bearer_matches"] is True for r in checked),
            "requests_watched_for_the_canary": len(watched),
            "requests_naming_the_canary": sum(any(r["mentions"][canary].values()) for r in watched),
            "files_holding_the_canary": _holding(recording, marker, canary)}


def _unwatched(path, canary):
    """A file's text without the stub's own use of the canary as a watched name (a count's key)."""
    text = path.read_text(errors="replace")
    return text.replace(json.dumps(canary) + ": {", "") if path.name == "stub.jsonl" else text


def trace(recording, source):
    recording = Path(recording)
    paths, execs = {}, []
    files = sorted(f for f in recording.glob("strace.*") if f.suffix[1:].isdigit() or f.name == "strace.cli")
    lines = [line for f in files for line in f.read_text(errors="replace").splitlines()]
    tree = _cli_tree(lines)
    pending = {}
    for line in tree[0] if tree else lines:
        _trace_line(line, paths, execs, pending)
    for (_, call), path in pending.items():
        _outcome(paths, path, call, None)
    decoy = _decoy(recording)
    return {"source": source, "traced_processes": tree[1] if tree else len(files),
            "cli_started_in_trace": tree is not None, "paths": dict(sorted(paths.items())),
            "execs": sorted(set(execs)), **({"decoy": decoy} if decoy else {})}


def _tool_errors(trial):
    stream = trial / "agent" / "claude-code.txt"
    events = [json.loads(line) for line in stream.read_text().splitlines() if line.startswith("{")]
    blocks = [b for e in events if e.get("type") == "user" for b in (e.get("message") or {}).get("content") or []]
    return sorted({b["content"] for b in blocks if isinstance(b, dict) and isinstance(b.get("content"), str)
                   and b["content"].startswith("<tool_use_error>")})


def after_limit(trial, log, source):
    """What the CLI did after the harness ended its agent phase (D4, a slot's lifetime)."""
    trial = Path(trial)
    finished = json.loads((trial / "result.json").read_text())["agent_execution"]["finished_at"]
    end = datetime.datetime.fromisoformat(finished.replace("Z", "+00:00")).timestamp()
    rows = [json.loads(line) for line in Path(log).read_text().splitlines() if line.strip()]
    after = [r for r in rows if r.get("time", 0) > end]
    return {"source": source, "agent_phase_finished_at": finished, "requests": len(rows),
            "requests_after_the_agent_phase": len(after),
            "last_request_after_s": round(after[-1]["time"] - end, 1) if after else None,
            "statuses_after": sorted({r.get("status") for r in after}),
            "bearer_matches_after": sorted({r["bearer_matches"] for r in after if "bearer_matches" in r}),
            "cli_tool_errors": _tool_errors(trial)}


def _number(value):
    return str(int(value)) if float(value).is_integer() else str(value)


def _pairs(flag, items):
    return [a for k, v in items for a in (flag, f"{k}={_number(v) if isinstance(v, float) else v}")]


def _multiplier(config, key):
    return [f"--{key.replace('_', '-')}", _number(config[key])] if key in config else []


def harbor_args(config):
    """The harness arguments a trial ran with, read back from its config.json (record.sh's own arguments,
    model and base URL, are left out)."""
    agent = config.get("agent") or {}
    kwargs = dict(agent.get("kwargs") or {})
    effort = kwargs.pop("reasoning_effort", None)
    args = ["--agent", agent.get("name", "oracle"), *_multiplier(config, "agent_setup_timeout_multiplier"),
            *_pairs("--ak", kwargs.items()), *_pairs("--ae", (agent.get("env") or {}).items())]
    args += ["--disable-verification"] if (config.get("verifier") or {}).get("disable") else []
    args += _multiplier(config, "agent_timeout_multiplier")
    return " ".join(args + (["--effort", effort] if effort else []))


def _text(data):
    text = json.dumps(data, indent=1)
    text = re.sub(r"/home/(?!claude/)[^/\"\s]+", "<home>", text)  # /home/claude: the CLI's own container path
    text = re.sub(r"\blh-fake-slot-[0-9a-f]+", "<fake slot token>", text)
    return re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "<address>", text) + "\n"


def _write(data, out):
    Path(out).write_text(_text(data))


def _placeholders(texts):
    """`texts` with each distinct VENDOR_IDS match replaced, in every text alike, by a placeholder of its shape."""
    seen = {}

    def placeholder(found):
        value = found.group(0)
        if value not in seen:
            number, prefix = str(len(seen) + 1), f"{found.group(1)}_" if found.group(1) else "00000000-0000-0000-0000-"
            seen[value] = prefix + number.rjust(len(value) - len(prefix), "0")
        return seen[value]
    return [VENDOR_IDS.sub(placeholder, text) for text in texts]


def passthrough_log(log, source):
    rows = [json.loads(line) for line in Path(log).read_text().splitlines() if line.strip()]
    start = rows[0]["time"] if rows else None
    return {"source": source, "requests": [{**row, "time": round(row["time"] - start, 1)} for row in rows]}


def live_probe(probe, log, note, out):
    """The live probe's fixtures (plan Task 4): one stream fixture per session, and the passthrough's log."""
    cuts = {}
    for result in sorted(Path(probe).glob("*/jobs/*/*/result.json")):
        effort, trial = result.relative_to(probe).parts[0], result.parent
        config = json.loads((trial / "agent" / "sessions" / ".claude.json").read_text())
        cuts[f"session-{effort}.json"] = {
            **fixture(trial, f"local recording live-probe-{effort} ({note}, effort {effort})"),
            "exported_config": {k: config[k] for k in CONFIG_KEYS if k in config}}
    cuts["passthrough-log.json"] = passthrough_log(log, f"local recording live-probe ({note}; the passthrough's log)")
    for name, text in zip(cuts, _placeholders([_text(data) for data in cuts.values()])):
        (Path(out) / name).write_text(text)


def main(argv):
    if argv[0] == "harbor-args":
        print(harbor_args(json.loads(Path(argv[1]).read_text())))
    elif argv[0] == "after-limit":
        _write(after_limit(Path(argv[1]), argv[2], argv[3]), argv[4])
    elif argv[0] == "live-probe":
        live_probe(Path(argv[1]), argv[2], argv[3], argv[4])
    elif argv[0] in ("requests", "trace"):
        _write((requests if argv[0] == "requests" else trace)(argv[1], argv[2]), argv[3])
    else:
        _write(fixture(Path(argv[0]), argv[1]), argv[2])


if __name__ == "__main__":
    main(sys.argv[1:])
