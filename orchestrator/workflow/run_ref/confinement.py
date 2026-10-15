"""Admission and provisioning of one `run_ref_confinement.v1` child before any release.

Admission (`admit_confined_child`) checks, in order: the durable child request
against its site and parent-resolved operands (a mismatch is
`run_ref_environment_escape_rejected`), the parent's checked child artifact,
that the child is pure (leaf execution arrives with the holder; until then any
effect site is `run_ref_environment_unavailable`, never a host fallback), the
host prerequisites and the sealed image, rehashed through the descriptor the
launch will bind. Provisioning (`provision_confined_child`) allocates the
attempt's clone with sanitized host Git beneath the run-reference root and the
child's control root beneath the parent run root, next to
`run-ref-attempts.jsonl`; neither may contain the other, nor the clone the
parent run or workspace. The control root holds `child-recipe.json`
(`run_ref_confined_child_recipe.v1`), the child-recipe variant that binds the
checked child artifact, the request, the admission record and the clone
baseline. An existing control root is reused only when its recipe, image pins
and clone baseline still match (`run_ref_environment_changed` otherwise).

The holder, its scope and leaves are not here (Task 6).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import platform
import shutil
import stat
from typing import Any

from orchestrator.contracts.closed_program.program import ClosedProgram
from orchestrator.workflow.evaluated.machine import site_nodes

from .checkpoint import MAX_CHECKPOINT_ENTRIES
from .confined_config import RunRefConfinedStaticConfig
from .contracts import RUN_REF_CONFINEMENT_PROFILE, VerifiedGitTreeIdentity, canonical_json_bytes
from .image_store import ImageStoreError, SealedImage, open_sealed_image
from .ledger import RunRefVisitKey
from .runtime import RunRefRuntimeError, build_run_ref_accounting, run_ref_visit_workspace
from .confined_source import ConfinedSource, confined_revision, materialize_confined_source
from .source import RunRefSourceRefusal, canonical_repository_revision_result
from .wire import validate_confined_child_request
from .workspace import freeze_tree


CHILD_ROOTS_DIRNAME = "run-ref-children"
RECIPE_FILENAME = "child-recipe.json"
RECIPE_SCHEMA = "run_ref_confined_child_recipe.v1"
ADMISSION_SCHEMA = "run_ref_environment_admission.v1"
CHILD_RUN_IDENTITY_SCHEMA = "run_ref_confined_child_run_identity.v1"
FIXED_BWRAP = Path("/usr/bin/bwrap")
FIXED_SYSTEMD_RUN = Path("/usr/bin/systemd-run")
_PTRACE_SCOPE = Path("/proc/sys/kernel/yama/ptrace_scope")


@dataclass(frozen=True)
class HostFacts:
    """Host prerequisites of the profile, probed once per admission."""

    bwrap: bool
    systemd_run: bool
    ptrace_scope: int | None
    machine: str

    @property
    def record(self) -> dict[str, Any]:
        return {"bwrap": self.bwrap, "systemd_run": self.systemd_run,
                "ptrace_scope": self.ptrace_scope, "machine": self.machine}


def _fixed_executable_admitted(path: Path) -> bool:
    from orchestrator.providers.isolation_backend import (
        ProviderIsolationBackendUnavailable,
        _admit_fixed_backend_executable,
    )

    try:
        _admit_fixed_backend_executable(path, keep_open=False)
    except (ProviderIsolationBackendUnavailable, OSError):
        return False
    return True


def probe_host() -> HostFacts:
    """Read the real host: fixed root-owned executables, Yama scope, architecture."""
    try:
        ptrace_scope: int | None = int(_PTRACE_SCOPE.read_text(encoding="ascii").strip())
    except (OSError, ValueError):
        ptrace_scope = None
    return HostFacts(bwrap=_fixed_executable_admitted(FIXED_BWRAP),
                     systemd_run=_fixed_executable_admitted(FIXED_SYSTEMD_RUN),
                     ptrace_scope=ptrace_scope, machine=platform.machine())


def require_host_prerequisites(host: HostFacts) -> None:
    """Refuse with `run_ref_environment_unavailable` naming the first missing prerequisite."""
    missing = [name for name, ok in (
        ("bwrap", host.bwrap),
        ("systemd_run", host.systemd_run),
        ("yama_ptrace_scope", host.ptrace_scope is not None and host.ptrace_scope >= 1),
        ("x86_64", host.machine == "x86_64"),
    ) if not ok]
    if missing:
        raise RunRefRuntimeError("run_ref_environment_unavailable", f"host_prerequisite_missing:{missing[0]}")


def checked_child_program(parent_program: ClosedProgram, config: RunRefConfinedStaticConfig) -> ClosedProgram:
    """The parent's checked child entry for this site; a confined child never compiles."""
    digest = config.program.child_program_digest
    tree = parent_program.tree.get("children", {}).get(digest)
    if tree is None:
        raise RunRefRuntimeError("run_ref_child_target_unavailable", "checked_child_artifact_missing")
    program = ClosedProgram.from_artifact(canonical_json_bytes(tree).decode("utf-8"))
    if program.digest != digest:
        raise RunRefRuntimeError("run_ref_child_target_unavailable", "checked_child_artifact_digest_differs")
    return program


