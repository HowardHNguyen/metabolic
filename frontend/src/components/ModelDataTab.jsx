import React from "react";
import { Wifi, WifiOff } from "lucide-react";
import { MODEL_SPEC as M } from "../localModel.js";

const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`;
const signed = (x, d = 3) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(d)}`;
const MODEL_NAMES = {
  lr: "Logistic regression (plain)", spline_lr: "Logistic regression with splines",
  lr_interact: "Logistic regression with 3 interaction terms (deployed)",
  lr_interact_nested: "Same, terms re-chosen inside each training fold",
  rf: "Random forest", xgb: "XGBoost", lgbm: "LightGBM", stack_lr_rf_xgb: "Stack: LR + RF + XGBoost",
};
const SET_NAMES = {
  no_waist: "Age, sex, race/ethnicity, BMI", core: "+ waist (the Quick Screen)",
  core_labs: "+ uric acid and urine albumin/creatinine", all_labs_leaky: "+ glucose, HDL, triglycerides (defines the label)",
};
const SURVEY = { G: "2011–12", P: "2017–20" };
const tierName = (id) => M.tiers.find((t) => t.tier === id)?.label;
const diff = (b) => (b.d_vs_dep == null ? "—" : `${signed(b.d_vs_dep, 4)} (${signed(b.d_dep_lo, 4)} to ${signed(b.d_dep_hi, 4)})`);

function Table({ head, rows }) {
  return (
    <table className="model-table">
      <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
      <tbody>{rows}</tbody>
    </table>
  );
}

