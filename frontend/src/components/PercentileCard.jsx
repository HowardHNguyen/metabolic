import React from "react";
import { PCT_LABELS, PCT_UNITS, groupLabel } from "../constants.js";

// For HDL a higher value is healthier, so the bar colors flip.
const HIGHER_IS_BETTER = { HDL: true };

function tone(variable, p) {
  const bad = HIGHER_IS_BETTER[variable] ? 100 - p : p;
  return bad >= 75 ? "high" : bad >= 50 ? "borderline" : "low";
}

export default function PercentileCard({ percentiles }) {
  const entries = Object.entries(percentiles?.values || {});
  if (!entries.length) return null;
  return (
    <article className="myrisk-side-card percentile-card">
      <h3>How you compare</h3>
      <p className="section-copy">
        Your values against {groupLabel(percentiles.group)} in the NHANES 2011–12 survey sample. The marker shows the share
        of people with a lower value.
      </p>
      <div className="pct-rows">
        {entries.map(([k, v]) => (
          <div className="pct-row" key={k}>
            <div className="pct-head">
              <span className="pct-name">{PCT_LABELS[k]}</span>
              <span className="pct-value">
                {k === "BMI" ? Number(v.value).toFixed(1) : Math.round(v.value)} {PCT_UNITS[k]}
              </span>
            </div>
            <div className="pct-track">
              <span className={`pct-marker ${tone(k, v.percentile)}`} style={{ left: `${v.percentile}%` }} />
            </div>
            <div className="pct-caption">
              Higher than {v.percentile}% of {groupLabel(percentiles.group).replace("US ", "")}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}
