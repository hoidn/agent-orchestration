from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from orchestrator.workflow.run_ref.contracts import (
    PostSetupBaselineIdentity,
    RepositoryRevisionId,
    SetupCommand,
    SetupPolicy,
    VerifiedCompilerRuntimeIdentity,
    VerifiedGitTreeIdentity,
    authored_setup_identity,
    compute_compiler_runtime_identity,
)
from orchestrator.workflow.run_ref import source as source_module
from orchestrator.workflow.run_ref.source import (
    RunRefSourceRefusal,
    SourceRequest,
    canonical_repository_revision_result,
    canonical_source_request,
    materialize_source,
    normalize_repository_locator,
    validate_commit_sha,
)
from orchestrator.workflow.run_ref.workspace import (
    TreeManifest,
    WorkspaceFreezeError,
    freeze_tree,
)


def _canonical_digest(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def test_repository_locator_normalization_accepts_only_canonical_supported_forms(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "parent" / "repository"
    repository.mkdir(parents=True)

    assert normalize_repository_locator(str(repository)) == repository.as_uri()
    assert normalize_repository_locator(repository.as_uri()) == repository.as_uri()
    assert (
        normalize_repository_locator("https://example.com/team/repository.git")
        == "https://example.com/team/repository.git"
    )
    assert (
        normalize_repository_locator("ssh://example.com/team/repository.git")
        == "ssh://example.com/team/repository.git"
    )


@pytest.mark.parametrize(
    "locator",
    [
        "file:///tmp/%ff/repository",
        "https://example.com/team/%c3%28/repository.git",
        "ssh://example.com/team/%e2%28%a1/repository.git",
    ],
)
def test_repository_locator_rejects_invalid_utf8_percent_encodings(
    locator: str,
) -> None:
    with pytest.raises(RunRefSourceRefusal) as caught:
        normalize_repository_locator(locator)

    assert caught.value.code == "trial_source_unresolvable"
    assert caught.value.rejected_value == locator


@pytest.mark.parametrize("scheme", ["file", "https", "ssh"])
@pytest.mark.parametrize("encoded_separator", ["%2f", "%2F", "%5c", "%5C"])
def test_repository_locator_rejects_encoded_path_separators(
    scheme: str,
    encoded_separator: str,
) -> None:
    if scheme == "file":
        locator = f"file:///tmp/team{encoded_separator}repository"
    else:
        locator = f"{scheme}://example.com/team{encoded_separator}repository.git"

    with pytest.raises(RunRefSourceRefusal) as caught:
        normalize_repository_locator(locator)

    assert caught.value.code == "trial_source_unresolvable"
    assert caught.value.rejected_value == locator


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        (
            "HTTPS://EXAMPLE.COM:443/team/caf%C3%A9%7Erepository.git/",
            "https://example.com/team/caf%C3%A9~repository.git",
        ),
        (
            "https://example.com/team/café~repository.git",
            "https://example.com/team/caf%C3%A9~repository.git",
        ),
        (
            "SSH://EXAMPLE.COM:22/team/caf%C3%A9%7erepository.git/",
            "ssh://example.com/team/caf%C3%A9~repository.git",
        ),
        (
            "ssh://example.com/team/café~repository.git",
            "ssh://example.com/team/caf%C3%A9~repository.git",
        ),
    ],
)
def test_repository_locator_normalizes_unicode_unreserved_and_authority_equivalents(
    locator: str,
    expected: str,
) -> None:
    assert normalize_repository_locator(locator) == expected


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        (
            "HTTPS://EXAMPLE.COM:443/team/repository.git/",
            "https://example.com/team/repository.git",
        ),
        (
            "SSH://EXAMPLE.COM:22/team/repository.git/",
            "ssh://example.com/team/repository.git",
        ),
        (
            "https://EXAMPLE.COM:8443/team/repository.git/",
            "https://example.com:8443/team/repository.git",
        ),
        (
            "ssh://EXAMPLE.COM:2222/team/repository.git/",
            "ssh://example.com:2222/team/repository.git",
        ),
    ],
)
def test_repository_locator_authority_normalization_is_deterministic(
    locator: str,
    expected: str,
) -> None:
    assert normalize_repository_locator(locator) == expected


@pytest.mark.parametrize("scheme", ["https", "ssh"])
@pytest.mark.parametrize(
    "noncanonical_path",
    [
        "/team/./repository.git",
        "/team/../repository.git",
        "/team/%2e/repository.git",
        "/team/%2E%2E/repository.git",
        "/team//repository.git",
        "//team/repository.git",
        "/team/%00/repository.git",
    ],
)
def test_network_repository_locator_rejects_noncanonical_decoded_segments(
    scheme: str,
    noncanonical_path: str,
) -> None:
    locator = f"{scheme}://example.com{noncanonical_path}"

    with pytest.raises(RunRefSourceRefusal) as caught:
        normalize_repository_locator(locator)

    assert caught.value.code == "trial_source_unresolvable"
    assert caught.value.rejected_value == locator


@pytest.mark.parametrize(
    ("locator", "expected"),
    [
        (
            "HTTPS://[2001:DB8::1]:443/team/repository.git/",
            "https://[2001:db8::1]/team/repository.git",
        ),
        (
            "ssh://[2001:DB8::1]:2222/team/repository.git/",
            "ssh://[2001:db8::1]:2222/team/repository.git",
        ),
    ],
)
def test_network_repository_locator_preserves_ipv6_authority_brackets(
    locator: str,
    expected: str,
) -> None:
    assert normalize_repository_locator(locator) == expected


@pytest.mark.parametrize(
    "locator",
    [
        "relative/repository",
        "git@example.com:team/repository.git",
        "http://example.com/team/repository.git",
        "https://user@example.com/team/repository.git",
        "ssh://user@example.com/team/repository.git",
        "https://example.com/team/repository.git?ref=main",
        "https://example.com/team/repository.git#fragment",
        "file:relative/repository",
    ],
)
def test_repository_locator_normalization_strictly_rejects_ambiguous_forms(
    locator: str,
) -> None:
    with pytest.raises(RunRefSourceRefusal) as caught:
        normalize_repository_locator(locator)

    assert caught.value.code == "trial_source_unresolvable"
    assert caught.value.rejected_value == locator


