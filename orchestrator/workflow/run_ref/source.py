from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote, unquote_to_bytes, urlsplit, urlunsplit

from orchestrator._common.io_atomic import durable_atomic_write

from .contracts import (
    PostSetupBaselineIdentity,
    RepositoryRevisionId,
    RunRefSourceRefusal,
    SetupPolicy,
    VerifiedGitTreeIdentity,
    authored_setup_identity,
    canonical_json_bytes,
    canonical_sha256,
)
from .workspace import (
    TreeEntry,
    TreeManifest,
    WorkspaceFreezeError,
    freeze_tree,
    manifest_from_entries,
)


_COMMIT_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SOURCE_SCHEMA = "run_ref_source.v1"
_MATERIALIZER_VERSION = "git-detached-clone-v1"
_SUBMODULE_POLICY = "reject-v1"
_LFS_POLICY = "reject-v1"
_MIRROR_SEAL_SCHEMA = "run_ref_mirror_seal.v1"
_MIRROR_SEAL_FILENAME = "run-ref-seal.json"
_SEALED_BRANCH = "refs/heads/run-ref-sealed"


@dataclass(frozen=True)
class SourceRequest:
    """One exact repository revision requested by a run-reference effect."""

    locator: str
    commit: str
    materializer_version: str = _MATERIALIZER_VERSION
    submodule_policy: str = _SUBMODULE_POLICY
    lfs_policy: str = _LFS_POLICY
    setup: SetupPolicy = SetupPolicy()


@dataclass(frozen=True)
class MaterializedSource:
    """Verified source facts and the independent detached clone they produced."""

    repository_revision_id: RepositoryRevisionId
    normalized_locator: str
    resolved_commit_sha: str
    verified_git_tree: VerifiedGitTreeIdentity
    mirror_path: Path
    mirror_seal_path: Path
    workspace_path: Path
    source_tree_manifest: TreeManifest
    setup_evidence_path: Path
    setup_evidence_digest: str
    post_setup_tree_manifest: TreeManifest
    post_setup_baseline_identity: PostSetupBaselineIdentity


@dataclass(frozen=True)
class _MirrorSourceIdentity:
    digest: str
    normalized_locator: str
    resolved_commit_sha: str
    materializer_version: str
    submodule_policy: str
    lfs_policy: str

    @property
    def components(self) -> dict[str, str]:
        return {
            "normalized_locator": self.normalized_locator,
            "resolved_commit_sha": self.resolved_commit_sha,
            "materializer_version": self.materializer_version,
            "submodule_policy": self.submodule_policy,
            "lfs_policy": self.lfs_policy,
        }


@dataclass(frozen=True)
class _GitTreeObject:
    mode: str
    object_type: str
    object_id: str
    path: str


def _refuse_unresolvable(locator: object, detail: str) -> RunRefSourceRefusal:
    return RunRefSourceRefusal(
        "trial_source_unresolvable",
        locator,
        f"repository locator is not a canonical supported locator: {detail}",
    )


def _decode_uri_path(locator: str, encoded_path: str) -> str:
    lowered_path = encoded_path.lower()
    if "%2f" in lowered_path or "%5c" in lowered_path:
        raise _refuse_unresolvable(locator, "encoded path separators are forbidden")
    try:
        decoded_path = unquote_to_bytes(encoded_path).decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise _refuse_unresolvable(
            locator,
            "URI path percent encoding is not valid UTF-8",
        ) from exc
    if "\\" in decoded_path:
        raise _refuse_unresolvable(
            locator,
            "backslashes are not canonical URI path separators",
        )
    return decoded_path


