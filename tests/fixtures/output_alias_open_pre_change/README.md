Captured with package 6a646c74 (main before output slots were checked at launch) on 2026-11-14, at target 2.40, from the program, externs and `two.md` of `../output_alias_pre_change/`; must never be regenerated. Step `one` fills its two `:out` slots `a` and `b` with the one file `artifacts/report.txt` (content `report` and a newline; `artifacts/` is ignored by git, so the test writes it). Two run roots:

- `runs/20261114T185034Z-9aoawq`, a **pending** start of `one`: `SHIM_HANG=1`, the process group killed (SIGKILL) once the stand-in logged its call; the memo holds one `started` row.
- `runs/20261114T185036Z-q87d4k`, a **failed** attempt of `one`: `SHIM_FAIL_CALL=1`; the memo holds `started`, `failed` (`provider_exit_nonzero`) and the terminal.

Command, in the fixture's files with `codex_shim.py` installed as `bin/codex`, `PATH` the stand-in's `bin` first and `PYTHONPATH` an export of `6a646c74`: `python -m orchestrator run main.orc --provider-externs-file providers.json --prompt-externs-file prompts.json --input message=hi --input report=artifacts/report.txt`, with the environment variable named above. `run.lock` and `state.json` were not kept.
