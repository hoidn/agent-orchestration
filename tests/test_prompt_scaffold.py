"""RED behavioral tests for orchestrator.prompt_scaffold (Task 7, Step 7.2).

Covers (brief 7.2 + X7): exact prompt bytes and no path guessing;
deterministic run.orc / prompt+provider manifests / output contract / scaffold
identity for all four public providers; target 2.27, pinned concrete model,
exact semantic return, exactly one :session-artifact omp_session;
omp_conf_root input and conf copy only for omp_conf; omp_no_tools binds the
code-owned neutral conf manifest without an authored override; binary pin and
provider policy are identity inputs; scaffold-root-relative manifest rows,
modes, full coverage, no extra nodes; symlink/special parent refusal,
concurrent same-identity publication, RENAME_NOREPLACE, verified reuse,
mismatched-occupant refusal, and no delete/force path; source/conf/provider/
binary-pin drift rejects rerun; verification-to-execution race fixtures
replace every consumed file after verification and execution consumes only
the captured private snapshot.
"""

from __future__ import annotations

import dataclasses
import errno
import hashlib
import json
import os
import stat
import subprocess
import sys
import threading
from pathlib import Path
from types import MappingProxyType

import pytest

from orchestrator._common.safe_tree import validate_relative_path
from orchestrator.prompt_contract import (
    RENDERER_VERSION,
    ContractField,
    ListType,
    MapType,
    OptionalType,
    PrimitiveType,
    SemanticContract,
    canonical_json_bytes,
    parse_inferred_draft,
)
from orchestrator.prompt_scaffold import (
    OMP_PROVIDER_POLICY,
    OMP_PROVIDER_POLICY_VERSION,
    PUBLIC_PROVIDER_NAMES,
    RunSnapshot,
    ScaffoldIdentityError,
    ScaffoldInputs,
    ScaffoldLockError,
    ScaffoldPublicationError,
    ScaffoldSnapshotError,
    ScaffoldVerificationError,
    compile_snapshot,
    create_run_root,
    generate_scaffold,
    identity_for,
    materialize_run_snapshot,
    resolve_concrete_model,
    scaffold_dir_name,
    slugify,
    verify_scaffold,
)
from orchestrator.prompt_scaffold_fs import (
    acquire_scaffold_lock,
    open_generated_root,
)
from orchestrator import prompt_scaffold_fs as _prompt_scaffold_fs
from orchestrator.providers.omp_conf import admit_conf_tree
from orchestrator.providers.omp_launch import LANE_POLICY
from orchestrator.providers.omp_pin import OMP_BINARY_PIN, OmpBinaryPin
from orchestrator.providers.omp_templates import DEFAULT_OMP_MODEL

CONF_DIR = Path(__file__).parent / "fixtures" / "omp" / "conf"

_SCALAR_STRING = SemanticContract(
    mode="scalar", type=PrimitiveType("String"), record_name=None, fields=()
)
_RECORD_CONTRACT = SemanticContract(
    mode="record",
    type=None,
    record_name="Result",
    fields=(
        ContractField("summary", PrimitiveType("String")),
        ContractField("changed_files", ListType(PrimitiveType("String"))),
    ),
)


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


def _generate(
    tmp_path: Path,
    prompt: bytes,
    *,
    contract: SemanticContract = _SCALAR_STRING,
    provider: str = "omp",
    model: str = DEFAULT_OMP_MODEL,
    conf=None,
    authoring: dict | None = None,
    slug: str = "task",
    pin: OmpBinaryPin = OMP_BINARY_PIN,
    generated_root: Path | None = None,
):
    root = generated_root or (tmp_path / "gen")
    root.mkdir(parents=True, exist_ok=True)
    inputs = _inputs(
        prompt, contract=contract, provider=provider, model=model,
        conf=conf, slug=slug, pin=pin,
    )
    return generate_scaffold(
        generated_root=root,
        inputs=inputs,
        prompt_bytes=prompt,
        authoring=authoring or {"mode": "exact"},
    ), inputs


def _published_files(result) -> dict[str, bytes]:
    return {
        path.relative_to(result.path).as_posix(): path.read_bytes()
        for path in result.path.rglob("*")
        if path.is_file()
    }


# --- exact prompt bytes and no path guessing ---------------------------------


def test_prompt_md_receives_exact_bytes_with_no_path_guessing(tmp_path: Path) -> None:
    prompt = b"task.md\n./also/a/path\n# summary of changed files\n"
    result, _ = _generate(tmp_path, prompt)
    assert (result.path / "prompt.md").read_bytes() == prompt


def test_prompt_md_exact_bytes_for_path_looking_prompt(tmp_path: Path) -> None:
    prompt = b"../secret/file.md"
    result, _ = _generate(tmp_path, prompt)
    assert (result.path / "prompt.md").read_bytes() == prompt
    assert result.path.name == f"task-{result.identity[:12]}"


