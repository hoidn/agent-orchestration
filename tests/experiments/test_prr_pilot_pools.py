"""Offline pool/private-home smoke against the approved PRR-P2 runtime."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest


RUNTIME_COMMIT = "675966acf67f842ec67bf474dc8da460ed4b4d8f"
RUNTIME_DEFAULT = Path("/home/ollie/sc-runtime-prr-direct-orc-20261024")
EVIDENCE = Path("/home/ollie/sc-evidence/preparation/PRR-P2-preparation-verification/pools")
SANDBOX_PROBE = ["bwrap", "--dev-bind", "/", "/", "--tmpfs", "/dev/shm", "--tmpfs", "/var/tmp",
                 "--unshare-pid", "--proc", "/proc", "true"]


DRIVER = r'''import hashlib, json, os, shutil, subprocess, sys
from pathlib import Path

runtime, source_task, scratch = map(Path, sys.argv[1:4])
runtime = runtime.resolve()
sys.path.insert(0, str(runtime))
from experiments.compare import pool as pooling, repos, sandbox, summarize

for module in (pooling, repos, sandbox, summarize):
    assert Path(module.__file__).resolve().is_relative_to(runtime), module.__file__
assert repos.runtime_commit(runtime) == "675966acf67f842ec67bf474dc8da460ed4b4d8f"

task = scratch / "task"
shutil.copytree(source_task, task)
base = (task / "base_commit").read_text().strip()
assert repos.git(runtime, "rev-parse", "--verify", base + "^{commit}") == base
compare_base = repos.build_candidate(runtime, base, task / "seed", scratch / "base-candidate")

empty_patch = scratch / "baseline.diff"
empty_patch.write_bytes(b"")
changed = scratch / "control-candidate"
assert repos.build_candidate(runtime, base, task / "seed", changed) == compare_base
(changed / "prr-pool-smoke-control.txt").write_text("small nonempty control patch\n")
partial_patch = scratch / "partial.diff"
partial_patch.write_bytes(repos.patch_of(changed, compare_base))
assert partial_patch.read_bytes()
raw_hashes = {"baseline": hashlib.sha256(empty_patch.read_bytes()).hexdigest(),
              "partial": hashlib.sha256(partial_patch.read_bytes()).hexdigest()}

judge = "gpt-6.1-sol"
criterion = scratch / "criterion.json"
criterion.write_text(json.dumps({
    "purpose": "calibration",
    "judges": [judge],
    "anchors": [],
    "rubric": {"workflow": "score_functional.orc", "entry": "score_functional::score",
               "criteria": ["quality"], "reference": None},
}, indent=2) + "\n")

fakebin = scratch / "fakebin"
fakebin.mkdir()
fake = fakebin / "codex"
controller = scratch / "controller" / "raw-source.diff"
controller.parent.mkdir()
controller.write_bytes(partial_patch.read_bytes())
peer = scratch / "peer" / "private.txt"
peer.parent.mkdir()
peer.write_text("inaccessible peer fixture\n")
fake.write_text(f"#!{sys.executable}\nraise SystemExit('pool-specific fake is installed after pool creation')\n",
                encoding="utf-8")
fake.chmod(0o755)
providers = scratch / "providers.json"
providers.write_text(json.dumps({"providers.judge": "codex_unrestricted_workspace"}) + "\n")

host_home = scratch / "empty-host-home"
host_home.mkdir()
config_data = sandbox.dependencies({"PATH": "", "HOME": str(host_home)})
config_data["codex"] = str(fake.resolve())
config_data["claude"] = None
config = scratch / "sandbox-dependencies.json"
config.write_text(json.dumps(config_data, indent=2) + "\n")
environment = {"COMPARE_SANDBOX": str(config), "HOME": str(host_home),
               "CODEX_HOME": str(host_home / ".codex"), "CLAUDE_CONFIG_DIR": str(host_home / ".claude")}
ref = {"main": str(repos.main_checkout(runtime)), "runtime": str(runtime), "base": base,
       "compare_base": compare_base}
pool_roots, mappings, homes, expected_hashes = [], [], [], []

for ordinal in (1, 2):
    root = scratch / f"pool-{ordinal}"
    batches = pooling.diff_batches([empty_patch, partial_patch], 1, 2, 2, ordinal)
    mapping = pooling.write_pool(task, criterion, root, [f"{judge}={providers}"], ref, {}, batches,
                                 environment=environment)
    assert len(mapping["batches"]) == 1 and len(mapping["batches"][0]) == 2
    assert len(mapping["clones"]) == 2
    assert all(entry["arm"] == "filler" for entry in mapping["clones"].values())
    for cid, entry in mapping["clones"].items():
        source_label = entry["labels"][0]
        raw = (empty_patch if source_label == "baseline" else partial_patch).read_bytes()
        recorded = (root / "records" / "patches" / f"{cid}.diff").read_bytes()
        clone_patch = repos.patch_of(root / "clones" / cid, mapping["compare_base"])
        assert hashlib.sha256(recorded).hexdigest() == raw_hashes[source_label]
        assert clone_patch == recorded
        assert hashlib.sha256(clone_patch).hexdigest() == raw_hashes[source_label]

    info = mapping["judges"][judge]
    home = Path(info["sandbox"]["home"])
    assert home.stat().st_mode & 0o777 == 0o700
    assert not (home / ".codex" / "auth.json").exists()
    assert not (home / ".claude" / ".credentials.json").exists()
    declaration = json.loads(Path(info["sandbox"]["declaration"]).read_text())
    assert controller not in map(Path, declaration["readonly"].values())
    assert peer not in map(Path, declaration["readonly"].values())
    assert str(controller) not in declaration["clones"] and str(peer) not in declaration["clones"]

    inputs = json.loads((root / f"records/score-inputs-{judge}.json").read_text())
    prompt_paths = inputs["batches"][0]["clones"]
    plan = {"ratings": {path: "S4" for path in prompt_paths},
            "controller": str(controller), "peer": str(peer)}
    fake.write_text("""#!%s
