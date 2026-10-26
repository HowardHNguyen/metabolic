"""Shared data loading and design matrix for the metabolic-syndrome models (NHANES 2011-12)."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "metabolic_syndrome.csv"

# NHANES race/ethnicity categories in the file; White is the reference level.
RACES = ["Black", "Asian", "Hispanic", "MexAmerican", "Other"]
RACE_FEATURES = [f"RACE_{r.upper()}" for r in RACES]

FEATURE_SETS = {
    # no tape measure, no blood test
    "no_waist": ["AGE", "MALE", *RACE_FEATURES, "BMI"],
    # no blood test: the deployed Quick Screen
    "core": ["AGE", "MALE", *RACE_FEATURES, "BMI", "WAIST"],
    # core + the two non-criterion labs in the file (uric acid, urine albumin/creatinine ratio)
    "core_labs": ["AGE", "MALE", *RACE_FEATURES, "BMI", "WAIST", "URIC", "LOG_UACR"],
    # every lab, including the three that define the label (glucose, HDL, TG) - leakage reference only
    "all_labs_leaky": ["AGE", "MALE", *RACE_FEATURES, "BMI", "WAIST", "URIC", "LOG_UACR", "GLUCOSE", "HDL", "TG"],
}


# Interaction terms of the deployed model (chosen in ml/benchmark.py; the benchmark also re-selects them inside every
# training fold to show the choice is not over-fitted). Sex-specific waist and age effects mirror the sex-specific
# waist cut-points of the criteria and the post-menopausal rise in women; WAIST2 lets the waist effect level off.
WAIST_CENTER = 98.0
INTERACTIONS = ["MALE_AGE", "MALE_WAIST", "WAIST2"]
CANDIDATE_TERMS = {
    "MALE_AGE": lambda X: X.MALE * X.AGE,
    "MALE_WAIST": lambda X: X.MALE * X.WAIST,
    "MALE_BMI": lambda X: X.MALE * X.BMI,
    "WAIST2": lambda X: (X.WAIST - WAIST_CENTER) ** 2,
    "AGE2": lambda X: (X.AGE - 50.0) ** 2,
    "AGE_WAIST": lambda X: X.AGE * X.WAIST,
}


def add_terms(X: pd.DataFrame, terms) -> pd.DataFrame:
    X = X.copy()
    for t in terms:
        X[t] = CANDIDATE_TERMS[t](X)
    return X


def load() -> pd.DataFrame:
    d = pd.read_csv(DATA)
    d = d[d.BMI.notna() & d.WaistCirc.notna()].reset_index(drop=True)  # complete cases for the anthropometrics
    return d


def design(d: pd.DataFrame) -> pd.DataFrame:
    X = pd.DataFrame(index=d.index)
    X["AGE"] = d.Age.astype(float)
    X["MALE"] = (d.Sex == "Male").astype(float)
    for r, f in zip(RACES, RACE_FEATURES):
        X[f] = (d.Race == r).astype(float)
    X["BMI"] = d.BMI.astype(float)
    X["WAIST"] = d.WaistCirc.astype(float)
    X["URIC"] = d.UricAcid.astype(float)
    X["LOG_UACR"] = np.log(d.UrAlbCr.astype(float))
    X["GLUCOSE"] = d.BloodGlucose.astype(float)
    X["HDL"] = d.HDL.astype(float)
    X["TG"] = d.Triglycerides.astype(float)
    return X


def target(d: pd.DataFrame) -> np.ndarray:
    return d.MetabolicSyndrome.values.astype(int)
