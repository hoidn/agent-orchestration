from pathlib import Path

import pytest

from orchestrator.experiments import evaluation


ROOT = Path(__file__).resolve().parents[2]
EXPERIMENT_MODULES = tuple(
    sorted(
        (ROOT / "orchestrator" / "experiments").rglob("*.py"),
        key=lambda path: path.relative_to(ROOT).as_posix(),
    )
)


@pytest.mark.parametrize(
    "module_path",
    EXPERIMENT_MODULES,
    ids=lambda path: path.relative_to(ROOT).as_posix(),
)
def test_experiment_production_modules_do_not_exceed_500_lines(
    module_path: Path,
) -> None:
    line_count = len(module_path.read_text(encoding="utf-8").splitlines())
    relative = module_path.relative_to(ROOT).as_posix()
    assert line_count <= 500, f"{relative} has {line_count} lines"


def test_evaluation_facade_public_api_is_exact() -> None:
    assert evaluation.__all__ == [
        "EvaluationError",
        "build_blind_packages",
        "build_calibration_packages",
        "ingest_review",
        "validate_calibration",
    ]
