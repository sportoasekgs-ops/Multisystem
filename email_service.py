"""
E-Mail-Service für das Buchungssystem.
Unterstützt Provider:
  - SMTP (Standard): Jeder SMTP-Server, inkl. Office365, Schulserver etc.
  - Resend: Cloud-E-Mail über https://resend.com (API-Key erforderlich)
  - Brevo: Cloud-E-Mail über https://brevo.com (API-Key + verifizierte Absenderadresse)
Konfiguration wird aus der Datenbank geladen (Setup-Wizard / Admin-CMS).
"""

import json
import logging
import os
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


logger = logging.getLogger(__name__)


def _safe_str(value, default=""):
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _get_config_or_env(config_key, env_key=None, default=""):
    value = None
    try:
        from system_config import get_config

        value = get_config(config_key)
    except Exception:
        value = None

    value = _safe_str(value)
    if value:
        return value

    if env_key:
        return _safe_str(os.getenv(env_key, default), default)

    return _safe_str(default, default)


def _get_app_name():
    try:
        from system_config import get_config

        name = get_config("school_name", "").strip()
        return name if name else "Buchungssystem"
    except Exception:
        return "Buchungssystem"


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────


def format_date_german(date_str):
    try:
        if "-" in str(date_str):
            parts = str(date_str).split("-")
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return str(date_str)


def get_german_weekday(weekday_abbr):
    weekday_map = {
        "Mon": "Montag",
        "Tue": "Dienstag",
        "Wed": "Mittwoch",
        "Thu": "Donnerstag",
        "Fri": "Freitag",
        "Sat": "Samstag",
        "Sun": "Sonntag",
    }
    return weekday_map.get(weekday_abbr, weekday_abbr)


# ── Provider-Konfiguration ────────────────────────────────────────────────────


def get_email_provider():
    """Gibt den konfigurierten E-Mail-Provider zurück: 'smtp', 'resend' oder 'brevo'."""
    provider = _get_config_or_env("email_provider", "EMAIL_PROVIDER", "smtp").lower()
    return provider if provider in {"smtp", "resend", "brevo"} else "smtp"


def get_smtp_config():
    try:
        host = _get_config_or_env("smtp_host", "SMTP_HOST", "")
        port_raw = _get_config_or_env("smtp_port", "SMTP_PORT", "587")
        user = _get_config_or_env("smtp_user", "SMTP_USER", "")
        password = _get_config_or_env("smtp_pass", "SMTP_PASS", "")
        tls_mode = _get_config_or_env("smtp_tls", "SMTP_TLS", "starttls").lower()
        from_addr = _get_config_or_env("smtp_from", "SMTP_FROM", user) or user

        try:
            port = int(port_raw or 587)
        except (TypeError, ValueError):
            port = 587

        if tls_mode not in {"starttls", "ssl", "none"}:
            tls_mode = "starttls"

        return host, port, user, password, tls_mode, from_addr
    except Exception as e:
        logger.error(f"[EMAIL] Fehler beim Laden der SMTP-Konfiguration: {e}")
        return "", 587, "", "", "starttls", ""


def get_resend_config():
    try:
        api_key = _get_config_or_env("resend_api_key", "RESEND_API_KEY", "")
        from_addr = _get_config_or_env("resend_from", "RESEND_FROM", "")
        return api_key, from_addr
    except Exception:
        return "", ""


def get_brevo_config():
    try:
        api_key = _get_config_or_env("brevo_api_key", "BREVO_API_KEY", "")
        from_addr = _get_config_or_env("brevo_from", "BREVO_FROM", "")
        from_name = _get_config_or_env(
            "brevo_from_name", "BREVO_FROM_NAME", _get_app_name()
        )
        return api_key, from_addr, from_name
    except Exception:
        return "", "", ""


def is_email_configured():
    provider = get_email_provider()
    if provider == "resend":
        api_key, from_addr = get_resend_config()
        return bool(api_key and from_addr)
    if provider == "brevo":
        api_key, from_addr, _ = get_brevo_config()
        return bool(api_key and from_addr)
    host, _, user, password, _, _ = get_smtp_config()
    return bool(host and user and password)


# Alias für alte Aufrufer
def is_smtp_configured():
    return is_email_configured()


# ── Kern-Sendefunktionen ──────────────────────────────────────────────────────


