# Provider JSON Rendering

The evaluated file-transport route now selects `file/2`. Its output contract
starts with the file-writing action and a single result path, then shows the
actual nested keys and their types. Compiler aliases and generated JSON
pointers stay internal. This implements the
[reviewed plan](../plans/2026-10-13-provider-json-contract-rendering-plan.md).

The notation is explicitly a type shape, not an example result. For example:

```text
{
  "evidence": {
    "notes": <string>
  },
  // {"under":"artifacts/review","must_exist_target":true}
  // workspace-relative; include the declared under prefix
  "report": <relpath>
}
```

Complete union alternatives include their tags and common fields. Authored
guidance and examples are JSON-encoded beside the relevant node. Empty records,
containers, nullable versus omittable fields, and direct scalar/`Value` roots
retain their existing meanings. The renderer reuses the checked descriptor's
transport schema and the validated payload's constraints and guidance; it
adds no public schema model, value parser, validator or transport.

`legacy` and `file/1` remain byte-identical for replay. A committed effect uses
its recorded rendering; new ordinary attempts use `file/2`. OMP retains its
existing normalized-text transport and `legacy` rendering. The separate
[OMP materialization correction](2026-10-13-provider-prompt-review.md) is
preserved. Internal compiled contracts, path authority and validation are
unchanged.

## Verification

- New rendering module: **31 tests passed**; tests cover structure, guidance,
  constraints and existing validator behavior, rather than instructional
  phrasing.
- Historical replay selectors: **4 passed**, including a real interrupted
  public run captured under `file/1` before changing the selector.
- Public provider-delivery selectors: **8 passed**, including compile/run
  with two distinct guided contracts followed by two read-only resumes.
- Affected suite: **403 passed in 45.67s**, using
  `pytest -q -n 16 --dist=worksteal` over the modules listed in the plan.
- Collection: **103 tests** across the added/changed modules named in the
  plan. The full affected run includes additional unchanged modules.
- Independent code/contract review: **PASS**. The reviewer additionally
  compiled four cases with a union inside a list, map, optional and record;
  all retained actual keys and constraints without input mutation.

Logs: `/tmp/provider-json-suite.log`, `/tmp/provider-json-suite.exit` and
`/tmp/provider-json-collect.log`. The new frozen fixture is
`tests/fixtures/provider_delivery_file1/`; its manifest records 14 captured
file hashes. Its memo SHA-256 is
`91cd2df7c4a967378cf359dd8905d0b9b5858cdbac00b182107193d85d2a06b4`.
The existing legacy fixture's 13 tracked files are unchanged.

Final integration found and corrected the shared flat/evaluated consumer
comparison: the old helper normalized only delivery-opening lines, which is
insufficient when the complete result presentation changes. It now checks
the request's identity, path, prompt digest and exact selected contract before
normalizing that contract to the historical presentation. The complete
contract body and surrounding prompt remain compared. A negative test confirms
that dataflow changes stay distinct and an adulterated type is rejected even
when its prompt digest is updated.

The three affected consumer modules collected **53 tests** and passed
**53 in 69.31s**, using `pytest -q -n 16 --dist=worksteal`; logs and exit code
are `/tmp/provider-json-consumer-suite.log` and
`/tmp/provider-json-consumer-suite.exit`. Independent review of this correction
passed. The direct-root selector also passed **5 tests** after correcting its
synthetic `Value` fixture to omit the example prohibited by that type.
Production rendering did not change during this integration correction, so
the earlier 403-test evidence remains applicable.

## Limits

No real provider was invoked to measure this presentation's effect. These
checks prove contract fidelity, dataflow and replay, not a reduction in model
mistakes. No full repository suite or performance benchmark was run.
Guidance absent from the compiled payload cannot be recovered by rendering.
Each subsequent prompt-byte change needs a new rendering version.

The [native-session CLI experiment](2026-10-13-native-session-cli-live.md)
ran independently with native JSON schemas. This renderer neither supplied
its prompts nor blocked its execution.