@pytest.mark.parametrize(
    "commit",
    [
        "A" * 40,
        "a" * 39,
        "a" * 41,
        "g" * 40,
        "main",
        "refs/heads/main",
        " a" * 20,
    ],
)
def test_commit_must_be_exact_lowercase_40_hex(commit: str) -> None:
    with pytest.raises(RunRefSourceRefusal) as caught:
        validate_commit_sha(commit)

    assert caught.value.code == "trial_source_revision_digest_mismatch"
    assert caught.value.rejected_value == commit


def test_commit_accepts_exact_lowercase_40_hex() -> None:
    commit = "0123456789abcdef0123456789abcdef01234567"

    assert validate_commit_sha(commit) == commit


def test_repository_revision_id_hashes_exactly_the_six_accepted_inputs() -> None:
    setup = SetupPolicy(
        commands=(
            SetupCommand(
                argv=("./tools/bootstrap", "--locked"),
                env=(("MODE", "release"),),
            ),
        )
    )
    setup_identity = authored_setup_identity(setup)
    inputs = {
        "normalized_locator": "https://example.com/team/repository.git",
        "resolved_commit_sha": "0123456789abcdef0123456789abcdef01234567",
        "materializer_version": "git-detached-clone-v1",
        "submodule_policy": "reject-v1",
        "lfs_policy": "reject-v1",
        "authored_setup_identity": setup_identity,
    }

    identity = RepositoryRevisionId.build(**inputs)

    assert identity.components == inputs
    assert identity.digest == _canonical_digest(inputs)

    valid_alternatives = {
        "normalized_locator": "ssh://example.com/team/repository.git",
        "resolved_commit_sha": "89abcdef0123456789abcdef0123456789abcdef",
        "materializer_version": "git-detached-clone-v2",
        "submodule_policy": "reject-v2",
        "lfs_policy": "reject-v2",
        "authored_setup_identity": "sha256:" + "2" * 64,
    }
    variants: list[dict[str, str]] = []
    for key, value in valid_alternatives.items():
        changed = dict(inputs)
        changed[key] = value
        variants.append(changed)
    assert all(
        RepositoryRevisionId.build(**variant).digest != identity.digest
        for variant in variants
    )
    assert len(
        {RepositoryRevisionId.build(**variant).digest for variant in variants}
    ) == len(variants)


def test_canonical_source_request_has_the_exact_closed_v1_shape() -> None:
    setup = SetupPolicy(
        commands=(
            SetupCommand(
                argv=("./tools/bootstrap", "--locked"),
                env=(("MODE", "release"),),
            ),
        )
    )
    request = SourceRequest(
        locator="HTTPS://EXAMPLE.COM:443/team/caf%C3%A9%7Erepository.git/",
        commit="0123456789abcdef0123456789abcdef01234567",
        setup=setup,
    )

    record = canonical_source_request(request)

    assert record == {
        "schema_version": "run_ref_source.v1",
        "normalized_locator": "https://example.com/team/caf%C3%A9~repository.git",
        "resolved_commit_sha": "0123456789abcdef0123456789abcdef01234567",
        "materializer_version": "git-detached-clone-v1",
        "submodule_policy": "reject-v1",
        "lfs_policy": "reject-v1",
        "authored_setup": {
            "commands": [
                {
                    "argv": ["./tools/bootstrap", "--locked"],
                    "env": [["MODE", "release"]],
                }
            ]
        },
        "authored_setup_identity": authored_setup_identity(setup),
    }
    assert {
        "verified_git_tree",
        "compiler_runtime_identity",
        "post_setup_baseline_identity",
        "workspace_path",
        "stdout",
        "stderr",
    }.isdisjoint(record)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("materializer_version", "git-detached-clone-v2"),
        ("submodule_policy", "allow-v1"),
        ("lfs_policy", "allow-v1"),
        ("setup", object()),
    ],
)
def test_canonical_source_request_rejects_unimplemented_v1_policy_values(
    field: str,
    value: object,
) -> None:
    values: dict[str, object] = {
        "locator": "https://example.com/team/repository.git",
        "commit": "0123456789abcdef0123456789abcdef01234567",
        "materializer_version": "git-detached-clone-v1",
        "submodule_policy": "reject-v1",
        "lfs_policy": "reject-v1",
        "setup": SetupPolicy(),
    }
    values[field] = value
    request = SourceRequest(**values)  # type: ignore[arg-type]

    with pytest.raises(RunRefSourceRefusal) as caught:
        canonical_source_request(request)

    assert caught.value.code == "trial_materialization_digest_mismatch"
    assert caught.value.rejected_value == value


def test_canonical_repository_revision_result_has_exact_identity_only_shape() -> None:
    inputs = {
        "normalized_locator": "https://example.com/team/repository.git",
        "resolved_commit_sha": "0123456789abcdef0123456789abcdef01234567",
        "materializer_version": "git-detached-clone-v1",
        "submodule_policy": "reject-v1",
        "lfs_policy": "reject-v1",
        "authored_setup_identity": "sha256:" + "1" * 64,
    }
    revision = RepositoryRevisionId.build(**inputs)

    record = canonical_repository_revision_result(revision)

    assert record == {
        "schema_version": "run_ref_repository_revision.v1",
        "digest": revision.digest,
        **inputs,
    }
    assert {
        "verified_git_tree",
        "compiler_runtime_identity",
        "post_setup_baseline_identity",
        "mirror_path",
        "workspace_path",
        "setup_evidence",
        "stdout",
        "stderr",
    }.isdisjoint(record)


