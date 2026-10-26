// Shared constants for the v1 metabolic model: Quick Screen (probability of metabolic syndrome now, no blood test)
// plus the rule-based criteria check. Ranges, tiers and criteria come from model.json so the UI cannot drift from it.
import { MODEL_SPEC } from "./localModel.js";

export const API_TIMEOUT_MS = 4000;
const R = MODEL_SPEC.ranges;

export const RACE_OPTIONS = [
  { v: "White", l: "White (non-Hispanic)" },
  { v: "Black", l: "Black (non-Hispanic)" },
  { v: "Asian", l: "Asian (non-Hispanic)" },
  { v: "MexAmerican", l: "Mexican American" },
  { v: "Hispanic", l: "Other Hispanic / Latino" },
  { v: "Other", l: "Other or multiracial" },
  { v: "Unknown", l: "Prefer not to say" },
];

export const FEATURES = {
  PREGNANT: { label: "Are you currently pregnant?", help: "Waist size and blood values change in pregnancy, so this screen doesn't apply.", type: "binary", onlyIf: (d) => Number(d.SEX) === 2 },
  SEX: { label: "Sex", help: "Biological sex assigned at birth. The waist and HDL cut-points differ for men and women.", type: "select", options: [{ v: 1, l: "Male" }, { v: 2, l: "Female" }] },
  AGE: { label: "Age (years)", help: `The model covers ages ${R.AGE[0]}–${R.AGE[1]}`, type: "number" },
  RACE: { label: "Race / ethnicity", help: "Used because metabolic syndrome is more common at the same waist size in some groups (for example, Asian and Hispanic adults). Optional.", type: "select", options: RACE_OPTIONS, stringValue: true },
  SYSBP: { label: "Systolic BP (top, mmHg)", help: "Top number, e.g. 130 in 130/80. Optional.", type: "number", optional: true },
  DIABP: { label: "Diastolic BP (bottom, mmHg)", help: "Bottom number. Optional.", type: "number", optional: true },
  GLUCOSE: { label: "Fasting blood sugar (mg/dL)", help: "From a test taken after not eating for 8+ hours. Optional.", type: "number", optional: true },
  HDL: { label: "HDL (“good”) cholesterol (mg/dL)", help: "From a lipid panel. Optional.", type: "number", optional: true },
  TG: { label: "Triglycerides (mg/dL)", help: "From a lipid panel, ideally fasting. Optional.", type: "number", optional: true },
  BPMEDS: { label: "Taking blood-pressure medicine?", help: "Counts toward the blood-pressure criterion.", type: "binary" },
  DIABETES: { label: "Diagnosed with diabetes, or taking medicine to lower blood sugar?", help: "Counts toward the blood-sugar criterion.", type: "binary" },
  TG_MEDS: { label: "Taking medicine for high triglycerides?", help: "For example fenofibrate, gemfibrozil, prescription omega-3 or niacin. Statins alone don't count.", type: "binary" },
  HDL_MEDS: { label: "Taking medicine prescribed for low HDL?", help: "Usually niacin or a fibrate. Statins alone don't count.", type: "binary" },
};

// Fields sent to the API, in order. WAIST is sent in cm (the wizard also accepts inches).
export const FEATURE_ORDER = ["PREGNANT", "SEX", "AGE", "RACE", "BMI", "WAIST", "SYSBP", "DIABP", "GLUCOSE", "HDL", "TG",
  "BPMEDS", "DIABETES", "TG_MEDS", "HDL_MEDS"];
const OPTIONAL_NUMBERS = ["SYSBP", "DIABP", "GLUCOSE", "HDL", "TG"];

export const STEPS = [
  { id: "about", title: "About you", features: ["SEX", "PREGNANT", "AGE", "RACE"] },
  { id: "body", title: "Body measurements", features: ["BMI_GROUP", "WAIST_GROUP"] },
  { id: "labs", title: "Blood pressure & labs (optional)", features: ["SYSBP", "DIABP", "GLUCOSE", "HDL", "TG"],
    intro: "Skip anything you don't know. Your Quick Screen result doesn't need these; they let us check the five official criteria one by one." },
  { id: "meds", title: "Conditions & medicines", features: ["BPMEDS", "DIABETES", "TG_MEDS", "HDL_MEDS"] },
];

