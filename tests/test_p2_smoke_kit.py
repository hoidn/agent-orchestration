"""The P2 live-smoke kit: the launcher's refusals, the wrapper's call limits, a rehearsal end to end, the one
retry by resume, and the readout on constructed results.

`run_smoke.sh` is driven through its command line with the kit's own rehearsal stand-in, on a closed PATH and a
temporary HOME. A paid-path test (`authorized=True`) only ever reaches a refusal before any call, and its
`claude` on the closed PATH is a copy of the stand-in. No test reaches a provider.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tests.agent_session_shims import closed_path

REPO = Path(__file__).resolve().parents[1]
KIT = REPO / "experiments" / "p2_smoke"
MODEL = "claude-haiku-5-5"
NO_PROVIDER = REPO / "experiments" / "thread_m" / "no_provider"
WRAPPER_FLAGS = ["--setting-sources", "project", "--strict-mcp-config", "--disable-slash-commands",
                 "--max-budget-usd", "0.5"]
SOURCE = "experiments/orc_vs_single_call/workflows/best_of_n.orc"
PINNED_CLI = json.loads((KIT / "criterion.json").read_text())["cli_version"]


def _manifest(kit: Path, regenerate: bool = False) -> str:
    if regenerate:
        names = json.loads((kit / "manifest.json").read_text())
        (kit / "manifest.json").write_text(json.dumps(
            {name: hashlib.sha256((kit / name).read_bytes()).hexdigest() for name in names}, indent=2))
    return hashlib.sha256((kit / "manifest.json").read_bytes()).hexdigest()


def _head(checkout: Path) -> str | None:
    found = subprocess.run(["git", "-C", str(checkout), "rev-parse", "HEAD"], capture_output=True, text=True, check=False)
    return found.stdout.strip() if found.returncode == 0 else None


RUNTIME_COMMIT = _head(REPO)


def launch(tmp: Path, *, kit: Path = KIT, runtime: Path = REPO, rehearsal: bool = True, authorized: bool = False,
           path: tuple = (), claude_bin: Path | None = None, **extra: str | None) -> subprocess.CompletedProcess[str]:
    """`run_smoke.sh RUNTIME <tmp>/results`; a rehearsal with the kit's stand-in unless `rehearsal=False`, with the
    runtime's own HEAD as the ledger's runtime commit and `claude_bin` as P2SMOKE_CLAUDE_BIN."""
    (tmp / "home").mkdir(exist_ok=True)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH" and not key.startswith("P2SMOKE_")}
    env.update(HOME=str(tmp / "home"), PATH=closed_path(*path), P2SMOKE_PYTHON=sys.executable,
               P2SMOKE_MANIFEST_SHA256=_manifest(kit), P2SMOKE_RUNTIME_COMMIT=_head(runtime) or "none")
    if claude_bin is not None:
        env["P2SMOKE_CLAUDE_BIN"] = str(claude_bin)
    if rehearsal:
        env["P2SMOKE_REHEARSAL_STANDINS"] = str(kit / "rehearsal")
    if authorized:
        env["P2SMOKE_SPEND_AUTHORIZED"] = "yes"   # only ever with the stand-in or a stub on a closed PATH
    env = {key: value for key, value in {**env, **extra}.items() if value is not None}
    return subprocess.run(["bash", str(kit / "run_smoke.sh"), str(runtime), str(tmp / "results")], env=env,
                          capture_output=True, text=True, timeout=600, check=False)


def calls(tmp: Path) -> list[dict]:
    """Stand-in invocations that would have been paid calls (everything but `--version`)."""
    log = tmp / "home" / ".claude" / "p2smoke-standin.log"
    rows = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return [row for row in rows if row["argv"] != ["--version"]]


def refused(launched: subprocess.CompletedProcess[str], gate: str) -> bool:
    return launched.returncode == 3 and gate in launched.stderr


def nothing_launched(tmp: Path) -> bool:
    """No paid call, no slot claimed, no slot directory, no temporary debris."""
    results = tmp / "results"
    left = sorted(path.name for path in results.iterdir()) if results.exists() else []
    slots = [path for path in (tmp / "home" / ".local" / "state" / "p2smoke").glob("*")]
    return calls(tmp) == [] and left in ([], ["rehearsal-ledger"]) and slots == [] and not (
        results / "rehearsal-ledger" / "smoke").exists()


def readout(results: Path, *extra: str, commit: str | None = RUNTIME_COMMIT) -> subprocess.CompletedProcess[str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith("P2SMOKE_")}
    env.update({"PATH": closed_path()}, **({"P2SMOKE_RUNTIME_COMMIT": commit} if commit else {}))
    return subprocess.run([sys.executable, "-B", str(KIT / "readout.py"), str(results), *extra], capture_output=True,
                          text=True, timeout=120, check=False, env=env)


def _standin_bin(tmp: Path) -> Path:
    """A copy of the stand-in outside the kit, as a paid run's CLI (for paid-path refusals only)."""
    bin_dir = tmp / "standin-bin"
    bin_dir.mkdir(exist_ok=True)
    shutil.copy2(KIT / "rehearsal" / "claude", bin_dir / "claude")
    return bin_dir / "claude"


def _kit_copy(tmp: Path, edit, *, regenerate: bool) -> Path:
    kit = tmp / "kit"
    shutil.copytree(KIT, kit)
    edit(kit)
    _manifest(kit, regenerate)
    return kit


