import React, { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { signup, signin, resendVerification } from "../api.js";

export default function AuthPage({ mode, onSuccess, onSwitchMode, flash }) {
  const isSignUp = mode === "signup";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [showName, setShowName] = useState(false);
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);
  const [needsConfirm, setNeedsConfirm] = useState(false);
  const [emailOn, setEmailOn] = useState(false);

  // Password reset only exists once email is configured on the server; until then do not offer it.
  useEffect(() => {
    fetch("/health").then((r) => r.json()).then((h) => setEmailOn(!!h.email && h.email !== "off")).catch(() => {});
  }, []);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setNeedsConfirm(false);
    setSubmitting(true);
    try {
      if (isSignUp) {
        // Same reply whether or not the email already had an account, and no session: sign in next.
        const result = await signup(email, password, name);
        setNotice(result.message);
        onSwitchMode("signin");
      } else {
        onSuccess(await signin(email, password));
      }
    } catch (err) {
      setError(err.message);
      setNeedsConfirm(err.code === "email_not_verified");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleResend() {
    setError(null);
    try {
      setNotice((await resendVerification(email)).message);
      setNeedsConfirm(false);
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="auth-shell">
      <div className="auth-card">
        <span className="auth-step-chip">{isSignUp ? "CREATE ACCOUNT" : "SIGN IN"}</span>
        <h1>{isSignUp ? "Create your account" : "Welcome back"}</h1>
        <p className="auth-sub">
          {isSignUp ? "Takes about 30 seconds. We need an account to save and track your assessments." : "Sign in to see your saved assessments."}
        </p>

        <form onSubmit={handleSubmit}>
          <div className="auth-field-label"><span>Email</span></div>
          <div className="auth-input-wrap">
            <input className="auth-input" type="email" required autoComplete="email" autoFocus
              value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
          </div>

          <div className="auth-field-label"><span>Password</span></div>
          <div className="auth-input-wrap">
            <input className="auth-input" type={showPwd ? "text" : "password"} required minLength={isSignUp ? 8 : undefined}
              autoComplete={isSignUp ? "new-password" : "current-password"}
              value={password} onChange={(e) => setPassword(e.target.value)}
              placeholder={isSignUp ? "At least 8 characters" : "Your password"}
              style={{ paddingRight: 40 }} />
            <button type="button" className="auth-pwd-toggle" onClick={() => setShowPwd(!showPwd)}>
              {showPwd ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          {isSignUp && (
            <div style={{ marginBottom: 16 }}>
              {!showName ? (
                <button type="button" onClick={() => setShowName(true)} className="auth-switch" style={{ border: "none", padding: 0, marginTop: 0, textAlign: "left" }}>
                  <span style={{ color: "var(--brand-700)", fontWeight: 600 }}>+ Add your name (optional)</span>
                </button>
              ) : (
                <>
                  <div className="auth-field-label"><span>Name</span><span style={{ textTransform: "none" }}>optional</span></div>
                  <div className="auth-input-wrap">
                    <input className="auth-input" type="text" autoComplete="name" value={name}
                      onChange={(e) => setName(e.target.value)} placeholder="What should we call you?" />
                  </div>
                </>
              )}
            </div>
          )}

          {(notice || flash) && !error && <div className="auth-notice" role="status">{notice || flash}</div>}
          {error && <div className="auth-error">{error}</div>}
          {needsConfirm && (
            <button type="button" className="auth-switch" onClick={handleResend}
              style={{ border: "none", padding: 0, margin: "0 0 12px", textAlign: "left" }}>
              <span style={{ color: "var(--brand-700)", fontWeight: 600 }}>Send me a new confirmation link</span>
            </button>
          )}

          <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={submitting}>
            {submitting ? "Working…" : isSignUp ? "Create account" : "Sign in"}
          </button>
        </form>

        {!isSignUp && emailOn && (
          <div className="auth-switch" style={{ marginTop: 8 }}>
            <button onClick={() => onSwitchMode("forgot")}>Forgot your password?</button>
          </div>
        )}
        <div className="auth-switch">
          <span>{isSignUp ? "Already have an account? " : "Need an account? "}</span>
          <button onClick={() => onSwitchMode(isSignUp ? "signin" : "signup")}>
            {isSignUp ? "Sign in" : "Sign up"}
          </button>
        </div>

        <div className="auth-legal">
          By continuing, you agree to our Terms and Privacy Policy. vitalCKM Metabolic Screen is an educational
          tool, not medical advice.
        </div>
      </div>
    </div>
  );
}
