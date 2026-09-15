"""Email delivery for notifications — REAL SMTP only, never faked (spec 72).

Loaded lazily by services.notify(). If SMTP_HOST is unset the caller must not
attempt to send (it records delivery as in-app only). Titles come from the same
i18n key namespace as the API; we ship en+hi strings so a farmer gets an email
in their language. Delivery runs on a daemon thread so HTTP requests never
block on SMTP (spec 50 spirit); failures are logged, never raised to callers.
"""
from __future__ import annotations

import logging
import smtplib
import threading
from email.message import EmailMessage
from html import escape

from app.config import get_settings
from app.i18n_strings import translate

log = logging.getLogger("agriflow.email")

_MAX_PARAMS = 20


def _render_subject(title_key: str, params: dict, language: str) -> str:
    text = translate(title_key, language)
    safe = {k: escape(str(v))[:60] for k, v in list(params.items())[:_MAX_PARAMS]}
    try:
        return "AgriFlow: " + text.format(**safe)
    except (KeyError, IndexError, ValueError):
        return "AgriFlow: " + text


def _build(msg_to: str, subject: str, body: str) -> EmailMessage:
    m = EmailMessage()
    m["From"] = get_settings().smtp_from or get_settings().smtp_user
    m["To"] = msg_to
    m["Subject"] = subject
    m.set_content(body)
    return m


def _send(msg: EmailMessage) -> None:
    s = get_settings()
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
        server.ehlo()
        if s.smtp_port == 587 or "STARTTLS" in server.esmtp_features:
            server.starttls()
            server.ehlo()
        if s.smtp_user:
            server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)


def send_now(to: str, title_key: str, params: dict, language: str = "en") -> bool:
    """Blocking send; returns True on success. Raises nothing."""
    s = get_settings()
    if not s.smtp_host or not s.smtp_from and not s.smtp_user:
        return False
    subject = _render_subject(title_key, params, language)
    body = (subject + "\n\n"
            + translate("email.body_note", language) + "\n")
    try:
        _send(_build(to, subject, body))
        return True
    except Exception as exc:  # noqa: BLE001 — delivery must never crash the app
        log.error("email send failed to %s: %s", to, exc)
        return False


def send_async(to: str, title_key: str, params: dict, language: str = "en") -> None:
    threading.Thread(target=send_now, args=(to, title_key, params, language),
                     daemon=True, name="agriflow-email").start()