def _runtime(tmp: Path, edit=None, *, commit_edit: bool = False) -> Path:
    """A small committed checkout holding the orchestrator package and the best-of-N source."""
    runtime = tmp / "runtime"
    shutil.copytree(REPO / "orchestrator", runtime / "orchestrator", ignore=shutil.ignore_patterns("__pycache__"))
    (runtime / SOURCE).parent.mkdir(parents=True)
    shutil.copy2(REPO / SOURCE, runtime / SOURCE)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-C", str(runtime)]
    subprocess.run([*git, "init", "-q"], check=True)
    if edit and commit_edit:
        edit(runtime)
    subprocess.run([*git, "add", "-A"], check=True)
    subprocess.run([*git, "commit", "-qm", "runtime"], check=True)
    if edit and not commit_edit:
        edit(runtime)
    return runtime


def _probe(tmp: Path, *edits: tuple[str, str]) -> Path:
    """A copy of the kit's stand-in (marker line kept) with `edits` applied; returns its directory."""
    probe = tmp / "probe"
    probe.mkdir(exist_ok=True)
    text = (KIT / "rehearsal" / "claude").read_text()
    for old, new in edits:
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    (probe / "claude").write_text(text)
    (probe / "claude").chmod(0o700)
    return probe


def _fake_cli(tmp: Path, version: str) -> Path:
    """A `claude` that prints `version` and logs anything else (no marker line)."""
    bin_dir = tmp / "fake-cli"
    bin_dir.mkdir(exist_ok=True)
    (bin_dir / "claude").write_text(f'#!/bin/sh\n[ "$1" = --version ] && {{ echo "{version} (Claude Code)"; exit 0; }}\n'
                                    f'echo "$@" >> "{tmp}/fake-cli-ran"\n')
    (bin_dir / "claude").chmod(0o700)
    return bin_dir / "claude"


FORGED_CLI = "/opt/claude/versions/" + PINNED_CLI   # a real CLI's path in forged records (never executed)


def _forge_real(results: Path, source: Path) -> None:
    """Constructed results: a copy of `source`'s rehearsal records made to look like a real run in every field the
    stand-in leaves (the flag, each launch's executed binary, the CLI version, each init event), so the readout
    gives a verdict. The records are repointed at the copy, so edits to its attempts are what the readout reads."""
    for record in results.glob("smoke*/smoke.json"):
        meta = json.loads(record.read_text().replace(str(source), str(results)))
        meta.update(rehearsal=False, claude_version=f"{PINNED_CLI} (Claude Code)", claude_path=FORGED_CLI,
                    runtime_dirty=False)           # a rehearsal may run on a dirty tree; a real run cannot
        for entry in meta["launches"]:
            entry.update(standin=False, target=FORGED_CLI)
            stdout = Path(entry["bundle"]).parent / "stdout.txt"
            if stdout.exists():
                stdout.write_text(stdout.read_text().replace('"claude_code_version": "0.0.0"',
                                                             f'"claude_code_version": "{PINNED_CLI}"'))
        record.write_text(json.dumps(meta))


def _remove(path: Path) -> None:
    """rmtree, after giving back write permission (the launcher makes each slot's bin/ read-only)."""
    subprocess.run(["chmod", "-R", "u+rwx", str(path)], check=False)
    shutil.rmtree(path, ignore_errors=True)


@pytest.fixture
def tmp(tmp_path) -> Path:
    yield tmp_path
    _remove(tmp_path)


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("rehearsal")
    launched = launch(tmp)
    assert launched.returncode == 0, launched.stderr
    yield tmp
    _remove(tmp)


# --- refusals before anything is launched ---

def test_paid_run_refuses_without_spend_authorization(tmp):
    launched = launch(tmp, rehearsal=False, claude_bin=_standin_bin(tmp))
    assert refused(launched, "P2SMOKE_SPEND_AUTHORIZED") and nothing_launched(tmp), launched.stderr


def test_rehearsal_refuses_while_a_spend_authorization_is_set(tmp):
    launched = launch(tmp, authorized=True)
    assert refused(launched, "never runs while") and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("value, gate", [(None, "set P2SMOKE_MANIFEST_SHA256"), ("0" * 64, "not the ledger's")],
                         ids=["absent", "another"])
def test_launcher_refuses_without_the_ledgers_manifest_digest(tmp, value, gate):
    launched = launch(tmp, P2SMOKE_MANIFEST_SHA256=value)
    assert refused(launched, gate) and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("name", ["criterion.json", "readout.py", "smoke_claude.sh", "rehearsal/claude"])
def test_launcher_refuses_a_kit_file_other_than_the_manifests(tmp, name):
    kit = _kit_copy(tmp, lambda kit: (kit / name).write_text((kit / name).read_text() + "\n"), regenerate=False)
    launched = launch(tmp, kit=kit)
    assert refused(launched, "differ from manifest.json") and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("binding", ["codex_metered", "claude_unrestricted_workspace", "claude_metered_haiku"])
def test_launcher_refuses_any_binding_but_the_claude_metered_template(tmp, binding):
    def edit(kit):
        (kit / "providers.json").write_text(json.dumps({"providers.coder": binding,
                                                         "providers.judge": "claude_unrestricted_workspace_metered"}))
    launched = launch(tmp, kit=_kit_copy(tmp, edit, regenerate=True))
    assert refused(launched, "bindings:") and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("old, new", [(':model "gpt-6-sol"', ':model "claude-fable-5-1"'),
                                      (':effort "high"', ':effort "low"')], ids=["model", "effort"])
