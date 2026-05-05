"""Named managed-job extractor registry primitives."""

from __future__ import annotations

from typing import Mapping

from .models import ManagedJobMetadata


def metadata_from_extractor(
    extractor_name: str,
    extractor_spec: Mapping[str, object],
) -> ManagedJobMetadata:
    """Build metadata from a policy-declared named extractor spec."""

    version = extractor_spec.get("version")
    job = extractor_spec.get("job")
    if not isinstance(version, str) or not version:
        raise ValueError(f"extractor '{extractor_name}' requires version")
    if not isinstance(job, Mapping):
        raise ValueError(f"extractor '{extractor_name}' requires job metadata")
    from .policy import metadata_from_mapping

    metadata = metadata_from_mapping(job, context=f"extractors.{extractor_name}.job")
    return ManagedJobMetadata(
        name_template=metadata.name_template,
        state_root_template=metadata.state_root_template,
        output_root_arg=metadata.output_root_arg,
        verify_files=metadata.verify_files,
        snapshot_roots=metadata.snapshot_roots,
        config_globs=metadata.config_globs,
        extractor=extractor_name,
        extractor_version=version,
    )
