import React, { useState } from "react";
import RiskScale from "./RiskScale.jsx";
import CriteriaCard from "./CriteriaCard.jsx";
import PercentileCard from "./PercentileCard.jsx";
import { RISK_LEVELS, tierLabel } from "../constants.js";
import { MODEL_SPEC } from "../localModel.js";

const INTERPRETATION = {
  low: "Metabolic syndrome is unlikely for someone with your measurements. Keeping your waist where it is will help keep it that way.",
  borderline: "Metabolic syndrome is possible. A blood test (lipid panel and fasting glucose) and a blood-pressure check would tell you for sure.",
  intermediate: "Metabolic syndrome is likely. Ask your clinician for a lipid panel, fasting glucose and blood-pressure check to confirm, and see the Health Coach for next steps.",
  high: "Metabolic syndrome is very likely. Please book a check-up; confirming it and acting early lowers your future risk of diabetes and heart disease.",
};

const FACTOR_PREVIEW_COUNT = 3;
const FACTOR_MAX_ROWS = 8;

export default function ResultsView({ data, prediction, explanation, scenarios, onNewAssessment, onGoToCoach, onGoToVisitSummary }) {
  const [levelsOpen, setLevelsOpen] = useState(false);
  const [showAllFactors, setShowAllFactors] = useState(false);

  const level = RISK_LEVELS.find((l) => l.tier === prediction.category);
  const riskPercent = Math.round(prediction.risk_probability * 100);

  const contributions = explanation?.contributions || [];
  const factorRows = contributions.slice(0, showAllFactors ? FACTOR_MAX_ROWS : FACTOR_PREVIEW_COUNT);
  const maxAbs = Math.max(...contributions.map((c) => Math.abs(c.value)), 0.0001);

  return (
    <div className="results-view">
      <section className="page-heading">
        <p className="eyebrow">Your result</p>
        <h1 className="page-title">Your metabolic health overview</h1>
        <p className="page-subtitle">
          How likely you are to have metabolic syndrome now, which of the five criteria you meet, and how your
          measurements compare with other US adults.
        </p>
      </section>

      <section className="myrisk-dashboard">
        <article className="results-gauge-card">
          <div className="results-gauge-label">QUICK SCREEN · CHANCE OF METABOLIC SYNDROME</div>

          <div className="risk-value-row">
            <div className="risk-number">{riskPercent}%</div>
            <span className={`risk-chip ${prediction.category}`}>
              <span className="risk-chip-dot" />
              {level?.label}
            </span>
          </div>

          <RiskScale probability={prediction.risk_probability} />

          <p className="risk-plain-language">
            <strong>What this means:</strong> About {riskPercent} out of 100 US adults with your age, sex, background,
            BMI and waist size have metabolic syndrome, based on the national NHANES health surveys.
          </p>
          <p className="care-note">
            The Quick Screen uses only body measurements, no blood test. It's an estimate, not a diagnosis; the five-criteria
            check is how metabolic syndrome is actually defined.
          </p>

          <p className="results-note">{INTERPRETATION[prediction.category]}</p>

          <div className="risk-actions">
            <button className="btn-primary" type="button" onClick={onGoToCoach}>Explore my next steps</button>
            <button className="btn-secondary" type="button" onClick={onGoToVisitSummary}>Talk with my doctor</button>
          </div>

          <div className={`risk-levels-compact ${levelsOpen ? "open" : ""}`}>
            <button className="risk-levels-toggle" type="button" onClick={() => setLevelsOpen((v) => !v)}>
              How the levels work <span>⌄</span>
            </button>
            <div className="risk-levels-panel">
              {RISK_LEVELS.map((lvl) => (
                <div key={lvl.tier} className={`risk-level-row ${lvl.tier} ${prediction.category === lvl.tier ? "active" : ""}`}>
                  <span>{lvl.label}</span>
                  <strong>{lvl.range}</strong>
                </div>
              ))}
              <p className="risk-levels-note">
                {MODEL_SPEC.external ? (
                  <>About 4 in 10 US adults have metabolic syndrome. Among {MODEL_SPEC.external.n.toLocaleString()} adults in the
                  2017–2020 national survey, the share who actually had it was{" "}
                  {MODEL_SPEC.external.tiers.map((t, i, a) => `${i === a.length - 1 ? "and " : ""}${Math.round(t.observed * 100)}% in the ${t.tier} group`).join(", ")}.
                  See Model &amp; Data.</>
                ) : (
                  <>About a third of US adults have metabolic syndrome. In testing, the share who actually had it was{" "}
                  {MODEL_SPEC.validation.tier_observed.map((t, i, a) => `${i === a.length - 1 ? "and " : ""}${Math.round(t.observed * 100)}% in the ${tierLabel(t.tier)} group`).join(", ")}.
                  See Model &amp; Data.</>
                )}
              </p>
            </div>
          </div>
        </article>

        <div className="myrisk-right-stack">
          <CriteriaCard criteria={prediction.criteria} />

          {factorRows.length > 0 && (
            <article className="myrisk-side-card">
              <h2 className="section-title">What's driving your Quick Screen</h2>
              <p className="section-copy">Compared with the average adult in the survey. Red raises your estimate; green lowers it.</p>

              <div className="factor-list">
                {factorRows.map((c) => {
                  const positive = c.value >= 0;
                  const amount = Math.min(50, (Math.abs(c.value) / maxAbs) * 50);
                  return (
                    <div className="factor-row" key={c.feature}>
                      <div className="factor-name">{c.friendly_name || c.feature}</div>
                      <div className="factor-track">
                        <span className="factor-center" />
                        <span className={`factor-fill ${positive ? "raise" : "lower"}`} style={{ "--amount": `${Math.max(amount, 4)}%` }} />
                      </div>
                      <div className={`factor-impact ${positive ? "raise" : "lower"}`}>
                        {positive ? "+" : ""}
                        {(c.value * 100).toFixed(1)}pp
                      </div>
                    </div>
                  );
                })}
              </div>

              {contributions.length > FACTOR_PREVIEW_COUNT && (
                <button className="factor-toggle" type="button" onClick={() => setShowAllFactors((v) => !v)}>
                  {showAllFactors ? "Show fewer factors" : "See all factors →"}
                </button>
              )}
            </article>
          )}
        </div>
      </section>

      <section className="results-lower">
        <PercentileCard percentiles={prediction.percentiles} />

        {scenarios?.scenarios?.length > 0 && (
          <article className="suggestions myrisk-side-card">
            <h3>If you changed one thing…</h3>
            <p className="section-copy">Quick Screen estimate after each change. Use the What-If tab to try your own numbers and see which criteria would flip.</p>
            <div className="suggestions-grid">
              {scenarios.scenarios.map((s) => (
                <div className="suggestion-card" key={s.name}>
                  <div className="suggestion-title">{s.name}</div>
                  <div className="suggestion-change">{s.description}</div>
                  <div className="suggestion-result">
                    {s.risk_percent.toFixed(0)}%
                    {s.delta_pp < -0.5 && <span className="suggestion-delta"> ({s.delta_pp.toFixed(1)}pp)</span>}
                  </div>
                </div>
              ))}
            </div>
          </article>
        )}
      </section>

      <div className="new-assessment-wrap">
        <button className="btn-secondary" type="button" onClick={onNewAssessment}>
          New assessment
        </button>
      </div>
    </div>
  );
}
