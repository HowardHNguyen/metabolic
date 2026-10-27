"""End-to-end check on iPhone-style WebKit: emailed confirmation link -> "Email confirmed" -> Sign in -> sign in.

Regression check (inherited from cardio-app 4.4.3). On WebKit the address-bar change from go("assess") could be handled before
React had applied the new user, and the "assess needs a user" guard then sent a freshly signed-in person to Create account.
Chromium never showed it, so the unit tests and desktop checks all passed.

Not part of CI (needs a database and a ~60 MB WebKit download). Run against a local server started with
EMAIL_PROVIDER=console and a throwaway database:

    pip install playwright asyncpg certifi && playwright install webkit
    BASE=http://127.0.0.1:8000 DB=postgresql://... python frontend/tests/e2e_webkit_signin.py

Each variant prints the page after opening the link, after tapping Sign in, and after signing in; the last line of each
must be the assessment page ("Let's check your metabolic health"). It creates and deletes throwaway accounts named
wk-probe-*@example.com. Never point DB at production data you care about.
"""
import asyncio, hashlib, json, secrets, ssl, subprocess, sys, urllib.request, certifi, asyncpg
from playwright.async_api import async_playwright
import os
BASE = os.environ.get("BASE", "https://metabolic.vitalckm.com")
DB = os.environ.get("DB") or sys.exit("Set DB to a throwaway Postgres URL (never production).")
ctx_ssl = ssl.create_default_context(cafile=certifi.where())

async def make_account(email, pw):
    req = urllib.request.Request(BASE + "/auth/signup", method="POST", data=json.dumps({"email": email, "password": pw}).encode(), headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, context=ctx_ssl)
    c = await asyncpg.connect(DB, timeout=20)
    raw = secrets.token_urlsafe(32)
    uid = await c.fetchval("SELECT id FROM users WHERE email=$1", email)
    await c.execute("INSERT INTO email_tokens (user_id, purpose, token_hash, expires_at) VALUES ($1,'verify',$2, NOW() + interval '1 hour')", uid, hashlib.sha256(raw.encode()).hexdigest())
    await c.close()
    return raw

async def drop(email):
    c = await asyncpg.connect(DB, timeout=20); await c.execute("DELETE FROM users WHERE email=$1", email); await c.close()

async def state(page, label):
    h1 = await page.evaluate("document.querySelector('h1')?.textContent")
    note = await page.evaluate("document.querySelector('.auth-notice,.auth-error')?.textContent")
    print(f"  {label:28s} url={page.url.split('?')[0]}  h1={h1!r}  note={note!r}")

async def run(variant):
    email, pw = f"wk-probe-{variant}@example.com", "wk-probe-pass-77"
    raw = await make_account(email, pw)
    try:
        async with async_playwright() as p:
            iphone = p.devices["iPhone 13"]
            b = await p.webkit.launch()
            ctx = await b.new_context(**iphone)
            page = await ctx.new_page()
            if variant == "stale":
                await page.goto(BASE + "/signin")
                await page.evaluate("localStorage.setItem('vitalckm_metabolic_session_v1', JSON.stringify({token:'eyJhbGciOiJIUzI1NiJ9.x.y', email:'gone@example.com', user_id:'00000000-0000-0000-0000-000000000000', name:null, savedAt: Date.now()}))")
            print(f"[{variant}] opening the emailed link")
            await page.goto(f"{BASE}/verify?token={raw}")
            await page.wait_for_timeout(2500)
            await state(page, "after opening link")
            await page.get_by_role("button", name="Sign in").click()
            await page.wait_for_timeout(1200)
            await state(page, "after tapping Sign in")
            await page.fill('input[type=email]', email)
            await page.fill('input[type=password]', pw)
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(5000)
            await state(page, "after signing in")
            await b.close()
    finally:
        await drop(email)

async def main():
    for v in ("clean", "stale"):
        await run(v)
asyncio.run(main())
