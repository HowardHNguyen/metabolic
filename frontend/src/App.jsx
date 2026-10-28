import React, { useEffect, useState } from "react";
import Landing from "./components/Landing.jsx";
import AuthPage from "./components/AuthPage.jsx";
import AppTopbar from "./components/AppTopbar.jsx";
import Header from "./components/Header.jsx";
import TopNav from "./components/TopNav.jsx";
import WizardForm from "./components/WizardForm.jsx";
import ResultsView from "./components/ResultsView.jsx";
import DoctorVisitSummary from "./components/DoctorVisitSummary.jsx";
import WhatIfTab from "./components/WhatIfTab.jsx";
import CoachTab from "./components/CoachTab.jsx";
import ModelDataTab from "./components/ModelDataTab.jsx";
import FaqTab from "./components/FaqTab.jsx";
import ResearchTab from "./components/ResearchTab.jsx";
import FamilyBar from "./components/FamilyBar.jsx";
import TrendTab from "./components/TrendTab.jsx";
import { ForgotPage, ResetPage, VerifyPage, ChangePasswordPage } from "./components/AccountEmailPages.jsx";
import { loadSession, saveSession } from "./session.js";
import { parseLocation } from "./linkRoute.js";
import { runPrediction, fetchAssessments, deleteAssessment, logout, logoutAll, ApiError } from "./api.js";
import { STEPS, initialData, stepHasHardErrors, formatChartDate, categorize, buildPayload } from "./constants.js";
import { MODEL } from "./localModel.js";

function getRoute() {
  if (typeof window === "undefined") return "landing";
  // hash routes (#/signin) and email-link paths (/verify?token=...); see linkRoute.js
  return parseLocation(window.location).route;
}
function go(r) {
  window.location.hash = r === "landing" ? "" : `/${r}`;
}

// Criteria met / not entered for a saved assessment, recomputed with the current rules.
function criteriaSummary(inputs) {
  try {
    const c = MODEL.criteriaCheck(inputs);
    return { met: c.met, unknown: c.unknown };
  } catch {
    return { met: null, unknown: null };
  }
}

export default function App() {
  const [route, setRoute] = useState(getRoute());
  const [user, setUser] = useState(() => loadSession());
  const [authFlash, setAuthFlash] = useState(null);

  useEffect(() => {
    const onHash = () => setRoute(getRoute());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  useEffect(() => {
    // Opening a confirmation or reset link means the person is (re)starting: a session left in this browser from an
    // earlier visit (or for an account that no longer exists) must not be carried into the new sign-in.
    if ((route === "verify" || route === "reset") && user) {
      setUser(null);
      saveSession(null);
    }
  }, [route]);  // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    // Plain-path entry points (/signin, /forgot) become hash routes, so later in-app navigation cannot mix the two.
    const { route: r, token } = parseLocation(window.location);
    if (!token && r !== "landing" && window.location.pathname !== "/") window.history.replaceState(null, "", `/#/${r}`);
  }, []);

  useEffect(() => {
    // loadSession() is the source of truth the moment after sign-in, before the user state has caught up
    if (route === "assess" && !user && !loadSession()) go("signup");
    if (route === "account" && !user && !loadSession()) go("signin");
  }, [route, user]);

  function handleAuthSuccess(u) {
    // Store the session FIRST and put the user and the destination into the same render. On WebKit (iPhone Safari and
    // in-app browsers) the "hashchange" from go() can be handled before React has applied setUser; the "assess needs a
    // user" guard below then saw route=assess with no user and sent a person who had just signed in to Create account.
    saveSession(u);
    setAuthFlash(null);
    setUser(u);
    setRoute("assess");
    go("assess");
  }
  function clearSession(next) {
    // Set the destination in the same render that clears the user; otherwise the "assess needs a user"
    // redirect below wins the race and sends everyone to the signup page.
    setRoute(next);
    setUser(null);
    saveSession(null);
    go(next);
  }
  async function handleSignOut() {
    if (user?.token) await logout(user.token); // revoke this device's token on the server
    clearSession("landing");
  }
  async function handleSignOutEverywhere() {
    if (user?.token) await logoutAll(user.token); // invalidate every token on every device
    clearSession("landing");
  }
  // After a password change the server issues this session a new token (every other session is ended).
  function handlePasswordChanged(res) {
    const u = { ...user, token: res.token };
    setUser(u);
    saveSession(u);
  }
  // The server rejected our token (expired, signed out elsewhere, suspended).
  function handleSessionExpired() {
    setAuthFlash("Your session has ended. Please sign in again.");
    clearSession("signin");
  }

  return (
    <>
      <FamilyBar current="metabolic" />
      {route === "landing" && (
        <Landing user={user} onStart={() => (user ? go("assess") : go("signup"))} onSignIn={() => go("signin")} />
      )}
      {(route === "signup" || route === "signin") && (
        <AuthPage mode={route} onSuccess={handleAuthSuccess} onSwitchMode={(m) => { if (m !== "signin") setAuthFlash(null); go(m); }} flash={authFlash} />
      )}
      {route === "forgot" && <ForgotPage onNavigate={(r) => go(r)} />}
      {route === "reset" && (
        <ResetPage onNavigate={(r) => go(r)} onDone={(msg) => { setAuthFlash(msg); go("signin"); }} />
      )}
      {route === "verify" && <VerifyPage onNavigate={(r) => go(r)} />}
      {route === "account" && user && (
        <>
          <AppTopbar email={user.email} onSignOut={handleSignOut} onSignOutEverywhere={handleSignOutEverywhere} onHome={() => go("landing")} />
          <ChangePasswordPage token={user.token} onChanged={handlePasswordChanged} onSessionExpired={handleSessionExpired} onBack={() => go("assess")} />
        </>
      )}
      {route === "assess" && user && (
        <>
          <AppTopbar email={user.email} onSignOut={handleSignOut} onSignOutEverywhere={handleSignOutEverywhere} onHome={() => go("landing")} onAccount={() => go("account")} />
          <AssessmentApp authToken={user.token} onSessionExpired={handleSessionExpired} />
        </>
      )}
    </>
  );
}

