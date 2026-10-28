"""Shared data loading and design matrix for the metabolic-syndrome models.

v2 (current): NHANES 2011-12 + 2017-March 2020 rebuilt from the raw CDC files with one label definition
              (ml/nhanes.py -> data/nhanes_pooled.csv). RECENT = 1 for the 2017-2020 cycle.
v1 (archived): the 2011-12 extract data/metabolic_syndrome.csv (label: measured values only, no medicines).
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_V1 = ROOT / "data" / "metabolic_syndrome.csv"
DATA = ROOT / "data" / "nhanes_pooled.csv"

# NHANES race/ethnicity categories in the file; White is the reference level.
RACES = ["Black", "Asian", "Hispanic", "MexAmerican", "Other"]
RACE_FEATURES = [f"RACE_{r.upper()}" for r in RACES]

FEATURE_SETS_V1 = {
    # no tape measure, no blood test
    "no_waist": ["AGE", "MALE", *RACE_FEATURES, "BMI"],
    # no blood test: the deployed Quick Screen
    "core": ["AGE", "MALE", *RACE_FEATURES, "BMI", "WAIST"],
    # core + the two non-criterion labs in the file (uric acid, urine albumin/creatinine ratio)
    "core_labs": ["AGE", "MALE", *RACE_FEATURES, "BMI", "WAIST", "URIC", "LOG_UACR"],
    # every lab, including the three that define the label (glucose, HDL, TG) - leakage reference only
    "all_labs_leaky": ["AGE", "MALE", *RACE_FEATURES, "BMI", "WAIST", "URIC", "LOG_UACR", "GLUCOSE", "HDL", "TG"],
}


# v2 adds RECENT (survey cycle 2017-2020 = 1) to every input set; the shipped model fixes RECENT = 1 (today's population)
FEATURE_SETS = {k: [*v, "RECENT"] for k, v in FEATURE_SETS_V1.items()}


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


def load(version: str = "v2") -> pd.DataFrame:
    if version == "v1":
        d = pd.read_csv(DATA_V1)
        return d[d.BMI.notna() & d.WaistCirc.notna()].reset_index(drop=True)  # complete cases for the anthropometrics
    return pd.read_csv(DATA)  # already restricted to complete waist/BMI/labs/BP by ml/nhanes.py


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
    X["RECENT"] = (d.cycle == "P").astype(float) if "cycle" in d else 0.0
    return X


def target(d: pd.DataFrame) -> np.ndarray:
    return d.MetabolicSyndrome.values.astype(int)
