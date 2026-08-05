from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
from pathlib import Path
import shutil

from jsonschema import Draft202012Validator, ValidationError
import pytest


ROOT = Path(__file__).resolve().parents[2]
A1_SCHEMA = (
    ROOT
    / "docs"
    / "plans"
    / "evidence"
    / "es-f1-large-scope-refreeze"
    / "a1-calibration-anchor.schema.json"
)
A1_ROOT = Path(
    "/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/"
    "pilot-2026-07-27/a1-v7"
)
POLICY_SHA256 = "sha256:" + "1" * 64
GIT_POLICY_SHA256 = "sha256:" + "2" * 64


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
