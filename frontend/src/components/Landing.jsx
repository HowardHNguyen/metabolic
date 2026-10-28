import React from "react";
import { Gauge, Activity, ListChecks, LineChart } from "lucide-react";
import logo from "../assets/vitalckm-logo.gif";
import { MODEL_SPEC as M } from "../localModel.js";

export default function Landing({ user, onStart, onSignIn }) {
  return (
    <div style={{ minHeight: "100vh", background: "var(--paper-50)" }}>
      <div className="topbar">
        <div className="shell topbar-inner">
          <div className="wordmark">
            <img src={logo} alt="vitalCKM" className="wordmark-logo" />
            <span className="wordmark-eyebrow">Metabolic Screen</span>
          </div>
          <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
            {user ? (
              <button className="btn-primary" style={{ background: "var(--brand-700)" }} onClick={onStart}>
                Continue to my assessment
              </button>
            ) : (
              <>
                <button className="btn-secondary" onClick={onSignIn}>Sign in</button>
                <button className="btn-primary" style={{ background: "var(--brand-700)" }} onClick={onStart}>
                  Begin assessment
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      <section className="landing-hero shell">
        <div className="landing-hero-badge">
          <Gauge size={34} color="#fff" strokeWidth={1.6} />
        </div>
        <h1>Do you have metabolic syndrome — and what would change it?</h1>
        <p>
          A free, evidence-based metabolic health screen. Your age, sex, BMI and waist give an instant estimate, no blood test
          needed. Add your blood pressure and lab results to check all five official criteria.
        </p>
        <div className="landing-cta-row">
          <button className="btn-primary" style={{ background: "var(--brand-700)", padding: "13px 26px" }} onClick={onStart}>
            Begin assessment →
          </button>
        </div>
      </section>

      <section className="landing-section shell">
        <h2>Built for clarity, not just a number</h2>
        <div className="landing-grid-3">
          <div className="landing-value-card">
            <ListChecks size={22} color="var(--brand-700)" />
            <h3>All five criteria, one by one</h3>
            <p>Waist, triglycerides, HDL, blood pressure and fasting glucose, checked against the official cut-points, so you see exactly which ones you meet.</p>
          </div>
          <div className="landing-value-card">
            <Activity size={22} color="var(--brand-600)" />
            <h3>Try changes before you make them</h3>
            <p>Drag sliders for waist, weight and lab values to watch your estimate and your criteria change instantly.</p>
          </div>
          <div className="landing-value-card">
            <LineChart size={22} color="var(--accent-600)" />
            <h3>See how you compare, and track it</h3>
            <p>Compare your numbers with US adults of your age and sex, save each assessment, and export a PDF for your doctor.</p>
          </div>
        </div>
      </section>

      <section className="landing-section shell">
        <h2>Trained on modern US data</h2>
        <p style={{ maxWidth: 660, margin: "0 auto", textAlign: "center", color: "var(--ink-600)" }}>
          The Quick Screen is a transparent logistic regression trained on {M.training.rows.toLocaleString()} adults from
          NHANES 2011–2012 and 2017–2020, the national health survey of the US. It reaches an AUC of{" "}
          {M.validation.auc.toFixed(2)} in cross-validation, holds up when trained on one survey and tested on the other, and
          its percentages are calibrated to the 2017–2020 population. It estimates whether you have metabolic syndrome now,
          not your future risk, and it is educational. The Model &amp; Data tab inside the app gives the full methodology
          and its limitations.
        </p>
      </section>

      <div className="landing-hero shell" style={{ padding: "40px 0 60px" }}>
        <button className="btn-primary" style={{ background: "var(--brand-700)", padding: "13px 26px" }} onClick={onStart}>
          Begin assessment →
        </button>
      </div>

      <footer className="landing-footer">
        vitalCKM Metabolic Screen · educational tool, not a substitute for professional medical advice · model
        trained on NHANES 2011–12 and 2017–20
      </footer>
    </div>
  );
}