def test_launcher_refuses_a_source_whose_literals_are_not_the_ones_it_rebinds(tmp, old, new):
    def edit(runtime):
        source = runtime / SOURCE
        source.write_text(source.read_text().replace(old, new, 1))
    launched = launch(tmp, runtime=_runtime(tmp, edit, commit_edit=True))
    assert refused(launched, "bindings:") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_a_missing_runtime(tmp):
    launched = launch(tmp, runtime=tmp / "no-such-runtime")
    assert refused(launched, "no runtime") and nothing_launched(tmp), launched.stderr


def test_paid_run_refuses_a_runtime_with_uncommitted_changes(tmp):
    runtime = _runtime(tmp, lambda runtime: (runtime / "orchestrator" / "__init__.py").write_text("# changed\n"))
    launched = launch(tmp, runtime=runtime, rehearsal=False, authorized=True, claude_bin=_fake_cli(tmp, PINNED_CLI))
    assert refused(launched, "uncommitted changes (its tree must be clean)") and nothing_launched(tmp), launched.stderr
    assert not (tmp / "fake-cli-ran").exists()


def test_paid_run_refuses_a_cli_other_than_the_pinned_version(tmp):
    launched = launch(tmp, rehearsal=False, authorized=True, claude_bin=_fake_cli(tmp, "2.1.322"))
    assert refused(launched, f"not the pinned {PINNED_CLI}") and nothing_launched(tmp), launched.stderr
    assert not (tmp / "fake-cli-ran").exists()


def test_paid_run_refuses_a_cli_that_is_a_rehearsal_stand_in(tmp):
    launched = launch(tmp, rehearsal=False, authorized=True, claude_bin=_standin_bin(tmp))
    assert refused(launched, "is a rehearsal stand-in") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_inside_a_smoke(tmp):
    launched = launch(tmp, P2SMOKE_IN_RUN="1")
    assert refused(launched, "nested session") and nothing_launched(tmp), launched.stderr


def test_paid_run_refuses_the_no_provider_stub(tmp):
    log = NO_PROVIDER.parent / "no-provider.log"
    existed = log.exists()
    launched = launch(tmp, rehearsal=False, authorized=True, claude_bin=NO_PROVIDER / "claude")
    assert refused(launched, "no-provider stub") and nothing_launched(tmp), launched.stderr
    assert log.exists() == existed                       # the stub was resolved, never run


def test_rehearsal_runs_only_a_marked_stand_in(tmp):
    unmarked = tmp / "unmarked"
    unmarked.mkdir()
    (unmarked / "claude").write_text("#!/bin/sh\necho 9.9.9\n")
    (unmarked / "claude").chmod(0o700)
    launched = launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(unmarked))
    assert refused(launched, "no marker line") and nothing_launched(tmp), launched.stderr


def test_paid_run_refuses_a_used_slot(tmp):
    (tmp / "home" / ".local" / "state" / "p2smoke" / "smoke").mkdir(parents=True)
    launched = launch(tmp, rehearsal=False, authorized=True, claude_bin=_standin_bin(tmp))
    assert refused(launched, "slot smoke is used") and calls(tmp) == [], launched.stderr
    assert not (tmp / "results" / "smoke").exists()


# --- the wrapper's call limits ---

def _wrapper(tmp: Path, launches: dict[int, float | None]) -> subprocess.CompletedProcess[str]:
    """smoke_claude.sh with a recording CLI and a ledger already holding `launches` (n: reported cost or None)."""
    bin_dir, ledger = tmp / "slot" / "bin", tmp / "ledger"
    bin_dir.mkdir(parents=True)
    shutil.copy2(KIT / "smoke_claude.sh", bin_dir / "claude")
    (tmp / "cli").write_text(f'#!/bin/sh\necho "$@" >> "{tmp}/cli-ran"\n')
    (tmp / "cli").chmod(0o700)
    (bin_dir / "claude.target").write_text(f"{tmp / 'cli'}\n")
    (bin_dir / "ledger").write_text(f"{ledger}\n")
    (tmp / "slot" / "gate").write_text("test\n")              # the gate is open for this invocation's phase
    for n, cost in launches.items():
        attempt = tmp / "run" / f"attempt-{n}"
        attempt.mkdir(parents=True)
        (ledger / f"launch-{n}").mkdir(parents=True)
        (ledger / f"launch-{n}" / "bundle").write_text(f"{attempt / 'result.json'}\n")
        if cost is not None:
            (attempt / "usage.json").write_text(json.dumps({
                "status": "reported", "complete": True, "reported_cost_usd": cost, "source": "result.modelUsage",
                "rows": [{"model": MODEL, "tokens": {"input": 10, "output": 10, "cache_read": 0, "cache_write": 0}}]}))
    env = {"HOME": str(tmp), "PATH": closed_path(), "PYTHONPATH": str(REPO), "P2SMOKE_PHASE": "test",
           "ORCHESTRATOR_OUTPUT_BUNDLE_PATH": str(tmp / "run" / "next" / "result.json")}
    return subprocess.run([str(bin_dir / "claude"), "-p", "--model", MODEL], env=env, capture_output=True, text=True,
                          timeout=60, check=False)


def test_the_wrapper_refuses_an_eighth_call(tmp):
    ran = _wrapper(tmp, dict.fromkeys(range(1, 8), 0.01))
    assert (ran.returncode, (tmp / "cli-ran").exists()) == (98, False)
    assert "count" in (tmp / "slot" / "refused-calls.log").read_text()


