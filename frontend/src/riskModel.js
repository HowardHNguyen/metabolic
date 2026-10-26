// Exact JavaScript port of backend/app/model.py. Same artifact (model.json), same arithmetic, so the browser produces
// the same probabilities, criteria results and percentiles as the API. Kept free of imports so it can be unit-tested in
// Node (frontend/tests/riskModel.test.mjs checks it against golden values that ml/train_final.py computes from the
// trained scikit-learn model).

const FRIENDLY = { AGE: "Age", SEX: "Sex", RACE: "Race / ethnicity", BMI: "Body weight (BMI)", WAIST: "Waist size" };
const RACE_LABEL = { MexAmerican: "Mexican American" };

const sigmoid = (z) => (z >= 0 ? 1 / (1 + Math.exp(-z)) : Math.exp(z) / (1 + Math.exp(z)));
const num = (v) => {
  if (v === null || v === undefined || v === "") return null;
  const f = Number(v);
  return Number.isNaN(f) ? null : f;
};
const report = (f) => (f === "MALE" ? "SEX" : f.startsWith("RACE_") ? "RACE" : f);
const rnd = (v) => Math.round(v * 1e5) / 1e5;

export function createRiskModel(spec) {
  const coef = Object.fromEntries(spec.features.map((f, i) => [f, spec.coef[i]]));
  const m = spec.base_profile;
  const crit = Object.fromEntries(spec.criteria.map((c) => [c.id, c]));

  function baseDesign(inp) {
    const race = inp.RACE || "Unknown";
    const x = { AGE: Number(inp.AGE), MALE: Number(inp.SEX) === 1 ? 1 : 0, BMI: Number(inp.BMI), WAIST: Number(inp.WAIST) };
    for (const [r, f] of Object.entries(spec.race_features)) {
      x[f] = spec.races.includes(race) ? (race === r ? 1 : 0) : m[f];
    }
    return x;
  }
  function withTerms(x) {
    const out = { ...x };
    for (const [name, t] of Object.entries(spec.terms)) {
      out[name] = t.type === "product" ? out[t.a] * out[t.b] : (out[t.a] - t.center) ** 2;
    }
    return out;
  }
  const z = (x) => spec.intercept + spec.features.reduce((s, f) => s + coef[f] * x[f], 0);
  const design = (inp) => withTerms(baseDesign(inp));
  const logit = (inp) => z(design(inp));
  const predictProb = (inp) => sigmoid(logit(inp));

  function category(p) {
    for (const t of spec.tiers) if (p < t.max) return t.tier;
    return spec.tiers[spec.tiers.length - 1].tier;
  }

  // ---- criteria check (rule-based)
  function criteriaCheck(inp) {
    const male = Number(inp.SEX) === 1;
    const waist = num(inp.WAIST), tg = num(inp.TG), hdl = num(inp.HDL);
    const sbp = num(inp.SYSBP), dbp = num(inp.DIABP), glu = num(inp.GLUCOSE);
    const yes = (k) => Boolean(num(inp[k]));
    const rows = [];
    const add = (id, status, value, reason) => rows.push({ id, label: crit[id].label, rule: crit[id].rule, status, value, reason });
    const g = (v) => String(v); // matches Python's :g for the integers and short decimals people enter

    if (waist === null) add("waist", "unknown", null, "Waist not entered");
    else {
      const cut = male ? crit.waist.male_min : crit.waist.female_min;
      add("waist", waist >= cut ? "met" : "not_met", waist, `Waist ${g(waist)} cm vs ${cut} cm`);
    }
    if (yes("TG_MEDS")) add("tg", "met", tg, "On medicine for high triglycerides");
    else if (tg === null) add("tg", "unknown", null, "Triglycerides not entered");
    else add("tg", tg >= crit.tg.min ? "met" : "not_met", tg, `Triglycerides ${g(tg)} vs ${crit.tg.min} mg/dL`);
    if (yes("HDL_MEDS")) add("hdl", "met", hdl, "On medicine for low HDL");
    else if (hdl === null) add("hdl", "unknown", null, "HDL not entered");
    else {
      const cut = male ? crit.hdl.male_below : crit.hdl.female_below;
      add("hdl", hdl < cut ? "met" : "not_met", hdl, `HDL ${g(hdl)} vs below ${cut} mg/dL`);
    }
    if (yes("BPMEDS")) add("bp", "met", sbp, "On blood-pressure medicine");
    else if (sbp === null || dbp === null) add("bp", "unknown", null, "Blood pressure not entered");
    else {
      const hit = sbp >= crit.bp.sys_min || dbp >= crit.bp.dia_min;
      add("bp", hit ? "met" : "not_met", sbp, `Blood pressure ${g(sbp)}/${g(dbp)} vs 130/85 mmHg`);
    }
    if (yes("DIABETES")) add("glucose", "met", glu, "Diagnosed diabetes or on glucose-lowering medicine");
    else if (glu === null) add("glucose", "unknown", null, "Fasting glucose not entered");
    else add("glucose", glu >= crit.glucose.min ? "met" : "not_met", glu, `Fasting glucose ${g(glu)} vs ${crit.glucose.min} mg/dL`);

    const met = rows.filter((r) => r.status === "met").length;
    const unknown = rows.filter((r) => r.status === "unknown").length;
    const verdict = met >= 3 ? "meets" : met + unknown < 3 ? "does_not_meet" : "incomplete";
    return { criteria: rows, met, unknown, needed: 3, verdict };
  }

  // ---- NHANES reference percentiles
  function groupKey(sex, age) {
    let band = spec.percentiles.age_bands[spec.percentiles.age_bands.length - 1];
    for (const b of spec.percentiles.age_bands) {
      if (Number(age) <= b[1]) { band = b; break; }
    }
    return `${Number(sex) === 1 ? "M" : "F"}${band[0]}-${band[1]}`;
  }
  function percentile(variable, value, sex, age) {
    if (value === null || value === undefined) return null;
    const q = spec.percentiles.groups[groupKey(sex, age)].q[variable];
    let i = 0;
    while (i < q.length && q[i] < value) i++; // bisect_left
    if (i === 0) return 1;
    if (i >= q.length) return 99;
    const lo = q[i - 1], hi = q[i];
    const frac = hi > lo ? (value - lo) / (hi - lo) : 0;
    return Math.max(1, Math.min(99, Math.floor(i + frac + 0.5)));
  }
  function percentiles(inp) {
    const values = {};
    for (const v of ["WAIST", "BMI", "GLUCOSE", "HDL", "TG"]) {
      const x = num(inp[v]);
      if (x !== null) values[v] = { value: x, percentile: percentile(v, x, inp.SEX, inp.AGE) };
    }
    return { group: groupKey(inp.SEX, inp.AGE), values };
  }

  function result(inp) {
    const p = predictProb(inp);
    return {
      risk_probability: p, risk_percent: Math.round(p * 1000) / 10,
      risk_label: p >= spec.high_threshold ? 1 : 0, category: category(p),
      component_probs: { "Quick Screen (logistic)": p }, threshold_used: spec.high_threshold, model_version: spec.version,
      criteria: criteriaCheck(inp), percentiles: percentiles(inp),
    };
  }

  // Exact Shapley split of the log-odds (see model.py), mapped to probability points with the secant slope.
  function explain(inp, topK = 8) {
    const xb = baseDesign(inp);
    const z0 = z(withTerms(m)), z1 = z(withTerms(xb));
    const p0 = sigmoid(z0), p = sigmoid(z1);
    const slope = Math.abs(z1 - z0) > 1e-9 ? (p - p0) / (z1 - z0) : p0 * (1 - p0);
    const grouped = {};
    const put = (f, v) => { grouped[report(f)] = (grouped[report(f)] || 0) + v; };
    for (const f of spec.base_features) put(f, coef[f] * (xb[f] - m[f]));
    for (const [name, t] of Object.entries(spec.terms)) {
      const c = coef[name];
      if (t.type === "product") {
        put(t.a, (c / 2) * (xb[t.a] - m[t.a]) * (xb[t.b] + m[t.b]));
        put(t.b, (c / 2) * (xb[t.b] - m[t.b]) * (xb[t.a] + m[t.a]));
      } else {
        put(t.a, c * ((xb[t.a] - t.center) ** 2 - (m[t.a] - t.center) ** 2));
      }
    }
    const race = inp.RACE || "Unknown";
    const valueOf = { SEX: Number(inp.SEX), RACE: RACE_LABEL[race] || race };
    const contributions = Object.entries(grouped).map(([key, c]) => {
      const v = c * slope;
      return {
        feature: key, friendly_name: FRIENDLY[key] || key, value: rnd(v), abs_value: rnd(Math.abs(v)),
        feature_value: key in valueOf ? valueOf[key] : xb[key], direction: v > 0 ? "increases" : "decreases",
      };
    }).sort((a, b) => b.abs_value - a.abs_value);
    return { base_value: rnd(p0), contributions: contributions.slice(0, topK) };
  }

  function scenarios(inp) {
    const baseline = result(inp);
    const out = [];
    const changes = {};
    const add = (name, description, change) => {
      const pred = result({ ...inp, ...change });
      out.push({
        name, description, risk_probability: pred.risk_probability, risk_percent: pred.risk_percent,
        delta_pp: Math.round((pred.risk_probability - baseline.risk_probability) * 10000) / 100,
      });
    };
    const W = Number(inp.WAIST), B = Number(inp.BMI);
    if (W > 80) {
      const v = Math.max(W - 5, 60);
      add("Trim waist by 5 cm (2 in)", `Waist: ${W.toFixed(0)} -> ${v.toFixed(0)} cm`, { WAIST: v }); changes.WAIST = v;
    }
    if (B > 25) {
      const v = Math.max(B - 2, 18.5);
      add("Lose weight (BMI down 2)", `BMI: ${B.toFixed(1)} -> ${v.toFixed(1)}`, { BMI: v }); changes.BMI = v;
    }
    if (Object.keys(changes).length) add("Both together", "Smaller waist and lower BMI", changes);
    return { baseline, scenarios: out };
  }

  return { design, logit, predictProb, category, result, explain, scenarios, criteriaCheck, percentile, percentiles, groupKey, spec };
}
