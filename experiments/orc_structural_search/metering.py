"""Provider consumption receipts for one comparison run (design: orc_structural_search_driver.md,
"Metering And Consumption").

Reads, never writes: Claude session JSONL (`~/.claude/projects/<slug>*/**/*.jsonl`, found by
`experiments.compare.scan.claude_sessions`), Codex rollouts (`~/.codex/sessions/**/*.jsonl`) and the
shim's `calls/<n>/prompt.txt` records. A figure without a receipt is the string "unavailable", never 0.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any

UNAVAILABLE = "unavailable"
CLAUDE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def _lines(path: Path) -> Iterator[dict]:
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def claude_usage(session_jsonl: Path) -> list[dict]:
    """One row per assistant message (`model` plus CLAUDE_FIELDS); a missing field is "unavailable".

    Claude Code writes one line per content block, repeating the message id and usage, so rows are keyed by
    `message.id` and the last line of a message wins.
    """
    rows: dict[Any, dict] = {}
    for n, entry in enumerate(_lines(session_jsonl)):
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        usage = message.get("usage") or {}
        rows[message.get("id", n)] = {"model": message.get("model", UNAVAILABLE),
                                      **{k: usage[k] if _is_int(usage.get(k)) else UNAVAILABLE
                                         for k in CLAUDE_FIELDS}}
    return list(rows.values())


def codex_usage(rollout_dir: Path) -> list[dict] | str:
    """One row per rollout (`rollout` plus the integer token fields of its last cumulative token event).

    The recognized event is the shape observed in local rollouts (2026-10-18):
    `{"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {...}}}}`.
    Summing `last_token_usage` overcounts (events repeat), so the cumulative total is read. `rollout_dir` may
    also be one rollout file. Returns "unavailable" when no such event is found.
    """
    paths = [rollout_dir] if rollout_dir.is_file() else sorted(rollout_dir.rglob("*.jsonl"))
    rows = [{"rollout": str(path), **total} for path in paths if (total := _last_total(path))]
    return rows or UNAVAILABLE


def _last_total(rollout: Path) -> dict | None:
    """The integer fields of the rollout's last cumulative token event, or None."""
    total = None
    for entry in _lines(rollout):
        usage = _total_token_usage(entry)
        if usage is not None:
            total = {k: v for k, v in usage.items() if _is_int(v)} or total
    return total


def _total_token_usage(entry: dict) -> dict | None:
    payload = entry.get("payload") or {}
    usage = (payload.get("info") or {}).get("total_token_usage") if isinstance(payload, dict) else None
    if entry.get("type") == "event_msg" and payload.get("type") == "token_count" and isinstance(usage, dict):
        return usage
    return None


def _text(content: Any) -> list[str]:
    """A message's text: a string, or the `text` of its text blocks (never tool results)."""
    if isinstance(content, str):
        return [content]
    return [b["text"] for b in content or [] if isinstance(b, dict) and b.get("type") in ("text", "input_text")
            and isinstance(b.get("text"), str)]


def _claude_user_text(entry: dict) -> list[str]:
    return _text((entry.get("message") or {}).get("content")) if entry.get("type") == "user" else []


def _codex_user_text(entry: dict) -> list[str]:
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    if entry.get("type") == "response_item" and payload.get("role") == "user":
        return _text(payload.get("content"))
    if entry.get("type") == "event_msg" and payload.get("type") == "user_message":
        return _text(payload.get("message"))
    return []


_USER_TEXT = {"claude": _claude_user_text, "codex": _codex_user_text}


def _user_texts(provider: str, session: Path) -> set[str]:
    """Stripped user-turn text: Claude `type == "user"` entries; Codex user `response_item`s and `user_message`s."""
    read = _USER_TEXT.get(provider, lambda entry: [])
    return {t.strip() for entry in _lines(session) for t in read(entry)}


def _claude_tokens(session: Path, sessions: Sequence[Path]) -> int | str:
    """The session's tokens plus those of its subagent files (`<session id>/subagents/*.jsonl`)."""
    files = [session, *(p for p in sessions if session.with_suffix("") in p.parents)]
    rows = [row for path in files for row in claude_usage(path)]
    values = [row[k] for row in rows for k in CLAUDE_FIELDS]
    return sum(values) if rows and all(_is_int(v) for v in values) else UNAVAILABLE


def _codex_tokens(rollout: Path) -> int | str:
    rows = codex_usage(rollout)
    return rows[0].get("total_tokens", UNAVAILABLE) if rows != UNAVAILABLE else UNAVAILABLE


def coverage(records_dir: Path, *, claude_sessions: Sequence[Path], codex_rollouts: Sequence[Path]) -> dict:
    """Join each shim call to a native session whose user-turn text equals its stripped `prompt.txt`.

    Calls sharing a prompt pair one to one, in order, with the sessions holding it, but only when the two counts
    are equal and none of those sessions is already claimed; otherwise those calls are unmatched. Tokens are an
    int only when no call is unmatched and every matched call of that provider has a complete receipt.
    """
    calls = sorted((records_dir / "calls").glob("*"), key=lambda p: int(p.name))
    candidates = [("claude", s) for s in claude_sessions if s.parent.name != "subagents"]
    candidates += [("codex", r) for r in codex_rollouts]
    matched, unmatched = _match_calls(calls, candidates, claude_sessions)
    report: dict[str, Any] = {"calls": len(calls), "unmatched_calls": unmatched}
    for provider, tokens in matched.items():
        report[provider] = _provider_report(tokens, unmatched)
    return report


def _match_calls(calls: Sequence[Path], candidates: Sequence[tuple[str, Path]],
                 claude_sessions: Sequence[Path]) -> tuple[dict[str, list[int | str]], int]:
    """(tokens of each matched call per provider, number of unmatched calls); see `coverage`."""
    texts = {c: _user_texts(*c) for c in candidates}
    by_prompt: dict[str, list[Path]] = {}
    for call in calls:
        by_prompt.setdefault((call / "prompt.txt").read_text().strip(), []).append(call)
    matched: dict[str, list[int | str]] = {"claude": [], "codex": []}
    claimed: set = set()
    unmatched = 0
    for prompt, group in by_prompt.items():
        holders = [c for c in candidates if prompt and prompt in texts[c]]
        if len(holders) != len(group) or claimed.intersection(holders):
            unmatched += len(group)
            continue
        claimed.update(holders)
        for provider, path in holders:
            tokens = _claude_tokens(path, claude_sessions) if provider == "claude" else _codex_tokens(path)
            matched[provider].append(tokens)
    return matched, unmatched


def _provider_report(tokens: list[int | str], unmatched: int) -> dict:
    receipts = [t for t in tokens if _is_int(t)]
    complete = tokens and not unmatched and len(receipts) == len(tokens)
    return {"calls": len(tokens), "calls_with_receipts": len(receipts),
            "tokens": sum(receipts) if complete else UNAVAILABLE,
            # The shim records no per-call timing; only run-level wall clock has a receipt
            # (recorded by the evaluation records).
            "wall_clock_sec": UNAVAILABLE}
