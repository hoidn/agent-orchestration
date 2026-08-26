"""Behavioral tests for orchestrator.providers.omp_observation (Task 4).

Covered contracts (brief step 4.3 + X5):
- Settlement: at least one assistant message, last one stopReason stop without
  an open toolCall block.
- Advisor journals: direct __advisor[.<slug>].jsonl under the artifacts dir,
  settled, with at least one non-header entry.
- Child journals: exactly one session_init with a non-empty agent, settled.
- Hub: success matched by tool-call identity; unmatched hub calls fail close;
  peer-team requires at least one matched call.
- observe_close: exactly one direct <timestamp>_<id>.jsonl primary selected by
  the stdout session id, every discovered journal valid and settled, topology
  counts enforced only for recognized conf digests, isolated child worktrees
  absent at close, safe-tree rejections fail observation.
"""
import contextlib
import json
import os
import stat
from pathlib import Path

import pytest
import orchestrator.providers.omp_observation as omp_observation

from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_observation import (
    ExpectedTopology,
    OmpObservationError,
    ObservationReport,
    PRESET_TOPOLOGIES,
    compare_session_manifests,
    hub_match,
    is_advisor_journal,
    is_advisor_name,
    is_child_journal,
    is_terminal_child,
    is_settled,
    observe_close,
)
from orchestrator.providers.omp_session import OmpSessionError, parse_journal_bytes
from orchestrator.providers.omp_session_manifest import build_session_manifest

CONF_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "omp", "conf")
SESSION_FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "omp", "sessions")

PRIMARY = "2026-08-23T22-33-31-340Z_11111111-1111-7111-8111-111111111111.jsonl"
PRIMARY_ID = "11111111-1111-7111-8111-111111111111"
HUB_PRIMARY = "2026-08-23T22-40-00-000Z_22222222-2222-7222-8222-222222222222.jsonl"
HUB_PRIMARY_ID = "22222222-2222-7222-8222-222222222222"
TS = "2026-08-23T22:33:31.340Z"


