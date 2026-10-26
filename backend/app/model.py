"""
Pure-Python metabolic model (no numpy / sklearn).

Two parts, both driven by artifacts/<MODEL_SUBDIR>/model.json (written by ml/train_final.py; the browser loads the same
file as frontend/src/model.json, so server and client compute identical results):

* Quick Screen: a logistic regression giving the probability that an adult currently has metabolic syndrome, from
  age, sex, race/ethnicity, BMI and waist (no blood test needed).
* Criteria check: the NCEP ATP III / harmonized definition applied directly to whatever measurements the person has
  (waist, triglycerides, HDL, blood pressure, fasting glucose, and related medicines). Rule-based, no ML.

Plus NHANES 2011-12 reference percentiles by sex and age band.
"""
from __future__ import annotations

import bisect
import json
import math
from pathlib import Path
from typing import Optional

FRIENDLY = {"AGE": "Age", "SEX": "Sex", "RACE": "Race / ethnicity", "BMI": "Body weight (BMI)", "WAIST": "Waist size"}
RACE_LABEL = {"MexAmerican": "Mexican American"}


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z)) if z >= 0 else math.exp(z) / (1.0 + math.exp(z))


def _num(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


class MetabolicModel:
    def __init__(self, path: Path):
        spec = json.loads(Path(path).read_text())
        self.spec = spec
        self.version: str = spec["version"]
        self.features: list[str] = spec["features"]
        self.intercept: float = spec["intercept"]
        self.coef: dict[str, float] = dict(zip(self.features, spec["coef"]))
        self.means: dict[str, float] = spec["train_means"]
        self.high_threshold: float = spec["high_threshold"]
        self.tiers = spec["tiers"]
        self.race_features: dict[str, str] = spec["race_features"]
        self.base_features: list[str] = spec["base_features"]
        self.terms: dict[str, dict] = spec["terms"]
        self.base_profile: dict[str, float] = spec["base_profile"]
        self.criteria = {c["id"]: c for c in spec["criteria"]}
        self.pct = spec["percentiles"]

    # -- Quick Screen -----------------------------------------------------------------
    def base_design(self, inp: dict) -> dict[str, float]:
        race = inp.get("RACE") or "Unknown"
        x = {"AGE": float(inp["AGE"]), "MALE": 1.0 if float(inp["SEX"]) == 1 else 0.0,
             "BMI": float(inp["BMI"]), "WAIST": float(inp["WAIST"])}
        for r, f in self.race_features.items():
            # race not given: each indicator takes its training mean, i.e. the average over the sample's mix
            x[f] = self.base_profile[f] if race not in self.spec["races"] else (1.0 if race == r else 0.0)
        return x

    def _with_terms(self, x: dict[str, float]) -> dict[str, float]:
        x = dict(x)
        for name, t in self.terms.items():
            x[name] = x[t["a"]] * x[t["b"]] if t["type"] == "product" else (x[t["a"]] - t["center"]) ** 2
        return x

    def design(self, inp: dict) -> dict[str, float]:
        return self._with_terms(self.base_design(inp))

    def _z(self, x: dict[str, float]) -> float:
        return self.intercept + sum(self.coef[f] * x[f] for f in self.features)

    def logit(self, inp: dict) -> float:
        return self._z(self.design(inp))

    def predict(self, inp: dict) -> float:
        return _sigmoid(self.logit(inp))

    def category(self, p: float) -> str:
        for t in self.tiers:
            if p < t["max"]:
                return t["tier"]
        return self.tiers[-1]["tier"]

    def explain(self, inp: dict, top_k: int = 8) -> dict:
        """Per-factor contribution relative to the average person in the training sample (base_profile).

        Log-odds contributions are exact Shapley values: a linear term goes to its factor; a product term c*a*b is split
        c/2*(a-ma)(b+mb) to a and c/2*(b-mb)(a+ma) to b; a square term goes to its factor. They sum exactly to
        z - z0, and are mapped to probability points with the secant slope, so they add up to (probability - base)."""
        xb = self.base_design(inp)
        m = self.base_profile
        z0, z = self._z(self._with_terms(m)), self._z(self._with_terms(xb))
        p0, p = _sigmoid(z0), _sigmoid(z)
        slope = (p - p0) / (z - z0) if abs(z - z0) > 1e-9 else p0 * (1 - p0)
        report = lambda f: "SEX" if f == "MALE" else "RACE" if f.startswith("RACE_") else f  # noqa: E731
        grouped: dict[str, float] = {}

        def put(f, v):
            grouped[report(f)] = grouped.get(report(f), 0.0) + v

        for f in self.base_features:
            put(f, self.coef[f] * (xb[f] - m[f]))
        for name, t in self.terms.items():
            c, a = self.coef[name], t["a"]
            if t["type"] == "product":
                bb = t["b"]
                put(a, c / 2 * (xb[a] - m[a]) * (xb[bb] + m[bb]))
                put(bb, c / 2 * (xb[bb] - m[bb]) * (xb[a] + m[a]))
            else:
                put(a, c * ((xb[a] - t["center"]) ** 2 - (m[a] - t["center"]) ** 2))
        race = inp.get("RACE") or "Unknown"
        value_of = {"SEX": float(inp["SEX"]), "RACE": RACE_LABEL.get(race, race)}
        out = []
        for key, c in grouped.items():
            v = c * slope
            out.append({"feature": key, "friendly_name": FRIENDLY.get(key, key), "value": round(v, 5),
                        "abs_value": round(abs(v), 5), "feature_value": value_of.get(key, xb.get(key)),
                        "direction": "increases" if v > 0 else "decreases"})
        out.sort(key=lambda c: c["abs_value"], reverse=True)
        return {"base_value": round(p0, 5), "contributions": out[:top_k]}

    # -- Criteria check ---------------------------------------------------------------
    def criteria_check(self, inp: dict) -> dict:
        """Each criterion is 'met', 'not_met' or 'unknown' (measurement not entered). Verdict: 'meets' when 3+ are met,
        'does_not_meet' when it can no longer reach 3 even if every unknown were met, else 'incomplete'."""
        male = float(inp["SEX"]) == 1
        c = self.criteria
        waist, tg, hdl = _num(inp.get("WAIST")), _num(inp.get("TG")), _num(inp.get("HDL"))
        sbp, dbp, glu = _num(inp.get("SYSBP")), _num(inp.get("DIABP")), _num(inp.get("GLUCOSE"))
        yes = lambda k: bool(_num(inp.get(k)))  # noqa: E731
        rows = []

        def add(cid, status, value, reason):
            rows.append({"id": cid, "label": c[cid]["label"], "rule": c[cid]["rule"], "status": status,
                         "value": value, "reason": reason})

        if waist is None:
            add("waist", "unknown", None, "Waist not entered")
        else:
            cut = c["waist"]["male_min"] if male else c["waist"]["female_min"]
            add("waist", "met" if waist >= cut else "not_met", waist, f"Waist {waist:g} cm vs {cut} cm")
        if yes("TG_MEDS"):
            add("tg", "met", tg, "On medicine for high triglycerides")
        elif tg is None:
            add("tg", "unknown", None, "Triglycerides not entered")
        else:
            add("tg", "met" if tg >= c["tg"]["min"] else "not_met", tg, f"Triglycerides {tg:g} vs {c['tg']['min']} mg/dL")
        if yes("HDL_MEDS"):
            add("hdl", "met", hdl, "On medicine for low HDL")
        elif hdl is None:
            add("hdl", "unknown", None, "HDL not entered")
        else:
            cut = c["hdl"]["male_below"] if male else c["hdl"]["female_below"]
            add("hdl", "met" if hdl < cut else "not_met", hdl, f"HDL {hdl:g} vs below {cut} mg/dL")
        if yes("BPMEDS"):
            add("bp", "met", sbp, "On blood-pressure medicine")
        elif sbp is None or dbp is None:
            add("bp", "unknown", None, "Blood pressure not entered")
        else:
            hit = sbp >= c["bp"]["sys_min"] or dbp >= c["bp"]["dia_min"]
            add("bp", "met" if hit else "not_met", sbp, f"Blood pressure {sbp:g}/{dbp:g} vs 130/85 mmHg")
        if yes("DIABETES"):
            add("glucose", "met", glu, "Diagnosed diabetes or on glucose-lowering medicine")
        elif glu is None:
            add("glucose", "unknown", None, "Fasting glucose not entered")
        else:
            add("glucose", "met" if glu >= c["glucose"]["min"] else "not_met", glu,
                f"Fasting glucose {glu:g} vs {c['glucose']['min']} mg/dL")
        met = sum(r["status"] == "met" for r in rows)
        unknown = sum(r["status"] == "unknown" for r in rows)
        verdict = "meets" if met >= 3 else "does_not_meet" if met + unknown < 3 else "incomplete"
        return {"criteria": rows, "met": met, "unknown": unknown, "needed": 3, "verdict": verdict}

    # -- NHANES reference percentiles -----------------------------------------------------
    def group_key(self, sex: float, age: float) -> str:
        for lo, hi in self.pct["age_bands"]:
            if age <= hi:
                break
        return f"{'M' if float(sex) == 1 else 'F'}{lo}-{hi}"

    def percentile(self, var: str, value: float, sex: float, age: float) -> Optional[int]:
        """Share (1-99) of NHANES adults of the same sex and age band with a lower value."""
        if value is None:
            return None
        q = self.pct["groups"][self.group_key(sex, age)]["q"][var]
        i = bisect.bisect_left(q, value)
        if i == 0:
            return 1
        if i >= len(q):
            return 99
        lo, hi = q[i - 1], q[i]
        frac = (value - lo) / (hi - lo) if hi > lo else 0.0
        return max(1, min(99, math.floor(i + frac + 0.5)))  # same rule as the browser (no banker's rounding)

    def percentiles(self, inp: dict) -> dict:
        sex, age = float(inp["SEX"]), float(inp["AGE"])
        out = {}
        for var in ("WAIST", "BMI", "GLUCOSE", "HDL", "TG"):
            v = _num(inp.get(var))
            if v is not None:
                out[var] = {"value": v, "percentile": self.percentile(var, v, sex, age)}
        return {"group": self.group_key(sex, age), "values": out}
