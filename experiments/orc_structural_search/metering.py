"""Provider consumption receipts for one comparison run (design: orc_structural_search_driver.md,
"Metering And Consumption").

Reads, never writes: Claude session JSONL (`~/.claude/projects/<slug>*/**/*.jsonl`, found by
`experiments.compare.scan.claude_sessions`), Codex rollouts (`~/.codex/sessions/**/*.jsonl`) and the
shim's `calls/<n>/prompt.txt` records. A figure without a receipt is the string "unavailable", never 0.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

from experiments.compare import scan
from experiments.orc_structural_search import pricing

UNAVAILABLE = "unavailable"
CLAUDE_FIELDS = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def _lines(path: Path) -> Iterator[dict]:
    for line in path.read_text().splitlines():
        if line.strip():
            yield json.loads(line)


def _is_int(value: Any) -> bool:
    return type(value) is int and value >= 0


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
    """One row per rollout (`rollout` plus the raw token fields of its last cumulative token event).

    The recognized event is the shape observed in local rollouts (2026-10-18):
    `{"type": "event_msg", "payload": {"type": "token_count", "info": {"total_token_usage": {...}}}}`.
    Summing `last_token_usage` overcounts (events repeat), so the cumulative total is read. `rollout_dir` may
    also be one rollout file. Returns "unavailable" when no such event is found.
    """
    paths = [rollout_dir] if rollout_dir.is_file() else sorted(rollout_dir.rglob("*.jsonl"))
    rows = [{"rollout": str(path), **total} for path in paths if (total := _last_total(path))]
    return rows or UNAVAILABLE


def _last_total(rollout: Path) -> dict | None:
    """The final cumulative event wins even when malformed; never recover an older total."""
    return _last_native_total(list(_lines(rollout)))


def _last_native_total(entries):
    total = None
    for entry in entries:
        payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
        if entry.get("type") == "event_msg" and payload.get("type") == "token_count":
            total = _total_token_usage(entry)
    return total


def _total_token_usage(entry: dict) -> dict | None:
    payload = entry.get("payload") if isinstance(entry.get("payload"), dict) else {}
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    usage = info.get("total_token_usage")
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
    message = entry.get("message")
    return _text(message.get("content")) if entry.get("type") == "user" and isinstance(message, dict) else []


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
    return {t.strip() for entry in _native_entries(session)[0] for t in read(entry)}


def _native_entries(path):
    entries = []
    try:
        for entry in _lines(path):
            if not isinstance(entry, dict):
                return entries, False
            entries.append(entry)
            if entry.get("type") in {"user", "assistant"} and not isinstance(entry.get("message"), dict):
                return entries, False
    except (OSError, ValueError, TypeError):
        return entries, False
    return entries, True


def _hash(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _known_model(model: Any) -> bool:
    return isinstance(model, str) and bool(model.strip()) and model.lower() not in {
        UNAVAILABLE, "unknown", "default", "auto"}


def _charge_tokens(provider: str, usage: dict, model: str) -> dict | str:
    fields = (CLAUDE_FIELDS if provider == "claude" else
              ("input_tokens", "output_tokens", "cache_write_input_tokens", "cached_input_tokens"))
    required = (*fields, "total_tokens") if provider == "codex" else fields
    if not _known_model(model) or not all(_is_int(usage.get(key)) for key in required):
        return UNAVAILABLE
    if any(key.endswith("_tokens") and not _is_int(value) for key, value in usage.items()):
        return UNAVAILABLE
    if provider == "claude":
        return dict(input=usage[fields[0]], output=usage[fields[1]],
                    cache_write=usage[fields[2]], cache_read=usage[fields[3]])
    return _codex_charge_tokens(usage)


def _codex_charge_tokens(usage: dict) -> dict | str:
    input_tokens, cache_read, cache_write = (usage["input_tokens"], usage["cached_input_tokens"],
                                              usage["cache_write_input_tokens"])
    total = usage["total_tokens"]
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


def _claude_rows(session: Path) -> list[dict]:
    messages = {}
    entries, complete = _native_entries(session)
    digest = _hash(session)
    for n, entry in enumerate(entries):
        if entry.get("type") == "assistant":
            message = entry.get("message")
            message = message if isinstance(message, dict) else {"usage": {"raw_message": message}}
            messages[message.get("id", n)] = message
    rows = []
    for message in messages.values():
        usage, model = message.get("usage") or {}, message.get("model", UNAVAILABLE)
        usage = usage if isinstance(usage, dict) else {"raw_usage": usage}
        charge = _charge_tokens("claude", usage, model) if message.get("id") and complete else UNAVAILABLE
        rows.append({**usage, "model": model, "charge_tokens": charge,
                     "provenance": {"session_sha256": digest, "message_id": message.get("id", UNAVAILABLE),
                                    "model_source": "message.model", "counter_source": "message.usage",
                                    "complete_native_transcript": complete}})
    return rows or [{"model": UNAVAILABLE, "charge_tokens": UNAVAILABLE,
                     "provenance": {"session_sha256": digest, "counter_source": "missing_message_usage"}}]


def _argv_model(call: Path) -> str:
    path = call / "argv.nul"
    if not path.is_file():
        return UNAVAILABLE
    args = _model_args(path.read_bytes().decode().split("\0"))
    if args is None:
        return UNAVAILABLE
    models = [arg.split("=", 1)[1] for arg in args if arg.startswith("--model=")]
    models.extend(args[n + 1] for n, arg in enumerate(args[:-1]) if arg in {"--model", "-m"})
    return models[0] if len(models) == 1 and _known_model(models[0]) else UNAVAILABLE


def _model_args(args):
    args = args[:args.index("--")] if "--" in args else args
    if any(re.search(r"(?:^|=)\s*model(?:_provider)?\s*=", arg) for arg in args):
        return None
    return args


def _context_model(entry):
    payload = entry.get("payload")
    model = payload.get("model") if isinstance(payload, dict) else None
    return model if _known_model(model) else UNAVAILABLE


def _codex_rows(session: Path, call: Path) -> list[dict]:
    entries, complete = _native_entries(session)
    usage = _last_native_total(entries)
    if usage is None:
        return []
    contexts = [_context_model(entry) for entry in entries if entry.get("type") == "turn_context"]
    models = set(contexts)
    model = next(iter(models)) if len(models) == 1 else UNAVAILABLE
    source = "turn_context.model"
    if not contexts:
        model, source = _argv_model(call), "shim.argv"
    if not _known_model(model):
        model = UNAVAILABLE
    return [{**usage, "model": model, "charge_tokens": _charge_tokens("codex", usage, model) if complete else UNAVAILABLE,
             "provenance": {"session_sha256": _hash(session), "model_source": source,
                            "counter_source": "last_total_token_usage", "complete_native_transcript": complete}}]


def _call_usage(call: Path, provider: str, session: Path, sessions: Sequence[Path]) -> dict:
    files = [session, *(p for p in sessions if session.with_suffix("") in p.parents)]
    usage = ([row for path in files for row in _claude_rows(path)] if provider == "claude"
             else _codex_rows(session, call))
    complete = bool(usage) and all(row["charge_tokens"] != UNAVAILABLE for row in usage)
    return {"call_id": call.name, "provider": provider, "usage": usage,
            "status": "complete" if complete else UNAVAILABLE,
            "reason": None if complete else "missing_or_invalid_model_counters"}


def _check_model_join(receipt, group):
    if len(group) < 2 or len({_argv_model(call) for call in group}) == 1:
        return receipt
    for row in receipt["usage"]:
        if row["provenance"].get("model_source") == "shim.argv":
            row.update(model=UNAVAILABLE, charge_tokens=UNAVAILABLE)
            receipt.update(status=UNAVAILABLE, reason="ambiguous_argv_model_join")
    return receipt


def _prompt(call: Path) -> str:
    path = call / "prompt.txt"
    return path.read_text().strip() if path.is_file() else ""


def _provider_hint(call: Path) -> str | None:
    path = call / "provider.txt"
    return path.read_text().strip() if path.is_file() else None


def coverage(records_dir: Path, *, claude_sessions: Sequence[Path], codex_rollouts: Sequence[Path],
             session_paths: list[str] | None = None) -> dict:
    """Join complete shim prompts one to one with native user turns; preserve per-model raw evidence."""
    calls = sorted((records_dir / "calls").glob("*"), key=lambda p: int(p.name))
    candidates = [("claude", s) for s in claude_sessions if s.parent.name != "subagents"]
    candidates += [("codex", r) for r in codex_rollouts]
    matched, unmatched, usage = _match_calls(calls, candidates, claude_sessions, session_paths)
    return {"calls": len(calls), "unmatched_calls": unmatched, "receipt_usage": usage,
            **{provider: _provider_report(tokens, unmatched) for provider, tokens in matched.items()}}


def _holders(candidates, texts, hint, prompt):
    holders = [c for c in candidates if prompt and prompt in texts[c] and (hint is None or c[0] == hint)]
    return [] if hint is None and len({provider for provider, _ in holders}) > 1 else holders


def _match_calls(calls, candidates, claude_sessions, session_paths=None):
    texts = {c: _user_texts(*c) for c in candidates}
    by_prompt = {}
    for call in calls:
        by_prompt.setdefault((_provider_hint(call), _prompt(call)), []).append(call)
    matched, claimed, usage, unmatched = {"claude": [], "codex": []}, set(), [], 0
    for (hint, prompt), group in by_prompt.items():
        holders = _holders(candidates, texts, hint, prompt)
        if len(holders) != len(group) or claimed.intersection(holders):
            unmatched += len(group)
            usage.extend({"call_id": call.name, "provider": hint or UNAVAILABLE, "status": UNAVAILABLE,
                          "usage": UNAVAILABLE, "reason": "unmatched_or_ambiguous_session"} for call in group)
            continue
        claimed.update(holders)
        if session_paths is not None:
            session_paths.extend(str(path) for _, path in holders)
        for call, (provider, path) in zip(group, holders):
            receipt = _check_model_join(_call_usage(call, provider, path, claude_sessions), group)
            usage.append(receipt)
            tokens = _receipt_tokens(receipt)
            matched[provider].append(tokens)
    return matched, unmatched, sorted(usage, key=lambda row: int(row["call_id"]))


def _receipt_tokens(receipt: dict) -> int | str:
    if receipt["status"] != "complete":
        return UNAVAILABLE
    if receipt["provider"] == "codex":
        totals = [row.get("total_tokens") for row in receipt["usage"]]
        return sum(totals) if all(_is_int(total) for total in totals) else UNAVAILABLE
    return sum(sum(row["charge_tokens"].values()) for row in receipt["usage"])


def _provider_report(tokens: list[int | str], unmatched: int) -> dict:
    receipts = [t for t in tokens if _is_int(t)]
    complete = tokens and not unmatched and len(receipts) == len(tokens)
    return {"calls": len(tokens), "calls_with_receipts": len(receipts),
            "tokens": sum(receipts) if complete else UNAVAILABLE,
            # The shim records no per-call timing; only run-level wall clock has a receipt
            # (recorded by the evaluation records).
            "wall_clock_sec": UNAVAILABLE}


def _scoped_sessions(tree, since, home):
    claude = [path for path in scan.claude_sessions(tree, home) if path.stat().st_mtime >= since]
    codex = []
    for path in sorted((home / ".codex" / "sessions").glob("*/*/*/rollout-*.jsonl")):
        if path.stat().st_mtime >= since:
            cwd = scan.codex_cwd(path)
            if cwd and Path(cwd).is_relative_to(tree):
                codex.append(path)
    return claude, codex


def receipts(records_dir: Path, *, tree: Path, since: float, home: Path) -> dict:
    """Scoped native receipts; absent, ambiguous or incomplete coverage remains unavailable."""
    unavailable = {"consumption": UNAVAILABLE, "receipt_usage": UNAVAILABLE, "native_session_paths": UNAVAILABLE}
    paths: list[str] = []
    try:
        claude, codex = _scoped_sessions(tree, since, home)
        report = coverage(records_dir, claude_sessions=claude, codex_rollouts=codex, session_paths=paths)
    except (OSError, ValueError, TypeError, KeyError):
        # A timeout can leave a partial native JSONL; consumption never prevents settling the attempt.
        return unavailable
    known = sorted(paths) if paths else UNAVAILABLE
    if not report["calls"] or report["unmatched_calls"] or any(
            report[provider]["calls"] and report[provider]["tokens"] == UNAVAILABLE
            for provider in ("claude", "codex")):
        return {"consumption": UNAVAILABLE, "receipt_usage": report["receipt_usage"], "native_session_paths": known}
    return {"consumption": report, "receipt_usage": report["receipt_usage"], "native_session_paths": known}


_BUDGET_KINDS = ("episode", "evaluation", "judge")


def _budget_path(value: Any) -> str | None:
    if isinstance(value, (str, Path)) and str(value).strip() not in {"", UNAVAILABLE}:
        return str(Path(value).resolve())
    return None


def _budget_key(row: Mapping, position: int) -> tuple:
    if path := _budget_path(row.get("records_dir")):
        return "records", path
    if key := row.get("_budget_identity"):
        return "source", str(key)
    identity = next((row[key] for key in ("evaluation_id", "episode_id", "run_id") if row.get(key)), position)
    return "row", row.get("kind"), str(identity)


def _judge_work(judge_pools: Sequence[Path]) -> list[dict]:
    work, seen = [], set()
    for value in judge_pools:
        pool = Path(value).resolve()
        if pool in seen:
            continue
        seen.add(pool)
        mapping_path = pool / "records" / "mapping.json"
        try:
            mapping = json.loads(mapping_path.read_text())
            judges = mapping.get("judges") if isinstance(mapping, dict) else None
            if not isinstance(judges, dict) or not judges:
                raise ValueError("missing_judge_mapping")
        except (OSError, ValueError, TypeError) as error:
            work.append({"kind": "judge", "_budget_identity": mapping_path,
                         "_unknown_reason": f"missing_or_invalid_judge_mapping: {type(error).__name__}"})
            continue
        for name in judges:
            record_path = pool / "records" / "judges" / str(name) / "record.json"
            try:
                work.append(_read_judge_record(pool, name))
            except (OSError, ValueError, TypeError) as error:
                work.append({"kind": "judge", "_budget_identity": record_path,
                             "_unknown_reason": f"missing_or_invalid_judge_record: {type(error).__name__}"})
    return work


def _read_judge_record(pool: Path, name: str) -> dict:
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError("invalid_judge_name")
    records_dir = pool / "records" / "judges" / name
    record = json.loads((records_dir / "record.json").read_text())
    if (not isinstance(record, dict) or record.get("kind") != "judge" or
            _budget_path(record.get("records_dir")) != str(records_dir.resolve())):
        raise ValueError("invalid_judge_record")
    return record


def _latest_budget_work(rows: Sequence[Mapping], judge_pools: Sequence[Path]) -> list[dict]:
    latest = {}
    for position, row in enumerate([*rows, *_judge_work(judge_pools)]):
        if isinstance(row, Mapping) and row.get("kind") in _BUDGET_KINDS:
            latest[_budget_key(row, position)] = dict(row)
    return list(latest.values())


def _unpriced(row: Mapping, reason: str) -> dict:
    return {"kind": row.get("kind"), "records_dir": row.get("records_dir", UNAVAILABLE), "reason": reason}


def _sum_or_unavailable(total: int | float, known: bool) -> int | float | str:
    return total if known and pricing.number(total) else UNAVAILABLE


def _budget_receipts(row: Mapping, records_dir: str | None, known: dict, kinds: dict) -> None:
    raw = row.get("receipt_usage")
    if not isinstance(raw, list) or records_dir is None:
        return
    for receipt in raw:
        if not isinstance(receipt, Mapping) or not isinstance(receipt.get("call_id"), str) or not receipt["call_id"]:
            continue
        identity = (records_dir, receipt["call_id"])
        if identity in known and known[identity] != receipt:
            raise ValueError(f"conflicting duplicate receipt for {identity}")
        known.setdefault(identity, receipt)
        kinds.setdefault(identity, row["kind"])


def _budget_row(row: Mapping, details: dict, price_table: Mapping, receipts: dict, receipt_kinds: dict) -> None:
    kind, result = row["kind"], details[row["kind"]]
    if reason := row.get("_unknown_reason"):
        result["calls_known"] = result["time_known"] = result["cost_known"] = False
        result["unpriced_work"].append(_unpriced(row, reason))
        return
    calls, seconds = row.get("provider_calls"), row.get("wall_clock_sec")
    if type(calls) is int and calls >= 0:
        result["calls"] += calls
    else:
        result["calls_known"] = False
    if pricing.number(seconds):
        result["wall_clock_sec"] += seconds
    else:
        result["time_known"] = False
    records_dir = _budget_path(row.get("records_dir"))
    _budget_receipts(row, records_dir, receipts, receipt_kinds)
    reason = ("incomplete_receipt_coverage" if not pricing.complete_coverage(calls, row.get("receipt_usage"))
              else "missing_records_dir" if records_dir is None else None)
    if reason is None:
        cost = pricing.cost({"provider_calls": calls, "receipt_usage": row["receipt_usage"]}, price_table)
        reason = "unpriced_receipt" if cost == UNAVAILABLE else None
        if reason is None:
            result["metered_cost"] += cost
    if reason:
        result["cost_known"] = False
        result["unpriced_work"].append(_unpriced(row, reason))


def _budget_summary(details: dict, receipts: Mapping, receipt_kinds: Mapping) -> dict:
    for identity, kind in receipt_kinds.items():
        details[kind]["receipts"] += 1
    result = {kind: {"calls": _sum_or_unavailable(values["calls"], values["calls_known"]),
                     "wall_clock_sec": _sum_or_unavailable(values["wall_clock_sec"], values["time_known"]),
                     "metered_cost": _sum_or_unavailable(values["metered_cost"], values["cost_known"]),
                     "receipts": values["receipts"], "unpriced_work": values["unpriced_work"]}
              for kind, values in details.items()}
    unknown_calls = any(not values["calls_known"] for values in details.values())
    unknown_time = any(not values["time_known"] for values in details.values())
    unpriced = [entry for values in details.values() for entry in values["unpriced_work"]]
    totals = {key: sum(values[key] for values in details.values()) for key in ("calls", "wall_clock_sec", "metered_cost")}
    return {"calls": _sum_or_unavailable(totals["calls"], not unknown_calls),
            "wall_clock_sec": _sum_or_unavailable(totals["wall_clock_sec"], not unknown_time),
            "metered_cost": _sum_or_unavailable(totals["metered_cost"], not unpriced),
            "receipts": len(receipts), "unpriced_work": unpriced, "by_kind": result}


def budget_union(rows: Sequence[Mapping], judge_pools: Sequence[Path], price_table: Mapping) -> dict:
    """Union saved campaign and judge evidence by records directory; never re-read native sessions."""
    pricing.validate(price_table)
    work = _latest_budget_work(rows, judge_pools)
    details = {kind: {"calls": 0, "calls_known": True, "wall_clock_sec": 0, "time_known": True,
                      "metered_cost": 0, "cost_known": True, "receipts": 0, "unpriced_work": []}
               for kind in _BUDGET_KINDS}
    receipts, receipt_kinds = {}, {}
    for row in work:
        _budget_row(row, details, price_table, receipts, receipt_kinds)
    return _budget_summary(details, receipts, receipt_kinds)
