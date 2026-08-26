"""Behavioral tests for orchestrator.providers.omp_session (Task 4).

Covered contracts (brief step 4.3 + X5):
- Pinned 256-byte title slot: exact width including LF, v:1, pad spaces, sole
  header immediately after, no later duplicate slot/header.
- Strict per-line JSON: duplicate keys, non-finite numbers, truncated lines,
  empty/whitespace lines, non-UTF-8 bytes all fail.
- Closed session header and the 15-type entry union with base fields.
- Primary selection with OMP resume-arg precedence (header id prefix, then
  basename prefix, then id-after-underscore), case-insensitive, ambiguity fails.
- Graph rules: roots (null/self/missing parent), children sorted by timestamp,
  leaf = last entry, path-to-root with cycle guard.
"""
import json
import os
import shutil

import pytest

from orchestrator._common.safe_tree import SafeTreeError
from orchestrator.prompt_session_chain import read_manifest_bound
from orchestrator.prompt_session import PromptSessionError
from orchestrator.providers.omp_session import (
    KNOWN_ENTRY_TYPES,
    OmpSessionError,
    ParsedJournal,
    SessionEntryRecord,
    SessionHeaderRecord,
    SessionNode,
    TitleSlot,
    build_session_tree,
    parse_journal,
    parse_journal_bytes,
    path_to_root,
    select_primary,
    session_leaf,
    validate_session_graph,
)
from orchestrator.providers.omp_session_manifest import build_session_manifest

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "omp", "sessions")
PRIMARY = "2026-08-23T22-33-31-340Z_11111111-1111-7111-8111-111111111111.jsonl"

TS = "2026-08-23T22:33:31.340Z"


def _slot(updated_at=TS, title="", source=None):
    """Serialize the pinned 256-byte title slot exactly as OMP does."""
    obj = {"type": "title", "v": 1, "title": title}
    if source is not None:
        obj["source"] = source
    obj["updatedAt"] = updated_at
    obj["pad"] = ""
    base = json.dumps(obj, separators=(",", ":")) + "\n"
    obj["pad"] = " " * (256 - len(base.encode("utf-8")))
    text = json.dumps(obj, separators=(",", ":")) + "\n"
    assert len(text.encode("utf-8")) == 256
    return text


def _header(**overrides):
    header = {
        "type": "session",
        "version": 3,
        "id": "11111111-1111-7111-8111-111111111111",
        "timestamp": TS,
        "cwd": "/workspace",
    }
    header.update(overrides)
    return header


def _entry(entry_type, entry_id, parent, timestamp=TS, **extra):
    entry = {"type": entry_type, "id": entry_id, "parentId": parent, "timestamp": timestamp}
    entry.update(extra)
    return entry


def _journal(*entries, header=None):
    slot = _slot()
    lines = [json.dumps(header if header is not None else _header(), separators=(",", ":"))]
    lines += [json.dumps(entry, separators=(",", ":")) for entry in entries]
    return (slot + "\n".join(lines) + "\n").encode("utf-8")


def _fixture(name):
    with open(os.path.join(FIXTURES, name), "rb") as handle:
        return handle.read()


def _usage(**over):
    usage = {
        "input": 10, "output": 2, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 12,
        "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0},
    }
    usage.update(over)
    return usage


def _assistant_msg(blocks=None, stop="stop", timestamp=1787524425001, **over):
    message = {
        "role": "assistant",
        "content": [{"type": "text", "text": "OK"}] if blocks is None else blocks,
        "api": "openai",
        "provider": "openai-codex",
        "model": "gpt-5.6-sol",
        "stopReason": stop,
        "timestamp": timestamp,
        "usage": _usage(),
    }
    message.update(over)
    return message


def _assistant(entry_id="a1", parent="u1", stop="stop", blocks=None): return _entry(
    "message", entry_id, parent, message=_assistant_msg(blocks=blocks, stop=stop))


