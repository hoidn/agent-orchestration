# Expected Outputs Guidance Annotations Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add optional guidance fields to `expected_outputs` so provider prompts can include explicit artifact intent/format hints without changing deterministic runtime validation semantics.

**Architecture:** Keep deterministic contracts unchanged (`name/path/type/allowed/...` remain authoritative). Introduce prompt-only annotation fields on `expected_outputs` (`description`, `format_hint`, `example`) with loader type checks. Update output-contract prompt rendering to include those fields when present. Runtime artifact parsing/validation continues to ignore guidance fields.

**Tech Stack:** Python (`orchestrator/loader.py`, `orchestrator/contracts/prompt_contract.py`, `orchestrator/contracts/output_contract.py`), pytest, markdown specs/docs.

---

## Scope and Compatibility Contract

1. Annotation fields are optional and backward-compatible.
2. Runtime validation behavior does not change for existing typed contracts.
3. New fields are prompt-only metadata for provider output contract injection.
4. Loader enforces annotation field types (`str`) and keeps existing contract validation strictness.
5. No new DSL version gate needed (field additions are additive and non-breaking).

---

### Task 1: Loader Support for Annotation Fields (Type-Checked)

**Files:**
- Modify: `orchestrator/loader.py`
- Modify: `tests/test_loader_validation.py`
- Modify: `specs/dsl.md`

**Step 1: Write failing loader tests for new optional fields**

Add tests in `tests/test_loader_validation.py`:

```python
def test_expected_outputs_guidance_fields_accept_strings(self):
    workflow = {
        "version": "1.1.1",
        "name": "guidance fields",
        "steps": [{
            "name": "DraftPlan",
            "provider": "codex",
            "expected_outputs": [{
                "name": "plan_path",
                "path": "state/plan_path.txt",
                "type": "relpath",
                "description": "Path to generated plan",
                "format_hint": "workspace-relative path",
                "example": "docs/plans/2026-02-27-foo.md",
            }],
        }],
    }
    result = self.loader.load(self.write_workflow(workflow))
    spec = result["steps"][0]["expected_outputs"][0]
    assert spec["description"] == "Path to generated plan"


def test_expected_outputs_guidance_fields_require_strings(self):
    workflow = {
        "version": "1.1.1",
        "name": "bad guidance types",
        "steps": [{
            "name": "DraftPlan",
            "command": ["echo", "ok"],
            "expected_outputs": [{
                "name": "plan_path",
                "path": "state/plan_path.txt",
                "type": "relpath",
                "description": {"bad": "type"},
            }],
        }],
    }
    with pytest.raises(WorkflowValidationError) as exc_info:
        self.loader.load(self.write_workflow(workflow))
    assert any("'description' must be a string" in str(err.message) for err in exc_info.value.errors)
```

Add equivalent negative tests for `format_hint` and `example` non-string values.

**Step 2: Run tests to verify red state**

Run:
```bash
pytest tests/test_loader_validation.py -k "expected_outputs and (guidance or description or format_hint or example)" -v
```
Expected: FAIL on missing loader support/type checks.

**Step 3: Implement minimal loader validation**

In `orchestrator/loader.py` `_validate_expected_outputs(...)`, add optional field checks:

```python
for key in ("description", "format_hint", "example"):
    if key in spec and not isinstance(spec[key], str):
        self._add_error(f"{context} '{key}' must be a string")
```

Do not alter runtime-required keys or value-type validation logic.

**Step 4: Re-run loader tests**

Run:
```bash
pytest tests/test_loader_validation.py -k "expected_outputs and (guidance or description or format_hint or example)" -v
pytest tests/test_loader_validation.py -v
```
Expected: PASS.

**Step 5: Document schema fields in spec**

Update `specs/dsl.md` `expected_outputs` section with optional fields:
- `description: string` (optional, prompt guidance)
- `format_hint: string` (optional, prompt guidance)
- `example: string` (optional, prompt guidance)

Explicitly state they do not affect runtime validation semantics.

**Step 6: Commit**

```bash
git add orchestrator/loader.py tests/test_loader_validation.py specs/dsl.md
git commit -m "feat(dsl): add prompt-guidance annotations for expected_outputs"
```

---

### Task 2: Inject Guidance Fields Into Output Contract Prompt Block

**Files:**
- Modify: `orchestrator/contracts/prompt_contract.py`
- Modify: `tests/test_prompt_contract_injection.py`