import json, os, re, sys
from pathlib import Path
prompt = sys.stdin.read()
plan = json.loads(%r)
paths = sorted((p for p in plan["ratings"] if p in prompt), key=prompt.index)
match = re.search(r"(?m)^- path: ([^\\n]+)$", prompt)
if not paths or match is None:
    raise SystemExit("unrecognized offline score request")
if "baseline.diff" in prompt or "partial.diff" in prompt or plan["controller"] in prompt or plan["peer"] in prompt:
    raise SystemExit("judge prompt exposed labels or controller paths")
read_only = {}
for clone in paths:
    probe = Path(clone) / ".prr-pool-write-probe"
    try:
        probe.write_text("must fail")
    except OSError:
        read_only[clone] = True
    else:
        probe.unlink()
        raise SystemExit("pool clone unexpectedly allowed writes")
if Path(plan["controller"]).exists() or Path(plan["peer"]).exists():
    raise SystemExit("ungranted controller or peer path was visible")
out = Path(match.group(1))
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps([{"clone": clone, "quality": "S4", "reason": "offline fixture"}
                           for clone in paths]), encoding="utf-8")
with Path("/tmp/prr-fake-calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps({"clones": paths, "read_only": read_only, "controller_visible": False,
                          "peer_visible": False}) + chr(10))