# --- deterministic scaffolds for all four public providers -------------------


@pytest.mark.parametrize("provider", PUBLIC_PROVIDER_NAMES)
def test_generated_files_deterministic_for_provider(
    tmp_path: Path, provider: str
) -> None:
    first, _ = _generate(tmp_path, b"prompt bytes", provider=provider, conf=_conf_for(provider))
    second, _ = _generate(tmp_path, b"prompt bytes", provider=provider, conf=_conf_for(provider))
    assert first.identity == second.identity
    for name in (
        "run.orc",
        "prompt.md",
        "prompts.json",
        "providers.json",
        "output-contract.json",
        "scaffold.json",
    ):
        assert (first.path / name).read_bytes() == (second.path / name).read_bytes()


def test_manifest_files_are_exact_one_key_objects_plus_lf(tmp_path: Path) -> None:
    for provider in PUBLIC_PROVIDER_NAMES:
        result, _ = _generate(tmp_path, b"p", provider=provider, conf=_conf_for(provider))
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
        result, _ = _generate(tmp_path, b"p", provider=provider, conf=_conf_for(provider))
        identities.add(result.identity)
    assert len(identities) == len(PUBLIC_PROVIDER_NAMES)
    a, _ = _generate(tmp_path, b"p", provider="omp", model="model-a")
    b, _ = _generate(tmp_path, b"p", provider="omp", model="model-b")
    assert a.identity != b.identity


def test_scaffold_dir_name_uses_slug_and_identity_prefix(tmp_path: Path) -> None:
    result, inputs = _generate(tmp_path, b"p")
    assert result.path.name == f"task-{result.identity[:12]}"
    assert scaffold_dir_name(inputs) == result.path.name


def test_slugify_normalization(tmp_path: Path) -> None:
    assert slugify("My Task-7 Brief!!") == "my-task-7-brief"
    assert slugify("") == "prompt"
    assert slugify("!!!") == "prompt"
    assert slugify("a" * 100) == "a" * 32
    assert slugify("UPPER Case") == "upper-case"
    result, _ = _generate(tmp_path, b"p", slug="!!!")
    assert result.path.name.startswith("prompt-")


# --- generated source: target, model, return, session ------------------------


@pytest.mark.parametrize("provider", PUBLIC_PROVIDER_NAMES)
def test_generated_source_target_2_27_model_and_session(
    tmp_path: Path, provider: str
) -> None:
    result, _ = _generate(
        tmp_path, b"p", provider=provider, model="model-x",
        conf=_conf_for(provider),
    )
    source = (result.path / "run.orc").read_text(encoding="utf-8")
    assert '(:target-dsl "2.27")' in source
    assert ':model "model-x"' in source
    assert source.count(":session-artifact omp_session") == 1
    assert "providers.task" in source
    assert "prompts.task" in source


def test_generated_record_source_declares_record_and_returns_it(tmp_path: Path) -> None:
    result, _ = _generate(
        tmp_path, b"p", contract=_RECORD_CONTRACT, provider="omp_conf",
        conf=_admit(CONF_DIR / "advised"),
    )
    source = (result.path / "run.orc").read_text(encoding="utf-8")
    assert "(defrecord Result" in source
    assert "    (summary String)" in source
    assert "    (changed_files List[String])" in source
    assert "-> Result" in source


def test_compile_check_derives_structurally_equal_contract(tmp_path: Path) -> None:
    for provider in PUBLIC_PROVIDER_NAMES:
        result, _ = _generate(
            tmp_path, b"p", contract=_RECORD_CONTRACT, provider=provider,
            conf=_conf_for(provider),
        )
        snapshot = materialize_run_snapshot(
            result.verification, create_run_root(tmp_path / "runs", f"r-{provider}")
        )
        _compiled, derived = compile_snapshot(snapshot, provider)
        assert derived.mode == "record"
        assert [(f.name, f.type) for f in derived.fields] == [
            (f.name, f.type) for f in _RECORD_CONTRACT.fields
        ]


@pytest.mark.parametrize(
    ("field_name", "field_type"),
    [
        # Authorized frontend admission: canonical Optional[T] / Map[String,T]
        # record fields (and nested compositions) must parse, render, and
        # compile structurally equal at target 2.27 (RED evidence; previously
        # workflow_boundary_collection_unsupported).
        ("attrs", MapType(PrimitiveType("Int"))),
        ("maybe", OptionalType(PrimitiveType("String"))),
        ("rows", ListType(MapType(PrimitiveType("Int")))),
        ("groups", MapType(ListType(PrimitiveType("Int")))),
        ("names", OptionalType(ListType(PrimitiveType("String")))),
    ],
)
def test_record_collection_field_must_compile_structurally_equal(
    tmp_path: Path, field_name: str, field_type
) -> None:
    valid = SemanticContract(
        mode="record",
        type=None,
        record_name="Result",
        fields=(ContractField(field_name, field_type),),
    )
    result, _ = _generate(tmp_path, b"p", contract=valid, provider="omp")
    snapshot = materialize_run_snapshot(
        result.verification, create_run_root(tmp_path / "runs", "r")
    )
    _compiled, derived = compile_snapshot(snapshot, "omp")
    assert derived.mode == "record"
    assert derived.fields[0].name == field_name
    assert derived.fields[0].type == field_type