@dataclass
class ConfinedAdmission:
    """Everything admitted before provisioning; owns the image descriptor."""

    config: RunRefConfinedStaticConfig
    request: dict[str, Any]
    commit: str
    program: ClosedProgram
    image: SealedImage
    host: HostFacts

    @property
    def inputs(self) -> dict[str, Any]:
        return {row["name"]: row["value"] for row in self.request["inputs"]}

    @property
    def environment_record(self) -> dict[str, Any]:
        """Image identity and pins: what resume must find unchanged."""
        record = self.image.record
        return {"profile": RUN_REF_CONFINEMENT_PROFILE,
                "image": {name: record[name] for name in (
                    "image", "manifest_digest", "config_digest", "platform", "tree_digest")},
                "executable_pins": record["executable_pins"]}

    @property
    def record(self) -> dict[str, Any]:
        return {"schema_version": ADMISSION_SCHEMA, **self.environment_record,
                "request_digest": self.request["digest"], "host": self.host.record}

    def close(self) -> None:
        self.image.close()


def admit_confined_child(
    config: RunRefConfinedStaticConfig,
    request_record: object,
    *,
    commit: str,
    inputs: Mapping[str, Any],
    parent_program: ClosedProgram,
    image_store: Path,
    host: HostFacts,
) -> ConfinedAdmission:
    """Admit one confined child before any provisioning or process release."""
    try:
        request = validate_confined_child_request(request_record, config, commit=commit, inputs=inputs)
    except (TypeError, ValueError) as exc:
        raise RunRefRuntimeError("run_ref_environment_escape_rejected", "confined_child_request_disagrees") from exc
    program = checked_child_program(parent_program, config)
    if site_nodes(program):
        raise RunRefRuntimeError("run_ref_environment_unavailable", "confined_leaf_execution_unavailable")
    require_host_prerequisites(host)
    try:
        image = open_sealed_image(image_store, config.policy.image)
    except ImageStoreError as exc:
        raise RunRefRuntimeError(exc.code, f"image_admission_refused:{exc.detail}") from exc
    return ConfinedAdmission(config=config, request=request, commit=commit, program=program,
                             image=image, host=host)


@dataclass(frozen=True)
class ConfinedAttemptLayout:
    """One attempt's clone, child run id and external control (child run) root."""

    workspace: Path
    child_run_id: str
    child_root: Path


def confined_attempt_layout(
    *,
    run_ref_root: Path,
    parent_run_root: Path,
    visit: RunRefVisitKey,
    attempt_ordinal: int,
    config: RunRefConfinedStaticConfig,
) -> ConfinedAttemptLayout:
    """One clone per visit attempt; the control root lives beneath the parent run root."""
    identity = {"schema_version": CHILD_RUN_IDENTITY_SCHEMA, "visit": visit.record,
                "attempt_ordinal": attempt_ordinal, "static_config_digest": config.digest}
    child_run_id = "run-ref-" + hashlib.sha256(canonical_json_bytes(identity)).hexdigest()[:40]
    return ConfinedAttemptLayout(
        workspace=run_ref_visit_workspace(Path(run_ref_root), visit, attempt_ordinal),
        child_run_id=child_run_id,
        child_root=Path(parent_run_root) / CHILD_ROOTS_DIRNAME / child_run_id,
    )


