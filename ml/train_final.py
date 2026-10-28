"""
Train + validate the production Quick Screen v2.0: probability that an adult currently has metabolic syndrome, from
measurements that need no blood test (age, sex, race/ethnicity, BMI, waist).

v2 is trained on NHANES 2011-12 + 2017-March 2020, rebuilt from the raw CDC files with ONE label definition (ATP III /
harmonized, medicines included; see ml/nhanes.py), n = 5,757. A survey-cycle indicator (RECENT) lets the two cycles
differ in overall level. The shipped model fixes RECENT = 1, so its percentages describe today's (2017-2020) population.
RECENT is folded into the intercept on export, so model.json keeps the same format as v1.

Penalised logistic regression with sex x age, sex x waist and waist^2 terms, exported as plain coefficients so the
FastAPI backend and the browser run the identical model with zero ML dependencies.

    python ml/nhanes.py                 # data/nhanes_pooled.csv
    python ml/benchmark.py              # ml/results/benchmark_v2.csv + cross_cycle_v2.csv
    python ml/train_final.py            # writes backend/artifacts/models_v1_mets/model.json and frontend/src/model.json
"""
from __future__ import annotations

import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.preprocessing import StandardScaler

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (DATA, FEATURE_SETS, INTERACTIONS, RACES, RACE_FEATURES, WAIST_CENTER, add_terms,  # noqa: E402
                    design, load, target)
from nhanes import weighted_percentiles  # noqa: E402

VERSION = "2.0.0-lr-mets-pooled"
RESULTS = ROOT / "ml" / "results"
BASE_FEATURES = FEATURE_SETS["core"]                    # includes RECENT
FEATURES = BASE_FEATURES + INTERACTIONS
EXPORT_BASE = [f for f in BASE_FEATURES if f != "RECENT"]
EXPORT_FEATURES = [f for f in FEATURES if f != "RECENT"]
C = 1.0
TERMS = {"MALE_AGE": {"type": "product", "a": "MALE", "b": "AGE"},
         "MALE_WAIST": {"type": "product", "a": "MALE", "b": "WAIST"},
         "WAIST2": {"type": "square", "a": "WAIST", "center": WAIST_CENTER}}
EFFECTS = [
    ("Age", "women, 40 -> 50 years", {"MALE": 0, "AGE": 40}, {"MALE": 0, "AGE": 50}),
    ("Age", "men, 40 -> 50 years", {"MALE": 1, "AGE": 40}, {"MALE": 1, "AGE": 50}),
    ("Waist", "women, 80 -> 90 cm", {"MALE": 0, "WAIST": 80}, {"MALE": 0, "WAIST": 90}),
    ("Waist", "men, 95 -> 105 cm", {"MALE": 1, "WAIST": 95}, {"MALE": 1, "WAIST": 105}),
    ("Waist", "men, 105 -> 115 cm", {"MALE": 1, "WAIST": 105}, {"MALE": 1, "WAIST": 115}),
    ("BMI", "28 -> 33 kg/m² (same waist)", {"BMI": 28}, {"BMI": 33}),
    ("Sex", "men vs women, age 50, waist 98 cm", {"MALE": 0, "AGE": 50, "WAIST": 98}, {"MALE": 1, "AGE": 50, "WAIST": 98}),
    *[(("Mexican American" if r == "MexAmerican" else r), "vs White", {f: 0}, {f: 1}) for r, f in zip(RACES, RACE_FEATURES)],
    ("Survey", "2017-2020 vs 2011-12 (same body measures)", {"RECENT": 0}, {"RECENT": 1}),
]
RANGES = {"AGE": [20, 80], "BMI": [13, 70], "WAIST": [55, 180],
          "SYSBP": [70, 260], "DIABP": [30, 150], "GLUCOSE": [40, 500], "HDL": [10, 200], "TG": [20, 2000]}