""" % (sys.executable, json.dumps(plan)), encoding="utf-8")
    fake.chmod(0o755)

    command = (root / f"records/score-{judge}.sh").read_text().strip()
    host_environment = dict(os.environ)
    for key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                "CLAUDE_CODE_OAUTH_TOKEN_FILE", "CODEX_HOME", "CLAUDE_CONFIG_DIR"):
        host_environment.pop(key, None)
    host_environment.update(HOME=str(host_home), CODEX_HOME=str(host_home / ".codex"),
                            CLAUDE_CONFIG_DIR=str(host_home / ".claude"))
    scored = subprocess.run(["bash", "-lc", command], env=host_environment,
                            cwd=runtime, capture_output=True, text=True, timeout=180)
    assert scored.returncode == 0, scored.stdout + "\n" + scored.stderr
    calls = ((root / "judges" / info["dir"] / "tmp" / "prr-fake-calls.jsonl").read_text().splitlines())
    assert len(calls) == 1
    event = json.loads(calls[0])
    assert set(event["read_only"].values()) == {True}
    assert event["controller_visible"] is False and event["peer_visible"] is False
    assert not any(".prr-pool-write-probe" in str(path) for path in (root / "clones").rglob("*"))

    assert not pooling.scan_judge(root, judge, "a" * 40)
    pooling.adjudicate_judge(root, judge, "cleared", "offline fake judge smoke")
    pooling.verify_pool(root)
    results = summarize.summarize(root, criterion)
    assert results.get("calibration") is None
    assert results["judges"] == [judge]
    assert len(results["clones"]) == 2
    assert set(results["clones"]) == set(mapping["clones"])
    assert all(results["clones"][cid]["score"] == 4 for cid in mapping["clones"])
    pool_roots.append(str(root))
    mappings.append(mapping)
    homes.append(str(home))
    expected_hashes.append(raw_hashes)

assert len(set(homes)) == 2 and homes[0] != homes[1]
print(json.dumps({"runtime": str(runtime), "runtime_commit": repos.runtime_commit(runtime),
                  "pools": pool_roots, "private_homes": homes, "clone_counts": [2, 2],
                  "one_batch_each": [len(m["batches"]) == 1 for m in mappings],
                  "raw_patch_sha256": expected_hashes, "calibration": [None, None],
                  "fake_provider_calls": 2}, sort_keys=True))
'''


def _open_tree(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        path.chmod(0o755)
        for child in path.iterdir():
            _open_tree(child)


def test_two_independent_anonymous_pilot_pools_use_private_read_only_judge_homes():
    if shutil.which("bwrap") is None or subprocess.run(SANDBOX_PROBE, capture_output=True).returncode:
        pytest.skip("the comparison sandbox requires working unprivileged bubblewrap")

    runtime = Path(os.environ.get("PRR_PILOT_RUNTIME", RUNTIME_DEFAULT)).resolve()
    if not runtime.is_dir():
        pytest.skip(f"approved PRR-P2 runtime is unavailable: {runtime}")
    actual_commit = subprocess.run(["git", "-C", str(runtime), "rev-parse", "HEAD"], check=True,
                                   capture_output=True, text=True).stdout.strip()
    assert actual_commit == RUNTIME_COMMIT

    repository = Path(__file__).resolve().parents[2]
    task_source = repository / "experiments/compare/tasks/pure-result-replay-command-recovery"
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    scratch = Path(tempfile.mkdtemp(prefix="prr-pool-smoke-", dir=EVIDENCE))
    log = EVIDENCE / "two-anonymous-pools.log"
    exit_file = EVIDENCE / "two-anonymous-pools.exit"
    try:
        child = subprocess.run([sys.executable, "-I", "-c", DRIVER, str(runtime), str(task_source), str(scratch)],
                              capture_output=True, text=True, timeout=360)
        log.write_text(child.stdout + child.stderr, encoding="utf-8")
        exit_file.write_text(f"{child.returncode}\n", encoding="utf-8")
        assert child.returncode == 0, child.stdout + "\n" + child.stderr
        report = json.loads(child.stdout.strip().splitlines()[-1])
        assert report["runtime_commit"] == RUNTIME_COMMIT
        assert report["clone_counts"] == [2, 2]
        assert report["one_batch_each"] == [True, True]
        assert report["calibration"] == [None, None]
        assert report["fake_provider_calls"] == 2
    finally:
        for clones in scratch.glob("pool-*/clones"):
            _open_tree(clones)
        _open_tree(scratch)
        shutil.rmtree(scratch)
