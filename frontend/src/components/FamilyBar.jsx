import React from "react";

// Shared across the vitalCKM screens (cardio, ckd, metabolic): a thin strip linking the sibling apps.
// Keep this file identical in all three repos; only the `current` prop differs.
const APPS = [
  { id: "cardio", label: "Heart", title: "Cardio Screen: 10-year heart risk", url: "https://cardio.vitalckm.com" },
  { id: "ckd", label: "Kidney", title: "CKD Screen: chronic kidney disease", url: "https://ckd.vitalckm.com" },
  { id: "metabolic", label: "Metabolic", title: "Metabolic Screen: metabolic syndrome", url: "https://metabolic.vitalckm.com" },
];

export default function FamilyBar({ current }) {
  return (
    <nav className="family-bar" aria-label="vitalCKM screens">
      <div className="shell family-bar-inner">
        <span className="family-bar-label">vitalCKM screens</span>
        <span className="family-bar-links">
          {APPS.map((a) =>
            a.id === current ? (
              <span key={a.id} className={`family-link current ${a.id}`} aria-current="page" title={a.title}>{a.label}</span>
            ) : (
              <a key={a.id} className={`family-link ${a.id}`} href={a.url} title={a.title}>{a.label}</a>
            )
          )}
        </span>
      </div>
    </nav>
  );
}
