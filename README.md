# vitalCKM · Metabolic Screen

**Target: [metabolic.vitalckm.com](https://metabolic.vitalckm.com)**

A metabolic syndrome screening tool, the "M" in vitalCKM's cardiovascular-kidney-metabolic family. Sibling apps:
[cardio.vitalckm.com](https://cardio.vitalckm.com) and [ckd.vitalckm.com](https://ckd.vitalckm.com). This repository is
the full source: React frontend, FastAPI backend, the model artifact, and the research code (`ml/`) that produced and
validated it. It follows the cardio-app architecture and deploys the same way, as one container on Azure.

> ⚠️ **Educational tool, not a medical diagnosis.** It estimates and explains; it does not diagnose or replace a
> licensed clinician. The in-app **Model & Data** tab covers methodology, performance and limitations.

---

## What it does

Metabolic syndrome (MetS) means meeting **3 or more of 5** criteria (NCEP ATP III / 2009 harmonized):

1. waist ≥ 102 cm (men) / ≥ 88 cm (women)
2. triglycerides ≥ 150 mg/dL, or treated
3. HDL < 40 mg/dL (men) / < 50 mg/dL (women), or treated
4. blood pressure ≥ 130/85 mmHg, or treated
5. fasting glucose ≥ 100 mg/dL, or diabetes / glucose-lowering treatment

The app has two parts:

| | What | How |
|---|---|---|
| **Quick Screen** | Probability that you have MetS *now*, with no blood test | Logistic regression on age, sex, race/ethnicity (optional), BMI and waist |
| **Criteria check** | Which of the 5 criteria you meet | The definition applied directly to whatever values you enter. Rule-based, no ML |

**Why the model doesn't use lab values:** three criteria *are* lab values. A model given glucose, HDL and triglycerides
re-learns the definition (counting the four criteria in the data already gives AUC 0.95), and its accuracy would be
meaningless. The model is used only where one is needed: estimating the answer when there's no blood test.

### Features

- **4-step wizard**: about you (pregnancy is out of scope), body measurements (height/weight → BMI, waist in in/cm with
  a how-to-measure guide), optional BP and labs, conditions and medicines. Two-tier validation, as in cardio.
- **Results**:
  - Quick Screen % with level (Unlikely / Possible / Likely / Very likely)
  - the five-criteria card with a verdict (meets / does not meet / incomplete)
  - exact factor contributions
  - "If you changed one thing…"
  - **How you compare**: NHANES percentiles by sex and age band
- **What-If**: waist/BMI sliders move the Quick Screen; lab and BP sliders flip criteria live. Everything runs in the
  browser with the identical model.
- **Health Coach**: recommendations driven by the criteria you meet.
- **Progress** (signed in): Quick Screen %, criteria met, waist and BMI over time, with PDF export.
- **Doctor visit summary**: a printable one-pager.
- **Model & Data**: every number is read from `model.json`.
- **Research**: re-analysis of the three research datasets in `data/research/` (see below). None of them is used by the
  screen.
- **Accounts**: identical to cardio-app. bcrypt + JWT, Postgres, revocable sessions, optional Azure Communication
  Services email.

## The model

**Data (v2):** NHANES 2011–12 and 2017–March 2020, rebuilt from the CDC files by `ml/nhanes.py` →
`data/nhanes_pooled.csv` (raw files in `data/nhanes_2011_2012/` and `data/external/`).
- Fasting subsample, aged 20–80, not pregnant, with waist, BMI, fasting labs and blood pressure (or BP medicine).
- 5,757 adults: 2,251 from 2011–12 (36.8% MetS) and 3,506 from 2017–20 (43.9%).
- One label for both surveys: ATP III / harmonized, 3 of 5 criteria, with BP and diabetes medicines counted.

**Deployed:** `2.0.0-lr-mets-pooled`.
- Logistic regression on age, sex, five race/ethnicity indicators, BMI and waist, plus a survey term (`RECENT`).
- Three extra terms: sex × age, sex × waist, waist². These let waist and age act differently by sex, matching the
  sex-specific cut-points.
- `RECENT` is fixed to 1 (2017–20) and folded into the intercept, so `model.json` keeps the v1 format and the
  percentages describe today's population. The survey term itself is small (OR 1.10): most of the
  rise in prevalence is explained by bigger waists and BMI.
- Explanations are exact Shapley values of the log-odds. They are additive and identical in Python and JS.

| 5×5 stratified CV | Value |
|---|---|
| AUC, pooled | **0.853** (95% CI 0.844–0.863) |
| Calibration slope, pooled | 1.00 |
| 2017–20 people only: AUC / slope / observed ÷ expected | 0.847 / 0.98 / 1.00 |
| Observed MetS in each level (2017–20) | Unlikely 6% · Possible 27% · Likely 55% · Very likely 78% |
| Cross-survey: trained on 2011–12 → tested on 2017–20 | AUC 0.845, O/E 1.04 |
| Cross-survey: trained on 2017–20 → tested on 2011–12 | AUC 0.860, O/E 0.97 |

**Benchmark:** see [`ml/RESULTS.md`](ml/RESULTS.md) (v1: [`ml/RESULTS_v1.md`](ml/RESULTS_v1.md)).
- Compared plain LR, spline LR, LR with nested term selection, random forest, XGBoost, LightGBM and an LR+RF+XGB
  stack on four input sets, in CV and in both cross-survey directions.
- The tree models and the stack are 0.005–0.008 AUC ahead, consistently but by less than 0.01. The deployed LR is
  kept for exact explanations, identical server/browser results and the offline What-If; a test fails if the gap ever
  reaches 0.01.
- Uric acid and urine albumin/creatinine add about +0.01 AUC but few people know them, so they aren't asked for.

**History:** 1.0.0 trained on the 2011–12 Kaggle extract (whose label turned out to ignore medicines); 1.1.0 added an
intercept shift after external validation on 2017–20 ([`ml/EXTERNAL.md`](ml/EXTERNAL.md)); 2.0.0 retrains on both
surveys with one label. Saved 1.x assessments show as "earlier model" in Progress, with a Recalculate button.

**Limitations:**
- It measures current status, not a forecast.
- The model is fitted to the unweighted samples; the "How you compare" percentiles are survey-weighted (2017–20).
- Blood pressure was measured differently in the two surveys (auscultation vs oscillometric).
- No reliable NHANES question on triglyceride/HDL medicines, so those two criteria use measured values.
- Home-measured waist adds noise.

## Research datasets (`data/research/`)

Shown in the Research tab, produced by `ml/research_summary.py` → `frontend/src/research.json`.

| File | What it is | Main finding | Data issues found |
|---|---|---|---|
| `Metabolic_data.xlsx` | Human randomized crossover trial: n=30, control vs treatment, pre/post. LBP, sCD14, insulin, glucose, lipids, adiponectin | No marker changed beyond chance (all q > 0.5) | One ID spelled two ways; 6 implausible near-zero AUC values |
| `Baza_*.xls/x` (4 files) | Rodent experiment: 64 animals, 4 groups × 2 "Gen" strata. Weight, day-30 biochemistry, melatonin/leptin/insulin, estrous cycles | Groups 2–4: higher glucose, higher ALT/AST, more incomplete cycles than group 1 | 21/64 ELISA day-0 rows duplicate other animals' baselines; group meanings not documented |
| `Metabolic_data_harbin_medical_university.xls` | LC-MS metabolomics supplementary tables: Graves' disease untreated / treated / healthy, 15 each | 2,810 features differ untreated vs healthy, 3 after treatment | Only 1,563 of 14,263 features are named; names are database matches |
| `dataset_uci_ankara_city_hospital.csv` | UCI gallstone dataset (319 patients) | Not a metabolic outcome; not used | — |

## Tech stack

| Layer | Stack |
|---|---|
| Frontend | React 18 + Vite, Recharts, jsPDF + html2canvas, Lucide icons |
| Backend | FastAPI, PostgreSQL (asyncpg). The model is **pure Python** (coefficients in JSON), with no numpy or scikit-learn at runtime |
| Auth | bcrypt, JWT sessions (revocable) |
| Research | scikit-learn, XGBoost, LightGBM, SciPy (`ml/`, not shipped) |
| Deployment | One Docker container (non-root; frontend built into `backend/static/`), Azure Web App for Containers, Azure Container Registry, GitHub Actions |

## Project layout

```
metabolic/
├── Dockerfile
├── backend/
│   ├── app/main.py            # FastAPI: auth, predict, scenarios, explain, criteria, assessments, security middleware
│   ├── app/model.py           # pure-Python Quick Screen + criteria check + percentiles (reads model.json)
│   ├── artifacts/models_v1_mets/model.json
│   └── tests/                 # unit/API tests + Postgres integration tests
├── frontend/
│   ├── src/riskModel.js       # exact JS port of model.py
│   ├── src/model.json         # same artifact the API loads (tested identical)
│   ├── src/research.json      # Research tab data (ml/research_summary.py)
│   ├── src/components/        # wizard, results, criteria, percentiles, what-if, coach, progress, model & data, research, FAQ
│   └── tests/riskModel.test.mjs
├── ml/
│   ├── nhanes.py              # builds the pooled dataset + weighted percentiles from the CDC files
│   ├── common.py              # data loading, design matrix, interaction terms
│   ├── benchmark.py           # model comparison (5×5 CV, paired bootstrap)
│   ├── train_final.py         # trains + validates the deployed model, writes both model.json files
│   ├── research_summary.py    # Research tab analyses
│   └── RESULTS.md, results/
├── data/nhanes_pooled.csv              # v2 training data (ml/nhanes.py from the CDC files)
├── data/nhanes_2011_2012/, data/external/  # raw CDC NHANES files, 2011-12 and 2017-20
├── data/metabolic_syndrome.csv          # v1 training data (2011-12 extract)
├── data/research/                       # research datasets (not used by the screen)
└── .github/workflows/         # ci.yml (PR + gate), main_metabolic-app.yml (deploy)
```

## Local development

```bash
# Backend. Postgres is optional: without DATABASE_URL the screen works, but auth and history are disabled
# (the UI requires sign-in, as in cardio).
cd backend
pip install -r requirements-dev.txt
DATABASE_URL="postgresql://user:pass@localhost:5432/metabolic" JWT_SECRET="some-random-64-char-string" \
  uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal; proxies API calls to the backend above)
cd frontend && npm ci && npm run dev
```

Tests (all run in CI):

```bash
cd backend && pytest -q                                   # unit + API tests
TEST_DATABASE_URL=postgresql://... pytest -q tests/test_db_integration.py tests/test_email_integration.py
cd frontend && node --test tests/*.test.mjs               # browser model == trained model (golden values)
```

Retraining (`pip install -r ml/requirements.txt`):

```bash
python ml/nhanes.py             # rebuild data/nhanes_pooled.csv from the CDC files
python ml/benchmark.py          # model comparison + cross-survey (~30 min on 2 cores) -> ml/results/*_v2.csv
python ml/show_results.py       # -> ml/RESULTS.md
python ml/train_final.py        # retrain + validate, rewrite both model.json
python ml/research_summary.py   # rebuild the Research tab data
```

## Deployment (Azure, same pattern as cardio-app)

Every pull request runs `ci.yml`: backend tests, Postgres tests, frontend tests and build, and a Docker smoke test.
A push to `main` runs the same suite, then builds the image, pushes it to Azure Container Registry tagged with the
commit SHA, deploys it to the Web App, and smoke-tests `/health`. Build and deploy are skipped until the repository
variable `DEPLOY_ENABLED` is `true`.

### One-time Azure setup

1. **Web App:** create a Linux *Web App for Containers* named `metabolic-app`.
   - Same resource group and App Service plan as `cardio-app` is fine.
   - Turn on the system-assigned identity.
   - Give it `AcrPull` on the existing registry, or use the registry's admin credentials.
2. **Database:** create a `metabolic` database on the existing Azure Database for PostgreSQL server, with its own user.
3. **App settings** on the Web App:

   | Variable | Value |
   |---|---|
   | `WEBSITES_PORT` | `8000` |
   | `DATABASE_URL` | `postgresql://<user>:<pass>@<server>.postgres.database.azure.com:5432/metabolic?sslmode=require` |
   | `JWT_SECRET` | a new random 64+ character secret (**not** cardio's) |
   | `ARTIFACT_DIR` | `/app/artifacts` |
   | `ALLOWED_ORIGINS` | `https://metabolic.vitalckm.com` |
   | `APP_BASE_URL` | `https://metabolic.vitalckm.com` |
   | `TRUSTED_PROXY_HOPS` | `1` |
   | `EMAIL_PROVIDER`, `ACS_CONNECTION_STRING`, `EMAIL_FROM` | optional; same ACS resource as cardio works |

   Health check path: `/health`.
4. **GitHub OIDC:** create an app registration (or reuse cardio's) with a federated credential for
   `repo:HowardHNguyen/metabolic:ref:refs/heads/main`. Give it *Website Contributor* on `metabolic-app`.
5. **GitHub repository settings → Secrets and variables → Actions:**
   - variables: `DEPLOY_ENABLED=true`, `ACR_LOGIN_SERVER` (e.g. `cardiovitalckmacr-fyg7axdjd5d0aud4.azurecr.io`),
     `AZURE_WEBAPP_NAME=metabolic-app`
   - secrets: `ACR_USERNAME`, `ACR_PASSWORD`, `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`
6. **Custom domain:**
   - At your DNS provider, add `CNAME metabolic → metabolic-app.azurewebsites.net` and the `asuid.metabolic` TXT record
     Azure shows.
   - Then add the custom domain in the Web App and bind a free App Service managed certificate.