// Two-tier validation: soft = typical clinical range (warns), hard = range the model supports and the API enforces.
export const FIELD_RANGES = {
  AGE: { soft: [20, 80], hard: R.AGE, unit: "years" },
  BMI: { soft: [17, 45], hard: R.BMI, unit: "" },
  WAIST: { soft: [60, 150], hard: R.WAIST, unit: "cm" },
  SYSBP: { soft: [90, 180], hard: R.SYSBP, unit: "mmHg" },
  DIABP: { soft: [55, 110], hard: R.DIABP, unit: "mmHg" },
  GLUCOSE: { soft: [65, 250], hard: R.GLUCOSE, unit: "mg/dL" },
  HDL: { soft: [25, 100], hard: R.HDL, unit: "mg/dL" },
  TG: { soft: [40, 500], hard: R.TG, unit: "mg/dL" },
  HEIGHT_FT: { soft: [4, 7], hard: [3, 8], unit: "ft" },
  HEIGHT_IN: { soft: [0, 11], hard: [0, 11], unit: "in" },
  WEIGHT_LB: { soft: [80, 350], hard: [50, 700], unit: "lbs" },
};

const isBlank = (v) => v === "" || v === null || v === undefined || Number.isNaN(Number(v));

export function validateField(feature, value, data) {
  const range = FIELD_RANGES[feature];
  if (!range) return { state: "ok", message: null };
  if (isBlank(value)) {
    if ((feature === "SYSBP" || feature === "DIABP") && data) {
      const other = feature === "SYSBP" ? data.DIABP : data.SYSBP;
      if (!isBlank(other)) return { state: "hard", message: "Enter both blood-pressure numbers, or neither" };
    }
    return { state: "ok", message: null };
  }
  const n = Number(value);
  const [hardMin, hardMax] = range.hard;
  const [softMin, softMax] = range.soft;
  const unit = range.unit ? ` ${range.unit}` : "";
  if (n < hardMin || n > hardMax) return { state: "hard", message: `Must be between ${hardMin} and ${hardMax}${unit}` };
  if (feature === "DIABP" && data && !isBlank(data.SYSBP) && n >= Number(data.SYSBP)) {
    return { state: "hard", message: "Must be lower than the systolic (top) number" };
  }
  if (n < softMin || n > softMax) return { state: "soft", message: `Unusual value — typical range is ${softMin}–${softMax}${unit}` };
  return { state: "ok", message: null };
}

export const outOfScope = (data) => Number(data.SEX) === 2 && Number(data.PREGNANT) === 1;

export function stepHasHardErrors(features, data) {
  if (features.includes("PREGNANT") && outOfScope(data)) return true;
  const fields = features.flatMap((f) => (f === "WAIST_GROUP" ? ["WAIST"] : f === "BMI_GROUP" ? ["BMI"] : [f]));
  return fields.some((f) => FIELD_RANGES[f] && validateField(f, data[f], data).state === "hard");
}

// Fields every assessment must have before it can be submitted.
export const REQUIRED = ["SEX", "AGE", "BMI", "WAIST"];
export const missingRequired = (data) => REQUIRED.filter((f) => isBlank(data[f]));
export const stepIncomplete = (features, data) => features.some((f) =>
  f === "BMI_GROUP" ? isBlank(data.BMI) : f === "WAIST_GROUP" ? isBlank(data.WAIST) : REQUIRED.includes(f) && isBlank(data[f]));

export function initialData() {
  const d = {};
  FEATURE_ORDER.forEach((f) => {
    const cfg = FEATURES[f];
    if (!cfg) d[f] = "";
    else if (cfg.type === "binary") d[f] = 0;
    else d[f] = "";
  });
  d.RACE = "";
  d.HEIGHT_FT = "";
  d.HEIGHT_IN = "";
  d.WEIGHT_LB = "";
  d.WAIST_IN = "";
  d.WAIST_UNIT = "in";
  return d;
}

