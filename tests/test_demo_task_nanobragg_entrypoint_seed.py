from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "examples" / "demo_task_nanobragg_entrypoint_port"


def test_entrypoint_seed_layout_exists():
    assert (SEED / "AGENTS.md").is_file()
    assert (SEED / "docs" / "index.md").is_file()
    assert (SEED / "docs" / "dev_guidelines.md").is_file()
    assert (SEED / "docs" / "tasks" / "port_nanobragg_entrypoint_to_pytorch.md").is_file()
    assert (SEED / "src_c" / "nanoBragg.c").is_file()
    assert (SEED / "src_c" / "README.md").is_file()
    assert (SEED / "torch_port" / "__init__.py").is_file()
    assert (SEED / "torch_port" / "entrypoint.py").is_file()
    assert (SEED / "torch_port" / "types.py").is_file()
    assert (SEED / "tests" / "test_smoke_entrypoint.py").is_file()


def test_entrypoint_task_names_function_and_source_region():
    task_text = (SEED / "docs" / "tasks" / "port_nanobragg_entrypoint_to_pytorch.md").read_text()
    assert "nanobragg_run" in task_text
    assert "nanoBragg.c" in task_text
    assert "main" in task_text


def test_smoke_test_imports_entrypoint():
    smoke_text = (SEED / "tests" / "test_smoke_entrypoint.py").read_text()
    assert "torch_port.entrypoint" in smoke_text
    assert "nanobragg_run" in smoke_text
