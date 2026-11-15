# Tiny tabular

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
