import React from "react";
import { RISK_LEVELS } from "../constants.js";
import { MODEL_SPEC } from "../localModel.js";

// Segment edges come from the model's tiers (model.json via RISK_LEVELS), so the bar can never disagree with the labels.
// Each band's width is proportional to its share of 0-100% (the metabolic tiers are wide enough to read at true scale).
const WEIGHTS = MODEL_SPEC.tiers.map((t) => t.max - t.min);
const COLORS = ["var(--moss-500)", "var(--amber-500)", "var(--flame-600)", "var(--risk-700)"];
const SEGMENTS = RISK_LEVELS.map((lvl, i) => ({ from: lvl.min, to: lvl.max, weight: WEIGHTS[i], color: COLORS[i] }));
const TOTAL_WEIGHT = SEGMENTS.reduce((sum, s) => sum + s.weight, 0);

function valueToPercent(value) {
  let cumulative = 0;
  for (const seg of SEGMENTS) {
    if (value <= seg.to) {
      const span = seg.to - seg.from;
      const frac = span > 0 ? (value - seg.from) / span : 0;
      return ((cumulative + frac * seg.weight) / TOTAL_WEIGHT) * 100;
    }
    cumulative += seg.weight;
  }
  return 100;
}

export default function RiskScale({ probability }) {
  const value = probability ?? 0;
  const markerPos = Math.max(0, Math.min(100, valueToPercent(value)));

  return (
    <div className="risk-scale-wrap">
      <div className="risk-scale">
        {SEGMENTS.map((seg) => (
          <span key={seg.from} style={{ background: seg.color, flex: seg.weight }} />
        ))}
      </div>
      <div className="risk-marker-track">
        {probability != null && <span className="risk-marker" style={{ left: `${markerPos}%` }} />}
      </div>
    </div>
  );
}
