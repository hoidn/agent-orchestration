"""Keep isolated-runner process settings local to each experiment test."""

import ctypes
import os
import sys

import pytest


@pytest.fixture(autouse=True)
def restore_subreaper_after_experiment():
    if sys.platform != 'linux':
        yield
        return
    libc = ctypes.CDLL(None, use_errno=True)
    prior = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0
    try:
        yield
    finally:
        assert libc.prctl(36, prior.value, 0, 0, 0) == 0


# Imported by live studies (prr_direct_orc runner, orc_gp_example) and cheap to run.
_ALWAYS_RUN = frozenset(
    f'test_orc_structural_search_{name}.py' for name in ('pricing', 'metering', 'records', 'pareto')
)


def pytest_collection_modifyitems(config, items):
    """Skip the closed structural-search campaign tests unless asked for.

    The campaign code is kept but not selected (roadmap Phase 6); its tests are
    42% of the suite's wall time. Set ORCHESTRATE_CAMPAIGN_TESTS=1 to run them.
    The fast modules whose code live studies still import always run.
    """
    if os.getenv('ORCHESTRATE_CAMPAIGN_TESTS') == '1':
        return
    skip = pytest.mark.skip(reason='closed campaign tests (set ORCHESTRATE_CAMPAIGN_TESTS=1 to run)')
    for item in items:
        name = item.path.name
        if name.startswith('test_orc_structural_search_') and name not in _ALWAYS_RUN:
            item.add_marker(skip)