def normalize_repository_locator(locator: str) -> str:
    """Return the canonical locator used by RepositoryRevisionId v1."""

    if not isinstance(locator, str) or not locator or "\0" in locator:
        raise _refuse_unresolvable(locator, "expected a non-empty NUL-free string")

    if os.path.isabs(locator):
        return Path(locator).resolve(strict=False).as_uri()

    try:
        parsed = urlsplit(locator)
    except ValueError as exc:
        raise _refuse_unresolvable(locator, "URI syntax is malformed") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"file", "https", "ssh"}:
        raise _refuse_unresolvable(
            locator,
            "only absolute paths and file/https/ssh URIs are supported",
        )
    if parsed.query or parsed.fragment:
        raise _refuse_unresolvable(locator, "query strings and fragments are not identity-safe")
    if parsed.username is not None or parsed.password is not None:
        raise _refuse_unresolvable(locator, "URI userinfo is forbidden")

    if scheme == "file":
        if parsed.netloc:
            raise _refuse_unresolvable(locator, "file URIs must not have an authority")
        decoded_path = _decode_uri_path(locator, parsed.path)
        if not os.path.isabs(decoded_path) or "\0" in decoded_path:
            raise _refuse_unresolvable(locator, "file URI path must be absolute")
        return Path(decoded_path).resolve(strict=False).as_uri()

    try:
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise _refuse_unresolvable(locator, str(exc)) from exc
    if not hostname or not parsed.path.startswith("/") or parsed.path == "/":
        raise _refuse_unresolvable(
            locator,
            "network URI requires a host and absolute repository path",
        )
    decoded_path = _decode_uri_path(locator, parsed.path)
    canonical_path_text = decoded_path.rstrip("/")
    decoded_segments = canonical_path_text.split("/")
    if (
        "\0" in decoded_path
        or not canonical_path_text
        or decoded_segments[0] != ""
        or any(
            segment in {"", ".", ".."}
            for segment in decoded_segments[1:]
        )
    ):
        raise _refuse_unresolvable(
            locator,
            "network URI path must have one leading slash and no empty, dot, "
            "parent, or NUL segment",
        )

    canonical_path = quote(canonical_path_text, safe="/")
    default_port = 443 if scheme == "https" else 22
    canonical_hostname = hostname.lower()
    canonical_authority = (
        f"[{canonical_hostname}]" if ":" in canonical_hostname else canonical_hostname
    )
    if port is not None and port != default_port:
        canonical_authority = f"{canonical_authority}:{port}"
    return urlunsplit((scheme, canonical_authority, canonical_path, "", ""))


def validate_commit_sha(commit: str) -> str:
    if not isinstance(commit, str) or _COMMIT_SHA_RE.fullmatch(commit) is None:
        raise RunRefSourceRefusal(
            "trial_source_revision_digest_mismatch",
            commit,
            "commit must be exactly 40 lowercase hexadecimal characters",
        )
    return commit


def _run_git(
    argv: tuple[str, ...],
    *,
    check: bool = True,
    text: bool = True,
) -> subprocess.CompletedProcess[Any]:
    """Run one argument-bounded Git command for the materializer."""

    return subprocess.run(
        argv,
        check=check,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
    )


def _git_stdout(argv: tuple[str, ...]) -> str:
    stdout = _run_git(argv).stdout
    if not isinstance(stdout, str):
        raise TypeError("text Git command returned non-text stdout")
    return stdout.strip()


def _git_bytes(argv: tuple[str, ...]) -> bytes:
    stdout = _run_git(argv, text=False).stdout
    if not isinstance(stdout, bytes):
        raise TypeError("binary Git command returned non-bytes stdout")
    return stdout


def _discard_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _materialization_refusal(
    rejected_value: object,
    detail: str,
) -> RunRefSourceRefusal:
    return RunRefSourceRefusal(
        "trial_materialization_digest_mismatch",
        rejected_value,
        detail,
    )


