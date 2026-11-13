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


def _manifest(kit: Path, regenerate: bool = False) -> str:
    if regenerate:
        names = json.loads((kit / "manifest.json").read_text())
        (kit / "manifest.json").write_text(json.dumps(
            {name: hashlib.sha256((kit / name).read_bytes()).hexdigest() for name in names}, indent=2))
    return hashlib.sha256((kit / "manifest.json").read_bytes()).hexdigest()


def launch(tmp: Path, *, kit: Path = KIT, runtime: Path = REPO, rehearsal: bool = True, authorized: bool = False,
           path: tuple = (), **extra: str | None) -> subprocess.CompletedProcess[str]:
    """`run_smoke.sh RUNTIME <tmp>/results`; a rehearsal with the kit's stand-in unless `rehearsal=False`."""
    (tmp / "home").mkdir(exist_ok=True)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH" and not key.startswith("P2SMOKE_")}
    env.update(HOME=str(tmp / "home"), PATH=closed_path(*path), P2SMOKE_PYTHON=sys.executable,
               P2SMOKE_MANIFEST_SHA256=_manifest(kit))
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


def readout(results: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-B", str(KIT / "readout.py"), str(results), *extra], capture_output=True,
                          text=True, timeout=120, check=False, env={**os.environ, "PATH": closed_path()})


def _standin_bin(tmp: Path) -> Path:
    """A closed-PATH directory whose `claude` is a copy of the stand-in (for paid-path refusals only)."""
    bin_dir = tmp / "standin-bin"
    bin_dir.mkdir(exist_ok=True)
    shutil.copy2(KIT / "rehearsal" / "claude", bin_dir / "claude")
    return bin_dir


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


def _flip_to_real(results: Path) -> None:
    """Constructed results: the rehearsal's records with `rehearsal` false, so the readout gives a verdict."""
    for record in results.glob("smoke*/smoke.json"):
        meta = json.loads(record.read_text())
        meta["rehearsal"] = False
        record.write_text(json.dumps(meta))


@pytest.fixture
def tmp(tmp_path) -> Path:
    yield tmp_path
    shutil.rmtree(tmp_path, ignore_errors=True)


@pytest.fixture(scope="module")
def rehearsal(tmp_path_factory) -> Path:
    tmp = tmp_path_factory.mktemp("rehearsal")
    launched = launch(tmp)
    assert launched.returncode == 0, launched.stderr
    yield tmp
    shutil.rmtree(tmp, ignore_errors=True)


# --- refusals before anything is launched ---

def test_paid_run_refuses_without_spend_authorization(tmp):
    launched = launch(tmp, rehearsal=False, path=(_standin_bin(tmp),))
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


def test_launcher_refuses_a_source_whose_models_are_not_the_ones_it_rebinds(tmp):
    def edit(runtime):
        source = runtime / SOURCE
        source.write_text(source.read_text().replace(':model "gpt-6-sol"', ':model "claude-fable-5-1"', 1))
    launched = launch(tmp, runtime=_runtime(tmp, edit, commit_edit=True))
    assert refused(launched, "bindings:") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_a_missing_runtime(tmp):
    launched = launch(tmp, runtime=tmp / "no-such-runtime")
    assert refused(launched, "no runtime") and nothing_launched(tmp), launched.stderr


def test_paid_run_refuses_a_runtime_with_uncommitted_changes(tmp):
    runtime = _runtime(tmp, lambda runtime: (runtime / "orchestrator" / "__init__.py").write_text("# changed\n"))
    launched = launch(tmp, runtime=runtime, rehearsal=False, authorized=True, path=(_standin_bin(tmp),))
    assert refused(launched, "uncommitted changes under orchestrator/") and nothing_launched(tmp), launched.stderr


def test_launcher_refuses_inside_a_smoke(tmp):
    launched = launch(tmp, P2SMOKE_IN_RUN="1")
    assert refused(launched, "nested session") and nothing_launched(tmp), launched.stderr