def test_the_wrapper_refuses_a_call_that_could_pass_the_smoke_ceiling(tmp):
    ran = _wrapper(tmp, {1: 2.6})                       # 2.6 recorded + 0.5 for this call > 3
    assert (ran.returncode, (tmp / "cli-ran").exists()) == (98, False)
    assert "spend" in (tmp / "slot" / "refused-calls.log").read_text()


def test_the_wrapper_counts_an_unreported_launch_at_the_per_call_ceiling(tmp):
    ran = _wrapper(tmp, {1: None, 2: None, 3: None, 4: None, 5: None})   # 5 x 0.5 + 0.5 = 3: allowed
    assert ran.returncode == 0, ran.stderr
    assert (tmp / "cli-ran").read_text().split() == [*WRAPPER_FLAGS, "-p", "--model", MODEL]


def test_the_wrapper_refuses_a_claude_started_inside_the_smoke(tmp):
    bin_dir = tmp / "slot" / "bin"
    bin_dir.mkdir(parents=True)
    shutil.copy2(KIT / "smoke_claude.sh", bin_dir / "claude")
    ran = subprocess.run([str(bin_dir / "claude"), "-p"], env={"PATH": closed_path(), "P2SMOKE_IN_RUN": "1"},
                         capture_output=True, text=True, timeout=60, check=False)
    assert ran.returncode == 97 and (tmp / "slot" / "nested-calls.log").exists()


# --- the rehearsal ---

def test_rehearsal_makes_five_calls_each_through_the_wrapper_on_haiku_at_high_effort(rehearsal):
    made = calls(rehearsal)
    assert len(made) == 5
    for call in made:
        argv = call["argv"]
        assert (argv[:len(WRAPPER_FLAGS)], argv[argv.index("--model") + 1], argv[argv.index("--effort") + 1],
                "stream-json" in argv, call["in_run"]) == (WRAPPER_FLAGS, MODEL, "high", True, "1")


def test_rehearsal_is_killed_mid_map_and_completes_on_resume(rehearsal):
    meta = json.loads((rehearsal / "results" / "smoke" / "smoke.json").read_text())
    kill = meta["kill"]
    assert (len(kill["committed_before"]), len(kill["held"]), kill["exit"], meta["resume_exit"], meta["status"],
            len(meta["committed_after"]), meta["rehearsal"]) == (2, 2, -9, 0, "completed", 5, True)


def test_the_held_coders_never_reached_the_cli(rehearsal):
    meta = json.loads((rehearsal / "results" / "smoke" / "smoke.json").read_text())
    launched = {launch["bundle"] for launch in meta["launches"]}
    assert len(launched) == 5 and not launched & set(meta["kill"]["held"])
    assert meta["usage"]["run"]["unknown_attempts"] == 2


def test_the_slot_bin_is_read_only(rehearsal):
    bin_dir = rehearsal / "results" / "smoke" / "bin"
    assert [path.name for path in (bin_dir, *bin_dir.iterdir()) if path.stat().st_mode & 0o222] == []


def test_the_program_copy_binds_a_ten_minute_call_timeout(rehearsal):
    import re
    copy = (rehearsal / "results" / "smoke" / "workspace" / "workflows" / "best_of_n.orc").read_text()
    assert set(re.findall(r":timeout-sec\s+([^\s()]+)", copy)) == {"600"}


def test_a_retry_with_another_cli_than_the_first_slot_ran_is_refused(rehearsal):
    again = launch(rehearsal, P2SMOKE_INFRA_RETRY="other cli", P2SMOKE_REHEARSAL_STANDINS=str(_probe(rehearsal)))
    assert refused(again, "the first slot ran"), again.stderr
    assert not (rehearsal / "results" / "smoke-retry").exists()


def test_readout_gives_no_verdict_on_a_rehearsal(rehearsal):
    shown = readout(rehearsal / "results")
    found = json.loads(shown.stdout)
    assert (shown.returncode, found["verdict"], found["rehearsal"], found["infrastructure"]) == (2, None, True, [])
    assert all(found["checks"].values()), found["checks"]


def test_rehearsal_refuses_to_run_the_smoke_twice(rehearsal):
    again = launch(rehearsal)
    assert refused(again, "slot smoke is used"), again.stderr
    assert len(calls(rehearsal)) == 5


def test_a_retry_of_a_valid_observation_is_refused(rehearsal):
    again = launch(rehearsal, P2SMOKE_INFRA_RETRY="did not like it")
    assert refused(again, "not an infrastructure failure"), again.stderr
    assert len(calls(rehearsal)) == 5 and not (rehearsal / "results" / "smoke-retry").exists()


# --- the readout on constructed results ---

@pytest.fixture
def copied(rehearsal, tmp) -> Path:
    results = tmp / "results"
    shutil.copytree(rehearsal / "results", results, symlinks=True)
    for record in results.glob("smoke*/smoke.json"):
        record.write_text(record.read_text().replace(str(rehearsal / "results"), str(results)))
    return results


@pytest.fixture
def real(rehearsal, tmp) -> Path:
    results = tmp / "results"
    shutil.copytree(rehearsal / "results", results, symlinks=True)
    _forge_real(results, rehearsal / "results")
    return results


def test_flipping_the_rehearsal_flag_alone_gets_no_verdict(copied):
    record = copied / "smoke" / "smoke.json"
    record.write_text(json.dumps({**json.loads(record.read_text()), "rehearsal": False}))
    shown = readout(copied)
    assert shown.returncode == 2 and "stand-in" in shown.stderr, shown.stderr


