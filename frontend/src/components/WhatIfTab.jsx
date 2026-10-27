import React, { useMemo, useState } from "react";
import { SLIDER_FIELDS, LAB_SLIDERS, COUNTERFACTUALS, buildCombinedScenario } from "../constants.js";
import { MODEL } from "../localModel.js";
import CriteriaCard from "./CriteriaCard.jsx";

// Everything here runs in the browser with the same model the API serves (verified against golden values in CI),
// so sliders respond instantly and make no network calls.
const riskOf = (values) => MODEL.result(values).risk_percent;

export default function WhatIfTab({ baseline, baselinePrediction }) {
  const startValues = () => {
    const initial = {};
    SLIDER_FIELDS.forEach((f) => (initial[f.key] = Number(baseline[f.key])));
    LAB_SLIDERS.forEach((f) => (initial[f.key] = baseline[f.key] === undefined ? null : Number(baseline[f.key])));
    return initial;
  };
  const [adjusted, setAdjusted] = useState(startValues);

  const current = useMemo(() => {
    const c = { ...baseline };
    Object.entries(adjusted).forEach(([k, v]) => {
      if (v === null) delete c[k];
      else c[k] = v;
    });
    // the systolic slider keeps the diastolic below it; a lab the person didn't enter stays "not entered"
    if (c.SYSBP !== undefined && c.DIABP !== undefined && c.DIABP >= c.SYSBP) c.DIABP = c.SYSBP - 1;
    return c;
  }, [baseline, adjusted]);

  const adjustedRisk = riskOf(current);
  const criteria = useMemo(() => MODEL.criteriaCheck(current), [current]);

  const { counterfactuals, maxImpact } = useMemo(() => {
    const compare = riskOf(current);
    const rows = COUNTERFACTUALS.filter((cf) => cf.onlyIf(current)).map((cf) => {
      const newRisk = riskOf({ ...current, [cf.key]: cf.target(current) });
      return { label: cf.label, reduction: compare - newRisk, newRisk };
    });
    const combined = riskOf(buildCombinedScenario(current));
    if (rows.length > 1) rows.push({ label: "Low-risk waist and BMI down 2 together", reduction: compare - combined, newRisk: combined });
    const cleaned = rows.map((r) => ({ ...r, reduction: Math.max(0, r.reduction) })).sort((a, b) => b.reduction - a.reduction);
    return { counterfactuals: cleaned, maxImpact: Math.max(...cleaned.map((r) => r.reduction), 0.0001) };
  }, [current]);

  const delta = baselinePrediction.risk_percent - adjustedRisk;
  const labFields = LAB_SLIDERS.filter((f) => adjusted[f.key] !== null);
  const missingLabs = LAB_SLIDERS.filter((f) => adjusted[f.key] === null);

  const slider = (f) => (
    <div className="whatif-slider" key={f.key}>
      <div className="whatif-slider-label">
        <span>{f.label}</span>
        <span className="whatif-slider-value">
          {adjusted[f.key]} {f.unit}
          {f.key === "WAIST" && <span className="was"> · {(adjusted[f.key] / 2.54).toFixed(1)} in</span>}
          {String(adjusted[f.key]) !== String(Number(baseline[f.key])) && <span className="was"> (was {Number(baseline[f.key])})</span>}
        </span>
      </div>
      <input type="range" min={f.min} max={f.max} step={f.step} value={adjusted[f.key]}
        onChange={(e) => setAdjusted((a) => ({ ...a, [f.key]: Number(e.target.value) }))} />
    </div>
  );

  return (
    <div className="whatif">
      <h2 className="page-title">What-If simulator</h2>
      <p className="driver-chart-sub">
        Drag the sliders to see how changes could affect your Quick Screen estimate and which of the five criteria you'd
        meet. Everything recalculates instantly on your device.
      </p>

      <div className="whatif-compare">
        <div className="whatif-box">
          <div className="whatif-box-label">YOUR QUICK SCREEN</div>
          <div className="whatif-box-value">{baselinePrediction.risk_percent.toFixed(0)}%</div>
          <div className="whatif-delta">{baselinePrediction.criteria.met} of 5 criteria met</div>
        </div>
        <div className="whatif-box adjusted">
          <div className="whatif-box-label">WITH YOUR ADJUSTMENTS</div>
          <div className="whatif-box-value">{adjustedRisk.toFixed(0)}%</div>
          <div className={`whatif-delta ${criteria.met < baselinePrediction.criteria.met ? "better" : criteria.met > baselinePrediction.criteria.met ? "worse" : ""}`}>
            {criteria.met} of 5 criteria met
            {Math.abs(delta) >= 0.5 && ` · ${delta > 0 ? "↓" : "↑"} ${Math.abs(delta).toFixed(0)} points`}
          </div>
        </div>
      </div>

      <div className="whatif-sliders">
        <div className="whatif-sliders-header">
          <span>Body measurements (change the Quick Screen and the waist criterion)</span>
          <button className="btn-secondary" type="button" onClick={() => setAdjusted(startValues())}>Reset to my values</button>
        </div>
        <div className="whatif-grid">{SLIDER_FIELDS.map(slider)}</div>
        {labFields.length > 0 && (
          <>
            <div className="whatif-sliders-header" style={{ marginTop: 22 }}>
              <span>Blood pressure and labs (change the criteria check only)</span>
            </div>
            <div className="whatif-grid">{labFields.map(slider)}</div>
          </>
        )}
        {missingLabs.length > 0 && (
          <p className="driver-chart-sub" style={{ marginTop: 14 }}>
            You didn't enter {missingLabs.map((f) => f.label.toLowerCase()).join(", ")}, so {missingLabs.length === 1 ? "it stays" : "they stay"}{" "}
            "not entered" here. Start a new assessment with those values to explore them.
          </p>
        )}
      </div>

      <div className="whatif-two-col">
        <CriteriaCard criteria={criteria} compact />
        <div className="impact-analysis">
          <h3>Single-change impact on the Quick Screen</h3>
          <p className="driver-chart-sub">
            Reduction if you changed <em>only this</em>, on top of your current slider settings. Waist and BMI usually fall
            together, so the combined row is the most realistic.
          </p>
          {counterfactuals.length === 0 ? (
            <p className="driver-chart-sub">Your waist and BMI are already in the low-risk range.</p>
          ) : (
            <div className="impact-rows">
              {counterfactuals.map((r) => {
                const meaningful = r.reduction >= 0.5;
                return (
                  <div className="impact-row" key={r.label}>
                    <div className="impact-label">{r.label}</div>
                    <div className="impact-track">
                      <div className={`impact-bar ${meaningful ? "" : "grey"}`} style={{ width: `${Math.max((r.reduction / maxImpact) * 100, 2)}%` }} />
                    </div>
                    <div className="impact-value">
                      {meaningful ? `−${r.reduction.toFixed(0)} pts` : "—"} → {r.newRisk.toFixed(0)}%
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
