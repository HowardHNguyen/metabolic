# Model benchmark: metabolic syndrome Quick Screen (model v2)

NHANES 2011–12 + 2017–March 2020 pooled (`ml/nhanes.py`), 5,757 adults, 2,366 with metabolic syndrome (41.1%); one label definition, medicines counted for BP and glucose. Every input set includes the survey term. 5-fold × 5-repeat stratified CV; every model sees the same folds. The AUC interval and the paired differences are 1,000-sample bootstraps of the repeat-averaged predictions; sets with lab inputs drop the few people missing them. Written by `ml/show_results.py` from `results/benchmark_v2.csv` and `cross_cycle_v2.csv`. The v1 benchmark is in [`RESULTS_v1.md`](RESULTS_v1.md).

## Age, sex, race/ethnicity, BMI

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) |
|---|---|---|---|---|
| Logistic regression | 0.830 (0.820–0.841) | 0.1663 | 1.00 | — |
| LR + splines | 0.838 (0.828–0.848) | 0.1613 | 0.99 | +0.0076 (+0.0044 to +0.0110) |
| Random forest | 0.834 (0.825–0.845) | 0.1625 | 1.04 | +0.0046 (+0.0003 to +0.0091) |
| XGBoost | 0.834 (0.826–0.846) | 0.1625 | 0.94 | +0.0050 (+0.0010 to +0.0088) |
| LightGBM | 0.833 (0.825–0.845) | 0.1629 | 0.93 | +0.0042 (+0.0000 to +0.0082) |
| Stack LR+RF+XGB | 0.837 (0.828–0.848) | 0.1625 | 1.02 | +0.0071 (+0.0045 to +0.0098) |

## + waist: **Quick Screen inputs**

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) | Δ vs deployed (95% CI) |
|---|---|---|---|---|---|
| Logistic regression | 0.847 (0.838–0.857) | 0.1581 | 1.00 | — | -0.0057 (-0.0079 to -0.0036) |
| LR + splines | 0.852 (0.843–0.862) | 0.1541 | 0.99 | +0.0047 (+0.0020 to +0.0074) | -0.0010 (-0.0032 to +0.0010) |
| LR + 3 interaction terms (**deployed**) | 0.853 (0.844–0.863) | 0.1535 | 1.00 | +0.0057 (+0.0036 to +0.0079) | — |
| LR + terms re-selected inside each fold | 0.853 (0.845–0.863) | 0.1531 | 1.00 | +0.0063 (+0.0040 to +0.0087) | +0.0006 (-0.0004 to +0.0016) |
| Random forest | 0.858 (0.850–0.869) | 0.1494 | 1.04 | +0.0119 (+0.0077 to +0.0162) | +0.0061 (+0.0026 to +0.0095) |
| XGBoost | 0.858 (0.851–0.869) | 0.1492 | 0.96 | +0.0120 (+0.0078 to +0.0162) | +0.0063 (+0.0030 to +0.0096) |
| LightGBM | 0.857 (0.850–0.868) | 0.1495 | 0.95 | +0.0116 (+0.0075 to +0.0161) | +0.0059 (+0.0025 to +0.0093) |
| Stack LR+RF+XGB | 0.860 (0.852–0.870) | 0.1498 | 1.03 | +0.0133 (+0.0098 to +0.0167) | +0.0076 (+0.0048 to +0.0103) |

## + uric acid, log urine albumin/creatinine

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) | Δ vs deployed (95% CI) |
|---|---|---|---|---|---|
| Logistic regression | 0.856 (0.847–0.866) | 0.1534 | 0.99 | — | -0.0060 (-0.0082 to -0.0038) |
| LR + splines | 0.863 (0.854–0.873) | 0.1479 | 0.98 | +0.0073 (+0.0042 to +0.0105) | +0.0013 (-0.0013 to +0.0040) |
| LR + 3 interaction terms (**deployed**) | 0.862 (0.853–0.872) | 0.1487 | 1.00 | +0.0060 (+0.0038 to +0.0082) | — |
| LR + terms re-selected inside each fold | 0.864 (0.855–0.874) | 0.1476 | 1.00 | +0.0077 (+0.0054 to +0.0104) | +0.0018 (+0.0004 to +0.0032) |
| Random forest | 0.870 (0.862–0.880) | 0.1439 | 1.13 | +0.0143 (+0.0095 to +0.0188) | +0.0083 (+0.0044 to +0.0123) |
| XGBoost | 0.872 (0.865–0.882) | 0.1421 | 0.97 | +0.0165 (+0.0121 to +0.0210) | +0.0105 (+0.0065 to +0.0144) |
| LightGBM | 0.871 (0.864–0.881) | 0.1423 | 0.95 | +0.0161 (+0.0114 to +0.0207) | +0.0101 (+0.0059 to +0.0141) |
| Stack LR+RF+XGB | 0.872 (0.865–0.882) | 0.1432 | 1.03 | +0.0167 (+0.0128 to +0.0206) | +0.0107 (+0.0073 to +0.0141) |

