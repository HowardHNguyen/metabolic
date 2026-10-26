import React, { useEffect, useRef, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { parseLocation } from "../linkRoute.js";
import { forgotPassword, resetPassword, verifyEmail, resendVerification, changePassword } from "../api.js";

// Reads the email-link token once (from ?token=... or the older #/route?token=... form), then removes it from the
// address bar and history so it is not left in a bookmark, a screenshot or the back button.
function useLinkToken() {
  const [{ route, token }] = useState(() => parseLocation(window.location));
  useEffect(() => {
    if (token || window.location.pathname !== "/") window.history.replaceState(null, "", `/#/${route === "landing" ? "" : route}`);
  }, [token, route]);
  return token;
}

function Card({ chip, title, sub, children }) {
  return (
    <div className="auth-shell">
      <div className="auth-card">
        <span className="auth-step-chip">{chip}</span>
        <h1>{title}</h1>
        {sub && <p className="auth-sub">{sub}</p>}
        {children}
      </div>
    </div>
  );
}

function EmailForm({ buttonLabel, action, onDone, initialEmail = "" }) {
  const [email, setEmail] = useState(initialEmail);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  async function submit(e) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      onDone((await action(email)).message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={submit}>
      <div className="auth-field-label"><span>Email</span></div>
      <div className="auth-input-wrap">
        <input className="auth-input" type="email" required autoComplete="email" autoFocus value={email}
          onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" />
      </div>
      {error && <div className="auth-error">{error}</div>}
      <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
        {busy ? "Sending…" : buttonLabel}
      </button>
    </form>
  );
}

export function ForgotPage({ onNavigate }) {
  const [sent, setSent] = useState(null);
  return (
    <Card chip="RESET PASSWORD" title="Forgot your password?"
      sub="Enter your email and we will send you a link to choose a new one.">
      {sent ? <div className="auth-notice" role="status">{sent}</div> : <EmailForm buttonLabel="Email me a reset link" action={forgotPassword} onDone={setSent} />}
      <div className="auth-switch">
        <button onClick={() => onNavigate("signin")}>Back to sign in</button>
      </div>
    </Card>
  );
}

export function ResetPage({ onNavigate, onDone }) {
  const token = useLinkToken();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  if (!token) {
    return (
      <Card chip="RESET PASSWORD" title="This link is invalid or has expired" sub="Request a new link to choose a new password.">
        <button className="btn-primary" style={{ width: "100%", justifyContent: "center" }} onClick={() => onNavigate("forgot")}>Request a new link</button>
      </Card>
    );
  }
  async function submit(e) {
    e.preventDefault();
    if (password !== confirm) { setError("The two passwords do not match."); return; }
    setError(null);
    setBusy(true);
    try {
      onDone((await resetPassword(token, password)).message);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Card chip="RESET PASSWORD" title="Choose a new password" sub="You will be signed out everywhere, then you can sign in with the new password.">
      <form onSubmit={submit}>
        <div className="auth-field-label"><span>New password</span></div>
        <div className="auth-input-wrap">
          <input className="auth-input" type={show ? "text" : "password"} required minLength={8} autoFocus autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" style={{ paddingRight: 40 }} />
          <button type="button" className="auth-pwd-toggle" onClick={() => setShow(!show)}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button>
        </div>
        <div className="auth-field-label"><span>Confirm new password</span></div>
        <div className="auth-input-wrap">
          <input className="auth-input" type={show ? "text" : "password"} required minLength={8} autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </div>
        {error && <div className="auth-error">{error}</div>}
        <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
          {busy ? "Saving…" : "Update password"}
        </button>
      </form>
      {error && /invalid or has expired/.test(error) && (
        <div className="auth-switch"><button onClick={() => onNavigate("forgot")}>Request a new link</button></div>
      )}
    </Card>
  );
}

export function VerifyPage({ onNavigate }) {
  const token = useLinkToken();
  const [state, setState] = useState(token ? "working" : "failed");
  const [message, setMessage] = useState("");
  const [resent, setResent] = useState(null);
  const started = useRef(false);
  useEffect(() => {
    if (!token || started.current) return; // links work once: never send the request twice (React dev double-run)
    started.current = true;
    verifyEmail(token).then((r) => { setMessage(r.message); setState("done"); }).catch((e) => { setMessage(e.message); setState("failed"); });
  }, [token]);
  if (state === "working") return <Card chip="CONFIRM EMAIL" title="Confirming your email…" />;
  if (state === "done") {
    return (
      <Card chip="CONFIRM EMAIL" title="Email confirmed" sub={message}>
        <button className="btn-primary" style={{ width: "100%", justifyContent: "center" }} onClick={() => onNavigate("signin")}>Sign in</button>
      </Card>
    );
  }
  return (
    <Card chip="CONFIRM EMAIL" title="This link is invalid or has expired" sub={message || "Enter your email and we will send a new confirmation link."}>
      {resent ? <div className="auth-notice" role="status">{resent}</div> : <EmailForm buttonLabel="Send a new link" action={resendVerification} onDone={setResent} />}
      <div className="auth-switch"><button onClick={() => onNavigate("signin")}>Back to sign in</button></div>
    </Card>
  );
}

// Signed-in users only. On success the server has signed every other device out and sent this one a new token.
export function ChangePasswordPage({ token, onChanged, onSessionExpired, onBack }) {
  const [current, setCurrent] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [show, setShow] = useState(false);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  async function submit(e) {
    e.preventDefault();
    if (password !== confirm) { setError("The two new passwords do not match."); return; }
    if (password === current) { setError("Choose a password that is different from the current one."); return; }
    setError(null);
    setBusy(true);
    try {
      onChanged(await changePassword(current, password, token));
      setCurrent(""); setPassword(""); setConfirm("");
      setDone(true);
    } catch (err) {
      if (err.status === 401) onSessionExpired();
      else setError(err.message);
    } finally {
      setBusy(false);
    }
  }
  if (done) {
    return (
      <Card chip="ACCOUNT" title="Password updated" sub="Your other devices have been signed out. This one stays signed in.">
        <button className="btn-primary" style={{ width: "100%", justifyContent: "center" }} onClick={onBack}>Back to the calculator</button>
      </Card>
    );
  }
  return (
    <Card chip="ACCOUNT" title="Change your password" sub="You will stay signed in here; every other device is signed out.">
      <form onSubmit={submit}>
        <div className="auth-field-label"><span>Current password</span></div>
        <div className="auth-input-wrap">
          <input className="auth-input" type={show ? "text" : "password"} required autoFocus autoComplete="current-password"
            value={current} onChange={(e) => setCurrent(e.target.value)} style={{ paddingRight: 40 }} />
          <button type="button" className="auth-pwd-toggle" onClick={() => setShow(!show)}>{show ? <EyeOff size={16} /> : <Eye size={16} />}</button>
        </div>
        <div className="auth-field-label"><span>New password</span></div>
        <div className="auth-input-wrap">
          <input className="auth-input" type={show ? "text" : "password"} required minLength={8} autoComplete="new-password"
            value={password} onChange={(e) => setPassword(e.target.value)} placeholder="At least 8 characters" />
        </div>
        <div className="auth-field-label"><span>Confirm new password</span></div>
        <div className="auth-input-wrap">
          <input className="auth-input" type={show ? "text" : "password"} required minLength={8} autoComplete="new-password"
            value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </div>
        {error && <div className="auth-error" role="alert">{error}</div>}
        <button type="submit" className="btn-primary" style={{ width: "100%", justifyContent: "center" }} disabled={busy}>
          {busy ? "Saving…" : "Change password"}
        </button>
      </form>
      <div className="auth-switch"><button onClick={onBack}>Cancel</button></div>
    </Card>
  );
}
