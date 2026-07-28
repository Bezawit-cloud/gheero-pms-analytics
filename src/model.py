"""Model initialization, candidate benchmarking, and hyperparameter tuning.
"""

import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold, RandomizedSearchCV
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import GaussianNB
from sklearn.tree import DecisionTreeClassifier
from sklearn.neighbors import KNeighborsClassifier
from sklearn.svm import SVC
from sklearn.ensemble import (
    RandomForestClassifier, ExtraTreesClassifier,
    GradientBoostingClassifier, AdaBoostClassifier
)
import xgboost as xgb
import lightgbm as lgb


def get_candidate_models(random_state=42):
    """Return dictionary of 11 candidate model instances."""
    return {
        'Logistic Regression': Pipeline([('scaler', StandardScaler()), ('model', LogisticRegression(max_iter=1000, random_state=random_state))]),
        'Naive Bayes (Gaussian)': Pipeline([('scaler', StandardScaler()), ('model', GaussianNB())]),
        'Decision Tree': DecisionTreeClassifier(max_depth=10, random_state=random_state),
        'K-Nearest Neighbors': Pipeline([('scaler', StandardScaler()), ('model', KNeighborsClassifier(n_neighbors=15))]),
        'Support Vector Machine (RBF)': Pipeline([('scaler', StandardScaler()), ('model', SVC(probability=True, kernel='rbf', C=1.0, random_state=random_state))]),
        'Random Forest': RandomForestClassifier(n_estimators=150, max_depth=12, random_state=random_state, n_jobs=-1),
        'Extra Trees': ExtraTreesClassifier(n_estimators=150, max_depth=12, random_state=random_state, n_jobs=-1),
        'AdaBoost': AdaBoostClassifier(n_estimators=100, random_state=random_state),
        'Gradient Boosting': GradientBoostingClassifier(n_estimators=150, max_depth=5, random_state=random_state),
        'XGBoost': xgb.XGBClassifier(n_estimators=150, max_depth=5, learning_rate=0.05, eval_metric='logloss', random_state=random_state, n_jobs=-1),
        'LightGBM': lgb.LGBMClassifier(n_estimators=150, max_depth=5, learning_rate=0.05, random_state=random_state, verbose=-1, n_jobs=-1)
    }


def tune_gradient_boosting(X_train, y_train, random_state=42, n_iter=8):
    """Tune Gradient Boosting model for Halfway Checkpoint (Tmid)."""
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
    param_dist_gb = {
        'n_estimators': [100, 150, 200],
        'max_depth': [3, 4, 5],
        'learning_rate': [0.03, 0.05, 0.1],
        'subsample': [0.8, 0.9, 1.0],
        'max_features': ['sqrt', 'log2', None]
    }
    gb_base = GradientBoostingClassifier(random_state=random_state)
    random_search = RandomizedSearchCV(
        estimator=gb_base,
        param_distributions=param_dist_gb,
        n_iter=n_iter,
        scoring='average_precision',
        cv=skf,
        n_jobs=-1,
        random_state=random_state
    )
    random_search.fit(X_train, y_train)
    print(f"Tuned Gradient Boosting Best CV PR-AUC: {random_search.best_score_:.4f}")
    return random_search.best_estimator_


def tune_random_forest(X_train, y_train, random_state=42, n_iter=8):
    """Tune Random Forest model for Creation Checkpoint (T0)."""
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=random_state)
    param_dist_rf = {
        'n_estimators': [100, 150, 200],
        'max_depth': [8, 12, 16, None],
        'min_samples_split': [2, 5, 10],
        'min_samples_leaf': [1, 2, 4],
        'max_features': ['sqrt', 'log2', 0.5]
    }
    rf_base = RandomForestClassifier(random_state=random_state, n_jobs=-1)
    random_search = RandomizedSearchCV(
        estimator=rf_base,
        param_distributions=param_dist_rf,
        n_iter=n_iter,
        scoring='average_precision',
        cv=skf,
        n_jobs=-1,
        random_state=random_state
    )
    random_search.fit(X_train, y_train)
    print(f"Tuned Random Forest Best CV PR-AUC: {random_search.best_score_:.4f}")
    return random_search.best_estimator_