TIERS = [
    {"tier": "low", "label": "Unlikely", "min": 0.0, "max": 0.15},
    {"tier": "borderline", "label": "Possible", "min": 0.15, "max": 0.40},
    {"tier": "intermediate", "label": "Likely", "min": 0.40, "max": 0.65},
    {"tier": "high", "label": "Very likely", "min": 0.65, "max": 1.0},
]
HIGH_THRESHOLD = 0.40
CRITERIA = [
    {"id": "waist", "label": "Large waist", "rule": "Waist ≥ 102 cm (40 in) for men, ≥ 88 cm (35 in) for women",
     "male_min": 102, "female_min": 88},
    {"id": "tg", "label": "High triglycerides", "rule": "Triglycerides ≥ 150 mg/dL, or on medicine for high triglycerides",
     "min": 150},
    {"id": "hdl", "label": "Low HDL (“good”) cholesterol",
     "rule": "HDL < 40 mg/dL for men, < 50 mg/dL for women, or on medicine for low HDL", "male_below": 40, "female_below": 50},
    {"id": "bp", "label": "High blood pressure", "rule": "Blood pressure ≥ 130/85 mmHg, or on blood-pressure medicine",
     "sys_min": 130, "dia_min": 85},
    {"id": "glucose", "label": "High fasting blood sugar",
     "rule": "Fasting glucose ≥ 100 mg/dL, or diagnosed diabetes / on glucose-lowering medicine", "min": 100},
]
AGE_BANDS = [[20, 39], [40, 59], [60, 80]]
CYCLE_NAMES = {"G": "2011-2012", "P": "2017-2020"}


def fit_raw(X: pd.DataFrame, y: np.ndarray):
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=C, max_iter=5000).fit(sc.transform(X), y)
    w = lr.coef_[0] / sc.scale_
    b = float(lr.intercept_[0] - np.sum(lr.coef_[0] * sc.mean_ / sc.scale_))
    return b, w


def predict(b, w, X):
    return 1 / (1 + np.exp(-(b + X.values @ w)))


def cal_slope(y, p):
    lo = np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4))).reshape(-1, 1)
    return float(LogisticRegression(C=1e6, max_iter=1000).fit(lo, y).coef_[0, 0])


def _rows(path: Path, cols) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path)
    return json.loads(df[[c for c in cols if c in df]].round(6).to_json(orient="records"))


def calibration_tables(y, p):
    dec = pd.qcut(p, 10, labels=False, duplicates="drop")
    calib = [{"decile": int(k) + 1, "predicted": round(float(p[dec == k].mean()), 4),
              "observed": round(float(y[dec == k].mean()), 4), "n": int((dec == k).sum())} for k in np.unique(dec)]
    ece = float(sum(abs(c["predicted"] - c["observed"]) * c["n"] for c in calib) / len(y))
    tiers = []
    for t in TIERS:
        m = (p >= t["min"]) & (p < t["max"])
        tiers.append({"tier": t["tier"], "n": int(m.sum()), "observed": round(float(y[m].mean()), 4) if m.any() else None})
    thr = {}
    for t in [tier["min"] for tier in TIERS[1:]]:
        f = p >= t
        thr[f"{t:g}"] = {"sensitivity": round(float((f & (y == 1)).sum() / y.sum()), 3),
                         "specificity": round(float((~f & (y == 0)).sum() / (y == 0).sum()), 3),
                         "ppv": round(float(y[f].mean()), 3) if f.any() else None, "flagged_pct": round(float(f.mean()), 3)}
    return calib, ece, tiers, thr