def test_canonical_repository_revision_result_rejects_digest_consistent_noncanonical_locator(
) -> None:
    noncanonical_locator = "HTTPS://EXAMPLE.COM:443/team/repository.git/"
    revision = RepositoryRevisionId.build(
        normalized_locator=noncanonical_locator,
        resolved_commit_sha="0123456789abcdef0123456789abcdef01234567",
        materializer_version="git-detached-clone-v1",
        submodule_policy="reject-v1",
        lfs_policy="reject-v1",
        authored_setup_identity="sha256:" + "1" * 64,
    )

    with pytest.raises(RunRefSourceRefusal) as caught:
        canonical_repository_revision_result(revision)

    assert caught.value.code == "trial_materialization_digest_mismatch"
    assert caught.value.rejected_value == noncanonical_locator


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("normalized_locator", ""),
        ("resolved_commit_sha", "A" * 40),
        ("resolved_commit_sha", "a" * 39),
        ("materializer_version", ""),
        ("submodule_policy", ""),
        ("lfs_policy", ""),
        ("authored_setup_identity", "sha256:" + "g" * 64),
    ],
)
def test_repository_revision_id_rejects_invalid_identity_components(
    field: str,
    value: str,
) -> None:
    inputs = {
        "normalized_locator": "https://example.com/team/repository.git",
        "resolved_commit_sha": "0123456789abcdef0123456789abcdef01234567",
        "materializer_version": "future-materializer-v2",
        "submodule_policy": "future-submodule-policy-v2",
        "lfs_policy": "future-lfs-policy-v2",
        "authored_setup_identity": "sha256:" + "1" * 64,
    }
    inputs[field] = value

    with pytest.raises(ValueError):
        RepositoryRevisionId.build(**inputs)


def test_repository_revision_id_rejects_tampered_digest_on_direct_construction() -> None:
    inputs = {
        "normalized_locator": "https://example.com/team/repository.git",
        "resolved_commit_sha": "0123456789abcdef0123456789abcdef01234567",
        "materializer_version": "git-detached-clone-v1",
        "submodule_policy": "reject-v1",
        "lfs_policy": "reject-v1",
        "authored_setup_identity": "sha256:" + "1" * 64,
    }

    with pytest.raises(ValueError, match="does not match"):
        RepositoryRevisionId(digest="sha256:" + "f" * 64, **inputs)


@pytest.mark.parametrize(
    "argv0",
    [
        "setup",
        "./",
        ".//tools/setup",
        "./tools//setup",
        "./tools/./setup",
        "./tools/../setup",
        "././tools/setup",
        "./tools\\setup",
    ],
)
def test_setup_command_rejects_noncanonical_workspace_relative_argv0(
    argv0: str,
) -> None:
    with pytest.raises(ValueError, match="canonical workspace-relative"):
        SetupCommand(argv=(argv0,))


@pytest.mark.parametrize("argv0", ["/usr/bin/env", "./setup", "./tools/setup"])
def test_setup_command_accepts_absolute_and_canonical_workspace_relative_argv0(
    argv0: str,
) -> None:
    assert SetupCommand(argv=(argv0,)).argv == (argv0,)


@pytest.mark.parametrize(
    "env",
    [
        (("PWD", "authored"),),
        (("ORC_RUN_REF_SETUP_EVIDENCE_PATH", "authored"),),
        (("DUPLICATE", "first"), ("DUPLICATE", "second")),
        (("NOT-AN-ENV-NAME", "value"),),
        (("VALID", "contains\0nul"),),
    ],
)
def test_setup_command_rejects_invalid_or_runtime_owned_environment(
    env: tuple[tuple[str, str], ...],
) -> None:
    with pytest.raises(ValueError):
        SetupCommand(argv=("/bin/true",), env=env)


@pytest.mark.parametrize(
    "commands",
    [
        [SetupCommand(argv=("/bin/true",))],
        (object(),),
    ],
)
def test_setup_policy_requires_a_tuple_of_setup_commands(commands: object) -> None:
    with pytest.raises((TypeError, ValueError)):
        SetupPolicy(commands=commands)


def test_tree_compiler_and_baseline_are_separate_facts_from_repository_identity() -> None:
    identity = RepositoryRevisionId.build(
        normalized_locator="https://example.com/team/repository.git",
        resolved_commit_sha="0123456789abcdef0123456789abcdef01234567",
        materializer_version="git-detached-clone-v1",
        submodule_policy="reject-v1",
        lfs_policy="reject-v1",
        authored_setup_identity="sha256:" + "1" * 64,
    )

    tree = VerifiedGitTreeIdentity("git-tree:" + "2" * 40)
    compiler = VerifiedCompilerRuntimeIdentity("sha256:" + "3" * 64)
    baseline = PostSetupBaselineIdentity("sha256:" + "4" * 64)

    assert identity.components == {
        "normalized_locator": "https://example.com/team/repository.git",
        "resolved_commit_sha": "0123456789abcdef0123456789abcdef01234567",
        "materializer_version": "git-detached-clone-v1",
        "submodule_policy": "reject-v1",
        "lfs_policy": "reject-v1",
        "authored_setup_identity": "sha256:" + "1" * 64,
    }
    assert tree.value not in identity.components.values()
    assert compiler.digest not in identity.components.values()
    assert baseline.digest not in identity.components.values()


def _write_compiler_package(root: Path, *, module_body: str) -> None:
    (root / "data").mkdir(parents=True)
    (root / "__init__.py").write_text("VERSION = 1\n", encoding="utf-8")
    (root / "compiler.py").write_text(module_body, encoding="utf-8")
    (root / "data" / "stdlib.orc").write_text("(workflow)\n", encoding="utf-8")


def _compiler_identity(root: Path) -> VerifiedCompilerRuntimeIdentity:
    return compute_compiler_runtime_identity(
        package_root=root,
        python_implementation="cpython",
        python_major_minor=(3, 13),
        orchestrator_version="0.1.0",
        lowering_schema=2,
    )


