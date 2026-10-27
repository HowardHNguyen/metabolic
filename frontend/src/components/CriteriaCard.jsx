import React from "react";
import { Check, X, HelpCircle } from "lucide-react";
import { VERDICT } from "../constants.js";

const ICON = {
  met: <X size={15} strokeWidth={2.4} />,
  not_met: <Check size={15} strokeWidth={2.4} />,
  unknown: <HelpCircle size={15} strokeWidth={2} />,
};
const STATUS_TEXT = { met: "Meets criterion", not_met: "OK", unknown: "Not entered" };

// The five NCEP ATP III / harmonized criteria, checked one by one. Metabolic syndrome = 3 or more.
export default function CriteriaCard({ criteria, compact = false }) {
  if (!criteria) return null;
  const v = VERDICT[criteria.verdict];
  return (
    <article className="myrisk-side-card criteria-card">
      <h2 className="section-title">The five criteria</h2>
      {!compact && (
        <p className="section-copy">
          Metabolic syndrome means meeting <strong>3 or more</strong> of these. This check follows the official definition
          exactly; it isn't a model.
        </p>
      )}
      <div className={`criteria-verdict ${v.tone}`}>
        <strong>{criteria.met} of 5 met</strong>
        <span>{v.title}</span>
      </div>
      <ul className="criteria-list">
        {criteria.criteria.map((c) => (
          <li key={c.id} className={`criteria-row ${c.status}`}>
            <span className="criteria-icon" aria-hidden="true">{ICON[c.status]}</span>
            <div className="criteria-text">
              <div className="criteria-label">{c.label}</div>
              <div className="criteria-rule">{c.status === "unknown" ? c.rule : c.reason}</div>
            </div>
            <span className="criteria-status">{STATUS_TEXT[c.status]}</span>
          </li>
        ))}
      </ul>
      {criteria.verdict === "incomplete" && !compact && (
        <p className="section-copy" style={{ marginTop: 10 }}>
          {criteria.met} met so far, with {criteria.unknown} not entered. Add blood pressure and lab values from a recent
          check-up to get a definite answer.
        </p>
      )}
    </article>
  );
}
