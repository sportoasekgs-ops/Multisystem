"""
E-Mail-Service für SportOase – ausschließlich SMTP (kein Resend).
Konfiguration wird aus der Datenbank geladen (Setup-Wizard / Admin-CMS → SMTP-Tab).
"""
import json
import logging
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import ADMIN_EMAIL


logger = logging.getLogger(__name__)


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────

def format_date_german(date_str):
    """Konvertiert YYYY-MM-DD zu TT.MM.JJJJ"""
    try:
        if '-' in str(date_str):
            parts = str(date_str).split('-')
            if len(parts) == 3:
                return f"{parts[2]}.{parts[1]}.{parts[0]}"
    except Exception:
        pass
    return str(date_str)


def get_german_weekday(weekday_abbr):
    """Konvertiert englische Wochentag-Abkürzung zu deutschem Namen"""
    weekday_map = {
        'Mon': 'Montag', 'Tue': 'Dienstag', 'Wed': 'Mittwoch',
        'Thu': 'Donnerstag', 'Fri': 'Freitag', 'Sat': 'Samstag', 'Sun': 'Sonntag'
    }
    return weekday_map.get(weekday_abbr, weekday_abbr)


# ── SMTP-Konfiguration aus Datenbank ─────────────────────────────────────────

def get_smtp_config():
    """Lädt SMTP-Konfiguration aus der Datenbank."""
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


def is_smtp_configured():
    """Gibt True zurück wenn alle SMTP-Pflichtfelder konfiguriert sind."""
    host, _, user, password, _, _ = get_smtp_config()
    return bool(host and user and password)


# ── Kern-Sendefunktion ────────────────────────────────────────────────────────

def send_email(to_email, subject, body_html, body_text=None):
    """
    Sendet eine E-Mail über SMTP.
    Konfiguration wird aus der Datenbank geladen.
    Im Demo-Modus wird nichts verschickt (nur Log-Ausgabe).
    """
    try:
        from demo_mode import is_demo_mode, send_demo_email_log
        if is_demo_mode():
            return send_demo_email_log(to_email, subject)
    except Exception:
        pass

    host, port, user, password, tls_mode, from_addr = get_smtp_config()

    if not host or not user or not password:
        logger.warning(
            f"[EMAIL] SMTP nicht konfiguriert – E-Mail an {to_email} nicht gesendet. "
            "Bitte SMTP im Admin-CMS (Tab 'SMTP') einrichten."
        )
        return False

    try:
        import socket as _socket
        # IPv4 erzwingen (verhindert "Network is unreachable" bei IPv6-Problemen auf Render/Cloud-Hosts)
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

        logger.info(f"[EMAIL] Erfolgreich gesendet an {to_email} (Betreff: {subject})")
        return True

    except Exception as e:
        logger.error(f"[EMAIL] FEHLER beim Versand an {to_email}: {e}")
        return False


# Alias für Rückwärtskompatibilität (alte Aufrufer)
send_email_resend = send_email
send_email_smtp   = send_email


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


# ── E-Mail-Templates & Versand-Funktionen ────────────────────────────────────

def _footer():
    return f"""
        <div style="margin-top:24px;padding-top:20px;border-top:1px solid #e5e7eb;text-align:center;color:#6b7280;font-size:12px;">
            Automatisch generiert am {datetime.now().strftime('%d.%m.%Y um %H:%M Uhr')}<br>
            SportOase Buchungssystem
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

    subject = f"📚 Neue Buchung: {offer} am {date}"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#3b82f6 0%,#1d4ed8 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">📚 Neue Buchung eingegangen</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">👤 Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">📅 Datum:</strong> {weekday}, {date}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #3b82f6;"><strong style="color:#3b82f6;">📋 Angebot:</strong> {offer} <span style="background:#3b82f6;color:white;padding:2px 10px;border-radius:12px;font-size:11px;margin-left:8px;">{offer_type.upper()}</span></div>
                    <div style="padding:16px;background:white;border-radius:8px;margin:12px 0;">
                        <strong style="color:#3b82f6;">👥 Schüler*innen ({count}):</strong>
                        <div style="margin-top:10px;">{students_html}</div>
                    </div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Neue Buchung – SportOase
Lehrkraft: {teacher} {f"({teacher_class})" if teacher_class else ""}
Datum: {weekday}, {date}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer} ({offer_type})
Schüler*innen ({count}): {', '.join([f"{s['name']} ({s['klasse']})" for s in students])}"""

    return subject, html, text


