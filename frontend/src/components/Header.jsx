import React from "react";
import logo from "../assets/vitalckm-logo.gif";

export default function Header() {
  return (
    <div className="topbar">
      <div className="shell">
        <div className="topbar-inner">
          <div className="wordmark">
            <img src={logo} alt="vitalCKM" className="wordmark-logo" />
          </div>
          <span className="wordmark-eyebrow">Metabolic Screen</span>
        </div>
      </div>
    </div>
  );
}
