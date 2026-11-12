"""Keep isolated-runner process settings local to each experiment test."""

import ctypes
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
