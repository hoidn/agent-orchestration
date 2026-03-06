from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_multiclass_metrics_port"


def test_task_seed_contains_expected_shared_and_task_specific_files():
    required = [
        SEED / "AGENTS.md",
        SEED / "docs" / "index.md",
        SEED / "docs" / "dev_guidelines.md",
        SEED / "docs" / "plans" / "templates" / "artifact_contracts.md",
        SEED / "docs" / "tasks" / "port_multiclass_metrics_to_rust.md",
        SEED / "src_py" / "multiclass_metrics.py",
        SEED / "rust" / "Cargo.toml",
        SEED / "rust" / "src" / "lib.rs",
        SEED / "rust" / "tests" / "smoke_metrics.rs",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert not missing, f"Missing expected task-seed files: {missing}"


def test_task_fixture_targets_bounded_python_to_rust_translation():
    task_text = (
        SEED / "docs" / "tasks" / "port_multiclass_metrics_to_rust.md"
    ).read_text()

    assert "Python" in task_text
    assert "Rust" in task_text
    assert "standard library" in task_text
    assert "do not add FFI" in task_text
    assert "do not add external Python dependencies" in task_text
    assert "multiclass" in task_text
    assert "expected calibration error" in task_text



def test_task_seed_stays_in_tractable_dependency_band():
    python_source = (SEED / "src_py" / "multiclass_metrics.py").read_text()
    cargo_toml = (SEED / "rust" / "Cargo.toml").read_text()

    forbidden_python = ["numpy", "pandas", "torch", "sklearn"]
    forbidden_rust = ["pyo3", "tokio", "ndarray"]

    for token in forbidden_python:
        assert token not in python_source
    for token in forbidden_rust:
        assert token not in cargo_toml



def test_task_seed_exposes_local_visible_check_entrypoint():
    smoke_test = (SEED / "rust" / "tests" / "smoke_metrics.rs").read_text()
    cargo_toml = (SEED / "rust" / "Cargo.toml").read_text()

    assert "[package]" in cargo_toml
    assert "#[test]" in smoke_test
    assert "top_k_accuracy" in smoke_test