def test_a_real_run_marked_as_a_rehearsal_is_refused(real):
    record = real / "smoke" / "smoke.json"
    record.write_text(json.dumps({**json.loads(record.read_text()), "rehearsal": True}))
    shown = readout(real)
    assert shown.returncode == 2 and "records disagree" in shown.stderr, shown.stderr


def _verdict(results: Path) -> dict:
    shown = readout(results)
    assert shown.returncode == 0, shown.stderr
    return json.loads(shown.stdout)


def _run_root(results: Path) -> Path:
    (memo,) = results.glob("smoke/workspace/.orchestrate/runs/*/memo.jsonl")
    return memo.parent


def test_readout_passes_the_good_result(real):
    found = _verdict(real)
    assert (found["verdict"], found["facts"]["paid_calls"]) == ("pass", 5), found["reasons"]


@pytest.mark.parametrize("which", [0, -1], ids=["coder-committed-before-the-kill", "judge"])
def test_readout_fails_a_redispatched_committed_item(real, which):
    memo = _run_root(real) / "memo.jsonl"
    rows = [json.loads(line) for line in memo.read_text().splitlines()]
    committed = [row for row in rows if row["record"] == "committed"][which]
    started = next(row for row in rows if row["record"] == "started" and row["identity"] == committed["identity"])
    memo.write_text(memo.read_text() + json.dumps({**started, "attempt": 2}) + "\n")
    found = _verdict(real)
    assert (found["verdict"], found["checks"]["no_redispatch"]) == ("fail", False), found["reasons"]


def _launched_attempt(results: Path, index: int = 0) -> Path:
    """The copy's attempt directory of the `index`-th launch (the records name the rehearsal's paths)."""
    meta = json.loads((results / "smoke" / "smoke.json").read_text())
    bundle = Path(meta["launches"][index]["bundle"])
    return _run_root(results) / "effects" / bundle.parent.parent.name / bundle.parent.name


def _edit_record(results: Path, edit, slot: str = "smoke") -> None:
    record = results / slot / "smoke.json"
    meta = json.loads(record.read_text())
    edit(meta)
    record.write_text(json.dumps(meta))


def test_readout_does_not_pass_a_missing_usage_file(real):
    (_launched_attempt(real) / "usage.json").unlink()
    found = _verdict(real)
    assert found["verdict"] == "undetermined" and any("usage not reported" in p for p in found["reasons"]), found
    assert found["checks"]["usage_recorded"] is False


def test_readout_fails_another_model(real):
    usage = _launched_attempt(real, 4) / "usage.json"
    value = json.loads(usage.read_text())
    value["rows"][0]["model"] = "claude-sonnet-5-5"
    usage.write_text(json.dumps(value))
    found = _verdict(real)
    assert (found["verdict"], found["checks"]["isolation"]) == ("fail", False), found
    assert any("another model" in p for p in found["reasons"]), found


@pytest.mark.parametrize("committed, held", [(1, 2), (3, 1), (2, 1), (0, 4)])
def test_readout_does_not_accept_a_kill_other_than_the_planned_one(real, committed, held):
    def edit(meta):
        kill = meta["kill"]
        coders = sorted(meta["committed_after"])[:4]
        kill["committed_before"] = coders[:committed]
        kill["held"] = (kill["held"] + [f"/nonexistent/held-{n}/result.json" for n in range(4)])[:held]
    _edit_record(real, edit)
    found = _verdict(real)
    assert (found["verdict"], found["checks"]["stopped_mid_map"]) == ("undetermined", False), found


def test_no_retry_after_a_kill_that_failed(real):
    def edit(meta):
        meta["kill"]["committed_before"] = meta["kill"]["committed_before"][:1]
        meta["resume_exit"] = 1                       # not completed, so only the failed kill can refuse it
    _edit_record(real, edit)
    checked = readout(real, "--retry-check")
    assert checked.returncode == 4 and json.loads(checked.stdout)["killed_as_planned"] is False, checked.stdout


def test_no_retry_of_a_run_that_completed(real):
    stdout = _launched_attempt(real, 0) / "stdout.txt"           # an infrastructure problem: version drift
    stdout.write_text(stdout.read_text().replace(f'"claude_code_version": "{PINNED_CLI}"', '"claude_code_version": "9.9.9"'))
    found = _verdict(real)
    checked = readout(real, "--retry-check")
    assert (found["verdict"], found["checks"]["completed"], checked.returncode) == ("undetermined", True, 4), checked.stdout


def test_readout_fails_a_held_attempt_that_has_usage(real):
    held = Path(json.loads((real / "smoke" / "smoke.json").read_text())["kill"]["held"][0]).parent
    shutil.copy2(_launched_attempt(real) / "usage.json", held / "usage.json")
    found = _verdict(real)
    assert (found["verdict"], found["checks"]["held_never_launched"]) == ("fail", False), found


def test_a_wrapper_spend_refusal_reads_as_fail(real):
    judge = _launched_attempt(real, 4)
    for name in ("stdout.txt", "usage.json"):
        (judge / name).unlink()
    _edit_record(real, lambda meta: meta["launches"][4].update(refused=True))
    (real / "smoke" / "refused-calls.log").write_text("spend: launch-5 refused\n")
    found = _verdict(real)
    assert (found["verdict"], found["checks"]["no_cost_stop"], found["infrastructure"]) == ("fail", False, []), found


