from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from jsonschema import Draft202012Validator
import pytest


POLICY_SCHEMA = "provider-phase-isolation-v1.schema.json"
ENVIRONMENT_SCHEMA = "provider-environment-manifest-v1.schema.json"
NETWORK_INVENTORY_SCHEMA = (
    "provider-isolation-network-inventory-v1.schema.json"
)
BUNDLE_TRANSFER_SCHEMA = (
    "provider-isolation-bundle-transfer-v1.schema.json"
)
_SHA256_A = "sha256:" + ("a" * 64)
_SHA256_B = "sha256:" + ("b" * 64)
_SHA256_C = "sha256:" + ("c" * 64)
_SHA256_D = "sha256:" + ("d" * 64)
_MAX_UINT64 = (1 << 64) - 1
_MAX_PATH_LENGTH = 4096
_MAX_BUNDLE_BYTES = 16_777_216


def _bundle_transfer_record(
    state: str,
    *,
    disposition: str | None = None,
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_version": "provider_isolation_bundle_transfer.v1",
        "state": state,
        "invocation_identity": _SHA256_A,
        "scope": ["root", "provider-step"],
        "ordinal": 1,
        "staged_identity": {
            "path": "bundle-transfers/attempt-000001.staged",
            "device": 11,
            "inode": 12,
            "mount_id": 13,
        },
        "target_identity": {
            "path": "results/provider-step.json",
            "device": 11,
            "inode": 12,
            "mount_id": 13,
        },
        "bundle_digest": _SHA256_B,
        "bundle_size": 17,
    }
    if state in {"validated", "rotation_pending", "rotated"}:
        record["contract_digest"] = _SHA256_C
        record["validation_disposition"] = disposition or "invalid"
        if record["validation_disposition"] == "valid":
            record["normalized_value_digest"] = _SHA256_D
    if state in {"rotation_pending", "rotated"}:
        record["archive_identity"] = {
            "path": "invalid-results/provider-step-attempt-000001.json",
            "device": 11,
            "inode": 12,
            "mount_id": 13,
        }
    return record


def _assert_schema_rejects(
    validator: Draft202012Validator,
    document: dict[str, object],
) -> None:
    assert list(validator.iter_errors(document))


