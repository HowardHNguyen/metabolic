# Model benchmark: metabolic syndrome Quick Screen

NHANES 2011–12, 2,311 adults with waist and BMI, 803 with metabolic syndrome (34.7%). 5-fold × 5-repeat stratified CV; every model sees the same folds. The AUC interval and the paired differences are 1,000-sample bootstraps of the repeat-averaged predictions. Written by `ml/show_results.py` from `results/benchmark.csv`.

## Age, sex, race/ethnicity, BMI

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) |
|---|---|---|---|---|
| Logistic regression | 0.811 (0.793–0.829) | 0.1675 | 0.99 | — |
| LR + splines | 0.815 (0.797–0.833) | 0.1640 | 0.97 | +0.0045 (-0.0005 to +0.0093) |
| Random forest | 0.811 (0.794–0.830) | 0.1651 | 1.13 | +0.0013 (-0.0063 to +0.0088) |
| XGBoost | 0.807 (0.792–0.827) | 0.1673 | 0.86 | -0.0017 (-0.0096 to +0.0059) |
| LightGBM | 0.803 (0.789–0.824) | 0.1688 | 0.81 | -0.0045 (-0.0132 to +0.0042) |
| Stack LR+RF+XGB | 0.816 (0.798–0.834) | 0.1643 | 1.02 | +0.0055 (+0.0005 to +0.0103) |

## + waist: **Quick Screen inputs**

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) | Δ vs deployed (95% CI) |
|---|---|---|---|---|---|
| Logistic regression | 0.826 (0.809–0.843) | 0.1621 | 0.99 | — | -0.0062 (-0.0097 to -0.0025) |
| LR + splines | 0.828 (0.812–0.845) | 0.1589 | 0.96 | +0.0023 (-0.0024 to +0.0067) | -0.0039 (-0.0089 to +0.0008) |
| LR + 3 interaction terms (**deployed**) | 0.833 (0.816–0.849) | 0.1577 | 0.99 | +0.0062 (+0.0025 to +0.0097) | — |
| LR + terms re-selected inside each fold | 0.831 (0.815–0.848) | 0.1581 | 0.99 | +0.0052 (+0.0014 to +0.0086) | -0.0010 (-0.0021 to -0.0000) |
| Random forest | 0.833 (0.818–0.851) | 0.1551 | 1.02 | +0.0078 (+0.0010 to +0.0151) | +0.0016 (-0.0044 to +0.0079) |
| XGBoost | 0.827 (0.813–0.846) | 0.1583 | 0.87 | +0.0033 (-0.0044 to +0.0112) | -0.0029 (-0.0095 to +0.0040) |
| LightGBM | 0.824 (0.810–0.843) | 0.1598 | 0.82 | +0.0004 (-0.0078 to +0.0087) | -0.0059 (-0.0132 to +0.0019) |
| Stack LR+RF+XGB | 0.835 (0.820–0.852) | 0.1563 | 1.03 | +0.0093 (+0.0042 to +0.0148) | +0.0031 (-0.0016 to +0.0080) |

## + uric acid, log urine albumin/creatinine

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) | Δ vs deployed (95% CI) |
|---|---|---|---|---|---|
| Logistic regression | 0.836 (0.819–0.853) | 0.1580 | 0.98 | — | -0.0050 (-0.0082 to -0.0013) |
| LR + splines | 0.838 (0.822–0.854) | 0.1545 | 0.94 | +0.0026 (-0.0030 to +0.0082) | -0.0024 (-0.0073 to +0.0029) |
| LR + 3 interaction terms (**deployed**) | 0.841 (0.825–0.856) | 0.1540 | 0.98 | +0.0050 (+0.0013 to +0.0082) | — |
| LR + terms re-selected inside each fold | 0.840 (0.824–0.856) | 0.1540 | 0.98 | +0.0045 (+0.0003 to +0.0080) | -0.0004 (-0.0028 to +0.0019) |
| Random forest | 0.843 (0.827–0.859) | 0.1519 | 1.11 | +0.0076 (+0.0005 to +0.0143) | +0.0026 (-0.0038 to +0.0088) |
| XGBoost | 0.839 (0.825–0.857) | 0.1527 | 0.88 | +0.0056 (-0.0019 to +0.0132) | +0.0006 (-0.0063 to +0.0075) |
| LightGBM | 0.835 (0.823–0.855) | 0.1540 | 0.83 | +0.0034 (-0.0047 to +0.0115) | -0.0015 (-0.0089 to +0.0058) |
| Stack LR+RF+XGB | 0.845 (0.829–0.861) | 0.1523 | 1.04 | +0.0092 (+0.0040 to +0.0144) | +0.0043 (-0.0004 to +0.0091) |

## + glucose, HDL, triglycerides (these define the label, so leakage reference only)

| Model | AUC (95% CI) | Brier | Cal. slope | Δ vs plain LR (95% CI) | Δ vs deployed (95% CI) |
|---|---|---|---|---|---|
| Logistic regression | 0.913 (0.902–0.925) | 0.1121 | 0.97 | — | -0.0043 (-0.0066 to -0.0015) |
| LR + splines | 0.933 (0.925–0.944) | 0.0970 | 0.93 | +0.0208 (+0.0132 to +0.0283) | +0.0165 (+0.0093 to +0.0237) |
| LR + 3 interaction terms (**deployed**) | 0.917 (0.907–0.929) | 0.1092 | 0.98 | +0.0043 (+0.0015 to +0.0066) | — |
| LR + terms re-selected inside each fold | 0.917 (0.907–0.929) | 0.1093 | 0.98 | +0.0041 (+0.0014 to +0.0065) | -0.0001 (-0.0004 to +0.0001) |
| Random forest | 0.955 (0.949–0.963) | 0.0870 | 1.80 | +0.0420 (+0.0332 to +0.0505) | +0.0377 (+0.0294 to +0.0463) |
| XGBoost | 0.967 (0.962–0.974) | 0.0696 | 1.09 | +0.0541 (+0.0453 to +0.0628) | +0.0499 (+0.0416 to +0.0583) |
| LightGBM | 0.967 (0.962–0.974) | 0.0693 | 1.01 | +0.0548 (+0.0461 to +0.0637) | +0.0505 (+0.0422 to +0.0590) |
| Stack LR+RF+XGB | 0.965 (0.960–0.972) | 0.0741 | 1.09 | +0.0520 (+0.0438 to +0.0603) | +0.0477 (+0.0397 to +0.0559) |

## Decision

- **Deployed: logistic regression with sex × age, sex × waist and waist² terms** (AUC 0.833). It beats plain LR and matches the tree models within a few thousandths, while keeping exact additive explanations and identical results in Python and the browser.
- When the terms are chosen inside each training fold the AUC is 0.831, so selecting them added almost no optimism.
- The stack is +0.0031 AUC versus the deployed model (-0.0016 to +0.0080). That interval includes zero, so they are not distinguishable.
- Uric acid and urine albumin/creatinine add about +0.01 AUC, but few people know these values, so the screen doesn't ask for them.
- The leakage row shows why blood tests aren't model inputs: a high AUC there only re-learns the definition. The app applies the definition directly as the criteria check instead.
