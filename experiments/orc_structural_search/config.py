"""Experiment configuration for structural search: mutable scope, condition and compile inputs.

Paths (`source_root`, `providers_file`, `command_boundaries_file`) are relative to a candidate root.
"""

import json
from dataclasses import dataclass
from pathlib import Path

CONDITIONS = ("topology-only", "prompt-only", "provider-only", "joint")
INTERFACES = ("I1", "I2", "I3")


@dataclass(frozen=True)
class ExperimentConfig:
    mutable_files: tuple[str, ...]
    mutable_definitions: tuple[str, ...]
    condition: str
    interface: str
    entry_workflow: str
    source_root: str
    providers_file: str
    command_boundaries_file: str | None
    episode_wall_clock_sec: int
    criterion_sha256: str | None

    def __post_init__(self) -> None:
        if self.condition not in CONDITIONS:
            raise ValueError(f"condition must be one of {CONDITIONS}, got {self.condition!r}")
        if self.interface not in INTERFACES:
            raise ValueError(f"interface must be one of {INTERFACES}, got {self.interface!r}")


def load_config(path: Path) -> ExperimentConfig:
    """Read an ExperimentConfig from JSON; unknown or missing keys raise TypeError."""
    data = json.loads(path.read_text())
    for key in ("mutable_files", "mutable_definitions"):
        data[key] = tuple(data[key])
    return ExperimentConfig(**data)