function AssessmentApp({ authToken, onSessionExpired }) {
  const [tab, setTab] = useState("calc");
  const [showVisitSummary, setShowVisitSummary] = useState(false);
  const [data, setData] = useState(initialData());
  const [step, setStep] = useState(0);
  const [prediction, setPrediction] = useState(null);
  const [scenarios, setScenarios] = useState(null);
  const [explanation, setExplanation] = useState(null);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(false);
  const [predictionSource, setPredictionSource] = useState(null);
  const [cleanPayload, setCleanPayload] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!authToken) return;
    let cancelled = false;
    // One quiet retry before ending the session: a single rejected request right after sign-in (a stale in-flight
    // request, a flaky mobile connection) must not throw a person who just signed in back to the sign-in page.
    const load = async () => {
      let list = await fetchAssessments(authToken);
      if (list === null) {
        await new Promise((r) => setTimeout(r, 1200));
        if (cancelled) return undefined;
        list = await fetchAssessments(authToken);
      }
      return list;
    };
    load().then((list) => {
      if (cancelled || list === undefined) return;
      if (list === null) { onSessionExpired(); return; }
      const items = (list || []).slice().reverse().map((a) => {
        const inputs = typeof a.inputs === "string" ? JSON.parse(a.inputs) : a.inputs;
        const ts = new Date(a.created_at);
        return {
          id: a.id,
          timestamp: ts.getTime(),
          date: formatChartDate(ts),
          risk: Number(a.risk_percent),
          probability: Number(a.risk_probability),
          // recomputed from the stored probability, so entries saved under earlier cut-points show the current levels
          category: categorize(Number(a.risk_probability)).tier,
          ...criteriaSummary(inputs),
          waist: Number(inputs.WAIST),
          bmi: Number(inputs.BMI),
          // a different major model version is not comparable; kept only so it can be deleted
          legacy: !String(a.model_version || "").startsWith("1."),
          inputs,
        };
      });
      setHistory(items);
    });
    return () => { cancelled = true; };  // a request made with an older token must not act on a newer session
  }, [authToken]);

  function handleChange(name, value) {
    setData((d) => ({ ...d, [name]: value }));
  }

  function handleNext() {
    const s = STEPS[step];
    if (stepHasHardErrors(s.features, data)) return;
    setStep((s2) => Math.min(s2 + 1, STEPS.length - 1));
  }
  function handleBack() {
    setStep((s) => Math.max(s - 1, 0));
  }

  async function handleSubmit() {
    const s = STEPS[step];
    if (stepHasHardErrors(s.features, data)) return;
    setLoading(true);
    setError(null);
    try {
      const payload = buildPayload(data);

      setCleanPayload(payload);
      const result = await runPrediction(payload, authToken);
      setPrediction(result.prediction);
      setScenarios(result.scenarios);
      setExplanation(result.explanation);
      setPredictionSource(result.source);

      // Signed in but nothing was saved: the server no longer accepts this token (e.g. signed out on another device).
      if (authToken && result.source === "api" && !result.prediction?.assessment_id) {
        if ((await fetchAssessments(authToken)) === null) onSessionExpired();
      }

      if (result.prediction?.assessment_id && authToken) {
        const now = new Date();
        setHistory((prev) => [...prev, {
          id: result.prediction.assessment_id,
          timestamp: now.getTime(),
          date: formatChartDate(now),
          risk: result.prediction.risk_percent,
          probability: result.prediction.risk_probability,
          category: result.prediction.category,
          met: result.prediction.criteria?.met,
          unknown: result.prediction.criteria?.unknown,
          waist: Number(data.WAIST),
          bmi: Number(data.BMI),
          legacy: false,
          inputs: { ...data, ...payload },
        }]);
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  function handleNewAssessment() {
    setData(initialData());
    setStep(0);
    setPrediction(null);
    setScenarios(null);
    setExplanation(null);
    setPredictionSource(null);
    setCleanPayload(null);
    setError(null);
    setShowVisitSummary(false);
    setTab("calc");
  }

  function handleTabChange(nextTab) {
    setShowVisitSummary(false);
    setTab(nextTab);
  }

  function handleRecalculate(historyEntry) {
    if (historyEntry.inputs) {
      const newData = initialData();
      Object.keys(historyEntry.inputs).forEach((k) => (newData[k] = historyEntry.inputs[k]));
      ["SYSBP", "DIABP", "GLUCOSE", "HDL", "TG", "HEIGHT_FT", "HEIGHT_IN", "WEIGHT_LB"].forEach((k) => {
        if (newData[k] === null || newData[k] === undefined) newData[k] = "";
      });
      newData.PREGNANT = 0;
      newData.WAIST_UNIT = "cm";
      newData.WAIST_IN = newData.WAIST ? Math.round((Number(newData.WAIST) / 2.54) * 10) / 10 : "";
      setData(newData);
    }
    setPrediction(null);
    setScenarios(null);
    setExplanation(null);
    setTab("calc");
    setStep(0);
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  async function handleDelete(id) {
    const ok = await deleteAssessment(id, authToken);
    if (ok) setHistory((prev) => prev.filter((h) => h.id !== id));
  }

  return (
    <>
      <Header />
      <TopNav active={tab} onChange={handleTabChange} resultAvailable={!!prediction} />
      {predictionSource === "offline" && (
        <div className="demo-banner">
          <div className="shell">
            <strong>Offline mode.</strong>&nbsp;We couldn't reach the server, so this result was calculated on your device with the same model. It was not saved to your history.
          </div>
        </div>
      )}
      {error && (
        <div className="shell">
          <div className="error-banner" role="alert">{error}</div>
        </div>
      )}

      <div className="shell app-body">
        {tab === "calc" && (
          <>
            {prediction ? (
              showVisitSummary ? (
                <DoctorVisitSummary
                  data={data}
                  prediction={prediction}
                  explanation={explanation}
                  onBack={() => setShowVisitSummary(false)}
                />
              ) : (
                <ResultsView
                  data={data}
                  prediction={prediction}
                  explanation={explanation}
                  scenarios={scenarios}
                  onNewAssessment={handleNewAssessment}
                  onGoToCoach={() => handleTabChange("coach")}
                  onGoToVisitSummary={() => setShowVisitSummary(true)}
                />
              )
            ) : (
              <>
                <h1 className="page-title">Let's check your metabolic health</h1>
                <p className="page-sub">Four short steps. Your age, sex, BMI and waist give an instant Quick Screen; add blood pressure and lab values if you have them to check all five metabolic syndrome criteria.</p>
                <WizardForm data={data} onChange={handleChange} stepIndex={step} onBack={handleBack} onNext={handleNext} onSubmit={handleSubmit} submitting={loading} />
              </>
            )}
          </>
        )}

        {tab === "trend" && <TrendTab history={history} userEmail="" onRecalculate={handleRecalculate} onDelete={handleDelete} />}

        {tab === "bie" && (
          prediction ? (
            <WhatIfTab baseline={cleanPayload} baselinePrediction={prediction} />
          ) : (
            <p className="empty-state">Run an assessment on the Screen tab first.</p>
          )
        )}

        {tab === "coach" && (
          prediction ? <CoachTab data={data} criteria={prediction.criteria} /> : <p className="empty-state">Run an assessment on the Screen tab first.</p>
        )}

        {tab === "model" && <ModelDataTab predictionSource={predictionSource} />}

        {tab === "research" && <ResearchTab />}

        {tab === "faq" && <FaqTab />}
      </div>

      <footer className="site-footer">
        <div className="shell">
          vitalCKM Metabolic Screen · educational tool, not a substitute for professional medical advice · model trained on NHANES 2011–2012
        </div>
      </footer>
    </>
  );
}
