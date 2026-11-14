# A small MLE-bench subset as a second long-horizon task family: feasibility

Scratch report, written 2026-11-13. Role: researcher. No model or provider call was made, no
dataset was downloaded, no Kaggle account or credential was created or used, nothing was
installed, and nothing in the repository was changed. Every figure carries one of three labels:
**read** (I read it in the named source today), **computed** (my arithmetic on files I read), or
**estimate** (my judgement, not a measurement). All URLs were read on 2026-11-13.

The brief was changed twice by the coordinator while I worked, and this report follows the
changed version: attempts may run up to the benchmark's standard 24 hours, in parallel; Haiku
spend of up to USD 200 per day is acceptable; a competition is included only if
`claude-haiku-5-5` succeeds on it 10 to 30 percent of the time (the band of roadmap owner
decision 14).

## 1. Conclusion

**A small subset fits this machine and grades offline, but the benchmark is a poor source of
tasks in a 10 to 30 percent band, and nothing published says where Haiku lands.**

- **It fits.** Thirteen candidate competitions take 13.4 GB by the benchmark's own size table
  (my estimate: at most about 27 GB on disk with the downloaded archives kept). Grading needs no
  network and no Kaggle access once a competition is prepared: the preparation script builds the
  held-out answers locally from the public training data, and the medal thresholds come from a
  leaderboard snapshot that is already in the repository.
- **The earlier survey's objections apply to the whole benchmark, not to single competitions.**
  Of the 158 GB lite split, one competition is 116 GB; the other 21 are 41.6 GB together, and 17
  of them are 4.8 GB together (computed from the README table). The 24-hour limit is a setting
  of the agent's start script, not of the harness. The closed leaderboard does not matter for an
  internal comparison.
- **The band is the problem.** Per competition, the medal outcome of a fixed agent is close to
  all-or-nothing. In the published grading reports, each of the three agents with 20 or more
  repeats per competition had only 1 to 4 of the 22 lite competitions at an observed medal rate
  of 10 to 30 percent (computed; section 6). So I expect 2 to 5 of my 13 candidates to screen
  into the band, fewer than the ten the planned comparison needs (estimate).
- **There is no published Haiku-class result under a plain agent CLI on the public benchmark.**
  The nearest evidence is a small model (Gemini 3 Flash) under purpose-built scaffolds (45 to 82
  percent medals on lite) and a strong model under a plain coding CLI (Codex with GPT-5.5: 68
  percent). Placement can only come from our own calibration run.
- **Scaffold structure matters more here than anywhere else surveyed.** With the model held
  fixed, published medal rates on lite range from 4 to 19 percent (GPT-4o, 2024) and from 45 to
  82 percent (Gemini 3 Flash, 2026) across scaffolds. That is the effect the roadmap wants to
  study, which is the argument for the family despite the band problem.
- **Money is not the binding limit; the single GPU and wall-clock are.** A plain CLI session
  will probably end by itself after one to four hours and cost USD 1 to 8 (estimate). A session
  kept working for the full 24 hours would cost about USD 10 to 60 (estimate from published
  figures). The machine can run about four attempts at once, only one of them on the GPU.

**Recommendation.** Run a small calibration tranche, but only as a supplement to the
Terminal-Bench family and only after that family's launcher exists, because it reuses the same
credential relay, network allowlist and guarded launcher. Start with a zero-spend oracle check on
one CPU-only competition. Do not plan on ten in-band competitions from this benchmark under the
medal definition; if the owner wants a full family from it, success has to be redefined as a
per-competition score threshold frozen from calibration data (section 7).

## 2. What the benchmark is, in one paragraph

MLE-bench is 75 past Kaggle competitions repackaged to run offline (plus 7 development
competitions). For each one the repository holds a description, a preparation script, a grading
function and a snapshot of the competition's private leaderboard. The agent gets the description
and the public data, trains a model, and writes one CSV of predictions. The grader scores the CSV
against held-out answers and compares the score with the human leaderboard: a score that would
have ranked in the bronze-medal zone or better counts as "any medal", which is the benchmark's
headline measure (read: paper §2.2, https://arxiv.org/abs/2410.07095). The published setting
gives an agent 24 hours, 36 virtual CPUs, 440 GB of memory and one 24 GB GPU per competition
(read: README, https://github.com/openai/mle-bench at commit `507f92e`, 2026-04-24). The
leaderboard stopped taking submissions on 2026-04-24 (read: README).

## 3. Per-competition facts

### 3.1 How grading works offline

- **The answer set is built locally.** `mlebench prepare -c <id>` downloads the competition's
  archive through the Kaggle API, then runs that competition's `prepare.py`, which splits the
  public training data into a new training set and a new test set and writes the test labels to
  a `private` directory (read: `mlebench/data.py`; for example
  `mlebench/competitions/spooky-author-identification/prepare.py` holds out 10 percent with a
  fixed seed). The new test set is 10 percent of the original training set unless stated
  otherwise (read: paper §2.1 and Table 8). Two lite competitions use the original test labels,
  which Kaggle released (read: paper Table 8).
- **Grading needs no network and no Kaggle access.** `mlebench grade-sample <csv> <id>` reads
  the CSV, the local answers and the leaderboard snapshot `leaderboard.csv` beside the
  competition's code (read: `mlebench/grade.py`, `mlebench/grade_helpers.py`). The only Kaggle
  calls are the download and an optional developer command that refreshes the snapshot (read:
  `mlebench/data.py`).
- **The leaderboard snapshots are Git LFS files.** A plain clone holds pointers only. I fetched
  them over the repository's public media address without Git LFS (40 MB with the grading
  reports; these are result files, not datasets).
- **Medal thresholds follow Kaggle's rule by number of teams** (read: `grade_helpers.py`, paper
  Table 1): bronze is the top 40 percent below 250 teams, rank 100 from 250 to 999 teams, and
  the top 10 percent from 1,000 teams.
- **Thresholds come from the original test set, scores from the new split.** The paper says the
  two are comparable "especially on average" (read: paper §2.1 and §6). Per competition they can
  be badly off: on two competitions every recent agent scores far past the gold threshold
  (computed from the grading reports; flagged in the table).
- **Disk.** The README gives one "dataset size" per competition and does not say whether it is
  the archive or the prepared data. `prepare` deletes the extracted raw files by default but
  keeps the downloaded archive (read: `mlebench/cli.py`, `mlebench/data.py`). My estimate is
  1.3 to 2 times the README figure on disk afterwards, and about 3 times at the peak.

### 3.2 Table: the lite split

Columns: **GB** is the README figure (read). **Metric** and direction are read from each
`config.yaml` and the grading reports. **Gold / bronze / median** are the thresholds in the
published grading reports (read). **Floor** is the score of the sample submission that the
repository's own test expects (read: `tests/constants.py`). **Teams** is the row count of the
leaderboard snapshot (computed). **GPU for a medal** is my estimate of whether a medal-level
score needs a GPU when training compute is held to about two hours. Modality is the README
category.