def _reject(payload, relpath="s.jsonl"):
    with pytest.raises(OmpSessionError):
        parse_journal_bytes(payload, relpath=relpath)


def _all_fifteen_entries():
    return [
        _entry("message", "k1", None, message={"role": "user", "content": [{"type": "text", "text": "hi"}], "timestamp": 1}),
        _entry("thinking_level_change", "k2", None, thinkingLevel="high", configured=None),
        _entry("model_change", "k3", None, model="openai-codex/gpt-5.6-sol", resolvedModelIsFallback=False),
        _entry("service_tier_change", "k4", None, serviceTier=None),
        _entry("compaction", "k5", None, summary="trimmed", firstKeptEntryId="k1", tokensBefore=1234),
        _entry("branch_summary", "k6", None, fromId="k1", summary="branch done"),
        _entry("custom", "k7", None, customType="metric", data={"x": 1}),
        _entry("custom_message", "k8", None, customType="blocker", content="input needed", display=True),
        _entry("label", "k9", None, targetId="k1", label="keep"),
        _entry("title_change", "k10", None, title="retitled", source="auto"),
        _entry("ttsr_injection", "k11", None, injectedRules=["verify"]),
        _entry("session_init", "k12", None, systemPrompt="sp", task="t", tools=["read"], agent="alpha"),
        _entry("mode_change", "k13", None, mode="auto", data={"reason": "x"}),
        _entry("credential_pin", "k14", None, provider="anthropic", hash="bbbb"),
        _entry("reset_boundary", "k15", None),
    ]


# ------------------------------------------------------------- title slot


def test_parses_golden_primary_fixture():
    journal = parse_journal_bytes(_fixture(PRIMARY), relpath="s.jsonl")
    assert isinstance(journal, ParsedJournal) and journal.relpath == "s.jsonl"
    assert isinstance(journal.title_slot, TitleSlot)
    assert (journal.title_slot.title, journal.title_slot.source) == ("", None)
    assert journal.title_slot.updated_at == "2026-08-23T22:33:31.340Z" and journal.title_slot.pad.strip() == ""
    assert isinstance(journal.header, SessionHeaderRecord)
    assert (journal.header.id, journal.header.version, journal.header.cwd) == (
        "11111111-1111-7111-8111-111111111111", 3, "/workspace")
    assert [entry.type for entry in journal.entries] == ["model_change", "thinking_level_change",
                                                         "message", "message", "credential_pin", "title_change"]
    first = journal.entries[0]
    assert isinstance(first, SessionEntryRecord)
    assert (first.id, first.parent_id, first.timestamp) == ("m1", None, "2026-08-23T22:33:31.926Z")
    assert first.payload["model"] == "openai-codex/gpt-5.6-sol"


