"""Summaries of the three research datasets in data/research/ for the app's Research tab.

None of these feed the Quick Screen (they have no metabolic-syndrome outcome, or are animal data); the tab presents
them as VitalCKM research evidence, with the data-quality problems found in each file stated plainly.

    python ml/research_summary.py      # writes frontend/src/research.json
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "data" / "research"
OUT = ROOT / "frontend" / "src" / "research.json"


def r(x, d=3):
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else round(float(x), d)


def bh(p: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values."""
    p = np.asarray(p, float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / np.arange(1, n + 1)
    q = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(q, 0, 1)
    return out


# --------------------------------------------------------------------------- human crossover trial
TRIAL_MARKERS = {
    "HOMA": ("HOMA-IR (insulin resistance)", ""), "ins": ("Fasting insulin", "µU/mL"), "gly": ("Fasting glucose", "mmol/L"),
    "tAUC_ins": ("Insulin, meal-test total AUC", ""), "tAUC_gly": ("Glucose, meal-test total AUC", ""),
    "TG_basal": ("Fasting triglycerides", "mmol/L"), "iAUC_TG": ("Triglycerides, meal-test incremental AUC", ""),
    "HDL": ("HDL cholesterol", "mmol/L"), "LDL": ("LDL cholesterol", "mmol/L"), "TChol": ("Total cholesterol", "mmol/L"),
    "ApoB": ("Apolipoprotein B", "g/L"), "ffa": ("Free fatty acids", "µmol/L"),
    "Adiponectine": ("Adiponectin", "µg/mL"), "Adipo_IR": ("Adipo-IR", ""),
    "LBP": ("LBP (endotoxemia marker)", "µg/mL"), "sCD14": ("sCD14 (endotoxemia marker)", "µg/mL"),
}


def trial() -> dict:
    d = pd.read_excel(RES / "Metabolic_data.xlsx")
    raw_ids = d.id.nunique()
    d["id"] = d.id.str.strip()
    issues = []
    if d.id.nunique() != raw_ids:
        issues.append(f"Participant IDs: {raw_ids} distinct spellings for {d.id.nunique()} people (trailing spaces); merged.")
    # values below 5% of the column median are treated as entry/calculation errors (e.g. an AUC of 0.5 where the
    # median is ~375) and dropped from that marker's analysis
    flagged = {}
    for c in TRIAL_MARKERS:
        med = d[c].median()
        bad = d[c] < 0.05 * med
        if bad.any():
            flagged[c] = int(bad.sum())
            d.loc[bad, c] = np.nan
    if flagged:
        issues.append("Implausibly low values removed: " + ", ".join(f"{TRIAL_MARKERS[k][0]} ({v})" for k, v in flagged.items()) + ".")
    people = d.groupby("id").first()
    rows = []
    for c, (label, unit) in TRIAL_MARKERS.items():
        # change from before to after each 4-week (or similar) period, per person and arm
        w = d.pivot_table(index=["id", "Traitement"], columns="Temps", values=c)
        delta = (w[1] - w[0]).unstack("Traitement")  # columns 0 = control period, 1 = treatment period
        delta = delta.dropna()
        diff = delta[1] - delta[0]
        t = stats.ttest_rel(delta[1], delta[0]) if len(delta) > 2 else None
        wil = stats.wilcoxon(delta[1], delta[0]) if len(delta) > 5 else None
        base = d[d.Temps == 0][c]
        rows.append({"key": c, "label": label, "unit": unit, "n": int(len(delta)), "baseline_mean": r(base.mean()),
                     "change_control": r(delta[0].mean()), "change_treatment": r(delta[1].mean()),
                     "effect": r(diff.mean()), "effect_ci": [r(diff.mean() - 1.96 * diff.std(ddof=1) / np.sqrt(len(diff))),
                                                            r(diff.mean() + 1.96 * diff.std(ddof=1) / np.sqrt(len(diff)))],
                     "effect_pct_of_baseline": r(100 * diff.mean() / base.mean(), 1),
                     "p_ttest": r(t.pvalue, 4) if t else None, "p_wilcoxon": r(wil.pvalue, 4) if wil else None})
    q = bh([x["p_ttest"] for x in rows])
    for x, qq in zip(rows, q):
        x["q_bh"] = r(qq, 4)
    # responders: HOMA effect by the file's own responder flag
    homa = d.pivot_table(index=["id", "Traitement"], columns="Temps", values="HOMA")
    hd = (homa[1] - homa[0]).unstack("Traitement").dropna()
    hd["eff"] = hd[1] - hd[0]
    hd = hd.join(people.repondeur)
    resp = {str(k): {"n": int(len(g)), "homa_effect": r(g.eff.mean())} for k, g in hd.groupby("repondeur")}
    return {
        "title": "Human randomized crossover trial",
        "file": "Metabolic_data.xlsx",
        "design": "Randomized crossover: each participant completed a control period and a treatment period in random "
                  "order (sequence CT or TC), with measurements before and after each period (visits v2/v3 and v5/v6).",
        "participants": int(people.shape[0]), "men": int((people.sexe == "H").sum()), "women": int((people.sexe == "F").sum()),
        "responders": int(people.repondeur.sum()), "responder_effect": resp,
        "treatment_note": "The files do not say what the treatment was, or how 'responder' was defined.",
        "markers": rows, "issues": issues,
        "method": "Effect = (change during treatment) − (change during control), averaged over participants; paired t-test "
                  "and Wilcoxon signed-rank test, with Benjamini-Hochberg q-values across the markers. Period and carry-over "
                  "effects are not modelled.",
    }


# --------------------------------------------------------------------------- rodent experiment
def rodent() -> dict:
    bio = pd.read_excel(RES / "Baza_BIOCHIMIE_04042025.xls")
    eli = pd.read_excel(RES / "Baza_ELISA_04042025.xls")
    wt = pd.read_excel(RES / "Baza_GREUTATE_16122024.xlsx")
    cyc = pd.read_excel(RES / "Baza_Cycles_07042025.xlsx")
    issues = []
    dup = int(eli.duplicated(["Melatonin_0", "Leptin_0", "Insulin_0"]).sum())
    if dup:
        issues.append(f"ELISA day-0 values: {dup} of {len(eli)} rows repeat another animal's baseline exactly "
                      "(melatonin, leptin and insulin), so baseline values look copied between groups.")
    groups = sorted(bio.Group.unique())

    def summarise(df, cols):
        out = []
        for c in cols:
            row = {"key": c, "by_group": []}
            for gen in sorted(df.Gen.unique()) if "Gen" in df else [None]:
                sub = df if gen is None else df[df.Gen == gen]
                samples = [sub[sub.Group == g][c].dropna() for g in groups]
                p = stats.f_oneway(*samples).pvalue if all(len(s) > 1 for s in samples) else None
                kw = stats.kruskal(*samples).pvalue if all(len(s) > 1 for s in samples) else None
                ref = samples[0]
                row["by_group"].append({
                    "gen": None if gen is None else int(gen),
                    "groups": [{"group": int(g), "n": int(len(s)), "mean": r(s.mean(), 2), "sd": r(s.std(ddof=1), 2),
                                "p_vs_group1": None if g == groups[0] else r(stats.ttest_ind(s, ref, equal_var=False).pvalue, 4)}
                               for g, s in zip(groups, samples)],
                    "p_anova": r(p, 4), "p_kruskal": r(kw, 4)})
            out.append(row)
        return out

    bio_cols = ["GLUCOSE_30", "TRIGLYCERIDES_30", "CHOLESTEROL_30", "ALT_30", "AST_30", "UREA_30"]
    eli_cols = [c for c in eli.columns if c not in ("Group", "Gen")]
    days = [int(c.split("_")[1]) for c in wt.columns if c.startswith("Weight_")]
    curves = []
    for gen in sorted(wt.Gen.unique()):
        for g in groups:
            sub = wt[(wt.Gen == gen) & (wt.Group == g)]
            curves.append({"gen": int(gen), "group": int(g),
                           "mean": [r(sub[f"Weight_{x}"].mean(), 1) for x in days],
                           "sd": [r(sub[f"Weight_{x}"].std(ddof=1), 1) for x in days]})
    return {
        "title": "Preclinical rodent experiment",
        "files": ["Baza_BIOCHIMIE_04042025.xls", "Baza_ELISA_04042025.xls", "Baza_GREUTATE_16122024.xlsx",
                  "Baza_Cycles_07042025.xlsx"],
        "design": f"{len(bio)} animals in {len(groups)} groups × 2 'Gen' strata, {int(bio.groupby(['Group', 'Gen']).size().iloc[0])} per "
                  "cell. Body weight every 3 days for 30 days; serum biochemistry on day 30; melatonin, leptin and insulin "
                  f"by ELISA on days 0, 15 and 30; estrous cycles counted in {len(cyc)} animals.",
        "group_note": "The files label groups 1–4 and 'Gen' 1–2 without saying what they are. Group 1 behaves like a control "
                      "(normal glucose, regular cycles). 'Gen' may be sex or generation; only one stratum has estrous-cycle data.",
        "biochemistry": summarise(bio, bio_cols), "elisa": summarise(eli, eli_cols),
        "weight": {"days": days, "curves": curves},
        "cycles": summarise(cyc.assign(Gen=1), ["Completecycles", "Incompletecycles"]),
        "issues": issues,
        "method": "Group means ± SD; one-way ANOVA and Kruskal-Wallis across the four groups within each 'Gen' stratum; "
                  "Welch t-test of each group against group 1. Not corrected for multiple comparisons.",
    }


# --------------------------------------------------------------------------- metabolomics (Graves' disease)
def metabolomics() -> dict:
    path = RES / "Metabolic_data_harbin_medical_university.xls"
    modes = []
    top_all = []
    for sheet, mode in ((0, "positive"), (1, "negative")):
        raw = pd.read_excel(path, sheet_name=sheet, header=None)
        samples, groups = raw.iloc[1, 8:].tolist(), raw.iloc[2, 8:].tolist()
        feat = raw.iloc[3:].reset_index(drop=True)
        names = feat[1].fillna("").astype(str).replace({"nan": ""})
        vals = feat.iloc[:, 8:].apply(pd.to_numeric, errors="coerce").values
        g = np.array(groups)
        pri, eut, hc, qc = (vals[:, g == k] for k in ("Pri_GD", "Eut_GD", "HC", "QC"))
        lg = lambda x: np.log2(x + 1.0)  # noqa: E731
        t_ph = stats.ttest_ind(lg(pri), lg(hc), axis=1, equal_var=False)
        t_eh = stats.ttest_ind(lg(eut), lg(hc), axis=1, equal_var=False)
        p_ph = np.nan_to_num(t_ph.pvalue, nan=1.0)
        p_eh = np.nan_to_num(t_eh.pvalue, nan=1.0)
        q_ph, q_eh = bh(p_ph), bh(p_eh)
        fc_ph = lg(pri).mean(1) - lg(hc).mean(1)
        fc_eh = lg(eut).mean(1) - lg(hc).mean(1)
        qc_cv = np.nanmedian(qc.std(1, ddof=1) / np.where(qc.mean(1) > 0, qc.mean(1), np.nan)) * 100
        modes.append({"mode": mode, "features": int(len(feat)), "n_pri": int(pri.shape[1]), "n_eut": int(eut.shape[1]),
                      "n_hc": int(hc.shape[1]), "n_qc": int(qc.shape[1]), "qc_median_cv_pct": r(qc_cv, 1),
                      "sig_pri_vs_hc": int((q_ph < 0.05).sum()), "sig_eut_vs_hc": int((q_eh < 0.05).sum()),
                      "near_zero_pct": r(100 * float((vals[:, g != "QC"] < 0.01).mean()), 1),
                      "annotated": int((names != "").sum())})
        order = [i for i in np.argsort(p_ph) if names[i]][:40]  # named (annotated) features only
        for i in order:
            top_all.append({"mode": mode, "id": str(feat.iloc[i, 0]), "name": names[i], "mz": r(feat.iloc[i, 2], 4),
                            "log2fc_pri_vs_hc": r(fc_ph[i], 2), "q_pri_vs_hc": float(f"{q_ph[i]:.3g}"),
                            "log2fc_eut_vs_hc": r(fc_eh[i], 2), "q_eut_vs_hc": float(f"{q_eh[i]:.3g}")})
    top = sorted(top_all, key=lambda x: x["q_pri_vs_hc"])[:15]
    return {
        "title": "Serum metabolomics in Graves' disease",
        "file": "Metabolic_data_harbin_medical_university.xls",
        "source": "Supplementary Tables S9 (positive ion mode) and S10 (negative ion mode) of a published untargeted LC-MS "
                  "study from Harbin Medical University.",
        "design": "Three groups of 15: untreated (primary) Graves' disease (Pri_GD), Graves' disease after treatment back to "
                  "normal thyroid function (Eut_GD), and healthy controls (HC), plus pooled quality-control (QC) injections.",
        "modes": modes, "top": top,
        "issues": [f"Only {sum(m['annotated'] for m in modes):,} of {sum(m['features'] for m in modes):,} features carry a "
                   "metabolite name; the rest are unidentified mass/retention-time signals.",
                   "Names are database matches (annotation scores ~35–60), not confirmed identities.",
                   f"About {modes[0]['near_zero_pct']:.0f}% of sample values are essentially zero (below detection), which "
                   "makes some per-feature tests unstable.",
                   "Thyroid disease, not metabolic syndrome: shown as research context only."],
        "method": "log2(intensity + 1); Welch t-test per feature; Benjamini-Hochberg false-discovery rate within each ion "
                  "mode. Exploratory re-analysis of the published tables, not the authors' own pipeline.",
    }


def main():
    out = {"trial": trial(), "rodent": rodent(), "metabolomics": metabolomics()}
    OUT.write_text(json.dumps(out, indent=1, allow_nan=False))
    t = out["trial"]
    print("trial", t["participants"], t["issues"])
    for m in t["markers"]:
        print(f"  {m['label']:42s} effect {m['effect']} CI {m['effect_ci']} p {m['p_ttest']} q {m['q_bh']}")
    print("rodent issues", out["rodent"]["issues"])
    for b in out["rodent"]["biochemistry"]:
        print(" ", b["key"], [(x["gen"], [gg["mean"] for gg in x["groups"]], x["p_anova"]) for x in b["by_group"]])
    for m in out["metabolomics"]["modes"]:
        print(" ", m)
    for x in out["metabolomics"]["top"][:8]:
        print("  ", x)


if __name__ == "__main__":
    main()
