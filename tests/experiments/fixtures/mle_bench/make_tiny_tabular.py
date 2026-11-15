"""Write the synthetic miniature competition `tiny-tabular` (MLE-bench family plan, "Tasks", the fixture).

Usage: python -I make_tiny_tabular.py <out dir>    writes <out dir>/tiny-tabular/

Seeded and standard library only: the same bytes on every machine (the wrap tests regenerate and compare). Nothing in it comes
from a real competition. The layout is that of a prepared MLE-bench competition with the data directory at
<out dir>:

  tiny-tabular/prepared/public/    train.csv (id, x1, x2, label), test.csv (no label), sample_submission.csv
                                   (0.5 for every id), description.md
  tiny-tabular/prepared/private/   answers.csv (id, probability as 0 or 1): the held-out answers, itself a valid
                                   submission
  tiny-tabular/competition/        stands in for mlebench/competitions/<id>/: config.yaml (the benchmark's shape),
                                   description.md, grade.py (ROC AUC, higher is better), prepare.py (importable,
                                   refuses to run), leaderboard.csv (twenty teams, best first)

The answers score 1.0 (gold: above every team); the sample submission scores 0.5 (below the last team).
"""

import random
import sys
from pathlib import Path

SEED = 20261115
ID = "tiny-tabular"
N_TRAIN, N_TEST, N_TEAMS = 60, 40, 20

DESCRIPTION = """# Tiny tabular

A synthetic competition made for tests. Each row has two features, `x1` and `x2`, in [0, 1]. Predict the
probability that `label` is 1 for each row of `test.csv`.

## Evaluation

Submissions are scored by the area under the ROC curve; higher is better.

## Submission file

A CSV file with a header and one row per test id:

```
id,probability
1001,0.5
```
"""

CONFIG = f"""id: {ID}
name: Tiny Tabular
competition_type: simple
awards_medals: true
prizes: null
description: mlebench/competitions/{ID}/description.md

dataset:
  answers: {ID}/prepared/private/answers.csv
  sample_submission: {ID}/prepared/public/sample_submission.csv

grader:
  name: roc-auc
  grade_fn: mlebench.competitions.{ID}.grade:grade

preparer: mlebench.competitions.{ID}.prepare:prepare
"""

GRADE = '''def grade(submission, answers):
    """ROC AUC of `probability` against the answers (pandas DataFrames); raises on an invalid submission."""
    if list(submission.columns) != ["id", "probability"] or len(submission) != len(answers):
        raise ValueError("the submission needs the columns id, probability and one row per test id")
    merged = answers.merge(submission, on="id", suffixes=("_true", ""))
    if len(merged) != len(answers) or merged["probability"].isna().any():
        raise ValueError("the submission's ids must be the test ids, each with a value")
    pos, neg = (merged.loc[merged["probability_true"] == k, "probability"] for k in (1, 0))
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
'''

PREPARE = '''def prepare(raw, public, private):
    raise NotImplementedError("tiny-tabular is written by tests/experiments/fixtures/mle_bench/make_tiny_tabular.py")
'''


def rows(rng):
    """(id, x1, x2, label) for train and test, ids unique, both labels present in the test rows."""
    ids = rng.sample(range(1000, 10000), N_TRAIN + N_TEST)
    out = []
    for i in ids:
        x1, x2 = round(rng.random(), 4), round(rng.random(), 4)
        out.append((i, x1, x2, int(x1 + x2 + rng.uniform(-0.2, 0.2) > 1)))
    train, test = sorted(out[:N_TRAIN]), sorted(out[N_TRAIN:])
    assert {r[3] for r in test} == {0, 1}
    return train, test


def leaderboard(rng):
    scores = sorted((round(rng.uniform(0.62, 0.97), 5) for _ in range(N_TEAMS)), reverse=True)
    teams = rng.sample(range(10000, 99999), N_TEAMS)
    head = "scoreNullable,teamId,hasTeamName,submissionDate,score,hasScore\n"
    return head + "".join(f"{s},{t},True,2026-01-{d + 1:02d} 12:00:00,{s},True\n"
                          for d, (s, t) in enumerate(zip(scores, teams)))


def csv(header, lines):
    return header + "\n" + "".join(",".join(str(v) for v in line) + "\n" for line in lines)


def files():
    rng = random.Random(SEED)
    train, test = rows(rng)
    pub, priv, comp = "prepared/public/", "prepared/private/", "competition/"
    return {
        pub + "train.csv": csv("id,x1,x2,label", train),
        pub + "test.csv": csv("id,x1,x2", [r[:3] for r in test]),
        pub + "sample_submission.csv": csv("id,probability", [(r[0], 0.5) for r in test]),
        pub + "description.md": DESCRIPTION,
        priv + "answers.csv": csv("id,probability", [(r[0], r[3]) for r in test]),
        comp + "config.yaml": CONFIG,
        comp + "description.md": DESCRIPTION,
        comp + "grade.py": GRADE,
        comp + "prepare.py": PREPARE,
        comp + "leaderboard.csv": leaderboard(rng),
    }


def main(out):
    root = Path(out) / ID
    for rel, text in files().items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_bytes(text.encode())


if __name__ == "__main__":
    main(sys.argv[1])