## + glucose, HDL, triglycerides (these define the label, so leakage reference only)

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) | Δ vs deployed (95% CI) |
|---|---|---|---|---|---|
| Logistic regression | 0.919 (0.911–0.926) | 0.1133 | 0.99 | — | -0.0056 (-0.0075 to -0.0037) |
| LR + splines | 0.942 (0.937–0.948) | 0.0940 | 0.97 | +0.0234 (+0.0190 to +0.0277) | +0.0179 (+0.0137 to +0.0219) |
| LR + 3 interaction terms (**deployed**) | 0.924 (0.918–0.931) | 0.1091 | 1.00 | +0.0056 (+0.0037 to +0.0075) | — |
| LR + terms re-selected inside each fold | 0.925 (0.918–0.931) | 0.1090 | 1.00 | +0.0057 (+0.0039 to +0.0077) | +0.0001 (-0.0002 to +0.0005) |
| Random forest | 0.967 (0.964–0.971) | 0.0769 | 1.83 | +0.0482 (+0.0428 to +0.0539) | +0.0426 (+0.0374 to +0.0480) |
| XGBoost | 0.978 (0.975–0.981) | 0.0579 | 1.24 | +0.0590 (+0.0534 to +0.0650) | +0.0534 (+0.0482 to +0.0591) |
| LightGBM | 0.978 (0.976–0.982) | 0.0566 | 1.17 | +0.0599 (+0.0542 to +0.0661) | +0.0544 (+0.0490 to +0.0603) |
| Stack LR+RF+XGB | 0.977 (0.974–0.980) | 0.0599 | 1.06 | +0.0580 (+0.0526 to +0.0638) | +0.0525 (+0.0473 to +0.0581) |

## Cross-survey: trained on 2011–12, tested on 2017–20 (n = 3,506)

| Model | AUC (95% CI) | Cal. slope | Observed ÷ predicted | Δ vs deployed (95% CI) |
|---|---|---|---|---|
| Logistic regression | 0.838 (0.825–0.850) | 0.88 | 1.04 | -0.0070 (-0.0096 to -0.0045) |
| LR + splines | 0.845 (0.833–0.857) | 0.90 | 1.04 | +0.0004 (-0.0026 to +0.0030) |
| LR + 3 interaction terms (**deployed**) | 0.845 (0.833–0.857) | 0.93 | 1.04 | — |
| LR + terms re-selected inside each fold | 0.846 (0.833–0.858) | 0.94 | 1.04 | +0.0012 (-0.0003 to +0.0026) |
| Random forest | 0.851 (0.838–0.863) | 1.02 | 1.04 | +0.0060 (+0.0012 to +0.0105) |
| XGBoost | 0.849 (0.836–0.862) | 0.86 | 1.04 | +0.0045 (-0.0003 to +0.0090) |
| LightGBM | 0.847 (0.834–0.859) | 0.82 | 1.04 | +0.0020 (-0.0033 to +0.0070) |
| Stack LR+RF+XGB | 0.851 (0.839–0.864) | 0.97 | 1.04 | +0.0063 (+0.0029 to +0.0095) |

## Cross-survey: trained on 2017–20, tested on 2011–12 (n = 2,251)

| Model | AUC (95% CI) | Cal. slope | Observed ÷ predicted | Δ vs deployed (95% CI) |
|---|---|---|---|---|
| Logistic regression | 0.855 (0.838–0.870) | 1.10 | 0.97 | -0.0051 (-0.0086 to -0.0016) |
| LR + splines | 0.859 (0.843–0.875) | 1.02 | 0.97 | -0.0010 (-0.0041 to +0.0024) |
| LR + 3 interaction terms (**deployed**) | 0.860 (0.844–0.875) | 1.04 | 0.97 | — |
| LR + terms re-selected inside each fold | 0.860 (0.844–0.875) | 1.03 | 0.97 | -0.0001 (-0.0020 to +0.0016) |
| Random forest | 0.866 (0.851–0.881) | 1.05 | 0.96 | +0.0060 (+0.0002 to +0.0118) |
| XGBoost | 0.863 (0.847–0.878) | 0.94 | 0.96 | +0.0030 (-0.0035 to +0.0090) |
| LightGBM | 0.863 (0.847–0.877) | 0.92 | 0.97 | +0.0024 (-0.0045 to +0.0088) |
| Stack LR+RF+XGB | 0.868 (0.852–0.882) | 1.08 | 0.96 | +0.0074 (+0.0027 to +0.0119) |

## Decision

- **Deployed: logistic regression with sex × age, sex × waist and waist² terms** (AUC 0.853). It beats plain LR; the best alternative is +0.0076 AUC ahead. We keep the LR for exact additive explanations and identical results in Python and the browser.
- When the terms are chosen inside each training fold the AUC is 0.853, so selecting them added almost no optimism.
- The stack is +0.0076 AUC versus the deployed model (+0.0048 to +0.0103). That is a small but measurable gain, and the tree models and the stack show a similar edge (under 0.01 AUC) in both cross-survey directions. We trade it for exact explanations, browser-side What-If and simplicity; revisit if the gap reaches 0.01 (a test in backend/tests/test_model.py enforces this).
- Uric acid and urine albumin/creatinine add about +0.01 AUC, but few people know these values, so the screen doesn't ask for them.
- The leakage row shows why blood tests aren't model inputs: a high AUC there only re-learns the definition. The app applies the definition directly as the criteria check instead.
