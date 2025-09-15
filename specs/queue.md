# Queues and Wait-For (Normative)

- Workspace directories
  - `inbox/`: agent work queues (`*.task` conventions per workflow)
  - `processed/`: completed work items, typically partitioned by run timestamp
  - `failed/`: quarantined work items
  - Orchestrator uses these by convention; lifecycle is authored explicitly in workflows.

- Task file creation
  - Write as `*.tmp`, then atomic rename to `*.task`.

- Lifecycle ownership
  - Orchestrator does not automatically move/archive/delete task files.
  - Workflows should author explicit steps to move items to `processed/{timestamp}/` or `failed/{timestamp}/`.
  - Helpers `--clean-processed`, `--archive-processed` are provided but do not act on individual items.

- Wait-for (blocking primitive)
  - `wait_for: { glob, timeout_sec=300, poll_ms=500, min_count=1 }`.
  - Mutually exclusive with `command`/`provider`/`for_each` in the same step.
  - On completion, record `files`, `wait_duration_ms`, `poll_count`, `timed_out` in state; on timeout set exit 124.

Example state fragment (`steps.<StepName>`):

```json
{
  "status": "completed",
  "files": ["inbox/engineer/replies/task_001.task"],
  "wait_duration_ms": 12345,
  "poll_count": 25,
  "timed_out": false
}
```

- Declarative per-item lifecycle (planned v1.2)
  - `for_each.on_item_complete` (opt-in, version-gated) moves items on success/failure.
  - See `versioning.md` for schema and acceptance.

## Workspace Directory Layout

```
workspace/
├── src/                    # User source code
├── prompts/               # Reusable prompt templates
├── artifacts/             # Agent-generated outputs
│   ├── architect/
│   ├── engineer/
│   └── qa/
├── inbox/                 # Agent work queues
│   ├── architect/
│   ├── engineer/
│   └── qa/
├── processed/             # Completed work items
│   └── {timestamp}/
└── failed/               # Failed work items (quarantine)
    └── {timestamp}/
```

Path resolution rule: All user-declared paths remain explicit and resolve against WORKSPACE. No auto-prefixing based on agent.

Path safety: See `security.md#path-safety` for normative rules; child processes may read/write anywhere permitted by the OS.

## Task Queue System

Writing tasks:
1. Create as `*.tmp` file
2. Atomic rename to `*.task`

Processing results (recommended, user-managed):
- Success: Add a step to `mv <task> processed/{timestamp}/`
- Failure: Add a step to `mv <task> failed/{timestamp}/`

Ownership clarification:
- The orchestrator does not automatically move, archive, or delete task files.
- Queue directories and `*.task` files are conventions used by workflows; authors are responsible for file lifecycle via explicit steps.
- The orchestrator provides blocking (`wait_for`) and safe CLI helpers (`--clean-processed`, `--archive-processed`) but never moves individual tasks on step success/failure.

Configuration defaults:
```yaml
inbox_dir: "inbox"
processed_dir: "processed"
failed_dir: "failed"
task_extension: ".task"
```