def canonical_source_request(request: SourceRequest) -> dict[str, object]:
    """Return the closed canonical v1 source-request record."""

    fixed_policy_values = (
        ("materializer_version", request.materializer_version, _MATERIALIZER_VERSION),
        ("submodule_policy", request.submodule_policy, _SUBMODULE_POLICY),
        ("lfs_policy", request.lfs_policy, _LFS_POLICY),
    )
    for field, actual, expected in fixed_policy_values:
        if actual != expected:
            raise _materialization_refusal(
                actual,
                f"source request {field} is not the implemented v1 value",
            )
    if not isinstance(request.setup, SetupPolicy):
        raise _materialization_refusal(
            request.setup,
            "source request setup must be a SetupPolicy",
        )

    normalized_locator = normalize_repository_locator(request.locator)
    resolved_commit = validate_commit_sha(request.commit)
    authored_setup = {
        "commands": [
            {
                "argv": list(command.argv),
                "env": [[name, value] for name, value in command.env],
            }
            for command in request.setup.commands
        ]
    }
    return {
        "schema_version": _SOURCE_SCHEMA,
        "normalized_locator": normalized_locator,
        "resolved_commit_sha": resolved_commit,
        "materializer_version": request.materializer_version,
        "submodule_policy": request.submodule_policy,
        "lfs_policy": request.lfs_policy,
        "authored_setup": authored_setup,
        "authored_setup_identity": authored_setup_identity(request.setup),
    }


def canonical_repository_revision_result(
    revision: RepositoryRevisionId,
) -> dict[str, object]:
    """Return the closed canonical repository-revision identity result."""

    try:
        canonical_locator = normalize_repository_locator(
            revision.normalized_locator
        )
    except RunRefSourceRefusal as exc:
        raise _materialization_refusal(
            revision.normalized_locator,
            "repository revision locator is not canonical",
        ) from exc
    if canonical_locator != revision.normalized_locator:
        raise _materialization_refusal(
            revision.normalized_locator,
            "repository revision locator is not in canonical byte form",
        )
    return {
        "schema_version": "run_ref_repository_revision.v1",
        "digest": revision.digest,
        **revision.components,
    }


def _canonical_absolute_local_path(path: Path, *, label: str) -> Path:
    candidate = Path(path)
    try:
        resolved = candidate.resolve(strict=False)
    except OSError as exc:
        raise _materialization_refusal(
            str(candidate),
            f"{label} cannot be normalized as a canonical absolute path",
        ) from exc
    if not candidate.is_absolute() or candidate != resolved:
        raise _materialization_refusal(
            str(candidate),
            f"{label} must be a canonical absolute path",
        )
    return candidate


def _require_directory_or_absent(path: Path, *, label: str) -> None:
    if not os.path.lexists(path):
        return
    try:
        identity = path.lstat()
    except OSError as exc:
        raise _materialization_refusal(
            str(path),
            f"{label} cannot be inspected",
        ) from exc
    if not stat.S_ISDIR(identity.st_mode):
        raise _materialization_refusal(
            str(path),
            f"{label} must be a directory or absent",
        )


def _source_policy_refusal(
    code: str,
    path: str,
    detail: str,
) -> RunRefSourceRefusal:
    return RunRefSourceRefusal(code, path, detail)


def _git_tree_objects(
    git_dir: Path,
    commit: str,
) -> tuple[_GitTreeObject, ...]:
    raw = _git_bytes(
        (
            "git",
            "--git-dir",
            str(git_dir),
            "ls-tree",
            "-rz",
            "-r",
            "-t",
            commit,
        )
    )
    objects: list[_GitTreeObject] = []
    for record in raw.split(b"\0"):
        if not record:
            continue
        try:
            header, path_bytes = record.split(b"\t", 1)
            mode_bytes, object_type_bytes, object_id_bytes = header.split(b" ", 2)
            path = path_bytes.decode("utf-8", errors="strict")
            mode = mode_bytes.decode("ascii", errors="strict")
            object_type = object_type_bytes.decode("ascii", errors="strict")
            object_id = object_id_bytes.decode("ascii", errors="strict")
        except (UnicodeDecodeError, ValueError) as exc:
            raise _materialization_refusal(
                commit,
                "Git tree contains an entry that is not canonically decodable",
            ) from exc
        objects.append(
            _GitTreeObject(
                mode=mode,
                object_type=object_type,
                object_id=object_id,
                path=path,
            )
        )
    return tuple(objects)


