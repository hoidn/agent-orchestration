from __future__ import annotations

import json
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


def test_nanobragg_visible_fixtures_make_parity_relevant_defaults_explicit():
    task_text = (SEED / "docs" / "tasks" / "port_nanobragg_accumulation_to_pytorch.md").read_text()
    fixture_dir = SEED / "fixtures" / "visible"

    assert "default_F" in task_text
    assert "do not guess" in task_text or "do not invent" in task_text

    for fixture_path in sorted(fixture_dir.glob("case_*.json")):
        payload = json.loads(fixture_path.read_text())
        assert "crystal" in payload, f"{fixture_path.name} missing crystal section"
        assert "default_F" in payload["crystal"], f"{fixture_path.name} missing crystal.default_F"


def test_nanobragg_seed_stays_in_expected_dependency_band():
    forbidden_paths = [
        SEED / "setup.py",
        SEED / "CMakeLists.txt",
        SEED / "requirements_cuda.txt",
        SEED / ".github" / "workflows" / "cuda.yml",
    ]

    missing_or_forbidden = [path for path in forbidden_paths if path.exists()]
    assert not missing_or_forbidden, f"Unexpected heavy-build or CUDA artifacts: {missing_or_forbidden}"


def test_nanobragg_seed_exposes_local_visible_check_entrypoint():
    index_text = (SEED / "docs" / "index.md").read_text()
    smoke_test_path = SEED / "tests" / "test_smoke_accumulation.py"

    assert smoke_test_path.exists(), f"Missing smoke test entrypoint: {smoke_test_path.relative_to(ROOT)}"

    smoke_test = smoke_test_path.read_text()

    assert "pytest -q" in index_text
    assert "import torch" in smoke_test
    assert "case_small" in smoke_test
    assert "shape" in smoke_test