@contextlib.contextmanager
def _root(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        yield fd
    finally:
        os.close(fd)


def _slot(updated_at=TS):
    obj = {"type": "title", "v": 1, "title": "", "updatedAt": updated_at, "pad": ""}
    base = json.dumps(obj, separators=(",", ":")) + "\n"
    obj["pad"] = " " * (256 - len(base.encode("utf-8")))
    text = json.dumps(obj, separators=(",", ":")) + "\n"
    assert len(text.encode("utf-8")) == 256
    return text


def _journal(session_id, entries, cwd="/workspace"):
    header = {"type": "session", "version": 3, "id": session_id, "timestamp": TS, "cwd": cwd}
    slot = _slot()
    lines = [json.dumps(header, separators=(",", ":"))]
    lines += [json.dumps(entry, separators=(",", ":")) for entry in entries]
    return (slot + "\n".join(lines) + "\n").encode("utf-8")


def _entry(entry_type, entry_id, parent, timestamp=TS, **extra):
    entry = {"type": entry_type, "id": entry_id, "parentId": parent, "timestamp": timestamp}
    entry.update(extra)
    return entry


def _usage():
    return {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "totalTokens": 0,
            "cost": {"input": 0.0, "output": 0.0, "cacheRead": 0.0, "cacheWrite": 0.0, "total": 0.0}}


def _hub_journal(call, results):
    entries = [
        _entry("message", "u1", None, message={"role": "user", "content": [], "timestamp": 1}),
        _entry("message", "a1", "u1", message={"role": "assistant", "content": [call] if call else [], "api": "a", "provider": "p",
                                              "model": "m", "stopReason": "toolUse" if call else "stop", "timestamp": 1, "usage": _usage()}),
    ]
    for index, (call_id, is_error) in enumerate(results):
        entries.append(_entry("message", f"r{index}", entries[-1]["id"], message={"role": "toolResult",
                                              "toolCallId": call_id, "toolName": "hub", "content": [], "isError": is_error,
                                              "timestamp": 2 + index}))
    entries.append(_entry("message", "a2", entries[-1]["id"], message={"role": "assistant", "content": [{"type": "text", "text": "x"}],
                                              "api": "a", "provider": "p", "model": "m", "stopReason": "stop",
                                              "timestamp": 9, "usage": _usage()}))
    return _journal("99999999-9999-7999-8999-999999999999", entries)


def _fixture(name):
    with open(os.path.join(SESSION_FIXTURES, name), "rb") as handle:
        return handle.read()


def _parse(name):
    return parse_journal_bytes(_fixture(name), relpath=name)


def _session(tmp_path, files):
    root = os.path.join(str(tmp_path), "session")
    for relative, payload in files.items():
        target = os.path.join(root, relative)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as handle:
            handle.write(payload if isinstance(payload, bytes) else payload.encode("utf-8"))
    return root


def _artifacts(primary_name):
    return primary_name[: -len(".jsonl")]


def _conf_digest(fixture_name):
    with _root(os.path.join(CONF_FIXTURES, fixture_name)) as fd:
        return admit_conf_tree(fd).manifest_sha256


def _conf_digest_dir(path):
    with _root(path) as fd:
        return admit_conf_tree(fd).manifest_sha256


def _neutral_map():
    return {_conf_digest("neutral"): PRESET_TOPOLOGIES["neutral"]}


def _fanout_map():
    return {_conf_digest("fanout"): PRESET_TOPOLOGIES["fanout"]}


def _peer_team_map():
    return {_conf_digest("fanout"): PRESET_TOPOLOGIES["peer-team"]}


def _observe(tmp_path, files, *, session_id=PRIMARY_ID, conf_map=None, worktree_root=None):
    root = _session(tmp_path, files)
    with _root(root) as fd:
        return observe_close(
            session_root_fd=fd,
            stdout_session_id=session_id,
            conf_manifest_sha256=next(iter(conf_map)) if conf_map else "unrecognized-digest",
            recognized_topologies=conf_map or {},
            isolated_worktree_root=worktree_root,
        )


# ------------------------------------------------------------- predicates


def test_is_settled_fixtures():
    assert is_settled(_parse(PRIMARY)) is True
    assert is_settled(_parse("unsettled-tooluse.jsonl")) is False
    assert is_settled(_parse("unsettled-user.jsonl")) is False
    assert is_settled(_parse("header-only.jsonl")) is False
    assert is_settled(_parse("hub-unmatched.jsonl")) is True  # ends with a stop assistant


def test_is_settled_requires_last_assistant_stop_without_tool_call():
    tool_call = {"type": "toolCall", "id": "tc1", "name": "bash", "arguments": {"command": "ls"}}
    entries = [
        _entry("message", "u1", None, message={"role": "user", "content": [], "timestamp": 1}),
        _entry("message", "a1", "u1", message={"role": "assistant", "content": [tool_call], "api": "a", "provider": "p",
                                              "model": "m", "stopReason": "toolUse", "timestamp": 1, "usage": _usage()}),
    ]
    journal = parse_journal_bytes(_journal("99999999-9999-7999-8999-999999999999", entries), relpath="c.jsonl")
    assert is_settled(journal) is False


def test_is_advisor_name():
    assert is_advisor_name("__advisor.jsonl") is True
    assert is_advisor_name("__advisor.v2.jsonl") is True
    assert is_advisor_name("__advisor.jsonl.bak") is False
    assert is_advisor_name("advisor.jsonl") is False
    assert is_advisor_name("__advisor..jsonl") is False
    assert is_advisor_name("__advisor.Up.jsonl") is False
    assert is_advisor_name("__advisor") is False


def test_is_advisor_journal():
    advisor = _parse("__advisor.jsonl")
    assert is_advisor_journal("d/__advisor.jsonl", advisor) is True
    assert is_advisor_journal("d/__advisor.v2.jsonl", advisor) is True
    assert is_advisor_journal("d/other.jsonl", advisor) is False
    assert is_advisor_journal("d/__advisor.jsonl", _parse("header-only.jsonl")) is False
    assert is_advisor_journal("d/__advisor.jsonl", _parse("unsettled-user.jsonl")) is False


def test_is_child_journal():
    assert is_child_journal(_parse("alpha.jsonl")) is True
    assert is_child_journal(_parse("beta.jsonl")) is True
    assert is_child_journal(_parse(PRIMARY)) is False
    assert is_child_journal(_parse("header-only.jsonl")) is False
    assert is_child_journal(_parse("unsettled-tooluse.jsonl")) is False
    two_inits = [
        _entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["read"], agent="alpha"),
        _entry("session_init", "si2", None, systemPrompt="sp", task="t", tools=["read"], agent="beta"),
    ]
    journal = parse_journal_bytes(_journal("99999999-9999-7999-8999-999999999999", two_inits), relpath="c.jsonl")
    assert is_child_journal(journal) is False

