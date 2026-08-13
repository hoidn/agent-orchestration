from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from jsonschema import Draft202012Validator, ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[2]
TASK0_EVIDENCE = ROOT / "docs/plans/evidence/es-f1-large-scope-refreeze"
A1_SCHEMA = TASK0_EVIDENCE / "a1-calibration-anchor.schema.json"
A1_ROOT = Path("/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/pilot-2026-07-27/a1-v7")
POLICY_SHA256 = "sha256:" + "1" * 64
GIT_POLICY_SHA256 = "sha256:" + "2" * 64
PREEDIT_POLICY = TASK0_EVIDENCE / "preedit-policy-manifest.json"
PREEDIT_POLICY_SCHEMA = TASK0_EVIDENCE / "preedit-policy-manifest.schema.json"
SOURCE_CENSUS = TASK0_EVIDENCE / "source-census.json"
SOURCE_CENSUS_SCHEMA = TASK0_EVIDENCE / "source-census.schema.json"
TASK0_REVIEW_ADOPTION = TASK0_EVIDENCE / "task0-review-adoption.json"
TASK0_REVIEW_ADOPTION_SCHEMA = TASK0_EVIDENCE / "task0-review-adoption.schema.json"
A1_RECORD = TASK0_EVIDENCE / "a1-calibration-anchor.json"
F1_ROOT = ROOT / "experiments/orc_effectiveness/f1_es"
REFERENCE_SCHEMA = F1_ROOT / "reference-product.schema.json"
REFERENCE_RECORD = F1_ROOT / "reference-product.json"
REFERENCE_DISPOSITION = F1_ROOT / "reference-product-disposition.json"
TASK_SEED_MANIFEST = F1_ROOT / "task-seed-manifest.json"
REFERENCE_TOP_LEVEL_FIELDS = (
    "schema_version", "bindings", "lineage", "repository", "adaptation",
    "evidence", "evaluation", "patch", "metric", "no_delivery", "record_sha256",
)
REFERENCE_BINDING_IDS = (
    "preedit_policy",
    "a1_anchor",
    "task_seed_manifest",
    "task_profile",
    "configuration_consumer_census",
    "preedit_selector_manifest",
    "visible_task_contract",
    "evaluator_fixture_manifest",
    "governing_design",
    "governing_plan",
    "reference_calibration",
    "f1_evaluator",
)


def _calibration_module():
    return importlib.import_module("scripts.experiments.es.reference_calibration")


def _git_contract(calibration, **changes):
    values = {
        "executable": Path("/usr/bin/git"),
        "version": "2.43.0",
        "executable_sha256": (
            "sha256:"
            "2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668"
        ),
        "diff_controls": (
            "--no-ext-diff",
            "--no-textconv",
            "--diff-algorithm=histogram",
            "--find-renames=100%",
            "--find-copies=100%",
            "--find-copies-harder",
        ),
        "policy_sha256": GIT_POLICY_SHA256,
    }
    values.update(changes)
    return calibration.GitContract(**values)


def _production_policy(calibration, path: str):
    return calibration.MetricPathPolicy(
        path=path,
        classification="production_python",
        responsibility_ids=("RESP",),
    )


def _write_tree(root: Path, rows: dict[str, bytes]) -> None:
    for relative, payload in rows.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)


def _require_a1_evidence() -> None:
    if not A1_ROOT.is_dir():
        pytest.skip(f"retained A1 calibration evidence is unavailable: {A1_ROOT}")


def _build_anchor(calibration):
    _require_a1_evidence()
    return calibration.build_a1_anchor(
        evidence_root=A1_ROOT,
        preedit_policy_sha256=POLICY_SHA256,
        git_contract=_git_contract(calibration),
    )


def test_canonical_json_uses_ascii_sorted_compact_lf_domain() -> None:
    calibration = _calibration_module()

    assert calibration.canonical_json_bytes(
        {"z": "λ", "a": [1, True, None]}
    ) == b'{"a":[1,true,null],"z":"\\u03bb"}\n'

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.canonical_json_bytes({"value": float("nan")})
    assert caught.value.code == "record_noncanonical"


def test_record_sha256_omits_exactly_the_top_level_digest_field() -> None:
    calibration = _calibration_module()
    body = {
        "schema_version": "example.v1",
        "nested": {"record_sha256": "this nested field remains in the body"},
        "value": 7,
    }
    sealed = calibration.seal_record(body)

    assert calibration.canonical_record_body_bytes(sealed) == (
        calibration.canonical_json_bytes(body)
    )
    assert sealed["record_sha256"] == calibration.compute_record_sha256(sealed)
    assert calibration.validate_record_sha256(sealed) == sealed["record_sha256"]


@pytest.mark.parametrize(
    "mutation",
    ["body", "digest", "missing", "complete-record-hash"],
)
def test_record_sha256_rejects_projection_and_digest_tamper(mutation: str) -> None:
    calibration = _calibration_module()
    record = calibration.seal_record({"schema_version": "example.v1", "value": 7})
    if mutation == "body":
        record["value"] = 8
    elif mutation == "digest":
        record["record_sha256"] = "sha256:" + "0" * 64
    elif mutation == "missing":
        record.pop("record_sha256")
    else:
        record["record_sha256"] = "sha256:" + hashlib.sha256(
            calibration.canonical_json_bytes(record)
        ).hexdigest()

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.validate_record_sha256(record)
    assert caught.value.code == "record_sha256_invalid"


def test_closed_canonical_loader_rejects_extra_digest_field_and_duplicate_key(
    tmp_path: Path,
) -> None:
    calibration = _calibration_module()
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "value", "record_sha256"],
        "properties": {
            "schema_version": {"const": "example.v1"},
            "value": {"type": "integer"},
            "record_sha256": {"type": "string"},
        },
    }
    schema_path = tmp_path / "record.schema.json"
    schema_path.write_bytes(json.dumps(schema, indent=2).encode() + b"\n")

    extra = calibration.seal_record(
        {
            "schema_version": "example.v1",
            "value": 7,
            "other_record_sha256": "sha256:" + "0" * 64,
        }
    )
    record_path = tmp_path / "extra.json"
    record_path.write_bytes(calibration.canonical_json_bytes(extra))
    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.load_canonical_record(
            record_path,
            schema_path=schema_path,
            expected_record_sha256=extra["record_sha256"],
        )
    assert caught.value.code == "record_schema_invalid"

    duplicate = calibration.seal_record({"schema_version": "example.v1", "value": 7})
    raw = calibration.canonical_json_bytes(duplicate).replace(
        b'{"record_sha256":', b'{"value":7,"record_sha256":', 1
    )
    record_path.write_bytes(raw)
    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.load_canonical_record(
            record_path,
            schema_path=schema_path,
            expected_record_sha256=duplicate["record_sha256"],
        )
    assert caught.value.code == "record_noncanonical"


def test_git_contract_is_exact_and_rejects_tool_drift() -> None:
    calibration = _calibration_module()

    assert calibration.verify_git_contract(_git_contract(calibration)).version == "2.43.0"

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.verify_git_contract(
            _git_contract(calibration, executable_sha256="sha256:" + "0" * 64)
        )
    assert caught.value.code == "git_contract_invalid"


def test_numstat_parser_handles_normal_and_nul_rename_rows() -> None:
    calibration = _calibration_module()

    rows = calibration.parse_numstat_z(
        b"2\t1\tplain.py\0" b"0\t0\t\0old name.py\0new name.py\0"
    )

    assert rows == (
        calibration.NumstatRow(2, 1, "plain.py", "plain.py"),
        calibration.NumstatRow(0, 0, "old name.py", "new name.py"),
    )