@pytest.mark.parametrize("what", ["program", "price_table", "kit_in_runtime"])
def test_readout_does_not_pass_a_run_off_the_pinned_runtime(real, what):
    if what == "program":
        copy = real / "smoke" / "workspace" / "workflows" / "best_of_n.orc"
        copy.write_text(copy.read_text() + ";\n")
    else:
        _edit_record(real, lambda meta: meta.update({"price_table_sha256": "0" * 64} if what == "price_table"
                                                     else {"kit_in_runtime": False}))
    found = _verdict(real)
    assert found["verdict"] == "undetermined", found


def test_readout_fails_a_cost_over_the_ceiling(real):
    report = real / "smoke" / "report.json"
    value = json.loads(report.read_text())
    value["run"]["usage"]["cost_usd"] = 3.2
    report.write_text(json.dumps(value))
    found = _verdict(real)
    assert (found["verdict"], found["checks"]["cost_under_ceiling"]) == ("fail", False), found["reasons"]


def test_retry_check_refuses_a_valid_observation(rehearsal):
    assert readout(rehearsal / "results", "--retry-check").returncode == 4


# --- the one retry by resume ---

@pytest.fixture(scope="module")
def retried(tmp_path_factory) -> Path:
    """gamma's call on resume ends with an API error (infrastructure); the one retry resumes the same run."""
    tmp = tmp_path_factory.mktemp("retried")
    (tmp / "home" / ".claude").mkdir(parents=True)
    (tmp / "home" / ".claude" / "fail-gamma").touch()
    first = launch(tmp)
    assert first.returncode == 0, first.stderr
    retry = launch(tmp, P2SMOKE_INFRA_RETRY="gamma: API error")
    assert retry.returncode == 0, retry.stderr
    yield tmp
    _remove(tmp)


def test_an_infrastructure_failure_gets_one_retry_by_resume_and_no_second(retried):
    first = json.loads((retried / "results" / "smoke" / "smoke.json").read_text())
    final = json.loads((retried / "results" / "smoke-retry" / "smoke.json").read_text())
    assert (first["resume_exit"] != 0, final["resume_exit"], final["status"], len(calls(retried))) == (True, 0, "completed", 6)
    again = launch(retried, P2SMOKE_INFRA_RETRY="again")
    assert refused(again, "one retry is used"), again.stderr


def test_the_readout_uses_the_retry_and_names_the_attempt_it_replaced(retried, tmp):
    results = tmp / "results"
    shutil.copytree(retried / "results", results, symlinks=True)
    _forge_real(results, retried / "results")
    found = _verdict(results)
    assert (found["verdict"], found["attempt_used"], len(found["facts"]["replaced_attempts"])) == ("pass", "retry", 1), found


# --- review B1: a retry never erases evidence ---

ISOLATION_PROBE = ('"general-purpose", "Plan", "statusline-setup"]', '"general-purpose", "Plan", "statusline-setup", "developer"]')


def test_b1_a_completed_run_with_an_isolation_failure_gets_no_retry_and_reads_fail(tmp):
    """The reviewer's case: every init event lists a user agent; the first attempt completes."""
    probe = _probe(tmp, ISOLATION_PROBE)
    first = launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe))
    assert first.returncode == 0, first.stderr
    checked = readout(tmp / "results", "--retry-check")
    retry = launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe), P2SMOKE_INFRA_RETRY="isolation")
    assert checked.returncode == 4 and refused(retry, "not an infrastructure failure"), checked.stdout + retry.stderr
    assert len(calls(tmp)) == 5 and not (tmp / "results" / "smoke-retry").exists()
    results = tmp / "copy"
    shutil.copytree(tmp / "results", results, symlinks=True)
    _forge_real(results, tmp / "results")
    found = _verdict(results)
    assert (found["verdict"], found["checks"]["isolation"]) == ("fail", False), found


def test_b1_a_retry_keeps_the_problem_of_a_sibling_it_did_not_dispatch_again(tmp):
    """gamma fails with an API error on resume and delta succeeds with a drifted CLI version; the retry
    dispatches gamma and the judge again, and delta's problem stays."""
    probe = _probe(tmp, ('"agents": agents, "claude_code_version": "0.0.0"}]',
                         '"agents": agents, "claude_code_version": "9.9.9" if Path.cwd().name == "delta" else "0.0.0"}]'))
    (tmp / "home" / ".claude").mkdir(parents=True)
    (tmp / "home" / ".claude" / "fail-gamma").touch()
    assert launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe)).returncode == 0
    retry = launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe), P2SMOKE_INFRA_RETRY="gamma: API error")
    assert retry.returncode == 0, retry.stderr
    results = tmp / "copy"
    shutil.copytree(tmp / "results", results, symlinks=True)
    _forge_real(results, tmp / "results")
    found = _verdict(results)
    assert found["verdict"] == "undetermined" and len(found["facts"]["replaced_attempts"]) == 1, found
    assert any("claude_code_version" in problem for problem in found["infrastructure"]), found


# --- review M1: no call outlives the launcher ---

