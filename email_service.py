"""
E-Mail-Service für das Buchungssystem.
Unterstützt zwei Provider:
  - SMTP (Standard): Jeder SMTP-Server, inkl. Office365, Schulserver etc.
  - Resend: Cloud-E-Mail über https://resend.com (API-Key erforderlich)
Konfiguration wird aus der Datenbank geladen (Setup-Wizard / Admin-CMS).
"""
import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import ADMIN_EMAIL


logger = logging.getLogger(__name__)


def _get_app_name():
    try:
        from system_config import get_config
        name = get_config('school_name', '').strip()
        return name if name else 'Buchungssystem'
    except Exception:
        return 'Buchungssystem'


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def format_date_german(date_str):
    try:
        if '-' in str(date_str):
            parts = str(date_str).split('-')
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return str(date_str)


def get_german_weekday(weekday_abbr):
    weekday_map = {
        'Mon': 'Montag', 'Tue': 'Dienstag', 'Wed': 'Mittwoch',
        'Thu': 'Donnerstag', 'Fri': 'Freitag', 'Sat': 'Samstag', 'Sun': 'Sonntag'
    }
    return weekday_map.get(weekday_abbr, weekday_abbr)


# ── Provider-Konfiguration ────────────────────────────────────────────────────

def get_email_provider():
    """Gibt den konfigurierten E-Mail-Provider zurück: 'smtp' oder 'resend'."""
    try:
        from system_config import get_config
        return get_config('email_provider', 'smtp').strip().lower()
    except Exception:
        return 'smtp'


def get_smtp_config():
    try:
        from system_config import get_config
        host     = get_config('smtp_host', '').strip()
        port     = int(get_config('smtp_port', '587') or 587)
        user     = get_config('smtp_user', '').strip()
        password = get_config('smtp_pass', '').strip()
        tls_mode = get_config('smtp_tls', 'starttls').strip()
        from_addr = get_config('smtp_from', '').strip() or user
        return host, port, user, password, tls_mode, from_addr
    except Exception as e:
        logger.error(f"[EMAIL] Fehler beim Laden der SMTP-Konfiguration: {e}")
        return '', 587, '', '', 'starttls', ''


def get_resend_config():
    try:
        from system_config import get_config
        api_key  = get_config('resend_api_key', '').strip()
        from_addr = get_config('resend_from', '').strip()
        return api_key, from_addr
    except Exception:
        return '', ''


def is_email_configured():
    provider = get_email_provider()
    if provider == 'resend':
        api_key, from_addr = get_resend_config()
        return bool(api_key and from_addr)
    else:
        host, _, user, password, _, _ = get_smtp_config()
        return bool(host and user and password)


# Alias für alte Aufrufer
def is_smtp_configured():
    return is_email_configured()


# ── Kern-Sendefunktionen ──────────────────────────────────────────────────────

def _send_via_resend(to_email, subject, body_html, body_text=None):
    """Sendet E-Mail über Resend HTTP-API."""
    import urllib.request
    import urllib.error

    api_key, from_addr = get_resend_config()
    if not api_key or not from_addr:
        logger.warning("[EMAIL] Resend nicht konfiguriert – kein API-Key oder Absender.")
        return False

    payload = {
        'from': from_addr,
        'to': [to_email],
        'subject': subject,
        'html': body_html,
    }
    if body_text:
        payload['text'] = body_text

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        'https://api.resend.com/emails',
        data=data,
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST'
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
        body = e.read().decode('utf-8', errors='replace')
        logger.error(f"[EMAIL] Resend HTTP-Fehler {e.code}: {body}")
        return False
    except Exception as e:
        logger.error(f"[EMAIL] Resend Fehler: {e}")
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
            ipv4 = _socket.getaddrinfo(host, port, _socket.AF_INET, _socket.SOCK_STREAM)[0][4][0]
        except Exception:
            ipv4 = host

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = from_addr
        msg['To']      = to_email

        if body_text:
            msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))

        if tls_mode == 'ssl':
            with smtplib.SMTP_SSL(ipv4, port, timeout=15) as server:
                server.login(user, password)
                server.sendmail(from_addr, [to_email], msg.as_string())
        else:
            with smtplib.SMTP(ipv4, port, timeout=15) as server:
                server.ehlo()
                if tls_mode == 'starttls':
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
    if provider == 'resend':
        return _send_via_resend(to_email, subject, body_html, body_text)
    else:
        return _send_via_smtp(to_email, subject, body_html, body_text)


# Aliases für Rückwärtskompatibilität
send_email_resend = send_email
send_email_smtp   = send_email


def send_password_reset_email(to_email, username, reset_url):
    """Sendet eine Passwort-Reset-E-Mail an einen lokalen Admin."""
    app_name = _get_app_name()
    subject  = f"Passwort zurücksetzen – {app_name}"

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
        'container':   'font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#ffffff;',
        'header':      'background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;border-radius:12px 12px 0 0;',
        'header_text': 'color:white;margin:0;font-size:20px;font-weight:600;',
        'body':        'padding:30px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 12px 12px;',
        'card':        'background:#f8fafc;border-radius:10px;padding:20px;margin:20px 0;',
        'info_row':    'display:flex;padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;',
        'label':       'color:#E91E63;font-weight:600;min-width:100px;',
        'value':       'color:#1f2937;',
        'success_box': 'background:#dcfce7;border:1px solid #86efac;color:#166534;padding:16px 20px;border-radius:10px;text-align:center;margin-bottom:20px;',
        'warning_box': 'background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:16px 20px;border-radius:10px;margin-bottom:20px;',
        'error_box':   'background:#fee2e2;border:1px solid #fca5a5;color:#991b1b;padding:16px 20px;border-radius:10px;margin-bottom:20px;',
        'footer':      'margin-top:24px;padding-top:20px;border-top:1px solid #e5e7eb;text-align:center;color:#6b7280;font-size:12px;',
    }


