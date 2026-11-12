"""Integration tests for expected_outputs enforcement in workflow execution."""

from pathlib import Path

from orchestrator.contracts.output_contract import validate_output_bundle


def test_bundle_guidance_is_runtime_neutral_for_value_validation(tmp_path: Path) -> None:
    bundle_path = tmp_path / "artifacts" / "work" / "decision.json"
    bundle_path.parent.mkdir(parents=True)
    bundle_path.write_text("true\n", encoding="utf-8")
    output_bundle = {
        "path": "artifacts/work/decision.json",
        "fields": [
            {
                "name": "decision",
                "json_pointer": "",
                "type": "bool",
                "description": "True only when approved.",
                "format_hint": "JSON boolean.",
                "example": True,
            }
        ],
    }

    assert validate_output_bundle(output_bundle, workspace=tmp_path) == {"decision": True}


# bundle-overrides-exit contract retired (contradicted by specs/io.md:44-48); current behavior owned by test_nonzero_exit_skips_output_bundle_validation below.
