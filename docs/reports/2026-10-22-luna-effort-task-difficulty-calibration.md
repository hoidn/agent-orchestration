# Luna low/high task-difficulty calibration: both tasks fail qualification

Role: captured LH experiment methods, results and limitations. This report grants
no provider spend and is not a launch recipe. The
[selected plan](../plans/2026-10-22-simple-evaluation-calibration-plan.md)
owns selection; frozen criteria, canonical joins and the supplementary target
report own the measurements. Earlier TD/TD2 records remain unchanged in the
[recovery report](2026-10-22-natural-task-difficulty-recovery.md).

**The two-task set is not calibrated.** RPI fails separation and the strict
upper score bound; PRR is within the target interval but fails separation.
All ten fresh sessions completed, consuming the authorized overall cap of
**twenty-six**, including sixteen historical starts. No Claude/Fable session,
native child or extra root was observed in this iteration. Both judge-integrity
reviews passed; no observation was dropped, relabeled or rescored.

## Method and authority

For each of `resume-projection-integrity` (RPI) and `pure-result-replay` (PRR),
two independent `direct_task` attempts used exact `gpt-5.6-luna` low and two
`luna_high` attempts used the same model at high effort. Both used
`control/direct_task.orc`, identical packages, seeded bases and tools, and a
14,400-second timeout. All eight outputs were fresh; effort was the treatment.

One exact `gpt-6.1-sol` high blind judge per task scored four anonymized clones
in one batch. The owner selected Sol with “change it to sol 6.1 high” before
judging. Completeness, correctness, scope and layering each score 0–2, totaling
0–8. Coders could use visible development tests; judges could neither execute
tests nor use archived test results. No artificial controls, reference or
hidden-test runs entered this pilot.

During generation, before judging, the owner added:

