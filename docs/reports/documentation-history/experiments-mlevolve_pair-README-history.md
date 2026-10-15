# experiments/mlevolve_pair/README.md: Historical Sections

Status: **Historical.** Original tense, versioned acceptance language, receipts
and commands are preserved as evidence, not current execution or work selection.
Current owner: [README.md](../../../experiments/mlevolve_pair/README.md).

## Historical operational record 5

`search.orc` records the authored ORC policy, but this specimen does not claim
that the policy executed: the original release compiler rejected the controller. It
first met the 256-node limit of a pure expression; since bound values are
shared in a payload it meets a loop inside a branch
(`workflow_boundary_type_invalid`). `compare.py` runs the Python controller with
direct and subprocess leaves, then attempts the ORC compile and public run.
The following reproduction is historical and requires its original release and
environment. In the current package, the old entry refuses at the retirement
boundary before the former lowerer diagnostic; this command is not the current
compact-controller recipe:

```bash
python -m experiments.mlevolve_pair.compare --output /tmp/mlevolve-pair-evidence.json
```