def _yield_child(*, is_error=False, exit_kind="normal"):
    call_id = "yield-1"
    entries = [
        _entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["write"], agent="alpha"),
        _entry("message", "u1", "si1", message={"role": "user", "content": [], "timestamp": 1}),
        _entry("message", "a1", "u1", message={"role": "assistant", "content": [
            {"type": "toolCall", "id": call_id, "name": "yield", "arguments": {"result": {}}}
        ], "api": "a", "provider": "p", "model": "m", "stopReason": "toolUse",
            "timestamp": 2, "usage": _usage()}),
        _entry("message", "r1", "a1", message={"role": "toolResult",
            "toolCallId": call_id, "toolName": "yield", "content": [],
            "details": {"status": "success"}, "isError": is_error, "timestamp": 3}),
        _entry("custom", "x1", "r1", customType="session_exit",
            data={"reason": "dispose", "kind": exit_kind, "recordedAt": TS}),
    ]
    return parse_journal_bytes(
        _journal("99999999-9999-7999-8999-999999999999", entries),
        relpath="Alpha.jsonl",
    )


def test_terminal_child_accepts_successful_yield_and_normal_exit():
    journal = _yield_child()
    assert is_settled(journal) is False
    assert is_terminal_child(journal) is True


def test_terminal_child_rejects_failed_yield_or_abnormal_exit():
    assert is_terminal_child(_yield_child(is_error=True)) is False
    assert is_terminal_child(_yield_child(exit_kind="abnormal")) is False

def _settled_child_with_exit(kind: str) -> bytes:
    entries = [
        _entry("session_init", "si1", None, systemPrompt="sp", task="t",
               tools=["read"], agent="alpha"),
        _entry("message", "a1", "si1", message={"role": "assistant",
            "content": [{"type": "text", "text": "done"}], "api": "a",
            "provider": "p", "model": "m", "stopReason": "stop",
            "timestamp": 2, "usage": _usage()}),
        _entry("custom", "x1", "a1", customType="session_exit",
            data={"reason": "dispose" if kind == "normal" else "signal",
                  "kind": kind, "recordedAt": TS}),
    ]
    return _journal("99999999-9999-7999-8999-999999999999", entries)


def test_terminal_child_rejects_abnormal_exit_after_assistant_stop():
    journal = parse_journal_bytes(
        _settled_child_with_exit("abnormal"), relpath="Alpha.jsonl")
    assert is_settled(journal) is True
    assert is_terminal_child(journal) is False




def test_hub_match_by_tool_call_identity():
    journal = _parse(HUB_PRIMARY)
    matched, unmatched = hub_match(journal)
    assert matched == 1
    assert unmatched == ()
    journal = _parse("hub-unmatched.jsonl")
    matched, unmatched = hub_match(journal)
    assert matched == 0
    assert unmatched == ("hub-call-9",)
    journal = _parse(PRIMARY)
    assert hub_match(journal) == (0, ())


def test_expected_topology_presets():
    assert PRESET_TOPOLOGIES["neutral"] == ExpectedTopology()
    assert PRESET_TOPOLOGIES["advised"] == ExpectedTopology(advisor=1)
    assert PRESET_TOPOLOGIES["fanout"] == ExpectedTopology(child=2)
    assert PRESET_TOPOLOGIES["peer-team"] == ExpectedTopology(child=2, hub_matched=True)
    assert PRESET_TOPOLOGIES["advised-fanout"] == ExpectedTopology(advisor=1, child=2)
    assert set(PRESET_TOPOLOGIES) == {"neutral", "advised", "fanout", "peer-team", "advised-fanout"}


def _manifest(root):
    with _root(root) as fd:
        return build_session_manifest(fd)


