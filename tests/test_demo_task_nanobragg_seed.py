from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_nanobragg_accumulation_port"


def test_nanobragg_seed_contains_expected_shared_and_task_specific_files():
    required = [
        SEED / "AGENTS.md",
        SEED / "README.md",
        SEED / "docs" / "index.md",
        SEED / "docs" / "dev_guidelines.md",
        SEED / "docs" / "plans" / "templates" / "artifact_contracts.md",
        SEED / "docs" / "plans" / "templates" / "check_plan_schema.md",
        SEED / "docs" / "plans" / "templates" / "plan_template.md",
        SEED / "docs" / "plans" / "templates" / "review_template.md",
        SEED / "docs" / "tasks" / "port_nanobragg_accumulation_to_pytorch.md",
        SEED / "src_c" / "nanoBragg.c",
        SEED / "src_c" / "README.md",
        SEED / "torch_port" / "__init__.py",
        SEED / "torch_port" / "accumulation.py",
        SEED / "torch_port" / "geometry.py",
        SEED / "torch_port" / "types.py",
        SEED / "tests" / "test_smoke_accumulation.py",
        SEED / "fixtures" / "visible" / "README.md",
        SEED / "fixtures" / "visible" / "case_small.json",
    ]

    missing = [str(path.relative_to(ROOT)) for path in required if not path.exists()]
    assert not missing, f"Missing expected nanoBragg seed files: {missing}"


def test_nanobragg_task_fixture_targets_bounded_pytorch_porting():
    task_text = (SEED / "docs" / "tasks" / "port_nanobragg_accumulation_to_pytorch.md").read_text()

    assert "nanoBragg.c" in task_text
    assert "PyTorch" in task_text
    assert "tensor-level numerical parity" in task_text
    assert "do not port the entire program" in task_text
    assert "visible smoke checks are incomplete" in task_text
    assert "state/task.md" in task_text


def test_nanobragg_seed_stays_in_expected_dependency_band():
    readme_text = (SEED / "README.md").read_text()
    task_text = (SEED / "docs" / "tasks" / "port_nanobragg_accumulation_to_pytorch.md").read_text()

    forbidden_tokens = [
        "setup.py",
        "cmake",
        "ninja",
        "cuda",
        "external service",
        "remote API",
    ]

    haystack = f"{readme_text}\n{task_text}".lower()
    for token in forbidden_tokens:
        assert token not in haystack


def test_nanobragg_seed_exposes_local_visible_check_entrypoint():
    index_text = (SEED / "docs" / "index.md").read_text()
    smoke_test = (SEED / "tests" / "test_smoke_accumulation.py").read_text()

    assert "pytest -q" in index_text
    assert "import torch" in smoke_test
    assert "case_small" in smoke_test
    assert "shape" in smoke_test