def test_title_slot_requires_exactly_256_bytes():
    _reject(_journal()[1:])  # first line now 255 bytes
    _reject(_slot().encode("utf-8")[:-1] + b"xx" + b"\n" + (json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8"))
    payload = (_slot()[:-1] + json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8")  # missing LF
    assert len(payload.split(b"\n", 1)[0]) != 255
    _reject(payload)


def test_title_slot_pad_must_be_spaces():
    obj = {"type": "title", "v": 1, "title": "", "updatedAt": TS, "pad": ""}
    obj["pad"] = " " * (255 - len((json.dumps(obj, separators=(",", ":")) + "\n").encode("utf-8"))) + "x"
    _reject((json.dumps(obj, separators=(",", ":")) + "\n" + json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8"))


def test_title_slot_closed_type_v_and_source():
    header_line = json.dumps(_header(), separators=(",", ":")) + "\n"
    _reject(_slot().encode("utf-8").replace(b'"v":1', b'"v":2') + header_line.encode("utf-8"))
    _reject(header_line.encode("utf-8"))
    parsed = parse_journal_bytes((_slot(source="user") + header_line).encode("utf-8"), relpath="s.jsonl")
    assert parsed.title_slot.source == "user"
    for source in (b'"source":"bogus"', b'"source":null  '):
        _reject(_slot(source="user").encode("utf-8").replace(b'"source":"user"', source) + header_line.encode("utf-8"))
    for slot in (_slot(updated_at=5), _slot(source=[])): _reject((slot + header_line).encode("utf-8"))

def test_multibyte_title_roundtrip():
    slot = _slot(title="h\u00e9llo")
    parsed = parse_journal_bytes((slot + json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8"), relpath="s.jsonl")
    assert parsed.title_slot.title == "h\u00e9llo"


def test_second_title_slot_or_header_rejected():
    _reject((_slot() + json.dumps(_header(), separators=(",", ":")) + "\n" + _slot() + "\n").encode("utf-8"))
    _reject((_slot() + json.dumps(_header(), separators=(",", ":")) + "\n" + json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8"))


def test_empty_file_and_slot_only_rejected():
    _reject(b"")
    _reject(_slot().encode("utf-8"))


# ----------------------------------------------------------------- header


def test_header_closed_keys_and_required():
    for missing in ("id", "timestamp", "cwd"):
        header = _header()
        del header[missing]
        _reject(_journal(_entry("reset_boundary", "r1", None), header=header))
    _reject(_journal(header=_header(unknown=1)))


def test_header_field_rules():
    for header in (_header(timestamp="2026-08-23"),  # not RFC 3339
                   _header(cwd="workspace"), _header(version="3"), _header(version=True),
                   _header(titleSource="bogus"), _header(titleSource=[]), _header(additionalDirectories="x")):
        _reject(_journal(header=header))


def test_header_optional_fields_admitted():
    header = _header(title="t", titleSource="auto", parentSession="p", providerPromptCacheKey="k",
                     additionalDirectories=["/x"], previousSessionFiles=["a.jsonl"])
    journal = parse_journal_bytes(_journal(header=header), relpath="s.jsonl")
    assert journal.header.title == "t"
    assert (journal.header.additional_directories, journal.header.previous_session_files) == (("/x",), ("a.jsonl",))


def test_header_only_journal_parses_with_zero_entries():
    journal = parse_journal_bytes(_fixture("header-only.jsonl"), relpath="h.jsonl")
    assert journal.entries == ()


# ---------------------------------------------------------------- entries


def test_all_fifteen_entry_types_admitted():
    journal = parse_journal_bytes(_journal(*_all_fifteen_entries()), relpath="s.jsonl")
    types = {entry.type for entry in journal.entries}
    assert types == KNOWN_ENTRY_TYPES
    assert len(KNOWN_ENTRY_TYPES) == 15
    assert len(journal.entries) == 15


def test_unknown_entry_type_rejected():
    for kind in ("bogus_type", ["message"]): _reject(_journal(_entry(kind, "x1", None)))

def test_entry_closed_keys_and_base_fields():
    _reject(_journal(_entry("model_change", "m1", None, model="a/b", mystery=1)))
    for entry in (_entry("model_change", "", None, model="a/b"),
                  _entry("model_change", "m1", 5, model="a/b"),
                  _entry("model_change", "m1", None, model="a/b", timestamp="yesterday"),
                  _entry("title_change", "t1", None, title="t", source=[])):
        _reject(_journal(entry))


def test_label_requires_string_when_present():
    parse_journal_bytes(_journal(_entry("label", "l1", None, targetId="k1", label="keep")), relpath="s.jsonl")
    parse_journal_bytes(_journal(_entry("label", "l1", None, targetId="k1")), relpath="s.jsonl")
    _reject(_journal(_entry("label", "l1", None, targetId="k1", label=None)))


def test_message_role_union_and_closed_assistant():
    provider_payload = {"type": "openaiResponsesHistory", "items": []}
    good = (
        {"role": "user", "content": [], "timestamp": 1, "synthetic": True, "steering": False,
         "attribution": "agent", "providerPayload": provider_payload},
        {"role": "developer", "content": [], "timestamp": 1, "attribution": "user",
         "providerPayload": provider_payload},
        {"role": "toolResult", "toolCallId": "c1", "toolName": "bash", "content": [],
         "isError": False, "timestamp": 1, "details": {"x": 1}, "attribution": "agent", "prunedAt": 5,
         "providerMetadata": {"type": "computer", "screenshot": {"type": "computer_screenshot", "image_url": "u"},
                              "acknowledgedSafetyChecks": []}, "useless": False},
    )
    for role, message in zip(("user", "developer", "toolResult"), good):
        parse_journal_bytes(_journal(_entry("message", f"m-{role}", None, message=message)), relpath="s.jsonl")
    parse_journal_bytes(_journal(_entry("message", "m-assistant", None, message=_assistant_msg(
        contextSnapshot={"promptTokens": 1, "nonMessageTokens": 0}, duration=3, ttft=1))), relpath="s.jsonl")
    _reject(_journal(_entry("message", "m-system", None, message={"role": "system", "content": []})))
    base = {"role": "assistant", "content": [], "stopReason": "stop", "api": "a", "provider": "p",
            "model": "m", "timestamp": 1, "usage": _usage(input=0, output=0, totalTokens=0)}
    for bad in (
        {"role": "assistant", "content": []},
        {**base, "stopReason": "bogus"},
        {**base, "stopReason": []},
        {**base, "content": [{"type": "weird"}]},
        {**base, "content": [{"type": "image", "data": "AAAA", "mimeType": "image/png", "detail": []}]},
        {**base, "bogus": 1},
        {**base, "duration": "fast"},
        {**base, "disabledFeatures": "x"},
        {**base, "stopDetails": "x"},
        {**base, "toolCallAbortMessages": {"k": 1}},
        {"role": "user", "content": [], "timestamp": "now"},
        {"role": "user", "content": [], "timestamp": 1, "synthetic": "yes"},
        {"role": "user", "content": [], "timestamp": 1, "attribution": "system"},
        {"role": "developer", "content": [], "timestamp": 1, "synthetic": True},
        {"role": "toolResult", "toolCallId": "c1", "toolName": "bash", "content": [],
         "isError": False, "timestamp": 1, "prunedAt": "soon"},
        {"role": "toolResult", "toolCallId": "c1", "toolName": "bash", "content": [],
         "isError": False, "timestamp": 1, "useless": "yes"},
    ):
        _reject(_journal(_entry("message", "m1", None, message=bad)))


def test_tool_result_requires_tool_identity():
    parse_journal_bytes(_journal(_entry(
        "message", "r1", None,
        message={"role": "toolResult", "toolCallId": "c1", "toolName": "bash", "content": [], "isError": False, "timestamp": 1},
    )), relpath="s.jsonl")
    for bad in (
        {"role": "toolResult", "toolName": "bash", "isError": False, "timestamp": 1},
        {"role": "toolResult", "toolCallId": "c1", "isError": False, "timestamp": 1},
        {"role": "toolResult", "toolCallId": "c1", "toolName": "bash", "timestamp": 1},
        {"role": "toolResult", "toolCallId": "c1", "toolName": "bash", "content": [], "isError": False, "timestamp": 1, "providerPayload": "garbage"}):
        _reject(_journal(_entry("message", "r1", None, message=bad)))

def test_content_block_tool_call_shape():
    tool_call = {"type": "toolCall", "id": "tc1", "name": "hub", "arguments": {"to": "beta"}}
    parse_journal_bytes(_journal(_assistant(blocks=[tool_call], stop="toolUse")), relpath="s.jsonl")
    for blocks in (
        [{"type": "toolCall", "name": "hub", "arguments": {}}],
        [{"type": "toolCall", "id": "tc1", "arguments": {}}],
        [{"type": "toolCall", "id": "tc1", "name": "hub"}],
    ):
        _reject(_journal(_assistant(blocks=blocks, stop="toolUse")))

def test_nested_assistant_shapes_closed():
    call_meta = {"type": "computer", "providerItemId": "p", "actions": [{"type": "screenshot"}],
                 "pendingSafetyChecks": [{"id": "s", "code": None}]}
    for blocks in ([{"type": "thinking"}], [{"type": "redactedThinking"}],
                   [{"type": "fallback", "from": {"model": "a"}, "to": {"model": "b", "x": 1}}],
                   [{"type": "anthropicServerTool", "block": {"type": "web_search_tool_result", "tool_use_id": "x"}}],
                   [{"type": "toolCall", "id": "t", "name": "hub", "arguments": {}, "bogus": 1}],
                   [{"type": "toolCall", "id": "t", "name": "hub", "arguments": {},
                     "providerMetadata": {**call_meta, "actions": [{"type": "screenshot", "x": 1}]}}],
                   [{"type": "toolCall", "id": "u", "name": "hub", "arguments": {},
                     "providerMetadata": {**call_meta, "actions": [{"type": {}}]}}]):
        _reject(_journal(_assistant(blocks=blocks)))
    for over in ({"contextSnapshot": {"promptTokens": 1}},
                 {"retryRecovery": {"kind": "auto-retry", "status": "recovered", "attempt": 1, "recoveredAt": "now",
                                    "recovery": "plain", "note": "n", "supersededBy": None}},
                 {"providerPayload": {"type": "nope", "items": []}}, {"stopDetails": {"category": "x"}}):
        _reject(_journal(_entry("message", "m1", None, message=_assistant_msg(**over))))
    for role in ("user", "developer"):
        _reject(_journal(_entry("message", f"m-{role}", None, message={"role": role, "content": [], "timestamp": 1,
                "providerPayload": {"type": "openaiResponsesHistory", "items": [], "extra": True}})))
    blocks = [{"type": "thinking", "thinking": "h"}, {"type": "redactedThinking", "data": "d"},
              {"type": "fallback", "from": {"model": "a"}, "to": {"model": "b"}},
              {"type": "anthropicServerTool", "block": {"type": "web_search_tool_result", "tool_use_id": "x", "content": []}},
              {"type": "toolCall", "id": "t", "name": "hub", "arguments": {}, "providerMetadata": call_meta}]
    recovery = {"kind": "auto-retry", "status": "recovered", "attempt": 1, "recoveredAt": "now", "recovery": "model", "note": "n"}
    msg = _assistant_msg(blocks=blocks, stop="toolUse", contextSnapshot={"promptTokens": 1, "nonMessageTokens": 0},
                         retryRecovery=recovery, providerPayload={"type": "openaiResponsesHistory", "items": []}, stopDetails=None)
    parse_journal_bytes(_journal(_entry("message", "m1", None, message=msg)), relpath="s.jsonl")


def test_session_init_agent_optional_but_nonempty():
    parse_journal_bytes(_journal(_entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["read"])), relpath="s.jsonl")
    _reject(_journal(_entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["read"], agent="")))


def test_service_tier_map_and_schema_mode():
    si = _entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["read"])
    for service_tier in (None, {}, {"openai": "priority"}, {"anthropic": "auto", "google": "scale"}):
        parse_journal_bytes(_journal(_entry("service_tier_change", "s1", None, serviceTier=service_tier)), relpath="s.jsonl")
    parse_journal_bytes(_journal(si | {"outputSchemaMode": "permissive"}), relpath="s.jsonl")
    for bad in ({"serviceTier": "priority"}, {"serviceTier": {"openai": "urgent"}},
                {"serviceTier": {"gemini": "flex"}}):
        _reject(_journal(_entry("service_tier_change", "s1", None, **bad)))
    _reject(_journal(si | {"outputSchemaMode": "loose"}))


def test_duplicate_entry_ids_rejected():
    _reject_graph(_entry("reset_boundary", "dup1", None), _entry("reset_boundary", "dup1", None))


# ------------------------------------------------------------------ lines


def test_empty_and_whitespace_lines_rejected():
    slot = _slot()
    header = json.dumps(_header(), separators=(",", ":"))
    _reject((slot + header + "\n\n" + json.dumps(_entry("reset_boundary", "r1", None), separators=(",", ":")) + "\n").encode("utf-8"))
    _reject((slot + header + "\n   \n" + json.dumps(_entry("reset_boundary", "r1", None), separators=(",", ":")) + "\n").encode("utf-8"))



def test_truncated_or_missing_final_newline():
    _reject(_journal(_assistant())[:-8])  # cut mid-JSON
    journal = parse_journal_bytes(_journal(_entry("reset_boundary", "r1", None))[:-1], relpath="s.jsonl")
    assert len(journal.entries) == 1


def test_strict_json_line_rejections():
    _reject(_slot().encode("utf-8") + (json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8") + b"\xff\xfe not utf8\n")
    _reject(_slot().encode("utf-8") + b'{"type":"session","version":3,"id":"i","timestamp":"%s","cwd":"/w","id":"j"}\n' % TS.encode())
    _reject(_slot().encode("utf-8") + (json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8") + b'{"type":"reset_boundary","id":"x1","parentId":null,"timestamp":"%s","bad":NaN}\n' % TS.encode())
    _reject(_slot().encode("utf-8") + (json.dumps(_header(), separators=(",", ":")) + "\n").encode("utf-8") + b"[1,2]\n")


# --------------------------------------------------------- primary select


def test_select_primary_header_id_prefix():
    candidates = [("d/2026-08-23T10-00-00-000Z_old-session.jsonl", "new-session-id-abc"),
                  ("d/2026-09-01T00-00-00-000Z_zzz.jsonl", "zzz-other")]
    assert select_primary(candidates, "new-session") == candidates[0][0]


def test_select_primary_basename_id_after_underscore_and_case():
    candidates = [("d/2026-08-23T10-00-00-000Z_old-session.jsonl", "New-Session-Id-ABC")]
    assert select_primary(candidates, "2026-08-23T10") == candidates[0][0]
    assert select_primary(candidates, "old-session") == candidates[0][0]
    assert select_primary(candidates, "NEW-SESSION") == candidates[0][0]


def test_select_primary_precedence_header_over_basename():
    candidates = [("d/2026-08-01_aaa.jsonl", "2026-08-99_ignored.jsonl"),
                  ("d/2026-08-02_ccc.jsonl", "ccc-other")]
    assert select_primary(candidates, "2026-08") == candidates[0][0]


def test_select_primary_ambiguous_and_no_match():
    with pytest.raises(OmpSessionError):
        select_primary([("x/a.jsonl", "same-1"), ("x/b.jsonl", "same-2")], "same")
    with pytest.raises(OmpSessionError):
        select_primary([("x/a.jsonl", "other")], "nothing-matches")

# ------------------------------------------------------------------ graph


def _graph_journal(*entries):
    return parse_journal_bytes(_journal(*entries), relpath="s.jsonl")


def _reject_graph(*entries):
    with pytest.raises(OmpSessionError):
        validate_session_graph(_graph_journal(*entries).entries)


def test_build_tree_chain_and_leaf():
    journal = parse_journal_bytes(_fixture(PRIMARY), relpath="s.jsonl")
    forest = build_session_tree(journal.entries)
    assert len(forest) == 1 and isinstance(root := forest[0], SessionNode)
    assert (root.entry.id, root.entry.parent_id) == ("m1", None)
    assert [child.entry.id for child in root.children] == ["t1"]
    assert session_leaf(journal.entries).id == "tc1"
    assert [entry.id for entry in path_to_root(journal.entries, "tc1")] == ["m1", "t1", "u1", "a1", "c1", "tc1"]
    entries = tuple(SessionEntryRecord("reset_boundary", f"d{i}", None if i == 0 else f"d{i-1}", TS, {}) for i in range(1100))
    node = build_session_tree(entries)[0]
    for _ in range(1099): node = node.children[0]
    assert node.entry.id == "d1099"


def test_build_tree_children_sorted_by_timestamp():
    journal = _graph_journal(
        _entry("model_change", "p1", None, timestamp="2026-08-23T22:00:00.000Z", model="a/b"),
        _entry("model_change", "c2", "p1", timestamp="2026-08-23T22:00:02.000Z", model="a/b"),
        _entry("model_change", "c1", "p1", timestamp="2026-08-23T22:00:01.000Z", model="a/b"),
    )
    forest = build_session_tree(journal.entries)
    assert [child.entry.id for child in forest[0].children] == ["c1", "c2"]


def test_self_and_missing_parent_rejected():
    _reject_graph(_entry("model_change", "self", "self", timestamp="2026-08-23T22:00:00.000Z", model="a/b"))
    _reject_graph(_entry("model_change", "orphan", "nobody", timestamp="2026-08-23T22:00:01.000Z", model="a/b"))


def test_cycle_parent_rejected():
    _reject_graph(_entry("model_change", "a", "b", timestamp="2026-08-23T22:00:00.000Z", model="a/b"),
                  _entry("model_change", "b", "a", timestamp="2026-08-23T22:00:01.000Z", model="a/b"))


def test_graph_requires_single_root_and_entries():
    _reject_graph(_entry("reset_boundary", "r1", None), _entry("reset_boundary", "r2", None))
    with pytest.raises(OmpSessionError): validate_session_graph(())


def test_leaf_is_last_entry():
    journal = _graph_journal(_entry("reset_boundary", "late", None),
                             _entry("model_change", "early", None, timestamp="2026-08-23T22:00:01.000Z", model="a/b"))
    assert session_leaf(journal.entries).id == "early"


# -------------------------------------------------------- parse via root fd


def test_parse_journal_via_root_fd_and_missing(tmp_path):
    session_dir = os.path.join(str(tmp_path), "session")
    os.makedirs(session_dir, exist_ok=True)
    shutil.copy2(os.path.join(FIXTURES, PRIMARY), os.path.join(session_dir, PRIMARY))
    fd = os.open(session_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        assert parse_journal(fd, PRIMARY).header.id == "11111111-1111-7111-8111-111111111111"
    finally:
        os.close(fd)
    fd = os.open(str(tmp_path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        with pytest.raises(SafeTreeError):
            parse_journal(fd, "missing.jsonl")
    finally:
        os.close(fd)


def test_session_manifest_rejects_hardlinked_file(tmp_path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    journal = session_dir / PRIMARY
    journal.write_bytes(_journal(_entry("message", "m1", None)))
    os.link(journal, tmp_path / "outside.jsonl")
    fd = os.open(session_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(OmpSessionError, match="hard-linked"):
            build_session_manifest(fd)
    finally:
        os.close(fd)


def test_manifest_bound_read_rejects_current_drift(tmp_path) -> None:
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    journal = session_dir / PRIMARY
    original = _journal(_entry("message", "m1", None))
    journal.write_bytes(original)
    fd = os.open(session_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        manifest = build_session_manifest(fd)
        journal.write_bytes(b"changed")
        with pytest.raises(PromptSessionError, match="session_link_invalid"):
            read_manifest_bound(fd, manifest, PRIMARY)
    finally:
        os.close(fd)


def test_session_manifest_enforces_total_byte_bound(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orchestrator.providers import omp_session_manifest

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    journal = _journal(_entry("message", "m1", None))
    (session_dir / PRIMARY).write_bytes(journal)
    monkeypatch.setattr(
        omp_session_manifest, "_SESSION_TREE_MAX_BYTES", len(journal) - 1
    )
    fd = os.open(session_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        with pytest.raises(OmpSessionError, match="byte bound"):
            build_session_manifest(fd)
    finally:
        os.close(fd)
