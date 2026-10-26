import React from "react";
import { FieldInput, BMIGroupInput, WaistGroupInput } from "./FieldInput.jsx";
import { STEPS, stepHasHardErrors, stepIncomplete, outOfScope as isOutOfScope } from "../constants.js";

export default function WizardForm({ data, onChange, stepIndex, onBack, onNext, onSubmit, submitting }) {
  const step = STEPS[stepIndex];
  const isLast = stepIndex === STEPS.length - 1;
  const outOfScope = step.features.includes("PREGNANT") && isOutOfScope(data);
  const hasErrors = stepHasHardErrors(step.features, data) || stepIncomplete(step.features, data);

  return (
    <div className="wizard">
      <div className="wizard-progress" role="progressbar" aria-valuenow={stepIndex + 1} aria-valuemin={1} aria-valuemax={STEPS.length}>
        {STEPS.map((s, i) => (
          <div key={s.id} className={`wizard-progress-seg ${i <= stepIndex ? "done" : ""}`} />
        ))}
      </div>
      <div className="wizard-stepmeta">
        <span>STEP {stepIndex + 1} OF {STEPS.length}</span>
        <span>{step.title.toUpperCase()}</span>
      </div>

      <div className="wizard-body">
        <div className="wizard-intro">
          <h2>{step.title}</h2>
          {step.intro && <p className="range-hint" style={{ marginTop: 4 }}>{step.intro}</p>}
        </div>
        {outOfScope && (
          <div className="age-warning" role="alert">
            <div className="age-warning-title">This screen isn't designed for pregnancy</div>
            <p>
              Waist size, blood sugar and blood fats all change during pregnancy, so the metabolic syndrome criteria
              don't apply. Your prenatal care team checks blood pressure and blood sugar as part of routine care. You're
              welcome to use this screen after your pregnancy.
            </p>
          </div>
        )}
        <div className="wizard-fields">
          {step.features.map((f) =>
            f === "BMI_GROUP" ? (
              <BMIGroupInput key="bmi" data={data} onChange={onChange} />
            ) : f === "WAIST_GROUP" ? (
              <WaistGroupInput key="waist" data={data} onChange={onChange} />
            ) : (
              <FieldInput key={f} name={f} value={data[f]} onChange={onChange} data={data} />
            )
          )}
        </div>
      </div>

      <div className="wizard-nav">
        <button type="button" className="btn-secondary" onClick={onBack} disabled={stepIndex === 0}>
          ← Back
        </button>
        {isLast ? (
          <button type="button" className="btn-primary" onClick={onSubmit} disabled={submitting || hasErrors}>
            {submitting ? "Calculating…" : "See my results"}
          </button>
        ) : (
          <button type="button" className="btn-primary" onClick={onNext} disabled={hasErrors}>
            Continue →
          </button>
        )}
      </div>
    </div>
  );
}
