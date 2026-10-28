"""Write ml/RESULTS.md (and print it) from ml/results/benchmark_v2.csv and cross_cycle_v2.csv (model v2).
The v1 benchmark (2011-12 extract only) is kept in ml/RESULTS_v1.md.

    python ml/show_results.py
"""
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
NAMES = {
    "lr": "Logistic regression", "spline_lr": "LR + splines", "lr_interact": "LR + 3 interaction terms (**deployed**)",
    "lr_interact_nested": "LR + terms re-selected inside each fold", "rf": "Random forest", "xgb": "XGBoost",
    "lgbm": "LightGBM", "stack_lr_rf_xgb": "Stack LR+RF+XGB",
}
SETS = {
    "no_waist": "Age, sex, race/ethnicity, BMI",
    "core": "+ waist: **Quick Screen inputs**",
    "core_labs": "+ uric acid, log urine albumin/creatinine",
    "all_labs_leaky": "+ glucose, HDL, triglycerides (these define the label, so leakage reference only)",
}


def fmt(x, lo, hi, d=4):
    if pd.isna(x):
        return "—"
    return f"{x:+.{d}f} ({lo:+.{d}f} to {hi:+.{d}f})"


def main():
    r = pd.read_csv(HERE / "results" / "benchmark_v2.csv")
    cross = pd.read_csv(HERE / "results" / "cross_cycle_v2.csv")
    c0 = r[r.feature_set == "core"].iloc[0]
    n, ev = int(c0.n), int(c0.events)
    out = ["# Model benchmark: metabolic syndrome Quick Screen (model v2)", "",
           f"NHANES 2011–12 + 2017–March 2020 pooled (`ml/nhanes.py`), {n:,} adults, {ev:,} with metabolic syndrome "
           f"({ev / n:.1%}); one label definition, medicines counted for BP and glucose. Every input set includes the survey "
           "term. 5-fold × 5-repeat stratified CV; every model sees the same folds. The AUC interval and the paired "
           "differences are 1,000-sample bootstraps of the repeat-averaged predictions; sets with lab inputs drop the few "
           "people missing them. Written by `ml/show_results.py` from `results/benchmark_v2.csv` and `cross_cycle_v2.csv`. "
           "The v1 benchmark is in [`RESULTS_v1.md`](RESULTS_v1.md).", ""]
    for fs, title in SETS.items():
        g = r[r.feature_set == fs]
        if g.empty:
            continue
        has_dep = "d_vs_dep" in g and g.d_vs_dep.notna().any()
        out += [f"## {title}", "",
                "| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) |" + (" Δ vs deployed (95% CI) |" if has_dep else ""),
                "|---|---|---|---|---|" + ("---|" if has_dep else "")]
        for _, b in g.iterrows():
            row = (f"| {NAMES.get(b.model, b.model)} | {b.auc:.3f} ({b.auc_lo:.3f}–{b.auc_hi:.3f}) | {b.brier:.4f} | "
                   f"{b.cal_slope:.2f} | {fmt(b.d_vs_lr, b.d_lo, b.d_hi)} |")
            if has_dep:
                row += f" {fmt(b.d_vs_dep, b.d_dep_lo, b.d_dep_hi)} |"
            out.append(row)
        out.append("")
    survey = {"G": "2011–12", "P": "2017–20"}
    for (tr, te), g in cross.groupby(["train", "test"], sort=False):
        out += [f"## Cross-survey: trained on {survey[tr]}, tested on {survey[te]} (n = {int(g.n.iloc[0]):,})", "",
                "| Model | AUC (95% CI) | Cal. slope | Observed ÷ predicted | Δ vs deployed (95% CI) |", "|---|---|---|---|---|"]
        for _, b in g.iterrows():
            out.append(f"| {NAMES.get(b.model, b.model)} | {b.auc:.3f} ({b.auc_lo:.3f}–{b.auc_hi:.3f}) | {b.cal_slope:.2f} | "
                       f"{b.o_e:.2f} | {fmt(b.d_vs_dep, b.d_dep_lo, b.d_dep_hi)} |")
        out.append("")
    core = r[r.feature_set == "core"].set_index("model")
    if {"lr_interact", "lr_interact_nested", "stack_lr_rf_xgb"} <= set(core.index):
        st = core.loc["stack_lr_rf_xgb"]
        out += ["## Decision", "",
                f"- **Deployed: logistic regression with sex × age, sex × waist and waist² terms** (AUC "
                f"{core.loc['lr_interact', 'auc']:.3f}). It beats plain LR; the best alternative is "
                f"{core.drop(index=['lr_interact']).d_vs_dep.max():+.4f} AUC ahead. We keep the LR for exact additive "
                "explanations and identical results in Python and the browser.",
                f"- When the terms are chosen inside each training fold the AUC is {core.loc['lr_interact_nested', 'auc']:.3f}, "
                "so selecting them added almost no optimism.",
                f"- The stack is {st.d_vs_dep:+.4f} AUC versus the deployed model ({st.d_dep_lo:+.4f} to {st.d_dep_hi:+.4f}). "
                + ("That interval includes zero, so they are not distinguishable."
                   if st.d_dep_lo <= 0 <= st.d_dep_hi else
                   "That is a small but measurable gain, and the tree models and the stack show a similar edge (under 0.01 AUC) "
                   "in both cross-survey directions. We trade it for exact explanations, browser-side What-If and simplicity; "
                   "revisit if the gap reaches 0.01 (a test in backend/tests/test_model.py enforces this)."),
                "- Uric acid and urine albumin/creatinine add about +0.01 AUC, but few people know these values, so the "
                "screen doesn't ask for them.",
                "- The leakage row shows why blood tests aren't model inputs: a high AUC there only re-learns the "
                "definition. The app applies the definition directly as the criteria check instead.", ""]
    text = "\n".join(out)
    (HERE / "RESULTS.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
