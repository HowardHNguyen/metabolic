import json
from pathlib import Path

import pytest

from app.model import MetabolicModel

ROOT = Path(__file__).resolve().parents[2]
PATH = Path(__file__).resolve().parents[1] / "artifacts" / "models_v1_mets" / "model.json"
M = MetabolicModel(PATH)
SPEC = json.loads(PATH.read_text())
BASE = dict(SEX=1, AGE=52, RACE="Black", BMI=31.0, WAIST=106)


@pytest.mark.parametrize("case", SPEC["golden"])
def test_matches_trained_sklearn_model(case):
    """Golden probabilities were produced by the scikit-learn objects in ml/train_final.py."""
    assert M.predict(case["input"]) == pytest.approx(case["p"], abs=1e-9)


def test_frontend_and_backend_load_the_same_artifact():
    assert json.loads((ROOT / "frontend/src/model.json").read_text()) == SPEC


def test_probability_orders_sensibly():
    assert M.predict({**BASE, "WAIST": 90}) < M.predict(BASE)
    assert M.predict({**BASE, "AGE": 30}) < M.predict(BASE)
    assert M.predict({**BASE, "RACE": "Asian"}) > M.predict({**BASE, "RACE": "White"})


def test_unknown_race_sits_between_the_groups():
    ps = [M.predict({**BASE, "RACE": r}) for r in SPEC["races"]]
    assert min(ps) < M.predict({**BASE, "RACE": "Unknown"}) < max(ps)


def test_explain_sums_to_probability_minus_base():
    for c in SPEC["golden"]:
        ex = M.explain(c["input"], top_k=50)
        assert sum(x["value"] for x in ex["contributions"]) == pytest.approx(M.predict(c["input"]) - ex["base_value"], abs=1e-4)


def test_tiers_cover_unit_interval_without_gaps():
    t = SPEC["tiers"]
    assert t[0]["min"] == 0 and t[-1]["max"] == 1 and all(a["max"] == b["min"] for a, b in zip(t, t[1:]))
    assert [M.category(p) for p in (0.0, 0.149, 0.15, 0.399, 0.40, 0.649, 0.65, 0.99)] == [
        "low", "low", "borderline", "borderline", "intermediate", "intermediate", "high", "high"]


def test_tiers_mean_what_their_labels_say():
    # observed prevalence inside each tier (cross-validated) must rise and sit inside the tier's own range,
    # so "Unlikely" / "Possible" / "Likely" / "Very likely" are honest descriptions
    obs = {r["tier"]: r["observed"] for r in SPEC["validation"]["tier_observed"]}
    for t in SPEC["tiers"]:
        assert t["min"] - 0.05 <= obs[t["tier"]] <= t["max"] + 0.05, t
    assert obs["low"] < obs["borderline"] < obs["intermediate"] < obs["high"]


def test_validation_claims_in_artifact_are_honest():
    v = SPEC["validation"]
    assert 0.78 < v["auc"] < 0.87 and 0.9 < v["calibration_slope"] < 1.1 and 0.95 < v["observed_over_expected"] < 1.05


def test_model_uses_no_blood_test_inputs():
    # the label is defined from glucose, HDL and triglycerides; using them would only re-learn the definition
    assert not {"GLUCOSE", "HDL", "TG", "URIC", "LOG_UACR"} & set(SPEC["features"])


def test_calibration_deciles_add_up():
    d = SPEC["validation"]["calibration_deciles"]
    assert [x["decile"] for x in d] == list(range(1, 11)) and sum(x["n"] for x in d) == SPEC["training"]["rows"]
    n = sum(x["n"] for x in d)
    assert abs(sum(x["predicted"] * x["n"] for x in d) / n - sum(x["observed"] * x["n"] for x in d) / n) < 0.01


# ---- criteria check
def crit(**kw):
    return M.criteria_check({"SEX": 1, "AGE": 50, **kw})


def status(res, cid):
    return next(c["status"] for c in res["criteria"] if c["id"] == cid)


