"""Suite-wide options. `--sample PERCENT` runs a random share of the collected tests.

The seed changes after every passing run. A run that fails or is interrupted keeps
its seed, so the next `--sample` run repeats the same tests until they pass.

Provider guard: for the whole session the test process's own PATH starts with a directory of blocking
`claude`, `codex`, `omp` and `pi` stubs (`<basetemp>/provider-guard/bin`). A stub logs its name, argv, the
current test (`PYTEST_CURRENT_TEST`, when the environment kept it) and its parent's command line to
`<basetemp>/provider-guard/calls.log` and exits 97, and the controller fails the run when that log is not
empty. Tests that install their own stand-ins put them before the stubs, and tests that need "no provider on
PATH" use `tests.agent_session_shims.closed_path`, which never includes the stubs. Opt-in live smoke tests
need `ORC_TEST_ALLOW_REAL_PROVIDERS=1`, which turns the guard off.
"""

import os
from pathlib import Path

import pytest

from tests.sampling import choose_seed, keep, record_outcome

GUARDED_CLIS = ("claude", "codex", "omp", "pi")
GUARD_LOG_ENV = "ORC_TEST_PROVIDER_GUARD_LOG"
GUARD_STUB = """#!/bin/sh
printf '%s argv=[%s] test=[%s] parent=[%s]\\n' "$(basename "$0")" "$*" "${{PYTEST_CURRENT_TEST:-unknown}}" \\
  "$(tr '\\0' ' ' < /proc/$PPID/cmdline 2>/dev/null)" >> "${{ORC_TEST_PROVIDER_GUARD_LOG:-{log}}}"
echo "test provider guard: $(basename "$0") is blocked; install a stand-in or use closed_path()" >&2
exit 97
"""


def pytest_addoption(parser):
    group = parser.getgroup("sampling")
    group.addoption("--sample", type=float, default=None, metavar="PERCENT",
                    help="run a random PERCENT of the collected tests; the seed is kept "
                         "until a run passes, then redrawn")
    group.addoption("--sample-seed", type=int, default=None, metavar="SEED",
                    help="use this seed for --sample instead of the kept or a new one")


def _is_controller(config) -> bool:
    return not hasattr(config, "workerinput")


def _install_provider_guard(config) -> None:
    guard = config._tmp_path_factory.getbasetemp() / "provider-guard"
    (guard / "bin").mkdir(parents=True)
    log = guard / "calls.log"
    for cli in GUARDED_CLIS:
        (guard / "bin" / cli).write_text(GUARD_STUB.format(log=log), encoding="utf-8")
        (guard / "bin" / cli).chmod(0o755)
    os.environ["PATH"] = os.pathsep.join([str(guard / "bin"), os.environ.get("PATH", "")])
    os.environ[GUARD_LOG_ENV] = str(log)


def _guard_hits() -> list[str]:
    log = Path(os.environ.get(GUARD_LOG_ENV, "/nonexistent"))
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


@pytest.hookimpl(trylast=True)       # after the tmpdir plugin has set up the basetemp factory
def pytest_configure(config):
    # xdist workers are started later by the controller and inherit its PATH and log variable.
    if _is_controller(config) and os.environ.get("ORC_TEST_ALLOW_REAL_PROVIDERS") != "1":
        _install_provider_guard(config)
    # The controller picks the seed; xdist copies options to workers, so all agree.
    config.sample_seed_reused = False
    if config.getoption("sample") is None or not _is_controller(config):
        return
    if config.getoption("sample_seed") is None:
        seed, reused = choose_seed(config.rootpath, config.getoption("sample"))
        config.option.sample_seed, config.sample_seed_reused = seed, reused


def pytest_collection_modifyitems(config, items):
    percent = config.getoption("sample")
    if percent is None:
        return
    seed = config.getoption("sample_seed")
    dropped = [item for item in items if not keep(item.nodeid, percent, seed)]
    items[:] = [item for item in items if keep(item.nodeid, percent, seed)]
    config.hook.pytest_deselected(items=dropped)


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if _is_controller(config) and _guard_hits():
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
        exitstatus = session.exitstatus
    if config.getoption("sample") is not None and _is_controller(config):
        record_outcome(config.rootpath, config.getoption("sample"),
                       config.getoption("sample_seed"), passed=exitstatus == 0)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    hits = _guard_hits() if _is_controller(config) else []
    if hits:
        terminalreporter.section("provider guard: a test process launched a real provider CLI name", red=True)
        for line in hits:
            terminalreporter.write_line(line)
    if config.getoption("sample") is None:
        return
    seed = config.getoption("sample_seed")
    origin = "kept from the last run, which did not pass" if config.sample_seed_reused else "new"
    after = ("the next --sample run draws a new seed" if exitstatus == 0
             else "the next --sample run repeats these tests")
    terminalreporter.write_line(
        f"sample: {config.getoption('sample'):g}% of the collected tests, seed {seed} ({origin}); {after}")
