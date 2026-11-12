from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_linear_classifier_port"


def test_task_seed_contains_expected_shared_and_task_specific_files():
    required = [
        SEED / "AGENTS.md",
        SEED / "docs" / "index.md",
        SEED / "docs" / "dev_guidelines.md",
        SEED / "docs" / "plans" / "templates" / "artifact_contracts.md",
        SEED / "docs" / "tasks" / "port_linear_classifier_to_rust.md",
        SEED / "src_py" / "linear_classifier.py",
        SEED / "rust" / "Cargo.toml",
        SEED / "rust" / "src" / "lib.rs",
        SEED / "rust" / "tests" / "smoke_linear_classifier.rs",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert not missing, f"Missing expected task-seed files: {missing}"