def test_compiler_identity_changes_when_content_changes_at_the_same_path(
    tmp_path: Path,
) -> None:
    package = tmp_path / "orchestrator"
    _write_compiler_package(package, module_body="VALUE = 1\n")
    before = _compiler_identity(package)

    (package / "compiler.py").write_text("VALUE = 2\n", encoding="utf-8")

    assert _compiler_identity(package).digest != before.digest


def test_compiler_identity_is_independent_of_equal_package_root_paths(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first" / "orchestrator"
    second = tmp_path / "second" / "orchestrator"
    _write_compiler_package(first, module_body="VALUE = 1\n")
    _write_compiler_package(second, module_body="VALUE = 1\n")

    assert _compiler_identity(first) == _compiler_identity(second)


def test_compiler_identity_ignores_generated_bytecode_cache(tmp_path: Path) -> None:
    package = tmp_path / "orchestrator"
    _write_compiler_package(package, module_body="VALUE = 1\n")
    before = _compiler_identity(package)
    cache = package / "__pycache__"
    cache.mkdir()
    (cache / "compiler.cpython-313.pyc").write_bytes(b"generated")

    assert _compiler_identity(package) == before


def test_freeze_tree_is_complete_deterministic_and_root_independent(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root in (first, second):
        (root / "empty").mkdir(parents=True)
        (root / "nested").mkdir()
        (root / "nested" / "payload.txt").write_bytes(b"payload\n")
        os.symlink("nested/payload.txt", root / "payload-link")
        (root / "nested" / "payload.txt").chmod(0o640)
        (root / "empty").chmod(0o750)
        (root / "nested").chmod(0o755)

    manifest = freeze_tree(first)

    assert [entry.path for entry in manifest.entries] == [
        "empty",
        "nested",
        "nested/payload.txt",
        "payload-link",
    ]
    assert [(entry.path, entry.kind) for entry in manifest.entries] == [
        ("empty", "directory"),
        ("nested", "directory"),
        ("nested/payload.txt", "file"),
        ("payload-link", "symlink"),
    ]
    file_entry = next(entry for entry in manifest.entries if entry.kind == "file")
    link_entry = next(entry for entry in manifest.entries if entry.kind == "symlink")
    assert file_entry.mode == 0o640
    assert file_entry.size == len(b"payload\n")
    assert file_entry.sha256 == "sha256:" + hashlib.sha256(b"payload\n").hexdigest()
    assert link_entry.link_target == "nested/payload.txt"
    assert link_entry.sha256 == "sha256:" + hashlib.sha256(
        b"nested/payload.txt"
    ).hexdigest()
    assert freeze_tree(first) == manifest
    assert freeze_tree(second) == manifest


def test_freeze_tree_can_exclude_runtime_owned_roots(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "HEAD").write_text("ignored\n", encoding="utf-8")
    (root / ".orchestrate").mkdir()
    (root / ".orchestrate" / "evidence").write_text("ignored\n", encoding="utf-8")
    (root / "product.txt").write_text("kept\n", encoding="utf-8")

    manifest = freeze_tree(root, excluded_roots=(".git", ".orchestrate"))

    assert [entry.path for entry in manifest.entries] == ["product.txt"]


def test_freeze_tree_rejects_special_entries(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    os.mkfifo(root / "unsupported-fifo")

    with pytest.raises(WorkspaceFreezeError, match="unsupported-fifo"):
        freeze_tree(root)


def _git(
    repository: Path,
    *arguments: str,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _repository_with_two_commits(root: Path) -> tuple[str, str]:
    root.mkdir()
    subprocess.run(
        ["git", "init", "--quiet", str(root)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    _git(root, "config", "user.name", "Run Ref Test")
    _git(root, "config", "user.email", "run-ref@example.invalid")
    (root / "payload.txt").write_text("first\n", encoding="utf-8")
    _git(root, "add", "payload.txt")
    _git(root, "commit", "--quiet", "-m", "first")
    first = _git(root, "rev-parse", "HEAD").stdout.strip()
    (root / "payload.txt").write_text("second\n", encoding="utf-8")
    _git(root, "commit", "--quiet", "-am", "second")
    second = _git(root, "rev-parse", "HEAD").stdout.strip()
    return first, second


def _add_checkout_manifest_shapes(repository: Path) -> str:
    nested = repository / "nested"
    nested.mkdir()
    executable = nested / "tool"
    executable.write_bytes(b"#!/bin/sh\nexit 0\n")
    executable.chmod(0o755)
    os.symlink("nested/tool", repository / "tool-link")
    _git(repository, "add", "nested/tool", "tool-link")
    _git(repository, "commit", "--quiet", "-m", "add manifest shapes")
    return _git(repository, "rev-parse", "HEAD").stdout.strip()


def _tree_manifest_payload(manifest: TreeManifest) -> dict[str, object]:
    return {
        "schema_version": manifest.schema_version,
        "entries": [
            {
                "path": entry.path,
                "kind": entry.kind,
                "mode": entry.mode,
                "size": entry.size,
                "sha256": entry.sha256,
                "link_target": entry.link_target,
            }
            for entry in manifest.entries
        ],
        "digest": manifest.digest,
    }


def test_materialize_source_seals_bare_mirror_and_reuses_it_without_source_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = tmp_path / "origin"
    first_commit, second_commit = _repository_with_two_commits(origin)
    assert first_commit != second_commit
    expected_tree = _git(origin, "rev-parse", f"{first_commit}^{{tree}}").stdout.strip()
    request = SourceRequest(locator=str(origin), commit=first_commit)
    run_ref_root = tmp_path / "run-ref"
    calls: list[tuple[str, ...]] = []
    real_run_git = source_module._run_git

    def recording_run_git(
        argv: tuple[str, ...],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[object]:
        calls.append(argv)
        return real_run_git(argv, **kwargs)

    monkeypatch.setattr(source_module, "_run_git", recording_run_git)
    first_workspace = tmp_path / "first-workspace"

    first_result = materialize_source(
        request,
        run_ref_root=run_ref_root,
        workspace=first_workspace,
    )

    assert first_result.resolved_commit_sha == first_commit
    assert first_result.verified_git_tree.value == f"git-tree:{expected_tree}"
    assert first_result.workspace_path == first_workspace
    assert first_result.mirror_path.is_dir()
    assert first_result.mirror_seal_path.is_file()
    assert (
        subprocess.run(
            [
                "git",
                "--git-dir",
                str(first_result.mirror_path),
                "rev-parse",
                "--is-bare-repository",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        == "true"
    )
    assert (first_workspace / "payload.txt").read_text(encoding="utf-8") == "first\n"
    assert (first_workspace / ".git").is_dir()
    assert not (first_workspace / ".git").is_symlink()
    assert not (first_workspace / ".git" / "commondir").exists()
    assert not (first_workspace / ".git" / "objects" / "info" / "alternates").exists()
    assert _git(first_workspace, "rev-parse", "--git-dir").stdout.strip() == ".git"
    assert _git(first_workspace, "rev-parse", "--git-common-dir").stdout.strip() == ".git"
    assert _git(first_workspace, "rev-parse", "HEAD").stdout.strip() == first_commit
    assert _git(first_workspace, "symbolic-ref", "-q", "HEAD", check=False).returncode == 1
    assert first_result.source_tree_manifest == freeze_tree(
        first_workspace,
        excluded_roots=(".git",),
    )
    assert all("worktree" not in call for call in calls)

    seal_mtime_ns = first_result.mirror_seal_path.stat().st_mtime_ns
    shutil.rmtree(origin)
    calls.clear()
    second_workspace = tmp_path / "second-workspace"

    second_result = materialize_source(
        request,
        run_ref_root=run_ref_root,
        workspace=second_workspace,
    )

    assert second_result.mirror_path == first_result.mirror_path
    assert second_result.mirror_seal_path.stat().st_mtime_ns == seal_mtime_ns
    assert second_result.source_tree_manifest == first_result.source_tree_manifest
    assert (second_workspace / "payload.txt").read_text(encoding="utf-8") == "first\n"
    assert _git(second_workspace, "rev-parse", "HEAD").stdout.strip() == first_commit
    assert _git(second_workspace, "symbolic-ref", "-q", "HEAD", check=False).returncode == 1
    assert (second_workspace / ".git").is_dir()
    assert not (second_workspace / ".git" / "commondir").exists()
    assert not (second_workspace / ".git" / "objects" / "info" / "alternates").exists()
    assert all("worktree" not in call for call in calls)
    assert all(not any(verb in call for verb in ("fetch", "ls-remote", "pull")) for call in calls)
    assert all(origin.as_uri() not in call for call in calls)


def test_materialize_source_partitions_mirrors_by_source_not_setup_identity(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin"
    commit, _ = _repository_with_two_commits(origin)
    run_ref_root = tmp_path / "run-ref"
    first_request = SourceRequest(
        locator=str(origin),
        commit=commit,
        setup=SetupPolicy(
            commands=(
                SetupCommand(
                    argv=("/bin/true",),
                    env=(("RUN_REF_SETUP_MODE", "first"),),
                ),
            )
        ),
    )
    second_request = SourceRequest(
        locator=str(origin),
        commit=commit,
        setup=SetupPolicy(
            commands=(
                SetupCommand(
                    argv=("/bin/true",),
                    env=(("RUN_REF_SETUP_MODE", "second"),),
                ),
            )
        ),
    )

    first = materialize_source(
        first_request,
        run_ref_root=run_ref_root,
        workspace=tmp_path / "first-workspace",
    )
    seal_mtime_ns = first.mirror_seal_path.stat().st_mtime_ns
    shutil.rmtree(origin)
    second = materialize_source(
        second_request,
        run_ref_root=run_ref_root,
        workspace=tmp_path / "second-workspace",
    )

    assert first.repository_revision_id.digest != second.repository_revision_id.digest
    assert (
        first.repository_revision_id.authored_setup_identity
        != second.repository_revision_id.authored_setup_identity
    )
    assert first.mirror_path == second.mirror_path
    assert first.mirror_seal_path == second.mirror_seal_path
    assert second.mirror_seal_path.stat().st_mtime_ns == seal_mtime_ns
    seal = json.loads(second.mirror_seal_path.read_text(encoding="utf-8"))
    assert seal["normalized_locator"] == first.normalized_locator
    assert seal["resolved_commit_sha"] == commit
    assert "repository_revision" not in seal
    assert "repository_revision_digest" not in seal
    assert "authored_setup_identity" not in json.dumps(seal, sort_keys=True)


@pytest.mark.parametrize("gitmodules_path", [".gitmodules", "nested/.gitmodules"])
def test_materialize_source_rejects_committed_gitmodules_before_sealing(
    tmp_path: Path,
    gitmodules_path: str,
) -> None:
    origin = tmp_path / "origin"
    _repository_with_two_commits(origin)
    path = origin / gitmodules_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[submodule \"dependency\"]\n", encoding="utf-8")
    _git(origin, "add", gitmodules_path)
    _git(origin, "commit", "--quiet", "-m", "add gitmodules")
    commit = _git(origin, "rev-parse", "HEAD").stdout.strip()
    run_ref_root = tmp_path / "run-ref"
    workspace = tmp_path / "workspace"

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(locator=str(origin), commit=commit),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_source_submodules_unsupported"
    assert caught.value.rejected_value == gitmodules_path
    assert not workspace.exists()
    assert list(run_ref_root.rglob("run-ref-seal.json")) == []


def test_materialize_source_rejects_gitlink_before_sealing(tmp_path: Path) -> None:
    origin = tmp_path / "origin"
    target_commit, _ = _repository_with_two_commits(origin)
    _git(
        origin,
        "update-index",
        "--add",
        "--cacheinfo",
        f"160000,{target_commit},vendor/dependency",
    )
    _git(origin, "commit", "--quiet", "-m", "add gitlink")
    commit = _git(origin, "rev-parse", "HEAD").stdout.strip()
    run_ref_root = tmp_path / "run-ref"
    workspace = tmp_path / "workspace"

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(locator=str(origin), commit=commit),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_source_submodules_unsupported"
    assert caught.value.rejected_value == "vendor/dependency"
    assert not workspace.exists()
    assert list(run_ref_root.rglob("run-ref-seal.json")) == []


def test_materialize_source_rejects_committed_lfs_filter_before_sealing(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin"
    _repository_with_two_commits(origin)
    attributes = origin / "nested" / ".gitattributes"
    attributes.parent.mkdir()
    attributes.write_text(
        "# filter=lfs in a comment is inert\n*.bin filter=lfs diff=lfs merge=lfs -text\n",
        encoding="utf-8",
    )
    _git(origin, "add", "nested/.gitattributes")
    _git(origin, "commit", "--quiet", "-m", "add lfs attributes")
    commit = _git(origin, "rev-parse", "HEAD").stdout.strip()
    run_ref_root = tmp_path / "run-ref"
    workspace = tmp_path / "workspace"

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(locator=str(origin), commit=commit),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_source_lfs_unsupported"
    assert caught.value.rejected_value == "nested/.gitattributes"
    assert not workspace.exists()
    assert list(run_ref_root.rglob("run-ref-seal.json")) == []


def test_materialize_source_seals_the_exact_git_object_checkout_manifest(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin"
    _repository_with_two_commits(origin)
    commit = _add_checkout_manifest_shapes(origin)

    result = materialize_source(
        SourceRequest(locator=str(origin), commit=commit),
        run_ref_root=tmp_path / "run-ref",
        workspace=tmp_path / "workspace",
    )

    seal = json.loads(result.mirror_seal_path.read_text(encoding="utf-8"))
    assert seal["expected_checkout_tree_manifest"] == _tree_manifest_payload(
        result.source_tree_manifest
    )
    assert [
        (entry.path, entry.kind, entry.mode)
        for entry in result.source_tree_manifest.entries
    ] == [
        ("nested", "directory", 0o755),
        ("nested/tool", "file", 0o755),
        ("payload.txt", "file", 0o644),
        ("tool-link", "symlink", 0o777),
    ]


@pytest.mark.parametrize(
    "mutation_kind",
    ["file_bytes", "file_mode", "directory_mode", "symlink_target"],
)
def test_materialize_source_rejects_and_cleans_checkout_manifest_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation_kind: str,
) -> None:
    origin = tmp_path / "origin"
    _repository_with_two_commits(origin)
    commit = _add_checkout_manifest_shapes(origin)
    workspace = tmp_path / "workspace"
    real_normalize_checkout_modes = source_module._normalize_checkout_modes
    mutated = False

    def mutate_after_mode_normalization(
        workspace_path: Path,
        expected_manifest: TreeManifest,
    ) -> None:
        nonlocal mutated
        real_normalize_checkout_modes(workspace_path, expected_manifest)
        if not mutated:
            mutated = True
            if mutation_kind == "file_bytes":
                (workspace_path / "payload.txt").write_text(
                    "tampered\n",
                    encoding="utf-8",
                )
            elif mutation_kind == "file_mode":
                (workspace_path / "nested" / "tool").chmod(0o700)
            elif mutation_kind == "directory_mode":
                (workspace_path / "nested").chmod(0o700)
            else:
                (workspace_path / "tool-link").unlink()
                os.symlink("payload.txt", workspace_path / "tool-link")

    monkeypatch.setattr(
        source_module,
        "_normalize_checkout_modes",
        mutate_after_mode_normalization,
    )

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(locator=str(origin), commit=commit),
            run_ref_root=tmp_path / "run-ref",
            workspace=workspace,
        )

    assert mutated is True
    assert caught.value.code == "trial_materialization_digest_mismatch"
    assert not workspace.exists()
    assert len(list((tmp_path / "run-ref").rglob("run-ref-seal.json"))) == 1


def test_materialize_source_runs_ordered_setup_with_closed_env_and_external_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = tmp_path / "origin"
    commit, _ = _repository_with_two_commits(origin)
    workspace = tmp_path / "workspace"
    run_ref_root = tmp_path / "run-ref"
    first_code = (
        "import os,pathlib,sys; "
        "pathlib.Path('order.txt').write_text('first:' + os.environ['DECLARED'] + '\\n'); "
        "print('first stdout'); print('first stderr', file=sys.stderr)"
    )
    second_code = (
        "import os,pathlib,sys; "
        "p=pathlib.Path('order.txt'); p.write_text(p.read_text() + 'second:' + "
        "str('RUN_REF_AMBIENT_SECRET' in os.environ) + '\\n'); "
        "pathlib.Path('.orchestrate').mkdir(); "
        "pathlib.Path('.orchestrate/setup-private').write_text('excluded\\n'); "
        "pathlib.Path('runtime-env.txt').write_text(os.environ['PWD'] + '\\n' + "
        "os.environ['ORC_RUN_REF_SETUP_EVIDENCE_PATH'] + '\\n'); "
        "print('second stdout'); print('second stderr', file=sys.stderr)"
    )
    request = SourceRequest(
        locator=str(origin),
        commit=commit,
        setup=SetupPolicy(
            commands=(
                SetupCommand(
                    argv=(sys.executable, "-c", first_code),
                    env=(("DECLARED", "literal"),),
                ),
                SetupCommand(
                    argv=(sys.executable, "-c", second_code),
                    env=(("DECLARED", "literal"),),
                ),
            )
        ),
    )
    monkeypatch.setenv("RUN_REF_AMBIENT_SECRET", "must-not-leak")
    real_subprocess_run = source_module.subprocess.run
    setup_calls: list[dict[str, object]] = []

    def recording_subprocess_run(*args: object, **kwargs: object):
        argv = args[0]
        if isinstance(argv, tuple) and argv and argv[0] == sys.executable:
            setup_calls.append(dict(kwargs))
        return real_subprocess_run(*args, **kwargs)

    monkeypatch.setattr(source_module.subprocess, "run", recording_subprocess_run)

    result = materialize_source(
        request,
        run_ref_root=run_ref_root,
        workspace=workspace,
    )

    assert (workspace / "order.txt").read_text(encoding="utf-8") == (
        "first:literal\nsecond:False\n"
    )
    assert len(setup_calls) == 2
    for call in setup_calls:
        assert call["shell"] is False
        assert call["cwd"] == workspace
        assert set(call["env"]) == {
            "DECLARED",
            "PWD",
            "ORC_RUN_REF_SETUP_EVIDENCE_PATH",
        }
    assert result.setup_evidence_path.is_file()
    assert not result.setup_evidence_path.is_relative_to(workspace)
    evidence = json.loads(result.setup_evidence_path.read_text(encoding="utf-8"))
    assert evidence["status"] == "passed"
    assert [row["exit_code"] for row in evidence["commands"]] == [0, 0]
    assert [row["stdout_size"] for row in evidence["commands"]] == [13, 14]
    assert [row["stderr_size"] for row in evidence["commands"]] == [13, 14]
    assert result.setup_evidence_digest == _canonical_digest(evidence)
    assert result.post_setup_tree_manifest == freeze_tree(
        workspace,
        excluded_roots=(".git", ".orchestrate"),
    )
    assert result.post_setup_baseline_identity == PostSetupBaselineIdentity(
        result.post_setup_tree_manifest.digest
    )
    assert ".orchestrate" not in {
        entry.path for entry in result.post_setup_tree_manifest.entries
    }


def test_materialize_source_preserves_canonical_evidence_and_mirror_on_setup_exit(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin"
    commit, _ = _repository_with_two_commits(origin)
    workspace = tmp_path / "workspace"
    run_ref_root = tmp_path / "run-ref"
    setup_code = (
        "import sys; "
        "print('failed stdout'); "
        "print('failed stderr', file=sys.stderr); "
        "raise SystemExit(7)"
    )

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(
                locator=str(origin),
                commit=commit,
                setup=SetupPolicy(
                    commands=(
                        SetupCommand(argv=(sys.executable, "-c", setup_code)),
                    )
                ),
            ),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_setup_failed"
    assert caught.value.rejected_value == [sys.executable, "-c", setup_code]
    assert not workspace.exists()
    assert len(list(run_ref_root.rglob("run-ref-seal.json"))) == 1
    evidence_paths = list((run_ref_root / "setup-evidence").rglob("*.json"))
    assert len(evidence_paths) == 1
    evidence_path = evidence_paths[0]
    assert not evidence_path.is_relative_to(workspace)
    raw_evidence = evidence_path.read_bytes()
    evidence = json.loads(raw_evidence)
    assert raw_evidence == (
        json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert evidence["status"] == "failed"
    assert len(evidence["commands"]) == 1
    assert evidence["commands"][0]["exit_code"] == 7
    assert evidence["commands"][0]["launch_error"] is None
    assert evidence["commands"][0]["stdout_size"] == len(b"failed stdout\n")
    assert evidence["commands"][0]["stderr_size"] == len(b"failed stderr\n")


def test_materialize_source_preserves_canonical_evidence_and_mirror_on_setup_launch_failure(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin"
    commit, _ = _repository_with_two_commits(origin)
    workspace = tmp_path / "workspace"
    run_ref_root = tmp_path / "run-ref"
    missing_executable = tmp_path / "missing-setup-executable"

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(
                locator=str(origin),
                commit=commit,
                setup=SetupPolicy(
                    commands=(SetupCommand(argv=(str(missing_executable),)),)
                ),
            ),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_setup_failed"
    assert caught.value.rejected_value == [str(missing_executable)]
    assert not workspace.exists()
    assert len(list(run_ref_root.rglob("run-ref-seal.json"))) == 1
    evidence_paths = list((run_ref_root / "setup-evidence").rglob("*.json"))
    assert len(evidence_paths) == 1
    evidence_path = evidence_paths[0]
    assert not evidence_path.is_relative_to(workspace)
    raw_evidence = evidence_path.read_bytes()
    evidence = json.loads(raw_evidence)
    assert raw_evidence == (
        json.dumps(
            evidence,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )
    assert evidence["status"] == "failed"
    assert len(evidence["commands"]) == 1
    assert evidence["commands"][0]["exit_code"] is None
    assert evidence["commands"][0]["stdout_size"] == 0
    assert evidence["commands"][0]["stderr_size"] == 0
    assert evidence["commands"][0]["launch_error"] == {
        "errno": 2,
        "kind": "FileNotFoundError",
    }


def test_materialize_source_closes_post_setup_special_entry_freeze_failure(
    tmp_path: Path,
) -> None:
    origin = tmp_path / "origin"
    commit, _ = _repository_with_two_commits(origin)
    workspace = tmp_path / "workspace"
    run_ref_root = tmp_path / "run-ref"
    setup_code = "import os; os.mkfifo('setup-created-fifo')"

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(
                locator=str(origin),
                commit=commit,
                setup=SetupPolicy(
                    commands=(
                        SetupCommand(argv=(sys.executable, "-c", setup_code)),
                    )
                ),
            ),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_materialization_digest_mismatch"
    assert caught.value.rejected_value == str(workspace)
    assert not workspace.exists()
    assert len(list(run_ref_root.rglob("run-ref-seal.json"))) == 1
    evidence_paths = list((run_ref_root / "setup-evidence").rglob("*.json"))
    assert len(evidence_paths) == 1
    evidence = json.loads(evidence_paths[0].read_text(encoding="utf-8"))
    assert evidence["status"] == "passed"
    assert evidence["commands"][0]["exit_code"] == 0


def test_setup_observations_do_not_change_revision_or_equal_workspace_baseline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = tmp_path / "origin"
    commit, _ = _repository_with_two_commits(origin)
    run_ref_root = tmp_path / "run-ref"
    setup_code = "import pathlib; print(pathlib.Path.cwd().name)"
    request = SourceRequest(
        locator=str(origin),
        commit=commit,
        setup=SetupPolicy(
            commands=(SetupCommand(argv=(sys.executable, "-c", setup_code)),)
        ),
    )
    timestamps = iter((0, 1_000_000, 10_000_000, 19_000_000))
    monkeypatch.setattr(source_module.time, "monotonic_ns", lambda: next(timestamps))

    first = materialize_source(
        request,
        run_ref_root=run_ref_root,
        workspace=tmp_path / "first-workspace",
    )
    second = materialize_source(
        request,
        run_ref_root=run_ref_root,
        workspace=tmp_path / "second-workspace",
    )

    first_evidence = json.loads(first.setup_evidence_path.read_text(encoding="utf-8"))
    second_evidence = json.loads(second.setup_evidence_path.read_text(encoding="utf-8"))
    assert first_evidence["commands"][0]["stdout_sha256"] != (
        second_evidence["commands"][0]["stdout_sha256"]
    )
    assert first_evidence["commands"][0]["duration_ms"] == 1
    assert second_evidence["commands"][0]["duration_ms"] == 9
    assert first.setup_evidence_digest != second.setup_evidence_digest
    assert first.repository_revision_id == second.repository_revision_id
    assert first.post_setup_tree_manifest == second.post_setup_tree_manifest
    assert first.post_setup_baseline_identity == second.post_setup_baseline_identity


def test_materialize_source_refuses_a_preexisting_workspace_before_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = tmp_path / "origin"
    commit, _ = _repository_with_two_commits(origin)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    marker = workspace / "belongs-to-caller"
    marker.write_text("preserve\n", encoding="utf-8")
    calls: list[tuple[str, ...]] = []
    real_run_git = source_module._run_git

    def recording_run_git(
        argv: tuple[str, ...],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[object]:
        calls.append(argv)
        return real_run_git(argv, **kwargs)

    monkeypatch.setattr(source_module, "_run_git", recording_run_git)

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(locator=str(origin), commit=commit),
            run_ref_root=tmp_path / "run-ref",
            workspace=workspace,
        )

    assert caught.value.code == "trial_workspace_preexisting"
    assert caught.value.rejected_value == str(workspace)
    assert marker.read_text(encoding="utf-8") == "preserve\n"
    assert calls == []


@pytest.mark.parametrize(
    "noncanonical_input",
    [
        "relative-workspace",
        "absolute-workspace-with-parent-segment",
        "relative-run-ref-root",
        "absolute-run-ref-root-with-parent-segment",
    ],
)
def test_materialize_source_rejects_noncanonical_local_paths_before_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    noncanonical_input: str,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace: Path = tmp_path / "workspace"
    run_ref_root: Path = tmp_path / "run-ref"
    if noncanonical_input == "relative-workspace":
        workspace = Path("workspace")
    elif noncanonical_input == "absolute-workspace-with-parent-segment":
        workspace = tmp_path / "unused" / ".." / "workspace"
    elif noncanonical_input == "relative-run-ref-root":
        run_ref_root = Path("run-ref")
    else:
        run_ref_root = tmp_path / "unused" / ".." / "run-ref"
    calls: list[tuple[str, ...]] = []

    def recording_run_git(
        argv: tuple[str, ...],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[object]:
        calls.append(argv)
        raise AssertionError("Git must not run for a noncanonical local path")

    monkeypatch.setattr(source_module, "_run_git", recording_run_git)

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(
                locator=str(tmp_path / "origin"),
                commit="0" * 40,
            ),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_materialization_digest_mismatch"
    if noncanonical_input.startswith("relative-workspace") or noncanonical_input.startswith(
        "absolute-workspace"
    ):
        assert caught.value.rejected_value == str(workspace)
    else:
        assert caught.value.rejected_value == str(run_ref_root)
    assert calls == []


def test_preexisting_workspace_refusal_precedes_local_path_validation_and_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    workspace = Path("workspace")
    workspace.mkdir()
    calls: list[tuple[str, ...]] = []

    def recording_run_git(
        argv: tuple[str, ...],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[object]:
        calls.append(argv)
        raise AssertionError("Git must not run for a preexisting workspace")

    monkeypatch.setattr(source_module, "_run_git", recording_run_git)

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(
                locator=str(tmp_path / "origin"),
                commit="0" * 40,
            ),
            run_ref_root=Path("relative-run-ref-root"),
            workspace=workspace,
        )

    assert caught.value.code == "trial_workspace_preexisting"
    assert caught.value.rejected_value == str(workspace)
    assert calls == []


def test_materialize_source_closes_existing_run_ref_root_file_before_workspace(
    tmp_path: Path,
) -> None:
    run_ref_root = tmp_path / "run-ref"
    run_ref_root.write_text("caller-owned file\n", encoding="utf-8")
    workspace = tmp_path / "workspace"

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(
                locator=str(tmp_path / "origin"),
                commit="0" * 40,
            ),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_materialization_digest_mismatch"
    assert caught.value.rejected_value == str(run_ref_root)
    assert run_ref_root.read_text(encoding="utf-8") == "caller-owned file\n"
    assert not workspace.exists()


def test_materialize_source_closes_existing_workspace_parent_file_before_git(
    tmp_path: Path,
) -> None:
    workspace_parent = tmp_path / "workspace-parent"
    workspace_parent.write_text("caller-owned file\n", encoding="utf-8")
    workspace = workspace_parent / "workspace"
    run_ref_root = tmp_path / "run-ref"

    with pytest.raises(RunRefSourceRefusal) as caught:
        materialize_source(
            SourceRequest(
                locator=str(tmp_path / "origin"),
                commit="0" * 40,
            ),
            run_ref_root=run_ref_root,
            workspace=workspace,
        )

    assert caught.value.code == "trial_materialization_digest_mismatch"
    assert caught.value.rejected_value == str(workspace_parent)
    assert workspace_parent.read_text(encoding="utf-8") == "caller-owned file\n"
    assert not workspace.exists()
    assert not run_ref_root.exists()