| Competition | GB | Modality | Metric, better | Gold / bronze / median | Floor | Teams | GPU for a medal (estimate) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| spooky-author-identification | 0.0019 | Text | Log loss, lower | 0.165 / 0.294 / 0.419 | 1.085 | 1,242 | No | Test about 1,958 rows |
| detecting-insults-in-social-commentary | 0.002 | Text | AUC, higher | 0.833 / 0.791 / 0.778 | 0.5 | 50 | No | **Rules can no longer be accepted on Kaggle** (read: Inspect Evals README); thresholds far below what agents score |
| random-acts-of-pizza | 0.003 | Text | AUC, higher | 0.979 / 0.692 / 0.600 | 0.5 | 462 | No | **A field leaks the label; the README says it should be dropped** |
| nomad2018-predict-transparent-conductors | 0.006 | Tabular | RMSLE, lower | 0.0559 / 0.0658 / 0.0699 | 0.212 | 879 | No | Test about 240 rows |
| text-normalization-challenge-english-language | 0.01 | Text, sequence | Accuracy, higher | 0.9972 / 0.99038 / 0.99037 | 0.933 | 261 | No | Bronze and median differ by 0.00001 |
| text-normalization-challenge-russian-language | 0.01 | Text, sequence | Accuracy, higher | 0.9901 / 0.97592 / 0.97591 | 0.875 | 163 | No | Same |
| aerial-cactus-identification | 0.025 | Image | AUC, higher | 1.0 / 1.0 / 0.9991 | 0.5 | 1,221 | Helpful (32-pixel images) | A medal needs a perfect score |
| leaf-classification | 0.036 | Tabular features and images | Log loss, lower | 0.0 / 0.0153 / 0.108 | 4.595 | 1,596 | No | Test about 99 rows |
| denoising-dirty-documents | 0.06 | Image to image | RMSE, lower | 0.0179 / 0.0452 / 0.0733 | 0.286 | 162 | Helpful | Submission is one row per pixel |
| jigsaw-toxic-comment-classification-challenge | 0.06 | Text | Column AUC, higher | 0.9874 / 0.9864 / 0.9808 | 0.5 | 4,539 | Yes | Original test labels; README: crowded leaderboard |
| the-icml-2013-whale-challenge-right-whale-redux | 0.29 | Audio | AUC, higher | 0.990 / 0.905 / 0.865 | 0.5 | 129 | No | **Rules can no longer be accepted on Kaggle** |
| tabular-playground-series-may-2022 | 0.57 | Tabular | AUC, higher | 0.99823 / 0.99818 / 0.9727 | 0.5 | 1,152 | Helpful | README: crowded leaderboard; no published medal |
| mlsp-2013-birds | 0.59 | Audio | AUC, higher | 0.935 / 0.874 / 0.866 | 0.5 | 81 | No | Test about 64 recordings |
| tabular-playground-series-dec-2021 | 0.7 | Tabular | Accuracy, higher | 0.9566 / 0.95658 / 0.9534 | 0.565 | 1,189 | No | README: crowded leaderboard |
| dog-breed-identification | 0.75 | Image | Log loss, lower | 0.0005 / 0.046 / 0.472 | 4.787 | 1,281 | Yes | README: test images come from a public labelled set; no published medal |
| plant-pathology-2020-fgvc7 | 0.8 | Image | Column AUC, higher | 0.978 / 0.974 / 0.949 | 0.5 | 1,318 | Yes | Test about 182 images |
| dogs-vs-cats-redux-kernels-edition | 0.85 | Image | Log loss, lower | 0.039 / 0.061 / 0.122 | 0.693 | 1,315 | Yes | Needs pretrained weights |
| new-york-city-taxi-fare-prediction | 5.7 | Tabular | RMSE, lower | 2.83 / 2.92 / 3.60 | 10.03 | 1,485 | No | 55 million rows; no published medal |
| histopathologic-cancer-detection | 7.76 | Image | AUC, higher | 0.9835 / 0.9738 / 0.9477 | 0.5 | 1,149 | Yes | |
| aptos2019-blindness-detection | 10.22 | Image | Quadratic kappa, higher | 0.9305 / 0.9145 / 0.8889 | 0.0 | 2,929 | Yes | Test about 366 images |
| ranzcr-clip-catheter-line-classification | 13.13 | Image | AUC, higher | 0.9736 / 0.9709 / 0.9675 | 0.5 | 1,547 | Yes | README: prepared sample submission lacks columns; no published medal |
| siim-isic-melanoma-classification | 116.16 | Image | AUC, higher | 0.9455 / 0.937 / 0.9128 | 0.5 | 3,308 | Yes | Too large here |

### 3.3 Table: other small competitions (medium split, at most 7 GB)

