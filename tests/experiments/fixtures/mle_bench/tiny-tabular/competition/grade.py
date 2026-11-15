def grade(submission, answers):
    """ROC AUC of `probability` against the answers (pandas DataFrames); raises on an invalid submission."""
    if list(submission.columns) != ["id", "probability"] or len(submission) != len(answers):
        raise ValueError("the submission needs the columns id, probability and one row per test id")
    merged = answers.merge(submission, on="id", suffixes=("_true", ""))
    if len(merged) != len(answers) or merged["probability"].isna().any():
        raise ValueError("the submission's ids must be the test ids, each with a value")
    pos, neg = (merged.loc[merged["probability_true"] == k, "probability"] for k in (1, 0))
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))
