import React from "react";

const TABS = [
  { id: "calc", label: "Screen" },
  { id: "trend", label: "Progress" },
  { id: "bie", label: "What-If" },
  { id: "coach", label: "Health Coach" },
  { id: "model", label: "Model & Data" },
  { id: "research", label: "Research" },
  { id: "faq", label: "FAQ" },
];

export default function TopNav({ active, onChange, resultAvailable }) {
  return (
    <nav className="topnav">
      <div className="shell topnav-inner">
        {TABS.map((t) => {
          const locked = (t.id === "bie" || t.id === "coach") && !resultAvailable;
          return (
            <button
              key={t.id}
              className={`topnav-tab ${active === t.id ? "active" : ""} ${locked ? "locked" : ""}`}
              onClick={() => onChange(t.id)}
              title={locked ? "Run an assessment first" : undefined}
            >
              {t.label}
            </button>
          );
        })}
      </div>
    </nav>
  );
}