def send_booking_notification(data):
    subject, html, text = create_booking_notification_email(data)
    return send_email(ADMIN_EMAIL, subject, html, text)


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

    subject = f"✅ Buchung bestätigt: {offer} am {date}"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">✅ Buchung bestätigt</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#dcfce7;border:1px solid #86efac;color:#166534;padding:16px 20px;border-radius:10px;text-align:center;margin-bottom:20px;">
                    <strong>🎉 Deine Buchung wurde erfolgreich gespeichert!</strong>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">👤 Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">📅 Datum:</strong> {weekday}, {date}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #E91E63;"><strong style="color:#E91E63;">📋 Angebot:</strong> {offer} <span style="background:#E91E63;color:white;padding:2px 10px;border-radius:12px;font-size:11px;margin-left:8px;">{offer_type.upper()}</span></div>
                    <div style="padding:16px;background:white;border-radius:8px;margin:12px 0;">
                        <strong style="color:#E91E63;">👥 Angemeldete Schüler*innen ({count}):</strong>
                        <div style="margin-top:10px;">{students_html}</div>
                    </div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Buchung bestätigt – SportOase
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

    subject = "⏳ Einzelbuchung angefragt – Warte auf Freigabe"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">⏳ Einzelbuchung angefragt</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>⚠️ Deine Buchung wartet auf Freigabe</strong>
                    <p style="margin:10px 0 0 0;font-size:14px;">Du bekommst eine E-Mail, sobald deine Anfrage bearbeitet wurde.</p>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">👤 Lehrkraft:</strong> {teacher} {f"({teacher_class})" if teacher_class else ""}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">📅 Datum:</strong> {weekday}, {date}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">📋 Angebot:</strong> {offer}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #f59e0b;"><strong style="color:#E91E63;">👤 Schüler*in:</strong> {student_name} (Klasse {student_class})</div>
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Einzelbuchung angefragt – SportOase
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
    subject        = "✅ Einzelbuchung genehmigt – SportOase"

    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">🎉 Einzelbuchung genehmigt!</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#dcfce7;border:1px solid #86efac;color:#166534;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>Hallo {teacher_name}!</strong>
                    <p style="margin:10px 0 0 0;">Deine exklusive Einzelbuchung wurde <strong>genehmigt</strong>. 🎉</p>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #22c55e;"><strong style="color:#E91E63;">📅 Datum:</strong> {date_formatted}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #22c55e;"><strong style="color:#E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #22c55e;"><strong style="color:#E91E63;">👤 Schüler*in:</strong> {student_name}</div>
                </div>
                <div style="background:#dbeafe;border:1px solid #93c5fd;color:#1e40af;padding:14px 18px;border-radius:10px;margin-top:20px;font-size:14px;">
                    💡 Der Slot ist jetzt vollständig für deine*n Schüler*in reserviert.
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Einzelbuchung genehmigt – SportOase
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

    reason_html = ""
    reason_text = ""
    if rejection_reason:
        reason_html = f"""
            <div style="background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:14px 18px;border-radius:10px;margin:16px 0;">
                <strong>💬 Begründung:</strong><br>
                <span style="display:block;margin-top:8px;">{rejection_reason}</span>
            </div>"""
        reason_text = f"\nBegründung:\n{rejection_reason}\n"

    subject = "❌ Einzelbuchung abgelehnt – SportOase"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">Einzelbuchung abgelehnt</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#fee2e2;border:1px solid #fca5a5;color:#991b1b;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>Hallo {teacher_name},</strong>
                    <p style="margin:10px 0 0 0;">Leider wurde deine exklusive Einzelbuchung <strong>abgelehnt</strong>.</p>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">📅 Datum:</strong> {date_formatted}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">👤 Schüler*in:</strong> {student_name}</div>
                </div>
                {reason_html}
                <div style="background:#f0f9ff;border:1px solid #bae6fd;color:#0369a1;padding:14px 18px;border-radius:10px;margin-top:16px;font-size:14px;">
                    💡 Du kannst deine*n Schüler*in gerne regulär (ohne exklusive Reservierung) anmelden, falls Plätze verfügbar sind.
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Einzelbuchung abgelehnt – SportOase
Hallo {teacher_name},
Leider wurde deine exklusive Einzelbuchung abgelehnt.
Datum: {date_formatted}
Zeit: {period}. Stunde ({period_time} Uhr)
Schüler*in: {student_name}{reason_text}"""

    return send_email(teacher_email, subject, html, text)


def send_booking_removed_due_to_exclusive(teacher_email, teacher_name, booking_info, exclusive_info):
    from config import PERIOD_TIMES
    date_formatted = format_date_german(booking_info.get('date', ''))
    period         = booking_info.get('period', '?')
    period_time    = PERIOD_TIMES.get(period, "")
    students       = booking_info.get('students', [])
    offer          = booking_info.get('offer_label', 'Unbekannt')

    students_html = "".join([
        f'<div style="padding:6px 10px;background:white;border-radius:4px;margin:4px 0;">• {s.get("name","?")} (Klasse {s.get("klasse","?")})</div>'
        for s in students
    ]) or '<div>Keine Schüler*innen</div>'
    students_list = ", ".join([f"{s.get('name','?')} ({s.get('klasse','?')})" for s in students])

    subject = "⚠️ Buchung storniert – SportOase"
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8"></head>
    <body style="margin:0;padding:20px;background:#f3f4f6;">
        <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;max-width:600px;margin:0 auto;background:#fff;border-radius:12px;overflow:hidden;box-shadow:0 4px 6px rgba(0,0,0,.1);">
            <div style="background:linear-gradient(135deg,#E91E63 0%,#C2185B 100%);padding:24px 30px;">
                <h2 style="color:white;margin:0;font-size:20px;">⚠️ Buchung storniert</h2>
            </div>
            <div style="padding:30px;">
                <div style="background:#fef3c7;border:1px solid #fcd34d;color:#92400e;padding:16px 20px;border-radius:10px;margin-bottom:20px;">
                    <strong>Hallo {teacher_name},</strong>
                    <p style="margin:10px 0 0 0;">Leider wurde deine Buchung automatisch storniert, da eine <strong>exklusive Einzelbuchung</strong> für denselben Slot genehmigt wurde.</p>
                </div>
                <div style="background:#f8fafc;border-radius:10px;padding:20px;">
                    <h4 style="margin:0 0 15px 0;color:#E91E63;font-size:14px;">📋 Deine stornierte Buchung:</h4>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">📅 Datum:</strong> {date_formatted}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">⏰ Zeit:</strong> {period}. Stunde ({period_time} Uhr)</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;"><strong style="color:#E91E63;">📚 Angebot:</strong> {offer}</div>
                    <div style="padding:12px 16px;background:white;border-radius:8px;margin:8px 0;border-left:4px solid #ef4444;">
                        <strong style="color:#E91E63;">👥 Schüler*innen:</strong>
                        <div style="margin-top:8px;">{students_html}</div>
                    </div>
                </div>
                <div style="background:#f0f9ff;border:1px solid #bae6fd;color:#0369a1;padding:14px 18px;border-radius:10px;margin-top:16px;font-size:14px;">
                    💡 Bitte buche deine Schüler*innen für einen anderen Slot neu ein.
                </div>
                {_footer()}
            </div>
        </div>
    </body></html>"""

    text = f"""Buchung storniert – SportOase
Hallo {teacher_name},
Deine Buchung wurde automatisch storniert (exklusive Einzelbuchung genehmigt).
Datum: {date_formatted}
Zeit: {period}. Stunde ({period_time} Uhr)
Angebot: {offer}
Schüler*innen: {students_list}
Bitte buche deine Schüler*innen für einen anderen Slot neu ein."""

    return send_email(teacher_email, subject, html, text)
