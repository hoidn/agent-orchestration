Captured on 2026-10-13 before file/2 selection, with the working tree file/1 renderer. This is a real ordinary public CLI run killed after its first committed provider effect; never regenerate it.

Capture used `tests.test_workflow_evaluated_resume_replay._pre_change_workspace(root)` and `tests.test_workflow_evaluated_resume_kills._kill_after_first_commit(root, args, _env(root, provider=True))`, which invokes the public CLI with the commit gate. The frozen fake provider is copied from the historical legacy fixture. `hashes.json` records all captured source and run file SHA-256 digests.

CLI arguments: `python -m orchestrator run main.orc --source-root . --provider-externs-file providers.json --prompt-externs-file prompts.json --input "message=typed input"`.
