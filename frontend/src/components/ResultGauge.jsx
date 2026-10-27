import React from "react";

const CX = 120;
const CY = 118;
const R = 96;
const STROKE = 16;

function polarToCartesian(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy - r * Math.sin(rad) };
}

// value in [0,1] maps to angle 180 (left) -> 0 (right), sweeping over the top
function describeArc(startValue, endValue) {
  const startAngle = 180 - startValue * 180;
  const endAngle = 180 - endValue * 180;
  const start = polarToCartesian(CX, CY, R, startAngle);
  const end = polarToCartesian(CX, CY, R, endAngle);
  const largeArc = startAngle - endAngle > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${R} ${R} 0 ${largeArc} 1 ${end.x} ${end.y}`;
}

const DEFAULT_BANDS = [
  { from: 0, to: 0.35, color: "var(--moss-500)" },
  { from: 0.35, to: 0.7, color: "var(--amber-500)" },
  { from: 0.7, to: 1, color: "var(--flame-600)" },
];

export default function ResultGauge({ probability, bands = DEFAULT_BANDS }) {
  const value = probability ?? 0;
  const needleAngle = 180 - value * 180;
  const needleTip = polarToCartesian(CX, CY, R - STROKE / 2 - 6, needleAngle);

  return (
    <div className="gauge-wrap">
      <svg viewBox="0 0 240 130" width="220" height="120" role="img" aria-label={`Predicted likelihood ${Math.round(value * 100)} percent`}>
        {/* track */}
        <path d={describeArc(0, 1)} fill="none" stroke="var(--line-200)" strokeWidth={STROKE} strokeLinecap="round" />
        {/* bands */}
        {bands.map((b) => (
          <path
            key={b.from}
            d={describeArc(b.from, b.to)}
            fill="none"
            stroke={b.color}
            strokeWidth={STROKE}
            strokeLinecap="butt"
            opacity={probability == null ? 0.35 : 1}
          />
        ))}
        {/* needle */}
        {probability != null && (
          <g style={{ transition: "transform 0.6s cubic-bezier(.2,.8,.2,1)" }}>
            <line x1={CX} y1={CY} x2={needleTip.x} y2={needleTip.y} stroke="var(--ink-900)" strokeWidth="3" strokeLinecap="round" />
            <circle cx={CX} cy={CY} r="5.5" fill="var(--ink-900)" />
          </g>
        )}
        {/* tick labels */}
        <text x="14" y="128" fontFamily="var(--font-mono)" fontSize="10" fill="var(--ink-600)">0</text>
        <text x="200" y="128" fontFamily="var(--font-mono)" fontSize="10" fill="var(--ink-600)">100</text>
      </svg>
      <div className="gauge-readout">
        {probability != null ? `${Math.round(value * 100)}%` : "—"}
      </div>
    </div>
  );
}