| Competition | GB | Modality | Metric, better | Gold / bronze / median | Floor | Teams | GPU for a medal (estimate) | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| us-patent-phrase-to-phrase-matching | 0.002 | Text | Pearson, higher | 0.870 / 0.862 / 0.851 | not a number | 1,889 | Yes (fine-tuned encoder) | Description states CC BY 4.0 |
| tweet-sentiment-extraction | 0.003 | Text, span | Jaccard, higher | 0.727 / 0.717 / 0.714 | 0.0 | 2,225 | Yes | Description states CC BY 4.0; bronze and median 0.003 apart |
| google-quest-challenge | 0.015 | Text | Column Spearman, higher | 0.423 / 0.375 / 0.357 | -0.010 | 1,572 | Yes | |
| chaii-hindi-and-tamil-question-answering | 0.032 | Text, question answering | Jaccard, higher | 0.763 / 0.737 / 0.728 | 0.0 | 943 | Yes (large multilingual encoder) | Test about 111 rows |
| learning-agency-lab-automated-essay-scoring-2 | 0.036 | Text | Quadratic kappa, higher | 0.836 / 0.835 / 0.828 | 0.013 | 2,708 | Yes for a medal; no for above median | |
| lmsys-chatbot-arena | 0.18 | Text | Log loss, lower | 0.984 / 1.003 / 1.052 | 1.099 | 1,688 | Yes, and 24 GB is tight | Winning solutions fine-tuned language models |
| statoil-iceberg-classifier-challenge | 0.30 | Image (radar) | Log loss, lower | 0.114 / 0.146 / 0.204 | 0.693 | 3,330 | Helpful | No published medal |
| tgs-salt-identification-challenge | 0.5 | Image segmentation | Mean precision, higher | 0.891 / 0.859 / 0.817 | 0.0 | 3,219 | Yes | No published medal |
| ventilator-pressure-prediction | 0.7 | Time series | Mean absolute error, lower | 0.112 / 0.136 / 0.164 | 17.65 | 2,605 | Yes | The config's grader name is a copy of another competition's |
| whale-categorization-playground | 0.73 | Image | MAP@5, higher | 0.562 / 0.405 / 0.328 | 0.115 | 529 | Yes | |
| petfinder-pawpularity-score | 1.04 | Image and tabular | RMSE, lower | 16.95 / 17.10 / 17.70 | 37.38 | 3,538 | Yes | |
| stanford-covid-vaccine | 2.68 | Sequence, tabular | Column RMSE, lower (the config's grader name says log loss) | 0.347 / 0.353 / 0.363 | 0.638 | 1,636 | Helpful | Recent agents score about 0.25, far past gold |
| kuzushiji-recognition | 4.51 | Image, detection | F1, higher | 0.903 / 0.658 / 0.599 | 0.0 | 294 | Yes | |
| cassava-leaf-disease-classification | 6.19 | Image | Accuracy, higher | 0.901 / 0.898 / 0.891 | 0.116 | 3,901 | Yes | |

Not listed because no published agent, or almost none, medals: champs-scalar-coupling (1.2 GB;
README: defect in the data), billion-word-imputation (1.7), AI4Code (2.2),
jigsaw-unintended-bias (2.4), uw-madison-gi-tract (2.5), facebook-recruiting-iii (3.2),
tensorflow-speech-recognition (3.8; README: preparation defect), nfl-player-contact (5.0). The
development split (spaceship-titanic and six others) has no published grading reports and no
size in the benchmark's table.

**Twenty-eight of the 75 competitions are at most 1.04 GB each and 8.3 GB together** (computed
from `experiments/competition_categories.csv`).

## 4. What Kaggle requires

- **An account and an API token.** The download uses the Kaggle API with a `kaggle.json` token
  in the user's home directory (read: README; `mlebench/utils.py`).
- **Rule acceptance per competition, by hand, in a browser.** A download for a competition whose
  rules the account has not accepted fails; the code then offers to open the rules page (read:
  `mlebench/data.py`). The Inspect Evals port tells users to join each competition with its
  "Late Submission" button and lists one rules link per competition (read:
  https://github.com/UKGovernmentBEIS/inspect_evals, `src/inspect_evals/mle_bench/README.md`).
- **Two lite competitions cannot be prepared any more.** The same README says the rules of
  detecting-insults-in-social-commentary and the-icml-2013-whale-challenge-right-whale-redux
  "can no longer be accepted on Kaggle", so lite is 20 runnable competitions.
- **Phone verification is probably needed.** Forum threads report that an account without a
  verified phone number cannot accept rules or download (read through a web search; anecdotal,
  not an official page).
- **I could not read any rules page or the terms of use.** Kaggle's pages returned only a title
  to my fetches. So I cannot say what each competition's rules allow for research use or
  redistribution. From background knowledge, not verified today: Kaggle's usual rules restrict
  competition data to the competition, the site's forums and non-commercial academic research,
  and forbid passing the data to people who have not accepted the rules; hosts can write
  different terms.
- **What I could read is the licence text inside three descriptions in the repository**:
  tweet-sentiment-extraction ("creative commons attribution 4.0"), us-patent-phrase-to-phrase-
  matching (CC BY 4.0) and jigsaw-toxic-comment-classification-challenge (CC0, with the comment
  text under Wikipedia's CC-SA-3.0). Eighteen of the 82 descriptions mention a licence term at
  all (computed). These three are the most permissive on the evidence available. The paper says
  only that the selection excluded competitions whose licence "restrict[s] its inclusion in our
  benchmark" (read: paper appendix A.1); it has no per-competition licence table.
- **Redistribution.** The benchmark ships no data; every user downloads under their own account.
  Prepared data and anything derived from it should stay on this machine and out of the
  repository, as the Terminal-Bench plan already rules for task files.

Needs the owner's personal action: the account, the phone verification, the token, clicking
through each competition's rules, and reading those rules for the use intended here.

## 5. The harness

### 5.1 How the benchmark runs an agent (read: `run_agent.py`, `agents/run.py`, `environment/`, `agents/`)

- **Images.** A base image `mlebench-env` (Ubuntu 20.04, Miniconda, a Python 3.11 environment
  with about 90 pinned packages including PyTorch 2.2.0 and TensorFlow 2.17) and one image per
  agent built on top of it. The Inspect Evals port reports about half an hour and about 25 GB
  for its image (read: its README). A build argument leaves the heavy packages out.
- **Entry point.** The container starts as root and runs a small web server on port 5000 that
  checks a submission's format. The harness then runs the agent's `start.sh` as user `nonroot`.
- **Data.** The public data is bind-mounted read-only at `/home/data`. **The private answers are
  bind-mounted into the same container** under `/private`, a directory only root can read,
  because the format checker runs the real grader against them. Outputs are copied out of
  `/home/submission`, `/home/logs` and `/home/code` when the agent's script returns.
- **Limits.** The time limit is not enforced by the harness: it is an environment variable
  (`TIME_LIMIT_SECS: 86400`) that the agent's own `start.sh` passes to `timeout`. Lowering it is
  a one-line change in the agent's `config.yaml`. CPU, memory and GPU come from a JSON file; the
  shipped default is 4 CPUs, 4 GB of shared memory, no memory limit and the `sysbox-runc`
  runtime, with `"gpus": -1` to pass all GPUs.
- **Credentials.** Agent API keys are environment variables of the agent's container, filled
  from the host environment.
- **Docker is assumed.** `run_agent.py` uses the Docker Python client and the documentation
  asks for Docker, Sysbox and the NVIDIA Container Toolkit.

### 5.2 Fit to this machine and to decisions D1 to D7 of the Terminal-Bench plan

| Constraint (plan decision) | Upstream harness | What it would take here |
| --- | --- | --- |
| Rootless Podman, no Docker daemon | Not supported as written. It might run against Podman's Docker-compatible socket with the runtime line removed; untested | Do not use `run_agent.py`. Wrap each competition as a Harbor task (below) |
| Withheld references (D2) | **Violated**: the answers sit in the agent's container behind a file permission | Keep the answers in the verifier image only; replace the format checker with one that compares against the sample submission |
| Oracle check (D1) | The repository's own tests do it: the answers file graded as a submission earns a gold medal, and the sample submission earns a listed floor score (read: `tests/integration/test_eval.py`, `tests/constants.py`) | Oracle agent copies the answers file from the task's `solution/` directory; the do-nothing agent leaves no submission and scores zero. **This checks the grader, not that the task is solvable**: no reference solution that trains a model exists. Solvability rests on the published medal rates |
| Fixed network policy (D3) | None; the instructions only forbid looking at solutions | The allowlist of the Terminal-Bench kit, plus a decision about pretrained weights (below) |
| No credential in a container (D4) | Violated: the key is a container environment variable | The relay and host-side passthrough of the Terminal-Bench kit, unchanged |
| Guarded launcher (D4, D7) | None | The Terminal-Bench launcher, with a task list and caps for this family |
| GPU in a container | Docker device request | **Not available today**: this machine has no NVIDIA Container Toolkit and no device specification for Podman (measured: no `nvidia-ctk`, no `/etc/cdi`). Harbor's current source wires GPUs only for the Docker engine (read: `src/harbor/environments/docker/docker.py` on the main branch), so a Podman run needs an extra compose file that names the device |

- **No maintained Harbor adapter exists.** Harbor's `adapters/` directory holds 85 adapters and
  none for MLE-bench (read: GitHub API listing of https://github.com/harbor-framework/harbor).
  The older Terminal-Bench registry had a dataset `mlebench-lite`; its page now redirects to a
  Harbor Hub task page that showed no content to my fetch, so I could not establish its state.
- **The maintained port is Inspect Evals** (`mle_bench`, `mle_bench_lite`; last changed
  2026-09-14). It builds its own Docker image, takes CPU, memory and GPU overrides, checks rule
  acceptance up front, and scores three booleans: valid submission, above median, any medal
  (read: its README). It assumes Docker and runs the model through Inspect, not through an
  agent CLI.
- **Running Claude Code as the agent** is therefore the same construction as the Terminal-Bench
  plan: Harbor installs the pinned CLI inside the task container and runs one non-interactive
  session; the key stays in the host passthrough behind the relay. What is new for this family
  is the task wrapper: a Dockerfile (a slim image with the data baked in or mounted), the
  benchmark's instructions and the competition description as the instruction, a verifier that
  runs `mlebench grade-sample` and writes the reward, and a task file with the limits.
- **Pretrained weights are a network-policy decision.** Medal-level scores on the image and
  text competitions depend on downloading pretrained models. The two strongest published
  set-ups allow the network "solely for fetching third-party packages and model checkpoints"
  (read: https://arxiv.org/abs/2507.02554 §3.4; https://arxiv.org/abs/2608.14354). A model hub
  on the allowlist also serves datasets, and the README records that the dog-breed test images
  come from a public labelled set. The alternative is a fixed set of weights placed in the
  image, which keeps the allowlist as it is and costs a few GB.

## 6. Published evidence

### 6.1 Small models, plain agent loops and scaffold structure

All rows are "any medal" on the lite split, mean of three seeds unless stated, 24 hours.

| Agent | Model | Lite medal rate | Source |
| --- | --- | --- | --- |
| MLAB (plain tool loop) | GPT-4o (2024) | 4.2% | read: paper Table 9 |
| OpenHands (plain coding agent) | GPT-4o | 11.5% | read: paper Table 9 |
| AIDE (tree search) | GPT-4o, 36 seeds | 19.0% | read: paper Table 9 |
| AIDE | Claude 3.5 Sonnet | 19.4% | read: paper Table 9 |
| AIDE | o1-preview, 16 seeds | 34.3% | read: paper Table 9 |
| Earlier best on lite, as arXiv 2507.02554 cites it | not stated in the abstract | 39.6% | read: arXiv 2507.02554 abstract |
| Better operators with a search policy | o3 | 47.7% | read: same, abstract and full-benchmark appendix |
| The same with high reasoning effort and better infrastructure (AIRA-dojo, greedy, 20 seeds) | o3 | 55.0% | read: same appendix; README leaderboard |
| AIDE | GLM-5 | 34.9% | read: arXiv 2604.13018 Table 2 |
| AIDE | **Gemini 3 Flash** | 45.5% | read: same |
| LoongFlow (evolutionary) | **Gemini 3 Flash** | 77.3% | read: same; the README notes it used test-set feedback |
| AiScientist (staged, multi-role, shared files) | **Gemini 3 Flash** | 81.8% | read: same |
| AiScientist without its shared-file state | GLM-5 | 31.8 points lower | read: same §4.5 |
| **Codex CLI (plain coding harness)** | GPT-5.5, effort xhigh | 68.2% (valid 100%, above median 81.8%) | read: same Table 2 |
| ScienceFlow | DeepSeek V4 Flash preview | 80.3% | read: arXiv 2608.14354 Table 1 |
| Best on the README leaderboard | Gemini 3 Pro | 80.3% | read: README |

- **No Haiku row exists anywhere I looked**, and no Claude Code row. The Codex row is the only
  published plain-CLI result, with a much stronger model.
- **Scaffold effect with the model fixed:** 4 to 19 percent for GPT-4o across three scaffolds;
  45 to 82 percent for Gemini 3 Flash across three; 35 to 82 percent for GLM-5. The paper's
  explanation for the 2024 gap is that the plain agents "tend to end their runs early, sometimes
  within the first few minutes", while the tree search keeps prompting until the time is used
  (read: paper §3.1).
- **A plain CLI plateaus early.** "AIDE and Codex improve rapidly early in the run, with Codex
  especially strong in the first few hours", and the staged system overtakes later (read:
  arXiv 2604.13018 §4.4).
- **OpenAI's own system card now uses a different, private variant** ("MLE-Bench Revised": 72
  problems, percentile score against a reference distribution, three leaderboard submissions
  allowed; read: https://deploymentsafety.openai.com/gpt-5-6, section 9.1.3.5). An aggregator
  lists a small model there, GPT-5.6 Luna, at about 42 to 62 percent by effort and USD 0.3 to 7
  per task (read: https://benchmarklist.com/benchmarks/mle_bench_revised/; secondary, and the
  card's text did not show these numbers). It is not comparable with the public benchmark.

### 6.2 Run-to-run variance

- **The benchmark's advice:** at least three seeds, report the mean and one standard error;
  "agents/LLMs can be quite high-variance" (read: README).
- **A later paper says three is too few:** "a minimum of 10 seeds per task", "20 seeds
  preferred", stratified bootstrap intervals, and a small subset with many seeds over the full
  set with few (read: arXiv 2507.02554 appendix I).
- **Repeating helps a lot:** the medal rate of o1-preview rose from 16.9 percent with one
  attempt to 34.1 percent with the best of eight (read: paper §1 and §3.2).
- **Validation misleads the agent:** choosing the final solution by its true test score instead
  of its validation score would raise the medal rate by 9 to 13 points (read: arXiv 2507.02554).
- **Per competition, outcomes are close to all-or-nothing** (computed from the grading reports
  in the repository's `runs/` directory; a competition counts when the agent has at least ten
  runs on it):

| Agent, repeats per competition | Lite competitions at 0% | at 10–30% | above 90% | Of 44 competitions up to 14 GB: at 10–30% |
| --- | --- | --- | --- | --- |
| GPT-4o with AIDE, about 38 | 11 of 22 | 1 | 0 | 2 |
| o1-preview with AIDE, about 21 | 5 of 22 | 4 | 1 | 4 |
| o3 with AIRA-dojo, 20 | 5 of 22 | 1 | 5 | 4 |
| Eleven 2025 agents pooled, about 35 | not computed for lite | | | 5 |
| Ten 2026 agents pooled, about 30 | not computed for lite | | | 3 |

- **The raw score is noisy against the medal margin.** For o3 with AIRA-dojo (20 runs), the
  spread of the score between runs, divided by the distance from the bronze threshold to the
  median threshold, is 0.2 on spooky-author and jigsaw-toxic, 0.3 on petfinder, 0.8 on
  us-patent, 1.3 on leaf-classification, 2.3 on the essay-scoring competition, 2.7 on
  tweet-sentiment and 8 on nomad2018 (computed; spread taken from the interquartile range). On
  the last four, one attempt's medal is largely luck of the draw.
- **Small test sets add grading noise of their own:** about 64 recordings (mlsp-2013-birds), 99
  rows (leaf-classification), 111 (chaii), 240 (nomad2018), 366 (aptos2019) (computed from paper
  Table 8).

### 6.3 Cost and wall-clock per attempt

- **Wall-clock is 24 hours by construction** for every leaderboard row except six at 12 hours
  and one at 36 (read: README).
- **Tokens, tree-search scaffold:** o1-preview with AIDE used 127.5 million input and 15.0
  million output tokens for one seed of 75 competitions (read: paper §6), which is 1.7 million
  input and 0.2 million output per 24-hour attempt (computed). At the repository's frozen Haiku
  prices (USD 0.10 and 0.50 per million; five times that above 100,000 prompt tokens; read:
  `orchestrator/providers/price_table.json`) that is USD 0.27 to 1.35 per attempt (computed).
- **Dollars, staged small-model agent over 24 hours:** USD 15.67 per task with Gemini 3 Flash
  and USD 27.44 for a simpler iterative agent, on PaperBench, not on MLE-bench (read:
  arXiv 2604.13018 §4.2).
- **Dollars, Haiku under Claude Code:** USD 2.89 and 68 minutes per Terminal-Bench trial at
  effort `max`, and USD 0.68 at `medium` (read: the earlier survey report in this repository).
  That is about USD 2.55 per hour of continuous work at `max` (computed).
- **No MLE-bench paper I read reports dollars per attempt.**

### 6.4 Contamination

- **Everything is public and old.** The competitions ran from 2012 to 2024, their winning
  write-ups and notebooks are public, and all of it predates the bound model's training cutoff.
  This is the opposite of the Terminal-Bench tasks, which were published after it.
- **The paper found no measurable effect for GPT-4o:** no correlation between the model's
  familiarity with a competition's winning write-ups and its score, and 8.4 percent medals with
  rewritten descriptions against 8.5 percent with the originals (read: paper §4). It adds that
  this "make[s] no guarantees about future models".
- **Mitigations in the repository:** an obfuscated description for every competition
  (`description_obfuscated.md`); a plagiarism check of the agent's code against the top 50
  public notebooks at a 60 percent similarity threshold, which needs Node.js; and a rule-breaking
  check of the logs that calls `gpt-4o-mini`, which is a provider call outside the models this
  project may use (read: `extras/README.md`, paper §2.3.1).
- **Known leaks and defects** are listed in the README: random-acts-of-pizza (label leak),
  dog-breed-identification (public labelled source), three competitions with crowded
  leaderboards (two tabular playgrounds and jigsaw-toxic), and several broken preparations.

## 7. Turning a continuous score into a success rate

The owner's condition needs a per-attempt success, so a definition must be chosen and frozen.

| Definition | Who uses it | Rates published per competition? | Fit to a 10–30% band |
| --- | --- | --- | --- |
| **Any medal** (score at or past the bronze threshold) | The benchmark's headline; every paper above; Inspect | Yes, for every agent in `runs/` | The standard. Bimodal per competition (section 6.2) |
| **Above the leaderboard median** | Reported beside the headline by the benchmark, Inspect and arXiv 2604.13018 | Yes, same files | Easier bar; moves the hard competitions toward the band and the easy ones out of it |
| **Valid submission** | Reported by the same sources | Yes | Useless for a current model: 100 percent for most 2026 agents |
| **Leaderboard percentile** of the score | Not reported by the benchmark; computable offline from the snapshot. OpenAI's private variant scores a percentile against a reference distribution | No | A graded outcome comparable across competitions |
| **Normalized score** between the sample submission and the gold threshold | The paper, for one figure only (read: Figure 5) | No | Graded, but unbounded on competitions whose thresholds are off |
| **A per-competition score threshold frozen from calibration runs** | Nobody | No | The only definition that can place most competitions in the band by construction |

- **What the benchmark recommends:** any medal, at least three seeds, mean and standard error,
  and a breakdown by complexity split (read: README). It says raw scores are useful per
  competition but "hard to aggregate" (read: paper §2.2).
- **My recommendation:** keep **any medal** as the primary success, because it is predeclared by
  someone else and comparable with every published number. Record the leaderboard percentile and
  above-median for every attempt as secondary graded outcomes, as the Terminal-Bench plan records
  sub-test counts. Decide only after calibration whether too few competitions are in the band; a
  frozen per-competition threshold is then the fallback, and it must be fixed from calibration
  attempts and applied to fresh ones.
- **The continuous score makes screening cheaper than a pass-or-fail verifier.** Three attempts
  that all land many margins below the bronze threshold, or all far above it, place a
  competition outside the band with more confidence than three failures or three passes would.

### Published per-competition rates under the three published definitions

Cells are successes over runs. "4o" is GPT-4o with AIDE, "o1p" is o1-preview with AIDE, "OH" is
GPT-4o with OpenHands (the nearest thing to a plain agent loop, four runs only), "o3" is o3 with
AIRA-dojo, "2025" pools eleven agents of 2025 and "2026" ten agents of 2026 (computed from the
grading reports, joined to experiments by `runs/run_group_experiments.csv`).

| Competition | Medal: 4o | o1p | OH | o3 | 2025 | 2026 | Above median: 4o | o1p | o3 | Valid: 4o |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| tweet-sentiment-extraction | 0/39 | 1/21 | 0/4 | 7/20 | 10/35 | 27/30 | 0/39 | 5/21 | 10/20 | 35/39 |
| petfinder-pawpularity-score | 0/39 | 0/20 | 0/4 | 7/20 | 5/35 | 26/30 | 5/39 | 2/20 | 18/20 | 33/39 |
| learning-agency-lab-automated-essay-scoring-2 | 0/38 | 0/20 | 0/4 | 5/20 | 12/33 | 29/30 | 0/38 | 1/20 | 10/20 | 34/38 |
| us-patent-phrase-to-phrase-matching | 0/38 | 1/21 | 0/4 | 11/20 | 8/35 | 30/30 | 0/38 | 8/21 | 16/20 | 35/38 |
| cassava-leaf-disease-classification | 0/39 | 1/21 | 0/4 | 3/20 | 8/35 | 25/30 | 0/39 | 3/21 | 9/20 | 26/39 |
| whale-categorization-playground | 1/38 | 0/21 | 0/4 | 7/20 | 15/35 | 30/30 | 2/38 | 4/21 | 15/20 | 34/38 |
| leaf-classification | 0/38 | 2/21 | 0/4 | 9/20 | 14/35 | 30/30 | 2/38 | 4/21 | 14/20 | 34/38 |
| jigsaw-toxic-comment-classification-challenge | 0/39 | 4/21 | 0/4 | 6/20 | 20/33 | 28/30 | 12/39 | 18/21 | 20/20 | 34/39 |
| kuzushiji-recognition | 0/39 | 1/21 | 0/4 | 3/20 | 14/35 | 28/30 | 0/39 | 9/21 | 5/20 | 26/39 |
| text-normalization-challenge-russian-language | 0/39 | 3/21 | 0/4 | 13/20 | 11/35 | 24/30 | 0/39 | 3/21 | 13/20 | 12/39 |
| mlsp-2013-birds | 1/38 | 2/21 | 0/4 | 14/20 | 20/35 | 30/30 | 1/38 | 2/21 | 14/20 | 4/38 |
| lmsys-chatbot-arena | 0/39 | 0/21 | 0/4 | 0/20 | 5/32 | 28/30 | 5/39 | 6/21 | 16/20 | 24/39 |
| chaii-hindi-and-tamil-question-answering | 0/38 | 0/21 | 0/4 | 1/20 | 3/35 | 19/30 | 0/38 | 0/21 | 3/20 | 34/38 |
| text-normalization-challenge-english-language | 15/38 | 15/20 | 0/4 | 10/20 | 19/35 | 29/30 | 15/38 | 15/20 | 10/20 | 31/38 |
| nomad2018-predict-transparent-conductors | 24/39 | 16/20 | 2/4 | 15/20 | 34/35 | 30/30 | 25/39 | 16/20 | 15/20 | 34/39 |
| spooky-author-identification | 1/38 | 5/20 | 0/4 | 17/20 | 30/35 | 30/30 | 9/38 | 18/20 | 20/20 | 34/38 |
| aptos2019-blindness-detection | 0/38 | 7/21 | 0/4 | 10/20 | 23/35 | 30/30 | 11/38 | 21/21 | 15/20 | 35/38 |
| google-quest-challenge | 7/39 | 14/21 | 0/4 | 19/20 | 35/35 | 30/30 | 16/39 | 20/21 | 19/20 | 34/39 |
| dog-breed-identification | 0/37 | 0/21 | 0/4 | 0/20 | 0/35 | 0/23 | 3/37 | 17/21 | 16/20 | 29/37 |
| statoil-iceberg-classifier-challenge | 0/39 | 0/19 | 0/4 | 0/20 | 0/32 | 0/21 | 1/39 | 5/19 | 14/20 | 31/39 |

## 8. Candidate subset

### 8.1 Where a Haiku-class model would land: the evidence, plainly

**There is none that is direct.** No per-competition result exists for Haiku 5.5, for any Haiku,
for Claude Code, or for any small 2026 model in a plain agent loop. What exists per competition
is in the table above: older models under a tree search, and pooled recent agents under heavy
scaffolds.

My working assumption, which is an estimate and may be wrong in either direction: a direct
Claude Code session with Haiku 5.5 lands between o1-preview with AIDE (34 percent on lite) and
o3 with AIRA-dojo (55 percent). Two things pull against each other. The model is stronger at
programming than either. But it has no search scaffold, it will probably stop early, and the
one published plain-CLI result needed a much stronger model to reach 68 percent. Under that
assumption a competition is likely in the band when the weaker anchor medals rarely and the
stronger anchor medals on a minority of runs.

### 8.2 The subset, ranked by how likely it is to fall in the band (any-medal definition)

Sizes are README figures (read). "GPU" says whether a medal realistically needs one (estimate).
"Time" is my estimate of the training compute a medal-level solution needs on this machine's
GPU or CPUs, which is the part of an attempt the model cannot shorten.

| Rank | Competition | GB | Modality | GPU | Time (estimate) | Published medal rates: o1p / o3 / 2025 pool | Likelihood of 10–30% for Haiku (estimate) and why |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | tweet-sentiment-extraction | 0.003 | Text | Yes | 0.5–2 h | 5% / 35% / 29% | **Highest.** Needs a fine-tuned span model and careful post-processing; bronze and median are 0.003 apart, so outcomes are noisy |
| 2 | petfinder-pawpularity-score | 1.04 | Image and tabular | Yes | 1–3 h | 0% / 35% / 14% | **High.** Stable score, small margin over the median; medal needs a good pretrained backbone |
| 3 | learning-agency-lab-automated-essay-scoring-2 | 0.036 | Text | Yes | 1–3 h | 0% / 25% / 36% | **High.** Medal zone is 0.001 wide in kappa; noisy |
| 4 | us-patent-phrase-to-phrase-matching | 0.002 | Text | Yes | 0.5–2 h | 5% / 55% / 23% | **Medium to high.** One known recipe (a fine-tuned encoder with context); may sit above the band if the model knows it |
| 5 | cassava-leaf-disease-classification | 6.19 | Image | Yes | 2–5 h | 5% / 15% / 23% | **Medium**, low edge. Medal zone is 0.4 points of accuracy |
| 6 | whale-categorization-playground | 0.73 | Image | Yes | 1–3 h | 0% / 35% / 43% | **Medium.** Few images per class; needs a metric-learning idea |
| 7 | leaf-classification | 0.036 | Tabular features | **No** | minutes | 10% / 45% / 40% | **Medium.** CPU-only; 99 test rows make each attempt's outcome partly chance |
| 8 | jigsaw-toxic-comment-classification-challenge | 0.06 | Text | Yes | 1–3 h | 19% / 30% / 61% | **Medium.** Crowded leaderboard; above the median is near-certain, a medal is not |
| 9 | kuzushiji-recognition | 4.51 | Image, detection | Yes | 3–8 h | 5% / 15% / 40% | **Medium**, low edge. A two-stage detection pipeline; long |
| 10 | text-normalization-challenge-russian-language | 0.01 | Text | **No** | 0.2–1 h | 14% / 65% / 31% | **Medium.** CPU-only; all-or-nothing on one idea (memorize by token class) |
| 11 | mlsp-2013-birds | 0.59 | Audio | **No** | minutes | 10% / 70% / 57% | **Medium to low**; may be above. CPU-only; 64 test recordings; an odd file layout that older agents failed to parse |
| 12 | lmsys-chatbot-arena | 0.18 | Text | Yes | 6–20 h | 0% / 0% / 16% | **Low**: probably at the floor. A medal needed a fine-tuned language model; 24 GB is tight |
| 13 | chaii-hindi-and-tamil-question-answering | 0.032 | Text | Yes | 2–6 h | 0% / 5% / 9% | **Low**: probably at the floor. Kept as a lower anchor |

**Total: 13.4 GB** (computed), about 27 GB on disk at most with archives kept (estimate).

**The condition "at least half need no GPU" conflicts with "middling".** Only three of the
thirteen are CPU-only, because the middling competitions are the ones that need a fine-tuned
pretrained model. The CPU-only competitions of the pool are mostly either easy or decided by
noise. To reach half, add these three CPU-only competitions (0.02 GB together), which I expect
to be **above** the band and which then serve as upper anchors:

| Competition | GB | GPU | Published medal rates: 4o / o1p / o3 | Expectation |
| --- | --- | --- | --- | --- |
| text-normalization-challenge-english-language | 0.01 | No | 39% / 75% / 50% | Above the band or noise-bound: every agent since 2024 sits between 39 and 75 percent |
| nomad2018-predict-transparent-conductors | 0.006 | No | 62% / 80% / 75% | Above the band; 240 test rows cap it near 75 percent |
| spooky-author-identification | 0.002 | No | 3% / 25% / 85% | Probably above the band |

**Probably too easy** (near-certain medal for a current model that produces a sound pipeline):
google-quest-challenge, aerial-cactus-identification, denoising-dirty-documents,
dogs-vs-cats-redux, plant-pathology-2020, histopathologic-cancer-detection,
stanford-covid-vaccine, tabular-playground-series-dec-2021, and probably aptos2019.

**Probably too hard** (no published medal at all, or almost none): dog-breed-identification,
tabular-playground-series-may-2022, statoil-iceberg, tgs-salt, ventilator-pressure,
new-york-city-taxi, ranzcr-clip, champs-scalar-coupling, AI4Code, jigsaw-unintended-bias,
uw-madison-gi-tract. Under the above-median definition several of these move into play
(dog-breed, statoil, lmsys, tabular-may-2022).

**Excluded whatever their rate:** random-acts-of-pizza (label leak), detecting-insults and
the-icml-2013-whale-challenge (rules cannot be accepted), siim-isic-melanoma (116 GB).

**What 60 GB would add:** aptos2019-blindness-detection (10.2 GB; probably above the band) and
freesound-audio-tagging-2019 (26.2 GB; audio; o3 6 of 20, the 2025 pool 8 of 33), which is the
one clearly band-likely competition between 14 and 36 GB. The other option at that size,
h-and-m-personalized-fashion-recommendations (34.6 GB; o3 2 of 20), is tabular but needs far
more memory than an attempt can have here. So 60 GB buys one more likely candidate.

### 8.3 What cannot be known without a calibration run

- The medal rate of Haiku 5.5 on any competition, at any effort level, with or without a GPU.
- How long a direct session keeps working before it stops by itself, and so the real time and
  cost per attempt.
- Whether the model recognizes the competitions and reproduces a known solution.
- How much the network policy (pretrained weights reachable or not) moves the rates.
- Whether the thresholds on the new split are fair for each candidate.

## 9. The 24-hour limit on this machine, parallelism and cost

### 9.1 Is the standard limit usable as is?

**Yes as a ceiling, no as a duration.** The limit is a variable in the agent's start script, so
24 hours can be set without touching the benchmark. But the published 24-hour results come from
scaffolds that keep prompting the model until the time runs out. A single non-interactive CLI
session ends when the model decides it is finished. On Terminal-Bench the Haiku sessions lasted
68 minutes on average and 471 minutes at most, against a limit of 8 hours (read: the earlier
survey). I expect one to four hours here (estimate). So "a 24-hour attempt" means one of three
different things, and the comparison must say which:

| Shape of an attempt | Expected length | Expected cost with Haiku 5.5 (estimate) | Basis |
| --- | --- | --- | --- |
| One direct session that stops by itself, limit 24 h | 1–4 h | USD 1–8 | Terminal-Bench: USD 0.68 at `medium`, USD 2.89 at `max`, per trial of about an hour; training waits add turns |
| A direct session re-prompted until 24 h have passed | 24 h | USD 10–60, central about 25 | USD 2.55 per working hour at `max` with the agent busy 30 to 60 percent of the time; USD 15.67 to 27.44 per 24-hour task for a small model in arXiv 2604.13018 |
| A staged workflow using the 24 h | up to 24 h | USD 10–60 | Same |
| For contrast: a tree search with short prompts | 24 h | USD 0.3–1.4 | The paper's token counts at Haiku prices |

- **Tokens.** USD 200 per day buys 25 to 200 direct sessions that stop by themselves, or 3 to 20
  sessions that work for 24 hours (central estimate about 8).
- **Long sessions cost more per token.** Haiku 5.5 is billed at five times its ordinary rates
  above 100,000 prompt tokens (read: the repository's price table), and a long session spends
  most of its life above that.

### 9.2 What one attempt needs, and how many fit

Per attempt (estimate; the published setting is far larger, but the shipped default container
file itself gives 4 CPUs):

| | CPU-only attempt | GPU attempt |
| --- | --- | --- |
| CPUs | 6 | 6–8 (data loading) |
| Memory | 16 GB | 24–32 GB |
| Shared memory | 4 GB | 4–8 GB |
| Scratch disk | 5–10 GB | 15–30 GB (checkpoints, pretrained weights) |
| GPU | none | the whole RTX 3090 |

Measured on this machine while writing: load average 43 to 67 on 32 cores; 50 GB of the 125 GB
memory available; the GPU idle (481 MiB of 24 GB in use); 76 GB free on `/home`, where Podman
keeps its images, and 55 GB free on `/`.

- **GPU attempts: one at a time.** Containers cannot cap GPU memory per attempt, so two
  attempts sharing the card would interfere and break "same limits for every attempt". Sharing
  by two is possible with the vendor's multi-process service and its per-client memory limit,
  at the cost of extra engineering and half the memory each (not tried).
- **CPU-only attempts: three beside a GPU attempt, or four alone**, and only in a quiet window
  like the one the Terminal-Bench plan asks for (24 CPUs reserved, load at or below 24). At
  today's load and free memory, two.
- **Disk is the second limit.** An image with the benchmark's full package set is about 25 GB;
  a slimmer one about 8 to 12 GB (estimate). Image, 27 GB of data and four scratch areas come to
  roughly 65 to 110 GB against 76 GB free on `/home`. The data should go on `/`.

**Which limit binds.** At the full 24 hours, four attempts finish per day and cost USD 40 to
240, so the cores and the GPU bind before the USD 200, except at the top of the cost range. For
the GPU competitions, the single GPU binds outright: one finished attempt per day. If sessions
stop by themselves, about 8 to 12 GPU attempts and 25 to 40 CPU-only attempts finish per day
(estimate), the spend is USD 40 to 320 a day, and tokens and the GPU bind together.

### 9.3 A shorter limit, as the secondary option

- **Validity of the thresholds.** The thresholds are fixed score bars from human leaderboards;
  humans had weeks. They do not depend on the agent's limit, so a medal under a 4-hour limit is
  the same achievement. What is lost is comparability with published 24-hour rates, and the
  rate itself falls for scaffolds that use the time.
- **What is published.** GPT-4o with AIDE "achieves a significant number of medals in the first
  couple hours" and then gains slowly: 8.7 percent at 24 hours, 11.8 percent at 100 (read: paper
  §3.4). Differences between search methods "emerg[e] only after 15 hours" (read:
  arXiv 2507.02554 appendix C). The README has six rows at 12 hours; the one matched pair
  scores 74.2 percent on lite at 12 hours against 80.3 at 24 (read: README, PiEvolve). I found
  no published run of the public benchmark at 2 to 4 hours. One paper runs four Kaggle tabular
  tasks at 4, 10 and 20 minutes and reports that scores rise with the budget (read:
  https://arxiv.org/abs/2603.05764). Inspect's default agent is capped at 30 messages, not by
  time (read: its README).
- **For this project** a limit of 4 to 6 hours would triple the daily throughput of GPU
  attempts and would probably not shorten a direct session that stops by itself anyway. It
  would cap a staged workflow, which is the arm most likely to use the time. That is an
  argument for fixing the limit by what the staged arm needs, measured in its smoke.

## 10. Sizing the calibration

The Terminal-Bench plan places each task with five attempts at each of three effort levels,
pools the fifteen, and labels a task "screened in" at 1 to 5 successes of 15. It notes that a
true rate cannot be shown to lie inside 10 to 30 percent without about 90 attempts per task.
The same arithmetic applies here.

| Design | Attempts | Days, each attempt held to 24 h | Days, sessions stop by themselves (estimate: 2.5 h) | Dollars (estimate) |
| --- | --- | --- | --- | --- |
| **Screen:** 13 candidates, 3 attempts, one effort level | 39 (30 on the GPU) | 30 | 3–4 | 40–310 |
| **One effort level:** 13 candidates, 5 attempts | 65 (50 on the GPU) | 50 | 5–6 | 65–520 |
| **As the Terminal-Bench ladder:** 13 candidates, 5 attempts, 3 effort levels | 195 (150 on the GPU) | 150 | 15–17 | 195–1,560 |
| The last, on the six CPU-only competitions of section 8.2 only | 90 | 23 (four at a time) | 2–3 | 90–720 |

- Days are set by the single GPU: the ten GPU candidates run one at a time. Dollars use USD 1
  to 8 per attempt; an attempt kept working for 24 hours would cost USD 10 to 60 instead.
- **Daily spend stays under USD 200 in every row** at the central estimate (about USD 3 per
  attempt and at most 40 attempts a day). The ladder's total passes the coordinator's
  delegation thresholds, so it needs the owner.
- **Expected yield (estimate): 2 to 5 of the 13 screened in**, by the bimodality of section 6.2.
- **Suggested order:** the screen first. Use the continuous score to drop competitions whose
  three attempts all land far from the bronze threshold on the same side, then spend the fuller
  design only on the rest.

## 11. Recommendation

**Worth a small calibration tranche, as a supplement and not as a like-for-like second family.**
The reasons for: single competitions are small, grade offline and deterministically, and this
is the benchmark where published work shows the largest effect of workflow structure with the
model held fixed, including for a small model. The reasons against relying on it: per
competition the medal outcome is nearly all-or-nothing, so few competitions will sit at 10 to 30
percent; the competitions and their solutions are in the model's training data; the thresholds
are approximate on the rebuilt test sets; and the one GPU makes real 24-hour attempts take
months. I would do the zero-spend oracle check on one CPU-only competition now, run the
39-attempt screen once the Terminal-Bench launcher exists, and decide from its scores whether
the family is two to five medal-defined tasks added to the Terminal-Bench set or a larger set
under a frozen per-competition threshold.

## 12. What only the owner can do

1. **Kaggle:** create or use a personal account, verify a phone number if asked, create an API
   token, and accept the rules of each chosen competition in a browser (16 competitions for the
   full candidate list). The token stays on the host and is used only for the download.
2. **Read the rules** of each chosen competition for research use and redistribution, since I
   could not read them, and decide whether the use is acceptable.
3. **One root action for GPU competitions:** install the NVIDIA Container Toolkit and generate
   the device specification that lets rootless Podman pass the GPU to a container. Without it
   only the CPU-only competitions can run.
4. **Approve the line and its spend.** This is a new experiment line that is not on the
   roadmap, which the budget delegation reserves for the owner; the ladder-sized design also
   exceeds the delegation's totals. The API key and the workspace spend limit are the same
   open question as in the Terminal-Bench plan.
5. **Decide three things the brief leaves open:** the success definition (any medal, or a frozen
   per-competition threshold if too few competitions are in the band); whether pretrained
   weights may be fetched from a model hub or must be placed in the image; and whether the
   GPU and a quiet window can be reserved for days.
6. **Disk:** about 60 GB free for images, data and scratch; today `/home` has 76 GB and `/` has
   55 GB.

## 13. Engineering hours to a passing oracle-style check on one competition

All estimates; none of this was run.

| Step | Hours |
| --- | --- |
| Install the benchmark package in a user environment; fetch the leaderboard snapshot without Git LFS; prepare one small competition with the owner's token | 2–3 |
| On the host: grade the answers file (expect a gold medal) and the sample submission (expect the listed floor), as the repository's own test does | 1 |
| Wrap the competition as a Harbor task: image with the data, instruction, verifier image holding the answers and the grader, reward file, oracle and do-nothing agents | 6–8 |
| Replace the format checker so the answers stay out of the agent's container | 2 |
| Run the oracle and do-nothing agents five times each on rootless Podman under the final network policy; fix what breaks | 3–4 |
| **Total, one CPU-only competition** | **about 16 (14–18)** |
| First GPU competition in addition: GPU pass-through for Podman under Harbor, the pretrained-weights decision implemented, a longer verifier | 6–10 |
| Each further competition | 1–2 |

This assumes the Terminal-Bench kit (relay, passthrough, allowlist, launcher) exists and is
reused; it is not counted here.

## 14. Open questions I could not settle by reading

1. What each competition's rules say about research use and redistribution, and what Kaggle's
   terms say about automated use. No Kaggle page was readable.
2. Whether a new account can still accept the rules of every candidate. Two lite competitions
   are known to be closed; others may have closed since.
3. Whether the README sizes are archives or prepared data, and so the real disk use.
4. The state of the older Terminal-Bench `mlebench-lite` dataset on Harbor Hub, which might
   save the wrapper work.
5. Whether Harbor 0.25.0 can mount a data directory into a task container or must bake the data
   into the image, and whether its Podman backend accepts a GPU device through an extra compose
   file. The current source shows mounts and shows GPUs wired for Docker only; the installed
   version was not checked.
6. Whether PyTorch 2.2.0 of the benchmark's package list is the right pin for this GPU and
   driver, or whether a newer image is needed.
7. How long a direct Claude Code session works on such a task before it stops, at each effort
   level. Every cost and throughput figure above depends on it.
8. Per-competition results of the small-model runs in arXiv 2604.13018 and of the Codex
   reference; they are not in the repository's `runs/` directory and I did not find them.
9. Whether the thresholds are fair on the rebuilt test set for each candidate. The grading
   reports show two competitions where they clearly are not.

## 15. Sources and method

**Sources (all read 2026-11-13).**
- https://github.com/openai/mle-bench at commit `507f92e`: README, `mlebench/` (`data.py`,
  `grade.py`, `grade_helpers.py`, `registry.py`, `cli.py`, `utils.py`), `environment/`,
  `agents/`, `run_agent.py`, `extras/README.md`, `experiments/splits/`,
  `experiments/competition_categories.csv`, `tests/`, `runs/` (242 grading reports and
  `run_group_experiments.csv`), and the per-competition `config.yaml`, `prepare.py`,
  `description.md` and `leaderboard.csv`.
- The paper, https://arxiv.org/abs/2410.07095 (version 6, HTML).
- https://arxiv.org/abs/2507.02554 (search policies and operators; AIRA-dojo).
- https://arxiv.org/abs/2604.13018 (staged agent; small-model and Codex rows on lite).
- https://arxiv.org/abs/2608.14354 (ScienceFlow; Table 1 and set-up only).
- https://arxiv.org/abs/2603.05764 (short time budgets on four tabular tasks).
- https://github.com/UKGovernmentBEIS/inspect_evals, `src/inspect_evals/mle_bench/README.md`.
- https://github.com/harbor-framework/harbor: the `adapters/` listing and
  `src/harbor/environments/docker/docker.py`, `podman.py`, `src/harbor/models/task/config.py`
  on the main branch.
- https://deploymentsafety.openai.com/gpt-5-6 (section 9.1.3.5) and
  https://benchmarklist.com/benchmarks/mle_bench_revised/ (secondary).
- In this repository: the long-horizon survey report, the Terminal-Bench plan and
  `orchestrator/providers/price_table.json`.
- Not readable: every Kaggle rules page and the Kaggle terms of use.

**Method for the computed figures.** I cloned the repository without its large files and
fetched the grading reports and leaderboard snapshots (40 MB) from its public media address.
The checked-in copy of `runs/run_group_experiments.csv` is a broken pointer with an unresolved
merge conflict; I fetched both versions it names and used the newer one, adding the nine run
groups that only the older one maps. For each competition I joined runs to experiments and
counted medals, above-median results and valid submissions. The working copies were scratch and
were deleted after writing, since the brief allows one file; every count can be regenerated from
the sources above. Local checks were read-only (`nvidia-smi`, `podman info`, `df`, `free`,
`uptime`).
