Read the listed steering, target design, baseline design, command-adapter
contract, progress ledger, selector bundle, architecture target contract, existing
implementation architecture index, drafted architecture, generated work-item
context, and generated check commands from the checkout before acting.

Review the drafted implementation architecture for the selected Lisp frontend
target-design gap. Decide whether it is safe to use as the source for the
downstream plan and implementation phases.

Do not approve based only on file existence, parseability, or section presence;
explicitly judge whether the architecture semantically matches the current
selection rationale, scope constraints, and existing implementation context.

Approve only if the architecture:

- stays bounded to exactly the selected design gap;
- is coherent with prior implementation architecture documents;
- does not redefine shared concepts owned by earlier slices or governing design
  docs;
- makes ownership boundaries explicit;
- follows the command-adapter contract when scripts, commands, adapters, or
  runtime-native effects are in scope;
- avoids report parsing, pointer files, debug projections, or inline glue as
  semantic authority;
- gives concrete implementation deliverables and deterministic verification
  commands;
- does not rely on unsupported DSL/runtime behavior.

Write the architecture review report to the target review-report path. Write the
review decision to the target decision path.

Use only one of these decisions:

- `APPROVE`: the architecture can drive the plan and implementation stack.
- `REVISE`: the architecture must be revised before planning.

If you write `REVISE`, the report must include specific findings and the
required changes. Do not revise the architecture in this step.
