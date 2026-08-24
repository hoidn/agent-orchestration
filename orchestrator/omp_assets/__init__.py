"""Launch-time OMP assets (Task 5, OMP-I1).

Holds the neutral conf package used by the no-tools and conf-inference lanes.
"""

from __future__ import annotations

__all__ = ["neutral_config_path"]


def neutral_config_path() -> str:
    """Absolute path of the neutral conf package (importlib-resources backed)."""
    from importlib import resources

    return resources.files("orchestrator.omp_assets").joinpath("confs", "neutral").as_posix()
