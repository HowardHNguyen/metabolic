import React, { useRef, useState } from "react";
import { TrendingUp } from "lucide-react";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { exportRiskOverTimeToPDF } from "../pdfExport.js";
import { tierLabel } from "../constants.js";

function Metric({ label, value, unit, delta, invert, deltaUnit = "pp" }) {
  const good = delta === null ? null : invert ? delta < 0 : delta > 0;
  return (
    <div className="trend-metric-card">
      <div className="trend-metric-label">{label.toUpperCase()}</div>
      <div className="trend-metric-value">
        {value}
        {unit && <span style={{ fontSize: 14, fontWeight: 400, marginLeft: 4 }}>{unit}</span>}
      </div>
      {delta !== null && Math.abs(delta) >= 0.05 && (
        <div className="trend-metric-delta" style={{ color: good ? "var(--moss-500)" : "var(--risk-700)" }}>
          {delta > 0 ? "↑" : "↓"} {Math.abs(delta).toFixed(1)} {deltaUnit}
        </div>
      )}
    </div>
  );
}

export default function TrendTab({ history, userEmail, onRecalculate, onDelete }) {
  const pdfContentRef = useRef(null);
  const [isExporting, setIsExporting] = useState(false);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [deleting, setDeleting] = useState(false);

  async function handleExportPDF() {
    setIsExporting(true);
    try {
      await exportRiskOverTimeToPDF(pdfContentRef, userEmail);
    } finally {
      setIsExporting(false);
    }
  }

  async function handleConfirmDelete() {
    if (!confirmDeleteId) return;
    setDeleting(true);
    try {
      await onDelete(confirmDeleteId);
      setConfirmDeleteId(null);
    } finally {
      setDeleting(false);
    }
  }

  const current = history.filter((h) => !h.legacy);
  const legacyCount = history.length - current.length;

  if (history.length === 0) {
    return (
      <div className="empty-state">
        <TrendingUp size={40} strokeWidth={1.3} style={{ opacity: 0.5, marginBottom: 12 }} />
        <div style={{ fontFamily: "var(--font-display)", fontSize: 22, fontWeight: 600, marginBottom: 6 }}>
          No saved assessments yet
        </div>
        <p>Run an assessment while signed in to start tracking your waist, BMI and criteria over time.</p>
      </div>
    );
  }

  const latest = current[current.length - 1];
  const prev = current.length > 1 ? current[current.length - 2] : null;

  return (
    <div>
      <div className="trend-header">
        <div>
          <h2 className="page-title" style={{ margin: "0 0 4px" }}>
            Progress over time
          </h2>
          <p className="driver-chart-sub" style={{ margin: 0 }}>
            {current.length} assessment{current.length !== 1 ? "s" : ""} saved
          </p>
          {legacyCount > 0 && (
            <p className="driver-chart-sub" style={{ margin: "4px 0 0" }}>
              {legacyCount} earlier assessment{legacyCount !== 1 ? "s were" : " was"} made with a different model
              version and {legacyCount !== 1 ? "aren't" : "isn't"} comparable, so {legacyCount !== 1 ? "they're" : "it's"} left
              out of the trend. You can still delete {legacyCount !== 1 ? "them" : "it"} below.
            </p>
          )}
        </div>
        <button className="btn-export" onClick={handleExportPDF} disabled={isExporting} title="Download a PDF report to share with your doctor">
          {isExporting ? "Generating PDF…" : "↓ Export PDF"}
        </button>
      </div>

      <div ref={pdfContentRef}>
        {latest && (<>
        <div className="trend-metrics">
          <Metric label="Quick Screen" value={latest.risk.toFixed(0)} unit="%" delta={prev ? latest.risk - prev.risk : null} invert deltaUnit="pts" />
          <Metric label="Criteria met" value={latest.met ?? "—"} unit="of 5" delta={prev && latest.met != null && prev.met != null ? latest.met - prev.met : null} invert deltaUnit="" />
          <Metric label="Waist" value={latest.waist.toFixed(0)} unit="cm" delta={prev ? latest.waist - prev.waist : null} invert deltaUnit="cm" />
          <Metric label="BMI" value={latest.bmi.toFixed(1)} delta={prev ? latest.bmi - prev.bmi : null} invert deltaUnit="" />
        </div>

        <div className="trend-chart-card">
          <div className="driver-chart-sub" style={{ marginBottom: 16 }}>QUICK SCREEN TRAJECTORY</div>
          <div style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={current}>
                <CartesianGrid stroke="var(--line-200)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 11, fill: "var(--ink-600)" }} />
                <YAxis tick={{ fontSize: 11, fill: "var(--ink-600)" }} unit="%" domain={[0, 100]} />
                <Tooltip formatter={(v) => [`${v}%`, "Quick Screen"]} />
                <Line type="monotone" dataKey="risk" stroke="var(--brand-700)" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        </>)}
        <div className="trend-chart-card" style={{ overflowX: "auto" }}>
          <table className="trend-table">
            <thead>
              <tr>
                <th>Date</th><th>Quick Screen</th><th>Level</th><th>Criteria met</th><th>Waist</th><th>BMI</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {history.slice().reverse().map((h) => (
                <tr key={h.id}>
                  <td>{h.date}</td>
                  <td className="trend-risk-cell">{h.legacy ? "—" : `${h.risk.toFixed(0)}%`}</td>
                  <td>{h.legacy ? "earlier model" : tierLabel(h.category)}</td>
                  <td>{h.met == null ? "—" : `${h.met} of 5${h.unknown ? ` (${h.unknown} not entered)` : ""}`}</td>
                  <td>{h.waist.toFixed(0)} cm</td>
                  <td>{h.bmi.toFixed(1)}</td>
                  <td>
                    <button className="trend-action-link" onClick={() => onRecalculate(h)}>Recalculate</button>
                    <button className="trend-action-link danger" onClick={() => setConfirmDeleteId(h.id)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {confirmDeleteId && (
        <div className="modal-overlay" onClick={() => !deleting && setConfirmDeleteId(null)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <h3>Delete this assessment?</h3>
            <p>This can't be undone.</p>
            <div style={{ display: "flex", gap: 10, justifyContent: "flex-end", marginTop: 18 }}>
              <button className="btn-secondary" onClick={() => setConfirmDeleteId(null)} disabled={deleting}>Cancel</button>
              <button className="btn-primary" style={{ background: "var(--risk-700)" }} onClick={handleConfirmDelete} disabled={deleting}>
                {deleting ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