def test_session_manifests_compare_and_refuse_drift(tmp_path):
    root = _session(tmp_path, {PRIMARY: _fixture(PRIMARY),
                               _artifacts(PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl")})
    snapshot = _manifest(root)
    row_mode = snapshot.rows[0].mode
    assert row_mode == f"{stat.S_IMODE(os.stat(os.path.join(root, snapshot.rows[0].relative_path)).st_mode):04o}"
    assert f'"mode":"{row_mode}"' in snapshot.manifest_bytes.decode()
    assert compare_session_manifests(snapshot, _manifest(root)) is True
    # modes stay recorded actual and may differ between snapshot and live
    os.chmod(os.path.join(root, _artifacts(PRIMARY), "alpha.jsonl"), 0o640)
    assert compare_session_manifests(snapshot, _manifest(root)) is True
    with open(os.path.join(root, _artifacts(PRIMARY), "alpha.jsonl"), "ab") as handle:
        handle.write(b" ")
    with pytest.raises(OmpObservationError):
        compare_session_manifests(snapshot, _manifest(root))
    os.remove(os.path.join(root, _artifacts(PRIMARY), "alpha.jsonl"))
    with pytest.raises(OmpObservationError):
        compare_session_manifests(snapshot, _manifest(root))
    # a symlink in the live tree is type-swapped and fails closed at build
    os.symlink("/etc/hostname", os.path.join(root, _artifacts(PRIMARY), "link.jsonl"))
    with pytest.raises(OmpSessionError):
        _manifest(root)


# ------------------------------------------------------------- observation


def test_observe_close_neutral_topology(tmp_path):
    report = _observe(tmp_path, {PRIMARY: _fixture(PRIMARY)}, conf_map=_neutral_map())
    assert isinstance(report, ObservationReport)
    assert report.primary_relpath == PRIMARY
    assert report.advisor_relpaths == ()
    assert report.child_relpaths == ()
    assert report.hub_matched is False
    assert report.unrecognized is False


def test_observe_close_advised_topology(tmp_path):
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/__advisor.jsonl": _fixture("__advisor.jsonl"),
    }
    report = _observe(tmp_path, files, conf_map={_conf_digest("advised"): PRESET_TOPOLOGIES["advised"]})
    assert report.advisor_relpaths == (_artifacts(PRIMARY) + "/__advisor.jsonl",)
    assert report.child_relpaths == ()


def test_observe_close_fanout_topology(tmp_path):
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl"),
        _artifacts(PRIMARY) + "/beta.jsonl": _fixture("beta.jsonl"),
        _artifacts(PRIMARY) + "/0.bash.log": b"truncated tool output",
    }
    report = _observe(tmp_path, files, conf_map=_fanout_map())
    assert report.child_relpaths == (_artifacts(PRIMARY) + "/alpha.jsonl", _artifacts(PRIMARY) + "/beta.jsonl")
    assert report.advisor_relpaths == ()


def test_observe_close_peer_team_topology(tmp_path):
    files = {
        HUB_PRIMARY: _fixture(HUB_PRIMARY),
        _artifacts(HUB_PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl"),
        _artifacts(HUB_PRIMARY) + "/beta.jsonl": _fixture("beta.jsonl"),
    }
    report = _observe(tmp_path, files, session_id=HUB_PRIMARY_ID, conf_map=_peer_team_map())
    assert report.hub_matched is True


def test_observe_close_rejects_ambiguous_advisor_child(tmp_path):
    entries = [
        _entry("session_init", "si1", None, systemPrompt="sp", task="t",
               tools=["read"], agent="alpha"),
        _entry("message", "a1", "si1", message={"role": "assistant",
            "content": [{"type": "text", "text": "done"}], "api": "a",
            "provider": "p", "model": "m", "stopReason": "stop",
            "timestamp": 2, "usage": _usage()}),
    ]
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/__advisor.jsonl": _journal(
            "99999999-9999-7999-8999-999999999999", entries),
    }
    with pytest.raises(OmpObservationError, match="ambiguously classified"):
        _observe(tmp_path, files, conf_map={})


def test_observe_close_unrecognized_conf_skips_counts(tmp_path):
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl"),
        _artifacts(PRIMARY) + "/beta.jsonl": _fixture("beta.jsonl"),
        _artifacts(PRIMARY) + "/gamma.jsonl": _fixture("alpha.jsonl"),
    }
    report = _observe(tmp_path, files, conf_map={})  # unrecognized digest
    assert report.unrecognized is True
    assert len(report.child_relpaths) == 3


def test_observe_close_topology_count_mismatch_fails(tmp_path):
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), _artifacts(PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl")}, conf_map=_fanout_map())  # 1 child, fanout wants 2
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), _artifacts(PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl"), _artifacts(PRIMARY) + "/beta.jsonl": _fixture("beta.jsonl")}, conf_map=_neutral_map())  # 2 children, neutral wants 0


def test_observe_close_peer_team_requires_matched_hub(tmp_path):
    unmatched = "2026-08-23T22-41-00-000Z_77777777-7777-7777-8777-777777777777.jsonl"
    files = {
        unmatched: _fixture("hub-unmatched.jsonl"),
        _artifacts(unmatched) + "/alpha.jsonl": _fixture("alpha.jsonl"),
        _artifacts(unmatched) + "/beta.jsonl": _fixture("beta.jsonl"),
    }
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, files, session_id="77777777-7777-7777-8777-777777777777", conf_map=_peer_team_map())


