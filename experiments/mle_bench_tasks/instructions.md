You are participating in *MLE-bench*, an offline version of Kaggle competitions adapted to test the coding ability of agents like yourself.

You will be given a machine learning task. You must solve the task by training a model and running the model on the test set to produce a submission file. You may not hand-label the data to produce a submission file.

BENCHMARK INSTRUCTIONS
------
First, please read the instructions below which are specific to our benchmark setup.

- **Competition-specific instructions**: The instructions for the competition are available in `${data}/description.md` and at the end of this message. Read them to understand the problem setup for the competition you are currently solving.
- **Dataset**: The dataset files for the competition are available in `${data}/`.
- **Submission**: We have simplified all competition types to use a simple CSV submission format. Regardless of what the competition instructions say, you MUST produce a submission file at `${submission}`. We will only evaluate submissions found at this path; failure to submit a `submission.csv` at this path will result in a failed attempt.
- **Test set**: In general, since we do not have access to the original test labels, we have constructed our own train/test split for each competition. As such, the dataset you see in `${data}/` may differ slightly from what is described in the competition instructions. Nevertheless the files available to you should otherwise be similar to the original and you should proceed with the competition task on the train/test splits available to you.
- **Submission checker**: `python ${validator} ${submission}` checks the format of a submission file against the sample submission: the same columns, the same ids, the same number of rows and no empty value. It does not give you a score, and a file it accepts can still be refused by the grader.
- **Cheating**: You are not allowed to view others' solutions to this competition. If we detect that your submission is plagiarized from others, the submission will be disqualified.

Your submission will be graded based on the metric in the competition-specific instructions. Your goal is to achieve the best score possible on the competition task.

Wherever there is a conflict between the points above and the competition-specific instructions, the above points should always take priority since these are always true for our offline benchmark setup.

ADDITIONAL NOTES
------

- **Compute**: You have access to ${hardware}.
- **Total Runtime**: You have a maximum of ${hours} hours to attempt this task. You may iteratively develop your solution within this time frame, but bear in mind that program runtime also counts towards this limit.

COMPETITION INSTRUCTIONS
------

