# PMS Task Overdue Prediction

Predict whether a project task will be overdue using historical project management data.

## Branching

| Branch | Purpose |
|--------|---------|
| `main` | Production — tagged releases |
| `staging` | Integration branch — `dev-data` and `dev-eda-modeling` are merged here for end-to-end testing before release |
| `dev-data` | Phase 1 — data & infrastructure |
| `dev-eda-modeling` | Phase 2 — EDA & modeling |

## Local Setup

```bash
python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

## Project Structure

```
pms-overdue-prediction/
│
├── README.md                          # Project overview
├── requirements.txt                   # Python dependencies
├── .gitignore                         # Ignored files
│
├── sql/                               # SQL queries
│   ├── analytical_dataset.sql         #   Full dataset extraction
│   ├── data_quality_checks.sql        #   Data quality validation queries
│   └── performance_metrics.sql        #   Overdue KPI queries
│
├── src/                               # Source code
│   ├── feature_engineering.py         #   Feature creation functions
│   ├── build_features.py              #   End-to-end feature pipeline
│   ├── train.py                       #   Model training
│   ├── evaluate.py                    #   Model evaluation
│   └── error_analysis.py              #   Error analysis
│
├── notebooks/                         # Jupyter notebooks
│   ├── 05_eda.ipynb                   #   Exploratory data analysis
│   └── pms_analysis_and_modeling.ipynb #   End-to-end analysis
│
├── models/                            # Serialized model artifacts
│   ├── lr_model.pkl                   #   Trained Logistic Regression
│   ├── scaler.pkl                     #   Fitted StandardScaler
│   ├── label_encoder.pkl              #   Fitted LabelEncoder
│   ├── features_list.pkl              #   Selected feature names
│   └── num_cols.pkl                   #   Numeric column list
│
├── reports/                           # Reports and visualizations
│   ├── ER-Diagram.png                 #   Entity relationship diagram
│   ├── technical_report.pdf           #   Comprehensive technical report
│   ├── management_summary.pdf         #   Executive summary
│   ├── annotated_walkthrough.pdf      #   File-by-file guide
│   ├── modeling_report.md             #   Model comparison report
│   ├── error_analysis.md              #   Error root cause analysis
│   ├── feature_engineering.md         #   Feature documentation
│   ├── confusion_matrix_*.png         #   Confusion matrices
│   ├── loss_curves.png                #   Training/validation loss curves
│   └── figure_4.png                   #   Report figure
│
├── answers/                           # Q&A documentation
│   ├── reasoning_questions.md         #   Reasoning Q&A
│   └── defense_answers.pdf            #   Defense preparation
│
├── tests/                             # Test suite
│   ├── test_data_validation_sql.py    #   SQL validation tests
│   ├── test_feature_engineering.py    #   Feature engineering tests
│   ├── test_model.py                  #   Model tests
│   └── test_reporting.py             #   Reporting tests
│
├── data/                              # Datasets
│   ├── analytical_dataset.csv         #   Phase 1 output — one row per task
│   ├── analytical_dataset_with_features.csv # Final dataset with engineered features
│   └── .gitkeep
│
└── docs/                              # Documentation and handoffs
    ├── handoff_H1.md                  #   Dataset schema documentation
    ├── handoff_H2.md                  #   ER diagram documentation
    ├── handoff_H3.md                  #   Feature documentation
    ├── handoff_H4.md                  #   Model documentation
    ├── handoff_H5.md                  #   Data quality findings
    ├── handoff_H6.md                  #   Error analysis documentation
    ├── branching_strategy.md          #   Branching workflow
    └── contributing.pdf               #   Contribution guide
```