// Payload for the API: numbers as numbers, blank optional values left out, waist in cm.
export function buildPayload(data) {
  const payload = {};
  FEATURE_ORDER.forEach((f) => {
    const cfg = FEATURES[f];
    if (f === "RACE") payload.RACE = data.RACE || "Unknown";
    else if (cfg?.type === "binary") payload[f] = data[f] ? 1 : 0;
    else if (OPTIONAL_NUMBERS.includes(f)) { if (!isBlank(data[f])) payload[f] = Number(data[f]); }
    else payload[f] = Number(data[f]);
  });
  payload.PREGNANT = outOfScope(data);
  if (data.HEIGHT_FT !== "" && data.HEIGHT_IN !== "") {
    payload.HEIGHT_FT = Number(data.HEIGHT_FT);
    payload.HEIGHT_IN = Number(data.HEIGHT_IN);
  }
  if (data.WEIGHT_LB !== "") payload.WEIGHT_LB = Number(data.WEIGHT_LB);
  return payload;
}

// Quick Screen probability tiers, read from model.json.
const pct = (x) => `${Math.round(x * 100)}%`;
export const RISK_LEVELS = MODEL_SPEC.tiers.map((t, i, a) => ({
  label: t.label, tier: t.tier,
  range: i === 0 ? `< ${pct(t.max)}` : i === a.length - 1 ? `≥ ${pct(t.min)}` : `${pct(t.min)} – < ${pct(t.max)}`,
  min: t.min, max: t.max,
}));

export function categorize(prob) {
  const t = MODEL_SPEC.tiers.find((x) => prob < x.max) || MODEL_SPEC.tiers[MODEL_SPEC.tiers.length - 1];
  return { label: t.label, tier: t.tier };
}
export const tierLabel = (tier) => (MODEL_SPEC.tiers.find((t) => t.tier === tier) || {}).label || tier;

export const VERDICT = {
  meets: { title: "Meets the criteria for metabolic syndrome", tone: "high" },
  does_not_meet: { title: "Does not meet the criteria", tone: "low" },
  incomplete: { title: "Not enough information to decide", tone: "borderline" },
};

// What-If: model inputs (change the Quick Screen probability) and lab values (change the criteria check only).
export const SLIDER_FIELDS = [
  { key: "WAIST", label: "Waist", unit: "cm", min: 60, max: 160, step: 1, model: true },
  { key: "BMI", label: "Body mass index", unit: "", min: 16, max: 55, step: 0.5, model: true },
];
export const LAB_SLIDERS = [
  { key: "TG", label: "Triglycerides", unit: "mg/dL", min: 40, max: 500, step: 5 },
  { key: "HDL", label: "HDL cholesterol", unit: "mg/dL", min: 20, max: 100, step: 1 },
  { key: "GLUCOSE", label: "Fasting glucose", unit: "mg/dL", min: 65, max: 200, step: 1 },
  { key: "SYSBP", label: "Systolic blood pressure", unit: "mmHg", min: 90, max: 190, step: 1 },
];

// "If you changed only this one factor" counterfactual targets for the Quick Screen.
export const healthyWaist = (b) => (Number(b.SEX) === 1 ? 94 : 80);
export const COUNTERFACTUALS = [
  { key: "WAIST", label: "Trim waist by 5 cm (2 in)", target: (b) => Math.max(Number(b.WAIST) - 5, 60), onlyIf: (b) => Number(b.WAIST) > 80 },
  { key: "WAIST", label: "Reach a low-risk waist (men 94 cm, women 80 cm)", target: healthyWaist, onlyIf: (b) => Number(b.WAIST) > healthyWaist(b) },
  { key: "BMI", label: "Lower BMI by 2", target: (b) => Math.max(Number(b.BMI) - 2, 18.5), onlyIf: (b) => Number(b.BMI) > 25 },
];

export function buildCombinedScenario(baseline) {
  const combined = { ...baseline };
  if (Number(baseline.WAIST) > healthyWaist(baseline)) combined.WAIST = healthyWaist(baseline);
  if (Number(baseline.BMI) > 25) combined.BMI = Math.max(Number(baseline.BMI) - 2, 18.5);
  return combined;
}