def main():
    d = load()
    X_all, y = design(d), target(d)
    Xb = X_all[BASE_FEATURES]
    X = add_terms(Xb, INTERACTIONS)[FEATURES]
    recent = (d.cycle == "P").values
    # ---- 5-fold x 5-repeat stratified CV on the pooled data
    reps, P = 5, np.zeros((5, len(d)))
    for r in range(reps):
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=r).split(X, y):
            b, w = fit_raw(X.iloc[tr], y[tr])
            P[r, te] = predict(b, w, X.iloc[te])
    p = P.mean(0)
    aucs = [roc_auc_score(y, q) for q in P]
    rng = np.random.default_rng(0)
    boots = [roc_auc_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(1000))]
    groups = {"Survey 2011-12": d.cycle == "G", "Survey 2017-20": d.cycle == "P",
              "Men": d.Sex == "Male", "Women": d.Sex == "Female", "Age 20-39": d.Age < 40,
              "Age 40-59": d.Age.between(40, 59), "Age 60-80": d.Age >= 60,
              **{f"{'Mexican American' if r == 'MexAmerican' else r}": d.Race == r for r in ["White", *RACES]}}
    sub = {}
    for name, mask in groups.items():
        m = mask.values
        if m.sum() >= 30:
            sub[name] = {"n": int(m.sum()), "events": int(y[m].sum()), "auc": round(float(roc_auc_score(y[m], p[m])), 3),
                         "observed": round(float(y[m].mean()), 4), "predicted": round(float(p[m].mean()), 4)}
    calib, ece, tier_obs, thr = calibration_tables(y, p)
    # the shipped model describes today's population: the same tables on the 2017-2020 people only
    calib_r, ece_r, tier_r, thr_r = calibration_tables(y[recent], p[recent])
    # ---- final fit on everyone
    b, w = fit_raw(X, y)
    coef = dict(zip(FEATURES, w))
    b_ship = b + coef["RECENT"]                          # RECENT fixed to 1 and folded into the intercept
    w_ship = [float(coef[f]) for f in EXPORT_FEATURES]
    ref = Xb[recent].mean()
    ref[RACE_FEATURES] = 0.0
    ref["RECENT"] = 1.0

    def logit_at(bb, ww, changes):
        row = ref.copy()
        for k, v in changes.items():
            row[k] = v
        return bb + add_terms(pd.DataFrame([row]), INTERACTIONS)[FEATURES].values[0] @ ww

    boot_fits = [fit_raw(X.iloc[i], y[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(300))]
    ors = []
    for factor, comp, lo_c, hi_c in EFFECTS:
        est = float(np.exp(logit_at(b, w, hi_c) - logit_at(b, w, lo_c)))
        bs = [np.exp(logit_at(bb, ww, hi_c) - logit_at(bb, ww, lo_c)) for bb, ww in boot_fits]
        ors.append({"feature": factor, "unit": comp, "or": round(est, 3),
                    "lo": round(float(np.percentile(bs, 2.5)), 3), "hi": round(float(np.percentile(bs, 97.5)), 3)})
    in_sample = roc_auc_score(y, predict(b, w, X))
    # golden cases from the scikit-learn objects themselves, at RECENT = 1
    sc = StandardScaler().fit(X)
    skl = LogisticRegression(C=C, max_iter=5000).fit(sc.transform(X), y)
    cases = [
        dict(SEX=2, AGE=34, RACE="White", BMI=22.5, WAIST=78),
        dict(SEX=1, AGE=52, RACE="Black", BMI=31.0, WAIST=106),
        dict(SEX=1, AGE=67, RACE="MexAmerican", BMI=28.4, WAIST=101),
        dict(SEX=2, AGE=58, RACE="Asian", BMI=26.0, WAIST=90),
        dict(SEX=2, AGE=45, RACE="Hispanic", BMI=36.5, WAIST=112),
        dict(SEX=1, AGE=25, RACE="Other", BMI=20.1, WAIST=72),
    ]
    golden = []
    for c in cases:
        row = {"AGE": c["AGE"], "MALE": 1.0 if c["SEX"] == 1 else 0.0,
               **{f: 1.0 if c["RACE"] == r else 0.0 for r, f in zip(RACES, RACE_FEATURES)},
               "BMI": c["BMI"], "WAIST": c["WAIST"], "RECENT": 1.0}
        xr = add_terms(pd.DataFrame([row])[BASE_FEATURES], INTERACTIONS)[FEATURES]
        golden.append({"input": c, "p": float(skl.predict_proba(sc.transform(xr))[:, 1][0])})
    Xe = add_terms(Xb, INTERACTIONS)[recent][EXPORT_FEATURES]     # today's population: reference for explanations
    cross = _rows(RESULTS / "cross_cycle_v2.csv", ["train", "test", "model", "n", "events", "auc", "auc_lo", "auc_hi",
                                                    "brier", "cal_slope", "o_e", "d_vs_dep", "d_dep_lo", "d_dep_hi"])
    model = {
        "version": VERSION, "trained": str(date.today()),
        "outcome": "Currently meeting the criteria for metabolic syndrome (3 or more of: large waist, high triglycerides, "
                   "low HDL, high blood pressure or BP medicine, high fasting glucose or diabetes / diabetes medicine)",
        "population": "Non-pregnant US adults aged 20-80",
        "features": EXPORT_FEATURES, "base_features": EXPORT_BASE, "terms": TERMS,
        "intercept": b_ship, "coef": w_ship,
        "train_means": {f: float(v) for f, v in Xe.mean().items()},
        "base_profile": {f: float(v) for f, v in Xb[recent][EXPORT_BASE].mean().items()},
        "races": ["White", *RACES], "race_features": dict(zip(RACES, RACE_FEATURES)),
        "ranges": RANGES, "tiers": TIERS, "high_threshold": HIGH_THRESHOLD, "criteria": CRITERIA,
        "percentiles": {"age_bands": AGE_BANDS, "source": "NHANES 2017-March 2020, survey-weighted (US adults)",
                        "groups": weighted_percentiles("P")},
        "survey_adjustment": {"feature": "RECENT", "coef": float(coef["RECENT"]), "pooled_intercept": b,
                              "note": "Survey-cycle term fixed to 2017-2020 (RECENT = 1) and folded into the intercept."},
        "training": {"source": "NHANES 2011-2012 + 2017-March 2020, rebuilt from the CDC files (ml/nhanes.py)",
                     "rows": int(len(d)), "events": int(y.sum()), "event_rate": round(float(y.mean()), 4),
                     "by_cycle": {CYCLE_NAMES[c]: {"n": int((d.cycle == c).sum()), "events": int(y[(d.cycle == c).values].sum()),
                                                   "prevalence": round(float(y[(d.cycle == c).values].mean()), 4),
                                                   "prevalence_measured_only": round(float(d.MetS_measured_only[d.cycle == c].mean()), 4)}
                                  for c in ("G", "P")},
                     "label": "ATP III / harmonized, medicines included (BP medicine; diagnosed diabetes, insulin or diabetes pills)",
                     "v1_label_finding": "The v1 training file (metabolic_syndrome.csv) was matched to the CDC 2011-12 files by "
                                         "participant ID: every value is identical, and its label matches the measured-values-only "
                                         "definition (no medicines) for 97.5% of people. v2 uses one definition, with medicines, "
                                         "for both surveys.",
                     "criteria_count_auc": round(float(roc_auc_score(y, (
                         np.where(d.Sex == "Male", d.WaistCirc >= 102, d.WaistCirc >= 88).astype(int) + (d.Triglycerides >= 150)
                         + np.where(d.Sex == "Male", d.HDL < 40, d.HDL < 50).astype(int) + (d.BloodGlucose >= 100)))), 4),
                     "data_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest()[:16],
                     "sklearn": sklearn.__version__, "regularisation_C": C},
        "validation": {"scheme": "5-fold x 5-repeat stratified cross-validation, both surveys pooled",
                       "auc": round(float(np.mean(aucs)), 4),
                       "auc_ci95": [round(float(x), 4) for x in np.percentile(boots, [2.5, 97.5])],
                       "auc_in_sample": round(float(in_sample), 4),
                       "brier": round(float(brier_score_loss(y, p)), 4),
                       "brier_null": round(float(y.mean() * (1 - y.mean())), 4),
                       "calibration_slope": round(cal_slope(y, p), 3), "observed_over_expected": round(float(y.mean() / p.mean()), 3),
                       "ece": round(ece, 4), "subgroups": sub, "calibration_deciles": calib, "thresholds": thr,
                       "tier_observed": tier_obs,
                       "recent": {"n": int(recent.sum()), "auc": round(float(roc_auc_score(y[recent], p[recent])), 4),
                                  "calibration_slope": round(cal_slope(y[recent], p[recent]), 3),
                                  "observed_over_expected": round(float(y[recent].mean() / p[recent].mean()), 3),
                                  "ece": round(ece_r, 4), "calibration_deciles": calib_r, "tier_observed": tier_r, "thresholds": thr_r}},
        "cross_cycle": cross,
        "odds_ratios": ors, "golden": golden,
        "benchmark": _rows(RESULTS / "benchmark_v2.csv", ["feature_set", "model", "auc", "auc_lo", "auc_hi", "brier", "cal_slope",
                                                         "d_vs_lr", "d_lo", "d_hi", "d_vs_dep", "d_dep_lo", "d_dep_hi"]),
        "history": [
            {"version": "1.0.0-lr-mets-quick", "note": "Trained on the 2011-12 extract (label without medicines); CV AUC 0.833."},
            {"version": "1.1.0-lr-mets-quick-recal", "note": "v1 + intercept shift (+0.24) after external validation on "
                                                         "NHANES 2017-2020 (AUC 0.844, O/E 1.10 -> 1.00)."},
            {"version": VERSION, "note": "Retrained on both surveys with one label definition (medicines included)."},
        ],
    }
    for path in (ROOT / "backend/artifacts/models_v1_mets/model.json", ROOT / "frontend/src/model.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(model, indent=1))
    v = model["validation"]
    print(f"{VERSION}\n rows={len(d)} events={int(y.sum())}  CV AUC {v['auc']} {v['auc_ci95']}  in-sample {v['auc_in_sample']}\n"
          f" Brier {v['brier']} (null {v['brier_null']})  slope {v['calibration_slope']}  O/E {v['observed_over_expected']}  ECE {v['ece']}")
    print(" recent (2017-20):", {k: v["recent"][k] for k in ("n", "auc", "calibration_slope", "observed_over_expected", "ece")})
    print(" tiers recent:", v["recent"]["tier_observed"])
    for k, s in sub.items():
        print(f"  {k:18s} {s}")
    print(pd.DataFrame(ors).to_string(index=False))
    print(f" RECENT coef {coef['RECENT']:+.4f}; shipped intercept {b_ship:.5f}")


if __name__ == "__main__":
    main()
