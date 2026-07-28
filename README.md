# PMS Task Overdue Prediction

Predict whether a project task will be overdue using historical project management data.

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
│   ├── analytical_dataset.sql         #   Full dataset extraction (leaky)
│   ├── analytical_dataset_leak_fixed.sql #   Leak-fixed extraction
│   └── data_quality_checks.sql        #   Data quality validation queries
│
├── src/                               # Source code
│   ├── build_features.py              #   End-to-end feature pipeline (leaky)
│   ├── build_features_leak_fixed.py   #   Leak-fixed pipeline
│   └── feature_engineering.py         #   Feature creation functions
│
├── notebooks/                         # Jupyter notebooks
│   ├── exploration/                   #   EDA and table exploration
│   ├── pipeline/                      #   Dataset building
│   ├── training/                      #   Model training
│   └── archive/                       #   Superseded notebooks
│
├── models/                            # Serialized model artifacts
│   └── *.joblib / *.pkl               #   Trained models
│
├── reports/                           # Reports and visualizations
│   ├── ER-Diagram.png                 #   Entity relationship diagram
│   ├── EDA_findings.md                #   EDA findings report
│   ├── model_report.md                #   Model comparison report (leaky data)
│   ├── model_report_clean_data.md     #   Model report (clean leak-free data)
│   └── model_report_fixed_end_date.md #   Model report (fixed target data)
│
├── pdf/                               # Compiled PDF reports
│   ├── technical_report.pdf           #   Comprehensive technical report
│   ├── management_summary.pdf         #   Executive summary
│   ├── feature_analysis.pdf           #   Feature analysis
│   ├── annotated_walkthrough.pdf      #   File-by-file guide
│   └── connect_db.pdf                 #   Database connection guide
│
├── tests/                             # Test suite
│   ├── test_data_validation_sql.py    #   SQL validation tests
│   ├── test_data_validation_leak_fixed.py # Leak-fixed validation tests
│   └── test_feature_engineering.py    #   Feature engineering tests
│
├── data/                              # Datasets
│   ├── raw/                           #   Original unmodified CSVs
│   ├── fixed_end_date/                #   Three-tier target fix
│   └── clean/                         #   Leak-free feature-engineered CSVs
│
└── docs/                              # Documentation and handoffs
    ├── handoff.md                     #   Master feature pipeline report
    ├── handoff_H1.md                  #   Dataset schema documentation
    ├── handoff_H2.md                  #   ER diagram / join strategy
    ├── handoff_H5.md                  #   Data quality findings
    ├── feature_and_leakage_documentation.pdf # Leakage fix reference
    └── contributing.pdf               #   Contribution guide
```