def test_policy_schema_loads_as_a_packaged_resource_outside_checkout_cwd(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    isolation = importlib.import_module("orchestrator.providers.isolation")

    schema = isolation.load_provider_isolation_schema(POLICY_SCHEMA)

    assert schema["$id"].endswith(POLICY_SCHEMA)
    assert schema["properties"]["schema_version"]["const"] == (
        "provider_phase_isolation.v1"
    )


def test_network_inventory_schema_loads_as_a_packaged_closed_resource(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    isolation = importlib.import_module("orchestrator.providers.isolation")
    root = importlib.resources.files("orchestrator.providers.schemas")
    names = {item.name for item in root.iterdir()}

    assert NETWORK_INVENTORY_SCHEMA in names
    schema = isolation.load_provider_isolation_schema(NETWORK_INVENTORY_SCHEMA)
    assert schema["properties"]["schema_version"]["const"] == (
        "provider_isolation_network_inventory.v1"
    )
    assert schema["additionalProperties"] is False
    assert schema["properties"]["listeners"]["maxItems"] > 0


def test_bundle_transfer_schema_loads_as_a_packaged_closed_resource(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    isolation = importlib.import_module("orchestrator.providers.isolation")
    root = importlib.resources.files("orchestrator.providers.schemas")
    names = {item.name for item in root.iterdir()}

    assert BUNDLE_TRANSFER_SCHEMA in names
    schema = isolation.load_provider_isolation_schema(BUNDLE_TRANSFER_SCHEMA)
    assert schema["$id"].endswith(BUNDLE_TRANSFER_SCHEMA)
    assert schema["properties"]["schema_version"]["const"] == (
        "provider_isolation_bundle_transfer.v1"
    )
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["file_identity"]["additionalProperties"] is False

    validator = Draft202012Validator(schema)
    top_level_unknown = _bundle_transfer_record("prepared")
    top_level_unknown["unexpected"] = True
    _assert_schema_rejects(validator, top_level_unknown)

    nested_unknown = _bundle_transfer_record("prepared")
    staged_identity = dict(nested_unknown["staged_identity"])
    staged_identity["unexpected"] = True
    nested_unknown["staged_identity"] = staged_identity
    _assert_schema_rejects(validator, nested_unknown)


@pytest.mark.parametrize(
    ("state", "disposition"),
    (
        ("prepared", None),
        ("published", None),
        ("validated", "valid"),
        ("validated", "invalid"),
        ("rotation_pending", "invalid"),
        ("rotated", "invalid"),
    ),
)
def test_bundle_transfer_schema_accepts_only_closed_state_shapes(
    state: str,
    disposition: str | None,
) -> None:
    isolation = importlib.import_module("orchestrator.providers.isolation")
    schema = isolation.load_provider_isolation_schema(BUNDLE_TRANSFER_SCHEMA)
    validator = Draft202012Validator(schema)

    assert not list(
        validator.iter_errors(
            _bundle_transfer_record(state, disposition=disposition)
        )
    )
    assert set(schema["properties"]["state"]["enum"]) == {
        "prepared",
        "published",
        "validated",
        "rotation_pending",
        "rotated",
    }

    unknown_state = _bundle_transfer_record("prepared")
    unknown_state["state"] = "unknown"
    _assert_schema_rejects(validator, unknown_state)


def test_bundle_transfer_schema_bounds_path_digest_size_and_ordinal_fields() -> None:
    isolation = importlib.import_module("orchestrator.providers.isolation")
    schema = isolation.load_provider_isolation_schema(BUNDLE_TRANSFER_SCHEMA)
    validator = Draft202012Validator(schema)

    assert schema["$defs"]["path"]["maxLength"] == _MAX_PATH_LENGTH
    assert schema["$defs"]["digest"]["minLength"] == 71
    assert schema["$defs"]["digest"]["maxLength"] == 71
    assert schema["properties"]["bundle_size"]["maximum"] == _MAX_BUNDLE_BYTES
    assert schema["properties"]["ordinal"]["maximum"] == _MAX_UINT64

    for invalid_path in ("", "x" * (_MAX_PATH_LENGTH + 1)):
        record = _bundle_transfer_record("prepared")
        staged_identity = dict(record["staged_identity"])
        staged_identity["path"] = invalid_path
        record["staged_identity"] = staged_identity
        _assert_schema_rejects(validator, record)

    for field in ("invocation_identity", "bundle_digest"):
        record = _bundle_transfer_record("prepared")
        record[field] = "sha256:" + ("a" * 65)
        _assert_schema_rejects(validator, record)

    for invalid_size in (-1, _MAX_BUNDLE_BYTES + 1, True):
        record = _bundle_transfer_record("prepared")
        record["bundle_size"] = invalid_size
        _assert_schema_rejects(validator, record)

    for invalid_ordinal in (0, _MAX_UINT64 + 1, True):
        record = _bundle_transfer_record("prepared")
        record["ordinal"] = invalid_ordinal
        _assert_schema_rejects(validator, record)


def test_bundle_transfer_schema_requires_state_specific_validation_identities() -> None:
    isolation = importlib.import_module("orchestrator.providers.isolation")
    schema = isolation.load_provider_isolation_schema(BUNDLE_TRANSFER_SCHEMA)
    validator = Draft202012Validator(schema)

    for required_field in (
        "invocation_identity",
        "scope",
        "ordinal",
        "staged_identity",
        "target_identity",
        "bundle_digest",
        "bundle_size",
    ):
        record = _bundle_transfer_record("prepared")
        del record[required_field]
        _assert_schema_rejects(validator, record)

    for required_field in ("path", "device", "inode", "mount_id"):
        record = _bundle_transfer_record("prepared")
        staged_identity = dict(record["staged_identity"])
        del staged_identity[required_field]
        record["staged_identity"] = staged_identity
        _assert_schema_rejects(validator, record)

    for state in ("validated", "rotation_pending", "rotated"):
        for required_field in ("contract_digest", "validation_disposition"):
            record = _bundle_transfer_record(state)
            del record[required_field]
            _assert_schema_rejects(validator, record)

    valid = _bundle_transfer_record("validated", disposition="valid")
    del valid["normalized_value_digest"]
    _assert_schema_rejects(validator, valid)

    invalid_with_normalized_value = _bundle_transfer_record(
        "validated",
        disposition="invalid",
    )
    invalid_with_normalized_value["normalized_value_digest"] = _SHA256_D
    _assert_schema_rejects(validator, invalid_with_normalized_value)

    for state in ("rotation_pending", "rotated"):
        record = _bundle_transfer_record(state)
        del record["archive_identity"]
        _assert_schema_rejects(validator, record)

        valid_rotation = _bundle_transfer_record(state)
        valid_rotation["validation_disposition"] = "valid"
        valid_rotation["normalized_value_digest"] = _SHA256_D
        _assert_schema_rejects(validator, valid_rotation)

    for state in ("prepared", "published"):
        record = _bundle_transfer_record(state)
        record["contract_digest"] = _SHA256_C
        record["validation_disposition"] = "invalid"
        _assert_schema_rejects(validator, record)


def test_built_wheel_imports_only_installed_package_and_loads_every_schema(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    build_root = tmp_path / "wheel-source"
    wheel_dir = tmp_path / "wheelhouse"
    target = tmp_path / "installed"
    build_root.mkdir()
    wheel_dir.mkdir()
    target.mkdir()
    shutil.copytree(repo_root / "orchestrator", build_root / "orchestrator")
    shutil.copy2(repo_root / "pyproject.toml", build_root / "pyproject.toml")
    shutil.copy2(repo_root / "LICENSE.md", build_root / "LICENSE.md")

    build = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-build-isolation",
            "--no-deps",
            "--wheel-dir",
            str(wheel_dir),
            str(build_root),
        ],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert build.returncode == 0, build.stdout
    wheels = tuple(wheel_dir.glob("orchestrator-*.whl"))
    assert len(wheels) == 1, build.stdout

    install = subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(target),
            str(wheels[0]),
        ],
        cwd=tmp_path,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert install.returncode == 0, install.stdout

    probe = """
import importlib.resources
import json
from pathlib import Path
import sys

target = Path(sys.argv[1]).resolve()
source = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(target))
import orchestrator

package_path = Path(orchestrator.__file__).resolve()
assert package_path.is_relative_to(target), (package_path, target)
assert not package_path.is_relative_to(source), (package_path, source)
root = importlib.resources.files("orchestrator.providers.schemas")
names = sorted(item.name for item in root.iterdir() if item.name.endswith(".json"))
assert names
for name in names:
    with root.joinpath(name).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
print(json.dumps(names))
"""
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    imported = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            probe,
            str(target),
            str(repo_root),
        ],
        cwd=tmp_path,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert imported.returncode == 0, imported.stdout
    resource_names = json.loads(imported.stdout.strip().splitlines()[-1])
    assert POLICY_SCHEMA in resource_names
    assert ENVIRONMENT_SCHEMA in resource_names
    assert NETWORK_INVENTORY_SCHEMA in resource_names
    assert BUNDLE_TRANSFER_SCHEMA in resource_names
