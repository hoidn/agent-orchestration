"""Closed adapter argv contract regressions."""

import pytest

from orchestrator.providers.omp_launch_contract import parse_adapter_argv


def test_frozen_no_tools_authority_requires_explicit_conf_root() -> None:
    argv = [
        "run", "--lane", "omp_no_tools", "--model", "model",
        "--conf-root-device", "1", "--conf-root-inode", "2",
        "--conf-manifest-sha256", "a" * 64,
    ]
    with pytest.raises(ValueError, match="no-tools-only"):
        parse_adapter_argv(argv, {"omp_no_tools"})
