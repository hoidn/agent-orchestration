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


def test_sliding_window_task_fixture_targets_bounded_python_to_rust_translation():
    task_text = (SEED / "docs" / "tasks" / "port_sliding_window_to_rust.md").read_text()

    assert "Python" in task_text
    assert "Rust" in task_text
    assert "standard library" in task_text
    assert "do not add FFI" in task_text
    assert "do not add external Python dependencies" in task_text
    assert "sliding-window" in task_text or "sliding window" in task_text
    assert "stride" in task_text
    assert "drop-last" in task_text or "drop last" in task_text


def test_sliding_window_seed_stays_in_tractable_dependency_band():
    python_source = (SEED / "src_py" / "sliding_window.py").read_text()
    cargo_toml = (SEED / "rust" / "Cargo.toml").read_text()

    forbidden_python = ["numpy", "pandas", "torch", "sklearn"]
    forbidden_rust = ["pyo3", "tokio", "ndarray"]

    for token in forbidden_python:
        assert token not in python_source
    for token in forbidden_rust:
        assert token not in cargo_toml


def test_sliding_window_seed_exposes_local_visible_check_entrypoint():
    smoke_test = (SEED / "rust" / "tests" / "smoke_sliding_window.rs").read_text()
    cargo_toml = (SEED / "rust" / "Cargo.toml").read_text()

    assert "[package]" in cargo_toml
    assert "#[test]" in smoke_test
    assert "sliding_windows" in smoke_test
    assert "pad" in smoke_test or "drop_last" in smoke_test
