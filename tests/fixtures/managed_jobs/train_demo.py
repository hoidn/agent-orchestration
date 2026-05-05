from pathlib import Path


Path("artifacts/managed_jobs").mkdir(parents=True, exist_ok=True)
Path("artifacts/managed_jobs/metrics.json").write_text('{"loss": 0.1}\n', encoding="utf-8")
print("managed demo training complete")
