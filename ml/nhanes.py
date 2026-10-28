"""Build analysis datasets from the raw CDC NHANES files, with ONE metabolic-syndrome definition for every cycle.

Cycles:
  G = 2011-2012              files in data/nhanes_2011_2012/  (DEMO_G, BMX_G, BPX_G, BPQ_G, DIQ_G, GLU_G, TRIGLY_G, HDL_G, BIOPRO_G, ALB_CR_G)
  P = 2017-March 2020 (pre-pandemic)  files in data/external/  (P_DEMO, P_BMX, P_BPXO, P_BPQ, P_DIQ, P_GLU, P_TRIGLY, P_HDL, P_BIOPRO, P_ALB_CR)

Label (NCEP ATP III / 2009 harmonized; the same rule as the app's criteria check). Metabolic syndrome = 3 or more of:
  - waist >= 102 cm (men) / >= 88 cm (women)
  - triglycerides >= 150 mg/dL
  - HDL < 40 mg/dL (men) / < 50 mg/dL (women)
  - mean systolic >= 130 or mean diastolic >= 85 mmHg, OR currently taking prescribed BP medicine (BPQ050A)
  - fasting glucose >= 100 mg/dL, OR diagnosed diabetes (DIQ010) / insulin (DIQ050) / diabetes pills (DIQ070)
NHANES has no reliable question on triglyceride- or HDL-specific drugs, so those two criteria use measured values only.

Who is included: fasting subsample, aged 20-80, not pregnant, with waist, BMI, fasting glucose, triglycerides, HDL, and
blood pressure measured (or on BP medicine).

Note: 2011-12 measured BP by auscultation (mercury), 2017-20 by oscillometric device; both are averaged over the readings.

    python ml/nhanes.py      # writes data/nhanes_pooled.csv and prints the flow per cycle
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DIRS = {"G": ROOT / "data" / "nhanes_2011_2012", "P": ROOT / "data" / "external"}
NAMES = {
    "G": dict(demo="DEMO_G", bmx="BMX_G", bpx="BPX_G", bpq="BPQ_G", diq="DIQ_G", glu="GLU_G", tg="TRIGLY_G", hdl="HDL_G",
              bio="BIOPRO_G", alb="ALB_CR_G"),
    "P": dict(demo="P_DEMO", bmx="P_BMX", bpx="P_BPXO", bpq="P_BPQ", diq="P_DIQ", glu="P_GLU", tg="P_TRIGLY", hdl="P_HDL",
              bio="P_BIOPRO", alb="P_ALB_CR"),
}
LABEL = {"G": "2011-2012", "P": "2017-2020"}
RACE_MAP = {1: "MexAmerican", 2: "Hispanic", 3: "White", 4: "Black", 6: "Asian", 7: "Other"}  # RIDRETH3
OUT = ROOT / "data" / "nhanes_pooled.csv"


def _read(cycle: str, key: str) -> pd.DataFrame:
    name = NAMES[cycle][key]
    for p in DIRS[cycle].iterdir():
        if p.stem.upper() == name.upper() and p.suffix.lower() == ".xpt":
            return pd.read_sas(p, format="xport", encoding="utf-8")
    raise FileNotFoundError(f"{name}.xpt not found in {DIRS[cycle]}")


def build_cycle(cycle: str) -> tuple[pd.DataFrame, dict]:
    t = {k: _read(cycle, k) for k in NAMES[cycle]}
    wt_fast = "WTSAF2YR" if cycle == "G" else "WTSAFPRP"
    wt_mec = "WTMEC2YR" if cycle == "G" else "WTMECPRP"
    flow = {}
    d = t["demo"][["SEQN", "RIAGENDR", "RIDAGEYR", "RIDRETH3", "RIDEXPRG", wt_mec]].copy()
    flow["participants"] = len(d)
    d = d[d.RIDAGEYR.between(20, 80)]
    flow["aged 20-80"] = len(d)
    d = d[d.RIDEXPRG != 1]
    flow["not pregnant"] = len(d)
    d = d.merge(t["bmx"][["SEQN", "BMXBMI", "BMXWAIST"]], on="SEQN", how="left")
    d = d[d.BMXBMI.notna() & d.BMXWAIST.notna()]
    flow["waist and BMI"] = len(d)
    d = (d.merge(t["glu"][["SEQN", "LBXGLU", wt_fast]], on="SEQN", how="inner")
          .merge(t["tg"][["SEQN", "LBXTR"]], on="SEQN", how="left").merge(t["hdl"][["SEQN", "LBDHDD"]], on="SEQN", how="left"))
    d = d[d.LBXGLU.notna() & d.LBXTR.notna() & d.LBDHDD.notna()]
    flow["fasting glucose, TG, HDL"] = len(d)
    bp = t["bpx"]
    sy = [c for c in bp if c.startswith("BPXSY") or c.startswith("BPXOSY")]
    di = [c for c in bp if c.startswith("BPXDI") or c.startswith("BPXODI")]
    bp = bp.assign(SBP=bp[sy].mean(axis=1), DBP=bp[di].replace(0, np.nan).mean(axis=1))[["SEQN", "SBP", "DBP"]]
    d = (d.merge(bp, on="SEQN", how="left").merge(t["bpq"][["SEQN", "BPQ050A"]], on="SEQN", how="left")
          .merge(t["diq"][["SEQN", "DIQ010", "DIQ050", "DIQ070"]], on="SEQN", how="left")
          .merge(t["bio"][["SEQN", "LBXSUA"]], on="SEQN", how="left").merge(t["alb"][["SEQN", "URDACT"]], on="SEQN", how="left"))
    d["BPMEDS"] = (d.BPQ050A == 1).astype(int)
    d["DIABTX"] = ((d.DIQ010 == 1) | (d.DIQ050 == 1) | (d.DIQ070 == 1)).astype(int)
    d = d[(d.SBP.notna() & d.DBP.notna()) | (d.BPMEDS == 1)]
    flow["blood pressure (or BP medicine)"] = len(d)
    d = d[d.RIDRETH3.isin(RACE_MAP)]
    male = d.RIAGENDR == 1
    c_w = np.where(male, d.BMXWAIST >= 102, d.BMXWAIST >= 88)
    c_tg = d.LBXTR >= 150
    c_h = np.where(male, d.LBDHDD < 40, d.LBDHDD < 50)
    c_bp = ((d.SBP >= 130) | (d.DBP >= 85)).fillna(False)
    c_g = d.LBXGLU >= 100
    with_meds = c_w.astype(int) + c_tg + c_h.astype(int) + (c_bp | (d.BPMEDS == 1)).astype(int) + (c_g | (d.DIABTX == 1)).astype(int)
    measured = c_w.astype(int) + c_tg + c_h.astype(int) + c_bp.astype(int) + c_g.astype(int)
    out = pd.DataFrame({
        "seqn": d.SEQN.astype(int), "cycle": cycle, "Age": d.RIDAGEYR.astype(float), "Sex": np.where(male, "Male", "Female"),
        "Race": d.RIDRETH3.map(RACE_MAP), "WaistCirc": d.BMXWAIST, "BMI": d.BMXBMI, "UricAcid": d.LBXSUA,
        "UrAlbCr": d.URDACT, "BloodGlucose": d.LBXGLU, "HDL": d.LBDHDD, "Triglycerides": d.LBXTR,
        "SBP": d.SBP.round(1), "DBP": d.DBP.round(1), "BPMEDS": d.BPMEDS, "DIABTX": d.DIABTX,
        "MetabolicSyndrome": (with_meds >= 3).astype(int), "MetS_measured_only": (measured >= 3).astype(int),
        "weight_fasting": d[wt_fast], "weight_mec": d[wt_mec],
    }).reset_index(drop=True)
    flow["final"] = len(out)
    return out, flow


def weighted_percentiles(cycle: str = "P") -> dict:
    """Survey-weighted 1st-99th percentiles of waist/BMI (all examined adults, MEC weights) and fasting labs (fasting
    subsample, fasting weights), by sex and age band: nationally representative reference values for 'How you compare'."""
    t = {k: _read(cycle, k) for k in ("demo", "bmx", "glu", "tg", "hdl")}
    wt_fast = "WTSAF2YR" if cycle == "G" else "WTSAFPRP"
    wt_mec = "WTMEC2YR" if cycle == "G" else "WTMECPRP"
    demo = t["demo"][["SEQN", "RIAGENDR", "RIDAGEYR", "RIDEXPRG", wt_mec]]
    demo = demo[demo.RIDAGEYR.between(20, 80) & (demo.RIDEXPRG != 1)]
    body = demo.merge(t["bmx"][["SEQN", "BMXBMI", "BMXWAIST"]], on="SEQN")
    labs = (demo.merge(t["glu"][["SEQN", "LBXGLU", wt_fast]], on="SEQN").merge(t["tg"][["SEQN", "LBXTR"]], on="SEQN", how="left")
                .merge(t["hdl"][["SEQN", "LBDHDD"]], on="SEQN", how="left"))
    spec = {"WAIST": (body, "BMXWAIST", wt_mec), "BMI": (body, "BMXBMI", wt_mec), "GLUCOSE": (labs, "LBXGLU", wt_fast),
            "HDL": (labs, "LBDHDD", wt_fast), "TG": (labs, "LBXTR", wt_fast)}
    out = {}
    for sex, s in (("M", 1), ("F", 2)):
        for lo, hi in ((20, 39), (40, 59), (60, 80)):
            key = f"{sex}{lo}-{hi}"
            out[key] = {"n": {}, "q": {}}
            for var, (df, col, wcol) in spec.items():
                g = df[(df.RIAGENDR == s) & df.RIDAGEYR.between(lo, hi) & df[col].notna() & (df[wcol] > 0)]
                v, w = g[col].values, g[wcol].values
                order = np.argsort(v)
                v, w = v[order], w[order]
                cw = (np.cumsum(w) - 0.5 * w) / w.sum()
                out[key]["q"][var] = [round(float(x), 2) for x in np.interp(np.arange(1, 100) / 100, cw, v)]
                out[key]["n"][var] = int(len(g))
    return out


def main():
    frames = []
    for cycle in ("G", "P"):
        df, flow = build_cycle(cycle)
        frames.append(df)
        print(f"NHANES {LABEL[cycle]}: " + " -> ".join(f"{k} {v:,}" for k, v in flow.items()))
        print(f"   metabolic syndrome {df.MetabolicSyndrome.mean():.1%} (with medicines), {df.MetS_measured_only.mean():.1%} (measured only)")
    pooled = pd.concat(frames, ignore_index=True)
    pooled.to_csv(OUT, index=False)
    print(f"wrote {OUT.relative_to(ROOT)}: {len(pooled):,} rows")


if __name__ == "__main__":
    main()