> (let's let the calibration target score for high be >3, <5; if out of range (/8) difficulty must be adjusted. iteration until success)

The frozen supplement interprets this as the mean of two high-effort scores
per task. Both tasks must satisfy all three predicates: high-minus-low ≥2,
high mean >3 and high mean <5. Exact endpoints fail. The canonical clone/run
join retains all four original observations per task and refuses missing,
duplicated, invalid or excluded evidence. The supplementary helper applies
existing `summarize.verdict` to unchanged canonical measures; the gap-only
canonical verdict is not final qualification.

The owner answered “i authorize” to ten fresh sessions, overall cap twenty-six.
The separate Sol amendment and judging approval retain that budget answer.
Each unit had a one-call cap, at most two concurrent generations and sequential
judges. There were no retries or replacements. The instruction to iterate adds
no budget; any subsequent natural task/seed revision and spend need a concrete
bounded iteration, preserving these original observations and criteria.

## Frozen lineage and review environment

Evidence (`E`) is `/home/ollie/sc-evidence/LH-20261022`; criterion/packet names
below are under `/home/ollie/sc-evidence/freeze-luna-effort-20261022`.
Operator sources are under `/home/ollie/sc-evidence/preparation`.

| Artifact | Exact identity |
| --- | --- |
| Generation runtime `/home/ollie/sc-runtime-luna-effort` | commit `fa057b597564be68ea94d8ffd77fa32d3cdc4eea` |
| Analysis runtime `/home/ollie/sc-runtime-luna-sol-judge` | commit `12da38844aa89ad815e58347e468001a69d4e2b5` |
| Original `criterion.json` | SHA256 `ffde67d90a2aee30030a28e1f99f1f4ffd27215d67f042589b10a088f81e9b36` |
| Original `generation-packet.json` | SHA256 `7126fe64554381db209d700d99c35bf7a80ba196afe4a5ae2295156978be4e9a`; 850 files |
| `criterion-sol-judge.json` | SHA256 `e7a71bd95a914bb4c4a86da25202814a64f815ddc899b4ee7a87ced775f978e0` |
| `difficulty-target.json` | SHA256 `2c2df8015cb7f22b01de89f14ab5443b998a632bf260cd67084d8caf111ba51b` |
| `judging-packet-sol.json` | SHA256 `37694b547dbd0ecab0b529055c4f5663e484ebce16184b422014f9becc26a0a4`; 952 files |
| `E/owner-approval-generation.json` | SHA256 `1db714f1b92c34f252618c95215843ee2ca53457d5c90fa8a2c5453ce5a48c01` |
| `E/owner-sol-judge-amendment.json` | SHA256 `310c4c18db42047c5b5a7446d3152eceb5b1e3385b85e5023956a78ecb4a6ab2` |
| `E/owner-approval-judging.json` | SHA256 `5066e4f7138b8fd8d96c1e791973f7de8ad5315af4dbb8af85d661bde779441a` |

The analysis criterion retains the original generation runtime and fixed
criterion/packet refs, adding a separate analysis runtime and Sol binding.
Original commands, masks, outcomes, raw patches and receipts remain unchanged.
Uniform terminal-single-call intake admits an original failed delivery only
with complete capture proof; all eight generations here completed with exit zero.

Review clones use a real Git baseline excluding `docs/plans/evidence`, then
apply the exact captured patch. This avoids the historical tracked-file masking
failure. Two real Bubblewrap/fake-Codex checks verified all eight Git views:
archive absent and untracked, no synthetic deletions, exact raw diff, and all
24 pool-record/index hashes unchanged. Sol/high forwarding, exec-scope native
agent disable flags, private roots, installed-Claude/auth isolation and guard
refusals passed. `E/judging-mask-smoke.json` SHA256 is
`36d987925ca6d262b97611a78115c34be5ebd4521866b83a1b1cb3f26de12717`.
This is scripted-CLI apparatus evidence, not a live-model prevention guarantee.

## Canonical results and measurement limits

`E/combined-readout.json` SHA256 is
`3b20f182cdc972c290de1b9aa6d065629f612a390335c8f255c6db12c5f30def`;
`E/difficulty-target-readout.json` SHA256 is
`0e436ee53d017ec572c64b97de41e6a7b1a1202b1072a39fd861aaddc6f44bf4`.

| Task | Low scores / mean | High scores / mean | Gap ≥2 | High >3 | High <5 | Target result |
| --- | --- | --- | --- | --- | --- | --- |
| RPI | 6, 6 / 6 | 5, 5 / 5 | −1: fail | Pass | Fail | `too_easy`; separation also fails |
| PRR | 4, 5 / 4.5 | 4, 4 / 4 | −0.5: fail | Pass | Pass | `insufficient_separation` |

All scores are out of eight. These totals expose a **rubric-granularity limit**.
RPI completeness/correctness are 1/1 for every attempt; low scope/layering are
2/2, while high-1 is 1/2 and high-2 is 2/1. The judge's reasons describe more
omitted functional requirements in low attempts, but the coarse functional
buckets tie and scope/layering reverse the total. PRR gives high correctness 1
versus low correctness 0, yet high scope/layering 1/1 versus low 1/2 and 2/2
again reverse the total; completeness is 1 throughout. Thus the totals do not
establish better low-effort functional coverage. These are the judge's diagnoses,
not independently validated technical findings. `too_easy` is the target's
mechanical label for RPI's mean, not an isolated diagnosis of intrinsic task
difficulty. Preserve the failed qualification and original scores unchanged.

## Integrity and deployed consumption

`E/generation-independent-audit.json` SHA256
`9a0107dcfd740c46c9e992f575efbf861f2b9ebd21e30cc57de92774edf57239`
reviewed all 962 generation actions, eight exact model/effort receipts, raw
patch hashes, 850 packet files and 2,307 protected historical files. All 24
original scan hits remain recorded with scoped private-tmp/tmux clearance.
`E/judging-independent-audit.json` SHA256 `308a3c5c2c0ec2d4dfaa8ef28c65c3e6d8b4cadfa8d485cf31b225af73e9e87f` records both Sol-high integrity reviews PASS.
All 44 judge actions were reviewed; 60 test-source-text scan false positives remain preserved with their original snapshots.

The canonical inventory has ten fresh physical calls plus sixteen historical
starts, exactly cap twenty-six, with zero Claude roots, children, extra roots
or spawn actions. All ten receipts are positive and complete. The following
are summed charge-token categories from those receipts; cache-write tokens are
zero. Wall times are canonical mean generation seconds, not native receipt time.

| Task / unit | Calls | Uncached input | Cache read | Output | Mean generation seconds |
| --- | --- | --- | --- | --- | --- |
| RPI low | 2 | 152,374 | 3,665,664 | 17,886 | 88.46 |
| RPI high | 2 | 880,365 | 66,022,912 | 189,075 | 1,041.59 |
| RPI Sol judge | 1 | 141,164 | 2,132,608 | 9,867 | Unavailable |
| PRR low | 2 | 127,461 | 2,919,168 | 16,855 | 98.39 |
| PRR high | 2 | 1,017,699 | 58,960,128 | 154,808 | 1,182.86 |
| PRR Sol judge | 1 | 136,597 | 1,458,688 | 7,451 | Unavailable |

Luna and Sol prices are unavailable in the frozen table. The readout's known-price
subtotal zero is not free execution; the full monetary cost is **unavailable**.
Two samples per arm and one judge per task do not estimate reliability or remove
judge bias. Absence findings cover retained native metadata and actions, not
universal prevention of direct APIs or deliberate bypasses. No model-superiority,
ORC-benefit, campaign or quality–cost Pareto claim follows; later gates stay intact.
