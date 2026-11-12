"""Suite-wide options. `--sample PERCENT` runs a random share of the collected tests."""

import random

from tests.sampling import keep


def pytest_addoption(parser):
    group = parser.getgroup("sampling")
    group.addoption("--sample", type=float, default=None, metavar="PERCENT",
                    help="run a random PERCENT of the collected tests (the seed is printed)")
    group.addoption("--sample-seed", type=int, default=None, metavar="SEED",
                    help="seed for --sample; reuse a printed seed to rerun the same tests")


def pytest_configure(config):
    # The controller picks the seed; xdist copies options to workers, so all agree.
    if (config.getoption("sample") is not None and config.getoption("sample_seed") is None
            and not hasattr(config, "workerinput")):
        config.option.sample_seed = random.SystemRandom().randrange(10**6)


def pytest_collection_modifyitems(config, items):
    percent = config.getoption("sample")
    if percent is None:
        return
    seed = config.getoption("sample_seed")
    dropped = [item for item in items if not keep(item.nodeid, percent, seed)]
    items[:] = [item for item in items if keep(item.nodeid, percent, seed)]
    config.hook.pytest_deselected(items=dropped)


def pytest_terminal_summary(terminalreporter, config):
    if config.getoption("sample") is not None:
        seed = config.getoption("sample_seed")
        terminalreporter.write_line(
            f"sample: {config.getoption('sample'):g}% of the collected tests, seed {seed} "
            f"(rerun the same tests with --sample-seed {seed})")
