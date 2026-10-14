"""Historical scaffold identity, captured bytes and tamper verification.

Expected assets were frozen from E/full-tmp before retiring their producers.
Fixture setup never compiles or renders them; the retained verifier recomputes
historical canonical bytes independently of the captured fixture data.
"""

from __future__ import annotations
import dataclasses
import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from types import MappingProxyType, SimpleNamespace
import pytest
from orchestrator.prompt_contract import (
    RENDERER_VERSION,
    PrimitiveType,
    SemanticContract,
    canonical_json_bytes,
)
from orchestrator.prompt_scaffold import (
    OMP_PROVIDER_POLICY, OMP_PROVIDER_POLICY_VERSION, PUBLIC_PROVIDER_NAMES,
    ScaffoldIdentityError, ScaffoldInputs, ScaffoldVerificationError,
    identity_for, scaffold_dir_name, slugify, verify_scaffold,
)
from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_launch import LANE_POLICY
from orchestrator.providers.omp_pin import OMP_BINARY_PIN, OmpBinaryPin
from orchestrator.providers.omp_templates import DEFAULT_OMP_MODEL
from tests.test_prompt_session import HISTORY, _copy_historical_tree

CONF_DIR = Path(__file__).parent / "fixtures" / "omp" / "conf"
_SCALAR_STRING = SemanticContract(mode="scalar", type=PrimitiveType("String"), record_name=None, fields=())


def _historical_scaffold(tmp_path, prompt, *, contract=_SCALAR_STRING, provider="omp",
    model=DEFAULT_OMP_MODEL, conf=None, authoring=None, slug="task", pin=OMP_BINARY_PIN):
    inputs = _inputs(prompt, contract=contract, provider=provider, model=model,
        conf=conf, slug=slug, pin=pin)
    identity = identity_for(inputs)
    source = HISTORY / "scaffolds" / f"{identity}-{(authoring or {'mode': 'exact'})['mode']}"
    assert source.is_dir(), f"missing frozen historical witness: {source.name}"
    path = tmp_path / "gen" / scaffold_dir_name(inputs)
    _copy_historical_tree(source, path)
    verification = verify_scaffold(generated_root=path.parent, name=path.name, inputs=inputs)
    return SimpleNamespace(path=path, identity=identity, verification=verification), inputs


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _admit(path) -> object:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        return admit_conf_tree(fd)
    finally:
        os.close(fd)


def _inputs(
    prompt: bytes,
    contract: SemanticContract = _SCALAR_STRING,
    provider: str = "omp",
    model: str = DEFAULT_OMP_MODEL,
    conf=None,
    slug: str = "task",
    pin: OmpBinaryPin = OMP_BINARY_PIN,
) -> ScaffoldInputs:
    return ScaffoldInputs(
        prompt_sha256=_sha256(prompt),
        contract=contract,
        provider=provider,
        model=model,
        conf_manifest=conf,
        slug=slug,
        pin=pin,
    )


def _conf_for(provider: str):
    """Admit the packaged neutral conf for omp_conf; ambient providers need none."""
    if provider == "omp_conf":
        return _admit(CONF_DIR / "neutral")
    return None


def _published_files(result) -> dict[str, bytes]:
    return {
        path.relative_to(result.path).as_posix(): path.read_bytes()
        for path in result.path.rglob("*")
        if path.is_file()
    }


