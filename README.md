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

**Data:** `data/metabolic_syndrome.csv`, NHANES 2011–2012.
- 2,401 adults aged 20–80; 2,311 with waist and BMI measured.
- 34.7% have MetS.

**Deployed:** `1.1.0-lr-mets-quick-recal`, i.e. `1.0.0` plus an intercept update to the 2017–2020 population (see below).
- Logistic regression on age, sex, five race/ethnicity indicators, BMI and waist.
- Three extra terms: sex × age, sex × waist, waist². These let waist and age act differently by sex, matching the
  sex-specific cut-points.
- Explanations are exact Shapley values of the log-odds. They are additive and identical in Python and JS.

| 5×5 stratified CV | Value |
|---|---|
| AUC | **0.833** (95% CI 0.816–0.849) |
| Calibration slope / observed ÷ expected / ECE | 0.99 / 1.00 / 0.02 |
| Observed MetS in each level | Unlikely 5% · Possible 26% · Likely 56% · Very likely 73% |
| Terms re-selected inside every training fold (nested) | AUC 0.831, so the choice is not over-fitted |

**External validation:** [`ml/EXTERNAL.md`](ml/EXTERNAL.md), produced by `ml/external_validation.py`.
- Every model was trained on 2011–12 and scored on 3,506 different adults from **NHANES 2017–March 2020**.
- Deployed model: AUC **0.844** (0.832–0.856), calibration slope 1.08.
- As developed, it under-estimated prevalence (O/E 1.10). v1.1 adds **+0.24** to the log-odds intercept, which brings
  O/E to 1.00. Ranking, odds ratios and explanations are unchanged.
- The stack is +0.004 AUC (+0.0001 to +0.0084); RF, XGBoost and LightGBM are tied. The deployed LR is kept for
  exact explanations and in-browser What-If.
- The CDC files are in `data/external/`. The next step is retraining on both surveys with one label definition.

**Benchmark:** see [`ml/RESULTS.md`](ml/RESULTS.md).
- Compared plain LR, spline LR, random forest, XGBoost, LightGBM and an LR+RF+XGB stack on four input sets.
- The interaction LR closes most of the gap to the tree models. The remaining stack advantage is shown with its
  interval on the Model & Data page.
- Uric acid and urine albumin/creatinine add about +0.01 AUC but few people know them, so they aren't asked for.

**Limitations:**
- It measures current status, not a forecast.
- One unweighted survey cycle, so percentages describe the sample, not exact national figures.
- Validated on one later US survey (2017–2020); the intercept update was estimated on that same sample.
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
│   ├── common.py              # data loading, design matrix, interaction terms
│   ├── benchmark.py           # model comparison (5×5 CV, paired bootstrap)
│   ├── train_final.py         # trains + validates the deployed model, writes both model.json files
│   ├── research_summary.py    # Research tab analyses
│   └── RESULTS.md, results/
├── data/metabolic_syndrome.csv          # NHANES 2011-12 training data
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
python ml/benchmark.py          # model comparison (~10 min on 2 cores) -> ml/results/benchmark.csv
python ml/external_validation.py  # external check on NHANES 2017-2020 (data/external/) -> ml/EXTERNAL.md
python ml/train_final.py        # retrain + validate + apply the external intercept update, rewrite both model.json
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
