"""Canonical Task-0 records and the shared ES implementation-delta metric.

This module is deliberately provider-free.  It validates one pinned Git tool,
measures explicit directory trees, and replays the retained A1 calibration
anchor without consulting an ambient checkout or inferring path ownership.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
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
