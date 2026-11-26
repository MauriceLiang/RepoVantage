# RepoVantage M1/M2 weekly training input

`repository_weekly_features.csv.gz` contains 15,600 repository-week aggregates for 300 repositories over 52 complete UTC weeks. It is the frozen input used by `scripts/train_course_ml.py` for M1 and M2, with the repository-level 150/150 split in `ml/course/splits/repositories-150-150-v1.json`.

The file is a compact training/evaluation input, not the raw collection archive. It is kept separate from `data/manifests/comparison-repositories-v1.json`; neither training nor evaluation samples are added to a user's personal repository list.

SHA-256: `5a463e44da2260d943a7851c872277984552fba3034e12eb8d5bb14c7c2c148d`.
