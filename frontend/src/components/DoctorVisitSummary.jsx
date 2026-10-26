import React from "react";
import CriteriaCard from "./CriteriaCard.jsx";
import { RISK_LEVELS } from "../constants.js";

const VALUE_ROWS = [
  { key: "WAIST", label: "Waist", unit: "cm" },
  { key: "BMI", label: "BMI", unit: "kg/m²" },
  { key: "SYSBP", label: "Systolic blood pressure", unit: "mmHg" },
  { key: "DIABP", label: "Diastolic blood pressure", unit: "mmHg" },
  { key: "GLUCOSE", label: "Fasting glucose", unit: "mg/dL" },
  { key: "HDL", label: "HDL cholesterol", unit: "mg/dL" },
  { key: "TG", label: "Triglycerides", unit: "mg/dL" },
];

const QUESTIONS = [
  "Do I have metabolic syndrome, based on my latest blood pressure, lipid panel and fasting glucose (or HbA1c)?",
  "Which of the five criteria should we work on first?",
  "Is my blood sugar in the prediabetes range, and should I join a diabetes-prevention program?",
  "What waist, weight, activity and diet goals make sense for me?",
  "Does metabolic syndrome change my heart, kidney or liver risk, and should anything else be checked?",
  "When should I be retested?",
];

const PRIORITIES = [
  "Waist and weight goals",
  "Lipid panel (triglycerides, HDL) and fasting glucose / HbA1c",
  "Blood-pressure goals and home monitoring",
  "Nutrition, physical activity, sleep and alcohol",
  "Medicine review",
];

export default function DoctorVisitSummary({ data, prediction, explanation, onBack }) {
  const catLabel = RISK_LEVELS.find((l) => l.tier === prediction.category)?.label;
  const riskPercent = Math.round(prediction.risk_probability * 100);
  const topFactors = (explanation?.contributions || []).slice(0, 3);

  return (
    <div className="visit-summary-page">
      <div className="visit-summary-toolbar no-print">
        <div className="page-heading" style={{ marginBottom: 0 }}>
          <p className="eyebrow">For your appointment</p>
          <h1 className="page-title">Doctor visit summary</h1>
          <p className="page-sub">
            A concise summary of your metabolic syndrome screen, the five criteria, and questions you may want to
            discuss with your healthcare professional.
          </p>
        </div>
        <div className="btn-row">
          <button className="btn-secondary" type="button" onClick={onBack}>← Back to My Risk</button>
          <button className="btn-primary" type="button" onClick={() => window.print()}>Export / Print PDF</button>
        </div>
      </div>

      <div className="print-only">
        <p className="eyebrow">vitalCKM Metabolic Screen</p>
        <h1 className="page-title">Doctor visit summary</h1>
      </div>

      <section className="card visit-summary-hero">
        <div className="card-pad">
          <div className="visit-summary-top">
            <div className="visit-risk-box">
              <div className="visit-risk-label">Quick Screen: chance of metabolic syndrome</div>
              <div className="visit-risk-value">{riskPercent}%</div>
              <div className={`risk-chip ${prediction.category}`}>
                <span className="risk-chip-dot" />
                {catLabel}
              </div>
            </div>
            <div className="visit-summary-message">
              <h2>What to discuss at your visit</h2>
              <p>
                The Quick Screen uses only age, sex, background, BMI and waist. The criteria check uses whatever blood
                pressure and lab values were entered: <strong>{prediction.criteria.met} of 5 met</strong>
                {prediction.criteria.unknown ? `, ${prediction.criteria.unknown} not entered` : ""}. This summary helps you
                organize the information for your clinician. It is not a diagnosis.
              </p>
            </div>
          </div>
        </div>
      </section>

      <div className="visit-grid">
        <section className="card visit-section">
          <h2>Top factors in the Quick Screen</h2>
          <p className="visit-section-copy">The strongest contributors to the estimate, compared with the average adult.</p>
          <div className="visit-factors">
            {topFactors.length > 0 ? (
              topFactors.map((c) => (
                <div className="visit-factor" key={c.feature}>
                  <strong>{c.friendly_name || c.feature}</strong>
                  <span className={c.value >= 0 ? "raise" : "lower"}>
                    {c.value >= 0 ? "↑ Raises the estimate" : "↓ Lowers the estimate"}
                  </span>
                </div>
              ))
            ) : (
              <p className="visit-section-copy">No factor breakdown available for this assessment.</p>
            )}
          </div>
        </section>

        <section className="card visit-section">
          <h2>Current health values</h2>
          <p className="visit-section-copy">Bring recent measurements or laboratory results if they have changed.</p>
          <div className="visit-values">
            {VALUE_ROWS.map((row) => {
              const raw = data[row.key];
              if (raw === "" || raw === null || raw === undefined) return null;
              return (
                <div className="visit-value-row" key={row.key}>
                  <span>{row.label}</span>
                  <strong>{raw}{row.unit ? ` ${row.unit}` : ""}</strong>
                </div>
              );
            })}
          </div>
        </section>

        <section className="visit-section full visit-criteria">
          <CriteriaCard criteria={prediction.criteria} compact />
        </section>

        <section className="card visit-section full">
          <h2>Questions you may want to ask</h2>
          <p className="visit-section-copy">These prompts are meant to support a productive conversation, not to suggest a specific treatment.</p>
          <div className="visit-questions">
            {QUESTIONS.map((q, i) => (
              <div className="visit-question" key={q}>
                <div className="visit-question-num">{i + 1}</div>
                <p>{q}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="card visit-section">
          <h2>Potential priorities to review</h2>
          <p className="visit-section-copy">Use this checklist during your appointment.</p>
          <div className="visit-plan">
            {PRIORITIES.map((p) => (
              <div className="visit-plan-item" key={p}>
                <span className="visit-plan-check" />
                <span>{p}</span>
              </div>
            ))}
          </div>
        </section>

        <section className="card visit-section">
          <h2>Notes from my clinician</h2>
          <p className="visit-section-copy">Use this space when printing the summary.</p>
          <div style={{ marginTop: 16, display: "grid", gap: 18 }}>
            <div style={{ height: 34, borderBottom: "1px solid var(--line-200)" }} />
            <div style={{ height: 34, borderBottom: "1px solid var(--line-200)" }} />
            <div style={{ height: 34, borderBottom: "1px solid var(--line-200)" }} />
            <div style={{ height: 34, borderBottom: "1px solid var(--line-200)" }} />
          </div>
        </section>
      </div>

      <aside className="visit-note">
        <strong>Important:</strong> vitalCKM Metabolic Screen is an educational screening tool. This summary is
        not a diagnosis, prescription, or treatment plan. Clinical decisions should be made with a qualified
        healthcare professional using your complete history, examination, laboratory data, and validated clinical
        tools.
      </aside>
    </div>
  );
}