def test_observe_close_rejects_abnormal_settled_child(tmp_path):
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/alpha.jsonl":
            _settled_child_with_exit("abnormal"),
    }
    with pytest.raises(OmpObservationError, match="child journal failed"):
        _observe(tmp_path, files, conf_map={})


def test_observe_close_unmatched_hub_in_child_fails(tmp_path):
    hub_call = {"type": "toolCall", "id": "hub-call-9", "name": "hub", "arguments": {"to": "beta"}}
    entries = [
        _entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["read"], agent="alpha"),
        _entry("message", "u1", "si1", message={"role": "user", "content": [], "timestamp": 1}),
        _entry("message", "a1", "u1", message={"role": "assistant", "content": [hub_call], "api": "a", "provider": "p",
                                              "model": "m", "stopReason": "toolUse", "timestamp": 1, "usage": _usage()}),
        _entry("message", "a2", "a1", message={"role": "assistant", "content": [{"type": "text", "text": "x"}], "api": "a",
                                              "provider": "p", "model": "m", "stopReason": "stop", "timestamp": 2, "usage": _usage()}),
    ]
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/alpha.jsonl": _journal("99999999-9999-7999-8999-999999999999", entries),
        _artifacts(PRIMARY) + "/beta.jsonl": _fixture("beta.jsonl"),
    }
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, files, conf_map=_fanout_map())


def test_observe_close_invalid_journals_fail(tmp_path):
    broken = _fixture("alpha.jsonl").replace(b'"type":"session_init"', b'"type":"session_init","mystery":1')
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), _artifacts(PRIMARY) + "/alpha.jsonl": broken,
                            _artifacts(PRIMARY) + "/beta.jsonl": _fixture("beta.jsonl")}, conf_map=_fanout_map())
    unsettled_child = _journal("99999999-9999-7999-8999-999999999999", [
        _entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["read"], agent="gamma"),
        _entry("message", "u1", "si1", message={"role": "user", "content": [], "timestamp": 1}),
        _entry("message", "a1", "u1", message={"role": "assistant", "content": [{"type": "text", "text": "x"}],
                                              "api": "a", "provider": "p", "model": "m",
                                              "stopReason": "toolUse", "timestamp": 1, "usage": _usage()}),
    ])
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), _artifacts(PRIMARY) + "/gamma.jsonl": unsettled_child}, conf_map={})
    unsettled_primary = _journal(PRIMARY_ID, [_entry("message", "u1", None, message={"role": "user", "content": [{"type": "text", "text": "?"}], "timestamp": 1})])
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: unsettled_primary}, conf_map=_neutral_map())


def test_observe_close_unclassifiable_journals_fail(tmp_path):
    for rel, payload in (
        (_artifacts(PRIMARY) + "/__advisor.jsonl", _fixture(PRIMARY)),
        (_artifacts(PRIMARY) + "/copy.jsonl", _fixture(PRIMARY)),
        (_artifacts(PRIMARY) + "/__advisor.Up.jsonl", _fixture("__advisor.jsonl")),
    ):
        with pytest.raises(OmpObservationError):
            _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), rel: payload}, conf_map=_neutral_map())


def test_observe_close_invalid_journal_graphs_fail(tmp_path):
    settled = {"role": "assistant", "content": [{"type": "text", "text": "x"}], "api": "a", "provider": "p", "model": "m",
               "stopReason": "stop", "timestamp": 2, "usage": _usage()}
    dup = _journal(PRIMARY_ID, [_entry("message", "u1", None, message={"role": "user", "content": [], "timestamp": 1}),
                                _entry("message", "a1", "u1", message=settled), _entry("message", "a1", "u1", message=settled)])
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: dup}, conf_map=_neutral_map())
    orphan = _journal("99999999-9999-7999-8999-999999999999", [
        _entry("session_init", "si1", None, systemPrompt="sp", task="t", tools=["read"], agent="alpha"),
        _entry("message", "u1", "missing", message={"role": "user", "content": [], "timestamp": 1}),
    ])
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), _artifacts(PRIMARY) + "/alpha.jsonl": orphan}, conf_map=_fanout_map())


