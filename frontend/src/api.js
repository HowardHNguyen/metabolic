import { API_TIMEOUT_MS } from "./constants.js";
import { MODEL } from "./localModel.js";

// Same-origin by default (single-container deploy, like ckd.vitalckm.com).
// Override with VITE_API_BASE if ever split into separate services again.
export const API_BASE = import.meta.env?.VITE_API_BASE || "";

// A request the server understood and refused (validation, out-of-scope, rate limit).
// Never papered over with a local result: the user needs to see why.
export class ApiError extends Error {
  constructor(message, status, code) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

async function toApiError(res) {
  let message = "Something went wrong. Please check your entries and try again.";
  let code;
  try {
    const d = (await res.json()).detail;
    if (typeof d === "string") message = d;
    else if (d?.message) { message = d.message; code = d.code; }
    else if (Array.isArray(d) && d.length) message = d.map((e) => `${(e.loc || []).slice(-1)[0]}: ${e.msg}`).join("; ");
  } catch {
    // keep the generic message
  }
  return new ApiError(message, res.status, code);
}

async function fetchWithTimeout(url, options, timeoutMs = API_TIMEOUT_MS) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

const post = (path, payload, token) =>
  fetchWithTimeout(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(payload),
  });

// Runs /predict, /scenarios and /explain in parallel. If the server is unreachable or errors (network,
// timeout, 5xx) the identical model runs in the browser instead (source: "offline", not saved).
// 4xx responses are surfaced as ApiError.
export async function runPrediction(payload, token) {
  try {
    const [predRes, scenRes, expRes] = await Promise.all([
      post("/predict", payload, token), post("/scenarios", payload, token), post("/explain", payload, token),
    ]);
    for (const r of [predRes, scenRes, expRes]) {
      if (r.status >= 400 && r.status < 500) throw await toApiError(r);
      if (!r.ok) throw new Error("server error");
    }
    return {
      source: "api", prediction: await predRes.json(), scenarios: await scenRes.json(), explanation: await expRes.json(),
    };
  } catch (e) {
    if (e instanceof ApiError) throw e;
    return {
      source: "offline", prediction: MODEL.result(payload), scenarios: MODEL.scenarios(payload),
      explanation: MODEL.explain(payload),
    };
  }
}

// Returns the user's assessments, or null when the server says the session is no longer valid
// (expired, signed out elsewhere, account suspended) so the app can send the user back to sign in.
export async function fetchAssessments(token) {
  const res = await fetch(`${API_BASE}/assessments`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (res.status === 401) return null;
  if (!res.ok) return [];
  return res.json();
}

export async function deleteAssessment(id, token) {
  const res = await fetch(`${API_BASE}/assessments/${id}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  return res.ok;
}

// POSTs JSON to an auth endpoint. Throws ApiError carrying the server's message (and code, e.g. "email_not_verified").
async function authPost(path, body, fallback, token) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: JSON.stringify(body),
  });
  let data = {};
  try {
    data = await res.json();
  } catch {
    // non-JSON error body: fall through to the generic message
  }
  if (!res.ok) {
    const d = data.detail;
    if (typeof d === "string") throw new ApiError(d, res.status);
    if (d?.message) throw new ApiError(d.message, res.status, d.code);
    throw new ApiError(fallback, res.status);
  }
  return data;
}

// Signup answers the same way whether or not the email was already registered, and issues no session:
// the caller shows the message and sends the user to sign in (after confirming their email, when email is on).
export const signup = (email, password, name) =>
  authPost("/auth/signup", { email, password, name: name || undefined }, "Sign up failed. Please check your entries.");
export const signin = (email, password) => authPost("/auth/signin", { email, password }, "Sign in failed");
export const verifyEmail = (token) => authPost("/auth/verify-email", { token }, "This link is invalid or has expired.");
export const resendVerification = (email) => authPost("/auth/resend-verification", { email }, "Could not send the email. Please try again.");
export const forgotPassword = (email) => authPost("/auth/forgot-password", { email }, "Could not send the email. Please try again.");
export const resetPassword = (token, password) =>
  authPost("/auth/reset-password", { token, password }, "This link is invalid or has expired.");

// Signed-in password change. Resolves to {token, email, ...}: the server ends every other session and issues this one a new
// token, which the caller must store. A 401 (ApiError.status) means this session itself is no longer valid.
export const changePassword = (currentPassword, newPassword, token) =>
  authPost("/auth/change-password", { current_password: currentPassword, new_password: newPassword },
    "Could not change the password. Please try again.", token);

// Best effort: the local session is cleared by the caller whether or not the server could be reached.
async function postAuthed(path, token) {
  try {
    const res = await fetchWithTimeout(`${API_BASE}${path}`, { method: "POST", headers: { Authorization: `Bearer ${token}` } });
    return res.ok;
  } catch {
    return false;
  }
}
export const logout = (token) => postAuthed("/auth/logout", token);
export const logoutAll = (token) => postAuthed("/auth/logout-all", token);
