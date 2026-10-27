import React, { useState } from "react";
import { LineChart, Line, BarChart, Bar, ErrorBar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from "recharts";
import R from "../research.json";

// Series colors: brand-neutral, distinguishable, and stable across charts (group 1..4).
const GROUP_COLORS = ["#4a5670", "#6f1eb8", "#2ca8f0", "#c24f26"];
const fmtP = (p) => (p === null || p === undefined ? "—" : p < 0.0001 ? "<0.0001" : p < 0.001 ? p.toFixed(4) : p.toFixed(3));
const BIO_LABELS = {
  GLUCOSE_30: "Glucose (mg/dL)", TRIGLYCERIDES_30: "Triglycerides (mg/dL)", CHOLESTEROL_30: "Cholesterol (mg/dL)",
  ALT_30: "ALT (U/L)", AST_30: "AST (U/L)", UREA_30: "Urea (mg/dL)",
};

function Issues({ items }) {
  if (!items?.length) return null;
  return (
    <div className="model-block warn research-issues">
      <h3>Data-quality notes</h3>
      <ul>{items.map((t) => <li key={t}>{t}</li>)}</ul>
    </div>
  );
}

function Trial() {
  const t = R.trial;
  const rows = t.markers.map((m) => {
    const b = Math.abs(m.baseline_mean) || 1;
    return { ...m, pct: (100 * m.effect) / b, lo: (100 * m.effect_ci[0]) / b, hi: (100 * m.effect_ci[1]) / b };
  });
  const span = Math.max(20, ...rows.map((r) => Math.max(Math.abs(r.lo), Math.abs(r.hi))));
  const pos = (v) => `${50 + (v / span) * 50}%`;
  const anySig = rows.some((r) => r.q_bh < 0.05);
  return (
    <section className="research-section">
      <p className="eyebrow">Study 1 · {t.file}</p>
      <h2 className="section-title">{t.title}</h2>
      <p className="section-copy">
        {t.design} {t.participants} adults ({t.men} men, {t.women} women); {t.responders} were flagged as responders in the
        file. {t.treatment_note}
      </p>
      <div className="research-callout">
        <strong>{anySig ? "Some markers changed." : "No marker changed by more than chance."}</strong>{" "}
        {anySig
          ? "See the table for the markers whose false-discovery-adjusted q-value is below 0.05."
          : "Every confidence interval below crosses zero, and no q-value is under 0.05. With 30 people the study can only detect fairly large effects, so 'no clear change' is not proof of no effect."}
      </div>
      <div className="forest">
        <div className="forest-head">
          <span>Marker</span>
          <span className="forest-axis-label">Treatment effect, % of baseline (95% CI) · ← lower · higher →</span>
          <span>p / q</span>
        </div>
        {rows.map((r) => (
          <div className="forest-row" key={r.key}>
            <span className="forest-name">{r.label}</span>
            <span className="forest-plot">
              <span className="forest-zero" />
              <span className="forest-ci" style={{ left: pos(Math.max(-span, r.lo)), width: `${((Math.min(span, r.hi) - Math.max(-span, r.lo)) / span) * 50}%` }} />
              <span className="forest-dot" style={{ left: pos(r.pct) }} title={`${r.pct.toFixed(1)}%`} />
            </span>
            <span className="forest-p">{fmtP(r.p_ttest)} / {fmtP(r.q_bh)}</span>
          </div>
        ))}
        <div className="forest-row forest-scale"><span /><span className="forest-axis"><span>−{span.toFixed(0)}%</span><span>0</span><span>+{span.toFixed(0)}%</span></span><span /></div>
      </div>
      <p className="driver-chart-sub" style={{ marginTop: 10 }}>{t.method}</p>
      <Issues items={t.issues} />
    </section>
  );
}

function Rodent() {
  const rd = R.rodent;
  const [gen, setGen] = useState(1);
  const days = rd.weight.days;
  const curves = rd.weight.curves.filter((c) => c.gen === gen);
  const weightData = days.map((d, i) => Object.fromEntries([["day", d], ...curves.map((c) => [`Group ${c.group}`, c.mean[i]])]));
  const bio = rd.biochemistry.filter((b) => ["GLUCOSE_30", "ALT_30", "AST_30", "TRIGLYCERIDES_30"].includes(b.key));
  const cyc = rd.cycles.find((c) => c.key === "Incompletecycles").by_group[0].groups;
  const cycComplete = rd.cycles.find((c) => c.key === "Completecycles").by_group[0].groups;
  const cycData = cyc.map((g, i) => ({ group: `Group ${g.group}`, Complete: cycComplete[i].mean, Incomplete: g.mean }));

  return (
    <section className="research-section">
      <p className="eyebrow">Study 2 · preclinical</p>
      <h2 className="section-title">{rd.title}</h2>
      <p className="section-copy">{rd.design} {rd.group_note}</p>
      <div className="research-callout">
        <strong>Groups 2–4 differ clearly from group 1.</strong> On day 30 they have higher blood glucose (about 102–131 vs
        94 mg/dL) and higher liver enzymes (ALT, AST), and the animals with cycle data have more incomplete estrous cycles.
        These are animal results and say nothing directly about human risk.
      </div>

      <div className="mode-toggle-inline" role="group" aria-label="Gen stratum" style={{ marginBottom: 12 }}>
        {[1, 2].map((g) => (
          <button key={g} type="button" className={gen === g ? "active" : ""} onClick={() => setGen(g)}>Gen {g}</button>
        ))}
      </div>

      <div className="research-grid">
        <div className="trend-chart-card">
          <div className="driver-chart-sub" style={{ marginBottom: 8 }}>BODY WEIGHT (g) BY DAY, MEAN PER GROUP · GEN {gen}</div>
          <div style={{ height: 240 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={weightData} margin={{ left: -10, right: 8 }}>
                <CartesianGrid stroke="var(--line-200)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="day" tick={{ fontSize: 11, fill: "var(--ink-600)" }} />
                <YAxis tick={{ fontSize: 11, fill: "var(--ink-600)" }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                {curves.map((c, i) => (
                  <Line key={c.group} type="monotone" dataKey={`Group ${c.group}`} stroke={GROUP_COLORS[i]} strokeWidth={2} dot={false} />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {bio.map((b) => {
          const s = b.by_group.find((x) => x.gen === gen);
          const data = s.groups.map((g) => ({ group: `G${g.group}`, mean: g.mean, sd: g.sd }));
          return (
            <div className="trend-chart-card" key={b.key}>
              <div className="driver-chart-sub" style={{ marginBottom: 8 }}>
                DAY 30 · {BIO_LABELS[b.key].toUpperCase()} · ANOVA p {fmtP(s.p_anova)}
              </div>
              <div style={{ height: 200 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={data} margin={{ left: -10, right: 8 }}>
                    <CartesianGrid stroke="var(--line-200)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="group" tick={{ fontSize: 11, fill: "var(--ink-600)" }} />
                    <YAxis tick={{ fontSize: 11, fill: "var(--ink-600)" }} />
                    <Tooltip formatter={(v) => v} />
                    <Bar dataKey="mean" fill="var(--brand-600)" radius={[4, 4, 0, 0]}>
                      <ErrorBar dataKey="sd" width={6} stroke="var(--ink-600)" />
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        })}

        <div className="trend-chart-card">
          <div className="driver-chart-sub" style={{ marginBottom: 8 }}>ESTROUS CYCLES PER ANIMAL (MEAN)</div>
          <div style={{ height: 200 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={cycData} margin={{ left: -10, right: 8 }}>
                <CartesianGrid stroke="var(--line-200)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="group" tick={{ fontSize: 11, fill: "var(--ink-600)" }} />
                <YAxis tick={{ fontSize: 11, fill: "var(--ink-600)" }} allowDecimals={false} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="Complete" stackId="c" fill="var(--moss-500)" />
                <Bar dataKey="Incomplete" stackId="c" fill="var(--flame-600)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
      <p className="driver-chart-sub" style={{ marginTop: 10 }}>{rd.method}</p>
      <Issues items={rd.issues} />
    </section>
  );
}

function Metabolomics() {
  const mx = R.metabolomics;
  const pos = mx.modes.find((m) => m.mode === "positive");
  const neg = mx.modes.find((m) => m.mode === "negative");
  const total = pos.features + neg.features;
  const sigPri = pos.sig_pri_vs_hc + neg.sig_pri_vs_hc;
  const sigEut = pos.sig_eut_vs_hc + neg.sig_eut_vs_hc;
  return (
    <section className="research-section">
      <p className="eyebrow">Study 3 · {mx.file}</p>
      <h2 className="section-title">{mx.title}</h2>
      <p className="section-copy">{mx.source} {mx.design}</p>
      <div className="model-stat-grid" style={{ margin: "14px 0" }}>
        <div className="model-stat"><div className="model-stat-label">FEATURES MEASURED</div><div className="model-stat-value">{total.toLocaleString()}</div></div>
        <div className="model-stat"><div className="model-stat-label">DIFFER: UNTREATED vs HEALTHY</div><div className="model-stat-value">{sigPri.toLocaleString()}</div></div>
        <div className="model-stat"><div className="model-stat-label">DIFFER: TREATED vs HEALTHY</div><div className="model-stat-value">{sigEut}</div></div>
        <div className="model-stat"><div className="model-stat-label">QC MEDIAN CV</div><div className="model-stat-value">{pos.qc_median_cv_pct}%</div></div>
      </div>
      <div className="research-callout">
        <strong>Treatment largely normalizes the blood metabolome.</strong> {sigPri.toLocaleString()} features differ between
        untreated Graves' disease and healthy controls (false-discovery rate under 5%), but only {sigEut} still differ once
        thyroid function is back to normal. The pooled QC samples vary by a median of about {pos.qc_median_cv_pct}%, which
        indicates good measurement stability.
      </div>
      <div className="trend-chart-card" style={{ overflowX: "auto" }}>
        <div className="driver-chart-sub" style={{ marginBottom: 8 }}>TOP NAMED FEATURES: UNTREATED GRAVES' vs HEALTHY</div>
        <table className="trend-table">
          <thead>
            <tr><th>Metabolite (database match)</th><th>Mode</th><th>m/z</th><th>log2 fold change, untreated</th><th>q</th><th>log2 fold change, treated</th><th>q</th></tr>
          </thead>
          <tbody>
            {mx.top.map((x) => (
              <tr key={x.id}>
                <td>{x.name}</td><td>{x.mode === "positive" ? "+" : "−"}</td><td>{x.mz}</td>
                <td style={{ color: x.log2fc_pri_vs_hc > 0 ? "var(--risk-700)" : "var(--brand-700)" }}>{x.log2fc_pri_vs_hc > 0 ? "+" : ""}{x.log2fc_pri_vs_hc}</td>
                <td>{x.q_pri_vs_hc}</td>
                <td>{x.log2fc_eut_vs_hc > 0 ? "+" : ""}{x.log2fc_eut_vs_hc}</td>
                <td>{x.q_eut_vs_hc}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="driver-chart-sub" style={{ marginTop: 10 }}>{mx.method}</p>
      <Issues items={mx.issues} />
    </section>
  );
}

export default function ResearchTab() {
  return (
    <div className="model-data research">
      <h2 className="page-title">Research</h2>
      <p className="driver-chart-sub">
        Three datasets from VitalCKM's metabolic research collection, re-analysed here so you can see what they show.{" "}
        <strong>None of them is used by the Quick Screen or the criteria check.</strong> They have no metabolic-syndrome
        outcome, are too small to train a calculator on, or come from animals; the Model &amp; Data tab explains what the
        screen is trained on.
      </p>
      <Trial />
      <Rodent />
      <Metabolomics />
    </div>
  );
}