def test_scalar_map_contract_compiles_and_derives(tmp_path: Path) -> None:
    scalar_map = SemanticContract(mode="scalar", type=MapType(PrimitiveType("Int")))
    result, _ = _generate(tmp_path, b"p", contract=scalar_map, provider="omp")
    snapshot = materialize_run_snapshot(
        result.verification, create_run_root(tmp_path / "runs", "r")
    )
    _compiled, derived = compile_snapshot(snapshot, "omp")
    assert derived == scalar_map


# --- omp_conf_root input and conf copy only for omp_conf ---------------------


def test_omp_conf_root_input_and_conf_copy_only_for_omp_conf(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "advised")
    result, _ = _generate(tmp_path, b"p", provider="omp_conf", conf=conf)
    source = (result.path / "run.orc").read_text(encoding="utf-8")
    assert "((omp_conf_root String))" in source
    assert ":inputs (omp_conf_root)" in source
    assert (result.path / "conf" / "config.yml").is_file()
    assert (result.path / "conf" / "agent" / "WATCHDOG.yml").is_file()
    for provider in ("omp", "omp_no_tools", "omp_unrestricted_workspace"):
        other, _ = _generate(tmp_path, b"p", provider=provider)
        assert "omp_conf_root" not in (other.path / "run.orc").read_text(
            encoding="utf-8"
        )
        assert not (other.path / "conf").exists()


def test_conf_files_copied_byte_for_byte_and_normalized_mode(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "advised")
    result, _ = _generate(tmp_path, b"p", provider="omp_conf", conf=conf)
    for relative in ("config.yml", "agent/WATCHDOG.yml"):
        expected = (CONF_DIR / "advised" / relative).read_bytes()
        published = (result.path / "conf" / relative).read_bytes()
        assert published == expected
        assert stat.S_IMODE(os.stat(result.path / "conf" / relative).st_mode) == 0o644


# --- omp_no_tools binds the code-owned neutral manifest ----------------------


def test_omp_no_tools_binds_neutral_conf_manifest(tmp_path: Path) -> None:
    result, inputs = _generate(tmp_path, b"p", provider="omp_no_tools")
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


# --- binary pin and provider policy are identity inputs ----------------------


def test_binary_pin_is_identity_input(tmp_path: Path) -> None:
    del tmp_path
    drifted = dataclasses.replace(OMP_BINARY_PIN, executable_sha256="0" * 64)
    # Identity stays pure: an alternate well-formed pin changes the basis hash.
    baseline = identity_for(_inputs(b"p", provider="omp"))
    drifted_result = identity_for(_inputs(b"p", provider="omp", pin=drifted))
    assert baseline != drifted_result
    # Generation refuses a pin that is not the current OMP_BINARY_PIN before
    # any filesystem write (X7: current binary pin mismatch refuses).
    generated_root = Path("/nonexistent-must-not-be-created")
    with pytest.raises(ValueError):
        generate_scaffold(
            generated_root=generated_root,
            inputs=_inputs(b"p", provider="omp", pin=drifted),
            prompt_bytes=b"p",
            authoring={"mode": "exact"},
        )
    assert not generated_root.exists()


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
    result, inputs = _generate(tmp_path, b"p", provider="omp_conf", conf=_admit(CONF_DIR / "neutral"))
    manifest = json.loads((result.path / "scaffold.json").read_bytes())
    assert manifest["identity"] == result.identity
    assert len(result.identity) == 64
    assert all(ch in "0123456789abcdef" for ch in result.identity)


def test_resolve_concrete_model_uses_template_default() -> None:
    assert resolve_concrete_model("omp", None) == DEFAULT_OMP_MODEL
    assert resolve_concrete_model("omp", "explicit-model") == "explicit-model"
    with pytest.raises(ValueError):
        resolve_concrete_model("omp", "")
    with pytest.raises(ValueError):
        resolve_concrete_model("unknown", None)


# --- scaffold manifest rows, modes, coverage, no extra nodes -----------------


def test_scaffold_manifest_rows_cover_all_files_without_extra_nodes(
    tmp_path: Path,
) -> None:
    conf = _admit(CONF_DIR / "advised")
    result, _ = _generate(tmp_path, b"p", provider="omp_conf", conf=conf)
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
    result, _ = _generate(tmp_path, b"p", provider="omp")
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


# --- publication safety ------------------------------------------------------


def test_symlink_generated_root_refused(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ScaffoldVerificationError):
        _generate(tmp_path, b"p", generated_root=link)


