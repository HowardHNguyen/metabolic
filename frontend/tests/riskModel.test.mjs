// Run: node --test frontend/tests   (no dependencies)
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRiskModel } from "../src/riskModel.js";

const spec = JSON.parse(readFileSync(new URL("../src/model.json", import.meta.url)));
const backendSpec = JSON.parse(readFileSync(new URL("../../backend/artifacts/models_v1_mets/model.json", import.meta.url)));
const M = createRiskModel(spec);
const BASE = { SEX: 1, AGE: 52, RACE: "Black", BMI: 31, WAIST: 106 };

test("frontend and backend ship the same model artifact", () => {
  assert.deepEqual(spec, backendSpec);
});

test("matches the trained scikit-learn model on golden cases", () => {
  for (const g of spec.golden) assert.ok(Math.abs(M.predictProb(g.input) - g.p) < 1e-9, JSON.stringify(g.input));
});

test("explanations sum to probability - base_value", () => {
  for (const g of [...spec.golden.map((x) => x.input), { ...BASE, RACE: "Unknown" }]) {
    const ex = M.explain(g, 50);
    const sum = ex.contributions.reduce((s, c) => s + c.value, 0);
    assert.ok(Math.abs(sum - (M.predictProb(g) - ex.base_value)) < 1e-4);
  }
});

test("unknown race contributes nothing", () => {
  const ex = M.explain({ ...BASE, RACE: "Unknown" }, 50);
  assert.ok(Math.abs(ex.contributions.find((c) => c.feature === "RACE").value) < 1e-9);
});

test("scenarios never increase the probability and 'both together' is the best", () => {
  const { scenarios } = M.scenarios(BASE);
  assert.ok(scenarios.length === 3 && scenarios.every((s) => s.delta_pp <= 0));
  assert.ok(scenarios.at(-1).delta_pp <= Math.min(...scenarios.slice(0, -1).map((s) => s.delta_pp)) + 1e-9);
});

test("tiers", () => {
  const cats = [0, 0.149, 0.15, 0.399, 0.4, 0.649, 0.65, 0.99].map((p) => M.category(p));
  assert.deepEqual(cats, ["low", "low", "borderline", "borderline", "intermediate", "intermediate", "high", "high"]);
});

test("criteria check matches the definition", () => {
  const r = M.criteriaCheck({ ...BASE, SYSBP: 134, DIABP: 84, GLUCOSE: 104, HDL: 38, TG: 168 });
  assert.equal(r.met, 5);
  assert.equal(r.verdict, "meets");
  assert.equal(M.criteriaCheck({ SEX: 2, AGE: 40, WAIST: 87.9 }).criteria[0].status, "not_met");
  assert.equal(M.criteriaCheck({ SEX: 2, AGE: 40, WAIST: 88 }).criteria[0].status, "met");
  assert.equal(M.criteriaCheck({ SEX: 1, AGE: 40, WAIST: 80, TG: 100, HDL: 60 }).verdict, "does_not_meet");
  assert.equal(M.criteriaCheck({ SEX: 1, AGE: 40, WAIST: 110, TG: 100 }).verdict, "incomplete");
  assert.equal(M.criteriaCheck({ SEX: 1, AGE: 40, BPMEDS: 1, DIABETES: 1, TG_MEDS: 1 }).verdict, "meets");
});

test("percentiles are monotone, bounded and use the right group", () => {
  const vals = [60, 80, 95, 105, 120, 170].map((w) => M.percentile("WAIST", w, 1, 50));
  assert.deepEqual(vals, [...vals].sort((a, b) => a - b));
  assert.equal(vals[0], 1);
  assert.equal(vals.at(-1), 99);
  assert.equal(M.groupKey(2, 80), "F60-80");
  assert.equal(M.groupKey(1, 39), "M20-39");
});
