"""Launch-time OMP assets (Tasks 5 and 7, OMP-I1).

Holds the five preset conf packages (``neutral/``, ``advised/``, ``fanout/``,
``peer-team/``, ``advised-fanout/``) and the ``--output`` inference workflow
resource. Every path helper materializes through ``importlib.resources`` so
the same bytes are reachable from an installed wheel; no source-checkout path
is ever assumed.
"""

from __future__ import annotations

from importlib import resources
import os

__all__ = [
    "PRESET_CONF_NAMES",
    "inference_output_contract_path",
    "neutral_config_path",
    "preset_conf_root",
    "preset_conf_roots",
]

PRESET_CONF_NAMES = ("neutral", "advised", "fanout", "peer-team", "advised-fanout")


def _package_path(*components: str) -> str:
    return os.fspath(resources.files("orchestrator.omp_assets").joinpath(*components))


def neutral_config_path() -> str:
    """Absolute path of the neutral conf package (single launch helper)."""
    from orchestrator.providers.omp_launch import neutral_conf_root

    return neutral_conf_root()


def preset_conf_root(name: str) -> str:
    """Absolute path of one admitted preset conf package."""
    if name not in PRESET_CONF_NAMES:
        raise ValueError(f"unknown OMP preset conf: {name!r}")
    return _package_path("confs", name)


def preset_conf_roots() -> dict[str, str]:
    """All admitted preset conf packages keyed by preset name."""
    return {name: preset_conf_root(name) for name in PRESET_CONF_NAMES}


def inference_output_contract_path() -> str:
    """Absolute path of the ``--output`` inference workflow resource."""
    return _package_path("infer-output-contract.orc")