def test_metric_counts_additions_and_separates_classifications(tmp_path: Path) -> None:
    calibration = _calibration_module()
    base = (tmp_path / "base").resolve()
    candidate = (tmp_path / "candidate").resolve()
    base.mkdir()
    candidate.mkdir()
    _write_tree(
        base,
        {
            "pkg/core.py": b"keep\nold\n",
            "pkg/deleted.py": b"gone forever\n",
            "pkg/rename_old.py": b"unique rename payload\n",
            "pkg/copy_source.py": b"unique copy payload " + b"x" * 1_024 + b"\n",
            "tests/test_core.py": b"old test\n",
            "docs/readme.md": b"unchanged docs\n",
        },
    )
    _write_tree(
        candidate,
        {
            "pkg/core.py": b"keep\nnew\nextra\n",
            "pkg/rename_new.py": b"unique rename payload\n",
            "pkg/copy_source.py": b"unique copy payload " + b"x" * 1_024 + b"\n",
            "pkg/copy_dest.py": b"unique copy payload " + b"x" * 1_024 + b"\n",
            "pkg/new.py": b"\n# comment\n",
            "tests/test_core.py": b"new test\nextra test\n",
            "docs/readme.md": b"unchanged docs\n",
        },
    )
    policies = tuple(
        sorted(
            (
                *(
                    _production_policy(calibration, path)
                    for path in (
                        "pkg/core.py",
                        "pkg/deleted.py",
                        "pkg/rename_new.py",
                        "pkg/copy_source.py",
                        "pkg/copy_dest.py",
                        "pkg/new.py",
                    )
                ),
                calibration.MetricPathPolicy("tests/test_core.py", "test", ()),
                calibration.MetricPathPolicy("docs/readme.md", "documentation", ()),
            ),
            key=lambda row: row.path,
        )
    )

    result = calibration.measure_implementation_delta(
        base_root=base,
        candidate_root=candidate,
        path_policies=policies,
        allowed_responsibility_ids=frozenset({"RESP"}),
        git_contract=_git_contract(calibration),
    )

    assert result.implementation_additions == 4
    assert result.implementation_deletions == 2
    assert result.base_physical_lines == 5
    assert result.candidate_postimage_physical_lines == 8
    assert result.totals_by_classification["test"].additions == 2
    assert result.totals_by_classification["test"].deletions == 1
    by_candidate = {row.candidate_path: row for row in result.rows}
    assert by_candidate["pkg/core.py"].change_kind == "modify"
    assert by_candidate["pkg/rename_new.py"].change_kind == "rename"
    assert by_candidate["pkg/copy_dest.py"].change_kind == "copy"
    assert by_candidate["pkg/new.py"].additions == 2
    deletion = next(row for row in result.rows if row.base_path == "pkg/deleted.py")
    assert deletion.change_kind == "delete"
    assert deletion.additions == 0
    assert deletion.deletions == 1


@pytest.mark.parametrize(
    "invalid_kind", ["binary", "non_utf8", "symlink", "generated", "unclassified"]
)
def test_metric_rejects_unsafe_or_unclassified_inputs(
    tmp_path: Path, invalid_kind: str
) -> None:
    calibration = _calibration_module()
    base = (tmp_path / invalid_kind / "base").resolve()
    candidate = (tmp_path / invalid_kind / "candidate").resolve()
    base.mkdir(parents=True)
    candidate.mkdir(parents=True)
    (base / "item.py").write_bytes(b"old\n")
    (candidate / "item.py").write_bytes(b"new\n")
    policies = (_production_policy(calibration, "item.py"),)
    if invalid_kind == "binary":
        (candidate / "item.py").write_bytes(b"new\0value\n")
    elif invalid_kind == "non_utf8":
        (candidate / "item.py").write_bytes(b"\xff\n")
    elif invalid_kind == "symlink":
        (candidate / "item.py").unlink()
        os.symlink(base / "item.py", candidate / "item.py")
    elif invalid_kind == "generated":
        policies = (
            calibration.MetricPathPolicy("item.py", "generated", ()),
        )
    elif invalid_kind == "unclassified":
        policies = ()

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.measure_implementation_delta(
            base_root=base,
            candidate_root=candidate,
            path_policies=policies,
            allowed_responsibility_ids=frozenset({"RESP"}),
            git_contract=_git_contract(calibration),
        )
    assert caught.value.code == "metric_input_invalid"


def test_metric_rejects_responsibility_and_git_contract_drift(tmp_path: Path) -> None:
    calibration = _calibration_module()
    base = (tmp_path / "base").resolve()
    candidate = (tmp_path / "candidate").resolve()
    base.mkdir()
    candidate.mkdir()
    (base / "item.py").write_bytes(b"old\n")
    (candidate / "item.py").write_bytes(b"new\n")

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.measure_implementation_delta(
            base_root=base,
            candidate_root=candidate,
            path_policies=(
                calibration.MetricPathPolicy(
                    "item.py", "production_python", ("UNKNOWN",)
                ),
            ),
            allowed_responsibility_ids=frozenset({"RESP"}),
            git_contract=_git_contract(calibration),
        )
    assert caught.value.code == "metric_input_invalid"

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.measure_implementation_delta(
            base_root=base,
            candidate_root=candidate,
            path_policies=(_production_policy(calibration, "item.py"),),
            allowed_responsibility_ids=frozenset({"RESP"}),
            git_contract=_git_contract(
                calibration,
                diff_controls=("--no-ext-diff",),
            ),
        )
    assert caught.value.code == "git_contract_invalid"


def test_a1_schema_is_closed_and_anchor_recomputes_667_2_690() -> None:
    calibration = _calibration_module()
    schema = json.loads(A1_SCHEMA.read_bytes())
    Draft202012Validator.check_schema(schema)
    anchor = _build_anchor(calibration)

    Draft202012Validator(schema).validate(anchor)
    assert [row["member_id"] for row in anchor["members"]] == [
        "pilot_lock",
        "summary",
        "block_record",
        "package_manifest",
        "direct_patch",
        "base_entrypoint",
        "base_types",
        "base_init",
        "direct_entrypoint",
        "direct_types",
        "direct_init",
        "review_1",
        "review_2",
    ]
    assert anchor["metric"]["implementation_additions"] == 667
    assert anchor["metric"]["implementation_deletions"] == 2
    assert anchor["metric"]["candidate_postimage_physical_lines"] == 690
    assert calibration.validate_record_sha256(anchor) == anchor["record_sha256"]

    opened = copy.deepcopy(anchor)
    opened["unexpected"] = None
    with pytest.raises(ValidationError):
        Draft202012Validator(schema).validate(opened)


def test_a1_loader_validates_schema_record_members_bindings_and_fresh_metric(
    tmp_path: Path,
) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    anchor_path = tmp_path / "a1-anchor.json"
    anchor_path.write_bytes(calibration.canonical_json_bytes(anchor))

    result = calibration.validate_a1_anchor(
        anchor_path,
        schema_path=A1_SCHEMA,
        expected_record_sha256=anchor["record_sha256"],
        expected_preedit_policy_sha256=POLICY_SHA256,
        git_contract=_git_contract(calibration),
    )

    assert result.record == anchor
    assert result.measurement.implementation_additions == 667
    assert result.measurement.implementation_deletions == 2
    assert result.measurement.candidate_postimage_physical_lines == 690


@pytest.mark.parametrize("mutation", ["stale-body", "digest", "metric", "extra", "policy"])
def test_a1_loader_rejects_record_and_policy_tamper(
    tmp_path: Path, mutation: str
) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    if mutation == "stale-body":
        anchor["selection"]["arm_id"] = "arm-tampered"
    elif mutation == "digest":
        anchor["record_sha256"] = "sha256:" + "0" * 64
    elif mutation == "metric":
        anchor["metric"]["implementation_additions"] = 666
        anchor = calibration.seal_record(anchor)
    elif mutation == "extra":
        anchor["unexpected_record_sha256"] = "sha256:" + "0" * 64
        anchor = calibration.seal_record(anchor)
    else:
        anchor["preedit_policy_sha256"] = "sha256:" + "3" * 64
        anchor = calibration.seal_record(anchor)
    anchor_path = tmp_path / f"{mutation}.json"
    anchor_path.write_bytes(calibration.canonical_json_bytes(anchor))

    with pytest.raises(calibration.CalibrationError):
        calibration.validate_a1_anchor(
            anchor_path,
            schema_path=A1_SCHEMA,
            expected_record_sha256=anchor["record_sha256"],
            expected_preedit_policy_sha256=POLICY_SHA256,
            git_contract=_git_contract(calibration),
        )


@pytest.mark.parametrize("mutation", ["missing", "symlink", "digest", "escape"])
def test_a1_member_validation_rejects_missing_alias_and_byte_drift(
    tmp_path: Path, mutation: str
) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    copied_root = (tmp_path / mutation / "a1-v7").resolve()
    for row in anchor["members"]:
        source = A1_ROOT / row["path"]
        target = copied_root / row["path"]
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    rows = copy.deepcopy(anchor["members"])
    target = copied_root / rows[5]["path"]
    if mutation == "missing":
        target.unlink()
    elif mutation == "symlink":
        target.unlink()
        os.symlink(copied_root / rows[6]["path"], target)
    elif mutation == "digest":
        target.write_bytes(target.read_bytes() + b"# drift\n")
    else:
        rows[5]["path"] = "../escape.py"

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.validate_a1_member_files(copied_root, rows)
    assert caught.value.code == "a1_member_invalid"