def test_paid_run_refuses_the_no_provider_stub(tmp):
    log = NO_PROVIDER.parent / "no-provider.log"
    existed = log.exists()
    launched = launch(tmp, rehearsal=False, authorized=True, path=(NO_PROVIDER,))
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
    launched = launch(tmp, rehearsal=False, authorized=True, path=(_standin_bin(tmp),))
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
    for n, cost in launches.items():
        attempt = tmp / "run" / f"attempt-{n}"
        attempt.mkdir(parents=True)
        (ledger / f"launch-{n}").mkdir(parents=True)
        (ledger / f"launch-{n}" / "bundle").write_text(f"{attempt / 'result.json'}\n")
        if cost is not None:
            (attempt / "usage.json").write_text(json.dumps({
                "status": "reported", "complete": True, "reported_cost_usd": cost, "source": "result.modelUsage",
                "rows": [{"model": MODEL, "tokens": {"input": 10, "output": 10, "cache_read": 0, "cache_write": 0}}]}))
    env = {"HOME": str(tmp), "PATH": closed_path(), "PYTHONPATH": str(REPO),
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

def test_rehearsal_makes_five_calls_each_through_the_wrapper_on_haiku(rehearsal):
    made = calls(rehearsal)
    assert len(made) == 5
    for call in made:
        argv = call["argv"]
        assert (argv[:len(WRAPPER_FLAGS)], argv[argv.index("--model") + 1], "stream-json" in argv, call["in_run"]) == (
            WRAPPER_FLAGS, MODEL, True, "1")


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
def real(rehearsal, tmp) -> Path:
    results = tmp / "results"
    shutil.copytree(rehearsal / "results", results, symlinks=True)
    _flip_to_real(results)
    return results


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


def _repoint(results: Path, rehearsal: Path) -> None:
    """Make the copy's records name the copy, so edits to its attempts are what the readout reads."""
    for record in results.glob("smoke*/smoke.json"):
        record.write_text(record.read_text().replace(str(rehearsal / "results"), str(results)))


def test_readout_does_not_pass_a_missing_usage_file(real, rehearsal):
    _repoint(real, rehearsal)
    (_launched_attempt(real) / "usage.json").unlink()
    found = _verdict(real)
    assert found["verdict"] == "undetermined" and any("usage not reported" in p for p in found["reasons"]), found
    assert found["checks"]["usage_recorded"] is False


def test_readout_does_not_pass_another_model(real, rehearsal):
    _repoint(real, rehearsal)
    usage = _launched_attempt(real, 4) / "usage.json"
    value = json.loads(usage.read_text())
    value["rows"][0]["model"] = "claude-sonnet-5-5"
    usage.write_text(json.dumps(value))
    found = _verdict(real)
    assert found["verdict"] == "undetermined" and any("another model" in p for p in found["reasons"]), found


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
    shutil.rmtree(tmp, ignore_errors=True)


def test_an_infrastructure_failure_gets_one_retry_by_resume_and_no_second(retried):
    first = json.loads((retried / "results" / "smoke" / "smoke.json").read_text())
    final = json.loads((retried / "results" / "smoke-retry" / "smoke.json").read_text())
    assert (first["resume_exit"] != 0, final["resume_exit"], final["status"], len(calls(retried))) == (True, 0, "completed", 6)
    again = launch(retried, P2SMOKE_INFRA_RETRY="again")
    assert refused(again, "one retry is used"), again.stderr


def test_the_readout_uses_the_retry_and_names_the_attempt_it_replaced(retried, tmp):
    results = tmp / "results"
    shutil.copytree(retried / "results", results, symlinks=True)
    _flip_to_real(results)
    found = _verdict(results)
    assert (found["verdict"], found["attempt_used"], len(found["facts"]["replaced_attempts"])) == ("pass", "retry", 1), found


# --- the frozen files ---

def test_the_kit_files_are_the_manifests():
    manifest = json.loads((KIT / "manifest.json").read_text())
    files = {path.relative_to(KIT).as_posix() for path in KIT.rglob("*") if path.is_file() and "__pycache__" not in path.parts}
    assert set(manifest) == files - {"manifest.json", "README.md"}
    assert {name: hashlib.sha256((KIT / name).read_bytes()).hexdigest() for name in manifest} == manifest
