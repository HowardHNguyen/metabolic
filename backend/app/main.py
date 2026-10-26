"""
vitalCKM Metabolic Screen API — v1 (metabolic syndrome Quick Screen + criteria check)
=====================================================================================
Environment variables:
  ARTIFACT_DIR     where model artifacts live (default: ./artifacts next to this package)
  MODEL_SUBDIR     artifacts subfolder to load (default: models_v1_mets)
  DATABASE_URL     postgres://user:pass@host:5432/dbname (auth + history disabled if unset)
  JWT_SECRET       random 64+ char string; REQUIRED whenever DATABASE_URL is set
  ALLOWED_ORIGINS  comma-separated CORS origins
  TRUSTED_PROXY_HOPS  reverse proxies in front of the app that append to X-Forwarded-For (default 1)
  ENABLE_DOCS      set to 1 to expose /docs and /openapi.json
  EMAIL_PROVIDER   "" (off, default) | "acs" (Azure Communication Services) | "console" (dev/tests only).
                   Off = no email verification or password reset, exactly as before email existed.
  ACS_CONNECTION_STRING, EMAIL_FROM   required when EMAIL_PROVIDER=acs (EMAIL_FROM = a verified sender address)
  APP_BASE_URL     origin used in email links (default https://metabolic.vitalckm.com)
  JWT_EXPIRY_HOURS session lifetime (default 168 = 7 days); sessions can also be revoked (logout / logout-all)
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

import asyncpg
import bcrypt
import jwt
from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import emailer
from .model import MetabolicModel

HERE = Path(__file__).resolve().parent
ARTIFACT_DIR = Path(os.getenv("ARTIFACT_DIR", HERE.parent / "artifacts"))
MODEL_SUBDIR = os.getenv("MODEL_SUBDIR", "models_v1_mets")
STATIC_DIR = Path(os.getenv("STATIC_DIR", ARTIFACT_DIR.parent / "static"))
DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", str(24 * 7)))
CLOCK_LEEWAY_SECONDS = 30  # tolerated clock difference when checking exp / iat
TRUSTED_PROXY_HOPS = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))
EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "").strip().lower()
ACS_CONNECTION_STRING = os.getenv("ACS_CONNECTION_STRING", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "").strip()
APP_BASE_URL = os.getenv("APP_BASE_URL", "https://metabolic.vitalckm.com").rstrip("/")
VERIFY_TTL = timedelta(hours=24)
RESET_TTL = timedelta(hours=1)
log = logging.getLogger("metabolic.api")
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:5173,https://metabolic.vitalckm.com",
    ).split(",") if o.strip()
]

STATE: dict[str, Any] = {}
EMAIL_MODE = ""  # resolved at startup: "", "acs" or "console"


def _resolve_email_mode() -> str:
    """Misconfiguration turns email OFF (and says so loudly) instead of stopping the app, so a bad setting
    can never take the site down."""
    if EMAIL_PROVIDER == "console":
        return "console"
    if EMAIL_PROVIDER == "acs":
        if ACS_CONNECTION_STRING and EMAIL_FROM:
            return "acs"
        log.error("EMAIL_PROVIDER=acs but ACS_CONNECTION_STRING or EMAIL_FROM is missing: email features are OFF")
        return ""
    if EMAIL_PROVIDER:
        log.error("Unknown EMAIL_PROVIDER %r: email features are OFF", EMAIL_PROVIDER)
    return ""


@asynccontextmanager
async def lifespan(app: FastAPI):
    global JWT_SECRET, EMAIL_MODE
    EMAIL_MODE = _resolve_email_mode()
    path = ARTIFACT_DIR / MODEL_SUBDIR / "model.json"
    if not path.exists():
        raise RuntimeError(f"Missing model artifact: {path}")
    STATE["model"] = MetabolicModel(path)
    if DATABASE_URL:
        if not JWT_SECRET:
            raise RuntimeError("JWT_SECRET must be set when DATABASE_URL is configured")
        STATE["db"] = await asyncpg.create_pool(DATABASE_URL, min_size=1, max_size=10, init=_init_connection)
        await _ensure_schema(STATE["db"])
        print("[startup] Database pool ready")
    else:
        JWT_SECRET = JWT_SECRET or secrets.token_urlsafe(64)  # dev only: sessions die on restart
        STATE["db"] = None
        print("[startup] WARNING: DATABASE_URL not set, auth and persistence disabled")
    print(f"[startup] Model {STATE['model'].version} loaded; email: {EMAIL_MODE or 'off'}")
    yield
    if STATE.get("db"):
        await STATE["db"].close()
    STATE.clear()


app = FastAPI(
    title="vitalCKM Metabolic Screen API", version="1.0.0", lifespan=lifespan,
    docs_url="/docs" if os.getenv("ENABLE_DOCS") == "1" else None,
    redoc_url=None,
    openapi_url="/openapi.json" if os.getenv("ENABLE_DOCS") == "1" else None,
)

# --------------------------------------------------------------------------- rate limiting
# In-memory sliding window per (client ip, path). One worker => one process-wide store.
RATE_LIMITS = {  # path -> (max requests, window seconds)
    "/auth/signup": (5, 3600),
    "/auth/signin": (10, 3600),
    "/predict": (240, 60),
    "/scenarios": (60, 60),
    "/explain": (60, 60),
    "/criteria": (120, 60),
    "/auth/verify-email": (20, 3600),
    "/auth/resend-verification": (5, 3600),
    "/auth/forgot-password": (5, 3600),
    "/auth/reset-password": (10, 3600),
    "/auth/change-password": (10, 3600),
}
_buckets: dict[tuple[str, str], deque] = defaultdict(deque)
_last_sweep = float("-inf")  # not 0.0: time.monotonic() can be small right after a machine boots


def client_ip(request: Request) -> str:
    """Client address as seen by the outermost trusted proxy.

    Only the entry appended by our own proxy is trusted (X-Forwarded-For can be forged by clients,
    so we count from the right). Falls back to the socket peer.
    """
    parts = [p.strip() for p in request.headers.get("x-forwarded-for", "").split(",") if p.strip()]
    if TRUSTED_PROXY_HOPS > 0 and len(parts) >= TRUSTED_PROXY_HOPS:
        ip = parts[-TRUSTED_PROXY_HOPS]
        if ip.count(":") == 1:  # ipv4:port
            ip = ip.split(":")[0]
        return ip
    return request.client.host if request.client else "unknown"


def _allow(key: tuple, max_req: int, window: float) -> bool:
    """Sliding-window counter. Returns False (and does not count) when the limit is already reached."""
    global _last_sweep
    now = time.monotonic()
    if now - _last_sweep > 300:  # drop idle keys so the dict cannot grow without bound
        _last_sweep = now
        for k in [k for k, q in _buckets.items() if not q or now - q[-1] > 3600]:
            del _buckets[k]
    q = _buckets[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= max_req:
        return False
    q.append(now)
    return True


def _rate_limited(ip: str, path: str) -> bool:
    limit = RATE_LIMITS.get(path)
    return bool(limit) and not _allow((ip, path), limit[0], limit[1])


def _mail_budget_ok(kind: str, email: str) -> bool:
    """At most 3 emails of each kind per address per hour, so the forms cannot be used to mail-bomb someone."""
    return _allow((hashlib.sha256(email.lower().encode()).hexdigest(), kind), 3, 3600)


RATE_MESSAGES = {
    "/auth/signup": "Too many sign-up attempts from your network. Please try again in an hour.",
    "/auth/signin": "Too many sign-in attempts. Please wait a while and try again.",
}


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    if request.method != "OPTIONS" and _rate_limited(client_ip(request), request.url.path):
        return JSONResponse(
            {"detail": RATE_MESSAGES.get(request.url.path, "Too many requests. Please slow down.")},
            status_code=429, headers={"Retry-After": "60"})
    return await call_next(request)


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
       "font-src 'self' https://fonts.gstatic.com; img-src 'self' data: blob:; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    resp = await call_next(request)  # outermost: also stamps 429s and error responses
    resp.headers.update({
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
        "Content-Security-Policy": CSP,
    })
    if request.url.path.startswith(API_PREFIXES):
        resp.headers["Cache-Control"] = "no-store"  # per-user answers: never reused by a browser or proxy cache
    return resp


app.add_middleware(
    CORSMiddleware, allow_origins=ALLOWED_ORIGINS, allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"], allow_headers=["Authorization", "Content-Type"],
)


# --------------------------------------------------------------------------- database
async def _init_connection(conn: asyncpg.Connection):
    # return JSONB as Python objects (asyncpg's default is a raw string)
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def _ensure_schema(pool: asyncpg.Pool):
    async with pool.acquire() as conn:
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS citext;")
        except Exception:
            pass
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email           CITEXT UNIQUE NOT NULL,
            password_hash   TEXT NOT NULL,
            full_name       TEXT,
            is_active       BOOLEAN NOT NULL DEFAULT true,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_login_at   TIMESTAMPTZ
        );""")
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true;")
        # bumped by "sign out everywhere": every token carries the version it was issued under
        await conn.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0;")
        # Email verification. Accounts that exist when this column is first added are grandfathered as verified
        # (one time only: later startups must not verify new, unconfirmed accounts).
        has_col = await conn.fetchval(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'email_verified_at'")
        if not has_col:
            async with conn.transaction():
                await conn.execute("ALTER TABLE users ADD COLUMN email_verified_at TIMESTAMPTZ;")
                await conn.execute("UPDATE users SET email_verified_at = created_at;")
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS assessments (
            id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id            UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            inputs             JSONB NOT NULL,
            risk_probability   NUMERIC(6,4) NOT NULL,
            risk_percent       NUMERIC(5,2) NOT NULL,
            risk_category      TEXT NOT NULL,
            component_probs    JSONB NOT NULL,
            threshold_used     NUMERIC(4,3) NOT NULL,
            model_version      TEXT NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_assess_user_date ON assessments(user_id, created_at DESC);")
        # individually revoked tokens (logout); rows are purged once the token would have expired anyway
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS revoked_tokens (
            jti         UUID PRIMARY KEY,
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            expires_at  TIMESTAMPTZ NOT NULL,
            revoked_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_revoked_expires ON revoked_tokens(expires_at);")
        # one-time links for email verification and password reset; only a SHA-256 of each token is stored
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS email_tokens (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            purpose     TEXT NOT NULL CHECK (purpose IN ('verify', 'reset')),
            token_hash  TEXT NOT NULL UNIQUE,
            expires_at  TIMESTAMPTZ NOT NULL,
            used_at     TIMESTAMPTZ,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );""")
        await conn.execute("CREATE INDEX IF NOT EXISTS idx_email_tokens_user ON email_tokens(user_id, purpose, created_at DESC);")


# --------------------------------------------------------------------------- schemas
OUT_OF_SCOPE = ("This screen is for non-pregnant adults. Waist size and blood values change during pregnancy, so the "
                "metabolic syndrome criteria do not apply. Your care team can check your metabolic health.")
RACES = ("White", "Black", "Asian", "Hispanic", "MexAmerican", "Other", "Unknown")


class AssessmentInput(BaseModel):
    """Validated against the range of the training data. The Quick Screen needs SEX, AGE, BMI and WAIST; the labs,
    blood pressure and medicines are optional and only feed the rule-based criteria check. Unknown keys are ignored."""
    model_config = ConfigDict(extra="ignore")
    SEX: float = Field(..., description="1 = male, 2 = female")
    AGE: float = Field(..., ge=20, le=80)
    RACE: str = Field("Unknown", description="NHANES race/ethnicity group, or Unknown (not given)")
    BMI: float = Field(..., ge=13, le=70)
    WAIST: float = Field(..., ge=55, le=180, description="Waist circumference, cm")
    SYSBP: Optional[float] = Field(None, ge=70, le=260)
    DIABP: Optional[float] = Field(None, ge=30, le=150)
    GLUCOSE: Optional[float] = Field(None, ge=40, le=500, description="Fasting glucose, mg/dL")
    HDL: Optional[float] = Field(None, ge=10, le=200)
    TG: Optional[float] = Field(None, ge=20, le=2000)
    BPMEDS: float = 0
    DIABETES: float = 0
    TG_MEDS: float = 0
    HDL_MEDS: float = 0
    PREGNANT: bool = Field(False, description="True if currently pregnant (out of scope)")
    HEIGHT_FT: Optional[float] = Field(None, ge=0, le=9)
    HEIGHT_IN: Optional[float] = Field(None, ge=0, le=12)
    WEIGHT_LB: Optional[float] = Field(None, ge=0, le=1000)

    @field_validator("SEX")
    @classmethod
    def _sex(cls, v):
        if v not in (1, 2):
            raise ValueError("SEX must be 1 (male) or 2 (female)")
        return v

    @field_validator("RACE")
    @classmethod
    def _race(cls, v):
        if v not in RACES:
            raise ValueError(f"RACE must be one of {', '.join(RACES)}")
        return v

    @field_validator("BPMEDS", "DIABETES", "TG_MEDS", "HDL_MEDS")
    @classmethod
    def _binary(cls, v):
        if v not in (0, 1):
            raise ValueError("must be 0 or 1")
        return v

    @model_validator(mode="after")
    def _bp(self):
        if (self.SYSBP is None) != (self.DIABP is None):
            raise ValueError("enter both blood-pressure numbers, or neither")
        if self.SYSBP is not None and self.DIABP >= self.SYSBP:
            raise ValueError("DIABP must be lower than SYSBP")
        return self

    def model_inputs(self) -> dict:
        if self.PREGNANT:
            raise HTTPException(422, {"code": "out_of_scope", "message": OUT_OF_SCOPE})
        return {k: getattr(self, k) for k in ("SEX", "AGE", "RACE", "BMI", "WAIST", "SYSBP", "DIABP", "GLUCOSE", "HDL",
                                              "TG", "BPMEDS", "DIABETES", "TG_MEDS", "HDL_MEDS")}


class PredictionResponse(BaseModel):
    risk_probability: float
    risk_percent: float
    risk_label: int
    category: str
    component_probs: dict[str, float]
    threshold_used: float
    model_version: str
    criteria: dict
    percentiles: dict
    assessment_id: Optional[str] = None


def _check_password_bytes(v: str) -> str:
    if len(v.encode()) > 72:  # bcrypt only uses the first 72 bytes (newer builds raise)
        raise ValueError("password must be at most 72 bytes")
    return v


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    name: Optional[str] = Field(None, max_length=120)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v):
        return _check_password_bytes(v)


class EmailRequest(BaseModel):
    email: EmailStr


class VerifyEmailRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)


class ResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=10, max_length=200)
    password: str = Field(..., min_length=8)

    @field_validator("password")
    @classmethod
    def _bcrypt_limit(cls, v):
        return _check_password_bytes(v)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(..., min_length=1, max_length=128)
    new_password: str = Field(..., min_length=8)

    @field_validator("new_password")
    @classmethod
    def _bcrypt_limit(cls, v):
        return _check_password_bytes(v)


class SigninRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., max_length=128)


class MessageResponse(BaseModel):
    message: str


SignupResponse = MessageResponse


class AuthResponse(BaseModel):
    token: str
    email: str
    name: Optional[str]
    user_id: str


# --------------------------------------------------------------------------- auth
def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode()[:72], hashed.encode())
    except ValueError:
        return False


# Verified against when the email is unknown, so a failed sign-in takes the same time either way.
_DUMMY_HASH = bcrypt.hashpw(b"timing-equaliser", bcrypt.gensalt()).decode()


def _make_token(user_id: str, email: str, token_version: int) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode({"sub": user_id, "email": email, "jti": str(uuid.uuid4()), "tv": token_version,
                       "iat": now, "exp": now + timedelta(hours=JWT_EXPIRY_HOURS)},
                      JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_token(token: str) -> Optional[dict]:
    """Valid signature + expiry and all required claims. Tokens without a jti/tv (issued before
    revocation existed) are rejected so that every live token can be revoked."""
    try:
        p = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM], leeway=CLOCK_LEEWAY_SECONDS,
                       options={"require": ["exp", "sub", "jti", "tv"]})
        uuid.UUID(str(p["sub"])); uuid.UUID(str(p["jti"]))
        if not isinstance(p["tv"], int):
            return None
        return p
    except Exception as e:
        log.info("token refused: %s", type(e).__name__)  # e.g. ExpiredSignatureError, ImmatureSignatureError, DecodeError
        return None


async def get_current_user_optional(authorization: Optional[str] = Header(None)):
    if not authorization or not authorization.startswith("Bearer "):
        return None
    payload = _decode_token(authorization.split(" ", 1)[1])
    if payload is None or STATE.get("db") is None:
        return None
    # one round trip, re-checked on every request: suspension, "sign out everywhere", per-token revocation
    async with STATE["db"].acquire() as conn:
        row = await conn.fetchrow("""
            SELECT u.is_active, u.token_version,
                   EXISTS (SELECT 1 FROM revoked_tokens r WHERE r.jti = $2::uuid) AS revoked
            FROM users u WHERE u.id = $1::uuid""", payload["sub"], payload["jti"])
    if not row or not row["is_active"] or row["revoked"] or row["token_version"] != payload["tv"]:
        reason = ("unknown user" if not row else "suspended" if not row["is_active"] else
                  "revoked" if row["revoked"] else "signed out elsewhere")
        log.info("token refused: %s", reason)
        return None
    return {"id": payload["sub"], "email": payload["email"], "jti": payload["jti"], "exp": payload["exp"]}


async def get_current_user(user: Optional[dict] = Depends(get_current_user_optional)):
    if user is None:
        raise HTTPException(401, "Authentication required")
    return user


# ---- email: tokens and delivery ------------------------------------------------------------------
def _link(route: str, token: str = "") -> str:
    # A plain path + query (https://host/verify?token=...), not a "#/" fragment: some mail apps and their in-app
    # browsers drop everything after "#", which lands the user on the start page with the token lost. The page strips
    # the token from the address bar as soon as it has read it, and Referrer-Policy keeps it out of Referer headers.
    return f"{APP_BASE_URL}/{route}" + (f"?token={token}" if token else "")


def _deliver(msg: emailer.Message) -> None:
    """Runs as a background task: a delivery problem is logged, never shown to (or used to probe) the caller."""
    try:
        if EMAIL_MODE == "console":
            emailer.console_send(msg)
        elif EMAIL_MODE == "acs":
            emailer.acs_send(msg, ACS_CONNECTION_STRING, EMAIL_FROM)
    except Exception:
        log.exception("email delivery failed (recipient domain: %s)", msg.to.rsplit("@", 1)[-1])


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


async def _issue_token(conn, user_id, purpose: str, ttl: timedelta) -> str:
    """New single-use link for the user; any earlier unused link of that purpose stops working."""
    raw = secrets.token_urlsafe(32)
    await conn.execute("UPDATE email_tokens SET used_at = NOW() WHERE user_id = $1::uuid AND purpose = $2 AND used_at IS NULL",
                       str(user_id), purpose)
    await conn.execute(
        "INSERT INTO email_tokens (user_id, purpose, token_hash, expires_at) VALUES ($1::uuid, $2, $3, NOW() + $4::interval)",
        str(user_id), purpose, _hash_token(raw), ttl)
    return raw


async def _consume_token(conn, raw: str, purpose: str):
    """Atomically marks a valid, unused, unexpired token as used and returns its user id (else None)."""
    row = await conn.fetchrow(
        "UPDATE email_tokens SET used_at = NOW() WHERE token_hash = $1 AND purpose = $2 AND used_at IS NULL "
        "AND expires_at > NOW() RETURNING user_id", _hash_token(raw), purpose)
    return row["user_id"] if row else None


_last_cleanup = float("-inf")  # same reason: the first run must never be skipped


async def _cleanup() -> None:
    """Background housekeeping, at most hourly: abandoned unconfirmed sign-ups and old tokens."""
    global _last_cleanup
    if time.monotonic() - _last_cleanup < 3600 or STATE.get("db") is None:
        return
    _last_cleanup = time.monotonic()
    try:
        async with STATE["db"].acquire() as conn:
            await conn.execute("DELETE FROM users WHERE email_verified_at IS NULL AND created_at < NOW() - INTERVAL '7 days'")
            await conn.execute("DELETE FROM email_tokens WHERE expires_at < NOW() - INTERVAL '1 day'")
    except Exception:
        log.exception("cleanup failed")


def _require_email() -> None:
    if not EMAIL_MODE:
        raise HTTPException(503, "Email is not available yet, so this feature is turned off.")
    _need_db()


def _need_db() -> None:
    if STATE.get("db") is None:
        raise HTTPException(503, "Database not configured")


SIGNUP_MESSAGE_OFF = ("Thanks. If this email was not already registered, your account has been created. "
                      "Please sign in to continue.")
SIGNUP_MESSAGE_ON = "Thanks. Check your email for a link to finish setting up your account."
LINK_INVALID = "This link is invalid or has expired."


@app.post("/auth/signup", response_model=SignupResponse)
async def signup(req: SignupRequest, background: BackgroundTasks):
    """Same reply whether or not the email already has an account, and no session is issued.

    With email on: a new address gets a confirmation link and cannot sign in until it is clicked. An address with
    an UNCONFIRMED account is claimed by the latest signup (so nobody can squat an address they do not control: only
    the mailbox owner can click the link). An address with a CONFIRMED account is never changed; its owner gets an
    "you already have an account" email instead. The bcrypt cost is paid in every case, so timing does not leak."""
    if STATE.get("db") is None:
        raise HTTPException(503, "Database not configured")
    pw_hash = await run_in_threadpool(_hash_password, req.password)
    send: Optional[emailer.Message] = None
    async with STATE["db"].acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow("SELECT id, email_verified_at FROM users WHERE email = $1 FOR UPDATE", req.email)
            if row is None:
                new = await conn.fetchrow(
                    "INSERT INTO users (email, password_hash, full_name, email_verified_at) "
                    "VALUES ($1, $2, $3, CASE WHEN $4 THEN NULL ELSE NOW() END) ON CONFLICT (email) DO NOTHING RETURNING id",
                    req.email, pw_hash, req.name, bool(EMAIL_MODE))
                if new and EMAIL_MODE and _mail_budget_ok("verify", req.email):
                    send = emailer.verify_message(req.email, _link("verify", await _issue_token(conn, new["id"], "verify", VERIFY_TTL)))
            elif EMAIL_MODE and row["email_verified_at"] is None:
                await conn.execute("UPDATE users SET password_hash = $2, full_name = $3 WHERE id = $1", row["id"], pw_hash, req.name)
                if _mail_budget_ok("verify", req.email):
                    send = emailer.verify_message(req.email, _link("verify", await _issue_token(conn, row["id"], "verify", VERIFY_TTL)))
            elif EMAIL_MODE and _mail_budget_ok("exists", req.email):
                send = emailer.already_registered_message(req.email, _link("signin"), _link("forgot"))
    if send:
        background.add_task(_deliver, send)
    background.add_task(_cleanup)
    return SignupResponse(message=SIGNUP_MESSAGE_ON if EMAIL_MODE else SIGNUP_MESSAGE_OFF)


@app.post("/auth/verify-email", response_model=MessageResponse)
async def verify_email(req: VerifyEmailRequest):
    _need_db()
    async with STATE["db"].acquire() as conn:
        async with conn.transaction():
            user_id = await _consume_token(conn, req.token, "verify")
            if user_id is None:
                raise HTTPException(400, LINK_INVALID)
            await conn.execute("UPDATE users SET email_verified_at = COALESCE(email_verified_at, NOW()) WHERE id = $1", user_id)
    return MessageResponse(message="Email confirmed. You can now sign in.")


@app.post("/auth/resend-verification", response_model=MessageResponse)
async def resend_verification(req: EmailRequest, background: BackgroundTasks):
    _require_email()
    async with STATE["db"].acquire() as conn:
        row = await conn.fetchrow("SELECT id, is_active FROM users WHERE email = $1 AND email_verified_at IS NULL", req.email)
        if row and row["is_active"] and _mail_budget_ok("verify", req.email):
            raw = await _issue_token(conn, row["id"], "verify", VERIFY_TTL)
            background.add_task(_deliver, emailer.verify_message(req.email, _link("verify", raw)))
    return MessageResponse(message="If that address has an account waiting for confirmation, we have sent a new link.")


@app.post("/auth/forgot-password", response_model=MessageResponse)
async def forgot_password(req: EmailRequest, background: BackgroundTasks):
    _require_email()
    async with STATE["db"].acquire() as conn:
        row = await conn.fetchrow("SELECT id, is_active FROM users WHERE email = $1", req.email)
        if row and row["is_active"] and _mail_budget_ok("reset", req.email):
            raw = await _issue_token(conn, row["id"], "reset", RESET_TTL)
            background.add_task(_deliver, emailer.reset_message(req.email, _link("reset", raw)))
    return MessageResponse(message="If that address has an account, we have emailed a link to reset the password.")


@app.post("/auth/reset-password", response_model=MessageResponse)
async def reset_password(req: ResetPasswordRequest, background: BackgroundTasks):
    """Sets a new password from a reset link. Signs the user out everywhere (token version bump), voids every other
    outstanding link, and counts as proof of mailbox control (the address becomes confirmed)."""
    _require_email()
    pw_hash = await run_in_threadpool(_hash_password, req.password)
    async with STATE["db"].acquire() as conn:
        async with conn.transaction():
            user_id = await _consume_token(conn, req.token, "reset")
            user = await conn.fetchrow(
                "UPDATE users SET password_hash = $2, token_version = token_version + 1, "
                "email_verified_at = COALESCE(email_verified_at, NOW()) WHERE id = $1 AND is_active RETURNING email",
                user_id, pw_hash) if user_id else None
            if user is None:
                raise HTTPException(400, LINK_INVALID)  # rolls the transaction back, so a bad link changes nothing
            await conn.execute("UPDATE email_tokens SET used_at = NOW() WHERE user_id = $1 AND used_at IS NULL", user_id)
    background.add_task(_deliver, emailer.password_changed_message(user["email"], _link("forgot")))
    return MessageResponse(message="Password updated. Please sign in with your new password.")


@app.post("/auth/signin", response_model=AuthResponse)
async def signin(req: SigninRequest):
    if STATE.get("db") is None:
        raise HTTPException(503, "Database not configured")
    async with STATE["db"].acquire() as conn:
        row = await conn.fetchrow(
            "SELECT id, email, password_hash, full_name, is_active, token_version, email_verified_at "
            "FROM users WHERE email = $1", req.email)
    ok = await run_in_threadpool(_verify_password, req.password, row["password_hash"] if row else _DUMMY_HASH)
    if not row or not ok:
        raise HTTPException(401, "Invalid email or password")
    if not row["is_active"]:
        raise HTTPException(403, "This account has been suspended.")
    if EMAIL_MODE and row["email_verified_at"] is None:  # only revealed to someone who knows the password
        raise HTTPException(403, {"code": "email_not_verified",
                                  "message": "Please confirm your email address first. Check your inbox for the link, or ask for a new one."})
    async with STATE["db"].acquire() as conn:
        await conn.execute("UPDATE users SET last_login_at = NOW() WHERE id = $1", row["id"])
    uid = str(row["id"])
    return AuthResponse(token=_make_token(uid, row["email"], row["token_version"]),
                        email=row["email"], name=row["full_name"], user_id=uid)


@app.post("/auth/change-password", response_model=AuthResponse)
async def change_password(req: ChangePasswordRequest, background: BackgroundTasks, user: dict = Depends(get_current_user)):
    """Signed-in password change. Needs the current password (a stolen session alone cannot take over the account).
    Signs every other session out (token version bump) and hands this one a fresh token, voids outstanding reset links,
    and tells the owner by email when email is on."""
    _need_db()
    # attempts are counted per account as well as per address, so a stolen token cannot be used to guess the
    # current password from many addresses
    if not _allow(("chpw-user", user["id"]), 10, 3600):
        raise HTTPException(429, "Too many attempts. Please try again later.", headers={"Retry-After": "3600"})
    async with STATE["db"].acquire() as conn:
        row = await conn.fetchrow(
            "SELECT email, full_name, password_hash FROM users WHERE id = $1::uuid AND is_active", user["id"])
    if row is None:
        raise HTTPException(401, "Authentication required")
    ok = await run_in_threadpool(_verify_password, req.current_password, row["password_hash"])
    if not ok:
        raise HTTPException(400, "Your current password is incorrect.")
    if req.new_password == req.current_password:
        raise HTTPException(400, "Choose a password that is different from the current one.")
    pw_hash = await run_in_threadpool(_hash_password, req.new_password)
    async with STATE["db"].acquire() as conn:
        async with conn.transaction():
            upd = await conn.fetchrow(
                "UPDATE users SET password_hash = $2, token_version = token_version + 1 "
                "WHERE id = $1::uuid AND is_active RETURNING token_version", user["id"], pw_hash)
            if upd is None:
                raise HTTPException(401, "Authentication required")
            await conn.execute(
                "UPDATE email_tokens SET used_at = NOW() WHERE user_id = $1::uuid AND purpose = 'reset' AND used_at IS NULL",
                user["id"])
    if EMAIL_MODE:
        background.add_task(_deliver, emailer.password_changed_message(row["email"], _link("forgot"), by_owner=True))
    return AuthResponse(token=_make_token(user["id"], row["email"], upd["token_version"]),
                        email=row["email"], name=row["full_name"], user_id=user["id"])


@app.post("/auth/logout", status_code=204)
async def logout(user: Optional[dict] = Depends(get_current_user_optional)):
    """Revoke the token used for this request. Always 204, so a client with an already-dead token can still sign out."""
    if user and STATE.get("db"):
        async with STATE["db"].acquire() as conn:
            await conn.execute("DELETE FROM revoked_tokens WHERE expires_at < NOW()")
            await conn.execute(
                "INSERT INTO revoked_tokens (jti, user_id, expires_at) VALUES ($1::uuid, $2::uuid, to_timestamp($3)) "
                "ON CONFLICT (jti) DO NOTHING", user["jti"], user["id"], float(user["exp"]))
    return None


@app.post("/auth/logout-all", status_code=204)
async def logout_all(user: dict = Depends(get_current_user)):
    """Sign out everywhere: invalidates every token issued so far, on every device."""
    async with STATE["db"].acquire() as conn:
        await conn.execute("UPDATE users SET token_version = token_version + 1 WHERE id = $1::uuid", user["id"])
    return None


@app.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return {"user_id": user["id"], "email": user["email"]}


# --------------------------------------------------------------------------- prediction
def _result(inp: dict) -> dict:
    m: MetabolicModel = STATE["model"]
    p = m.predict(inp)
    return {
        "risk_probability": p, "risk_percent": round(p * 100, 1),
        "risk_label": int(p >= m.high_threshold), "category": m.category(p),
        "component_probs": {"Quick Screen (logistic)": p},
        "threshold_used": m.high_threshold, "model_version": m.version,
        "criteria": m.criteria_check(inp), "percentiles": m.percentiles(inp),
    }


@app.get("/health")
def health():
    m: Optional[MetabolicModel] = STATE.get("model")
    return {"status": "ok" if m else "starting", "model_version": m.version if m else None,
            "features": len(m.features) if m else 0, "db_connected": STATE.get("db") is not None,
            "email": EMAIL_MODE or "off"}


@app.post("/predict", response_model=PredictionResponse)
async def predict(payload: AssessmentInput, save: bool = True,
                  user: Optional[dict] = Depends(get_current_user_optional)):
    """Quick Screen probability + criteria check. Saved to the user's history only if authenticated AND save=true
    (the What-If sliders pass save=false)."""
    result = _result(payload.model_inputs())
    if save and user and STATE.get("db"):
        async with STATE["db"].acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO assessments (user_id, inputs, risk_probability, risk_percent, risk_category,
                                         component_probs, threshold_used, model_version)
                VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8) RETURNING id
            """, user["id"], payload.model_dump(), result["risk_probability"], result["risk_percent"],
                result["category"], result["component_probs"], result["threshold_used"],
                result["model_version"])
            result["assessment_id"] = str(row["id"])
    return result


@app.get("/assessments")
async def list_assessments(user: dict = Depends(get_current_user)):
    async with STATE["db"].acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, inputs, risk_probability, risk_percent, risk_category, threshold_used, model_version, created_at
            FROM assessments WHERE user_id = $1::uuid ORDER BY created_at DESC LIMIT 200
        """, user["id"])
    return [{
        "id": str(r["id"]), "inputs": r["inputs"], "risk_probability": float(r["risk_probability"]),
        "risk_percent": float(r["risk_percent"]), "risk_category": r["risk_category"],
        "threshold_used": float(r["threshold_used"]), "model_version": r["model_version"],
        "created_at": r["created_at"].isoformat(),
    } for r in rows]


@app.delete("/assessments/{assessment_id}", status_code=204)
async def delete_assessment(assessment_id: str, user: dict = Depends(get_current_user)):
    """Delete one assessment owned by the current user (404 if missing or not theirs)."""
    if STATE.get("db") is None:
        raise HTTPException(503, "Database not configured")
    try:
        aid = str(uuid.UUID(assessment_id))
    except ValueError:
        raise HTTPException(404, "Assessment not found")
    async with STATE["db"].acquire() as conn:
        result = await conn.execute("DELETE FROM assessments WHERE id = $1::uuid AND user_id = $2::uuid", aid, user["id"])
    if result.split()[-1] == "0":
        raise HTTPException(404, "Assessment not found")
    return None


@app.post("/scenarios")
async def scenarios(payload: AssessmentInput):
    """Quick Screen probability after single changes to the two modifiable model inputs (waist, BMI) and both together.
    Waist and BMI move together in real life; the combined row is the realistic one."""
    base_in = payload.model_inputs()
    baseline = _result(base_in)
    out = []

    def add(name: str, desc: str, **changes):
        pred = _result({**base_in, **changes})
        out.append({"name": name, "description": desc, "risk_probability": pred["risk_probability"],
                    "risk_percent": pred["risk_percent"],
                    "delta_pp": round((pred["risk_probability"] - baseline["risk_probability"]) * 100, 2)})

    changes: dict[str, float] = {}
    if base_in["WAIST"] > 80:
        v = max(base_in["WAIST"] - 5.0, 60.0)
        add("Trim waist by 5 cm (2 in)", f"Waist: {base_in['WAIST']:.0f} -> {v:.0f} cm", WAIST=v); changes["WAIST"] = v
    if base_in["BMI"] > 25:
        v = max(base_in["BMI"] - 2.0, 18.5)
        add("Lose weight (BMI down 2)", f"BMI: {base_in['BMI']:.1f} -> {v:.1f}", BMI=v); changes["BMI"] = v
    if changes:
        add("Both together", "Smaller waist and lower BMI", **changes)
    return {"baseline": baseline, "scenarios": out}


@app.post("/criteria")
async def criteria(payload: AssessmentInput):
    """Rule-based metabolic syndrome criteria check only (no model)."""
    return STATE["model"].criteria_check(payload.model_inputs())


@app.post("/explain")
async def explain(payload: AssessmentInput, top_k: int = 8):
    """Exact additive factor contributions of the logistic model (they sum to risk - base_value)."""
    return STATE["model"].explain(payload.model_inputs(), top_k=max(1, min(top_k, 12)))


# --------------------------------------------------------------------------- frontend (SPA)
API_PREFIXES = ("/auth", "/predict", "/assessments", "/scenarios", "/explain", "/criteria", "/health")
_INDEX = STATIC_DIR / "index.html"


@app.exception_handler(StarletteHTTPException)
async def spa_or_http_error(request: Request, exc: StarletteHTTPException):
    if (exc.status_code == 404 and request.method == "GET" and _INDEX.exists()
            and not request.url.path.startswith(API_PREFIXES)):
        return FileResponse(_INDEX)  # client-side routes
    return await http_exception_handler(request, exc)


if STATIC_DIR.is_dir():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
