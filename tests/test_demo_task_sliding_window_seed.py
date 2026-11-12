from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_sliding_window_port"


def test_sliding_window_seed_contains_expected_shared_and_task_specific_files():
    required = [
        SEED / "AGENTS.md",
        SEED / "docs" / "index.md",
        SEED / "docs" / "dev_guidelines.md",
        SEED / "docs" / "plans" / "templates" / "artifact_contracts.md",
        SEED / "docs" / "tasks" / "port_sliding_window_to_rust.md",
        SEED / "src_py" / "sliding_window.py",
        SEED / "rust" / "Cargo.toml",
        SEED / "rust" / "src" / "lib.rs",
        SEED / "rust" / "tests" / "smoke_sliding_window.rs",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert not missing, f"Missing expected sliding-window seed files: {missing}"
