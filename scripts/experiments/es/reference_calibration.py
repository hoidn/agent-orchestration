"""Canonical Task-0 records and the shared ES implementation-delta metric.

This module is deliberately provider-free.  It validates one pinned Git tool,
measures explicit directory trees, and replays the retained A1 calibration
anchor without consulting an ambient checkout or inferring path ownership.
"""

from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, NoReturn, Sequence

from jsonschema import Draft202012Validator


METRIC_VERSION = "implementation_delta_physical_lines.v1"
PINNED_GIT_EXECUTABLE = Path("/usr/bin/git")
PINNED_GIT_VERSION = "2.43.0"
PINNED_GIT_EXECUTABLE_SHA256 = (
    "sha256:2a8c18fbf43da9f692d75474c72bea9dfd796c260b0f3dfe456376abc3bbd668"
)
PINNED_GIT_DIFF_CONTROLS = (
    "--no-ext-diff",
    "--no-textconv",
    "--diff-algorithm=histogram",
    "--find-renames=100%",
    "--find-copies=100%",
    "--find-copies-harder",
)
A1_EVIDENCE_ROOT = Path(
    "/home/ollie/.local/share/agent-orchestration/lean-pilot-evidence/"
    "pilot-2026-07-27/a1-v7"
)

_SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
_ARCHITECTURE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_ALLOWED_CLASSIFICATIONS = frozenset(
    {
        "production_python",
        "test",
        "documentation",
        "fixture",
        "vendored",
        "benchmark_task_seed_asset",
    }
)
_FORBIDDEN_CLASSIFICATIONS = frozenset({"generated", "cache"})
_A1_RESPONSIBILITY_ID = "A1_REFERENCE_CALIBRATION"


class CalibrationError(ValueError):
    """One canonical-record, metric, or A1 calibration invariant failed."""

    def __init__(self, code: str, value: object, detail: str) -> None:
        super().__init__(f"{code}: {detail}: {value!r}")
        self.code = code
        self.value = value
        self.detail = detail


@dataclass(frozen=True)
class GitContract:
    executable: Path
    version: str
    executable_sha256: str
    diff_controls: tuple[str, ...]
    policy_sha256: str


@dataclass(frozen=True)
class NumstatRow:
    additions: int
    deletions: int
    old_path: str
    new_path: str


@dataclass(frozen=True)
class MetricPathPolicy:
    path: str
    classification: str
    responsibility_ids: tuple[str, ...]


@dataclass(frozen=True)
class DeltaPathRow:
    base_path: str | None
    candidate_path: str | None
    base_blob_id: str | None
    candidate_blob_id: str | None
    base_mode: int | None
    candidate_mode: int | None
    base_physical_lines: int
    candidate_physical_lines: int
    additions: int
    deletions: int
    change_kind: str
    classification: str
    responsibility_ids: tuple[str, ...]


@dataclass(frozen=True)
class DeltaTotals:
    additions: int
    deletions: int
    base_physical_lines: int
    candidate_postimage_physical_lines: int


@dataclass(frozen=True)
class ImplementationDelta:
    metric_version: str
    git_contract_policy_sha256: str
    rows: tuple[DeltaPathRow, ...]
    totals_by_classification: Mapping[str, DeltaTotals]
    implementation_additions: int
    implementation_deletions: int
    base_physical_lines: int
    candidate_postimage_physical_lines: int


@dataclass(frozen=True)
class A1MemberExpectation:
    member_id: str
    path: str
    byte_count: int
    sha256: str


@dataclass(frozen=True)
class A1Calibration:
    record: dict[str, Any]
    measurement: ImplementationDelta


@dataclass(frozen=True)
class ReferenceProduct:
    """One fully validated controller-only ES reference authority."""

    record: dict[str, Any]
    _selector_manifest: dict[str, Any]
    _source_census: dict[str, Any]
    _record_path: Path | None = field(default=None, repr=False, compare=False)
    _schema_path: Path | None = field(default=None, repr=False, compare=False)
    _expected_record_sha256: str | None = field(
        default=None, repr=False, compare=False
    )
    _validation_provenance: object | None = field(
        default=None, repr=False, compare=False
    )


@dataclass(frozen=True)
class _FileSnapshot:
    path: str
    blob_id: str
    mode: int
    physical_lines: int
    payload: bytes


@dataclass(frozen=True)
class _UnclassifiedDelta:
    base_path: str | None
    candidate_path: str | None
    additions: int
    deletions: int
    change_kind: str


A1_MEMBER_EXPECTATIONS = (
    A1MemberExpectation(
        "pilot_lock",
        "pilot-lock.json",
        14_598,
        "sha256:b8d69ba2f3d2b2e7bc6d9181d776db0b7abacd2035f851cd44be613dac6d8503",
    ),
    A1MemberExpectation(
        "summary",
        "summary-2026-07-31/pilot-summary.json",
        10_901,
        "sha256:153263159d6516d032be83bd8f53954be0ba05b39af58be23d1abdca34085e89",
    ),
    A1MemberExpectation(
        "block_record",
        "evidence/b-5970f312e6698e50/block-attempt.json",
        2_576,
        "sha256:e5c3c5d8fca11860d48864cc1f4164d7b80df26cba62751754899f659b8f72c2",
    ),
    A1MemberExpectation(
        "package_manifest",
        "packages/b-5970f312e6698e50/b-5970f312e6698e50/manifest.json",
        2_987,
        "sha256:142320b4bf4f20e4015520583c535efcf22e8713552c152a25719c1473377cde",
    ),
    A1MemberExpectation(
        "direct_patch",
        "packages/b-5970f312e6698e50/b-5970f312e6698e50/"
        "candidates/candidate-3cca13b2595a/diff.patch",
        33_695,
        "sha256:55cd1a8216d0b7c749e6d9dfb47b1fa998ebed888101e5dca03349ba75d57ebb",
    ),
    A1MemberExpectation(
        "base_entrypoint",
        "evaluation/b-5970f312e6698e50/base/torch_port/entrypoint.py",
        360,
        "sha256:c458f6b0fba0dc2ebd80c756d51278f53dc9d15320bf5f677c7878d8331aaa80",
    ),
    A1MemberExpectation(
        "base_types",
        "evaluation/b-5970f312e6698e50/base/torch_port/types.py",
        85,
        "sha256:63118fc7530528b564f29752a20415b51db02fb572843d3864ba5e2f903eb92a",
    ),
    A1MemberExpectation(
        "base_init",
        "evaluation/b-5970f312e6698e50/base/torch_port/__init__.py",
        113,
        "sha256:b33a873ed5bde35302e67190698bf0fa655bdd57077db89d5183101ef6f4ec35",
    ),
    A1MemberExpectation(
        "direct_entrypoint",
        "evaluation/b-5970f312e6698e50/candidates/arm-4301192e76f41f90/"
        "torch_port/entrypoint.py",
        26_770,
        "sha256:f1ea1162fba1151aa8b13967565eaed9d515b0ebb8d35d0565a97c1fdaaa653c",
    ),
    A1MemberExpectation(
        "direct_types",
        "evaluation/b-5970f312e6698e50/candidates/arm-4301192e76f41f90/"
        "torch_port/types.py",
        85,
        "sha256:63118fc7530528b564f29752a20415b51db02fb572843d3864ba5e2f903eb92a",
    ),
    A1MemberExpectation(
        "direct_init",
        "evaluation/b-5970f312e6698e50/candidates/arm-4301192e76f41f90/"
        "torch_port/__init__.py",
        113,
        "sha256:b33a873ed5bde35302e67190698bf0fa655bdd57077db89d5183101ef6f4ec35",
    ),
    A1MemberExpectation(
        "review_1",
        "evidence/b-5970f312e6698e50/reviews/calibration-reviewer-01/"
        "review-result.json",
        7_998,
        "sha256:881cf86d2fdcdef1a158fedceaf3211e82de0a3616c1f7080d48c5fe5443b2d9",
    ),
    A1MemberExpectation(
        "review_2",
        "evidence/b-5970f312e6698e50/reviews/calibration-reviewer-02/"
        "review-result.json",
        11_577,
        "sha256:b10b517fdf63f330666fe96798733c3f1551987033fe9a86f2f43f5139cb07b4",
    ),
)


def canonical_json_bytes(value: object) -> bytes:
    """Encode one canonical JSON value in the Task-0 ASCII-plus-LF domain."""

    try:
        return (
            json.dumps(
                value,
                ensure_ascii=True,
                allow_nan=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            + b"\n"
        )
    except (TypeError, ValueError) as exc:
        raise CalibrationError(
            "record_noncanonical", value, "value cannot be encoded as canonical JSON"
        ) from exc


def canonical_record_body_bytes(record: Mapping[str, object]) -> bytes:
    """Canonicalize a record after omitting only its top-level self digest."""

    if not isinstance(record, Mapping):
        raise CalibrationError(
            "record_noncanonical", record, "record must be a JSON object"
        )
    body = dict(record)
    body.pop("record_sha256", None)
    return canonical_json_bytes(body)


def compute_record_sha256(record: Mapping[str, object]) -> str:
    return "sha256:" + hashlib.sha256(canonical_record_body_bytes(record)).hexdigest()


def validate_record_sha256(record: Mapping[str, object]) -> str:
    if not isinstance(record, Mapping):
        raise CalibrationError(
            "record_sha256_invalid", record, "digest-bearing record must be an object"
        )
    actual = record.get("record_sha256")
    if not isinstance(actual, str) or _SHA256_RE.fullmatch(actual) is None:
        raise CalibrationError(
            "record_sha256_invalid", actual, "record_sha256 is missing or malformed"
        )
    expected = compute_record_sha256(record)
    if actual != expected:
        raise CalibrationError(
            "record_sha256_invalid",
            {"actual": actual, "expected": expected},
            "record body and record_sha256 disagree",
        )
    return actual


def seal_record(body: Mapping[str, object]) -> dict[str, Any]:
    if not isinstance(body, Mapping):
        raise CalibrationError("record_noncanonical", body, "record body must be an object")
    record: dict[str, Any] = dict(body)
    record.pop("record_sha256", None)
    record["record_sha256"] = compute_record_sha256(record)
    return record


def _reject_nonfinite_constant(value: str) -> NoReturn:
    raise CalibrationError(
        "record_noncanonical", value, "non-finite JSON constants are forbidden"
    )


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CalibrationError(
                "record_noncanonical", key, "JSON object contains a duplicate key"
            )
        result[key] = value
    return result


def _parse_json_bytes(raw: bytes, *, label: object) -> Any:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_nonfinite_constant,
        )
    except CalibrationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CalibrationError(
            "record_noncanonical", label, "bytes are not strict JSON"
        ) from exc


def load_canonical_record(
    path: Path,
    *,
    schema_path: Path,
    expected_record_sha256: str,
) -> dict[str, Any]:
    """Load one closed-schema canonical record and verify its self digest."""

    candidate = Path(path)
    schema_candidate = Path(schema_path)
    try:
        raw = candidate.read_bytes()
        schema_raw = schema_candidate.read_bytes()
    except OSError as exc:
        raise CalibrationError(
            "record_unreadable",
            {"record": str(candidate), "schema": str(schema_candidate)},
            "record or schema is missing or unreadable",
        ) from exc
    value = _parse_json_bytes(raw, label=candidate)
    schema = _parse_json_bytes(schema_raw, label=schema_candidate)
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise CalibrationError(
            "record_noncanonical",
            str(candidate),
            "record must be canonical JSON followed by exactly one LF",
        )
    if not isinstance(schema, dict):
        raise CalibrationError(
            "record_schema_invalid", str(schema_candidate), "schema must be an object"
        )
    digest = validate_record_sha256(value)
    if (
        not isinstance(expected_record_sha256, str)
        or _SHA256_RE.fullmatch(expected_record_sha256) is None
        or digest != expected_record_sha256
    ):
        raise CalibrationError(
            "record_sha256_invalid",
            {"actual": digest, "expected": expected_record_sha256},
            "record does not match the explicit expected digest",
        )
    try:
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    except Exception as exc:
        raise CalibrationError(
            "record_schema_invalid", str(schema_candidate), "schema is invalid"
        ) from exc
    if errors:
        raise CalibrationError(
            "record_schema_invalid", str(candidate), errors[0].message
        )
    return value


def _git_environment() -> dict[str, str]:
    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_SYSTEM": os.devnull,
        "HOME": "/nonexistent",
        "LANG": "C",
        "LC_ALL": "C",
        "XDG_CONFIG_HOME": "/nonexistent",
    }


