"""Opening lines of a structured-result contract block: how the result reaches the runtime.

`legacy` is the text composed before the delivery was selected; the flat route
and evaluated rows committed before `file/1` existed render it. `file` is the
evaluated route's file transport (docs/design/provider_result_delivery.md).

`_LEGACY`, `_FILE`, `RELPATH_GUIDANCE` and the relpath walk are replay identity
for committed rows: the `prompt` input part digests the bytes they produce. A
change needs a new rendering name (`file/2`) registered beside `file/1` in
`orchestrator.workflow.evaluated.providers.DELIVERY_SELECTORS`, never an
in-place edit. The resume test over tests/fixtures/provider_delivery_pre_change
(a run committed under `legacy`) fails when those bytes drift.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, List


RELPATH_GUIDANCE = (
    "# Relpath values are workspace-relative. Include the declared `under` "
    "prefix in the value: for `under: artifacts/work`, write "
    "`artifacts/work/...`; for `under: artifacts/review`, write "
    "`artifacts/review/...`."
)

_LEGACY = (
    "Produce {subject} exactly as specified. If ORCHESTRATOR_OUTPUT_BUNDLE_PATH is present, write only to "
    "that runtime-owned authoritative target. Otherwise, do not create or modify the listed path; emit the "
    "{noun} as final assistant text only so the runtime can materialize it."
)
_FILE = (
    "Write the {noun} specified below to the file on the `- path:` line, "
    "with a file-writing or shell tool, before you finish. The environment "
    "variable ORCHESTRATOR_OUTPUT_BUNDLE_PATH names the same file. "
    "Returning the value in your reply does not deliver it."
)
_BUNDLE = ("the following JSON bundle", "JSON object")
_KINDS = {"value": ("one JSON value", "JSON value"), "bundle": _BUNDLE, "variant": _BUNDLE}


def _schema_mentions_relpath(spec: Any) -> bool:
    """Whether a field spec, walked as `_append_schema_spec` walks it, contains a `relpath` type."""
    if not isinstance(spec, Mapping):
        return False
    if spec.get("type") == "relpath":
        return True
    children = [spec.get(key) for key in ("item", "items", "keys", "values")]
    children.extend(spec.get("fields") or ())
    variants = spec.get("variants")
    if isinstance(variants, Mapping):
        for variant in variants.values():
            if isinstance(variant, Mapping):
                children.extend(variant.get("fields") or ())
    return any(_schema_mentions_relpath(child) for child in children)


def delivery_opening(kind: str, delivery: str, payload: Mapping[str, Any]) -> List[str]:
    """Lines between the block heading and its `- path:` line, the only place the attempt path appears.

    `kind` is `value` (direct JSON root), `bundle` (record) or `variant` (tagged
    union) and `payload` its contract payload. `legacy` always appends the relpath
    guidance; `file` appends it only when the payload's fields, variant fields or
    shared fields contain a `relpath` type.
    """
    if delivery not in ("legacy", "file"):
        raise ValueError(f"unknown output contract delivery: {delivery!r}")
    subject, noun = _KINDS[kind]
    specs = (payload, *payload.get("shared_fields", ()))
    lines = [_LEGACY.format(subject=subject, noun=noun) if delivery == "legacy" else _FILE.format(noun=noun)]
    if delivery == "legacy" or any(_schema_mentions_relpath(spec) for spec in specs):
        lines.append(RELPATH_GUIDANCE)
    return lines