def test_manifest_files_are_exact_one_key_objects_plus_lf(tmp_path: Path) -> None:
    for provider in PUBLIC_PROVIDER_NAMES:
        result, _ = _historical_scaffold(tmp_path, b"p", provider=provider, conf=_conf_for(provider))
        assert (result.path / "prompts.json").read_bytes() == (
            b'{"prompts.task":"prompt.md"}\n'
        )
        assert (result.path / "providers.json").read_bytes() == (
            json.dumps(
                {"providers.task": provider},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            + b"\n"
        )


def test_identity_differs_across_providers_and_models(tmp_path: Path) -> None:
    identities = set()
    for provider in PUBLIC_PROVIDER_NAMES:
        result, _ = _historical_scaffold(tmp_path, b"p", provider=provider, conf=_conf_for(provider))
        identities.add(result.identity)
    assert len(identities) == len(PUBLIC_PROVIDER_NAMES)
    assert identity_for(_inputs(b"p", model="model-a")) != identity_for(_inputs(b"p", model="model-b"))


def test_scaffold_dir_name_uses_slug_and_identity_prefix(tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p")
    assert result.path.name == f"task-{result.identity[:12]}"
    assert scaffold_dir_name(inputs) == result.path.name


def test_slugify_normalization(tmp_path: Path) -> None:
    assert slugify("My Task-7 Brief!!") == "my-task-7-brief"
    assert slugify("") == "prompt"
    assert slugify("!!!") == "prompt"
    assert slugify("a" * 100) == "a" * 32
    assert slugify("UPPER Case") == "upper-case"
    result, _ = _historical_scaffold(tmp_path, b"p", slug="!!!")
    assert result.path.name.startswith("prompt-")


def test_omp_conf_root_input_and_conf_copy_only_for_omp_conf(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "advised")
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp_conf", conf=conf)
    source = (result.path / "run.orc").read_text(encoding="utf-8")
    assert "((omp_conf_root String))" in source
    assert ":inputs (omp_conf_root)" in source
    assert (result.path / "conf" / "config.yml").is_file()
    assert (result.path / "conf" / "agent" / "WATCHDOG.yml").is_file()
    for provider in ("omp", "omp_no_tools", "omp_unrestricted_workspace"):
        other, _ = _historical_scaffold(tmp_path, b"p", provider=provider)
        assert "omp_conf_root" not in (other.path / "run.orc").read_text(
            encoding="utf-8"
        )
        assert not (other.path / "conf").exists()


def test_conf_files_copied_byte_for_byte_and_normalized_mode(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "advised")
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp_conf", conf=conf)
    for relative in ("config.yml", "agent/WATCHDOG.yml"):
        expected = (CONF_DIR / "advised" / relative).read_bytes()
        published = (result.path / "conf" / relative).read_bytes()
        assert published == expected
        assert stat.S_IMODE(os.stat(result.path / "conf" / relative).st_mode) == 0o644


def test_omp_no_tools_binds_neutral_conf_manifest(tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp_no_tools")
    manifest = json.loads((result.path / "scaffold.json").read_bytes())
    assert manifest["conf_manifest_sha256"]
    assert manifest["provider"]["registry_name"] == "omp_no_tools"
    # The neutral tree admits to the closed schema and its digest is bound.
    from orchestrator.providers.omp_launch import neutral_conf_root

    neutral = _admit(neutral_conf_root())
    assert manifest["conf_manifest_sha256"] == neutral.manifest_sha256
    assert "conf" not in _published_files(result)


def test_omp_no_tools_refuses_authored_conf_override(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "advised")
    with pytest.raises(ValueError):
        _inputs(b"p", provider="omp_no_tools", conf=conf)


def test_omp_conf_requires_authored_conf(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _inputs(b"p", provider="omp_conf", conf=None)


def test_binary_pin_is_identity_input(tmp_path: Path) -> None:
    del tmp_path
    drifted = dataclasses.replace(OMP_BINARY_PIN, executable_sha256="0" * 64)
    # Identity stays pure: an alternate well-formed pin changes the basis hash.
    baseline = identity_for(_inputs(b"p", provider="omp"))
    drifted_result = identity_for(_inputs(b"p", provider="omp", pin=drifted))
    assert baseline != drifted_result


def test_provider_policy_table_is_closed_and_matches_launch_lanes() -> None:
    assert tuple(OMP_PROVIDER_POLICY) == PUBLIC_PROVIDER_NAMES
    for name, policy in OMP_PROVIDER_POLICY.items():
        assert policy["policy_version"] == OMP_PROVIDER_POLICY_VERSION
        assert policy["lane"] == LANE_POLICY[name]
        assert policy["approval_mode"] in ("write", "yolo")
        assert policy["publishes_fresh_session"] is True
    assert OMP_PROVIDER_POLICY["omp_unrestricted_workspace"]["approval_mode"] == "yolo"
    assert OMP_PROVIDER_POLICY["omp"]["approval_mode"] == "write"
    assert OMP_PROVIDER_POLICY["omp_no_tools"]["lane"] == "no-tools"
    assert OMP_PROVIDER_POLICY["omp_conf"]["lane"] == "conf"


def test_identity_uses_closed_basis_object(tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp_conf", conf=_admit(CONF_DIR / "neutral"))
    manifest = json.loads((result.path / "scaffold.json").read_bytes())
    assert manifest["identity"] == result.identity
    assert len(result.identity) == 64
    assert all(ch in "0123456789abcdef" for ch in result.identity)


def test_scaffold_manifest_rows_cover_all_files_without_extra_nodes(
    tmp_path: Path,
) -> None:
    conf = _admit(CONF_DIR / "advised")
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp_conf", conf=conf)
    manifest = json.loads((result.path / "scaffold.json").read_bytes())
    rows = manifest["files"]
    assert isinstance(rows, list) and rows
    for row in rows:
        assert set(row) == {"path", "size", "sha256", "mode"}
        assert row["mode"] == "0644"
        assert isinstance(row["size"], int) and row["size"] >= 0
        assert len(row["sha256"]) == 64
    paths = [row["path"] for row in rows]
    assert paths == sorted(paths, key=lambda p: p.encode("utf-8"))
    assert len(paths) == len(set(paths))
    published = {
        path: data
        for path, data in _published_files(result).items()
        if path != "scaffold.json"
    }
    assert set(paths) == set(published)
    for path, row in zip(paths, rows):
        assert row["size"] == len(published[path])
        assert row["sha256"] == _sha256(published[path])
    assert "scaffold.json" not in paths


def test_scaffold_manifest_provider_binary_and_digests(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp")
    manifest = json.loads((result.path / "scaffold.json").read_bytes())
    assert set(manifest) == {
        "schema_version",
        "identity",
        "renderer_version",
        "prompt_sha256",
        "semantic_contract_sha256",
        "provider",
        "binary",
        "conf_manifest_sha256",
        "files",
    }
    assert manifest["schema_version"] == "prompt_scaffold.v1"
    assert manifest["identity"] == result.identity
    assert manifest["prompt_sha256"] == _sha256(b"p")
    assert manifest["provider"]["registry_name"] == "omp"
    assert manifest["provider"]["concrete_model"] == DEFAULT_OMP_MODEL
    assert manifest["binary"]["sha256"] == OMP_BINARY_PIN.executable_sha256
    assert manifest["conf_manifest_sha256"] is None


def test_prompt_drift_rejects_rerun(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(tmp_path, b"p")
    drifted = _inputs(b"mutated", provider="omp")
    with pytest.raises(ScaffoldIdentityError):
        verify_scaffold(
            generated_root=result.path.parent,
            name=result.path.name,
            inputs=drifted,
        )


def test_provider_drift_rejects_rerun(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp")
    drifted = _inputs(b"p", provider="omp_conf", conf=_admit(CONF_DIR / "neutral"))
    with pytest.raises(ScaffoldIdentityError):
        verify_scaffold(
            generated_root=result.path.parent,
            name=result.path.name,
            inputs=drifted,
        )


def test_binary_pin_drift_rejects_rerun(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp")
    drifted = _inputs(b"p", provider="omp", pin=dataclasses.replace(
        OMP_BINARY_PIN, executable_sha256="0" * 64
    ))
    with pytest.raises(ValueError):
        verify_scaffold(
            generated_root=result.path.parent,
            name=result.path.name,
            inputs=drifted,
        )


def test_conf_drift_rejects_rerun(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "neutral")
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp_conf", conf=conf)
    drifted_tree = tmp_path / "drifted-conf"
    import shutil

    shutil.copytree(CONF_DIR / "neutral", drifted_tree)
    config_path = drifted_tree / "config.yml"
    config_path.write_text(
        config_path.read_text(encoding="utf-8").replace(
            "maxConcurrency: 4", "maxConcurrency: 9"
        )
    )
    drifted_conf = _admit(drifted_tree)
    assert drifted_conf.manifest_sha256 != conf.manifest_sha256
    drifted = _inputs(b"p", provider="omp_conf", conf=drifted_conf)
    with pytest.raises(ScaffoldIdentityError):
        verify_scaffold(
            generated_root=result.path.parent,
            name=result.path.name,
            inputs=drifted,
        )


def test_verify_scaffold_captures_bytes_and_recomputes_identity(
    tmp_path: Path,
) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp")
    verification = verify_scaffold(
        generated_root=result.path.parent, name=result.path.name, inputs=inputs
    )
    assert verification.identity == result.identity
    assert verification.files["run.orc"] == (result.path / "run.orc").read_bytes()
    assert verification.files["prompt.md"] == b"p"


def test_output_contract_json_closed_shape(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp", authoring={"mode": "default"})
    document = json.loads((result.path / "output-contract.json").read_bytes())
    assert set(document) == {"schema_version", "semantic", "authoring"}
    assert document["schema_version"] == "scaffold_output_contract.v1"
    assert document["semantic"] == {"mode": "scalar", "type": "String"}
    assert document["authoring"] == {"mode": "default"}


@pytest.mark.parametrize("provider", ["omp", "omp_unrestricted_workspace"])
def test_ambient_providers_reject_conf_manifest(provider, tmp_path: Path) -> None:
    del tmp_path
    with pytest.raises(ValueError):
        _inputs(b"p", provider=provider, conf=_admit(CONF_DIR / "neutral"))


def test_identity_basis_conf_manifest_is_exact_closed_object(tmp_path: Path) -> None:
    del tmp_path
    conf = _admit(CONF_DIR / "neutral")
    manifest_object = json.loads(conf.manifest_bytes)
    assert set(manifest_object) == {"schema_version", "files"}
    assert manifest_object["schema_version"] == "omp_conf_manifest.v1"
    inputs = _inputs(b"p", provider="omp_conf", conf=conf)
    policy = OMP_PROVIDER_POLICY["omp_conf"]
    expected = canonical_json_bytes(
        {
            "schema": "scaffold_identity.v1",
            "renderer_version": RENDERER_VERSION,
            "prompt_sha256": _sha256(b"p"),
            "semantic_contract": {"mode": "scalar", "type": "String"},
            "provider": {
                "extern": "providers.task",
                "registry_name": "omp_conf",
                "concrete_model": DEFAULT_OMP_MODEL,
                "policy_version": policy["policy_version"],
                "lane": policy["lane"],
                "approval_mode": policy["approval_mode"],
                "publishes_fresh_session": policy["publishes_fresh_session"],
            },
            "binary": {
                "platform": OMP_BINARY_PIN.platform,
                "arch": OMP_BINARY_PIN.arch,
                "version": OMP_BINARY_PIN.version,
                "sha256": OMP_BINARY_PIN.executable_sha256,
            },
            "prompt_externs": {"prompts.task": "prompt.md"},
            "provider_externs": {"providers.task": "omp_conf"},
            "conf_manifest": manifest_object,
        }
    )
    assert identity_for(inputs) == _sha256(expected)
    # The basis value is the closed manifest object, never the digest key.
    digest_keyed = json.loads(expected)
    digest_keyed["conf_manifest"] = conf.manifest_sha256
    assert identity_for(inputs) != _sha256(canonical_json_bytes(digest_keyed))


def test_identity_basis_ambient_conf_manifest_null(tmp_path: Path) -> None:
    del tmp_path
    inputs = _inputs(b"p", provider="omp")
    policy = OMP_PROVIDER_POLICY["omp"]
    expected = canonical_json_bytes(
        {
            "schema": "scaffold_identity.v1",
            "renderer_version": RENDERER_VERSION,
            "prompt_sha256": _sha256(b"p"),
            "semantic_contract": {"mode": "scalar", "type": "String"},
            "provider": {
                "extern": "providers.task",
                "registry_name": "omp",
                "concrete_model": DEFAULT_OMP_MODEL,
                "policy_version": policy["policy_version"],
                "lane": policy["lane"],
                "approval_mode": policy["approval_mode"],
                "publishes_fresh_session": policy["publishes_fresh_session"],
            },
            "binary": {
                "platform": OMP_BINARY_PIN.platform,
                "arch": OMP_BINARY_PIN.arch,
                "version": OMP_BINARY_PIN.version,
                "sha256": OMP_BINARY_PIN.executable_sha256,
            },
            "prompt_externs": {"prompts.task": "prompt.md"},
            "provider_externs": {"providers.task": "omp"},
            "conf_manifest": None,
        }
    )
    assert identity_for(inputs) == _sha256(expected)


@pytest.mark.parametrize("mode", [0o600, 0o777])
def test_occupant_actual_mode_must_be_0644(mode, tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp")
    os.chmod(result.path / "prompt.md", mode)
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)


def test_occupant_noncanonical_manifest_rejected(tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp")
    scaffold = result.path / "scaffold.json"
    original = scaffold.read_bytes()
    manifest = json.loads(original)
    # Extra top-level key.
    extra = dict(manifest)
    extra["extra"] = True
    scaffold.write_bytes(canonical_json_bytes(extra))
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)
    # Duplicate JSON key.
    marker = b'"schema_version":"prompt_scaffold.v1"'
    scaffold.write_bytes(
        original.replace(marker, marker + b"," + marker, 1)
    )
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)
    # Non-canonical formatting of an otherwise valid manifest.
    scaffold.write_bytes(json.dumps(manifest, sort_keys=True).encode("utf-8"))
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)


def test_self_consistent_run_orc_tamper_rejected(tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp")
    occupied = result.path
    tampered = b"(evil run.orc)\n"
    (occupied / "run.orc").write_bytes(tampered)
    manifest = json.loads((occupied / "scaffold.json").read_bytes())
    for row in manifest["files"]:
        if row["path"] == "run.orc":
            row["sha256"] = _sha256(tampered)
            row["size"] = len(tampered)
    (occupied / "scaffold.json").write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)


def test_self_consistent_conf_tamper_rejected(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "neutral")
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp_conf", conf=conf)
    occupied = result.path
    tampered = b"maxConcurrency: 9\n"
    (occupied / "conf" / "config.yml").write_bytes(tampered)
    manifest = json.loads((occupied / "scaffold.json").read_bytes())
    for row in manifest["files"]:
        if row["path"] == "conf/config.yml":
            row["sha256"] = _sha256(tampered)
            row["size"] = len(tampered)
    (occupied / "scaffold.json").write_bytes(canonical_json_bytes(manifest))
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)


def test_extra_empty_directory_rejected(tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp")
    (result.path / "empty-dir").mkdir()
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)


def _fresh_interpreter_imports(stmt: str) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, "-c", stmt],
        cwd=repo_root,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr


def test_direct_first_import_prompt_scaffold_fs() -> None:
    _fresh_interpreter_imports(
        "import orchestrator.prompt_scaffold_fs; "
        "import orchestrator.prompt_scaffold; "
        "assert orchestrator.prompt_scaffold.verify_scaffold is not None"
    )


def test_direct_first_import_prompt_contract_authoring() -> None:
    _fresh_interpreter_imports(
        "import orchestrator.prompt_contract_authoring; "
        "import orchestrator.prompt_contract; "
        "assert orchestrator.prompt_contract.validate_authoring("
        "{'mode': 'exact'}) == {'mode': 'exact'}"
    )


def test_verification_captures_are_immutable(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(
        tmp_path, b"p", provider="omp_conf", conf=_admit(CONF_DIR / "advised")
    )
    verification = result.verification
    assert isinstance(verification.files, MappingProxyType)
    assert isinstance(verification.conf_files, MappingProxyType)
    assert isinstance(verification.manifest, MappingProxyType)
    with pytest.raises(TypeError):
        verification.files["run.orc"] = b"x"
    with pytest.raises(TypeError):
        verification.conf_files["config.yml"] = b"x"
    with pytest.raises(TypeError):
        verification.manifest["identity"] = "0"


def test_verification_retains_exact_manifest_bytes(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp")
    published_manifest = (result.path / "scaffold.json").read_bytes()
    verification = result.verification
    assert verification.manifest_bytes == published_manifest
    assert verification.manifest_bytes == canonical_json_bytes(
        json.loads(published_manifest)
    ) + b"\n"
    # Task 9 must bind the verified bytes without reopening the mutable
    # scaffold; the captured bytes stay stable after a live-file swap.
    (result.path / "scaffold.json").write_bytes(b"{(mutated after verify)}\n")
    assert _sha256(verification.manifest_bytes) == _sha256(published_manifest)
    assert "scaffold.json" not in verification.files


@pytest.mark.parametrize(
    "bad_name", ["../evil", "a/b", "a\0b", "..", "."]
)
def test_verify_scaffold_rejects_unsafe_name(bad_name, tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp")
    with pytest.raises(ValueError):
        verify_scaffold(
            generated_root=result.path.parent, name=bad_name, inputs=inputs
        )


def test_forged_conf_content_hash_rejected() -> None:
    conf = _admit(CONF_DIR / "neutral")
    record = next(iter(conf.files.values()))
    forged = dataclasses.replace(record, sha256="0" * 64)
    files = MappingProxyType(
        dict(conf.files, **{record.relative_path: forged})
    )
    forged_snapshot = dataclasses.replace(conf, files=files)
    with pytest.raises(ValueError):
        _inputs(b"p", provider="omp_conf", conf=forged_snapshot)
    # bool must not pass as a record size (True is an int subclass); forge
    # a fully self-consistent snapshot so only the bool passes.
    tampered = b"x"
    forged = dataclasses.replace(
        record, content=tampered, size_bytes=True, sha256=_sha256(tampered)
    )
    files = MappingProxyType({record.relative_path: forged})
    rows = [
        {"mode": "0644", "path": record.relative_path,
         "sha256": _sha256(tampered), "size": True}
    ]
    manifest_bytes = canonical_json_bytes(
        {"schema_version": "omp_conf_manifest.v1", "files": rows}
    )
    forged_snapshot = dataclasses.replace(
        conf, files=files, manifest_bytes=manifest_bytes,
        manifest_sha256=_sha256(manifest_bytes),
    )
    with pytest.raises(ValueError):
        _inputs(b"p", provider="omp_conf", conf=forged_snapshot)


def test_forged_conf_manifest_hash_rejected() -> None:
    conf = _admit(CONF_DIR / "neutral")
    forged_snapshot = dataclasses.replace(conf, manifest_sha256="0" * 64)
    with pytest.raises(ValueError):
        _inputs(b"p", provider="omp_conf", conf=forged_snapshot)
    # Non-bytes manifest bytes must raise ValueError, not TypeError.
    forged_bytes = dataclasses.replace(conf, manifest_bytes="not-bytes")
    with pytest.raises(ValueError):
        _inputs(b"p", provider="omp_conf", conf=forged_bytes)


def test_forged_conf_rows_disagree_with_records_rejected() -> None:
    # Self-consistent records (content hash matches) but the canonical
    # manifest rows still describe the original bytes.
    conf = _admit(CONF_DIR / "neutral")
    record = next(iter(conf.files.values()))
    tampered = b"# tampered\n"
    forged = dataclasses.replace(
        record, content=tampered, size_bytes=len(tampered),
        sha256=_sha256(tampered),
    )
    files = MappingProxyType(
        dict(conf.files, **{record.relative_path: forged})
    )
    forged_snapshot = dataclasses.replace(conf, files=files)
    with pytest.raises(ValueError):
        _inputs(b"p", provider="omp_conf", conf=forged_snapshot)


def test_occupant_scaffold_json_actual_mode_enforced(tmp_path: Path) -> None:
    result, inputs = _historical_scaffold(tmp_path, b"p", provider="omp")
    (result.path / "scaffold.json").chmod(0o600)
    with pytest.raises(ScaffoldVerificationError):
        verify_scaffold(generated_root=result.path.parent, name=result.path.name, inputs=inputs)


def test_verification_manifest_is_deeply_immutable(tmp_path: Path) -> None:
    result, _ = _historical_scaffold(tmp_path, b"p", provider="omp")
    manifest = result.verification.manifest
    row = manifest["files"][0]
    with pytest.raises(TypeError):
        row["sha256"] = "0" * 64
    with pytest.raises(TypeError):
        row["size"] = 1
    with pytest.raises(TypeError):
        manifest["files"] = ()


def test_malformed_inputs_raise_closed_errors() -> None:
    with pytest.raises(ValueError):
        ScaffoldInputs(
            prompt_sha256=123,  # type: ignore[arg-type]
            contract=_SCALAR_STRING, provider="omp",
            model=DEFAULT_OMP_MODEL, conf_manifest=None, slug="task",
            pin=OMP_BINARY_PIN,
        )
    with pytest.raises(ValueError):
        ScaffoldInputs(
            prompt_sha256=_sha256(b"p"), contract=_SCALAR_STRING,
            provider="omp", model=DEFAULT_OMP_MODEL, conf_manifest=None,
            slug="task", pin="not-a-pin",  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError):
        ScaffoldInputs(
            prompt_sha256=_sha256(b"p"), contract=_SCALAR_STRING,
            provider="omp_conf", model=DEFAULT_OMP_MODEL,
            conf_manifest=object(),  # type: ignore[arg-type]
            slug="task", pin=OMP_BINARY_PIN,
        )


def test_conf_snapshot_mapping_captured_immutably(tmp_path: Path) -> None:
    """A caller-retained mutable ConfSnapshot mapping must not change identity
    or rendered/executed conf bytes after ScaffoldInputs validates (OMP-T7-
    FINAL-001)."""
    conf = _admit(CONF_DIR / "neutral")
    mutable = dict(conf.files)  # caller-retained mutable mapping
    inputs = _inputs(
        b"p", provider="omp_conf",
        conf=dataclasses.replace(conf, files=mutable),
    )
    identity_before = identity_for(inputs)
    original = next(iter(mutable.values())).content
    record = next(iter(mutable.values()))
    tampered = b"# tampered after validation\n"
    mutable[record.relative_path] = dataclasses.replace(
        record, content=tampered, sha256=_sha256(tampered),
        size_bytes=len(tampered),
    )
    # Identity stays bound to the captured manifest, whatever the mapping now
    # claims.
    assert identity_for(inputs) == identity_before
    source = HISTORY / "scaffolds" / f"{identity_before}-exact"
    path = tmp_path / "gen" / scaffold_dir_name(inputs)
    _copy_historical_tree(source, path)
    verification = verify_scaffold(generated_root=path.parent, name=path.name, inputs=inputs)
    assert verification.conf_files["config.yml"] == original
    assert verification.files["conf/config.yml"] == original


@pytest.mark.parametrize("fixture_name", [
    "df6586a68a8cecbbc1cfcf7eac846948c670927113191eeca4ece186c9e2f975-exact",
    "8a649cd63f4bf17c0df36748af80feeab5c0578510ca7638b2bd43fd199be969-inferred",
], ids=["record", "inferred-provenance"])
def test_historical_record_and_inferred_scaffolds_verify_without_compiler(tmp_path, fixture_name):
    from tests.test_workflow_closed_program_isolation import BLOCK_COMPILER
    script = BLOCK_COMPILER + '''
from pathlib import Path
import json
from orchestrator.prompt_contract import canonical_json_bytes, parse_semantic_contract, PrimitiveType, ListType
from tests.test_prompt_scaffold import _historical_scaffold, _admit, HISTORY
source = HISTORY / "scaffolds" / sys.argv[2]
manifest = json.loads((source / "scaffold.json").read_bytes())
document = json.loads((source / "output-contract.json").read_bytes())
contract = parse_semantic_contract(canonical_json_bytes(document["semantic"]))
assert contract.mode == "record"
assert contract.fields[0].name == "summary"
assert contract.fields[0].type.name == "String"
provider = manifest["provider"]["registry_name"]
conf = _admit(source / "conf") if provider == "omp_conf" else None
result, _ = _historical_scaffold(Path(sys.argv[1]), (source / "prompt.md").read_bytes(),
    contract=contract, provider=provider, conf=conf, authoring=document["authoring"])
assert result.verification.manifest_bytes == (source / "scaffold.json").read_bytes()
for relative, data in result.verification.files.items():
    assert data == (source / relative).read_bytes()
if document["authoring"]["mode"] == "inferred":
    assert contract.record_name == "PromptResult_fe3340e5"
    assert document["authoring"]["provider"] == "omp_conf_inference"
    assert document["authoring"]["session_id"] == "sess-first"
else:
    assert [(field.name, field.type) for field in contract.fields] == [
        ("summary", PrimitiveType("String")),
        ("changed_files", ListType(PrimitiveType("String")))]
assert not any(name.startswith("orchestrator.workflow_lisp") for name in sys.modules)
assert "orchestrator.workflow.executor" not in sys.modules
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(tmp_path), fixture_name],
        cwd=Path(__file__).resolve().parents[1], env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
        text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
