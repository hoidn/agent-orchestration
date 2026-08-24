"""OMP package assets (Task 5, OMP-I1)."""

from __future__ import annotations

from importlib import resources

import yaml

from orchestrator.omp_assets import neutral_config_path
from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_launch import neutral_conf_root

_BUNDLED_AGENTS = [
    "designer",
    "librarian",
    "reviewer",
    "scout",
    "security-reviewer",
    "sonic",
    "task",
]


def test_neutral_conf_path_helper_is_single_sourced() -> None:
    """F8: one neutral-conf path helper; the assets package reuses it."""
    assert neutral_config_path() == neutral_conf_root()


def test_neutral_conf_package_resolves() -> None:
    root = neutral_conf_root()
    assert root.endswith("confs/neutral")
    config = resources.files("orchestrator.omp_assets").joinpath(
        "confs", "neutral", "config.yml"
    )
    assert config.is_file()
    assert neutral_config_path() == root


def test_neutral_conf_contract() -> None:
    root = neutral_conf_root()
    with open(f"{root}/config.yml", encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    assert document["advisor"]["enabled"] is False
    assert document["memory"]["backend"] == "off"
    assert document["task"]["maxConcurrency"] == 1
    assert document["task"]["maxRecursionDepth"] == 0
    assert document["task"]["disabledAgents"] == _BUNDLED_AGENTS


def test_neutral_conf_tree_admits() -> None:
    import os

    fd = os.open(neutral_conf_root(), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        snapshot = admit_conf_tree(fd)
    finally:
        os.close(fd)
    assert snapshot.manifest_sha256
    assert "config.yml" in snapshot.files
    assert "agent/WATCHDOG.yml" not in snapshot.files