export default function ModelDataTab({ predictionSource }) {
  const v = M.validation;
  const rv = v.recent;
  const t = M.training;
  const bench = M.benchmark || [];
  const core = bench.filter((b) => b.feature_set === "core");
  const best = (fs) => bench.filter((b) => b.feature_set === fs).reduce((a, b) => (b.auc > (a?.auc ?? 0) ? b : a), null);
  const nested = core.find((b) => b.model === "lr_interact_nested");
  const stack = core.find((b) => b.model === "stack_lr_rf_xgb");
  const cross = M.cross_cycle || [];
  const crossDep = (tr) => cross.find((r) => r.train === tr && r.model === "lr_interact");
  const byCycle = Object.entries(t.by_cycle);
  const ahead = core.filter((b) => b.d_dep_lo != null && b.d_dep_lo > 0);

  return (
    <div className="model-data">
      <h2 className="page-title">About the model</h2>
      <p className="driver-chart-sub">
        vitalCKM Metabolic Screen v{M.version} has two parts. The <strong>Quick Screen</strong> estimates the chance that
        you have metabolic syndrome <em>now</em>, from five things you can measure at home. The <strong>criteria check</strong>{" "}
        applies the official definition to whatever blood pressure and lab values you enter. The model is trained on{" "}
        {t.rows.toLocaleString()} adults from two US national surveys, NHANES 2011–12 and 2017–2020.
      </p>

      <div className={`model-connected ${predictionSource === "offline" ? "demo" : ""}`}>
        {predictionSource === "api" ? (
          <><Wifi size={14} /> <strong>Connected.</strong>&nbsp;Your last result came from the server.</>
        ) : predictionSource === "offline" ? (
          <><WifiOff size={14} /> <strong>Offline mode.</strong>&nbsp;Your last result was calculated on your device with the same model.</>
        ) : (
          <span>Run an assessment to see connection status.</span>
        )}
      </div>

      <div className="model-block">
        <h3>What metabolic syndrome is</h3>
        <p>
          A cluster of linked risk factors that together raise the risk of type 2 diabetes, heart disease and stroke. Under
          the NCEP ATP III / 2009 harmonized definition used here, you have it if you meet <strong>3 or more</strong> of:
        </p>
        <ul>{M.criteria.map((c) => <li key={c.id}><strong>{c.label}:</strong> {c.rule}</li>)}</ul>
        <p>
          The waist cut-points are the US ones. Some guidelines use lower cut-points for people of Asian ancestry (90 cm men,
          80 cm women); the Quick Screen accounts for this through race/ethnicity, but the criteria check uses the US values.
        </p>
      </div>

      <div className="model-block">
        <h3>Why the Quick Screen doesn't use blood tests</h3>
        <p>
          Three of the five criteria <em>are</em> blood tests (glucose, HDL, triglycerides). A model given those values would
          simply re-learn the definition: in the training data, just counting four of the criteria already separates people
          with and without metabolic syndrome with an AUC of {t.criteria_count_auc.toFixed(2)}. So when you have the values,
          we apply the definition directly; the model is only used where one is needed, estimating the answer when you don't
          have a blood test.
        </p>
        <p>
          <strong>Inputs:</strong> age, sex, race/ethnicity (optional), BMI and waist. The model is a logistic regression
          with three extra terms (sex × age, sex × waist and waist²) so that waist and age can matter differently for men and
          women, matching the sex-specific cut-points. A survey term lets 2011–12 and 2017–2020 differ in overall level; the
          live model uses the 2017–2020 level, so its percentages describe today's population.
        </p>
      </div>

      <div className="model-block info">
        <h3>How well does it work?</h3>
        <div className="model-stat-grid">
          <div className="model-stat"><div className="model-stat-label">AUC (CROSS-VALIDATED)</div><div className="model-stat-value">{v.auc.toFixed(2)}</div></div>
          <div className="model-stat"><div className="model-stat-label">95% INTERVAL</div><div className="model-stat-value">{v.auc_ci95[0].toFixed(2)}–{v.auc_ci95[1].toFixed(2)}</div></div>
          <div className="model-stat"><div className="model-stat-label">CALIBRATION SLOPE</div><div className="model-stat-value">{v.calibration_slope.toFixed(2)}</div></div>
          <div className="model-stat"><div className="model-stat-label">PREDICTED ÷ OBSERVED, 2017–20</div><div className="model-stat-value">{(1 / rv.observed_over_expected).toFixed(2)}</div></div>
        </div>
        <p style={{ marginTop: 12 }}>
          <strong>AUC</strong> is the chance the model gives a higher estimate to a person who has metabolic syndrome than to
          one who doesn't: 0.5 is a coin flip, 1.0 is perfect. It was measured with {v.scheme}, so every person is scored by a
          model that never saw them.{nested && ` Choosing the three extra terms was itself re-done inside every training fold as a check; that scores ${nested.auc.toFixed(3)}, so the choice was not tuned to the test data.`}
        </p>
        <p>
          <strong>Calibration</strong> means the percentages match reality. Here are the {rv.n.toLocaleString()} people from
          the 2017–2020 survey, the population the live model describes, sorted from lowest to highest estimate in ten equal
          groups:
        </p>
        <Table head={["Group (lowest to highest)", "People", "Model estimated", "Actually had it"]} rows={rv.calibration_deciles.map((d) => (
          <tr key={d.decile}><td>{d.decile}</td><td>{d.n.toLocaleString()}</td><td>{pct(d.predicted, 1)}</td><td>{pct(d.observed, 1)}</td></tr>
        ))} />
        <p style={{ marginTop: 12 }}>What each level means in practice (2017–2020 survey, cross-validated):</p>
        <Table head={["Level", "Estimate", "People", "Actually had it"]} rows={rv.tier_observed.map((r) => {
          const tt = M.tiers.find((x) => x.tier === r.tier);
          return <tr key={r.tier}><td>{tierName(r.tier)}</td><td>{pct(tt.min)}–{pct(tt.max)}</td><td>{r.n.toLocaleString()}</td><td>{pct(r.observed)}</td></tr>;
        })} />
        <p style={{ marginTop: 12 }}>
          At the "Likely" line ({pct(M.high_threshold)}), the screen picks up {pct(rv.thresholds[String(M.high_threshold)].sensitivity)} of
          people who have metabolic syndrome and correctly clears {pct(rv.thresholds[String(M.high_threshold)].specificity)} of those who don't.
        </p>
        <p style={{ marginTop: 12 }}>Results by group, both surveys (ages 40–80 are the hardest to sort, because most older adults have some criteria):</p>
        <Table head={["Group", "People", "With MetS", "AUC", "Estimated", "Observed"]} rows={Object.entries(v.subgroups).map(([name, g]) => (
          <tr key={name}><td>{name}</td><td>{g.n.toLocaleString()}</td><td>{g.events}</td><td>{g.auc.toFixed(2)}</td><td>{pct(g.predicted, 1)}</td><td>{pct(g.observed, 1)}</td></tr>
        ))} />
      </div>

      {cross.length > 0 && (
        <div className="model-block info">
          <h3>Tested across surveys</h3>
          <p>
            A tougher test than cross-validation: train on one survey only and score the other, years apart, with people the
            model never saw. Both directions:
          </p>
          <Table head={["Trained on → tested on", "People", "AUC (95% interval)", "Calibration slope", "Observed ÷ predicted"]}
            rows={["G", "P"].map((tr) => crossDep(tr)).filter(Boolean).map((r) => (
              <tr key={r.train}><td>{SURVEY[r.train]} → {SURVEY[r.test]}</td><td>{r.n.toLocaleString()}</td>
                <td>{r.auc.toFixed(3)} ({r.auc_lo.toFixed(3)}–{r.auc_hi.toFixed(3)})</td><td>{r.cal_slope.toFixed(2)}</td><td>{r.o_e.toFixed(2)}</td></tr>
            ))} />
          <p style={{ marginTop: 12 }}>
            Ranking carries over well in both directions. The overall level shifts only a little (observed ÷ predicted a few
            percent from 1): metabolic syndrome became more common between the surveys, but mostly because waists and BMI grew,
            which the model already accounts for. The survey term in the live model absorbs the rest, so its percentages are
            calibrated to 2017–2020.
          </p>
          <p style={{ marginTop: 12 }}>Every benchmark model, trained on 2011–12 and tested on 2017–2020:</p>
          <Table head={["Model", "AUC", "Calibration slope", "Difference vs deployed (95% interval)"]}
            rows={cross.filter((r) => r.train === "G").map((r) => (
              <tr key={r.model} className={r.model === "lr_interact" ? "model-row-active" : ""}>
                <td>{MODEL_NAMES[r.model] || r.model}</td><td>{r.auc.toFixed(3)}</td><td>{r.cal_slope.toFixed(2)}</td><td>{diff(r)}</td></tr>
            ))} />
        </div>
      )}

      {core.length > 0 && (
        <div className="model-block">
          <h3>Why this model?</h3>
          <p>
            We compared logistic regression with splines, random forests, gradient-boosted trees (XGBoost, LightGBM) and a
            stacked ensemble on the same cross-validation folds. The last column shows each model's AUC difference from the
            deployed model with a 95% bootstrap interval; if it includes zero, the data cannot tell the two apart.
          </p>
          <Table head={["Model (Quick Screen inputs)", "AUC", "Calibration slope", "Difference vs deployed (95% interval)"]}
            rows={core.map((b) => (
              <tr key={b.model} className={b.model === "lr_interact" ? "model-row-active" : ""}>
                <td>{MODEL_NAMES[b.model] || b.model}</td><td>{b.auc.toFixed(3)}</td><td>{b.cal_slope.toFixed(2)}</td><td>{diff(b)}</td></tr>
            ))} />
          <p style={{ marginTop: 12 }}>
            {ahead.length === 0
              ? "No model is distinguishably better than the deployed logistic regression. "
              : `${ahead.map((b) => MODEL_NAMES[b.model] || b.model).join(" and ")} ${ahead.length === 1 ? "is" : "are"} slightly ahead (by at most ${signed(Math.max(...ahead.map((b) => b.d_vs_dep)), 3)} AUC). `}
            We keep the logistic regression because it gives exact, additive explanations and runs identically on our server and
            in your browser, so the What-If sliders are instant and work offline{stack ? `; the stack scores ${stack.auc.toFixed(3)} against ${core.find((b) => b.model === "lr_interact")?.auc.toFixed(3)}` : ""}.
          </p>
          <p style={{ marginTop: 12 }}>Best AUC with each set of inputs, which shows what each kind of measurement adds:</p>
          <Table head={["Inputs", "Best model", "AUC"]} rows={Object.keys(SET_NAMES).map((fs) => {
            const b = best(fs);
            return b ? <tr key={fs}><td>{SET_NAMES[fs]}</td><td>{MODEL_NAMES[b.model] || b.model}</td><td>{b.auc.toFixed(3)}</td></tr> : null;
          })} />
          <p style={{ marginTop: 12 }}>
            Uric acid and urine albumin add only a little, and few people know those values, so they aren't asked for. The last
            row scores highly only because it includes the definition.
          </p>
        </div>
      )}

      <div className="model-block">
        <h3>How much does each factor matter?</h3>
        <p>
          Odds ratios: how much the odds of having metabolic syndrome are multiplied by each change, with everything else at
          the 2017–2020 average (95% interval from resampling). Because of the interaction terms, waist and age matter
          differently for men and women.
        </p>
        <Table head={["Factor", "Comparison", "Odds ratio", "95% interval"]} rows={M.odds_ratios.map((o) => (
          <tr key={o.feature + o.unit}><td>{o.feature}</td><td>{o.unit}</td><td>×{o.or.toFixed(2)}</td><td>{o.lo.toFixed(2)}–{o.hi.toFixed(2)}</td></tr>
        ))} />
      </div>

      <div className="model-block">
        <h3>Training data</h3>
        <p>
          The US National Health and Nutrition Examination Survey (NHANES), two cycles rebuilt from the official CDC files:
          adults aged 20–80 in the fasting subsample, not pregnant, with waist, BMI, fasting glucose, triglycerides, HDL and
          blood pressure (or blood-pressure medicine) measured.
        </p>
        <Table head={["Survey", "People", "Metabolic syndrome", "Without counting medicines"]} rows={byCycle.map(([name, c]) => (
          <tr key={name}><td>{name}</td><td>{c.n.toLocaleString()}</td><td>{c.events.toLocaleString()} ({pct(c.prevalence, 1)})</td><td>{pct(c.prevalence_measured_only, 1)}</td></tr>
        ))} />
        <p style={{ marginTop: 12 }}>
          <strong>Label:</strong> {t.label}, the same rule as the criteria check. Both surveys use exactly the same definition.
          NHANES has no reliable question on triglyceride- or HDL-specific medicines, so those two criteria use measured values.
        </p>
        <p>
          <strong>How you compare</strong> uses survey-weighted percentiles from NHANES 2017–2020, so they represent US
          adults of your sex and age band, not just the people in the sample.
        </p>
        <p>
          <strong>Earlier versions.</strong> {t.v1_label_finding}
        </p>
        <ul>{(M.history || []).map((h) => <li key={h.version}><strong>{h.version}</strong>: {h.note}</li>)}</ul>
      </div>

      <div className="model-block warn">
        <h3>Known limitations</h3>
        <ul>
          <li><strong>Current status, not a forecast.</strong> NHANES measures people once, so this screen says whether you're likely to have metabolic syndrome now. It does not predict your future risk.</li>
          <li><strong>US data only.</strong> Validated within and across two US national surveys, not outside the US or in clinical settings.</li>
          <li><strong>Blood-pressure methods differ.</strong> 2011–12 measured blood pressure with a cuff and stethoscope, 2017–2020 with an automatic device; readings are averaged in both.</li>
          <li><strong>Small groups are less certain.</strong> The "Other / multiracial" group has {v.subgroups.Other?.n ?? "few"} people, and accuracy is lower at ages 40–80.</li>
          <li><strong>Self-measured waist.</strong> NHANES staff measured waists with a standard method. Home measurements vary by a few centimetres, which shifts the estimate.</li>
          <li><strong>Not a diagnosis.</strong> Educational use only. A clinician diagnoses metabolic syndrome from measured blood pressure and fasting labs.</li>
        </ul>
      </div>
    </div>
  );
}
