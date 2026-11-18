"""The kit's settle checks on what the real Claude CLI 2.1.327 printed in the study's first paid run.

The fixture is cut from that run's one call (the smoke's `direct` arm on Haiku, 2026-11-18): its stream-json stdout
with every identifier replaced by a placeholder of the same shape, long strings shortened and the CLI's
thinking-token and command-list events left out. The session had the account's claude.ai connectors (three init
events: the session, then two one-turn continuations woken by its own background tasks; three cumulative results).
No provider is called.
"""

import json
from pathlib import Path

from experiments.compare import scan
from experiments.seed_set import rules, spend, units
from orchestrator.providers.pricing import load_price_table

REPO = Path(__file__).resolve().parents[2]
STREAM = Path(__file__).with_name("fixtures") / "seed_set" / "claude-2.1.327-direct-stream.jsonl"
ARGV = ["-p", "--output-format", "stream-json", "--verbose", "--model", spend.HAIKU, "--effort", "medium",
        "--permission-mode", "bypassPermissions"]
CONNECTORS = ["claude.ai Claude Docs", "claude.ai Google Slides", "claude.ai Google Drive"]


def events():
    return [json.loads(line) for line in STREAM.read_text().splitlines()]


def isolated(event):
    """An init event as the recorded one less what came from the account: connectors, their tools, synced skills."""
    if (event.get("type"), event.get("subtype")) != ("system", "init"):
        return event
    return event | {"tools": [t for t in event["tools"] if not t.startswith("mcp__")], "mcp_servers": [],
                    "skills": [s for s in event["skills"] if ":" not in s]}


def recorded_call(root, stream=None):
    call = root / "calls" / "1"
    call.mkdir(parents=True)
    (call / "prompt.txt").write_text("the task\n")
    (call / "argv.nul").write_bytes(b"".join(arg.encode() + b"\0" for arg in ARGV))
    rows = events() if stream is None else stream
    (call / "stdout.txt").write_text("".join(json.dumps(row) + "\n" for row in rows))
    (call / "stderr.txt").write_text("")
    return root


def hits(records, home):
    compiled = scan.patterns(main=home.parent / "main", runtime=home.parent / "runtime", solution="f" * 40, home=home)
    return scan.find_hits(records, home.parent / "tree", 0, home, compiled, expected_claude_model=spend.HAIKU)


def test_the_recorded_session_is_an_isolation_breach_naming_the_account_connectors(tmp_path):
    reason = units.isolation_breach(recorded_call(tmp_path))
    assert reason is not None and all(name in reason for name in CONNECTORS), reason


def test_a_session_with_only_the_clis_built_in_tools_skills_plugins_and_agents_is_no_breach(tmp_path):
    assert units.isolation_breach(recorded_call(tmp_path, [isolated(e) for e in events()])) is None


def test_the_clis_init_events_are_no_scan_hit(tmp_path):
    assert hits(recorded_call(tmp_path / "records"), tmp_path / "home") == []


def test_an_agent_naming_another_sessions_store_is_still_a_scan_hit(tmp_path):
    action = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "name": "Bash", "input": {"command": "ls ~/.claude/projects"}}]}}
    found = hits(recorded_call(tmp_path / "records", [*events(), action]), tmp_path / "home")
    assert [hit["pattern"] for hit in found] == ["other sessions' files"]


def test_one_call_with_three_cumulative_results_is_priced_at_its_last(tmp_path):
    records = recorded_call(tmp_path)
    last = [e for e in events() if e["type"] == "result"][-1]
    table = load_price_table(REPO / "orchestrator/providers/price_table.json")
    assert units.priced(records, table, 0.5) == {"usd": round(last["total_cost_usd"], 6), "missing": [],
                                                 "calls": {"1": round(last["total_cost_usd"], 6)}}


def test_the_continuations_are_one_successful_call_with_no_provider_error_or_limit(tmp_path):
    records = recorded_call(tmp_path)
    assert (units.physical_calls(records), units.succeeded(units.stream_events(records / "calls/1/stdout.txt")),
            units.provider_incident(records), units.usage_limit(records)) == (1, True, None, None)


def write_session(home, tree, rows, name):
    slug = "".join(c if c.isalnum() else "-" for c in str(tree / "cand-1"))
    path = home / name.format(slug=slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


TRANSCRIPT = ".claude/projects/{slug}/00000000-0000-4000-8000-000000000001.jsonl"
MCP_LOG = ".cache/claude-cli-nodejs/{slug}/mcp-logs-claude-ai-Google-Drive/2026-11-18T09-42-38-245Z.jsonl"


def test_the_audit_accepts_the_clis_one_transcript_and_still_flags_an_mcp_servers_log(tmp_path):
    home, tree = tmp_path / "home", tmp_path / "tree"
    write_session(home, tree, [{"type": "queue-operation", "sessionId": "s", "accountUuid": "a",
                                "organizationUuid": "o"}], TRANSCRIPT)
    clean = units.audit_sessions(home, tree, 1, spend.HAIKU)
    write_session(home, tree, [{"debug": "connected", "timestamp": "t", "sessionId": "s", "cwd": "/w"}], MCP_LOG)
    reason = units.audit_sessions(home, tree, 1, spend.HAIKU)[0]
    assert (clean[:2], len(clean[2]), "outside the unit tree's store" in reason) == ((None, None), 1, True)


def smoke_checks(records, home):
    """The smoke's call checks on one settled run, its facts as `study.settle` records them."""
    facts = {"scan_hits": len(hits(records, home))}
    if reason := units.isolation_breach(records):
        facts["incident"] = f"session audit: {reason}"
    return rules.call_checks([("direct", records, spend.HAIKU, "medium", facts)], {rules.unit_of(records): 1})


def test_the_smoke_checks_fail_the_recorded_run_and_pass_an_isolated_one(tmp_path):
    recorded = smoke_checks(recorded_call(tmp_path / "a" / "records"), tmp_path / "a" / "home")
    clean = smoke_checks(recorded_call(tmp_path / "b" / "records", [isolated(e) for e in events()]),
                         tmp_path / "b" / "home")
    assert (recorded["scans_and_session_audits_clean"], all(clean.values())) == (False, True), (recorded, clean)