@pytest.mark.parametrize("mutation", ["pilot", "block", "summary", "review"])
def test_a1_internal_binding_validation_rejects_selection_drift(mutation: str) -> None:
    calibration = _calibration_module()
    anchor = _build_anchor(calibration)
    payloads = calibration.validate_a1_member_files(A1_ROOT, anchor["members"])
    changed = dict(payloads)
    if mutation == "pilot":
        value = json.loads(changed["pilot_lock"])
        value["task"]["task_id"] = "A2"
        changed["pilot_lock"] = json.dumps(value).encode()
    elif mutation == "block":
        value = json.loads(changed["block_record"])
        direct = next(
            row for row in value["treatment_executions"] if row["treatment_id"] == "DIRECT"
        )
        direct["lifecycle_outcome"] = "PROTOCOL_FAILURE"
        changed["block_record"] = json.dumps(value).encode()
    elif mutation == "summary":
        value = json.loads(changed["summary"])
        block = next(row for row in value["valid_blocks"] if row["block_id"] == anchor["selection"]["block_id"])
        outcome = next(
            row for row in block["method_outcomes"] if row["comparison"] == "DIRECT_VS_ORC"
        )
        outcome["method_outcome"] = "B_WIN"
        changed["summary"] = json.dumps(value).encode()
    else:
        value = json.loads(changed["review_1"])
        pair = next(
            row
            for row in value["pairwise_results"]
            if row["candidate_b_label"] == "candidate-3cca13b2595a"
        )
        pair["outcome"] = "A"
        changed["review_1"] = json.dumps(value).encode()

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.validate_a1_evidence_bindings(changed, anchor["selection"])
    assert caught.value.code == "a1_binding_invalid"


def _json_record(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_bytes())
    assert isinstance(value, dict)
    return value


def _raw_sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _git_environment(**changes: str) -> dict[str, str]:
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "LC_ALL": "C",
        "LANG": "C",
        "TZ": "UTC",
    }
    environment.update(changes)
    return environment


def _run_git(
    repository: Path,
    *args: str,
    input_bytes: bytes | None = None,
    extra_environment: dict[str, str] | None = None,
) -> bytes:
    return subprocess.run(
        ("/usr/bin/git", "-C", str(repository), *args),
        input=input_bytes,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(**(extra_environment or {})),
    ).stdout


def _binding_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError:
        return str(resolved)


def _authority_binding(path: Path, schema_path: Path | None = None) -> dict[str, Any]:
    binding: dict[str, Any] = {
        "path": _binding_path(path),
        "sha256": _raw_sha256(path),
    }
    record = _json_record(path) if path.suffix == ".json" else None
    if record is not None and "record_sha256" in record:
        binding["record_sha256"] = record["record_sha256"]
    if schema_path is not None:
        binding["schema_path"] = _binding_path(schema_path)
        binding["schema_sha256"] = _raw_sha256(schema_path)
    return binding


_VALIDATE_A1_AUTHORITIES = (
    (
        "policy",
        "--policy",
        PREEDIT_POLICY,
        "--policy-schema",
        PREEDIT_POLICY_SCHEMA,
        "--expected-policy-sha256",
    ),
    (
        "source-census",
        "--source-census",
        SOURCE_CENSUS,
        "--source-census-schema",
        SOURCE_CENSUS_SCHEMA,
        "--expected-source-census-sha256",
    ),
    (
        "task0-review-adoption",
        "--task0-review-adoption",
        TASK0_REVIEW_ADOPTION,
        "--task0-review-adoption-schema",
        TASK0_REVIEW_ADOPTION_SCHEMA,
        "--expected-task0-review-adoption-sha256",
    ),
    (
        "a1-anchor",
        "--a1-anchor",
        A1_RECORD,
        "--a1-anchor-schema",
        A1_SCHEMA,
        "--expected-a1-anchor-sha256",
    ),
)
_VALIDATE_A1_REQUIRED_OPTIONS = tuple(
    option
    for _, record_option, _, schema_option, _, digest_option in (
        _VALIDATE_A1_AUTHORITIES
    )
    for option in (record_option, schema_option, digest_option)
)


def _published_validate_a1_argv() -> list[str]:
    argv = [
        sys.executable,
        "-m",
        "scripts.experiments.es.reference_calibration",
        "validate-a1",
    ]
    for (
        _,
        record_option,
        record_path,
        schema_option,
        schema_path,
        digest_option,
    ) in _VALIDATE_A1_AUTHORITIES:
        argv.extend(
            (
                record_option,
                str(record_path.resolve()),
                schema_option,
                str(schema_path.resolve()),
                digest_option,
                _json_record(record_path)["record_sha256"],
            )
        )
    assert tuple(argv[4::2]) == _VALIDATE_A1_REQUIRED_OPTIONS
    assert len(argv) == 4 + 2 * len(_VALIDATE_A1_REQUIRED_OPTIONS)
    return argv


