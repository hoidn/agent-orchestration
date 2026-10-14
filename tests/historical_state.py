"""Historical persisted states for retained reader and shared-service tests."""

import hashlib
import json

from orchestrator.state import RunState


def write_historical_state(
    manager,
    workflow_file,
    context=None,
    bound_inputs=None,
    *,
    result_persistence_profile=None,
    observability=None,
):
    """Write a schema-2.1 fixture with the actual historical serializer."""
    state = RunState(
        schema_version="2.1",
        run_id=manager.run_id,
        workflow_file=str(workflow_file),
        workflow_checksum="sha256:" + hashlib.sha256(
            (manager.workspace / workflow_file).read_bytes()
        ).hexdigest(),
        started_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        status="running",
        run_root=str(manager.run_root),
        context=context or {},
        bound_inputs=bound_inputs or {},
        result_persistence_profile=result_persistence_profile,
        observability=observability,
    )
    manager.io_run_root.mkdir(parents=True, exist_ok=True)
    manager.logs_dir.mkdir(exist_ok=True)
    manager.state_file.write_text(json.dumps(state.to_dict(), indent=2), encoding="utf-8")
    return manager.load()
