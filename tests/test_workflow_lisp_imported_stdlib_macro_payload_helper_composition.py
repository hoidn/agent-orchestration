from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.workflow_lisp.compiler import compile_stage3_entrypoint
from orchestrator.workflow_lisp.diagnostics import LispFrontendCompileError
from orchestrator.workflow_lisp.workflows import ExternalToolBinding


FIXTURES = Path(__file__).parent / "fixtures" / "workflow_lisp" / "current235" / "modules"
VALID_ROOT = FIXTURES / "valid" / "imported_stdlib_macro_payload_helper_composition"
VALID_ENTRY_FIXTURE = (
    VALID_ROOT / "imported_stdlib_macro_payload_helper_composition" / "entry.orc"
)

INVALID_FIXTURES: dict[str, tuple[Path, Path, str]] = {
    "bad_field": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_bad_field",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_bad_field"
        / "imported_stdlib_macro_payload_helper_bad_field"
        / "entry.orc",
        "record_field_unknown",
    ),
    "signature_mismatch": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_signature_mismatch",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_signature_mismatch"
        / "imported_stdlib_macro_payload_helper_signature_mismatch"
        / "entry.orc",
        "type_mismatch",
    ),
    "effect_position_invalid": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_effect_position_invalid",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_effect_position_invalid"
        / "imported_stdlib_macro_payload_helper_effect_position_invalid"
        / "entry.orc",
        "effect_not_permitted",
    ),
    "variant_unproved": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_variant_unproved",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_variant_unproved"
        / "imported_stdlib_macro_payload_helper_variant_unproved"
        / "entry.orc",
        "variant_ref_unproved",
    ),
    "hidden_command_effect": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_hidden_command_effect",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_hidden_command_effect"
        / "imported_stdlib_macro_payload_helper_hidden_command_effect"
        / "entry.orc",
        "macro_hidden_effect",
    ),
    "non_symbol_callee": (
        FIXTURES / "invalid" / "imported_stdlib_macro_payload_helper_non_symbol_callee",
        FIXTURES
        / "invalid"
        / "imported_stdlib_macro_payload_helper_non_symbol_callee"
        / "imported_stdlib_macro_payload_helper_non_symbol_callee"
        / "entry.orc",
        "frontend_parse_error",
    ),
}


def _compile_entry_fixture(
    path: Path,
    *,
    source_root: Path,
    tmp_path: Path,
    command_boundaries: dict[str, ExternalToolBinding] | None = None,
):
    return compile_stage3_entrypoint(
        path,
        source_roots=(source_root,),
        provider_externs={},
        prompt_externs={},
        command_boundaries=command_boundaries or {},
        validate_shared=True,
        workspace_root=tmp_path,

    )






def test_positive_imported_stdlib_macro_payload_helper_route_compiles_on_wcc_schema2_and_executes(
    tmp_path: Path,
) -> None:
    result = _compile_entry_fixture(VALID_ENTRY_FIXTURE, source_root=VALID_ROOT, tmp_path=tmp_path)

    assert result.entry_result.lowering_schema_version == 2









@pytest.mark.parametrize(
    ("fixture_key", "command_boundaries"),
    [
        ("bad_field", None),
        ("signature_mismatch", None),
        ("effect_position_invalid", None),
        ("variant_unproved", None),
        (
            "hidden_command_effect",
            {
                "run_checks": ExternalToolBinding(
                    name="run_checks",
                    stable_command=("python", "scripts/run_checks.py"),
                )
            },
        ),
        ("non_symbol_callee", None),
    ],
)
def test_invalid_imported_stdlib_macro_payload_helper_routes_fail_with_owner_layer_diagnostics(
    tmp_path: Path,
    *,
    fixture_key: str,
    command_boundaries: dict[str, ExternalToolBinding] | None,
) -> None:
    source_root, path, expected_code = INVALID_FIXTURES[fixture_key]

    with pytest.raises(LispFrontendCompileError) as excinfo:
        _compile_entry_fixture(
            path,
            source_root=source_root,
            tmp_path=tmp_path,
            command_boundaries=command_boundaries,
        )

    assert excinfo.value.diagnostics[0].code == expected_code
