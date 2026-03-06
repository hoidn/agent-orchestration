# Workspace Index

Start here.

## Key Files

- `state/task.md`: canonical task description injected at runtime
- `docs/tasks/port_sliding_window_to_rust.md`: canonical task fixture for this seed
- `src_py/sliding_window.py`: Python reference behavior to port
- `rust/`: Rust crate target area
- `docs/dev_guidelines.md`: local engineering rules
- `docs/plans/templates/`: optional planning and review aids
- `artifacts/`: execution, check, and review outputs
- `state/`: workflow state and task artifacts

## Expectations

- Read the injected task first. If it mirrors the canonical task fixture, follow the injected file.
- Keep the port standard-library only unless the task explicitly says otherwise.
- Derive visible checks from the Rust crate and the task.
- Preserve documented semantics, especially window boundaries, stride behavior, drop-last handling, and padding rules.