def _send_via_resend(to_email, subject, body_html, body_text=None):
    """Sendet E-Mail über Resend HTTP-API."""
    import urllib.error
    import urllib.request

    api_key, from_addr = get_resend_config()
    if not api_key or not from_addr:
        logger.warning(
            "[EMAIL] Resend nicht konfiguriert – kein API-Key oder Absender."
        )
        return False

    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "html": body_html,
    }
    if body_text:
        payload["text"] = body_text

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.getcode()
            if status in (200, 201):
                logger.info(f"[EMAIL] Resend: Erfolgreich gesendet an {to_email}")
                return True
            logger.error(f"[EMAIL] Resend: HTTP {status}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"[EMAIL] Resend HTTP-Fehler {e.code}: {body}")
        return False
    except Exception as e:
        logger.error(f"[EMAIL] Resend Fehler: {e}")
        return False


def _send_via_brevo(to_email, subject, body_html, body_text=None):
    """Sendet E-Mail über Brevo HTTP-API."""
    import urllib.error
    import urllib.request

    api_key, from_addr, from_name = get_brevo_config()
    if not api_key or not from_addr:
        logger.warning("[EMAIL] Brevo nicht konfiguriert – kein API-Key oder Absender.")
        return False

    payload = {
        "sender": {"email": from_addr, "name": from_name or _get_app_name()},
        "to": [{"email": to_email}],
        "subject": subject,
        "htmlContent": body_html,
    }
    if body_text:
        payload["textContent"] = body_text

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=data,
        headers={
            "api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            status = resp.getcode()
            if status in (200, 201, 202):
                logger.info(f"[EMAIL] Brevo: Erfolgreich gesendet an {to_email}")
                return True
            logger.error(f"[EMAIL] Brevo: HTTP {status}")
            return False
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        logger.error(f"[EMAIL] Brevo HTTP-Fehler {e.code}: {body}")
        return False
    except Exception as e:
        logger.error(f"[EMAIL] Brevo Fehler: {e}")
        return False


def _send_via_smtp(to_email, subject, body_html, body_text=None):
    """Sendet E-Mail über SMTP."""
    host, port, user, password, tls_mode, from_addr = get_smtp_config()

    if not host or not user or not password:
        logger.warning(
            f"[EMAIL] SMTP nicht konfiguriert – E-Mail an {to_email} nicht gesendet."
        )
        return False

    try:
        import socket as _socket

        try:
            ipv4 = _socket.getaddrinfo(
                host, port, _socket.AF_INET, _socket.SOCK_STREAM
            )[0][4][0]
        except Exception:
            ipv4 = host

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = from_addr
        msg["To"] = to_email

        if body_text:
            msg.attach(MIMEText(body_text, "plain", "utf-8"))
        msg.attach(MIMEText(body_html, "html", "utf-8"))

        if tls_mode == "ssl":
            with smtplib.SMTP_SSL(ipv4, port, timeout=15) as server:
                server.login(user, password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(ipv4, port, timeout=15) as server:
                server.ehlo()
                if tls_mode == "starttls":
                    server.starttls()
                    server.ehlo()
                server.login(user, password)
                server.sendmail(from_addr, [to_email], msg.as_string())

        logger.info(f"[EMAIL] SMTP: Erfolgreich gesendet an {to_email}")
        return True

    except Exception as e:
        logger.error(f"[EMAIL] SMTP FEHLER an {to_email}: {e}")
        return False


def send_email(to_email, subject, body_html, body_text=None):
    """
    Sendet eine E-Mail über den konfigurierten Provider (SMTP oder Resend).
    Im Demo-Modus wird nichts verschickt.
    """
    try:
        from demo_mode import is_demo_mode, send_demo_email_log

        if is_demo_mode():
            return send_demo_email_log(to_email, subject)
    except Exception:
        pass

    provider = get_email_provider()
    if provider == "resend":
        return _send_via_resend(to_email, subject, body_html, body_text)
    if provider == "brevo":
        return _send_via_brevo(to_email, subject, body_html, body_text)
    return _send_via_smtp(to_email, subject, body_html, body_text)


# Aliases für Rückwärtskompatibilität
send_email_resend = send_email
send_email_smtp = send_email


def send_password_reset_email(to_email, username, reset_url):
    """Sendet eine Passwort-Reset-E-Mail an einen lokalen Admin."""
    app_name = _get_app_name()
    subject = f"Passwort zurücksetzen – {app_name}"

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Passwort zurücksetzen</h2>
            </div>
            <div style="padding:30px;">
                <p style="color:#1f2937;font-size:15px;">Hallo <strong>{username}</strong>,</p>
                <p style="color:#4b5563;font-size:14px;">
                    du hast eine Anfrage zum Zurücksetzen deines Passworts gestellt.<br>
                    Klicke auf den folgenden Button, um ein neues Passwort zu setzen:
                </p>
                <div style="text-align:center;margin:28px 0;">
                    <a href="{reset_url}"
                       style="background:linear-gradient(135deg,#E91E63,#C2185B);color:white;padding:14px 32px;border-radius:10px;text-decoration:none;font-weight:600;font-size:15px;display:inline-block;">
                        Passwort zurücksetzen
                    </a>
                </div>
                <div style="background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:14px 18px;border-radius:10px;font-size:13px;">
                    Dieser Link ist <strong>1 Stunde</strong> gültig und kann nur einmal verwendet werden.
                </div>
                <p style="color:#6b7280;font-size:13px;margin-top:20px;">
                    Falls du diese Anfrage nicht gestellt hast, kannst du diese E-Mail ignorieren.
                </p>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Passwort zurücksetzen – {app_name}

Hallo {username},

du hast eine Anfrage zum Zurücksetzen deines Passworts gestellt.
Klicke auf den folgenden Link (gültig 1 Stunde):

{reset_url}

Falls du diese Anfrage nicht gestellt hast, kannst du diese E-Mail ignorieren."""

    return send_email(to_email, subject, html, text)


# ── E-Mail-Styles ─────────────────────────────────────────────────────────────


def get_email_styles():
    return {
        "container": 'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#ffffff;',
        "header": "background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;border-radius:12px 12px 0 0;",
        "header_text": "color:white;margin:0;font-size:20px;font-weight:600;",
        "body": "padding:30px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;",
        "card": "background:#f8fafc;border-radius:10px;padding:20px;margin:20px 0;",
        "info_row": "display:flex;padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;",
        "label": "color:#E91E63;font-weight:600;min-width:100px;",
        "value": "color:#1f2937;",
        "success_box": "background:#dcfce7;border:1px solid #86efac;color:#166534;padding:16px 20px;border-radius:10px;text-align:center;margin-bottom:20px;",
        "warning_box": "background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:16px 20px;border-radius:10px;margin-bottom:20px;",
        "error_box": "background:#fee2e2;border:1px solid #fca5a5;color:#991b1b;padding:16px 20px;border-radius:10px;margin-bottom:20px;",
        "footer": "margin-top:24px;padding-top:20px;border-top:1px solid #e5e7eb;text-align:center;color:#6b7280;font-size:12px;",
    }


def _footer():
    return f"""
        <div style="margin-top:24px;padding-top:20px;border-top:1px solid #e5e7eb;text-align:center;color:#6b7280;font-size:12px;">
            Automatisch generiert am {datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")}<br>
            {_get_app_name()} – Buchungssystem
        </div>"""


def create_booking_notification_email(data):
    from dynamic_config import get_period

    teacher = data.get("teacher_name", "Unbekannt")
    teacher_class = data.get("teacher_class", "")
    date = format_date_german(data.get("date", ""))
    weekday = get_german_weekday(data.get("weekday", ""))
    period = data.get("period", "")
    p_info = get_period(period); period_time = f"{p_info.get('start', '?')} - {p_info.get('end', '?')}"
    offer = data.get("offer_label", "")
    offer_type = data.get("offer_type", "")

    students_json = data.get("students_json", "[]")
    students = (
        json.loads(students_json) if isinstance(students_json, str) else students_json
    )
    count = len(students)

    students_html = (
        "".join(
            [
                f'<div style="padding:8px 12px;background:white;border-radius:6px;margin:6px 0;">• {s["name"]} (Klasse {s["klasse"]})</div>'
                for s in students
            ]
        )
        or '<div style="color:#6b7280;">Keine Schüler*innen</div>'
    )

    subject = f"Neue Buchung: {offer} am {date}"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#3b82f6 0%,#1d4ed8 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Neue Buchung eingegangen</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">Datum:</strong> {weekday}, {date}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">Angebot:</strong> {offer} <span style="background:#3b82f6;color:white;padding:2px 10px;border-radius:12px;font-size:11px;margin-left:8px;">{offer_type.upper()}</span></div>
                    <div style="padding:16px;background:white;border-radius:8px;margin:12px 0;">
                        <strong style="color:#3b82f6;">Schüler*innen ({count}):</strong>
                        <div style="margin-top:10px;">{students_html}</div>
                    </div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Neue Buchung – {_get_app_name()}
Lehrkraft: {teacher} {f"({teacher_class})" if teacher_class else ""}
Datum: {weekday}, {date}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer} ({offer_type})
Schüler*innen ({count}): {", ".join([f"{s['name']} ({s['klasse']})" for s in students])}"""

    return subject, html, text


def send_booking_notification(data):
    """Sendet Buchungsbenachrichtigung an Admin."""
    admin_email = (
        _get_config_or_env("admin_email", "ADMIN_EMAIL", "")
        or _get_config_or_env("smtp_user", "SMTP_USER", "")
        or ""
    )
    if not admin_email:
        logger.warning(
            "[EMAIL] Keine Admin-E-Mail konfiguriert – Buchungsbenachrichtigung nicht gesendet."
        )
        return False
    subject, html, text = create_booking_notification_email(data)
    return send_email(admin_email, subject, html, text)


def create_user_confirmation_email(data):
    from dynamic_config import get_period

    teacher = data.get("teacher_name", "Unbekannt")
    teacher_class = data.get("teacher_class", "")
    date = format_date_german(data.get("date", ""))
    weekday = get_german_weekday(data.get("weekday", ""))
    period = data.get("period", "")
    p_info = get_period(period); period_time = f"{p_info.get('start', '?')} - {p_info.get('end', '?')}"
    offer = data.get("offer_label", "")
    offer_type = data.get("offer_type", "")

    students_json = data.get("students_json", "[]")
    students = (
        json.loads(students_json) if isinstance(students_json, str) else students_json
    )
    count = len(students)

    students_html = (
        "".join(
            [
                f'<div style="padding:8px 12px;background:white;border-radius:6px;margin:6px 0;">• {s["name"]} (Klasse {s["klasse"]})</div>'
                for s in students
            ]
        )
        or '<div style="color:#6b7280;">Keine Schüler*innen</div>'
    )

    subject = f"Buchung bestätigt: {offer} am {date}"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Buchung bestätigt</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#dcfce7;border:1px solid #86efac;color:#166534;padding:16px 20px;border-radius:10px;text-align:center;margin-bottom:20px;">
                    <strong>Deine Buchung wurde erfolgreich gespeichert!</strong>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">Datum:</strong> {weekday}, {date}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">Angebot:</strong> {offer} <span style="background:#E91E63;color:white;padding:2px 10px;border-radius:12px;font-size:11px;margin-left:8px;">{offer_type.upper()}</span></div>
                    <div style="padding:16px;background:white;border-radius:8px;margin:12px 0;">
                        <strong style="color:#E91E63;">Angemeldete Schüler*innen ({count}):</strong>
                        <div style="margin-top:10px;">{students_html}</div>
                    </div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Buchung bestätigt – {_get_app_name()}
Deine Buchung wurde erfolgreich gespeichert!
Lehrkraft: {teacher} {f"({teacher_class})" if teacher_class else ""}
Datum: {weekday}, {date}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer} ({offer_type})
Schüler*innen ({count}): {", ".join([f"{s['name']} ({s['klasse']})" for s in students])}"""

    return subject, html, text


def send_user_booking_confirmation(email, data):
    subject, html, text = create_user_confirmation_email(data)
    return send_email(email, subject, html, text)


def send_exclusive_pending_email(email, data):
    from dynamic_config import get_period

    students = data.get("students", [])
    if not students:
        return False
    student = students[0]
    student_name = student.get("name", "Unbekannt")
    student_class = student.get("klasse", "")
    teacher = data.get("teacher_name", "Unbekannt")
    teacher_class = data.get("teacher_class", "")
    date = format_date_german(data.get("date", ""))
    weekday = get_german_weekday(data.get("weekday", ""))
    period = data.get("period", "?")
    p_info = get_period(period); period_time = f"{p_info.get('start', '?')} - {p_info.get('end', '?')}"
    offer = data.get("offer_label", "Unbekannt")

    subject = "Einzelbuchung angefragt – Warte auf Freigabe"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Einzelbuchung angefragt</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>Deine Buchung wartet auf Freigabe</strong>
                    <p style="margin:10px 0 0 0;font-size:14px;">Du bekommst eine E-Mail, sobald deine Anfrage bearbeitet wurde.</p>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Datum:</strong> {weekday}, {date}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Angebot:</strong> {offer}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Schüler*in:</strong> {student_name} (Klasse {student_class})</div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Einzelbuchung angefragt – {_get_app_name()}
Deine Buchung wartet auf Freigabe.
Lehrkraft: {teacher} {f"({teacher_class})" if teacher_class else ""}
Datum: {weekday}, {date}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer}
Schüler*in: {student_name} (Klasse {student_class})"""

    return send_email(email, subject, html, text)


def send_exclusive_approved_email(
    teacher_email, teacher_name, student_name, date_str, period
):
    from dynamic_config import get_period

    p_info = get_period(period); period_time = f"{p_info.get('start', '?')} - {p_info.get('end', '?')}"
    date_formatted = format_date_german(date_str)
    subject = f"Einzelbuchung genehmigt – {_get_app_name()}"

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Einzelbuchung genehmigt!</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#dcfce7;border:1px solid #86efac;color:#166534;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>Hallo {teacher_name}!</strong>
                    <p style="margin:10px 0 0 0;">Deine exklusive Einzelbuchung wurde <strong>genehmigt</strong>.</p>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #22c55e;"><strong style="color:#E91E63;">Datum:</strong> {date_formatted}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #22c55e;"><strong style="color:#E91E63;">Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #22c55e;"><strong style="color:#E91E63;">Schüler*in:</strong> {student_name}</div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Einzelbuchung genehmigt – {_get_app_name()}
Hallo {teacher_name}!
Deine exklusive Einzelbuchung wurde genehmigt.
Datum: {date_formatted}
Zeit: {period}. Stunde ({period_time} Uhr)
Schüler*in: {student_name}"""

    return send_email(teacher_email, subject, html, text)


def send_exclusive_rejected_email(
    teacher_email, teacher_name, student_name, date_str, period, rejection_reason=None
):
    from dynamic_config import get_period

    p_info = get_period(period); period_time = f"{p_info.get('start', '?')} - {p_info.get('end', '?')}"
    date_formatted = format_date_german(date_str)
    subject = f"Einzelbuchung abgelehnt – {_get_app_name()}"
    reason_html = (
        f'<p style="margin:10px 0 0 0;font-size:14px;">Grund: {rejection_reason}</p>'
        if rejection_reason
        else ""
    )
    reason_text = f"\nGrund: {rejection_reason}" if rejection_reason else ""

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#ef4444 0%,#b91c1c 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Einzelbuchung abgelehnt</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#fee2e2;border:1px solid #fca5a5;color:#991b1b;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>Hallo {teacher_name},</strong>
                    <p style="margin:10px 0 0 0;">deine exklusive Einzelbuchung wurde leider <strong>abgelehnt</strong>.</p>
                    {reason_html}
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">Datum:</strong> {date_formatted}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">Schüler*in:</strong> {student_name}</div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Einzelbuchung abgelehnt – {_get_app_name()}
Hallo {teacher_name},
deine exklusive Einzelbuchung wurde leider abgelehnt.{reason_text}
Datum: {date_formatted}
Zeit: {period}. Stunde ({period_time} Uhr)
Schüler*in: {student_name}"""

    return send_email(teacher_email, subject, html, text)


def send_booking_removed_due_to_exclusive(
    teacher_email, teacher_name, booking_info, exclusive_info
):
    """Informiert eine Lehrkraft, dass ihre Buchung wegen einer exklusiven Reservierung storniert wurde."""
    date_formatted = format_date_german(booking_info.get("date", ""))
    period = booking_info.get("period", "?")
    offer_label = booking_info.get("offer_label", "gebuchten Slot")
    exclusive_teacher = exclusive_info.get("teacher", "eine andere Lehrkraft")
    exclusive_student = exclusive_info.get("student", "eine Schüler*in")

    subject = f"Buchung storniert – {_get_app_name()}"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#f59e0b 0%,#d97706 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Buchung storniert</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>Hallo {teacher_name},</strong>
                    <p style="margin:10px 0 0 0;">deine Buchung musste storniert werden, weil der Slot exklusiv für <strong>{exclusive_student}</strong> durch <strong>{exclusive_teacher}</strong> reserviert wurde.</p>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Datum:</strong> {date_formatted}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Zeit:</strong> {period}. Stunde</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">Angebot:</strong> {offer_label}</div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Buchung storniert – {_get_app_name()}
Hallo {teacher_name},
deine Buchung für {offer_label} am {date_formatted} in der {period}. Stunde musste storniert werden,
weil der Slot exklusiv für {exclusive_student} durch {exclusive_teacher} reserviert wurde."""

    return send_email(teacher_email, subject, html, text)