def _sha256_bytes(payload: bytes) -> str:
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def verify_git_contract(contract: GitContract) -> GitContract:
    if not isinstance(contract, GitContract):
        raise CalibrationError(
            "git_contract_invalid", contract, "Git contract has the wrong type"
        )
    executable = Path(contract.executable)
    try:
        metadata = executable.lstat()
        resolved = executable.resolve(strict=True)
        payload = executable.read_bytes()
    except OSError as exc:
        raise CalibrationError(
            "git_contract_invalid", str(executable), "Git executable is unreadable"
        ) from exc
    expected = {
        "executable": PINNED_GIT_EXECUTABLE,
        "version": PINNED_GIT_VERSION,
        "sha256": PINNED_GIT_EXECUTABLE_SHA256,
        "diff_controls": PINNED_GIT_DIFF_CONTROLS,
    }
    observed = {
        "executable": executable,
        "version": contract.version,
        "sha256": contract.executable_sha256,
        "diff_controls": tuple(contract.diff_controls),
    }
    if (
        observed != expected
        or resolved != executable
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or _sha256_bytes(payload) != contract.executable_sha256
        or _SHA256_RE.fullmatch(contract.policy_sha256) is None
    ):
        raise CalibrationError(
            "git_contract_invalid",
            {"declared": observed, "expected": expected},
            "Git path, version, bytes, controls, or policy binding drifted",
        )
    try:
        completed = subprocess.run(
            (str(executable), "--version"),
            cwd=Path("/"),
            env=_git_environment(),
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise CalibrationError(
            "git_contract_invalid", str(executable), "pinned Git could not launch"
        ) from exc
    expected_version = f"git version {contract.version}\n".encode("ascii")
    if completed.returncode != 0 or completed.stdout != expected_version or completed.stderr:
        raise CalibrationError(
            "git_contract_invalid",
            {
                "exit_code": completed.returncode,
                "stdout": completed.stdout.decode("utf-8", errors="replace"),
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
            },
            "pinned Git reported a different version",
        )
    return contract


def _run_pinned_git(
    contract: GitContract,
    arguments: Sequence[str],
    *,
    cwd: Path,
    input_bytes: bytes | None = None,
    accepted_codes: frozenset[int] = frozenset({0}),
) -> bytes:
    argv = (str(contract.executable), *arguments)
    try:
        completed = subprocess.run(
            argv,
            cwd=cwd,
            env=_git_environment(),
            check=False,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except OSError as exc:
        raise CalibrationError(
            "git_execution_failed", argv, "pinned Git command could not launch"
        ) from exc
    if completed.returncode not in accepted_codes or completed.stderr:
        raise CalibrationError(
            "git_execution_failed",
            {
                "argv": argv,
                "exit_code": completed.returncode,
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
            },
            "pinned Git command failed",
        )
    return completed.stdout


def _render_git_tree(
    contract: GitContract,
    repository: Path,
    snapshots: Mapping[str, _FileSnapshot],
) -> str:
    trie: dict[str, Any] = {}
    for relative, snapshot in snapshots.items():
        node = trie
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            nested = node.setdefault(part, {})
            if not isinstance(nested, dict):
                raise CalibrationError(
                    "metric_input_invalid", relative, "metric path collides with a file"
                )
            node = nested
        if parts[-1] in node:
            raise CalibrationError(
                "metric_input_invalid", relative, "metric path is duplicated"
            )
        node[parts[-1]] = snapshot

    written_blobs: set[str] = set()

    def render(node: Mapping[str, Any]) -> str:
        entries: list[tuple[bytes, bytes]] = []
        for name, value in node.items():
            encoded_name = name.encode("utf-8")
            if isinstance(value, _FileSnapshot):
                if value.blob_id not in written_blobs:
                    observed = _run_pinned_git(
                        contract,
                        ("-C", str(repository), "hash-object", "-w", "--stdin"),
                        cwd=repository.parent,
                        input_bytes=value.payload,
                    ).decode("ascii", errors="strict").strip()
                    if observed != value.blob_id:
                        raise CalibrationError(
                            "metric_output_invalid",
                            {"actual": observed, "expected": value.blob_id},
                            "Git wrote a different blob identity",
                        )
                    written_blobs.add(value.blob_id)
                mode = b"100755" if value.mode & 0o111 else b"100644"
                entry = mode + b" blob " + value.blob_id.encode("ascii")
                entries.append((encoded_name, entry + b"\t" + encoded_name + b"\0"))
            elif isinstance(value, dict):
                tree_id = render(value)
                entry = b"040000 tree " + tree_id.encode("ascii")
                entries.append(
                    (encoded_name + b"/", entry + b"\t" + encoded_name + b"\0")
                )
            else:
                raise CalibrationError(
                    "metric_input_invalid", name, "metric tree node has an invalid type"
                )
        tree_input = b"".join(payload for _, payload in sorted(entries))
        return _run_pinned_git(
            contract,
            ("-C", str(repository), "mktree", "-z"),
            cwd=repository.parent,
            input_bytes=tree_input,
        ).decode("ascii", errors="strict").strip()

    return render(trie)


def _run_git_diff(
    contract: GitContract,
    base: Mapping[str, _FileSnapshot],
    candidate: Mapping[str, _FileSnapshot],
) -> bytes:
    with tempfile.TemporaryDirectory(prefix=".es-reference-calibration-") as raw:
        temporary = Path(raw)
        repository = temporary / "objects.git"
        _run_pinned_git(
            contract,
            ("init", "--bare", "--quiet", str(repository)),
            cwd=temporary,
        )
        base_tree = _render_git_tree(contract, repository, base)
        candidate_tree = _render_git_tree(contract, repository, candidate)
        return _run_pinned_git(
            contract,
            (
                "-C",
                str(repository),
                "diff",
                "--numstat",
                "-z",
                *contract.diff_controls,
                base_tree,
                candidate_tree,
                "--",
            ),
            cwd=temporary,
        )


def parse_numstat_z(raw: bytes) -> tuple[NumstatRow, ...]:
    if not isinstance(raw, bytes):
        raise CalibrationError(
            "metric_output_invalid", type(raw).__name__, "numstat output must be bytes"
        )
    rows: list[NumstatRow] = []
    offset = 0
    while offset < len(raw):
        first_tab = raw.find(b"\t", offset)
        second_tab = raw.find(b"\t", first_tab + 1) if first_tab >= 0 else -1
        if first_tab < 0 or second_tab < 0:
            raise CalibrationError(
                "metric_output_invalid", raw[offset:], "numstat row header is malformed"
            )
        additions_raw = raw[offset:first_tab]
        deletions_raw = raw[first_tab + 1 : second_tab]
        if additions_raw == b"-" or deletions_raw == b"-":
            raise CalibrationError(
                "metric_output_invalid", raw[offset:], "binary numstat row is forbidden"
            )
        try:
            additions = int(additions_raw.decode("ascii"))
            deletions = int(deletions_raw.decode("ascii"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise CalibrationError(
                "metric_output_invalid", raw[offset:], "numstat counts are malformed"
            ) from exc
        path_offset = second_tab + 1
        if path_offset < len(raw) and raw[path_offset] == 0:
            old_end = raw.find(b"\0", path_offset + 1)
            new_end = raw.find(b"\0", old_end + 1) if old_end >= 0 else -1
            if old_end < 0 or new_end < 0:
                raise CalibrationError(
                    "metric_output_invalid", raw[offset:], "rename/copy paths are malformed"
                )
            old_raw = raw[path_offset + 1 : old_end]
            new_raw = raw[old_end + 1 : new_end]
            offset = new_end + 1
        else:
            path_end = raw.find(b"\0", path_offset)
            if path_end < 0:
                raise CalibrationError(
                    "metric_output_invalid", raw[offset:], "numstat path is unterminated"
                )
            old_raw = new_raw = raw[path_offset:path_end]
            offset = path_end + 1
        try:
            old_path = old_raw.decode("utf-8", errors="strict")
            new_path = new_raw.decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise CalibrationError(
                "metric_output_invalid", raw, "numstat path is not strict UTF-8"
            ) from exc
        if not old_path or not new_path or additions < 0 or deletions < 0:
            raise CalibrationError(
                "metric_output_invalid", (old_path, new_path), "numstat row is invalid"
            )
        rows.append(NumstatRow(additions, deletions, old_path, new_path))
    return tuple(rows)


def _canonical_relative_path(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise CalibrationError("metric_input_invalid", value, f"{label} is empty")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or pure.as_posix() != value
        or any(part in {"", ".", ".."} for part in pure.parts)
        or "\n" in value
        or "\r" in value
        or "\0" in value
    ):
        raise CalibrationError(
            "metric_input_invalid", value, f"{label} is not canonical relative POSIX text"
        )
    return value


def _canonical_root(path: Path, *, label: str) -> Path:
    candidate = Path(path)
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise CalibrationError(
            "metric_input_invalid", str(candidate), f"{label} is missing or unreadable"
        ) from exc
    if (
        not candidate.is_absolute()
        or resolved != candidate
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        raise CalibrationError(
            "metric_input_invalid", str(candidate), f"{label} must be a canonical real directory"
        )
    return candidate


def _git_blob_id(payload: bytes) -> str:
    framed = b"blob " + str(len(payload)).encode("ascii") + b"\0" + payload
    return hashlib.sha1(framed).hexdigest()


def _scan_tree(root: Path) -> dict[str, _FileSnapshot]:
    rows: dict[str, _FileSnapshot] = {}

    def visit(directory: Path, parts: tuple[str, ...]) -> None:
        try:
            entries = sorted(os.scandir(directory), key=lambda entry: entry.name.encode("utf-8"))
        except (OSError, UnicodeEncodeError) as exc:
            raise CalibrationError(
                "metric_input_invalid", str(directory), "metric tree is unreadable"
            ) from exc
        try:
            for entry in entries:
                relative_parts = (*parts, entry.name)
                try:
                    metadata = entry.stat(follow_symlinks=False)
                except OSError as exc:
                    raise CalibrationError(
                        "metric_input_invalid", entry.path, "metric member is unreadable"
                    ) from exc
                if stat.S_ISLNK(metadata.st_mode):
                    raise CalibrationError(
                        "metric_input_invalid", entry.path, "symlink metric input is forbidden"
                    )
                if stat.S_ISDIR(metadata.st_mode):
                    visit(Path(entry.path), relative_parts)
                    continue
                if not stat.S_ISREG(metadata.st_mode):
                    raise CalibrationError(
                        "metric_input_invalid", entry.path, "metric input must be a regular file"
                    )
                relative = PurePosixPath(*relative_parts).as_posix()
                _canonical_relative_path(relative, label="metric path")
                try:
                    payload = Path(entry.path).read_bytes()
                    text = payload.decode("utf-8", errors="strict")
                except (OSError, UnicodeDecodeError) as exc:
                    raise CalibrationError(
                        "metric_input_invalid",
                        relative,
                        "metric input must be readable strict UTF-8",
                    ) from exc
                if b"\0" in payload:
                    raise CalibrationError(
                        "metric_input_invalid", relative, "NUL-bearing metric input is forbidden"
                    )
                rows[relative] = _FileSnapshot(
                    path=relative,
                    blob_id=_git_blob_id(payload),
                    mode=stat.S_IMODE(metadata.st_mode),
                    physical_lines=len(text.splitlines()),
                    payload=payload,
                )
        finally:
            for entry in entries:
                del entry

    visit(root, ())
    return rows


def _normalize_git_path(raw: str, root: Path) -> str | None:
    path = Path(raw)
    if not path.is_absolute():
        if raw == "/dev/null":
            return None
        return _canonical_relative_path(raw, label="Git output path")
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError:
        return None
    return _canonical_relative_path(relative, label="Git output path")


def _classify_numstat_rows(
    numstat_rows: Sequence[NumstatRow],
    *,
    base_root: Path,
    candidate_root: Path,
    base: Mapping[str, _FileSnapshot],
    candidate: Mapping[str, _FileSnapshot],
) -> tuple[_UnclassifiedDelta, ...]:
    rows: list[_UnclassifiedDelta] = []
    consumed_base: set[str] = set()
    consumed_candidate: set[str] = set()
    for raw in numstat_rows:
        old_from_base = _normalize_git_path(raw.old_path, base_root)
        new_from_candidate = _normalize_git_path(raw.new_path, candidate_root)
        if raw.old_path != raw.new_path:
            if raw.old_path == "/dev/null" and new_from_candidate in candidate:
                assert new_from_candidate is not None
                rows.append(
                    _UnclassifiedDelta(
                        None,
                        new_from_candidate,
                        raw.additions,
                        raw.deletions,
                        "add",
                    )
                )
                consumed_candidate.add(new_from_candidate)
                continue
            if raw.new_path == "/dev/null" and old_from_base in base:
                assert old_from_base is not None
                rows.append(
                    _UnclassifiedDelta(
                        old_from_base,
                        None,
                        raw.additions,
                        raw.deletions,
                        "delete",
                    )
                )
                consumed_base.add(old_from_base)
                continue
            if old_from_base not in base or new_from_candidate not in candidate:
                raise CalibrationError(
                    "metric_output_invalid", raw, "rename/copy row escapes metric roots"
                )
            assert old_from_base is not None and new_from_candidate is not None
            if old_from_base == new_from_candidate:
                kind = "modify"
            elif (
                old_from_base in candidate
                and base[old_from_base].blob_id == candidate[old_from_base].blob_id
            ):
                kind = "copy"
            else:
                kind = "rename"
            rows.append(
                _UnclassifiedDelta(
                    old_from_base,
                    new_from_candidate,
                    raw.additions,
                    raw.deletions,
                    kind,
                )
            )
            if kind != "copy":
                consumed_base.add(old_from_base)
            consumed_candidate.add(new_from_candidate)
            continue

        path_from_base = _normalize_git_path(raw.old_path, base_root)
        path_from_candidate = _normalize_git_path(raw.new_path, candidate_root)
        relative = path_from_candidate or path_from_base
        if relative is None:
            raise CalibrationError(
                "metric_output_invalid", raw, "numstat path escapes metric roots"
            )
        in_base = relative in base
        in_candidate = relative in candidate
        if in_base and in_candidate:
            base_path = candidate_path = relative
            kind = "modify"
            consumed_base.add(relative)
            consumed_candidate.add(relative)
        elif in_base:
            base_path, candidate_path, kind = relative, None, "delete"
            consumed_base.add(relative)
        elif in_candidate:
            base_path, candidate_path, kind = None, relative, "add"
            consumed_candidate.add(relative)
        else:
            raise CalibrationError(
                "metric_output_invalid", raw, "numstat path names no metric member"
            )
        rows.append(
            _UnclassifiedDelta(
                base_path,
                candidate_path,
                raw.additions,
                raw.deletions,
                kind,
            )
        )

    for relative in sorted(set(base) | set(candidate), key=lambda value: value.encode("utf-8")):
        if relative in consumed_base or relative in consumed_candidate:
            continue
        if relative not in base or relative not in candidate:
            raise CalibrationError(
                "metric_output_invalid", relative, "Git omitted a changed metric path"
            )
        if (
            base[relative].blob_id != candidate[relative].blob_id
            or base[relative].mode != candidate[relative].mode
        ):
            raise CalibrationError(
                "metric_output_invalid", relative, "Git omitted changed metric bytes or mode"
            )
        rows.append(_UnclassifiedDelta(relative, relative, 0, 0, "unchanged"))
        consumed_base.add(relative)
        consumed_candidate.add(relative)

    represented_base = {row.base_path for row in rows if row.base_path is not None}
    represented_candidate = {
        row.candidate_path for row in rows if row.candidate_path is not None
    }
    if represented_base != set(base) or represented_candidate != set(candidate):
        raise CalibrationError(
            "metric_output_invalid",
            {
                "base_missing": sorted(set(base) - represented_base),
                "candidate_missing": sorted(set(candidate) - represented_candidate),
            },
            "metric rows do not cover both input trees",
        )
    return tuple(rows)


def _validate_path_policies(
    policies: Sequence[MetricPathPolicy],
    *,
    allowed_responsibility_ids: frozenset[str],
) -> dict[str, MetricPathPolicy]:
    if not isinstance(allowed_responsibility_ids, frozenset) or any(
        not isinstance(value, str) or not value for value in allowed_responsibility_ids
    ):
        raise CalibrationError(
            "metric_input_invalid",
            allowed_responsibility_ids,
            "allowed responsibility IDs must be an explicit string domain",
        )
    by_path: dict[str, MetricPathPolicy] = {}
    for policy in policies:
        if not isinstance(policy, MetricPathPolicy):
            raise CalibrationError(
                "metric_input_invalid", policy, "path policy has the wrong type"
            )
        path = _canonical_relative_path(policy.path, label="classified path")
        if path in by_path:
            raise CalibrationError(
                "metric_input_invalid", path, "path classification is duplicated"
            )
        if (
            policy.classification not in _ALLOWED_CLASSIFICATIONS
            or policy.classification in _FORBIDDEN_CLASSIFICATIONS
        ):
            raise CalibrationError(
                "metric_input_invalid",
                policy.classification,
                "path classification is forbidden or unknown",
            )
        if (
            not isinstance(policy.responsibility_ids, tuple)
            or tuple(sorted(set(policy.responsibility_ids)))
            != policy.responsibility_ids
        ):
            raise CalibrationError(
                "metric_input_invalid",
                policy.responsibility_ids,
                "responsibility IDs must be unique and ordered",
            )
        if policy.classification == "production_python":
            if (
                not path.endswith(".py")
                or not policy.responsibility_ids
                or not set(policy.responsibility_ids).issubset(
                    allowed_responsibility_ids
                )
            ):
                raise CalibrationError(
                    "metric_input_invalid",
                    policy,
                    "production Python requires an allowed responsibility assignment",
                )
        elif policy.responsibility_ids:
            raise CalibrationError(
                "metric_input_invalid",
                policy,
                "non-production paths may not own behavioral responsibilities",
            )
        by_path[path] = policy
    return by_path


def measure_implementation_delta(
    *,
    base_root: Path,
    candidate_root: Path,
    path_policies: Sequence[MetricPathPolicy],
    allowed_responsibility_ids: frozenset[str],
    git_contract: GitContract,
) -> ImplementationDelta:
    """Measure explicit trees using the frozen physical-additions contract."""

    contract = verify_git_contract(git_contract)
    base_path = _canonical_root(Path(base_root), label="base root")
    candidate_path = _canonical_root(Path(candidate_root), label="candidate root")
    if (
        base_path == candidate_path
        or base_path.is_relative_to(candidate_path)
        or candidate_path.is_relative_to(base_path)
    ):
        raise CalibrationError(
            "metric_input_invalid",
            (str(base_path), str(candidate_path)),
            "metric roots must be distinct and non-nested",
        )
    policies = _validate_path_policies(
        path_policies, allowed_responsibility_ids=allowed_responsibility_ids
    )
    base = _scan_tree(base_path)
    candidate = _scan_tree(candidate_path)
    raw = _run_git_diff(contract, base, candidate)
    unclassified = _classify_numstat_rows(
        parse_numstat_z(raw),
        base_root=base_path,
        candidate_root=candidate_path,
        base=base,
        candidate=candidate,
    )

    rows: list[DeltaPathRow] = []
    used_policies: set[str] = set()
    for raw_row in unclassified:
        logical_path = raw_row.candidate_path or raw_row.base_path
        assert logical_path is not None
        policy = policies.get(logical_path)
        if policy is None:
            raise CalibrationError(
                "metric_input_invalid", logical_path, "metric path is unclassified"
            )
        if logical_path in used_policies:
            raise CalibrationError(
                "metric_output_invalid", logical_path, "classification was reused"
            )
        used_policies.add(logical_path)
        before = base.get(raw_row.base_path) if raw_row.base_path is not None else None
        after = (
            candidate.get(raw_row.candidate_path)
            if raw_row.candidate_path is not None
            else None
        )
        rows.append(
            DeltaPathRow(
                base_path=raw_row.base_path,
                candidate_path=raw_row.candidate_path,
                base_blob_id=before.blob_id if before else None,
                candidate_blob_id=after.blob_id if after else None,
                base_mode=before.mode if before else None,
                candidate_mode=after.mode if after else None,
                base_physical_lines=before.physical_lines if before else 0,
                candidate_physical_lines=after.physical_lines if after else 0,
                additions=raw_row.additions,
                deletions=raw_row.deletions,
                change_kind=raw_row.change_kind,
                classification=policy.classification,
                responsibility_ids=policy.responsibility_ids,
            )
        )
    if used_policies != set(policies):
        raise CalibrationError(
            "metric_input_invalid",
            sorted(set(policies) - used_policies),
            "classification names no metric path",
        )
    rows.sort(
        key=lambda row: (row.candidate_path or row.base_path or "").encode("utf-8")
    )

    base_classification: dict[str, str] = {}
    candidate_classification: dict[str, str] = {}
    for row in rows:
        if row.base_path is not None:
            previous = base_classification.setdefault(row.base_path, row.classification)
            if previous != row.classification:
                raise CalibrationError(
                    "metric_input_invalid",
                    row.base_path,
                    "one base path has conflicting classifications",
                )
        if row.candidate_path is not None:
            previous = candidate_classification.setdefault(
                row.candidate_path, row.classification
            )
            if previous != row.classification:
                raise CalibrationError(
                    "metric_input_invalid",
                    row.candidate_path,
                    "one candidate path has conflicting classifications",
                )

    totals: dict[str, DeltaTotals] = {}
    for classification in sorted({row.classification for row in rows}):
        classified_rows = [row for row in rows if row.classification == classification]
        totals[classification] = DeltaTotals(
            additions=sum(row.additions for row in classified_rows),
            deletions=sum(row.deletions for row in classified_rows),
            base_physical_lines=sum(
                base[path].physical_lines
                for path, assigned in base_classification.items()
                if assigned == classification
            ),
            candidate_postimage_physical_lines=sum(
                candidate[path].physical_lines
                for path, assigned in candidate_classification.items()
                if assigned == classification
            ),
        )
    production = totals.get("production_python", DeltaTotals(0, 0, 0, 0))

    if _scan_tree(base_path) != base or _scan_tree(candidate_path) != candidate:
        raise CalibrationError(
            "metric_input_invalid", None, "metric input tree changed during measurement"
        )
    return ImplementationDelta(
        metric_version=METRIC_VERSION,
        git_contract_policy_sha256=contract.policy_sha256,
        rows=tuple(rows),
        totals_by_classification=totals,
        implementation_additions=production.additions,
        implementation_deletions=production.deletions,
        base_physical_lines=production.base_physical_lines,
        candidate_postimage_physical_lines=(
            production.candidate_postimage_physical_lines
        ),
    )


def _expected_member_rows() -> list[dict[str, object]]:
    return [
        {
            "member_id": row.member_id,
            "path": row.path,
            "byte_count": row.byte_count,
            "sha256": row.sha256,
        }
        for row in A1_MEMBER_EXPECTATIONS
    ]


def _safe_member_path(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if (
        pure.is_absolute()
        or pure.as_posix() != relative
        or any(part in {"", ".", ".."} for part in pure.parts)
    ):
        raise CalibrationError(
            "a1_member_invalid", relative, "A1 member path is not canonical relative text"
        )
    current = root
    for index, part in enumerate(pure.parts):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as exc:
            raise CalibrationError(
                "a1_member_invalid", relative, "A1 member is missing or unreadable"
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise CalibrationError(
                "a1_member_invalid", relative, "A1 member path contains a symlink"
            )
        expected_directory = index < len(pure.parts) - 1
        if expected_directory and not stat.S_ISDIR(metadata.st_mode):
            raise CalibrationError(
                "a1_member_invalid", relative, "A1 member parent is not a directory"
            )
        if not expected_directory and not stat.S_ISREG(metadata.st_mode):
            raise CalibrationError(
                "a1_member_invalid", relative, "A1 member is not a regular file"
            )
    return current


def validate_a1_member_files(
    evidence_root: Path, members: Sequence[Mapping[str, object]]
) -> dict[str, bytes]:
    root = _canonical_root(Path(evidence_root), label="A1 evidence root")
    expected = _expected_member_rows()
    rendered = [dict(row) if isinstance(row, Mapping) else row for row in members]
    if rendered != expected:
        raise CalibrationError(
            "a1_member_invalid", rendered, "A1 member inventory or order drifted"
        )
    payloads: dict[str, bytes] = {}
    for row in expected:
        path = _safe_member_path(root, str(row["path"]))
        try:
            payload = path.read_bytes()
        except OSError as exc:
            raise CalibrationError(
                "a1_member_invalid", str(path), "A1 member is unreadable"
            ) from exc
        if len(payload) != row["byte_count"] or _sha256_bytes(payload) != row["sha256"]:
            raise CalibrationError(
                "a1_member_invalid",
                {
                    "member_id": row["member_id"],
                    "byte_count": len(payload),
                    "sha256": _sha256_bytes(payload),
                },
                "A1 member bytes drifted",
            )
        payloads[str(row["member_id"])] = payload
    return payloads


def _strict_object(payload: bytes, *, member_id: str) -> dict[str, Any]:
    value = _parse_json_bytes(payload, label=member_id)
    if not isinstance(value, dict):
        raise CalibrationError(
            "a1_binding_invalid", member_id, "A1 JSON member must be an object"
        )
    return value


def _require_a1(condition: bool, value: object, detail: str) -> None:
    if not condition:
        raise CalibrationError("a1_binding_invalid", value, detail)


def _expected_selection() -> dict[str, object]:
    return {
        "pilot_lock_sha256": A1_MEMBER_EXPECTATIONS[0].sha256,
        "block_id": "b-5970f312e6698e50",
        "block_record_sha256": A1_MEMBER_EXPECTATIONS[2].sha256,
        "arm_id": "arm-4301192e76f41f90",
        "treatment_id": "DIRECT",
        "lifecycle_outcome": "COMPLETED",
        "viability_case": "BOTH",
        "comparison": "DIRECT_VS_ORC",
        "method_outcome": "A_WIN",
        "product_quality_review_outcome": "A",
        "product_manifest_sha256": (
            "sha256:1ec8f066bc042a582b20059aeb6f45f21ae5f799def730b3a6ca8792e97bde7a"
        ),
        "review_result_sha256": [
            A1_MEMBER_EXPECTATIONS[11].sha256,
            A1_MEMBER_EXPECTATIONS[12].sha256,
        ],
    }


def _selected_candidate_wins(review: Mapping[str, Any], candidates: Sequence[str]) -> bool:
    selected = "candidate-3cca13b2595a"
    pairwise = review.get("pairwise_results")
    if not isinstance(pairwise, list):
        return False
    for competitor in candidates:
        if competitor == selected:
            continue
        matching = [
            row
            for row in pairwise
            if isinstance(row, dict)
            and {row.get("candidate_a_label"), row.get("candidate_b_label")}
            == {selected, competitor}
        ]
        if len(matching) != 1:
            return False
        row = matching[0]
        selected_is_a = row.get("candidate_a_label") == selected
        if row.get("outcome") != ("A" if selected_is_a else "B"):
            return False
    return True


def validate_a1_evidence_bindings(
    member_payloads: Mapping[str, bytes], selection: Mapping[str, object]
) -> None:
    expected_ids = {row.member_id for row in A1_MEMBER_EXPECTATIONS}
    _require_a1(
        set(member_payloads) == expected_ids,
        sorted(member_payloads),
        "A1 evidence payload set drifted",
    )
    _require_a1(
        dict(selection) == _expected_selection(), selection, "A1 selection record drifted"
    )
    pilot = _strict_object(member_payloads["pilot_lock"], member_id="pilot_lock")
    summary = _strict_object(member_payloads["summary"], member_id="summary")
    block = _strict_object(member_payloads["block_record"], member_id="block_record")
    package = _strict_object(
        member_payloads["package_manifest"], member_id="package_manifest"
    )
    reviews = (
        _strict_object(member_payloads["review_1"], member_id="review_1"),
        _strict_object(member_payloads["review_2"], member_id="review_2"),
    )

    pilot_review = pilot.get("review")
    pilot_task = pilot.get("task")
    _require_a1(
        pilot.get("record_kind") == "pilot_lock.v1"
        and isinstance(pilot_task, dict)
        and pilot_task.get("task_id") == "A1"
        and isinstance(pilot_review, dict)
        and pilot_review.get("reviewer_ids")
        == ["calibration-reviewer-01", "calibration-reviewer-02"]
        and pilot_review.get("selected_final_files") == ["torch_port/entrypoint.py"]
        and pilot.get("evidence_root") == str(A1_EVIDENCE_ROOT / "evidence"),
        pilot,
        "pilot lock does not bind the retained A1 review task",
    )
    _require_a1(
        summary.get("record_kind") == "pilot_summary.v1"
        and summary.get("pilot_lock_digest") == selection["pilot_lock_sha256"],
        summary,
        "summary does not bind the pilot lock",
    )
    valid_blocks = summary.get("valid_blocks")
    summary_blocks = (
        [
            row
            for row in valid_blocks
            if isinstance(row, dict) and row.get("block_id") == selection["block_id"]
        ]
        if isinstance(valid_blocks, list)
        else []
    )
    _require_a1(len(summary_blocks) == 1, valid_blocks, "summary block binding drifted")
    summary_block = summary_blocks[0]
    _require_a1(
        summary_block.get("block_attempt_digest") == selection["block_record_sha256"],
        summary_block,
        "summary block digest drifted",
    )
    method_rows = summary_block.get("method_outcomes")
    methods = (
        [
            row
            for row in method_rows
            if isinstance(row, dict)
            and row.get("comparison") == selection["comparison"]
        ]
        if isinstance(method_rows, list)
        else []
    )
    _require_a1(len(methods) == 1, method_rows, "summary method binding drifted")
    method = methods[0]
    review_summary = method.get("product_quality_review")
    _require_a1(
        method.get("viability_case") == selection["viability_case"]
        and method.get("method_outcome") == selection["method_outcome"]
        and isinstance(review_summary, dict)
        and review_summary.get("outcome")
        == selection["product_quality_review_outcome"]
        and review_summary.get("review_result_digests")
        == selection["review_result_sha256"],
        method,
        "summary comparison or review outcome drifted",
    )

    treatment_rows = block.get("treatment_executions")
    direct_rows = (
        [
            row
            for row in treatment_rows
            if isinstance(row, dict)
            and row.get("treatment_id") == selection["treatment_id"]
        ]
        if isinstance(treatment_rows, list)
        else []
    )
    _require_a1(
        block.get("record_kind") == "block_attempt.v1"
        and block.get("status") == "VALID"
        and block.get("block_id") == selection["block_id"]
        and block.get("pilot_lock_digest") == selection["pilot_lock_sha256"]
        and len(direct_rows) == 1,
        block,
        "block record binding drifted",
    )
    direct = direct_rows[0]
    _require_a1(
        direct.get("opaque_arm_label") == selection["arm_id"]
        and direct.get("lifecycle_outcome") == selection["lifecycle_outcome"]
        and direct.get("product_manifest_digest")
        == selection["product_manifest_sha256"]
        and direct.get("product_frozen") is True,
        direct,
        "DIRECT lifecycle or product binding drifted",
    )

    candidate_labels = package.get("candidate_labels")
    files = package.get("files")
    _require_a1(
        package.get("package_id") == selection["block_id"]
        and isinstance(candidate_labels, list)
        and len(candidate_labels) == len(set(candidate_labels)) == 3
        and "candidate-3cca13b2595a" in candidate_labels
        and isinstance(files, list),
        package,
        "package manifest binding drifted",
    )
    expected_package_files = {
        A1_MEMBER_EXPECTATIONS[4].path.split(
            "packages/b-5970f312e6698e50/b-5970f312e6698e50/", 1
        )[1]: A1_MEMBER_EXPECTATIONS[4],
        "candidates/candidate-3cca13b2595a/files/torch_port/entrypoint.py": (
            A1_MEMBER_EXPECTATIONS[8]
        ),
    }
    for relative, expected in expected_package_files.items():
        matching = [
            row
            for row in files
            if isinstance(row, dict) and row.get("path") == relative
        ]
        _require_a1(
            len(matching) == 1
            and matching[0].get("size") == expected.byte_count
            and matching[0].get("sha256") == expected.sha256,
            matching,
            "selected package file binding drifted",
        )

    reviewer_ids: list[str] = []
    session_ids: list[str] = []
    for review, expected_id, expected_sha in zip(
        reviews,
        ("calibration-reviewer-01", "calibration-reviewer-02"),
        selection["review_result_sha256"],
        strict=True,
    ):
        candidates = review.get("candidates")
        labels = (
            [row.get("opaque_label") for row in candidates if isinstance(row, dict)]
            if isinstance(candidates, list)
            else []
        )
        reviewer_id = review.get("reviewer_id")
        session_id = review.get("session_id")
        _require_a1(
            review.get("record_kind") == "review_result.v1"
            and review.get("review_class") == "LIVE"
            and review.get("pilot_lock_digest") == selection["pilot_lock_sha256"]
            and reviewer_id == expected_id
            and review.get("review_id") == f"{selection['block_id']}-{expected_id}"
            and isinstance(session_id, str)
            and session_id
            and labels == candidate_labels
            and _selected_candidate_wins(review, candidate_labels)
            and _sha256_bytes(member_payloads[f"review_{len(reviewer_ids) + 1}"])
            == expected_sha,
            review,
            "review identity, candidate set, or pairwise selection drifted",
        )
        reviewer_ids.append(reviewer_id)
        session_ids.append(session_id)
    _require_a1(
        len(set(reviewer_ids)) == 2 and len(set(session_ids)) == 2,
        {"reviewers": reviewer_ids, "sessions": session_ids},
        "A1 reviewers must have distinct identities and sessions",
    )


def _measure_a1(evidence_root: Path, git_contract: GitContract) -> ImplementationDelta:
    base = (
        evidence_root
        / "evaluation/b-5970f312e6698e50/base/torch_port"
    )
    candidate = (
        evidence_root
        / "evaluation/b-5970f312e6698e50/candidates/"
        "arm-4301192e76f41f90/torch_port"
    )
    policies = tuple(
        MetricPathPolicy(path, "production_python", (_A1_RESPONSIBILITY_ID,))
        for path in ("__init__.py", "entrypoint.py", "types.py")
    )
    result = measure_implementation_delta(
        base_root=base,
        candidate_root=candidate,
        path_policies=policies,
        allowed_responsibility_ids=frozenset({_A1_RESPONSIBILITY_ID}),
        git_contract=git_contract,
    )
    if (
        result.implementation_additions != 667
        or result.implementation_deletions != 2
        or result.base_physical_lines != 25
        or result.candidate_postimage_physical_lines != 690
    ):
        raise CalibrationError(
            "a1_metric_invalid",
            {
                "additions": result.implementation_additions,
                "deletions": result.implementation_deletions,
                "base_lines": result.base_physical_lines,
                "candidate_lines": result.candidate_postimage_physical_lines,
            },
            "fresh A1 measurement does not reproduce 667/2/25/690",
        )
    return result


def build_a1_anchor(
    *,
    evidence_root: Path,
    preedit_policy_sha256: str,
    git_contract: GitContract,
) -> dict[str, Any]:
    """Build, but do not publish, the closed retained A1 anchor record."""

    root = _canonical_root(Path(evidence_root), label="A1 evidence root")
    if root != A1_EVIDENCE_ROOT:
        raise CalibrationError(
            "a1_member_invalid", str(root), "A1 evidence root is not the frozen root"
        )
    if _SHA256_RE.fullmatch(preedit_policy_sha256) is None:
        raise CalibrationError(
            "a1_binding_invalid",
            preedit_policy_sha256,
            "pre-edit policy digest is malformed",
        )
    members = _expected_member_rows()
    payloads = validate_a1_member_files(root, members)
    selection = _expected_selection()
    validate_a1_evidence_bindings(payloads, selection)
    measurement = _measure_a1(root, git_contract)
    return seal_record(
        {
            "schema_version": "es_f1_a1_calibration_anchor.v1",
            "preedit_policy_sha256": preedit_policy_sha256,
            "evidence_root": str(root),
            "members": members,
            "selection": selection,
            "metric": {
                "metric_version": METRIC_VERSION,
                "git_contract_policy_sha256": git_contract.policy_sha256,
                "base_member_ids": ["base_entrypoint", "base_types", "base_init"],
                "candidate_member_ids": [
                    "direct_entrypoint",
                    "direct_types",
                    "direct_init",
                ],
                "patch_member_id": "direct_patch",
                "implementation_additions": measurement.implementation_additions,
                "implementation_deletions": measurement.implementation_deletions,
                "candidate_postimage_physical_lines": (
                    measurement.candidate_postimage_physical_lines
                ),
            },
        }
    )


def validate_a1_anchor(
    path: Path,
    *,
    schema_path: Path,
    expected_record_sha256: str,
    expected_preedit_policy_sha256: str,
    git_contract: GitContract,
) -> A1Calibration:
    """Validate one A1 anchor, all retained bytes, joins, and a fresh metric."""

    record = load_canonical_record(
        path,
        schema_path=schema_path,
        expected_record_sha256=expected_record_sha256,
    )
    if (
        record.get("preedit_policy_sha256") != expected_preedit_policy_sha256
        or _SHA256_RE.fullmatch(expected_preedit_policy_sha256) is None
    ):
        raise CalibrationError(
            "a1_binding_invalid",
            record.get("preedit_policy_sha256"),
            "A1 anchor binds a different pre-edit policy",
        )
    if record.get("evidence_root") != str(A1_EVIDENCE_ROOT):
        raise CalibrationError(
            "a1_member_invalid", record.get("evidence_root"), "A1 root drifted"
        )
    metric = record.get("metric")
    if not isinstance(metric, dict) or metric.get("git_contract_policy_sha256") != (
        git_contract.policy_sha256
    ):
        raise CalibrationError(
            "a1_binding_invalid", metric, "A1 Git policy binding drifted"
        )
    members = record.get("members")
    selection = record.get("selection")
    if not isinstance(members, list) or not isinstance(selection, dict):
        raise CalibrationError(
            "a1_binding_invalid", record, "A1 members or selection are malformed"
        )
    payloads = validate_a1_member_files(A1_EVIDENCE_ROOT, members)
    validate_a1_evidence_bindings(payloads, selection)
    measurement = _measure_a1(A1_EVIDENCE_ROOT, git_contract)
    observed_metric = {
        "metric_version": METRIC_VERSION,
        "git_contract_policy_sha256": git_contract.policy_sha256,
        "base_member_ids": ["base_entrypoint", "base_types", "base_init"],
        "candidate_member_ids": [
            "direct_entrypoint",
            "direct_types",
            "direct_init",
        ],
        "patch_member_id": "direct_patch",
        "implementation_additions": measurement.implementation_additions,
        "implementation_deletions": measurement.implementation_deletions,
        "candidate_postimage_physical_lines": (
            measurement.candidate_postimage_physical_lines
        ),
    }
    if metric != observed_metric:
        raise CalibrationError(
            "a1_metric_invalid", metric, "A1 record does not match fresh measurement"
        )
    return A1Calibration(record=record, measurement=measurement)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
_TASK0_EVIDENCE_RELATIVE = PurePosixPath(
    "docs/plans/evidence/es-f1-large-scope-refreeze"
)
_VALIDATE_A1_SCHEMA_PATHS = {
    "preedit_policy": _TASK0_EVIDENCE_RELATIVE
    / "preedit-policy-manifest.schema.json",
    "source_census": _TASK0_EVIDENCE_RELATIVE / "source-census.schema.json",
    "review_adoption": _TASK0_EVIDENCE_RELATIVE
    / "task0-review-adoption.schema.json",
    "a1_anchor": _TASK0_EVIDENCE_RELATIVE / "a1-calibration-anchor.schema.json",
}
_REFERENCE_TOP_LEVEL_FIELDS = (
    "schema_version",
    "bindings",
    "lineage",
    "repository",
    "evidence_store",
    "patch",
    "metric",
    "structural_scope",
    "evaluator_evidence",
    "desired_state_proofs",
    "bypass_oracle",
    "no_delivery",
    "record_sha256",
)
_REFERENCE_BINDINGS = {
    "preedit_policy": (
        _TASK0_EVIDENCE_RELATIVE / "preedit-policy-manifest.json",
        _TASK0_EVIDENCE_RELATIVE / "preedit-policy-manifest.schema.json",
    ),
    "source_census": (
        _TASK0_EVIDENCE_RELATIVE / "source-census.json",
        _TASK0_EVIDENCE_RELATIVE / "source-census.schema.json",
    ),
    "selector_manifest": (
        _TASK0_EVIDENCE_RELATIVE / "preedit-selector-manifest.json",
        _TASK0_EVIDENCE_RELATIVE / "preedit-selector-manifest.schema.json",
    ),
    "task0_review_adoption": (
        _TASK0_EVIDENCE_RELATIVE / "task0-review-adoption.json",
        _TASK0_EVIDENCE_RELATIVE / "task0-review-adoption.schema.json",
    ),
    "a1_anchor": (
        _TASK0_EVIDENCE_RELATIVE / "a1-calibration-anchor.json",
        _TASK0_EVIDENCE_RELATIVE / "a1-calibration-anchor.schema.json",
    ),
    "task_seed_manifest": (
        PurePosixPath("experiments/orc_effectiveness/f1_es/task-seed-manifest.json"),
        PurePosixPath(
            "experiments/orc_effectiveness/f1_es/task-seed-manifest.schema.json"
        ),
    ),
    "visible_task_contract": (
        PurePosixPath(
            "experiments/orc_effectiveness/f1_es/task/visible-task-contract.json"
        ),
        PurePosixPath(
            "experiments/orc_effectiveness/f1_es/task/visible-task-contract.schema.json"
        ),
    ),
    "evaluator_fixture_manifest": (
        PurePosixPath(
            "experiments/orc_effectiveness/f1_es/evaluator/fixture-manifest.json"
        ),
        None,
    ),
    "governing_plan": (
        PurePosixPath(
            "docs/plans/2026-08-03-es-f1-large-scope-refreeze-execution-plan.md"
        ),
        None,
    ),
    "reference_calibration": (
        PurePosixPath("scripts/experiments/es/reference_calibration.py"),
        None,
    ),
    "f1_evaluator": (
        PurePosixPath("scripts/experiments/es/f1_evaluator.py"),
        None,
    ),
    "boundary_proof_runner": (
        PurePosixPath("scripts/experiments/es/boundary_proofs.py"),
        None,
    ),
}
_REFERENCE_SELF_DIGEST_BINDINGS = frozenset(
    {
        "preedit_policy",
        "source_census",
        "selector_manifest",
        "task0_review_adoption",
        "a1_anchor",
    }
)
_REFERENCE_CAS_MEMBER_IDS = (
    "canonical_patch",
    "candidate_evidence",
    "visible_check_result",
    "registry_signature_report",
    "artifact_fixture_verification",
    "lifecycle_result",
    "hard_evaluation",
    "bypass_discovery",
    "bypass_classification",
    "no_delivery_report",
)
_REFERENCE_REF = "refs/heads/reference-product"
_BOUNDARY_PROOF_RUNNER_SHA256 = (
    "sha256:d2a8d0a2c6c0e542bf8e2835f3b274527e638287e35239954e29b185a33e0b85"
)
_REFERENCE_CLASSIFICATIONS = (
    "benchmark_task_seed_asset",
    "documentation",
    "fixture",
    "production_python",
    "test",
    "vendored",
)
_REFERENCE_HARD_EVIDENCE = (
    ("F1-H01-FOCUSED-SUITES", ("visible_check_result",)),
    ("F1-H02-SCHEMA-CONFORMANCE", ("candidate_evidence", "lifecycle_result")),
    ("F1-H03-BUILTIN-SIGNATURES", ("registry_signature_report",)),
    ("F1-H04-ARTIFACT-ERA-COMPATIBILITY", ("artifact_fixture_verification",)),
    (
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
        ("lifecycle_result", "bypass_classification"),
    ),
    ("F1-H06-STRUCTURAL-ROUNDTRIP", ("lifecycle_result",)),
    ("F1-H07-STRUCTURAL-IDENTITY-REJECTION", ("lifecycle_result",)),
    ("F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY", ("lifecycle_result",)),
    (
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
        ("lifecycle_result", "registry_signature_report"),
    ),
    ("F1-H10-OWNERSHIP-BOUNDARY", ("lifecycle_result",)),
)
_REFERENCE_INTEGRATION_CHAIN_PATHS = (
    "ptycho_torch/extension_identity.py",
    "ptycho_torch/generators/extension_adapter.py",
    "ptycho_torch/extension_persistence.py",
    "ptycho_torch/extension_inference.py",
)
_REFERENCE_EDGE_STATIC_SPECS = {
    "01_identity_config_to_construction_adapters": {
        "producer_path": _REFERENCE_INTEGRATION_CHAIN_PATHS[0],
        "consumer_path": _REFERENCE_INTEGRATION_CHAIN_PATHS[1],
        "imported_binding": "ExtensionIdentity",
        "producer_owner": "ExtensionIdentity",
        "producer_name": "from_config",
        "resolved_symbol": "ExtensionIdentity.from_config",
    },
    "02_construction_adapters_to_persistence_rebuild": {
        "producer_path": "ptycho_torch/generators/registry.py",
        "consumer_path": _REFERENCE_INTEGRATION_CHAIN_PATHS[2],
        "imported_binding": "resolve_generator",
        "producer_owner": None,
        "producer_name": "resolve_generator",
        "resolved_symbol": "resolve_generator",
    },
    "03_persistence_rebuild_to_inference_workflows": {
        "producer_path": _REFERENCE_INTEGRATION_CHAIN_PATHS[2],
        "consumer_path": _REFERENCE_INTEGRATION_CHAIN_PATHS[3],
        "imported_binding": "load_extension_checkpoint",
        "producer_owner": None,
        "producer_name": "load_extension_checkpoint",
        "resolved_symbol": "load_extension_checkpoint",
    },
}
_REFERENCE_EDGE_LIFECYCLE_CLAUSES = {
    "01_identity_config_to_construction_adapters": (
        "F1-H08-STRUCTURAL-IDENTITY-SENSITIVITY",
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
    ),
    "02_construction_adapters_to_persistence_rebuild": (
        "F1-H09-CONSTRUCTION-REBUILD-EQUALITY",
    ),
    "03_persistence_rebuild_to_inference_workflows": (
        "F1-H05-FULL-ARCHITECTURE-LIFECYCLE",
    ),
}
_REFERENCE_EDGE_EVIDENCE_KIND = (
    "static_import_call_resolution_with_lifecycle_conformance"
)
_REFERENCE_EDGE_EVIDENCE_SEMANTICS = (
    "STATIC_IMPORT_CALL_RESOLUTION_PLUS_LIFECYCLE_CONFORMANCE_"
    "NOT_FUNCTION_LEVEL_RUNTIME_TRACE"
)
_REFERENCE_DOCUMENTATION_PATH = "benchmark/es_f1/reference-product-notes.md"
_REFERENCE_TREATMENT_PROMPT = PurePosixPath(
    "workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc"
)
_REFERENCE_PROMPT_EXTERNS = _REFERENCE_TREATMENT_PROMPT.with_name("prompts.json")
_REFERENCE_EVALUATOR_RUBRIC = (
    _REFERENCE_TREATMENT_PROMPT.parent / "prompts" / "trial_rubric.md"
)
_REFERENCE_LOGICAL_OUTER_ARGV = (
    "codex",
    "exec",
    "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check",
    "--model",
    "gpt-5.5",
    "--config",
    "reasoning_effort=high",
)
_REFERENCE_LOGICAL_METERED_ARGV = (
    "/opt/codex",
    "exec",
    "--json",
    "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check",
    "--model",
    "gpt-5.5",
    "--config",
    "model_reasoning_effort=high",
    "--",
    "-",
)
_REFERENCE_PRODUCT_VALIDATION_PROVENANCE = object()


def _reference_fail(code: str, value: object, detail: str) -> NoReturn:
    raise CalibrationError(code, value, detail)


def _normalize_reference_publication_observations(
    derived_observations: Sequence[Mapping[str, Any]],
    *,
    cas_member_sha256_by_id: Mapping[str, str],
) -> list[dict[str, Any]]:
    """Bind derived evaluator facts to the ordered published CAS members."""

    expected_clause_ids = tuple(
        clause_id for clause_id, _ in _REFERENCE_HARD_EVIDENCE
    )
    expected_member_ids = set(_REFERENCE_CAS_MEMBER_IDS) - {"hard_evaluation"}
    if (
        not isinstance(derived_observations, Sequence)
        or isinstance(derived_observations, (str, bytes, bytearray))
        or not isinstance(cas_member_sha256_by_id, Mapping)
        or set(cas_member_sha256_by_id) != expected_member_ids
        or any(
            not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None
            for digest in cas_member_sha256_by_id.values()
        )
    ):
        _reference_fail(
            "reference_publication_invalid",
            cas_member_sha256_by_id,
            "publication CAS digest domain is not exact",
        )
    if len(derived_observations) != len(expected_clause_ids):
        _reference_fail(
            "reference_publication_invalid",
            derived_observations,
            "derived hard-clause domain is incomplete",
        )

    hard_evidence = dict(_REFERENCE_HARD_EVIDENCE)
    normalized: list[dict[str, Any]] = []
    for expected_clause_id, raw in zip(
        expected_clause_ids, derived_observations, strict=True
    ):
        if (
            not isinstance(raw, Mapping)
            or set(raw) != {"clause_id", "satisfied", "evidence", "details"}
            or raw.get("clause_id") != expected_clause_id
            or type(raw.get("satisfied")) is not bool
            or not isinstance(raw.get("details"), str)
            or not isinstance(raw.get("evidence"), list)
            or not raw["evidence"]
            or any(
                not isinstance(digest, str)
                or _SHA256_RE.fullmatch(digest) is None
                for digest in raw["evidence"]
            )
        ):
            _reference_fail(
                "reference_publication_invalid",
                raw,
                "derived hard-clause observation is not exact",
            )
        normalized.append(
            {
                "clause_id": expected_clause_id,
                "satisfied": raw["satisfied"],
                "evidence": [
                    cas_member_sha256_by_id[member_id]
                    for member_id in hard_evidence[expected_clause_id]
                ],
                "details": raw["details"],
            }
        )
    return normalized


def _reference_relative_path(value: object, *, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        _reference_fail("reference_binding_invalid", value, f"{label} is empty")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or path.as_posix() != value
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        _reference_fail(
            "reference_binding_invalid", value, f"{label} is not canonical relative text"
        )
    return path


def _read_regular_file(path: Path, *, code: str, label: str) -> bytes:
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise CalibrationError(code, str(path), f"{label} is missing or unreadable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        _reference_fail(code, str(path), f"{label} must be a regular non-symlink file")
    return raw


def _load_reference_authorities(
    record: Mapping[str, object],
) -> dict[str, dict[str, Any]]:
    bindings = record.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != set(_REFERENCE_BINDINGS):
        _reference_fail(
            "reference_binding_invalid", bindings, "reference authority domain is not exact"
        )
    loaded: dict[str, dict[str, Any]] = {}
    for binding_id, (expected_relative, expected_schema_relative) in (
        _REFERENCE_BINDINGS.items()
    ):
        binding = bindings[binding_id]
        if not isinstance(binding, dict):
            _reference_fail(
                "reference_binding_invalid", binding, f"{binding_id} binding is not an object"
            )
        relative = _reference_relative_path(
            binding.get("path"), label=f"{binding_id}.path"
        )
        if relative != expected_relative:
            _reference_fail(
                "reference_binding_invalid", str(relative), f"{binding_id} path drifted"
            )
        path = _REPOSITORY_ROOT / relative
        raw = _read_regular_file(
            path, code="reference_binding_invalid", label=binding_id
        )
        if binding.get("sha256") != _sha256_bytes(raw):
            _reference_fail(
                "reference_binding_invalid", binding, f"{binding_id} raw digest drifted"
            )
        if expected_schema_relative is None:
            if set(binding) != {"path", "sha256"}:
                _reference_fail(
                    "reference_binding_invalid",
                    binding,
                    f"{binding_id} binding fields are not exact",
                )
            if path.suffix == ".json":
                value = _parse_json_bytes(raw, label=path)
                if not isinstance(value, dict):
                    _reference_fail(
                        "reference_binding_invalid", value, f"{binding_id} is not an object"
                    )
                loaded[binding_id] = value
            continue
        expected_fields = {"path", "sha256", "schema_path", "schema_sha256"}
        if binding_id in _REFERENCE_SELF_DIGEST_BINDINGS:
            expected_fields.add("record_sha256")
        if set(binding) != expected_fields:
            _reference_fail(
                "reference_binding_invalid",
                binding,
                f"{binding_id} record binding fields are not exact",
            )
        schema_relative = _reference_relative_path(
            binding.get("schema_path"), label=f"{binding_id}.schema_path"
        )
        if schema_relative != expected_schema_relative:
            _reference_fail(
                "reference_binding_invalid",
                str(schema_relative),
                f"{binding_id} schema path drifted",
            )
        schema_path = _REPOSITORY_ROOT / schema_relative
        schema_raw = _read_regular_file(
            schema_path,
            code="reference_binding_invalid",
            label=f"{binding_id} schema",
        )
        if binding.get("schema_sha256") != _sha256_bytes(schema_raw):
            _reference_fail(
                "reference_binding_invalid", binding, f"{binding_id} schema digest drifted"
            )
        if binding_id in _REFERENCE_SELF_DIGEST_BINDINGS:
            loaded[binding_id] = load_canonical_record(
                path,
                schema_path=schema_path,
                expected_record_sha256=str(binding.get("record_sha256")),
            )
        else:
            value = _parse_json_bytes(raw, label=path)
            schema = _parse_json_bytes(schema_raw, label=schema_path)
            if (
                not isinstance(value, dict)
                or raw != canonical_json_bytes(value)
                or not isinstance(schema, dict)
            ):
                _reference_fail(
                    "reference_binding_invalid",
                    binding,
                    f"{binding_id} is not canonical schema-bound JSON",
                )
            try:
                Draft202012Validator.check_schema(schema)
                errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
            except Exception as exc:
                raise CalibrationError(
                    "reference_binding_invalid",
                    binding_id,
                    "bound authority schema validation failed",
                ) from exc
            if errors:
                _reference_fail(
                    "reference_binding_invalid",
                    binding,
                    f"{binding_id} does not match its bound schema",
                )
            loaded[binding_id] = value

    policy = loaded["preedit_policy"]
    census = loaded["source_census"]
    selector = loaded["selector_manifest"]
    anchor = loaded["a1_anchor"]
    adoption = loaded["task0_review_adoption"]
    if census.get("preedit_policy_sha256") != policy.get("record_sha256"):
        _reference_fail(
            "reference_binding_invalid", census, "source census policy join drifted"
        )
    if (
        selector.get("preedit_policy_sha256") != policy.get("record_sha256")
        or selector.get("source_census_sha256") != census.get("record_sha256")
    ):
        _reference_fail(
            "reference_binding_invalid", selector, "selector authority join drifted"
        )
    if anchor.get("preedit_policy_sha256") != policy.get("record_sha256"):
        _reference_fail(
            "reference_binding_invalid", anchor, "A1 policy join drifted"
        )
    _validate_task0_review_adoption(
        adoption,
        policy=policy,
        census=census,
        anchor=anchor,
    )
    return loaded


def _reference_git(repository: Path, *args: str, input_bytes: bytes | None = None) -> bytes:
    try:
        completed = subprocess.run(
            (str(PINNED_GIT_EXECUTABLE), "-C", str(repository), *args),
            input=input_bytes,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CalibrationError(
            "reference_repository_invalid",
            {"repository": str(repository), "args": args},
            "bound Git query failed",
        ) from exc
    return completed.stdout


def _canonical_directory(path_value: object, *, label: str) -> Path:
    if not isinstance(path_value, str):
        _reference_fail("reference_repository_invalid", path_value, f"{label} is not text")
    path = Path(path_value)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise CalibrationError(
            "reference_repository_invalid", str(path), f"{label} is unreadable"
        ) from exc
    if (
        not path.is_absolute()
        or resolved != path
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISDIR(metadata.st_mode)
    ):
        _reference_fail(
            "reference_repository_invalid", str(path), f"{label} is not a canonical directory"
        )
    return path


def _canonical_regular_file(path_value: Path, *, label: str) -> Path:
    candidate = Path(path_value)
    try:
        metadata = candidate.lstat()
        resolved = candidate.resolve(strict=True)
        resolved_metadata = resolved.lstat()
    except OSError as exc:
        raise CalibrationError(
            "reference_product_invalid", str(candidate), f"{label} is unreadable"
        ) from exc
    if (
        stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not stat.S_ISREG(resolved_metadata.st_mode)
    ):
        _reference_fail(
            "reference_product_invalid",
            str(candidate),
            f"{label} must be a regular non-symlink file",
        )
    return resolved


def _validate_reference_repository(
    record: Mapping[str, object], authorities: Mapping[str, dict[str, Any]]
) -> Path:
    lineage = record.get("lineage")
    repository_record = record.get("repository")
    if not isinstance(lineage, dict) or set(lineage) != {
        "projection_commit",
        "projection_tree",
        "task_seed_commit",
        "task_seed_tree",
        "reference_commit",
        "reference_tree",
    }:
        _reference_fail("reference_repository_invalid", lineage, "lineage is not exact")
    if not isinstance(repository_record, dict) or set(repository_record) != {
        "storage_root",
        "relative_path",
        "locator",
        "head_ref",
        "object_format",
        "commit_count",
        "object_count",
        "unreachable_object_count",
        "repository_snapshot_sha256",
    }:
        _reference_fail(
            "reference_repository_invalid", repository_record, "repository record is not exact"
        )
    storage_root = _canonical_directory(
        repository_record["storage_root"], label="reference storage root"
    )
    repository = _canonical_directory(
        repository_record["locator"], label="reference bare repository"
    )
    relative = _reference_relative_path(
        repository_record["relative_path"], label="repository.relative_path"
    )
    if (
        relative != PurePosixPath("git-sha1") / str(lineage["reference_commit"])
        or repository != storage_root / relative
        or repository_record["head_ref"] != _REFERENCE_REF
        or repository_record["object_format"] != "sha1"
        or repository_record["commit_count"] != 3
        or repository_record["unreachable_object_count"] != 0
    ):
        _reference_fail(
            "reference_repository_invalid", repository_record, "content-addressed repository binding drifted"
        )
    task_seed = authorities["task_seed_manifest"]
    recipe = task_seed.get("recipe")
    projection = task_seed.get("parent_projection")
    if not isinstance(recipe, dict) or not isinstance(projection, dict) or lineage != {
        "projection_commit": projection.get("commit"),
        "projection_tree": projection.get("tree"),
        "task_seed_commit": recipe.get("commit"),
        "task_seed_tree": recipe.get("tree"),
        "reference_commit": lineage.get("reference_commit"),
        "reference_tree": lineage.get("reference_tree"),
    }:
        _reference_fail(
            "reference_repository_invalid", lineage, "task-seed lineage join drifted"
        )
    if _reference_git(repository, "rev-parse", "--is-bare-repository") != b"true\n":
        _reference_fail(
            "reference_repository_invalid", str(repository), "reference repository is not bare"
        )
    if _reference_git(repository, "remote") != b"":
        _reference_fail(
            "reference_repository_invalid", str(repository), "reference repository has remotes"
        )
    refs = _reference_git(
        repository, "for-each-ref", "--format=%(refname) %(objectname)"
    ).decode("ascii").splitlines()
    if refs != [f"{_REFERENCE_REF} {lineage['reference_commit']}"]:
        _reference_fail("reference_repository_invalid", refs, "reference ref domain drifted")
    history = _reference_git(
        repository, "rev-list", "--parents", "--topo-order", "--all"
    ).decode("ascii").splitlines()
    if history != [
        f"{lineage['reference_commit']} {lineage['task_seed_commit']}",
        f"{lineage['task_seed_commit']} {lineage['projection_commit']}",
        str(lineage["projection_commit"]),
    ]:
        _reference_fail(
            "reference_repository_invalid", history, "reference history is not the exact three-commit lineage"
        )
    for commit_key, tree_key in (
        ("projection_commit", "projection_tree"),
        ("task_seed_commit", "task_seed_tree"),
        ("reference_commit", "reference_tree"),
    ):
        observed = _reference_git(
            repository, "rev-parse", f"{lineage[commit_key]}^{{tree}}"
        ).decode("ascii").strip()
        if observed != lineage[tree_key]:
            _reference_fail(
                "reference_repository_invalid", observed, f"{commit_key} tree drifted"
            )
    task_package = __import__(
        "scripts.experiments.es.task_package", fromlist=["task_package"]
    )
    if task_package.directory_snapshot_digest(repository) != repository_record[
        "repository_snapshot_sha256"
    ]:
        _reference_fail(
            "reference_repository_invalid", str(repository), "repository snapshot drifted"
        )
    object_rows = _reference_git(
        repository,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype)",
    ).splitlines()
    reachable = {
        line.split(b" ", 1)[0]
        for line in _reference_git(repository, "rev-list", "--objects", "--all").splitlines()
    }
    all_objects = {line.split(b" ", 1)[0] for line in object_rows}
    if (
        all_objects != reachable
        or repository_record["object_count"] != len(object_rows)
    ):
        _reference_fail(
            "reference_repository_invalid", repository_record, "repository object closure drifted"
        )
    return repository


def _load_reference_cas(
    record: Mapping[str, object], repository: Path
) -> tuple[Path, dict[str, bytes]]:
    store = record.get("evidence_store")
    if not isinstance(store, dict) or set(store) != {"algorithm", "root", "members"}:
        _reference_fail("reference_evidence_invalid", store, "evidence store is not exact")
    root = _canonical_directory(store["root"], label="reference evidence store")
    try:
        root.relative_to(repository)
    except ValueError:
        pass
    else:
        _reference_fail(
            "reference_evidence_invalid", str(root), "evidence store is inside the bare repository"
        )
    members = store.get("members")
    if (
        store.get("algorithm") != "sha256"
        or not isinstance(members, list)
        or [row.get("member_id") if isinstance(row, dict) else None for row in members]
        != list(_REFERENCE_CAS_MEMBER_IDS)
    ):
        _reference_fail("reference_evidence_invalid", store, "CAS member domain is not exact")
    payloads: dict[str, bytes] = {}
    seen_paths: set[str] = set()
    for row in members:
        if not isinstance(row, dict) or set(row) != {
            "member_id",
            "cas_relative_path",
            "byte_count",
            "sha256",
        }:
            _reference_fail("reference_evidence_invalid", row, "CAS member row is not exact")
        digest = row["sha256"]
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            _reference_fail("reference_evidence_invalid", row, "CAS member digest is malformed")
        relative = _reference_relative_path(
            row["cas_relative_path"], label=f"CAS {row['member_id']} path"
        )
        expected_relative = PurePosixPath(digest.removeprefix("sha256:")) / "payload"
        if relative != expected_relative or relative.as_posix() in seen_paths:
            _reference_fail("reference_evidence_invalid", row, "CAS path is not content addressed")
        seen_paths.add(relative.as_posix())
        member_path = root
        try:
            for ordinal, part in enumerate(relative.parts):
                member_path /= part
                metadata = member_path.lstat()
                if stat.S_ISLNK(metadata.st_mode):
                    _reference_fail(
                        "reference_evidence_invalid",
                        str(member_path),
                        "CAS member path contains a symlink",
                    )
                if ordinal < len(relative.parts) - 1 and not stat.S_ISDIR(
                    metadata.st_mode
                ):
                    _reference_fail(
                        "reference_evidence_invalid",
                        str(member_path),
                        "CAS member parent component is not a directory",
                    )
            resolved_member = member_path.resolve(strict=True)
            resolved_member.relative_to(root)
        except CalibrationError:
            raise
        except (OSError, ValueError) as exc:
            raise CalibrationError(
                "reference_evidence_invalid",
                str(member_path),
                "CAS member path is unreadable or escapes its canonical root",
            ) from exc
        if resolved_member != member_path:
            _reference_fail(
                "reference_evidence_invalid",
                str(member_path),
                "CAS member does not resolve to its canonical root-relative path",
            )
        payload = _read_regular_file(
            member_path,
            code="reference_evidence_invalid",
            label=f"CAS member {row['member_id']}",
        )
        if len(payload) != row["byte_count"] or _sha256_bytes(payload) != digest:
            _reference_fail("reference_evidence_invalid", row, "CAS payload binding drifted")
        payloads[row["member_id"]] = payload
    return root, payloads


def _validate_reference_patch(
    record: Mapping[str, object], repository: Path, payloads: Mapping[str, bytes]
) -> None:
    patch = record.get("patch")
    lineage = record["lineage"]
    expected_argv = [
        str(PINNED_GIT_EXECUTABLE),
        "-C",
        str(repository),
        "diff",
        "--patch",
        "--binary",
        "--full-index",
        "--no-color",
        "--src-prefix=a/",
        "--dst-prefix=b/",
        *PINNED_GIT_DIFF_CONTROLS,
        lineage["task_seed_commit"],
        lineage["reference_commit"],
        "--",
    ]
    if not isinstance(patch, dict) or patch != {
        "member_id": "canonical_patch",
        "format": "git-diff-binary-full-index.v1",
        "base": lineage["task_seed_commit"],
        "target": lineage["reference_commit"],
        "argv": expected_argv,
    }:
        _reference_fail("reference_patch_invalid", patch, "canonical patch binding drifted")
    try:
        observed = subprocess.run(
            expected_argv,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CalibrationError(
            "reference_patch_invalid", expected_argv, "canonical patch replay failed"
        ) from exc
    if observed != payloads["canonical_patch"]:
        _reference_fail("reference_patch_invalid", patch, "canonical patch bytes drifted")


def _reference_tree_entries(repository: Path, tree: str) -> dict[str, dict[str, Any]]:
    raw = _reference_git(repository, "ls-tree", "-r", "-z", "--full-tree", tree)
    rows: dict[str, dict[str, Any]] = {}
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            raw_mode, object_type, object_id = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8", errors="strict")
            mode = int(raw_mode, 8)
        except (ValueError, UnicodeDecodeError) as exc:
            raise CalibrationError(
                "reference_metric_invalid", entry, "Git tree entry is malformed"
            ) from exc
        if path in rows:
            _reference_fail("reference_metric_invalid", path, "Git tree path duplicated")
        rows[path] = {
            "mode": mode,
            "object_type": object_type.decode("ascii"),
            "object_id": object_id.decode("ascii"),
        }
    return rows


def _reference_strict_text_tree(
    repository: Path, entries: Mapping[str, Mapping[str, Any]]
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for path, entry in entries.items():
        if entry["object_type"] != "blob" or entry["mode"] not in {0o100644, 0o100755}:
            continue
        payload = _reference_git(repository, "cat-file", "blob", entry["object_id"])
        try:
            payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            continue
        if b"\0" in payload:
            continue
        rows[path] = {**entry, "payload": payload, "mode": entry["mode"] & 0o777}
    return rows


def _write_metric_tree(root: Path, rows: Mapping[str, Mapping[str, Any]]) -> None:
    for relative, row in rows.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(row["payload"])
        target.chmod(row["mode"])


def _normalized_python_ast(payload: bytes) -> str:
    try:
        tree = ast.parse(payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise CalibrationError(
            "reference_metric_invalid", None, "production Python is not parseable"
        ) from exc
    body = list(tree.body)
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]
    normalized = ast.Module(body=body, type_ignores=[])
    return ast.dump(normalized, annotate_fields=True, include_attributes=False)


def _serialize_delta(measurement: ImplementationDelta) -> dict[str, Any]:
    return json.loads(canonical_json_bytes(asdict(measurement)))


def _validate_reference_metric(
    record: Mapping[str, object],
    *,
    repository: Path,
    authorities: Mapping[str, dict[str, Any]],
) -> None:
    metric = record.get("metric")
    lineage = record["lineage"]
    scope = record.get("structural_scope")
    if not isinstance(metric, dict) or set(metric) != {
        "metric_version",
        "git_contract_policy_sha256",
        "rows",
        "totals_by_classification",
        "implementation_additions",
        "implementation_deletions",
        "base_physical_lines",
        "candidate_postimage_physical_lines",
    }:
        _reference_fail("reference_metric_invalid", metric, "metric record is not exact")
    policy = authorities["preedit_policy"]
    census = authorities["source_census"]
    if (
        metric.get("metric_version") != METRIC_VERSION
        or metric.get("git_contract_policy_sha256") != policy.get("record_sha256")
    ):
        _reference_fail("reference_metric_invalid", metric, "metric authority drifted")
    if not isinstance(scope, dict):
        _reference_fail("reference_metric_invalid", scope, "structural scope is absent")
    responsibility_domain = {
        row["responsibility_id"]
        for row in policy.get("responsibilities", [])
        if isinstance(row, dict) and isinstance(row.get("responsibility_id"), str)
    }
    cluster_domain = scope.get("cluster_domain")
    if not isinstance(cluster_domain, list) or len(cluster_domain) != len(set(cluster_domain)):
        _reference_fail("reference_metric_invalid", cluster_domain, "cluster domain is malformed")
    census_leaves = {
        row["path"]: row
        for row in census.get("leaf_rows", [])
        if isinstance(row, dict) and isinstance(row.get("path"), str)
    }
    rows = metric.get("rows")
    if not isinstance(rows, list) or not rows:
        _reference_fail("reference_metric_invalid", rows, "metric rows are absent")
    expected_row_fields = {
        "base_path",
        "candidate_path",
        "base_blob_id",
        "candidate_blob_id",
        "base_mode",
        "candidate_mode",
        "base_physical_lines",
        "candidate_physical_lines",
        "additions",
        "deletions",
        "change_kind",
        "classification",
        "responsibility_ids",
        "cluster_ids",
    }
    by_path: dict[str, dict[str, Any]] = {}
    policies: list[MetricPathPolicy] = []
    for value in rows:
        if not isinstance(value, dict) or set(value) != expected_row_fields:
            _reference_fail("reference_metric_invalid", value, "metric row is not exact")
        path = value.get("candidate_path") or value.get("base_path")
        if not isinstance(path, str) or path in by_path:
            _reference_fail("reference_metric_invalid", value, "metric path domain is not unique")
        by_path[path] = value
        classification = value.get("classification")
        responsibilities = value.get("responsibility_ids")
        clusters = value.get("cluster_ids")
        if classification not in _REFERENCE_CLASSIFICATIONS:
            _reference_fail("reference_metric_invalid", value, "metric classification is invalid")
        if not isinstance(responsibilities, list) or len(responsibilities) != len(
            set(responsibilities)
        ):
            _reference_fail("reference_metric_invalid", value, "responsibility assignment is invalid")
        if not isinstance(clusters, list) or len(clusters) != len(set(clusters)):
            _reference_fail("reference_metric_invalid", value, "cluster assignment is invalid")
        if classification == "production_python":
            if (
                not responsibilities
                or not clusters
                or not set(responsibilities) <= responsibility_domain
                or not set(clusters) <= set(cluster_domain)
            ):
                _reference_fail(
                    "reference_metric_invalid", value, "production assignments are incomplete"
                )
            if path in census_leaves and responsibilities != sorted(
                census_leaves[path]["responsibility_ids"]
            ):
                _reference_fail(
                    "reference_metric_invalid", value, "existing production responsibilities drifted"
                )
        elif responsibilities or clusters:
            _reference_fail(
                "reference_metric_invalid", value, "nonproduction path carries assignments"
            )
        if (
            classification == "benchmark_task_seed_asset"
            and value.get("change_kind") != "unchanged"
        ):
            _reference_fail(
                "reference_metric_invalid", value, "task-seed asset changed outside explicit scope"
            )
        policies.append(
            MetricPathPolicy(path, classification, tuple(responsibilities))
        )

    base_entries = _reference_tree_entries(repository, lineage["task_seed_tree"])
    candidate_entries = _reference_tree_entries(repository, lineage["reference_tree"])
    base_text = _reference_strict_text_tree(repository, base_entries)
    candidate_text = _reference_strict_text_tree(repository, candidate_entries)
    text_domain = set(base_text) | set(candidate_text)
    if set(by_path) != text_domain:
        _reference_fail(
            "reference_metric_invalid",
            {"record": sorted(by_path), "tree": sorted(text_domain)},
            "metric does not cover the complete strict-text tree projection",
        )
    unsupported_domain = (set(base_entries) | set(candidate_entries)) - text_domain
    if any(base_entries.get(path) != candidate_entries.get(path) for path in unsupported_domain):
        _reference_fail(
            "reference_metric_invalid", sorted(unsupported_domain), "unsupported tree leaf changed"
        )
    with tempfile.TemporaryDirectory(prefix=".es-reference-metric.") as temporary:
        root = Path(temporary)
        base_root = root / "base"
        candidate_root = root / "candidate"
        base_root.mkdir()
        candidate_root.mkdir()
        _write_metric_tree(base_root, base_text)
        _write_metric_tree(candidate_root, candidate_text)
        policy_metric = policy["a1"]["metric"]
        contract = GitContract(
            executable=Path(policy_metric["git_executable"]),
            version=str(policy_metric["git_version"]).removeprefix("git version "),
            executable_sha256=policy_metric["git_sha256"],
            diff_controls=tuple(policy_metric["diff_controls"]),
            policy_sha256=policy["record_sha256"],
        )
        measurement = measure_implementation_delta(
            base_root=base_root,
            candidate_root=candidate_root,
            path_policies=tuple(policies),
            allowed_responsibility_ids=frozenset(responsibility_domain),
            git_contract=contract,
        )
    observed = _serialize_delta(measurement)
    zero = {
        "additions": 0,
        "deletions": 0,
        "base_physical_lines": 0,
        "candidate_postimage_physical_lines": 0,
    }
    observed["totals_by_classification"] = {
        classification: observed["totals_by_classification"].get(
            classification, copy.deepcopy(zero)
        )
        for classification in _REFERENCE_CLASSIFICATIONS
    }
    for observed_row in observed["rows"]:
        path = observed_row.get("candidate_path") or observed_row.get("base_path")
        observed_row["cluster_ids"] = copy.deepcopy(by_path[path]["cluster_ids"])
    if observed != metric:
        _reference_fail("reference_metric_invalid", metric, "metric replay drifted")
    additions = metric["implementation_additions"]
    if not isinstance(additions, int) or not 5_000 <= additions <= 10_000:
        _reference_fail("reference_metric_invalid", additions, "reference scale is out of band")
    for row in rows:
        if row["classification"] != "production_python" or row["change_kind"] == "unchanged":
            continue
        base_path = row["base_path"]
        candidate_path = row["candidate_path"]
        if candidate_path is None:
            continue
        candidate_ast = _normalized_python_ast(candidate_text[candidate_path]["payload"])
        if base_path is None:
            if candidate_ast == ast.dump(ast.Module(body=[], type_ignores=[])):
                _reference_fail(
                    "reference_metric_invalid", row, "new production path is AST-empty padding"
                )
        elif candidate_ast == _normalized_python_ast(base_text[base_path]["payload"]):
            _reference_fail(
                "reference_metric_invalid", row, "production delta changes no executable AST"
            )


def _ast_span(node: ast.AST) -> dict[str, int]:
    return {
        "line_start": node.lineno,
        "column_start": node.col_offset,
        "line_end": node.end_lineno,
        "column_end": node.end_col_offset,
    }


class _ReferenceScopeBindingVisitor(ast.NodeVisitor):
    """Collect one lexical scope's bindings without descending into children."""

    def __init__(self, target: str) -> None:
        self.target = target
        self.count = 0

    def _bind(self, name: str | None) -> None:
        self.count += int(name == self.target)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._bind(node.id)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._bind(alias.asname or alias.name.split(".", 1)[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            self._bind(alias.asname or alias.name)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._bind(node.name)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._bind(node.name)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._bind(node.name)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return

    def visit_Global(self, node: ast.Global) -> None:
        self.count += node.names.count(self.target)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.count += node.names.count(self.target)


def _reference_scope_binding_count(
    statements: Sequence[ast.stmt], target: str
) -> int:
    visitor = _ReferenceScopeBindingVisitor(target)
    for statement in statements:
        visitor.visit(statement)
    return visitor.count


def _reference_function_binds_name(
    function: ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda,
    target: str,
) -> bool:
    arguments = function.args
    argument_names = [
        *(argument.arg for argument in arguments.posonlyargs),
        *(argument.arg for argument in arguments.args),
        *(argument.arg for argument in arguments.kwonlyargs),
    ]
    if arguments.vararg is not None:
        argument_names.append(arguments.vararg.arg)
    if arguments.kwarg is not None:
        argument_names.append(arguments.kwarg.arg)
    if target in argument_names:
        return True
    if isinstance(function, ast.Lambda):
        visitor = _ReferenceScopeBindingVisitor(target)
        visitor.visit(function.body)
        return visitor.count != 0
    return _reference_scope_binding_count(function.body, target) != 0


def _resolve_reference_static_edge(
    *,
    edge_id: str,
    producer_payload: bytes,
    consumer_payload: bytes,
) -> dict[str, Any]:
    """Resolve one exact import-and-call edge without executing candidate code."""

    spec = _REFERENCE_EDGE_STATIC_SPECS.get(edge_id)
    if spec is None:
        _reference_fail(
            "reference_structure_invalid", edge_id, "static edge identity is unknown"
        )
    try:
        producer_tree = ast.parse(producer_payload.decode("utf-8", errors="strict"))
        consumer_tree = ast.parse(consumer_payload.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, SyntaxError) as exc:
        raise CalibrationError(
            "reference_structure_invalid",
            edge_id,
            "static edge source is not strict UTF-8 Python",
        ) from exc

    imported_module = str(spec["producer_path"]).removesuffix(".py").replace(
        "/", "."
    )
    imported_binding = str(spec["imported_binding"])
    exact_imports: list[ast.ImportFrom] = []
    aliased_target_import = False
    for node in consumer_tree.body:
        if (
            not isinstance(node, ast.ImportFrom)
            or node.level != 0
            or node.module != imported_module
        ):
            continue
        for alias in node.names:
            if alias.name != imported_binding:
                continue
            aliased_target_import = aliased_target_import or alias.asname is not None
            if alias.asname is None:
                exact_imports.append(node)
    if (
        aliased_target_import
        or len(exact_imports) != 1
        or _reference_scope_binding_count(
            consumer_tree.body, imported_binding
        )
        != 1
    ):
        _reference_fail(
            "reference_structure_invalid",
            edge_id,
            "consumer import is missing, aliased, shadowed, or ambiguous",
        )
    import_node = exact_imports[0]

    producer_name = str(spec["producer_name"])
    producer_owner = spec["producer_owner"]
    if producer_owner is None:
        producer_nodes = [
            node
            for node in producer_tree.body
            if isinstance(node, ast.FunctionDef) and node.name == producer_name
        ]
        producer_binding_count = _reference_scope_binding_count(
            producer_tree.body, producer_name
        )
    else:
        owner_name = str(producer_owner)
        owner_nodes = [
            node
            for node in producer_tree.body
            if isinstance(node, ast.ClassDef) and node.name == owner_name
        ]
        if (
            len(owner_nodes) != 1
            or _reference_scope_binding_count(producer_tree.body, owner_name)
            != 1
        ):
            _reference_fail(
                "reference_structure_invalid",
                edge_id,
                "producer class binding is missing, shadowed, or ambiguous",
            )
        owner = owner_nodes[0]
        producer_nodes = [
            node
            for node in owner.body
            if isinstance(node, ast.FunctionDef) and node.name == producer_name
        ]
        producer_binding_count = _reference_scope_binding_count(
            owner.body, producer_name
        )
        if len(producer_nodes) == 1:
            method = producer_nodes[0]
            classmethod_count = sum(
                isinstance(decorator, ast.Name) and decorator.id == "classmethod"
                for decorator in method.decorator_list
            )
            if (
                classmethod_count != 1
                or not method.args.args
                or method.args.args[0].arg != "cls"
            ):
                _reference_fail(
                    "reference_structure_invalid",
                    edge_id,
                    "qualified producer is not an exact classmethod",
                )
    if len(producer_nodes) != 1 or producer_binding_count != 1:
        _reference_fail(
            "reference_structure_invalid",
            edge_id,
            "producer callable is missing, shadowed, or ambiguous",
        )
    producer_node = producer_nodes[0]

    def matches_consumer_call(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        if producer_owner is None:
            return isinstance(node.func, ast.Name) and node.func.id == imported_binding
        return (
            isinstance(node.func, ast.Attribute)
            and node.func.attr == producer_name
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == imported_binding
        )

    consumer_nodes = [
        node for node in ast.walk(consumer_tree) if matches_consumer_call(node)
    ]
    if len(consumer_nodes) != 1:
        _reference_fail(
            "reference_structure_invalid",
            edge_id,
            "consumer call is missing or ambiguous",
        )
    consumer_node = consumer_nodes[0]
    parents: dict[ast.AST, ast.AST] = {
        child: parent
        for parent in ast.walk(consumer_tree)
        for child in ast.iter_child_nodes(parent)
    }
    ancestor = parents.get(consumer_node)
    while ancestor is not None:
        if isinstance(
            ancestor, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ) and _reference_function_binds_name(ancestor, imported_binding):
            _reference_fail(
                "reference_structure_invalid",
                edge_id,
                "consumer call binding is shadowed in its lexical scope",
            )
        ancestor = parents.get(ancestor)

    resolved_symbol = str(spec["resolved_symbol"])
    return {
        "producer": {
            "node_kind": "FunctionDef",
            "symbol": resolved_symbol,
            "span": _ast_span(producer_node),
        },
        "consumer": {
            "node_kind": "Call",
            "symbol": resolved_symbol,
            "span": _ast_span(consumer_node),
        },
        "imported_module": imported_module,
        "imported_binding": imported_binding,
        "import_span": _ast_span(import_node),
    }


def _validate_reference_structural_scope(
    record: Mapping[str, object],
    *,
    repository: Path,
    authorities: Mapping[str, dict[str, Any]],
    lifecycle_clause_satisfaction: Mapping[str, bool],
) -> None:
    scope = record.get("structural_scope")
    metric = record["metric"]
    lineage = record["lineage"]
    if not isinstance(scope, dict) or set(scope) != {
        "responsibility_ids",
        "cluster_domain",
        "changed_cluster_ids",
        "integration_edges",
    }:
        _reference_fail("reference_structure_invalid", scope, "structural scope is not exact")
    expected_responsibilities = [
        row["responsibility_id"]
        for row in authorities["preedit_policy"]["responsibilities"]
    ]
    selector_spike = authorities["selector_manifest"]["feasibility_spike"]
    expected_clusters = selector_spike["cluster_domain"]
    changed_clusters = list(
        dict.fromkeys(
            cluster
            for row in metric["rows"]
            if row["classification"] == "production_python"
            for cluster in row["cluster_ids"]
        )
    )
    if (
        scope["responsibility_ids"] != expected_responsibilities
        or scope["cluster_domain"] != expected_clusters
        or scope["changed_cluster_ids"] != changed_clusters
        or len(changed_clusters) < 4
    ):
        _reference_fail(
            "reference_structure_invalid", scope, "structural domains or changed-cluster union drifted"
        )
    edges = scope["integration_edges"]
    frozen_edges = selector_spike["integration_edges"]
    if not isinstance(edges, list) or len(edges) != len(frozen_edges) or len(edges) < 3:
        _reference_fail("reference_structure_invalid", edges, "integration edge domain drifted")
    production_by_path = {
        row["candidate_path"]: row
        for row in metric["rows"]
        if row["classification"] == "production_python" and row["candidate_path"]
    }
    actual_edge_paths = [
        (
            edge["producer"].get("path"),
            edge["consumer"].get("path"),
        )
        if (
            isinstance(edge, dict)
            and isinstance(edge.get("producer"), dict)
            and isinstance(edge.get("consumer"), dict)
        )
        else None
        for edge in edges
    ]
    expected_edge_paths = [
        (
            _REFERENCE_EDGE_STATIC_SPECS[frozen["edge_id"]]["producer_path"],
            _REFERENCE_EDGE_STATIC_SPECS[frozen["edge_id"]]["consumer_path"],
        )
        for frozen in frozen_edges
    ]
    if actual_edge_paths != expected_edge_paths:
        _reference_fail(
            "reference_structure_invalid",
            actual_edge_paths,
            "explicit integration edge topology drifted",
        )
    for edge, frozen in zip(edges, frozen_edges, strict=True):
        if not isinstance(edge, dict) or set(edge) != {
            "edge_id",
            "from_cluster",
            "to_cluster",
            "producer",
            "consumer",
            "evidence",
        }:
            _reference_fail("reference_structure_invalid", edge, "integration edge is not exact")
        if (
            edge["edge_id"] != frozen["edge_id"]
            or edge["from_cluster"] != frozen["from_cluster"]
            or edge["to_cluster"] != frozen["to_cluster"]
        ):
            _reference_fail("reference_structure_invalid", edge, "frozen edge identity drifted")
        static_spec = _REFERENCE_EDGE_STATIC_SPECS.get(edge["edge_id"])
        lifecycle_clause_ids = _REFERENCE_EDGE_LIFECYCLE_CLAUSES.get(
            edge["edge_id"]
        )
        if static_spec is None or lifecycle_clause_ids is None:
            _reference_fail(
                "reference_structure_invalid", edge, "edge conformance contract is missing"
            )
        payload_by_role: dict[str, bytes] = {}
        blob_by_role: dict[str, str] = {}
        for role in ("producer", "consumer"):
            endpoint = edge[role]
            if not isinstance(endpoint, dict) or set(endpoint) != {
                "path",
                "blob_id",
                "node_kind",
                "symbol",
                "span",
            }:
                _reference_fail(
                    "reference_structure_invalid", endpoint, f"{role} endpoint is not exact"
                )
            path = endpoint["path"]
            if (
                path != static_spec[f"{role}_path"]
                or path not in production_by_path
                or (
                    edge["from_cluster"]
                    if role == "producer"
                    else edge["to_cluster"]
                )
                not in production_by_path[path]["cluster_ids"]
            ):
                _reference_fail(
                    "reference_structure_invalid",
                    endpoint,
                    f"{role} path or cluster ownership drifted",
                )
            blob = _reference_git(
                repository,
                "rev-parse",
                f"{lineage['reference_tree']}:{path}",
            ).decode("ascii").strip()
            if endpoint["blob_id"] != blob:
                _reference_fail(
                    "reference_structure_invalid", endpoint, f"{role} blob drifted"
                )
            payload_by_role[role] = _reference_git(
                repository, "show", f"{lineage['reference_tree']}:{path}"
            )
            blob_by_role[role] = blob
        resolution = _resolve_reference_static_edge(
            edge_id=edge["edge_id"],
            producer_payload=payload_by_role["producer"],
            consumer_payload=payload_by_role["consumer"],
        )
        for role in ("producer", "consumer"):
            expected_endpoint = {
                "path": static_spec[f"{role}_path"],
                "blob_id": blob_by_role[role],
                **resolution[role],
            }
            if edge[role] != expected_endpoint:
                _reference_fail(
                    "reference_structure_invalid",
                    edge[role],
                    f"{role} static endpoint resolution drifted",
                )
        evidence = edge["evidence"]
        if not isinstance(evidence, dict) or set(evidence) != {
            "evidence_kind",
            "evidence_semantics",
            "target_tree",
            "imported_module",
            "imported_binding",
            "import_span",
            "consumer_blob_id",
            "resolved_producer_blob_id",
            "resolved_symbol",
            "lifecycle_report_member_id",
            "lifecycle_clause_ids",
        }:
            _reference_fail("reference_structure_invalid", evidence, "edge evidence is not exact")
        if evidence != {
            "evidence_kind": _REFERENCE_EDGE_EVIDENCE_KIND,
            "evidence_semantics": _REFERENCE_EDGE_EVIDENCE_SEMANTICS,
            "target_tree": lineage["reference_tree"],
            "imported_module": resolution["imported_module"],
            "imported_binding": resolution["imported_binding"],
            "import_span": resolution["import_span"],
            "consumer_blob_id": edge["consumer"]["blob_id"],
            "resolved_producer_blob_id": edge["producer"]["blob_id"],
            "resolved_symbol": edge["producer"]["symbol"],
            "lifecycle_report_member_id": "lifecycle_result",
            "lifecycle_clause_ids": list(lifecycle_clause_ids),
        }:
            _reference_fail(
                "reference_structure_invalid", evidence, "hybrid edge evidence drifted"
            )
        if any(
            lifecycle_clause_satisfaction.get(clause_id) is not True
            for clause_id in lifecycle_clause_ids
        ):
            _reference_fail(
                "reference_structure_invalid",
                lifecycle_clause_satisfaction,
                "edge lifecycle conformance is absent or unsatisfied",
            )


def _validate_reference_desired_state(
    record: Mapping[str, object],
    *,
    repository: Path,
    authorities: Mapping[str, dict[str, Any]],
) -> None:
    boundary = __import__(
        "scripts.experiments.es.boundary_proofs", fromlist=["boundary_proofs"]
    )
    desired = record.get("desired_state_proofs")
    if not isinstance(desired, dict) or set(desired) != {
        "schema_version",
        "runner_sha256",
        "target_tree",
        "execution",
        "result_rows",
    }:
        _reference_fail("reference_proof_invalid", desired, "desired-state record is not exact")
    expected_execution = {
        "python": {
            "path": str(boundary.PINNED_PYTHON),
            "target": str(boundary.PINNED_PYTHON_TARGET),
            "version": boundary.PINNED_PYTHON_VERSION,
            "sha256": boundary.PINNED_PYTHON_SHA256,
        },
        "pytest_carrier": {
            "path": str(boundary.PINNED_PYTEST_CARRIER),
            "version": boundary.PINNED_PYTEST_CARRIER_VERSION,
            "sha256": boundary.PINNED_PYTEST_CARRIER_SHA256,
        },
    }
    if (
        desired["schema_version"] != "es_f1_boundary_desired_state.v1"
        or desired["runner_sha256"] != _BOUNDARY_PROOF_RUNNER_SHA256
        or desired["target_tree"] != record["lineage"]["reference_tree"]
        or desired["execution"] != expected_execution
    ):
        _reference_fail("reference_proof_invalid", desired, "desired-state authority drifted")
    try:
        contract = boundary.validate_contract(
            authorities["selector_manifest"],
            consumer_rows=authorities["source_census"]["consumer_rows"],
            expected_runner_sha256=_BOUNDARY_PROOF_RUNNER_SHA256,
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_proof_invalid", None, "Task-0 proof contract validation failed"
        ) from exc
    rows = desired["result_rows"]
    if (
        not isinstance(rows, list)
        or len(rows) != 23
        or len(contract.desired_specs) != 23
        or len(contract.witnesses) != 23
    ):
        _reference_fail("reference_proof_invalid", rows, "desired-state result domain drifted")
    runtime_witness_kinds = {
        "pytest_runtime",
        "controller_pytest_runtime",
        "runtime_probe",
    }
    for row, spec, witness in zip(
        rows, contract.desired_specs, contract.witnesses, strict=True
    ):
        expected_fields = {
            "proof_id",
            "ordinal",
            "selector_id",
            "witness_id",
            "consumer_id",
            "proof_kind",
            "witness_kind",
            "target_tree",
            "target_path",
            "target_blob_id",
            "mechanically_observed",
            "observation",
            "observation_sha256",
            "passed",
        }
        if witness.witness_kind in runtime_witness_kinds:
            expected_fields.add("source_event")
        if not isinstance(row, dict) or set(row) != expected_fields:
            _reference_fail("reference_proof_invalid", row, "desired-state result row is not exact")
        expected_identity = {
            "proof_id": spec.proof_id,
            "ordinal": spec.ordinal,
            "selector_id": spec.selector_id,
            "witness_id": spec.witness_id,
            "consumer_id": spec.consumer_id,
            "proof_kind": spec.proof_kind,
            "witness_kind": witness.witness_kind,
            "target_tree": record["lineage"]["reference_tree"],
            "target_path": witness.consumer_path,
        }
        if any(row[key] != value for key, value in expected_identity.items()):
            _reference_fail("reference_proof_invalid", row, "desired-state result join drifted")
        if (
            row["observation"] != spec.expected_result
            or row["observation_sha256"] != _sha256_bytes(
                canonical_json_bytes(row["observation"])
            )
            or row["mechanically_observed"] is not True
            or row["passed"] is not True
        ):
            _reference_fail("reference_proof_invalid", row, "desired-state observation is not passing")
        if witness.witness_kind in runtime_witness_kinds:
            if row["source_event"] != row["observation"]:
                _reference_fail("reference_proof_invalid", row, "runtime source event drifted")
        expected_blob: str | None
        if spec.proof_kind == "reference_absence":
            expected_blob = None
            completed = subprocess.run(
                (
                    str(PINNED_GIT_EXECUTABLE),
                    "-C",
                    str(repository),
                    "cat-file",
                    "-e",
                    f"{record['lineage']['reference_tree']}:{witness.consumer_path}",
                ),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_git_environment(),
            )
            if completed.returncode == 0:
                _reference_fail(
                    "reference_proof_invalid", row, "required-absence path is present"
                )
        else:
            expected_blob = _reference_git(
                repository,
                "rev-parse",
                f"{record['lineage']['reference_tree']}:{witness.consumer_path}",
            ).decode("ascii").strip()
        if row["target_blob_id"] != expected_blob:
            _reference_fail("reference_proof_invalid", row, "desired-state target blob drifted")


def _canonical_cas_json(payload: bytes, *, member_id: str) -> dict[str, Any]:
    value = _parse_json_bytes(payload, label=member_id)
    if not isinstance(value, dict) or payload != canonical_json_bytes(value):
        _reference_fail(
            "reference_evaluator_invalid", member_id, "CAS JSON report is not canonical"
        )
    return value


def _validate_against_schema(value: object, relative: str, *, label: str) -> None:
    schema_path = _REPOSITORY_ROOT / relative
    schema = _parse_json_bytes(
        _read_regular_file(
            schema_path, code="reference_evaluator_invalid", label=f"{label} schema"
        ),
        label=schema_path,
    )
    if not isinstance(schema, dict):
        _reference_fail("reference_evaluator_invalid", schema, f"{label} schema is invalid")
    try:
        Draft202012Validator.check_schema(schema)
        errors = sorted(Draft202012Validator(schema).iter_errors(value), key=str)
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_invalid", label, "report schema validation failed"
        ) from exc
    if errors:
        _reference_fail(
            "reference_evaluator_invalid",
            {"label": label, "path": list(errors[0].absolute_path)},
            errors[0].message,
        )


def _witness_routes(lifecycle: Mapping[str, object]) -> list[dict[str, str]]:
    raw_result = lifecycle["lifecycle_result"]
    semantic = raw_result["semantic_report"]
    witness = next(
        row
        for row in semantic["architecture_results"]
        if row["architecture_id"] == "reference_witness"
    )
    checkpoint = {
        witness["evaluator_checkpoint_reload"]["implementation_identity"],
        witness["adapter_checkpoint_reload"]["implementation_identity"],
    }
    bundle = {
        witness["evaluator_bundle_reload"]["implementation_identity"],
        witness["adapter_bundle_reload"]["implementation_identity"],
    }
    persisted = {
        witness["persisted_implementation"],
        witness["persisted_rebuild_implementation"],
        witness["bundle_implementation"],
    }
    if len(checkpoint) != 1 or len(bundle) != 1 or len(persisted) != 1:
        _reference_fail(
            "reference_evaluator_invalid", witness, "witness reload identities diverge"
        )
    identities = {
        "REGISTRY_CONSTRUCTOR": witness["registry_constructor_identity"],
        "PUBLIC_CONSTRUCTION": witness["public_implementation"],
        "CHECKPOINT_RELOAD": next(iter(checkpoint)),
        "BUNDLE_RELOAD": next(iter(bundle)),
        "PERSISTED_REBUILD": next(iter(persisted)),
    }
    return [
        {
            "role": role,
            "architecture_id": "reference_witness",
            "implementation_identity": identity,
        }
        for role, identity in identities.items()
    ]


def project_reference_lifecycle_repeat_facts(
    lifecycle_result: Mapping[str, Any],
) -> dict[str, Any]:
    """Project two clean lifecycle runs onto repeatable semantic facts.

    Torch checkpoint and bundle containers are authenticated and reloaded inside
    each run, but their raw bytes can encode serialization-local metadata.  The
    artifact-identity payloads likewise contain evaluator-workspace locations.
    Validate those facts before removing only their container/path-bound values;
    retain state, observable, routing, structural, and outcome facts verbatim.
    """

    expected_fields = {
        "adapter_result",
        "audit_digest",
        "copy_digest_after",
        "copy_digest_before",
        "adapter_process_id",
        "semantic_observations",
        "semantic_report",
        "lifecycle_observations",
    }
    if not isinstance(lifecycle_result, Mapping) or set(lifecycle_result) != expected_fields:
        _reference_fail(
            "reference_evaluator_repeat_invalid",
            lifecycle_result,
            "lifecycle repeat input is not exact",
        )
    audit_digest = lifecycle_result["audit_digest"]
    adapter_process_id = lifecycle_result["adapter_process_id"]
    if (
        not isinstance(audit_digest, str)
        or _SHA256_RE.fullmatch(audit_digest) is None
        or type(adapter_process_id) is not int
        or adapter_process_id <= 0
        or lifecycle_result["copy_digest_before"]
        != lifecycle_result["copy_digest_after"]
    ):
        _reference_fail(
            "reference_evaluator_repeat_invalid",
            lifecycle_result,
            "lifecycle repeat envelope is invalid",
        )

    evaluator_module = __import__(
        "scripts.experiments.es.f1_evaluator", fromlist=["f1_evaluator"]
    )
    semantic = lifecycle_result["semantic_report"]
    try:
        evaluator_module.require_evaluator_successor_schema(
            semantic, record_type="semantic-lifecycle"
        )
        derived_observations = evaluator_module.derive_lifecycle_observations(
            semantic_report=semantic,
            adapter_process_id=adapter_process_id,
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_repeat_invalid",
            semantic,
            "lifecycle repeat semantics are invalid",
        ) from exc
    if (
        lifecycle_result["lifecycle_observations"] != derived_observations
        or not all(row.get("satisfied") is True for row in derived_observations)
    ):
        _reference_fail(
            "reference_evaluator_repeat_invalid",
            derived_observations,
            "lifecycle repeat clauses are not exact and passing",
        )

    semantic_rows = semantic["architecture_results"]
    expected_semantic_observations = {
        row["architecture_id"]: {
            "checkpoint": row["adapter_checkpoint_reload"],
            "bundle": row["adapter_bundle_reload"],
        }
        for row in semantic_rows
    }
    if lifecycle_result["semantic_observations"] != expected_semantic_observations:
        _reference_fail(
            "reference_evaluator_repeat_invalid",
            lifecycle_result["semantic_observations"],
            "lifecycle repeat adapter observations are not joined exactly",
        )

    def project_reload(reload: Mapping[str, Any]) -> dict[str, Any]:
        projected = copy.deepcopy(dict(reload))
        projected.pop("artifact_bytes")
        projected.pop("artifact_sha256")
        projected.pop("fresh_pid")
        return projected

    projected_semantic = copy.deepcopy(dict(semantic))
    projected_semantic.pop("construction_pid")
    projected_rows = projected_semantic["architecture_results"]
    for row in projected_rows:
        for reload_name in (
            "evaluator_checkpoint_reload",
            "evaluator_bundle_reload",
            "adapter_checkpoint_reload",
            "adapter_bundle_reload",
        ):
            row[reload_name] = project_reload(row[reload_name])
        for sensitivity in row["identity_sensitivity"].values():
            baseline = sensitivity.pop("baseline_identity_digest")
            alternate = sensitivity.pop("alternate_identity_digest")
            sensitivity["identity_digest_relation"] = (
                "distinct" if baseline != alternate else "equal"
            )

    projected_semantic_observations = {
        row["architecture_id"]: {
            "checkpoint": copy.deepcopy(row["adapter_checkpoint_reload"]),
            "bundle": copy.deepcopy(row["adapter_bundle_reload"]),
        }
        for row in projected_rows
    }
    return {
        "adapter_result": copy.deepcopy(lifecycle_result["adapter_result"]),
        "copy_digest_before": lifecycle_result["copy_digest_before"],
        "copy_digest_after": lifecycle_result["copy_digest_after"],
        "semantic_observations": projected_semantic_observations,
        "semantic_report": projected_semantic,
        "lifecycle_facts": [
            {
                "clause_id": row["clause_id"],
                "satisfied": row["satisfied"],
                "details": row["details"],
            }
            for row in derived_observations
        ],
    }


def _validate_reference_evaluator(
    record: Mapping[str, object],
    *,
    payloads: Mapping[str, bytes],
    authorities: Mapping[str, dict[str, Any]],
) -> dict[str, bool]:
    evaluator_module = __import__(
        "scripts.experiments.es.f1_evaluator", fromlist=["f1_evaluator"]
    )
    evidence = record.get("evaluator_evidence")
    expected_evidence_fields = {
        "report_member_ids",
        "witness_architecture_id",
        "witness_identity_roles",
        "witness_route_identities",
        "candidate_id",
        "architecture_ids",
        "lifecycle_stage_ids",
        "lifecycle_observations",
        "hard_clause_evidence",
        "artifact_applicability",
    }
    if not isinstance(evidence, dict) or set(evidence) != expected_evidence_fields:
        _reference_fail(
            "reference_evaluator_invalid", evidence, "evaluator evidence is not exact"
        )
    expected_report_ids = {
        "candidate_evidence": "candidate_evidence",
        "visible_check_result": "visible_check_result",
        "registry_signature_report": "registry_signature_report",
        "artifact_fixture_verification": "artifact_fixture_verification",
        "lifecycle_result": "lifecycle_result",
        "hard_evaluation": "hard_evaluation",
    }
    if evidence["report_member_ids"] != expected_report_ids:
        _reference_fail(
            "reference_evaluator_invalid", evidence, "evaluator report-member join drifted"
        )
    reports = {
        member_id: _canonical_cas_json(payloads[member_id], member_id=member_id)
        for member_id in _REFERENCE_CAS_MEMBER_IDS
        if member_id != "canonical_patch"
    }
    visible_contract = authorities["visible_task_contract"]
    fixture = authorities["evaluator_fixture_manifest"]
    candidate = reports["candidate_evidence"]
    _validate_against_schema(
        candidate,
        "experiments/orc_effectiveness/f1_es/task/candidate-extension-evidence.schema.json",
        label="candidate evidence",
    )
    expected_architectures = [
        *visible_contract["builtin_architectures"],
        "reference_witness",
    ]
    declarations = [
        *candidate.get("builtin_architectures", []),
        candidate.get("candidate_witness"),
    ]
    if (
        candidate.get("candidate_id") != evidence["candidate_id"]
        or [row.get("public_id") for row in declarations if isinstance(row, dict)]
        != expected_architectures
        or candidate.get("candidate_witness", {}).get("public_id")
        != "reference_witness"
        or evidence["architecture_ids"] != expected_architectures
        or evidence["witness_architecture_id"] != "reference_witness"
    ):
        _reference_fail(
            "reference_evaluator_invalid", candidate, "candidate architecture domain drifted"
        )
    visible_manifest_path = _REPOSITORY_ROOT / (
        "experiments/orc_effectiveness/f1_es/task/visible-check-manifest.json"
    )
    visible_manifest_raw = _read_regular_file(
        visible_manifest_path,
        code="reference_evaluator_invalid",
        label="visible check manifest",
    )
    if _sha256_bytes(visible_manifest_raw) != visible_contract["visible_checks"]["sha256"]:
        _reference_fail(
            "reference_evaluator_invalid", str(visible_manifest_path), "visible-check authority drifted"
        )
    visible_manifest = _parse_json_bytes(visible_manifest_raw, label=visible_manifest_path)
    visible = reports["visible_check_result"]
    try:
        evaluator_module.require_evaluator_successor_schema(
            visible, record_type="visible-check-result"
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_invalid", visible, "visible check report is invalid"
        ) from exc
    invocations = visible.get("invocations")
    by_id = {row["id"]: row for row in visible_manifest["invocations"]}
    expected_invocations = visible_manifest["invocation_order"]
    if (
        set(visible) != {
            "schema_version",
            "copy_digest_before",
            "copy_digest_after",
            "invocations",
        }
        or visible["copy_digest_before"] != visible["copy_digest_after"]
        or not isinstance(invocations, list)
        or [row.get("invocation_id") for row in invocations] != expected_invocations
    ):
        _reference_fail(
            "reference_evaluator_invalid", visible, "visible-check result domain drifted"
        )
    for invocation in invocations:
        expected = by_id[invocation["invocation_id"]]
        expected_argv = [
            visible_manifest["runner"]["python_executable"],
            *visible_manifest["runner"]["argv_prefix"],
            *expected["selectors"],
        ]
        if (
            set(invocation) != {
                "invocation_id",
                "argv",
                "exit_code",
                "stdout_sha256",
                "stderr_sha256",
            }
            or invocation["argv"] != expected_argv
            or invocation["exit_code"] != 0
            or any(
                not isinstance(invocation[key], str)
                or _SHA256_RE.fullmatch(invocation[key]) is None
                for key in ("stdout_sha256", "stderr_sha256")
            )
        ):
            _reference_fail(
                "reference_evaluator_invalid", invocation, "visible invocation failed or drifted"
            )

    registry = reports["registry_signature_report"]
    if (
        set(registry) != {
            "schema_version",
            "registry_baseline",
            "loaded_forbidden_modules",
            "outside_project_origin_rows",
            "cache_artifacts",
        }
        or registry["registry_baseline"] != fixture["registry_baseline"]
        or registry["loaded_forbidden_modules"]
        or registry["outside_project_origin_rows"]
        or registry["cache_artifacts"]
    ):
        _reference_fail(
            "reference_evaluator_invalid", registry, "registry signature report drifted"
        )
    try:
        registry_observation = evaluator_module.derive_registry_observation(
            expected_registry_baseline=fixture["registry_baseline"],
            registry_report=registry,
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_invalid", registry, "registry observation failed"
        ) from exc
    if registry_observation.get("satisfied") is not True:
        _reference_fail(
            "reference_evaluator_invalid", registry_observation, "registry observation failed"
        )

    lifecycle = reports["lifecycle_result"]
    if set(lifecycle) != {"schema_version", "lifecycle_request", "lifecycle_result"} or lifecycle[
        "schema_version"
    ] != "es_f1_reference_lifecycle_evidence.v1":
        _reference_fail(
            "reference_evaluator_invalid", lifecycle, "lifecycle envelope is not exact"
        )
    request = lifecycle["lifecycle_request"]
    result = lifecycle["lifecycle_result"]
    _validate_against_schema(
        request,
        "experiments/orc_effectiveness/f1_es/task/lifecycle-probe-request.schema.json",
        label="lifecycle request",
    )
    if (
        request["candidate_evidence_sha256"] != _sha256_bytes(payloads["candidate_evidence"])
        or request["candidate_id"] != candidate["candidate_id"]
        or [row["architecture_id"] for row in request["architecture_cases"]]
        != expected_architectures
        or request["required_lifecycle_stages"]
        != visible_contract["required_lifecycle_stages"]
    ):
        _reference_fail(
            "reference_evaluator_invalid", request, "lifecycle request binding drifted"
        )
    try:
        derived_cases, _ = evaluator_module.build_lifecycle_probe_inputs(
            architecture_rows=declarations,
            seed=request["seed"],
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_invalid", request, "lifecycle input derivation failed"
        ) from exc
    if derived_cases != request["architecture_cases"]:
        _reference_fail(
            "reference_evaluator_invalid", request, "lifecycle architecture cases drifted"
        )
    if not isinstance(result, dict) or set(result) != {
        "adapter_result",
        "audit_digest",
        "copy_digest_after",
        "copy_digest_before",
        "adapter_process_id",
        "semantic_observations",
        "semantic_report",
        "lifecycle_observations",
    }:
        _reference_fail(
            "reference_evaluator_invalid", result, "lifecycle result is not exact"
        )
    adapter_result = result["adapter_result"]
    _validate_against_schema(
        adapter_result,
        "experiments/orc_effectiveness/f1_es/task/lifecycle-probe-result.schema.json",
        label="lifecycle adapter result",
    )
    if (
        adapter_result["candidate_id"] != candidate["candidate_id"]
        or [row["architecture_id"] for row in adapter_result["architecture_results"]]
        != expected_architectures
        or result["copy_digest_before"] != result["copy_digest_after"]
    ):
        _reference_fail(
            "reference_evaluator_invalid", result, "lifecycle adapter result drifted"
        )
    semantic = result["semantic_report"]
    try:
        evaluator_module.require_evaluator_successor_schema(
            semantic, record_type="semantic-lifecycle"
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_invalid", semantic, "semantic lifecycle report is invalid"
        ) from exc
    semantic_rows = semantic["architecture_results"]
    if (
        [row["architecture_id"] for row in semantic_rows] != expected_architectures
        or any(
            row["completed_stages"] != visible_contract["required_lifecycle_stages"]
            or row["config_digest"] != case["config"]["sha256"]
            or row["input_digest"] != case["input"]["sha256"]
            for row, case in zip(
                semantic_rows, request["architecture_cases"], strict=True
            )
        )
    ):
        _reference_fail(
            "reference_evaluator_invalid", semantic, "semantic lifecycle domain drifted"
        )
    expected_semantic_observations = {
        row["architecture_id"]: {
            "checkpoint": row["adapter_checkpoint_reload"],
            "bundle": row["adapter_bundle_reload"],
        }
        for row in semantic_rows
    }
    # The authenticated evaluator returns only SHA256(canonical audit ledger),
    # not the ledger bytes.  Its bound source authenticates that production
    # contract; semantic observations are a separate returned field.
    if (
        result["semantic_observations"] != expected_semantic_observations
        or not isinstance(result["audit_digest"], str)
        or _SHA256_RE.fullmatch(result["audit_digest"]) is None
    ):
        _reference_fail(
            "reference_evaluator_invalid", result, "lifecycle audit envelope drifted"
        )
    try:
        lifecycle_observations = evaluator_module.derive_lifecycle_observations(
            semantic_report=semantic,
            adapter_process_id=result["adapter_process_id"],
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_invalid", semantic, "lifecycle observation derivation failed"
        ) from exc
    if (
        result["lifecycle_observations"] != lifecycle_observations
        or evidence["lifecycle_observations"] != lifecycle_observations
        or not all(row.get("satisfied") is True for row in lifecycle_observations)
        or evidence["lifecycle_stage_ids"]
        != visible_contract["required_lifecycle_stages"]
    ):
        _reference_fail(
            "reference_evaluator_invalid", lifecycle_observations, "lifecycle observations drifted"
        )
    routes = _witness_routes(lifecycle)
    expected_roles = visible_contract["witness_identity_proof"]["identity_roles"]
    route_identities = {row["implementation_identity"] for row in routes}
    builtin_identities = {
        row["implementation_identity"] for row in registry["registry_baseline"]
    }
    if (
        evidence["witness_identity_roles"] != expected_roles
        or [row["role"] for row in routes] != expected_roles
        or evidence["witness_route_identities"] != routes
        or len(route_identities) != 1
        or not route_identities.isdisjoint(builtin_identities)
    ):
        _reference_fail(
            "reference_evaluator_invalid", routes, "witness identity is aliased or incomplete"
        )

    artifact = reports["artifact_fixture_verification"]
    try:
        evaluator_module.require_evaluator_successor_schema(
            artifact, record_type="artifact-fixture-verification"
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_evaluator_invalid", artifact, "artifact report schema failed"
        ) from exc
    if (
        set(artifact) != {
            "schema_version",
            "artifact_eras",
            "loaded_forbidden_modules",
            "outside_project_origin_rows",
            "cache_artifacts",
        }
        or artifact["loaded_forbidden_modules"]
        or artifact["outside_project_origin_rows"]
        or artifact["cache_artifacts"]
        or evidence["artifact_applicability"] != artifact["artifact_eras"]
    ):
        _reference_fail(
            "reference_evaluator_invalid", artifact, "artifact applicability envelope drifted"
        )
    identity_by_architecture = {
        row["architecture"]: row["implementation_identity"]
        for row in registry["registry_baseline"]
    }
    identity_by_architecture["reference_witness"] = next(iter(route_identities))
    if len(artifact["artifact_eras"]) != 10:
        _reference_fail(
            "reference_evaluator_invalid", artifact, "artifact era domain is not ten"
        )
    cell_count = positive_count = rejection_count = 0
    for actual_era, frozen_era in zip(
        artifact["artifact_eras"], fixture["artifact_eras"], strict=True
    ):
        applicable = {
            "reference_witness" if value == "$candidate_witness" else value
            for value in frozen_era["applicable_architecture_ids"]
        }
        rejected = {
            "reference_witness" if value == "$candidate_witness" else value
            for value in frozen_era["rejected_architecture_ids"]
        }
        cells = actual_era.get("architecture_results")
        if (
            actual_era.get("era_id") != frozen_era["era_id"]
            or not isinstance(cells, list)
            or [row.get("architecture_id") for row in cells]
            != expected_architectures
            or applicable | rejected != set(expected_architectures)
            or applicable & rejected
        ):
            _reference_fail(
                "reference_evaluator_invalid", actual_era, "artifact partition drifted"
            )
        for cell in cells:
            cell_count += 1
            is_positive = cell["architecture_id"] in applicable
            positive_count += int(is_positive)
            rejection_count += int(not is_positive)
            expected_cell = {
                "architecture_id": cell["architecture_id"],
                "diagnostic": None if is_positive else "UNSUPPORTED_ARTIFACT_ARCHITECTURE",
                "implementation_identity": (
                    identity_by_architecture[cell["architecture_id"]]
                    if is_positive
                    else None
                ),
                "module_returned": is_positive,
                "strict_load": is_positive,
            }
            if cell != expected_cell:
                _reference_fail(
                    "reference_evaluator_invalid", cell, "artifact applicability cell drifted"
                )
    if (cell_count, positive_count, rejection_count) != (150, 10, 140):
        _reference_fail(
            "reference_evaluator_invalid",
            (cell_count, positive_count, rejection_count),
            "artifact matrix totals drifted",
        )

    hard_map = {
        clause: list(member_ids) for clause, member_ids in _REFERENCE_HARD_EVIDENCE
    }
    if evidence["hard_clause_evidence"] != hard_map:
        _reference_fail(
            "reference_evaluator_invalid", evidence, "hard-clause evidence map drifted"
        )
    hard = reports["hard_evaluation"]
    hard_ids = list(evaluator_module.HARD_CLAUSE_IDS)
    observations = hard.get("evaluator_observations") if isinstance(hard, dict) else None
    if (
        not isinstance(hard, dict)
        or set(hard) != {
            "schema_version",
            "candidate_id",
            "candidate_claims_digest",
            "evaluator_observations",
            "hard_findings",
        }
        or hard["schema_version"] != "es-f1-hard-evaluation.v2"
        or hard["candidate_id"] != candidate["candidate_id"]
        or hard["candidate_claims_digest"] != _sha256_bytes(payloads["candidate_evidence"])
        or hard["hard_findings"] != []
        or not isinstance(observations, list)
        or [row.get("clause_id") for row in observations] != hard_ids
    ):
        _reference_fail(
            "reference_evaluator_invalid", hard, "hard evaluation envelope drifted"
        )
    cas_sha = {member_id: _sha256_bytes(payload) for member_id, payload in payloads.items()}
    for observation in observations:
        clause = observation["clause_id"]
        expected_digest = _sha256_bytes(
            canonical_json_bytes([cas_sha[member_id] for member_id in hard_map[clause]])
        )
        if (
            set(observation) != {
                "clause_id",
                "details",
                "evidence_digest",
                "satisfied",
            }
            or observation["satisfied"] is not True
            or observation["evidence_digest"] != expected_digest
        ):
            _reference_fail(
                "reference_evaluator_invalid", observation, "hard-clause observation drifted"
            )
    return {
        row["clause_id"]: row["satisfied"] for row in lifecycle_observations
    }


def _validate_reference_bypass(
    record: Mapping[str, object],
    *,
    repository: Path,
    payloads: Mapping[str, bytes],
    authorities: Mapping[str, dict[str, Any]],
) -> None:
    source_census_module = __import__(
        "scripts.experiments.es.source_census", fromlist=["source_census"]
    )
    evaluator = __import__(
        "scripts.experiments.es.f1_evaluator", fromlist=["f1_evaluator"]
    )
    discovery = _canonical_cas_json(
        payloads["bypass_discovery"], member_id="bypass_discovery"
    )
    classification_report = _canonical_cas_json(
        payloads["bypass_classification"], member_id="bypass_classification"
    )
    bypass = record.get("bypass_oracle")
    if not isinstance(bypass, dict) or set(bypass) != {
        "report_member_ids",
        "candidate_tree",
        "discovery_candidate_set_sha256",
        "authority_bindings",
        "classification_sha256",
        "legacy_report_sha256",
        "desired_state_results_sha256",
        "derived_observation",
    }:
        _reference_fail("reference_bypass_invalid", bypass, "bypass oracle is not exact")
    if bypass["report_member_ids"] != {
        "discovery": "bypass_discovery",
        "classification": "bypass_classification",
    }:
        _reference_fail("reference_bypass_invalid", bypass, "bypass member join drifted")
    target_tree = record["lineage"]["reference_tree"]
    if (
        set(discovery) != {
            "schema_version",
            "candidate_tree",
            "discovery_input",
            "discovery_output",
        }
        or discovery["schema_version"] != "es_f1_reference_bypass_discovery.v1"
        or discovery["candidate_tree"] != target_tree
    ):
        _reference_fail("reference_bypass_invalid", discovery, "bypass discovery envelope drifted")
    discovery_input = discovery["discovery_input"]
    if discovery_input.get("projection") != {
        "repository": str(repository),
        "commit": record["lineage"]["reference_commit"],
        "tree": target_tree,
        "inventory_sha256": discovery["discovery_output"]["projection"][
            "inventory_sha256"
        ],
        "leaf_count": discovery["discovery_output"]["projection"]["leaf_count"],
    }:
        _reference_fail(
            "reference_bypass_invalid", discovery_input, "bypass projection binding drifted"
        )
    input_digest = _sha256_bytes(
        source_census_module.canonical_json_bytes(discovery_input)
    )
    try:
        expected_discovery = source_census_module.discover_source(
            discovery_input,
            discovery_input_sha256=input_digest,
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_bypass_invalid", discovery_input, "candidate source discovery failed"
        ) from exc
    if expected_discovery != discovery["discovery_output"]:
        _reference_fail(
            "reference_bypass_invalid", discovery, "candidate source discovery replay drifted"
        )
    try:
        expected_classification = evaluator.classify_task0_bypass_discovery(
            discovery_input=discovery_input,
            discovery_output=expected_discovery,
            verified_construction_route=evaluator.F1_PUBLIC_CONSTRUCTION_ROUTE,
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_bypass_invalid", discovery, "bypass classification failed"
        ) from exc
    if (
        set(classification_report) != {
            "schema_version",
            "candidate_tree",
            "authority_bindings",
            "classification",
            "legacy_report",
            "derived_observation",
        }
        or classification_report["schema_version"]
        != "es_f1_reference_bypass_classification.v1"
        or classification_report["candidate_tree"] != target_tree
        or classification_report["classification"] != expected_classification
        or classification_report["authority_bindings"]
        != expected_classification["authority_bindings"]
    ):
        _reference_fail(
            "reference_bypass_invalid", classification_report, "bypass classification replay drifted"
        )
    if (
        expected_classification["novel_direct_matches"]
        or expected_classification["restored_required_consumer_ids"]
    ):
        _reference_fail(
            "reference_bypass_invalid", expected_classification, "bypass classification is not closed"
        )
    census = authorities["source_census"]
    consumer_by_id = {row["consumer_id"]: row for row in census["consumer_rows"]}
    expected_partition = {
        status + "_consumer_ids": [
            consumer_id
            for consumer_id in census["legacy_bypass_inventory"]
            if consumer_by_id[consumer_id]["coverage_status"] == status
        ]
        for status in ("required", "inherited", "open")
    }
    legacy = classification_report["legacy_report"]
    if not isinstance(legacy, dict) or legacy != {
        "bindings": expected_classification["authority_bindings"],
        "legacy_inventory_partition": expected_partition,
        "novel_matches": expected_classification["novel_direct_matches"],
        "schema_version": "es-f1-legacy-bypass-report.v1",
        "selected_required_results": record["desired_state_proofs"]["result_rows"],
    }:
        _reference_fail("reference_bypass_invalid", legacy, "legacy bypass report drifted")
    try:
        derived = evaluator._derive_task0_bypass_observation(legacy)
    except Exception as exc:
        raise CalibrationError(
            "reference_bypass_invalid", legacy, "bypass observation derivation failed"
        ) from exc
    expected_bypass = {
        "report_member_ids": {
            "discovery": "bypass_discovery",
            "classification": "bypass_classification",
        },
        "candidate_tree": target_tree,
        "discovery_candidate_set_sha256": expected_discovery[
            "candidate_set_sha256"
        ],
        "authority_bindings": expected_classification["authority_bindings"],
        "classification_sha256": _sha256_bytes(
            canonical_json_bytes(expected_classification)
        ),
        "legacy_report_sha256": _sha256_bytes(canonical_json_bytes(legacy)),
        "desired_state_results_sha256": _sha256_bytes(
            canonical_json_bytes(record["desired_state_proofs"]["result_rows"])
        ),
        "derived_observation": derived,
    }
    if (
        bypass != expected_bypass
        or classification_report["derived_observation"] != derived
        or derived.get("satisfied") is not True
    ):
        _reference_fail("reference_bypass_invalid", bypass, "bypass oracle did not close")


def _reference_object_ids(repository: Path, ref: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                row.split(b" ", 1)[0].decode("ascii")
                for row in _reference_git(repository, "rev-list", "--objects", ref).splitlines()
            }
        )
    )


def _reference_typed_object_rows(
    repository: Path, object_ids: Sequence[str]
) -> list[dict[str, Any]]:
    if not object_ids:
        return []
    output = _reference_git(
        repository,
        "cat-file",
        "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        input_bytes=("\n".join(object_ids) + "\n").encode("ascii"),
    )
    rows: list[dict[str, Any]] = []
    try:
        for raw in output.splitlines():
            object_id, object_type, byte_count = raw.decode("ascii").split(" ")
            rows.append(
                {
                    "object_id": object_id,
                    "object_type": object_type,
                    "byte_count": int(byte_count),
                }
            )
    except (UnicodeDecodeError, ValueError) as exc:
        raise CalibrationError(
            "reference_no_delivery_invalid",
            str(repository),
            "Git object inventory is malformed",
        ) from exc
    if [row["object_id"] for row in rows] != list(object_ids):
        _reference_fail(
            "reference_no_delivery_invalid", rows, "Git object inventory order drifted"
        )
    return rows


def _reference_lookup_rows(
    repository: Path, object_ids: Sequence[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for object_id in object_ids:
        try:
            completed = subprocess.run(
                (
                    str(PINNED_GIT_EXECUTABLE),
                    "-C",
                    str(repository),
                    "cat-file",
                    "-e",
                    object_id,
                ),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=_git_environment(),
            )
        except OSError as exc:
            raise CalibrationError(
                "reference_no_delivery_invalid",
                str(repository),
                "Git object lookup failed",
            ) from exc
        rows.append(
            {
                "object_id": object_id,
                "return_code": completed.returncode,
                "stdout": completed.stdout.decode("utf-8", errors="strict"),
                "stderr_sha256": _sha256_bytes(completed.stderr),
            }
        )
    return rows


def _reference_lookups_are_absent(rows: Sequence[Mapping[str, object]]) -> bool:
    return all(
        isinstance(row.get("return_code"), int)
        and row["return_code"] != 0
        and row.get("stdout") == ""
        for row in rows
    )


def _reference_packet_payloads() -> tuple[bytes, bytes]:
    packets = __import__(
        "orchestrator.workflow.trial.packets", fromlist=["packets"]
    )
    include = (
        "task_spec",
        "validated_result",
        "workspace_delta",
        "check_results",
        "declared_artifacts",
        "failure_evidence",
    )
    task_spec = {
        "inputs": {
            "task": "task",
            "check_contract": "checks",
            "model": "gpt-5.5",
            "effort": "high",
        }
    }
    empty_delta = {
        "changed_files": [],
        "deleted_files": [],
        "untracked_files": [],
        "normalized_diff": {
            "entries": [],
            "catalog_digest": "sha256:" + "0" * 64,
            "truncated": False,
            "omitted_bytes": 0,
            "omitted_entries": 0,
        },
        "declared_artifacts": [],
    }
    common = {
        "opaque_label": "opaque-" + "1" * 64,
        "observation_include": include,
        "sealed_identity_values": ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH"),
        "max_item_bytes": 65_536,
        "max_packet_bytes": 262_144,
    }
    completed = packets.build_trial_evaluation_packet(
        **common,
        observations={
            "task_spec": task_spec,
            "validated_result": True,
            "workspace_delta": empty_delta,
            "check_results": [],
            "declared_artifacts": [],
        },
    )
    failed = packets.build_trial_evaluation_packet(
        **common,
        observations={
            "task_spec": task_spec,
            "failure_evidence": {
                "code": "run_ref_child_launch_failed",
                "phase": "launch",
                "retryable": False,
                "secondary_causes": [],
            },
        },
    )
    try:
        if packets.validate_trial_evaluation_packet(completed) != completed:
            raise ValueError("completed packet validation drifted")
        if packets.validate_trial_evaluation_packet(failed) != failed:
            raise ValueError("failed packet validation drifted")
    except Exception as exc:
        raise CalibrationError(
            "reference_no_delivery_invalid", None, "logical provider packets drifted"
        ) from exc
    return canonical_json_bytes(completed), canonical_json_bytes(failed)


def _reference_surface_payloads(task_seed_manifest: object) -> list[dict[str, Any]]:
    evaluation = __import__(
        "orchestrator.workflow.trial.evaluation", fromlist=["evaluation"]
    )
    metering = __import__("scripts.experiments.es.metering", fromlist=["metering"])
    provider_boundary = __import__(
        "scripts.experiments.es.provider_boundary", fromlist=["provider_boundary"]
    )
    if tuple(metering.normalize_codex_argv(_REFERENCE_LOGICAL_METERED_ARGV)) != (
        _REFERENCE_LOGICAL_METERED_ARGV
    ):
        _reference_fail(
            "reference_no_delivery_invalid", None, "logical metered argv drifted"
        )
    logical_environment = provider_boundary.boundary_environment(
        shim_dir=Path("/run/orc-es-f1/provider-shim"),
        manifest=provider_boundary.ManifestPublication(
            Path("/run/orc-es-f1/provider-boundary.json"),
            "sha256:" + "3" * 64,
        ),
        inherited_path="/usr/local/bin:/usr/bin:/bin",
    )
    completed_packet, failed_packet = _reference_packet_payloads()
    rows = [
        {
            "surface_id": f"visible_task_asset:{asset.target_path}",
            "surface_class": "visible_task_asset",
            "logical_path": asset.target_path,
            "payload": _reference_git(
                task_seed_manifest.locator,
                "show",
                f"{task_seed_manifest.commit}:{asset.target_path}",
            ),
        }
        for asset in task_seed_manifest.visible_assets
    ]
    rows.extend(
        (
            {
                "surface_id": "treatment_prompt_authority",
                "surface_class": "treatment_prompt",
                "logical_path": _REFERENCE_TREATMENT_PROMPT.as_posix(),
                "payload": _read_regular_file(
                    _REPOSITORY_ROOT / _REFERENCE_TREATMENT_PROMPT,
                    code="reference_no_delivery_invalid",
                    label="treatment prompt authority",
                ),
            },
            {
                "surface_id": "prompt_extern_authority",
                "surface_class": "prompt_externs",
                "logical_path": _REFERENCE_PROMPT_EXTERNS.as_posix(),
                "payload": _read_regular_file(
                    _REPOSITORY_ROOT / _REFERENCE_PROMPT_EXTERNS,
                    code="reference_no_delivery_invalid",
                    label="prompt extern authority",
                ),
            },
            {
                "surface_id": "trial_evaluator_instruction",
                "surface_class": "evaluator_instruction",
                "logical_path": evaluation.TRIAL_EVALUATOR_INSTRUCTION_ID,
                "payload": evaluation.TRIAL_EVALUATOR_INSTRUCTION.encode("utf-8"),
            },
            {
                "surface_id": "trial_evaluator_rubric",
                "surface_class": "evaluator_rubric",
                "logical_path": _REFERENCE_EVALUATOR_RUBRIC.as_posix(),
                "payload": _read_regular_file(
                    _REPOSITORY_ROOT / _REFERENCE_EVALUATOR_RUBRIC,
                    code="reference_no_delivery_invalid",
                    label="evaluator rubric",
                ),
            },
            {
                "surface_id": "logical_outer_argv",
                "surface_class": "provider_argv",
                "logical_path": "task3a://provider/outer-argv",
                "payload": canonical_json_bytes(list(_REFERENCE_LOGICAL_OUTER_ARGV)),
            },
            {
                "surface_id": "logical_metered_argv",
                "surface_class": "provider_argv",
                "logical_path": "task3a://provider/metered-argv",
                "payload": canonical_json_bytes(list(_REFERENCE_LOGICAL_METERED_ARGV)),
            },
            {
                "surface_id": "logical_provider_environment",
                "surface_class": "provider_environment",
                "logical_path": "task3a://provider/environment",
                "payload": canonical_json_bytes(logical_environment),
            },
            {
                "surface_id": "logical_completed_packet",
                "surface_class": "provider_packet",
                "logical_path": "task3a://provider/completed-packet",
                "payload": completed_packet,
            },
            {
                "surface_id": "logical_failed_packet",
                "surface_class": "provider_packet",
                "logical_path": "task3a://provider/failed-packet",
                "payload": failed_packet,
            },
        )
    )
    if len({row["surface_id"] for row in rows}) != len(rows):
        _reference_fail(
            "reference_no_delivery_invalid", rows, "logical surface ids are not unique"
        )
    return rows


def _reference_task_seed_closure(task_seed_manifest: object) -> dict[str, Any]:
    repository = task_seed_manifest.locator
    object_ids = _reference_object_ids(repository, "refs/heads/task-seed")
    object_rows = _reference_typed_object_rows(repository, object_ids)
    history_rows: list[dict[str, Any]] = []
    for raw in _reference_git(
        repository, "rev-list", "--parents", "--topo-order", "--all"
    ).splitlines():
        values = raw.decode("ascii").split(" ")
        history_rows.append({"commit": values[0], "parents": values[1:]})
    tree_rows = [
        {
            "commit": row["commit"],
            "tree": _reference_git(
                repository, "rev-parse", f"{row['commit']}^{{tree}}"
            ).decode("ascii").strip(),
        }
        for row in history_rows
    ]
    ref_rows = [
        {"refname": values[0], "object_id": values[1]}
        for values in (
            row.decode("ascii").split(" ")
            for row in _reference_git(
                repository, "for-each-ref", "--format=%(refname) %(objectname)"
            ).splitlines()
        )
    ]
    try:
        all_rows = _reference_git(
            repository,
            "cat-file",
            "--batch-all-objects",
            "--batch-check=%(objectname) %(objecttype) %(objectsize)",
        ).splitlines()
        all_ids = {row.split(b" ", 1)[0].decode("ascii") for row in all_rows}
        fsck_argv = (
            str(PINNED_GIT_EXECUTABLE),
            "-C",
            str(repository),
            "fsck",
            "--full",
            "--strict",
            "--no-reflogs",
            "--unreachable",
        )
        fsck = subprocess.run(
            fsck_argv,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
    except (OSError, UnicodeDecodeError) as exc:
        raise CalibrationError(
            "reference_no_delivery_invalid",
            str(repository),
            "task-seed object closure query failed",
        ) from exc
    visible_assets = [
        {
            "source_path": row.source_path,
            "target_path": row.target_path,
            "mode": row.mode,
            "object_type": row.object_type,
            "object_id": row.oid,
            "byte_count": row.byte_count,
            "sha256": row.digest,
        }
        for row in task_seed_manifest.visible_assets
    ]
    return {
        "repository_locator": str(repository),
        "head_ref": _reference_git(repository, "symbolic-ref", "HEAD")
        .decode("ascii")
        .strip(),
        "ref_rows": ref_rows,
        "history_rows": history_rows,
        "tree_rows": tree_rows,
        "reachable_object_count": len(object_rows),
        "reachable_objects_sha256": _sha256_bytes(canonical_json_bytes(object_rows)),
        "unreachable_object_count": len(all_ids - set(object_ids)),
        "fsck": {
            "argv": list(fsck_argv),
            "return_code": fsck.returncode,
            "stdout_sha256": _sha256_bytes(fsck.stdout),
            "stderr_sha256": _sha256_bytes(fsck.stderr),
        },
        "visible_asset_rows": visible_assets,
    }


def _reference_forbidden_domain(
    record: Mapping[str, object],
    *,
    repository: Path,
    reference_only_objects: Sequence[Mapping[str, object]],
    canonical_patch: bytes,
) -> tuple[dict[str, Any], list[tuple[str, bytes]]]:
    source_blob_rows: list[dict[str, Any]] = []
    forbidden_payloads: list[tuple[str, bytes]] = []
    for row in reference_only_objects:
        if row["object_type"] != "blob":
            continue
        payload = _reference_git(repository, "cat-file", "blob", str(row["object_id"]))
        if not payload:
            _reference_fail(
                "reference_no_delivery_invalid", row, "reference-only blob is empty"
            )
        source_blob_rows.append(
            {
                "object_id": row["object_id"],
                "byte_count": len(payload),
                "content_sha256": _sha256_bytes(payload),
            }
        )
        forbidden_payloads.append(
            (f"reference_source_blob:{row['object_id']}", payload)
        )
    try:
        canary_payload = _reference_git(
            repository,
            "show",
            f"{record['lineage']['reference_tree']}:{_REFERENCE_DOCUMENTATION_PATH}",
        )
        canary = canary_payload.decode("ascii", errors="strict").removesuffix("\n")
    except UnicodeDecodeError as exc:
        raise CalibrationError(
            "reference_no_delivery_invalid",
            _REFERENCE_DOCUMENTATION_PATH,
            "reference canary is not ASCII",
        ) from exc
    if (
        canary_payload != (canary + "\n").encode("ascii")
        or not canary.startswith("es-f1-reference-canary.v1:")
        or len(canary.removeprefix("es-f1-reference-canary.v1:")) != 64
    ):
        _reference_fail(
            "reference_no_delivery_invalid", canary, "reference canary drifted"
        )
    patch_sha256 = _sha256_bytes(canonical_patch)
    measured_count = record["metric"]["implementation_additions"]
    domain = {
        "reference_locator": str(repository),
        "reference_relative_path": record["repository"]["relative_path"],
        "reference_ref": _REFERENCE_REF,
        "reference_commit": record["lineage"]["reference_commit"],
        "reference_tree": record["lineage"]["reference_tree"],
        "reference_object_ids": [row["object_id"] for row in reference_only_objects],
        "reference_source_blobs": source_blob_rows,
        "canonical_patch": {
            "member_id": "canonical_patch",
            "byte_count": len(canonical_patch),
            "sha256": patch_sha256,
        },
        "reference_manifest": {
            "schema_version": "es_f1_reference_product.v1",
            "path": "experiments/orc_effectiveness/f1_es/reference-product.json",
        },
        "reference_canary": {
            "path": _REFERENCE_DOCUMENTATION_PATH,
            "value": canary,
        },
        "measured_count": {
            "metric_version": record["metric"]["metric_version"],
            "value": measured_count,
            "ascii": str(measured_count),
        },
    }
    for name in (
        "reference_locator",
        "reference_relative_path",
        "reference_ref",
        "reference_commit",
        "reference_tree",
    ):
        forbidden_payloads.append((name, str(domain[name]).encode("utf-8")))
    forbidden_payloads.extend(
        (f"reference_object:{object_id}", str(object_id).encode("ascii"))
        for object_id in domain["reference_object_ids"]
    )
    forbidden_payloads.extend(
        (
            ("canonical_patch", canonical_patch),
            ("reference_manifest_schema", b"es_f1_reference_product.v1"),
            (
                "reference_manifest_path",
                b"experiments/orc_effectiveness/f1_es/reference-product.json",
            ),
            ("reference_canary", canary.encode("ascii")),
            ("measured_count", str(measured_count).encode("ascii")),
        )
    )
    return domain, forbidden_payloads


def _validate_reference_no_delivery(
    record: Mapping[str, object],
    *,
    repository: Path,
    payloads: Mapping[str, bytes],
    authorities: Mapping[str, dict[str, Any]],
) -> None:
    task_package = __import__(
        "scripts.experiments.es.task_package", fromlist=["task_package"]
    )
    source = __import__(
        "orchestrator.workflow.run_ref.source", fromlist=["source"]
    )
    report = _canonical_cas_json(
        payloads["no_delivery_report"], member_id="no_delivery_report"
    )
    if set(report) != {
        "schema_version",
        "bindings",
        "task_seed_closure",
        "reference_only_objects",
        "task_seed_lookup_rows",
        "surface_scan",
        "provider_workspace",
        "controller_resolution",
    } or report["schema_version"] != "es_f1_reference_no_delivery.v1":
        _reference_fail(
            "reference_no_delivery_invalid", report, "no-delivery report is not exact"
        )
    task_seed_manifest_path = (
        _REPOSITORY_ROOT
        / _reference_relative_path(
            record["bindings"]["task_seed_manifest"]["path"],
            label="task-seed manifest",
        )
    )
    try:
        task_seed_manifest = task_package.load_task_seed_manifest(task_seed_manifest_path)
        task_seed_result = task_package.verify_task_seed(
            task_seed_manifest.locator, task_seed_manifest
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_no_delivery_invalid",
            str(task_seed_manifest_path),
            "task-seed closure validation failed",
        ) from exc
    if task_seed_result.unreachable_object_count != 0:
        _reference_fail(
            "reference_no_delivery_invalid",
            task_seed_result.unreachable_object_count,
            "task-seed repository has unreachable objects",
        )
    expected_bindings = {
        "task_seed_manifest_sha256": record["bindings"]["task_seed_manifest"]["sha256"],
        "task_seed_repository_snapshot_sha256": authorities["task_seed_manifest"][
            "repository"
        ]["repository_snapshot_sha256"],
        "reference_repository_snapshot_sha256": record["repository"][
            "repository_snapshot_sha256"
        ],
        "reference_ref": _REFERENCE_REF,
        "reference_commit": record["lineage"]["reference_commit"],
        "reference_tree": record["lineage"]["reference_tree"],
        "canonical_patch_member_id": "canonical_patch",
        "canonical_patch_sha256": _sha256_bytes(payloads["canonical_patch"]),
    }
    if report["bindings"] != expected_bindings:
        _reference_fail(
            "reference_no_delivery_invalid", report["bindings"], "report bindings drifted"
        )
    expected_closure = _reference_task_seed_closure(task_seed_manifest)
    if report["task_seed_closure"] != expected_closure:
        _reference_fail(
            "reference_no_delivery_invalid",
            report["task_seed_closure"],
            "task-seed closure replay drifted",
        )

    task_seed_ids = _reference_object_ids(
        task_seed_manifest.locator, "refs/heads/task-seed"
    )
    reference_ids = _reference_object_ids(repository, _REFERENCE_REF)
    reference_only_ids = tuple(sorted(set(reference_ids) - set(task_seed_ids)))
    reference_only_objects = _reference_typed_object_rows(
        repository, reference_only_ids
    )
    task_seed_lookup_rows = _reference_lookup_rows(
        task_seed_manifest.locator, reference_only_ids
    )
    if (
        not reference_only_objects
        or report["reference_only_objects"] != reference_only_objects
        or report["task_seed_lookup_rows"] != task_seed_lookup_rows
        or not _reference_lookups_are_absent(task_seed_lookup_rows)
    ):
        _reference_fail(
            "reference_no_delivery_invalid",
            report["reference_only_objects"],
            "reference-only object partition drifted",
        )

    domain, forbidden_payloads = _reference_forbidden_domain(
        record,
        repository=repository,
        reference_only_objects=reference_only_objects,
        canonical_patch=payloads["canonical_patch"],
    )
    expected_surface_rows: list[dict[str, Any]] = []
    expected_matches: list[dict[str, str]] = []
    for surface in _reference_surface_payloads(task_seed_manifest):
        payload = surface.pop("payload")
        matches = [
            forbidden_id
            for forbidden_id, forbidden_payload in forbidden_payloads
            if forbidden_payload in payload
        ]
        row = {
            **surface,
            "byte_count": len(payload),
            "sha256": _sha256_bytes(payload),
            "matches": matches,
        }
        expected_surface_rows.append(row)
        expected_matches.extend(
            {"surface_id": row["surface_id"], "forbidden_id": forbidden_id}
            for forbidden_id in matches
        )
    expected_scan = {
        "scope": {
            "surface_set": "task3a_logical_prelaunch.v1",
            "final_prompt_manifest": "not_yet_materialized",
            "final_environment_lock": "not_yet_materialized",
            "task5_replay_required": True,
        },
        "forbidden_domain": domain,
        "surface_rows": expected_surface_rows,
        "matches": expected_matches,
    }
    if report["surface_scan"] != expected_scan or expected_matches:
        _reference_fail(
            "reference_no_delivery_invalid",
            report["surface_scan"],
            "provider-visible surface scan drifted or detected delivery",
        )

    provider = report["provider_workspace"]
    if not isinstance(provider, dict) or set(provider) != {
        "destination",
        "destination_initial_state",
        "run_ref_root",
        "source_request",
        "normalized_locator",
        "resolved_commit",
        "verified_git_tree",
        "source_tree_manifest_sha256",
        "post_setup_tree_manifest_sha256",
        "head_commit",
        "head_tree",
        "symbolic_ref_return_code",
        "status_porcelain",
        "reference_object_lookup_rows",
    }:
        _reference_fail(
            "reference_no_delivery_invalid", provider, "provider workspace is not exact"
        )
    destination = _canonical_directory(
        provider["destination"], label="no-delivery provider workspace"
    )
    run_ref_root = _canonical_directory(
        provider["run_ref_root"], label="no-delivery run-ref root"
    )
    source_request = source.canonical_source_request(
        source.SourceRequest(
            locator=str(task_seed_manifest.locator), commit=task_seed_manifest.commit
        )
    )
    symbolic = subprocess.run(
        (str(PINNED_GIT_EXECUTABLE), "-C", str(destination), "symbolic-ref", "-q", "HEAD"),
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_git_environment(),
    )
    provider_lookup_rows = _reference_lookup_rows(destination, reference_only_ids)
    if (
        destination.parent != run_ref_root.parent
        or destination == run_ref_root
        or provider["destination_initial_state"] != "absent"
        or provider["source_request"] != source_request
        or provider["normalized_locator"] != source_request["normalized_locator"]
        or provider["resolved_commit"] != task_seed_manifest.commit
        or provider["verified_git_tree"] != f"git-tree:{task_seed_manifest.tree}"
        or provider["source_tree_manifest_sha256"]
        != provider["post_setup_tree_manifest_sha256"]
        or _SHA256_RE.fullmatch(str(provider["source_tree_manifest_sha256"])) is None
        or provider["head_commit"]
        != _reference_git(destination, "rev-parse", "HEAD").decode("ascii").strip()
        or provider["head_commit"] != task_seed_manifest.commit
        or provider["head_tree"]
        != _reference_git(destination, "rev-parse", "HEAD^{tree}")
        .decode("ascii")
        .strip()
        or provider["head_tree"] != task_seed_manifest.tree
        or provider["symbolic_ref_return_code"] != symbolic.returncode
        or symbolic.returncode == 0
        or provider["status_porcelain"]
        != _reference_git(destination, "status", "--porcelain=v1").decode(
            "utf-8", errors="strict"
        )
        or provider["status_porcelain"] != ""
        or provider["reference_object_lookup_rows"] != provider_lookup_rows
        or not _reference_lookups_are_absent(provider_lookup_rows)
    ):
        _reference_fail(
            "reference_no_delivery_invalid", provider, "provider workspace replay drifted"
        )

    escape_candidates = (
        repository / "objects" / "info" / "alternates",
        repository / "info" / "grafts",
        repository / "shallow",
        repository / "refs" / "replace",
    )
    controller = {
        "repository_locator": str(repository),
        "head_ref": _reference_git(repository, "symbolic-ref", "HEAD")
        .decode("ascii")
        .strip(),
        "ref_rows": [
            {"refname": values[0], "object_id": values[1]}
            for values in (
                row.decode("ascii").split(" ")
                for row in _reference_git(
                    repository,
                    "for-each-ref",
                    "--format=%(refname) %(objectname)",
                ).splitlines()
            )
        ],
        "resolved_commit": _reference_git(repository, "rev-parse", _REFERENCE_REF)
        .decode("ascii")
        .strip(),
        "resolved_tree": _reference_git(
            repository, "rev-parse", f"{_REFERENCE_REF}^{{tree}}"
        )
        .decode("ascii")
        .strip(),
        "remote_rows": _reference_git(repository, "remote", "-v")
        .decode("utf-8")
        .splitlines(),
        "escape_paths": [
            path.relative_to(repository).as_posix()
            for path in escape_candidates
            if os.path.lexists(path)
        ],
        "reference_object_rows": reference_only_objects,
    }
    if report["controller_resolution"] != controller:
        _reference_fail(
            "reference_no_delivery_invalid",
            report["controller_resolution"],
            "controller-only resolution drifted",
        )
    expected_top = {
        "report_member_id": "no_delivery_report",
        "task_seed_repository": str(task_seed_manifest.locator),
        "task_seed_tree": task_seed_manifest.tree,
        "reference_object_ids": list(reference_only_ids),
        "task5_replay_required": True,
    }
    if record.get("no_delivery") != expected_top:
        _reference_fail(
            "reference_no_delivery_invalid",
            record.get("no_delivery"),
            "top-level no-delivery authority drifted",
        )


def load_reference_product(
    path: Path,
    *,
    schema_path: Path,
    expected_record_sha256: str,
) -> ReferenceProduct:
    """Reopen and fully validate one controller-only reference product.

    This operation is deliberately nonexecuting: desired-state proof rows are
    validated against their frozen contract, but no proof command is run.
    """

    try:
        record_path = _canonical_regular_file(
            Path(path), label="reference-product record"
        )
        schema_locator = _canonical_regular_file(
            Path(schema_path), label="reference-product schema"
        )
        record = load_canonical_record(
            record_path,
            schema_path=schema_locator,
            expected_record_sha256=expected_record_sha256,
        )
        if (
            set(record) != set(_REFERENCE_TOP_LEVEL_FIELDS)
            or record.get("schema_version") != "es_f1_reference_product.v1"
        ):
            _reference_fail(
                "reference_product_invalid",
                record,
                "reference product top-level contract drifted",
            )
        authorities = _load_reference_authorities(record)
        repository = _validate_reference_repository(record, authorities)
        _, payloads = _load_reference_cas(record, repository)
        _validate_reference_patch(record, repository, payloads)
        _validate_reference_metric(
            record, repository=repository, authorities=authorities
        )
        _validate_reference_desired_state(
            record, repository=repository, authorities=authorities
        )
        lifecycle_clause_satisfaction = _validate_reference_evaluator(
            record, payloads=payloads, authorities=authorities
        )
        _validate_reference_structural_scope(
            record,
            repository=repository,
            authorities=authorities,
            lifecycle_clause_satisfaction=lifecycle_clause_satisfaction,
        )
        _validate_reference_bypass(
            record,
            repository=repository,
            payloads=payloads,
            authorities=authorities,
        )
        _validate_reference_no_delivery(
            record,
            repository=repository,
            payloads=payloads,
            authorities=authorities,
        )
        return ReferenceProduct(
            record=copy.deepcopy(record),
            _selector_manifest=copy.deepcopy(authorities["selector_manifest"]),
            _source_census=copy.deepcopy(authorities["source_census"]),
            _record_path=record_path,
            _schema_path=schema_locator,
            _expected_record_sha256=expected_record_sha256,
            _validation_provenance=_REFERENCE_PRODUCT_VALIDATION_PROVENANCE,
        )
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(
            "reference_product_invalid",
            str(path),
            "incidental reference-product validation failure",
        ) from exc


def build_desired_state_execution_manifest(
    selector_manifest: Mapping[str, Any],
    *,
    source_census: Mapping[str, Any],
) -> dict[str, Any]:
    """Project baseline input bindings into the later desired-state contract.

    Task-0 authority remains immutable.  A static witness that failed on the
    baseline must observe a changed or removed target in the desired tree, so
    that target cannot simultaneously remain a required baseline input in the
    execution view.  All other selector, witness, and proof data is preserved
    exactly.
    """

    boundary = __import__(
        "scripts.experiments.es.boundary_proofs", fromlist=["boundary_proofs"]
    )
    try:
        boundary.validate_record_sha256(selector_manifest)
        boundary.validate_record_sha256(source_census)
        boundary.validate_authority_bindings(selector_manifest, source_census)
        boundary.validate_contract(
            selector_manifest,
            consumer_rows=source_census["consumer_rows"],
            expected_runner_sha256=_BOUNDARY_PROOF_RUNNER_SHA256,
        )
    except Exception as exc:
        raise CalibrationError(
            "reference_execution_projection_invalid",
            selector_manifest,
            "source proof authority is invalid",
        ) from exc

    section_names = (
        "provider_visible_pytest_selectors",
        "controller_only_proof_selectors",
        "coverage_witnesses",
        "desired_state_proof_specs",
    )
    projection = {
        section: copy.deepcopy(selector_manifest[section]) for section in section_names
    }
    try:
        controllers = projection["controller_only_proof_selectors"]
        controllers_by_id = {row["selector_id"]: row for row in controllers}
        witnesses_by_id = {
            row["witness_id"]: row for row in projection["coverage_witnesses"]
        }
        specs_by_witness_id = {
            row["witness_id"]: row
            for row in projection["desired_state_proof_specs"]
        }
        baseline_rows = selector_manifest["baseline_characterization"][
            "witness_results"
        ]
        if not isinstance(baseline_rows, list) or len(baseline_rows) != len(
            projection["coverage_witnesses"]
        ):
            _reference_fail(
                "reference_execution_projection_invalid",
                baseline_rows,
                "baseline witness-result domain is not exact",
            )
        projected_targets: set[str] = set()
        for baseline, witness in zip(
            baseline_rows,
            projection["coverage_witnesses"],
            strict=True,
        ):
            spec = specs_by_witness_id[witness["witness_id"]]
            if (
                baseline["witness_id"] != witness["witness_id"]
                or baseline["selector_id"] != witness["selector_id"]
                or baseline["consumer_id"] != witness["consumer_id"]
                or baseline["proof_kind"] != witness["proof_kind"]
                or baseline["target_path"] != witness["consumer_path"]
                or baseline["mechanically_observed"] is not True
                or type(baseline["passed"]) is not bool
                or baseline["passed"]
                != (baseline["observation"] == spec["expected_result"])
            ):
                _reference_fail(
                    "reference_execution_projection_invalid",
                    baseline,
                    "baseline result does not exactly join its desired witness",
                )
            if baseline["passed"] is True:
                continue
            if witnesses_by_id[witness["witness_id"]] != witness:
                _reference_fail(
                    "reference_execution_projection_invalid",
                    witness,
                    "desired witness identity is ambiguous",
                )
            selector = controllers_by_id[spec["selector_id"]]
            target = witness["consumer_path"]
            if (
                witness["witness_kind"] != "static_ast"
                or witness["proof_kind"]
                not in {"non_cdi_static", "reference_absence"}
                or witness["selector_id"] != selector["selector_id"]
                or selector["proof_kind"] != witness["proof_kind"]
                or target in projected_targets
            ):
                _reference_fail(
                    "reference_execution_projection_invalid",
                    spec,
                    "mutable static proof ownership is ambiguous",
                )
            owners = [
                row["selector_id"]
                for row in controllers
                if any(binding["path"] == target for binding in row["input_bindings"])
            ]
            if owners != [selector["selector_id"]]:
                _reference_fail(
                    "reference_execution_projection_invalid",
                    {"target": target, "owners": owners},
                    "mutable target must have exactly one owning baseline binding",
                )
            retained = [
                binding
                for binding in selector["input_bindings"]
                if binding["path"] != target
            ]
            if not retained or len(retained) + 1 != len(selector["input_bindings"]):
                _reference_fail(
                    "reference_execution_projection_invalid",
                    target,
                    "target projection must remove one binding and retain another",
                )
            selector["input_bindings"] = retained
            projected_targets.add(target)
        if not projected_targets:
            _reference_fail(
                "reference_execution_projection_invalid",
                projected_targets,
                "desired-state projection has no baseline-failing static target",
            )
        boundary.validate_contract(
            projection,
            consumer_rows=source_census["consumer_rows"],
            expected_runner_sha256=_BOUNDARY_PROOF_RUNNER_SHA256,
        )
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(
            "reference_execution_projection_invalid",
            projection,
            "desired-state proof projection is invalid",
        ) from exc
    return projection


def project_desired_state_provider_nodes(
    execution_manifest: Mapping[str, Any],
    *,
    collected_node_ids: Sequence[str],
    builtin_architecture_ids: Sequence[str],
    witness_architecture_id: str,
) -> dict[str, Any]:
    """Admit only the candidate sibling nodes implied by a complete registry.

    Task 0 records the pre-edit node domain.  A reference product that adds one
    distinct public architecture legitimately extends tests parameterized over
    the complete built-in registry.  This projection retains every Task-0 node
    in order and admits exactly one candidate sibling for every such complete
    built-in group; every other collection delta fails closed.
    """

    try:
        projection = copy.deepcopy(execution_manifest)
        providers = projection["provider_visible_pytest_selectors"]
        if not isinstance(providers, list) or not providers:
            _reference_fail(
                "reference_execution_projection_invalid",
                providers,
                "provider selector domain is empty or malformed",
            )
        builtins = tuple(builtin_architecture_ids)
        if (
            not builtins
            or len(set(builtins)) != len(builtins)
            or any(
                not isinstance(value, str)
                or _ARCHITECTURE_ID_RE.fullmatch(value) is None
                for value in builtins
            )
            or not isinstance(witness_architecture_id, str)
            or _ARCHITECTURE_ID_RE.fullmatch(witness_architecture_id) is None
            or witness_architecture_id in builtins
        ):
            _reference_fail(
                "reference_execution_projection_invalid",
                {
                    "builtin_architecture_ids": builtins,
                    "witness_architecture_id": witness_architecture_id,
                },
                "architecture partition is invalid",
            )
        if isinstance(collected_node_ids, (str, bytes)):
            _reference_fail(
                "reference_execution_projection_invalid",
                collected_node_ids,
                "collected provider nodes are not a sequence of node IDs",
            )
        collected = tuple(collected_node_ids)
        if (
            not collected
            or len(set(collected)) != len(collected)
            or any(not isinstance(node, str) or not node for node in collected)
        ):
            _reference_fail(
                "reference_execution_projection_invalid",
                collected,
                "collected provider node domain is empty, duplicate, or malformed",
            )

        modules = tuple(row["pytest_module_path"] for row in providers)
        if (
            any(not isinstance(module, str) or not module for module in modules)
            or len(set(modules)) != len(modules)
        ):
            _reference_fail(
                "reference_execution_projection_invalid",
                modules,
                "provider module ownership is ambiguous",
            )
        target_by_selector: list[list[str]] = [[] for _ in providers]
        owners: list[int] = []
        for node in collected:
            matching = [
                index
                for index, module in enumerate(modules)
                if node.startswith(module + "::")
            ]
            if len(matching) != 1:
                _reference_fail(
                    "reference_execution_projection_invalid",
                    node,
                    "collected node has no unique provider selector owner",
                )
            owner = matching[0]
            owners.append(owner)
            target_by_selector[owner].append(node)
        if owners != sorted(owners):
            _reference_fail(
                "reference_execution_projection_invalid",
                owners,
                "collected provider selector order drifted",
            )

        expected_additions: set[str] = set()
        actual_additions: set[str] = set()
        for row, target_nodes in zip(providers, target_by_selector, strict=True):
            source_nodes = tuple(row["pytest_node_ids"])
            if (
                not source_nodes
                or len(set(source_nodes)) != len(source_nodes)
                or any(not isinstance(node, str) or not node for node in source_nodes)
            ):
                _reference_fail(
                    "reference_execution_projection_invalid",
                    row,
                    "Task-0 provider nodes are malformed",
                )
            source_domain = set(source_nodes)
            if tuple(node for node in target_nodes if node in source_domain) != source_nodes:
                _reference_fail(
                    "reference_execution_projection_invalid",
                    row["selector_id"],
                    "Task-0 provider nodes are missing, duplicated, or reordered",
                )

            suffixes_by_prefix: dict[str, list[str]] = {}
            for node in source_nodes:
                if "[" not in node or not node.endswith("]"):
                    continue
                prefix, suffix = node.rsplit("[", 1)
                suffixes_by_prefix.setdefault(prefix, []).append(suffix[:-1])
            eligible_prefixes = {
                prefix
                for prefix, suffixes in suffixes_by_prefix.items()
                if tuple(suffixes) == builtins
            }
            expected_additions.update(
                f"{prefix}[{witness_architecture_id}]"
                for prefix in eligible_prefixes
            )
            actual_additions.update(
                node for node in target_nodes if node not in source_domain
            )
            row["pytest_node_ids"] = list(target_nodes)

        if not expected_additions or actual_additions != expected_additions:
            _reference_fail(
                "reference_execution_projection_invalid",
                {
                    "expected_additions": sorted(expected_additions),
                    "actual_additions": sorted(actual_additions),
                },
                "provider collection delta is not the exact candidate sibling set",
            )
        if [
            node
            for row in providers
            for node in row["pytest_node_ids"]
        ] != list(collected):
            _reference_fail(
                "reference_execution_projection_invalid",
                collected,
                "projected provider rows do not reproduce collection order",
            )
        return projection
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(
            "reference_execution_projection_invalid",
            execution_manifest,
            "provider node projection is invalid",
        ) from exc


def build_reference_desired_state_execution_manifest(
    selector_manifest: Mapping[str, Any],
    *,
    source_census: Mapping[str, Any],
    workspace: Path,
    expected_tree: str,
    python: Path,
    pytest_carrier: Path,
    expected_pytest_carrier_sha256: str,
    builtin_architecture_ids: Sequence[str],
    witness_architecture_id: str,
    forbidden_roots: tuple[Path, ...] = (),
) -> dict[str, Any]:
    """Build the exact reference execution view from a fresh collection."""

    boundary = __import__(
        "scripts.experiments.es.boundary_proofs", fromlist=["boundary_proofs"]
    )
    execution = build_desired_state_execution_manifest(
        selector_manifest,
        source_census=source_census,
    )
    try:
        contract = boundary.validate_contract(
            execution,
            consumer_rows=source_census["consumer_rows"],
            expected_runner_sha256=_BOUNDARY_PROOF_RUNNER_SHA256,
        )
        interpreter, interpreter_target = boundary._verify_pinned_python(Path(python))
        carrier = boundary._verify_pytest_carrier(
            Path(pytest_carrier),
            expected_sha256=expected_pytest_carrier_sha256,
        )
        root, _ = boundary._verify_tree(Path(workspace), expected_tree)
        with tempfile.TemporaryDirectory(prefix="es-reference-provider-collection-") as raw:
            report = boundary._run_pytest_observation(
                contract,
                python=interpreter,
                workspace=root,
                report_path=(Path(raw) / "provider-collection-origin.json").resolve(),
                forbidden_roots=forbidden_roots,
                pytest_carrier=carrier,
                python_target=interpreter_target,
                collect_only=True,
            )
        projection = project_desired_state_provider_nodes(
            execution,
            collected_node_ids=report["node_ids"],
            builtin_architecture_ids=builtin_architecture_ids,
            witness_architecture_id=witness_architecture_id,
        )
        boundary.validate_contract(
            projection,
            consumer_rows=source_census["consumer_rows"],
            expected_runner_sha256=_BOUNDARY_PROOF_RUNNER_SHA256,
        )
        boundary._verify_tree(root, expected_tree)
        return projection
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(
            "reference_execution_projection_invalid",
            str(workspace),
            "reference provider-node projection failed",
        ) from exc


def execute_reference_desired_state(
    reference: ReferenceProduct, *, workspace: Path
) -> list[dict[str, Any]]:
    """Execute the already-validated proof contract in one detached workspace."""

    if not isinstance(reference, ReferenceProduct):
        _reference_fail(
            "reference_execution_invalid",
            reference,
            "reference must be a validated ReferenceProduct",
        )
    if (
        reference._validation_provenance
        is not _REFERENCE_PRODUCT_VALIDATION_PROVENANCE
        or not isinstance(reference._record_path, Path)
        or not isinstance(reference._schema_path, Path)
        or not isinstance(reference._expected_record_sha256, str)
        or _SHA256_RE.fullmatch(reference._expected_record_sha256) is None
    ):
        _reference_fail(
            "reference_execution_invalid",
            reference,
            "reference was not minted by the validated loader",
        )
    try:
        current_record_digest = validate_record_sha256(reference.record)
        selector_digest = validate_record_sha256(reference._selector_manifest)
        census_digest = validate_record_sha256(reference._source_census)
        bindings = reference.record["bindings"]
        selector_binding_digest = bindings["selector_manifest"]["record_sha256"]
        census_binding_digest = bindings["source_census"]["record_sha256"]
    except CalibrationError:
        raise
    except (KeyError, TypeError) as exc:
        raise CalibrationError(
            "reference_execution_invalid",
            reference.record,
            "reference authority bindings are malformed",
        ) from exc
    if (
        current_record_digest != reference._expected_record_sha256
        or selector_digest != selector_binding_digest
        or census_digest != census_binding_digest
    ):
        _reference_fail(
            "reference_execution_invalid",
            {
                "record": current_record_digest,
                "expected_record": reference._expected_record_sha256,
                "selector": selector_digest,
                "selector_binding": selector_binding_digest,
                "source_census": census_digest,
                "source_census_binding": census_binding_digest,
            },
            "loaded reference authority changed after validation",
        )
    fresh = load_reference_product(
        reference._record_path,
        schema_path=reference._schema_path,
        expected_record_sha256=reference._expected_record_sha256,
    )
    if (
        fresh.record != reference.record
        or fresh._selector_manifest != reference._selector_manifest
        or fresh._source_census != reference._source_census
    ):
        _reference_fail(
            "reference_execution_invalid",
            str(reference._record_path),
            "fresh reference authority differs from the loaded authority",
        )
    candidate = _canonical_directory(str(workspace), label="reference proof workspace")
    expected_tree = fresh.record["lineage"]["reference_tree"]
    expected_commit = fresh.record["lineage"]["reference_commit"]
    try:
        head = _reference_git(candidate, "rev-parse", "HEAD").decode("ascii").strip()
        tree = _reference_git(candidate, "rev-parse", "HEAD^{tree}").decode(
            "ascii"
        ).strip()
        status = _reference_git(candidate, "status", "--porcelain=v1")
        symbolic = subprocess.run(
            (
                str(PINNED_GIT_EXECUTABLE),
                "-C",
                str(candidate),
                "symbolic-ref",
                "-q",
                "HEAD",
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        )
    except CalibrationError:
        raise
    except OSError as exc:
        raise CalibrationError(
            "reference_execution_invalid",
            str(candidate),
            "proof workspace query failed",
        ) from exc
    if (
        head != expected_commit
        or tree != expected_tree
        or status
        or symbolic.returncode == 0
    ):
        _reference_fail(
            "reference_execution_invalid",
            {"head": head, "tree": tree, "status": status.decode("utf-8")},
            "proof workspace is not the clean detached reference tree",
        )
    boundary = __import__(
        "scripts.experiments.es.boundary_proofs", fromlist=["boundary_proofs"]
    )
    execution = fresh.record["desired_state_proofs"]["execution"]
    try:
        evaluator_evidence = fresh.record["evaluator_evidence"]
        witness_architecture_id = evaluator_evidence["witness_architecture_id"]
        architecture_ids = tuple(evaluator_evidence["architecture_ids"])
        builtin_architecture_ids = tuple(
            architecture_id
            for architecture_id in architecture_ids
            if architecture_id != witness_architecture_id
        )
        if len(builtin_architecture_ids) + 1 != len(architecture_ids):
            _reference_fail(
                "reference_execution_projection_invalid",
                architecture_ids,
                "validated evaluator architecture partition is ambiguous",
            )
        execution_manifest = build_reference_desired_state_execution_manifest(
            fresh._selector_manifest,
            source_census=fresh._source_census,
            workspace=candidate.resolve(),
            expected_tree=expected_tree,
            python=Path(execution["python"]["path"]),
            pytest_carrier=Path(execution["pytest_carrier"]["path"]),
            expected_pytest_carrier_sha256=execution["pytest_carrier"]["sha256"],
            builtin_architecture_ids=builtin_architecture_ids,
            witness_architecture_id=witness_architecture_id,
        )
        result = boundary.execute_desired_state(
            execution_manifest,
            consumer_rows=fresh._source_census["consumer_rows"],
            workspace=candidate.resolve(),
            expected_tree=expected_tree,
            expected_runner_sha256=_BOUNDARY_PROOF_RUNNER_SHA256,
            python=Path(execution["python"]["path"]),
            pytest_carrier=Path(execution["pytest_carrier"]["path"]),
            expected_pytest_carrier_sha256=execution["pytest_carrier"]["sha256"],
            expected_result_rows=fresh.record["desired_state_proofs"][
                "result_rows"
            ],
        )
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(
            "reference_execution_invalid",
            str(candidate),
            "desired-state proof execution failed",
        ) from exc
    return result


def _published_schema_path(value: str | Path, *, role: str) -> Path:
    expected_relative = _VALIDATE_A1_SCHEMA_PATHS[role]
    expected = _REPOSITORY_ROOT / expected_relative
    supplied = Path(value)
    if not supplied.is_absolute():
        supplied = _REPOSITORY_ROOT / supplied
    try:
        supplied_metadata = supplied.lstat()
        supplied_resolved = supplied.resolve(strict=True)
        expected_resolved = expected.resolve(strict=True)
    except OSError as exc:
        raise CalibrationError(
            "schema_authority_invalid",
            str(value),
            f"{role} schema is missing or unreadable",
        ) from exc
    if (
        supplied_resolved != expected_resolved
        or stat.S_ISLNK(supplied_metadata.st_mode)
        or not stat.S_ISREG(supplied_metadata.st_mode)
    ):
        raise CalibrationError(
            "schema_authority_invalid",
            str(value),
            f"{role} must use the exact published schema",
        )
    return expected_resolved


def _policy_schema_bindings(
    policy: Mapping[str, object],
    supplied: Mapping[str, Path],
) -> None:
    rows = policy.get("schema_bindings")
    if not isinstance(rows, list):
        raise CalibrationError(
            "authority_binding_invalid", rows, "policy schema bindings are absent"
        )
    by_role = {
        row.get("role"): row
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("role"), str)
    }
    for role, path in supplied.items():
        row = by_role.get(role)
        expected_relative = _VALIDATE_A1_SCHEMA_PATHS[role].as_posix()
        try:
            raw = path.read_bytes()
        except OSError as exc:
            raise CalibrationError(
                "schema_authority_invalid", str(path), "schema became unreadable"
            ) from exc
        if row != {
            "role": role,
            "path": expected_relative,
            "byte_count": len(raw),
            "sha256": _sha256_bytes(raw),
        }:
            raise CalibrationError(
                "authority_binding_invalid",
                row,
                f"policy binding for {role} schema drifted",
            )


def _validate_task0_review_adoption(
    adoption: Mapping[str, object],
    *,
    policy: Mapping[str, object],
    census: Mapping[str, object],
    anchor: Mapping[str, object],
) -> None:
    source_census = __import__(
        "scripts.experiments.es.source_census", fromlist=["source_census"]
    )
    bindings = adoption.get("bindings")
    if not isinstance(bindings, dict):
        raise CalibrationError(
            "authority_binding_invalid", bindings, "review adoption bindings are absent"
        )
    expected_core = {
        "preedit_policy_sha256": policy.get("record_sha256"),
        "source_census_sha256": census.get("record_sha256"),
        "a1_anchor_sha256": anchor.get("record_sha256"),
    }
    if any(bindings.get(key) != value for key, value in expected_core.items()):
        raise CalibrationError(
            "authority_binding_invalid",
            bindings,
            "review adoption does not bind the supplied Task-0 authorities",
        )
    evidence = _REPOSITORY_ROOT / _TASK0_EVIDENCE_RELATIVE
    tombstone_path = evidence / "feasibility-post-purge-tombstone.json"
    tombstone_schema = evidence / "feasibility-post-purge-tombstone.schema.json"
    capture_path = evidence / "feasibility-capture-manifest.json"
    capture_schema = evidence / "feasibility-capture-manifest.schema.json"
    try:
        tombstone = load_canonical_record(
            tombstone_path,
            schema_path=tombstone_schema,
            expected_record_sha256=str(bindings["post_purge_tombstone_sha256"]),
        )
        capture_digest = tombstone["capture_manifest"]["sha256"]
        capture = load_canonical_record(
            capture_path,
            schema_path=capture_schema,
            expected_record_sha256=capture_digest,
        )
        source_census.validate_post_purge_tombstone(
            tombstone,
            capture_manifest=capture,
        )
        source_census.validate_review_adoption(
            adoption,
            expected_bindings={
                "plan_sha256": bindings["plan_sha256"],
                "preedit_policy_sha256": policy["record_sha256"],
                "source_census_sha256": census["record_sha256"],
                "selector_manifest_sha256": bindings["selector_manifest_sha256"],
                "a1_anchor_sha256": anchor["record_sha256"],
            },
            expected_post_purge_tombstone_sha256=tombstone["record_sha256"],
            post_purge_tombstone=tombstone,
            review_view_root=_REPOSITORY_ROOT,
        )
    except CalibrationError:
        raise
    except Exception as exc:
        raise CalibrationError(
            "authority_binding_invalid",
            adoption,
            "Task-0 review adoption validation failed",
        ) from exc


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate-a1")
    for option in (
        "policy",
        "policy-schema",
        "expected-policy-sha256",
        "source-census",
        "source-census-schema",
        "expected-source-census-sha256",
        "task0-review-adoption",
        "task0-review-adoption-schema",
        "expected-task0-review-adoption-sha256",
        "a1-anchor",
        "a1-anchor-schema",
        "expected-a1-anchor-sha256",
    ):
        validate.add_argument(f"--{option}", required=True)
    return parser


def _command_validate_a1(args: argparse.Namespace) -> None:
    schema_paths = {
        "preedit_policy": _published_schema_path(
            args.policy_schema, role="preedit_policy"
        ),
        "source_census": _published_schema_path(
            args.source_census_schema, role="source_census"
        ),
        "review_adoption": _published_schema_path(
            args.task0_review_adoption_schema, role="review_adoption"
        ),
        "a1_anchor": _published_schema_path(
            args.a1_anchor_schema, role="a1_anchor"
        ),
    }
    policy = load_canonical_record(
        Path(args.policy),
        schema_path=schema_paths["preedit_policy"],
        expected_record_sha256=args.expected_policy_sha256,
    )
    _policy_schema_bindings(policy, schema_paths)
    census = load_canonical_record(
        Path(args.source_census),
        schema_path=schema_paths["source_census"],
        expected_record_sha256=args.expected_source_census_sha256,
    )
    adoption = load_canonical_record(
        Path(args.task0_review_adoption),
        schema_path=schema_paths["review_adoption"],
        expected_record_sha256=args.expected_task0_review_adoption_sha256,
    )
    if census.get("preedit_policy_sha256") != policy.get("record_sha256"):
        raise CalibrationError(
            "authority_binding_invalid",
            census.get("preedit_policy_sha256"),
            "source census binds another policy",
        )
    metric = policy.get("a1", {}).get("metric") if isinstance(policy.get("a1"), dict) else None
    if not isinstance(metric, dict):
        raise CalibrationError(
            "authority_binding_invalid", metric, "policy A1 metric is absent"
        )
    contract = GitContract(
        executable=Path(metric["git_executable"]),
        version=str(metric["git_version"]).removeprefix("git version "),
        executable_sha256=metric["git_sha256"],
        diff_controls=tuple(metric["diff_controls"]),
        policy_sha256=policy["record_sha256"],
    )
    calibration = validate_a1_anchor(
        Path(args.a1_anchor),
        schema_path=schema_paths["a1_anchor"],
        expected_record_sha256=args.expected_a1_anchor_sha256,
        expected_preedit_policy_sha256=policy["record_sha256"],
        git_contract=contract,
    )
    anchor = calibration.record
    policy_a1 = policy["a1"]
    if (
        policy_a1.get("evidence_root") != anchor.get("evidence_root")
        or policy_a1.get("members") != anchor.get("members")
        or any(
            policy_a1["metric"].get(key) != anchor["metric"].get(key)
            for key in (
                "metric_version",
                "implementation_additions",
                "implementation_deletions",
                "candidate_postimage_physical_lines",
            )
        )
    ):
        raise CalibrationError(
            "authority_binding_invalid", policy_a1, "policy and A1 anchor drifted"
        )
    _validate_task0_review_adoption(
        adoption,
        policy=policy,
        census=census,
        anchor=anchor,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-a1":
            _command_validate_a1(args)
        else:  # pragma: no cover - argparse closes the command domain.
            parser.error(f"unsupported command: {args.command}")
    except CalibrationError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