def _blob_bytes(git_dir: Path, object_id: str) -> bytes:
    return _git_bytes(
        (
            "git",
            "--git-dir",
            str(git_dir),
            "cat-file",
            "blob",
            object_id,
        )
    )


def _attributes_enable_lfs(payload: bytes) -> bool:
    for raw_line in payload.splitlines():
        line = raw_line.strip()
        if not line or line.startswith(b"#"):
            continue
        if b"filter=lfs" in line.split():
            return True
    return False


def _validate_source_policy(git_dir: Path, commit: str) -> None:
    for entry in _git_tree_objects(git_dir, commit):
        leaf_name = PurePosixPath(entry.path).name
        if leaf_name == ".gitmodules":
            raise _source_policy_refusal(
                "trial_source_submodules_unsupported",
                entry.path,
                "committed .gitmodules files are unsupported",
            )
        if entry.mode == "160000" or entry.object_type == "commit":
            raise _source_policy_refusal(
                "trial_source_submodules_unsupported",
                entry.path,
                "committed Git links are unsupported",
            )
        if leaf_name == ".gitattributes" and _attributes_enable_lfs(
            _blob_bytes(git_dir, entry.object_id)
        ):
            raise _source_policy_refusal(
                "trial_source_lfs_unsupported",
                entry.path,
                "committed Git attributes enable the unsupported LFS filter",
            )


def _expected_checkout_tree_manifest(
    git_dir: Path,
    commit: str,
) -> TreeManifest:
    entries: list[TreeEntry] = []
    for entry in _git_tree_objects(git_dir, commit):
        if entry.mode == "040000" and entry.object_type == "tree":
            entries.append(
                TreeEntry(
                    path=entry.path,
                    kind="directory",
                    mode=0o755,
                    size=0,
                    sha256=None,
                )
            )
            continue
        if entry.mode in {"100644", "100755"} and entry.object_type == "blob":
            payload = _blob_bytes(git_dir, entry.object_id)
            entries.append(
                TreeEntry(
                    path=entry.path,
                    kind="file",
                    mode=0o755 if entry.mode == "100755" else 0o644,
                    size=len(payload),
                    sha256=f"sha256:{hashlib.sha256(payload).hexdigest()}",
                )
            )
            continue
        if entry.mode == "120000" and entry.object_type == "blob":
            target_bytes = _blob_bytes(git_dir, entry.object_id)
            try:
                target = target_bytes.decode("utf-8", errors="strict")
            except UnicodeDecodeError as exc:
                raise _materialization_refusal(
                    entry.path,
                    "Git symlink target is not canonical UTF-8 text",
                ) from exc
            entries.append(
                TreeEntry(
                    path=entry.path,
                    kind="symlink",
                    mode=0o777,
                    size=len(target_bytes),
                    sha256=f"sha256:{hashlib.sha256(target_bytes).hexdigest()}",
                    link_target=target,
                )
            )
            continue
        raise _materialization_refusal(
            entry.path,
            f"Git tree entry has unsupported mode/type {entry.mode}/{entry.object_type}",
        )
    return manifest_from_entries(entries)


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


def _normalize_checkout_modes(
    workspace: Path,
    expected_manifest: TreeManifest,
) -> None:
    """Remove ambient-umask variance from Git-represented file and dir modes."""

    for entry in expected_manifest.entries:
        if entry.kind == "symlink":
            continue
        try:
            os.chmod(workspace / entry.path, entry.mode, follow_symlinks=False)
        except OSError as exc:
            raise _materialization_refusal(
                entry.path,
                "could not normalize checkout mode to the sealed Git object mode",
            ) from exc


def _sha256_bytes(payload: bytes) -> str:
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _setup_evidence_path(
    *,
    run_ref_root: Path,
    revision: RepositoryRevisionId,
    workspace: Path,
) -> Path:
    workspace_attempt = canonical_sha256(
        {"workspace_path": str(workspace.resolve(strict=False))}
    ).removeprefix("sha256:")
    return (
        run_ref_root
        / "setup-evidence"
        / revision.digest.removeprefix("sha256:")
        / f"{workspace_attempt}.json"
    )