// Rule-based coaching recommendations from the criteria check and the measurements.
export function buildCoachingRecs(d, criteria) {
  const recs = [];
  const status = (id) => criteria?.criteria?.find((c) => c.id === id)?.status;
  const male = Number(d.SEX) === 1;
  const waist = Number(d.WAIST);
  if (status("waist") === "met") recs.push({
    title: "Waist size", severity: "high",
    detail: `A waist of ${waist.toFixed(0)} cm (${(waist / 2.54).toFixed(1)} in) is above the ${male ? "102 cm / 40 in" : "88 cm / 35 in"} cut-point. Fat stored around the middle drives the other four criteria. Losing 5–10% of body weight through calorie reduction and 150+ minutes a week of activity typically trims several centimetres and improves triglycerides, HDL, blood pressure and blood sugar together.`,
  });
  else if (waist > healthyWaist(d)) recs.push({
    title: "Waist size", severity: "medium",
    detail: `Your waist (${waist.toFixed(0)} cm) is below the criteria cut-point but above the lower-risk level of ${healthyWaist(d)} cm. Keeping it from rising is one of the most effective ways to prevent metabolic syndrome.`,
  });
  if (status("tg") === "met") recs.push({
    title: "Triglycerides", severity: Number(d.TG) >= 500 ? "high" : "medium",
    detail: `${d.TG ? `Triglycerides of ${d.TG} mg/dL are` : "Your triglycerides are"} above 150 mg/dL. Cutting sugar-sweetened drinks, refined carbohydrates and alcohol, and adding oily fish and activity, often lowers them substantially. Levels of 500 mg/dL or more need prompt medical review.`,
  });
  if (status("hdl") === "met") recs.push({
    title: "HDL (“good”) cholesterol", severity: "medium",
    detail: `HDL below ${male ? 40 : 50} mg/dL is one of the criteria. Regular aerobic exercise, weight loss, stopping smoking and replacing refined carbohydrates with unsaturated fats can raise it.`,
  });
  if (status("bp") === "met") recs.push({
    title: "Blood pressure", severity: Number(d.SYSBP) >= 140 || Number(d.DIABP) >= 90 ? "high" : "medium",
    detail: `${d.SYSBP ? `A reading of ${d.SYSBP}/${d.DIABP} mmHg` : "Your blood pressure"} meets the criterion (130/85 or above, or treated). DASH-style eating, sodium under 2.3 g a day, limiting alcohol and regular activity help; ask about home monitoring.`,
  });
  if (status("glucose") === "met") recs.push({
    title: "Blood sugar", severity: Number(d.DIABETES) === 1 || Number(d.GLUCOSE) >= 126 ? "high" : "medium",
    detail: Number(d.DIABETES) === 1
      ? "With diabetes, work with your care team on an individual HbA1c goal and heart- and kidney-protective treatment."
      : `A fasting glucose of ${d.GLUCOSE} mg/dL is above 100${Number(d.GLUCOSE) >= 126 ? " and in the diabetes range on a single test" : " (the prediabetes range starts here)"}. Ask your clinician about an HbA1c test. A structured lifestyle program (such as the CDC National Diabetes Prevention Program) cuts the chance of progressing to type 2 diabetes by more than half.`,
  });
  const unknown = (criteria?.criteria || []).filter((c) => c.status === "unknown").map((c) => c.label.toLowerCase());
  if (unknown.length) recs.push({
    title: "Complete the picture", severity: "low",
    detail: `We couldn't check: ${unknown.join(", ")}. A fasting lipid panel, a fasting glucose (or HbA1c) and a blood-pressure reading — all routine at a check-up — would let you see all five criteria.`,
  });
  if (recs.length === 0) recs.push({
    title: "Maintain current health practices", severity: "low",
    detail: "None of the five criteria are met. Keep up regular activity, a balanced diet and routine check-ups, and recheck if your weight or waist changes.",
  });
  return recs;
}

export function formatChartDate(d) {
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const time = d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  if (sameDay) return time;
  return `${d.getMonth() + 1}/${d.getDate()} ${time}`;
}

export const PCT_LABELS = { WAIST: "Waist", BMI: "BMI", GLUCOSE: "Fasting glucose", HDL: "HDL cholesterol", TG: "Triglycerides" };
export const PCT_UNITS = { WAIST: "cm", BMI: "kg/m²", GLUCOSE: "mg/dL", HDL: "mg/dL", TG: "mg/dL" };
export function groupLabel(key) {
  const sex = key.startsWith("M") ? "men" : "women";
  return `US ${sex} aged ${key.slice(1).replace("-", "–")}`;
}
