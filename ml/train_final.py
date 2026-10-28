"""
Train + validate the production Quick Screen (v1.0.0): probability that an adult currently has metabolic syndrome,
from measurements that need no blood test (age, sex, race/ethnicity, BMI, waist). Penalised logistic regression,
exported as plain coefficients to model.json so the FastAPI backend and the browser run the identical model with zero
ML dependencies. Also exports the metabolic-syndrome criteria, NHANES reference percentiles, and validation figures
shown on the Model & Data tab.

    python ml/train_final.py            # writes backend/artifacts/models_v1_mets/model.json
                                        #        frontend/src/model.json
Selection rationale: ml/RESULTS.md (benchmark).
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

VERSION = "1.1.0-lr-mets-quick-recal"
EXTERNAL = ROOT / "ml" / "results" / "external_2017_2020.json"
BASE_FEATURES = FEATURE_SETS["core"]
C = 1.0
FEATURES = BASE_FEATURES + INTERACTIONS
# how each extra term is built from the base features (read by backend/app/model.py and frontend/src/riskModel.js)
TERMS = {"MALE_AGE": {"type": "product", "a": "MALE", "b": "AGE"},
         "MALE_WAIST": {"type": "product", "a": "MALE", "b": "WAIST"},
         "WAIST2": {"type": "square", "a": "WAIST", "center": WAIST_CENTER}}
# Odds ratios shown on the Model & Data tab. With interaction terms an effect depends on the other values, so each
# comparison is stated at a reference profile (everything else at the sample average).
EFFECTS = [
    ("Age", "women, 40 -> 50 years", {"MALE": 0, "AGE": 40}, {"MALE": 0, "AGE": 50}),
    ("Age", "men, 40 -> 50 years", {"MALE": 1, "AGE": 40}, {"MALE": 1, "AGE": 50}),
    ("Waist", "women, 80 -> 90 cm", {"MALE": 0, "WAIST": 80}, {"MALE": 0, "WAIST": 90}),
    ("Waist", "men, 95 -> 105 cm", {"MALE": 1, "WAIST": 95}, {"MALE": 1, "WAIST": 105}),
    ("Waist", "men, 105 -> 115 cm", {"MALE": 1, "WAIST": 105}, {"MALE": 1, "WAIST": 115}),
    ("BMI", "28 -> 33 kg/m² (same waist)", {"BMI": 28}, {"BMI": 33}),
    ("Sex", "men vs women, age 50, waist 98 cm", {"MALE": 0, "AGE": 50, "WAIST": 98}, {"MALE": 1, "AGE": 50, "WAIST": 98}),
    *[(("Mexican American" if r == "MexAmerican" else r), "vs White", {f: 0}, {f: 1}) for r, f in zip(RACES, RACE_FEATURES)],
]
# Hard input ranges enforced by the API = observed NHANES range, padded slightly.
RANGES = {"AGE": [20, 80], "BMI": [13, 70], "WAIST": [55, 180],
          "SYSBP": [70, 260], "DIABP": [30, 150], "GLUCOSE": [40, 500], "HDL": [10, 200], "TG": [20, 2000]}
# Probability of *currently* meeting the criteria. Prevalence in the training sample is ~34%.
TIERS = [
    {"tier": "low", "label": "Unlikely", "min": 0.0, "max": 0.15},
    {"tier": "borderline", "label": "Possible", "min": 0.15, "max": 0.40},
    {"tier": "intermediate", "label": "Likely", "min": 0.40, "max": 0.65},
    {"tier": "high", "label": "Very likely", "min": 0.65, "max": 1.0},
]
HIGH_THRESHOLD = 0.40  # "Likely" or above
# NCEP ATP III / 2009 harmonized criteria (US waist cut-points). Metabolic syndrome = 3 or more of 5.
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
PCT_VARS = {"WAIST": "WaistCirc", "BMI": "BMI", "GLUCOSE": "BloodGlucose", "HDL": "HDL", "TG": "Triglycerides"}
AGE_BANDS = [[20, 39], [40, 59], [60, 80]]


def fit_raw(X: pd.DataFrame, y: np.ndarray):
    sc = StandardScaler().fit(X)
    lr = LogisticRegression(C=C, max_iter=5000).fit(sc.transform(X), y)
    w = lr.coef_[0] / sc.scale_
    b = float(lr.intercept_[0] - np.sum(lr.coef_[0] * sc.mean_ / sc.scale_))
    return b, w


def predict(b, w, X):
    return 1 / (1 + np.exp(-(b + X.values @ w)))


def _benchmark_rows() -> list[dict]:
    path = ROOT / "ml" / "results" / "benchmark.csv"
    if not path.exists():
        return []
    rows = json.loads(pd.read_csv(path)[["feature_set", "model", "auc", "auc_lo", "auc_hi", "brier", "cal_slope",
                                         "d_vs_lr", "d_lo", "d_hi", "d_vs_dep", "d_dep_lo", "d_dep_hi"]]
                      .round(6).to_json(orient="records"))
    return rows


def _external(ext: dict | None) -> dict | None:
    """External-validation figures shown on the Model & Data tab (from ml/results/external_2017_2020.json)."""
    if not ext:
        return None
    keep = ("auc", "auc_lo", "auc_hi", "brier", "cal_slope", "citl", "o_e", "ece", "d_vs_dep", "d_lo", "d_hi",
            "auc_weighted", "observed_weighted", "mean_pred_weighted", "mean_pred", "observed")
    return {
        "source": "NHANES 2017-March 2020 (pre-pandemic): fasting subsample, non-pregnant adults aged 20-80",
        "flow": ext["flow"], "n": ext["n"], "events": ext["events"], "prevalence": ext["prevalence"],
        "prevalence_measured_only": ext["prevalence_measured_only"],
        "label": "ATP III with medicines (BP medicine counts for blood pressure; diagnosed diabetes or diabetes medicine for glucose)",
        "models": {k: {kk: v[kk] for kk in keep if kk in v} for k, v in ext["sets"]["core"]["models"].items()},
        "models_with_labs": ({k: {kk: v[kk] for kk in ("auc", "d_vs_dep", "d_lo", "d_hi") if kk in v}
                              for k, v in ext["sets"]["core_labs"]["models"].items()} if "core_labs" in ext["sets"] else None),
        "shipped": ext.get("shipped"), **{k: ext["deployed"][k] for k in
                                          ("calibration_deciles", "tiers", "thresholds", "subgroups", "recalibration",
                                           "criteria_count_auc")},
    }


def percentiles(d: pd.DataFrame) -> dict:
    out = {}
    for sex in ["Male", "Female"]:
        for lo, hi in AGE_BANDS:
            m = (d.Sex == sex) & d.Age.between(lo, hi)
            key = f"{sex[0]}{lo}-{hi}"
            out[key] = {"n": int(m.sum()), "q": {}}
            for v, col in PCT_VARS.items():
                s = d.loc[m, col].dropna()
                out[key]["q"][v] = [round(float(x), 2) for x in np.percentile(s, np.arange(1, 100))]
    return out


def criteria_agreement(d: pd.DataFrame) -> dict:
    """How the dataset's label relates to the 4 criteria that are measured in the file (BP is not)."""
    male = d.Sex == "Male"
    met = (np.where(male, d.WaistCirc >= 102, d.WaistCirc >= 88).astype(int) + (d.Triglycerides >= 150)
           + np.where(male, d.HDL < 40, d.HDL < 50).astype(int) + (d.BloodGlucose >= 100))
    y = d.MetabolicSyndrome
    rows = []
    for k in range(5):
        m = met == k
        rows.append({"criteria_met": k, "n": int(m.sum()), "labelled_mets": int(y[m].sum())})
    return {"note": "Blood pressure is not in the file, so people with 2 measured criteria are labelled by their (unseen) BP.",
            "rows": rows, "auc_of_count": round(float(roc_auc_score(y, met)), 4)}