def test_special_file_generated_root_refused(tmp_path: Path) -> None:
    special = tmp_path / "fifo"
    os.mkfifo(special)
    with pytest.raises(ScaffoldVerificationError):
        generate_scaffold(
            generated_root=special,
            inputs=_inputs(b"p"),
            prompt_bytes=b"p",
            authoring={"mode": "exact"},
        )


def test_generate_requires_nonempty_prompt_and_model(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _generate(tmp_path, b"")
    with pytest.raises(ValueError):
        _generate(tmp_path, b"p", model="")


def test_verified_reuse_returns_identical_scaffold(tmp_path: Path) -> None:
    first, _ = _generate(tmp_path, b"p")
    assert first.reused is False
    second, _ = _generate(tmp_path, b"p")
    assert second.reused is True
    assert second.path == first.path
    assert second.identity == first.identity
    assert _published_files(first) == _published_files(second)


def test_mismatched_occupant_refused_without_delete_or_force(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p")
    occupied = result.path
    original = _published_files(result)
    (occupied / "run.orc").write_text("(definitely not the generated source)\n")
    with pytest.raises(ScaffoldVerificationError):
        _generate(tmp_path, b"p")
    assert _published_files(result)["run.orc"] == (
        b"(definitely not the generated source)\n"
    )
    assert set(_published_files(result)) == set(original)
    assert not (occupied.parent / ".tmp").exists()


def test_identity_drift_occupant_refused(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p")
    scaffold_json = result.path / "scaffold.json"
    manifest = json.loads(scaffold_json.read_bytes())
    manifest["identity"] = "0" * 64
    scaffold_json.write_text(json.dumps(manifest))
    with pytest.raises(ScaffoldIdentityError):
        _generate(tmp_path, b"p")


def test_extra_node_in_occupant_refused(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p")
    (result.path / "sneaky.txt").write_text("extra\n")
    with pytest.raises(ScaffoldVerificationError):
        _generate(tmp_path, b"p")


def test_concurrent_same_identity_publication(tmp_path: Path) -> None:
    generated_root = tmp_path / "gen"
    generated_root.mkdir()
    barrier = threading.Barrier(2)
    outcomes: list = []
    errors: list = []

    def worker() -> None:
        try:
            barrier.wait()
            inputs = _inputs(b"p", provider="omp")
            outcome = generate_scaffold(
                generated_root=generated_root,
                inputs=inputs,
                prompt_bytes=b"p",
                authoring={"mode": "exact"},
            )
            outcomes.append(outcome)
        except BaseException as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert len(outcomes) == 2
    assert outcomes[0].identity == outcomes[1].identity
    assert outcomes[0].path == outcomes[1].path
    assert sorted([outcome.reused for outcome in outcomes]) == [False, True]
    scaffold_dirs = [
        entry
        for entry in generated_root.iterdir()
        if entry.is_dir() and entry.name != ".omp-scaffold-locks"
    ]
    assert len(scaffold_dirs) == 1
    assert _published_files(outcomes[0]) == _published_files(outcomes[1])


# --- drift rejects rerun ------------------------------------------------------


def test_prompt_drift_rejects_rerun(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"original")
    drifted = _inputs(b"mutated", provider="omp")
    with pytest.raises(ScaffoldIdentityError):
        verify_scaffold(
            generated_root=result.path.parent,
            name=result.path.name,
            inputs=drifted,
        )


def test_provider_drift_rejects_rerun(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
    drifted = _inputs(b"p", provider="omp_conf", conf=_admit(CONF_DIR / "neutral"))
    with pytest.raises(ScaffoldIdentityError):
        verify_scaffold(
            generated_root=result.path.parent,
            name=result.path.name,
            inputs=drifted,
        )


def test_binary_pin_drift_rejects_rerun(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
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
    result, _ = _generate(tmp_path, b"p", provider="omp_conf", conf=conf)
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
    result, inputs = _generate(tmp_path, b"p", provider="omp")
    verification = verify_scaffold(
        generated_root=result.path.parent, name=result.path.name, inputs=inputs
    )
    assert verification.identity == result.identity
    assert verification.files["run.orc"] == (result.path / "run.orc").read_bytes()
    assert verification.files["prompt.md"] == b"p"


# --- run-owned private snapshot + verification-to-execution races ------------


def test_snapshot_modes_are_private(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp_conf", conf=_admit(CONF_DIR / "advised"))
    run_root = create_run_root(tmp_path / "runs", "r1")
    snapshot = materialize_run_snapshot(result.verification, run_root)
    for directory in (
        snapshot.root,
        snapshot.root / "conf",
        snapshot.root / "conf" / "agent",
    ):
        assert stat.S_IMODE(os.stat(directory).st_mode) == 0o500
    for file_path in snapshot.root.rglob("*"):
        if file_path.is_file():
            assert stat.S_IMODE(os.stat(file_path).st_mode) == 0o400


def test_pre_existing_run_root_fails(tmp_path: Path) -> None:
    create_run_root(tmp_path / "runs", "rid")
    with pytest.raises(ScaffoldSnapshotError):
        create_run_root(tmp_path / "runs", "rid")


def test_ambient_snapshot_has_no_conf_root(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
    snapshot = materialize_run_snapshot(
        result.verification, create_run_root(tmp_path / "runs", "r")
    )
    assert snapshot.conf_root is None
    assert set(snapshot.root.rglob("*")) == {
        snapshot.root / "run.orc",
        snapshot.root / "prompt.md",
        snapshot.root / "prompts.json",
        snapshot.root / "providers.json",
        snapshot.root / "output-contract.json",
    }


def test_race_swap_run_orc_after_verification_consumes_snapshot_bytes(
    tmp_path: Path,
) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
    verification = result.verification
    captured_run_orc = verification.files["run.orc"]
    (result.path / "run.orc").write_text("(substituted evil source)\n")
    snapshot = materialize_run_snapshot(
        verification, create_run_root(tmp_path / "runs", "r")
    )
    assert snapshot.run_orc.read_bytes() == captured_run_orc
    assert b"evil" not in snapshot.run_orc.read_bytes()


def test_race_swap_prompt_and_externs_after_verification(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"captured prompt", provider="omp")
    verification = result.verification
    (result.path / "prompt.md").write_text("substituted prompt\n")
    (result.path / "prompts.json").write_text('{"prompts.task":"evil.md"}\n')
    (result.path / "providers.json").write_text('{"providers.task":"evil"}\n')
    snapshot = materialize_run_snapshot(
        verification, create_run_root(tmp_path / "runs", "r")
    )
    assert snapshot.prompt_md.read_bytes() == b"captured prompt"
    assert snapshot.prompts_json.read_bytes() == b'{"prompts.task":"prompt.md"}\n'
    assert snapshot.providers_json.read_bytes() == (
        json.dumps(
            {"providers.task": "omp"},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def test_race_swap_conf_after_verification_consumes_snapshot_conf(
    tmp_path: Path,
) -> None:
    conf = _admit(CONF_DIR / "advised")
    result, _ = _generate(tmp_path, b"p", provider="omp_conf", conf=conf)
    captured_conf = result.verification.conf_files["config.yml"]
    (result.path / "conf" / "config.yml").write_text("evil: true\n")
    snapshot = materialize_run_snapshot(
        result.verification, create_run_root(tmp_path / "runs", "r")
    )
    assert (snapshot.conf_root / "config.yml").read_bytes() == captured_conf
    assert b"evil" not in (snapshot.conf_root / "config.yml").read_bytes()


def test_compile_from_snapshot_consumes_only_snapshot_paths_after_swaps(
    tmp_path: Path,
) -> None:
    result, _ = _generate(
        tmp_path, b"verified prompt", contract=_RECORD_CONTRACT, provider="omp_conf",
        conf=_admit(CONF_DIR / "advised"),
    )
    verification = result.verification
    # Swap every path execution could read in the published scaffold.
    (result.path / "run.orc").write_text("(evil)\n")
    (result.path / "prompt.md").write_text("evil\n")
    (result.path / "prompts.json").write_text('{"prompts.task":"evil.md"}\n')
    (result.path / "providers.json").write_text('{"providers.task":"evil"}\n')
    (result.path / "conf" / "config.yml").write_text("evil: true\n")
    snapshot = materialize_run_snapshot(
        verification, create_run_root(tmp_path / "runs", "r")
    )
    compiled, derived = compile_snapshot(snapshot, "omp_conf")
    assert derived.mode == "record"
    assert [(f.name, f.type) for f in derived.fields] == [
        (f.name, f.type) for f in _RECORD_CONTRACT.fields
    ]
    mapping = compiled.entry_result.lowered_workflows[0].authored_mapping
    step = next(s for s in mapping["steps"] if "provider" in s)
    assert step["provider"] == "omp_conf"
    assert step["asset_file"] == "prompt.md"
    # The compiler's asset resolver reads prompt.md relative to the snapshot.
    from orchestrator.workflow.assets import WorkflowAssetResolver

    resolver = WorkflowAssetResolver(snapshot.run_orc)
    assert resolver.read_text("prompt.md") == "verified prompt"
    assert (snapshot.root / "prompt.md").read_bytes() == b"verified prompt"
    assert snapshot.run_orc.read_bytes() == verification.files["run.orc"]


def test_verify_then_swap_then_snapshot_keeps_verified_bytes(tmp_path: Path) -> None:
    result, inputs = _generate(tmp_path, b"p", provider="omp")
    verification = verify_scaffold(
        generated_root=result.path.parent, name=result.path.name, inputs=inputs
    )
    captured = verification.files
    (result.path / "run.orc").write_text("(swapped after verify)\n")
    snapshot = materialize_run_snapshot(
        verification, create_run_root(tmp_path / "runs", "r")
    )
    assert snapshot.run_orc.read_bytes() == captured["run.orc"]
    _compiled, derived = compile_snapshot(snapshot, "omp")
    assert derived.mode == "scalar"
    assert derived.type == PrimitiveType("String")


# --- inferred generation provenance binding ----------------------------------


def test_repeated_inferred_generation_retains_first_authoring(tmp_path: Path) -> None:
    contract = parse_inferred_draft(
        json.dumps({"fields": [{"name": "summary", "type": "String"}]}),
        prompt_sha256=_sha256(b"inferred prompt"),
    )
    first_authoring = {
        "mode": "inferred",
        "output_request_sha256": "a" * 64,
        "provider": "omp_conf_inference",
        "model": DEFAULT_OMP_MODEL,
        "session_id": "sess-first",
        "usage": {
            "input": 1,
            "output": 1,
            "cacheRead": 0,
            "cacheWrite": 0,
            "totalTokens": 2,
            "cost": {
                "input": 0.0,
                "output": 0.0,
                "cacheRead": 0.0,
                "cacheWrite": 0.0,
                "total": 0.0,
            },
        },
    }
    second_authoring = dict(first_authoring, session_id="sess-second")
    first, _ = _generate(
        tmp_path,
        b"inferred prompt",
        contract=contract,
        provider="omp_no_tools",
        authoring=first_authoring,
    )
    second, _ = _generate(
        tmp_path,
        b"inferred prompt",
        contract=contract,
        provider="omp_no_tools",
        authoring=second_authoring,
    )
    assert second.reused is True
    assert second.identity == first.identity
    document = json.loads((first.path / "output-contract.json").read_bytes())
    assert document["authoring"]["session_id"] == "sess-first"
    assert document["semantic"]["record_name"].startswith("PromptResult_")


def test_output_contract_json_closed_shape(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp", authoring={"mode": "default"})
    document = json.loads((result.path / "output-contract.json").read_bytes())
    assert set(document) == {"schema_version", "semantic", "authoring"}
    assert document["schema_version"] == "scaffold_output_contract.v1"
    assert document["semantic"] == {"mode": "scalar", "type": "String"}
    assert document["authoring"] == {"mode": "default"}


def test_generate_rejects_invalid_authoring(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _generate(tmp_path, b"p", provider="omp", authoring={"mode": "bogus"})


# --- security fix round: identity binding, verification, publication --------


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
    result, inputs = _generate(tmp_path, b"p", provider="omp")
    os.chmod(result.path / "prompt.md", mode)
    with pytest.raises(ScaffoldVerificationError):
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )


def test_occupant_noncanonical_manifest_rejected(tmp_path: Path) -> None:
    result, inputs = _generate(tmp_path, b"p", provider="omp")
    scaffold = result.path / "scaffold.json"
    original = scaffold.read_bytes()
    manifest = json.loads(original)
    # Extra top-level key.
    extra = dict(manifest)
    extra["extra"] = True
    scaffold.write_bytes(canonical_json_bytes(extra))
    with pytest.raises(ScaffoldVerificationError):
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )
    # Duplicate JSON key.
    marker = b'"schema_version":"prompt_scaffold.v1"'
    scaffold.write_bytes(
        original.replace(marker, marker + b"," + marker, 1)
    )
    with pytest.raises(ScaffoldVerificationError):
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )
    # Non-canonical formatting of an otherwise valid manifest.
    scaffold.write_bytes(json.dumps(manifest, sort_keys=True).encode("utf-8"))
    with pytest.raises(ScaffoldVerificationError):
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )


def test_self_consistent_run_orc_tamper_rejected(tmp_path: Path) -> None:
    result, inputs = _generate(tmp_path, b"p", provider="omp")
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
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )


def test_self_consistent_conf_tamper_rejected(tmp_path: Path) -> None:
    conf = _admit(CONF_DIR / "neutral")
    result, inputs = _generate(tmp_path, b"p", provider="omp_conf", conf=conf)
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
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )


def test_extra_empty_directory_rejected(tmp_path: Path) -> None:
    result, inputs = _generate(tmp_path, b"p", provider="omp")
    (result.path / "empty-dir").mkdir()
    with pytest.raises(ScaffoldVerificationError):
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )


def test_symlinked_runs_root_ancestor_rejected_without_writing(
    tmp_path: Path,
) -> None:
    real_runs = tmp_path / "real-runs"
    real_runs.mkdir()
    link = tmp_path / "runs"
    link.symlink_to(real_runs, target_is_directory=True)
    with pytest.raises(ScaffoldSnapshotError):
        create_run_root(link, "rid")
    assert list(real_runs.iterdir()) == []


def test_materialize_rejects_symlinked_run_root(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
    real = tmp_path / "real-root"
    real.mkdir()
    run_root = tmp_path / "run-root"
    run_root.symlink_to(real, target_is_directory=True)
    with pytest.raises(ScaffoldSnapshotError):
        materialize_run_snapshot(result.verification, run_root)
    assert list(real.iterdir()) == []


def test_unsafe_model_renders_as_literal_and_compiles_exact(
    tmp_path: Path,
) -> None:
    model = 'gpt-4.1" ) (evil # comment'
    result, _ = _generate(tmp_path, b"p", provider="omp", model=model)
    source = (result.path / "run.orc").read_text(encoding="utf-8")
    assert ':model "gpt-4.1\\" ) (evil # comment"' in source
    snapshot = materialize_run_snapshot(
        result.verification, create_run_root(tmp_path / "runs", "r")
    )
    compiled, _derived = compile_snapshot(snapshot, "omp")
    mapping = compiled.entry_result.lowered_workflows[0].authored_mapping
    step = next(s for s in mapping["steps"] if "provider" in s)
    assert step["provider_call_policy"]["model"] == model


def test_model_control_character_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        _generate(tmp_path, b"p", provider="omp", model="bad\x01model")


def test_prompt_sha256_mismatch_rejected_before_writes(tmp_path: Path) -> None:
    root = tmp_path / "gen"
    root.mkdir()
    with pytest.raises(ValueError):
        generate_scaffold(
            generated_root=root, inputs=_inputs(b"p"),
            prompt_bytes=b"other", authoring={"mode": "exact"},
        )
    assert list(root.iterdir()) == []


def test_prompt_invalid_utf8_rejected_before_writes(tmp_path: Path) -> None:
    root = tmp_path / "gen"
    root.mkdir()
    with pytest.raises(ValueError):
        generate_scaffold(
            generated_root=root, inputs=_inputs(b"\xff\xfe"),
            prompt_bytes=b"\xff\xfe", authoring={"mode": "exact"},
        )
    assert list(root.iterdir()) == []


def test_lock_symlink_fails_closed_without_touching_target(
    tmp_path: Path,
) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
    victim = tmp_path / "victim"
    victim.write_text("secret\n")
    locks = result.path.parent / ".omp-scaffold-locks"
    (locks / f"{result.identity}.lock").unlink()
    (locks / f"{result.identity}.lock").symlink_to(victim)
    root_fd = open_generated_root(result.path.parent)
    try:
        with pytest.raises(ScaffoldLockError):
            acquire_scaffold_lock(root_fd, result.identity)
    finally:
        os.close(root_fd)
    assert victim.read_text() == "secret\n"


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
        "assert orchestrator.prompt_scaffold.compile_snapshot is not None"
    )


def test_direct_first_import_prompt_contract_authoring() -> None:
    _fresh_interpreter_imports(
        "import orchestrator.prompt_contract_authoring; "
        "import orchestrator.prompt_contract; "
        "assert orchestrator.prompt_contract.validate_authoring("
        "{'mode': 'exact'}) == {'mode': 'exact'}"
    )


def test_eexist_race_winner_verified_and_reused(monkeypatch, tmp_path: Path) -> None:
    first, _ = _generate(tmp_path, b"p")
    assert first.reused is False
    real_open = os.open
    hidden = {"active": True}

    def _hide_destination(name, *args, **kwargs):
        if hidden["active"] and name == first.path.name:
            raise FileNotFoundError(errno.ENOENT, "hidden destination")
        return real_open(name, *args, **kwargs)

    real_rename = _prompt_scaffold_fs.rename_noreplace_at

    def _race_rename(*args, **kwargs):
        hidden["active"] = False
        real_rename(*args, **kwargs)
        raise OSError(errno.EEXIST, "race lost")

    monkeypatch.setattr(_prompt_scaffold_fs.os, "open", _hide_destination)
    monkeypatch.setattr(
        _prompt_scaffold_fs, "rename_noreplace_at", _race_rename
    )
    second, _ = _generate(tmp_path, b"p")
    assert second.reused is True
    assert second.identity == first.identity
    assert _published_files(second) == _published_files(first)


def test_replaced_generated_root_rejected_before_rename(
    monkeypatch, tmp_path: Path
) -> None:
    root = tmp_path / "gen"
    root.mkdir()
    real_write_tree = _prompt_scaffold_fs.write_tree

    def _swap_parent_and_continue(root_fd, files, file_mode):
        real_write_tree(root_fd, files, file_mode)
        moved = tmp_path / "gen-moved"
        root.rename(moved)
        root.mkdir()

    monkeypatch.setattr(
        _prompt_scaffold_fs, "write_tree", _swap_parent_and_continue
    )
    with pytest.raises(ScaffoldPublicationError):
        _generate(tmp_path, b"p", generated_root=root)
    assert list(root.iterdir()) == []


def test_verification_captures_are_immutable(tmp_path: Path) -> None:
    result, _ = _generate(
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
    result, _ = _generate(tmp_path, b"p", provider="omp")
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
    # scaffold.json never enters the execution snapshot file set.
    snapshot = materialize_run_snapshot(
        verification, create_run_root(tmp_path / "runs", "r")
    )
    assert "scaffold.json" not in verification.files
    assert not (snapshot.root / "scaffold.json").exists()


def test_unknown_temp_replacement_never_deleted(monkeypatch, tmp_path: Path) -> None:
    root = tmp_path / "gen"
    root.mkdir()
    real_write_tree = _prompt_scaffold_fs.write_tree
    swap = {}

    def _swap_and_fail(root_fd, files, file_mode):
        real_write_tree(root_fd, files, file_mode)
        # root_fd is the temp dir itself; derive its real path and swap the
        # directory out for an unknown replacement mid-publication.
        temp_path = Path(os.readlink(f"/proc/self/fd/{root_fd}"))
        parent = temp_path.parent
        temp = temp_path.name
        os.rename(temp_path, parent / (temp + "-moved"))
        replacement = parent / temp
        replacement.mkdir()
        temp_fd = os.open(
            replacement, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        )
        try:
            marker = os.open(
                "marker.txt", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600,
                dir_fd=temp_fd,
            )
            os.write(marker, b"attacker")
            os.close(marker)
        finally:
            os.close(temp_fd)
        swap["temp"] = temp
        raise RuntimeError("forced write failure")

    monkeypatch.setattr(_prompt_scaffold_fs, "write_tree", _swap_and_fail)
    with pytest.raises(RuntimeError):
        _generate(tmp_path, b"p", generated_root=root)
    replacement = root / swap["temp"]
    assert replacement.is_dir()
    assert (replacement / "marker.txt").read_bytes() == b"attacker"


@pytest.mark.parametrize(
    "bad_name", ["../evil", "a/b", "a\0b", "..", "."]
)
def test_verify_scaffold_rejects_unsafe_name(bad_name, tmp_path: Path) -> None:
    result, inputs = _generate(tmp_path, b"p", provider="omp")
    with pytest.raises(ValueError):
        verify_scaffold(
            generated_root=result.path.parent, name=bad_name, inputs=inputs
        )


def test_compile_snapshot_rejects_different_provider(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
    snapshot = materialize_run_snapshot(
        result.verification, create_run_root(tmp_path / "runs", "r")
    )
    with pytest.raises(ValueError):
        compile_snapshot(snapshot, "omp_unrestricted_workspace")
    _compiled, derived = compile_snapshot(snapshot, "omp")
    assert derived.mode == "scalar"
    assert derived.type == PrimitiveType("String")


# --- second fix round: forged conf, closed inputs, deep immutability, ownership


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
    result, inputs = _generate(tmp_path, b"p", provider="omp")
    (result.path / "scaffold.json").chmod(0o600)
    with pytest.raises(ScaffoldVerificationError):
        generate_scaffold(
            generated_root=result.path.parent, inputs=inputs,
            prompt_bytes=b"p", authoring={"mode": "exact"},
        )


def test_verification_manifest_is_deeply_immutable(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
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
    root = tmp_path / "gen"
    root.mkdir()
    result = generate_scaffold(
        generated_root=root, inputs=inputs, prompt_bytes=b"p",
        authoring={"mode": "exact"},
    )
    published = _published_files(result)
    assert published["conf/config.yml"] == original
    # The private run snapshot copies the same captured bytes.
    verification = verify_scaffold(
        generated_root=root, name=result.path.name, inputs=inputs,
    )
    snapshot = _prompt_scaffold_fs.materialize_run_snapshot(
        verification,
        _prompt_scaffold_fs.create_run_root(tmp_path / "runs", "r1"),
    )
    try:
        conf_root = snapshot.conf_root
        assert (Path(conf_root) / "config.yml").read_bytes() == original
    finally:
        snapshot.close()


def test_run_snapshot_requires_provider_and_root_fd() -> None:
    with pytest.raises(TypeError):
        RunSnapshot(
            root=Path("."), run_orc=Path("."), prompt_md=Path("."),
            prompts_json=Path("."), providers_json=Path("."),
            output_contract_json=Path("."), conf_root=None,
        )


def test_run_snapshot_context_manager_owns_root_fd(tmp_path: Path) -> None:
    result, _ = _generate(tmp_path, b"p", provider="omp")
    snapshot = materialize_run_snapshot(
        result.verification, create_run_root(tmp_path / "runs", "r")
    )
    os.fstat(snapshot.root_fd)  # open before entering
    with snapshot:
        os.fstat(snapshot.root_fd)
    # Context exit closed the retained descriptor: compilation refuses.
    with pytest.raises(ValueError):
        compile_snapshot(snapshot, "omp")
    snapshot.close()  # idempotent double-close is safe
    snapshot.close()
