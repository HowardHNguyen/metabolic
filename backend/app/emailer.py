"""Outbound email.

Provider is chosen by EMAIL_PROVIDER:
  ""        off (default): no email features; the app behaves as before email existed
  "console" development and tests: messages go to OUTBOX and the log (links included - never use in production)
  "acs"     Azure Communication Services Email (needs ACS_CONNECTION_STRING and EMAIL_FROM)

Sending never raises into a request: callers run it as a background task and failures are logged.
"""
from __future__ import annotations

import html
import logging
from collections import deque
from dataclasses import dataclass

log = logging.getLogger("metabolic.email")


@dataclass(frozen=True)
class Message:
    to: str
    subject: str
    text: str
    html: str


OUTBOX: deque[Message] = deque(maxlen=200)  # console provider only (tests read this)


def console_send(msg: Message) -> None:
    OUTBOX.append(msg)
    print(f"[email:console] to={msg.to} subject={msg.subject}\n{msg.text}\n", flush=True)  # dev only: shows the links


def acs_send(msg: Message, connection_string: str, sender: str) -> None:
    from azure.communication.email import EmailClient  # imported lazily: only needed when ACS is configured

    client = EmailClient.from_connection_string(connection_string)
    # begin_send returns once ACS has accepted the message for delivery; we do not wait for the final status
    client.begin_send({
        "senderAddress": sender,
        "recipients": {"to": [{"address": msg.to}]},
        "content": {"subject": msg.subject, "plainText": msg.text, "html": msg.html},
    })


# ---------------------------------------------------------------------------- templates
def _wrap(body_html: str) -> str:
    return ("<div style=\"font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:#1b1f2a;max-width:520px\">"
            f"{body_html}<p style=\"color:#6b7280;font-size:12px;margin-top:28px\">vitalCKM Metabolic Screen is an educational tool, "
            "not medical advice. You are receiving this because this address was used on metabolic.vitalckm.com.</p></div>")


def _button(url: str, label: str) -> str:
    return (f"<p><a href=\"{html.escape(url)}\" style=\"background:#1f4fd8;color:#fff;padding:10px 18px;border-radius:6px;"
            f"text-decoration:none;display:inline-block\">{html.escape(label)}</a></p>"
            f"<p style=\"font-size:13px;color:#4b5563\">If the button does not work, copy this link into your browser:<br>{html.escape(url)}</p>")


def verify_message(to: str, url: str) -> Message:
    return Message(
        to, "Confirm your email for vitalCKM Metabolic Screen",
        f"Please confirm your email address to finish creating your account:\n\n{url}\n\n"
        "The link works once and expires in 24 hours. If you did not sign up, ignore this email: no account will be activated.",
        _wrap("<p>Please confirm your email address to finish creating your account.</p>" + _button(url, "Confirm my email")
              + "<p>The link works once and expires in 24 hours. If you did not sign up, ignore this email: no account will be activated.</p>"))


def already_registered_message(to: str, signin_url: str, forgot_url: str) -> Message:
    return Message(
        to, "You already have a vitalCKM Metabolic Screen account",
        f"Someone tried to create an account with this email address, but you already have one.\n\nSign in: {signin_url}\n"
        f"Forgot your password? {forgot_url}\n\nIf this was not you, no action is needed: nothing about your account changed.",
        _wrap("<p>Someone tried to create an account with this email address, but you already have one.</p>"
              + _button(signin_url, "Sign in")
              + f"<p>Forgot your password? <a href=\"{html.escape(forgot_url)}\">Reset it</a>.</p>"
              + "<p>If this was not you, no action is needed: nothing about your account changed.</p>"))


def reset_message(to: str, url: str) -> Message:
    return Message(
        to, "Reset your vitalCKM Metabolic Screen password",
        f"We received a request to reset your password. Choose a new one here:\n\n{url}\n\n"
        "The link works once and expires in 1 hour. If you did not ask for this, ignore this email: your password has not changed.",
        _wrap("<p>We received a request to reset your password.</p>" + _button(url, "Choose a new password")
              + "<p>The link works once and expires in 1 hour. If you did not ask for this, ignore this email: your password has not changed.</p>"))


def password_changed_message(to: str, forgot_url: str, by_owner: bool = False) -> Message:
    # by_owner: changed from inside a signed-in session (that session stays signed in, all others end)
    what = ("Your password was just changed and your other sessions were signed out."
            if by_owner else "Your password was just changed and you were signed out everywhere.")
    return Message(
        to, "Your vitalCKM Metabolic Screen password was changed",
        f"{what}\n\nIf this was not you, reset it now: {forgot_url}",
        _wrap(f"<p>{what}</p>"
              + f"<p>If this was not you, <a href=\"{html.escape(forgot_url)}\">reset it now</a>.</p>"))