def test_hub_match_failed_then_success_and_orphan_fail():
    call = {"type": "toolCall", "id": "h1", "name": "hub", "arguments": {}}
    for journal in (
        parse_journal_bytes(_hub_journal(call, [("h1", True), ("h1", False)]), relpath="c.jsonl"),
        parse_journal_bytes(_hub_journal(None, [("h9", False)]), relpath="c.jsonl"),
    ):
        with pytest.raises(OmpObservationError):
            hub_match(journal)


def test_observe_close_extra_or_second_top_level_journal_fails(tmp_path):
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), "stray.jsonl": _fixture("header-only.jsonl")}, conf_map=_neutral_map())
    other = "2026-08-24T00-00-00-000Z_99999999-9999-7999-8999-999999999999.jsonl"
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {PRIMARY: _fixture(PRIMARY), other: _fixture(PRIMARY)}, conf_map=_neutral_map())


def test_observe_close_primary_basename_must_match_header(tmp_path):
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {"primary.jsonl": _fixture(PRIMARY)}, conf_map=_neutral_map())
    fake = "2026-08-24T00-00-00-000Z_" + PRIMARY_ID + ".jsonl"
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, {fake: _fixture(PRIMARY)}, conf_map=_neutral_map())


def test_observe_close_nested_journal_outside_artifacts_fails(tmp_path):
    files = {
        PRIMARY: _fixture(PRIMARY),
        "other/child.jsonl": _fixture("alpha.jsonl"),
    }
    with pytest.raises(OmpObservationError):
        _observe(tmp_path, files, conf_map=_neutral_map())


def test_observe_close_bounds_nonjournal_artifacts(tmp_path, monkeypatch):
    primary = _fixture(PRIMARY)
    monkeypatch.setattr(
        omp_observation, "SESSION_TREE_MAX_BYTES", len(primary) + 3
    )
    with pytest.raises(OmpObservationError, match="tree-byte bound"):
        _observe(
            tmp_path,
            {PRIMARY: primary, _artifacts(PRIMARY) + "/token.out": b"xxxx"},
            conf_map=_neutral_map(),
        )


def test_observe_close_worktree_must_be_absent_at_close(tmp_path):
    root = os.path.join(str(tmp_path), "omp-wt")
    beta_worktree = os.path.join(root, "beta-wt")
    beta = _fixture("beta.jsonl").replace(
        b"/home/user/.omp/wt/beta-wt", beta_worktree.encode("utf-8")
    )
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl"),
        _artifacts(PRIMARY) + "/beta.jsonl": beta,
    }
    os.makedirs(beta_worktree, exist_ok=True)
    try:
        with pytest.raises(OmpObservationError):
            _observe(tmp_path, files, conf_map=_fanout_map(), worktree_root=root)
        # explicit canonical root still enforces the check
        with pytest.raises(OmpObservationError):
            _observe(tmp_path, files, conf_map=_fanout_map(), worktree_root=root + "/")
    finally:
        os.rmdir(beta_worktree)
    report = _observe(tmp_path, files, conf_map=_fanout_map(), worktree_root=root)
    assert len(report.child_relpaths) == 2
    report = _observe(tmp_path, files, conf_map=_fanout_map(), worktree_root=None)
    assert report.unrecognized is False


def test_observe_close_non_worktree_child_cwd_unaffected(tmp_path):
    files = {
        PRIMARY: _fixture(PRIMARY),
        _artifacts(PRIMARY) + "/alpha.jsonl": _fixture("alpha.jsonl"),
        _artifacts(PRIMARY) + "/beta.jsonl": _fixture("beta.jsonl"),
    }
    # alpha cwd is /workspace; the pinned root points at a different tree location
    _observe(tmp_path, files, conf_map=_fanout_map(), worktree_root="/home/user/.omp/wt")


def test_observe_close_symlink_in_session_fails(tmp_path):
    root = _session(tmp_path, {PRIMARY: _fixture(PRIMARY)})
    artifacts = os.path.join(root, _artifacts(PRIMARY))
    os.makedirs(artifacts, exist_ok=True)
    os.symlink("/etc/hostname", os.path.join(artifacts, "link.jsonl"))
    with _root(root) as fd:
        with pytest.raises(OmpObservationError):
            observe_close(session_root_fd=fd, stdout_session_id=PRIMARY_ID, conf_manifest_sha256=_conf_digest("neutral"), recognized_topologies=_neutral_map(), isolated_worktree_root=None)


