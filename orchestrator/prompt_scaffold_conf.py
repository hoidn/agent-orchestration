"""Owned immutable conf snapshots for prompt scaffold identity inputs."""

from types import MappingProxyType

from orchestrator.prompt_scaffold_render import _validate_conf_snapshot
from orchestrator.providers.omp_conf import ConfSnapshot


def owned_conf_snapshot(manifest: object) -> ConfSnapshot:
    """Validate and detach one caller-owned conf snapshot."""
    if not isinstance(manifest, ConfSnapshot):
        raise ValueError("conf_manifest must be a ConfSnapshot")
    owned = ConfSnapshot(
        files=MappingProxyType(dict(manifest.files)),
        manifest_bytes=manifest.manifest_bytes,
        manifest_sha256=manifest.manifest_sha256,
    )
    _validate_conf_snapshot(owned)
    return owned


__all__ = ["owned_conf_snapshot"]
