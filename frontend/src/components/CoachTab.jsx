import React, { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { buildCoachingRecs } from "../constants.js";

function CoachCard({ rec, defaultOpen }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="coach-card" style={{ padding: 0, overflow: "hidden" }}>
      <button
        onClick={() => setOpen(!open)}
        style={{
          width: "100%", border: "none", background: "transparent", padding: 18, textAlign: "left",
          cursor: "pointer", display: "flex", justifyContent: "space-between", alignItems: "flex-start",
          gap: 12, fontFamily: "inherit",
        }}
      >
        <div>
          <div className={`coach-priority ${rec.severity}`}>
            {rec.severity === "high" ? "High priority" : rec.severity === "medium" ? "Medium priority" : "Maintain"}
          </div>
          <div className="coach-card-title" style={{ marginBottom: 0 }}>{rec.title}</div>
        </div>
        {open ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
      </button>
      {open && (
        <div style={{ padding: "0 18px 18px" }}>
          <p style={{ margin: 0, fontSize: 13.5, color: "var(--ink-600)" }}>{rec.detail}</p>
        </div>
      )}
    </div>
  );
}

export default function CoachTab({ data, criteria }) {
  const recs = buildCoachingRecs(data, criteria);
  return (
    <div className="coach">
      <h2 className="page-title">Your personalized recommendations</h2>
      <p className="driver-chart-sub">
        Based on the criteria you meet and your measurements. Waist comes first because it drives the other four.
        Always discuss with your clinician before changing any medicine.
      </p>
      <div className="coach-grid">
        {recs.map((rec, i) => (
          <CoachCard key={rec.title} rec={rec} defaultOpen={i < 2} />
        ))}
      </div>
    </div>
  );
}
