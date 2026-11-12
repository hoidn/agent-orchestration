"""Token usage read from one provider call's transport stdout.

`usage_from_stdout(metadata_mode, raw_stdout, *, model)` returns

    {"status": "reported", "source": str, "reported_cost_usd": float | None, "complete": bool,
     "rows": [{"model": str | None, "tokens": {"input", "output", "cache_read", "cache_write"}}]}

or `{"status": "unknown", "reason": "no_transport" | "no_usage_event" | "malformed"}`; never zero for
usage it could not read, and never raises. Sources:

- Claude `--output-format stream-json`: the last `result` line's `modelUsage`, one row per model, and
  its `total_cost_usd` (an empty `modelUsage` with a cost keeps the cost, with no rows). Without a
  usable `result` line (a killed, timed-out or terminated turn), the `assistant` lines'
  `message.usage`, once per message id (Claude repeats a message's usage on each of its content-block
  lines; the last wins), with `complete: false`: those rows are a lower bound, since stream-json
  assistant lines carry the output count of the first streamed chunk, not of the finished message.
- Codex `exec --json`: the last `turn.completed` line's `usage`; the model is the call's policy model.
  Charged input is input minus cached and cache-write tokens.

A cut final line (a killed writer) is ignored; any other undecodable line makes usage `malformed`.
`usage_from_stdout` reads nothing but its arguments; `spent` reads a run's `usage.json` files.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from typing import Any, Iterable

from .pricing import cap_cost
from .types import ProviderSessionMetadataMode

UNAVAILABLE = "unavailable"
CLAUDE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
CODEX_FIELDS = ("input_tokens", "output_tokens", "cache_write_input_tokens", "cached_input_tokens")
_MODEL_USAGE_FIELDS = dict(zip(("inputTokens", "outputTokens", "cacheCreationInputTokens", "cacheReadInputTokens"),
                               CLAUDE_FIELDS))
_CLAUDE = ProviderSessionMetadataMode.CLAUDE_STREAM_JSON_STDOUT.value
_CODEX = ProviderSessionMetadataMode.CODEX_EXEC_JSONL_STDOUT.value


class _Malformed(ValueError):
    pass


def _is_int(value: Any) -> bool:
    return type(value) is int and value >= 0


def known_model(model: Any) -> bool:
    return isinstance(model, str) and bool(model.strip()) and model.lower() not in {
        UNAVAILABLE, "unknown", "default", "auto"}


def claude_message_rows(entries: Iterable[dict]) -> list[dict]:
    """One row per assistant message (`model` plus CLAUDE_FIELDS); a missing field is "unavailable".

    Claude Code writes one line per content block, repeating the message id and usage, so rows are keyed by
    `message.id` and the last line of a message wins.
    """
    rows: dict[Any, dict] = {}
    for n, entry in enumerate(entries):
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") if isinstance(entry.get("message"), dict) else {}
        usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
        key = message.get("id", n)
        rows[key if isinstance(key, (str, int)) else n] = {"model": message.get("model", UNAVAILABLE),
                                      **{k: usage[k] if _is_int(usage.get(k)) else UNAVAILABLE
                                         for k in CLAUDE_FIELDS}}
    return list(rows.values())


def charge_tokens(provider: str, usage: dict, model: str) -> dict | str:
    """The four charged counts of one native usage row, or "unavailable" for an unknown model or bad counter."""
    fields = CLAUDE_FIELDS if provider == "claude" else CODEX_FIELDS
    required = (*fields, "total_tokens") if provider == "codex" else fields
    if not known_model(model) or not all(_is_int(usage.get(key)) for key in required):
        return UNAVAILABLE
    if any(key.endswith("_tokens") and not _is_int(value) for key, value in usage.items()):
        return UNAVAILABLE
    if provider == "claude":
        return dict(input=usage[fields[0]], output=usage[fields[1]],
                    cache_write=usage[fields[2]], cache_read=usage[fields[3]])
    return codex_charge_tokens(usage)


def codex_charge_tokens(usage: dict) -> dict | str:
    """Charged Codex counts; `total_tokens` decides whether cache-write is inside input.

    `turn.completed` reports no total; it is then taken as input plus output (cache-write inside input).
    """
    input_tokens, cache_read, cache_write = (usage["input_tokens"], usage["cached_input_tokens"],
                                              usage["cache_write_input_tokens"])
    total = usage.get("total_tokens", input_tokens + usage["output_tokens"])
    if total == input_tokens + usage["output_tokens"]:
        charged_input = input_tokens - cache_read - cache_write
    elif total == input_tokens + cache_write + usage["output_tokens"]:
        charged_input = input_tokens - cache_read
    else:
        return UNAVAILABLE
    if charged_input < 0:
        return UNAVAILABLE
    return dict(input=charged_input, output=usage["output_tokens"],
                cache_write=cache_write, cache_read=cache_read)


def _events(raw_stdout: bytes) -> list[dict]:
    lines = raw_stdout.split(b"\n")
    events = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        try:
            event = json.loads(line.decode("utf-8"))
        except RecursionError:
            raise _Malformed from None
        except ValueError:
            if index == len(lines) - 1 and line.startswith(b"{"):     # unterminated JSON: the writer was cut off
                break
            raise _Malformed from None
        if not isinstance(event, dict):
            raise _Malformed
        events.append(event)
    return events


def _row(model, tokens) -> dict:
    if tokens == UNAVAILABLE:
        raise _Malformed
    return {"model": model, "tokens": {key: tokens[key] for key in ("input", "output", "cache_read", "cache_write")}}


def _claude(events: list[dict], model: str | None) -> dict | None:
    results = [event for event in events if event.get("type") == "result" and "modelUsage" in event]
    if results and (results[-1]["modelUsage"] or _cost(results[-1]) is not None):
        return _claude_result(results[-1])
    messages = claude_message_rows(events)
    if not messages:
        return None
    totals: dict[str, dict] = {}
    for message in messages:
        row = _row(message["model"], charge_tokens("claude", message, message["model"]))
        into = totals.setdefault(row["model"], dict.fromkeys(row["tokens"], 0))
        for key, value in row["tokens"].items():
            into[key] += value
    return _reported("assistant.message.usage", [{"model": name, "tokens": tokens}
                                                 for name, tokens in totals.items()], None, complete=False)


def _claude_result(result: dict) -> dict:
    per_model = result["modelUsage"]
    if not isinstance(per_model, dict) or not all(isinstance(counts, dict) for counts in per_model.values()):
        raise _Malformed
    rows = []
    for name, counts in per_model.items():
        native = {field: counts.get(key) for key, field in _MODEL_USAGE_FIELDS.items()}
        rows.append(_row(name, charge_tokens("claude", native, name)))
    return _reported("result.modelUsage", rows, _cost(result))


def _cost(result: dict) -> float | None:
    cost = result.get("total_cost_usd")
    return cost if type(cost) in (int, float) else None


def _codex(events: list[dict], model: str | None) -> dict | None:
    completed = [event for event in events if event.get("type") == "turn.completed" and "usage" in event]
    if not completed:
        return None
    usage = completed[-1]["usage"]
    if not isinstance(usage, dict) or not all(_is_int(usage.get(key)) for key in CODEX_FIELDS):
        raise _Malformed
    return _reported("turn.completed.usage", [_row(model, codex_charge_tokens(usage))], None)


def _reported(source: str, rows: list[dict], cost: float | None, *, complete: bool = True) -> dict:
    return {"status": "reported", "source": source, "reported_cost_usd": cost, "complete": complete, "rows": rows}


_READERS = {_CLAUDE: _claude, _CODEX: _codex}


def usage_from_stdout(metadata_mode: str | None, raw_stdout: bytes, *, model: str | None) -> dict:
    """The usage one call's transport stdout reports (module docstring); never raises on bad input."""
    reader = _READERS.get(metadata_mode)
    if reader is None:
        return {"status": "unknown", "reason": "no_transport"}
    try:
        usage = reader(_events(raw_stdout), model)
    except _Malformed:
        return {"status": "unknown", "reason": "malformed"}
    return usage or {"status": "unknown", "reason": "no_usage_event"}