def _footer():
    return f"""
        <div style="margin-top:24px;padding-top:20px;border-top:1px solid #e5e7eb;text-align:center;color:#6b7280;font-size:12px;">
            Automatisch generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}<br>
            {_get_app_name()} – Buchungssystem
        </div>"""


def create_booking_notification_email(data):
    from config import PERIOD_TIMES
    teacher       = data.get("teacher_name", "Unbekannt")
    teacher_class = data.get("teacher_class", "")
    date          = format_date_german(data.get("date", ""))
    weekday       = get_german_weekday(data.get("weekday", ""))
    period        = data.get("period", "")
    period_time   = PERIOD_TIMES.get(period, "")
    offer         = data.get("offer_label", "")
    offer_type    = data.get("offer_type", "")

    students_json = data.get("students_json", "[]")
    students      = json.loads(students_json) if isinstance(students_json, str) else students_json
    count         = len(students)

    students_html = "".join([
        f'<div style="padding:8px 12px;background:white;border-radius:6px;margin:6px 0;">• {s["name"]} (Klasse {s["klasse"]})</div>'
        for s in students
    ]) or '<div style="color:#6b7280;">Keine Schüler*innen</div>'

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
Schüler*innen ({count}): {', '.join([f"{s['name']} ({s['klasse']})" for s in students])}"""

    return subject, html, text


def send_booking_notification(data):
    """Sendet Buchungsbenachrichtigung an Admin."""
    try:
        from system_config import get_config
        admin_email = (
            get_config('admin_email', '').strip()
            or get_config('smtp_user', '').strip()
            or ADMIN_EMAIL
        )
    except Exception:
        admin_email = ADMIN_EMAIL
    if not admin_email:
        logger.warning("[EMAIL] Keine Admin-E-Mail konfiguriert – Buchungsbenachrichtigung nicht gesendet.")
        return False
    subject, html, text = create_booking_notification_email(data)
    return send_email(admin_email, subject, html, text)


def create_user_confirmation_email(data):
    from config import PERIOD_TIMES
    teacher       = data.get("teacher_name", "Unbekannt")
    teacher_class = data.get("teacher_class", "")
    date          = format_date_german(data.get("date", ""))
    weekday       = get_german_weekday(data.get("weekday", ""))
    period        = data.get("period", "")
    period_time   = PERIOD_TIMES.get(period, "")
    offer         = data.get("offer_label", "")
    offer_type    = data.get("offer_type", "")

    students_json = data.get("students_json", "[]")
    students      = json.loads(students_json) if isinstance(students_json, str) else students_json
    count         = len(students)

    students_html = "".join([
        f'<div style="padding:8px 12px;background:white;border-radius:6px;margin:6px 0;">• {s["name"]} (Klasse {s["klasse"]})</div>'
        for s in students
    ]) or '<div style="color:#6b7280;">Keine Schüler*innen</div>'

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
Schüler*innen ({count}): {', '.join([f"{s['name']} ({s['klasse']})" for s in students])}"""

    return subject, html, text


def send_user_booking_confirmation(email, data):
    subject, html, text = create_user_confirmation_email(data)
    return send_email(email, subject, html, text)


def send_exclusive_pending_email(email, data):
    from config import PERIOD_TIMES
    students = data.get('students', [])
    if not students:
        return False
    student       = students[0]
    student_name  = student.get('name', 'Unbekannt')
    student_class = student.get('klasse', '')
    teacher       = data.get('teacher_name', 'Unbekannt')
    teacher_class = data.get('teacher_class', '')
    date          = format_date_german(data.get('date', ''))
    weekday       = get_german_weekday(data.get('weekday', ''))
    period        = data.get('period', '?')
    period_time   = PERIOD_TIMES.get(period, '')
    offer         = data.get('offer_label', 'Unbekannt')

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


def send_exclusive_approved_email(teacher_email, teacher_name, student_name, date_str, period):
    from config import PERIOD_TIMES
    period_time    = PERIOD_TIMES.get(period, "")
    date_formatted = format_date_german(date_str)
    subject        = f"Einzelbuchung genehmigt – {_get_app_name()}"

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


def send_exclusive_rejected_email(teacher_email, teacher_name, student_name, date_str, period, rejection_reason=None):
    from config import PERIOD_TIMES
    period_time    = PERIOD_TIMES.get(period, "")
    date_formatted = format_date_german(date_str)
    subject        = f"Einzelbuchung abgelehnt – {_get_app_name()}"
    reason_html    = f'<p style="margin:10px 0 0 0;font-size:14px;">Grund: {rejection_reason}</p>' if rejection_reason else ''
    reason_text    = f'\nGrund: {rejection_reason}' if rejection_reason else ''

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
