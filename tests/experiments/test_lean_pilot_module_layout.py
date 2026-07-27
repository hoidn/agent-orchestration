from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_MODULES = tuple(
    sorted(
        (ROOT / "orchestrator" / "experiments").glob("*.py"),
        key=lambda path: path.name,
    )
)


@pytest.mark.parametrize(
    "module_path",
    EXPERIMENT_MODULES,
    ids=lambda path: path.name,
)
def test_experiment_production_modules_do_not_exceed_500_lines(
    module_path: Path,
) -> None:
    line_count = len(module_path.read_text(encoding="utf-8").splitlines())
    assert line_count <= 500, f"{module_path.name} has {line_count} lines"