def test_a_call_in_flight_when_the_run_stops_is_terminated_and_recorded(tmp):
    """alpha fails at once, beta is still running: the driver stops the run, and the launcher terminates beta."""
    probe = _probe(tmp, ("sys.stdin.read()\n", "sys.stdin.read()\nif Path.cwd().name == 'beta':\n"
                                                "    __import__('time').sleep(60)\n"
                                                "    (home / 'slept-beta').touch()\n"))
    (tmp / "home" / ".claude").mkdir(parents=True)
    (tmp / "home" / ".claude" / "fail-alpha").touch()
    launched = launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe))
    assert launched.returncode == 0, launched.stderr
    meta = json.loads((tmp / "results" / "smoke" / "smoke.json").read_text())
    (terminated,) = meta["terminated"]
    with pytest.raises(ProcessLookupError):
        os.kill(terminated["pid"], 0)
    assert terminated["bundle"] in {entry["bundle"] for entry in meta["launches"]}
    assert not (tmp / "home" / ".claude" / "slept-beta").exists()
    found = json.loads(readout(tmp / "results").stdout)
    assert any("terminated" in problem for problem in found["infrastructure"]), found


# --- re-review N1: a model's own failure is never retried ---

INVALID_DELTA = ('bundle.write_text(json.dumps(answer))',
                 'bundle.write_text("not json" if Path.cwd().name == "delta" else json.dumps(answer))')


def test_n1_a_model_failure_beside_an_infrastructure_failure_gets_no_retry_and_reads_fail(tmp):
    """The reviewer's case: on resume gamma hits an API error and delta returns an invalid result."""
    probe = _probe(tmp, INVALID_DELTA)
    (tmp / "home" / ".claude").mkdir(parents=True)
    (tmp / "home" / ".claude" / "fail-gamma").touch()
    assert launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe)).returncode == 0
    checked = readout(tmp / "results", "--retry-check")
    retry = launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe), P2SMOKE_INFRA_RETRY="gamma: API error")
    assert checked.returncode == 4 and refused(retry, "not an infrastructure failure"), checked.stdout + retry.stderr
    assert not (tmp / "results" / "smoke-retry").exists()
    results = tmp / "copy"
    shutil.copytree(tmp / "results", results, symlinks=True)
    _forge_real(results, tmp / "results")
    found = _verdict(results)
    assert (found["verdict"], found["checks"]["no_model_failure"]) == ("fail", False), found


# --- re-review N2 and m3: the CLI binary and the runtime commit are named, not looked up ---

def test_paid_run_refuses_without_an_explicit_cli_binary(tmp):
    launched = launch(tmp, rehearsal=False, authorized=True, path=(_fake_cli(tmp, PINNED_CLI).parent,))
    assert refused(launched, "P2SMOKE_CLAUDE_BIN") and nothing_launched(tmp), launched.stderr


@pytest.mark.parametrize("commit, gate", [(None, "set P2SMOKE_RUNTIME_COMMIT"), ("0" * 40, "not the ledger's")],
                         ids=["absent", "another"])
def test_launcher_refuses_a_runtime_other_than_the_ledgers_commit(tmp, commit, gate):
    launched = launch(tmp, P2SMOKE_RUNTIME_COMMIT=commit)
    assert refused(launched, gate) and nothing_launched(tmp), launched.stderr


def test_the_record_names_the_executed_binary_and_its_hash(rehearsal):
    meta = json.loads((rehearsal / "results" / "smoke" / "smoke.json").read_text())
    standin = KIT / "rehearsal" / "claude"
    assert (meta["claude_path"], meta["claude_sha256"]) == (str(standin), hashlib.sha256(standin.read_bytes()).hexdigest())
    assert {entry["target"] for entry in meta["launches"]} == {str(standin)}


@pytest.mark.parametrize("commit", [None, "0" * 40], ids=["absent", "another"])
def test_readout_needs_the_ledgers_runtime_commit_for_a_verdict(real, commit):
    shown = readout(real, commit=commit)
    if commit is None:
        assert shown.returncode == 2 and "P2SMOKE_RUNTIME_COMMIT" in shown.stderr, shown.stderr
    else:
        assert json.loads(shown.stdout)["verdict"] == "undetermined", shown.stdout


def test_a_real_record_whose_binary_is_the_kits_stand_in_is_refused(real):
    _edit_record(real, lambda meta: meta["launches"][0].update(target=str(KIT / "rehearsal" / "claude")))
    shown = readout(real)
    assert shown.returncode == 2 and "records disagree" in shown.stderr, shown.stderr


# --- re-review 3 and 4: the sweep kills only the kit's calls, and misses none ---

def _proc_start(pid: int) -> str:
    return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]


def test_the_sweep_leaves_alone_a_recorded_pid_whose_start_time_does_not_match(tmp):
    """The reviewer's case: an unrelated session leader's pid in the ledger; its start time differs."""
    other = subprocess.Popen(["sleep", "300"], start_new_session=True)
    try:
        record = tmp / "results" / "rehearsal-ledger" / "launch-7"
        record.mkdir(parents=True)
        (record / "proc").write_text(f"{other.pid} {int(_proc_start(other.pid)) + 1} {other.pid}\n")
        probe = _probe(tmp, ("sys.stdin.read()\n", "sys.stdin.read()\nif Path.cwd().name == 'beta':\n"
                                                    "    __import__('time').sleep(30)\n"))
        (tmp / "home" / ".claude").mkdir(parents=True)
        (tmp / "home" / ".claude" / "fail-alpha").touch()
        assert launch(tmp, P2SMOKE_REHEARSAL_STANDINS=str(probe)).returncode == 0
        meta = json.loads((tmp / "results" / "smoke" / "smoke.json").read_text())
        assert other.poll() is None, "the sweep killed a process that is not the kit's"
        assert "launch-7" in {entry["launch"] for entry in meta["sweep_left_alone"]}, meta["sweep_left_alone"]
        assert "launch-7" not in {entry["launch"] for entry in meta["terminated"]}
    finally:
        other.kill()
        other.wait()


