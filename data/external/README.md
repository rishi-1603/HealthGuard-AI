# External datasets

## heart_disease.csv
- Source: UCI Machine Learning Repository, Heart Disease (ID 45), `https://archive.ics.uci.edu/static/public/45/data.csv`
- Content: 303 patients, Cleveland Clinic Foundation (real clinical data)
- License: CC BY 4.0 (UCI ML Repository default)
- Use: real-data validation of the fairness structure and intervention-economics
  methods (scripts/realdata_validation.py). `num > 0` = disease presence;
  `sex` = protected attribute (1 = male, 0 = female).
