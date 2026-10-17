# Provider result delivery

Status: Implemented in targets 2.35, 2.36 and 3.0

This document describes ordinary composed-provider delivery shared by typed
2.35/2.36 execution and the fresh-only native 3.0 profile.
[Providers](../../specs/providers.md#composed-provider-result-delivery) and
[State](../../specs/state.md#evaluated-provider-delivery-identity) own the
normative delivery and replay rules.

## Transport selection

Both runtimes prepare ordinary provider calls with `session_request=None`.
The selected registry template's `command_metadata_mode` therefore determines
the transport; its name and optional session metadata do not. An arbitrary
provider alias can use OMP transport, and a template with an ordinary command
and OMP session variant still selects file delivery for an ordinary call.

For `omp_json_stdout`, the executor validates the transport and exposes
`normalized_stdout`. Only a zero-exit execution without a transport error may
materialize those bytes. The shared performer preserves raw stdout and stderr,
then exclusively creates `result.json` relative to its pinned attempt owner.
Missing/empty normalized output refuses even if a provider planted a result.
An existing leaf or symlink refuses the exclusive write. The normal captured
result validator subsequently checks JSON, the result schema and required
outputs; ordinary native validation remains strict and redacts runtime data.

For other command transports, the provider writes the runtime-owned result
file. The absolute `ORCHESTRATOR_OUTPUT_BUNDLE_PATH` names the attempt file;
its workspace-relative spelling appears once in the prompt contract. A reply
or a file written elsewhere does not satisfy this delivery contract.

## Rendering identities

| Name | Presentation | Selection |
| --- | --- | --- |
| `legacy` | Historical structured contract with transport materialization guidance | OMP commands and historical replay |
| `file/1` | Historical file instructions followed by field/pointer schema | Historical replay |
| `file/2` | File instructions followed by nested JSON type notation | New ordinary file transports |

`file/2` projects the checked result descriptor and overlays only this call's
contract annotations. Records display actual keys and empty records. Tagged
unions display complete alternatives, including shared fields. Lists/maps keep
recursive element/value shapes; optional values remain nullable, and omittable
record fields are marked separately. Enum/path constraints and JSON-encoded
authored descriptions, format hints and examples stay at their relevant nodes.
Type markers and alternatives are schema notation, not generated output values.
Required output-position contracts still precede the structured result block.

`legacy` and `file/1` renderers are immutable because committed prompt hashes
include their bytes. A presentation change receives another registered name.
Typed replay resolves only the committed `delivery` digest: absent means
historical legacy without adding a part, recognized means the exact renderer,
and unknown means `effect_input_diverged` before dispatch. Current registry
metadata never selects a committed rendering. Native execution records no memo
and gains no replay or recovery behavior from sharing these helpers.

## Evidence and inspection

The frozen fixtures under `tests/fixtures/provider_delivery_pre_change/` and
`tests/fixtures/provider_delivery_file1/` retain historical run and renderer
bytes. Tests resume their committed prefix and exercise subsequent fresh
file/2 attempts without rewriting prior evidence. Local subprocess shims
exercise typed and native OMP parsing/materialization without external calls.

`python scripts/provider_delivery_census.py --state-dir DIR` reads typed memo
attempts, pairs outcomes by identity/attempt, resolves known delivery digests,
and summarizes results. It does not modify runs or interpret native state.