def _delayed_wrapper(where: str):
    """A kit copy whose wrapper, for beta only, sleeps 6 s at `where` (before its slot claim, or after its record)."""
    anchor = {"before_claim": 'ledger=$(cat "$here/ledger")\n', "after_record": '# 2b. the gate\n'}[where]

    def edit(kit):
        wrapper = kit / "smoke_claude.sh"
        text = wrapper.read_text()
        assert text.count(anchor) == 1, anchor
        wrapper.write_text(text.replace(anchor, '[ "${PWD##*/}" != beta ] || sleep 6\n' + anchor))
    return edit


@pytest.mark.parametrize("where", ["before_claim", "after_record"])
def test_a_call_starting_when_the_run_stops_never_reaches_the_cli(tmp, where):
    """The reviewer's injected delay: alpha fails at once while beta's wrapper is slow to start."""
    kit = _kit_copy(tmp, _delayed_wrapper(where), regenerate=True)
    (tmp / "home" / ".claude").mkdir(parents=True)
    (tmp / "home" / ".claude" / "fail-alpha").touch()
    assert launch(tmp, kit=kit).returncode == 0
    ledger = tmp / "results" / "rehearsal-ledger"
    deadline = __import__("time").monotonic() + 60
    while __import__("time").monotonic() < deadline and not all(
            (launch / "done").exists() or (launch / "refused").exists() or (launch / "gated").exists()
            or not _alive_record(launch) for launch in ledger.glob("launch-*")):
        __import__("time").sleep(0.2)
    __import__("time").sleep(7 if where == "before_claim" else 0)      # let a late claimant reach its gate
    assert [Path(call["cwd"]).name for call in calls(tmp)] == ["alpha"], calls(tmp)
    meta = json.loads((tmp / "results" / "smoke" / "smoke.json").read_text())
    if where == "after_record":
        assert [entry["launch"] for entry in meta["terminated"]], meta


def _alive_record(launch: Path) -> bool:
    try:
        pid = int((launch / "proc").read_text().split()[0])
        os.kill(pid, 0)
        return True
    except (OSError, ValueError, IndexError):
        return False


# --- re-review m11: every guard has a test that fails without it ---

def test_readout_fails_a_call_that_ran_outside_the_wrapper(real):
    """Hand resume: the judge's attempt has output but no launch record."""
    _edit_record(real, lambda meta: meta["launches"].pop())
    found = _verdict(real)
    assert (found["verdict"], found["checks"]["isolation"]) == ("fail", False), found
    assert any("without a launch record" in problem for problem in found["isolation_problems"]), found


def test_no_retry_when_an_isolation_problem_sits_beside_an_infrastructure_failure(real):
    api_error = _launched_attempt(real, 0) / "stdout.txt"
    api_error.write_text(api_error.read_text() + json.dumps(
        {"type": "result", "is_error": True, "api_error_status": 529, "result": "API Error: overloaded"}) + "\n")
    hooked = _launched_attempt(real, 1) / "stdout.txt"
    hooked.write_text(hooked.read_text() + json.dumps({"type": "system", "subtype": "hook_started"}) + "\n")
    _edit_record(real, lambda meta: meta.update(resume_exit=1))
    checked = readout(real, "--retry-check")
    shown = json.loads(checked.stdout)
    assert (checked.returncode, bool(shown["infrastructure_failure"]), bool(shown["isolation"])) == (4, True, True), shown


def test_readout_does_not_pass_a_run_on_a_dirty_runtime(real):
    _edit_record(real, lambda meta: meta.update(runtime_dirty=True))
    assert _verdict(real)["verdict"] == "undetermined"


def test_paid_run_refuses_a_kit_that_is_not_the_runtimes_own(tmp):
    launched = launch(tmp, runtime=_runtime(tmp), rehearsal=False, authorized=True,
                      claude_bin=_fake_cli(tmp, PINNED_CLI))
    assert refused(launched, "not the runtime's own experiments/p2_smoke") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_a_program_copy_other_than_the_pinned_one(tmp):
    def edit(kit):
        edit_json = json.loads((kit / "criterion.json").read_text())
        edit_json["program_sha256"] = "0" * 64
        (kit / "criterion.json").write_text(json.dumps(edit_json))
    launched = launch(tmp, kit=_kit_copy(tmp, edit, regenerate=True))
    assert refused(launched, "program copy is not the pinned one") and nothing_launched(tmp), launched.stderr


def test_readout_treats_a_launch_without_a_bundle_as_infrastructure(real, tmp, monkeypatch):
    _edit_record(real, lambda meta: meta["launches"].append({"launch": "launch-6", "bundle": None, "target": FORGED_CLI,
                                                              "standin": False, "refused": False}))
    (tmp / "stdout.txt").write_text("")                    # a file the readout must not read from its cwd
    found = _verdict(real)
    assert found["verdict"] == "undetermined" and any("no attempt" in p for p in found["infrastructure"]), found


# --- the frozen files ---

def test_the_kit_files_are_the_manifests():
    manifest = json.loads((KIT / "manifest.json").read_text())
    files = {path.relative_to(KIT).as_posix() for path in KIT.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    assert set(manifest) == files - {"manifest.json", "README.md"}
    assert {name: hashlib.sha256((KIT / name).read_bytes()).hexdigest() for name in manifest} == manifest
