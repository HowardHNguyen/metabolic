import React from "react";
import { Wifi, WifiOff } from "lucide-react";
import { MODEL_SPEC as M } from "../localModel.js";

const pct = (x, d = 0) => `${(x * 100).toFixed(d)}%`;
const signed = (x) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(3)}`;
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
const tierName = (id) => M.tiers.find((t) => t.tier === id)?.label;

export default function ModelDataTab({ predictionSource }) {
  const v = M.validation;
  const t = M.training;
  const bench = M.benchmark || [];
  const core = bench.filter((b) => b.feature_set === "core");
  const best = (fs) => bench.filter((b) => b.feature_set === fs).reduce((a, b) => (b.auc > (a?.auc ?? 0) ? b : a), null);
  const nested = core.find((b) => b.model === "lr_interact_nested");
  const ca = v.criteria_agreement;

  return (
    <div className="model-data">
      <h2 className="page-title">About the model</h2>
      <p className="driver-chart-sub">
        vitalCKM Metabolic Screen v{M.version} has two parts. The <strong>Quick Screen</strong> estimates the chance that
        you have metabolic syndrome <em>now</em>, from five things you can measure at home. The <strong>criteria check</strong>{" "}
        applies the official definition to whatever blood pressure and lab values you enter.
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
        <ul>
          {M.criteria.map((c) => <li key={c.id}><strong>{c.label}:</strong> {c.rule}</li>)}
        </ul>
        <p>
          The waist cut-points are the US ones. Some guidelines use lower cut-points for people of Asian ancestry (90 cm men,
          80 cm women); the Quick Screen accounts for this through race/ethnicity, but the criteria check uses the US
          values.
        </p>
      </div>

      <div className="model-block">
        <h3>Why the Quick Screen doesn't use blood tests</h3>
        <p>
          Three of the five criteria <em>are</em> blood tests (glucose, HDL, triglycerides). A model given those values
          would simply re-learn the definition: in the training data, counting the four criteria that were measured already
          separates people with and without metabolic syndrome with an AUC of {ca.auc_of_count.toFixed(2)}. That number
          would look impressive and mean nothing. So when you have the values, we apply the definition directly; the model is
          only used for the part that needs one, estimating the answer when you don't have a blood test.
        </p>
        <p>
          <strong>Inputs:</strong> age, sex, race/ethnicity (optional), BMI and waist. The model is a logistic regression
          with three extra terms (sex × age, sex × waist and waist²) so that waist and age can matter differently for men and
          women, matching the sex-specific cut-points.
        </p>
      </div>

      <div className="model-block info">
        <h3>How well does it work?</h3>
        <div className="model-stat-grid">
          <div className="model-stat"><div className="model-stat-label">AUC (CROSS-VALIDATED)</div><div className="model-stat-value">{v.auc.toFixed(2)}</div></div>
          <div className="model-stat"><div className="model-stat-label">95% INTERVAL</div><div className="model-stat-value">{v.auc_ci95[0].toFixed(2)}–{v.auc_ci95[1].toFixed(2)}</div></div>
          <div className="model-stat"><div className="model-stat-label">CALIBRATION SLOPE</div><div className="model-stat-value">{v.calibration_slope.toFixed(2)}</div></div>
          <div className="model-stat"><div className="model-stat-label">PREDICTED ÷ OBSERVED</div><div className="model-stat-value">{(1 / v.observed_over_expected).toFixed(2)}</div></div>
        </div>
        <p style={{ marginTop: 12 }}>
          <strong>AUC</strong> is the chance the model gives a higher estimate to a person who has metabolic syndrome than to
          one who doesn't: 0.5 is a coin flip, 1.0 is perfect. It was measured with {v.scheme}, so every person is scored by a
          model that never saw them.{nested && ` Choosing the three extra terms was itself re-done inside every training fold as a check; that scores ${nested.auc.toFixed(3)}, so the choice was not tuned to the test data.`}
        </p>
        <p>
          <strong>Calibration</strong> means the percentages match reality. We sorted everyone from lowest to highest
          estimate, cut them into ten equal groups, and compared the average estimate with the share who actually had
          metabolic syndrome:
        </p>
        <table className="model-table">
          <thead><tr><th>Group (lowest to highest)</th><th>People</th><th>Model estimated</th><th>Actually had it</th></tr></thead>
          <tbody>
            {v.calibration_deciles.map((d) => (
              <tr key={d.decile}><td>{d.decile}{d.decile === 1 ? " (lowest)" : d.decile === v.calibration_deciles.length ? " (highest)" : ""}</td><td>{d.n.toLocaleString()}</td><td>{pct(d.predicted, 1)}</td><td>{pct(d.observed, 1)}</td></tr>
            ))}
          </tbody>
        </table>
        <p style={{ marginTop: 12 }}>What each level means in practice (cross-validated):</p>
        <table className="model-table">
          <thead><tr><th>Level</th><th>Estimate</th><th>People</th><th>Actually had it</th></tr></thead>
          <tbody>
            {v.tier_observed.map((r) => {
              const tt = M.tiers.find((x) => x.tier === r.tier);
              return <tr key={r.tier}><td>{tierName(r.tier)}</td><td>{pct(tt.min)}–{pct(tt.max)}</td><td>{r.n.toLocaleString()}</td><td>{pct(r.observed)}</td></tr>;
            })}
          </tbody>
        </table>
        <p style={{ marginTop: 12 }}>
          At the "Likely" line ({pct(M.high_threshold)}), the screen picks up {pct(v.thresholds[String(M.high_threshold)].sensitivity)} of
          people who have metabolic syndrome and correctly clears {pct(v.thresholds[String(M.high_threshold)].specificity)} of those who
          don't.
        </p>
        <p style={{ marginTop: 12 }}>Results by group (ages 60–80 are the hardest to sort, because most older adults have some criteria):</p>
        <table className="model-table">
          <thead><tr><th>Group</th><th>People</th><th>With MetS</th><th>AUC</th><th>Estimated</th><th>Observed</th></tr></thead>
          <tbody>
            {Object.entries(v.subgroups).map(([name, g]) => (
              <tr key={name}><td>{name}</td><td>{g.n.toLocaleString()}</td><td>{g.events}</td><td>{g.auc.toFixed(2)}</td><td>{pct(g.predicted, 1)}</td><td>{pct(g.observed, 1)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      {core.length > 0 && (
        <div className="model-block">
          <h3>Why this model?</h3>
          <p>
            We compared logistic regression with splines, random forests, gradient-boosted trees (XGBoost, LightGBM) and a
            stacked ensemble, all on the same cross-validation folds. The last column shows each model's AUC difference from
            the deployed model with a 95% bootstrap interval. If the interval includes zero, the data cannot tell the two
            apart. The deployed model is the most accurate logistic regression; it gives exact, additive explanations, and
            it runs identically on our server and in your browser.
          </p>
          <table className="model-table">
            <thead><tr><th>Model (Quick Screen inputs)</th><th>AUC</th><th>Calibration slope</th><th>Difference vs deployed (95% interval)</th></tr></thead>
            <tbody>
              {core.map((b) => (
                <tr key={b.model} className={b.model === "lr_interact" ? "model-row-active" : ""}>
                  <td>{MODEL_NAMES[b.model] || b.model}</td><td>{b.auc.toFixed(3)}</td><td>{b.cal_slope.toFixed(2)}</td>
                  <td>{b.d_vs_dep == null ? "—" : `${signed(b.d_vs_dep)} (${signed(b.d_dep_lo)} to ${signed(b.d_dep_hi)})`}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p style={{ marginTop: 12 }}>Best AUC with each set of inputs, which shows what each kind of measurement adds:</p>
          <table className="model-table">
            <thead><tr><th>Inputs</th><th>Best model</th><th>AUC</th></tr></thead>
            <tbody>
              {Object.keys(SET_NAMES).map((fs) => {
                const b = best(fs);
                return b ? <tr key={fs}><td>{SET_NAMES[fs]}</td><td>{MODEL_NAMES[b.model] || b.model}</td><td>{b.auc.toFixed(3)}</td></tr> : null;
              })}
            </tbody>
          </table>
          <p style={{ marginTop: 12 }}>
            Uric acid and urine albumin add only a little, and few people know those values, so they aren't asked for. The last
            row is shown only to make the point above: it scores highly because it includes the definition.
          </p>
        </div>
      )}

      <div className="model-block">
        <h3>How much does each factor matter?</h3>
        <p>
          Odds ratios: how much the odds of having metabolic syndrome are multiplied by each change, with everything else at
          the survey average (95% interval from resampling). Because of the interaction terms, waist and age matter
          differently for men and women.
        </p>
        <table className="model-table">
          <thead><tr><th>Factor</th><th>Comparison</th><th>Odds ratio</th><th>95% interval</th></tr></thead>
          <tbody>
            {M.odds_ratios.map((o) => (
              <tr key={o.feature + o.unit}><td>{o.feature}</td><td>{o.unit}</td><td>×{o.or.toFixed(2)}</td><td>{o.lo.toFixed(2)}–{o.hi.toFixed(2)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="model-block">
        <h3>Training data</h3>
        <p>
          The US National Health and Nutrition Examination Survey (NHANES), 2011–2012 cycle: {t.rows_in_file.toLocaleString()} adults
          aged 20–80 with fasting labs, of whom {t.rows.toLocaleString()} had both waist and BMI measured
          ({t.excluded_missing_waist_or_bmi} without them were left out). {t.events.toLocaleString()} ({pct(t.event_rate)}) had
          metabolic syndrome. The "How you compare" percentiles use the same {t.rows_in_file.toLocaleString()} people, by sex
          and age band.
        </p>
        <p>
          <strong>How the label relates to the criteria.</strong> Blood pressure isn't in the file, so we checked the label
          against the four criteria that are:
        </p>
        <table className="model-table">
          <thead><tr><th>Measured criteria met (of 4)</th><th>People</th><th>Labelled metabolic syndrome</th></tr></thead>
          <tbody>
            {ca.rows.map((r) => (
              <tr key={r.criteria_met}><td>{r.criteria_met}</td><td>{r.n.toLocaleString()}</td><td>{r.labelled_mets.toLocaleString()} ({r.n ? pct(r.labelled_mets / r.n) : "—"})</td></tr>
            ))}
          </tbody>
        </table>
        <p style={{ marginTop: 8 }}>
          It agrees with the definition: nobody meeting 0 criteria is labelled, almost everybody meeting 3 or 4 is, and
          people with 2 are split by their (unseen) blood pressure. The few labelled with only 1 most likely qualify through
          medicine use, which the file doesn't record.
        </p>
      </div>

      <div className="model-block warn">
        <h3>Known limitations</h3>
        <ul>
          <li><strong>Current status, not a forecast.</strong> NHANES measures people once, so this screen says whether you're likely to have metabolic syndrome now. It does not predict your future risk.</li>
          <li><strong>One survey cycle, unweighted.</strong> NHANES is designed to represent the US when its survey weights are used; this extract has no weights, so the percentages and percentiles describe the survey sample, not exact national figures. Data are from 2011–12.</li>
          <li><strong>Internal validation only.</strong> All numbers come from cross-validation within this one dataset. The screen has not been tested on other populations or later NHANES cycles yet.</li>
          <li><strong>Small groups are less certain.</strong> The "Other / multiracial" group has only {v.subgroups.Other?.n ?? "a few dozen"} people, and accuracy is lower at ages 60–80 (AUC {v.subgroups["Age 60-80"].auc.toFixed(2)}).</li>
          <li><strong>Self-measured waist.</strong> NHANES staff measured waists with a standard method. Home measurements vary by a few centimetres, which shifts the estimate.</li>
          <li><strong>Not a diagnosis.</strong> Educational use only. A clinician diagnoses metabolic syndrome from measured blood pressure and fasting labs.</li>
        </ul>
      </div>
    </div>
  );
}
