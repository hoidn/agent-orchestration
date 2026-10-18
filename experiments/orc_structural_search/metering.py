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
    rows = []
    for path in paths:
        total = None
        for entry in _lines(path):
            payload = entry.get("payload") or {}
            usage = (payload.get("info") or {}).get("total_token_usage") if isinstance(payload, dict) else None
            if entry.get("type") == "event_msg" and payload.get("type") == "token_count" and isinstance(usage, dict):
                total = {k: v for k, v in usage.items() if _is_int(v)} or total
        if total:
            rows.append({"rollout": str(path), **total})
    return rows or UNAVAILABLE


def _strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def _has_prompt(session: Path, prompt: str) -> bool:
    return any(text.strip() == prompt for entry in _lines(session) for text in _strings(entry))


def _claude_tokens(session: Path, sessions: Sequence[Path]) -> int | str:
    """The session's tokens plus those of its subagent files (`<session id>/subagents/*.jsonl`)."""
    files = [session, *(p for p in sessions if session.with_suffix("") in p.parents)]
    rows = [row for path in files for row in claude_usage(path)]
    values = [row[k] for row in rows for k in CLAUDE_FIELDS]
    return sum(values) if rows and all(_is_int(v) for v in values) else UNAVAILABLE


def _codex_tokens(rollout: Path) -> int | str:
    rows = codex_usage(rollout)
    return rows[0].get("total_tokens", UNAVAILABLE) if rows != UNAVAILABLE else UNAVAILABLE


def _wall_clock(calls: list[Path]) -> float | str:
    """Summed `wall_clock_sec` of each call's `timing.json`; the shim writes none, so usually "unavailable"."""
    timings = [call / "timing.json" for call in calls]
    if not calls or not all(t.is_file() for t in timings):
        return UNAVAILABLE
    values = [json.loads(t.read_text()).get("wall_clock_sec") for t in timings]
    return sum(values) if all(isinstance(v, (int, float)) for v in values) else UNAVAILABLE


def coverage(records_dir: Path, *, claude_sessions: Sequence[Path], codex_rollouts: Sequence[Path]) -> dict:
    """Join each shim call to the one native session whose user text equals its prompt, per provider.

    A call matches the first not-yet-matched session (Claude top-level sessions, then Codex rollouts) holding
    a string equal to its stripped `prompt.txt`, so identical prompts pair one to one. Tokens are an int only
    when no call is unmatched and every matched call of that provider has a complete receipt.
    """
    calls = sorted((records_dir / "calls").glob("*"), key=lambda p: int(p.name))
    candidates = [("claude", s) for s in claude_sessions if s.parent.name != "subagents"]
    candidates += [("codex", r) for r in codex_rollouts]
    matched: dict[str, list[tuple[Path, int | str]]] = {"claude": [], "codex": []}
    unmatched = 0
    for call in calls:
        prompt = (call / "prompt.txt").read_text().strip()
        hit = next((c for c in candidates if prompt and _has_prompt(c[1], prompt)), None)
        if hit is None:
            unmatched += 1
            continue
        candidates.remove(hit)
        provider, path = hit
        tokens = _claude_tokens(path, claude_sessions) if provider == "claude" else _codex_tokens(path)
        matched[provider].append((call, tokens))
    report: dict[str, Any] = {"calls": len(calls), "unmatched_calls": unmatched}
    for provider, pairs in matched.items():
        receipts = [t for _, t in pairs if _is_int(t)]
        complete = pairs and not unmatched and len(receipts) == len(pairs)
        report[provider] = {"calls": len(pairs), "calls_with_receipts": len(receipts),
                            "tokens": sum(receipts) if complete else UNAVAILABLE,
                            "wall_clock_sec": _wall_clock([c for c, _ in pairs])}
    return report