def refuse_overlapping_roots(layout: ConfinedAttemptLayout, *, parent_run_root: Path,
                             parent_workspace: Path) -> None:
    """Refuse a clone that aliases authority: compared after resolving every symlink."""
    real = lambda path: Path(os.path.realpath(path))  # noqa: E731
    clone, control = real(layout.workspace), real(layout.child_root)
    contained = [control, real(parent_run_root), real(parent_workspace)]
    if clone.is_relative_to(control) or any(path.is_relative_to(clone) for path in contained):
        raise RunRefRuntimeError("run_ref_environment_escape_rejected", "confined_roots_overlap")


@dataclass(frozen=True)
class ProvisionedChild:
    layout: ConfinedAttemptLayout
    source: ConfinedSource
    recipe: dict[str, Any]

    @property
    def recipe_bytes(self) -> bytes:
        return canonical_json_bytes(self.recipe)


def _recipe(admission: ConfinedAdmission, layout: ConfinedAttemptLayout, source: ConfinedSource) -> dict[str, Any]:
    return {
        "schema_version": RECIPE_SCHEMA,
        "child_run_id": layout.child_run_id,
        "child_root": layout.child_root.as_posix(),
        "clone_root": layout.workspace.as_posix(),
        "static_config_digest": admission.config.digest,
        "child_program_digest": admission.program.digest,
        "request_digest": admission.request["digest"],
        "commit": admission.commit,
        "repository_revision": canonical_repository_revision_result(source.repository_revision_id),
        "verified_git_tree": source.verified_git_tree.value,
        "mirror_path": source.mirror_path.as_posix(),
        "baseline_digest": source.source_tree_manifest.digest,
        "admission": admission.record,
    }


