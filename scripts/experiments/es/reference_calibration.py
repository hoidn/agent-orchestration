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
    _record_path: Path | None = field(default=None, repr=False, compare=False)
    _schema_path: Path | None = field(default=None, repr=False, compare=False)
    _expected_record_sha256: str | None = field(
        default=None, repr=False, compare=False
    )
    _validation_provenance: object | None = field(
        default=None, repr=False, compare=False
    )


_REFERENCE_EVALUATION_CAPTURE_SEAL = object()


@dataclass(frozen=True)
class _ReferenceEvaluationCapture:
    """Opaque proof that the controller executed two exact reference copies."""

    reference_repository: Path
    reference_commit: str
    reference_tree: str
    replay: dict[str, Any]
    payload: bytes
    _seal: object = field(repr=False, compare=False)


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


_F1V2_RESPONSIBILITY_IDS = frozenset(
    {
        "PUBLIC_RESOLUTION",
        "TRANSACTIONAL_TORCH_APPLICATION",
        "TOLERANT_PATH_RETIREMENT",
        "LEGACY_STATE_ISOLATION",
        "BOUNDARY_VALIDATION_AND_DERIVATION",
        "CONSUMER_MIGRATION",
    }
)


def _reference_git_bytes(repository: Path, *args: str) -> bytes:
    try:
        return subprocess.run(
            (str(PINNED_GIT_EXECUTABLE), "-C", str(repository), *args),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        raise CalibrationError(
            "reference_repository_invalid",
            {"repository": str(repository), "args": args},
            "bound Git query failed",
        ) from exc


def _normalize_reference_observations(
    observations: object,
    *,
    clause_ids: Sequence[str],
) -> dict[str, object]:
    if not isinstance(observations, list) or [
        row.get("clause_id") if isinstance(row, dict) else None
        for row in observations
    ] != list(clause_ids):
        raise CalibrationError(
            "reference_evaluation_invalid",
            observations,
            "real evaluator observations do not cover every clause in order",
        )
    rows: list[dict[str, object]] = []
    for observation in observations:
        assert isinstance(observation, dict)
        if (
            set(observation)
            != {"clause_id", "details", "evidence", "satisfied"}
            or observation["satisfied"] is not True
            or not isinstance(observation["details"], str)
            or not observation["details"]
            or not isinstance(observation["evidence"], list)
            or not observation["evidence"]
            or any(
                not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None
                for digest in observation["evidence"]
            )
        ):
            raise CalibrationError(
                "reference_evaluation_invalid",
                observation,
                "real evaluator returned one failed or malformed observation",
            )
        rows.append(
            {
                "clause_id": observation["clause_id"],
                "details": observation["details"],
                "evidence_digest": _sha256_bytes(
                    canonical_json_bytes(observation["evidence"])
                ),
                "satisfied": True,
            }
        )
    return {
        "schema_version": "es_f1_reference_evaluation_result.v1",
        "clause_results": rows,
    }


def capture_reference_evaluation_replay(
    *,
    reference_repository: Path,
    reference_commit: str,
    reference_tree: str,
    output_root: Path,
) -> _ReferenceEvaluationCapture:
    """Materialize and evaluate the exact reference twice; accept no verdict input."""

    repository = _canonical_root(
        Path(reference_repository), label="reference repository"
    )
    if (
        re.fullmatch(r"[0-9a-f]{40}", reference_commit) is None
        or re.fullmatch(r"[0-9a-f]{40}", reference_tree) is None
        or _reference_git_bytes(repository, "rev-parse", reference_commit)
        != f"{reference_commit}\n".encode("ascii")
        or _reference_git_bytes(
            repository, "rev-parse", f"{reference_commit}^{{tree}}"
        )
        != f"{reference_tree}\n".encode("ascii")
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            {"commit": reference_commit, "tree": reference_tree},
            "reference evaluation target identity drifted",
        )
    root = Path(output_root)
    if (
        not root.is_absolute()
        or root.resolve(strict=False) != root
        or os.path.lexists(root)
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            str(root),
            "reference evaluation output root must be canonical, absolute, and absent",
        )
    try:
        root.parent.mkdir(parents=True, exist_ok=True)
        root.mkdir()
    except OSError as exc:
        raise CalibrationError(
            "reference_evaluation_invalid",
            str(root),
            "reference evaluation output root could not be created",
        ) from exc
    source = __import__(
        "orchestrator.workflow.run_ref.source", fromlist=["source"]
    )
    evaluator = __import__(
        "scripts.experiments.es.f1_evaluator", fromlist=["f1_evaluator"]
    )
    runs: list[dict[str, object]] = []
    normalized_payloads: list[bytes] = []
    for run_id in (
        "reference-materialization-a",
        "reference-materialization-b",
    ):
        run_root = root / run_id
        materialized = source.materialize_source(
            source.SourceRequest(
                locator=str(repository),
                commit=reference_commit,
            ),
            run_ref_root=run_root / "run-ref",
            workspace=run_root / "workspace",
        )
        if (
            materialized.resolved_commit_sha != reference_commit
            or materialized.verified_git_tree.value != f"git-tree:{reference_tree}"
        ):
            raise CalibrationError(
                "reference_evaluation_invalid",
                run_id,
                "reference materialization identity drifted",
            )
        observations = evaluator.evaluate_candidate(
            candidate_evidence_path=(
                materialized.workspace_path / "es_f1_candidate_evidence.json"
            ),
            output_root=run_root / "evaluation",
            workspace=materialized.workspace_path,
        )
        normalized_result = _normalize_reference_observations(
            observations,
            clause_ids=evaluator.HARD_CLAUSE_IDS,
        )
        normalized = canonical_json_bytes(normalized_result)
        normalized_payloads.append(normalized)
        runs.append(
            {
                "run_id": run_id,
                "materialization": {
                    "resolved_commit": materialized.resolved_commit_sha,
                    "verified_git_tree": materialized.verified_git_tree.value,
                    "source_tree_manifest_sha256": (
                        materialized.source_tree_manifest.digest
                    ),
                    "post_setup_tree_manifest_sha256": (
                        materialized.post_setup_tree_manifest.digest
                    ),
                },
                "normalized_result": normalized_result,
                "normalized_result_sha256": _sha256_bytes(normalized),
            }
        )
    if normalized_payloads[0] != normalized_payloads[1]:
        raise CalibrationError(
            "reference_evaluation_invalid",
            [row["normalized_result_sha256"] for row in runs],
            "independent reference evaluations diverged",
        )
    result_digest = _sha256_bytes(normalized_payloads[0])
    replay = {
        "target_tree": reference_tree,
        "runs": runs,
        "normalized_results_byte_equal": True,
        "normalized_result_sha256": result_digest,
    }
    payload = canonical_json_bytes(replay)
    return _ReferenceEvaluationCapture(
        reference_repository=repository,
        reference_commit=reference_commit,
        reference_tree=reference_tree,
        replay=copy.deepcopy(replay),
        payload=payload,
        _seal=_REFERENCE_EVALUATION_CAPTURE_SEAL,
    )


def _reference_text_tree(
    repository: Path, treeish: str
) -> tuple[dict[str, _FileSnapshot], dict[str, tuple[bytes, int, str, str | None]]]:
    rows: dict[str, _FileSnapshot] = {}
    entries: dict[str, tuple[bytes, int, str, str | None]] = {}
    raw = _reference_git_bytes(
        repository, "ls-tree", "-r", "-z", "--full-tree", treeish
    )
    for entry in raw.split(b"\0"):
        if not entry:
            continue
        try:
            metadata, raw_path = entry.split(b"\t", 1)
            raw_mode, object_type, raw_oid = metadata.split(b" ", 2)
            path = raw_path.decode("utf-8", errors="strict")
            mode = int(raw_mode, 8)
            oid = raw_oid.decode("ascii")
        except (UnicodeDecodeError, ValueError) as exc:
            raise CalibrationError(
                "reference_metric_invalid", entry, "Git tree entry is malformed"
            ) from exc
        try:
            path = _canonical_relative_path(path, label="reference tree path")
        except CalibrationError as exc:
            raise CalibrationError(
                "reference_metric_invalid",
                path,
                "Git tree path is not canonical relative text",
            ) from exc
        if object_type != b"blob" or mode not in {0o100644, 0o100755}:
            entries[path] = (object_type, mode, oid, "nonregular")
            continue
        payload = _reference_git_bytes(repository, "cat-file", "blob", oid)
        if b"\0" in payload:
            entries[path] = (object_type, mode, oid, "binary")
            continue
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            entries[path] = (object_type, mode, oid, "non_utf8")
            continue
        entries[path] = (object_type, mode, oid, None)
        rows[path] = _FileSnapshot(
            path=path,
            blob_id=oid,
            mode=mode & 0o777,
            physical_lines=len(text.splitlines()),
            payload=payload,
        )
    return rows, entries


def _write_reference_metric_tree(
    root: Path, rows: Mapping[str, _FileSnapshot]
) -> None:
    for relative, row in rows.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(row.payload)
        target.chmod(row.mode)


def build_reference_metric(
    *,
    repository: Path,
    task_seed_commit: str,
    reference_commit: str,
    changed_path_policies: Sequence[MetricPathPolicy],
    git_contract: GitContract,
) -> dict[str, Any]:
    """Replay the frozen metric over one already-adapted reference commit."""

    repository = _canonical_root(Path(repository), label="reference repository")
    supplied = _validate_path_policies(
        changed_path_policies,
        allowed_responsibility_ids=_F1V2_RESPONSIBILITY_IDS,
    )
    base, base_entries = _reference_text_tree(repository, task_seed_commit)
    candidate, candidate_entries = _reference_text_tree(repository, reference_commit)
    unsafe_changed = [
        {
            "path": path,
            "base_kind": (
                None if path not in base_entries else base_entries[path][3]
            ),
            "candidate_kind": (
                None if path not in candidate_entries else candidate_entries[path][3]
            ),
        }
        for path in sorted(set(base_entries) | set(candidate_entries))
        if base_entries.get(path) != candidate_entries.get(path)
        and (
            (path in base_entries and base_entries[path][3] is not None)
            or (
                path in candidate_entries
                and candidate_entries[path][3] is not None
            )
        )
    ]
    if unsafe_changed:
        raise CalibrationError(
            "reference_metric_invalid",
            unsafe_changed,
            "changed Git entries must be regular UTF-8 text files without NUL bytes",
        )
    with tempfile.TemporaryDirectory(prefix=".es-f1v2-metric.") as temporary:
        temporary_root = Path(temporary)
        base_root = temporary_root / "base"
        candidate_root = temporary_root / "candidate"
        base_root.mkdir()
        candidate_root.mkdir()
        _write_reference_metric_tree(base_root, base)
        _write_reference_metric_tree(candidate_root, candidate)
        unclassified = _classify_numstat_rows(
            parse_numstat_z(_run_git_diff(git_contract, base, candidate)),
            base_root=base_root,
            candidate_root=candidate_root,
            base=base,
            candidate=candidate,
        )
        policies: list[MetricPathPolicy] = []
        used: set[str] = set()
        for row in unclassified:
            path = row.candidate_path or row.base_path
            assert path is not None
            if row.change_kind == "unchanged":
                policies.append(
                    MetricPathPolicy(path, "benchmark_task_seed_asset", ())
                )
                continue
            policy = supplied.get(path)
            if policy is None:
                raise CalibrationError(
                    "reference_metric_invalid",
                    path,
                    "changed reference path lacks an explicit classification",
                )
            policies.append(policy)
            used.add(path)
        if used != set(supplied):
            raise CalibrationError(
                "reference_metric_invalid",
                sorted(set(supplied) - used),
                "changed-path classification names no changed reference path",
            )
        measurement = measure_implementation_delta(
            base_root=base_root,
            candidate_root=candidate_root,
            path_policies=tuple(policies),
            allowed_responsibility_ids=_F1V2_RESPONSIBILITY_IDS,
            git_contract=git_contract,
        )
    if not 5_000 <= measurement.implementation_additions <= 10_000:
        raise CalibrationError(
            "reference_metric_invalid",
            measurement.implementation_additions,
            "adapted reference is outside the inclusive calibration band",
        )
    result = json.loads(canonical_json_bytes(asdict(measurement)))
    result["base_commit"] = task_seed_commit
    result["base_tree"] = _reference_git_bytes(
        repository, "rev-parse", f"{task_seed_commit}^{{tree}}"
    ).decode("ascii").strip()
    result["reference_commit"] = reference_commit
    result["reference_tree"] = _reference_git_bytes(
        repository, "rev-parse", f"{reference_commit}^{{tree}}"
    ).decode("ascii").strip()
    result["historical_churn"] = {
        "authority": "non_authoritative_inclusive_per_commit_churn",
        "production_additions": 8_698,
        "production_deletions": 11_197,
    }
    return result


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
_F1V2_EVIDENCE_RELATIVE = _TASK0_EVIDENCE_RELATIVE / "f1v2"
_F1V2_REFERENCE_BINDINGS = {
    "preedit_policy": (
        _TASK0_EVIDENCE_RELATIVE / "preedit-policy-manifest.json",
        _TASK0_EVIDENCE_RELATIVE / "preedit-policy-manifest.schema.json",
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
    "task_profile": (
        PurePosixPath("experiments/orc_effectiveness/f1_es/task-profile.json"),
        PurePosixPath("experiments/orc_effectiveness/f1_es/task-profile.schema.json"),
    ),
    "configuration_consumer_census": (
        _F1V2_EVIDENCE_RELATIVE / "configuration-consumer-census.json",
        _F1V2_EVIDENCE_RELATIVE / "configuration-consumer-census.schema.json",
    ),
    "preedit_selector_manifest": (
        _F1V2_EVIDENCE_RELATIVE / "preedit-selector-manifest.json",
        _F1V2_EVIDENCE_RELATIVE / "preedit-selector-manifest.schema.json",
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
    "governing_design": (
        PurePosixPath(
            "docs/superpowers/specs/2026-08-06-es-f1v2-config-ownership-task-design.md"
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
}


def _raw_file_binding(relative: PurePosixPath) -> tuple[Path, bytes]:
    path = _REPOSITORY_ROOT / relative
    try:
        metadata = path.lstat()
        raw = path.read_bytes()
    except OSError as exc:
        raise CalibrationError(
            "reference_binding_invalid", str(relative), "bound file is unreadable"
        ) from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise CalibrationError(
            "reference_binding_invalid",
            str(relative),
            "bound file must be a regular non-symlink",
        )
    return path, raw


def build_reference_bindings() -> dict[str, dict[str, Any]]:
    """Bind exactly the current F1v2 Task-0 through Task-3 authorities."""

    result: dict[str, dict[str, Any]] = {}
    for binding_id, (relative, schema_relative) in _F1V2_REFERENCE_BINDINGS.items():
        path, raw = _raw_file_binding(relative)
        row: dict[str, Any] = {"path": relative.as_posix(), "sha256": _sha256_bytes(raw)}
        if path.suffix == ".json":
            value = _parse_json_bytes(raw, label=path)
            if not isinstance(value, dict) or raw != canonical_json_bytes(value):
                raise CalibrationError(
                    "reference_binding_invalid",
                    binding_id,
                    "bound JSON is not one canonical object",
                )
            if "record_sha256" in value:
                row["record_sha256"] = validate_record_sha256(value)
        if schema_relative is not None:
            _, schema_raw = _raw_file_binding(schema_relative)
            row.update(
                {
                    "schema_path": schema_relative.as_posix(),
                    "schema_sha256": _sha256_bytes(schema_raw),
                }
            )
        result[binding_id] = row
    return result


_F1V2_TREATMENT_WORKFLOW = PurePosixPath(
    "workflows/experiments/qa_placement_effectiveness/qa_placement_arms.orc"
)
_F1V2_PROMPT_EXTERNS = _F1V2_TREATMENT_WORKFLOW.with_name("prompts.json")
_F1V2_EVALUATOR_RUBRIC = (
    _F1V2_TREATMENT_WORKFLOW.parent / "prompts" / "trial_rubric.md"
)
_F1V2_PROVIDER_ARGV = (
    "codex",
    "exec",
    "--dangerously-bypass-approvals-and-sandbox",
    "--skip-git-repo-check",
    "--model",
    "gpt-5.5",
    "--config",
    "reasoning_effort=high",
)
_F1V2_METERED_ARGV = (
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
_F1V2_CAMPAIGN_COMMITS = {
    "campaign_parent": "99efda11155119161d371d5d0e5ec7c33a720594",
    "campaign_start": "7d630bcc14191ec5f8206a9ceb097a62a1c011c6",
    "campaign_end": "015ca6e93d78c5f7f42adf0cae883d895de5f80c",
}
F1V2_HISTORICAL_PRODUCTION_PATHS = (
    "ptycho/config/__init__.py",
    "ptycho/config/config.py",
    "ptycho/config/legacy_state.py",
    "ptycho/config/resolution.py",
    "ptycho/config/strict_types.py",
    "ptycho/evaluation.py",
    "ptycho/inference.py",
    "ptycho/metadata.py",
    "ptycho/misc.py",
    "ptycho/model.py",
    "ptycho/nongrid_simulation.py",
    "ptycho/physics.py",
    "ptycho/raw_data.py",
    "ptycho/workflows/backend_selector.py",
    "ptycho/workflows/components.py",
    "ptycho/workflows/grid_lines_workflow.py",
    "ptycho_torch/api/api_helper.py",
    "ptycho_torch/api/base_api.py",
    "ptycho_torch/api/example_predict.py",
    "ptycho_torch/api/example_train.py",
    "ptycho_torch/api/example_train_lightning.py",
    "ptycho_torch/api/example_train_predict_in_memory.py",
    "ptycho_torch/api/example_use.py",
    "ptycho_torch/beta_modules/model.py",
    "ptycho_torch/cli/shared.py",
    "ptycho_torch/config_bridge.py",
    "ptycho_torch/config_factory.py",
    "ptycho_torch/config_params.py",
    "ptycho_torch/config_resolution.py",
    "ptycho_torch/data_container_bridge.py",
    "ptycho_torch/dataloader.py",
    "ptycho_torch/dset_loader_pt_mmap.py",
    "ptycho_torch/execution_request.py",
    "ptycho_torch/inference.py",
    "ptycho_torch/model.py",
    "ptycho_torch/model_manager.py",
    "ptycho_torch/notebooks/analysis.py",
    "ptycho_torch/raw_data_bridge.py",
    "ptycho_torch/train.py",
    "ptycho_torch/train_lightning_only.py",
    "ptycho_torch/utils.py",
    "ptycho_torch/workflows/components.py",
    "ptycho_torch/workflows/recon_logging.py",
    "scripts/compare_models.py",
    "scripts/grid_study/__init__.py",
    "scripts/grid_study/evaluate_results.py",
    "scripts/grid_study/grid_data_generator.py",
    "scripts/grid_study/inference_pipeline.py",
    "scripts/grid_study/probe_utils.py",
    "scripts/grid_study/run_grid_study.py",
    "scripts/grid_study/train_models.py",
    "scripts/inference/baseline_inference.py",
    "scripts/inference/inference.py",
    "scripts/pytorch_api_demo.py",
    "scripts/reconstruction/hio_cdi_benchmark.py",
    "scripts/run_baseline.py",
    "scripts/simulation/run_with_synthetic_lines.py",
    "scripts/simulation/simulate_and_save.py",
    "scripts/studies/aligned_ablation_variant_grid.py",
    "scripts/studies/cdi_natural_patch_benchmark.py",
    "scripts/studies/dose_response_study.py",
    "scripts/studies/grid_lines_compare_wrapper.py",
    "scripts/studies/grid_lines_torch_runner.py",
    "scripts/studies/grid_study_dataset_builder.py",
    "scripts/studies/make_lines_datasets.py",
    "scripts/studies/make_synthetic_truth_datasets.py",
    "scripts/studies/ood_fig5_metrics.py",
    "scripts/studies/probe_mischaracterization_stress_test.py",
    "scripts/studies/tf_reference_cnn_runner.py",
    "scripts/studies/varpro_probe_ablation_runner.py",
    "scripts/training/train.py",
)
F1V2_HISTORICAL_PRODUCTION_PATH_COUNT = 71
F1V2_HISTORICAL_PRODUCTION_PATHS_SHA256 = (
    "sha256:c32e9fbea1ff3b04158ee71ae13f1cb9b9f3afa5db1c9cd48fcdefead6ce13a5"
)
F1V2_REFERENCE_CANARY = "F1V2_CONTROLLER_ONLY_REFERENCE_CANARY_8F191031"
F1V2_DECOMPOSITION_VOCABULARY = (
    "adapted-campaign-path-ledger",
    "configuration-resolution-reference-shape",
    "controller-only-reference-materialization",
)


def _f1v2_packet_payloads() -> tuple[bytes, bytes]:
    packets = __import__("orchestrator.workflow.trial.packets", fromlist=["packets"])
    common = {
        "opaque_label": "opaque-" + "1" * 64,
        "observation_include": (
            "task_spec",
            "validated_result",
            "workspace_delta",
            "check_results",
            "declared_artifacts",
            "failure_evidence",
        ),
        "sealed_identity_values": ("DIRECT", "DESIGN_QA", "PRODUCT_QA", "RICH"),
        "max_item_bytes": 4_194_304,
        "max_packet_bytes": 8_388_608,
    }
    task_spec = {
        "inputs": {
            "task": "task",
            "check_contract": "checks",
            "model": "gpt-5.5",
            "effort": "high",
        }
    }
    completed = packets.build_trial_evaluation_packet(
        **common,
        observations={
            "task_spec": task_spec,
            "validated_result": True,
            "workspace_delta": {
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
            },
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
    return canonical_json_bytes(completed), canonical_json_bytes(failed)


def _f1v2_provider_surfaces(
    task_seed_manifest: Mapping[str, Any],
) -> list[dict[str, Any]]:
    provider_boundary = __import__(
        "scripts.experiments.es.provider_boundary", fromlist=["provider_boundary"]
    )
    evaluation = __import__(
        "orchestrator.workflow.trial.evaluation", fromlist=["evaluation"]
    )
    repository = Path(task_seed_manifest["repository"]["locator"])
    commit = str(task_seed_manifest["recipe"]["commit"])
    surfaces = [
        {
            "surface_id": f"visible_task_asset:{row['target_path']}",
            "surface_class": "visible_task_asset",
            "logical_path": row["target_path"],
            "payload": _reference_git_bytes(
                repository, "show", f"{commit}:{row['target_path']}"
            ),
        }
        for row in task_seed_manifest["visible_assets"]["rows"]
    ]
    for surface_id, surface_class, relative in (
        ("treatment_prompt", "treatment_prompt", _F1V2_TREATMENT_WORKFLOW),
        ("prompt_externs", "prompt_externs", _F1V2_PROMPT_EXTERNS),
        ("evaluator_rubric", "evaluator_rubric", _F1V2_EVALUATOR_RUBRIC),
    ):
        _, raw = _raw_file_binding(relative)
        surfaces.append(
            {
                "surface_id": surface_id,
                "surface_class": surface_class,
                "logical_path": relative.as_posix(),
                "payload": raw,
            }
        )
    environment = provider_boundary.boundary_environment(
        shim_dir=Path("/run/orc-es-f1/provider-shim"),
        manifest=provider_boundary.ManifestPublication(
            Path("/run/orc-es-f1/provider-boundary.json"), "sha256:" + "3" * 64
        ),
        inherited_path="/usr/local/bin:/usr/bin:/bin",
    )
    completed_packet, failed_packet = _f1v2_packet_payloads()
    surfaces.extend(
        (
            {
                "surface_id": "trial_evaluator_instruction",
                "surface_class": "evaluator_instruction",
                "logical_path": evaluation.TRIAL_EVALUATOR_INSTRUCTION_ID,
                "payload": evaluation.TRIAL_EVALUATOR_INSTRUCTION.encode(),
            },
            {
                "surface_id": "logical_outer_argv",
                "surface_class": "provider_argv",
                "logical_path": "task3a://provider/outer-argv",
                "payload": canonical_json_bytes(list(_F1V2_PROVIDER_ARGV)),
            },
            {
                "surface_id": "logical_metered_argv",
                "surface_class": "provider_argv",
                "logical_path": "task3a://provider/metered-argv",
                "payload": canonical_json_bytes(list(_F1V2_METERED_ARGV)),
            },
            {
                "surface_id": "logical_provider_environment",
                "surface_class": "provider_environment",
                "logical_path": "task3a://provider/environment",
                "payload": canonical_json_bytes(environment),
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
    return surfaces


def _f1v2_object_ids(repository: Path, ref: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            row.decode("ascii").split(" ", 1)[0]
            for row in _reference_git_bytes(
                repository, "rev-list", "--objects", ref
            ).splitlines()
        )
    )


def build_reference_no_delivery(
    *,
    task_seed_manifest: Mapping[str, Any],
    reference_repository: Path,
    reference_commit: str,
    reference_tree: str,
    canonical_patch: bytes,
    implementation_additions: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Derive the explicit package-level scan; make no provider-internal claim."""

    reference_canary = F1V2_REFERENCE_CANARY
    decomposition_vocabulary = F1V2_DECOMPOSITION_VOCABULARY
    reference_repository = _canonical_root(
        Path(reference_repository), label="reference repository"
    )
    task_seed_repository = Path(task_seed_manifest["repository"]["locator"])
    task_seed_ids = _f1v2_object_ids(task_seed_repository, "refs/heads/task-seed")
    reference_ids = _f1v2_object_ids(reference_repository, reference_commit)
    reference_only = tuple(sorted(set(reference_ids) - set(task_seed_ids)))
    reference_only_blobs: list[tuple[str, bytes]] = []
    reference_only_blob_rows: list[dict[str, Any]] = []
    for object_id in reference_only:
        if (
            _reference_git_bytes(reference_repository, "cat-file", "-t", object_id)
            != b"blob\n"
        ):
            continue
        payload = _reference_git_bytes(
            reference_repository, "cat-file", "blob", object_id
        )
        reference_only_blobs.append((object_id, payload))
        reference_only_blob_rows.append(
            {
                "object_id": object_id,
                "byte_count": len(payload),
                "sha256": _sha256_bytes(payload),
            }
        )
    reference_only_object_catalog_sha256 = _sha256_bytes(
        canonical_json_bytes(
            {
                "object_ids": list(reference_only),
                "blob_rows": reference_only_blob_rows,
            }
        )
    )
    lookups = []
    for object_id in reference_only:
        try:
            completed = subprocess.run(
                (
                    str(PINNED_GIT_EXECUTABLE),
                    "-C",
                    str(task_seed_repository),
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
                object_id,
                "reference-only object lookup could not launch",
            ) from exc
        lookups.append(
            {
                "object_id": object_id,
                "return_code": completed.returncode,
                "stdout": completed.stdout.decode("utf-8", errors="replace"),
                "stderr": completed.stderr.decode("utf-8", errors="replace"),
            }
        )
    if not reference_only or any(
        row["return_code"] != 1 or row["stdout"] or row["stderr"]
        for row in lookups
    ):
        raise CalibrationError(
            "reference_no_delivery_invalid",
            lookups,
            "reference-only objects resolve from the task seed",
        )
    forbidden_payloads: list[tuple[str, bytes]] = [
        *((name, value.encode()) for name, value in _F1V2_CAMPAIGN_COMMITS.items()),
        ("reference_commit", reference_commit.encode()),
        ("reference_tree", reference_tree.encode()),
        ("reference_locator", str(reference_repository).encode()),
        ("canonical_patch", canonical_patch),
        ("canonical_patch_sha256", _sha256_bytes(canonical_patch).encode()),
        ("reference_manifest_name", b"reference-product.json"),
        ("reference_canary", reference_canary.encode()),
        ("measured_implementation_additions", str(implementation_additions).encode()),
        *(tuple((f"decomposition_vocabulary:{index}", value.encode())) for index, value in enumerate(decomposition_vocabulary)),
        *(
            (f"reference_only_object_id:{object_id}", object_id.encode())
            for object_id in reference_only
        ),
        *(
            (f"reference_only_blob_bytes:{object_id}", payload)
            for object_id, payload in reference_only_blobs
        ),
        *(
            (
                f"reference_only_blob_digest:{row['object_id']}",
                row["sha256"].encode(),
            )
            for row in reference_only_blob_rows
        ),
    ]
    surface_rows: list[dict[str, Any]] = []
    matches: list[dict[str, str]] = []
    for surface in _f1v2_provider_surfaces(task_seed_manifest):
        payload = surface.pop("payload")
        matched = [name for name, forbidden in forbidden_payloads if forbidden in payload]
        surface_rows.append(
            {
                **surface,
                "byte_count": len(payload),
                "sha256": _sha256_bytes(payload),
                "matches": matched,
            }
        )
        matches.extend(
            {"surface_id": surface["surface_id"], "forbidden_id": name}
            for name in matched
        )
    report = {
        "schema_version": "es_f1_reference_no_delivery.v2",
        "claim_limit": "not_provider_training_data_isolation",
        "task_seed": {
            "commit": task_seed_manifest["recipe"]["commit"],
            "tree": task_seed_manifest["recipe"]["tree"],
            "repository_snapshot_sha256": task_seed_manifest["repository"][
                "repository_snapshot_sha256"
            ],
        },
        "reference_only_object_count": len(reference_only),
        "reference_only_object_ids_sha256": _sha256_bytes(
            canonical_json_bytes(list(reference_only))
        ),
        "reference_only_blob_rows": reference_only_blob_rows,
        "reference_only_object_catalog_sha256": (
            reference_only_object_catalog_sha256
        ),
        "task_seed_lookup_rows": lookups,
        "forbidden_domain": [
            {
                "forbidden_id": name,
                "byte_count": len(payload),
                "sha256": _sha256_bytes(payload),
            }
            for name, payload in forbidden_payloads
        ],
        "surface_rows": surface_rows,
        "matches": matches,
        "workspace_source_policy": "exact_task_seed_only.v1",
    }
    if matches:
        raise CalibrationError(
            "reference_no_delivery_invalid", matches, "reference data reached a provider surface"
        )
    no_delivery = {
        "report_member_id": "no_delivery_scan",
        "report_sha256": _sha256_bytes(canonical_json_bytes(report)),
        "claim_limit": "not_provider_training_data_isolation",
        "surface_set": "task3a_explicit_prelaunch_provider_surfaces.v2",
        "reference_canary": reference_canary,
        "decomposition_vocabulary": list(decomposition_vocabulary),
        "reference_only_object_catalog_sha256": (
            reference_only_object_catalog_sha256
        ),
    }
    return no_delivery, report


_F1V2_TOP_LEVEL_FIELDS = {
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
_F1V2_LINEAGE_FIELDS = {
    "source_commit",
    "source_tree",
    "projection_commit",
    "projection_tree",
    "task_seed_commit",
    "task_seed_tree",
    "campaign_parent",
    "campaign_start",
    "campaign_end",
    "reference_commit",
    "reference_tree",
}
_F1V2_REFERENCE_REF = "refs/heads/reference-product"
_F1V2_PATCH_PREFIX = (
    "diff",
    "--patch",
    "--binary",
    "--full-index",
    "--no-color",
    "--src-prefix=a/",
    "--dst-prefix=b/",
    *PINNED_GIT_DIFF_CONTROLS,
)


def _f1v2_exact_object(
    value: object, fields: set[str], *, label: str
) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise CalibrationError(
            "reference_product_invalid", value, f"{label} field domain is not exact"
        )
    return value


def _validate_f1v2_reference_repository(
    value: object,
    lineage: Mapping[str, object],
) -> Path:
    """Reopen one exact remote-free, content-addressed reference repository."""

    fields = {
        "storage_root",
        "relative_path",
        "locator",
        "head_ref",
        "object_format",
        "commit_count",
        "object_count",
        "unreachable_object_count",
        "repository_snapshot_sha256",
        "reference_commit",
        "reference_tree",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise CalibrationError(
            "reference_repository_invalid",
            value,
            "repository field domain is not exact",
        )
    repository_row = value
    try:
        storage_root = _canonical_root(
            Path(repository_row["storage_root"]), label="reference storage root"
        )
        repository = _canonical_root(
            Path(repository_row["locator"]), label="reference repository"
        )
    except (CalibrationError, TypeError, ValueError, OSError) as exc:
        raise CalibrationError(
            "reference_repository_invalid",
            value,
            "reference storage root or repository is not canonical",
        ) from exc
    reference_commit = lineage["reference_commit"]
    reference_tree = lineage["reference_tree"]
    expected_relative = f"git-sha1/{reference_commit}"
    if (
        not isinstance(reference_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", reference_commit) is None
        or not isinstance(reference_tree, str)
        or re.fullmatch(r"[0-9a-f]{40}", reference_tree) is None
        or repository_row["storage_root"] != str(storage_root)
        or repository_row["relative_path"] != expected_relative
        or repository != storage_root / expected_relative
        or repository_row["locator"] != str(repository)
        or repository_row["head_ref"] != _F1V2_REFERENCE_REF
        or repository_row["object_format"] != "sha1"
        or repository_row["commit_count"] != 3
        or repository_row["unreachable_object_count"] != 0
        or repository_row["reference_commit"] != reference_commit
        or repository_row["reference_tree"] != reference_tree
    ):
        raise CalibrationError(
            "reference_repository_invalid",
            repository_row,
            "content-addressed repository binding drifted",
        )

    def raise_walk_error(error: OSError) -> NoReturn:
        raise error

    unsafe_paths: list[str] = []
    try:
        for directory, directory_names, file_names in os.walk(
            repository,
            topdown=True,
            onerror=raise_walk_error,
            followlinks=False,
        ):
            directory_names.sort()
            root = Path(directory)
            for name in sorted((*directory_names, *file_names)):
                path = root / name
                mode = path.lstat().st_mode
                if not stat.S_ISREG(mode) and not stat.S_ISDIR(mode):
                    unsafe_paths.append(path.relative_to(repository).as_posix())
    except OSError as exc:
        raise CalibrationError(
            "reference_repository_invalid",
            str(repository),
            "reference repository entries cannot be inspected safely",
        ) from exc
    if unsafe_paths:
        raise CalibrationError(
            "reference_repository_invalid",
            tuple(sorted(unsafe_paths)),
            "reference repository contains unsafe filesystem entries",
        )
    escape_paths = tuple(
        path.relative_to(repository).as_posix()
        for path in (
            repository / "objects" / "info" / "alternates",
            repository / "info" / "grafts",
            repository / "shallow",
            repository / "refs" / "replace",
        )
        if os.path.lexists(path)
    )
    if escape_paths:
        raise CalibrationError(
            "reference_repository_invalid",
            escape_paths,
            "reference repository declares substituted or external identity",
        )
    if (
        _reference_git_bytes(repository, "rev-parse", "--is-bare-repository")
        != b"true\n"
        or _reference_git_bytes(repository, "rev-parse", "--show-object-format")
        != b"sha1\n"
        or _reference_git_bytes(repository, "symbolic-ref", "HEAD")
        != f"{_F1V2_REFERENCE_REF}\n".encode("ascii")
        or _reference_git_bytes(repository, "remote") != b""
    ):
        raise CalibrationError(
            "reference_repository_invalid",
            repository_row,
            "reference repository format, HEAD, or remote domain drifted",
        )
    refs = _reference_git_bytes(
        repository, "for-each-ref", "--format=%(refname) %(objectname)"
    ).decode("ascii").splitlines()
    history = _reference_git_bytes(
        repository, "rev-list", "--parents", "--topo-order", "--all"
    ).decode("ascii").splitlines()
    if refs != [f"{_F1V2_REFERENCE_REF} {reference_commit}"] or history != [
        f"{reference_commit} {lineage['task_seed_commit']}",
        f"{lineage['task_seed_commit']} {lineage['projection_commit']}",
        str(lineage["projection_commit"]),
    ]:
        raise CalibrationError(
            "reference_repository_invalid",
            {"refs": refs, "history": history},
            "reference repository lineage is not the exact three-commit chain",
        )
    for commit_key, tree_key in (
        ("projection_commit", "projection_tree"),
        ("task_seed_commit", "task_seed_tree"),
        ("reference_commit", "reference_tree"),
    ):
        observed = _reference_git_bytes(
            repository, "rev-parse", f"{lineage[commit_key]}^{{tree}}"
        ).decode("ascii").strip()
        if observed != lineage[tree_key]:
            raise CalibrationError(
                "reference_repository_invalid", observed, f"{commit_key} tree drifted"
            )
    raw_object_rows = _reference_git_bytes(
        repository,
        "cat-file",
        "--batch-all-objects",
        "--batch-check=%(objectname) %(objecttype)",
    ).splitlines()
    object_rows: list[tuple[str, str]] = []
    try:
        for raw_row in raw_object_rows:
            object_id, object_type = raw_row.decode("ascii").split(" ", 1)
            if (
                re.fullmatch(r"[0-9a-f]{40}", object_id) is None
                or object_type not in {"blob", "tree", "commit", "tag"}
            ):
                raise ValueError
            object_rows.append((object_id, object_type))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CalibrationError(
            "reference_repository_invalid",
            raw_object_rows,
            "reference object inventory is malformed",
        ) from exc
    reachable = {
        row.split(b" ", 1)[0].decode("ascii")
        for row in _reference_git_bytes(
            repository, "rev-list", "--objects", "--all"
        ).splitlines()
    }
    all_objects = {object_id for object_id, _ in object_rows}
    if (
        all_objects != reachable
        or repository_row["object_count"] != len(object_rows)
        or sum(object_type == "commit" for _, object_type in object_rows) != 3
    ):
        raise CalibrationError(
            "reference_repository_invalid",
            repository_row,
            "reference repository object closure or counts drifted",
        )
    task_package = __import__(
        "scripts.experiments.es.task_package", fromlist=["task_package"]
    )
    try:
        snapshot = task_package.directory_snapshot_digest(repository)
    except task_package.TaskPackageError as exc:
        raise CalibrationError(
            "reference_repository_invalid",
            str(repository),
            "reference repository snapshot is unreadable",
        ) from exc
    if snapshot != repository_row["repository_snapshot_sha256"]:
        raise CalibrationError(
            "reference_repository_invalid",
            snapshot,
            "reference repository snapshot drifted",
        )
    for campaign_commit in _F1V2_CAMPAIGN_COMMITS.values():
        if subprocess.run(
            (
                str(PINNED_GIT_EXECUTABLE),
                "-C",
                str(repository),
                "cat-file",
                "-e",
                campaign_commit,
            ),
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
        ).returncode == 0:
            raise CalibrationError(
                "reference_repository_invalid",
                campaign_commit,
                "historical campaign object leaked into the reference repository",
            )
    return repository


def _validate_f1v2_reference_product(record: Mapping[str, object]) -> None:
    """Reopen the closed F1v2 authority without executing provider work."""

    top = _f1v2_exact_object(dict(record), _F1V2_TOP_LEVEL_FIELDS, label="record")
    if top["schema_version"] != "es_f1_reference_product.v2":
        raise CalibrationError(
            "reference_product_invalid",
            top["schema_version"],
            "schema version drifted",
        )
    if top["bindings"] != build_reference_bindings():
        raise CalibrationError(
            "reference_binding_invalid",
            top["bindings"],
            "Task-0 through Task-3 authority bindings drifted",
        )
    task_package = __import__(
        "scripts.experiments.es.task_package", fromlist=["task_package"]
    )
    task_seed_path = (
        _REPOSITORY_ROOT / _F1V2_REFERENCE_BINDINGS["task_seed_manifest"][0]
    )
    try:
        task_seed = task_package.load_task_seed_manifest(task_seed_path).raw
        consumer_census = task_package.load_configuration_consumer_census(
            _REPOSITORY_ROOT
            / _F1V2_REFERENCE_BINDINGS["configuration_consumer_census"][0]
        )
        selector_manifest = task_package.load_f1v2_selector_manifest(
            _REPOSITORY_ROOT
            / _F1V2_REFERENCE_BINDINGS["preedit_selector_manifest"][0]
        )
    except (OSError, task_package.TaskPackageError) as exc:
        raise CalibrationError(
            "reference_binding_invalid",
            str(task_seed_path),
            "bound v3 task-seed, census, or selector authority rejected",
        ) from exc
    lineage = _f1v2_exact_object(
        top["lineage"], _F1V2_LINEAGE_FIELDS, label="lineage"
    )
    expected_lineage = {
        "source_commit": "c081b7b6cd160b3da7031ee325bbf0ade1025d7a",
        "source_tree": "9193ae2f81116d1bac4cf3cb74395613c1220dbe",
        "projection_commit": task_seed["parent_projection"]["commit"],
        "projection_tree": task_seed["parent_projection"]["tree"],
        "task_seed_commit": task_seed["recipe"]["commit"],
        "task_seed_tree": task_seed["recipe"]["tree"],
        **_F1V2_CAMPAIGN_COMMITS,
        "reference_commit": lineage["reference_commit"],
        "reference_tree": lineage["reference_tree"],
    }
    if lineage != expected_lineage:
        raise CalibrationError(
            "reference_repository_invalid", lineage, "lineage authority drifted"
        )

    repository = _validate_f1v2_reference_repository(top["repository"], lineage)

    evidence = _f1v2_exact_object(
        top["evidence"], {"algorithm", "root", "members"}, label="evidence"
    )
    evidence_root = _canonical_root(Path(evidence["root"]), label="evidence root")
    try:
        evidence_root.relative_to(repository)
    except ValueError:
        pass
    else:
        raise CalibrationError(
            "reference_evidence_invalid",
            str(evidence_root),
            "evidence root is inside the reference repository",
        )
    members = evidence["members"]
    if evidence["algorithm"] != "sha256" or not isinstance(members, list):
        raise CalibrationError(
            "reference_evidence_invalid", evidence, "evidence store is malformed"
        )
    payloads: dict[str, bytes] = {}
    for raw_row in members:
        row = _f1v2_exact_object(
            raw_row,
            {"member_id", "cas_relative_path", "byte_count", "sha256"},
            label="evidence member",
        )
        digest = row["sha256"]
        if not isinstance(digest, str) or _SHA256_RE.fullmatch(digest) is None:
            raise CalibrationError(
                "reference_evidence_invalid", row, "evidence digest is malformed"
            )
        relative = _canonical_relative_path(
            row["cas_relative_path"], label="evidence member path"
        )
        if relative != f"{digest.removeprefix('sha256:')}/payload":
            raise CalibrationError(
                "reference_evidence_invalid", row, "evidence path is not content addressed"
            )
        path = evidence_root / relative
        try:
            metadata = path.lstat()
            payload = path.read_bytes()
        except OSError as exc:
            raise CalibrationError(
                "reference_evidence_invalid", str(path), "evidence member is unreadable"
            ) from exc
        if (
            stat.S_ISLNK(metadata.st_mode)
            or not stat.S_ISREG(metadata.st_mode)
            or path.resolve(strict=True) != path
            or len(payload) != row["byte_count"]
            or _sha256_bytes(payload) != digest
            or row["member_id"] in payloads
        ):
            raise CalibrationError(
                "reference_evidence_invalid", row, "evidence member binding drifted"
            )
        payloads[row["member_id"]] = payload
    if tuple(payloads) != (
        "canonical_patch",
        "evaluation_replay",
        "no_delivery_scan",
    ):
        raise CalibrationError(
            "reference_evidence_invalid", list(payloads), "evidence member domain drifted"
        )

    patch = _f1v2_exact_object(
        top["patch"],
        {"member_id", "base_commit", "target_commit", "argv"},
        label="patch",
    )
    expected_argv = [
        *_F1V2_PATCH_PREFIX,
        lineage["task_seed_commit"],
        lineage["reference_commit"],
        "--",
    ]
    if patch != {
        "member_id": "canonical_patch",
        "base_commit": lineage["task_seed_commit"],
        "target_commit": lineage["reference_commit"],
        "argv": expected_argv,
    } or payloads["canonical_patch"] != _reference_git_bytes(
        repository, *expected_argv
    ):
        raise CalibrationError(
            "reference_patch_invalid", patch, "canonical reference patch drifted"
        )

    metric = _f1v2_exact_object(
        top["metric"],
        {
            "metric_version",
            "git_contract_policy_sha256",
            "rows",
            "totals_by_classification",
            "implementation_additions",
            "implementation_deletions",
            "base_physical_lines",
            "candidate_postimage_physical_lines",
            "base_commit",
            "base_tree",
            "reference_commit",
            "reference_tree",
            "historical_churn",
        },
        label="metric",
    )
    if (
        metric["metric_version"] != METRIC_VERSION
        or not isinstance(metric["rows"], list)
        or not isinstance(metric["totals_by_classification"], dict)
        or not isinstance(
            metric["totals_by_classification"].get("production_python"), dict
        )
        or metric["totals_by_classification"]["production_python"].get(
            "additions"
        )
        != metric["implementation_additions"]
        or not isinstance(metric["implementation_additions"], int)
        or isinstance(metric["implementation_additions"], bool)
        or not 5_000 <= metric["implementation_additions"] <= 10_000
        or metric["base_commit"] != lineage["task_seed_commit"]
        or metric["base_tree"] != lineage["task_seed_tree"]
        or metric["reference_commit"] != lineage["reference_commit"]
        or metric["reference_tree"] != lineage["reference_tree"]
        or metric["historical_churn"]
        != {
            "authority": "non_authoritative_inclusive_per_commit_churn",
            "production_additions": 8_698,
            "production_deletions": 11_197,
        }
    ):
        raise CalibrationError(
            "reference_metric_invalid", metric, "reference metric binding drifted"
        )
    production_paths: dict[str, tuple[str, ...]] = {}
    changed_path_policies: list[MetricPathPolicy] = []
    for raw_row in metric["rows"]:
        row = _f1v2_exact_object(
            raw_row,
            {
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
            },
            label="metric row",
        )
        path = row["candidate_path"]
        responsibility_ids = row["responsibility_ids"]
        if row["change_kind"] != "unchanged":
            changed_path = path or row["base_path"]
            if not isinstance(changed_path, str) or not isinstance(
                responsibility_ids, list
            ):
                raise CalibrationError(
                    "reference_metric_invalid", row, "changed metric row is malformed"
                )
            changed_path_policies.append(
                MetricPathPolicy(
                    changed_path,
                    row["classification"],
                    tuple(responsibility_ids),
                )
            )
        if row["classification"] == "production_python" and isinstance(path, str):
            if (
                not isinstance(responsibility_ids, list)
                or not responsibility_ids
                or not set(responsibility_ids) <= _F1V2_RESPONSIBILITY_IDS
            ):
                raise CalibrationError(
                    "reference_metric_invalid", row, "production responsibility drifted"
                )
            production_paths[path] = tuple(responsibility_ids)
    observed_metric = build_reference_metric(
        repository=repository,
        task_seed_commit=lineage["task_seed_commit"],
        reference_commit=lineage["reference_commit"],
        changed_path_policies=tuple(changed_path_policies),
        git_contract=GitContract(
            executable=PINNED_GIT_EXECUTABLE,
            version=PINNED_GIT_VERSION,
            executable_sha256=PINNED_GIT_EXECUTABLE_SHA256,
            diff_controls=PINNED_GIT_DIFF_CONTROLS,
            policy_sha256=metric["git_contract_policy_sha256"],
        ),
    )
    if metric != observed_metric:
        raise CalibrationError(
            "reference_metric_invalid", metric, "fresh endpoint measurement drifted"
        )

    adaptation = _f1v2_exact_object(
        top["adaptation"],
        {
            "strategy",
            "historical_production_paths",
            "historical_production_path_count",
            "historical_production_paths_sha256",
            "rows",
            "new_production_responsibilities",
        },
        label="adaptation",
    )
    expected_historical_paths = list(F1V2_HISTORICAL_PRODUCTION_PATHS)
    rows = adaptation["rows"]
    new_responsibilities = adaptation["new_production_responsibilities"]
    if (
        adaptation["strategy"] != "behavioral-adaptation-no-history-replay.v1"
        or adaptation["historical_production_paths"] != expected_historical_paths
        or adaptation["historical_production_path_count"]
        != F1V2_HISTORICAL_PRODUCTION_PATH_COUNT
        or len(expected_historical_paths)
        != F1V2_HISTORICAL_PRODUCTION_PATH_COUNT
        or adaptation["historical_production_paths_sha256"]
        != F1V2_HISTORICAL_PRODUCTION_PATHS_SHA256
        or adaptation["historical_production_paths_sha256"]
        != _sha256_bytes(canonical_json_bytes(expected_historical_paths))
        or not isinstance(rows, list)
        or not rows
        or not isinstance(new_responsibilities, list)
    ):
        raise CalibrationError(
            "reference_adaptation_invalid", adaptation, "adaptation ledger is malformed"
        )
    projection_targets: set[str] = set()
    historical_paths: set[str] = set()
    for raw_row in rows:
        row = _f1v2_exact_object(
            raw_row,
            {
                "historical_path",
                "projection_targets",
                "disposition",
                "conflict_rationale",
            },
            label="adaptation row",
        )
        targets = row["projection_targets"]
        if (
            not isinstance(row["historical_path"], str)
            or row["historical_path"] in historical_paths
            or not isinstance(targets, list)
            or any(not isinstance(target, str) for target in targets)
            or len(set(targets)) != len(targets)
            or row["disposition"] not in {"adapted", "superseded", "not_applicable"}
            or (row["disposition"] == "adapted" and not targets)
            or (row["disposition"] != "adapted" and targets)
            or not isinstance(row["conflict_rationale"], str)
            or not row["conflict_rationale"].strip()
        ):
            raise CalibrationError(
                "reference_adaptation_invalid", row, "adaptation row is invalid"
            )
        historical_paths.add(row["historical_path"])
        projection_targets.update(targets)
    if historical_paths != set(F1V2_HISTORICAL_PRODUCTION_PATHS):
        raise CalibrationError(
            "reference_adaptation_invalid",
            sorted(historical_paths),
            "adaptation rows do not cover the frozen historical path domain",
        )
    observed_responsibilities: dict[str, tuple[str, ...]] = {}
    for raw_row in new_responsibilities:
        row = _f1v2_exact_object(
            raw_row, {"path", "responsibility_ids"}, label="responsibility row"
        )
        if (
            not isinstance(row["path"], str)
            or row["path"] in observed_responsibilities
            or not isinstance(row["responsibility_ids"], list)
        ):
            raise CalibrationError(
                "reference_adaptation_invalid", row, "responsibility row is malformed"
            )
        observed_responsibilities[row["path"]] = tuple(row["responsibility_ids"])
    if (
        projection_targets != set(production_paths)
        or observed_responsibilities != production_paths
    ):
        raise CalibrationError(
            "reference_adaptation_invalid",
            adaptation,
            "adaptation ledger does not cover measured production paths exactly",
        )

    evaluation = _f1v2_exact_object(
        top["evaluation"],
        {"target_tree", "evaluation_replay_member_id", "normalized_result_sha256"},
        label="evaluation",
    )
    evaluator = __import__(
        "scripts.experiments.es.f1_evaluator", fromlist=["f1_evaluator"]
    )
    fixture_path, fixture_raw = _raw_file_binding(
        _F1V2_REFERENCE_BINDINGS["evaluator_fixture_manifest"][0]
    )
    fixture_manifest = _parse_json_bytes(fixture_raw, label=fixture_path)
    if (
        not isinstance(selector_manifest, dict)
        or not isinstance(consumer_census, dict)
        or not isinstance(fixture_manifest, dict)
        or selector_manifest.get("selectors")
        != list(task_package.F1_PROVIDER_VISIBLE_SELECTORS)
        or selector_manifest.get("deselected_node_ids")
        != list(task_package.F1_PROVIDER_VISIBLE_DESELECTORS)
        or not isinstance(selector_manifest.get("candidate_owned_selector"), str)
        or fixture_manifest.get("hard_clause_ids")
        != list(task_package.F1_HARD_CLAUSE_IDS)
        or fixture_manifest.get("bypass_classes")
        != list(task_package.F1_BYPASS_CLASSES)
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            selector_manifest,
            "bound evaluator or selector authority drifted",
        )
    calibration_binding = _f1v2_exact_object(
        fixture_manifest.get("calibration_cases"),
        {"path", "schema_version", "sha256"},
        label="calibration case binding",
    )
    calibration_relative = _canonical_relative_path(
        calibration_binding["path"], label="calibration case path"
    )
    calibration_path = _REPOSITORY_ROOT / calibration_relative
    try:
        calibration_metadata = calibration_path.lstat()
        calibration_raw = calibration_path.read_bytes()
    except OSError as exc:
        raise CalibrationError(
            "reference_evaluation_invalid",
            calibration_relative,
            "calibration cases are unreadable",
        ) from exc
    calibration_cases = _parse_json_bytes(calibration_raw, label=calibration_path)
    if (
        stat.S_ISLNK(calibration_metadata.st_mode)
        or not stat.S_ISREG(calibration_metadata.st_mode)
        or _sha256_bytes(calibration_raw) != calibration_binding["sha256"]
        or not isinstance(calibration_cases, dict)
        or calibration_cases.get("schema_version")
        != calibration_binding["schema_version"]
        or calibration_raw != canonical_json_bytes(calibration_cases)
        or not isinstance(calibration_cases.get("cases"), list)
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            calibration_relative,
            "calibration case authority drifted",
        )
    seen_negative_ids: set[str] = set()
    for raw_case in calibration_cases["cases"]:
        if not isinstance(raw_case, dict) or raw_case.get("defect_kind") == "none":
            continue
        case_id = raw_case.get("case_id")
        expected = evaluator.CALIBRATION_DEFECT_CLAUSES.get(case_id)
        if (
            not isinstance(case_id, str)
            or expected is None
            or raw_case.get("defect_kind") != case_id
            or raw_case.get("expected_failed_clauses") != list(expected)
            or case_id in seen_negative_ids
        ):
            raise CalibrationError(
                "reference_evaluation_invalid",
                raw_case,
                "negative calibration authority drifted",
            )
        seen_negative_ids.add(case_id)
    if seen_negative_ids != set(evaluator.CALIBRATION_DEFECT_CLAUSES):
        raise CalibrationError(
            "reference_evaluation_invalid",
            sorted(seen_negative_ids),
            "negative calibration case domain is incomplete",
        )

    replay = _parse_json_bytes(
        payloads["evaluation_replay"], label="evaluation_replay"
    )
    if (
        evaluation["target_tree"] != lineage["reference_tree"]
        or evaluation["evaluation_replay_member_id"] != "evaluation_replay"
        or not isinstance(evaluation["normalized_result_sha256"], str)
        or _SHA256_RE.fullmatch(evaluation["normalized_result_sha256"]) is None
        or not isinstance(replay, dict)
        or set(replay)
        != {
            "target_tree",
            "runs",
            "normalized_results_byte_equal",
            "normalized_result_sha256",
        }
        or replay["target_tree"] != lineage["reference_tree"]
        or replay["normalized_results_byte_equal"] is not True
        or replay["normalized_result_sha256"]
        != evaluation["normalized_result_sha256"]
        or payloads["evaluation_replay"] != canonical_json_bytes(replay)
    ):
        raise CalibrationError(
            "reference_evaluation_invalid", evaluation, "evaluation authority drifted"
        )
    runs = replay["runs"]
    if not isinstance(runs, list) or len(runs) != 2:
        raise CalibrationError(
            "reference_evaluation_invalid",
            replay,
            "evaluation replay must contain exactly two runs",
        )
    normalized_bytes: list[bytes] = []
    materializations: list[dict[str, object]] = []
    for expected_run_id, raw_run in zip(
        ("reference-materialization-a", "reference-materialization-b"), runs
    ):
        run = _f1v2_exact_object(
            raw_run,
            {
                "run_id",
                "materialization",
                "normalized_result",
                "normalized_result_sha256",
            },
            label="evaluation replay run",
        )
        materialization = _f1v2_exact_object(
            run["materialization"],
            {
                "resolved_commit",
                "verified_git_tree",
                "source_tree_manifest_sha256",
                "post_setup_tree_manifest_sha256",
            },
            label="evaluation materialization",
        )
        result = _f1v2_exact_object(
            run["normalized_result"],
            {"schema_version", "clause_results"},
            label="normalized evaluation result",
        )
        clause_results = result["clause_results"]
        normalized = canonical_json_bytes(result)
        if (
            run["run_id"] != expected_run_id
            or run["normalized_result_sha256"] != _sha256_bytes(normalized)
            or materialization["resolved_commit"] != lineage["reference_commit"]
            or materialization["verified_git_tree"]
            != f"git-tree:{lineage['reference_tree']}"
            or any(
                not isinstance(materialization[field], str)
                or _SHA256_RE.fullmatch(materialization[field]) is None
                for field in (
                    "source_tree_manifest_sha256",
                    "post_setup_tree_manifest_sha256",
                )
            )
            or materialization["source_tree_manifest_sha256"]
            != materialization["post_setup_tree_manifest_sha256"]
            or result["schema_version"]
            != "es_f1_reference_evaluation_result.v1"
            or not isinstance(clause_results, list)
            or [
                row.get("clause_id") if isinstance(row, dict) else None
                for row in clause_results
            ]
            != list(task_package.F1_HARD_CLAUSE_IDS)
            or any(
                not isinstance(row, dict)
                or set(row)
                != {"clause_id", "details", "evidence_digest", "satisfied"}
                or row["satisfied"] is not True
                or not isinstance(row["details"], str)
                or not row["details"]
                or not isinstance(row["evidence_digest"], str)
                or _SHA256_RE.fullmatch(row["evidence_digest"]) is None
                for row in clause_results
            )
        ):
            raise CalibrationError(
                "reference_evaluation_invalid",
                run,
                "normalized evaluation replay drifted",
            )
        normalized_bytes.append(normalized)
        materializations.append(materialization)
    if (
        normalized_bytes[0] != normalized_bytes[1]
        or materializations[0] != materializations[1]
        or replay["normalized_result_sha256"]
        != _sha256_bytes(normalized_bytes[0])
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            replay,
            "normalized evaluation runs are not byte-identical",
        )

    no_delivery = _f1v2_exact_object(
        top["no_delivery"],
        {
            "report_member_id",
            "report_sha256",
            "claim_limit",
            "surface_set",
            "reference_canary",
            "decomposition_vocabulary",
            "reference_only_object_catalog_sha256",
        },
        label="no_delivery",
    )
    expected_no_delivery, expected_report = build_reference_no_delivery(
        task_seed_manifest=task_seed,
        reference_repository=repository,
        reference_commit=lineage["reference_commit"],
        reference_tree=lineage["reference_tree"],
        canonical_patch=payloads["canonical_patch"],
        implementation_additions=metric["implementation_additions"],
    )
    if (
        no_delivery != expected_no_delivery
        or payloads["no_delivery_scan"] != canonical_json_bytes(expected_report)
    ):
        raise CalibrationError(
            "reference_no_delivery_invalid", no_delivery, "non-delivery evidence drifted"
        )


def load_reference_product(
    path: Path,
    *,
    schema_path: Path,
    expected_record_sha256: str,
) -> ReferenceProduct:
    """Load and fully revalidate one closed F1v2 reference product."""

    record = load_canonical_record(
        Path(path),
        schema_path=Path(schema_path),
        expected_record_sha256=expected_record_sha256,
    )
    _validate_f1v2_reference_product(record)
    return ReferenceProduct(
        record=copy.deepcopy(record),
        _record_path=Path(path),
        _schema_path=Path(schema_path),
        _expected_record_sha256=expected_record_sha256,
    )


def _require_reference_evaluation_capture(
    body: Mapping[str, object],
    capture: object,
) -> _ReferenceEvaluationCapture:
    if (
        type(capture) is not _ReferenceEvaluationCapture
        or capture._seal is not _REFERENCE_EVALUATION_CAPTURE_SEAL
        or capture.payload != canonical_json_bytes(capture.replay)
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            capture,
            "reference product requires an opaque two-run evaluator capture",
        )
    lineage = body.get("lineage")
    repository = body.get("repository")
    evaluation = body.get("evaluation")
    evidence = body.get("evidence")
    if not all(
        isinstance(row, Mapping)
        for row in (lineage, repository, evaluation, evidence)
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            body,
            "reference capture bindings are absent",
        )
    assert isinstance(lineage, Mapping)
    assert isinstance(repository, Mapping)
    assert isinstance(evaluation, Mapping)
    assert isinstance(evidence, Mapping)
    members = evidence.get("members")
    if not isinstance(members, list):
        raise CalibrationError(
            "reference_evaluation_invalid",
            evidence,
            "reference evidence members are absent",
        )
    replay_rows = [
        row
        for row in members
        if isinstance(row, Mapping) and row.get("member_id") == "evaluation_replay"
    ]
    if len(replay_rows) != 1 or not isinstance(evidence.get("root"), str):
        raise CalibrationError(
            "reference_evaluation_invalid",
            members,
            "reference replay member is not unique",
        )
    replay_row = replay_rows[0]
    relative = _canonical_relative_path(
        replay_row.get("cas_relative_path"), label="evaluation replay CAS path"
    )
    replay_path = Path(str(evidence["root"])).joinpath(
        *PurePosixPath(relative).parts
    )
    try:
        replay_payload = replay_path.read_bytes()
    except OSError as exc:
        raise CalibrationError(
            "reference_evaluation_invalid",
            str(replay_path),
            "reference replay member is unreadable",
        ) from exc
    expected_evaluation = {
        "target_tree": capture.reference_tree,
        "evaluation_replay_member_id": "evaluation_replay",
        "normalized_result_sha256": capture.replay[
            "normalized_result_sha256"
        ],
    }
    if (
        capture.reference_repository != Path(str(repository.get("locator")))
        or capture.reference_commit != lineage.get("reference_commit")
        or capture.reference_tree != lineage.get("reference_tree")
        or evaluation != expected_evaluation
        or replay_payload != capture.payload
        or replay_row.get("byte_count") != len(capture.payload)
        or replay_row.get("sha256") != _sha256_bytes(capture.payload)
    ):
        raise CalibrationError(
            "reference_evaluation_invalid",
            evaluation,
            "reference replay does not match the executed two-run capture",
        )
    return capture


def build_reference_product(
    body: Mapping[str, object],
    *,
    output_path: Path,
    schema_path: Path,
    evaluation_capture: _ReferenceEvaluationCapture | None,
) -> ReferenceProduct:
    """Validate, seal, and atomically publish one assembled F1v2 record."""

    capture = _require_reference_evaluation_capture(body, evaluation_capture)
    record = seal_record(body)
    try:
        schema = _parse_json_bytes(Path(schema_path).read_bytes(), label=schema_path)
    except OSError as exc:
        raise CalibrationError(
            "record_schema_invalid", str(schema_path), "schema is unreadable"
        ) from exc
    if not isinstance(schema, dict):
        raise CalibrationError(
            "record_schema_invalid", str(schema_path), "schema must be an object"
        )
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(record), key=str)
    if errors:
        raise CalibrationError(
            "record_schema_invalid", str(output_path), errors[0].message
        )
    _validate_f1v2_reference_product(record)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as temporary:
        temporary.write(canonical_json_bytes(record))
        temporary_path = Path(temporary.name)
    os.replace(temporary_path, output)
    return ReferenceProduct(
        record=copy.deepcopy(record),
        _record_path=output,
        _schema_path=Path(schema_path),
        _expected_record_sha256=record["record_sha256"],
        _validation_provenance=capture,
    )


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