def _run_reference_calibration_cli(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        argv,
        check=False,
        cwd=ROOT,
        env={**os.environ, "PYTHONHASHSEED": "0"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


@pytest.mark.parametrize(
    "surface_mutation",
    [
        *[
            ("missing", option)
            for option in _VALIDATE_A1_REQUIRED_OPTIONS
        ],
        ("unknown", "--output"),
    ],
    ids=[
        *[
            "missing-" + option.removeprefix("--")
            for option in _VALIDATE_A1_REQUIRED_OPTIONS
        ],
        "unknown-output",
    ],
)
def test_task3a_validate_a1_cli_requires_exact_closed_option_surface(
    tmp_path: Path,
    surface_mutation: tuple[str, str],
) -> None:
    argv = _published_validate_a1_argv()
    mutation, option = surface_mutation
    if mutation == "missing":
        option_index = argv.index(option)
        del argv[option_index : option_index + 2]
    else:
        output = tmp_path / "not-an-output-command.json"
        argv.extend((option, str(output)))

    completed = _run_reference_calibration_cli(argv)

    assert completed.returncode == 2
    assert completed.stdout == b""
    if mutation == "unknown":
        assert not output.exists()


def test_task3a_validate_a1_cli_accepts_exact_published_authority_chain_silently(
) -> None:
    _require_a1_evidence()
    anchor = _json_record(A1_RECORD)
    bound_paths = {
        *[
            path
            for _, _, record_path, _, schema_path, _ in (
                _VALIDATE_A1_AUTHORITIES
            )
            for path in (record_path, schema_path)
        ],
        *[
            A1_ROOT / row["path"]
            for row in anchor["members"]
        ],
    }
    before = {
        path.resolve(): path.read_bytes()
        for path in bound_paths
    }

    completed = _run_reference_calibration_cli(
        _published_validate_a1_argv()
    )
    help_completed = _run_reference_calibration_cli(
        [
            sys.executable,
            "-m",
            "scripts.experiments.es.reference_calibration",
            "validate-a1",
            "--help",
        ]
    )

    assert completed.returncode == 0
    assert completed.stdout == b""
    assert completed.stderr == b""
    assert {
        path: path.read_bytes()
        for path in before
    } == before
    assert anchor["metric"] == {
        "metric_version": "implementation_delta_physical_lines.v1",
        "git_contract_policy_sha256": _json_record(PREEDIT_POLICY)[
            "record_sha256"
        ],
        "base_member_ids": ["base_entrypoint", "base_types", "base_init"],
        "candidate_member_ids": [
            "direct_entrypoint",
            "direct_types",
            "direct_init",
        ],
        "patch_member_id": "direct_patch",
        "implementation_additions": 667,
        "implementation_deletions": 2,
        "candidate_postimage_physical_lines": 690,
    }
    assert help_completed.returncode == 0
    assert help_completed.stdout != b""


@pytest.mark.parametrize(
    "authority_id",
    [row[0] for row in _VALIDATE_A1_AUTHORITIES],
)
def test_task3a_validate_a1_cli_rejects_each_expected_self_digest_drift(
    authority_id: str,
) -> None:
    argv = _published_validate_a1_argv()
    digest_option = next(
        row[5]
        for row in _VALIDATE_A1_AUTHORITIES
        if row[0] == authority_id
    )
    argv[argv.index(digest_option) + 1] = "sha256:" + "0" * 64

    completed = _run_reference_calibration_cli(argv)

    assert completed.returncode == 2
    assert completed.stdout == b""


@pytest.mark.parametrize(
    "authority_id",
    [row[0] for row in _VALIDATE_A1_AUTHORITIES],
)
def test_task3a_validate_a1_cli_rejects_byte_identical_nonpublished_schema_path(
    tmp_path: Path,
    authority_id: str,
) -> None:
    argv = _published_validate_a1_argv()
    _, _, _, schema_option, schema_path, _ = next(
        row for row in _VALIDATE_A1_AUTHORITIES if row[0] == authority_id
    )
    copied_schema = tmp_path / authority_id / schema_path.name
    copied_schema.parent.mkdir(parents=True)
    copied_schema.write_bytes(schema_path.read_bytes())
    argv[argv.index(schema_option) + 1] = str(copied_schema.resolve())

    completed = _run_reference_calibration_cli(argv)

    assert copied_schema.read_bytes() == schema_path.read_bytes()
    assert completed.returncode == 2
    assert completed.stdout == b""


@pytest.mark.parametrize(
    ("authority_id", "binding_field"),
    [
        ("source-census", "preedit_policy_sha256"),
        ("a1-anchor", "preedit_policy_sha256"),
        ("task0-review-adoption", "preedit_policy_sha256"),
        ("task0-review-adoption", "source_census_sha256"),
        ("task0-review-adoption", "a1_anchor_sha256"),
    ],
    ids=(
        "census-to-policy",
        "a1-to-policy",
        "adoption-to-policy",
        "adoption-to-census",
        "adoption-to-a1",
    ),
)
def test_task3a_validate_a1_cli_rejects_internally_resealed_authority_join_drift(
    tmp_path: Path,
    authority_id: str,
    binding_field: str,
) -> None:
    calibration = _calibration_module()
    (
        _,
        record_option,
        record_path,
        _,
        _,
        digest_option,
    ) = next(
        row for row in _VALIDATE_A1_AUTHORITIES if row[0] == authority_id
    )
    changed = _json_record(record_path)
    if authority_id == "task0-review-adoption":
        changed["bindings"][binding_field] = "sha256:" + "0" * 64
    else:
        changed[binding_field] = "sha256:" + "0" * 64
    changed = calibration.seal_record(
        {key: value for key, value in changed.items() if key != "record_sha256"}
    )
    changed_path = tmp_path / authority_id / record_path.name
    changed_path.parent.mkdir(parents=True)
    changed_path.write_bytes(calibration.canonical_json_bytes(changed))
    argv = _published_validate_a1_argv()
    argv[argv.index(record_option) + 1] = str(changed_path.resolve())
    argv[argv.index(digest_option) + 1] = changed["record_sha256"]

    completed = _run_reference_calibration_cli(argv)

    assert completed.returncode == 2
    assert completed.stdout == b""


def test_task3a_closed_reference_product_or_nonpromotable_disposition_exists() -> None:
    calibration = _calibration_module()

    assert REFERENCE_SCHEMA.is_file()
    schema = _json_record(REFERENCE_SCHEMA)
    Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    assert set(schema["properties"]) == set(REFERENCE_TOP_LEVEL_FIELDS)
    assert set(schema["required"]) == set(REFERENCE_TOP_LEVEL_FIELDS)
    assert REFERENCE_DISPOSITION.is_file()
    disposition = _json_record(REFERENCE_DISPOSITION)
    assert REFERENCE_DISPOSITION.read_bytes() == calibration.canonical_json_bytes(
        disposition
    )
    assert set(disposition) == {
        "schema_version",
        "package_status",
        "terminal_result",
        "scale_rejection",
        "successor_design",
        "task4_eligible",
        "reference_promotion_eligible",
        "reference_promotion_requires",
        "record_sha256",
    }
    assert calibration.validate_record_sha256(disposition) == disposition[
        "record_sha256"
    ]
    assert disposition["schema_version"] == "es_f1_reference_disposition.v1"
    assert (
        disposition["package_status"]
        == "SUPERSEDED_PRELAUNCH_SCOPE_TOO_SMALL"
    )
    assert disposition["terminal_result"] == "GREEN_TERMINAL_SCALE_REJECTION"
    assert disposition["scale_rejection"] == {
        "byte_count": 937062,
        "capture": "ES_F1_TASK3A_SCALE_REJECTION",
        "inclusive_band": {"maximum": 10000, "minimum": 5000},
        "observed_implementation_additions": 615,
        "path": (
            "/home/ollie/.local/state/orchestrator/es-reference-products/captures/"
            "task3a-24d907a-attempt-09/scale-rejection.json"
        ),
        "result": "REJECTED_OUT_OF_BAND",
        "sha256": (
            "sha256:79883e9e098463fc5f7a927ab7762cc8172408cc62763d68ee6cf538ad9a0692"
        ),
    }
    assert disposition["successor_design"] == {
        "commit": "69f242939732b6cebb3c698bd465172a02fbddcd",
        "path": "docs/superpowers/specs/2026-08-06-es-f1v2-config-ownership-task-design.md",
    }
    assert disposition["task4_eligible"] is False
    assert disposition["reference_promotion_eligible"] is False
    assert disposition["reference_promotion_requires"] == (
        "experiments/orc_effectiveness/f1_es/reference-product.json"
    )


def test_task3a_f1v2_reference_schema_replaces_extension_boundary_shape() -> None:
    schema = _json_record(REFERENCE_SCHEMA)

    Draft202012Validator.check_schema(schema)
    assert schema["properties"]["schema_version"] == {
        "const": "es_f1_reference_product.v2"
    }
    assert set(schema["required"]) == {
        "schema_version",
        "bindings",
        "lineage",
        "repository",
        "adaptation",
        "evidence",
        "evaluation",
        "patch",
        "metric",
        "no_delivery",
        "record_sha256",
    }
    assert set(schema["properties"]) == set(schema["required"])
    assert schema["additionalProperties"] is False
    for field in REFERENCE_TOP_LEVEL_FIELDS:
        if field in {"schema_version", "record_sha256"}:
            continue
        nested = schema["properties"][field]
        assert nested["type"] == "object"
        assert nested["additionalProperties"] is False
        assert set(nested["properties"]) == set(nested["required"])


F1V2_REPRESENTATIVE_PATH_LINES = {
    "ptycho/config/resolution.py": 2_200,
    "ptycho/config/strict_types.py": 2_200,
    "ptycho_torch/config_resolution.py": 2_200,
    "ptycho_torch/execution_request.py": 2_098,
}
F1V2_REPRESENTATIVE_RESPONSIBILITIES = {
    "ptycho/config/resolution.py": ("PUBLIC_RESOLUTION",),
    "ptycho/config/strict_types.py": ("BOUNDARY_VALIDATION_AND_DERIVATION",),
    "ptycho_torch/config_resolution.py": ("TRANSACTIONAL_TORCH_APPLICATION",),
    "ptycho_torch/execution_request.py": ("CONSUMER_MIGRATION",),
}
F1V2_CLAUSES = (
    "F1-H01-FOCUSED-SUITES",
    "F1-H02-SCHEMA-CONFORMANCE",
    "F1-H03-PUBLIC-RESOLUTION",
    "F1-H04-TRANSACTIONAL-APPLICATION",
    "F1-H05-STRICT-INPUT-CONTRACT",
    "F1-H06-DERIVED-PUBLIC-FIELDS",
    "F1-H07-CONSUMER-CLOSURE",
    "F1-H08-PROVENANCE-ROUNDTRIP",
    "F1-H09-CROSS-SURFACE-COHERENCE",
    "F1-H10-BYPASS-ORACLE",
)


def _representative_config_module(owner: str, line_count: int) -> bytes:
    lines = [
        f'"""Representative {owner} configuration surface."""',
        "from __future__ import annotations",
        "",
        "from dataclasses import dataclass",
        "from typing import Mapping",
        "",
        "@dataclass(frozen=True)",
        "class ConfigField:",
        "    name: str",
        "    owner: str",
        "    default: object",
        "",
        "FIELDS: tuple[ConfigField, ...] = (",
    ]
    footer = [
        ")",
        "",
        "def resolve(source: Mapping[str, object]) -> dict[str, object]:",
        '    """Resolve the declared fields without ambient configuration."""',
        "    return {field.name: source.get(field.name, field.default) for field in FIELDS}",
    ]
    field_count = line_count - len(lines) - len(footer)
    lines.extend(
        f'    ConfigField("{owner}_{ordinal:04d}", "{owner}", {ordinal}),'
        for ordinal in range(field_count)
    )
    lines.extend(footer)
    assert len(lines) == line_count
    return ("\n".join(lines) + "\n").encode()


def _f1v2_reference_repository(tmp_path: Path) -> tuple[Path, str, str]:
    manifest = _json_record(TASK_SEED_MANIFEST)
    seed_commit = manifest["recipe"]["commit"]
    staging = tmp_path / "reference.git"
    subprocess.run(
        ["/usr/bin/git", "clone", "--bare", manifest["repository"]["locator"], str(staging)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )
    _run_git(staging, "remote", "remove", "origin")
    index = tmp_path / "reference.index"
    environment = _git_environment(GIT_INDEX_FILE=str(index))
    _run_git(staging, "read-tree", seed_commit, extra_environment=environment)
    for path, line_count in F1V2_REPRESENTATIVE_PATH_LINES.items():
        payload = _representative_config_module(
            path.removesuffix(".py").replace("/", "_"), line_count
        )
        blob = _run_git(
            staging, "hash-object", "-w", "--stdin", input_bytes=payload
        ).decode().strip()
        _run_git(
            staging,
            "update-index",
            "--add",
            "--cacheinfo",
            f"100644,{blob},{path}",
            extra_environment=environment,
        )
    tree = _run_git(staging, "write-tree", extra_environment=environment).decode().strip()
    commit = _run_git(
        staging,
        "commit-tree",
        tree,
        "-p",
        seed_commit,
        input_bytes=b"Adapt F1v2 reference behavior\n",
        extra_environment={
            "GIT_AUTHOR_NAME": "ES F1v2 reference",
            "GIT_AUTHOR_EMAIL": "es-f1v2-reference@invalid",
            "GIT_AUTHOR_DATE": "2026-08-13T00:00:00-0700",
            "GIT_COMMITTER_NAME": "ES F1v2 reference",
            "GIT_COMMITTER_EMAIL": "es-f1v2-reference@invalid",
            "GIT_COMMITTER_DATE": "2026-08-13T00:00:00-0700",
        },
    ).decode().strip()
    _run_git(staging, "update-ref", "refs/heads/reference-product", commit)
    _run_git(staging, "update-ref", "-d", "refs/heads/task-seed")
    _run_git(staging, "symbolic-ref", "HEAD", "refs/heads/reference-product")
    repository = tmp_path / "reference-store" / "git-sha1" / commit
    repository.parent.mkdir(parents=True)
    staging.rename(repository)
    return repository.resolve(), commit, tree


def _f1v2_reference_blob(
    repository: Path, reference_commit: str
) -> tuple[str, bytes]:
    path = next(iter(F1V2_REPRESENTATIVE_PATH_LINES))
    object_id = _run_git(
        repository, "rev-parse", f"{reference_commit}:{path}"
    ).decode().strip()
    return object_id, _run_git(repository, "cat-file", "blob", object_id)


def _f1v2_reference_repository_row(
    repository: Path, reference_commit: str, reference_tree: str
) -> dict[str, object]:
    task_package = importlib.import_module("scripts.experiments.es.task_package")
    object_rows = _run_git(
        repository,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype)",
    ).splitlines()
    return {
        "storage_root": str(repository.parents[1]),
        "relative_path": f"git-sha1/{reference_commit}",
        "locator": str(repository),
        "head_ref": "refs/heads/reference-product",
        "object_format": "sha1",
        "commit_count": 3,
        "object_count": len(object_rows),
        "unreachable_object_count": 0,
        "repository_snapshot_sha256": task_package.directory_snapshot_digest(
            repository
        ),
        "reference_commit": reference_commit,
        "reference_tree": reference_tree,
    }


def _f1v2_reference_lineage(
    reference_commit: str, reference_tree: str
) -> dict[str, str]:
    seed = _json_record(TASK_SEED_MANIFEST)
    return {
        "projection_commit": seed["parent_projection"]["commit"],
        "projection_tree": seed["parent_projection"]["tree"],
        "task_seed_commit": seed["recipe"]["commit"],
        "task_seed_tree": seed["recipe"]["tree"],
        "reference_commit": reference_commit,
        "reference_tree": reference_tree,
    }


def test_task3a_f1v2_metric_replays_the_adapted_endpoint(tmp_path: Path) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(tmp_path)
    seed = _json_record(TASK_SEED_MANIFEST)

    metric = calibration.build_reference_metric(
        repository=repository,
        task_seed_commit=seed["recipe"]["commit"],
        reference_commit=reference_commit,
        changed_path_policies=tuple(
            calibration.MetricPathPolicy(
                path,
                "production_python",
                F1V2_REPRESENTATIVE_RESPONSIBILITIES[path],
            )
            for path in F1V2_REPRESENTATIVE_PATH_LINES
        ),
        git_contract=_git_contract(
            calibration,
            policy_sha256=_json_record(PREEDIT_POLICY)["record_sha256"],
        ),
    )

    assert metric["implementation_additions"] == 8_698
    assert metric["implementation_deletions"] == 0
    assert metric["base_commit"] == seed["recipe"]["commit"]
    assert metric["base_tree"] == seed["recipe"]["tree"]
    assert metric["reference_commit"] == reference_commit
    assert metric["reference_tree"] == reference_tree
    assert metric["historical_churn"] == {
        "authority": "non_authoritative_inclusive_per_commit_churn",
        "production_additions": 8_698,
        "production_deletions": 11_197,
    }


@pytest.mark.parametrize(
    ("entry_mode", "payload"),
    (
        ("120000", b"ptycho/config/resolution.py"),
        ("100644", b"binary\0payload\n"),
        ("100644", b"non-utf8: \xff\n"),
    ),
    ids=("symlink", "binary", "non-utf8"),
)
def test_task3a_f1v2_metric_rejects_changed_unsafe_git_entries(
    tmp_path: Path,
    entry_mode: str,
    payload: bytes,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, _ = _f1v2_reference_repository(tmp_path)
    seed = _json_record(TASK_SEED_MANIFEST)
    index = tmp_path / "unsafe.index"
    environment = _git_environment(GIT_INDEX_FILE=str(index))
    _run_git(repository, "read-tree", reference_commit, extra_environment=environment)
    blob = _run_git(
        repository,
        "hash-object",
        "-w",
        "--stdin",
        input_bytes=payload,
    ).decode().strip()
    _run_git(
        repository,
        "update-index",
        "--add",
        "--cacheinfo",
        f"{entry_mode},{blob},unsafe.py",
        extra_environment=environment,
    )
    unsafe_tree = _run_git(
        repository,
        "write-tree",
        extra_environment=environment,
    ).decode().strip()
    unsafe_commit = _run_git(
        repository,
        "commit-tree",
        unsafe_tree,
        "-p",
        reference_commit,
        input_bytes=b"Add unsafe reference entry\n",
        extra_environment={
            "GIT_AUTHOR_NAME": "ES F1v2 reference",
            "GIT_AUTHOR_EMAIL": "es-f1v2-reference@invalid",
            "GIT_AUTHOR_DATE": "2026-08-13T00:01:00-0700",
            "GIT_COMMITTER_NAME": "ES F1v2 reference",
            "GIT_COMMITTER_EMAIL": "es-f1v2-reference@invalid",
            "GIT_COMMITTER_DATE": "2026-08-13T00:01:00-0700",
        },
    ).decode().strip()

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.build_reference_metric(
            repository=repository,
            task_seed_commit=seed["recipe"]["commit"],
            reference_commit=unsafe_commit,
            changed_path_policies=tuple(
                calibration.MetricPathPolicy(
                    path,
                    "production_python",
                    F1V2_REPRESENTATIVE_RESPONSIBILITIES[path],
                )
                for path in F1V2_REPRESENTATIVE_PATH_LINES
            ),
            git_contract=_git_contract(
                calibration,
                policy_sha256=_json_record(PREEDIT_POLICY)["record_sha256"],
            ),
        )

    assert caught.value.code == "reference_metric_invalid"


def test_task3a_f1v2_metric_rejects_noncanonical_git_path_before_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = _calibration_module()
    object_id = "a" * 40
    root = tmp_path / "materialized"
    root.mkdir()
    escaped = tmp_path / "escape.txt"

    def crafted_tree(_repository: Path, *args: str) -> bytes:
        if args[:4] == ("ls-tree", "-r", "-z", "--full-tree"):
            return f"100644 blob {object_id}\t../escape.txt\0".encode()
        if args == ("cat-file", "blob", object_id):
            return b"must not escape\n"
        raise AssertionError(args)

    monkeypatch.setattr(calibration, "_reference_git_bytes", crafted_tree)

    with pytest.raises(calibration.CalibrationError) as caught:
        rows, _ = calibration._reference_text_tree(Path("/unused"), "tree")
        calibration._write_reference_metric_tree(root, rows)

    assert caught.value.code == "reference_metric_invalid"
    assert not escaped.exists()


def test_task3a_f1v2_bindings_reopen_current_task_artifacts() -> None:
    calibration = _calibration_module()

    bindings = calibration.build_reference_bindings()

    assert tuple(bindings) == REFERENCE_BINDING_IDS
    assert all(not Path(row["path"]).is_absolute() for row in bindings.values())
    for binding_id in ("configuration_consumer_census", "preedit_selector_manifest"):
        bound = _json_record(ROOT / bindings[binding_id]["path"])
        assert bindings[binding_id]["record_sha256"] == bound["record_sha256"]


def test_task3a_f1v2_no_delivery_scans_an_explicit_surface_domain(
    tmp_path: Path,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(tmp_path)
    seed = _json_record(TASK_SEED_MANIFEST)
    patch = _run_git(
        repository,
        "diff",
        "--patch",
        "--binary",
        "--full-index",
        "--no-color",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        *calibration.PINNED_GIT_DIFF_CONTROLS,
        seed["recipe"]["commit"],
        reference_commit,
        "--",
    )

    no_delivery, report = calibration.build_reference_no_delivery(
        task_seed_manifest=seed,
        reference_repository=repository,
        reference_commit=reference_commit,
        reference_tree=reference_tree,
        canonical_patch=patch,
        implementation_additions=8_698,
    )

    assert no_delivery["claim_limit"] == "not_provider_training_data_isolation"
    assert no_delivery["surface_set"] == "task3a_explicit_prelaunch_provider_surfaces.v2"
    assert no_delivery["reference_canary"] == calibration.F1V2_REFERENCE_CANARY
    assert no_delivery["decomposition_vocabulary"] == list(
        calibration.F1V2_DECOMPOSITION_VOCABULARY
    )
    assert report["matches"] == []
    assert report["task_seed_lookup_rows"]
    assert all(
        set(row) == {"object_id", "return_code", "stdout", "stderr"}
        and row["return_code"] == 1
        and row["stdout"] == ""
        and row["stderr"] == ""
        for row in report["task_seed_lookup_rows"]
    )
    assert report["surface_rows"]
    assert all(
        set(row) == {
            "surface_id",
            "surface_class",
            "logical_path",
            "byte_count",
            "sha256",
            "matches",
        }
        for row in report["surface_rows"]
    )
    assert {row["surface_class"] for row in report["surface_rows"]} >= {
        "visible_task_asset",
        "treatment_prompt",
        "provider_argv",
        "provider_environment",
        "provider_packet",
    }
    object_id, blob = _f1v2_reference_blob(repository, reference_commit)
    blob_row = {
        "object_id": object_id,
        "byte_count": len(blob),
        "sha256": "sha256:" + hashlib.sha256(blob).hexdigest(),
    }
    assert blob_row in report["reference_only_blob_rows"]
    expected_catalog_sha256 = "sha256:" + hashlib.sha256(
        calibration.canonical_json_bytes(
            {
                "object_ids": [
                    row["object_id"] for row in report["task_seed_lookup_rows"]
                ],
                "blob_rows": report["reference_only_blob_rows"],
            }
        )
    ).hexdigest()
    assert report["reference_only_object_catalog_sha256"] == (
        expected_catalog_sha256
    )
    assert no_delivery["reference_only_object_catalog_sha256"] == (
        expected_catalog_sha256
    )
    forbidden = {row["forbidden_id"]: row for row in report["forbidden_domain"]}
    assert forbidden[f"reference_only_object_id:{object_id}"] == {
        "forbidden_id": f"reference_only_object_id:{object_id}",
        "byte_count": len(object_id),
        "sha256": "sha256:" + hashlib.sha256(object_id.encode()).hexdigest(),
    }
    assert forbidden[f"reference_only_blob_bytes:{object_id}"] == {
        "forbidden_id": f"reference_only_blob_bytes:{object_id}",
        "byte_count": len(blob),
        "sha256": blob_row["sha256"],
    }
    digest = blob_row["sha256"]
    assert forbidden[f"reference_only_blob_digest:{object_id}"] == {
        "forbidden_id": f"reference_only_blob_digest:{object_id}",
        "byte_count": len(digest),
        "sha256": "sha256:" + hashlib.sha256(digest.encode()).hexdigest(),
    }


@pytest.mark.parametrize(
    "leak_kind",
    ("object_id", "blob_bytes", "blob_digest"),
)
def test_task3a_f1v2_no_delivery_rejects_reference_only_object_leaks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    leak_kind: str,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    seed = _json_record(TASK_SEED_MANIFEST)
    object_id, blob = _f1v2_reference_blob(repository, reference_commit)
    digest = "sha256:" + hashlib.sha256(blob).hexdigest()
    leaked_payload = {
        "object_id": object_id.encode(),
        "blob_bytes": blob,
        "blob_digest": digest.encode(),
    }[leak_kind]
    expected_forbidden_id = {
        "object_id": f"reference_only_object_id:{object_id}",
        "blob_bytes": f"reference_only_blob_bytes:{object_id}",
        "blob_digest": f"reference_only_blob_digest:{object_id}",
    }[leak_kind]
    monkeypatch.setattr(
        calibration,
        "_f1v2_provider_surfaces",
        lambda _manifest: [
            {
                "surface_id": "injected_provider_surface",
                "surface_class": "visible_task_asset",
                "logical_path": "benchmark/es_f1/injected",
                "payload": leaked_payload,
            }
        ],
    )

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.build_reference_no_delivery(
            task_seed_manifest=seed,
            reference_repository=repository,
            reference_commit=reference_commit,
            reference_tree=reference_tree,
            canonical_patch=b"unrelated patch",
            implementation_additions=8_698,
        )

    assert caught.value.code == "reference_no_delivery_invalid"
    assert {
        "surface_id": "injected_provider_surface",
        "forbidden_id": expected_forbidden_id,
    } in caught.value.value


def test_task3a_f1v2_no_delivery_rejects_unexpected_object_lookup_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    seed = _json_record(TASK_SEED_MANIFEST)
    original_run = calibration.subprocess.run

    def unexpected_lookup(argv, *args, **kwargs):
        if tuple(argv[-2:]) == ("-e", argv[-1]) and "cat-file" in argv:
            return subprocess.CompletedProcess(
                argv,
                128,
                stdout=b"",
                stderr=b"fatal: repository lookup failed\n",
            )
        return original_run(argv, *args, **kwargs)

    monkeypatch.setattr(calibration.subprocess, "run", unexpected_lookup)

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.build_reference_no_delivery(
            task_seed_manifest=seed,
            reference_repository=repository,
            reference_commit=reference_commit,
            reference_tree=reference_tree,
            canonical_patch=b"unrelated patch",
            implementation_additions=8_698,
        )

    assert caught.value.code == "reference_no_delivery_invalid"
    assert caught.value.value[0]["return_code"] == 128
    assert caught.value.value[0]["stderr"] == "fatal: repository lookup failed\n"


def test_task3a_f1v2_reference_repository_binding_reopens_exact_cas(
    tmp_path: Path,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    row = _f1v2_reference_repository_row(
        repository, reference_commit, reference_tree
    )

    reopened = calibration._validate_f1v2_reference_repository(
        row,
        _f1v2_reference_lineage(reference_commit, reference_tree),
    )

    assert reopened == repository
    schema = _json_record(REFERENCE_SCHEMA)
    assert set(schema["properties"]["repository"]["properties"]) == set(row)


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("storage_root", "{repository_parent}"),
        ("relative_path", "git-sha1/0000000000000000000000000000000000000000"),
        ("locator", "{repository_parent}"),
        ("object_format", "sha256"),
        ("commit_count", 2),
        ("object_count", 1),
        ("unreachable_object_count", 1),
        ("repository_snapshot_sha256", "sha256:" + "0" * 64),
    ),
)
def test_task3a_f1v2_reference_repository_binding_rejects_declared_drift(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    row = _f1v2_reference_repository_row(
        repository, reference_commit, reference_tree
    )
    row[field] = (
        str(repository.parent)
        if replacement == "{repository_parent}"
        else replacement
    )

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration._validate_f1v2_reference_repository(
            row,
            _f1v2_reference_lineage(reference_commit, reference_tree),
        )

    assert caught.value.code == "reference_repository_invalid"


@pytest.mark.parametrize(
    ("field", "replacement"),
    (
        ("storage_root", 1),
        ("storage_root", None),
        ("locator", 1),
        ("locator", None),
    ),
)
def test_task3a_f1v2_reference_repository_rejects_nonpath_binding_values(
    tmp_path: Path,
    field: str,
    replacement: object,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    row = _f1v2_reference_repository_row(
        repository, reference_commit, reference_tree
    )
    row[field] = replacement

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration._validate_f1v2_reference_repository(
            row,
            _f1v2_reference_lineage(reference_commit, reference_tree),
        )

    assert caught.value.code == "reference_repository_invalid"


@pytest.mark.parametrize(
    ("relative_path", "entry_kind"),
    (
        ("objects/info/alternates", "file"),
        ("info/grafts", "file"),
        ("shallow", "file"),
        ("refs/replace", "directory"),
    ),
)
def test_task3a_f1v2_reference_repository_rejects_git_escape_entries(
    tmp_path: Path,
    relative_path: str,
    entry_kind: str,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    row = _f1v2_reference_repository_row(
        repository, reference_commit, reference_tree
    )
    escape = repository / relative_path
    escape.parent.mkdir(parents=True, exist_ok=True)
    if entry_kind == "directory":
        escape.mkdir()
    else:
        escape.write_text("forbidden repository escape\n")

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration._validate_f1v2_reference_repository(
            row,
            _f1v2_reference_lineage(reference_commit, reference_tree),
        )

    assert caught.value.code == "reference_repository_invalid"
    assert caught.value.value == (relative_path,)


def test_task3a_f1v2_reference_repository_rejects_internal_symlink_before_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    row = _f1v2_reference_repository_row(
        repository, reference_commit, reference_tree
    )
    config = repository / "config"
    config.unlink()
    config.symlink_to(repository / "HEAD")
    git_calls: list[tuple[str, ...]] = []

    def reject_git_query(_repository: Path, *args: str) -> bytes:
        git_calls.append(args)
        raise AssertionError("unsafe repository reached Git")

    monkeypatch.setattr(calibration, "_reference_git_bytes", reject_git_query)

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration._validate_f1v2_reference_repository(
            row,
            _f1v2_reference_lineage(reference_commit, reference_tree),
        )

    assert caught.value.code == "reference_repository_invalid"
    assert caught.value.value == ("config",)
    assert git_calls == []


def test_task3a_f1v2_reference_repository_rejects_walk_error_before_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    row = _f1v2_reference_repository_row(
        repository, reference_commit, reference_tree
    )
    walk_calls: list[dict[str, object]] = []
    git_calls: list[tuple[str, ...]] = []

    def unreadable_walk(root, *, topdown, onerror, followlinks):
        walk_calls.append(
            {
                "root": root,
                "topdown": topdown,
                "onerror": onerror,
                "followlinks": followlinks,
            }
        )
        assert onerror is not None
        onerror(PermissionError("nested repository directory is unreadable"))
        yield root, [], []

    def reject_git_query(_repository: Path, *args: str) -> bytes:
        git_calls.append(args)
        raise AssertionError("unreadable repository reached Git")

    monkeypatch.setattr(calibration.os, "walk", unreadable_walk)
    monkeypatch.setattr(calibration, "_reference_git_bytes", reject_git_query)

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration._validate_f1v2_reference_repository(
            row,
            _f1v2_reference_lineage(reference_commit, reference_tree),
        )

    assert caught.value.code == "reference_repository_invalid"
    assert caught.value.value == str(repository)
    assert len(walk_calls) == 1
    assert walk_calls[0]["topdown"] is True
    assert walk_calls[0]["followlinks"] is False
    assert git_calls == []


def test_task3a_f1v2_reference_repository_rejects_non_sha1_object_database(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = _calibration_module()
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    row = _f1v2_reference_repository_row(
        repository, reference_commit, reference_tree
    )
    original = calibration._reference_git_bytes

    def object_format_override(candidate: Path, *args: str) -> bytes:
        if args == ("rev-parse", "--show-object-format"):
            return b"sha256\n"
        return original(candidate, *args)

    monkeypatch.setattr(
        calibration, "_reference_git_bytes", object_format_override
    )

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration._validate_f1v2_reference_repository(
            row,
            _f1v2_reference_lineage(reference_commit, reference_tree),
        )

    assert caught.value.code == "reference_repository_invalid"


def _write_cas_member(root: Path, member_id: str, payload: bytes) -> dict[str, object]:
    digest = "sha256:" + hashlib.sha256(payload).hexdigest()
    relative = Path(digest.removeprefix("sha256:")) / "payload"
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return {
        "member_id": member_id,
        "cas_relative_path": relative.as_posix(),
        "byte_count": len(payload),
        "sha256": digest,
    }


def _passing_reference_observations() -> list[dict[str, object]]:
    return [
        {
            "clause_id": clause_id,
            "details": f"Evaluator satisfied {clause_id}.",
            "evidence": [
                "sha256:" + hashlib.sha256(clause_id.encode()).hexdigest()
            ],
            "satisfied": True,
        }
        for clause_id in F1V2_CLAUSES
    ]


def test_task3a_f1v2_evaluation_capture_materializes_and_evaluates_twice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    calls: list[tuple[Path, Path, Path]] = []

    def evaluate_candidate(*, candidate_evidence_path, output_root, workspace):
        calls.append((candidate_evidence_path, output_root, workspace))
        assert candidate_evidence_path == workspace / "es_f1_candidate_evidence.json"
        assert (
            _run_git(workspace, "rev-parse", "HEAD").decode().strip()
            == reference_commit
        )
        assert (
            _run_git(workspace, "rev-parse", "HEAD^{tree}").decode().strip()
            == reference_tree
        )
        return _passing_reference_observations()

    monkeypatch.setattr(evaluator, "evaluate_candidate", evaluate_candidate)

    capture = calibration.capture_reference_evaluation_replay(
        reference_repository=repository,
        reference_commit=reference_commit,
        reference_tree=reference_tree,
        output_root=tmp_path / "evaluation-capture",
    )

    assert len(calls) == 2
    assert calls[0][2] != calls[1][2]
    assert all(workspace.is_dir() for _, _, workspace in calls)
    assert capture.replay["target_tree"] == reference_tree
    assert [row["run_id"] for row in capture.replay["runs"]] == [
        "reference-materialization-a",
        "reference-materialization-b",
    ]
    assert capture.replay["normalized_results_byte_equal"] is True
    assert capture.replay["runs"][0]["normalized_result"] == (
        capture.replay["runs"][1]["normalized_result"]
    )


def test_task3a_f1v2_evaluation_capture_rejects_failed_real_observation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration = _calibration_module()
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    repository, reference_commit, reference_tree = _f1v2_reference_repository(
        tmp_path
    )
    observations = _passing_reference_observations()
    observations[-1]["satisfied"] = False
    monkeypatch.setattr(
        evaluator,
        "evaluate_candidate",
        lambda **_: copy.deepcopy(observations),
    )

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.capture_reference_evaluation_replay(
            reference_repository=repository,
            reference_commit=reference_commit,
            reference_tree=reference_tree,
            output_root=tmp_path / "evaluation-capture",
        )

    assert caught.value.code == "reference_evaluation_invalid"


@pytest.fixture(scope="module")
def f1v2_reference_product(tmp_path_factory):
    calibration = _calibration_module()
    root = tmp_path_factory.mktemp("f1v2-reference-product")
    repository, reference_commit, reference_tree = _f1v2_reference_repository(root)
    seed = _json_record(TASK_SEED_MANIFEST)
    patch_argv = [
        "diff",
        "--patch",
        "--binary",
        "--full-index",
        "--no-color",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        *calibration.PINNED_GIT_DIFF_CONTROLS,
        seed["recipe"]["commit"],
        reference_commit,
        "--",
    ]
    patch = _run_git(repository, *patch_argv)
    no_delivery, no_delivery_report = calibration.build_reference_no_delivery(
        task_seed_manifest=seed,
        reference_repository=repository,
        reference_commit=reference_commit,
        reference_tree=reference_tree,
        canonical_patch=patch,
        implementation_additions=8_698,
    )
    evidence_root = root / "evidence"
    evaluator = importlib.import_module("scripts.experiments.es.f1_evaluator")
    patcher = pytest.MonkeyPatch()
    patcher.setattr(
        evaluator,
        "evaluate_candidate",
        lambda **_: _passing_reference_observations(),
    )
    try:
        evaluation_capture = calibration.capture_reference_evaluation_replay(
            reference_repository=repository,
            reference_commit=reference_commit,
            reference_tree=reference_tree,
            output_root=root / "evaluation-capture",
        )
    finally:
        patcher.undo()
    evaluation_replay = evaluation_capture.replay
    normalized_digest = evaluation_replay["normalized_result_sha256"]
    members = [
        _write_cas_member(evidence_root, "canonical_patch", patch),
        _write_cas_member(
            evidence_root,
            "evaluation_replay",
            evaluation_capture.payload,
        ),
        _write_cas_member(
            evidence_root,
            "no_delivery_scan",
            calibration.canonical_json_bytes(no_delivery_report),
        ),
    ]
    metric = calibration.build_reference_metric(
        repository=repository,
        task_seed_commit=seed["recipe"]["commit"],
        reference_commit=reference_commit,
        changed_path_policies=tuple(
            calibration.MetricPathPolicy(
                path,
                "production_python",
                F1V2_REPRESENTATIVE_RESPONSIBILITIES[path],
            )
            for path in F1V2_REPRESENTATIVE_PATH_LINES
        ),
        git_contract=_git_contract(
            calibration,
            policy_sha256=_json_record(PREEDIT_POLICY)["record_sha256"],
        ),
    )
    body = {
        "schema_version": "es_f1_reference_product.v2",
        "bindings": calibration.build_reference_bindings(),
        "lineage": {
            "source_commit": "c081b7b6cd160b3da7031ee325bbf0ade1025d7a",
            "source_tree": "9193ae2f81116d1bac4cf3cb74395613c1220dbe",
            "projection_commit": seed["parent_projection"]["commit"],
            "projection_tree": seed["parent_projection"]["tree"],
            "task_seed_commit": seed["recipe"]["commit"],
            "task_seed_tree": seed["recipe"]["tree"],
            "campaign_parent": "99efda11155119161d371d5d0e5ec7c33a720594",
            "campaign_start": "7d630bcc14191ec5f8206a9ceb097a62a1c011c6",
            "campaign_end": "015ca6e93d78c5f7f42adf0cae883d895de5f80c",
            "reference_commit": reference_commit,
            "reference_tree": reference_tree,
        },
        "repository": _f1v2_reference_repository_row(
            repository, reference_commit, reference_tree
        ),
        "adaptation": {
            "strategy": "behavioral-adaptation-no-history-replay.v1",
            "historical_production_paths": list(
                calibration.F1V2_HISTORICAL_PRODUCTION_PATHS
            ),
            "historical_production_path_count": (
                calibration.F1V2_HISTORICAL_PRODUCTION_PATH_COUNT
            ),
            "historical_production_paths_sha256": (
                calibration.F1V2_HISTORICAL_PRODUCTION_PATHS_SHA256
            ),
            "rows": [
                {
                    "historical_path": path,
                    "projection_targets": (
                        [path] if path in F1V2_REPRESENTATIVE_PATH_LINES else []
                    ),
                    "disposition": (
                        "adapted"
                        if path in F1V2_REPRESENTATIVE_PATH_LINES
                        else "not_applicable"
                    ),
                    "conflict_rationale": (
                        "Adapted this historical responsibility to the projection API."
                        if path in F1V2_REPRESENTATIVE_PATH_LINES
                        else "The representative projection does not need this historical path."
                    ),
                }
                for path in calibration.F1V2_HISTORICAL_PRODUCTION_PATHS
            ],
            "new_production_responsibilities": [
                {
                    "path": path,
                    "responsibility_ids": list(responsibility_ids),
                }
                for path, responsibility_ids in F1V2_REPRESENTATIVE_RESPONSIBILITIES.items()
            ],
        },
        "evidence": {
            "algorithm": "sha256",
            "root": str(evidence_root.resolve()),
            "members": members,
        },
        "evaluation": {
            "target_tree": reference_tree,
            "evaluation_replay_member_id": "evaluation_replay",
            "normalized_result_sha256": normalized_digest,
        },
        "patch": {
            "member_id": "canonical_patch",
            "base_commit": seed["recipe"]["commit"],
            "target_commit": reference_commit,
            "argv": patch_argv,
        },
        "metric": metric,
        "no_delivery": no_delivery,
    }
    output = root / "reference-product.json"
    product = calibration.build_reference_product(
        body,
        output_path=output,
        schema_path=REFERENCE_SCHEMA,
        evaluation_capture=evaluation_capture,
    )
    return calibration, output, product


def _replace_cas_json_member(calibration, body, member_id: str, value) -> None:
    row = next(
        row for row in body["evidence"]["members"] if row["member_id"] == member_id
    )
    row.update(
        _write_cas_member(
            Path(body["evidence"]["root"]),
            member_id,
            calibration.canonical_json_bytes(value),
        )
    )


def _recompute_replay_digests(calibration, body, replay) -> None:
    for run in replay["runs"]:
        run["normalized_result_sha256"] = "sha256:" + hashlib.sha256(
            calibration.canonical_json_bytes(run["normalized_result"])
        ).hexdigest()
    replay["normalized_result_sha256"] = replay["runs"][0][
        "normalized_result_sha256"
    ]
    body["evaluation"]["normalized_result_sha256"] = replay[
        "normalized_result_sha256"
    ]
    _replace_cas_json_member(calibration, body, "evaluation_replay", replay)


def test_task3a_f1v2_reference_product_builds_and_reloads(
    f1v2_reference_product,
) -> None:
    calibration, output, built = f1v2_reference_product

    loaded = calibration.load_reference_product(
        output,
        schema_path=REFERENCE_SCHEMA,
        expected_record_sha256=built.record["record_sha256"],
    )

    assert loaded.record == built.record
    assert output.read_bytes() == calibration.canonical_json_bytes(built.record)


def test_task3a_f1v2_reference_build_rejects_caller_authored_verdict(
    f1v2_reference_product,
    tmp_path: Path,
) -> None:
    calibration, _, built = f1v2_reference_product
    body = copy.deepcopy(built.record)
    body.pop("record_sha256")

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.build_reference_product(
            body,
            output_path=tmp_path / "forged-reference-product.json",
            schema_path=REFERENCE_SCHEMA,
            evaluation_capture=None,
        )

    assert caught.value.code == "reference_evaluation_invalid"


def test_task3a_f1v2_reference_loader_reopens_v3_semantic_authorities(
    f1v2_reference_product,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calibration, output, built = f1v2_reference_product
    task_package = importlib.import_module("scripts.experiments.es.task_package")
    calls: list[str] = []

    for name in (
        "load_task_seed_manifest",
        "verify_task_seed",
        "load_configuration_consumer_census",
        "load_f1v2_selector_manifest",
    ):
        original = getattr(task_package, name)

        def observed(*args, __name=name, __original=original, **kwargs):
            calls.append(__name)
            return __original(*args, **kwargs)

        monkeypatch.setattr(task_package, name, observed)

    calibration.load_reference_product(
        output,
        schema_path=REFERENCE_SCHEMA,
        expected_record_sha256=built.record["record_sha256"],
    )

    assert set(calls) == {
        "load_task_seed_manifest",
        "verify_task_seed",
        "load_configuration_consumer_census",
        "load_f1v2_selector_manifest",
    }


@pytest.mark.parametrize(
    "rejected_loader",
    (
        "load_task_seed_manifest",
        "verify_task_seed",
        "load_configuration_consumer_census",
        "load_f1v2_selector_manifest",
    ),
)
def test_task3a_f1v2_reference_loader_fails_closed_on_v3_authority_rejection(
    f1v2_reference_product,
    monkeypatch: pytest.MonkeyPatch,
    rejected_loader: str,
) -> None:
    calibration, output, built = f1v2_reference_product
    task_package = importlib.import_module("scripts.experiments.es.task_package")

    def reject(*_args, **_kwargs):
        raise task_package.TaskPackageError(
            "test_v3_authority_rejection",
            rejected_loader,
            "canonical loader rejected the bound authority",
        )

    monkeypatch.setattr(task_package, rejected_loader, reject)

    with pytest.raises(calibration.CalibrationError) as caught:
        calibration.load_reference_product(
            output,
            schema_path=REFERENCE_SCHEMA,
            expected_record_sha256=built.record["record_sha256"],
        )

    assert caught.value.code == "reference_binding_invalid"


@pytest.mark.parametrize(
    "tamper",
    (
        "nested_extra",
        "campaign_identity",
        "historical_domain",
        "run_divergence",
        "clause_order",
        "failed_clause",
        "no_delivery_resealed",
    ),
)
def test_task3a_f1v2_reference_product_rejects_semantic_tamper(
    f1v2_reference_product,
    tmp_path: Path,
    tamper: str,
) -> None:
    calibration, _, built = f1v2_reference_product
    body = copy.deepcopy(built.record)
    body.pop("record_sha256")
    if tamper == "nested_extra":
        body["evaluation"]["unexpected"] = True
    elif tamper == "campaign_identity":
        body["lineage"]["campaign_start"] = "0" * 40
    elif tamper == "historical_domain":
        adaptation = body["adaptation"]
        removed = adaptation["historical_production_paths"].pop()
        adaptation["rows"] = [
            row for row in adaptation["rows"] if row["historical_path"] != removed
        ]
        adaptation["historical_production_path_count"] -= 1
        adaptation["historical_production_paths_sha256"] = (
            "sha256:"
            + hashlib.sha256(
                calibration.canonical_json_bytes(
                    adaptation["historical_production_paths"]
                )
            ).hexdigest()
        )
    elif tamper in {"run_divergence", "clause_order", "failed_clause"}:
        replay_row = next(
            row
            for row in body["evidence"]["members"]
            if row["member_id"] == "evaluation_replay"
        )
        replay = json.loads(
            (
                Path(body["evidence"]["root"])
                / replay_row["cas_relative_path"]
            ).read_text()
        )
        if tamper == "run_divergence":
            replay["runs"][1]["normalized_result"]["clause_results"][0][
                "details"
            ] = "Divergent second materialization."
        else:
            for run in replay["runs"]:
                result = run["normalized_result"]
                if tamper == "clause_order":
                    result["clause_results"].reverse()
                else:
                    result["clause_results"][-1]["satisfied"] = False
        _recompute_replay_digests(calibration, body, replay)
    else:
        report_row = next(
            row
            for row in body["evidence"]["members"]
            if row["member_id"] == "no_delivery_scan"
        )
        report = json.loads(
            (
                Path(body["evidence"]["root"])
                / report_row["cas_relative_path"]
            ).read_text()
        )
        report["surface_rows"].pop()
        _replace_cas_json_member(calibration, body, "no_delivery_scan", report)
        body["no_delivery"]["report_sha256"] = "sha256:" + hashlib.sha256(
            calibration.canonical_json_bytes(report)
        ).hexdigest()
    changed = calibration.seal_record(body)
    path = tmp_path / "reference-product.json"
    path.write_bytes(calibration.canonical_json_bytes(changed))

    with pytest.raises(calibration.CalibrationError):
        calibration.load_reference_product(
            path,
            schema_path=REFERENCE_SCHEMA,
            expected_record_sha256=changed["record_sha256"],
        )
