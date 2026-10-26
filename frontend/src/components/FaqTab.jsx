import React from "react";
import { MODEL_SPEC as M } from "../localModel.js";

const FAQS = [
  {
    q: "Is this a substitute for medical advice?",
    a: "No. vitalCKM Metabolic Screen is an educational tool. It helps you understand where you stand and what would help. A clinician diagnoses metabolic syndrome from measured blood pressure and fasting lab results, alongside your full history.",
  },
  {
    q: "What is metabolic syndrome, and why does it matter?",
    a: "It's a cluster of five linked risk factors: a large waist, high triglycerides, low HDL cholesterol, high blood pressure and high fasting blood sugar. Having three or more roughly doubles the risk of heart disease and raises the risk of type 2 diabetes several-fold. About a third of US adults have it.",
  },
  {
    q: "What's the difference between the Quick Screen and the criteria check?",
    a: "The criteria check applies the official definition to the values you enter; it isn't a model, and it's the real answer when you have all five values. The Quick Screen is a model that estimates the chance you have metabolic syndrome from age, sex, background, BMI and waist alone. It's useful when you haven't had a recent blood test.",
  },
  {
    q: "How accurate is the Quick Screen?",
    a: `In cross-validation (every person scored by a model that never saw them) its AUC is ${M.validation.auc.toFixed(2)} (95% interval ${M.validation.auc_ci95[0].toFixed(2)}–${M.validation.auc_ci95[1].toFixed(2)}), and its percentages match what was observed. It still misses some people and flags some who don't have metabolic syndrome, so a blood test is the way to be sure. See the Model & Data tab for details by age, sex and background.`,
  },
  {
    q: "Why do you ask about race and ethnicity?",
    a: "At the same waist size, metabolic syndrome is more common in some groups. In this data that includes Asian, Mexican American and other Hispanic adults, which is also why some guidelines use lower waist cut-points for Asian ancestry. Including it makes the estimate more accurate. It's optional: choose \"Prefer not to say\" and the model uses an average across groups.",
  },
  {
    q: "How do I measure my waist?",
    a: "Stand up and breathe out normally. Wrap a tape measure around your bare belly just above the top of your hip bones (usually around the belly button), keeping it level all the way round and snug without pressing into the skin. Read it at the end of a normal breath out.",
  },
  {
    q: "Why can't I use this if I'm pregnant?",
    a: "Waist size, blood sugar and blood fats all change during pregnancy, so the criteria and the model don't apply. Your prenatal care includes the checks that matter during pregnancy.",
  },
  {
    q: "What's the 'What's driving your Quick Screen' chart showing?",
    a: "For each factor, how many percentage points it moves your estimate compared with the average adult in the survey. Because the model is a logistic regression, these are exact and add up to the difference between your estimate and the average.",
  },
  {
    q: "What does the Research tab have to do with my result?",
    a: "Nothing directly. It shows three studies from VitalCKM's research collection: a nutrition crossover trial, a preclinical rodent study and a metabolomics study. None is used by the screen, because none has the kind of outcome needed to train it.",
  },
  {
    q: "Is my data saved anywhere?",
    a: "If you have an account, your assessments are saved so you can track your waist, BMI and criteria over time and export a PDF. You can delete any assessment from the Progress tab. The What-If simulator runs entirely in your browser.",
  },
];

export default function FaqTab() {
  return (
    <div className="faq">
      <h2 className="page-title">Frequently asked questions</h2>

      <div className="hero-disclosure" role="note">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#6b4419" strokeWidth="2">
          <path d="M12 9v4M12 17h.01M10.29 3.86l-8.18 14.18A2 2 0 0 0 3.82 21h16.36a2 2 0 0 0 1.71-2.96L13.71 3.86a2 2 0 0 0-3.42 0z" />
        </svg>
        <span>Educational screening tool only. This is not a medical diagnosis — talk to a healthcare provider about your metabolic health.</span>
      </div>

      <div className="faq-list">
        {FAQS.map((item) => (
          <div className="faq-item" key={item.q}>
            <h3>{item.q}</h3>
            <p>{item.a}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
