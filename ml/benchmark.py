"""Model comparison for the metabolic-syndrome Quick Screen (NHANES 2011-12).

5-fold x 5-repeat stratified CV. Every model sees the same folds. For each model and feature set we report
mean CV AUC, a paired bootstrap 95% CI for its AUC difference vs plain logistic regression, Brier score and
calibration slope. Preprocessing (scaling, splines) is fitted inside each training fold.

    python ml/benchmark.py            # v2 pooled data -> ml/results/benchmark_v2.csv + cross_cycle_v2.csv
    python ml/benchmark.py v1         # archived v1 (2011-12 extract) -> ml/results/benchmark.csv
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
from common import CANDIDATE_TERMS, FEATURE_SETS, FEATURE_SETS_V1, INTERACTIONS, add_terms, design, load, target  # noqa: E402

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


def summarise(y, preds, idx, fs):
    rows = []
    p_lr = preds["lr"].mean(0) if preds["lr"].ndim == 2 else preds["lr"]
    p_dep = None if "lr_interact" not in preds else (preds["lr_interact"].mean(0) if preds["lr_interact"].ndim == 2 else preds["lr_interact"])
    for name, P in preds.items():
        p = P.mean(0) if P.ndim == 2 else P
        aucs = [roc_auc_score(y, q) for q in P] if P.ndim == 2 else [roc_auc_score(y, p)]
        boot = np.array([roc_auc_score(y[i], p[i]) for i in idx])
        row = {"feature_set": fs, "model": name, "n": len(y), "events": int(y.sum()),
               "auc": np.mean(aucs), "auc_lo": np.percentile(boot, 2.5), "auc_hi": np.percentile(boot, 97.5),
               "brier": brier_score_loss(y, p), "cal_slope": cal_slope(y, p), "o_e": y.mean() / p.mean()}
        if name != "lr":
            dd = np.array([roc_auc_score(y[i], p[i]) - roc_auc_score(y[i], p_lr[i]) for i in idx])
            row.update(d_vs_lr=roc_auc_score(y, p) - roc_auc_score(y, p_lr), d_lo=np.percentile(dd, 2.5), d_hi=np.percentile(dd, 97.5))
        if p_dep is not None and name != "lr_interact":
            dd = np.array([roc_auc_score(y[i], p[i]) - roc_auc_score(y[i], p_dep[i]) for i in idx])
            row.update(d_vs_dep=roc_auc_score(y, p) - roc_auc_score(y, p_dep),
                       d_dep_lo=np.percentile(dd, 2.5), d_dep_hi=np.percentile(dd, 97.5))
        rows.append(row)
    return rows


def main(version="v2"):
    t0 = time.time()
    d = load(version)
    sets = FEATURE_SETS if version == "v2" else FEATURE_SETS_V1
    X_all, y_all = design(d), target(d)
    rows, cross = [], []
    for fs, cols in sets.items():
        keep = X_all[cols].notna().all(axis=1).values          # e.g. a few people without uric acid / urine albumin
        X, y = X_all.loc[keep, cols].reset_index(drop=True), y_all[keep]
        preds = {}
        for name, make in models(cols).items():
            P = np.zeros((REPS, len(y)))
            for r in range(REPS):
                for tr, te in StratifiedKFold(FOLDS, shuffle=True, random_state=r).split(X, y):
                    P[r, te] = make().fit(X.iloc[tr], y[tr]).predict_proba(X.iloc[te])[:, 1]
            preds[name] = P
            print(f"  {fs:15s} {name:20s} CV AUC {np.mean([roc_auc_score(y, q) for q in P]):.4f}  ({time.time() - t0:.0f}s)", flush=True)
        rng = np.random.default_rng(0)
        rows += summarise(y, preds, [rng.integers(0, len(y), len(y)) for _ in range(BOOT)], fs)
        if version == "v2" and fs == "core":
            # cross-cycle validation: train on one survey, test on the other (both directions)
            cyc = d.loc[keep, "cycle"].values
            for train_c, test_c in (("G", "P"), ("P", "G")):
                tr_, te_ = cyc == train_c, cyc == test_c
                cp = {name: make().fit(X[tr_], y[tr_]).predict_proba(X[te_])[:, 1] for name, make in models(cols).items()}
                yt = y[te_]
                rng = np.random.default_rng(0)
                for r_ in summarise(yt, cp, [rng.integers(0, len(yt), len(yt)) for _ in range(BOOT)], fs):
                    cross.append({"train": train_c, "test": test_c, **r_})
                print(f"  cross-cycle {train_c}->{test_c} done ({time.time() - t0:.0f}s)", flush=True)
    res = pd.DataFrame(rows)
    OUT.mkdir(exist_ok=True)
    res.round(6).to_csv(OUT / ("benchmark_v2.csv" if version == "v2" else "benchmark.csv"), index=False)
    if cross:
        pd.DataFrame(cross).round(6).to_csv(OUT / "cross_cycle_v2.csv", index=False)
        print(pd.DataFrame(cross).round(4)[["train", "test", "model", "auc", "auc_lo", "auc_hi", "cal_slope", "o_e", "d_vs_dep", "d_dep_lo", "d_dep_hi"]].to_string(index=False))
    print(res.round(4).to_string(index=False))
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "v2")
