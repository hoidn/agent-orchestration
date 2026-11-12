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


def pytest_collection_modifyitems(config, items):
    """Skip the closed structural-search campaign tests unless asked for.

    The campaign code is kept but not selected (roadmap Phase 6); its tests are
    42% of the suite's wall time. Set ORCHESTRATE_CAMPAIGN_TESTS=1 to run them.
    """
    if os.getenv('ORCHESTRATE_CAMPAIGN_TESTS'):
        return
    skip = pytest.mark.skip(reason='closed campaign tests (set ORCHESTRATE_CAMPAIGN_TESTS=1 to run)')
    for item in items:
        if item.path.name.startswith('test_orc_structural_search_'):
            item.add_marker(skip)
