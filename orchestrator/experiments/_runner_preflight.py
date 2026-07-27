"""Attempt selection and complete preflight assembly for the lean-pilot runner."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from . import _runner_apparatus as apparatus
from . import _runner_source as source
from ._runner_types import ArmCommand, RunnerError, _Preflight, _PreparedArm
from .contracts import (
    PilotContractError,
    canonical_sha256,
    load_record,
    validate_record,
)


def _contains_logical_token(value: str, tokens: tuple[str, ...]) -> bool:
    return any(
        re.search(
            rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
            value,
            flags=re.IGNORECASE,
        )
        is not None
        for token in tokens
    )


def _validate_candidate_visibility(
    *,
    arms: tuple[_PreparedArm, ...],
    evidence_root: Path,
    record_path: Path,
    randomization_seed: str,
    treatment_ids: tuple[str, ...],
    apparatus_control_root: Path,
) -> None:
    for arm in arms:
        command = arm.command
        peer_commands = tuple(
            peer.command
            for peer in arms
            if peer.command.opaque_arm_label != command.opaque_arm_label
        )
        forbidden_fragments = (
            str(evidence_root),
            str(record_path),
            randomization_seed,
            str(apparatus_control_root),
            *(
                fragment
                for peer in peer_commands
                for fragment in (
                    str(peer.workspace),
                    str(peer.runtime_root),
                    str(peer.result_path),
                    peer.opaque_arm_label,
                )
            ),
        )
        visible_values = (
            *command.argv,
            *(key for key, _value in command.environment),
            *(value for _key, value in command.environment),
        )
        if any(
            fragment and fragment in value
            for value in visible_values
            for fragment in forbidden_fragments
        ) or any(
            _contains_logical_token(value, treatment_ids)
            for value in visible_values
        ):
            raise RunnerError(
                "candidate-visible command exposes controller-only data"
            )


def _validate_root_topology(
    *,
    repository_root: Path,
    control_root: Path,
    work_root: Path,
    evidence_root: Path,
) -> None:
    roots = (
        ("archive.repository_root", repository_root),
        ("apparatus.control_root", control_root),
        ("work_root", work_root),
        ("evidence_root", evidence_root),
    )
    for index, (first_label, first) in enumerate(roots):
        for second_label, second in roots[index + 1 :]:
            if apparatus.paths_overlap(first, second):
                raise RunnerError(
                    f"{first_label} and {second_label} must be pairwise disjoint"
                )


def _attempt_identity(
    lock: Mapping[str, object],
    block_id: str,
    evidence_root: Path,
) -> tuple[str, int, Path]:
    smoke_id = lock["smoke_id"]
    live_ids = lock["live_attempt_ids"]
    if not isinstance(smoke_id, str):
        raise RunnerError("lock attempt identifiers are malformed")
    if not isinstance(live_ids, list) or any(
        not isinstance(item, str) for item in live_ids
    ):
        raise RunnerError("lock live attempt identifiers are malformed")

    known_ids = [smoke_id, *live_ids]
    existing: dict[str, dict[str, Any]] = {}
    for known_id in known_ids:
        path = evidence_root / known_id / "block-attempt.json"
        if path.exists():
            existing[known_id] = load_record(
                path,
                expected_kind="block_attempt.v1",
            )
        elif path.parent.exists():
            raise RunnerError(f"incomplete evidence already exists for {known_id}")

    if block_id not in known_ids:
        raise RunnerError(f"block_id is not locked: {block_id}")
    if block_id in existing:
        raise RunnerError(f"block_id is already used: {block_id}")

    used_live = [item for item in live_ids if item in existing]
    if used_live != live_ids[: len(used_live)]:
        raise RunnerError("existing live attempts are not a contiguous prefix")

    if block_id == smoke_id:
        return "SMOKE", 0, evidence_root / block_id / "block-attempt.json"
    next_index = len(used_live)
    if next_index >= len(live_ids) or block_id != live_ids[next_index]:
        raise RunnerError("live block_id must be the next locked prefix item")
    return "LIVE", next_index, evidence_root / block_id / "block-attempt.json"


def _preflight(
    *,
    lock: Mapping[str, object],
    block_id: str,
    work_root: Path,
    evidence_root: Path,
) -> _Preflight:
    work_root = Path(work_root).resolve(strict=False)
    evidence_root = Path(evidence_root).resolve(strict=False)
    try:
        validate_record(lock)
    except PilotContractError as exc:
        raise RunnerError(str(exc)) from exc
    locked_evidence = lock["evidence_root"]
    if (
        not isinstance(locked_evidence, str)
        or evidence_root.resolve(strict=False).as_posix() != locked_evidence
    ):
        raise RunnerError("supplied evidence_root does not exactly match the lock")
    archive = lock["archive"]
    locked_apparatus = lock["apparatus"]
    if not isinstance(archive, Mapping):
        raise RunnerError("lock archive is not an object")
    if not isinstance(locked_apparatus, Mapping):
        raise RunnerError("lock apparatus is not an object")
    repository_root = apparatus.canonical_absolute_path(
        archive["repository_root"],
        label="archive.repository_root",
    )
    control_root = apparatus.canonical_absolute_path(
        locked_apparatus["control_root"],
        label="apparatus.control_root",
    )
    _validate_root_topology(
        repository_root=repository_root,
        control_root=control_root,
        work_root=work_root,
        evidence_root=evidence_root,
    )

    source_binding = source.preflight_source(lock)

    attempt_class, sequence_index, record_path = _attempt_identity(
        lock,
        block_id,
        evidence_root,
    )
    verified = apparatus.verified_assets(lock)
    treatment_paths = apparatus.string_list(
        locked_apparatus["treatment_asset_paths"],
        label="apparatus treatment_asset_paths",
    )
    treatment_verified = {
        path: verified[path]
        for path in treatment_paths
        if path in verified
    }
    if len(treatment_verified) != len(treatment_paths):
        raise RunnerError("treatment asset binding is not verified")

    role_paths = (
        locked_apparatus["task_path"],
        locked_apparatus["provider_config_path"],
        locked_apparatus["prompt_config_path"],
        locked_apparatus["command_config_path"],
    )
    if any(not isinstance(path, str) or path not in verified for path in role_paths):
        raise RunnerError("apparatus role binding is not verified")
    task_path, provider_path, prompt_path, shared_command_path = role_paths
    apparatus.validate_standard_role_manifests(
        verified=treatment_verified,
        provider_path=provider_path,
        prompt_path=prompt_path,
        command_path=shared_command_path,
    )

    apparatus_environment = locked_apparatus["environment"]
    if not isinstance(apparatus_environment, Mapping):
        raise RunnerError("apparatus environment is not an object")
    allowed = apparatus.string_list(
        apparatus_environment["allowed_keys"],
        label="apparatus environment allowed_keys",
    )
    allowed_keys = set(allowed)
    if not {"HOME", "TMPDIR"} <= allowed_keys:
        raise RunnerError(
            "apparatus environment allowed_keys must include HOME and TMPDIR"
        )
    credential_names = apparatus.string_list(
        apparatus_environment["credential_keys"],
        label="apparatus environment credential_keys",
    )
    credential_keys = set(credential_names)
    if len(credential_names) != len(credential_keys):
        raise RunnerError("apparatus environment credential_keys has duplicates")
    if not credential_keys <= allowed_keys:
        raise RunnerError(
            "apparatus environment credential_keys must be within allowed_keys"
        )
    if {"HOME", "TMPDIR"} & credential_keys:
        raise RunnerError(
            "controller-owned environment keys cannot be credentials"
        )
    launcher_environment_keys = allowed_keys - {
        "HOME",
        "TMPDIR",
        *credential_keys,
    }
    environment_identity = apparatus_environment["identity"]
    if not isinstance(environment_identity, str):
        raise RunnerError("apparatus environment identity is malformed")
    provider_policy_digest = canonical_sha256(lock["provider_policy"])
    secret_values: dict[str, str] | None = None

    visible_check = locked_apparatus["visible_check"]
    if not isinstance(visible_check, Mapping):
        raise RunnerError("apparatus visible_check is not an object")
    visible_argv = apparatus.string_list(
        visible_check["argv"],
        label="apparatus visible_check argv",
    )
    visible_timeout = visible_check["timeout_milliseconds"]
    if (
        isinstance(visible_timeout, bool)
        or not isinstance(visible_timeout, int)
        or visible_timeout <= 0
    ):
        raise RunnerError("visible check timeout must be positive")

    exclusions_raw = locked_apparatus["product_projection_exclusions"]
    if not isinstance(exclusions_raw, list) or any(
        not isinstance(item, str) for item in exclusions_raw
    ):
        raise RunnerError("product projection exclusions are malformed")
    exclusions = tuple(PurePosixPath(item) for item in exclusions_raw)
    maximum_skew = locked_apparatus["maximum_start_skew_milliseconds"]
    quiescence_grace = locked_apparatus["quiescence_grace_milliseconds"]
    if (
        isinstance(maximum_skew, bool)
        or not isinstance(maximum_skew, int)
        or maximum_skew <= 0
        or isinstance(quiescence_grace, bool)
        or not isinstance(quiescence_grace, int)
        or quiescence_grace <= 0
    ):
        raise RunnerError("apparatus timing bounds are malformed")

    treatments = lock["treatments"]
    if not isinstance(treatments, list):
        raise RunnerError("lock treatments are not an array")
    seed = lock["randomization_seed"]
    if not isinstance(seed, str):
        raise RunnerError("lock randomization seed is malformed")
    block_work_root = work_root / block_id
    prepared: list[_PreparedArm] = []
    for treatment in treatments:
        if not isinstance(treatment, Mapping):
            raise RunnerError("lock treatment is not an object")
        treatment_id = treatment["treatment_id"]
        command_path = treatment["command_config_path"]
        command_digest = treatment["command_digest"]
        if (
            not isinstance(treatment_id, str)
            or not isinstance(command_path, str)
            or not isinstance(command_digest, str)
            or command_path not in treatment_verified
        ):
            raise RunnerError("treatment command binding is malformed")
        if (
            apparatus.sha256_bytes(treatment_verified[command_path])
            != command_digest
        ):
            raise RunnerError(f"{treatment_id} command digest mismatch")
        config_argv, config_environment, timeout = apparatus.parse_treatment_config(
            treatment_verified[command_path],
            label=f"{treatment_id} command config",
            expected_environment_identity=environment_identity,
            expected_provider_policy_digest=provider_policy_digest,
        )

        opaque_label = apparatus.opaque_label(seed, block_id, treatment_id)
        workspace_path = block_work_root / opaque_label / "workspace"
        runtime_root = block_work_root / ".controller" / opaque_label
        result_path = runtime_root / "raw-result.json"
        asset_root = runtime_root / "apparatus"
        staged_paths = {
            "task_path": asset_root.joinpath(*PurePosixPath(task_path).parts),
            "provider_config": asset_root.joinpath(
                *PurePosixPath(provider_path).parts
            ),
            "prompt_config": asset_root.joinpath(
                *PurePosixPath(prompt_path).parts
            ),
            "command_config": asset_root.joinpath(
                *PurePosixPath(shared_command_path).parts
            ),
        }
        replacements = {
            "workspace": str(workspace_path),
            "task_path": str(staged_paths["task_path"]),
            "result_path": str(result_path),
            "provider_config": str(staged_paths["provider_config"]),
            "prompt_config": str(staged_paths["prompt_config"]),
            "command_config": str(staged_paths["command_config"]),
            "apparatus_root": str(asset_root),
        }
        argv = tuple(
            apparatus.substitute(
                item,
                replacements,
                label=f"{treatment_id} command argv",
            )
            for item in config_argv
        )

        if {"HOME", "TMPDIR"} & set(config_environment):
            raise RunnerError(
                "HOME and TMPDIR are controller-owned environment keys"
            )
        if set(config_environment) != launcher_environment_keys:
            raise RunnerError(
                f"{treatment_id} environment must provide the exact locked "
                "non-controller, non-credential keys"
            )
        if secret_values is None:
            secret_values = apparatus.resolve_credentials(credential_names)
        environment = dict(config_environment)
        for key, value in tuple(environment.items()):
            environment[key] = apparatus.substitute(
                value,
                replacements,
                label=f"{treatment_id} environment value",
            )
        environment["HOME"] = str(runtime_root / "home")
        environment["TMPDIR"] = str(runtime_root / "tmp")
        environment.update(secret_values)
        missing_environment = allowed_keys - set(environment)
        if missing_environment:
            raise RunnerError(
                "allowed environment keys lack verified values: "
                + ", ".join(sorted(missing_environment))
            )
        if set(environment) != allowed_keys:
            raise RunnerError("closed environment does not match the lock allowlist")

        prepared.append(
            _PreparedArm(
                command=ArmCommand(
                    treatment_id=treatment_id,
                    opaque_arm_label=opaque_label,
                    command_digest=command_digest,
                    argv=argv,
                    environment=tuple(sorted(environment.items())),
                    timeout_milliseconds=timeout,
                    workspace=workspace_path,
                    runtime_root=runtime_root,
                    result_path=result_path,
                ),
                staged_assets=apparatus.stage_verified_assets(
                    root=asset_root,
                    verified=treatment_verified,
                ),
                credential_names=credential_names,
            )
        )

    prepared_arms = tuple(prepared)
    _validate_candidate_visibility(
        arms=prepared_arms,
        evidence_root=evidence_root,
        record_path=record_path,
        randomization_seed=seed,
        treatment_ids=tuple(
            arm.command.treatment_id for arm in prepared_arms
        ),
        apparatus_control_root=apparatus.canonical_absolute_path(
            locked_apparatus["control_root"],
            label="apparatus.control_root",
        ),
    )
    return _Preflight(
        repo=source_binding.repo,
        treeish=source_binding.treeish,
        archive_digest=source_binding.archive_digest,
        source_task_path=source_binding.task_path,
        task_brief_digest=source_binding.task_digest,
        exclusions=exclusions,
        visible_check_argv=visible_argv,
        visible_check_timeout_milliseconds=visible_timeout,
        maximum_start_skew_milliseconds=maximum_skew,
        quiescence_grace_milliseconds=quiescence_grace,
        arms=prepared_arms,
        attempt_class=attempt_class,
        sequence_index=sequence_index,
        record_path=record_path,
    )
