"""External (temporal) validation of the Quick Screen on NHANES 2017–March 2020 (pre-pandemic, "P_" files).

Every model is trained on the full NHANES 2011–12 training data. It is then scored on adults from the 2017–2020
cycle, none of whom were in training. This answers the open question from the benchmark: on new people, does any model
(the LR+RF+XGB stack in particular) beat the deployed logistic regression?

Data: the official CDC XPT files, saved in data/external/:
    P_DEMO, P_BMX, P_BPXO, P_BPQ, P_DIQ, P_GLU, P_TRIGLY, P_HDL (required); P_BIOPRO, P_ALB_CR (optional)
    from https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/<NAME>.xpt
If a file is missing, the script tries to download it (works in Colab or any machine that can reach cdc.gov).

    python ml/external_validation.py      # -> ml/results/external_2017_2020.json and ml/EXTERNAL.md

Label: NCEP ATP III / harmonized metabolic syndrome, 3 or more of these 5 criteria:
  - waist >= 102 cm (men) / 88 cm (women)
  - triglycerides >= 150 mg/dL
  - HDL < 40 mg/dL (men) / < 50 mg/dL (women)
  - BP >= 130/85 mmHg or on BP medicine
  - fasting glucose >= 100 mg/dL, or diagnosed diabetes / on insulin or diabetes pills
How the 2011–12 training extract built its label is not documented. A sensitivity label that ignores medicines is
therefore also reported.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.request
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import optimize
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "backend"))
from benchmark import models as make_models  # noqa: E402
from common import FEATURE_SETS, RACES, RACE_FEATURES, design, load, target  # noqa: E402
from app.model import MetabolicModel  # noqa: E402

warnings.filterwarnings("ignore")
EXT = ROOT / "data" / "external"
CDC = "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/{}.xpt"
REQUIRED = ["P_DEMO", "P_BMX", "P_BPXO", "P_BPQ", "P_DIQ", "P_GLU", "P_TRIGLY", "P_HDL"]
OPTIONAL = ["P_BIOPRO", "P_ALB_CR"]
BOOT = 1000
RACE_MAP = {1: "MexAmerican", 2: "Hispanic", 3: "White", 4: "Black", 6: "Asian", 7: "Other"}  # RIDRETH3
NAMES = {"lr": "Logistic regression (plain)", "spline_lr": "LR + splines", "lr_interact": "LR + 3 interaction terms (deployed)",
         "lr_interact_nested": "LR + terms re-chosen on training data", "rf": "Random forest", "xgb": "XGBoost",
         "lgbm": "LightGBM", "stack_lr_rf_xgb": "Stack LR+RF+XGB"}


# --------------------------------------------------------------------------- data
def xpt(name: str, required: bool = True) -> pd.DataFrame | None:
    for p in [*EXT.glob(f"{name}.*"), *EXT.glob(f"{name.lower()}.*")]:
        if p.suffix.lower() == ".xpt":
            return pd.read_sas(p, format="xport", encoding="utf-8")
    EXT.mkdir(parents=True, exist_ok=True)
    try:
        dest = EXT / f"{name}.xpt"
        urllib.request.urlretrieve(CDC.format(name), dest)
        return pd.read_sas(dest, format="xport", encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        if required:
            raise SystemExit(f"{name}.xpt not found in {EXT} and could not be downloaded ({e}).")
        return None


def build() -> tuple[pd.DataFrame, dict]:
    t = {n: xpt(n) for n in REQUIRED}
    t.update({n: xpt(n, required=False) for n in OPTIONAL})
    flow = {}
    d = t["P_DEMO"][["SEQN", "RIAGENDR", "RIDAGEYR", "RIDRETH3", "RIDEXPRG"]].copy()
    flow["P_DEMO participants"] = len(d)
    d = d[d.RIDAGEYR.between(20, 80)]
    flow["aged 20-80"] = len(d)
    d = d[d.RIDEXPRG != 1]
    flow["not pregnant"] = len(d)
    d = d.merge(t["P_BMX"][["SEQN", "BMXBMI", "BMXWAIST"]], on="SEQN", how="left")
    d = d[d.BMXBMI.notna() & d.BMXWAIST.notna()]
    flow["waist and BMI measured"] = len(d)
    glu = t["P_GLU"][["SEQN", "LBXGLU", *[c for c in ["WTSAFPRP"] if c in t["P_GLU"]]]]
    d = d.merge(glu, on="SEQN", how="inner").merge(t["P_TRIGLY"][["SEQN", "LBXTR"]], on="SEQN", how="left")
    d = d.merge(t["P_HDL"][["SEQN", "LBDHDD"]], on="SEQN", how="left")
    d = d[d.LBXGLU.notna() & d.LBXTR.notna() & d.LBDHDD.notna()]
    flow["fasting glucose, triglycerides and HDL measured"] = len(d)
    bp = t["P_BPXO"]
    sys_cols = [c for c in ["BPXOSY1", "BPXOSY2", "BPXOSY3"] if c in bp]
    dia_cols = [c for c in ["BPXODI1", "BPXODI2", "BPXODI3"] if c in bp]
    bp = bp.assign(SBP=bp[sys_cols].mean(1), DBP=bp[dia_cols].mean(1))[["SEQN", "SBP", "DBP"]]
    d = d.merge(bp, on="SEQN", how="left")
    bpq = t["P_BPQ"]
    d = d.merge(bpq[["SEQN", *[c for c in ["BPQ040A", "BPQ050A"] if c in bpq]]], on="SEQN", how="left")
    diq = t["P_DIQ"]
    d = d.merge(diq[["SEQN", *[c for c in ["DIQ010", "DIQ050", "DIQ070"] if c in diq]]], on="SEQN", how="left")
    d["BPMEDS"] = (d.get("BPQ050A") == 1).astype(int)
    d["DIABTX"] = ((d.get("DIQ010") == 1) | (d.get("DIQ050") == 1) | (d.get("DIQ070") == 1)).astype(int)
    d = d[(d.SBP.notna() & d.DBP.notna()) | (d.BPMEDS == 1)]
    flow["blood pressure measured (or on BP medicine)"] = len(d)
    if t["P_BIOPRO"] is not None and "LBXSUA" in t["P_BIOPRO"]:
        d = d.merge(t["P_BIOPRO"][["SEQN", "LBXSUA"]], on="SEQN", how="left")
    if t["P_ALB_CR"] is not None and "URDACT" in t["P_ALB_CR"]:
        d = d.merge(t["P_ALB_CR"][["SEQN", "URDACT"]], on="SEQN", how="left")
    d = d[d.RIDRETH3.isin(RACE_MAP)]  # every code is mapped; guards against unexpected codes
    male = d.RIAGENDR == 1
    c_waist = np.where(male, d.BMXWAIST >= 102, d.BMXWAIST >= 88)
    c_tg = d.LBXTR >= 150
    c_hdl = np.where(male, d.LBDHDD < 40, d.LBDHDD < 50)
    bp_high = (d.SBP >= 130) | (d.DBP >= 85)
    c_glu = d.LBXGLU >= 100
    measured = c_waist.astype(int) + c_tg + c_hdl.astype(int) + bp_high.fillna(False).astype(int) + c_glu
    with_meds = (c_waist.astype(int) + c_tg + c_hdl.astype(int) + (bp_high.fillna(False) | (d.BPMEDS == 1)).astype(int)
                 + (c_glu | (d.DIABTX == 1)).astype(int))
    # file layout of the 2011-12 training extract, so common.design() can be reused unchanged
    out = pd.DataFrame({
        "seqn": d.SEQN.astype(int), "Age": d.RIDAGEYR.astype(float), "Sex": np.where(male, "Male", "Female"),
        "Race": d.RIDRETH3.map(RACE_MAP), "WaistCirc": d.BMXWAIST, "BMI": d.BMXBMI,
        "UricAcid": d.get("LBXSUA", np.nan), "UrAlbCr": d.get("URDACT", np.nan),
        "BloodGlucose": d.LBXGLU, "HDL": d.LBDHDD, "Triglycerides": d.LBXTR,
        "SBP": d.SBP, "DBP": d.DBP, "BPMEDS": d.BPMEDS, "DIABTX": d.DIABTX,
        "MetabolicSyndrome": (with_meds >= 3).astype(int), "MetS_measured_only": (measured >= 3).astype(int),
        "weight": d.get("WTSAFPRP", np.nan),
    }).reset_index(drop=True)
    flow["final external sample"] = len(out)
    return out, flow


# --------------------------------------------------------------------------- metrics
def cal_slope(y, p):
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return float(LogisticRegression(C=1e6, max_iter=1000).fit(np.log(p / (1 - p)).reshape(-1, 1), y).coef_[0, 0])


def citl(y, p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    lo = np.log(p / (1 - p))
    return float(optimize.brentq(lambda a: (1 / (1 + np.exp(-(lo + a)))).mean() - y.mean(), -10, 10))


def ece(y, p):
    q = pd.qcut(p, 10, labels=False, duplicates="drop")
    return float(sum(abs(p[q == k].mean() - y[q == k].mean()) * (q == k).sum() for k in np.unique(q)) / len(y))


def metrics(y, p, idx, ref=None, w=None):
    boot = np.array([roc_auc_score(y[i], p[i]) for i in idx])
    m = {"auc": roc_auc_score(y, p), "auc_lo": np.percentile(boot, 2.5), "auc_hi": np.percentile(boot, 97.5),
         "brier": brier_score_loss(y, p), "cal_slope": cal_slope(y, p), "citl": citl(y, p),
         "o_e": y.mean() / p.mean(), "ece": ece(y, p), "mean_pred": p.mean(), "observed": y.mean()}
    if w is not None and np.isfinite(w).all() and (w > 0).any():
        m["auc_weighted"] = roc_auc_score(y, p, sample_weight=w)
        m["observed_weighted"] = float(np.average(y, weights=w))
        m["mean_pred_weighted"] = float(np.average(p, weights=w))
    if ref is not None:
        dd = np.array([roc_auc_score(y[i], p[i]) - roc_auc_score(y[i], ref[i]) for i in idx])
        m.update(d_vs_dep=roc_auc_score(y, p) - roc_auc_score(y, ref), d_lo=np.percentile(dd, 2.5), d_hi=np.percentile(dd, 97.5))
    return {k: (round(float(v), 5) if isinstance(v, (float, np.floating)) else v) for k, v in m.items()}


# --------------------------------------------------------------------------- main
def main():
    t0 = time.time()
    ext, flow = build()
    for k, v in flow.items():
        print(f"  {k:52s} {v:6,d}")
    tr = load()
    Xtr_all, ytr = design(tr), target(tr)
    Xex_all = design(ext)
    ye = ext.MetabolicSyndrome.values
    ye_m = ext.MetS_measured_only.values
    w = ext.weight.values.astype(float)
    rng = np.random.default_rng(0)
    idx = [rng.integers(0, len(ye), len(ye)) for _ in range(BOOT)]
    spec = MetabolicModel(ROOT / "backend" / "artifacts" / "models_v1_mets" / "model.json")
    # the live app's model, computed by the app's own pure-Python code
    inp = [{"SEX": 1 if s == "Male" else 2, "AGE": a, "RACE": r, "BMI": b, "WAIST": wc}
           for s, a, r, b, wc in zip(ext.Sex, ext.Age, ext.Race, ext.BMI, ext.WaistCirc)]
    p_live = np.array([spec.predict(x) for x in inp])

    results = {"flow": flow, "n": int(len(ext)), "events": int(ye.sum()), "prevalence": round(float(ye.mean()), 4),
               "prevalence_measured_only": round(float(ye_m.mean()), 4),
               "training": {"n": int(len(tr)), "prevalence": round(float(ytr.mean()), 4)}, "sets": {}}
    preds = {}
    for fs in ["core", "core_labs"]:
        cols = FEATURE_SETS[fs]
        if Xex_all[cols].isna().any(axis=None):
            keep = ~Xex_all[cols].isna().any(axis=1).values
            if fs != "core" and keep.mean() < 0.8:
                print(f"skipping {fs}: optional lab files missing for {1 - keep.mean():.0%} of people")
                continue
        else:
            keep = np.ones(len(ext), bool)
        Xtr, Xex = Xtr_all[cols], Xex_all[cols][keep]
        y_, ym_, w_ = ye[keep], ye_m[keep], w[keep]
        idx_ = idx if keep.all() else [rng.integers(0, len(y_), len(y_)) for _ in range(BOOT)]
        preds[fs] = {}
        for name, make in make_models(cols).items():
            preds[fs][name] = make().fit(Xtr, ytr).predict_proba(Xex)[:, 1]
            print(f"  {fs:10s} {name:20s} external AUC {roc_auc_score(y_, preds[fs][name]):.4f}  ({time.time() - t0:.0f}s)")
        ref = preds[fs].get("lr_interact")
        results["sets"][fs] = {"n": int(keep.sum()), "models": {
            name: {**metrics(y_, p, idx_, None if name == "lr_interact" else ref, w_),
                   "auc_measured_only_label": round(float(roc_auc_score(ym_, p)), 5)}
            for name, p in preds[fs].items()}}

    # development model = the deployed LR refit on 2011-12 without any recalibration. The shipped model (model.json) may
    # add an intercept shift that was estimated on THIS external sample (see train_final.py), so its calibration here
    # is not independent evidence; its discrimination (AUC) is identical to the development model's.
    p_dev = preds["core"]["lr_interact"]
    shift = float(spec.spec.get("recalibration", {}).get("intercept_shift", 0.0))
    lg = lambda q: np.log(q / (1 - q))  # noqa: E731
    assert np.allclose(lg(p_dev) + shift, lg(p_live), atol=1e-7), "refit model + shift differs from the live model.json"
    p = p_live
    results["shipped"] = {"version": spec.version, "intercept_shift": shift,
                          **metrics(ye, p, idx, None, w), "auc_measured_only_label": round(float(roc_auc_score(ye_m, p)), 5)}
    # shipped model in depth (the same tables as the Model & Data tab, now on new people)
    dec = pd.qcut(p, 10, labels=False)
    deep = {
        "calibration_deciles": [{"decile": k + 1, "n": int((dec == k).sum()), "predicted": round(float(p[dec == k].mean()), 4),
                                 "observed": round(float(ye[dec == k].mean()), 4)} for k in range(10)],
        "tiers": [], "thresholds": {}, "subgroups": {},
        "criteria_count_auc": round(float(roc_auc_score(ye, (ext.WaistCirc >= np.where(ext.Sex == "Male", 102, 88)).astype(int)
                                                     + (ext.Triglycerides >= 150) + (ext.HDL < np.where(ext.Sex == "Male", 40, 50))
                                                     + (ext.BloodGlucose >= 100))), 4),
    }
    for t in spec.tiers:
        m = (p >= t["min"]) & (p < t["max"])
        deep["tiers"].append({"tier": t["label"], "range": [t["min"], t["max"]], "n": int(m.sum()),
                              "observed": round(float(ye[m].mean()), 4) if m.any() else None})
    for th in (0.15, 0.40, 0.65):
        f = p >= th
        deep["thresholds"][f"{th:g}"] = {"sensitivity": round(float((f & (ye == 1)).sum() / ye.sum()), 3),
                                         "specificity": round(float((~f & (ye == 0)).sum() / (ye == 0).sum()), 3),
                                         "ppv": round(float(ye[f].mean()), 3), "flagged": round(float(f.mean()), 3)}
    groups = {"Men": ext.Sex == "Male", "Women": ext.Sex == "Female", "Age 20-39": ext.Age < 40,
              "Age 40-59": ext.Age.between(40, 59), "Age 60-80": ext.Age >= 60,
              **{("Mexican American" if r == "MexAmerican" else r): ext.Race == r for r in ["White", *RACES]}}
    for g, mask in groups.items():
        m = mask.values
        if m.sum() >= 30 and 0 < ye[m].sum() < m.sum():
            deep["subgroups"][g] = {"n": int(m.sum()), "events": int(ye[m].sum()), "auc": round(float(roc_auc_score(ye[m], p[m])), 3),
                                    "predicted": round(float(p[m].mean()), 4), "observed": round(float(ye[m].mean()), 4)}
    # intercept shift that would recalibrate the DEVELOPMENT model to this cycle (read by train_final.py)
    a = citl(ye, p_dev)
    p_re = 1 / (1 + np.exp(-(lg(p_dev) + a)))
    deep["recalibration"] = {"intercept_shift": round(a, 4), "o_e_before": round(float(ye.mean() / p_dev.mean()), 3),
                             "o_e_after": round(float(ye.mean() / p_re.mean()), 3), "cal_slope_after": round(cal_slope(ye, p_re), 3),
                             "shift_in_shipped_model": shift}
    results["deployed"] = deep
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "external_2017_2020.json").write_text(json.dumps(results, indent=1))
    report(results)
    print(f"done in {time.time() - t0:.0f}s")


def report(r):
    def row(name, m):
        d = "—" if "d_vs_dep" not in m else f"{m['d_vs_dep']:+.4f} ({m['d_lo']:+.4f} to {m['d_hi']:+.4f})"
        return (f"| {NAMES.get(name, name)} | {m['auc']:.3f} ({m['auc_lo']:.3f}–{m['auc_hi']:.3f}) | {m['brier']:.4f} | "
                f"{m['cal_slope']:.2f} | {m['citl']:+.3f} | {m['o_e']:.2f} | {m['ece']:.3f} | {d} |")
    L = ["# External validation: NHANES 2017–March 2020", "",
         "Every model is trained on NHANES 2011–12 (the app's training data) and scored on adults from the 2017–March 2020 "
         "pre-pandemic cycle, none of whom were in training. Written by `ml/external_validation.py`.", "",
         "## Sample", "", "| Step | People |", "|---|---|"]
    L += [f"| {k} | {v:,} |" for k, v in r["flow"].items()]
    L += ["", f"Metabolic syndrome (ATP III, with medicines): **{r['prevalence']:.1%}**; measured values only: "
          f"{r['prevalence_measured_only']:.1%}. Training data (2011–12): {r['training']['prevalence']:.1%}.", ""]
    for fs, title in (("core", "Quick Screen inputs (age, sex, race/ethnicity, BMI, waist)"),
                      ("core_labs", "+ uric acid and urine albumin/creatinine")):
        if fs not in r["sets"]:
            continue
        s = r["sets"][fs]
        L += [f"## {title}", "", f"n = {s['n']:,}", "",
              "| Model | AUC (95% CI) | Brier | Cal. slope | Cal.-in-the-large | O/E | ECE | Δ AUC vs deployed (95% CI) |",
              "|---|---|---|---|---|---|---|---|"]
        L += [row(k, m) for k, m in s["models"].items()]
        dep = s["models"]["lr_interact"]
        if "auc_weighted" in dep:
            L += ["", f"Survey-weighted (fasting-subsample weights), deployed model: AUC {dep['auc_weighted']:.3f}; "
                  f"weighted prevalence {dep['observed_weighted']:.1%} vs weighted mean prediction {dep['mean_pred_weighted']:.1%}."]
        L += [""]
    d = r["deployed"]
    sh = r["shipped"]
    L += [f"## Shipped model ({sh['version']}) on the new cycle", "",
          f"Intercept shift in the shipped model: {sh['intercept_shift']:+.4f}. AUC {sh['auc']:.3f} "
          f"({sh['auc_lo']:.3f}–{sh['auc_hi']:.3f}), calibration slope {sh['cal_slope']:.2f}, O/E {sh['o_e']:.2f}. "
          "When the shift is non-zero it was estimated on this same sample, so O/E here is not independent evidence.", "",
          "| Decile | People | Predicted | Observed |", "|---|---|---|---|"]
    L += [f"| {x['decile']} | {x['n']} | {x['predicted']:.1%} | {x['observed']:.1%} |" for x in d["calibration_deciles"]]
    L += ["", "| Level | People | Observed MetS |", "|---|---|---|"]
    pct = lambda v: "—" if v is None else f"{v:.0%}"  # noqa: E731
    L += [f"| {x['tier']} ({x['range'][0]:.0%}–{x['range'][1]:.0%}) | {x['n']} | {pct(x['observed'])} |" for x in d["tiers"]]
    L += ["", "| Group | People | With MetS | AUC | Predicted | Observed |", "|---|---|---|---|---|---|"]
    L += [f"| {g} | {x['n']} | {x['events']} | {x['auc']:.3f} | {x['predicted']:.1%} | {x['observed']:.1%} |"
          for g, x in d["subgroups"].items()]
    rc = d["recalibration"]
    L += ["", f"Criteria-count AUC on the new cycle (no model, BP excluded): {d['criteria_count_auc']:.3f}.", "",
          f"Recalibrating the development model to this cycle: log-odds shift {rc['intercept_shift']:+.3f} moves O/E from "
          f"{rc['o_e_before']:.2f} to {rc['o_e_after']:.2f} (slope {rc['cal_slope_after']:.2f}).", ""]
    text = "\n".join(L)
    (HERE / "EXTERNAL.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