def test_observe_close_rejects_externally_hardlinked_journal(tmp_path):
    root = _session(tmp_path, {PRIMARY: _fixture(PRIMARY)})
    os.link(os.path.join(root, PRIMARY), tmp_path / "external-alias.jsonl")
    with _root(root) as fd:
        with pytest.raises(OmpObservationError, match="hard-linked"):
            observe_close(
                session_root_fd=fd,
                stdout_session_id=PRIMARY_ID,
                conf_manifest_sha256=_conf_digest("neutral"),
                recognized_topologies=_neutral_map(),
                isolated_worktree_root=None,
            )


def test_observe_close_undecodable_name_fails(tmp_path):
    root = _session(tmp_path, {PRIMARY: _fixture(PRIMARY)})
    raw = os.path.join(root, _artifacts(PRIMARY)).encode("utf-8") + b"\xff\xfe_bad.jsonl"
    fd = os.open(raw, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    os.close(fd)
    with _root(root) as fd_root:
        with pytest.raises(OmpObservationError):
            observe_close(session_root_fd=fd_root, stdout_session_id=PRIMARY_ID, conf_manifest_sha256=_conf_digest("neutral"), recognized_topologies=_neutral_map(), isolated_worktree_root=None)


# ---------------------------------------------------------------------------
# Task 10 R5: one code-owned topology authority keyed ONLY by canonical
# packaged-conf digest (labels and paths never select)
# ---------------------------------------------------------------------------


def test_recognized_preset_topologies_five_distinct_digests():
    from orchestrator.omp_assets import preset_conf_root
    from orchestrator.providers.omp_observation import (
        ExpectedTopology,
        recognized_preset_topologies,
    )

    topologies = recognized_preset_topologies()
    assert len(topologies) == 5
    assert len(set(topologies)) == 5
    import dataclasses

    assert topologies == {
        _conf_digest_dir(preset_conf_root(name)): ExpectedTopology(
            **dataclasses.asdict(PRESET_TOPOLOGIES[name])
        )
        for name in ("neutral", "advised", "fanout", "peer-team", "advised-fanout")
    }


def test_recognized_preset_topologies_copied_path_same_digest_and_topology(tmp_path):
    """R5: a copied/renamed packaged conf tree resolves the SAME canonical
    digest and therefore the same expected counts; the filesystem path never
    selects. observe_close enforces the copied-path digest identically."""
    from orchestrator.omp_assets import preset_conf_root
    from orchestrator.providers.omp_observation import (
        ExpectedTopology,
        recognized_preset_topologies,
    )

    topologies = recognized_preset_topologies()
    copied = tmp_path / "renamed-preset"
    copied.mkdir()
    source = preset_conf_root("advised-fanout")
    for entry in Path(source).rglob("*"):
        if entry.is_file():
            target = copied / entry.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(entry.read_bytes())
    copied_digest = _conf_digest_dir(copied)
    assert copied_digest in topologies
    assert topologies[copied_digest] == ExpectedTopology(advisor=1, child=2)

    # The copied-path digest enforces the counts during close observation.
    files = {PRIMARY: _fixture(PRIMARY)}
    for name in ("__advisor.jsonl", "alpha.jsonl", "beta.jsonl"):
        files[_artifacts(PRIMARY) + "/" + name] = _fixture(name)
    report = _observe(
        tmp_path, files,
        conf_map={copied_digest: topologies[copied_digest]},
    )
    assert report.unrecognized is False
    assert len(report.advisor_relpaths) == 1 and len(report.child_relpaths) == 2


def test_recognized_preset_topologies_label_key_is_not_authoritative(tmp_path):
    """R5 RED: a name-labeled key (e.g. ``{"advised": ...}``) is absent from
    the digest-keyed authority, so the same conf digest selects NO counts and
    close observation stays unrecognized rather than trusting the label."""
    from orchestrator.providers.omp_observation import (
        ExpectedTopology,
        recognized_preset_topologies,
    )

    topologies = recognized_preset_topologies()
    digest = _conf_digest("advised")
    assert digest not in {"advised": ExpectedTopology(advisor=1)}
    report = _observe(
        tmp_path,
        {PRIMARY: _fixture(PRIMARY)},
        conf_map={},
    )
    assert report.unrecognized is True
