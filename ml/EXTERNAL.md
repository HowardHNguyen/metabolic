# External validation: NHANES 2017–March 2020

Every model is trained on NHANES 2011–12 (the app's training data) and scored on adults from the 2017–March 2020 pre-pandemic cycle, none of whom were in training. Written by `ml/external_validation.py`.

## Sample

| Step | People |
|---|---|
| P_DEMO participants | 15,560 |
| aged 20-80 | 9,232 |
| not pregnant | 9,145 |
| waist and BMI measured | 7,963 |
| fasting glucose, triglycerides and HDL measured | 3,711 |
| blood pressure measured (or on BP medicine) | 3,506 |
| final external sample | 3,506 |

Metabolic syndrome (ATP III, with medicines): **43.9%**; measured values only: 37.2%. Training data (2011–12): 34.8%.

## Quick Screen inputs (age, sex, race/ethnicity, BMI, waist)

n = 3,506

| Model | AUC (95% CI) | Brier | Cal. slope | Cal.-in-the-large | O/E | ECE | Δ AUC vs deployed (95% CI) |
|---|---|---|---|---|---|---|---|
| Logistic regression (plain) | 0.838 (0.825–0.850) | 0.1679 | 1.04 | +0.226 | 1.09 | 0.063 | -0.0061 (-0.0096 to -0.0027) |
| LR + splines | 0.844 (0.832–0.856) | 0.1625 | 1.05 | +0.247 | 1.10 | 0.045 | +0.0007 (-0.0035 to +0.0047) |
| LR + 3 interaction terms (deployed) | 0.844 (0.832–0.856) | 0.1623 | 1.08 | +0.241 | 1.10 | 0.042 | — |
| LR + terms re-chosen on training data | 0.843 (0.831–0.855) | 0.1624 | 1.07 | +0.238 | 1.10 | 0.042 | -0.0004 (-0.0011 to +0.0002) |
| Random forest | 0.845 (0.832–0.858) | 0.1602 | 1.12 | +0.250 | 1.11 | 0.046 | +0.0019 (-0.0037 to +0.0071) |
| XGBoost | 0.841 (0.827–0.854) | 0.1625 | 0.95 | +0.264 | 1.10 | 0.046 | -0.0027 (-0.0086 to +0.0031) |
| LightGBM | 0.839 (0.826–0.851) | 0.1632 | 0.90 | +0.249 | 1.10 | 0.044 | -0.0048 (-0.0112 to +0.0011) |
| Stack LR+RF+XGB | 0.848 (0.835–0.860) | 0.1603 | 1.09 | +0.237 | 1.10 | 0.056 | +0.0044 (+0.0001 to +0.0084) |

Survey-weighted (fasting-subsample weights), deployed model: AUC 0.843; weighted prevalence 39.8% vs weighted mean prediction 37.3%.

## + uric acid and urine albumin/creatinine

n = 3,460

| Model | AUC (95% CI) | Brier | Cal. slope | Cal.-in-the-large | O/E | ECE | Δ AUC vs deployed (95% CI) |
|---|---|---|---|---|---|---|---|
| Logistic regression (plain) | 0.847 (0.835–0.860) | 0.1630 | 1.06 | +0.240 | 1.10 | 0.062 | -0.0070 (-0.0106 to -0.0036) |
| LR + splines | 0.854 (0.842–0.866) | 0.1575 | 1.04 | +0.258 | 1.10 | 0.044 | -0.0003 (-0.0052 to +0.0047) |
| LR + 3 interaction terms (deployed) | 0.854 (0.842–0.867) | 0.1571 | 1.10 | +0.252 | 1.10 | 0.045 | — |
| LR + terms re-chosen on training data | 0.854 (0.842–0.866) | 0.1572 | 1.09 | +0.248 | 1.10 | 0.041 | -0.0004 (-0.0026 to +0.0017) |
| Random forest | 0.858 (0.846–0.870) | 0.1552 | 1.22 | +0.256 | 1.11 | 0.052 | +0.0042 (-0.0011 to +0.0094) |
| XGBoost | 0.857 (0.845–0.869) | 0.1547 | 1.00 | +0.256 | 1.10 | 0.040 | +0.0028 (-0.0030 to +0.0086) |
| LightGBM | 0.853 (0.840–0.865) | 0.1566 | 0.92 | +0.243 | 1.09 | 0.039 | -0.0015 (-0.0077 to +0.0044) |
| Stack LR+RF+XGB | 0.861 (0.849–0.873) | 0.1542 | 1.12 | +0.233 | 1.09 | 0.056 | +0.0070 (+0.0027 to +0.0112) |

Survey-weighted (fasting-subsample weights), deployed model: AUC 0.854; weighted prevalence 39.8% vs weighted mean prediction 36.8%.

## Shipped model (1.1.0-lr-mets-quick-recal) on the new cycle

Intercept shift in the shipped model: +0.2407. AUC 0.844 (0.832–0.856), calibration slope 1.08, O/E 1.00. When the shift is non-zero it was estimated on this same sample, so O/E here is not independent evidence.

| Decile | People | Predicted | Observed |
|---|---|---|---|
| 1 | 351 | 2.0% | 1.4% |
| 2 | 351 | 8.5% | 6.0% |
| 3 | 350 | 17.4% | 15.4% |
| 4 | 351 | 28.2% | 26.5% |
| 5 | 350 | 38.7% | 37.7% |
| 6 | 351 | 49.6% | 52.4% |
| 7 | 350 | 60.0% | 63.7% |
| 8 | 351 | 69.3% | 70.9% |
| 9 | 350 | 78.0% | 78.6% |
| 10 | 351 | 87.1% | 86.0% |

| Level | People | Observed MetS |
|---|---|---|
| Unlikely (0%–15%) | 796 | 5% |
| Possible (15%–40%) | 838 | 25% |
| Likely (40%–65%) | 841 | 57% |
| Very likely (65%–100%) | 1031 | 79% |

| Group | People | With MetS | AUC | Predicted | Observed |
|---|---|---|---|---|---|
| Men | 1744 | 719 | 0.853 | 43.7% | 41.2% |
| Women | 1762 | 819 | 0.837 | 44.1% | 46.5% |
| Age 20-39 | 1031 | 247 | 0.845 | 27.7% | 24.0% |
| Age 40-59 | 1186 | 544 | 0.816 | 44.3% | 45.9% |
| Age 60-80 | 1289 | 747 | 0.824 | 56.4% | 58.0% |
| White | 1205 | 546 | 0.846 | 45.9% | 45.3% |
| Black | 894 | 380 | 0.860 | 41.9% | 42.5% |
| Asian | 431 | 146 | 0.846 | 35.1% | 33.9% |
| Hispanic | 353 | 173 | 0.841 | 49.4% | 49.0% |
| Mexican American | 436 | 204 | 0.798 | 48.8% | 46.8% |
| Other | 187 | 89 | 0.835 | 38.0% | 47.6% |

Criteria-count AUC on the new cycle (no model, BP excluded): 0.949.

Recalibrating the development model to this cycle: log-odds shift +0.241 moves O/E from 1.10 to 1.00 (slope 1.08).