**Step 1: Add failing prompt-injection test**

Add test verifying provider prompt includes annotation lines:

```python
def test_output_contract_block_includes_guidance_fields(tmp_path: Path):
    # expected_outputs entry includes description/format_hint/example
    # assert captured prompt includes these lines under Output Contract
```

Assertions should include:
- `"description:"` line
- `"format_hint:"` line
- `"example:"` line

**Step 2: Run tests to verify red state**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "guidance_fields" -v
```
Expected: FAIL because renderer omits new fields.

**Step 3: Implement renderer changes**

In `render_output_contract_block(...)` append optional lines when fields are present:

```python
if "description" in spec:
    lines.append(f"  description: {spec['description']}")
if "format_hint" in spec:
    lines.append(f"  format_hint: {spec['format_hint']}")
if "example" in spec:
    lines.append(f"  example: {spec['example']}")
```

Keep existing output order stable and deterministic.

**Step 4: Re-run prompt-injection tests**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "guidance_fields or output_contract" -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add orchestrator/contracts/prompt_contract.py tests/test_prompt_contract_injection.py
git commit -m "feat(prompt): include expected_outputs guidance annotations in contract injection"
```

---

### Task 3: Runtime Validation Non-Regression (Guidance Ignored)

**Files:**
- Modify: `tests/test_output_contract.py`
- Optional (only if needed): `orchestrator/contracts/output_contract.py`

**Step 1: Add non-regression test**

Add test verifying `validate_expected_outputs(...)` ignores annotation fields and still parses typed values:

```python
def test_validate_expected_outputs_ignores_guidance_fields(tmp_path: Path):
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "decision.txt").write_text("APPROVE\n")
    specs = [{
        "name": "decision",
        "path": "state/decision.txt",
        "type": "enum",
        "allowed": ["APPROVE", "REVISE"],
        "description": "Gate decision",
        "format_hint": "uppercase token",
        "example": "APPROVE",
    }]
    artifacts = validate_expected_outputs(specs, workspace=tmp_path)
    assert artifacts["decision"] == "APPROVE"
```

**Step 2: Run targeted tests**

Run:
```bash
pytest tests/test_output_contract.py -k "guidance_fields or expected_outputs" -v
```
Expected: PASS. If this fails due to unexpected strict-field logic, make minimal compatibility fix in `output_contract.py`.

**Step 3: Commit**

```bash
git add tests/test_output_contract.py orchestrator/contracts/output_contract.py
git commit -m "test(output_contract): verify guidance annotations do not affect runtime parsing"
```

---

### Task 4: Docs + Drafting Guidance Update

**Files:**
- Modify: `specs/providers.md`
- Modify: `docs/workflow_drafting_guide.md`
- Optional: `workflows/examples/*.yaml` (example with guidance fields)

**Step 1: Document prompt-only semantics**

Update docs to clarify:
- annotation fields are for provider instruction clarity,
- runtime enforcement still comes from typed contract fields,
- recommendation to keep guidance concise and unambiguous.

**Step 2: Add one minimal example**

Add/update one example snippet showing:

```yaml
expected_outputs:
  - name: review_decision
    path: state/review_decision.txt
    type: enum
    allowed: [APPROVE, REVISE]
    description: Final implementation gate decision.
    format_hint: Uppercase token, no extra text.
    example: APPROVE
```

**Step 3: Docs sanity checks**

Run:
```bash
pytest tests/test_prompt_contract_injection.py -k "output_contract" -v
pytest tests/test_loader_validation.py -k "expected_outputs" -v
```
Expected: PASS.

**Step 4: Commit**

```bash
git add specs/providers.md docs/workflow_drafting_guide.md workflows/examples
git commit -m "docs: describe expected_outputs guidance annotations"
```

---

## Final Verification

Run:
```bash
pytest tests/test_loader_validation.py -k "expected_outputs" -v
pytest tests/test_prompt_contract_injection.py -k "output_contract" -v
pytest tests/test_output_contract.py -v
```

Manual smoke:
```bash
python -m orchestrator.cli.main run workflows/examples/backlog_plan_execute_v0.yaml --dry-run
```

Expected:
- Loader accepts guidance fields when strings and rejects invalid types.
- Provider prompt contract injection includes guidance lines deterministically.
- Runtime output validation behavior is unchanged (guidance fields ignored).