def test_criteria_cut_points_by_sex():
    assert status(crit(WAIST=102), "waist") == "met" and status(crit(WAIST=101.9), "waist") == "not_met"
    assert status(crit(SEX=2, WAIST=88), "waist") == "met" and status(crit(SEX=2, WAIST=87.9), "waist") == "not_met"
    assert status(crit(HDL=39), "hdl") == "met" and status(crit(HDL=40), "hdl") == "not_met"
    assert status(crit(SEX=2, HDL=49), "hdl") == "met" and status(crit(SEX=2, HDL=50), "hdl") == "not_met"
    assert status(crit(TG=150), "tg") == "met" and status(crit(TG=149), "tg") == "not_met"
    assert status(crit(GLUCOSE=100), "glucose") == "met" and status(crit(GLUCOSE=99), "glucose") == "not_met"
    assert status(crit(SYSBP=130, DIABP=70), "bp") == "met" and status(crit(SYSBP=120, DIABP=85), "bp") == "met"
    assert status(crit(SYSBP=129, DIABP=84), "bp") == "not_met"


def test_medicines_count_as_met_even_without_values():
    r = crit(BPMEDS=1, DIABETES=1, TG_MEDS=1, HDL_MEDS=1)
    assert r["met"] == 4 and r["verdict"] == "meets"


def test_verdicts():
    assert crit()["verdict"] == "incomplete" and crit()["unknown"] == 5
    assert crit(WAIST=110, TG=200, HDL=30)["verdict"] == "meets"
    assert crit(WAIST=110, TG=100)["verdict"] == "incomplete"  # 1 met, 3 unknown: could still reach 3
    assert crit(WAIST=80, TG=100, HDL=60)["verdict"] == "does_not_meet"  # 3 not met: cannot reach 3 whatever BP/glucose are


def test_dataset_label_agrees_with_the_criteria():
    rows = {r["criteria_met"]: r for r in SPEC["validation"]["criteria_agreement"]["rows"]}
    assert rows[0]["labelled_mets"] == 0 and rows[4]["labelled_mets"] == rows[4]["n"]
    assert rows[3]["labelled_mets"] >= rows[3]["n"] - 2  # 3 measured criteria met = metabolic syndrome


# ---- percentiles
def test_percentiles_are_monotone_and_bounded():
    vals = [M.percentile("WAIST", w, 1, 50) for w in (60, 80, 95, 105, 120, 170)]
    assert vals == sorted(vals) and vals[0] == 1 and vals[-1] == 99


def test_percentile_group_keys():
    assert M.group_key(1, 20) == "M20-39" and M.group_key(2, 40) == "F40-59" and M.group_key(2, 80) == "F60-80"
    assert set(SPEC["percentiles"]["groups"]) == {f"{s}{a}-{b}" for s in "MF" for a, b in SPEC["percentiles"]["age_bands"]}


def test_unknown_race_contributes_nothing_to_the_explanation():
    ex = M.explain({**BASE, "RACE": "Unknown"}, top_k=50)
    assert next(c for c in ex["contributions"] if c["feature"] == "RACE")["value"] == pytest.approx(0, abs=1e-9)


def test_explanation_of_the_average_profile_is_zero():
    # interaction terms are split by exact Shapley values, so a person at the sample average has nothing to explain
    mp = SPEC["base_profile"]
    avg = {"SEX": 1 if mp["MALE"] >= 0.5 else 2, "AGE": mp["AGE"], "RACE": "Unknown", "BMI": mp["BMI"], "WAIST": mp["WAIST"]}
    ex = M.explain({**avg, "SEX": 1}, top_k=50)
    others = [c for c in ex["contributions"] if c["feature"] != "SEX"]
    assert all(abs(c["value"]) < 0.05 for c in others)


def test_no_benchmarked_model_is_credibly_better_than_the_deployed_one():
    # the Model & Data page says the deployed model ties the tree models; if a retrain makes another model's whole
    # interval clear zero, that text (and the choice of model) must be revisited
    rows = [b for b in SPEC["benchmark"] if b["feature_set"] == "core"]
    assert any(b["model"] == "lr_interact" for b in rows)
    for b in rows:
        if b["d_vs_dep"] is not None:
            assert b["d_dep_lo"] <= 0, f"{b['model']} is now credibly better than the deployed model"