def _setup_command_evidence(
    *,
    ordinal: int,
    command: object,
    exit_code: int | None,
    duration_ms: int,
    stdout: bytes,
    stderr: bytes,
    launch_error: dict[str, object] | None,
) -> dict[str, object]:
    argv = tuple(getattr(command, "argv"))
    declared_env = tuple(getattr(command, "env"))
    return {
        "ordinal": ordinal,
        "argv": list(argv),
        "declared_env": [[name, value] for name, value in declared_env],
        "runtime_env_names": ["ORC_RUN_REF_SETUP_EVIDENCE_PATH", "PWD"],
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "stdout_size": len(stdout),
        "stdout_sha256": _sha256_bytes(stdout),
        "stdout_base64": base64.b64encode(stdout).decode("ascii"),
        "stderr_size": len(stderr),
        "stderr_sha256": _sha256_bytes(stderr),
        "stderr_base64": base64.b64encode(stderr).decode("ascii"),
        "launch_error": launch_error,
    }


def _run_setup(
    setup: SetupPolicy,
    *,
    workspace: Path,
    run_ref_root: Path,
    revision: RepositoryRevisionId,
) -> tuple[Path, str]:
    evidence_path = _setup_evidence_path(
        run_ref_root=run_ref_root,
        revision=revision,
        workspace=workspace,
    )
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, object]] = []
    failure_argv: tuple[str, ...] | None = None

    for ordinal, command in enumerate(setup.commands, start=1):
        effective_env = dict(command.env)
        effective_env.update(
            {
                "PWD": str(workspace),
                "ORC_RUN_REF_SETUP_EVIDENCE_PATH": str(evidence_path),
            }
        )
        started_ns = time.monotonic_ns()
        try:
            completed = subprocess.run(
                command.argv,
                cwd=workspace,
                env=effective_env,
                check=False,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            duration_ms = (time.monotonic_ns() - started_ns) // 1_000_000
            stdout = completed.stdout if isinstance(completed.stdout, bytes) else b""
            stderr = completed.stderr if isinstance(completed.stderr, bytes) else b""
            exit_code: int | None = completed.returncode
            launch_error = None
        except OSError as exc:
            duration_ms = (time.monotonic_ns() - started_ns) // 1_000_000
            stdout = b""
            stderr = b""
            exit_code = None
            launch_error = {
                "kind": type(exc).__name__,
                "errno": exc.errno,
            }
        rows.append(
            _setup_command_evidence(
                ordinal=ordinal,
                command=command,
                exit_code=exit_code,
                duration_ms=duration_ms,
                stdout=stdout,
                stderr=stderr,
                launch_error=launch_error,
            )
        )
        if launch_error is not None or exit_code != 0:
            failure_argv = command.argv
            break

    payload = {
        "schema_version": "run_ref_setup_evidence.v1",
        "repository_revision_digest": revision.digest,
        "authored_setup_identity": revision.authored_setup_identity,
        "status": "failed" if failure_argv is not None else "passed",
        "commands": rows,
    }
    evidence_digest = canonical_sha256(payload)
    durable_atomic_write(
        evidence_path,
        canonical_json_bytes(payload) + b"\n",
    )
    if failure_argv is not None:
        raise RunRefSourceRefusal(
            "trial_setup_failed",
            list(failure_argv),
            "run-reference setup command failed",
        )
    return evidence_path, evidence_digest


def _revision_identity(
    request: SourceRequest,
) -> tuple[_MirrorSourceIdentity, RepositoryRevisionId]:
    canonical_request = canonical_source_request(request)
    source_components = {
        "normalized_locator": str(canonical_request["normalized_locator"]),
        "resolved_commit_sha": str(canonical_request["resolved_commit_sha"]),
        "materializer_version": str(canonical_request["materializer_version"]),
        "submodule_policy": str(canonical_request["submodule_policy"]),
        "lfs_policy": str(canonical_request["lfs_policy"]),
    }
    source = _MirrorSourceIdentity(
        digest=canonical_sha256(
            {
                "schema_version": _SOURCE_SCHEMA,
                **source_components,
            }
        ),
        **source_components,
    )
    revision = RepositoryRevisionId.build(
        normalized_locator=source_components["normalized_locator"],
        resolved_commit_sha=source_components["resolved_commit_sha"],
        materializer_version=source_components["materializer_version"],
        submodule_policy=source_components["submodule_policy"],
        lfs_policy=source_components["lfs_policy"],
        authored_setup_identity=str(canonical_request["authored_setup_identity"]),
    )
    return source, revision


def _seal_payload(
    source: _MirrorSourceIdentity,
    *,
    git_tree: str,
    expected_checkout_tree_manifest: TreeManifest,
) -> dict[str, object]:
    return {
        "schema_version": _MIRROR_SEAL_SCHEMA,
        "source_digest": source.digest,
        **source.components,
        "verified_git_tree": f"git-tree:{git_tree}",
        "expected_checkout_tree_manifest": _tree_manifest_payload(
            expected_checkout_tree_manifest
        ),
    }


def _read_seal(path: Path, source: _MirrorSourceIdentity) -> dict[str, object]:
    try:
        raw = path.read_bytes()
        payload = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _materialization_refusal(
            str(path),
            "sealed source mirror manifest is missing or unreadable",
        ) from exc
    if not isinstance(payload, dict):
        raise _materialization_refusal(
            str(path),
            "sealed source mirror manifest must be an object",
        )
    expected_identity = {
        "schema_version": _MIRROR_SEAL_SCHEMA,
        "source_digest": source.digest,
        **source.components,
    }
    if any(payload.get(key) != value for key, value in expected_identity.items()):
        raise _materialization_refusal(
            source.digest,
            "sealed source mirror manifest does not match the requested source",
        )
    tree = payload.get("verified_git_tree")
    try:
        VerifiedGitTreeIdentity(tree)  # type: ignore[arg-type]
    except (TypeError, ValueError) as exc:
        raise _materialization_refusal(
            tree,
            "sealed source mirror manifest has an invalid Git tree identity",
        ) from exc
    return payload


def _verify_local_mirror(
    mirror_path: Path,
    seal_path: Path,
    source: _MirrorSourceIdentity,
) -> tuple[VerifiedGitTreeIdentity, TreeManifest]:
    payload = _read_seal(seal_path, source)
    try:
        is_bare = _git_stdout(
            ("git", "--git-dir", str(mirror_path), "rev-parse", "--is-bare-repository")
        )
        resolved = _git_stdout(
            (
                "git",
                "--git-dir",
                str(mirror_path),
                "rev-parse",
                f"{source.resolved_commit_sha}^{{commit}}",
            )
        )
        tree = _git_stdout(
            (
                "git",
                "--git-dir",
                str(mirror_path),
                "rev-parse",
                f"{source.resolved_commit_sha}^{{tree}}",
            )
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _materialization_refusal(
            source.digest,
            "sealed source mirror cannot resolve its bound revision",
        ) from exc
    verified = VerifiedGitTreeIdentity(f"git-tree:{tree}")
    expected_checkout_tree_manifest = _expected_checkout_tree_manifest(
        mirror_path,
        source.resolved_commit_sha,
    )
    if (
        is_bare != "true"
        or resolved != source.resolved_commit_sha
        or payload.get("verified_git_tree") != verified.value
        or payload.get("expected_checkout_tree_manifest")
        != _tree_manifest_payload(expected_checkout_tree_manifest)
    ):
        raise _materialization_refusal(
            source.digest,
            "sealed source mirror content does not match its manifest",
        )
    return verified, expected_checkout_tree_manifest


def _initialize_mirror(
    *,
    source: _MirrorSourceIdentity,
    mirrors_root: Path,
    mirror_path: Path,
) -> tuple[VerifiedGitTreeIdentity, TreeManifest]:
    staging = Path(
        tempfile.mkdtemp(
            prefix=f".{source.digest.removeprefix('sha256:')}.",
            dir=mirrors_root,
        )
    )
    try:
        _run_git(("git", "init", "--bare", "--quiet", str(staging)))
        _run_git(
            (
                "git",
                "--git-dir",
                str(staging),
                "fetch",
                "--quiet",
                "--no-tags",
                "--force",
                source.normalized_locator,
                f"{source.resolved_commit_sha}:{_SEALED_BRANCH}",
            )
        )
        resolved = _git_stdout(
            (
                "git",
                "--git-dir",
                str(staging),
                "rev-parse",
                f"{source.resolved_commit_sha}^{{commit}}",
            )
        )
        tree = _git_stdout(
            (
                "git",
                "--git-dir",
                str(staging),
                "rev-parse",
                f"{source.resolved_commit_sha}^{{tree}}",
            )
        )
        if resolved != source.resolved_commit_sha:
            raise _materialization_refusal(
                resolved,
                "source resolved to a commit other than the exact authored revision",
            )
        _validate_source_policy(staging, source.resolved_commit_sha)
        verified = VerifiedGitTreeIdentity(f"git-tree:{tree}")
        expected_checkout_tree_manifest = _expected_checkout_tree_manifest(
            staging,
            source.resolved_commit_sha,
        )
        durable_atomic_write(
            staging / _MIRROR_SEAL_FILENAME,
            canonical_json_bytes(
                _seal_payload(
                    source,
                    git_tree=tree,
                    expected_checkout_tree_manifest=expected_checkout_tree_manifest,
                )
            )
            + b"\n",
        )
        if mirror_path.exists() or mirror_path.is_symlink():
            _discard_path(mirror_path)
        os.replace(staging, mirror_path)
    except RunRefSourceRefusal:
        raise
    except (OSError, subprocess.CalledProcessError) as exc:
        raise _refuse_unresolvable(
            source.normalized_locator,
            "the exact authored commit could not be fetched",
        ) from exc
    finally:
        if staging.exists() or staging.is_symlink():
            _discard_path(staging)
    return verified, expected_checkout_tree_manifest


def _sealed_mirror(
    *,
    source: _MirrorSourceIdentity,
    run_ref_root: Path,
) -> tuple[Path, Path, VerifiedGitTreeIdentity, TreeManifest]:
    digest = source.digest.removeprefix("sha256:")
    mirrors_root = run_ref_root / "mirrors"
    locks_root = run_ref_root / "mirror-locks"
    mirrors_root.mkdir(parents=True, exist_ok=True)
    locks_root.mkdir(parents=True, exist_ok=True)
    mirror_path = mirrors_root / digest
    seal_path = mirror_path / _MIRROR_SEAL_FILENAME
    lock_path = locks_root / f"{digest}.lock"

    with lock_path.open("a+b") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            if seal_path.is_file():
                verified, expected_checkout_tree_manifest = _verify_local_mirror(
                    mirror_path,
                    seal_path,
                    source,
                )
            else:
                if mirror_path.exists() or mirror_path.is_symlink():
                    _discard_path(mirror_path)
                verified, expected_checkout_tree_manifest = _initialize_mirror(
                    source=source,
                    mirrors_root=mirrors_root,
                    mirror_path=mirror_path,
                )
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    return (
        mirror_path,
        seal_path,
        verified,
        expected_checkout_tree_manifest,
    )


def materialize_source(
    request: SourceRequest,
    *,
    run_ref_root: Path,
    workspace: Path,
) -> MaterializedSource:
    """Seal an exact source mirror and produce one fresh independent clone."""

    workspace_path = Path(workspace)
    if os.path.lexists(workspace_path):
        raise RunRefSourceRefusal(
            "trial_workspace_preexisting",
            str(workspace_path),
            "run-reference workspace must not preexist",
        )
    workspace_path = _canonical_absolute_local_path(
        workspace_path,
        label="run-reference workspace",
    )
    run_ref_root_path = _canonical_absolute_local_path(
        Path(run_ref_root),
        label="run-reference root",
    )
    _require_directory_or_absent(
        run_ref_root_path,
        label="run-reference root",
    )
    _require_directory_or_absent(
        workspace_path.parent,
        label="run-reference workspace parent",
    )

    source, revision = _revision_identity(request)
    try:
        (
            mirror_path,
            seal_path,
            verified_tree,
            expected_checkout_tree_manifest,
        ) = _sealed_mirror(
            source=source,
            run_ref_root=run_ref_root_path,
        )
    except OSError as exc:
        raise _materialization_refusal(
            str(run_ref_root_path),
            "run-reference mirror coordination failed",
        ) from exc

    try:
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise _materialization_refusal(
            str(workspace_path.parent),
            "run-reference workspace parent could not be created",
        ) from exc
    workspace_created = False
    try:
        _run_git(
            (
                "git",
                "clone",
                "--quiet",
                "--no-checkout",
                "--no-local",
                str(mirror_path),
                str(workspace_path),
            )
        )
        workspace_created = True
        _run_git(
            (
                "git",
                "-C",
                str(workspace_path),
                "checkout",
                "--quiet",
                "--detach",
                source.resolved_commit_sha,
            )
        )
        checked_commit = _git_stdout(
            ("git", "-C", str(workspace_path), "rev-parse", "HEAD")
        )
        checked_tree = _git_stdout(
            (
                "git",
                "-C",
                str(workspace_path),
                "rev-parse",
                "HEAD^{tree}",
            )
        )
        if (
            checked_commit != source.resolved_commit_sha
            or f"git-tree:{checked_tree}" != verified_tree.value
        ):
            raise _materialization_refusal(
                source.resolved_commit_sha,
                "detached clone does not match the sealed source revision",
            )
        _normalize_checkout_modes(
            workspace_path,
            expected_checkout_tree_manifest,
        )
        source_tree_manifest = freeze_tree(
            workspace_path,
            excluded_roots=(".git",),
        )
        if source_tree_manifest != expected_checkout_tree_manifest:
            raise _materialization_refusal(
                source_tree_manifest.digest,
                "detached clone manifest does not match the sealed Git object manifest",
            )
        setup_evidence_path, setup_evidence_digest = _run_setup(
            request.setup,
            workspace=workspace_path,
            run_ref_root=run_ref_root_path,
            revision=revision,
        )
        post_setup_tree_manifest = freeze_tree(
            workspace_path,
            excluded_roots=(".git", ".orchestrate"),
        )
        post_setup_baseline_identity = PostSetupBaselineIdentity(
            post_setup_tree_manifest.digest
        )
    except RunRefSourceRefusal:
        if workspace_created:
            _discard_path(workspace_path)
        raise
    except WorkspaceFreezeError as exc:
        if workspace_created or os.path.lexists(workspace_path):
            _discard_path(workspace_path)
        raise _materialization_refusal(
            str(workspace_path),
            "run-reference workspace cannot be represented by the deterministic tree contract",
        ) from exc
    except (OSError, subprocess.CalledProcessError) as exc:
        if workspace_created or os.path.lexists(workspace_path):
            _discard_path(workspace_path)
        raise _materialization_refusal(
            source.resolved_commit_sha,
            "failed to create and verify the detached source clone",
        ) from exc

    return MaterializedSource(
        repository_revision_id=revision,
        normalized_locator=source.normalized_locator,
        resolved_commit_sha=source.resolved_commit_sha,
        verified_git_tree=verified_tree,
        mirror_path=mirror_path,
        mirror_seal_path=seal_path,
        workspace_path=workspace_path,
        source_tree_manifest=source_tree_manifest,
        setup_evidence_path=setup_evidence_path,
        setup_evidence_digest=setup_evidence_digest,
        post_setup_tree_manifest=post_setup_tree_manifest,
        post_setup_baseline_identity=post_setup_baseline_identity,
    )


__all__ = [
    "MaterializedSource",
    "RunRefSourceRefusal",
    "SourceRequest",
    "canonical_repository_revision_result",
    "canonical_source_request",
    "materialize_source",
    "normalize_repository_locator",
    "validate_commit_sha",
]