def provision_confined_child(
    admission: ConfinedAdmission,
    layout: ConfinedAttemptLayout,
    *,
    run_ref_root: Path,
    parent_run_root: Path,
    parent_workspace: Path,
) -> ProvisionedChild:
    """Allocate the sanitized clone and the control root, or revalidate an existing pair."""
    refuse_overlapping_roots(layout, parent_run_root=parent_run_root, parent_workspace=parent_workspace)
    if os.path.lexists(layout.child_root):
        try:
            _read_recipe(layout)
        except RunRefRuntimeError:
            _discard_unpublished_attempt(layout)
        else:
            return _reuse_provisioned_child(admission, layout)
    elif os.path.lexists(layout.workspace):
        # The control root, named by the child run id, is durable before any clone, so a
        # clone without it was not made for this child: keep it and fail closed.
        raise RunRefRuntimeError("run_ref_evidence_invalid", "orphan_clone_not_bound_to_child")
    children = layout.child_root.parent
    if not children.is_dir():
        children.mkdir(parents=True, exist_ok=True)
        _fsync_directory(children.parent)  # the run-ref-children entry in the parent run root
    layout.child_root.mkdir(mode=0o700)
    _fsync_directory(children)
    try:
        source = materialize_confined_source(admission.config.repo, admission.commit,
                                             run_ref_root=run_ref_root, workspace=layout.workspace)
    except RunRefSourceRefusal:
        if not os.path.lexists(layout.workspace):
            os.rmdir(layout.child_root)  # refused before cloning: nothing was provisioned
        raise
    refuse_overlapping_roots(layout, parent_run_root=parent_run_root, parent_workspace=parent_workspace)
    if len(source.source_tree_manifest.entries) > MAX_CHECKPOINT_ENTRIES:
        raise RunRefRuntimeError("run_ref_environment_unavailable", "clone_exceeds_entry_bound")
    provisioned = ProvisionedChild(layout=layout, source=source, recipe=_recipe(admission, layout, source))
    fd = os.open(layout.child_root / RECIPE_FILENAME,
                 os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        os.write(fd, provisioned.recipe_bytes)
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(layout.child_root)
    return provisioned


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _discard_entry(path: Path) -> None:
    if stat.S_ISDIR(os.lstat(path).st_mode):
        shutil.rmtree(path)
    else:
        os.unlink(path)


def _discard_unpublished_attempt(layout: ConfinedAttemptLayout) -> None:
    """Without a complete recipe nothing was released: drop the partial control root and clone.

    Anything beyond a torn recipe in the control root means authority was published, so
    that root fails closed instead.
    """
    if not stat.S_ISDIR(os.lstat(layout.child_root).st_mode) or set(os.listdir(layout.child_root)) - {RECIPE_FILENAME}:
        raise RunRefRuntimeError("run_ref_evidence_invalid", "confined_child_recipe_unreadable")
    _discard_entry(layout.child_root)
    if os.path.lexists(layout.workspace):
        _discard_entry(layout.workspace)


def _read_recipe(layout: ConfinedAttemptLayout) -> dict[str, Any]:
    import json

    try:
        fd = os.open(layout.child_root / RECIPE_FILENAME, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            payload = b"".join(iter(lambda: os.read(fd, 1 << 20), b""))
        finally:
            os.close(fd)
        recipe = json.loads(payload)
    except (OSError, ValueError) as exc:
        raise RunRefRuntimeError("run_ref_evidence_invalid", "confined_child_recipe_unreadable") from exc
    if not isinstance(recipe, dict) or canonical_json_bytes(recipe) != payload:
        raise RunRefRuntimeError("run_ref_evidence_invalid", "confined_child_recipe_not_canonical")
    return recipe


def _reuse_provisioned_child(admission: ConfinedAdmission, layout: ConfinedAttemptLayout) -> ProvisionedChild:
    recipe = _read_recipe(layout)
    _source, revision = confined_revision(admission.config.repo, admission.commit)
    expected = {
        "schema_version": RECIPE_SCHEMA, "child_run_id": layout.child_run_id,
        "child_root": layout.child_root.as_posix(), "clone_root": layout.workspace.as_posix(),
        "static_config_digest": admission.config.digest, "child_program_digest": admission.program.digest,
        "request_digest": admission.request["digest"], "commit": admission.commit,
        "repository_revision": canonical_repository_revision_result(revision),
    }
    if {name: recipe.get(name) for name in expected} != expected:
        raise RunRefRuntimeError("run_ref_evidence_invalid", "confined_child_recipe_disagrees")
    stored = recipe.get("admission") or {}
    if {name: stored.get(name) for name in admission.environment_record} != admission.environment_record:
        raise RunRefRuntimeError("run_ref_environment_changed", "image_snapshot_or_pins_changed")
    try:
        manifest = freeze_tree(layout.workspace, excluded_roots=(".git",))
    except (OSError, ValueError) as exc:
        raise RunRefRuntimeError("run_ref_environment_changed", "clone_unreadable") from exc
    try:
        verified_tree = VerifiedGitTreeIdentity(recipe.get("verified_git_tree"))
        mirror_path = Path(recipe.get("mirror_path"))
        if not isinstance(recipe.get("baseline_digest"), str):
            raise TypeError("baseline digest is not a string")
    except (TypeError, ValueError) as exc:
        raise RunRefRuntimeError("run_ref_evidence_invalid", "confined_child_recipe_disagrees") from exc
    if manifest.digest != recipe["baseline_digest"]:
        raise RunRefRuntimeError("run_ref_environment_changed", "clone_differs_from_baseline")
    source = ConfinedSource(repository_revision_id=revision, verified_git_tree=verified_tree,
                            mirror_path=mirror_path, workspace_path=layout.workspace,
                            source_tree_manifest=manifest)
    return ProvisionedChild(layout=layout, source=source, recipe=recipe)


def confined_child_accounting(layout: ConfinedAttemptLayout, *, attempt_ordinal: int, terminal_status: str,
                              elapsed_ms: int) -> dict[str, Any]:
    """The profile has no setup and never compiles in the clone: both durations are 0."""
    return build_run_ref_accounting(child_run_id=layout.child_run_id, attempt_ordinal=attempt_ordinal,
                                    terminal_status=terminal_status, elapsed_ms=elapsed_ms,
                                    setup_ms=0, compile_ms=0)


__all__ = [
    "ConfinedAdmission",
    "ConfinedAttemptLayout",
    "HostFacts",
    "ProvisionedChild",
    "admit_confined_child",
    "checked_child_program",
    "confined_child_accounting",
    "confined_attempt_layout",
    "probe_host",
    "provision_confined_child",
    "refuse_overlapping_roots",
    "require_host_prerequisites",
]