def main():
    d = load()
    X_all, y = design(d), target(d)
    Xb = X_all[BASE_FEATURES]
    X = add_terms(Xb, INTERACTIONS)[FEATURES]
    # ---- repeated stratified CV (the validation numbers reported in-app)
    reps, P = 5, np.zeros((5, len(d)))
    for r in range(reps):
        for tr, te in StratifiedKFold(5, shuffle=True, random_state=r).split(X, y):
            b, w = fit_raw(X.iloc[tr], y[tr])
            P[r, te] = predict(b, w, X.iloc[te])
    p = P.mean(0)
    aucs = [roc_auc_score(y, q) for q in P]
    rng = np.random.default_rng(0)
    boots = [roc_auc_score(y[i], p[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(1000))]
    groups = {"Men": d.Sex == "Male", "Women": d.Sex == "Female", "Age 20-39": d.Age < 40,
              "Age 40-59": d.Age.between(40, 59), "Age 60-80": d.Age >= 60,
              **{f"{'Mexican American' if r == 'MexAmerican' else r}": d.Race == r for r in ["White", *RACES]}}
    sub = {}
    for name, mask in groups.items():
        m = mask.values
        if m.sum() < 30:
            continue
        sub[name] = {"n": int(m.sum()), "events": int(y[m].sum()), "auc": round(float(roc_auc_score(y[m], p[m])), 3),
                     "observed": round(float(y[m].mean()), 4), "predicted": round(float(p[m].mean()), 4)}
    dec = pd.qcut(p, 10, labels=False, duplicates="drop")
    calib = [{"decile": int(k) + 1, "predicted": round(float(p[dec == k].mean()), 4),
              "observed": round(float(y[dec == k].mean()), 4), "n": int((dec == k).sum())} for k in np.unique(dec)]
    ece = float(sum(abs(c["predicted"] - c["observed"]) * c["n"] for c in calib) / len(y))
    lo = np.log(np.clip(p, 1e-4, 1 - 1e-4) / (1 - np.clip(p, 1e-4, 1 - 1e-4))).reshape(-1, 1)
    slope = float(LogisticRegression(C=1e6, max_iter=1000).fit(lo, y).coef_[0, 0])
    thr = {}
    for t in [tier["min"] for tier in TIERS[1:]]:
        flagged = p >= t
        thr[f"{t:g}"] = {"sensitivity": round(float((flagged & (y == 1)).sum() / y.sum()), 3),
                         "specificity": round(float((~flagged & (y == 0)).sum() / (y == 0).sum()), 3),
                         "ppv": round(float(y[flagged].mean()), 3) if flagged.any() else None,
                         "flagged_pct": round(float(flagged.mean()), 3)}
    tier_obs = []
    for t in TIERS:
        m = (p >= t["min"]) & (p < t["max"])
        tier_obs.append({"tier": t["tier"], "n": int(m.sum()), "observed": round(float(y[m].mean()), 4) if m.any() else None})
    # ---- final fit on all rows
    b, w = fit_raw(X, y)
    # ---- recalibration (v1.1): shift the intercept so the average estimate matches NHANES 2017-March 2020, the newer
    # population (ml/external_validation.py). Slopes, odds ratios, ranking and AUC are unchanged; only the overall
    # level of the percentages moves. The internal validation numbers below describe the development model (no shift).
    ext = json.loads(EXTERNAL.read_text()) if EXTERNAL.exists() else None
    shift = float(ext["deployed"]["recalibration"]["intercept_shift"]) if ext else 0.0
    ref = Xb.mean()
    ref[RACE_FEATURES] = 0.0  # reference profile: White, otherwise the sample average

    def logit_at(bb, ww, changes):
        row = ref.copy()
        for k, v in changes.items():
            row[k] = v
        r = add_terms(pd.DataFrame([row]), INTERACTIONS)[FEATURES].values[0]
        return bb + r @ ww

    boot_fits = [fit_raw(X.iloc[i], y[i]) for i in (rng.integers(0, len(y), len(y)) for _ in range(300))]
    ors = []
    for factor, comp, lo_c, hi_c in EFFECTS:
        est = float(np.exp(logit_at(b, w, hi_c) - logit_at(b, w, lo_c)))
        bs = [np.exp(logit_at(bb, ww, hi_c) - logit_at(bb, ww, lo_c)) for bb, ww in boot_fits]
        ors.append({"feature": factor, "unit": comp, "or": round(est, 3),
                    "lo": round(float(np.percentile(bs, 2.5)), 3), "hi": round(float(np.percentile(bs, 97.5)), 3)})
    in_sample = roc_auc_score(y, predict(b, w, X))
    # golden cases from the scikit-learn objects themselves (not from our own arithmetic)
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
               "BMI": c["BMI"], "WAIST": c["WAIST"]}
        xr = add_terms(pd.DataFrame([row]), INTERACTIONS)[FEATURES]
        z = float(skl.decision_function(sc.transform(xr))[0]) + shift
        golden.append({"input": c, "p": 1.0 / (1.0 + np.exp(-z))})
    # race not given -> the race indicators take their training means (an average over the sample's mix)
    raw = pd.read_csv(DATA)
    model = {
        "version": VERSION, "trained": str(date.today()),
        "outcome": "Currently meeting the criteria for metabolic syndrome (3 or more of: large waist, high triglycerides, "
                   "low HDL, high blood pressure, high fasting glucose)",
        "population": "Non-pregnant US adults aged 20-80",
        "features": FEATURES, "base_features": BASE_FEATURES, "terms": TERMS,
        "intercept": b + shift, "coef": [float(x) for x in w],
        "recalibration": {"intercept_shift": round(shift, 4), "development_intercept": b,
                          "method": "intercept-only (calibration-in-the-large) update on the log-odds scale",
                          "estimated_on": "NHANES 2017-March 2020 (pre-pandemic), the external validation sample"},
        "train_means": {f: float(v) for f, v in X.mean().items()},
        "base_profile": {f: float(v) for f, v in Xb.mean().items()},
        "races": ["White", *RACES], "race_features": dict(zip(RACES, RACE_FEATURES)),
        "ranges": RANGES, "tiers": TIERS, "high_threshold": HIGH_THRESHOLD, "criteria": CRITERIA,
        "percentiles": {"age_bands": AGE_BANDS, "groups": percentiles(raw)},
        "training": {"source": "NHANES 2011-2012 metabolic syndrome extract (metabolic_syndrome.csv)",
                     "rows_in_file": int(len(raw)), "rows": int(len(d)), "events": int(y.sum()),
                     "event_rate": round(float(y.mean()), 4), "excluded_missing_waist_or_bmi": int(len(raw) - len(d)),
                     "data_sha256": hashlib.sha256(DATA.read_bytes()).hexdigest()[:16],
                     "sklearn": sklearn.__version__, "regularisation_C": C},
        "validation": {"scheme": "5-fold x 5-repeat stratified cross-validation",
                       "auc": round(float(np.mean(aucs)), 4),
                       "auc_ci95": [round(float(x), 4) for x in np.percentile(boots, [2.5, 97.5])],
                       "auc_in_sample": round(float(in_sample), 4),
                       "brier": round(float(brier_score_loss(y, p)), 4),
                       "brier_null": round(float(y.mean() * (1 - y.mean())), 4),
                       "calibration_slope": round(slope, 3), "observed_over_expected": round(float(y.mean() / p.mean()), 3),
                       "ece": round(ece, 4), "subgroups": sub, "calibration_deciles": calib, "thresholds": thr,
                       "tier_observed": tier_obs, "criteria_agreement": criteria_agreement(raw)},
        "odds_ratios": ors, "golden": golden,
        "benchmark": _benchmark_rows(),
        "external": _external(ext),
    }
    for path in (ROOT / "backend/artifacts/models_v1_mets/model.json", ROOT / "frontend/src/model.json"):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(model, indent=1))
    v = model["validation"]
    print(f"{VERSION}\n rows={len(d)} events={int(y.sum())}  CV AUC {v['auc']} {v['auc_ci95']}  in-sample {v['auc_in_sample']}\n"
          f" Brier {v['brier']} (null {v['brier_null']})  slope {v['calibration_slope']}  O/E {v['observed_over_expected']}  ECE {v['ece']}")
    for k, s in sub.items():
        print(f"  {k:18s} {s}")
    print(" thresholds", thr)
    print(" tiers", tier_obs)
    print(pd.DataFrame(ors).to_string(index=False))
    print(" coef", dict(zip(FEATURES, np.round(w, 5))))
    print(f" intercept shift {shift:+.4f} -> shipped intercept {b + shift:.5f}")


if __name__ == "__main__":
    main()
