import React, { useEffect, useState } from "react";
import { FEATURES, validateField } from "../constants.js";

export function FieldInput({ name, value, onChange, data }) {
  const cfg = FEATURES[name];
  const check = validateField(name, value, data);
  if (cfg.onlyIf && !cfg.onlyIf(data)) return null;

  if (cfg.type === "select") {
    return (
      <div className={`field ${check.state === "hard" ? "invalid" : ""}`}>
        <label>{cfg.label}</label>
        <select value={value} onChange={(e) => onChange(name, e.target.value === "" ? "" : cfg.stringValue ? e.target.value : Number(e.target.value))}>
          {value === "" && <option value="">Select…</option>}
          {cfg.options.map((o) => (
            <option key={o.v} value={o.v}>
              {o.l}
            </option>
          ))}
        </select>
        {cfg.help && <span className="range-hint">{cfg.help}</span>}
      </div>
    );
  }

  if (cfg.type === "binary") {
    return (
      <div className="field">
        <label>{cfg.label}</label>
        <div className="mode-toggle-inline" style={{ width: "fit-content" }}>
          <button type="button" className={Number(value) === 0 ? "active" : ""} onClick={() => onChange(name, 0)}>
            No
          </button>
          <button type="button" className={Number(value) === 1 ? "active" : ""} onClick={() => onChange(name, 1)}>
            Yes
          </button>
        </div>
        {cfg.help && <span className="range-hint">{cfg.help}</span>}
      </div>
    );
  }

  // number
  return (
    <div className={`field ${check.state === "hard" ? "invalid" : ""}`}>
      <label>{cfg.label}</label>
      <input
        type="number"
        step="any"
        value={value}
        onChange={(e) => onChange(name, e.target.value)}
        placeholder={cfg.optional ? "Optional" : cfg.help}
      />
      {check.state === "soft" && <span className="field-error" style={{ color: "var(--amber-500)" }}>{check.message}</span>}
      {check.state === "hard" && <span className="field-error">{check.message}</span>}
      {check.state === "ok" && cfg.help && <span className="range-hint">{cfg.help}</span>}
    </div>
  );
}

// Special composite field: height (ft/in) + weight (lbs) auto-calculating BMI.
export function BMIGroupInput({ data, onChange }) {
  const [manuallyEdited, setManuallyEdited] = useState(false);

  useEffect(() => {
    if (manuallyEdited) return;
    const ft = Number(data.HEIGHT_FT) || 0;
    const inch = Number(data.HEIGHT_IN) || 0;
    const totalInches = ft * 12 + inch;
    const lb = Number(data.WEIGHT_LB) || 0;
    if (totalInches > 0 && lb > 0) {
      const computed = Math.round((lb / (totalInches * totalInches)) * 703 * 10) / 10;
      if (computed !== Number(data.BMI)) onChange("BMI", computed);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data.HEIGHT_FT, data.HEIGHT_IN, data.WEIGHT_LB, manuallyEdited]);

  const bmiVal = Number(data.BMI) || 0;
  const bmiCategory = !bmiVal ? "" : bmiVal < 18.5 ? "Underweight" : bmiVal < 25 ? "Normal" : bmiVal < 30 ? "Overweight" : "Obese";
  const bmiTier = bmiCategory === "Normal" ? "low" : bmiCategory === "Obese" ? "high" : bmiCategory ? "borderline" : null;

  return (
    <div className="bmi-group">
      <div className="bmi-group-title">Height, weight & BMI</div>
      <div className="bmi-group-row">
        <div className="field">
          <label>Height <span className="unit">ft and in</span></label>
          <div className="height-inputs">
            <input type="number" min={3} max={8} step={1} value={data.HEIGHT_FT} placeholder="ft"
              onChange={(e) => onChange("HEIGHT_FT", e.target.value)} />
            <input type="number" min={0} max={11} step={1} value={data.HEIGHT_IN} placeholder="in"
              onChange={(e) => onChange("HEIGHT_IN", e.target.value)} />
          </div>
        </div>
        <div className="field">
          <label>Weight <span className="unit">lbs</span></label>
          <input type="number" min={50} max={700} step={1} value={data.WEIGHT_LB} placeholder="lbs"
            onChange={(e) => onChange("WEIGHT_LB", e.target.value)} />
        </div>
      </div>
      <div className="bmi-readout">
        <div className="field">
          <label>Body Mass Index (BMI) <span className="unit">auto-calculated · editable</span></label>
          <input type="number" step="0.1" value={data.BMI}
            onChange={(e) => { setManuallyEdited(true); onChange("BMI", e.target.value); }} />
        </div>
        {bmiCategory && <span className={`risk-badge ${bmiTier}`}>{bmiCategory}</span>}
      </div>
      <div className="range-hint">Normal: 18.5–24.9 · Overweight: 25–29.9 · Obese: 30+</div>
    </div>
  );
}

// Waist circumference in inches or cm; the model and the API always get cm.
export function WaistGroupInput({ data, onChange }) {
  const unit = data.WAIST_UNIT || "in";
  const check = validateField("WAIST", data.WAIST, data);
  const shown = unit === "in" ? data.WAIST_IN : data.WAIST;

  function setValue(raw) {
    if (unit === "in") {
      onChange("WAIST_IN", raw);
      onChange("WAIST", raw === "" ? "" : Math.round(Number(raw) * 2.54 * 10) / 10);
    } else {
      onChange("WAIST", raw);
      onChange("WAIST_IN", raw === "" ? "" : Math.round((Number(raw) / 2.54) * 10) / 10);
    }
  }
  const cm = Number(data.WAIST) || 0;
  const male = Number(data.SEX) === 1;
  const cut = male ? 102 : 88;

  return (
    <div className="bmi-group">
      <div className="bmi-group-title">Waist circumference</div>
      <div className={`field ${check.state === "hard" ? "invalid" : ""}`}>
        <label>
          Waist <span className="unit">measured at the top of the hip bones</span>
        </label>
        <div className="waist-row">
          <input type="number" step="0.1" value={shown} placeholder={unit === "in" ? "inches" : "cm"}
            onChange={(e) => setValue(e.target.value)} />
          <div className="mode-toggle-inline" role="group" aria-label="Waist unit">
            {["in", "cm"].map((u) => (
              <button key={u} type="button" className={unit === u ? "active" : ""} onClick={() => onChange("WAIST_UNIT", u)}>
                {u}
              </button>
            ))}
          </div>
        </div>
        {check.state === "hard" && <span className="field-error">{check.message}</span>}
        {check.state === "soft" && <span className="field-error" style={{ color: "var(--amber-500)" }}>{check.message}</span>}
      </div>
      {cm > 0 && check.state !== "hard" && (
        <div className="bmi-readout">
          <span className="range-hint">{unit === "in" ? `${cm} cm` : `${(cm / 2.54).toFixed(1)} in`}</span>
          {data.SEX !== "" && (
            <span className={`risk-badge ${cm >= cut ? "high" : "low"}`}>{cm >= cut ? "Above" : "Below"} the {male ? "40 in / 102 cm" : "35 in / 88 cm"} cut-point</span>
          )}
        </div>
      )}
      <div className="range-hint">
        How to measure: stand up, breathe out normally, and wrap a tape measure around your bare belly just above the
        hip bones, level all the way round and snug but not pressing into the skin. Not sure? It's usually a bit above
        your pants size.
      </div>
    </div>
  );
}