def spent(run_root: Path, table: dict, *, in_flight: frozenset[str] = frozenset()) -> tuple[float, list[str]]:
    """The cap's figure for the run's provider attempts (`pricing.cap_cost`), and the attempts whose spend is unknown.

    A provider attempt is an `effects/<sha>/attempt-<n>/` directory holding a regular `prompt.txt`.
    Every attempt with a regular `usage.json` is counted; one whose usage is unknown, incomplete or
    unpriced is listed, never counted as zero. An attempt without `usage.json` is skipped only when it
    is in `in_flight` (run-relative directories still running), else listed. A `usage.json` that is not
    a regular file reads as unknown. Symbolic links are never followed.
    """
    total, unmetered = 0.0, []
    for attempt in _attempt_dirs(Path(run_root)):
        relative = attempt.relative_to(run_root).as_posix()
        usage = _regular_json(attempt / "usage.json")
        if usage is _ABSENT and relative in in_flight:
            continue
        cost = None if usage is _ABSENT else cap_cost(usage, table)
        if cost is None:
            unmetered.append(relative)
        else:
            total += cost
    return total, unmetered


_ABSENT = object()


def _attempt_dirs(run_root: Path) -> list[Path]:
    attempts = []
    for effect in _real_dirs(run_root / "effects"):
        attempts.extend(path for path in _real_dirs(effect)
                        if path.name.startswith("attempt-") and _is_regular(path / "prompt.txt"))
    return sorted(attempts)


def _real_dirs(path: Path) -> list[Path]:
    try:
        with os.scandir(path) as entries:
            return [Path(entry.path) for entry in entries if entry.is_dir(follow_symlinks=False)]
    except OSError:
        return []


def _is_regular(path: Path) -> bool:
    try:
        return stat.S_ISREG(os.lstat(path).st_mode)
    except OSError:
        return False


def _regular_json(path: Path) -> Any:
    """The parsed file, `_ABSENT` when there is none, or None when it is not a readable regular JSON file."""
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except FileNotFoundError:
        return _ABSENT
    except OSError:
        return None
    if not stat.S_ISREG(os.fstat(descriptor).st_mode):      # checked before `fdopen`, which raises on a directory
        os.close(descriptor)
        return None
    with os.fdopen(descriptor, "rb") as stream:
        try:
            return json.loads(stream.read().decode("utf-8"))
        except (OSError, ValueError, RecursionError):
            return None
