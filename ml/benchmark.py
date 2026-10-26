"""Model comparison for the metabolic-syndrome Quick Screen (NHANES 2011-12).

5-fold x 5-repeat stratified CV. Every model sees the same folds. For each model and feature set we report
mean CV AUC, a paired bootstrap 95% CI for its AUC difference vs plain logistic regression, Brier score and
calibration slope. Preprocessing (scaling, splines) is fitted inside each training fold.

    python ml/benchmark.py            # writes ml/results/benchmark.csv and prints the table
"""
from __future__ import annotations

import itertools
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from lightgbm import LGBMClassifier
from sklearn.ensemble import RandomForestClassifier, StackingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import SplineTransformer, StandardScaler
from sklearn.base import BaseEstimator, ClassifierMixin
from sklearn.compose import ColumnTransformer
from xgboost import XGBClassifier

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CANDIDATE_TERMS, FEATURE_SETS, INTERACTIONS, add_terms, design, load, target  # noqa: E402

warnings.filterwarnings("ignore")
OUT = Path(__file__).resolve().parent / "results"
REPS, FOLDS, BOOT = 5, 5, 1000
CONTINUOUS = {"AGE", "BMI", "WAIST", "URIC", "LOG_UACR", "GLUCOSE", "HDL", "TG"}


class TermsLR(BaseEstimator, ClassifierMixin):
    """Logistic regression on the base features plus product / square terms. With terms=None the terms are chosen
    inside fit() by inner 5-fold CV over every combination of 1-3 candidates, so the outer CV scores the whole
    selection procedure (no peeking)."""

    def __init__(self, terms=None):
        self.terms = terms

    def _pipe(self):
        return make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=5000))

    def fit(self, X, y):
        if self.terms is not None:
            self.terms_ = list(self.terms)
        else:
            best = (-1.0, None)
            combos = [c for k in (1, 2, 3) for c in itertools.combinations(CANDIDATE_TERMS, k)]
            folds = list(StratifiedKFold(5, shuffle=True, random_state=99).split(X, y))
            for c in combos:
                Xc = add_terms(X, c)
                a = np.mean([roc_auc_score(y[te], self._pipe().fit(Xc.iloc[tr], y[tr]).predict_proba(Xc.iloc[te])[:, 1])
                             for tr, te in folds])
                if a > best[0]:
                    best = (a, c)
            self.terms_ = list(best[1])
        self.m_ = self._pipe().fit(add_terms(X, self.terms_), y)
        self.classes_ = self.m_.classes_
        return self

    def predict_proba(self, X):
        return self.m_.predict_proba(add_terms(X, self.terms_))


def models(cols):
    cont = [c for c in cols if c in CONTINUOUS]
    other = [c for c in cols if c not in CONTINUOUS]
    spline = ColumnTransformer([("s", SplineTransformer(n_knots=4, degree=3), cont), ("p", "passthrough", other)])
    lr = lambda: make_pipeline(StandardScaler(), LogisticRegression(C=1.0, max_iter=5000))  # noqa: E731
    rf = lambda: RandomForestClassifier(n_estimators=400, min_samples_leaf=10, n_jobs=-1, random_state=0)  # noqa: E731
    xgb = lambda: XGBClassifier(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8,  # noqa: E731
                                colsample_bytree=0.8, n_jobs=2, random_state=0, verbosity=0)
    lgbm = lambda: LGBMClassifier(n_estimators=300, num_leaves=8, learning_rate=0.05, min_child_samples=20,  # noqa: E731
                                  subsample=0.8, subsample_freq=1, colsample_bytree=0.8, verbose=-1, random_state=0)
    return {
        "lr": lr,
        "spline_lr": lambda: make_pipeline(spline, StandardScaler(), LogisticRegression(C=1.0, max_iter=5000)),
        **({"lr_interact": lambda: TermsLR(INTERACTIONS), "lr_interact_nested": lambda: TermsLR(None)}
           if {"AGE", "MALE", "WAIST"} <= set(cols) else {}),
        "rf": rf,
        "xgb": xgb,
        "lgbm": lgbm,
        "stack_lr_rf_xgb": lambda: StackingClassifier(
            [("lr", lr()), ("rf", rf()), ("xgb", xgb())],
            final_estimator=LogisticRegression(max_iter=2000), cv=5, n_jobs=1),
    }


def cal_slope(y, p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    lo = np.log(p / (1 - p)).reshape(-1, 1)
    return float(LogisticRegression(C=1e6, max_iter=1000).fit(lo, y).coef_[0, 0])


def main():
    t0 = time.time()
    d = load()
    X_all, y = design(d), target(d)
    rows = []
    for fs, cols in FEATURE_SETS.items():
        X = X_all[cols]
        preds = {}
        for name, make in models(cols).items():
            P = np.zeros((REPS, len(y)))
            for r in range(REPS):
                for tr, te in StratifiedKFold(FOLDS, shuffle=True, random_state=r).split(X, y):
                    m = make().fit(X.iloc[tr], y[tr])
                    P[r, te] = m.predict_proba(X.iloc[te])[:, 1]
            preds[name] = P
            print(f"  {fs:15s} {name:16s} AUC {np.mean([roc_auc_score(y, q) for q in P]):.4f}  ({time.time() - t0:.0f}s)",
                  flush=True)
        rng = np.random.default_rng(0)
        idx = [rng.integers(0, len(y), len(y)) for _ in range(BOOT)]
        p_lr = preds["lr"].mean(0)
        for name, P in preds.items():
            p = P.mean(0)
            aucs = [roc_auc_score(y, q) for q in P]
            boot = np.array([roc_auc_score(y[i], p[i]) for i in idx])
            row = {"feature_set": fs, "model": name, "n": len(y), "events": int(y.sum()),
                   "auc": np.mean(aucs), "auc_lo": np.percentile(boot, 2.5), "auc_hi": np.percentile(boot, 97.5),
                   "brier": brier_score_loss(y, p), "cal_slope": cal_slope(y, p), "o_e": y.mean() / p.mean()}
            if name != "lr":
                dd = np.array([roc_auc_score(y[i], p[i]) - roc_auc_score(y[i], p_lr[i]) for i in idx])
                row.update(d_vs_lr=roc_auc_score(y, p) - roc_auc_score(y, p_lr),
                           d_lo=np.percentile(dd, 2.5), d_hi=np.percentile(dd, 97.5))
            if "lr_interact" in preds and name != "lr_interact":  # difference vs the deployed model
                p_dep = preds["lr_interact"].mean(0)
                dd = np.array([roc_auc_score(y[i], p[i]) - roc_auc_score(y[i], p_dep[i]) for i in idx])
                row.update(d_vs_dep=roc_auc_score(y, p) - roc_auc_score(y, p_dep),
                           d_dep_lo=np.percentile(dd, 2.5), d_dep_hi=np.percentile(dd, 97.5))
            rows.append(row)
    res = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    res.round(5).to_csv(OUT / "benchmark.csv", index=False)
    print(res.round(4).to_string(index=False))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()
