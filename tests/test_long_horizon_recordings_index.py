"""The long-horizon kit's recordings index (`recordings.json`) against the local cache and the fixtures."""

import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

KIT = Path(__file__).resolve().parents[1] / "experiments" / "long_horizon_tasks"
_spec = importlib.util.spec_from_file_location("lh_cut_fixture_index", KIT / "cut_fixture.py")
cut = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cut)

INDEX = json.loads((KIT / "recordings.json").read_text())
CACHE = Path(os.environ.get("LH", Path.home() / "lh-cache")) / "recordings"
DECOY = KIT / "fixtures" / "traces" / "t2a-strace-decoy-low.json"


def _configs():
    for rec in INDEX["recordings"]:
        found = sorted((CACHE / rec["name"]).glob("jobs/*/*/config.json"))
        if found:
            yield rec, json.loads(found[0].read_text())


@pytest.mark.skipif(not CACHE.is_dir(), reason="the local recordings cache is not on this machine")
def test_every_task_2a_recording_s_harbor_arguments_equal_its_trial_configuration():
    wrong = [rec["name"] for rec, config in _configs()
             if rec["name"].startswith("t2a-") and rec["harbor_args"] != cut.harbor_args(config)]
    assert wrong == []


REQUESTS_2A = sorted((KIT / "fixtures" / "requests").glob("t2a-*.json"))


@pytest.mark.skipif(not CACHE.is_dir(), reason="the local recordings cache is not on this machine")
def test_every_task_2a_request_fixture_is_the_cut_of_its_recording(tmp_path):
    wrong = []
    for path in REQUESTS_2A:
        cut._write(cut.requests(CACHE / path.stem / "stub.jsonl", json.loads(path.read_text())["source"]),
                   tmp_path / path.name)
        wrong += [path.stem] if (tmp_path / path.name).read_text() != path.read_text() else []
    assert wrong == []


@pytest.mark.skipif(not CACHE.is_dir(), reason="the local recordings cache is not on this machine")
def test_every_file_a_task_2a_request_cut_reads_has_its_digest_in_the_index():
    digests = {rec["name"]: rec["files_sha256"] for rec in INDEX["recordings"]}
    read = [(path.stem, f) for path in REQUESTS_2A for f in [CACHE / path.stem / "stub.jsonl", CACHE / path.stem /
            "canary.txt", *sorted((CACHE / path.stem).glob(cut.SESSION_FILES))] if f.exists()]
    assert [str(f.relative_to(CACHE)) for name, f in read if digests.get(name, {}).get(str(f.relative_to(CACHE)))
            != hashlib.sha256(f.read_bytes()).hexdigest()] == []


def test_the_decoy_canary_reached_no_request_and_no_file_but_the_harness_s_export():
    decoy = json.loads(DECOY.read_text())["decoy"]
    assert (decoy["requests_naming_the_canary"],
            decoy["requests_with_the_slot_token"] == decoy["requests_watched_for_the_canary"] == decoy["requests"] > 0,
            [f.endswith("agent/sessions/.credentials.json") for f in decoy["files_holding_the_canary"]]) == (
        0, True, [True])


def test_the_decoy_canary_occurs_in_no_other_committed_fixture_or_the_index():
    canary = json.loads(DECOY.read_text())["decoy"]["canary"]
    files = [p for p in (KIT / "fixtures").rglob("*.json") if p != DECOY] + [KIT / "recordings.json"]
    assert [p.name for p in files if canary in p.read_text()] == []


FIXTURES = KIT / "fixtures"
DENY = ("Task,CronCreate,CronDelete,CronList,EnterWorktree,ExitWorktree,ListAgents,Monitor,NotebookEdit,"
        "RemoteTrigger,ReportFindings,ScheduleWakeup,SendMessage,Skill,TaskStop,ToolSearch,Workflow,Write")
CLI_2A = [r for r in INDEX["recordings"] if r["name"].startswith("t2a-") and "--agent claude-code" in r["harbor_args"]]


def _recording_of(path):
    found = re.match(r"local recording ([a-z0-9-]+)", json.loads(path.read_text()).get("source", ""))
    return found.group(1) if found else None


def _arg(args, flag):
    found = re.search(rf"(?:^| ){re.escape(flag)}(\S+)", args)
    return found.group(1) if found else None


def test_every_local_fixture_s_recording_is_in_the_index():
    names = {r["name"] for r in INDEX["recordings"]}
    sources = {_recording_of(p) for p in FIXTURES.rglob("*.json")} - {None}
    assert sorted(sources - names) == []


def test_every_task_2a_session_s_effort_is_the_effort_its_requests_carried():
    wrong = [r["name"] for r in CLI_2A if (FIXTURES / "requests" / f"{r['name']}.json").exists()
             and {s["effort"] for s in json.loads((FIXTURES / "requests" / f"{r['name']}.json").read_text())["shapes"]}
             != {_arg(r["harbor_args"], "--effort ")}]
    assert wrong == []


def test_every_task_2a_session_s_cli_version_is_the_version_its_init_event_reported():
    streams = {_recording_of(p): p for p in FIXTURES.glob("*.json")}
    wrong = [r["name"] for r in CLI_2A if r["name"] in streams
             and (json.loads(streams[r["name"]].read_text()).get("init") or {}).get("claude_code_version")
             not in (None, _arg(r["harbor_args"], "--ak version="))]
    assert wrong == []


def test_every_task_2a_token_mode_session_ran_with_the_eighteen_name_deny_list():
    wrong = [r["name"] for r in CLI_2A if r["name"] != "t2a-simple-key-sizes"
             and _arg(r["harbor_args"], "--ak disallowed_tools=") != DENY]
    assert wrong == []


PROBE_LOG = Path.home() / ".local" / "state" / "lh-probe" / "passthrough" / "requests.jsonl"


@pytest.mark.skipif(not (CACHE / "live-probe").is_dir() or not PROBE_LOG.is_file(),
                    reason="the live probe's recordings and the passthrough's log are not on this machine")
def test_the_live_probe_fixtures_are_the_cut_of_its_recordings(tmp_path):
    committed = sorted((FIXTURES / "live-probe").glob("*.json"))
    note = re.match(r"local recording live-probe \((.*); the passthrough's log\)$",
                    json.loads((FIXTURES / "live-probe" / "passthrough-log.json").read_text())["source"]).group(1)
    cut.live_probe(CACHE / "live-probe", PROBE_LOG, note, tmp_path)
    assert [p.name for p in committed if (tmp_path / p.name).read_text() != p.read_text()] == []
