"""Suite-wide options. `--sample PERCENT` runs a random share of the collected tests.

The seed changes after every passing run. A run that fails or is interrupted keeps
its seed, so the next `--sample` run repeats the same tests until they pass.
"""

import re

import pytest

from tests.sampling import choose_seed, keep, record_outcome

# Modules whose in-process memo folds must stay equal to their bytes (tests/memo_fold_guard.py).
_FOLD_GUARDED = re.compile(r"test_(workflow_evaluated_|workflow_host_input|workflow_python_|workflow_run_ref_"
                           r"|dashboard_|cli_dashboard_command|cli_report_command)")
# Modules whose replay-free start views are recomputed with the replay.
_START_VIEW_GUARDED = re.compile(r"kill|resume|recovery|invalidate|parallel")


def pytest_addoption(parser):
    group = parser.getgroup("sampling")
    group.addoption("--sample", type=float, default=None, metavar="PERCENT",
                    help="run a random PERCENT of the collected tests; the seed is kept "
                         "until a run passes, then redrawn")
    group.addoption("--sample-seed", type=int, default=None, metavar="SEED",
                    help="use this seed for --sample instead of the kept or a new one")


def _is_controller(config) -> bool:
    return not hasattr(config, "workerinput")


def pytest_configure(config):
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
    if config.getoption("sample") is not None and _is_controller(config):
        record_outcome(config.rootpath, config.getoption("sample"),
                       config.getoption("sample_seed"), passed=exitstatus == 0)


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if config.getoption("sample") is None:
        return
    seed = config.getoption("sample_seed")
    origin = "kept from the last run, which did not pass" if config.sample_seed_reused else "new"
    after = ("the next --sample run draws a new seed" if exitstatus == 0
             else "the next --sample run repeats these tests")
    terminalreporter.write_line(
        f"sample: {config.getoption('sample'):g}% of the collected tests, seed {seed} ({origin}); {after}")


@pytest.fixture(autouse=True)
def _evaluated_fast_path_guards(request, monkeypatch):
    """Check the evaluated runtime's shared-state fast paths in the modules that exercise them."""
    module = request.node.path.name
    if not _FOLD_GUARDED.match(module):
        yield
        return
    from tests.memo_fold_guard import FoldGuard, install_start_view_guard

    guard = FoldGuard(monkeypatch)
    if _START_VIEW_GUARDED.search(module):
        install_start_view_guard(monkeypatch)
    yield
    guard.check(request.node.nodeid)
